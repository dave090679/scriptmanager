# Global plugin to make it easier to create/load application modules for NVDA.
#
# First get the required stuff :-)
import config
import wx
import globalPluginHandler
import appModuleHandler
import api
import ui
import addonHandler
import os
import sys
import gui
impPath = os.path.abspath(os.path.dirname(__file__))
sys.path.append(impPath)
import sm_backend, sm_frontend
addonHandler.initTranslation()
from scriptHandler import script

# Klasse von globalpluginhandler-globalplugin ableiten
class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	# Our plugin should be assigned to the keyboard combination NVDA+Shift+0. This assignment takes place in a dictionary named __gestures__.
	# and now follows the actual script. The name of the script doesn't quite match the name specified above (the "Script_" is missing, but that's how it should be :-).
	@script(
		description=_("opens the nvda script manager window"),
		category=_("script manager"),
		gesture="kb:nvda+shift+0"
	)
	def script_scriptmanager(self, gesture):
		focus=api.getFocusObject()
		self.appname=appModuleHandler.getAppNameFromProcessID(focus.processID,False)
		addon = False
		load = False
		if  not appModuleHandler.doesAppModuleExist(self.appname):
			sm_backend.createnewmodule('appModule', self.appname, True)
			load = True
		else:
			load = sm_backend.userappmoduleexists(self.appname)
			if not sm_backend.userappmoduleexists(self.appname):
				addon = sm_backend.appmoduleprovidedbyaddon(self.appname)
				if addon: 
					sm_backend.copyappmodulefromaddon(addon=addon, appname=self.appname)
					load = True
		if load: 
			wx.CallAfter(self.loadappmodule, self.appname)
		else:
			wx.CallAfter(self.loadappmodule,'')


	def loadappmodule(self, appname):
		userconfigfile = config.getScratchpadDir(True)+os.sep+'appModules'+os.sep+appname+'.py'
		if appname: 
			frame = sm_frontend.scriptmanager_mainwindow(None, -1, _('NVDA Script Manager'), userconfigfile)
		else:
			frame = sm_frontend.scriptmanager_mainwindow(None, -1, _('NVDA Script Manager'), '')
		frame.Show(True)
		frame.SetPosition(wx.Point(0,0))
		frame.SetSize(wx.DisplaySize())
		frame.text.SetFocus()

