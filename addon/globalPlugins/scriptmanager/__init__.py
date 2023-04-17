# globales Plug-in zum einfacheren erstellen/laden von Anwendungsmodulen fuer nvda.
#
# erstmal das benoetigte Zeugs rankarren:-)
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
	# unser Plugin soll an die Tastenkombination nvda+0 zugewiesen werden. Diese Zuweisung erfolgt in einem Woerterbuch, das den Namen __gestures__ haben muss.
	__gestures={
		'kb:nvda+shift+0':'scriptmanager'
	}
	# und nun folgt das eigentliche Script. Der name des Scripts stimmt zwar nicht ganz mit dem oben angegebenen Namen ueberein (das "Script_" fehlt, das stimmt aber so:-).
	@script(
		description=_("opens the nvda script manager window")
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
					sm_backend.copyfromaddon(addon=addon, appname=self.appname)
					load = True
		if load: 
			wx.CallAfter(self.loadappmodule, self.appname)
		else:
			wx.CallAfter(self.loadappmodule,'')


	def loadappmodule(self, appName):
		userconfigfile = config.getScratchpadDir(True)+os.sep+'appModules'+os.sep+appName+'.py'
		if appName: 
			frame = sm_frontend.scriptmanager_mainwindow(None, -1, _('NVDA Script Manager'), userconfigfile)
		else:
			frame = sm_frontend.scriptmanager_mainwindow(None, -1, _('NVDA Script Manager'), '')
		frame.Show(True)
		frame.SetPosition(wx.Point(0,0))
		frame.SetSize(wx.DisplaySize())
		frame.text.SetFocus()

