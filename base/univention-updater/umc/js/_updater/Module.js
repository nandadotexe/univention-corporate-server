/*
 * Copyright 2011 Univention GmbH
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
/*global console MyError dojo dojox dijit umc */

dojo.provide("umc.modules._updater.Module");

dojo.require("umc.i18n");
dojo.require("umc.widgets.TabbedModule");


// Module with some useful additions:
//
//	-	add a method that can exchange two tabs against each other
//
dojo.declare("umc.modules._updater.Module", [
    umc.widgets.TabbedModule,
	umc.i18n.Mixin
	], 
{

	// exchange two tabs, preserve selectedness.
	exchangeChild: function(from,to) {
		var what = 'nothing';
		try
		{
			what = 'getting FROM selection';
			var is_selected = from.get('selected');
			what = 'hiding FROM';
			this.hideChild(from);
			what = 'showing TO';
			this.showChild(to);
			if (is_selected)
			{
				what = 'selecting TO';
				this.selectChild(to);
			}
		}
		catch(error)
		{
			console.error("exchangeChild: [" + what + "] " + error.message);
		}
	}

	// TODO hideChild() should check selectedness too, and
	// select a different tab when needed.
		
});

