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
import json

impPath = os.path.abspath(os.path.dirname(__file__))
sys.path.append(impPath)
import sm_backend, sm_frontend
addonHandler.initTranslation()
from scriptHandler import script

LABEL_SETTINGS_SECTION = 'scriptmanager'
LABEL_METHOD_ORDER_KEY = 'labelingMethodOrder'
LABEL_METHOD_ENABLED_KEY = 'enabledLabelingMethods'
DOUBLE_PRESS_TIMEOUT_MS = 400
AUTOMATIC_METHOD_CODES = ('A', 'B', 'C')
LABEL_METHODS = {
	'A': {
		'name': _('Method A: Automation ID'),
		'selectorKey': 'automationId',
		'automatic': True,
		'prompt': _('Automation ID'),
	},
	'B': {
		'name': _('Method B: Control ID'),
		'selectorKey': 'controlId',
		'automatic': True,
		'prompt': _('Control ID'),
	},
	'C': {
		'name': _('Method C: Window class name'),
		'selectorKey': 'windowClassName',
		'automatic': True,
		'prompt': _('Window class name'),
	},
	'D': {
		'name': _('Method D: Manual Automation ID'),
		'selectorKey': 'automationId',
		'automatic': False,
		'prompt': _('Automation ID'),
	},
	'E': {
		'name': _('Method E: Manual window class name'),
		'selectorKey': 'windowClassName',
		'automatic': False,
		'prompt': _('Window class name'),
	},
}


class LabelingMethodsDialog(wx.Dialog):

	def __init__(self, parent, orderedCodes, enabledCodes):
		super(LabelingMethodsDialog, self).__init__(parent, title=_('Script Manager labeling methods'))
		self.orderedCodes = list(orderedCodes)
		self.enabledCodes = set(enabledCodes)

		mainSizer = wx.BoxSizer(wx.VERTICAL)
		mainSizer.Add(
			wx.StaticText(
				self,
				label=_('Choose which automatic labeling methods are active and in which order they are tried.'),
			),
			0,
			wx.ALL | wx.EXPAND,
			10,
		)

		listSizer = wx.BoxSizer(wx.HORIZONTAL)
		self.methodsList = wx.CheckListBox(self, choices=[])
		listSizer.Add(self.methodsList, 1, wx.EXPAND | wx.ALL, 10)

		buttonSizer = wx.BoxSizer(wx.VERTICAL)
		self.moveUpButton = wx.Button(self, label=_('Move up'))
		self.moveDownButton = wx.Button(self, label=_('Move down'))
		buttonSizer.Add(self.moveUpButton, 0, wx.BOTTOM, 5)
		buttonSizer.Add(self.moveDownButton, 0)
		listSizer.Add(buttonSizer, 0, wx.TOP | wx.RIGHT, 10)
		mainSizer.Add(listSizer, 1, wx.EXPAND)

		mainSizer.Add(self.CreateButtonSizer(wx.OK | wx.CANCEL), 0, wx.ALL | wx.EXPAND, 10)
		self.SetSizerAndFit(mainSizer)

		self.moveUpButton.Bind(wx.EVT_BUTTON, self.onMoveUp)
		self.moveDownButton.Bind(wx.EVT_BUTTON, self.onMoveDown)
		self._refreshList()

	def _refreshList(self):
		labels = [LABEL_METHODS[code]['name'] for code in self.orderedCodes]
		selection = self.methodsList.GetSelection()
		self.methodsList.Set(labels)
		for index, code in enumerate(self.orderedCodes):
			self.methodsList.Check(index, code in self.enabledCodes)
		if selection != wx.NOT_FOUND and selection < len(self.orderedCodes):
			self.methodsList.SetSelection(selection)
		elif self.orderedCodes:
			self.methodsList.SetSelection(0)

	def _swapSelected(self, offset):
		selection = self.methodsList.GetSelection()
		if selection == wx.NOT_FOUND:
			return
		targetIndex = selection + offset
		if targetIndex < 0 or targetIndex >= len(self.orderedCodes):
			return
		self.orderedCodes[selection], self.orderedCodes[targetIndex] = self.orderedCodes[targetIndex], self.orderedCodes[selection]
		self._refreshList()
		self.methodsList.SetSelection(targetIndex)

	def onMoveUp(self, event):
		self._swapSelected(-1)

	def onMoveDown(self, event):
		self._swapSelected(1)

	def getState(self):
		enabledCodes = []
		for index, code in enumerate(self.orderedCodes):
			if self.methodsList.IsChecked(index):
				enabledCodes.append(code)
		return list(self.orderedCodes), enabledCodes


