# globales Plug-in zum einfacheren erstellen/laden von Anwendungsmodulen fuer nvda.
#
# erstmal das benoetigte Zeugs rankarren:-)
import gui
import globalPluginHandler
import appModuleHandler
import os
import config
import api
import ui
import subprocess
import wx
import sys
import inspect
import addonHandler
addonHandler.initTranslation()
#
# Klasse von globalpluginhandler-globalplugin ableiten
class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	# unser Plugin soll an die Tastenkombination nvda+0 zugewiesen werden. Diese Zuweisung erfolgt in einem Woerterbuch, das den Namen __gestures__ haben muss.
	__gestures={
		'kb:nvda+shift+0':'scriptmanager'
	}
	# und nun folgt das eigentliche Script. Der name des Scripts stimmt zwar nicht ganz mit dem oben angegebenen Namen ueberein (das "Script_" fehlt, das stimmt aber so:-).
	def userappmoduleexists(self, appname):
		userconfigfile = config.getUserDefaultConfigPath()+chr(92)+'appModules'+chr(92)+appname+'.py'
		if os.access(userconfigfile,os.F_OK): return userconfigfile
		else: return None

	def systemappmoduleexists(self, appname):
		sysconfigfile = config.getSystemConfigPath()+chr(92)+'appModules'+chr(92)+appname+'.py'
		if os.access(sysconfigfile,os.F_OK): return sysconfigfile
		else: return None

	def appmoduleprovidedbyaddon(self, appname):
		l = list()
		for addon in addonHandler.getRunningAddons():
			if os.access(addon.path+chr(92)+'appmodules'+chr(92)+appname+'.py',os.F_OK): l.append(addon.manifest['name'])
		if len(l) > 0: return ', '.join(l)
		else: return None

	def createnewappmodule(self, appname):
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

	def copysystouser(self, appname):
		userconfigfile = config.getUserDefaultConfigPath()+chr(92)+'appModules'+chr(92)+appName+'.py'
		sysconfigfile = config.getSystemConfigPath()+chr(92)+'appModules'+chr(92)+appName+'.py'
		fd1 = open(sysconfigfile,'r')
		fd2 = open(userconfigfile,'a')
		for line in fd1:
			fd2.write(line)
		fd2.close()
		fd1.close()

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
		if not self.userappmoduleexists(appName):
			if  appModuleHandler.doesAppModuleExist(appName):
				self.warning_msg += _("an Appmodule for {appname} was found at the following location(s):\n").format(appname=appName)
				self.l = ''
				if self.systemappmoduleexists(appName):
					self.warning_msg += _("* in the sysconfig folder")
					self.l += 's'
				addons = self.appmoduleprovidedbyaddon(appName)
				if addons: 
					self.l += 'a'
					self.warning_msg += _("* within the following addons(s): {addons}\n").format(addons=addons)
				if self.l == '':
					self.l += 'c'
					self.warning_msg += _("There's allready an Appmodule for {appname} included in to NVDA but it is only included as a compiled file and it can't be loaded into notepad for editing.\n").format(appname=appName)
				self.warning_msg += _("If you continue and create a new appmodule, the above one(s) will stop working.\nDo you really want to create a new Appmodule?")
			self.createnewappmodule(appName)
		if self.warning_msg == '':
			frame = MyMenu(None, -1, _('NVDA Script Manager'), userconfigfile)
			frame.Show(True)
	script_scriptmanager.__doc__=_("tries to load the appmodule for the currently running application or creates a new file, if it doesn't exist yet.")

class insertfunctionsdialog(wx.Dialog):
	functionstring = ''
	def __init__(self, parent, id, title):
		super(insertfunctionsdialog, self).__init__(parent, id, title)
		mainsizer = wx.BoxSizer(orient=wx.VERTICAL)
		self.tree = wx.TreeCtrl(self, style=wx.TR_SINGLE | wx.TR_NO_BUTTONS)
		rootnode = self.tree.AddRoot(text='root')
		for moduleitem in sys.modules.keys():
			functionlist = inspect.getmembers(sys.modules[moduleitem], inspect.isfunction)
			if len(functionlist) > 0: 
				modulenode = self.tree.AppendItem(parent=rootnode, text=moduleitem)
				for functionentry in functionlist:
					functionnode = self.tree.AppendItem(parent=modulenode, text=functionentry[0])
		mainsizer.Add(self.tree)
		buttons = self.CreateButtonSizer(wx.OK|wx.CANCEL)
		mainsizer.Add(buttons)
		self.SetSizer(mainsizer)
		self.Bind(wx.EVT_BUTTON,self.onOk,id=wx.ID_OK)
		self.Bind(wx.EVT_BUTTON,self.onCancel,id=wx.ID_CANCEL)
	def onOk(self, event):
		tmpfunction = self.tree.GetItemText(self.tree.GetItemParent(self.tree.GetSelection()))+'.'
		tmpfunction = tmpfunction+self.tree.GetItemText(self.tree.GetSelection())+'('
		args = inspect.getargspec(sys.modules[self.tree.GetItemText(self.tree.GetItemParent(self.tree.GetSelection()))].__dict__[self.tree.GetItemText(self.tree.GetSelection())])[0]
		for x in range(len(args)):
			tmpfunction = tmpfunction +args[x]
			if x < len(args)-1:
				tmpfunction = tmpfunction+', '
		tmpfunction = tmpfunction+')'
		self.functionstring = tmpfunction
		self.EndModal(wx.ID_OK)
	def onCancel(self, event):
		self.functionstring = ''
		self.EndModal(wx.ID_CANCEL)

