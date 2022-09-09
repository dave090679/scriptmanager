import datetime
import config
import sys
import os
impPath = os.path.abspath(os.path.dirname(__file__))
sys.path.append(impPath)
import sm_backend
import ui
import gui
import wx
import inspect
import addonHandler
import re
addonHandler.initTranslation()

class insertfunctionsdialog(wx.Dialog):
	functionstring = ''
	def __init__(self, parent, id, title):
		super(insertfunctionsdialog, self).__init__(parent, id, title)
		mainsizer = wx.BoxSizer(orient=wx.VERTICAL)
		self.tree = wx.TreeCtrl(self, style=wx.TR_SINGLE | wx.TR_NO_BUTTONS)
		rootnode = self.tree.AddRoot(text='root')
		modulelist = sys.modules.keys()
		for moduleitem in sorted(modulelist):
			functionlist = inspect.getmembers(sys.modules[moduleitem], inspect.isfunction)
			if len(functionlist) > 0: 
				modulenode = self.tree.AppendItem(parent=rootnode, text=moduleitem)
				for functionentry in sorted(functionlist):
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
		args = inspect.getfullargspec(sys.modules[self.tree.GetItemText(self.tree.GetItemParent(self.tree.GetSelection()))].__dict__[self.tree.GetItemText(self.tree.GetSelection())])[0]
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