# Klasse von globalpluginhandler-globalplugin ableiten
class GlobalPlugin(globalPluginHandler.GlobalPlugin):

	def __init__(self):
		super(GlobalPlugin, self).__init__()
		self._pendingLabelCallLater = None
		self._toolsMenuItem = None
		self._preferencesMenuItem = None
		self._ensureLabelConfigDefaults()
		wx.CallAfter(self._installMenuItems)

	def terminate(self):
		self._cancelPendingLabelAction()
		self._removeMenuItems()
		super(GlobalPlugin, self).terminate()

	# Our plugin should be assigned to the keyboard combination NVDA+Shift+0. This assignment takes place in a dictionary named __gestures__.
	# and now follows the actual script. The name of the script doesn't quite match the name specified above (the "Script_" is missing, but that's how it should be :-).
	@script(
		description=_('opens the nvda script manager window'),
		category=_('script manager'),
		gesture='kb:nvda+shift+0'
	)
	def script_scriptmanager(self, gesture):
		self._openScriptManagerForCurrentFocus()

	@script(
		description=_('creates or updates a labeling rule for the current navigator object'),
		category=_('script manager'),
		gesture='kb:nvda+shift+r'
	)
	def script_labelNavigatorObject(self, gesture):
		if self._pendingLabelCallLater and self._pendingLabelCallLater.IsRunning():
			self._cancelPendingLabelAction()
			wx.CallAfter(self._labelObjectWithManualMethodSelection)
			return
		self._pendingLabelCallLater = wx.CallLater(DOUBLE_PRESS_TIMEOUT_MS, self._runAutomaticLabelAction)

	def _runAutomaticLabelAction(self):
		self._pendingLabelCallLater = None
		self._labelObjectAutomatically()

	def _cancelPendingLabelAction(self):
		if self._pendingLabelCallLater and self._pendingLabelCallLater.IsRunning():
			self._pendingLabelCallLater.Stop()
		self._pendingLabelCallLater = None

	def _installMenuItems(self):
		try:
			sysTrayIcon = gui.mainFrame.sysTrayIcon
			if not self._toolsMenuItem:
				self._toolsMenuItem = sysTrayIcon.toolsMenu.Append(wx.ID_ANY, _('Script Manager'))
				sysTrayIcon.Bind(wx.EVT_MENU, self.onOpenScriptManagerFromMenu, self._toolsMenuItem)
			if not self._preferencesMenuItem:
				self._preferencesMenuItem = sysTrayIcon.preferencesMenu.Append(wx.ID_ANY, _('Script Manager labeling methods'))
				sysTrayIcon.Bind(wx.EVT_MENU, self.onOpenLabelingMethodsFromMenu, self._preferencesMenuItem)
		except Exception:
			self._toolsMenuItem = None
			self._preferencesMenuItem = None

	def _removeMenuItems(self):
		try:
			sysTrayIcon = gui.mainFrame.sysTrayIcon
		except Exception:
			return
		for menuItem, handler, menuGetter in (
			(self._toolsMenuItem, self.onOpenScriptManagerFromMenu, lambda: sysTrayIcon.toolsMenu),
			(self._preferencesMenuItem, self.onOpenLabelingMethodsFromMenu, lambda: sysTrayIcon.preferencesMenu),
		):
			if not menuItem:
				continue
			try:
				sysTrayIcon.Unbind(wx.EVT_MENU, handler=handler, source=menuItem)
			except Exception:
				pass
			try:
				menuGetter().Remove(menuItem.GetId())
			except Exception:
				pass
		self._toolsMenuItem = None
		self._preferencesMenuItem = None

	def onOpenScriptManagerFromMenu(self, event):
		self._openScriptManagerForCurrentFocus()

	def onOpenLabelingMethodsFromMenu(self, event):
		order, enabled = self._loadAutomaticMethodSettings()
		dialog = LabelingMethodsDialog(gui.mainFrame, order, enabled)
		try:
			if dialog.ShowModal() != wx.ID_OK:
				return
			updatedOrder, updatedEnabled = dialog.getState()
			self._saveAutomaticMethodSettings(updatedOrder, updatedEnabled)
			ui.message(_('Script Manager labeling methods saved.'))
		finally:
			dialog.Destroy()

	def _openScriptManagerForCurrentFocus(self):
		focus = api.getFocusObject()
		appname, shouldLoad = self._prepareUserAppModuleForObject(focus, createIfMissing=False)
		if shouldLoad:
			wx.CallAfter(self.loadappmodule, appname)
		else:
			wx.CallAfter(self.loadappmodule, '')

	def _prepareUserAppModuleForObject(self, obj, createIfMissing):
		appname = self._getAppNameFromObject(obj)
		if not appname:
			return '', False
		addon = False
		load = False
		if not appModuleHandler.doesAppModuleExist(appname):
			sm_backend.createnewmodule('appModule', appname, True)
			load = True
		else:
			load = sm_backend.userappmoduleexists(appname)
			if not load:
				addon = sm_backend.appmoduleprovidedbyaddon(appname)
				if addon:
					sm_backend.copyappmodulefromaddon(addon=addon, appname=appname)
					load = True
		if not load and createIfMissing:
			sm_backend.createnewmodule('appModule', appname, True)
			load = True
		return appname, bool(load)

	def _ensureUserAppModulePath(self, obj):
		appname, shouldLoad = self._prepareUserAppModuleForObject(obj, createIfMissing=True)
		if not appname or not shouldLoad:
			return '', ''
		return appname, sm_backend.get_user_appmodule_path(appname)

	def _getAppNameFromObject(self, obj):
		try:
			return appModuleHandler.getAppNameFromProcessID(obj.processID, False)
		except Exception:
			return ''

	def loadappmodule(self, appname):
		userconfigfile = config.getScratchpadDir(True) + os.sep + 'appModules' + os.sep + appname + '.py'
		if appname:
			frame = sm_frontend.scriptmanager_mainwindow(None, -1, _('NVDA Script Manager'), userconfigfile)
		else:
			frame = sm_frontend.scriptmanager_mainwindow(None, -1, _('NVDA Script Manager'), '')
		frame.Show(True)
		frame.SetPosition(wx.Point(0, 0))
		frame.SetSize(wx.DisplaySize())
		frame.text.SetFocus()

	def _getLabelTargetObject(self):
		try:
			target = api.getNavigatorObject()
		except Exception:
			target = None
		if not target:
			try:
				target = api.getFocusObject()
			except Exception:
				target = None
		return target

	def _labelObjectAutomatically(self):
		target = self._getLabelTargetObject()
		if not target:
			ui.message(_('No object is available for labeling.'))
			return
		candidates = sm_backend.get_label_method_candidates(target)
		order, enabled = self._loadAutomaticMethodSettings()
		for methodCode in order:
			if methodCode not in enabled:
				continue
			rule = self._buildRuleForMethod(methodCode, target, candidates, manualSelection=False)
			if rule:
				self._saveRuleForObject(target, rule)
				return
		ui.message(_('No automatic labeling method is available for this object. Press NVDA+Shift+R twice to choose a method manually.'))

	def _labelObjectWithManualMethodSelection(self):
		target = self._getLabelTargetObject()
		if not target:
			ui.message(_('No object is available for labeling.'))
			return
		candidates = sm_backend.get_label_method_candidates(target)
		methodCode = self._chooseManualMethod(candidates)
		if not methodCode:
			return
		rule = self._buildRuleForMethod(methodCode, target, candidates, manualSelection=True)
		if rule:
			self._saveRuleForObject(target, rule)

	def _chooseManualMethod(self, candidates):
		choices = ['A', 'B', 'C', 'D', 'E']
		labels = [self._getMethodChoiceLabel(code, candidates) for code in choices]
		dialog = wx.SingleChoiceDialog(
			gui.mainFrame,
			_('Choose a labeling method for the current object.'),
			_('Script Manager labeling'),
			labels,
		)
		try:
			if dialog.ShowModal() != wx.ID_OK:
				return None
			selection = dialog.GetSelection()
			if selection == wx.NOT_FOUND:
				return None
			return choices[selection]
		finally:
			dialog.Destroy()

	def _getMethodChoiceLabel(self, methodCode, candidates):
		methodInfo = LABEL_METHODS[methodCode]
		selectorValue = candidates.get(methodInfo['selectorKey'], '')
		if selectorValue:
			return _('{name} (current value: {value})').format(name=methodInfo['name'], value=selectorValue)
		return methodInfo['name']

	def _buildRuleForMethod(self, methodCode, target, candidates, manualSelection):
		methodInfo = LABEL_METHODS[methodCode]
		selectorKey = methodInfo['selectorKey']
		selectorValue = candidates.get(selectorKey, '')
		if manualSelection or not selectorValue:
			selectorValue = self._promptForSelectorValue(methodInfo, selectorValue)
		if not selectorValue:
			return None
		labelText = self._promptForLabelText(target)
		if labelText is None:
			return None
		roleName = candidates.get('role', '')
		if not roleName:
			ui.message(_('The current object has no usable role information for labeling.'))
			return None
		return {
			'label': labelText,
			'method': methodInfo['name'],
			'methodCode': methodCode,
			'selectors': {
				'role': roleName,
				selectorKey: selectorValue,
			},
		}

	def _promptForSelectorValue(self, methodInfo, defaultValue):
		dialog = wx.TextEntryDialog(
			gui.mainFrame,
			_('Enter the value for {field}.').format(field=methodInfo['prompt']),
			_('Script Manager labeling'),
			value=defaultValue,
		)
		try:
			if dialog.ShowModal() != wx.ID_OK:
				return None
			value = dialog.GetValue().strip()
			if not value:
				ui.message(_('No selector value was entered.'))
				return None
			return value
		finally:
			dialog.Destroy()

	def _promptForLabelText(self, target):
		defaultLabel = ''
		try:
			defaultLabel = target.name or ''
		except Exception:
			defaultLabel = ''
		dialog = wx.TextEntryDialog(
			gui.mainFrame,
			_('Enter the label text to store for this object.'),
			_('Script Manager labeling'),
			value=defaultLabel,
		)
		try:
			if dialog.ShowModal() != wx.ID_OK:
				return None
			labelText = dialog.GetValue().strip()
			if not labelText:
				ui.message(_('No label text was entered.'))
				return None
			return labelText
		finally:
			dialog.Destroy()

	def _saveRuleForObject(self, target, rule):
		appname, appmodulePath = self._ensureUserAppModulePath(target)
		if not appname or not appmodulePath:
			ui.message(_('No AppModule could be prepared for the current object.'))
			return
		try:
			action = sm_backend.save_label_rule(appmodulePath, rule)
		except Exception as error:
			gui.messageBox(str(error), _('Script Manager labeling error'), wx.OK | wx.ICON_ERROR)
			return
		try:
			appModuleHandler.reloadAppModules()
		except Exception:
			pass
		ui.message(
			_('Labeling rule {action} for {appname}.').format(
				action=_('updated') if action == 'updated' else _('created'),
				appname=appname,
			)
		)

	def _ensureLabelConfigDefaults(self):
		section = self._getLabelConfigSection()
		updated = False
		if LABEL_METHOD_ORDER_KEY not in section:
			section[LABEL_METHOD_ORDER_KEY] = json.dumps(list(AUTOMATIC_METHOD_CODES))
			updated = True
		if LABEL_METHOD_ENABLED_KEY not in section:
			section[LABEL_METHOD_ENABLED_KEY] = json.dumps(list(AUTOMATIC_METHOD_CODES))
			updated = True
		if updated:
			self._saveConfig()

	def _getLabelConfigSection(self):
		try:
			if LABEL_SETTINGS_SECTION not in config.conf:
				config.conf[LABEL_SETTINGS_SECTION] = {}
			return config.conf[LABEL_SETTINGS_SECTION]
		except Exception:
			config.conf[LABEL_SETTINGS_SECTION] = {}
			return config.conf[LABEL_SETTINGS_SECTION]

	def _loadAutomaticMethodSettings(self):
		section = self._getLabelConfigSection()
		order = self._parseStoredMethodCodes(section.get(LABEL_METHOD_ORDER_KEY), list(AUTOMATIC_METHOD_CODES))
		enabled = self._parseStoredMethodCodes(section.get(LABEL_METHOD_ENABLED_KEY), list(AUTOMATIC_METHOD_CODES))
		for code in AUTOMATIC_METHOD_CODES:
			if code not in order:
				order.append(code)
		return order, [code for code in enabled if code in AUTOMATIC_METHOD_CODES]

	def _saveAutomaticMethodSettings(self, orderedCodes, enabledCodes):
		section = self._getLabelConfigSection()
		section[LABEL_METHOD_ORDER_KEY] = json.dumps([code for code in orderedCodes if code in AUTOMATIC_METHOD_CODES])
		section[LABEL_METHOD_ENABLED_KEY] = json.dumps([code for code in enabledCodes if code in AUTOMATIC_METHOD_CODES])
		self._saveConfig()

	def _parseStoredMethodCodes(self, rawValue, fallback):
		if isinstance(rawValue, (list, tuple)):
			codes = [str(value) for value in rawValue]
		else:
			try:
				codes = json.loads(rawValue) if rawValue else list(fallback)
			except Exception:
				codes = list(fallback)
		filtered = []
		for code in codes:
			if code in AUTOMATIC_METHOD_CODES and code not in filtered:
				filtered.append(code)
		return filtered or list(fallback)

	def _saveConfig(self):
		try:
			config.conf.save()
		except Exception:
			pass
