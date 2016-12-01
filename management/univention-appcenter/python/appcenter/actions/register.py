#!/usr/bin/python2.7
# -*- coding: utf-8 -*-
#
# Univention App Center
#  univention-app base module for registering an app
#
# Copyright 2015-2016 Univention GmbH
#
# http://www.univention.de/
#
# All rights reserved.
#
# The source code of this program is made available
# under the terms of the GNU Affero General Public License version 3
# (GNU AGPL V3) as published by the Free Software Foundation.
#
# Binary versions of this program provided by Univention to you as
# well as other copyrighted, protected or trademarked materials like
# Logos, graphics, fonts, specific documentations and configurations,
# cryptographic keys etc. are subject to a license agreement between
# you and Univention and not subject to the GNU AGPL V3.
#
# In the case you use this program under the terms of the GNU AGPL V3,
# the program is provided in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public
# License with the Debian GNU/Linux or Univention distribution in file
# /usr/share/common-licenses/AGPL-3; if not, see
# <http://www.gnu.org/licenses/>.
#

import os.path
import shutil
import time
import re

from ldap.dn import str2dn, dn2str

from univention.appcenter.app import AppManager
from univention.appcenter.udm import create_object_if_not_exists, get_app_ldap_object, remove_object_if_exists
from univention.appcenter.database import DatabaseConnector, DatabaseError
from univention.appcenter.actions import StoreAppAction, Abort
from univention.appcenter.actions.credentials import CredentialsAction
from univention.appcenter.utils import mkdir, app_ports, currently_free_port_in_range, generate_password
from univention.appcenter.log import catch_stdout
from univention.appcenter.ucr import ucr_save, ucr_get, ucr_keys


