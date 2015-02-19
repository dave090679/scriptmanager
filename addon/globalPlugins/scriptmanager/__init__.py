# globales Plug-in zum einfacheren erstellen/laden von Anwendungsmodulen fuer nvda.
#
# erstmal das benoetigte Zeugs rankarren:-)
import api
import wx
import globalPluginHandler
import appModuleHandler
import api
import ui
import subprocess
import addonHandler
import os
import sys
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
		# die Funktion wx.CallAfter wird benutzt, um Code auszufuehren, *nachdem* alle Ereignisbehandlungsroutinen abgearbeitet sind. Dies gewaehrleistet, dass NVDA waehrend der Anzeige des meldungsfensters erwartungsgemaess reagiert. 
		# Die Funktion CallAfter erwartet als ersten Parameter den Namen der Funktion, gefolgt von allen Argumenten (wahlweise benannt oder unbenannt).
		# Wenn keine Argumente angegeben werden, wird die uebergebene Funktion (je nach Kontext) entweder ohne Argumente aufgerufen oder es wird ein Argument uebergeben, das die uebergeordnete Instanz darstellt (in unserem Fall das globale Plug-In)
		# der Kontext self ist hier notwendig, weil unsere Funktion loadappmodule (genau wie das Script auch) Bestandteil des globalplugin-Objekts ist.
		wx.CallAfter(self.loadappmodule, appModuleHandler.getAppNameFromProcessID(api.getFocusObject().processID,False))
	# Unsere Funktion loadappmodule muss ein Argument entgegennehmen, das unser globales Plug-in darstellt, weil sie Bestandteil des globalen Plug-ins ist.
	def loadappmodule(self, appName):
		focus=api.getFocusObject()
		appName=appModuleHandler.getAppNameFromProcessID(focus.processID,False)
		userconfigfile = config.getUserDefaultConfigPath()+chr(92)+'appModules'+chr(92)+appName+'.py'
		sysconfigfile = config.getSystemConfigPath()+chr(92)+'appModules'+chr(92)+appName+'.py'
		self.warning_msg = ''
		self.l = ''
		if not sm_backend.userappmoduleexists(appName):
			if  appModuleHandler.doesAppModuleExist(appName):
				self.warning_msg += _("an Appmodule for {appname} was found at the following location(s):\n").format(appname=appName)
				self.l = ''
				if sm_backend.systemappmoduleexists(appName):
					self.warning_msg += _("* in the sysconfig folder")
					self.l += 's'
				addons = sm_backend.appmoduleprovidedbyaddon(appName)
				if addons: 
					self.l += 'a'
					self.warning_msg += _("* within the following addons(s): {addons}\n").format(addons=addons)
				if self.l == '':
					self.l += 'c'
					self.warning_msg += _("There's allready an Appmodule for {appname} included in to NVDA but it is only included as a compiled file and it can't be loaded into notepad for editing.\n").format(appname=appName)
				self.warning_msg += _("If you continue and create a new appmodule, the above one(s) will stop working.\nDo you really want to create a new Appmodule?")
			sm_backend.createnewappmodule(appName)
		if self.warning_msg == '':
			frame = sm_frontend.MyMenu(None, -1, _('NVDA Script Manager'), userconfigfile)
			frame.Show(True)