class scriptmanager_mainwindow(wx.Frame):
	def __init__(self, parent, id, title, scriptfile):
		wx.Frame.__init__(self, parent, id, title)
		menubar = wx.MenuBar()
		self.StatusBar()
		filemenu = wx.Menu()
		filenew = wx.Menu()
		edit = wx.Menu()
		#scripts = wx.Menu()
		#view = wx.Menu()
		help = wx.Menu()
		filemenu.AppendSubMenu(filenew, _('new'))
		filemenu.Append(101, _('&Open')+'\tctrl+o', _('Open an appmodule'))
		filemenu.Append(102, _('&Save')+'\tctrl+s', _('Save the appmodule'))
		filemenu.Append(103, _('Save &as...')+'\tctrl+shift+s', _('Save the module as a new file'))
		filemenu.AppendSeparator()
		quit = wx.MenuItem(filemenu, 105, _('&Quit')+'\tAlt+F4', _('Quit the Application'))
		filemenu.AppendItem(quit)
		filenew.Append(110, _('empty file')+'\tctrl+n')
		filenew.Append(111, _('appmodule'))
		filenew.Append(112, _('global plugin'))
		filenew.Append(113, _('braille display driver'))
		filenew.Append(114, _('speech synthesizer driver'))
		filenew.Append(115, _('visual enhancement provider'))
		edit.Append(200, _('undo')+'\tctrl+z')
		edit.Append(212, _('redo')+'\tctrl+y')
		edit.Append(201, _('cut')+'\tctrl+x')
		edit.Append(202, _('copy')+'\tctrl+c')
		edit.Append(203, _('paste')+'\tctrl+v')
		edit.Append(204, _('select all')+'\tctrl+a')
		edit.Append(205, _('delete')+'\tctrl+y')
		edit.Append(206, _('insert function...')+'\tctrl+i')
		edit.Append(207, _('&find...')+'	ctrl+f')
		findnextitem = wx.MenuItem(edit, 208, _('find next')+'\tf3')
		findnextitem.Enable(True)
		edit.AppendItem(findnextitem)
		findprevitem = wx.MenuItem(edit, 209, _('find previous')+'\tshift+f3')
		findprevitem.Enable(True)
		edit.AppendItem(findprevitem)
		edit.Append(210, _('replace\tctrl+h'))
		edit.Append(211, _('go to Line...\tctrl+g'))
		help.Append(901, _('about...'))
		menubar.Append(filemenu, _('&File'))
		menubar.Append(edit, _('&Edit'))
		menubar.Append(help, _('&Help'))
		self.SetMenuBar(menubar)
		self.Centre()
		self.Bind(wx.EVT_MENU, self.OnQuit, id=105)
		self.Bind(wx.EVT_MENU, self.OnNewEmptyFile, id=110)
		self.Bind(wx.EVT_MENU, self.OnNewAppModule, id=111)
		self.Bind(wx.EVT_MENU, self.OnNewGlobalPlugin, id=112)
		self.Bind(wx.EVT_MENU, self.OnNewBrailleDisplayDriver, id=113)
		self.Bind(wx.EVT_MENU, self.OnNewSynthDriver, id=114)
		self.Bind(wx.EVT_MENU, self.OnNewVisionEnhancementProvider, id=115)
		self.Bind(wx.EVT_MENU, self.OnOpenFile, id=101)
		self.Bind(wx.EVT_MENU, self.OnSaveFile, id=102)
		self.Bind(wx.EVT_MENU, self.OnSaveAsFile, id=103)
		self.Bind(wx.EVT_MENU, self.OnUndo, id=200)
		self.Bind(wx.EVT_MENU, self.OnRedo, id=212)
		self.Bind(wx.EVT_MENU, self.OnCut, id=201)
		self.Bind(wx.EVT_MENU, self.OnCopy, id=202)
		self.Bind(wx.EVT_MENU, self.OnPaste, id=203)
		self.Bind(wx.EVT_MENU, self.OnDelete, id=204)
		self.Bind(wx.EVT_MENU, self.OnSelectAll, id=205)
		self.Bind(wx.EVT_MENU, self.OnInsertFunction, id=206)
		self.Bind(wx.EVT_MENU, self.OnFinditem, id=207)
		self.Bind(wx.EVT_MENU, self.OnFindnextitem, id=208)
		self.Bind(wx.EVT_MENU, self.OnFindpreviousitem, id=209)
		self.Bind(wx.EVT_MENU, self.OnReplaceitem, id=210)
		self.Bind(wx.EVT_MENU, self.OnGotoLineItem, id=211)
		self.Bind(wx.EVT_MENU, self.OnAbout, id=901)
		self.Bind(wx.EVT_FIND, self.on_find)
		# self.Bind(wx.EVT_FIND_NEXT, self.findnext)
		self.Bind(wx.EVT_FIND_REPLACE, self.on_replace)
		self.Bind(wx.EVT_FIND_REPLACE_ALL, self.on_find_replace_all)
		self.Bind(wx.EVT_KEY_DOWN,self.OnKeyDown)
		self.text = wx.TextCtrl(parent=self, id=1000, value='', size=(-1, -1), style=wx.TE_MULTILINE | wx.TE_PROCESS_ENTER | wx.TE_DONTWRAP)
		self.text.Bind(wx.EVT_TEXT,self.OnTextChanged)
		if scriptfile != '':
			self.text.LoadFile(scriptfile)
			self.last_name_saved = scriptfile
		self.modify = False
		self.text.SelectNone()
		self.text.SetFocus()
	def OnNewEmptyFile(self, event):
		file_name = os.path.basename(self.last_name_saved)
		if self.text.IsModified and self.text.GetValue():
			dlg = wx.MessageDialog(self, _('Save changes?'), '', wx.YES_NO | wx.YES_DEFAULT | wx.CANCEL | wx.ICON_QUESTION)
			val = dlg.ShowModal()
			if val == wx.ID_YES:
				self.OnSaveFile(event)
				self.DoNewEmptyFile()
			elif val == wx.ID_CANCEL:
				dlg.Destroy()
			else:
				self.DoNewEmptyFile()
		else:
			self.DoNewEmptyFile()

	def OnNewAppModule(self, event):
		self.defaultdir = config.getScratchpadDir(True)+os.sep+'appModules'
		self.defaultfile = _('untitled')+'.py'
		if self.text.IsModified and self.text.GetValue():
			dlg = wx.MessageDialog(self, _('Save changes?'), '', wx.YES_NO | wx.YES_DEFAULT | wx.CANCEL | wx.ICON_QUESTION)
			val = dlg.ShowModal()
			if val == wx.ID_YES:
				self.OnSaveFile(event)
				self.DoNewEmptyFile()
				self.text.SetValue(sm_backend.createnewmodule('appModule', _('untitled'), False))
			elif val == wx.ID_CANCEL:
				dlg.Destroy()
			else:
				self.DoNewEmptyFile()
				self.text.SetValue(sm_backend.createnewmodule('appModule', _('untitled'), False))
		else:
			self.DoNewEmptyFile()
			self.text.SetValue(sm_backend.createnewmodule('appModule', _('untitled'), False))

	def OnNewGlobalPlugin(self, event):
		self.defaultdir = config.getScratchpadDir(True)+os.sep+'globalPlugins'
		if self.text.IsModified and self.text.GetValue():
			dlg = wx.MessageDialog(self, _('Save changes?'), '', wx.YES_NO | wx.YES_DEFAULT | wx.CANCEL | wx.ICON_QUESTION)
			val = dlg.ShowModal()
			if val == wx.ID_YES:
				self.OnSaveFile(event)
				self.DoNewEmptyFile()
				self.text.SetValue(sm_backend.createnewmodule('globalPlugin', _('untitled'), False))
			elif val == wx.ID_CANCEL:
				dlg.Destroy()
			else:
				self.DoNewEmptyFile()
				self.text.SetValue(sm_backend.createnewmodule('globalPlugin', _('untitled'), False))
		else:
			self.DoNewEmptyFile()
			self.text.SetValue(sm_backend.createnewmodule('globalPlugin', _('untitled'), False))

	def OnNewBrailleDisplayDriver(self, event):
		self.defaultdir = config.getScratchpadDir(True)+os.sep+'brailleDisplayDrivers'
		if self.text.IsModified and self.text.GetValue():
			dlg = wx.MessageDialog(self, _('Save changes?'), '', wx.YES_NO | wx.YES_DEFAULT | wx.CANCEL | wx.ICON_QUESTION)
			val = dlg.ShowModal()
			if val == wx.ID_YES:
				self.OnSaveFile(event)
				self.DoNewEmptyFile()
				self.text.SetValue(sm_backend.createnewmodule('brailleDisplayDriver', _('untitled'), False))
			elif val == wx.ID_CANCEL:
				dlg.Destroy()
			else:
				self.DoNewEmptyFile()
				self.text.SetValue(sm_backend.createnewmodule('brailleDisplayDriver', _('untitled'), False))
		else:
			self.DoNewEmptyFile()
			self.text.SetValue(sm_backend.createnewmodule('brailleDisplayDriver', _('untitled'), False))

	def OnNewSynthDriver(self, event):
		self.defaultdir = config.getScratchpadDir(True)+os.sep+'synthDrivers'
		if self.text.IsModified and self.text.GetValue():
			dlg = wx.MessageDialog(self, _('Save changes?'), '', wx.YES_NO | wx.YES_DEFAULT | wx.CANCEL | wx.ICON_QUESTION)
			val = dlg.ShowModal()
			if val == wx.ID_YES:
				self.OnSaveFile(event)
				self.DoNewEmptyFile()
				self.text.SetValue(sm_backend.createnewmodule('synthDriver', _('untitled'), False))
			elif val == wx.ID_CANCEL:
				dlg.Destroy()
			else:
				self.DoNewEmptyFile()
				self.text.SetValue(sm_backend.createnewmodule('synthDriver', _('untitled'), False))
		else:
			self.DoNewEmptyFile()
			self.text.SetValue(sm_backend.createnewmodule('synthDriver', _('untitled'), False))

	def OnNewVisionEnhancementProvider(self, event):
		self.defaultdir = config.getScratchpadDir(True)+os.sep+'visionEnhancementProviders'
		if self.text.IsModified and self.text.GetValue():
			dlg = wx.MessageDialog(self, _('Save changes?'), '', wx.YES_NO | wx.YES_DEFAULT | wx.CANCEL | wx.ICON_QUESTION)
			val = dlg.ShowModal()
			if val == wx.ID_YES:
				self.OnSaveFile(event)
				self.DoNewEmptyFile()
				self.text.SetValue(sm_backend.createnewmodule('visionEnhancementProvider', _('untitled'), False))
			elif val == wx.ID_CANCEL:
				dlg.Destroy()
			else:
				self.DoNewEmptyFile()
				self.text.SetValue(sm_backend.createnewmodule('visionEnhancementProvider', _('untitled'), False))
		else:
			self.DoNewEmptyFile()
			self.text.SetValue(sm_backend.createnewmodule('visionEnhancementProvider', _('untitled'), False))




	def DoNewEmptyFile(self):
		self.last_name_saved = ''
		self.text.Clear()

	def OnFinditem(self, event):
		if not hasattr(self, 'frdata'):
			self.frdata = wx.FindReplaceData()
			self.frdata.Flags = self.frdata.Flags | wx.FR_DOWN | wx.FR_NOMATCHCASE
		self.dlg = wx.FindReplaceDialog(parent=self, data=self.frdata, title=_('Find'), style=0)
		self.dlg.Show()
	def OnGotoLineItem(self, event):
		caption=_('go to line number')
		prompt=_('line number:')
		message=_('enter the line number to go to')
		value=self.text.PositionToXY(self.text.GetInsertionPoint())[1]+1
		max=self.text.GetNumberOfLines()
		ned = wx.NumberEntryDialog(parent=self, message=message, prompt=prompt, caption=caption, value=value, min=1, max=max, pos=wx.DefaultPosition)
		if ned.ShowModal() == wx.ID_OK:
			self.text.SetInsertionPoint(self.text.XYToPosition(0, ned.Value-1))
			ned.Destroy()

	def OnReplaceitem(self, event):
		if not hasattr(self, 'frdata'):
			self.frdata = wx.FindReplaceData()
			self.frdata.Flags = self.frdata.Flags | wx.FR_DOWN | wx.FR_NOMATCHCASE
		self.dlg = wx.FindReplaceDialog(parent=self, data=self.frdata, title=_('Find and replace'), style=wx.FR_REPLACEDIALOG)
		self.dlg.Show()
	def OnFindnextitem(self, event):
		self.frdata.Flags = self.frdata.Flags or FR_DOWN
		self.searchresultindex += 1
		if self.searchresultindex == len(self.searchresults):
			self.searchresultindex = 0
		pos = self.text.XYToPosition(self.searchresults[self.searchresultindex][1], self.searchresults[self.searchresultindex][0])
		self.text.SetSelection(pos, pos+len(self.frdata.FindString))

	def OnFindpreviousitem(self, event):
		self.frdata.Flags = self.frdata.Flags or not FR_DOWN
		self.searchresultindex -= 1
		if self.searchresultindex < 0:
			self.searchresultindex = len(self.searchresults)-1
		pos = self.text.XYToPosition(self.searchresults[self.searchresultindex][1], self.searchresults[self.searchresultindex][0])
		self.text.SetSelection(pos, pos+len(self.frdata.FindString))





	def on_find(self, event):
		fstring = self.frdata.FindString          # also from event.GetFindString()
		wordborder = ""
		searchflags = 0
		if self.frdata.Flags & wx.FR_NOMATCHCASE:
			searchflags = searchflags | re.I
		if self.frdata.Flags & wx.FR_WHOLEWORD:
			wordborder = r"\b"
		self.searchpattern = re.compile(pattern=wordborder+fstring+wordborder, flags=searchflags)
		if not hasattr(self, 'searchresults'):
			self.searchresults = []
			for line in range(self.text.GetNumberOfLines()):
				for m in self.searchpattern.finditer(self.text.GetLineText(line)):
					column = m.start()
					self.searchresults.append((line, column))
		if len(self.searchresults) > 0:
			if hasattr(self,"searchresultindex"):
				if self.searchresultindex >= len(self.searchresults):
					self.searchresultindex = 0
				elif self.searchresultindex < 0:
					self.searchresultindex = len(self.searchresults)-1
			if self.frdata.Flags & wx.FR_DOWN:
				direction = 1
				if not hasattr(self, "searchresultindex"):
					self.searchresultindex = 0
			else:
				direction = -1
				if not hasattr(self, "searchresultindex"):
					self.searchresultindex = len(self.searchresults)-1
			pos = self.text.XYToPosition(self.searchresults[self.searchresultindex][1], self.searchresults[self.searchresultindex][0])
			self.text.SetSelection(pos, pos+len(fstring))
			self.searchresultindex += direction
		else:
			gui.messageBox(message=_("text not found"), caption=_("find"))



	def on_replace(self, event):
		fstring = self.frdata.FindString          # also from event.GetFindString()
		rstring = self.frdata.ReplaceString
		wordborder = ""
		searchflags = 0
		if self.frdata.Flags & wx.FR_NOMATCHCASE:
			searchflags = searchflags | re.I
		if self.frdata.Flags & wx.FR_WHOLEWORD:
			wordborder = r"\b"
		self.searchpattern = re.compile(pattern=wordborder+fstring+wordborder, flags=searchflags)
		self.searchresults = []
		for line in range(self.text.GetNumberOfLines()):
			for m in self.searchpattern.finditer(self.text.GetLineText(line)):
				column = m.start()
				self.searchresults.append((line, column))
		if len(self.searchresults) > 0:
			if hasattr(self,"searchresultindex"):
				if self.searchresultindex >= len(self.searchresults):
					self.searchresultindex = 0
				elif self.searchresultindex < 0:
					self.searchresultindex = len(self.searchresults)-1
			if self.frdata.Flags & wx.FR_DOWN:
				direction = 1
				if not hasattr(self, "searchresultindex"):
					self.searchresultindex = 0
			else:
				end = 0
				direction = -1
				if not hasattr(self, "searchresultindex"):
					self.searchresultindex = len(self.searchresults)-1
			pos = self.text.XYToPosition(self.searchresults[self.searchresultindex][1], self.searchresults[self.searchresultindex][0])
			self.text.Remove(pos, pos+len(fstring))
			self.text.WriteText(rstring)
			self.searchresultindex += direction
		else:
			gui.messageBox(message=_("text not found"), caption=_("find"))


	def on_find_replace_all(self, event):
		fstring = self.frdata.FindString          # also from event.GetFindString()
		rstring = self.frdata.ReplaceString
		wordborder = ""
		searchflags = 0
		if self.frdata.Flags & wx.FR_NOMATCHCASE:
			searchflags = searchflags | re.I
		if self.frdata.Flags & wx.FR_WHOLEWORD:
			wordborder = r"\b"
		self.searchpattern = re.compile(pattern=wordborder+fstring+wordborder, flags=searchflags)
		self.searchresults = []
		for line in range(self.text.GetNumberOfLines()):
			for m in self.searchpattern.finditer(self.text.GetLineText(line)):
				column = m.start()
				self.searchresults.append((line, column))
		if len(self.searchresults) > 0:
			for r in self.searchresults:
				pos = self.text.XYToPosition(r[1], r[0])
				self.text.Remove(pos, pos+len(fstring))
				self.text.WriteText(rstring)
		else:
			gui.messageBox(message=_("text not found"), caption=_("find"))

	def OnInsertFunction(self, event):
		ifd = insertfunctionsdialog(self, id=wx.ID_ANY, title=_('insert function'))
		if ifd.ShowModal() == wx.ID_OK:
			self.text.WriteText(ifd.functionstring)
			ifd.Destroy()
	def OnOpenFile(self, event):
		if self.text.IsModified and self.text.GetValue():
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
		wcd = _('All files (*.*)')+'|*.*|'+_('appmodule source files (*.py)')+'|*.py'
		dir = os.getcwd()
		try:
			open_dlg = wx.FileDialog(self, message=_('Choose a file'), defaultDir=dir, defaultFile='', wildcard=wcd, style=wx.FD_OPEN | wx.FD_CHANGE_DIR | wx.FD_FILE_MUST_EXIST)
		except:
			pass
		if open_dlg.ShowModal() == wx.ID_OK:
			path = open_dlg.GetDirectory()+os.sep+open_dlg.GetFilename()
			ui.message(path)
			if self.text.GetLastPosition():
				self.text.Clear()
			self.text.LoadFile(path)
			self.last_name_saved = path
			self.statusbar.SetStatusText('', 1)
			self.modify = False
			self.text.SetSelection(0,0)
		open_dlg.Destroy()
	def OnSaveFile(self, event):
		if self.last_name_saved:
			try:
				self.text.SaveFile(self.last_name_saved)
				self.statusbar.SetStatusText(os.path.basename(self.last_name_saved) + ' '+_('saved'), 0)
				self.statusbar.SetStatusText('', 1)
				self.modify = False
			except error:
				dlg = wx.MessageDialog(self, _('Error saving file')+'\n' + str(error))
				dlg.ShowModal()
		else:
			self.OnSaveAsFile(event)
	def OnSaveAsFile(self, event):
		wcd=_('All files(*.*)')+'|*.*|'+_('appmodule source files (*.py)')+'|*.py'
		if hasattr(self, 'defaultdir'):
			dir = self.defaultdir
		else:
			dir = os.getcwd()
		if hasattr(self, 'defaultfile'):
			defaultfile = self.defaultfile
		else:
			defaultfile = _('untitled')+'.py'
		save_dlg = wx.FileDialog(self, message=_('Save file as...'), defaultDir=dir, defaultFile=defaultfile,
		wildcard=wcd, style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
		if save_dlg.ShowModal() == wx.ID_OK:
			path = save_dlg.GetPath()
			try:
				self.text.SaveFile(path)
				self.last_name_saved = os.path.basename(path)
				self.statusbar.SetStatusText(self.last_name_saved + ' '+_('saved'), 0)
				self.statusbar.SetStatusText('', 1)
				self.Modify = False
			except error:
				dlg = wx.MessageDialog(self, _('Error saving file')+'\n' + str(error))
				dlg.ShowModal()
		save_dlg.Destroy()
	def OnUndo(self, event):
		self.text.Undo()
	def OnRedo(self, event):
		self.text.Redo()

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
		if hasattr(self, 'searchpattern'):
			self.searchresults = []
			for x in range(self.text.GetNumberOfLines()):
				for m in self.searchpattern.finditer(self.text.GetLineText(x)):
					column = m.start()
					self.searchresults.append((x, column))
		self.statusbar.SetStatusText(_(' modified'), 1)
		self.modify = True
		event.Skip()

	def OnKeyDown(self, event):
		keycode = event.GetKeyCode()
		if hasattr(self, "searchresults"):
			if len(self.searchresults) > 0:
				navkeylist = [wx.WXK_DOWN, wx.WXK_END, wx.WXK_HOME, wx.WXK_LEFT, wx.WXK_NUMPAD_DOWN, wx.WXK_NUMPAD_END, wx.WXK_NUMPAD_HOME, wx.WXK_NUMPAD_LEFT, wx.WXK_NUMPAD_PAGEDOWN, wx.WXK_NUMPAD_PAGEUP, wx.WXK_NUMPAD_RIGHT, wx.WXK_NUMPAD_UP, wx.WXK_PAGEDOWN, wx.WXK_PAGEUP, wx.WXK_RIGHT, wx.WXK_UP]
				if keycode in navkeylist:
					x = 0
					while (self.text.XYToPosition(self.searchresults[x][1], self.searchresults[x][0])+len(self.frdata.FindString)) < self.text.GetInsertionPoint():
						x += 1
				self.searchresultindex = x
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
		dlg = wx.MessageDialog(self, _('\tNVDA Script-manager\t\n (c) 2011-{year} by David Parduhn\n portions copyright (C) jan bodnar 2005-2006').format(year=datetime.date.today().year),_('About nvda Script Manager'), wx.OK | wx.ICON_INFORMATION)
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


