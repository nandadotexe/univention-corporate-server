#!/usr/bin/python2.4
# -*- coding: utf-8 -*-
#
# Univention Installer
#  installer module: partition configuration
#
# Copyright (C) 2004, 2005, 2006 Univention GmbH
#
# http://www.univention.de/
#
# All rights reserved.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.
#
# Binary versions of this file provided by Univention to you as
# well as other copyrighted, protected or trademarked materials like
# Logos, graphics, fonts, specific documentations and configurations,
# cryptographic keys etc. are subject to a license agreement between
# you and Univention.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

#
# Results of previous modules are placed in self.all_results (dictionary)
# Results of this module need to be stored in the dictionary self.result (variablename:value[,value1,value2])
#

import objects
from objects import *
from local import _
import os, re, string, curses

# possible partition types
POSS_PARTTYPE_UNUSABLE = 0
POSS_PARTTYPE_PRIMARY = 1
POSS_PARTTYPE_LOGICAL = 2
POSS_PARTTYPE_BOTH = 3

# partition types
PARTTYPE_PRIMARY = 0
PARTTYPE_LOGICAL = 1
PARTTYPE_EXTENDED = 2
PARTTYPE_FREESPACE_PRIMARY = 4
PARTTYPE_FREESPACE_LOGICAL = 5
PARTTYPE_LVM_VG = 100
PARTTYPE_LVM_LV = 101
PARTTYPE_LVM_VG_FREE = 102

class object(content):
	def __init__(self,max_y,max_x,last=(1,1), file='/tmp/installer.log', cmdline={}):
		self.written=0
		content.__init__(self,max_y,max_x,last, file, cmdline)

	def MiB2MB(self, mb):
		return mb * 1024.0 * 1024.0 / 1000.0 / 1000.0

	def MB2MiB(self, mb):
		return mb * 1000.0 * 1000.0 / 1024.0 / 1024.0

	def checkname(self):
		return ['devices']

	def profile_prerun(self):
		self.start()
		self.container['profile']={}
		self.read_profile()
		return {}

	def profile_complete(self):
		if self.check('partitions') | self.check('partition'):
			return False
		root_device=0
		root_fs=0
		for key in self.container['profile']['create'].keys():
			for minor in self.container['profile']['create'][key].keys():
				fstype=self.container['profile']['create'][key][minor]['fstype']
				mpoint=self.container['profile']['create'][key][minor]['mpoint']
				if mpoint == '/':
					root_device=1
					if fstype in ['xfs','ext2','ext3']:
						root_fs=1
		if not root_device:
			#Missing / as mountpoint
			self.message='Missing / as mountpoint'
			return False
		if not root_fs:
			#Wrong filesystemtype for mountpoint /
			self.message='Wrong filesystemtype for mountpoint /'
			return False

		return True

	def get_real_partition_device_name(self, device, number):
		match=0
		dev_match=0
		#/dev/cXdX
		regex = re.compile(".*c[0-9]d[0-9]*")
		match = re.search(regex,device)
		if match:
			regex = re.compile(".*c[0-9]*d[0-9]*")
			dev_match=re.search(regex,match.group())

		if dev_match:
			return '%sp%d' % (dev_match.group(),number)
		else:
			return '%s%d' % (device,number)
	def run_profiled(self):
		self.act_profile()
		for key in self.container['profile']['create'].keys():
			device=key.lstrip('/').replace('/','_')
			for minor in self.container['profile']['create'][key].keys():
				type=self.container['profile']['create'][key][minor]['type']
				format=self.container['profile']['create'][key][minor]['format']
				fstype=self.container['profile']['create'][key][minor]['fstype']
				start=self.container['profile']['create'][key][minor]['start']
				end=self.container['profile']['create'][key][minor]['end']
				mpoint=self.container['profile']['create'][key][minor]['mpoint']
				dev="%s"%self.get_real_partition_device_name(device,minor)
				self.container['result'][dev]="%s %s %s %s %s %s"%(type,format,fstype,start,end,mpoint)
		return self.container['result']

	def layout(self):
		self.sub=self.partition(self,self.minY-2,self.minX-20,self.maxWidth+20,self.maxHeight+5)
		self.sub.draw()

	def input(self,key):
		return self.sub.input(key)

	def kill_subwin(self):
		#Defined to prevent subwin from killing (module == subwin)
		if hasattr(self.sub, 'sub'):
			self.sub.sub.exit()
		return ""

	def incomplete(self):
		root_device=0
		root_fs=0
		mpoint_temp=[]
		for disk in self.container['disk'].keys():
			for part in self.container['disk'][disk]['partitions']:
				if self.container['disk'][disk]['partitions'][part]['num'] > 0 : # only valid partitions
					if len(self.container['disk'][disk]['partitions'][part]['mpoint'].strip()):
						if self.container['disk'][disk]['partitions'][part]['mpoint'] in mpoint_temp:
							return _('Double Mount-Point \'%s\'') % self.container['disk'][disk]['partitions'][part]['mpoint']
						mpoint_temp.append(self.container['disk'][disk]['partitions'][part]['mpoint'])
					if self.container['disk'][disk]['partitions'][part]['mpoint'] == '/':
						if not self.container['disk'][disk]['partitions'][part]['fstype'] in ['xfs','ext2','ext3']:
							root_fs=self.container['disk'][disk]['partitions'][part]['fstype']
						root_device=1

		# check LVM Logical Volumes if LVM is enabled
		if self.container['lvm']['enabled'] and self.container['lvm']['vg'].has_key( self.container['lvm']['ucsvgname'] ):
			vg = self.container['lvm']['vg'][ self.container['lvm']['ucsvgname'] ]
			for lvname in vg['lv'].keys():
				lv = vg['lv'][lvname]
				mpoint = lv['mpoint'].strip()
				if len(mpoint):
					if mpoint in mpoint_temp:
						return _('Double Mount-Point \'%s\'') % mpoint
				mpoint_temp.append(mpoint)
				if mpoint == '/':
					if not lv['fstype'] in ['xfs','ext2','ext3']:
						root_fs = lv['fstype']
					root_device=1

		if not root_device:
			self.move_focus( 1 )
			return _('Missing \'/\' as mountpoint')

		if root_fs:
			self.move_focus( 1 )
			return _('Wrong filesystemtype \'%s\' for mountpoint \'/\'' % root_fs)

		# check if LVM is enabled, /-partition is LVM LV and /boot is missing
		rootfs_is_lvm = False
		bootfs_is_lvm = None
		# check for /boot on regular partition
		for disk in self.container['disk'].keys():
			for part in self.container['disk'][disk]['partitions']:
				if self.container['disk'][disk]['partitions'][part]['num'] > 0 : # only valid partitions
					mpoint = self.container['disk'][disk]['partitions'][part]['mpoint'].strip()
					if mpoint == '/boot':
						bootfs_is_lvm = False
		if self.container['lvm']['enabled'] and self.container['lvm']['vg'].has_key( self.container['lvm']['ucsvgname'] ):
			vg = self.container['lvm']['vg'][ self.container['lvm']['ucsvgname'] ]
			for lvname in vg['lv'].keys():
				mpoint = vg['lv'][ lvname ]['mpoint'].strip()
				if mpoint == '/':
					rootfs_is_lvm = True
				if mpoint == '/boot':
					bootfs_is_lvm = True
		self.debug('PARTITION: bootfs_is_lvm=%s  rootfs_is_lvm=%s' % (bootfs_is_lvm, rootfs_is_lvm))
		if rootfs_is_lvm and bootfs_is_lvm in [ None, True ]:
			msglist= [ _('Unable to create bootable config!'),
					   _('/-partition is located on LVM and'),
					   _('/boot-partition is missing or located'),
					   _('on LVM too.') ]
			self.sub.sub=msg_win(self.sub, self.sub.minY+(self.sub.maxHeight/8)+2,self.sub.minX+(self.sub.maxWidth/8),1,1, msglist)
			self.sub.sub.draw()
			return 1

		if len(self.container['history']) or self.test_changes():
			self.sub.sub=self.sub.verify_exit(self.sub,self.sub.minY+(self.sub.maxHeight/8)+2,self.sub.minX+(self.sub.maxWidth/8),self.sub.maxWidth,self.sub.maxHeight-7)
			self.sub.sub.draw()
			return 1

	def profile_f12_run(self):
		# send the F12 key event to the subwindow
		if hasattr(self.sub, 'sub'):
			self.sub.sub.input(276)
			self.sub.sub.exit()
			return 1
		if len(self.container['history']) or self.test_changes():
			self.sub.sub=self.sub.verify_exit(self.sub,self.sub.minY+(self.sub.maxHeight/8)+2,self.sub.minX+(self.sub.maxWidth/8),self.sub.maxWidth,self.sub.maxHeight-7)
			self.sub.draw()
			return 1

	def test_changes(self):
		for disk in self.container['disk'].keys():
			for part in self.container['disk'][disk]['partitions']:
				if self.container['disk'][disk]['partitions'][part]['format']:
					return 1
		return 0

	def helptext(self):
		return ""

	def modheader(self):
		return _('Partition')

	def start(self):
		self.container={}
		self.container['min_size']=float(1)
		self.container['debug']=''
		self.container['profile']={}
		self.container['disk']=self.read_devices()
		self.container['history']=[]
		self.container['temp']={}
		self.container['selected']=1
		self.container['autopartition'] = None
		self.container['lvm'] = {}
		self.container['lvm']['enabled'] = None
		self.container['lvm']['lvm1available'] = False
		self.container['lvm']['warnedlvm1'] = False
		self.container['lvm']['ucsvgname'] = None
		self.container['lvm']['lvmconfigread'] = False

	def read_profile(self):
		self.container['result']={}
		self.container['profile']['empty']=[]
		self.container['profile']['delete']={}
		self.container['profile']['create']={}
		for key in self.all_results.keys():
			if key == 'part_delete':
				delete=self.all_results['part_delete'].replace("'","").split(' ')
				for entry in delete:
					if entry == 'all': # delete all existing partitions
						for disk in self.container['disk'].keys():
							if len(self.container['disk'][disk]['partitions'].keys()):
								self.container['profile']['delete'][disk]=[]
							for part in self.container['disk'][disk]['partitions'].keys():
								if self.container['disk'][disk]['partitions'][part]['num'] > 0:
									self.container['profile']['delete'][disk].append(self.container['disk'][disk]['partitions'][part]['num'])
						self.container['profile']['empty'].append('all')
					elif self.parse_syntax(entry):
						result=self.parse_syntax(entry)
						result[0]=self.get_device_name(result[0])
						if not self.container['profile']['delete'].has_key(result[0]):
							self.container['profile']['delete'][result[0]]=[]
						if not result[1] and self.container['disk'].has_key(result[0]) and len(self.container['disk'][result[0]]['partitions'].keys()): # case delete complete /dev/sda
							for part in self.container['disk'][result[0]]['partitions'].keys():
								self.container['profile']['delete'][result[0]].append(self.container['disk'][result[0]]['partitions'][part]['num'])
							self.container['profile']['empty'].append(result[0])
						else:
							self.container['profile']['delete'][result[0]].append(result[1])

			elif self.parse_syntax(key): # test for matching syntax (dev_sda2, /dev/sda2, etc)
				result=self.parse_syntax(key)
				result[0]=self.get_device_name(result[0])
				if not self.container['profile']['create'].has_key(result[0]):
					self.container['profile']['create'][result[0]]={}
				parms=self.all_results[key].replace("'","").split()
				self.container['result'][key]=''
				if len(parms) >= 5:
					if len(parms) < 6 or parms[5] == 'None' or parms[5] == 'linux-swap':
						mpoint = ''
					else:
						mpoint = parms[5]
					if parms[0] == 'only_mount':
						parms[1]=0
					if result[1] < 5 and result[1] > 0:
						type = PARTTYPE_PRIMARY

					temp={	'type':parms[0],
						'fstype':parms[2],
						'start':parms[3],
						'end':parms[4],
						'mpoint':mpoint,
						'format':parms[1]
						}

					self.debug('Added to create container: [%s]' % temp)
					self.container['profile']['create'][result[0]][result[1]]=temp
				else:
					self.debug('Syntax error for key=[%s]' % key)
					pass


	def get_device_name(self, partition):
		match=0
		dev_match=0
		self.debug('Try to get the device name for %s' % partition)
		# /dev/hdX
		regex = re.compile(".*hd[a-z]([0-9]*)$")
		match = re.search(regex,partition)
		if match:
			regex = re.compile(".*hd[a-z]*")
			dev_match=re.search(regex,match.group())
		#/dev/sdX
		regex = re.compile(".*sd[a-z]([0-9]*)$")
		match = re.search(regex,partition)
		if match:
			regex = re.compile(".*sd[a-z]*")
			dev_match=re.search(regex,match.group())
		#/dev/mdX
		regex = re.compile(".*md([0-9]*)$")
		match = re.search(regex,partition)
		if match:
			regex = re.compile(".*md*")
			dev_match=re.search(regex,match.group())
		#/dev/xdX
		regex = re.compile(".*xd[a-z]([0-9]*)$")
		match = re.search(regex,partition)
		if match:
			regex = re.compile(".*xd[a-z]*")
			dev_match=re.search(regex,match.group())
		#/dev/adX
		regex = re.compile(".*ad[a-z]([0-9]*)$")
		match = re.search(regex,partition)
		if match:
			regex = re.compile(".*ad[a-z]*")
			dev_match=re.search(regex,match.group())
		#/dev/edX
		regex = re.compile(".*ed[a-z]([0-9]*)$")
		match = re.search(regex,partition)
		if match:
			regex = re.compile(".*ed[a-z]*")
			dev_match=re.search(regex,match.group())
		#/dev/pdX
		regex = re.compile(".*pd[a-z]([0-9]*)$")
		match = re.search(regex,partition)
		if match:
			regex = re.compile(".*pd[a-z]*")
			dev_match=re.search(regex,match.group())
		#/dev/pfX
		regex = re.compile(".*pf[a-z]([0-9]*)$")
		match = re.search(regex,partition)
		if match:
			regex = re.compile(".*pf[a-z]*")
			dev_match=re.search(regex,match.group())
		#/dev/vdX
		regex = re.compile(".*vd[a-z]([0-9]*)$")
		match = re.search(regex,partition)
		if match:
			regex = re.compile(".*vd[a-z]*")
			dev_match=re.search(regex,match.group())
		#/dev/dasdX
		regex = re.compile(".*dasd[a-z]([0-9]*)$")
		match = re.search(regex,partition)
		if match:
			regex = re.compile(".*dasd[a-z]*")
			dev_match=re.search(regex,match.group())
		#/dev/dptiX
		regex = re.compile(".*dpti[a-z]([0-9]*)")
		match = re.search(regex,partition)
		if match:
			regex = re.compile(".*dpti[0-9]*")
			dev_match=re.search(regex,match.group())
		#/dev/cXdX
		regex = re.compile(".*c[0-9]d[0-9]*")
		match = re.search(regex,partition)
		if match:
			regex = re.compile(".*c[0-9]*d[0-9]*")
			dev_match=re.search(regex,match.group())
		#/dev/arX
		regex = re.compile(".*ar[0-9]*")
		match = re.search(regex,partition)
		if match:
			regex = re.compile(".*ar[0-9]*")
			dev_match=re.search(regex,match.group())

		if dev_match:
			return '%s' % dev_match.group()
		else:
			return partition


	def parse_syntax(self,entry): # need to test different types of profile
		num=0
		if len(entry.split('/')) > 2 and entry.split('/')[1] == 'dev' and len(entry.split('-')) > 1 and entry.split('-')[1].isdigit(): # got something like /dev/sda-2
			devices=entry.split('-')
			dev=devices[0]
			num=devices[1]
		elif len(entry.split('/')) > 2 and entry.split('/')[1] == 'dev': # got /dev/sda1 /dev/sda
			devices=entry.split('/')[-1]
			i=-1
			while devices[i].isdigit(): # need to find part_num in string
				i-=1
			if i < -1:
				num=int(devices[i+1:])
				dev=entry[:i+1]
			else:
				dev=entry

		elif len(entry.split('_')) > 1 and entry.split('_')[0] == "dev": # got dev_sda1
			devices=entry.split('_')[-1]
			i=-1
			while devices[i].isdigit():
				i-=1
			if i < -1:
				num=int(devices[i+1:])
				dev="/%s" % entry[:i+1].replace('_','/')
			else:
				dev="/%s" % entry.replace('_','/')

		else:
			return  0
		return ["%s"%dev.strip(),num]

	def act_profile(self):
		if not self.written:
			self.act = self.prof_active(self,_('Deleting partitions'),_('Please wait ...'),name='act')
			self.act.action='prof_delete'
			self.act.draw()
			self.act = self.prof_active(self,_('Write partitions'),_('Please wait ...'),name='act')
			self.act.action='prof_write'
			self.act.draw()
			self.written=1

	class prof_active(act_win):
		def get_real_partition_device_name(self, device, number):
			match=0
			dev_match=0
			#/dev/cXdX
			regex = re.compile(".*c[0-9]d[0-9]*")
			match = re.search(regex,device)
			if match:
				regex = re.compile(".*c[0-9]*d[0-9]*")
				dev_match=re.search(regex,match.group())

			if dev_match:
				return '%sp%d' % (dev_match.group(),number)
			else:
				return '%s%d' % (device,number)

		def function(self):
			if self.action == 'prof_delete':
				for disk in self.parent.container['profile']['delete'].keys():
					num_list=self.parent.container['profile']['delete'][disk]
					num_list.reverse()
					for num in num_list:
						command='/sbin/parted --script %s p rm %s'%(disk,num)
						p=os.popen('%s >>/tmp/installer.log 2>&1'%command)
						p.close()
			elif self.action == 'prof_write':
				for disk in self.parent.container['profile']['create'].keys():
					num_list=self.parent.container['profile']['create'][disk].keys()
					num_list.sort()
					for num in num_list:
						type = self.parent.container['profile']['create'][disk][num]['type']
						fstype = self.parent.container['profile']['create'][disk][num]['fstype']
						start = self.parent.container['profile']['create'][disk][num]['start']
						end = self.parent.container['profile']['create'][disk][num]['end']
						if not fstype or fstype in [ 'None', 'none' ]:
							command='/sbin/PartedCreate -d %s -t %s -s %s -e %s' % (disk, type, self.parent.MiB2MB(start), self.parent.MiB2MB(end))
						else:
							command='/sbin/PartedCreate -d %s -t %s -f %s -s %s -e %s' % (disk, type, fstype, self.parent.MiB2MB(start), self.parent.MiB2MB(end))
						self.parent.debug('run command: %s' % command)
						p=os.popen('%s >>/tmp/installer.log 2>&1' % command)
						p.close()
						if fstype in ['ext2','ext3','vfat','msdos']:
							mkfs_cmd='/sbin/mkfs.%s %s' % (fstype,self.get_real_partition_device_name(disk,num))
						elif fstype == 'xfs':
							mkfs_cmd='/sbin/mkfs.xfs -f %s' % self.get_real_partition_device_name(disk,num)
						elif fstype == 'linux-swap':
							mkfs_cmd='/bin/mkswap %s' % self.get_real_partition_device_name(disk,num)
						self.parent.debug('PARTITION: %s' % mkfs_cmd)
						p=os.popen('%s 2>&1'%mkfs_cmd)
						p.close()

			self.stop()


	def read_lvm_pv(self):
