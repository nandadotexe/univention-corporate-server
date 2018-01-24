/*
 * Copyright 2016-2017 Univention GmbH
 *
 * http://www.univention.de/
 *
 * All rights reserved.
 *
 * The source code of this program is made available
 * under the terms of the GNU Affero General Public License version 3
 * (GNU AGPL V3) as published by the Free Software Foundation.
 *
 * Binary versions of this program provided by Univention to you as
 * well as other copyrighted, protected or trademarked materials like
 * Logos, graphics, fonts, specific documentations and configurations,
 * cryptographic keys etc. are subject to a license agreement between
 * you and Univention and not subject to the GNU AGPL V3.
 *
 * In the case you use this program under the terms of the GNU AGPL V3,
 * the program is provided in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 * GNU Affero General Public License for more details.
 *
 * You should have received a copy of the GNU Affero General Public
 * License with the Debian GNU/Linux or Univention distribution in file
 * /usr/share/common-licenses/AGPL-3; if not, see
 * <http://www.gnu.org/licenses/>.
 */
/*global define*/

define([
	"dojo/_base/declare",
	"dojo/_base/lang",
	"dojo/_base/array",
	"dojo/Deferred",
	"dojo/aspect",
	"dojo/on",
	"dojo/dom",
	"dojo/dom-class",
	"dojo/promise/all",
	"dojox/string/sprintf",
	"dojox/widget/Standby",
	"dijit/registry",
	"dijit/Dialog",
	"dijit/Tooltip",
	"umc/tools",
	"umc/store",
	"umc/json",
	"umc/dialog",
	"umc/widgets/Button",
	"umc/widgets/Form",
	"umc/widgets/Wizard",
	"umc/widgets/ContainerWidget",
	"umc/widgets/MultiInput",
	"umc/modules/udm/cache",
	"put-selector/put",
	"./PortalCategory",
	"umc/i18n/tools",
	// portal.json -> contains entries of this portal as specified in the LDAP directory
	"umc/json!/univention/portal/portal.json",
	// apps.json -> contains all locally installed apps
	"umc/json!/univention/portal/apps.json",
	"umc/i18n!portal"
], function(declare, lang, array, Deferred, aspect, on, dom, domClass, all, sprintf, Standby, registry, Dialog, Tooltip, tools, store, json, dialog, Button, Form, Wizard, ContainerWidget, MultiInput, cache, put, PortalCategory, i18nTools, portalContent, installedApps, _) {

	// convert IPv6 addresses to their canonical form:
	//   ::1:2 -> 0000:0000:0000:0000:0000:0000:0001:0002
	//   1111:2222::192.168.1.1 -> 1111:2222:0000:0000:0000:0000:c0a8:0101
	// but this can also be used for IPv4 addresses:
	//   192.168.1.1 -> c0a8:0101
	var canonicalizeIPAddress = function(address) {
		if (tools.isFQDN(address)) {
			return address;
		}

		// remove leading and trailing ::
		address = address.replace(/^:|:$/g, '');

		// split address into 2-byte blocks
		var parts = address.split(':');

		// replace IPv4 address inside IPv6 address
		if (tools.isIPv4Address(parts[parts.length - 1])) {
			// parse bytes of IPv4 address
			var ipv4Parts = parts[parts.length - 1].split('.');
			for (var i = 0; i < 4; ++i) {
				var byte = parseInt(ipv4Parts[i], 10);
				ipv4Parts[i] = sprintf('%02x', byte);
			}

			// remove IPv4 address and append bytes in IPv6 style
			parts.splice(-1, 1);
			parts.push(ipv4Parts[0] + ipv4Parts[1]);
			parts.push(ipv4Parts[2] + ipv4Parts[3]);
		}

		// expand grouped zeros "::"
		var iEmptyPart = array.indexOf(parts, '');
		if (iEmptyPart >= 0) {
			parts.splice(iEmptyPart, 1);
			while (parts.length < 8) {
				parts.splice(iEmptyPart, 0, '0');
			}
		}

		// add leading zeros
		parts = array.map(parts, function(ipart) {
			return sprintf('%04s', ipart);
		});

		return parts.join(':');
	};

	var getAnchorElement = function(uri) {
		var _linkElement = document.createElement('a');
		_linkElement.setAttribute('href', uri);
		return _linkElement;
	};

	var getURIHostname = function(uri) {
		return getAnchorElement(uri).hostname.replace(/^\[|\]$/g, '');
	};

	var getURIProtocol = function(uri) {
		return getAnchorElement(uri).protocol;
	};

	var _getAddressType = function(link) {
		if (tools.isFQDN(link)) {
			return 'fqdn';
		}
		if (tools.isIPv6Address(link)) {
			return 'ipv6';
		}
		if (tools.isIPv4Address(link)) {
			return 'ipv4';
		}
		return '';
	};

	var _getProtocolType = function(link) {
		if (link.indexOf('//') === 0) {
			return 'relative';
		}
		if (link.indexOf('https') === 0) {
			return 'https';
		}
		if (link.indexOf('http') === 0) {
			return 'http';
		}
		return '';
	};

	var _regExpRelativeLink = /^\/([^/].*)?$/;
	var _isRelativeLink = function(link) {
		return _regExpRelativeLink.test(link);
	};

	// return 1 if link is a relative link, otherwise 0
	var _scoreRelativeURI = function(link) {
		return link.indexOf('/') === 0 && link.indexOf('//') !== 0 ? 1 : 0;
	};

	// score according to the following matrix
	//               Browser address bar
	//              | FQDN | IPv4 | IPv6
	//       / FQDN |  4   |  1   |  1
	// link <  IPv4 |  2   |  4   |  2
	//       \ IPv6 |  1   |  2   |  4
	var _scoreAddressType = function(browserLinkType, linkType) {
		var scores = {
			fqdn: { fqdn: 4, ipv4: 2, ipv6: 1 },
			ipv4: { fqdn: 1, ipv4: 4, ipv6: 2 },
			ipv6: { fqdn: 1, ipv4: 2, ipv6: 4 }
		};
		try {
			return scores[browserLinkType][linkType] || 0;
		} catch(err) {
			return 0;
		}
	};

	// score according to the following matrix
	//              Browser address bar
	//               | https | http
	//       / "//"  |   4   |  4
	// link <  https |   2   |  1
	//       \ http  |   1   |  2
	var _scoreProtocolType = function(browserProtocolType, protocolType) {
		var scores = {
			https: { relative: 4, https: 2, http: 1 },
			http:  { relative: 4, https: 1, http: 2 }
		};
		try {
			return scores[browserProtocolType][protocolType] || 0;
		} catch(err) {
			return 0;
		}
	};

	// score is computed as the number of matched characters
	var _scoreAddressMatch = function(browserHostname, hostname, matchBackwards) {
		if (matchBackwards) {
			// match not from the beginning of the string, but from the end
			browserHostname = browserHostname.split('').reverse().join('');
			hostname = hostname.split('').reverse().join('');
		}
		var i;
		for (i = 0; i < Math.min(browserHostname.length, hostname.length); ++i) {
			if (browserHostname[i] !== hostname[i]) {
				break;
			}
		}
		return i;
	};

	// Given the browser URI and a list of links, each link is ranked via a
	// multi-part score. This effectively allows to chose the best matching
	// link w.r.t. the browser session.
	var _rankLinks = function(browserURI, links) {
		// score all links
		var browserHostname = getURIHostname(browserURI);
		var browserLinkType = _getAddressType(browserHostname);
		var canonicalizedBrowserHostname = canonicalizeIPAddress(browserHostname);
		var browserProtocolType = _getProtocolType(browserURI);
		links = array.map(links, function(ilink) {
			var linkHostname = getURIHostname(ilink);
			var canonicalizedLinkHostname = canonicalizeIPAddress(linkHostname);
			var linkType = _getAddressType(linkHostname);
			var linkProtocolType = _getProtocolType(ilink);
			var addressMatchScore = 0;
			if (browserLinkType === linkType) {
				// FQDNs are matched backwards, IP addresses forwards
				var matchBackwards = linkType === 'fqdn' ? true : false;
				addressMatchScore = _scoreAddressMatch(canonicalizedBrowserHostname, canonicalizedLinkHostname, matchBackwards);
			}
			return {
				scores: [
					_scoreRelativeURI(ilink),
					addressMatchScore,
					_scoreAddressType(browserLinkType, linkType),
					_scoreProtocolType(browserProtocolType, linkProtocolType)
				],
				link: ilink
			};
		});

		function _cmp(x, y) {
			for (var i = 0; i < x.scores.length; ++i) {
				if (x.scores[i] === y.scores[i]) {
					continue;
				}
				if (x.scores[i] < y.scores[i]) {
					return 1;
				}
				return -1;
			}
		}

		// sort links descending w.r.t. their scores
		links.sort(_cmp);

		// return the best match
		return links;
	};

	var getHighestRankedLink = function(browserURI, links) {
		return _rankLinks(browserURI, links)[0].link || '#';
	};

	var getLocalLinks = function(browserHostname, serverFQDN, links) {
		// check whether there is any relative link
		var relativeLinks = array.filter(links, function(ilink) {
			return _isRelativeLink(ilink);
		});
		if (relativeLinks.length) {
			return relativeLinks;
		}

		// check whether there is a link containing the FQDN of the local server
		var localLinks = [];
		array.forEach(links, function(ilink) {
			var uri = getAnchorElement(ilink);
			if (uri.hostname === serverFQDN) {
				uri.hostname = browserHostname;
				localLinks.push(uri.href);
			}
		});
		return localLinks;
	};

	var getFQDNHostname = function(links) {
		// check for any relative link
		var hasRelativeLink = array.some(links, function(ilink) {
			return _isRelativeLink(ilink);
		});
		if (hasRelativeLink) {
			return tools.status('fqdn');
		}

		// look for any links that refer to an FQDN
		var fqdnLinks = [];
		array.forEach(links, function(ilink) {
			var linkHostname = getURIHostname(ilink);
			if (tools.isFQDN(linkHostname)) {
				fqdnLinks.push(linkHostname);
			}
		});
		if (fqdnLinks.length) {
			return fqdnLinks[0];
		}
		return null;
	};

	var _getLogoName = function(logo) {
		if (logo) {
			if (hasAbsolutePath(logo)) {
				// make sure that the path starts with http[s]:// ...
				// just to make tools.getIconClass() leaving the URL untouched
				logo = window.location.origin + logo;

				if (!hasImageSuffix(logo)) {
					// an URL starting with http[s]:// needs also to have a .svg suffix
					logo = logo + '.svg';
				}
			}
		}
		return logo;
	};

	var _regHasImageSuffix = /\.(svg|jpg|jpeg|png|gif)$/i;
	var hasImageSuffix = function(path) {
		return path && _regHasImageSuffix.test(path);
	};

	var hasAbsolutePath = function(path) {
		return path && path.indexOf('/') === 0;
	};

	// adjust white styling of header via extra CSS class
	if (lang.getObject('portal.fontColor', false, portalContent) === 'white') {
		try {
			domClass.add(dom.byId('umcHeader'), 'umcWhiteIcons');
		} catch(err) { }
	}

	// remove display=none from header
	try {
		domClass.remove(dom.byId('umcHeaderRight'), 'dijitDisplayNone');
	} catch(err) { }

	var locale = i18nTools.defaultLang().replace(/-/, '_');
	return {
		portalCategories: null,
		editMode: false,

		_initStyling: function() {
			on(dom.byId('portalLogo'), 'click', lang.hitch(this, function() {
				if (!this.editMode) {
					return;
				}

				// this._editSinglePortalProp('logo');
				this._editPortalProperties(['logo']);
			}));
			on(dom.byId('portalTitle'), 'click', lang.hitch(this, function() {
				if (!this.editMode) {
					return;
				}

				// this._editSinglePortalProp('displayName');
				this._editPortalProperties(['displayName']);
			}));
		},

		_updateStyling: function() {
			// set title
			var portal = portalContent.portal;
			var title = dom.byId('portalTitle');
			var portalName = lang.replace(portal.name[locale] || portal.name.en_US || '', tools._status);
			title.innerHTML = portalName;
			document.title = portalName;
			domClass.toggle(title, 'editMode', this.editMode);

			// custom logo
			var logoNode = dom.byId('portalLogo');
			// TODO: use ? with timestamp to prevent caching and always get newest image, feels hacky?
			logoNode.src = portal.logo ? lang.replace('{0}?{1}', [portal.logo, Date.now()]) : '/univention/portal/portal-logo-dummy.svg';
			domClass.toggle(logoNode, 'dijitDisplayNone', (!portal.logo && !this.editMode));
			domClass.toggle(logoNode, 'editMode', this.editMode);
			// TODO tooltip on hover in edit mode
		},

		_editPortalProperties: function(propNames) {
			console.log('edit portal props: ' + propNames);
			var standbyWidget = this.standbyWidget;
			standbyWidget.show();
			var moduleStore = store('$dn$', 'udm', 'settings/portal_all');
			var moduleCache = cache.get('settings/portal_all');

			moduleCache.getProperties('settings/portal', portalContent.portal.dn).then(lang.hitch(this, function(portalProps) {
				var portalProps = lang.clone(portalProps);
				var props = array.filter(portalProps, function(iprop) {
					return array.indexOf(propNames, iprop.id) >= 0;
				});
				
				this._requireWidgets(props).then(lang.hitch(this, function() {
					array.forEach(props, function(iprop) {
						// iprop.umcpCommand = moduleStore.umcpCommand;
						// TODO MultiInput is not required in _requireWidgets
						if (iprop.multivalue && iprop.type !== 'MultiInput') {
							iprop.subtypes = [{
								type: iprop.type,
								dynamicValues: iprop.dynamicValues,
								dynamicValuesInfo: iprop.dynamicValuesInfo,
								dynamicOptions: iprop.dynamicOptions,
								staticValues: iprop.staticValues,
								size: iprop.size,
								depends: iprop.depends
							}];
							iprop.type = 'MultiInput';
						}
					});
					var form = new Form({
						widgets: props,
						layout: propNames,
						moduleStore: moduleStore,
						onSubmit: lang.hitch(this, function(e) {
							if (e) {
								e.preventDefault();
							}

							// TODO validate
							// reset settings from last validation
							tools.forIn(form._widgets, function(iname, iwidget) {
								if (iwidget.setValid) {
									iwidget.setValid(null);
								}
							});

							// validate all widgets to mark invalid/required fields
							form.validate();
							// TODO return if not valid?

							var validateParams = {
								objectType: 'settings/portal',
								properties: {}
							};
							array.forEach(props, function(iprop) {
								validateParams.properties[iprop.id] = form._widgets[iprop.id].get('value');
							});
							// TODO not tested
							tools.umcpCommand('udm/validate', validateParams).then(function(result) {
								// TODO check for non valid values
								// and set the widget to valid=false
								console.log(result);
							});
							
							var putParams = {
								'$dn$': portalContent.portal.dn
							};
							array.forEach(props, function(iprop) {
								putParams[iprop.id] = form._widgets[iprop.id].get('value');
							});
							form.moduleStore.put(putParams).then(lang.hitch(this, function(result) {
								// TODO: check result and make error handling
								json.load('/univention/portal/portal.json', require, lang.hitch(this, function(result) {
									portalContent = result;
									this._updateStyling();	
								}));
							}), function(e) {
								console.log('error');
								console.log(e);
							});

						})
					});
					form.startup();
					form.load(portalContent.portal.dn).then(function() {
						form.ready().then(function() {
							// TODO use dialog.confirmForm instead?
							// TODO better title for the dialog
							var deferred = dialog.confirm(form, [{
								name: 'cancel',
								label: 'Cancel', // TODO translation
								callback: function(r) {
									console.log('cancel clicked');
									// TODO hide seems to be immediate; no animation
									deferred.dialog.hide().then(function() {
										deferred.dialog.destroyRecursive();
									});
								}
							}, {
								name: 'submit',
								label: 'Save', // TODO translation
								callback: function() {
									console.log('submit clicked');
									form.onSubmit();
								}
							}], 'Edit portal property');
							standbyWidget.hide();
						});
					});
				}));
			}));
		},

		_createCategories: function() {
			this.portalCategories = [];

			var portal = portalContent.portal;
			var entries = portalContent.entries;
			var protocol = window.location.protocol;
			var host = window.location.host;
			var isIPv4 = tools.isIPv4Address(host);
			var isIPv6 = tools.isIPv6Address(host);

			if (portal.showApps) {
				var apps = this._getApps(installedApps, locale, protocol, isIPv4, isIPv6);
				this._addCategory(_('Local Apps'), apps, 'localApps');
			}
			array.forEach(['service', 'admin'], lang.hitch(this, function(category) {
				var categoryEntries = array.filter(entries, function(entry) {
					// TODO: filter by entry.authRestriction (anonymous, authenticated, admin)
					return entry.category === category && entry.activated && entry.portals && entry.portals.indexOf(portal.dn) !== -1;
				});
				var apps = this._getApps(categoryEntries, locale, protocol, isIPv4, isIPv6);
				var heading;
				if (category === 'admin') {
					heading = _('Administration');
				} else if (category === 'service') {
					heading = _('Applications');
				}
				this._addCategory(heading, apps, category);
			}));
		},

		_getApps: function(categoryEntries, locale, protocol, isIPv4, isIPv6) {
			var apps = [];
			var browserHostname = getURIHostname(document.location.href);
			array.forEach(categoryEntries, function(entry) {
				// get the best link to be displayed
				var links = getLocalLinks(browserHostname, tools.status('fqdn'), entry.links);
				links = links.concat(entry.links);
				var link = getHighestRankedLink(document.location.href, links);

				// get the hostname to be displayed on the tile
				var hostname = getFQDNHostname(entry.links) || getURIHostname(link);
				apps.push({
					name: entry.name[locale] || entry.name.en_US,
					description: entry.description[locale] || entry.description.en_US,
					logo_name: _getLogoName(entry.logo_name),
					web_interface: link,
					host_name: hostname
				});
			});
			return apps;
		},

		_addCategory: function(heading, apps, category) {
			if (!heading || !apps.length) {
				return;
			}
			var portalCategory = new PortalCategory({
				heading: heading,
				apps: apps,
				domainName: tools.status('domainname'),
				sorting: (category === 'service'),
				category: category
			});
			portalCategory.startup();
			aspect.after(portalCategory.grid, 'onAddEntry', lang.hitch(this, function(category) {
				this.addPortalEntry(category);
			}), true);
			this.content.appendChild(portalCategory.domNode);
			this.portalCategories.push(portalCategory);
		},

		// TODO copy pasted from udm/DetailPage.js
		_requireWidgets: function(properties) {
			var deferreds = [];
			array.forEach(properties, function(prop) {
				if (typeof prop.type == 'string') {
					var path = prop.type.indexOf('/') < 0 ? 'umc/widgets/' + prop.type : prop.type;
					var errHandler;
					var deferred = new Deferred();
					var loaded = function() {
						deferred.resolve();
						errHandler.remove();
					};
					errHandler = require.on('error', loaded);
					require([path], loaded);
					deferreds.push(deferred);
				}
			});
			return all(deferreds);
		},

		addPortalEntry: function(category) {
			console.log('add portal entry');
			var standbyWidget = this.standbyWidget;
			standbyWidget.show();
			var moduleStore = store('$dn$', 'udm', 'settings/portal_all');
			var moduleCache = cache.get('settings/portal_all');

			moduleCache.getProperties('settings/portal_entry').then(lang.hitch(this, function(portalEntryProps) {
				console.log(portalEntryProps);

				this._requireWidgets(portalEntryProps).then(lang.hitch(this, function() {
					var wizard = new Wizard({
						pages: [{
							name: 'name',
							widgets: [this._getPropFromArray(portalEntryProps, 'name')],
							layout: ['name'],
							// headerText: 'header text'
						}, {
							name: 'icon',
							widgets: [this._getPropFromArray(portalEntryProps, 'icon')],
							layout: ['icon'],
							// headerText: ''
						}, {
							name: 'displayName',
							widgets: [this._getPropFromArray(portalEntryProps, 'displayName')],
							layout: ['displayName']
						}, {
							name: 'link',
							widgets: [this._getPropFromArray(portalEntryProps, 'link')],
							layout: ['link']
						}, {
							name: 'description',
							widgets: [this._getPropFromArray(portalEntryProps, 'description')],
							layout: ['description']
						}]
					});
					on(wizard, 'cancel', lang.hitch(this, function() {
						// TODO close dialog and destroy
						console.log('cancel called');
					}));
					on(wizard, 'finished', lang.hitch(this, function(values) {
						console.log('finished');
						console.log(values);
					}));
					var dialog = new Dialog({
						title: 'Create a portal entry',
						content: wizard
					});
					dialog.show();
					standbyWidget.hide();
				}));
			}));
		},

		_getPropFromArray: function(propArray, id) {
			return array.filter(propArray, function(iProp) {
				return iProp.id === id;
			})[0];
		},

		start: function() {
			this.content = dom.byId('content');
			this.search = registry.byId('umcLiveSearch');
			this.search.on('search', lang.hitch(this, 'filterPortal'));
			this._setupEditMode();
			this._initStyling();
			this._updateStyling();
			this._createCategories();
		},

		_checkEditAuthorization: function() {
			var authDeferred = new Deferred();

			tools.umcpCommand('get/modules').then(function(result) {
				var isAuthorized = array.filter(result.modules, function(iModule) {
					return iModule.flavor === 'settings/portal_all';
				}).length;
				if (isAuthorized) {
					authDeferred.resolve();
				} else {
					authDeferred.reject();
				}
			});

			return authDeferred;
		},

		_setupEditMode: function() {
			this._checkEditAuthorization().then(lang.hitch(this, function() {
				// create standby widget that covers the whole screen when loading form dialogs
				this.standbyWidget = new Standby({
					target: dom.byId('portal'),
					zIndex: 100,
					image: require.toUrl("dijit/themes/umc/images/standbyAnimation.svg").toString(),
					duration: 200
				});
				put(dom.byId('portal'), this.standbyWidget.domNode);
				this.standbyWidget.startup();

				
				// create floating button to enter edit mode
				this.portalEditFloatingButton = put(dom.byId('portal'), 'div.portalEditFloatingButton div.icon <');
				new Tooltip({
					label: 'Edit mode', // TODO wording / translation
					connectId: [this.portalEditFloatingButton],
					position: ['above']
				});
				on(this.portalEditFloatingButton, 'click', lang.hitch(this, 'setEditMode', true));

				// create toolbar at bottom to exit edit mode
				// and have options to edit portal options
				// that are not (easily) representable in the portal directly
				this.portalEditBar = new ContainerWidget({
					'class': 'portalEditBar'
				});
				var allocationButton = new Button({
					iconClass: '',
					'class': 'portalEditBarAllocationButton umcFlatButton',
					description: 'Edit allocation of portal', // TODO wording / translation
					callback: lang.hitch(this, '_editPortalProperties', ['portalComputers'])
				});
				var appearanceButton = new Button({
					iconClass: '',
					'class': 'portalEditBarAppearanceButton umcFlatButton',
					description: 'Edit appearance of portal', // TODO wording / translation
					callback: lang.hitch(this, '_editPortalProperties', ['fontColor', 'background', 'cssBackground'])
				});
				var closeButton = new Button({
					iconClass: 'umcCrossIcon',
					'class': 'portalEditBarCloseButton umcFlatButton',
					description: 'Close Edit mode', // TODO wording / translation
					callback: lang.hitch(this, 'setEditMode', false)
				});
				this.portalEditBar.addChild(allocationButton);
				this.portalEditBar.addChild(appearanceButton);
				this.portalEditBar.addChild(closeButton);
				put(dom.byId('portal'), this.portalEditBar.domNode);
			}));
		},

		setEditMode: function(active) {
			this.editMode = active;
			domClass.toggle(dom.byId('portal'), 'editMode', this.editMode);
			this._updateStyling();

			var categories = array.filter(this.portalCategories, function(iPortalCategory) {
				return array.indexOf(['service', 'admin'], iPortalCategory.category) >= 0;
			});

			// add/remove tile to categories for adding portal entries
			array.forEach(categories, lang.hitch(this, function(iCategory) {
				if (this.editMode) {
					iCategory.grid.store.add({
						portalEditAddEntryDummy: true,
						category: iCategory.category,
						id: '$portalEditAddEntryDummy$'
					});
				} else {
					iCategory.grid.store.remove('$portalEditAddEntryDummy$');
				}
				iCategory.grid._renderQuery();
			}));
		},

		filterPortal: function() {
			var searchPattern = lang.trim(this.search.get('value'));
			var searchQuery = this.search.getSearchQuery(searchPattern);

			var query = function(app) {
				return app.portalEditAddEntryDummy || searchQuery.test(app);
			};

			array.forEach(this.portalCategories, function(category) {
				category.set('query', query);
			});
		},

		getHighestRankedLink: getHighestRankedLink,
		canonicalizeIPAddress: canonicalizeIPAddress,
		getLocalLinks: getLocalLinks,
		getFQDNHostname: getFQDNHostname
	};
});
