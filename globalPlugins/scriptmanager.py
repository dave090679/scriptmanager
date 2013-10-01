# globales Plug-in zum einfacheren erstellen/laden von Anwendungsmodulen fuer nvda.
#
# erstmal das benoetigte Zeugs rankarren:-)
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
#
# Klasse von globalpluginhandler-globalplugin ableiten
class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	# unser Plugin soll an die Tastenkombination nvda+0 zugewiesen werden. Diese Zuweisung erfolgt in einem Woerterbuch, das den Namen __gestures__ haben muss.
	__gestures={
		'kb:nvda+shift+0':'scriptmanager'
	}
	# und nun folgt das eigentliche Script. Der name des Scripts stimmt zwar nicht ganz mit dem oben angegebenen Namen ueberein (das "Script_" fehlt, das stimmt aber so:-).
	def script_scriptmanager(self, gesture):
		class insertfunctionsdialog(wx.Dialog):
			functionstring = ''
			def __init__(self, parent, id, title):
				super(insertfunctionsdialog, self).__init__(parent, id, title)
				mainsizer = wx.BoxSizer(orient=wx.VERTICAL)
				self.tree = wx.TreeCtrl(self, style=wx.TR_SINGLE | wx.TR_NO_BUTTONS)
				rootnode = self.tree.AddRoot(text='root')
				for moduleitem in sys.modules.keys():
					modulenode = self.tree.AppendItem(parent=rootnode, text=moduleitem)
					for functionentry in inspect.getmembers(sys.modules[moduleitem], inspect.isfunction):
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
			modify = False
			def __init__(self, parent, id, title):
				wx.Frame.__init__(self, parent, id, title, wx.DefaultPosition, wx.Size(380, 250))
				menubar = wx.MenuBar()
				file = wx.Menu()
				edit = wx.Menu()
				tools = wx.Menu()
				run = wx.Menu()
				view = wx.Menu()
				help = wx.Menu()
				file.Append(101, _('&Open\tctrl+o'), _('Open an appmodule'))
				file.Append(102, _('&Save\tctrl+s'), _('Save the appmodule'))
				file.AppendSeparator()
				quit = wx.MenuItem(file, 105, _('&Quit\tCtrl+Q'), _('Quit the Application'))
				file.AppendItem(quit)
				edit.Append(201, _('cut\tctrl+x'))
				edit.Append(202, _('copy\tctrl+c'))
				edit.Append(203, _('paste\tctrl+v'))
				edit.Append(204, _('select all\tctrl+a'))
				edit.Append(205, _('delete\tctrl+y'))
				edit.Append(206, _('insert function\tctrl+i'))
				edit.Append(207, _('&find...\tctrl+f'))
				#edit.Append(208, _('find next\tf3'))
				#edit.Append(206, _('find previous\tshift+f3'))
				run.Append(501,_('&run'))
				run.Append(502,_('&compile...'))
				menubar.Append(file, _('&File'))
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
				self.text = wx.TextCtrl(self, 1000, '', size=(-1, -1), style=wx.TE_MULTILINE | wx.TE_PROCESS_ENTER)
				focus=api.getFocusObject()
				appName=appModuleHandler.getAppNameFromProcessID(focus.processID,False)
				userconfigfile = config.getUserDefaultConfigPath()+chr(92)+'appModules'+chr(92)+appName+'.py'
				sysconfigfile = config.getSystemConfigPath()+chr(92)+'appModules'+chr(92)+appName+'.py'
				appmodule_template = [
					'#appModules/'+appName.replace('.exe','')+'.py',
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
				if not os.access(userconfigfile,os.F_OK):
					if os.access(sysconfigfile, os.F_OK) :
						fd1 = open(sysconfigfile,'r')
						fd2 = open(userconfigfile,'a')
						for line in fd1:
							fd2.write(line)
						fd2.close()
						fd1.close()
					else:
						fd1 = open(userconfigfile,'w')
						for line in appmodule_template:
							fd1.write(line+os.linesep)
						fd1.close()
						ui.message(_('new appmodule created.'))
				tmpfile = open(userconfigfile,'r')
				tmptext = tmpfile.read()
				self.text.WriteText(tmptext)
				self.modify = False
				self.last_name_saved = userconfigfile
			def OnInsertFunction(self, event):
				ifd = insertfunctionsdialog(self, id=wx.ID_ANY, title=_('insert function'))
				if ifd.ShowModal() == wx.ID_OK:
					self.text.WriteText(ifd.functionstring)
					ifd.Destroy()

			def OnOpenFile(self, event):
				file_name = os.path.basename(self.last_name_saved)
				if self.modify:
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
						file = open(self.last_name_saved, 'w')
						text = self.text.GetValue()
						file.write(text)
						file.close()
						self.statusbar.SetStatusText(os.path.basename(self.last_name_saved) + ' '+_('saved'), 0)
						self.modify = False
						self.statusbar.SetStatusText('', 1)
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
						file = open(path, 'w')
						text = self.text.GetValue()
						file.write(text)
						file.close()
						self.last_name_saved = os.path.basename(path)
						self.statusbar.SetStatusText(self.last_name_saved + ' '+_('saved'), 0)
						self.modify = False
						self.statusbar.SetStatusText('', 1)
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
				self.modify = True
				self.statusbar.SetStatusText(_(' modified'), 1)
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
				if self.modify:
					dlg = wx.MessageDialog(self, _('Save before Exit?'), '', wx.YES_NO | wx.YES_DEFAULT | wx.CANCEL | wx.ICON_QUESTION)
					val = dlg.ShowModal()
					if val == wx.ID_YES:
						self.OnSaveFile(event)
						if not self.modify:
							self.Close()
					elif val == wx.ID_CANCEL:
						dlg.Destroy()
					else:
						self.Close()
				else:
					self.Close()
		frame = MyMenu(None, -1, _('NVDA Script Manager'))
		frame.Show(True)
	script_scriptmanager.__doc__=_("tries to load the appmodule for the currently running application or creates a new file, if it doesn't exist yet.")