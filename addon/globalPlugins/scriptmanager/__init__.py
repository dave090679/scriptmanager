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
		if  not appModuleHandler.doesAppModuleExist(sm_backend.appName):
			sm_backend.createnewappmodule(sm_backend.appName)
		else:
			if not sm_backend.userappmoduleexists(sm_backend.appName):
				addon = sm_backend.appmoduleprovidedbyaddon(sm_backend.appName)
				if addon: 
					sm_backend.copyfromaddon(addon=addon, appname=sm_backend.appName)
				else:
					if sm_backend.systemappmoduleexists(sm_backend.appName):
						sm_backend.copysystouser(sm_backend.appName)
					else:
						msg = _("""There's allready an Appmodule for {appname} included in to NVDA but it is only included as a compiled file and it can't be loaded into the script manager for editing.\n
If you continue and create a new appmodule, the above one(s) will stop working.\nDo you really want to create a new Appmodule?""").format(appname=sm_backend.appName)
						if wx.CallAfter(gui.messageBox, message=msg, style=wx.YES|wx.NO|wx.ICON_WARNING)==wx.NO: return
		wx.CallAfter(self.loadappmodule, appModuleHandler.getAppNameFromProcessID(api.getFocusObject().processID,False))
	# Unsere Funktion loadappmodule muss ein Argument entgegennehmen, das unser globales Plug-in darstellt, weil sie Bestandteil des globalen Plug-ins ist.
	def loadappmodule(self, appName):
		userconfigfile = config.getUserDefaultConfigPath()+chr(92)+'appModules'+chr(92)+sm_backend.appName+'.py'
		frame = sm_frontend.MyMenu(None, -1, _('NVDA Script Manager'), userconfigfile)
		frame.Show(True)