#		p = os.popen('pvscan 2> /dev/null')
#		p.close()
		p = os.popen('pvdisplay -c 2> /dev/null')
		content=p.read()
		p.close()

		#  /dev/sdb4:vg_member50:3907584:-1:8:8:-1:4096:477:477:0:dEMYyK-EdEu-uXvk-OS39-IeBe-whg1-c8fTCF

		for line in content.splitlines():
			item = line.strip().split(':')

			self.container['lvm']['pv'][ item[0] ] = { 'touched': 0,
													   'vg': item[1],
													   'PEsize': int( item[7] ), # physical extent size in kilobytes
													   'totalPE': int( item[8] ),
													   'freePE': int( item[9] ),
													   'allocPE': int( item[10] ),
													   }

		# set PV-Flag in disk-container
		for disk in self.container['disk'].keys():
			for part in self.container['disk'][disk]['partitions']:
				self.container['disk'][disk]['partitions'][part]['pvflag'] = (part in self.container['lvm']['pv'].keys())


	def read_lvm_vg(self):
#		p = os.popen('vgscan 2> /dev/null')
#		p.close()

		p = os.popen('vgdisplay 2> /dev/null | grep " Format "')
		content=p.read()
		p.close()
		if 'lvm1' in content:
			self.container['lvm']['lvm1available'] = True

		p = os.popen('vgdisplay -c 2> /dev/null')
		content=p.read()
		p.close()

		#  vg_member50:r/w:772:-1:0:0:0:-1:0:2:2:2940928:4096:718:8:710:B2oHiE-D06t-g4eM-lblN-ELf2-KAYH-ef3CxX

		# get available VGs
		for line in content.splitlines():
			item = line.strip().split(':')
			self.container['lvm']['vg'][ item[0] ] = { 'touched': 0,
													   'PEsize': int(item[12]), # physical extent size in kilobytes
													   'totalPE': int(item[13]),
													   'allocPE': int(item[14]),
													   'freePE': int(item[15]),
													   'size': int(item[12])*int(item[13])/1024.0,
													   'created': 1,
													   'lv': {}
													   }

	def read_lvm_lv(self):