class MyMenu(wx.Frame):
	def __init__(self, parent, id, title, scriptfile):
		wx.Frame.__init__(self, parent, id, title, wx.DefaultPosition, wx.Size(380, 250))
		menubar = wx.MenuBar()
		self.StatusBar()
		filemenu = wx.Menu()
		edit = wx.Menu()
		tools = wx.Menu()
		run = wx.Menu()
		view = wx.Menu()
		help = wx.Menu()
		filemenu.Append(101, _('&Open')+'\tctrl+o', _('Open an appmodule'))
		filemenu.Append(102, _('&Save')+'\tctrl+s', _('Save the appmodule'))
		filemenu.AppendSeparator()
		quit = wx.MenuItem(filemenu, 105, _('&Quit')+'\tAlt+F4', _('Quit the Application'))
		filemenu.AppendItem(quit)
		edit.Append(201, _('cut')+'\tctrl+x')
		edit.Append(202, _('copy')+'\tctrl+c')
		edit.Append(203, _('paste')+'\tctrl+v')
		edit.Append(204, _('select all')+'\tctrl+a')
		edit.Append(205, _('delete')+'\tctrl+y')
		edit.Append(206, _('insert function...')+'\tctrl+i')
		edit.Append(207, _('&find...')+'\tctrl+f')
		#edit.Append(208, _('find next')+'\tf3')
		#edit.Append(206, _('find previous')+'\tshift+f3')
		run.Append(501,_('&run'))
		run.Append(502,_('&compile...'))
		menubar.Append(filemenu, _('&File'))
		menubar.Append(edit, _('&Edit'))
		menubar.Append(view, _('&view'))
		menubar.Append(help, _('&Help'))
		self.SetMenuBar(menubar)
		self.Centre()
		self.Bind(wx.EVT_MENU, self.OnQuit, id=105)
		self.Bind(wx.EVT_MENU, self.OnSaveFile, id=102)
		self.Bind(wx.EVT_MENU, self.OnCut, id=201)
		self.Bind(wx.EVT_MENU, self.OnCopy, id=202)
		self.Bind(wx.EVT_MENU, self.OnPaste, id=203)
		self.Bind(wx.EVT_MENU, self.OnDelete, id=205)
		self.Bind(wx.EVT_MENU, self.OnSelectAll, id=204)
		self.Bind(wx.EVT_MENU, self.OnInsertFunction, id=206)
		self.Bind(wx.EVT_KEY_DOWN,self.OnKeyDown)
		self.text = wx.TextCtrl(parent=self, id=1000, value='', size=(-1, -1), style=wx.TE_MULTILINE | wx.TE_PROCESS_ENTER)
		self.text.Bind(wx.EVT_TEXT,self.OnTextChanged)
		tmpfile = open(scriptfile,'r')
		tmptext = tmpfile.read()
		self.text.WriteText(tmptext)
		tmpfile.close()
		self.last_name_saved = scriptfile
		self.modify = False
		self.text.SetSelection(0,0)

	def OnInsertFunction(self, event):
		ifd = insertfunctionsdialog(self, id=wx.ID_ANY, title=_('insert function'))
		if ifd.ShowModal() == wx.ID_OK:
			self.text.WriteText(ifd.functionstring)
			ifd.Destroy()
	def OnOpenFile(self, event):
		file_name = os.path.basename(self.last_name_saved)
		if self.text.IsMmodified:
			dlg = wx.MessageDialog(self, _('Save changes?'), '', wx.YES_NO | wx.YES_DEFAULT | wx.CANCEL | wx.ICON_QUESTION)
			val = dlg.ShowModal()
			if val == wx.ID_YES:
				self.OnSaveFile(event)
				self.DoOpenFile()
			elif val == wx.ID_CANCEL:
				dlg.Destroy()
			else:
				self.DoOpenFile()
		else:
			self.DoOpenFile()
	def DoOpenFile(self):
		wcd = _('All files (*.*)')+'|*.*|'+_('appmodule source files (*.py)')+'|*.py|'
		dir = os.getcwd()
		open_dlg = wx.FileDialog(self, message=_('Choose a file'), defaultDir=dir, defaultFile='',
		wildcard=wcd, style=wx.OPEN|wx.CHANGE_DIR)
		if open_dlg.ShowModal() == wx.ID_OK:
			path = open_dlg.GetPath()
			try:
				file = open(path, 'r')
				text = file.read()
				file.close()
				if self.text.GetLastPosition():
					self.text.Clear()
					self.text.WriteText(text)
					self.last_name_saved = path
					self.statusbar.SetStatusText('', 1)
					self.modify = False
					self.text.SetSelection(0,0)
			except IOError, error:
				dlg = wx.MessageDialog(self, _('Error opening file')+'\n' + str(error))
				dlg.ShowModal()
			except UnicodeDecodeError, error:
				dlg = wx.MessageDialog(self, _('Error opening file')+'\n' + str(error))
				dlg.ShowModal()
		open_dlg.Destroy()
	def OnSaveFile(self, event):
		if self.last_name_saved:
			try:
				file2 = open(self.last_name_saved, 'w')
				text = self.text.GetValue()
				file2.write(text)
				file2.close()
				self.statusbar.SetStatusText(os.path.basename(self.last_name_saved) + ' '+_('saved'), 0)
				self.statusbar.SetStatusText('', 1)
				self.modify = False
			except IOError, error:
				dlg = wx.MessageDialog(self, _('Error saving file')+'\n' + str(error))
				dlg.ShowModal()
		else:
			self.OnSaveAsFile(event)
	def OnSaveAsFile(self, event):
		wcd=_('All files(*.*)')+'|*.*|'+_('appmodule source files (*.py)')+'|*.py|'
		dir = os.getcwd()
		save_dlg = wx.FileDialog(self, message=_('Save file as...'), defaultDir=dir, defaultFile='',
		wildcard=wcd, style=wx.SAVE | wx.OVERWRITE_PROMPT)
		if save_dlg.ShowModal() == wx.ID_OK:
			path = save_dlg.GetPath()
			try:
				file2 = open(path, 'w')
				text = self.text.GetValue()
				file2.write(text)
				file2.close()
				self.last_name_saved = os.path.basename(path)
				self.statusbar.SetStatusText(self.last_name_saved + ' '+_('saved'), 0)
				self.statusbar.SetStatusText('', 1)
				self.Modify = False
			except IOError, error:
				dlg = wx.MessageDialog(self, _('Error saving file')+'\n' + str(error))
				dlg.ShowModal()
		save_dlg.Destroy()
	def OnCut(self, event):
		self.text.Cut()
	def OnCopy(self, event):
		self.text.Copy()
	def OnPaste(self, event):
		self.text.Paste()
	def OnDelete(self, event):
		frm, to = self.text.GetSelection()
		self.text.Remove(frm, to)
	def OnSelectAll(self, event):
		self.text.SelectAll()
	def OnTextChanged(self, event):
		self.statusbar.SetStatusText(_(' modified'), 1)
		self.modify = True
		event.Skip()
	def OnKeyDown(self, event):
		keycode = event.GetKeyCode()
		if keycode == wx.WXK_INSERT:
			if not self.replace:
				self.statusbar.SetStatusText(_('INS'), 2)
				self.replace = True
			else:
				self.statusbar.SetStatusText('', 2)
				self.replace = False
		event.Skip()
	def StatusBar(self):
		self.statusbar = self.CreateStatusBar()
		self.statusbar.SetFieldsCount(3)
		self.statusbar.SetStatusWidths([-5, -2, -1])
	def OnAbout(self, event):
		dlg = wx.MessageDialog(self, _('\tNVDA Script-manager\t\n (c) 2011 by David Parduhn\n portions copyright (C) jan bodnar 2005-2006'),_('About nvda Script Manager'), wx.OK | wx.ICON_INFORMATION)
		dlg.ShowModal()
		dlg.Destroy()
	def OnQuit(self, event):
		if self.modify==True:
			dlg = wx.MessageDialog(self, _('Save before Exit?'), '', wx.YES_NO | wx.YES_DEFAULT | wx.CANCEL | wx.ICON_QUESTION)
			val = dlg.ShowModal()
			if val == wx.ID_YES:
				self.OnSaveFile(event)
				self.Close()
			elif val == wx.ID_CANCEL:
				dlg.Destroy()
			else:
				self.Close()
		else:
			self.Close()
