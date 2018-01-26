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
	"dojo/dom-construct",
	"dojo/promise/all",
	"dojox/string/sprintf",
	"dojox/widget/Standby",
	"dojox/html/styles",
	"dijit/registry",
	"dijit/Dialog",
	"dijit/Tooltip",
	"dijit/_WidgetBase",
	"dijit/_TemplatedMixin",
	"umc/tools",
	"umc/store",
	"umc/json",
	"umc/dialog",
	"umc/widgets/Button",
	"umc/widgets/Form",
	"umc/widgets/Wizard",
	"umc/widgets/ContainerWidget",
	"umc/widgets/ConfirmDialog",
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
], function(declare, lang, array, Deferred, aspect, on, dom, domClass, domConstruct, all, sprintf, Standby, styles, registry, Dialog, Tooltip, _WidgetBase, _TemplatedMixin, tools, store, json, dialog, Button, Form, Wizard, ContainerWidget, ConfirmDialog, MultiInput, cache, put, PortalCategory, i18nTools, portalContent, installedApps, _) {

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

	var PortalEntryWizard = declare('PortalEntryWizard', [Wizard], {
		autoFocus: true,

		'class': 'portalEntryWizard',

		pageMainBootstrapClasses: 'col-xxs-12 col-xs-8',

		_getPropFromArray: function(propArray, id) {
			return array.filter(propArray, function(iProp) {
				return iProp.id === id;
			})[0];
		},

		postMixInProperties: function() {
			this.inherited(arguments);

			lang.mixin(this, {
				pages: [{
					name: 'name',
					widgets: [this._getPropFromArray(this.portalEntryProps, 'name')],
					layout: ['name'],
					headerText: 's', // FIXME hacky workaround to get 'nav' to show so that Page.js adds the mainBootstrapClasses to 'main'
					// helpText: 'gelp hetxt',
					// helpTextRegion: 'main'
				}, {
					name: 'icon',
					widgets: [this._getPropFromArray(this.portalEntryProps, 'icon')],
					layout: ['icon'],
					headerText: 's',
					// helpText: 'gelp hetxt',
					// helpTextRegion: 'main'
				}, {
					name: 'displayName',
					widgets: [this._getPropFromArray(this.portalEntryProps, 'displayName')],
					layout: ['displayName'],
					headerText: 's',
					// helpText: 'gelp hetxt',
					// helpTextRegion: 'main'
				}, {
					name: 'link',
					widgets: [this._getPropFromArray(this.portalEntryProps, 'link')],
					layout: ['link'],
					headerText: 's',
					// helpText: 'gelp hetxt',
					// helpTextRegion: 'main'
				}, {
					name: 'description',
					widgets: [this._getPropFromArray(this.portalEntryProps, 'description')],
					layout: ['description'],
					headerText: 's',
					// helpText: 'gelp hetxt',
					// helpTextRegion: 'main'
				}]
			})
		},

		next: function(currentPage) {
			// TODO if currentpage is internal name check if the name
			// is already used on next
			if (currentPage) {
				var origArgs = arguments;
				var deferred = new Deferred();
				tools.umcpCommand('udm/validate', {
					objectType: 'settings/portal_entry',
					properties: this.getPage(currentPage)._form.get('value')
				}).then(lang.hitch(this, function(response) {
					var allValid = true;
					array.forEach(response.result, lang.hitch(this, function(iprop) {
						if (iprop.valid instanceof Array) {
							if (!iprop.valid.length) {
								iprop.valid = [false];
								iprop.details = ['This value is required'];
								allValid = false;
							} else {
								array.forEach(iprop.valid, function(ivalid, index) {
									if (ivalid) {
										// TODO is this needed?
										// iprop.valid[index] = null;
									} else {
										allValid = false;
									}
								});
							}
						} else {
							if (iprop.valid) {
								// iprop.valid = null;
							} else {
								allValid = false;
							}
						}

						var widget = this.getPage(currentPage)._form.getWidget(iprop.property);
						widget.setValid(iprop.valid, iprop.details);
					}));
					if (allValid) {
						deferred.resolve(this.inherited(origArgs));
					} else {
						deferred.resolve(currentPage);
					}
				}));
				return deferred;
			} else {
				return this.inherited(arguments);
			}
		},

		_finish: function(currentPage) {
			var deferred = new Deferred();
			tools.umcpCommand('udm/validate', {
				objectType: 'settings/portal_entry',
				properties: this.getPage(currentPage)._form.get('value')
			}).then(lang.hitch(this, function(response) {
				var allValid = true;
				array.forEach(response.result, lang.hitch(this, function(iprop) {
					if (iprop.valid instanceof Array) {
						if (!iprop.valid.length) {
							iprop.valid = [false];
							iprop.details = ['This value is required'];
							allValid = false;
						} else {
							array.forEach(iprop.valid, function(ivalid, index) {
								if (ivalid) {
									// TODO is this needed?
									// iprop.valid[index] = null;
								} else {
									allValid = false;
								}
							});
						}
					} else {
						if (iprop.valid) {
							// iprop.valid = null;
						} else {
							allValid = false;
						}
					}

					var widget = this.getPage(currentPage)._form.getWidget(iprop.property);
					widget.setValid(iprop.valid, iprop.details);
				}));
				if (allValid) {
					deferred.resolve();
				} else {
					deferred.reject();
				}
			}));
			deferred.then(lang.hitch(this, function() {
				this.onFinished(this.getValues());
			}));
		}
	});

	var PortalEntryWizardTile = declare('Tile', [_WidgetBase, _TemplatedMixin], {
		templateString: '' +
			'<div class="umcAppGallery col-xs-4" data-dojo-attach-point="domNode">' +
				'<div class="umcGalleryWrapperItem" data-dojo-attach-point="wrapperNode">' +
					'<div class="cornerPiece boxShadow bl">' +
						'<div class="hoverBackground"></div>' +
					'</div>' +
					'<div class="cornerPiece boxShadow tr">' +
						'<div class="hoverBackground"></div>' +
					'</div>' +
					'<div class="cornerPiece boxShadowCover bl"></div>' +
					'<div class="appIcon umcGalleryIcon" data-dojo-attach-point="iconNode"></div>' +
					'<div class="appInnerWrapper umcGalleryItem">' +
						'<div class="contentWrapper">' +
							'<div class="appContent">' +
								'<div class="umcGalleryName" data-dojo-attach-point="nameWrapperNode">' +
									'<div class="umcGalleryNameContent" data-dojo-attach-point="nameNode"></div>' +
								'</div>' +
								'<div class="umcGallerySubName" data-dojo-attach-point="linkNode"></div>' +
							'</div>' +
							'<div class="appHover">' +
								'<div data-dojo-attach-point="descriptionNode"></div>' +
							'</div>' +
						'</div>' +
					'</div>' +
				'</div>' +
			'</div>',

		currentPageClass: null,
		_setCurrentPageClassAttr: function(page) {
			domClass.toggle(this.wrapperNode, 'hover', page === 'description');
			domClass.replace(this.domNode, page, this.currentPageClass);
			this._set('currentPageClass', page);
		},

		icon: null,
		iconStyle: null,
		_setIconAttr: function(iconUri) {
			if (this.iconStyle) {
				styles.removeCssRule(this.iconStyle.selector, this.iconStyle.declaration);
			}
			if (iconUri) {
				this.iconStyle = {
					selector: lang.replace('#{0} .appIcon', [this.id]),
					declaration: lang.replace('background-image: url("{0}") !important;', [iconUri])
				};
				styles.insertCssRule(this.iconStyle.selector, this.iconStyle.declaration);
			}
			this._set('icon', iconUri);
		},

		name: null,
		_setNameAttr: function(name) {
			this.set('nameClass', name ? 'hasName': null);
			this.nameNode.innerHTML = name;
			this._set('name', name);
		},
		nameClass: null,
		_setNameClassAttr: { node: 'nameWrapperNode', type: 'class' },

		link: null,
		_setLinkAttr: function(link) {
			this.set('linkClass', link ? 'hasLink' : null);
			this.linkNode.innerHTML = link;
			this._set('link', link);
		},
		linkClass: null,
		_setLinkClassAttr: { node: 'linkNode', type: 'class' },

		description: null,
		_setDescriptionAttr: function(description) {
			this.set('descriptionClass', description ? 'hasDescription' : null)	;
			this.descriptionNode.innerHTML = description;
			this._set('description', description);
		},
		descriptionClass: null,
		_setDescriptionClassAttr: { node: 'descriptionNode', type: 'class' }
	});

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

				this._editPortalProperties(['logo'], 'Edit the portal logo' /* TODO wording / translation */);
			}));
			on(dom.byId('portalTitle'), 'click', lang.hitch(this, function() {
				if (!this.editMode) {
					return;
				}

				this._editPortalProperties(['displayName'], 'Edit the portal title' /* TODO wording / translation */);
			}));
			this._portalLogoTooltip = new Tooltip({
				label: 'Edit logo', // TODO wording / translation
				connectId: [dom.byId('portalLogo')],
				position: ['below']
			});
			this._portalTitleTooltip = new Tooltip({
				label: 'Edit title', // TODO wording / translation
				connectId: [dom.byId('portalTitle')],
				position: ['below']
			});
		},

		_updateStyling: function() {
			// update global class for edit mode
			domClass.toggle(dom.byId('portal'), 'editMode', this.editMode);

			// update title
			var portal = portalContent.portal;
			var title = dom.byId('portalTitle');
			var portalName = lang.replace(portal.name[locale] || portal.name.en_US || '', tools._status);
			title.innerHTML = portalName;
			document.title = portalName;

			// update custom logo
			var logoNode = dom.byId('portalLogo');
			// FIXME: use ? with timestamp to prevent caching and always get newest image, feels hacky?
			logoNode.src = portal.logo ? lang.replace('{0}?{1}', [portal.logo, Date.now()]) : '/univention/portal/portal-logo-dummy.svg';
			domClass.toggle(logoNode, 'dijitDisplayNone', (!portal.logo && !this.editMode));

			// update header tooltips
			this._portalLogoTooltip.set('connectId', (this.editMode ? dom.byId('portalLogo') : [] ));
			this._portalTitleTooltip.set('connectId', (this.editMode ? dom.byId('portalTitle') : [] ));

			// update color of header icons
			domClass.toggle(dom.byId('umcHeader'), 'umcWhiteIcons', lang.getObject('portal.fontColor', false, portalContent) === 'white');
		},

		_reloadCss: function() {
			// reload the portal.css file
			// TODO this is too hacky
			var re = /.*\/portal.css\??$/;
			var links = document.getElementsByTagName('link');
			var link = array.filter(links, function(ilink) {
				return re.test(ilink.href);
			})[0];
			if (link.href.lastIndexOf('?') === link.href.length-1) {
				link.href = link.href.substr(0, link.href.length-1);
			} else {
				link.href += '?';
			}
		},

		// TODO copy pasted partially from udm/DetailPage - _prepareWidgets
		_prepareProps: function(props) {
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

			return props;
		},

		_editPortalProperties: function(propNames, dialogTitle) {
			// show standby animation
			var standbyWidget = this.standbyWidget;
			standbyWidget.show();

			var moduleCache = cache.get('settings/portal_all');
			moduleCache.getProperties('settings/portal', portalContent.portal.dn).then(lang.hitch(this, function(portalProps) {
				portalProps = lang.clone(portalProps);
				var props = array.filter(portalProps, function(iprop) {
					return array.indexOf(propNames, iprop.id) >= 0;
				});

				this._requireWidgets(props).then(lang.hitch(this, function() {
					props = this._prepareProps(props);

					var moduleStore = store('$dn$', 'udm', 'settings/portal_all');
					var form = new Form({
						widgets: props,
						layout: propNames,
						moduleStore: moduleStore,
					});
					on(form, 'submit', lang.hitch(this, function() {
						// ------ copy pasted from udm/DetailPage.js - save()
						// reset settings from last validation
						tools.forIn(form._widgets, function(iname, iwidget) {
							if (iwidget.setValid) {
								iwidget.setValid(null);
							}
						});

						// validate all widgets to mark invalid/required fields
						form.validate();
						// ------
						// TODO udm/DetailPage.js checks required widgets here (required but empty)
						// TODO udm/DetailPage.js returns if no changes were made



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
							// console.log(result);
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
								console.log('json load result:');
								console.log(result);
								// TODO load json again if it fails?
								if (!result.portal) {
									console.log(result);
								}
								portalContent = result;
								this._updateStyling();

								// TODO only do this when changing appearance?
								this._reloadCss();
							}));
						}), function(e) {
							// TODO check if this is needed
							console.log('error');
							console.log(e);
						});
					}));
					form.startup();
					// load form with portal
					form.load(portalContent.portal.dn).then(function() {
						form.ready().then(function() {
							// create dialog to show form if form is loaded
							console.log(form.get('value'));
							var dialog = new ConfirmDialog({
								title: dialogTitle,
								message: form,
								options: [{
									name: 'cancel',
									label: 'Cancel', // TODO wording / translation
									callback: function(r) {
										dialog.close();
									}
								}, {
									name: 'submit',
									label: 'Save', // TODO wording / translation
									callback: function() {
										form.submit();
									}
								}]
							});
							dialog.startup();
							dialog.show().then(function() {
								standbyWidget.hide();
							});
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
			var standbyWidget = this.standbyWidget;
			standbyWidget.show();
			var moduleStore = store('$dn$', 'udm', 'settings/portal_all');
			var moduleCache = cache.get('settings/portal_all');

			moduleCache.getProperties('settings/portal_entry').then(lang.hitch(this, function(portalEntryProps) {
				portalEntryProps = lang.clone(portalEntryProps);

				this._requireWidgets(portalEntryProps).then(lang.hitch(this, function() {
					portalEntryProps = this._prepareProps(portalEntryProps);
					var c = new ContainerWidget({});
					var tile = new PortalEntryWizardTile();
					var wizard = new PortalEntryWizard({
						portalEntryProps: portalEntryProps
					});
					wizard.startup();
					tile.set('currentPageClass', wizard.selectedChildWidget.name);
					// TODO own all event handlers
					wizard.watch('selectedChildWidget', function(name, oldPage, newPage) {
						tile.set('currentPageClass', newPage.name);
						var subtext = {
							'icon': 'Icon',
							'displayName': 'Display Name',
							'link': 'Link',
							'description': 'Description'
						}[newPage.name];
						dialog.set('title', lang.replace('{0}: {1}', [dialog._initialTitle, subtext]));
					});
					wizard.getWidget('icon')._image.watch('value', function(name, oldVal, newVal) {
						var iconUri = '';
						if (newVal) {
							iconUri = lang.replace('data:image/{0};base64,{1}', [this._getImageType(), newVal]);
						}
						tile.set('icon', iconUri);
					})
					// on(wizard.getWidget('icon'), 'change', function(value) {
						// if (value) {
							// value = lang.replace('data:image/{0};base64,{1}', [this._image._getImageType(), value]);
						// }
						// tile.set('icon', value);
					// });
					on(wizard.getWidget('displayName'), 'change', function() {
						var displayName = ''
						var displayNames = wizard.getWidget('displayName').get('value');
						if (displayNames.length) {
							var locale = i18nTools.defaultLang().replace(/-/, '_');
							var displayNamesWithText = array.filter(displayNames, function(idisplayName) {
								return idisplayName[1];
							});
							var localDisplayName = array.filter(displayNamesWithText, function(idisplayName) {
								return idisplayName[0] === locale;
							})[0];
							if (localDisplayName) {
								displayName = localDisplayName[1];
							} else if (displayNamesWithText.length) {
								displayName = displayNamesWithText[0][1];
							}
						}
						tile.set('name', displayName);
					});
					on(wizard.getWidget('link'), 'change', function() {
						var link = '';
						var entryLinks = wizard.getWidget('link').get('value');
						if (entryLinks.length) {
							var browserHostname = getURIHostname(document.location.href);
							var links = getLocalLinks(browserHostname, tools.status('fqdn'), entryLinks);
							links = links.concat(entryLinks);
							var link = getHighestRankedLink(document.location.href, links);
						}
						tile.set('link', link);
					});
					on(wizard.getWidget('description'), 'change', function() {
						var description = '';
						var descriptions = wizard.getWidget('description').get('value');
						if (descriptions.length) {
							var locale = i18nTools.defaultLang().replace(/-/, '_');
							var descriptionsWithText = array.filter(descriptions, function(idescription) {
								return idescription[1];
							});
							var localDescription = array.filter(descriptionsWithText, function(idescription) {
								return idescription[0] === locale;
							})[0];
							if (localDescription) {
								description = localDescription[1];
							} else if (descriptionsWithText.length) {
								description = descriptionsWithText[0][1];
							}
						}
						tile.set('description', description);
					});


					on(wizard, 'cancel', lang.hitch(this, function() {
						// TODO close dialog and destroy
						console.log('cancel called');
						dialog.hide().then(function() {
							dialog.destroyRecursive();
						});
					}));
					on(wizard, 'finished', lang.hitch(this, function(values) {
						lang.mixin(values, {
							activated: true,
							category: category,
							portal: [portalContent.portal.dn],
						});
						var addDeferred = moduleStore.add(values, {
							objectType: 'settings/portal_entry'
						});
						addDeferred.then(function(result) {
							// TODO check result to see if creating was successful
						}, function() {
							// TODO error case
						});
						// TODO close Dialog on finish
						// TODO add entry to grid store of PortalCategory
					}));


					c.addChild(tile);
					c.addChild(wizard);

					var dialog = new Dialog({
						_initialTitle: 'Create a new portal entry', // TODO wording / translation
						title: 'Create a new portal entry', // TODO wording / translation
						'class': 'portalEntryDialog',
						content: c
					});
					dialog.show();
					standbyWidget.hide();
				}));
			}));
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
				}).length >= 1;
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
				// TODO is tooltip necessary? it is kind of unaesthetic
				new Tooltip({
					label: 'Edit mode', // TODO wording / translation
					connectId: [this.portalEditFloatingButton],
					position: ['above']
				});
				on(this.portalEditFloatingButton, 'click', lang.hitch(this, 'setEditMode', true));

				// create toolbar at bottom to exit edit mode
				// and have options to edit portal properties
				this.portalEditBar = new ContainerWidget({
					'class': 'portalEditBar'
				});
				var allocationButton = new Button({
					iconClass: '',
					'class': 'portalEditBarAllocationButton umcFlatButton',
					// label: 'Allocation', // TODO wording / translation
					description: 'Edit allocation of portal', // TODO wording / translation
					callback: lang.hitch(this, '_editPortalProperties', ['portalComputers'], 'Edit portal allocation', /* TODO wording / translation */)
				});
				var headerButton = new Button({
					iconClass: '',
					'class': 'portalEditBarHeaderButton umcFlatButton',
					description: 'Edit header of portal', // TODO wording / translation
					callback: lang.hitch(this, '_editPortalProperties', ['logo', 'displayName'], 'Edit portal logo and title' /* TODO wording / translation */)
				});
				var appearanceButton = new Button({
					iconClass: '',
					'class': 'portalEditBarAppearanceButton umcFlatButton',
					description: 'Edit appearance of portal', // TODO wording / translation
					callback: lang.hitch(this, '_editPortalProperties', ['fontColor', 'background', 'cssBackground'], 'Edit the appearance of the portal' /* TODO wording / translation */)
				});
				var closeButton = new Button({
					iconClass: 'umcCrossIcon',
					'class': 'portalEditBarCloseButton umcFlatButton',
					// TODO is tooltip necessary? it is kind of unaesthetic
					description: 'Close Edit mode', // TODO wording / translation
					callback: lang.hitch(this, 'setEditMode', false)
				});
				this.portalEditBar.addChild(allocationButton);
				this.portalEditBar.addChild(headerButton);
				this.portalEditBar.addChild(appearanceButton);
				this.portalEditBar.addChild(closeButton);
				put(dom.byId('portal'), this.portalEditBar.domNode);
			}));
		},

		setEditMode: function(active) {
			this.editMode = active;
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