#		p = os.popen('lvscan 2> /dev/null')
#		p.close()

		p = os.popen('lvdisplay -c 2> /dev/null')
		content=p.read()
		p.close()

		#  /dev/ucsvg/ucsvg-vol1:ucsvg:3:1:-1:0:819200:100:-1:0:0:254:0
		#  /dev/ucsvg/ucsvg-vol2:ucsvg:3:1:-1:0:311296:38:-1:0:0:254:1
		#  /dev/ucsvg/ucsvg_vol3:ucsvg:3:1:-1:0:204800:25:-1:0:0:254:2

		# get available LVs
		for line in content.splitlines():
			item = line.strip().split(':')

			vg = item[1]
			pesize = self.container['lvm']['vg'][ vg ]['PEsize']
			lvname = item[0].split('/')[-1]

			p = os.popen('/bin/file -Ls %s' % item[0])
			data = p.read()
			p.close()
			fstype=''
			if 'SGI XFS filesystem data' in data:
				fstype = 'xfs'
			elif 'ext2 filesystem data' in data:
				fstype = 'ext2'
			elif 'ext3 filesystem data' in data:
				fstype = 'ext3'
			elif 'swap file' in data and 'Linux' in data:
				fstype = 'linux-swap'
			elif 'FAT (16 bit)' in data:
				fstype = 'fat16'
			elif 'FAT (32 bit)' in data:
				fstype = 'fat32'

			self.container['lvm']['vg'][ item[1] ]['lv'][ lvname ] = {  'dev': item[0],
																		'vg': item[1],
																		'touched': 0,
																		'PEsize': int(pesize), # physical extent size in kilobytes
																		'currentLE': int(item[7]),
																		'format': 0,
																		'size': int(item[7])*int(pesize)/1024.0,
																		'fstype': fstype,
																		'flag': '',
																		'mpoint': '',
																		}

	def read_lvm(self):
		# read initial LVM status
		self.container['lvm']['pv'] = {}
		self.container['lvm']['vg'] = {}
		self.read_lvm_pv()
		self.read_lvm_vg()
		self.read_lvm_lv()
		if len(self.container['lvm']['vg'].keys()) > 0:
			self.container['lvm']['enabled'] = True
		self.container['lvm']['lvmconfigread'] = True

	def read_devices(self):
		if os.path.exists('/lib/univention-installer/partitions'):
			file=open('/lib/univention-installer/partitions')
			self.debug('Reading from /lib/univention-installer/partitions')
		else:
			file=open('/proc/partitions')
			self.debug('Reading from /proc/partitions')
		proc_partitions=file.readlines()
		devices=[]
		for line in proc_partitions[2:]:
			cols=line.split()
			if len(cols) >= 4  and cols[0] != 'major':
				match=0
				dev_match=0
				self.debug('Testing Entry /dev/%s ' % cols[3])
				# /dev/hdX
				regex = re.compile(".*hd[a-z]([0-9]*)$")
				match = re.search(regex,cols[3])
				if match:
					regex = re.compile(".*hd[a-z]*")
					dev_match=re.search(regex,match.group())
				#/dev/sdX
				regex = re.compile(".*sd[a-z]([0-9]*)$")
				match = re.search(regex,cols[3])
				if match:
					regex = re.compile(".*sd[a-z]*")
					dev_match=re.search(regex,match.group())
				#/dev/mdX
				regex = re.compile(".*md([0-9]*)$")
				match = re.search(regex,cols[3])
				if match:
					regex = re.compile(".*md*")
					dev_match=re.search(regex,match.group())
				#/dev/xdX
				regex = re.compile(".*xd[a-z]([0-9]*)$")
				match = re.search(regex,cols[3])
				if match:
					regex = re.compile(".*xd[a-z]*")
					dev_match=re.search(regex,match.group())
				#/dev/adX
				regex = re.compile(".*ad[a-z]([0-9]*)$")
				match = re.search(regex,cols[3])
				if match:
					regex = re.compile(".*ad[a-z]*")
					dev_match=re.search(regex,match.group())
				#/dev/edX
				regex = re.compile(".*ed[a-z]([0-9]*)$")
				match = re.search(regex,cols[3])
				if match:
					regex = re.compile(".*ed[a-z]*")
					dev_match=re.search(regex,match.group())
				#/dev/pdX
				regex = re.compile(".*pd[a-z]([0-9]*)$")
				match = re.search(regex,cols[3])
				if match:
					regex = re.compile(".*pd[a-z]*")
					dev_match=re.search(regex,match.group())
				#/dev/pfX
				regex = re.compile(".*pf[a-z]([0-9]*)$")
				match = re.search(regex,cols[3])
				if match:
					regex = re.compile(".*pf[a-z]*")
					dev_match=re.search(regex,match.group())
				#/dev/vdX
				regex = re.compile(".*vd[a-z]([0-9]*)$")
				match = re.search(regex,cols[3])
				if match:
					regex = re.compile(".*vd[a-z]*")
					dev_match=re.search(regex,match.group())
				#/dev/dasdX
				regex = re.compile(".*dasd[a-z]([0-9]*)$")
				match = re.search(regex,cols[3])
				if match:
					regex = re.compile(".*dasd[a-z]*")
					dev_match=re.search(regex,match.group())
				#/dev/dptiX
				regex = re.compile(".*dpti[a-z]([0-9]*)")
				match = re.search(regex,cols[3])
				if match:
					regex = re.compile(".*dpti[0-9]*")
					dev_match=re.search(regex,match.group())
				#/dev/cXdX
				regex = re.compile(".*c[0-9]d[0-9]*")
				match = re.search(regex,cols[3])
				if match:
					regex = re.compile(".*c[0-9]*d[0-9]*")
					dev_match=re.search(regex,match.group())
				#/dev/arX
				regex = re.compile(".*ar[0-9]*")
				match = re.search(regex,cols[3])
				if match:
					regex = re.compile(".*ar[0-9]*")
					dev_match=re.search(regex,match.group())

				if dev_match:
					devices.append('/dev/%s' % dev_match.group())
					self.debug('Extracting /dev/%s ' % cols[3])

		uniqlist = []
		for dev in devices:
			if not dev in uniqlist:
				uniqlist.append(dev)
		devices = uniqlist
		devices.sort()
		self.debug('devices=%s' % devices)

		diskList={}
		_re_warning=re.compile('^Warning: Unable to open .*')
		_re_error=re.compile('^Error: Unable to open .*')
		_re_disk_geometry=re.compile('^Disk geometry for .*')
		devices_remove=[]
		for dev in devices:
			dev=dev.strip()
			p = os.popen('/sbin/parted -s %s unit MB p 2>&1 | grep [a-z]'% dev)

			first_line=p.readline().strip()
			self.debug('first line: [%s]' % first_line)
			if _re_warning.match(first_line):
				self.debug('Firstline starts with warning')
				self.debug('Remove device: %s' % dev)
				devices_remove.append(dev)
				continue
			elif _re_error.match(first_line):
				os.system('/sbin/install-mbr -f %s' % dev)
				p = os.popen('/sbin/parted %s unit MB p 2>&1 | grep [a-z]'% dev)
				first_line=p.readline()
				if _re_error.match(first_line):
					self.debug('Firstline starts with error')
					self.debug('Remove device %s' % dev)
					devices_remove.append(dev)
					continue
			if first_line.startswith('Disk '):
				mb_size = int(self.MB2MiB(int(first_line.split(' ')[-1].split('MB')[0].split(',')[0])))
			else:
				mb_size = 0
			extended=0
			primary=0
			logical=0
			partList={}
			last_end=float(0)
			_re_int=re.compile('^[0-9].*')
			for line in p.readlines():
				line=line.strip()
				if not _re_int.match(line):
					if _re_error.match(line):
						self.debug('Line starts wirh Error: [%s]' % line)
						self.debug('Remove device %s' % dev)
						devices_remove.append(dev)
					continue
				line=line.strip()
				cols=line.split()
				num=cols[0]
				part=dev+cols[0]
				start=self.MB2MiB(float(cols[1].split('MB')[0].replace(',','.')))
				#
				end=self.MB2MiB(float(cols[2].split('MB')[0].replace(',','.')))
				# EVIL EVIL EVIL START ==> FIXME TODO
				# start is used as identifier but extended and logical partition can have same start point
				while start in partList.keys():
					start += 0.00000001
				# EVIL EVIL EVIL END 

				size=end-start
				type=cols[4]
				if type == 'extended':
					ptype=PARTTYPE_EXTENDED
					extended=1
					primary+=1
				if type == 'primary':
					ptype=PARTTYPE_PRIMARY
					primary+=1
				if type == 'logical':
					ptype=PARTTYPE_LOGICAL
					logical+=1

				fstype=''
				flag=[]

				if len(cols) > 5:
					fstype=cols[5]
					#FIXME
					if fstype in ['boot','hidden','raid','lvm','lba','palo','prep','boot,','hidden,','raid,','lvm,','lba,','palo,','prep']:
						flag.append(fstype.strip(','))
						fstype=''


				for i in range(6,10):
					if len(cols) > i:
						flag.append(cols[i].strip(','))
				if ( start - last_end) > self.container['min_size']:
					free_start=last_end+float(0.01)
					free_end = start-float(0.01)
					partList[free_start]=self.generate_freespace(free_start,free_end)


				partList[start]={'type':ptype,
						'touched':0,
						'fstype':fstype,
						'size':size,
						'end':end,
						'num':int(num),
						'mpoint':'',
						'flag':flag,
						'format':0,
						'preexist': 1
						}
				if type == 'extended':
					last_end=start
				else:
					last_end=end
			if ( mb_size - last_end) > self.container['min_size']:
				free_start=last_end+float(0.01)
				free_end = float(mb_size)
				partList[free_start]=self.generate_freespace(free_start,free_end)
			diskList[dev]={'partitions':partList,
					'primary':primary,
					'extended':extended,
					'logical':logical,
					'size':mb_size
					}

			p.close()
		for d in devices_remove:
			devices.remove(d)
		return diskList


	def scan_extended_size(self):
		for disk in self.container['disk'].keys():
			part_list = self.container['disk'][disk]['partitions'].keys()
			part_list.sort()
			start=float(-1)
			end=float(-1)
			found=0
			found_extended=0
			for part in part_list:
				if self.container['disk'][disk]['partitions'][part]['type'] == PARTTYPE_LOGICAL:
					found=1
					if start < 0:
						start = part
					elif part < start:
						start = part
					if end < part+self.container['disk'][disk]['partitions'][part]['size']:
						end = part+self.container['disk'][disk]['partitions'][part]['size']
				elif self.container['disk'][disk]['partitions'][part]['type'] == PARTTYPE_EXTENDED:
					found_extended=1
					extended_start = part
					extended_end = part+self.container['disk'][disk]['partitions'][part]['size']
			if found and found_extended:
				self.debug('scan_extended_size: extended_start=%s  start=%s  diff=%s' % (extended_start,start,start - extended_start))
				self.debug('scan_extended_size: extended_end=%s  end=%s  diff=%s' % (extended_end,end, extended_end - end))
				if extended_start < start-float(0.1):
					self.container['temp'][disk]=[extended_start,start-float(0.1),end]
				elif extended_end > end+float(0.1):
					self.container['temp'][disk]=[extended_start,start+float(0.01),end]



	def generate_freespace(self,start,end):
		return {'type':PARTTYPE_FREESPACE_PRIMARY,
			'touched':0,
			'fstype':'---',
			'size':end-start,
			'end':end,
			'num':-1,
			'mpoint':'',
			'flag':[],
			'format':0
			}



	def use_mpoint(self,mpoint):
		for disk in self.container['disk']:
			for part in self.container['disk'][disk]['partitions']:
				if self.container['disk'][disk]['partitions'][part]['mpoint'] == mpoint:
					return 1
		return 0

	def get_device(self, disk, part):
		device="/dev/%s" % disk.replace('/dev/', '').replace('//', '/')
		regex = re.compile(".*c[0-9]d[0-9]*")
		match = re.search(regex,disk)
		if match: # got /dev/cciss/cXdXpX
			device += "p"
		device += "%s"%self.container['disk'][disk]['partitions'][part]['num']
		return device

	def result(self):
		result={}
		tmpresult = []
		partitions = []
		for disk in self.container['disk']:
			partitions.append( disk )
			for part in self.container['disk'][disk]['partitions']:
				if self.container['disk'][disk]['partitions'][part]['num'] > 0 : # only valid partitions
					if self.container['disk'][disk]['partitions'][part]['fstype'][0:3] != 'LVM':
						mpoint=self.container['disk'][disk]['partitions'][part]['mpoint']
						if mpoint == '':
							mpoint = 'None'
						fstype=self.container['disk'][disk]['partitions'][part]['fstype']
						if fstype == '':
							fstype = 'None'
						device = self.get_device(disk, part)

						if mpoint == '/boot':
							result[ 'boot_partition' ] = device
						if mpoint == '/':
							if not result.has_key( 'boot_partition' ):
								result[ 'boot_partition' ] = device

						format=self.container['disk'][disk]['partitions'][part]['format']
						start=part
						end=part+self.container['disk'][disk]['partitions'][part]['size']
						type='only_mount'
						if self.container['disk'][disk]['partitions'][part]['touched']:
							type=self.container['disk'][disk]['partitions'][part]['type']
						tmpresult.append( ("PHY", device, type, format, fstype, start, end, mpoint) )
		result[ 'disks' ] = string.join( partitions, ' ')

		# append LVM if enabled
		if self.container['lvm']['enabled'] and self.container['lvm']['vg'].has_key( self.container['lvm']['ucsvgname'] ):
			vg = self.container['lvm']['vg'][ self.container['lvm']['ucsvgname'] ]
			for lvname in vg['lv'].keys():
				lv = vg['lv'][lvname]
				mpoint = lv['mpoint']
				if not mpoint:
					mpoint = 'None'
				fstype = lv['fstype']
				if not fstype:
					fstype = 'None'

				if mpoint == '/boot':
					result[ 'boot_partition' ] = lv['dev']
				if mpoint == '/':
					if not result.has_key( 'boot_partition' ):
						result[ 'boot_partition' ] = lv['dev']

				format = lv['format']
				start = 0
				end = lv['size']
				type='only_mount'
				tmpresult.append( ("LVM", lv['dev'], type, format, fstype, start, end, mpoint) )
		# sort partitions by mountpoint
		i = 0
		tmpresult.sort(lambda x,y: cmp(x[7], y[7]))  # sort by mountpoint
		for (parttype, device, type, format, fstype, start, end, mpoint) in tmpresult:
			result[ 'dev_%d' % i ] =  "%s %s %s %s %s %sM %sM %s" % (parttype, device, type, format, fstype, start, end, mpoint)
			i += 1
		return result

	class partition(subwin):

		def __init__(self,parent,pos_y,pos_x,width,height):
			self.part_objects = {}
			subwin.__init__(self,parent,pos_y,pos_x,width,height)
			self.check_lvm_msg()

		def set_lvm(self, flag, vgname = None):
			self.container['lvm']['enabled'] = flag
			if flag:
				if vgname:
					self.container['lvm']['ucsvgname'] = vgname
				else:
					self.container['lvm']['ucsvgname'] = 'vg_ucs'
				self.parent.debug( 'Partition: LVM enabled: lvm1available=%s  ucsvgname="%s"' %
							(self.container['lvm']['lvm1available'], self.container['lvm']['ucsvgname']))
				if not self.container['lvm']['vg'].has_key( self.container['lvm']['ucsvgname'] ):
					self.container['lvm']['vg'][ self.container['lvm']['ucsvgname'] ] = { 'touched': 1,
																						  'PEsize': 4096, # physical extent size in kilobytes
																						  'totalPE': 0,
																						  'allocPE': 0,
																						  'freePE': 0,
																						  'size': 0,
																						  'created': 0,
																						  'lv': {}
																						  }

		def auto_partitioning(self, result):
			self.container['autopartition'] = True
			self.parent.debug('PARTITION: AUTO PARTITIONING')

			# remove all LVM LVs
			for vgname,vg in self.container['lvm']['vg'].items():
				for lvname, lv in vg['lv'].items():
					self.parent.debug('deleting LVM LV: %s' % lvname)
					self.part_delete_generic( 'lvm_lv', vgname, lvname )

			# reduce all LVM VGs
			for vgname,vg in self.container['lvm']['vg'].items():
				self.parent.debug('reducing LVM VG: %s' % vgname)
				self.container['history'].append('/sbin/vgreduce -a --removemissing %s' % vgname)
				self.container['history'].append('/sbin/vgreduce -a %s' % vgname)
				self.container['history'].append('/sbin/vgremove %s' % vgname)

			# remove all logical partitions, next all extended partitions and finally all primary partitions
			for parttype in [ PARTTYPE_LOGICAL, PARTTYPE_EXTENDED, PARTTYPE_PRIMARY ]:
				for diskname, disk in self.container['disk'].items():
					for partname, part in disk['partitions'].items():
						if part['type'] == parttype:
							self.parent.debug('deleting part: %s on %s (%s)' % (partname, diskname, self.parent.get_device(diskname, partname)))
							self.part_delete_generic( 'part', diskname, partname, force=True )

			# remove internal data avout LVM VGs and LVM PGs
			for vgname,vg in self.container['lvm']['vg'].items():
				self.parent.debug('removing LVM VG: %s' % vgname)
				del self.container['lvm']['vg'][vgname]
			self.container['lvm']['pv'] = {}

			self.parent.debug("HISTORY")
			for h in self.container['history']:
				self.parent.debug('==> %s' % h)

			# reactivate LVM
			self.set_lvm(True)

			# get disk list
			disklist = self.container['disk'].keys()
			disklist.sort()

			# get system memory
			p = os.popen('free')
			data = p.read()
			p.close()
			regex = re.compile('^\s+Mem:\s+(\d+)\s+.*$')
			sysmem = -1
			for line in data.splitlines():
				match = regex.match(line)
				if match:
					sysmem = int(match.group(1)) / 1024
			self.parent.debug('AUTOPART: sysmem=%s' % sysmem)

			# create primary partition on first harddisk for /boot
			partsize = 96
			targetdisk = None
			targetpart = None
			for disk in disklist:
				for part in self.container['disk'][disk]['partitions'].keys():
					if self.container['disk'][disk]['partitions'][part]['type'] in [ PARTTYPE_FREESPACE_PRIMARY ]:
						if int(self.container['disk'][disk]['partitions'][part]['size']) > partsize:
							targetdisk = disk
							targetpart = part
					if targetdisk:
						break
				if targetdisk:
					break
			if targetdisk:
				# part_create_generic(self,arg_disk,arg_part,mpoint,size,fstype,type,flag,format,end=0):
				self.part_create_generic(targetdisk, targetpart, '/boot', partsize, 'ext3', PARTTYPE_PRIMARY, [], 1)
			else:
				msglist = [ _('Not enough disk space found for /boot!'),
							_('Auto-partitioning aborted.') ]
				self.sub = msg_win(self,self.pos_y+2,self.pos_x+5,self.maxWidth,6, msglist)
				self.draw()
				return

			# determine size of free space areas
			freespacelist = []
			freespacemax = 0.0
			freespacesum = 0.0
			for disk in self.container['disk'].keys():
				for part in self.container['disk'][disk]['partitions'].keys():
					if self.container['disk'][disk]['partitions'][part]['type'] in [ PARTTYPE_FREESPACE_PRIMARY ]:
						freespacelist.append( ( int(self.container['disk'][disk]['partitions'][part]['size']), disk, part ) )
						freespacesum += int(self.container['disk'][disk]['partitions'][part]['size'])
						if int(self.container['disk'][disk]['partitions'][part]['size']) > freespacemax:
							freespacemax = int(self.container['disk'][disk]['partitions'][part]['size'])
			freespacelist.sort(lambda x,y: int(x[0]) < int(y[0]))
			self.parent.debug('AUTOPART: freespacelist=%s' % freespacelist)
			self.parent.debug('AUTOPART: freespacesum=%s' % freespacesum)
			self.parent.debug('AUTOPART: freespacemax=%s' % freespacemax)

			# create primary partition on first harddisk for /swap
			minsystemsize = 4096   # minimum free space for system
			minswapsize = 192      # minimum free space for swap partition
			swapsize = 2 * sysmem  # default for swap partition
			if swapsize > 2048:    # limit swap partition to 2GB
				swapsize = 2048
			if swapsize < minswapsize:
				swapsize = minswapsize
			if (freespacesum - minswapsize < minsystemsize) or (freespacemax < minswapsize):
				self.parent.debug('AUTOPART: not enough disk space for swap (freespacesum=%s  freespacemax=%s  minswapsize=%s  minsystemsize=%s' %
								  (freespacesum, freespacemax, minswapsize, minsystemsize))
				msglist = [ _('Not enough disk space found!'),
							_('Auto-partitioning aborted.') ]
				self.sub = msg_win(self,self.pos_y+2,self.pos_x+5,self.maxWidth,6, msglist)
				self.draw()
				return
			while freespacesum - swapsize < minsystemsize:
				swapsize -= 16
				if swapsize < minswapsize:
					swapsize = minswapsize

			targetdisk = None
			targetpart = None
			for disk in disklist:
				for part in self.container['disk'][disk]['partitions'].keys():
					if self.container['disk'][disk]['partitions'][part]['type'] in [ PARTTYPE_FREESPACE_PRIMARY ]:
						if int(self.container['disk'][disk]['partitions'][part]['size']) > swapsize:
							targetdisk = disk
							targetpart = part
					if targetdisk:
						break
				if targetdisk:
					break
			if targetdisk:
				# part_create_generic(self,arg_disk,arg_part,mpoint,size,fstype,type,flag,format,end=0):
				self.parent.debug('AUTOPART: create swap: disk=%s  part=%s  swapsize=%s' % (targetdisk, targetpart, swapsize))
				self.part_create_generic(targetdisk, targetpart, '', swapsize, 'linux-swap', PARTTYPE_PRIMARY, [], 1)
			else:
				self.parent.debug('AUTOPART: no disk space for swap found')
				self.parent.debug('AUTOPART: DISK=%s' % self.container['disk'])
				msglist = [ _('Not enough disk space found for /boot!'),
							_('Auto-partitioning aborted.') ]
				self.sub = msg_win(self,self.pos_y+2,self.pos_x+5,self.maxWidth,6, msglist)
				self.draw()
				return

			# create one LVM PV per free space range
			parttype_mapping = { PARTTYPE_FREESPACE_PRIMARY: PARTTYPE_PRIMARY,
								 PARTTYPE_FREESPACE_LOGICAL: PARTTYPE_LOGICAL }
			for disk in disklist:
				for part in self.container['disk'][disk]['partitions'].keys():
					if self.container['disk'][disk]['partitions'][part]['type'] in [ PARTTYPE_FREESPACE_PRIMARY, PARTTYPE_FREESPACE_LOGICAL ]:
						# part_create_generic(self,arg_disk,arg_part,mpoint,size,fstype,type,flag,format,end=0):
						size = self.container['disk'][disk]['partitions'][part]['size']
						parttype = parttype_mapping[ self.container['disk'][disk]['partitions'][part]['type'] ]
						self.part_create_generic(disk, part, '', size, '', parttype, ['lvm'], 0)

			# create one LVM LV for /-filesystem
			vgname = self.parent.container['lvm']['ucsvgname']
			vg = self.parent.container['lvm']['vg'][ vgname ]
			lvname = 'rootfs'
			format = 1
			fstype = 'ext3'
			mpoint = '/'
			flag = []
			currentLE = vg['freePE']
			self.lv_create(vgname, lvname, currentLE, format, fstype, flag, mpoint)

		def ask_lvm_enable_callback(self, result):
			self.set_lvm( (result == 'BT_YES') )

		def check_lvm_msg(self):
			# check if LVM config has to be read
			if not self.container['lvm']['lvmconfigread']:
				self.draw()
				self.act = self.active(self,_('Detecting LVM devices'),_('Please wait ...'),name='act',action='read_lvm')
				self.act.draw()
				self.draw()

			# ask for auto partitioning
			if self.container['lvm']['lvmconfigread'] and self.container['autopartition'] == None and not hasattr(self,'sub'):
				msglist=[ _('Do you want to use auto-partitioning?') ]
				self.container['autopartition'] = False
				self.sub = yes_no_win(self, self.pos_y+4, self.pos_x+4, self.width-8, self.height-15, msglist, default='yes', callback_yes=self.auto_partitioning)
				self.draw()

			# show warning if LVM1 volumes are detected
			if self.container['lvm']['lvm1available'] and not self.container['lvm']['warnedlvm1'] and not hasattr(self,'sub'):
				self.container['lvm']['warnedlvm1'] = True
				msglist = [ _('LVM1 volumes detected. To use LVM1 volumes all'),
							_('existing LVM1 snapshots have to be removed!'),
							_('Otherwise kernel is unable to mount them!') ]
				self.sub = msg_win(self,self.pos_y+2,self.pos_x+5,self.maxWidth,6, msglist)
				self.draw()

			# if more than one volume group is present, ask which one to use
			if not self.container['lvm']['ucsvgname'] and len(self.container['lvm']['vg'].keys()) > 1 and not hasattr(self,'sub'):
				self.sub = self.ask_lvm_vg(self,self.minY+2,self.minX+5,self.maxWidth,self.maxHeight-3)
				self.draw()

			# if only one volume group os present, use it
			if not self.container['lvm']['ucsvgname'] and len(self.container['lvm']['vg'].keys()) == 1:
				self.parent.debug('Enabling LVM - only one VG found - %s' % self.container['lvm']['vg'].keys() )
				self.container['lvm']['ucsvgname'] = self.container['lvm']['vg'].keys()[0]
				self.layout()
				self.draw()

			# if LVM is not automagically enabled then ask user if it should be enabled
			if self.container['lvm']['enabled'] == None and not hasattr(self,'sub'):
				msglist=[ _('No LVM volume group found on current system.'),
						  _('Do you want to use LVM2?') ]
				self.sub = yes_no_win(self, self.pos_y+4, self.pos_x+4, self.width-8, self.height-15, msglist, default='yes',
									  callback_yes=self.ask_lvm_enable_callback, callback_no=self.ask_lvm_enable_callback)
				self.draw()


		def draw(self):
			self.shadow.refresh(0,0,self.pos_y+1,self.pos_x+1,self.pos_y+self.height+1,self.pos_x+self.width+1)
			self.pad.refresh(0,0,self.pos_y,self.pos_x,self.pos_y+self.height,self.pos_x+self.width)
			self.header.draw()
			for element in self.elements:
				element.draw()
			if self.startIt:
				self.startIt=0
				self.start()
			if hasattr(self,"sub"):
				self.sub.draw()

		def modheader(self):
			return _(' Partition dialog ')

		def layout(self):
			self.reset_layout()
			self.container=self.parent.container
			self.minY=self.parent.minY
			self.minX=self.parent.minX-16
			self.maxWidth=self.parent.maxWidth
			self.maxHeight=self.parent.maxHeight

			col1=10
			col2=13
			col3=8
			col4=6
			col5=14
			col6=9

			head1=self.get_col(_('Device'),col1,'l')
			head2=self.get_col(_('Area(MB)'),col2)
			head3=self.get_col(_('Typ'),col3)
			head4=self.get_col(_('Form.'),col4)
			head5=self.get_col(_('Mount-Point'),col5,'l')
			head6=self.get_col(_('Size(MB)'),col6)
			text = '%s %s %s %s %s %s'%(head1,head2,head3,head4,head5,head6)
			self.add_elem('TXT_0', textline(text,self.minY,self.minX+2)) #0

			device=self.container['disk'].keys()
			device.sort()

			self.parent.debug('LAYOUT')

			dict=[]
			for dev in device:
				disk = self.container['disk'][dev]
				self.rebuild_table(disk,dev)
				txt = '%s  (%s) %s' % (dev.split('/',2)[-1], _('diskdrive'), '-'*(col1+col2+col3+col4+col5+10))
				path = self.get_col(txt,col1+col2+col3+col4+col5+4,'l')

				size = self.get_col('%s'%disk['size'],col6)
				# save for later use (evaluating inputs)
				self.part_objects[ len(dict) ] = [ 'disk', dev ]
				dict.append('%s %s' % (path,size))

				part_list=self.container['disk'][dev]['partitions'].keys()
				part_list.sort()
				for i in range(len(part_list)):
					part = self.container['disk'][dev]['partitions'][part_list[i]]
					path = self.get_col(' %s' % self.dev_to_part(part, dev),col1,'l')

					format=self.get_col('',col4,'m')
					if part['format']:
						format=self.get_col('X',col4,'m')
					if 'lvm' in part['flag']:
						type=self.get_col('LVMPV',col3)

						device = self.parent.get_device(dev, part_list[i])
						# display corresponding vg of pv if available
						if self.container['lvm'].has_key('pv') and self.container['lvm']['pv'].has_key( device ):
							if self.container['lvm']['pv'][device]['vg']:
								mount=self.get_col( self.container['lvm']['pv'][device]['vg'], col5, 'l')
							else:
								mount=self.get_col( _('(unassigned)'), col5, 'l')
						else:
							mount=self.get_col('',col5,'l')
					else:
						type=self.get_col(part['fstype'],col3)
						if part['fstype']== 'linux-swap':
							type=self.get_col('swap',col3)
						mount=self.get_col(part['mpoint'],col5,'l')
					size=self.get_col('%s'%int(part['size']),col6)
					if part['type'] in [0,1,2]:
						start=('%s' % part_list[i]).split('.')[0]
						end=('%s' % (part_list[i]+part['size'])).split('.')[0]
						area=self.get_col('%s-%s' % (start,end),col2)

					if part['type'] == PARTTYPE_PRIMARY: # PRIMARY
						path = self.get_col(' %s' % self.dev_to_part(part, dev),col1,'l')
					elif part['type'] == PARTTYPE_LOGICAL: # LOGICAL
						path = self.get_col('  %s' % self.dev_to_part(part, dev),col1,'l')
					elif part['type'] == PARTTYPE_EXTENDED: # EXTENDED
						path = self.get_col(' %s' % self.dev_to_part(part, dev),col1,'l')
						type = self.get_col('extended',col3)
					elif part['type'] == PARTTYPE_FREESPACE_PRIMARY or part['type'] == PARTTYPE_FREESPACE_LOGICAL: # FREESPACE
						area=self.get_col('',col2)
						mount=self.get_col('',col5,'l')
						if not self.possible_type(self.container['disk'][dev],part_list[i]):
							path = self.get_col(' !!!',col1,'l')
							type = self.get_col(_('unusable'),col3)
						elif self.possible_type(self.container['disk'][dev],part_list[i]) == POSS_PARTTYPE_LOGICAL:
							path = self.get_col('  ---',col1,'l')
							type = self.get_col(_('free'),col3)
						elif self.possible_type(self.container['disk'][dev],part_list[i]) == POSS_PARTTYPE_BOTH or \
								 self.possible_type(self.container['disk'][dev],part_list[i]) == POSS_PARTTYPE_PRIMARY:
							path = self.get_col(' ---',col1,'l')
							type = self.get_col(_('free'),col3)
					else:
						area=self.get_col('',col2)
						type=self.get_col(_('unknown'),col3)
						path=self.get_col('---',col1)

					self.part_objects[ len(dict) ] = [ 'part', dev, part_list[i], i ]
					dict.append('%s %s %s %s %s %s'%(path,area,type,format,mount,size))

			# display LVM items if enabled
			if self.container['lvm']['enabled'] and self.container['lvm'].has_key('vg'):
				for vgname in self.container['lvm']['vg'].keys():
					# remove following line to display all VGs!
					# but check other code parts for compliance first
					if vgname == self.container['lvm']['ucsvgname']:
						vg = self.container['lvm']['vg'][ vgname ]
						self.parent.debug('==> VG = %s' % vg)
						lvlist = vg['lv'].keys() # equal to   self.container['lvm']['vg'][ vgname ]['lv'].keys()
						lvlist.sort()

						txt = '%s  (%s) %s' % (vgname, _('LVM volume group'), '-'*(col1+col2+col3+col4+col5+10))
						path = self.get_col(txt,col1+col2+col3+col4+col5+4,'l')
						vgsize = vg['PEsize'] * vg['totalPE'] / 1024
						size = self.get_col('%s' % vgsize,col6)

						self.part_objects[ len(dict) ] = [ 'lvm_vg', vgname, None ]
						dict.append('%s %s' % (path,size))

						for lvname in lvlist:
							lv = vg['lv'][ lvname ]
							self.parent.debug('==> LV = %s' % lv)
							path = self.get_col(' %s' % lvname,col1,'l')
							format = self.get_col('',col4,'m')
							if lv['format']:
								format=self.get_col('X',col4,'m')
							size=self.get_col('%s' % int(lv['size']),col6)
							type=self.get_col(lv['fstype'],col3)
							if lv['fstype']== 'linux-swap':
								type=self.get_col('swap',col3)
							mount=self.get_col(lv['mpoint'],col5,'l')
							area=self.get_col('',col2)

							self.part_objects[ len(dict) ] = [ 'lvm_lv', vgname, lvname ]
							dict.append('%s %s %s %s %s %s'%(path,area,type,format,mount,size))

						# show free space in volume group  ( don't show less than 3 physical extents )
						if vg['freePE'] > 2:
							path = self.get_col(' ---',col1,'l')
							format = self.get_col('',col4,'m')
							vgfree = vg['PEsize'] * vg['freePE'] / 1024
							size=self.get_col('%s' % int(vgfree),col6)
							type=self.get_col('free',col3)
							mount=self.get_col('',col5,'l')
							area=self.get_col('',col2)
							self.parent.debug('==> FREE %s MB' % vgfree)

							self.part_objects[ len(dict) ] = [ 'lvm_vg_free', vgname, None ]
							dict.append('%s %s %s %s %s %s'%(path,area,type,format,mount,size))


			self.container['dict']=dict

			self.add_elem('SEL_part', select(dict,self.minY+1,self.minX,self.maxWidth+11,14,self.container['selected'])) #1
			self.add_elem('BT_create', button(_('F2-Create'),self.minY+16,self.minX,18)) #2
			self.add_elem('BT_edit', button(_('F3-Edit'),self.minY+16,self.minX+(self.width/2)-4,align="middle")) #3
			self.add_elem('BT_delete', button(_('F4-Delete'),self.minY+16,self.minX+(self.width)-7,align="right")) #4
			self.add_elem('BT_reset', button(_('F5-Reset changes'),self.minY+17,self.minX,30)) #5
			self.add_elem('BT_write', button(_('F6-Write partitions'),self.minY+17,self.minX+(self.width)-37,30)) #6
			self.add_elem('BT_back', button(_('F11-Back'),self.minY+18,self.minX,30)) #7
			self.add_elem('BT_next', button(_('F12-Next'),self.minY+18,self.minX+(self.width)-37,30)) #8
			if self.startIt:
				self.parent.scan_extended_size()
				self.parent.debug('SCAN_EXT: %s' % self.container['temp'])
				if len(self.container['temp'].keys()):
					self.sub=self.resize_extended(self,self.minY+4,self.minX-2,self.maxWidth+16,self.maxHeight-8)
					self.sub.draw()

		def get_col(self, word, width, align='r'):
			wspace=' '*width
			if align is 'l':
				return word[:width]+wspace[len(word):]
			elif align is 'm':
				space=(width-len(word))/2
				return "%s%s%s" % (wspace[:space],word[:width],wspace[space+len(word):width])
			return wspace[len(word):]+word[:width]

		def dev_to_part(self, part, dev, type="part"):
			#/dev/hdX /dev/sdX /dev/mdX /dev/xdX /dev/adX /dev/edX /dev/pdX /dev/pfX /dev/vdX /dev/dasdX /dev/dptiX /dev/arX
			for ex in [".*hd[a-z]([0-9]*)$",".*sd[a-z]([0-9]*)$",".*md([0-9]*)$",".*xd[a-z]([0-9]*)$",".*ad[a-z]([0-9]*)$", ".*ed[a-z]([0-9]*)$",".*pd[a-z]([0-9]*)$",".*pf[a-z]([0-9]*)$",".*vd[a-z]([0-9]*)$",".*dasd[a-z]([0-9]*)$",".*dpti[a-z]([0-9]*)",".*ar[0-9]*"]:
				regex = re.compile(ex)
				match = re.search(regex,dev)
				if match:
					if type == "part":
						return "%s%s" %(dev.split('/')[-1], part['num'])
					elif type == "full":
						return "%s%s" %(dev, part['num'])
			#/dev/cciss/cXdX
			regex = re.compile(".*c[0-9]d[0-9]*")
			match = re.search(regex,dev)
			if match:
				if type == "part":
					return "%sp%s" % (dev.split('/')[-1],part['num'])
				elif type == "full":
					return "%sp%s" % (dev,part['num'])



		def helptext(self):
			return _('UCS-Partition-Tool \n \n This tool is designed for creating, editing and deleting partitions during the installation. \n \n Use \"F2-Create\" to add a new partition. \n \n Use \"F3-Edit\" to configure an already existing partition. \n \n Use \"F4-Delete\" to remove a partition. \n \n Use the \"Reset changes\" button to cancel your changes to the partition table. \n \n Use the \"Write Partitions\" button to create and/or format your partitions.')

		def input(self,key):
			self.check_lvm_msg()
			if hasattr(self,"sub"):
				rtest=self.sub.input(key)
				if not rtest:
					if not self.sub.incomplete():
						self.subresult=self.sub.get_result()
						self.sub.exit()
						self.parent.layout()
				elif rtest=='next':
					self.subresult=self.sub.get_result()
					self.sub.exit()
					return 'next'
				elif rtest == 'tab':
					self.sub.tab()
			elif not len(self.get_elem('SEL_part').list) and key in [ 10, 32, 276 ]:
				if self.get_elem('BT_reset').get_status():#reset changes
					self.parent.start()
					self.parent.layout()
					self.get_elem_by_id(self.current).set_on()
					self.get_elem('SEL_part').set_off()
					if hasattr(self,"sub"):
						self.sub.draw()
				elif self.get_elem('BT_back').get_status():#back
					return 'prev'
				elif self.get_elem('BT_next').get_status() or key == 276:#next
					if len(self.container['history']) or self.parent.test_changes():
						self.sub=self.verify_exit(self,self.minY+(self.maxHeight/8)+2,self.minX+(self.maxWidth/8),self.maxWidth,self.maxHeight-7)
						self.sub.draw()
					else:
						return 'next'

			elif key == 260:
				#move left
				active=0
				for elemid in ['BT_edit', 'BT_delete', 'BT_reset', 'BT_write', 'BT_back', 'BT_next']:
					if self.get_elem(elemid).active:
						active=self.get_elem_id(elemid)
				if active:
					self.get_elem_by_id(active).set_off()
					self.get_elem_by_id(active-1).set_on()
					self.current=active-1
					self.draw()
			elif key == 261:
				#move right
				active=0
				for elemid in ['BT_create', 'BT_edit', 'BT_delete', 'BT_reset', 'BT_write', 'BT_back']:
					if self.get_elem(elemid).active:
						active=self.get_elem_id(elemid)
				if active:
					self.get_elem_by_id(active).set_off()
					self.get_elem_by_id(active+1).set_on()
					self.current=active+1
					self.draw()


			elif len(self.get_elem('SEL_part').result()) > 0:
				selected = self.part_objects[ self.get_elem('SEL_part').result()[0] ]
				self.parent.debug('self.part_objects=%s' % self.part_objects)
				self.parent.debug('cur_elem=%s' % self.get_elem('SEL_part').result()[0])
				self.parent.debug('partition: selected=[%s]' % selected)
				self.container['selected']=self.get_elem('SEL_part').result()[0]
				disk=selected[1]
				part=''
				type=''
				if selected[0] == 'part':
					part=selected[2]
					type = self.container['disk'][disk]['partitions'][part]['type']
				elif selected[0] == 'lvm_lv':
					type = PARTTYPE_LVM_LV

				if key == 266:# F2 - Create
					self.parent.debug('partition: create')
					if self.resolve_type(type) == 'free' and self.possible_type(self.container['disk'][disk],part):
						self.parent.debug('partition: create!')
						self.sub=self.edit(self,self.minY-1,self.minX+4,self.maxWidth,self.maxHeight+3)
						self.sub.draw()
					elif selected[0] == 'lvm_vg_free':
						self.parent.debug('partition: create lvm!')
						self.sub=self.edit_lvm_lv(self,self.minY-1,self.minX+4,self.maxWidth,self.maxHeight+3)
						self.sub.draw()
				elif key == 267:# F3 - Edit
					self.parent.debug('partition: edit')
					if self.resolve_type(type) == 'primary' or self.resolve_type(type) == 'logical':
						item = self.part_objects[ self.get_elem('SEL_part').result()[0] ]
						if 'lvm' in self.parent.container['disk'][item[1]]['partitions'][item[2]]['flag']:
							self.parent.debug('partition: edit lvm pv not allowed')
							msglist=[ _('LVM physical volumes cannot be modified!'), _('If necessary delete this partition.') ]
							self.sub = msg_win(self, self.pos_y+4, self.pos_x+4, self.width-8, self.height-14, msglist)
							self.sub.draw()
						else:
							self.parent.debug('partition: edit!')
							self.sub=self.edit(self,self.minY-1,self.minX+4,self.maxWidth,self.maxHeight+3)
							self.sub.draw()
					elif selected[0] == 'lvm_lv':
						self.parent.debug('partition: edit lvm!')
						self.sub=self.edit_lvm_lv(self,self.minY-1,self.minX+4,self.maxWidth,self.maxHeight+3)
						self.sub.draw()
				elif key == 268:# F4 - Delete
					self.parent.debug('partition: delete (%s)' % type)
					if type == PARTTYPE_PRIMARY or type == PARTTYPE_LOGICAL or type == PARTTYPE_LVM_LV:
						self.parent.debug('partition: delete!')
						self.part_delete(self.get_elem('SEL_part').result()[0])
					elif type == PARTTYPE_EXTENDED:
						self.sub=self.del_extended(self,self.minY+4,self.minX-2,self.maxWidth+16,self.maxHeight-5)
						self.sub.draw()

				elif key == 269:# F5 - Reset changes
					self.parent.start()
					self.parent.layout()
					self.get_elem_by_id(self.current).set_on()
					self.get_elem('SEL_part').set_off()
					if hasattr(self,"sub"):
						self.sub.draw()
				elif key == 270:# F6 - Write Partitions
					self.sub=self.verify(self,self.minY+(self.maxHeight/8),self.minX+(self.maxWidth/8),self.maxWidth,self.maxHeight-7)
					self.sub.draw()

				elif key == 276:
					if len(self.container['history']) or self.parent.test_changes():
						self.sub=self.verify_exit(self,self.minY+(self.maxHeight/8)+2,self.minX+(self.maxWidth/8),self.maxWidth,self.maxHeight-7)
						self.sub.draw()
					else:
						return 'next'
				elif key in [ 10, 32 ]:
					if self.get_elem('SEL_part').get_status():
						if self.resolve_type(type) == 'extended':
							pass
						elif disk or part and self.possible_type(self.container['disk'][disk],part): #select
							if self.resolve_type(type) in ['primary', 'logical']:
								item = self.part_objects[ self.get_elem('SEL_part').result()[0] ]
								if 'lvm' in self.parent.container['disk'][item[1]]['partitions'][item[2]]['flag']:
									self.parent.debug('partition: edit lvm pv not allowed')
									msglist=[ _('LVM physical volumes cannot be modified!'), _('If necessary delete this partition.') ]
									self.sub = msg_win(self, self.pos_y+4, self.pos_x+4, self.width-8, self.height-14, msglist)
									self.sub.draw()
								else:
									self.parent.debug('partition: edit!')
									self.sub=self.edit(self,self.minY-1,self.minX+4,self.maxWidth,self.maxHeight+3)
									self.sub.draw()
					elif self.get_elem('BT_create').get_status():#create
						if self.resolve_type(type) is 'free' and self.possible_type(self.container['disk'][disk],part):
							self.sub=self.edit(self,self.minY-1,self.minX+4,self.maxWidth,self.maxHeight+3)
							self.sub.draw()
					elif self.get_elem('BT_edit').get_status():#edit
						if self.resolve_type(type) == 'primary' or self.resolve_type(type) == 'logical':
							item = self.part_objects[ self.get_elem('SEL_part').result()[0] ]
							if 'lvm' in self.parent.container['disk'][item[1]]['partitions'][item[2]]['flag']:
								self.parent.debug('partition: edit lvm pv not allowed')
								msglist=[ _('LVM physical volumes cannot be modified!'), _('If necessary delete this partition.') ]
								self.sub = msg_win(self, self.pos_y+4, self.pos_x+4, self.width-8, self.height-14, msglist)
								self.sub.draw()
							else:
								self.sub=self.edit(self,self.minY-1,self.minX+4,self.maxWidth,self.maxHeight+3)
								self.sub.draw()
					elif self.get_elem('BT_delete').get_status():#delete
						if type == PARTTYPE_PRIMARY or type == PARTTYPE_LOGICAL or type == PARTTYPE_LVM_LV:
							self.part_delete(self.get_elem('SEL_part').result()[0])
						elif type == PARTTYPE_EXTENDED:
							self.sub=self.del_extended(self,self.minY+4,self.minX-2,self.maxWidth+16,self.maxHeight-5)
							self.sub.draw()
					elif self.get_elem('BT_reset').get_status():#reset changes
						self.parent.start()
						self.parent.layout()
						self.get_elem_by_id(self.current).set_on()
						self.get_elem('SEL_part').set_off()
						if hasattr(self,"sub"):
							self.sub.draw()
					elif self.get_elem('BT_write').get_status():#write changes
						self.sub=self.verify(self,self.minY+(self.maxHeight/8),self.minX+(self.maxWidth/8),self.maxWidth,self.maxHeight-7)
						self.sub.draw()
					elif self.get_elem('BT_back').get_status():#back
						return 'prev'
					elif self.get_elem('BT_next').get_status():#next
						if len(self.container['history']) or self.parent.test_changes():
							self.sub=self.verify_exit(self,self.minY+(self.maxHeight/8)+2,self.minX+(self.maxWidth/8),self.maxWidth,self.maxHeight-7)
							self.sub.draw()
						else:
							return 'next'
					elif key == 10 and self.get_elem_by_id(self.current).usable():
						return self.get_elem_by_id(self.current).key_event(key)
				elif key == curses.KEY_DOWN or key == curses.KEY_UP:
					self.get_elem('SEL_part').key_event(key)
				else:
					self.get_elem_by_id(self.current).key_event(key)
				return 1

		def resolve_part(self,index):
			i=0
			device = self.container['disk'].keys()
			device.sort()
			for disk in device:
				if index is i:
					return ['disk',disk]
				partitions=self.container['disk'][disk]['partitions'].keys()
				partitions.sort()
				j=0
				for part in partitions:
					i+=1
					if index is i:
						return ['part',disk ,part,j]
					j+=1
				i+=1

		def pv_delete(self, parttype, disk, part, force=False):
			# returns False if pv has been deleted
			# return True if pv cannot be deleted

			forceflag=''
			if force:
				forceflag='-ff'

			if 'lvm' in parttype:
				return False

			if self.container['lvm']['enabled'] and 'lvm' in self.container['disk'][disk]['partitions'][part]['flag']:
				device = '%s%d' % (disk,self.container['disk'][disk]['partitions'][part]['num'])
				if self.container['lvm']['pv'].has_key(device):
					pv = self.container['lvm']['pv'][ device ]

					# check if PV is empty
					if pv['allocPE'] > 0 and not force:
						msglist = [ _('Unable to remove physical volume from'),
									_('volume group "%s"!') % pv['vg'],
									_('Physical volume contains used physical extents!') ]
						self.sub = msg_win(self, self.pos_y+4, self.pos_x+4, self.width-8, self.height-13, msglist)
						self.draw()
						return True
					else:
						# PV is empty
						vgname = pv['vg']
						if vgname:
							# PV is assigned to VG --> update VG data
							vg = self.container['lvm']['vg'][ vgname ]
							vg['freePE'] -= pv['totalPE']
							vg['totalPE'] -= pv['totalPE']
							vg['size'] = vg['PEsize'] * vg['totalPE'] / 1024.0
							if vg['freePE'] + vg['allocPE'] != vg['totalPE']:
								self.parent.debug('PARTITION: assertion failed: vg[freePE] + vg[allocPE] != vg[totalPE]: %d + %d != %d' %
												  (vg['freePE'], vg['allocPE'], vg['totalPE']))
							# reduce VG
							self.container['history'].append('/sbin/vgreduce %s %s' % (vgname, device))
							self.container['history'].append('/sbin/pvremove %s %s' % (forceflag, device))
