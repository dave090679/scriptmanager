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
#
# Klasse von globalpluginhandler-globalplugin ableiten
class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	# unser Plugin soll an die Tastenkombination nvda+0 zugewiesen werden. Diese Zuweisung erfolgt in einem Woerterbuch, das den Namen __gestures__ haben muss.
	__gestures={
		'kb:nvda+shift+0':'scriptmanager'
	}
	# und nun folgt das eigentliche Script. Der name des Scripts stimmt zwar nicht ganz mit dem oben angegebenen Namen ueberein (das "Script_" fehlt, das stimmt aber so:-).
	def script_scriptmanager(self, gesture):
		focus=api.getFocusObject()
		self.appname=appModuleHandler.getAppNameFromProcessID(focus.processID,False)
		addon = False
		load = False
		if  not appModuleHandler.doesAppModuleExist(self.appname):
			sm_backend.createnewmodule('appModule', self.appname, True)
			load = True
		else:
			if not sm_backend.userappmoduleexists(self.appname):
				addon = sm_backend.appmoduleprovidedbyaddon(self.appname)
				if addon: 
					sm_backend.copyfromaddon(addon=addon, appname=self.appname)
					load = True
		if not load:
			msg = _("""There's allready an Appmodule for {appname} included in to NVDA but it is only included as a compiled file and it can't be loaded into the script manager for editing.""").format(appname=self.appname)
			msgbox = wx.CallAfter(gui.messageBox, message=msg)
		if load: wx.CallAfter(self.loadappmodule, self.appname)

	def loadappmodule(self, appName):
		userconfigfile = config.getScratchpadDir(True)+os.sep+'appModules'+os.sep+appName+'.py'
		frame = sm_frontend.scriptmanager_mainwindow(None, -1, _('NVDA Script Manager'), userconfigfile)
		frame.Show(True)
