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
		appname=appModuleHandler.getAppNameFromProcessID(focus.processID,False)
		load = False
		if  not appModuleHandler.doesAppModuleExist(appname):
			sm_backend.createnewappmodule(appname)
			load = True
		else:
			if not sm_backend.userappmoduleexists(appname):
				addon = sm_backend.appmoduleprovidedbyaddon(appname)
				if addon: 
					sm_backend.copyfromaddon(addon=addon, appname=appname)
					load = True
				else:
					if sm_backend.systemappmoduleexists(appname):
						sm_backend.copysystouser(appname)
						load = True
			else:
				load = True
		msg = _("""There's allready an Appmodule for {appname} included in to NVDA but it is only included as a compiled file and it can't be loaded into the script manager for editing.\n
If you continue and create a new appmodule, the above one(s) will stop working.\nDo you really want to create a new Appmodule?""").format(appname=appname)
		if not load:
			load = wx.CallAfter(gui.messageBox, message=msg, style=wx.YES|wx.NO|wx.ICON_WARNING)==wx.YES
		if load: wx.CallAfter(self.loadappmodule, appname)

	def loadappmodule(self, appName):
		userconfigfile = config.getUserDefaultConfigPath()+chr(92)+'appModules'+chr(92)+appName+'.py'
		frame = sm_frontend.MyMenu(None, -1, _('NVDA Script Manager'), userconfigfile)
		frame.Show(True)