#							self.container['history'].append('/sbin/pvscan')
#							self.container['history'].append('/sbin/vgscan')
			return False

		def part_delete(self,index):
			result=self.part_objects[index]
			arg_parttype = result[0]
			arg_disk = result[1]
			arg_part = None
			if len(result) > 2:
				arg_part = result[2]

			self.part_delete_generic(arg_parttype, arg_disk, arg_part)

			self.layout()
			self.draw()


		def part_delete_generic(self, arg_parttype, arg_disk, arg_part, force=False):

			if self.pv_delete(arg_parttype, arg_disk, arg_part, force):
				return

			if arg_parttype == 'lvm_lv':
				type = PARTTYPE_LVM_LV
			else:
				type=self.container['disk'][arg_disk]['partitions'][arg_part]['type']

			if type == PARTTYPE_PRIMARY:
				self.container['history'].append('/sbin/parted --script %s rm %s' % (arg_disk,self.container['disk'][arg_disk]['partitions'][arg_part]['num']))
				self.container['disk'][arg_disk]['partitions'][arg_part]['type']=PARTTYPE_FREESPACE_PRIMARY
				self.container['disk'][arg_disk]['partitions'][arg_part]['touched']=1
				self.container['disk'][arg_disk]['partitions'][arg_part]['format']=0
				self.container['disk'][arg_disk]['partitions'][arg_part]['mpoint']=''
				self.container['disk'][arg_disk]['partitions'][arg_part]['num']=-1
				self.container['disk'][arg_disk]['primary']-=1

			elif type == PARTTYPE_LOGICAL:
				deleted=self.container['disk'][arg_disk]['partitions'][arg_part]['num']
				self.container['history'].append('/sbin/parted --script %s rm %s' % (arg_disk,self.container['disk'][arg_disk]['partitions'][arg_part]['num']))
				self.container['disk'][arg_disk]['partitions'][arg_part]['type']=PARTTYPE_FREESPACE_LOGICAL
				self.container['disk'][arg_disk]['partitions'][arg_part]['touched']=1
				self.container['disk'][arg_disk]['partitions'][arg_part]['format']=0
				self.container['disk'][arg_disk]['partitions'][arg_part]['mpoint']=''
				self.container['disk'][arg_disk]['partitions'][arg_part]['num']=-1
				count=0
				for part in self.container['disk'][arg_disk]['partitions'].keys():
					if self.container['disk'][arg_disk]['partitions'][part]['type'] == PARTTYPE_LOGICAL:
						count += 1
					if self.container['disk'][arg_disk]['partitions'][part]['type'] is PARTTYPE_EXTENDED:
						extended=part
				if not count and extended: # empty extended
					self.container['history'].append('/sbin/parted --script %s rm %s' % (arg_disk,self.container['disk'][arg_disk]['partitions'][extended]['num']))
					self.container['disk'][arg_disk]['extended']=0
					self.container['disk'][arg_disk]['primary']-=1
					self.container['disk'][arg_disk]['partitions'][extended]['type']=PARTTYPE_FREESPACE_PRIMARY
					self.container['disk'][arg_disk]['partitions'][extended]['touched']=1
					self.container['disk'][arg_disk]['partitions'][arg_part]['num']=-1
				self.container['disk'][arg_disk]['logical']-=1
				self.container['disk'][arg_disk] = self.renum_logical(self.container['disk'][arg_disk],deleted)

			elif type == PARTTYPE_EXTENDED:
				self.container['disk'][arg_disk]['extended']=0
				self.container['disk'][arg_disk]['primary']-=1
				self.container['disk'][arg_disk]['partitions'][arg_part]['type']=PARTTYPE_FREESPACE_PRIMARY
				self.container['disk'][arg_disk]['partitions'][arg_part]['touched']=1
				for part in self.container['disk'][arg_disk]['partitions'].keys():
					if self.container['disk'][arg_disk]['partitions'][part]['type'] == PARTTYPE_LOGICAL:
						self.container['history'].append('/sbin/parted --script %s rm %s' % (arg_disk,self.container['disk'][arg_disk]['partitions'][part]['num']))
						self.container['disk'][arg_disk]['partitions'][part]['type']=PARTTYPE_FREESPACE_LOGICAL
						self.container['disk'][arg_disk]['partitions'][part]['touched']=1
						self.container['disk'][arg_disk]['logical']-=1
				self.container['history'].append('/sbin/parted --script %s rm %s' % (arg_disk,self.container['disk'][arg_disk]['partitions'][arg_part]['num']))
				self.container['disk'][arg_disk]['partitions'][arg_part]['num']=-1

			elif type == PARTTYPE_LVM_LV:
				lv = self.container['lvm']['vg'][ arg_disk ]['lv'][ arg_part ]

				self.parent.debug('removing LVM LV %s' % lv['dev'])
				self.container['history'].append('/sbin/lvremove -f %s' % lv['dev'])

				# update used/free space on volume group
				currentLE = lv['currentLE']
				self.parent.container['lvm']['vg'][ lv['vg'] ]['freePE'] += currentLE
				self.parent.container['lvm']['vg'][ lv['vg'] ]['allocPE'] -= currentLE

				del self.container['lvm']['vg'][ arg_disk ]['lv'][ arg_part ]

			if type == PARTTYPE_LOGICAL:
				self.minimize_extended(arg_disk)
			if type != PARTTYPE_LVM_LV:
				self.container['disk'][arg_disk]=self.rebuild_table(self.container['disk'][arg_disk],arg_disk)

		def part_create(self,index,mpoint,size,fstype,type,flag,format,end=0):
			result=self.part_objects[index]
			self.part_create_generic(result[1], result[2], mpoint, size, fstype, type, flag, format, end)


		def part_create_generic(self,arg_disk,arg_part,mpoint,size,fstype,type,flag,format,end=0):
			part_list = self.container['disk'][arg_disk]['partitions'].keys()
			part_list.sort()
			old_size=self.container['disk'][arg_disk]['partitions'][arg_part]['size']
			old_type=self.container['disk'][arg_disk]['partitions'][arg_part]['type']
			old_sectors=self.container['disk'][arg_disk]['partitions'][arg_part]['size']
			new_sectors=size
			if type == PARTTYPE_PRIMARY or type == PARTTYPE_LOGICAL: #create new primary/logical disk
				current=arg_part
				if type == PARTTYPE_LOGICAL: # need to modify/create extended
					if not self.container['disk'][arg_disk]['extended']: #create extended
						size=new_sectors+float(0.01)
						self.container['disk'][arg_disk]['partitions'][arg_part]['size']=size
						self.container['disk'][arg_disk]['partitions'][arg_part]['touched']=1
						self.container['disk'][arg_disk]['partitions'][arg_part]['mpoint']=''
						self.container['disk'][arg_disk]['partitions'][arg_part]['fstype']=''
						self.container['disk'][arg_disk]['partitions'][arg_part]['flag']=[]
						self.container['disk'][arg_disk]['partitions'][arg_part]['format']=0
						self.container['disk'][arg_disk]['partitions'][arg_part]['type']=PARTTYPE_EXTENDED
						self.container['disk'][arg_disk]['partitions'][arg_part]['num']=0
						self.container['disk'][arg_disk]['primary']+=1
						self.container['disk'][arg_disk]['extended']=1
						self.container['history'].append('/sbin/parted --script %s mkpart %s %s %s' %
														 (arg_disk,
														  self.resolve_type(PARTTYPE_EXTENDED),
														  self.parent.MiB2MB(arg_part),
														  self.parent.MiB2MB(arg_part+size)))
						current += float(0.01)
						size -= float(0.01)

					else: # resize extended
						for part in self.container['disk'][arg_disk]['partitions'].keys():
							if self.container['disk'][arg_disk]['partitions'][part]['type'] == PARTTYPE_EXTENDED:
								break #found extended leaving loop
						if (part + self.container['disk'][arg_disk]['partitions'][part]['size']) < arg_part+1:
							self.container['disk'][arg_disk]['partitions'][part]['size']+=new_sectors
							self.container['disk'][arg_disk]['partitions'][part]['touched']=1
							self.container['history'].append('/sbin/parted --script %s resize %s %s %s' %
															 (arg_disk,
															  self.container['disk'][arg_disk]['partitions'][part]['num'],
															  self.parent.MiB2MB(part),
															  self.parent.MiB2MB(part+self.container['disk'][arg_disk]['partitions'][part]['size'])))
							size -= float(0.01)
						elif part > arg_part:
							self.container['disk'][arg_disk]['partitions'][part]['size']+=(part-arg_part)
							self.container['disk'][arg_disk]['partitions'][arg_part]=self.container['disk'][arg_disk]['partitions'][part]
							self.container['disk'][arg_disk]['partitions'][arg_part]['touched']=1
							self.container['disk'][arg_disk]['partitions'].pop(part)
							self.container['history'].append('/sbin/parted --script %s resize %s %s %s' %
															 (arg_disk,
															  self.container['disk'][arg_disk]['partitions'][arg_part]['num'],
															  self.parent.MiB2MB(arg_part),
															  self.parent.MiB2MB(arg_part+self.container['disk'][arg_disk]['partitions'][arg_part]['size'])))
							current += float(0.01)
							size -= float(0.01)

				if not self.container['disk'][arg_disk]['partitions'].has_key(current):
					self.container['disk'][arg_disk]['partitions'][current]={}
				self.container['disk'][arg_disk]['partitions'][current]['touched']=1
				if len(mpoint) > 0 and not mpoint.startswith('/'):
					mpoint='/%s' % mpoint
				self.container['disk'][arg_disk]['partitions'][current]['mpoint']=mpoint
				self.container['disk'][arg_disk]['partitions'][current]['fstype']=fstype
				self.container['disk'][arg_disk]['partitions'][current]['flag']=flag
				self.container['disk'][arg_disk]['partitions'][current]['format']=format
				self.container['disk'][arg_disk]['partitions'][current]['type']=type
				self.container['disk'][arg_disk]['partitions'][current]['num']=0
				self.container['disk'][arg_disk]['partitions'][current]['size']=new_sectors
				self.container['history'].append('/sbin/parted --script %s mkpart %s %s %s' %
												 (arg_disk,self.resolve_type(type), self.parent.MiB2MB(current), self.parent.MiB2MB(current+size)))
				if type == PARTTYPE_PRIMARY:
					self.container['disk'][arg_disk]['primary']+=1
				if not (old_size - size) < self.container['min_size']:
					self.container['disk'][arg_disk]['partitions'][current]['size']=new_sectors
					if not end: #start at first sector of freespace
						new_free=current+new_sectors
					else: # new partition at the end of freespace
						self.container['disk'][arg_disk]['partitions'][current+old_sectors-newsectors]=self.container['disk'][arg_disk]['partitions'][current]
						new_free=current
					self.container['disk'][arg_disk]['partitions'][new_free]={}
					self.container['disk'][arg_disk]['partitions'][new_free]['touched']=1
					self.container['disk'][arg_disk]['partitions'][new_free]['size']=old_sectors-new_sectors
					self.container['disk'][arg_disk]['partitions'][new_free]['mpoint']=''
					self.container['disk'][arg_disk]['partitions'][new_free]['fstype']=''
					self.container['disk'][arg_disk]['partitions'][new_free]['flag']=[]
					self.container['disk'][arg_disk]['partitions'][new_free]['format']=0
					self.container['disk'][arg_disk]['partitions'][new_free]['type']=PARTTYPE_FREESPACE_PRIMARY
					self.container['disk'][arg_disk]['partitions'][new_free]['num']=-1 #temporary wrong num
				if type == PARTTYPE_LOGICAL:
					self.minimize_extended(arg_disk)
				self.rebuild_table( self.container['disk'][arg_disk],arg_disk)

				for f in flag:
					self.container['history'].append('/sbin/parted --script %s set %d %s on' % (arg_disk,self.container['disk'][arg_disk]['partitions'][current]['num'],f))

				if 'lvm' in flag:
					self.pv_create(arg_disk, current)

				self.parent.debug("HISTORY")
				for h in self.container['history']:
					self.parent.debug('==> %s' % h)


		def pv_create(self, disk, part):
			device = '%s%d' % (disk,self.container['disk'][disk]['partitions'][part]['num'])
			ucsvgname = self.container['lvm']['ucsvgname']
			
			# create new PV entry
			pesize = self.container['lvm']['vg'][ ucsvgname ]['PEsize']
			# number of physical extents
			pecnt = int(self.container['disk'][disk]['partitions'][part]['size'] * 1024 / pesize)
			# LVM uses about 2% of percent for metadata overhead
			totalpe = int(pecnt * 0.978)

			self.parent.debug('PARTITION: pv_create: pesize=%sk   partsize=%sM=%sk  pecnt=%sPE  totalpe=%sPE' %
							  (pesize, self.container['disk'][disk]['partitions'][part]['size'],
							   self.container['disk'][disk]['partitions'][part]['size'] * 1024, pecnt, totalpe))
			
			self.container['lvm']['pv'][ device ] = { 'touched': 1,
													  'vg': ucsvgname,
													  'PEsize': pesize,
													  'totalPE': totalpe,
													  'freePE': totalpe,
													  'allocPE': 0,
													  }
			
			# update VG entry
			self.container['lvm']['vg'][ ucsvgname ]['touched'] = 1
			self.container['lvm']['vg'][ ucsvgname ]['totalPE'] += totalpe
			self.container['lvm']['vg'][ ucsvgname ]['freePE'] += totalpe
			self.container['lvm']['vg'][ ucsvgname ]['size'] = (self.container['lvm']['vg'][ ucsvgname ]['totalPE'] *
																self.container['lvm']['vg'][ ucsvgname ]['PEsize'] / 1024.0)
			
			device = self.parent.get_device(disk, part)
