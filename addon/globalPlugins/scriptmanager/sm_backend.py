import os
import config
import sys

def userappmoduleexists(appname):
	userconfigfile = config.getUserDefaultConfigPath()+chr(92)+'appModules'+chr(92)+appname+'.py'
	if os.access(userconfigfile,os.F_OK): return userconfigfile
	else: return None

def systemappmoduleexists(appname):
	sysconfigfile = config.getSystemConfigPath()+chr(92)+'appModules'+chr(92)+appname+'.py'
	if os.access(sysconfigfile,os.F_OK): return sysconfigfile
	else: return None

def appmoduleprovidedbyaddon(appname):
	l = list()
	for addon in addonHandler.getRunningAddons():
		if os.access(addon.path+chr(92)+'appmodules'+chr(92)+appname+'.py',os.F_OK): l.append(addon.manifest['name'])
	if len(l) > 0: return ', '.join(l)
	else: return None

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
	if self.l != '':
		if gui.messageBox(message=self.warning_msg,
		style=wx.YES|wx.NO|wx.ICON_WARNING)==wx.NO: 
			return
	userconfigfile = config.getUserDefaultConfigPath()+chr(92)+'appModules'+chr(92)+appname+'.py'
	fd1 = open(userconfigfile,'w')
	for line in appmodule_template:
		fd1.write(line+os.linesep)
	fd1.close()
	ui.message(_('Creating a new Appmodule for {appname}').format(appname=appname))
	self.warning_msg = ''

def copysystouser(appname):
	userconfigfile = config.getUserDefaultConfigPath()+chr(92)+'appModules'+chr(92)+appName+'.py'
	sysconfigfile = config.getSystemConfigPath()+chr(92)+'appModules'+chr(92)+appName+'.py'
	fd1 = open(sysconfigfile,'r')
	fd2 = open(userconfigfile,'a')
	for line in fd1:
		fd2.write(line)
	fd2.close()
	fd1.close()
