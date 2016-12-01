#!/usr/bin/python2.7
# -*- coding: utf-8 -*-
#
# Univention Management Console
#  module: univention-app-appliance
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

import locale
from univention.management.console.base import Base, UMC_Error
from univention.management.console.modules.decorators import simple_response
from univention.appcenter import get_action
from univention.app_appliance import AppManager
from univention.appcenter.ucr import ucr_instance
from univention.lib.i18n import Translation

_ = Translation('univention-app-appliance').translate


class Instance(Base):

	def init(self):
		locale.setlocale(locale.LC_ALL, str(self.locale))

	@simple_response
	def get(self):
		domain = get_action('domain')
		ucr = ucr_instance()
		application = ucr.get('umc/web/appliance/id', '')
		app = AppManager.find(application)
		if app is None:
			raise UMC_Error(_('Could not find an application for %s') % (application,))
		return domain.to_dict([app])[0]