#			self.container['history'].append('/sbin/pvscan')
			self.container['history'].append('/sbin/pvcreate %s' % device)
			if not self.container['lvm']['vg'][ ucsvgname ]['created']:
				self.container['history'].append('/sbin/vgcreate --physicalextentsize %sk %s %s' %
														 (self.container['lvm']['vg'][ ucsvgname ]['PEsize'], ucsvgname, device))
				self.container['lvm']['vg'][ ucsvgname ]['created'] = 1
#				self.container['history'].append('/sbin/vgscan')
			else:
				self.container['history'].append('/sbin/vgextend %s %s' % (ucsvgname, device))




		def minimize_extended(self, disk):
			self.parent.debug('### minimize: %s'%disk)
			new_start=float(-1)
			start=new_start
			new_end=float(-1)
			end=new_end
			part_list=self.container['disk'][disk]['partitions'].keys()
			part_list.sort()
			for part in part_list:
				# check all logical parts and find minimum size for extended
				if self.container['disk'][disk]['partitions'][part]['type'] == PARTTYPE_LOGICAL:
					if new_end > 0:
						new_end=part+self.container['disk'][disk]['partitions'][part]['size']
					if new_start < 0 or part < new_start:
						new_start = part
					if new_end < 0 or new_end < part+self.container['disk'][disk]['partitions'][part]['size']:
						new_end = part+self.container['disk'][disk]['partitions'][part]['size']
				elif self.container['disk'][disk]['partitions'][part]['type'] == PARTTYPE_EXTENDED:
					start = part
					end=start+self.container['disk'][disk]['partitions'][part]['size']
			new_start -= float(0.01)
			if self.container['disk'][disk]['partitions'].has_key(start):
				if new_start > start:
					self.parent.debug('### minimize at start: %s'%[new_start,start])
					self.container['disk'][disk]['partitions'][start]['size']=end-new_start
					self.container['disk'][disk]['partitions'][new_start]=self.container['disk'][disk]['partitions'][start]
					self.container['history'].append('/sbin/parted --script %s resize %s %s %s; #1' %
													 (disk,
													  self.container['disk'][disk]['partitions'][start]['num'],
													  self.parent.MiB2MB(new_start),
													  self.parent.MiB2MB(new_end)))
					self.container['disk'][disk]['partitions'].pop(start)
				elif new_end > end:
					self.parent.debug('### minimize at end: %s'%[new_end,end])
					self.container['disk'][disk]['partitions'][part_list[-1]]['type']=PARTTYPE_FREESPACE_LOGICAL
					self.container['disk'][disk]['partitions'][part_list[-1]]['num']=-1
					self.container['history'].append('/sbin/parted --script %s resize %s %s %s' %
													 (disk,
													  self.container['disk'][disk]['partitions'][start]['num'],
													  self.parent.MiB2MB(start),
													  self.parent.MiB2MB(new_end)))


			self.layout()
			self.draw()


		def rebuild_table(self, disc, device):
			part=disc['partitions'].keys()
			part.sort()
			old=disc['partitions']
			new={}
			extended=-1
			last_new=-1
			previous_type=-1
			next_type=-1
			primary=[1,2,3,4]
			new_primary=-1
			redo=0
			for i in range(len(part)):
				current_type=old[part[i]]['type']
				if current_type == PARTTYPE_PRIMARY or current_type == PARTTYPE_EXTENDED: # Copy primary
					#need to find next number for primary
					if old[part[i]]['num'] == 0:
						new_primary=part[i]
					else:
						primary.remove(int(old[part[i]]['num']))
					if current_type == PARTTYPE_EXTENDED:
						extended=part[i]
				if i > 0:
					previous_type=new[last_new]['type']
					if (previous_type == PARTTYPE_FREESPACE_PRIMARY and current_type == PARTTYPE_FREESPACE_PRIMARY) or \
					   (previous_type == PARTTYPE_FREESPACE_LOGICAL and current_type == PARTTYPE_FREESPACE_LOGICAL) or \
					   (previous_type == PARTTYPE_FREESPACE_PRIMARY and current_type == PARTTYPE_FREESPACE_LOGICAL): # found freespace next to freespace -> merge
						new[last_new]['size']= (part[i] + old[part[i]]['size']) - last_new
					elif previous_type == PARTTYPE_FREESPACE_LOGICAL and current_type == PARTTYPE_FREESPACE_PRIMARY:
						if extended < 0:
							old[part[i]]['size']+=new[last_new]['size']
							new[last_new]=old[part[i]]
							new[last_new]['touched']
						else:
							new[extended]['size']-=old[part[i-1]]['size']
							new[extended]['touched']=1
							old[part[i]]['size']+=new[last_new]['size']
							new[last_new]=old[part[i]]
							new[last_new]['touched']
						redo=1
					elif previous_type == PARTTYPE_EXTENDED and current_type == PARTTYPE_FREESPACE_LOGICAL and \
						 not i == 1 and disc['partitions'][part[i-2]]['type'] == PARTTYPE_FREESPACE_PRIMARY:
						# freespace next to extended part
						# a logical part has been remove
						# the extended have to be resized
						# frespaces have to be merged
						old[part[i-2]]['size']=( part[i] + old[part[i]]['size']) - part[i-2]
						new[part[i-2]]=old[part[i-2]] # resize primary freespace
						new[part[i-2]]['touched']=1
						new[last_new]['size']-=old[part[i]]['size']
						new[part[i]+old[part[i]]['size']]=new[last_new]
						new[part[i]+old[part[i]]['size']]['touched']=1
						new.pop(last_new)
						last_new=part[i]+old[part[i]]['size']

					elif previous_type == PARTTYPE_EXTENDED and current_type == PARTTYPE_FREESPACE_LOGICAL:
						old[part[i-1]]['size']-=old[part[i]]['size']
						new_start=part[i]
						new_end=new_start+old[part[i-1]]['size']
						new[new_start]=old[part[i-1]]
						self.container['history'].append('/sbin/parted --script %s resize %s %s %s' %
														 (device,
														  old[part[i-1]]['num'],
														  self.parent.MiB2MB(new_start),
														  self.parent.MiB2MB(new_end)))
						new[part[i-1]]=old[part[i]]
						redo=1

					elif current_type == PARTTYPE_EXTENDED and previous_type == PARTTYPE_LOGICAL:
						# new logical in front of extend found - need to resize extended
						old[part[i]]['size']+=old[part[i-1]]['size']
						new[last_new]=old[part[i]]
						new[last_new]['touched']=1
						old[part[i-1]]['size']-=1
						new[last_new+1]=old[part[i-1]]
						new[last_new+1]['touched']=1
						last_new+=1

					elif current_type == PARTTYPE_LOGICAL:
						# Copy logical and correct number
						if not old[part[i]]['num']:
							disc['logical']+=1
							old[part[i]]['num']=4+disc['logical']
						new[part[i]]=old[part[i]]
						last_new=part[i]

					elif current_type == PARTTYPE_PRIMARY:
						# Copy primary
						new[part[i]]=old[part[i]]
						last_new=part[i]

					elif current_type == PARTTYPE_FREESPACE_PRIMARY or current_type == PARTTYPE_FREESPACE_LOGICAL:
						# Copy Freespace
						new[part[i]]=old[part[i]]
						last_new=part[i]

					elif current_type == PARTTYPE_EXTENDED:
						new[part[i]]=old[part[i]]
						extended = part[i]
						last_new=part[i]


				else:
					new[part[i]]=old[part[i]]
					last_new=part[i]

			if new_primary > -1: # new primary needs free number
				new[new_primary]['num'] = primary[0]

			disc['partitions']=new

			if redo:
				return self.rebuild_table(disc,device)
			else:
				return disc

		def renum_logical(self,disk,deleted): # got to renum partitions Example: Got 5 logical on hda and remove hda7
			parts = disk['partitions'].keys()
			parts.sort()
			for part in parts:
				if disk['partitions'][part]['type'] == PARTTYPE_LOGICAL and disk['partitions'][part]['num'] > deleted:
					disk['partitions'][part]['num'] -= 1
			return disk


		def possible_type(self, disk, p_index):
			# 1 -> primary only
			# 2 -> logical only
			# 3 -> both
			# 0 -> unusable
			parts=disk['partitions'].keys()
			parts.sort()
			current=parts.index(p_index)
			if len(disk['partitions'])>1:
				if disk['extended']:
					if len(parts)-1 > current and disk['partitions'][parts[current-1]]['type'] == PARTTYPE_LOGICAL and \
						   disk['partitions'][parts[current+1]]['type'] == PARTTYPE_LOGICAL:
						return 2
					primary=0
					if disk['primary'] < 4:
						primary = 1
					if len(parts)-1 > current and disk['partitions'][parts[current+1]]['type'] == PARTTYPE_EXTENDED:
						return 2+primary
					elif disk['partitions'][parts[current-1]]['type'] == PARTTYPE_LOGICAL:
						return 2+primary
					else:
						return 0+primary

				elif disk['primary'] < 4:
					return 3
				else:
					return 0
			else:
				return 3


		def lv_create(self, vgname, lvname, currentLE, format, fstype, flag, mpoint):
			vg = self.parent.container['lvm']['vg'][ vgname ]
			size = int(vg['PEsize'] * currentLE / 1024.0)
			self.container['lvm']['vg'][vgname]['lv'][lvname] = { 'dev': '/dev/%s/%s' % (vgname, lvname),
																  'vg': vgname,
																  'touched': 1,
																  'PEsize': vg['PEsize'],
																  'currentLE': currentLE,
																  'format': format,
																  'size': size,
																  'fstype': fstype,
																  'flag': '',
																  'mpoint': mpoint,
																  }

			self.parent.container['history'].append('/sbin/lvcreate -l %d --name "%s" "%s"' % (currentLE, lvname, vgname) )
