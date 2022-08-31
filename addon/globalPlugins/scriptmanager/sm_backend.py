import datetime
import addonHandler
import os
import config
import sys
import api
import appModuleHandler
import ui
import config
addonHandler.initTranslation()

def userappmoduleexists(appname):
	userconfigfile = config.getScratchpadDir(True)+os.sep+'appModules'+os.sep+appname+'.py'
	if os.access(userconfigfile,os.F_OK): return userconfigfile
	else: return None

def appmoduleprovidedbyaddon(appname):
	ret = None
	for addon in addonHandler.getRunningAddons():
		if os.access(addon.path+os.sep+'appmodules'+os.sep+appname+'.py',os.F_OK): ret = addon
	return ret

def copyappmodulefromaddon(appname, addon):
	addonname = addon.manifest['name']
	addonfullpath = addon.path+os.sep+'appmodules'+os.sep+appname+'.py'
	userconfigfile = config.getScratchpadDir(True)+os.sep+'appModules'+os.sep+appName+'.py'
	fd1 = open(addonfullpath,'r')
	fd2 = open(userconfigfile,'a')
	ui.message(_("copying appmodule for {appname} from addon {addonname} to user's config folder...").format(addonname=addonname, appname=appname))
	for line in fd1:
		fd2.write(line)
	fd2.close()
	fd1.close()

def createnewmodule(moduletype, modulename, createfile):
	l = moduletype[0].lower()
	u = moduletype[0].upper()
	module_template = [
		'#'+moduletype+'s/'+modulename+'.py',
		'# '+_('A part of NonVisual Desktop Access (NVDA)'),
		'# '+_('Copyright (C) 2006-{year} NVDA Contributors').format(year=datetime.date.today().year),
		'# '+_('This file is covered by the GNU General Public License.'),
		'# '+_('See the file COPYING for more details.'),
		'import '+moduletype+'Handler',
		'import controlTypes',
		'import api',
		'from scriptHandler import script',
		'import addonHandler',
		'addonHandler.initTTranslation()',
		'class '+moduletype.replace(l, u, 1)+'('+moduletype+'Handler.'+moduletype.replace(l, u, 1)+'):']
	if moduletype in ['appModule', 'globalPlugin']:
		module_template += [chr(9)+'# '+_('some snapshot variables similar to these in the python console'),
			chr(9)+'nav = api.getNavigatorObject()',
			chr(9)+'focus = api.getFocusObject()',
			chr(9)+'fg = api.getForegroundObject()',
			chr(9)+'rp = api.getReviewPosition()',
			chr(9)+'caret = api.getCaretObject()',
			chr(9)+'desktop = api.getDesktopObject()',
			chr(9)+'mouse = api.getMouseObject()'
	]
	text = os.linesep.join(module_template)
	if createfile:
		userconfigfile = config.getScratchpadDir(True)+os.sep+moduletype+'s'+os.sep+modulename+'.py'
		fd1 = open(userconfigfile,'w')
		ui.message(_('Creating a new {moduletype}  {modulename}').format(moduletype=moduletype, modulename=modulename))
		fd1.write(text)
		fd1.close()
	else:
		return text



