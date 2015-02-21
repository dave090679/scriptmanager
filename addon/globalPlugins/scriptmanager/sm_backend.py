import addonHandler
import os
import config
import sys
import api
import appModuleHandler
import ui
import config
focus=api.getFocusObject()
appName=appModuleHandler.getAppNameFromProcessID(focus.processID,False)
def userappmoduleexists(appname):
	userconfigfile = config.getUserDefaultConfigPath()+chr(92)+'appModules'+chr(92)+appname+'.py'
	if os.access(userconfigfile,os.F_OK): return userconfigfile
	else: return None

def systemappmoduleexists(appname):
	sysconfigfile = config.getSystemConfigPath()+chr(92)+'appModules'+chr(92)+appname+'.py'
	if os.access(sysconfigfile,os.F_OK): return sysconfigfile
	else: return None

def appmoduleprovidedbyaddon(appname):
	ret = None
	for addon in addonHandler.getRunningAddons():
		if os.access(addon.path+chr(92)+'appmodules'+chr(92)+appname+'.py',os.F_OK): ret = addon
	return ret

def copyappmodulefromaddon(appname, addon):
	addonname = addon.manifest['name']
	addonfullpath = addon.path+chr(92)+'appmodules'+chr(92)+appname+'.py'
	userconfigfile = config.getUserDefaultConfigPath()+chr(92)+'appModules'+chr(92)+appName+'.py'
	fd1 = open(addonfullpath,'r')
	fd2 = open(userconfigfile,'a')
	ui.message(_("copying appmodule for {appname} from addon {addonname} to user's config folder...").format(addonname=addonname, appname=appname))
	for line in fd1:
		fd2.write(line)
	fd2.close()
	fd1.close()

def createnewappmodule(appname):
	appmodule_template = [
		'#appModules/'+appname+'.py',
		'#A part of NonVisual Desktop Access (NVDA)',
		'#Copyright (C) 2006-2012 NVDA Contributors',
		'#This file is covered by the GNU General Public License.',
		'#See the file COPYING for more details.',
		'import appModuleHandler',
		'import api',
		'class AppModule(appModuleHandler.AppModule):',
		chr(9)+'# some snapshot variables similar to these in the python console',
		chr(9)+'nav = api.getNavigatorObject()',
		chr(9)+'focus = api.getFocusObject()',
		chr(9)+'fg = api.getForegroundObject()',
		chr(9)+'rp = api.getReviewPosition()',
		chr(9)+'caret = api.getCaretObject()',
		chr(9)+'desktop = api.getDesktopObject()',
		chr(9)+'mouse = api.getMouseObject()'
	]
	userconfigfile = config.getUserDefaultConfigPath()+chr(92)+'appModules'+chr(92)+appname+'.py'
	fd1 = open(userconfigfile,'w')
	ui.message(_('Creating a new Appmodule for {appname}').format(appname=appname))
	for line in appmodule_template:
		fd1.write(line+os.linesep)
	fd1.close()



def copysystouser(appname):
	userconfigfile = config.getUserDefaultConfigPath()+chr(92)+'appModules'+chr(92)+appName+'.py'
	sysconfigfile = config.getSystemConfigPath()+chr(92)+'appModules'+chr(92)+appName+'.py'
	fd1 = open(sysconfigfile,'r')
	fd2 = open(userconfigfile,'a')
	ui.message(_('copying app module for {appname} from system config folder to user folder...').format(appname=appname))
	for line in fd1:
		fd2.write(line)
	fd2.close()
	fd1.close()