#			self.parent.container['history'].append('/sbin/lvscan 2> /dev/null')

			self.parent.debug("HISTORY")
			for h in self.parent.container['history']:
				self.parent.debug('==> %s' % h)

			# update used/free space on volume group
			self.parent.container['lvm']['vg'][ vgname ]['freePE'] -= currentLE
			self.parent.container['lvm']['vg'][ vgname ]['allocPE'] += currentLE



		def resolve_type(self,type):
			mapping = { PARTTYPE_PRIMARY: 'primary',
						PARTTYPE_LOGICAL: 'logical',
						PARTTYPE_EXTENDED: 'extended',
						PARTTYPE_FREESPACE_PRIMARY: 'free',
						PARTTYPE_FREESPACE_LOGICAL: 'free',
						8: 'meta',
						9: 'meta',
						PARTTYPE_LVM_VG: 'lvm_vg',
						PARTTYPE_LVM_LV: 'lvm_lv',
						PARTTYPE_LVM_VG_FREE: 'lvm_lv_free',
						}
			if mapping.has_key(type):
				return mapping[type]
			self.parent.debug('ERROR: resolve_type(%s)=unknown' % type)
			return 'unknown'

		def get_result(self):
			pass


		# returns False if one or more device files cannot be found - otherwise True
		def write_devices_check(self):
			missing_devices=[]
			for disk in self.container['disk'].keys():
				for part in self.container['disk'][disk]['partitions']:
					if self.container['disk'][disk]['partitions'][part]['num'] > 0 : # only valid partitions
						dev = self.parent.get_device(disk, part)
						if not os.path.exists(dev):
							missing_devices.append(dev)
			missing_devices.sort()
			if missing_devices:
				self.parent.debug('MISSING DEVICES: %s' % missing_devices)
				msglist = [ _('No device files found for following devices. Please'),
							_('decrease number of partitions on a single disk or use LVM.'),
							'' ]
				# create device list and wrap at column 55
				tmpstr = ''
				for dev in missing_devices:
					if len(tmpstr) + len(dev) > 55:
						msglist.append(tmpstr)
						tmpstr = dev
					else:
						if tmpstr == '':
							tmpstr = dev
						else:
							tmpstr += ', %s' % dev
				if len(tmpstr):
					msglist.append(tmpstr)

				self.sub = msg_win(self,self.pos_y+1,self.pos_x+1,self.width-1,2, msglist)
				self.draw()
				return False
			else:
				self.parent.debug('WRITE_DEVICES')
				self.write_devices()
				return True

		def write_devices(self):
			self.draw()
			self.act = self.active(self, _('Write partitions'), _('Please wait ...'), name='act', action='create_partitions')
			self.act.draw()
			if self.container['lvm']['enabled']:
				self.act = self.active(self, _('Create LVM Volumes'), _('Please wait ...'), name='act', action='make_filesystem')
				self.act.draw()
			self.act = self.active(self, _('Create Filesystems'), _('Please wait ...'), name='act', action='make_filesystem')
			self.act.draw()
			self.draw()

		class active(act_win):
			def __init__(self,parent,header,text,name='act',action=None):
				if action=='read_lvm':
					self.pos_x=parent.minX+(parent.maxWidth/2)-20
					self.pos_y=parent.minY+5
				else:
					self.pos_x=parent.minX+(parent.maxWidth/2)-15
					self.pos_y=parent.minY+5
				self.action = action
				act_win.__init__(self,parent,header,text,name)

			def function(self):
				if self.action == 'read_lvm':
					self.parent.parent.debug('Partition: Reading LVM config')
					self.parent.parent.read_lvm()
				elif self.action == 'create_partitions':
					self.parent.parent.debug('Partition: Create Partitions')
					for command in self.parent.container['history']:
						p=os.popen('%s 2>&1'%command)
						self.parent.parent.debug('PARTITION: running "%s"'%command)
						self.parent.parent.debug('=> %s' % p.read().replace('\n','\n=> '))
						p.close()
					self.parent.container['history']=[]
					self.parent.parent.written=1
				elif self.action == 'make_filesystem':
					self.parent.parent.debug('Partition: Create Filesystem')
					# create filesystems on physical partitions
					for disk in self.parent.container['disk'].keys():
						for part in self.parent.container['disk'][disk]['partitions'].keys():
							if self.parent.container['disk'][disk]['partitions'][part]['format']:
								device = self.parent.parent.get_device(disk, part)
								fstype=self.parent.container['disk'][disk]['partitions'][part]['fstype']
								if fstype in ['ext2','ext3','vfat','msdos']:
									mkfs_cmd='/sbin/mkfs.%s %s' % (fstype,device)
								elif fstype == 'xfs':
									mkfs_cmd='/sbin/mkfs.xfs -f %s' % device
								elif fstype == 'linux-swap':
									mkfs_cmd='/bin/mkswap %s' % device
								else:
									mkfs_cmd='/bin/true %s' % device
								p=os.popen('%s 2>&1'%mkfs_cmd)
								self.parent.parent.debug('PARTITION: running "%s"' % mkfs_cmd)
								self.parent.parent.debug('=> %s' % p.read().replace('\n','\n=> '))
								p.close()
								self.parent.container['disk'][disk]['partitions'][part]['format']=0
					# create filesystems on logical volumes
					for vgname in self.parent.container['lvm']['vg'].keys():
						vg = self.parent.container['lvm']['vg'][ vgname ]
						for lvname in vg['lv'].keys():
							if vg['lv'][lvname]['format']:
								device = vg['lv'][lvname]['dev']
								fstype = vg['lv'][lvname]['fstype']
								if fstype in ['ext2','ext3','vfat','msdos']:
									mkfs_cmd='/sbin/mkfs.%s %s' % (fstype,device)
								elif fstype == 'xfs':
									mkfs_cmd='/sbin/mkfs.xfs -f %s' % device
								elif fstype == 'linux-swap':
									mkfs_cmd='/bin/mkswap %s' % device
								else:
									mkfs_cmd='/bin/true %s' % device
								p=os.popen('%s 2>&1'%mkfs_cmd)
								self.parent.parent.debug('PARTITION: running "%s"' % mkfs_cmd)
								self.parent.parent.debug('=> %s' % p.read().replace('\n','\n=> '))
								p.close()
								vg['lv'][lvname]['format'] = 0

				self.parent.layout()
				self.stop()


		class edit(subwin):
			def __init__(self,parent,pos_x,pos_y,width,heigth):
				subwin.__init__(self,parent,pos_x,pos_y,width,heigth)

			def helptext(self):
				return self.parent.helptext()

			def no_format_callback_part_create(self, result):
				selected=self.parent.container['temp']['selected']
				mpoint=self.parent.container['temp']['mpoint']
				size=self.parent.container['temp']['size']
				fstype=self.parent.container['temp']['fstype']
				type=self.parent.container['temp']['type']
				flag=self.parent.container['temp']['flag']
				self.parent.container['temp']={}
				if result == 'BT_YES':
					format=1
					self.parent.part_create(selected,mpoint,size,fstype,type,flag,format)
				elif result == 'BT_NO':
					format=0
					self.parent.part_create(selected,mpoint,size,fstype,type,flag,format)
				return 0


			def no_format_callback_part_edit(self, result, path, part):
				fstype=self.parent.container['temp']['fstype']
				self.parent.container['temp']={}
				if result == 'BT_YES':
					format=1
				else:
					format=0
				self.parent.container['disk'][path]['partitions'][part]['format']=format
				self.parent.container['disk'][path]['partitions'][part]['fstype']=fstype
				return 0


			def input(self, key):
				dev = self.parent.part_objects[self.parent.get_elem('SEL_part').result()[0]]
				type = dev[0]
				path = dev[1]
				disk=self.parent.container['disk'][path]

				if hasattr(self,"sub"):
					if not self.sub.input(key):
						self.parent.layout()
						return 0
					return 1
				if key == 260 and self.get_elem('BT_save').active:
					#move left
					self.get_elem('BT_save').set_off()
					self.get_elem('BT_cancel').set_on()
					self.current = self.get_elem_id('BT_cancel')
					self.draw()
				elif key == 261 and self.get_elem('BT_cancel').active:
					#move right
					self.get_elem('BT_cancel').set_off()
					self.get_elem('BT_save').set_on()
					self.current = self.get_elem_id('BT_save')
					self.draw()
				elif key in [ 10, 32, 276 ]:
					if self.get_elem('BT_cancel').usable() and self.get_elem('BT_cancel').get_status():
						return 0
					elif ( self.get_elem('BT_save').usable() and self.get_elem('BT_save').get_status() ) or key == 276:
						if self.operation is 'create': # Speichern
							part=dev[2]
							mpoint=self.get_elem('INP_mpoint').result().strip()
							if self.get_elem('INP_size').result().isdigit():
								size=float(self.get_elem('INP_size').result())
							else:
								return 1
							format=self.get_elem('CB_format').result()
							fstype=self.get_elem('SEL_fstype').result()[0]
							type=int(self.get_elem('RB_pri_log').result())
							if float(disk['partitions'][part]['size']) < size:
								size=float(disk['partitions'][part]['size'])
							flag=[]
							if self.get_elem('CB_bootable').result():
								flag.append('boot')
							if self.elem_exists('CB_ppcprep') and self.get_elem('CB_ppcprep').result():
								flag.append('prep')
								flag.append('boot')
							if self.elem_exists('CB_lvmpv') and self.get_elem('CB_lvmpv').result():
								flag.append('lvm')
								mpoint=''
								format=1
								fstype='LVMPV'

							if fstype == 'linux-swap':
								mpoint=''
							if len(mpoint) > 0 and not mpoint.startswith('/'):
								mpoint='/%s' % mpoint
							self.parent.container['temp']={'selected':self.parent.get_elem('SEL_part').result()[0],
										'mpoint':mpoint,
										'size':size,
										'fstype':fstype,
										'type':type,
										'flag':flag,
										}

							msglist = [ _('The selected filesystem takes no'),
										_('effect, if format is not selected.'),
										'',
										_('Do you want to format this partition?') ]

							if not format:
								self.sub = yes_no_win(self, self.pos_y+4, self.pos_x+1, self.width-2, 0,
													  msglist=msglist, callback_yes=self.no_format_callback_part_create,
													  callback_no=self.no_format_callback_part_create, default='no' )
								self.sub.draw()
								return 1
							else:
								self.parent.container['temp']={}
								format=1

							num=0 # temporary zero
							self.parent.part_create(self.parent.get_elem('SEL_part').result()[0],mpoint,size,fstype,type,flag,format)
						elif self.operation is 'edit': # Speichern
							part=dev[2]
							mpoint=self.get_elem('INP_mpoint').result().strip()
							fstype=self.get_elem('SEL_fstype').result()[0]
							flag=[]
							if self.get_elem('CB_bootable').result():
								flag.append('boot')
							if self.elem_exists('CB_ppcprep') and self.get_elem('CB_ppcprep').result():
								flag.append('prep')
								flag.append('boot')

							self.parent.container['temp']={'fstype':fstype}
							if fstype == 'linux-swap':
								mpoint=''
							if len(mpoint) > 0 and not mpoint.startswith('/'):
								mpoint='/%s' % mpoint
							self.parent.container['disk'][path]['partitions'][part]['mpoint']=mpoint
							#if self.get_elem('CB_bootable').result():
							old_flags=self.parent.container['disk'][path]['partitions'][part]['flag']

							for f in old_flags:
								if f not in flag:
									self.parent.container['history'].append('/sbin/parted --script %s set %d %s off' % (path,self.parent.container['disk'][path]['partitions'][part]['num'],f))
							for f in flag:
								if f not in old_flags:
									self.parent.container['history'].append('/sbin/parted --script %s set %d %s on' % (path,self.parent.container['disk'][path]['partitions'][part]['num'],f))

							self.parent.container['disk'][path]['partitions'][part]['flag']=flag

							rootfs = (mpoint == '/')
							# if format is not set and mpoint == '/' OR
							#    format is not set and fstype changed
							if ( self.parent.container['disk'][path]['partitions'][part]['fstype'] != fstype or rootfs) and not self.get_elem('CB_format').result():
								if rootfs:
									msglist = [ _('This partition is designated as root filesystem,'),
												_('but "format" is not selected. This can cause'),
												_('problems with preexisting data on disk!'),
												'',
												_('Do you want to format this partition?')
												]
								else:
									msglist = [ _('The selected filesystem takes no'),
												_('effect, if "format" is not selected.'),
												'',
												_('Do you want to format this partition?')
												]

								self.sub = yes_no_win(self, self.pos_y+4, self.pos_x+1, self.width-2, 0,
													  msglist=msglist, callback_yes=self.no_format_callback_part_edit,
													  callback_no=self.no_format_callback_part_edit, default='no', path=path, part=part )
								self.sub.draw()
								return 1
							else:
								self.parent.container['temp']={}
								if self.get_elem('CB_format').result():
									self.parent.container['disk'][path]['partitions'][part]['format']=1
								else:
									self.parent.container['disk'][path]['partitions'][part]['format']=0
								self.parent.container['disk'][path]['partitions'][part]['fstype']=fstype
						self.parent.container['disk'][path]=self.parent.rebuild_table(disk,path)

						self.parent.layout()
						self.parent.draw()
						return 0
					elif key == 10 and self.get_elem_by_id(self.current).usable():
						return self.get_elem_by_id(self.current).key_event(key)
				if self.get_elem_by_id(self.current).usable():
					self.get_elem_by_id(self.current).key_event(key)
				if self.operation == 'edit':
					# if partition is LVM PV
					if not self.elem_exists('CB_lvmpv'):
						self.get_elem('INP_mpoint').enable()
						self.get_elem('SEL_fstype').enable()
						self.get_elem('CB_format').enable()
						self.get_elem('CB_bootable').enable()
						if self.elem_exists('CB_ppcprep'):
							self.get_elem('CB_ppcprep').enable()

						if 'linux-swap' in self.get_elem('SEL_fstype').result():
							self.get_elem('INP_mpoint').disable()
						else:
							self.get_elem('INP_mpoint').enable()
						if self.current == self.get_elem_id('INP_mpoint'):
							self.get_elem('INP_mpoint').set_on()
							self.get_elem('INP_mpoint').draw()
						
				elif self.operation == 'create':
					if self.elem_exists('CB_lvmpv') and self.get_elem('CB_lvmpv').result():
						# partition is LVM PV
						self.get_elem('INP_mpoint').disable()
						self.get_elem('SEL_fstype').disable()
						self.get_elem('CB_format').disable()
						self.get_elem('CB_bootable').disable()
						if self.elem_exists('CB_ppcprep'):
							self.get_elem('CB_ppcprep').disable()
					else:
						# partition is no LVM PV
						self.get_elem('INP_mpoint').enable()
						self.get_elem('SEL_fstype').enable()
						self.get_elem('CB_format').enable()
						self.get_elem('CB_bootable').enable()
						if self.elem_exists('CB_ppcprep'):
							self.get_elem('CB_ppcprep').enable()

						if 'linux-swap' in self.get_elem('SEL_fstype').result():
							self.get_elem('INP_mpoint').disable()
						else:
							self.get_elem('INP_mpoint').enable()
					if self.current == self.get_elem_id('INP_mpoint'):
						self.get_elem('INP_mpoint').set_on()
						self.get_elem('INP_mpoint').draw()
				return 1

			def get_result(self):
				pass

			def layout(self):
				dev = self.parent.part_objects[self.parent.get_elem('SEL_part').result()[0]]
				type = dev[0]
				path = dev[1]
				disk=self.parent.container['disk'][path]
				self.operation=''

				if type is 'disk': # got a diskdrive
					self.operation='diskinfo'
					self.add_elem('TXT_1',textline(_('Physical Diskdrive'),self.pos_y+2,self.pos_x+2))#0
					self.add_elem('TXT_2',textline(_('Device: %s') % path,self.pos_y+4,self.pos_x+2))#1
					self.add_elem('TXT_3',textline(_('Size: %s') % disk['size'],self.pos_y+6,self.pos_x+2))#2
					self.add_elem('D1',dummy())#3
					self.add_elem('TXT_4',textline(_('Primary Partitions: %s') % disk[(_('primary'))],self.pos_y+10,self.pos_x+2))#4
					self.add_elem('TXT_5',textline(_('Logical Partitions: %s') % disk[(_('logical'))],self.pos_y+12,self.pos_x+2))#5
					self.add_elem('D2',dummy())#6
					self.add_elem('D3',dummy())#7
					self.add_elem('D4',dummy())#8
					self.add_elem('D5',dummy())#9
					self.add_elem('BT_next',button(_("Next"),self.pos_y+17,self.pos_x+20,15)) #10
					self.add_elem('D6',dummy())#11
					self.current=self.get_elem_id('BT_next')
					self.get_elem_by_id(self.current).set_on()

				elif type is 'part':
					start = dev[2]
					partition=disk['partitions'][start]
					part_type=self.parent.resolve_type(partition['type'])
					if partition['type'] is PARTTYPE_FREESPACE_PRIMARY or partition['type'] is PARTTYPE_FREESPACE_LOGICAL: # got freespace
						self.operation='create'
						self.add_elem('TXT_1', textline(_('New Partition:'),self.pos_y+2,self.pos_x+5)) #0

						self.add_elem('TXT_2', textline(_('Mount-Point:'),self.pos_y+4,self.pos_x+5)) #1
						self.add_elem('INP_mpoint', input(partition['mpoint'],self.pos_y+4,self.pos_x+6+len(_('Mount-Point:')),20)) #2
						self.add_elem('TXT_3', textline(_('Size (MB):'),self.pos_y+6,self.pos_x+5)) #3
						self.add_elem('INP_size', input('%s' % int(partition['size']),self.pos_y+6,self.pos_x+6+len(_('Mount-Point:')),20)) #4
						self.add_elem('TXT_4', textline(_('Filesystem'),self.pos_y+8,self.pos_x+5)) #5

						try:
							file=open('modules/filesystem')
						except:
							file=open('/lib/univention-installer/modules/filesystem')
						dict={}
						filesystem_num=0
						filesystem=file.readlines()
						for line in range(len(filesystem)):
							fs=filesystem[line].split(' ')
							if len(fs) > 1:
								entry = fs[1][:-1]
								dict[entry]=[entry,line]
						file.close()
						self.add_elem('SEL_fstype', select(dict,self.pos_y+9,self.pos_x+4,15,6)) #6
						self.get_elem('SEL_fstype').set_off()
						dict={}
						if self.parent.possible_type(disk, start) is 1:
							dict[_('primary')]=[0]
						elif self.parent.possible_type(disk, start) is 2:
							dict[_('logical')]=[1]
						elif self.parent.possible_type(disk, start) is 3:
							dict[_('primary')]=[0]
							dict[_('logical')]=[1]
						self.add_elem('RB_pri_log', radiobutton(dict,self.pos_y+9,self.pos_x+33,10,2,[0])) #7

						self.add_elem('CB_bootable', checkbox({_('bootable'):'1'},self.pos_y+12,self.pos_x+33,11,1,[])) #8
						if self.parent.parent.cmdline.has_key('architecture') and self.parent.parent.cmdline['architecture'] == 'powerpc':
							self.add_elem('CB_ppcprep', checkbox({_('PPC PreP'):'1'},self.pos_y+13,self.pos_x+33,11,1,[])) #9
						if self.operation == 'create':
							self.add_elem('CB_format', checkbox({_('format'):'1'},self.pos_y+14,self.pos_x+33,14,1,[0])) #10
						else:
							self.add_elem('CB_format', checkbox({_('format'):'1'},self.pos_y+14,self.pos_x+33,14,1,[])) #10
						if self.parent.container['lvm']['enabled']:
							self.add_elem('CB_lvmpv', checkbox({_('LVM PV'):'1'},self.pos_y+15,self.pos_x+33,14,1,[])) #13
						self.add_elem('BT_save', button("F12-"+_("Save"),self.pos_y+17,self.pos_x+(self.width)-4,align="right")) #11
						self.add_elem('BT_cancel', button("ESC-"+_("Cancel"),self.pos_y+17,self.pos_x+4,align="left")) #12

						self.current=self.get_elem_id('INP_mpoint')
						self.get_elem('INP_mpoint').set_on()
					else:  #got a valid partition
						self.operation='edit'
						self.add_elem('TXT_1', textline(_('Partition: %s') % self.parent.dev_to_part(partition,path,type="full"),self.pos_y+2,self.pos_x+5))#0
						if part_type== "primary":
							self.add_elem('TXT_2', textline(_('Typ: primary'),self.pos_y+4,self.pos_x+5))#1
						else:
							self.add_elem('TXT_2', textline(_('Typ: logical'),self.pos_y+4,self.pos_x+5))#1
						self.add_elem('TXT_3', textline(_('Size: %s MB') % int(partition['size']),self.pos_y+4,self.pos_x+33))#2
						self.add_elem('TXT_4', textline(_('Filesystem'),self.pos_y+7,self.pos_x+5)) #3

						try:
							file=open('modules/filesystem')
						except:
							file=open('/lib/univention-installer/modules/filesystem')
						dict={}
						filesystem_num=0
						filesystem=file.readlines()
						for line in range(0, len(filesystem)):
							fs=filesystem[line].split(' ')
							if len(fs) > 1:
								entry = fs[1][:-1]
								dict[entry]=[entry,line]
								if entry == partition['fstype']:
									filesystem_num=line
						file.close()
						self.add_elem('SEL_fstype', select(dict,self.pos_y+8,self.pos_x+4,15,6, filesystem_num)) #4
						self.add_elem('TXT_5', textline(_('Mount-Point'),self.pos_y+7,self.pos_x+33)) #5
						self.add_elem('INP_mpoint', input(partition['mpoint'],self.pos_y+8,self.pos_x+33,20)) #6
						if 'boot' in partition['flag']:
							self.add_elem('CB_bootable', checkbox({_('bootable'):'1'},self.pos_y+10,self.pos_x+33,11,1,[0])) #7
						else:
							self.add_elem('CB_bootable', checkbox({_('bootable'):'1'},self.pos_y+10,self.pos_x+33,11,1,[])) #7
						if self.parent.parent.cmdline.has_key('architecture') and self.parent.parent.cmdline['architecture'] == 'powerpc':
							if 'prep' in partition['flag']:
								self.add_elem('CB_ppcprep', checkbox({_('PPC PreP'):'1'},self.pos_y+11,self.pos_x+33,11,1,[0])) #9
							else:
								self.add_elem('CB_ppcprep', checkbox({_('PPC PreP'):'1'},self.pos_y+11,self.pos_x+33,11,1,[])) #9
						if partition['format']:
							self.add_elem('CB_format', checkbox({_('format'):'1'},self.pos_y+12,self.pos_x+33,14,1,[0])) #10
						else:
							self.add_elem('CB_format', checkbox({_('format'):'1'},self.pos_y+12,self.pos_x+33,14,1,[])) #10

						self.add_elem('BT_save', button("F12-"+_("Save"),self.pos_y+17,self.pos_x+(self.width)-8,align="right")) #11
						self.add_elem('BT_cancel', button("ESC-"+_("Cancel"),self.pos_y+17,self.pos_x+6,15)) #12
						if filesystem_num == 3:
							self.get_elem('INP_mpoint').disable()


		class edit_lvm_lv(subwin):
			def __init__(self,parent,pos_x,pos_y,width,heigth):
				self.close_on_subwin_exit = False
				subwin.__init__(self,parent,pos_x,pos_y,width,heigth)

			def helptext(self):
				return self.parent.helptext()

			def no_format_callback(self, result, lv):
				if result == 'BT_YES':
					format=1
				else:
					format=0
				lv['format'] = format
				return result

			def input(self, key):
				parttype, vgname, lvname = self.parent.part_objects[self.parent.get_elem('SEL_part').result()[0]]

				if hasattr(self,"sub"):
					res = self.sub.input(key)
					if not res:
						if not self.sub.incomplete():
							self.sub.exit()
							self.draw()
							if self.close_on_subwin_exit:
								return 0
					return 1
				elif key == 260 and self.get_elem('BT_save').active:
					#move left
					self.get_elem('BT_save').set_off()
					self.get_elem('BT_cancel').set_on()
					self.current = self.get_elem_id('BT_cancel')
					self.draw()
				elif key == 261 and self.get_elem('BT_cancel').active:
					#move right
					self.get_elem('BT_cancel').set_off()
					self.get_elem('BT_save').set_on()
					self.current = self.get_elem_id('BT_save')
					self.draw()
				elif key in [ 10, 32, 276 ]:
					if self.get_elem('BT_cancel').usable() and self.get_elem('BT_cancel').get_status():
						return 0
					elif ( self.get_elem('BT_save').usable() and self.get_elem('BT_save').get_status() ) or key == 276:

						if self.operation is 'create': # save new logical volume

							vg = self.parent.container['lvm']['vg'][ vgname ]

							# get values

							lvname = self.get_elem('INP_name').result()
							mpoint = self.get_elem('INP_mpoint').result().strip()
							if self.get_elem('INP_size').result().isdigit():
								size = float(self.get_elem('INP_size').result())
							else:
								size = None
							format = self.get_elem('CB_format').result()
							fstype = self.get_elem('SEL_fstype').result()[0]

							# do some consistency checks
							lvname_ok = True
							for c in lvname:
								if not(c.isalnum() or c == '_'):
									lvname_ok = False

							if not lvname or lvname in vg['lv'].keys() or not lvname_ok:
								if not lvname:
									msglist = [ _('Please enter volume name!') ]
								elif not lvname_ok:
									msglist = [ _('Logical volume name contains illegal characters!') ]
								else:
									msglist = [ _('Logical volume name is already in use!') ]

								self.get_elem_by_id(self.current).set_off()
								self.current=self.get_elem_id('INP_name')
								self.get_elem_by_id(self.current).set_on()

								self.sub = msg_win(self,self.pos_y+4,self.pos_x+1,self.width-2,7, msglist)
								self.draw()
								return 1

							if size == None:
								self.get_elem_by_id(self.current).set_off()
								self.current=self.get_elem_id('INP_size')
								self.get_elem_by_id(self.current).set_on()

								msglist = [ _('Size contains non-digit characters!') ]
								self.sub = msg_win(self,self.pos_y+4,self.pos_x+1,self.width-2,7, msglist)
								self.draw()
								return 1

							currentLE = int(round(size * 1024.0 / vg['PEsize'] + 0.5))
							if currentLE > vg['freePE']:  # decrease logical volume by one physical extent - maybe it fits then
								currentLE -= 1
							if currentLE > vg['freePE']:
								self.get_elem_by_id(self.current).set_off()
								self.current=self.get_elem_id('INP_size')
								self.get_elem_by_id(self.current).set_on()

								msglist = [ _('Not enough free space on volume group!') ]
								self.sub = msg_win(self,self.pos_y+4,self.pos_x+1,self.width-2,7, msglist)
								self.draw()
								return 1
							size = int(vg['PEsize'] * currentLE / 1024.0)

							# data seems to be ok ==> create LVM LV
							self.parent.lv_create(vgname, lvname, currentLE, format, fstype, '', mpoint)

							msglist = [ _('The selected filesystem takes no'),
										_('effect, if format is not selected.'),
										'',
										_('Do you want to format this partition?') ]

							if not format:
								self.close_on_subwin_exit = True
								self.sub = yes_no_win(self, self.pos_y+4, self.pos_x+1, self.width-2, 0,
													  msglist=msglist, callback_yes=self.no_format_callback,
													  callback_no=self.no_format_callback, default='no', lv=vg['lv'][lvname] )
								self.sub.draw()
								return 1

						elif self.operation is 'edit': # Speichern

							# get and save values

							oldfstype = self.parent.container['lvm']['vg'][vgname]['lv'][lvname]['fstype']
							fstype = self.get_elem('SEL_fstype').result()[0]
							self.parent.container['lvm']['vg'][vgname]['lv'][lvname]['touched'] = 1
							self.parent.container['lvm']['vg'][vgname]['lv'][lvname]['mpoint'] = self.get_elem('INP_mpoint').result().strip()
							self.parent.container['lvm']['vg'][vgname]['lv'][lvname]['format'] = self.get_elem('CB_format').result()
							self.parent.container['lvm']['vg'][vgname]['lv'][lvname]['fstype'] = fstype

							rootfs = (self.parent.container['lvm']['vg'][vgname]['lv'][lvname]['mpoint'] == '/')
							# if format is not set and mpoint == '/' OR
							#    format is not set and fstype changed
							if ( oldfstype != fstype or rootfs) and not self.get_elem('CB_format').result():
								if rootfs:
									msglist = [ _('This volume is designated as root filesystem,'),
												_('but "format" is not selected. This can cause'),
												_('problems with preexisting data on disk!'),
												'',
												_('Do you want to format this partition?')
												]
								else:
									msglist = [ _('The selected filesystem takes no'),
												_('effect, if "format" is not selected.'),
												'',
												_('Do you want to format this partition?')
												]

								self.close_on_subwin_exit = True
								self.sub = yes_no_win(self, self.pos_y+4, self.pos_x+1, self.width-2, 0,
													  msglist=msglist, callback_yes=self.no_format_callback,
													  callback_no=self.no_format_callback, default='no',
													  lv=self.parent.container['lvm']['vg'][vgname]['lv'][lvname] )
								self.sub.draw()
								return 1


						self.parent.layout()
						self.parent.draw()

						return 0

					elif key == 10 and self.get_elem_by_id(self.current).usable():
						return self.get_elem_by_id(self.current).key_event(key)

				if self.get_elem_by_id(self.current).usable():
					self.get_elem_by_id(self.current).key_event(key)

				return 1

			def get_result(self):
				pass

			def layout(self):
				parttype, vgname, lvname = self.parent.part_objects[self.parent.get_elem('SEL_part').result()[0]]
				self.operation=''

				if parttype is 'lvm_vg_free':  # FREE SPACE ON VOLUME GROUP
					vg = self.parent.container['lvm']['vg'][ vgname ]
					maxsize = (vg['PEsize'] * vg['freePE'] / 1024)

					lvname_proposal = ''
					for i in range(1,255):
						if not vg['lv'].has_key('vol%d' % i):
							lvname_proposal = 'vol%d' % i
							break

					self.operation='create'
					self.add_elem('TXT_0', textline(_('New Logical Volume:'),self.pos_y+2,self.pos_x+5)) #0
					self.add_elem('INP_name', input(lvname_proposal,self.pos_y+2,self.pos_x+5+len(_('New Logical Volume:'))+1,20)) #2
					self.add_elem('TXT_1', textline(_('Mount-Point:'),self.pos_y+4,self.pos_x+5)) #1
					self.add_elem('INP_mpoint', input('',self.pos_y+4,self.pos_x+5+len(_('Mount-Point:'))+1,20)) #2
					self.add_elem('TXT_3', textline(_('Size (MB):'),self.pos_y+6,self.pos_x+5)) #3
					self.add_elem('INP_size', input('%s' % int(maxsize),self.pos_y+6,self.pos_x+5+len(_('Mount-Point:'))+1,20)) #4
					self.add_elem('TXT_5', textline(_('Filesystem'),self.pos_y+8,self.pos_x+5)) #5

					try:
						file=open('modules/filesystem')
					except:
						file=open('/lib/univention-installer/modules/filesystem')
					dict={}
					filesystem_num=0
					filesystem=file.readlines()
					i=0
					for line in filesystem:
						fs=line.split(' ')
						if len(fs) > 1:
							entry = fs[1][:-1]
							if entry != 'linux-swap':   # disable swap on LVM
								dict[entry]=[entry,i]
								i += 1
					file.close()
					self.add_elem('SEL_fstype', select(dict,self.pos_y+9,self.pos_x+4,15,6)) #6
					self.get_elem('SEL_fstype').set_off()

					self.add_elem('CB_format', checkbox({_('format'):'1'},self.pos_y+14,self.pos_x+33,14,1,[0])) #7

					self.add_elem('BT_save', button("F12-"+_("Save"),self.pos_y+17,self.pos_x+(self.width)-4,align="right")) #8
					self.add_elem('BT_cancel', button("ESC-"+_("Cancel"),self.pos_y+17,self.pos_x+4,align="left")) #9

					self.current=self.get_elem_id('INP_name')
					self.get_elem_by_id(self.current).set_on()
				elif parttype is 'lvm_lv':  # EXISTING LOGICAL VOLUME
					lv = self.parent.container['lvm']['vg'][ vgname ]['lv'][ lvname ]
					self.operation='edit'
					self.add_elem('TXT_0', textline(_('LVM Logical Volume: %s') % lvname,self.pos_y+2,self.pos_x+5))#0
					self.add_elem('TXT_2', textline(_('Size: %s MB') % int(lv['size']),self.pos_y+4,self.pos_x+5))#2
					self.add_elem('TXT_3', textline(_('Filesystem'),self.pos_y+7,self.pos_x+5)) #3

					try:
						file=open('modules/filesystem')
					except:
						file=open('/lib/univention-installer/modules/filesystem')
					dict={}
					filesystem_num=0
					filesystem=file.readlines()
					i=0
					for line in filesystem:
						fs=line.split(' ')
						if len(fs) > 1:
							entry = fs[1][:-1]
							if entry != 'linux-swap':   # disable swap on LVM
								dict[entry]=[entry,i]
								if entry == lv['fstype']:
									filesystem_num=i
								i += 1
					file.close()
					self.add_elem('SEL_fstype', select(dict,self.pos_y+8,self.pos_x+4,15,6, filesystem_num)) #4
					self.add_elem('TXT_5', textline(_('Mount-Point'),self.pos_y+7,self.pos_x+33)) #5
					self.add_elem('INP_mpoint', input(lv['mpoint'],self.pos_y+8,self.pos_x+33,20)) #6

					if lv['format']:
						self.add_elem('CB_format', checkbox({_('format'):'1'},self.pos_y+12,self.pos_x+33,14,1,[0])) #7
					else:
						self.add_elem('CB_format', checkbox({_('format'):'1'},self.pos_y+12,self.pos_x+33,14,1,[])) #7

					self.add_elem('BT_save', button("F12-"+_("Save"),self.pos_y+17,self.pos_x+(self.width)-8,align="right")) #8
					self.add_elem('BT_cancel', button("ESC-"+_("Cancel"),self.pos_y+17,self.pos_x+6,15)) #9

		class del_extended(subwin):
			def input(self, key):
				if key in [ 10, 32 ]:
					if self.elements[3].get_status():
						self.parent.part_delete(self.parent.get_elem('SEL_part').result()[0])
						self.parent.layout()
						return 0
					elif self.elements[4].get_status():
						return 0
				elif key == 260 and self.elements[4].active:
					#move left
					self.elements[4].set_off()
					self.elements[3].set_on()
					self.current=3
					self.draw()
				elif key == 261 and self.elements[3].active:
					#move right
					self.elements[3].set_off()
					self.elements[4].set_on()
					self.current=4
					self.draw()
				return 1

			def layout(self):
				message=_('The selected partition is the extended partition of this disc.')
				self.elements.append(textline(message,self.pos_y+2,self.pos_x+2)) #0
				message=_('The extended partition contains all logical partitions.')
				self.elements.append(textline(message,self.pos_y+3,self.pos_x+2)) #1
				message=_('Do you really want to delete all logical partitions?')
				self.elements.append(textline(message,self.pos_y+5,self.pos_x+2)) #2

				self.elements.append(button(_("Yes"),self.pos_y+8,self.pos_x+10,15)) #3
				self.elements.append(button(_("No"),self.pos_y+8,self.pos_x+40,15)) #4
				self.current=4
				self.elements[4].set_on()

			def get_result(self):
				pass

		class resize_extended(subwin):
			def input(self, key):
				if key in [ 10, 32 ]:
					if self.elements[2].get_status():
						if self.elements[2].get_status():
							for disk in self.parent.container['temp'].keys():
								self.parent.parent.debug('resize_extended: disk=%s   temp=%s' % (disk, self.parent.container['temp']))
								part=self.parent.container['temp'][disk][0]
								start=self.parent.container['temp'][disk][1]
								end=self.parent.container['temp'][disk][2]
								self.parent.parent.debug('resize_extended: end=%s  start=%s' % (end, start))
								self.parent.container['disk'][disk]['partitions'][part]['size']=end-start
								self.parent.container['disk'][disk]['partitions'][start]=self.parent.container['disk'][disk]['partitions'][part]
								self.parent.container['history'].append('/sbin/parted --script %s resize %s %s %s' %
																		(disk,
																		 self.parent.container['disk'][disk]['partitions'][part]['num'],
																		 self.parent.parent.MiB2MB(start),
																		 self.parent.parent.MiB2MB(end)))
								self.parent.parent.debug('COMMAND: /sbin/parted --script %s resize %s %s %s' %
														 (disk,
														  self.parent.container['disk'][disk]['partitions'][part]['num'],
														  self.parent.parent.MiB2MB(start),
														  self.parent.parent.MiB2MB(end)))
								self.parent.container['disk'][disk]['partitions'].pop(part)
						self.parent.container['temp']={}
						self.parent.rebuild_table(self.parent.container['disk'][disk],disk)
						self.parent.layout()
						return 0
				return 1

			def layout(self):
				message=_('Found over-sized extended partition.')
				self.elements.append(textline(message,self.pos_y+2,self.pos_x+2)) #0
				message=_('This program will resize them to free unused space')
				self.elements.append(textline(message,self.pos_y+3,self.pos_x+2)) #1

				self.elements.append(button(_("OK"),self.pos_y+6,self.pos_x+30,15)) #2
				self.current=2
				self.elements[2].set_on()
			def get_result(self):
				pass


		class ask_lvm_vg(subwin):
			def input(self, key):
				if key in [ 10, 32 ]:
					if self.elements[4].get_status(): #Ok
						return self._ok()
				elif key == 260 and self.elements[4].active:
					#move left
					self.elements[4].set_off()
					self.elements[3].set_on()
					self.current=3
					self.draw()
				elif key == 261 and self.elements[3].active:
					#move right
					self.elements[3].set_off()
					self.elements[4].set_on()
					self.current=4
					self.draw()
				if self.elements[self.current].usable():
					self.elements[self.current].key_event(key)
				return 1

			def layout(self):
				message=_('UCS Installer supports only one LVM volume group.')
				self.elements.append(textline(message,self.pos_y+2,self.pos_x+(self.width/2),align="middle")) #0
				message=_('Please select volume group to use for installation.')
				self.elements.append(textline(message,self.pos_y+3,self.pos_x+(self.width/2),align="middle")) #1
				message=_('Volume Group:')
				self.elements.append(textline(message,self.pos_y+5,self.pos_x+2)) #2

				dict = {}
				line = 0
				for vg in self.parent.container['lvm']['vg'].keys():
					dict[ vg ] = [ vg, line ]
					line += 1
				default_line = 0
				self.elements.append(select(dict,self.pos_y+6,self.pos_x+3,self.width-6,4, default_line)) #3

				self.elements.append(button(_("OK"),self.pos_y+11,self.pos_x+(self.width/2)-7,15)) #4
				self.current=3
				self.elements[3].set_on()
			def _ok(self):
				self.parent.set_lvm(True, vgname = self.elements[3].result()[0] )
				return 0

		class verify(subwin):
			def input(self, key):
				if key in [ 10, 32 ]:
					if self.elements[2].get_status(): #Yes
						return self._ok()
					elif self.elements[3].get_status(): #No
						return self._false()
				elif key == 260 and self.elements[3].active:
					#move left
					self.elements[3].set_off()
					self.elements[2].set_on()
					self.current=2
					self.draw()
				elif key == 261 and self.elements[2].active:
					#move right
					self.elements[2].set_off()
					self.elements[3].set_on()
					self.current=3
					self.draw()
				return 1
			def layout(self):
				message=_('Do you really want to write all changes?')
				self.elements.append(textline(message,self.pos_y+2,self.pos_x+(self.width/2),align="middle")) #0
				message=_('This may destroy all data on modified discs!')
				self.elements.append(textline(message,self.pos_y+4,self.pos_x+(self.width/2),align="middle")) #1

				self.elements.append(button(_("Yes"),self.pos_y+7,self.pos_x+5,15)) #2
				self.elements.append(button(_("No"),self.pos_y+7,self.pos_x+35,15)) #3
				self.current=3
				self.elements[3].set_on()
			def _ok(self):
				if not self.parent.write_devices_check():
					return 1  # do not return 0 ==> will close self.sub, but write_devices_check replaced self.sub with new msg win
				return 0
			def _false(self):
				return 0

		class verify_exit(verify):
			def _ok(self):
				if self.parent.write_devices_check():
					return 'next'
				return 1  # do not return 0 ==> will close self.sub, but write_devices_check replaced self.sub with new msg win

			def _false(self):
				return 0

		class no_disk(subwin):
			def input(self, key):
				if key in [ 10, 32 ]:
					if self.elements[2].get_status(): #Yes
						return self._ok()
				return 1
			def layout(self):
				message=_('No disk detected!')
				self.elements.append(textline(message,self.pos_y+2,self.pos_x+(self.width/2),align="middle")) #0
				message=_('Please try to load the suitable module and rescan!')
				self.elements.append(textline(message,self.pos_y+4,self.pos_x+(self.width/2),align="middle")) #1

				self.elements.append(button(_("Ok"),self.pos_y+7,self.pos_x+(self.width/2),15,align="middle")) #2
				self.current=3
				self.elements[3].set_on()
			def _ok(self):
				if not self.parent.write_devices_check():
					return 1  # do not return 0 ==> will close self.sub, but write_devices_check replaced self.sub with new msg win
				return 0


		class wrong_rootfs(subwin):
			def layout(self):
				message=_('Wrong filesystem type for mount-point "/" !')
				self.elements.append(textline(message,self.pos_y+2,self.pos_x+(self.width/2),align="middle")) #0
				message=_('Please choose another filesystem.')
				self.elements.append(textline(message,self.pos_y+4,self.pos_x+(self.width/2),align="middle")) #1

				self.elements.append(button(_("Ok"),self.pos_y+7,self.pos_x+(self.width/2),15,align="middle")) #2
				self.current=3
				self.elements[3].set_on()

			def _ok(self):
				return 0