class Register(CredentialsAction):

	'''Registers one or more applications. Done automatically via install, only useful if something went wrong / finer grained control is needed.'''
	help = 'Registers an app'

	def setup_parser(self, parser):
		super(Register, self).setup_parser(parser)
		parser.add_argument('--files', dest='register_task', action='append_const', const='files', help='Creating shared directories; copying files from App Center server')
		parser.add_argument('--component', dest='register_task', action='append_const', const='component', help='Adding the component to the list of available repositories')
		parser.add_argument('--host', dest='register_task', action='append_const', const='host', help='Creating a computer object for the app (docker apps only)')
		parser.add_argument('--app', dest='register_task', action='append_const', const='app', help='Registering the app itself (internal UCR variables, ucs-overview variables, adding a special LDAP object for the app)')
		parser.add_argument('--database', dest='register_task', action='append_const', const='database', help='Installing, starting a database management system and creating a databse for the app (if necessary)')
		parser.add_argument('--do-it', dest='do_it', action='store_true', default=None, help='Always do it, disregarding installation status')
		parser.add_argument('--undo-it', dest='do_it', action='store_false', default=None, help='Undo any registrations, disregarding installation status')
		parser.add_argument('apps', nargs='*', action=StoreAppAction, help='The ID of the app that shall be registered')

	def main(self, args):
		AppManager.reload_package_manager()
		apps = args.apps
		if not apps:
			self.debug('No apps given. Using all')
			apps = AppManager.get_all_apps()
		self._register_component_for_apps(apps, args)
		self._register_files_for_apps(apps, args)
		self._register_host_for_apps(apps, args)
		self._register_app_for_apps(apps, args)
		self._register_database_for_apps(apps, args)
		self._register_installed_apps_in_ucr()

	def _do_register(self, app, args):
		if args.do_it is None:
			return app.is_installed()
		return args.do_it

	def _shall_register(self, args, task):
		return args.register_task is None or task in args.register_task

	def _register_component_for_apps(self, apps, args):
		if not self._shall_register(args, 'component'):
			return
		server = AppManager.get_server()
		server = server[server.find('/') + 2:]
		updates = {}
		for app in apps:
			if self._do_register(app, args):
				updates.update(self._register_component(app, server, delay=True))
			else:
				updates.update(self._unregister_component_dict(app))
		with catch_stdout(self.logger):
			ucr_save(updates)

	def _register_component(self, app, server=None, delay=False):
		if app.docker and not ucr_get('docker/container/uuid'):
			self.log('Component needs to be registered in the container')
			return {}
		if app.without_repository:
			self.log('No repository to register')
			return {}
		if server is None:
			server = AppManager.get_server()
			server = server[server.find('/') + 2:]
		updates = {}
		self.log('Registering component for %s' % app.id)
		for _app in AppManager.get_all_apps_with_id(app.id):
			if _app == app:
				updates.update(self._register_component_dict(_app, server))
			else:
				updates.update(self._unregister_component_dict(_app))
		if not delay:
			with catch_stdout(self.logger):
				ucr_save(updates)
		return updates

	def _register_component_dict(self, app, server):
		ret = {}
		ucr_base_key = app.ucr_component_key
		self.debug('Adding %s' % ucr_base_key)
		ret[ucr_base_key] = 'enabled'
		ucr_base_key = '%s/%%s' % ucr_base_key
		ret[ucr_base_key % 'server'] = server
		ret[ucr_base_key % 'description'] = app.name
		ret[ucr_base_key % 'localmirror'] = 'false'
		ret[ucr_base_key % 'version'] = ucr_get(ucr_base_key % 'version', 'current')
		return ret

	def _unregister_component(self, app):
		if app.without_repository:
			self.log('No repository to unregister')
			return
		updates = self._unregister_component_dict(app)
		ucr_save(updates)
		return updates

	def _unregister_component_dict(self, app):
		ret = {}
		ucr_base_key = app.ucr_component_key
		for key in ucr_keys():
			if key == ucr_base_key or key.startswith('%s/' % ucr_base_key):
				self.debug('Removing %s' % key)
				ret[key] = None
		return ret

	def _register_files_for_apps(self, apps, args):
		if not self._shall_register(args, 'files'):
			return
		for app in apps:
			if self._do_register(app, args):
				self._register_files(app)
			else:
				self._unregister_files(app)

	def _register_files(self, app):
		self.log('Creating data directories for %s...' % app.id)
		mkdir(app.get_data_dir())
		mkdir(app.get_conf_dir())
		mkdir(app.get_share_dir())
		for ext in ['univention-config-registry-variables', 'schema']:
			fname = app.get_cache_file(ext)
			if os.path.exists(fname):
				self.log('Copying %s' % fname)
				shutil.copy2(fname, app.get_share_file(ext))

	def _unregister_files(self, app):
		# not removing anything here. these may be important backup files
		pass

	def _register_host_for_apps(self, apps, args):
		if not self._shall_register(args, 'host'):
			return
		for app in apps:
			if self._do_register(app, args):
				self._register_host(app, args)
			else:
				self._unregister_host(app, args)

	def _register_host(self, app, args):
		if not app.docker:
			self.debug('App is not docker. Skip registering host')
			return None, None
		hostdn = ucr_get(app.ucr_hostdn_key)
		lo, pos = self._get_ldap_connection(args)
		if hostdn:
			if lo.get(hostdn):
				self.log('Already found %s as a host for %s. Better do nothing...' % (hostdn, app.id))
				return hostdn, None
			else:
				self.warn('%s should be the host for %s. But it was not found in LDAP. Creating a new one' % (hostdn, app.id))
		# quasi unique hostname; make sure it does not exceed 63 chars
		hostname = '%s-%d' % (app.id[:46], time.time() * 1000000)
		password = generate_password()
		self.log('Registering the container host %s for %s' % (hostname, app.id))
		if app.docker_server_role == 'memberserver':
			base = 'cn=memberserver,cn=computers,%s' % ucr_get('ldap/base')
		else:
			base = 'cn=dc,cn=computers,%s' % ucr_get('ldap/base')
		while base and not lo.get(base):
			base = dn2str(str2dn(base)[1:])
		pos.setDn(base)
		domain = ucr_get('domainname')
		description = '%s (%s)' % (app.name, app.version)
		policies = ['cn=app-release-update,cn=policies,%s' % ucr_get('ldap/base'), 'cn=app-update-schedule,cn=policies,%s' % ucr_get('ldap/base')]
		obj = create_object_if_not_exists('computers/%s' % app.docker_server_role, lo, pos, name=hostname, description=description, domain=domain, password=password, objectFlag='docker', policies=policies)
		ucr_save({app.ucr_hostdn_key: obj.dn})
		return obj.dn, password

	def _unregister_host(self, app, args):
		hostdn = ucr_get(app.ucr_hostdn_key)
		if not hostdn:
			self.log('No hostdn for %s found. Nothing to remove' % app.id)
			return
		lo, pos = self._get_ldap_connection(args)
		remove_object_if_exists('computers/%s' % app.docker_server_role, lo, pos, hostdn)
		ucr_save({app.ucr_hostdn_key: None})

	def _register_app_for_apps(self, apps, args):
		if not self._shall_register(args, 'app'):
			return
		updates = {}
		if apps:
			lo, pos = self._get_ldap_connection(args, allow_machine_connection=True)
		for app in apps:
			if self._do_register(app, args):
				updates.update(self._register_app(app, args, lo, pos, delay=True))
			else:
				updates.update(self._unregister_app(app, args, lo, pos, delay=True))
		ucr_save(updates)

	def _register_app(self, app, args, lo=None, pos=None, delay=False):
		if lo is None:
			lo, pos = self._get_ldap_connection(args, allow_machine_connection=True)
		updates = {}
		self.log('Registering UCR for %s' % app.id)
		self.log('Marking %s as installed' % app)
		if app.is_installed():
			status = ucr_get(app.ucr_status_key, 'installed')
		else:
			status = 'installed'
		ucr_save({app.ucr_status_key: status, app.ucr_version_key: app.version})
		self._register_ports(app)
		updates.update(self._register_docker_variables(app))
		updates.update(self._register_app_report_variables(app))
		# Register app in LDAP (cn=...,cn=apps,cn=univention)
		ldap_object = get_app_ldap_object(app, lo, pos, or_create=True)
		self.log('Adding localhost to LDAP object')
		ldap_object.add_localhost()
		updates.update(self._register_overview_variables(app))
		if not delay:
			ucr_save(updates)
			self._reload_apache()
		return updates

	def _register_database_for_apps(self, apps, args):
		if not self._shall_register(args, 'database'):
			return
		for app in apps:
			if self._do_register(app, args):
				self._register_database(app)

	def _register_database(self, app):
		database_connector = DatabaseConnector.get_connector(app)
		if database_connector:
			try:
				database_connector.create_database()
			except DatabaseError as exc:
				raise Abort(str(exc))

	def _register_docker_variables(self, app):
		updates = {}
		if app.docker:
			try:
				from univention.appcenter.actions.service import Service, ORIGINAL_INIT_SCRIPT
			except ImportError:
				# univention-appcenter-docker is not installed
				pass
			else:
				try:
					init_script = Service.get_init(app)
					self.log('Creating %s' % init_script)
					os.symlink(ORIGINAL_INIT_SCRIPT, init_script)
					self._call_script('/usr/sbin/update-rc.d', os.path.basename(init_script), 'defaults', '41', '14')
				except OSError as exc:
					msg = str(exc)
					if exc.errno == 17:
						self.log(msg)
					else:
						self.warn(msg)
				updates[app.ucr_image_key] = app.get_docker_image_name()
		return updates

	def _register_ports(self, app):
		updates = {}
		current_port_config = {}
		for app_id, container_port, host_port in app_ports():
			if app_id == app.id:
				current_port_config[app.ucr_ports_key % container_port] = str(host_port)
				updates[app.ucr_ports_key % container_port] = None
		for port in app.ports_exclusive:
			updates[app.ucr_ports_key % port] = str(port)
		for port in app.ports_redirection:
			host_port, container_port = port.split(':')
			updates[app.ucr_ports_key % container_port] = str(host_port)
		if app.auto_mod_proxy and app.has_local_web_interface():
			self.log('Setting ports for apache proxy')
			try:
				min_port = int(ucr_get('appcenter/ports/min'))
			except (TypeError, ValueError):
				min_port = 40000
			try:
				max_port = int(ucr_get('appcenter/ports/max'))
			except (TypeError, ValueError):
				max_port = 41000
			ports_taken = set()
			for app_id, container_port, host_port in app_ports():
				if host_port < max_port:
					ports_taken.add(host_port)
			if app.web_interface_port_http:
				key = app.ucr_ports_key % app.web_interface_port_http
				if key in current_port_config:
					value = current_port_config[key]
				else:
					next_port = currently_free_port_in_range(min_port, max_port, ports_taken)
					ports_taken.add(next_port)
					value = str(next_port)
				updates[key] = value
			if app.web_interface_port_https:
				key = app.ucr_ports_key % app.web_interface_port_https
				if key in current_port_config:
					value = current_port_config[key]
				else:
					next_port = currently_free_port_in_range(min_port, max_port, ports_taken)
					ports_taken.add(next_port)
					value = str(next_port)
				updates[key] = value
		for container_port, host_port in current_port_config.iteritems():
			if container_port in updates:
				if updates[container_port] == host_port:
					updates.pop(container_port)
		if updates:
			# save immediately, no delay: next call needs to know
			# about the (to be) registered ports
			ucr_save(updates)

	def _register_app_report_variables(self, app):
		updates = {}
		for key in ucr_keys():
			if re.match('appreport/%s/' % app.id, key):
				updates[key] = None
		registry_key = 'appreport/%s/%%s' % app.id
		anything_set = False
		for key in ['object_type', 'object_filter', 'object_attribute', 'attribute_type', 'attribute_filter']:
			value = getattr(app, 'app_report_%s' % key)
			if value:
				anything_set = True
			updates[registry_key % key] = value
		if anything_set:
			updates[registry_key % 'report'] = 'yes'
		return updates

	def _register_overview_variables(self, app):
		updates = {}
		if app.ucs_overview_category is not False:
			for key in ucr_keys():
				if re.match('ucs/web/overview/entries/[^/]+/%s/' % app.id, key):
					updates[key] = None
		if app.ucs_overview_category and app.web_interface:
			self.log('Setting overview variables')
			registry_key = 'ucs/web/overview/entries/%s/%s/%%s' % (app.ucs_overview_category, app.id)
			port_http = app.web_interface_port_http
			port_https = app.web_interface_port_https
			if app.auto_mod_proxy:
				# the port in the ini is not the "public" port!
				# the web interface lives behind our apache with its
				# default ports
				port_http = port_https = None
			label = app.get_localised('web_interface_name') or app.get_localised('name')
			label_de = app.get_localised('web_interface_name', 'de') or app.get_localised('name', 'de')
			variables = {
				'icon': os.path.join('/univention-management-console/js/dijit/themes/umc/icons/scalable', app.logo_name),
				'port_http': str(port_http or ''),
				'port_https': str(port_https or ''),
				'label': label,
				'label/de': label_de,
				'description': app.get_localised('description'),
				'description/de': app.get_localised('description', 'de'),
				'link': app.web_interface,
			}
			for key, value in variables.iteritems():
				updates[registry_key % key] = value
		return updates

	def _unregister_app(self, app, args, lo=None, pos=None, delay=False):
		if lo is None:
			lo, pos = self._get_ldap_connection(args, allow_machine_connection=True)
		updates = {}
		for key in ucr_keys():
			if key.startswith('appcenter/apps/%s/' % app.id):
				updates[key] = None
			if re.match('ucs/web/overview/entries/[^/]+/%s/' % app.id, key):
				updates[key] = None
			if re.match('appreport/%s/' % app.id, key):
				updates[key] = None
		if app.docker:
			try:
				from univention.appcenter.actions.service import Service
			except ImportError:
				# univention-appcenter-docker is not installed
				pass
			else:
				try:
					init_script = Service.get_init(app)
					os.unlink(init_script)
					self._call_script('/usr/sbin/update-rc.d', os.path.basename(init_script), 'remove')
				except OSError:
					pass
		ldap_object = get_app_ldap_object(app, lo, pos)
		if ldap_object:
			self.log('Removing localhost from LDAP object')
			ldap_object.remove_localhost()
		if not delay:
			ucr_save(updates)
			self._reload_apache()
		return updates

	def _register_installed_apps_in_ucr(self):
		installed_codes = []
		for app in AppManager.get_all_apps():
			if app.is_installed():
				installed_codes.append(app.code)
		with catch_stdout(self.logger):
			ucr_save({
				'appcenter/installed': '-'.join(installed_codes),
				'repository/app_center/installed': '-'.join(installed_codes),  # to be deprecated
			})