# -*- coding: iso-8859-15 -*-

try:
	import univention.ucslint.base as uub
except:
	import ucslint.base as uub
import re, os

# 1) check if translation strings are correct; detect something like  _('foo %s bar' % var)  ==> _('foo %s bar') % var
# 2) check if all translation strings are translated in de.po file

class UniventionPackageCheck(uub.UniventionPackageCheckBase):
	def __init__(self):
		uub.UniventionPackageCheckBase.__init__(self)
		self.name = '0008-Translations'

	def getMsgIds(self):
		return { '0008-1': [ uub.RESULT_ERROR, 'file contains construct like _("foo %s bar" % var) that cannot be translated correctly' ],
				 '0008-2': [ uub.RESULT_WARN, 'failed to open file' ],
				 '0008-3': [ uub.RESULT_ERROR, 'po-file contains "fuzzy" string' ],
				 '0008-4': [ uub.RESULT_WARN, 'po-file contains empty msg string' ],
				 '0008-5': [ uub.RESULT_ERROR, 'po-file contains no character set definition' ],
				 '0008-6': [ uub.RESULT_ERROR, 'po-file contains invalid character set definition' ],
				 }

	def postinit(self, path):
		""" checks to be run before real check or to create precalculated data for several runs. Only called once! """
		pass

	def check(self, path):
		""" the real check """

		fnlist_joinscripts = {}

		if not os.path.isdir( os.path.join(path, 'debian') ):
			print "ERROR: directory %s does not exist!" % path
			return

		regEx1 = re.compile("[\\(\\[\\{\s,:]_\\(\s*'[^']+'\s*%", re.DOTALL)
		regEx2 = re.compile('[\\(\\[\\{\s,:]_\\(\s*"[^"]+"\s*%', re.DOTALL)

		py_files = []
		po_files = []
		for dirpath, dirnames, filenames in os.walk( path ):
			if '/.svn/' in dirpath and dirpath.endswith('/.svn'):   # ignore svn files
				continue
			for fn in filenames:
				if fn.endswith('.py'):
					py_files.append( os.path.join( dirpath, fn ) )
				if fn.endswith('.po'):
					po_files.append( os.path.join( dirpath, fn ) )

		for fn in py_files:
			try:
				content = open(fn, 'r').read()
			except:
				self.msg.append( uub.UPCMessage( '0008-2', 'failed to open and read file %s' % fn ) )
				continue
			self.debug('testing %s' % fn)
			for regex in (regEx1, regEx2):
				flen = len(content)
				pos = 0
				while pos < flen:
					match = regex.search( content, pos )
					if not match:
						pos = flen+1
					else:
						line = content.count('\n', 0, match.start()) + 1
						pos = match.end()
						self.msg.append( uub.UPCMessage( '0008-1', '%s contains construct like _("foo %%s bar" %% var) in line %d' % (fn, line) ) )

		regEx1 = re.compile('\n#.*?fuzzy')
		regEx2 = re.compile('msgstr ""\n\n', re.DOTALL)
		regExCharset = re.compile('"Content-Type: text/plain; charset=(.*?)\\\\n"', re.DOTALL)

		for fn in po_files:
			try:
				content = open(fn, 'r').read()
			except:
				self.msg.append( uub.UPCMessage( '0008-2', 'failed to open and read file %s' % fn ) )
				continue

			match = regExCharset.search( content )
			if not match:
				self.msg.append( uub.UPCMessage( '0008-5', 'cannot find charset definition in %s' % fn ) )
			elif not match.group(1).lower() in ('utf-8'):
				self.msg.append( uub.UPCMessage( '0008-6', 'invalid charset (%s) defined in %s' % (match.group(1), fn) ) )

			self.debug('testing %s' % fn)
			for regex, errid, errtxt in [ (regEx1, '0008-3', '%s contains "fuzzy" in line %d'),
										  (regEx2, '0008-4', '%s contains empty msgstr in line %d') ]:
				flen = len(content)
				pos = 0
				while pos < flen:
					match = regex.search( content, pos )
					if not match:
						pos = flen+1
					else:
						# match.start() + 1 ==> avoid wrong line numbers because regEx1 starts with \n
						line = content.count('\n', 0, match.start() + 1 ) + 1
						pos = match.end()
						self.msg.append( uub.UPCMessage( errid, errtxt % (fn, line) ) )

