import gui
import wx
import inspect
class insertfunctionsdialog(wx.Dialog):
	functionstring = ''
	def __init__(self, parent, id, title):
		super(insertfunctionsdialog, self).__init__(parent, id, title)
		mainsizer = wx.BoxSizer(orient=wx.VERTICAL)
		self.tree = wx.TreeCtrl(self, style=wx.TR_SINGLE | wx.TR_NO_BUTTONS)
		rootnode = self.tree.AddRoot(text='root')
		moduleslist = sys.modules.keys()
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


