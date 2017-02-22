/*
 * Copyright 2017 Univention GmbH
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
/*global define,dojo,getQuery*/


define([
	"login",
	"dojo/_base/lang",
	"dojo/_base/array",
	"dojo/on",
	"dojo/query",
	"dojo/dom",
	"dojo/dom-construct",
	"dojo/dom-attr",
	"dojo/has",
	"dojo/_base/event",
	"dojo/cookie",
	"dijit/Tooltip",
	"dojox/html/entities",
	"umc/dialog",
	"umc/json!/univention/meta.json",
	"umc/i18n!login,umc/app"
], function(login, lang, array, on, query, dom, domConstruct, domAttr, has, dojoEvent, cookie, Tooltip, entities, dialog, meta, _) {

	return {
		renderLoginDialog: function() {
			this.addLinks();
			this.translateDOM();
			this.addTooltips();
			login.renderLoginDialog();
			this.checkCookiesEnabled();
		},

		addLinks: function() {
			array.forEach(this.getLinks(), function(link) {
				domConstruct.place(domConstruct.toDom(link), dom.byId('umcLoginLinks'));
			});
		},

		getLinks: function() {
			var links = [];
			links.push(this.warningBrowserOutdated());
			links.push(this.insecureConnection());
			links.push(this.howToLogin());
			links.push(this.passwordForgotten());
			return array.filter(links, function(link) { return link; });
		},

		insecureConnection: function() {
			// Show warning if connection is unsecured
			if (window.location.protocol === 'https:' || window.location.host === 'localhost') {
				return;
			}
			return lang.replace('<p class="umcLoginWarning"><a href="https://{url}" title="{tooltip}">{text}</a></p>', {
				url: entities.encode(window.location.href.slice(7)),
				tooltip: entities.encode(_('This network connection is not encrypted. All personal or sensitive data such as passwords will be transmitted in plain text. Please follow this link to use a secure SSL connection.')),
				text: entities.encode(_('This network connection is not encrypted. Click here for an HTTPS connection.'))
			});
		},

		warningBrowserOutdated: function() {
			if (has('ie') < 11 || has('ff') < 38 || has('chrome') < 37 || has('safari') < 9) {
				// by umc (4.1.0) supported browsers are Chrome >= 33, FF >= 24, IE >=9 and Safari >= 7
				// they should work with UMC. albeit, they are
				// VERY slow and escpecially IE 8 may take minutes (!)
				// to load a heavy UDM object (on a slow computer at least).
				// IE 8 is also known to cause timeouts when under heavy load
				// (presumably because of many async requests to the server
				// during UDM-Form loading).
				// By browser vendor supported versions:
				// The oldest supported Firefox ESR version is 38 (2016-01-27).
				// Microsoft is ending the support for IE < 11 (2016-01-12).
				// Chrome has no long term support version. Chromium 37 is supported through
				// Ubuntu 12.04 LTS (2016-01-27).
				// Apple has no long term support for safari. The latest version is 9 (2016-01-27)
				return '<p class="umcLoginWarning">Your browser is outdated! You may experience performance issues and other problems when using Univention Services.</p>';
			}
		},

		howToLogin: function() {
			var helpText = _('Please login with a valid username and password.') + ' ';
			if (getQuery('username') === 'root') {
				helpText += _('Use the %s user for the initial system configuration.', '<b><a href="javascript:void();" onclick="_fillUsernameField(\'root\')">root</a></b>');
			} else {
				helpText += _('The default username to manage the domain is %s.', '<b><a href="javascript:void();" onclick="_fillUsernameField(\'Administrator\')">Administrator</a></b>');
			}
			return lang.replace('<a href="javascript:void(0);" data-i18n="How do I login?" title="{tooltip}"></a>', {tooltip: entities.encode(helpText)});
		},

		passwordForgotten: function() {
			// FIXME: check if self-service is installed
			return '<a target="_blank" href="/univention/self-service/" data-i18n="Forgot your password?"></a>';
		},

		_cookiesEnabled: function() {
			if (!cookie.isSupported()) {
				return false;
			}
			if (cookie('UMCUsername')) {
				return true;
			}
			var cookieTestString = 'cookiesEnabled';
			cookie('_umcCookieCheck', cookieTestString, {expires: 1});
			if (cookie('_umcCookieCheck') !== cookieTestString) {
				return false;
			}
			cookie('_umcCookieCheck', cookieTestString, {expires: -1});
			return true;
		},

		checkCookiesEnabled: function() {
			if (this._cookiesEnabled()) {
				return;
			}
			login._loginDialog.disableForm(_('Please enable your browser cookies which are necessary for Univention Services.'));
		},

		addTooltips: function() {
			dojo.query('#umcLoginLinks a').forEach(lang.hitch(this, function(node) {
				if (node.title) {
					on(node, 'mouseover', lang.hitch(this, 'showTooltip', node));
				}
			}));
		},

		translateDOM: function() {
			query('*[data-i18n]').forEach(function(inode) {
				var value = domAttr.get(inode, 'data-i18n');
				var translation = _(value, meta.ucr);
				domAttr.set(inode, 'innerHTML', translation);
			
			});
		},

		_fillUsernameField: function(username) {
			dom.byId('umcLoginUsername').value = username;
			dom.byId('umcLoginPassword').focus();

			//fire change event manually for internet explorer
			if (has('ie') < 10) {
				var event = document.createEvent("HTMLEvents");
				event.initEvent("change", true, false);
				dom.byId('umcLoginUsername').dispatchEvent(event);
			}
		},

		showTooltip: function(node) {
			Tooltip.show(node.title, node);
			on.once(dojo.body(), 'click', function(evt) {
				Tooltip.hide(node);
				dojoEvent.stop(evt);
			});
		}
	};
});