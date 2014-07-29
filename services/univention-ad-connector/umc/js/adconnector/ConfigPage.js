/*
 * Copyright 2011-2013 Univention GmbH
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
	"dojo/when",
	"umc/dialog",
	"umc/tools",
	"umc/render",
	"umc/widgets/Page",
	"umc/widgets/StandbyMixin",
	"umc/widgets/Text",
	"umc/widgets/InfoUploader",
	"umc/i18n!umc/modules/adconnector"
], function(declare, lang, array, when, dialog, tools, render, Page, StandbyMixin, Text, InfoUploader, _) {

	var makeParagraphs = function(sentences) {
		return array.map(sentences, function(para) {
			return '<p>' + para + '</p>';
		}).join('');
	};

	return declare("umc.modules.adconnector.ConfigPage", [Page, StandbyMixin], {
		initialState: null,

		headerText: _('Configuration of the Active Directory connection'),
		forceHelpText: true,

		_widgets: null,

		_buttons: null,

		postCreate: function() {
			this.inherited(arguments);
			this._setHelpText(this.initialState);
		},

		_setHelpText: function(state) {
			if (state && state.mode_admember) {
				this.helpText = _('The system is part of an Active Directory domain.');
			} else if (state && state.mode_adconnector) {
				this.helpText = _('The domain exists in parallel to an Active Directory domain.');
			}
			this.helpText += ' ' + _('This module configures the connection between the Univention Corporate Server and Active Directory.');
			this.showDescription();
		},

		buildRendering: function() {
			this.inherited(arguments);

			var widgets = [{
				name: 'running',
				type: Text
			}, {
				name: 'unencrypted',
				type: Text,
				content: makeParagraphs([
					_('Currently, an unencrypted connection to the Active Directory domain is used.'),
					_('A certification authority should be configured on the Active Directory server. All necessary steps are described in the <a href="http://docs.univention.de/manual-3.2.html#ad-connector:ad-zertifikat" target="_blank">UCS manual</a>.'),
					_('Activate the encrypted connection afterwards.')
				])
			}, {
				name: 'certificateUpload',
				type: InfoUploader,
				showClearButton: false,
				command: 'adconnector/upload/certificate',
				onUploaded: lang.hitch(this, function(result) {
					if (typeof result  == "string") {
						return;
					}
					if (result.success) {
						this.addNotification(_('The certificate was imported successfully'));
						this.showHideElements();
					} else {
						dialog.alert(_('Failed to import the certificate') + ': ' + result.message);
					}
				})
			}, {
				name: 'downloadInfoADMember',
				type: Text,
				content: makeParagraphs([
					_('By default the Active Directory connection does not transfer passwords into the UCS directory service. The system uses the Active Directory Kerberos infrastructure for authentication.'),
					_('However, in some szenarios it may be reasonable to transfer passwords. In this case, The password service should be installed on the Active Directory server.')
				])
			}, {
				name: 'download',
				type: Text,
				content: ''
			}, {
				name: 'downloadNextStepADMember',
				type: Text,
				content: _('After the installation the replication of password hashes has to be activated:')
			}];

			var buttons = [{
				name: 'start',
				label: _('Start Active Directory connection service'),
				callback: lang.hitch(this, '_umcpCommandAndUpdate', 'adconnector/service', {action: 'start'})
			}, {
				name: 'stop',
				label: _('Stop Active Directory connection service'),
				callback: lang.hitch(this, '_umcpCommandAndUpdate', 'adconnector/service', {action: 'stop'})
			}, {
				name: 'activate',
				label: _('Activate encrypted connection'),
				callback: lang.hitch(this, '_umcpCommandAndUpdate', 'adconnector/enable_ssl')
			}, {
				name: 'password_sync',
				label: _('Activate password synchronization'),
				callback: lang.hitch(this, '_umcpCommandAndUpdate', 'adconnector/password_sync_service')
			}, {
				name: 'password_sync_stop',
				label: _('Stop password synchronization'),
				callback: lang.hitch(this, '_umcpCommandAndUpdate', 'adconnector/password_sync_service', {enable: false})
			}];

			this._widgets = render.widgets(widgets);
			this._buttons = render.buttons(buttons);

			var layout = [{
				label: _('Active Directory connection service'),
				layout: ['running', 'start', 'stop']
			}, {
				label: _('Active Directory Server configuration'),
				layout: ['unencrypted', ['certificateUpload', 'activate']]
			}];
			if (this.initialState.mode_adconnector) {
				layout.push({
					label: _('Download the password service for Windows and the UCS certificate'),
					layout: ['download']
				});
			} else {
				layout.push({
					label: _('Password service'),
					layout: ['downloadInfoADMember', 'download', 'downloadNextStepADMember', 'password_sync', 'password_sync_stop']
				});
			}
			var _container = render.layout(layout, this._widgets, this._buttons);

			_container.set('style', 'overflow: auto');
			this.addChild(_container);

			this.showHideElements(this.initialState);
		},

		_umcpCommandAndUpdate: function(command, params) {
			return this.standbyDuring(tools.umcpCommand(command, params).then(lang.hitch(this, function() {
				this.showHideElements();
			})));
		},

		_update_download_text: function(result) {
			var downloadText = _('The MSI files are the installation files for the password service and can be started by double clicking on it.') + '<br>' +
			_('The package is installed in the <b>C:\\Windows\\UCS-AD-Connector</b> directory automatically. Additionally, the password service is integrated into the Windows environment as a system service, which means the service can be started automatically or manually.') +
			'<ul><li><a href="/univention-ad-connector/ucs-ad-connector.msi">ucs-ad-connector.msi</a><br>' +
			_('Installation file for the password service for <b>%s</b> Windows.<br />It can be started by double clicking on it.', '32bit') +
			'</li><li><a href="/univention-ad-connector/ucs-ad-connector-64bit.msi">ucs-ad-connector-64bit.msi</a><br>' +
			_('Installation file for the password service for <b>%s</b> Windows.<br />It can be started by double clicking on it.', '64bit') +
			'</li><li><a href="/univention-ad-connector/vcredist_x86.exe">vcredist_x86.exe</a><br>' +
			_('Microsoft Visual C++ 2010 Redistributable Package (x86) - <b>Must</b> be installed on a <b>64bit</b> Windows.') +
			'</li>';

			if (result.configured) {
				downloadText += '<li><a href="/umcp/command/adconnector/cert.pem" type="application/octet-stream">cert.pem</a><br>' +
				_('The <b>cert.pem</b> file contains the SSL certificates created in UCS for secure communication.') + ' ' +
				_('It must be copied into the installation directory of the password service.') +
				_('<br />Please verify that the file has been downloaded as <b>cert.pem</b>, Internet Explorer appends a .txt under some circumstances.') +
				'</li><li><a href="/umcp/command/adconnector/private.key" type="application/octet-stream">private.key</a><br>' +
				_('The <b>private.key</b> file contains the private key to the SSL certificates.') + ' ' +
				_('It must be copied into the installation directory of the password service.') +
				'</li>';
			}
			downloadText += '</ul>';
			this._widgets.download.set('content', downloadText);
		},

		showHideElements: function(state) {
			if (!state) {
				state = this.standbyDuring(tools.umcpCommand('adconnector/state')).then(function(response) {
					return response.result;
				});
			}
			when(state, lang.hitch(this, function(state) {
				this._setHelpText(state);
				this._update_download_text(state);

				if (state.running) {
					this._widgets.running.set('content', _('Active Directory connection service is currently running.'));
					this._buttons.start.set('visible', false);
					this._buttons.stop.set('visible', true);
				} else {
					var message = _('Active Directory connection service is not running.');
					this._buttons.start.set('visible', true);
					this._buttons.stop.set('visible', false);
					this._widgets.running.set('content', message);
				}
				var certMsg = '';
				var showUploadButton = true;
				if (!state.certificate) {
					if (!state.ssl_enabled) {
						showUploadButton = false;
					} else {
						certMsg = makeParagraphs([
							_('Currently, an encrypted connection between UCS and the Active Directory domain is used.'),
							_('To achieve a higher level of security, the Active Directory system\'s root certificate should be exported and uploaded here. The Active Directory certificate service creates that certificate.'),
							_('The necessary steps depend on the actual Microsoft Windows version and are described in the <a href="http://docs.univention.de/manual-3.2.html#ad-connector:ad-zertifikat" target="_blank">UCS manual</a>.')
						]);
					}
				} else {
					certMsg = makeParagraphs([
						_('Currently, a secured connection between UCS and the Active Directory domain is used.'),
						_('When there is a need of adjustment, you may upload a new root certificate of the Active Directory domain.')
					]);
				}
				this._widgets.certificateUpload.set('value', certMsg);
				this._widgets.certificateUpload.set('visible', showUploadButton);
				this._widgets.unencrypted.set('visible', !showUploadButton);
				this._buttons.activate.set('visible', !showUploadButton);

				this._widgets.downloadInfoADMember.set('visible', state.mode_admember);
				this._widgets.downloadNextStepADMember.set('visible', state.mode_admember);
				this._buttons.password_sync.set('visible', state.mode_admember && !state.password_sync_enabled);
				this._buttons.password_sync_stop.set('visible', state.mode_admember && state.password_sync_enabled);
			}));
		}
	});

});
