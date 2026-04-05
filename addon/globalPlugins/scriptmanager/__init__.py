# Global plugin to make it easier to create/load application modules for NVDA.
#
# First get the required stuff :-)
import wx
import globalPluginHandler
import appModuleHandler
import api
import ui
import addonHandler
import config
import languageHandler
import os
import shutil
import sys
import gui
import re
import threading
import keyword
import ast
import json
import tokenize
import textInfos
from gui import guiHelper, settingsDialogs
from gui.nvdaControls import AutoWidthColumnCheckListCtrl
impPath = os.path.abspath(os.path.dirname(__file__))
sys.path.append(impPath)
import sm_backend, sm_frontend
addonHandler.initTranslation()
from scriptHandler import script, getLastScriptRepeatCount
from logHandler import log

AUTO_LABEL_METHODS = (
	("A", _("A: Text child objects")),
	("B", _("B: OneCore OCR")),
	("C", _("C: UIA Automation ID")),
	("D", _("D: Hover tooltip")),
)
DEFAULT_AUTO_LABEL_METHOD_ORDER = [code for code, _label in AUTO_LABEL_METHODS]
LABEL_METHOD_SETTINGS_FILENAME = "scriptmanagerLabelMethods.json"


def _install_language_normalization_guard():
	"""Guard against NVDA core calling normalizeLanguage with None."""
	originalNormalizeLanguage = getattr(languageHandler, "normalizeLanguage", None)
	if originalNormalizeLanguage is None:
		return
	if getattr(originalNormalizeLanguage, "_scriptManagerGuarded", False):
		return

	def normalizeLanguageSafe(language):
		if language is None:
			try:
				language = languageHandler.getLanguage()
			except Exception:
				language = "en"
			if not language:
				language = "en"
		try:
			return originalNormalizeLanguage(language)
		except AttributeError:
			fallback = language or "en"
			return str(fallback).replace("-", "_")

	normalizeLanguageSafe._scriptManagerGuarded = True
	languageHandler.normalizeLanguage = normalizeLanguageSafe


class LabelMethodSettingsDialog(wx.Dialog):
	"""Dialog to enable, disable and reorder automatic labeling methods."""

	def __init__(self, parent):
		super().__init__(parent, title=_("Automatic labeling methods"))
		settings = _load_label_method_settings()
		self._method_order = list(settings["order"])
		self._enabled_methods = set(settings["enabled"])
		self._build_ui()
		self._refresh_method_list()

	def _build_ui(self):
		mainSizer = wx.BoxSizer(wx.VERTICAL)
		mainSizer.Add(
			wx.StaticText(
				self,
				label=_(
					"Choose which automatic labeling methods should be used for NVDA+Shift+R and arrange their priority."
				),
			),
			0,
			wx.ALL | wx.EXPAND,
			10,
		)

		contentSizer = wx.BoxSizer(wx.HORIZONTAL)
		self.methodsList = AutoWidthColumnCheckListCtrl(
			self,
			style=wx.LC_REPORT | wx.LC_SINGLE_SEL,
		)
		self.methodsList.InsertColumn(0, _("Method"))
		self.methodsList.Bind(wx.EVT_LIST_ITEM_SELECTED, self._onSelectionChanged)
		itemCheckedEvent = getattr(wx, "EVT_LIST_ITEM_CHECKED", None)
		if itemCheckedEvent is not None:
			self.methodsList.Bind(itemCheckedEvent, self._onCheckStateChanged)
		itemUncheckedEvent = getattr(wx, "EVT_LIST_ITEM_UNCHECKED", None)
		if itemUncheckedEvent is not None:
			self.methodsList.Bind(itemUncheckedEvent, self._onCheckStateChanged)
		contentSizer.Add(self.methodsList, 1, wx.ALL | wx.EXPAND, 10)

		buttonSizer = wx.BoxSizer(wx.VERTICAL)
		self.moveUpButton = wx.Button(self, label=_("Move &up"))
		self.moveDownButton = wx.Button(self, label=_("Move &down"))
		buttonSizer.Add(self.moveUpButton, 0, wx.BOTTOM | wx.EXPAND, 5)
		buttonSizer.Add(self.moveDownButton, 0, wx.EXPAND)
		contentSizer.Add(buttonSizer, 0, wx.TOP | wx.RIGHT | wx.BOTTOM, 10)

		self.moveUpButton.Bind(wx.EVT_BUTTON, self._onMoveUp)
		self.moveDownButton.Bind(wx.EVT_BUTTON, self._onMoveDown)

		mainSizer.Add(contentSizer, 1, wx.EXPAND)
		mainSizer.Add(
			wx.StaticText(
				self,
				label=_(
					"Checked entries are applied automatically. Higher entries have higher priority."
				),
			),
			0,
			wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
			10,
		)
		mainSizer.Add(self.CreateButtonSizer(wx.OK | wx.CANCEL), 0, wx.ALL | wx.ALIGN_RIGHT, 10)
		self.SetSizerAndFit(mainSizer)

	def _refresh_method_list(self):
		self.methodsList.DeleteAllItems()
		for index, method_code in enumerate(self._method_order):
			self.methodsList.InsertItem(index, _get_auto_label_method_label(method_code))
			self._set_checked(index, method_code in self._enabled_methods)
		if self._method_order:
			selection = self._get_selection()
			if selection == wx.NOT_FOUND:
				self._set_selection(0)
		self._update_move_buttons()

	def _get_selection(self):
		selection = self.methodsList.GetFirstSelected()
		if selection < 0:
			return wx.NOT_FOUND
		return selection

	def _set_selection(self, index):
		if hasattr(self.methodsList, "Select"):
			self.methodsList.Select(index)
			return
		self.methodsList.SetItemState(index, wx.LIST_STATE_SELECTED, wx.LIST_STATE_SELECTED)

	def _set_checked(self, index, checked):
		if hasattr(self.methodsList, "Check"):
			self.methodsList.Check(index, checked)
			return
		if hasattr(self.methodsList, "CheckItem"):
			self.methodsList.CheckItem(index, checked)

	def _is_checked(self, index):
		if hasattr(self.methodsList, "IsChecked"):
			return self.methodsList.IsChecked(index)
		if hasattr(self.methodsList, "IsItemChecked"):
			return self.methodsList.IsItemChecked(index)
		return False

	def _capture_enabled_methods_from_list(self):
		enabled = set()
		for index, method_code in enumerate(self._method_order):
			if self._is_checked(index):
				enabled.add(method_code)
		self._enabled_methods = enabled

	def _update_move_buttons(self):
		selection = self._get_selection()
		has_selection = selection != wx.NOT_FOUND
		self.moveUpButton.Enable(has_selection and selection > 0)
		self.moveDownButton.Enable(has_selection and selection < len(self._method_order) - 1)

	def _onSelectionChanged(self, event):
		self._update_move_buttons()
		event.Skip()

	def _onCheckStateChanged(self, event):
		index = event.GetIndex()
		if 0 <= index < len(self._method_order):
			method_code = self._method_order[index]
			if self._is_checked(index):
				self._enabled_methods.add(method_code)
			else:
				self._enabled_methods.discard(method_code)
		event.Skip()

	def _move_selected(self, direction):
		selection = self._get_selection()
		if selection == wx.NOT_FOUND:
			return
		self._capture_enabled_methods_from_list()
		target = selection + direction
		if target < 0 or target >= len(self._method_order):
			return
		self._method_order[selection], self._method_order[target] = self._method_order[target], self._method_order[selection]
		self._refresh_method_list()
		self._set_selection(target)
		self._update_move_buttons()

	def _onMoveUp(self, event):
		self._move_selected(-1)

	def _onMoveDown(self, event):
		self._move_selected(1)

	def getSettings(self):
		self._capture_enabled_methods_from_list()
		return {
			"order": list(self._method_order),
			"enabled": [method_code for method_code in self._method_order if method_code in self._enabled_methods],
		}


class ScriptManagerSettingsPanel(settingsDialogs.SettingsPanel):
	title = _("Script Manager")

	def makeSettings(self, settingsSizer):
		helper = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		infoLabel = helper.addItem(
			wx.StaticText(
				self,
				label=_(
					"Scratchpad-dependent functions stay unavailable until Scratchpad processing is enabled in NVDA's Advanced settings."
				),
			)
		)
		if hasattr(infoLabel, "Wrap"):
			infoLabel.Wrap(550)
		editorInfoLabel = helper.addItem(
			wx.StaticText(
				self,
				label=_(
					"Editor options such as definition filter, docstring/error translation, blacklist usage, and indentation are available directly in Script Manager under Edit > Settings."
				),
			)
		)
		if hasattr(editorInfoLabel, "Wrap"):
			editorInfoLabel.Wrap(550)
		self.showAddonFolderHintCheckBox = helper.addItem(
			wx.CheckBox(
				self,
				label=_("Show add-on folder hint when opening the temp folder"),
			)
		)
		self._loadValues()

	def _loadValues(self):
		self.showAddonFolderHintCheckBox.SetValue(sm_backend.get_show_addon_folder_hint())

	def onSave(self):
		sm_backend.set_show_addon_folder_hint(self.showAddonFolderHintCheckBox.GetValue())


class ObjectPathDialog(wx.Dialog):
	"""Dialog zum Aufbau eines Navigations-Objektpfads für die Beschriftungsmethode E."""

	_NAV_STEPS = [
		("previous", _("← previous")),
		("next", _("→ &next")),
		("parent", _("↑ &parent")),
		("firstChild", _("↓ &firstChild")),
		("lastChild", _("↓ &lastChild")),
	]

	def __init__(self, parent, nav_obj):
		super().__init__(parent, title=_("Define object path (method E)"))
		self._nav_obj = nav_obj
		self._steps = []
		self._build_ui()
		self._bind_shortcuts()
		self._update()

	def _build_ui(self):
		mainSizer = wx.BoxSizer(wx.VERTICAL)

		stepBox = wx.StaticBoxSizer(
			wx.StaticBox(self, label=_("Add navigation step:")), wx.HORIZONTAL
		)
		self._step_buttons = {}
		for step, label in self._NAV_STEPS:
			btn = wx.Button(self, label=label)
			btn.Bind(wx.EVT_BUTTON, lambda e, s=step: self._add_step(s))
			stepBox.Add(btn, 0, wx.ALL, 4)
			self._step_buttons[step] = btn
		mainSizer.Add(stepBox, 0, wx.EXPAND | wx.ALL, 5)

		pathSizer = wx.BoxSizer(wx.HORIZONTAL)
		pathSizer.Add(
			wx.StaticText(self, label=_("Current path:")), 0,
			wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5
		)
		self._path_ctrl = wx.TextCtrl(self, style=wx.TE_READONLY)
		pathSizer.Add(self._path_ctrl, 1, wx.EXPAND | wx.ALL, 5)
		mainSizer.Add(pathSizer, 0, wx.EXPAND | wx.ALL, 5)

		previewSizer = wx.BoxSizer(wx.HORIZONTAL)
		previewSizer.Add(
			wx.StaticText(self, label=_("Target object name:")), 0,
			wx.ALIGN_CENTER_VERTICAL | wx.ALL, 5
		)
		self._preview_ctrl = wx.TextCtrl(self, style=wx.TE_READONLY)
		previewSizer.Add(self._preview_ctrl, 1, wx.EXPAND | wx.ALL, 5)
		mainSizer.Add(previewSizer, 0, wx.EXPAND | wx.ALL, 5)

		editSizer = wx.BoxSizer(wx.HORIZONTAL)
		self._remove_btn = wx.Button(self, label=_("&Remove last step"))
		self._remove_btn.Bind(wx.EVT_BUTTON, self._remove_last)
		editSizer.Add(self._remove_btn, 0, wx.ALL, 5)
		self._clear_btn = wx.Button(self, label=_("&Clear path"))
		self._clear_btn.Bind(wx.EVT_BUTTON, self._clear)
		editSizer.Add(self._clear_btn, 0, wx.ALL, 5)
		mainSizer.Add(editSizer, 0, wx.ALL, 5)

		btnSizer = self.CreateButtonSizer(wx.OK | wx.CANCEL)
		mainSizer.Add(btnSizer, 0, wx.ALIGN_RIGHT | wx.ALL, 5)

		self.SetSizerAndFit(mainSizer)
		self._ok_btn = self.FindWindowById(wx.ID_OK)
		self._cancel_btn = self.FindWindowById(wx.ID_CANCEL)

	def _bind_shortcuts(self):
		self._shortcut_ids = {
			"next": wx.NewIdRef(),
			"previous": wx.NewIdRef(),
			"firstChild": wx.NewIdRef(),
			"lastChild": wx.NewIdRef(),
			"parent": wx.NewIdRef(),
			"ok": wx.NewIdRef(),
			"clear": wx.NewIdRef(),
			"remove": wx.NewIdRef(),
			"cancel": wx.NewIdRef(),
		}
		for step in ("next", "previous", "firstChild", "lastChild", "parent"):
			self.Bind(
				wx.EVT_MENU,
				lambda evt, stepName=step: self._add_step(stepName),
				id=self._shortcut_ids[step],
			)
		self.Bind(wx.EVT_MENU, self._on_ok_shortcut, id=self._shortcut_ids["ok"])
		self.Bind(wx.EVT_MENU, self._clear, id=self._shortcut_ids["clear"])
		self.Bind(wx.EVT_MENU, self._remove_last, id=self._shortcut_ids["remove"])
		self.Bind(wx.EVT_MENU, self._on_cancel_shortcut, id=self._shortcut_ids["cancel"])
		entries = [
			(wx.ACCEL_NORMAL, wx.WXK_RIGHT, int(self._shortcut_ids["next"])),
			(wx.ACCEL_NORMAL, wx.WXK_LEFT, int(self._shortcut_ids["previous"])),
			(wx.ACCEL_NORMAL, wx.WXK_DOWN, int(self._shortcut_ids["firstChild"])),
			(wx.ACCEL_SHIFT, wx.WXK_DOWN, int(self._shortcut_ids["lastChild"])),
			(wx.ACCEL_NORMAL, wx.WXK_UP, int(self._shortcut_ids["parent"])),
			(wx.ACCEL_NORMAL, wx.WXK_RETURN, int(self._shortcut_ids["ok"])),
			(wx.ACCEL_NORMAL, wx.WXK_NUMPAD_ENTER, int(self._shortcut_ids["ok"])),
			(wx.ACCEL_NORMAL, wx.WXK_DELETE, int(self._shortcut_ids["clear"])),
			(wx.ACCEL_NORMAL, wx.WXK_BACK, int(self._shortcut_ids["remove"])),
			(wx.ACCEL_NORMAL, wx.WXK_ESCAPE, int(self._shortcut_ids["cancel"])),
		]
		self.SetAcceleratorTable(wx.AcceleratorTable(entries))

	def _add_step(self, step):
		self._steps.append(step)
		self._update(announce=True)

	def _remove_last(self, event):
		if self._steps:
			self._steps.pop()
			self._update(announce=True)

	def _clear(self, event):
		if self._steps:
			self._steps = []
			self._update(announce=True)

	def _on_ok_shortcut(self, event):
		if self._steps:
			self.EndModal(wx.ID_OK)

	def _on_cancel_shortcut(self, event):
		self.EndModal(wx.ID_CANCEL)

	def _get_target(self):
		obj = self._nav_obj
		for step in self._steps:
			if obj is None:
				return None
			obj = getattr(obj, step, None)
		return obj

	def _update(self, announce=False):
		if self._steps:
			self._path_ctrl.SetValue("self." + ".".join(self._steps))
		else:
			self._path_ctrl.SetValue("self")
		target = self._get_target()
		if not self._steps:
			self._preview_ctrl.SetValue(_("(no steps defined yet)"))
		elif target is not None:
			name = (getattr(target, "name", "") or "").strip()
			self._preview_ctrl.SetValue(name if name else _("(no name)"))
		else:
			self._preview_ctrl.SetValue(_("(object not reachable)"))
		if self._ok_btn:
			self._ok_btn.Enable(bool(self._steps))
		if self._remove_btn:
			self._remove_btn.Enable(bool(self._steps))
		if self._clear_btn:
			self._clear_btn.Enable(bool(self._steps))
		if announce:
			self._announce_target(target)

	def _announce_target(self, target):
		if target is None:
			ui.message(_("(object not reachable)"))
			return
		name = (getattr(target, "name", "") or "").strip()
		ui.message(name if name else _("(no name)"))

	def get_path(self):
		"""Gibt den Punktpfad zurück, z.B. 'previous.previous'."""
		return ".".join(self._steps)


def _method_code(method):
	return str(method or "").split(":", 1)[0].strip().upper()


def _show_single_choice_index(message, caption, choices, parent=None):
	"""Compatibility wrapper for single-choice dialogs across wx versions.

	Returns the selected index or -1 if cancelled.
	"""
	dlg = wx.SingleChoiceDialog(parent, message, caption, choices)
	try:
		if dlg.ShowModal() == wx.ID_OK:
			return dlg.GetSelection()
		return -1
	finally:
		dlg.Destroy()


def _get_scratchpad_appmodule_path(appname, ensure_exists=True):
	if not appname:
		return None
	scratchpad_dir = config.getScratchpadDir(bool(ensure_exists))
	appmodules_dir = os.path.join(scratchpad_dir, "appModules")
	if ensure_exists:
		os.makedirs(appmodules_dir, exist_ok=True)
	return os.path.join(appmodules_dir, appname + ".py")


def _user_appmodule_exists(appname):
	path = _get_scratchpad_appmodule_path(appname, ensure_exists=False)
	if path and os.path.isfile(path):
		return path
	return None


def _find_addon_appmodule_provider(appname):
	for addon in addonHandler.getRunningAddons():
		addon_module_path = os.path.join(addon.path, "appModules", appname + ".py")
		if os.path.isfile(addon_module_path):
			return addon
	return None


def _copy_addon_appmodule_to_scratchpad(appname, addon):
	addonname = addon.manifest["name"]
	addon_module_path = os.path.join(addon.path, "appModules", appname + ".py")
	user_module_path = _get_scratchpad_appmodule_path(appname, ensure_exists=True)
	shutil.copy2(addon_module_path, user_module_path)
	ui.message(
		_("copying appmodule for {appname} from addon {addonname} to user's config folder...").format(
			addonname=addonname,
			appname=appname,
		)
	)


def _disable_addon_and_create_empty_appmodule(appname, addon):
	addonname = addon.manifest["name"]
	sm_backend.createnewmodule("appModule", appname, True)
	addon.disable(onInstall=False)
	ui.message(
		_("addon {addonname} disabled. Created empty appModule for {appname}.").format(
			addonname=addonname,
			appname=appname,
		)
	)


# Klasse von globalpluginhandler-globalplugin ableiten
class GlobalPlugin(globalPluginHandler.GlobalPlugin):

	def __init__(self):
		super().__init__()
		_install_language_normalization_guard()
		sm_backend.ensure_scriptmanager_config_spec()
		self._settingsPanelRegistered = False
		if ScriptManagerSettingsPanel not in settingsDialogs.NVDASettingsDialog.categoryClasses:
			settingsDialogs.NVDASettingsDialog.categoryClasses.append(ScriptManagerSettingsPanel)
			self._settingsPanelRegistered = True
		self._labelRuleDialogActive = False
		self._pendingForceChoice = False
		self._labelCallbackPending = False
		self._pendingLabelNavObject = None
		self._pendingLabelAppName = None
		self._highlightColorCache = {}
		self._graphicLabelingActive = False
		self.preferencesMenu = gui.mainFrame.sysTrayIcon.preferencesMenu
		self.toolsMenu = gui.mainFrame.sysTrayIcon.toolsMenu
		self._sysTrayIcon = gui.mainFrame.sysTrayIcon
		self.labelMethodSettingsItem = self.preferencesMenu.Append(
			wx.ID_ANY,
			_("Script Manager labeling &methods..."),
			_("Configure automatic labeling method priority"),
		)
		self._sysTrayIcon.Bind(
			wx.EVT_MENU,
			self.onLabelMethodSettings,
			self.labelMethodSettingsItem,
		)
		self.scriptManagerToolsItem = self.toolsMenu.Append(
			wx.ID_ANY,
			_("Script &Manager"),
			_("Open Script Manager with an empty file"),
		)
		self._sysTrayIcon.Bind(wx.EVT_MENU, self.onToolsEmptyFile, self.scriptManagerToolsItem)

	def terminate(self):
		try:
			self._sysTrayIcon.Unbind(wx.EVT_MENU, handler=self.onToolsEmptyFile, source=self.scriptManagerToolsItem)
		except Exception:
			pass
		try:
			self.toolsMenu.RemoveItem(self.scriptManagerToolsItem)
		except Exception:
			pass
		try:
			self.preferencesMenu.RemoveItem(self.labelMethodSettingsItem)
		except Exception:
			pass
		if self._settingsPanelRegistered:
			try:
				settingsDialogs.NVDASettingsDialog.categoryClasses.remove(ScriptManagerSettingsPanel)
			except ValueError:
				pass
		super().terminate()

	def _ensureScratchpadForAction(self, reasonText):
		if sm_backend.ensure_scratchpad_available(parent=gui.mainFrame, reasonText=reasonText):
			return True
		ui.message(sm_backend.get_scratchpad_disabled_message(reasonText))
		return False

	def onLabelMethodSettings(self, evt):
		gui.mainFrame.prePopup()
		dlg = LabelMethodSettingsDialog(gui.mainFrame)
		try:
			if dlg.ShowModal() == wx.ID_OK:
				_save_label_method_settings(dlg.getSettings())
				ui.message(_("Automatic labeling methods saved"))
		finally:
			dlg.Destroy()
			gui.mainFrame.postPopup()

	def _askOpenAppModule(self, appname):
		if wx.MessageBox(
			_("open appModule in Script Manager now?"),
			_("Script Manager"),
			wx.YES_NO | wx.ICON_QUESTION,
		) == wx.YES:
			self.loadappmodule(appname)

	def onToolsEmptyFile(self, evt):
		self.loadappmodule("", source="toolsMenu")

	def onToolsCreateAppModule(self, evt):
		appName = self._toolsAppNameByMenuId.get(evt.GetId())
		if not appName:
			return
		if not self._ensureScratchpadForAction(_("Script Manager needs scratchpad to create appModules.")):
			return
		self._prepareAndLoadAppModule(appName)

	def _prepareAndLoadAppModule(self, appname):
		if not appname:
			self.loadappmodule("")
			return
		load = False
		if not appModuleHandler.doesAppModuleExist(appname):
			sm_backend.createnewmodule('appModule', appname, True)
			load = True
		else:
			load = _user_appmodule_exists(appname)
			if not load:
				addon = _find_addon_appmodule_provider(appname)
				if addon:
					addonname = addon.manifest['name']
					dlg = wx.MessageDialog(
						None,
						_("An appModule for {appname} is provided by the addon '{addonname}'.\n\nDo you want to temporarily disable this addon and create an empty appModule in the scratchpad?").format(appname=appname, addonname=addonname),
						_("appModule provided by addon"),
						wx.YES_NO | wx.ICON_QUESTION,
					)
					result = dlg.ShowModal()
					dlg.Destroy()
					if result == wx.ID_YES:
						_disable_addon_and_create_empty_appmodule(appname=appname, addon=addon)
					else:
						_copy_addon_appmodule_to_scratchpad(addon=addon, appname=appname)
					load = bool(_user_appmodule_exists(appname))
		if load:
			self.loadappmodule(appname)
		else:
			self.loadappmodule("")

	# Our plugin should be assigned to the keyboard combination NVDA+Shift+0. This assignment takes place in a dictionary named __gestures__.
	# and now follows the actual script. The name of the script doesn't quite match the name specified above (the "Script_" is missing, but that's how it should be :-).
	@script(
		description=_("opens the nvda script manager window"),
		category=_("script manager"),
		gesture="kb:nvda+shift+0"
	)
	def script_scriptmanager(self, gesture):
		if not self._ensureScratchpadForAction(_("Script Manager needs scratchpad to load appModules.")):
			self.loadappmodule("", source="gestureScratchpadFallback")
			return
		focus = api.getFocusObject()
		processId = getattr(focus, "processID", 0) if focus else 0
		appname = appModuleHandler.getAppNameFromProcessID(processId, False) if processId else ""
		self._prepareAndLoadAppModule(appname)

	def loadappmodule(self, appname, source="unknown"):
		log.debug(
			"ScriptManager open requested: source=%s appname=%r scratchpadEnabled=%s",
			source,
			appname,
			sm_backend.is_scratchpad_enabled(),
		)
		if appname and sm_backend.is_scratchpad_enabled():
			userconfigfile = _get_scratchpad_appmodule_path(appname, ensure_exists=True)
			frame = sm_frontend.scriptmanager_mainwindow(None, -1, _('NVDA Script Manager'), userconfigfile)
		else:
			frame = sm_frontend.scriptmanager_mainwindow(None, -1, _('NVDA Script Manager'), '')
		frame.Show(True)
		frame.SetPosition(wx.Point(0, 0))
		frame.SetSize(wx.DisplaySize())
		if hasattr(frame, "bring_to_foreground"):
			frame.bring_to_foreground()
		else:
			frame.Raise()
			frame.text.SetFocus()

	@script(
		description=_("creates a new label for the focused object and saves a labeling rule in the appModule"),
		category=_("script manager"),
		gesture="kb:nvda+shift+r"
	)
	def script_labelInaccessibleNavigatorObject(self, gesture):
		# repeatCount sofort erfassen – wie in NVDAs navigatorObject_current
		self._pendingForceChoice = getLastScriptRepeatCount() >= 1
		if self._labelRuleDialogActive:
			return
		if not self._labelCallbackPending:
			nav = api.getNavigatorObject()
			self._pendingLabelNavObject = nav
			processId = getattr(nav, "processID", 0) if nav else 0
			if not processId:
				focusObj = api.getFocusObject()
				processId = getattr(focusObj, "processID", 0) if focusObj else 0
			if processId:
				self._pendingLabelAppName = appModuleHandler.getAppNameFromProcessID(processId, False)
			else:
				self._pendingLabelAppName = None
			self._labelCallbackPending = True
			wx.CallAfter(self._doLabelInaccessibleNavigatorObject)

	def _doLabelInaccessibleNavigatorObject(self):
		self._labelCallbackPending = False
		if not self._ensureScratchpadForAction(_("Labeling rules are stored in scratchpad appModules.")):
			self._pendingLabelNavObject = None
			self._pendingLabelAppName = None
			return
		forceChoice = self._pendingForceChoice
		self._pendingForceChoice = False
		if self._labelRuleDialogActive:
			return
		self._labelRuleDialogActive = True
		try:
			nav = self._pendingLabelNavObject or api.getNavigatorObject()
			if not nav:
				ui.message(_("no navigator object available"))
				return

			candidates = _collect_auto_label_candidates(nav)

			controlId = _get_control_id(nav)
			windowHandle = getattr(nav, "windowHandle", 0) or 0
			hasControlId = bool(controlId and controlId != 0 and controlId != windowHandle)

			method = None
			label = None
			chosenMethod = None

			if forceChoice:
				# Doppeltes Drücken: immer vollständiges Menü – Auto-Methoden + manuelle Methoden
				choiceList = [
					_("{method}: {preview}").format(method=c[1], preview=c[2])
					for c in candidates
				]
				if hasControlId:
					choiceList.append(_("D: Manual text (static label)"))
				choiceList.append(_("E: Manual, object-path-based"))
				selected = _show_single_choice_index(
					_("Please choose a labeling method (including manual options):"),
					_("Element label"),
					choiceList,
					parent=None,
				)
				if selected is None or selected < 0:
					return
				if selected < len(candidates):
					method = candidates[selected][0]
					label = candidates[selected][2]
				else:
					manualList = []
					if hasControlId:
						manualList.append("D")
					manualList.append("E")
					chosenMethod = manualList[selected - len(candidates)]
			elif len(candidates) >= 1:
				method = candidates[0][0]
				label = candidates[0][2]

			if not label and chosenMethod is None:
				manualMethods = []
				if hasControlId:
					manualMethods.append(("D", _("D: Manual text (static label)")))
				manualMethods.append(("E", _("E: Manual, object-path-based")))
				if len(manualMethods) > 1:
					selected = _show_single_choice_index(
						_("No automatic label found. Please choose a manual method:"),
						_("Labeling"),
						[item[1] for item in manualMethods],
						parent=None,
					)
					if selected is None or selected < 0:
						ui.message(_("no labeling method was successful"))
						return
					chosenMethod = manualMethods[selected][0]
				else:
					chosenMethod = manualMethods[0][0]

			if chosenMethod is not None:
				if _method_code(chosenMethod) == "D" and hasControlId:
					manualLabel = wx.GetTextFromUser(
						_("Please enter a new label:"),
						_("Labeling"),
						"",
						None,
					)
					if manualLabel and manualLabel.strip():
						method = "D"
						label = manualLabel.strip()
				elif _method_code(chosenMethod) == "E":
					dlg = ObjectPathDialog(None, nav)
					if dlg.ShowModal() == wx.ID_OK:
						path = dlg.get_path()
						if path:
							method = "E"
							label = path
					dlg.Destroy()

			if not label:
				ui.message(_("no labeling method was successful"))
				return

			self.appname = self._pendingLabelAppName
			if not self.appname:
				focus = api.getFocusObject()
				if not focus:
					ui.message(_("no focus object available"))
					return
				self.appname = appModuleHandler.getAppNameFromProcessID(focus.processID, False)
			modulePath = _ensure_user_appmodule(self.appname)
			if not modulePath:
				ui.message(_("could not create or load appmodule"))
				return

			if not _write_choose_overlay_rule(modulePath, nav, label, method):
				ui.message(_("could not save labeling rule"))
				return
			ui.message(_("labeling rule was saved into appModule"))
			wx.CallAfter(self._askOpenAppModule, self.appname)
		finally:
			self._labelRuleDialogActive = False
			self._pendingLabelNavObject = None
			self._pendingLabelAppName = None

	@script(
		description=_("detects and stores a unique highlight marker for the current navigator object"),
		category=_("script manager"),
		gesture="kb:nvda+shift+h"
	)
	def script_setHighlightColor(self, gesture):
		if not self._ensureScratchpadForAction(_("Highlight marker settings are stored in scratchpad appModules.")):
			return
		nav = api.getNavigatorObject()
		if not nav:
			ui.message(_("no navigator object available"))
			return
		uniqueMarker, errorCode = _get_unique_highlight_marker_for_object(nav)
		if not uniqueMarker:
			if errorCode == "noFeatureLines":
				ui.message(_("No text lines with usable formatting features were found"))
			elif errorCode == "noFeatureTokens":
				ui.message(_("No unique formatting features were found in the selected object"))
			elif errorCode == "notUnique":
				ui.message(_("No unique highlight marker line found"))
			else:
				ui.message(_("Could not analyze text formatting for navigator object"))
			return

		appname = None
		processId = getattr(nav, "processID", 0) if nav else 0
		if processId:
			appname = appModuleHandler.getAppNameFromProcessID(processId, False)
		if not appname:
			focusObj = api.getFocusObject()
			processId = getattr(focusObj, "processID", 0) if focusObj else 0
			if processId:
				appname = appModuleHandler.getAppNameFromProcessID(processId, False)
		if not appname:
			ui.message(_("could not determine current application"))
			return

		modulePath = _ensure_user_appmodule(appname)
		if not modulePath:
			ui.message(_("could not create or load appmodule"))
			return

		featureKey = uniqueMarker.get("featureKey")
		featureValue = uniqueMarker.get("featureValue")
		targetLine = uniqueMarker.get("lineText", "")
		self._highlightColorCache[appname] = {
			"featureKey": featureKey,
			"featureValue": featureValue,
			"lineText": targetLine,
		}
		if not _write_highlight_marker_rule(modulePath, nav, uniqueMarker):
			ui.message(_("could not save highlight marker settings"))
			return
		ui.message(
			_("Highlight marker saved for {appname}: {feature} = {value}; current entry: {line}").format(
				appname=appname,
				feature=featureKey,
				value=featureValue,
				line=targetLine or _("unknown"),
			)
		)
		wx.CallAfter(self._askOpenAppModule, appname)

	@script(
		description=_("Scans all graphics in the current foreground window, recognizes them via OneCore OCR and stores labels by control ID"),
		category=_("script manager"),
		gesture="kb:nvda+shift+g"
	)
	def script_autoLabelGraphicsInForegroundWindow(self, gesture):
		if self._graphicLabelingActive:
			ui.message(_("graphic labeling is already running"))
			return
		if not self._ensureScratchpadForAction(_("Graphic label rules are stored in scratchpad appModules.")):
			return

		foreground = api.getForegroundObject()
		if not foreground:
			ui.message(_("no foreground window available"))
			return

		processId = getattr(foreground, "processID", 0) or 0
		if not processId:
			focusObj = api.getFocusObject()
			processId = getattr(focusObj, "processID", 0) if focusObj else 0
		if not processId:
			ui.message(_("could not determine current application"))
			return

		appname = appModuleHandler.getAppNameFromProcessID(processId, False)
		if not appname:
			ui.message(_("could not determine current application"))
			return

		modulePath = _ensure_user_appmodule(appname)
		if not modulePath:
			ui.message(_("could not create or load appmodule"))
			return

		self._graphicLabelingActive = True
		try:
			graphicLabelsByControlId = {}
			for obj in _iter_subtree_objects(foreground):
				if not _is_graphic_object(obj):
					continue
				ocrLabel = _get_onecore_ocr_label(obj)
				if not ocrLabel:
					continue
				controlId = _get_control_id(obj)
				windowHandle = getattr(obj, "windowHandle", 0) or 0
				if not controlId or controlId == windowHandle:
					continue
				graphicLabelsByControlId[controlId] = ocrLabel

			if not _write_graphic_label_overlay_rule(modulePath, graphicLabelsByControlId):
				ui.message(_("could not save graphic labels"))
				return

			ui.message(
				_("{count} graphics labeled").format(count=len(graphicLabelsByControlId))
			)
		finally:
			self._graphicLabelingActive = False


def _normalize_rgb_color_value(colorValue):
	if colorValue is None:
		return None
	if isinstance(colorValue, str):
		return None
	if hasattr(colorValue, "red") and hasattr(colorValue, "green") and hasattr(colorValue, "blue"):
		try:
			return (
				int(colorValue.red),
				int(colorValue.green),
				int(colorValue.blue),
			)
		except Exception:
			return None
	try:
		if len(colorValue) >= 3:
			return (
				int(colorValue[0]),
				int(colorValue[1]),
				int(colorValue[2]),
			)
	except Exception:
		return None
	return None


def _normalize_highlight_feature_value(featureName, featureValue):
	if featureValue is None:
		return None
	if featureName in ("color", "background-color"):
		return _normalize_rgb_color_value(featureValue)
	if isinstance(featureValue, bool):
		return bool(featureValue)
	if isinstance(featureValue, (int, float)):
		return featureValue
	if isinstance(featureValue, str):
		normalized = featureValue.strip()
		return normalized if normalized else None
	if isinstance(featureValue, (tuple, list)):
		normalizedItems = []
		for item in featureValue:
			normalizedItem = _normalize_highlight_feature_value(featureName, item)
			if normalizedItem is None:
				continue
			normalizedItems.append(normalizedItem)
		if not normalizedItems:
			return None
		return tuple(normalizedItems)
	return None


def _extract_highlight_features_from_field(fieldData):
	featureKeys = (
		"color",
		"background-color",
		"bold",
		"italic",
		"underline",
		"strikethrough",
		"invalid-spelling",
		"font-name",
		"font-size",
		"text-position",
	)
	features = {}
	for key in featureKeys:
		if key not in fieldData:
			continue
		normalized = _normalize_highlight_feature_value(key, fieldData.get(key))
		if normalized is None:
			continue
		features[key] = normalized
	foreground = features.get("color")
	background = features.get("background-color")
	if foreground is not None and background is not None:
		features["color-pair"] = (foreground, background)
	return features


def _get_line_feature_data_from_text_info(info):
	try:
		items = list(info.getTextWithFields({}))
	except TypeError:
		items = list(info.getTextWithFields())
	except Exception:
		return None

	currentFeatures = {}
	lineHasText = False
	lineFeatures = set()
	lineTextParts = []
	perLineFeatureData = []

	def _flush_line():
		nonlocal lineHasText, lineFeatures, lineTextParts
		if not lineHasText:
			lineFeatures = set()
			lineTextParts = []
			return
		lineText = "".join(lineTextParts).strip()
		if lineText:
			perLineFeatureData.append({
				"text": lineText,
				"features": set(lineFeatures),
			})
		lineHasText = False
		lineFeatures = set()
		lineTextParts = []

	for item in items:
		if isinstance(item, textInfos.FieldCommand):
			if item.command != "formatChange":
				continue
			fieldData = getattr(item, "field", None)
			if not fieldData:
				continue
			for featureKey, featureValue in _extract_highlight_features_from_field(fieldData).items():
				currentFeatures[featureKey] = featureValue
			continue

		if not isinstance(item, str) or not item:
			continue

		for chunk in item.splitlines(True):
			textPart = chunk.rstrip("\r\n")
			if textPart:
				lineHasText = True
				lineTextParts.append(textPart)
				for featureKey, featureValue in currentFeatures.items():
					lineFeatures.add((featureKey, featureValue))
			if chunk.endswith("\n") or chunk.endswith("\r"):
				_flush_line()

	_flush_line()
	return perLineFeatureData


def _get_unique_highlight_marker_for_object(navObj):
	try:
		info = navObj.makeTextInfo(textInfos.POSITION_ALL)
	except Exception:
		return None, "textInfoUnavailable"

	lineFeatureData = _get_line_feature_data_from_text_info(info)
	if lineFeatureData is None:
		return None, "textInfoUnavailable"

	if not lineFeatureData:
		return None, "noFeatureLines"

	featureCounts = {}
	featureLastLineIndex = {}
	for lineIndex, lineData in enumerate(lineFeatureData):
		features = lineData.get("features", set())
		for token in features:
			featureCounts[token] = featureCounts.get(token, 0) + 1
			featureLastLineIndex[token] = lineIndex

	if not featureCounts:
		return None, "noFeatureTokens"

	uniqueTokens = [token for token, count in featureCounts.items() if count == 1]
	if not uniqueTokens:
		return None, "notUnique"

	featurePriority = {
		"color-pair": 0,
		"background-color": 1,
		"color": 2,
		"bold": 3,
		"underline": 4,
		"italic": 5,
		"strikethrough": 6,
		"font-size": 7,
		"font-name": 8,
		"text-position": 9,
		"invalid-spelling": 10,
	}

	def _token_sort_key(token):
		featureKey = token[0]
		return (
			featurePriority.get(featureKey, 100),
			len(repr(token[1])),
		)

	selectedToken = sorted(uniqueTokens, key=_token_sort_key)[0]
	selectedLineIndex = featureLastLineIndex[selectedToken]
	selectedLineText = lineFeatureData[selectedLineIndex].get("text", "")

	return {
		"featureKey": selectedToken[0],
		"featureValue": selectedToken[1],
		"lineText": selectedLineText,
		"lineIndex": selectedLineIndex,
	}, None


def _ensure_user_appmodule(appname):
	if not appname:
		return None
	if not appModuleHandler.doesAppModuleExist(appname):
		try:
			sm_backend.createnewmodule('appModule', appname, True)
		except Exception:
			return None
		return _user_appmodule_exists(appname)

	path = _user_appmodule_exists(appname)
	if path:
		return path

	addon = _find_addon_appmodule_provider(appname)
	if addon:
		try:
			_copy_addon_appmodule_to_scratchpad(addon=addon, appname=appname)
		except Exception:
			return None
		return _user_appmodule_exists(appname)

	return None


def _get_label_method_settings_path():
	config_dir = os.path.dirname(sm_backend.get_scratchpad_dir(ensure_exists=True, ensure_subdirs=True))
	return os.path.join(config_dir, LABEL_METHOD_SETTINGS_FILENAME)


def _normalize_label_method_order(order):
	allowed_codes = [code for code, _label in AUTO_LABEL_METHODS]
	normalized = []
	for method_code in order or []:
		method_code = _method_code(method_code)
		if method_code in allowed_codes and method_code not in normalized:
			normalized.append(method_code)
	for method_code in allowed_codes:
		if method_code not in normalized:
			normalized.append(method_code)
	return normalized


def _normalize_enabled_label_methods(enabled, order):
	allowed_codes = set(order)
	normalized = []
	for method_code in enabled or []:
		method_code = _method_code(method_code)
		if method_code in allowed_codes and method_code not in normalized:
			normalized.append(method_code)
	return [method_code for method_code in order if method_code in normalized]


def _load_label_method_settings():
	default_order = list(DEFAULT_AUTO_LABEL_METHOD_ORDER)
	default_settings = {
		"order": default_order,
		"enabled": list(default_order),
	}
	try:
		with open(_get_label_method_settings_path(), "r", encoding="utf-8") as settings_file:
			loaded = json.load(settings_file)
	except Exception:
		return default_settings
	order = _normalize_label_method_order(loaded.get("order", default_order))
	enabled = _normalize_enabled_label_methods(loaded.get("enabled", default_order), order)
	return {
		"order": order,
		"enabled": enabled,
	}


def _save_label_method_settings(settings):
	order = _normalize_label_method_order(settings.get("order", DEFAULT_AUTO_LABEL_METHOD_ORDER))
	enabled = _normalize_enabled_label_methods(settings.get("enabled", DEFAULT_AUTO_LABEL_METHOD_ORDER), order)
	with open(_get_label_method_settings_path(), "w", encoding="utf-8") as settings_file:
		json.dump({"order": order, "enabled": enabled}, settings_file, indent=2)


def _get_auto_label_method_label(method_code):
	for code, label in AUTO_LABEL_METHODS:
		if code == _method_code(method_code):
			return label
	return str(method_code)


def _get_auto_label_value(nav, method_code):
	method_code = _method_code(method_code)
	if method_code == "A":
		return _collect_txt_children_label(nav)
	if method_code == "B":
		return _get_onecore_ocr_label(nav)
	if method_code == "C":
		return _get_automation_id(nav)
	if method_code == "D":
		return _get_hover_tooltip_label(nav)
	return ""


def _collect_auto_label_candidates(nav):
	settings = _load_label_method_settings()
	candidates = []
	for method_code in settings["enabled"]:
		label_value = _get_auto_label_value(nav, method_code)
		if label_value:
			candidates.append((method_code, _get_auto_label_method_label(method_code), label_value))
	return candidates


def _collect_txt_children_label(obj):
	parts = []
	for child in getattr(obj, "children", []):
		childName = getattr(child, "name", "")
		roleName = str(getattr(getattr(child, "role", None), "name", "") or "").upper()
		if childName and roleName == "STATICTEXT":
			parts.append(childName)
	return "; ".join(parts).strip()


def _get_onecore_ocr_label(obj):
	try:
		left, top, width, height = obj.location
	except Exception:
		return ""

	if not width or not height:
		return ""

	try:
		import screenBitmap
		from contentRecog import RecogImageInfo
		from contentRecog.uwpOcr import UwpOcr

		recognizer = UwpOcr()
		if not recognizer.validateObject(obj):
			return ""
		if not recognizer.validateCaptureBounds(obj.location):
			return ""
		imgInfo = RecogImageInfo.createFromRecognizer(left, top, width, height, recognizer)
	except Exception:
		return ""

	resultBox = {"text": ""}
	done = threading.Event()

	def _onResult(result):
		try:
			if isinstance(result, Exception):
				return
			text = getattr(result, "text", "")
			if isinstance(text, str) and text.strip():
				resultBox["text"] = text.strip().replace("\n", " ")
		finally:
			done.set()

	try:
		sb = screenBitmap.ScreenBitmap(imgInfo.recogWidth, imgInfo.recogHeight)
		pixels = sb.captureImage(imgInfo.screenLeft, imgInfo.screenTop, imgInfo.screenWidth, imgInfo.screenHeight)
		recognizer.recognize(pixels, imgInfo, _onResult)
		done.wait(2.0)
		recognizer.cancel()
	except Exception:
		return ""

	return (resultBox.get("text") or "").strip()


def _get_automation_id(obj):
	for attr in ("UIAAutomationId", "uiaAutomationId", "automationId"):
		value = getattr(obj, attr, None)
		if value is None:
			continue
		value = str(value).strip()
		if value:
			return value
	return ""


def _get_hover_tooltip_label(obj):
	"""Extract tooltip text from UI Automation or NVDA object properties."""
	try:
		# Try to get tooltip from various NVDA object attributes
		tooltip = getattr(obj, "tooltip", None)
		if isinstance(tooltip, str) and tooltip.strip():
			return tooltip.strip()
		
		# Try to get description or help text
		description = getattr(obj, "description", None)
		if isinstance(description, str) and description.strip():
			return description.strip()
		
		# Try UIAElement for HelpText property
		try:
			from NVDAObjects.UIA import UIA
			if isinstance(obj, UIA):
				uiaElement = getattr(obj, "UIAElement", None)
				if uiaElement:
					try:
						helpText = uiaElement.GetCurrentPropertyValue(30088)  # UIA_HelpTextPropertyId = 30088
						if helpText and isinstance(helpText, str):
							return helpText.strip()
					except Exception:
						pass
		except ImportError:
			pass
		
		# Try to get from IAccessible interface (older COM-based accessibility)
		try:
			iaccessible = getattr(obj, "IAccessible", None)
			if iaccessible:
				tooltip = iaccessible.accHelp
				if tooltip and isinstance(tooltip, str):
					return tooltip.strip()
		except Exception:
			pass
		
		return ""
	except Exception:
		return ""


def _get_control_id(obj):
	for attr in ("windowControlID", "controlId"):
		value = getattr(obj, attr, None)
		if value is None:
			continue
		try:
			return int(value)
		except Exception:
			continue
	return 0


def _is_graphic_object(obj):
	role = getattr(obj, "role", None)
	roleName = str(getattr(role, "name", "") or "").upper()
	if roleName == "GRAPHIC":
		return True
	try:
		return role == getattr(controlTypes.Role, "GRAPHIC", None)
	except Exception:
		return False


def _iter_subtree_objects(root, maxObjects=6000):
	if not root:
		return
	stack = [root]
	seen = set()
	count = 0
	while stack and count < maxObjects:
		obj = stack.pop()
		if obj is None:
			continue
		objId = id(obj)
		if objId in seen:
			continue
		seen.add(objId)
		yield obj
		count += 1
		children = []
		try:
			child = getattr(obj, "firstChild", None)
			while child is not None:
				children.append(child)
				child = getattr(child, "next", None)
		except Exception:
			children = []
		if children:
			stack.extend(reversed(children))


def _write_graphic_label_overlay_rule(modulePath, labelsByControlId):
	content = None
	moduleEncoding = None

	try:
		with tokenize.open(modulePath) as f:
			content = f.read()
			moduleEncoding = getattr(f, "encoding", None)
	except Exception:
		for fallbackEncoding in ("utf-8", "utf-8-sig", "mbcs", "cp1252", "latin-1"):
			try:
				with open(modulePath, "r", encoding=fallbackEncoding) as f:
					content = f.read()
				moduleEncoding = fallbackEncoding
				break
			except Exception:
				continue

	if content is None:
		return False

	if "import appModuleHandler" not in content:
		content = "import appModuleHandler\n" + content

	if "class AppModule(" not in content:
		content += "\n\nclass AppModule(appModuleHandler.AppModule):\n\tpass\n"

	startMarker = "# ScriptManagerGraphicLabelerStart"
	endMarker = "# ScriptManagerGraphicLabelerEnd"
	pattern = r"\n?%s.*?%s\n?" % (re.escape(startMarker), re.escape(endMarker))
	content = re.sub(pattern, "\n", content, flags=re.S)

	orderedItems = ", ".join([
		"{key}: {value!r}".format(key=key, value=labelsByControlId[key])
		for key in sorted(labelsByControlId)
	])

	rule = [
		"",
		startMarker,
		"class ScriptManagerGraphicLabelOverlay(object):",
		"\tdef _get_name(self):",
		"\t\tcontrolId = getattr(self, 'windowControlID', 0) or getattr(self, 'controlId', 0) or getattr(self, 'controlid', 0)",
		"\t\tif not controlId:",
		"\t\t\treturn super(ScriptManagerGraphicLabelOverlay, self).name",
		"\t\ttry:",
		"\t\t\tappmodule = getattr(self, 'appmodule', None) or getattr(self, 'appModule', None)",
		"\t\t\treturn appmodule.graphiclabels[controlId]",
		"\t\texcept Exception:",
		"\t\t\treturn super(ScriptManagerGraphicLabelOverlay, self).name",
		"",
		"class AppModule(AppModule):",
		"\tgraphiclabels = {{{items}}}".format(items=orderedItems),
		"\tdef chooseNVDAObjectOverlayClasses(self, obj, clsList):",
		"\t\tsuper().chooseNVDAObjectOverlayClasses(obj, clsList)",
		"\t\troleName = str(getattr(getattr(obj, 'role', None), 'name', '') or '').upper()",
		"\t\tif roleName == 'GRAPHIC':",
		"\t\t\tclsList.insert(0, ScriptManagerGraphicLabelOverlay)",
		"",
		endMarker,
		"",
	]

	content = content.rstrip() + "\n" + "\n".join(rule)

	writeEncodings = []
	if moduleEncoding:
		writeEncodings.append(moduleEncoding)
	for fallbackEncoding in ("utf-8", "utf-8-sig", "mbcs", "cp1252", "latin-1"):
		if fallbackEncoding not in writeEncodings:
			writeEncodings.append(fallbackEncoding)

	for currentEncoding in writeEncodings:
		try:
			with open(modulePath, "w", encoding=currentEncoding) as f:
				f.write(content)
			return True
		except Exception:
			continue
	return False


def _sanitize_identifier(value, default="generated"):
	value = re.sub(r"[^0-9a-zA-Z_]", "_", str(value or "")).strip("_")
	if not value:
		value = default
	if not value:
		return ""
	if value[0].isdigit():
		value = "_" + value
	if keyword.iskeyword(value):
		value = value + "_"
	return value


def _get_role_pattern_data(obj):
	role = getattr(obj, "role", None)
	roleName = getattr(role, "name", "") or ""
	roleToken = _sanitize_identifier(str(roleName).lower() or str(role).lower(), "object")
	roleMember = _sanitize_identifier(str(roleName).upper(), "")
	if roleMember:
		roleExpression = "controlTypes.Role.{member}".format(member=roleMember)
	else:
		roleExpression = repr(role)
	return roleToken, roleExpression


def _get_overlay_base_class_data(obj):
	for cls in getattr(obj.__class__, "__mro__", ()):
		moduleName = getattr(cls, "__module__", "")
		className = getattr(cls, "__name__", "")
		if moduleName.startswith("NVDAObjects") and className:
			return (
				"from {moduleName} import {className}".format(moduleName=moduleName, className=className),
				className,
			)
	moduleName = getattr(obj.__class__, "__module__", "")
	className = getattr(obj.__class__, "__name__", "")
	if moduleName and moduleName != "builtins" and className:
		return (
			"from {moduleName} import {className}".format(moduleName=moduleName, className=className),
			className,
		)
	return ("", "object")


def _build_get_name_lines(method, label, className, labelsDictName):
	if _method_code(method) == "D":
		return [
			"\tdef _get_name(self):",
			"\t\tcontrolId = getattr(self, 'windowControlID', 0) or getattr(self, 'controlId', 0)",
			"\t\treturn self.appmodule.{labelsDict}.get(controlId, super({className}, self).name)".format(
				labelsDict=labelsDictName,
				className=className,
			),
		]

	if _method_code(method) == "A":
		return [
			"\tdef _get_name(self):",
			"\t\treturn '; '.join([x.name for x in self.children if x.role == controlTypes.ROLE_STATICTEXT and x.name])",
		]

	if _method_code(method) == "B":
		return [
			"\tdef _get_name(self):",
			"\t\tname = super({className}, self).name".format(className=className),
			"\t\tclassName = getattr(self, 'windowClassName', '') or getattr(self, 'className', '')",
			"\t\tif name and name != className:",
			"\t\t\treturn name",
			"\t\ttry:",
			"\t\t\tleft, top, width, height = self.location",
			"\t\texcept Exception:",
			"\t\t\treturn name or ''",
			"\t\tif not width or not height:",
			"\t\t\treturn name or ''",
			"\t\ttry:",
			"\t\t\timport screenBitmap",
			"\t\t\tfrom contentRecog import RecogImageInfo",
			"\t\t\tfrom contentRecog.uwpOcr import UwpOcr",
			"\t\t\trecognizer = UwpOcr()",
			"\t\t\tif not recognizer.validateObject(self):",
			"\t\t\t\treturn name or ''",
			"\t\t\tif not recognizer.validateCaptureBounds(self.location):",
			"\t\t\t\treturn name or ''",
			"\t\t\timgInfo = RecogImageInfo.createFromRecognizer(left, top, width, height, recognizer)",
			"\t\texcept Exception:",
			"\t\t\treturn name or ''",
			"\t\tresultBox = {'text': ''}",
			"\t\t_done = threading.Event()",
			"\t\tdef _onResult(result):",
			"\t\t\ttry:",
			"\t\t\t\tif isinstance(result, Exception):",
			"\t\t\t\t\treturn",
			"\t\t\t\ttext = getattr(result, 'text', '')",
			"\t\t\t\tif isinstance(text, str) and text.strip():",
			"\t\t\t\t\tresultBox['text'] = text.strip().replace('\\n', ' ')",
			"\t\t\tfinally:",
			"\t\t\t\t_done.set()",
			"\t\ttry:",
			"\t\t\tsb = screenBitmap.ScreenBitmap(imgInfo.recogWidth, imgInfo.recogHeight)",
			"\t\t\tpixels = sb.captureImage(imgInfo.screenLeft, imgInfo.screenTop, imgInfo.screenWidth, imgInfo.screenHeight)",
			"\t\t\trecognizer.recognize(pixels, imgInfo, _onResult)",
			"\t\t\t_done.wait(2.0)",
			"\t\t\trecognizer.cancel()",
			"\t\texcept Exception:",
			"\t\t\treturn name or ''",
			"\t\treturn (resultBox.get('text') or '').strip() or (name or '')",
		]

	if _method_code(method) == "E":
		# label contains the dot-separated navigation path, e.g. "previous.previous"
		steps = [s.strip() for s in label.split(".") if s.strip()]
		lines = [
			"\tdef _get_name(self):",
			"\t\ttry:",
			"\t\t\t_obj = self",
		]
		for step in steps:
			lines.append("\t\t\t_obj = getattr(_obj, {step!r}, None)".format(step=step))
			lines.append("\t\t\tif _obj is None: return super({className}, self).name or ''".format(className=className))
		lines += [
			"\t\t\treturn getattr(_obj, 'name', None) or ''",
			"\t\texcept Exception:",
			"\t\t\treturn super({className}, self).name or ''".format(className=className),
		]
		return lines

	return [
		"\tdef _get_name(self):",
		"\t\tname = super({className}, self).name".format(className=className),
		"\t\tif name:",
		"\t\t\treturn name",
		"\t\treturn str(getattr(self, 'UIAAutomationId', '') or getattr(self, 'uiaAutomationId', '') or getattr(self, 'automationId', '') or '')",
	]


def _write_choose_overlay_rule(modulePath, navObj, label, method):
	content = None
	moduleEncoding = None

	try:
		with tokenize.open(modulePath) as f:
			content = f.read()
			moduleEncoding = getattr(f, "encoding", None)
	except Exception:
		for fallbackEncoding in ("utf-8", "utf-8-sig", "mbcs", "cp1252", "latin-1"):
			try:
				with open(modulePath, "r", encoding=fallbackEncoding) as f:
					content = f.read()
				moduleEncoding = fallbackEncoding
				break
			except Exception:
				continue

	if content is None:
		return False

	if "import appModuleHandler" not in content:
		content = "import appModuleHandler\n" + content

	if "class AppModule(" not in content:
		content += "\n\nclass AppModule(appModuleHandler.AppModule):\n\tpass\n"

	appname = os.path.splitext(os.path.basename(modulePath))[0]
	roleToken, roleExpression = _get_role_pattern_data(navObj)
	importLine, overlayBaseClass = _get_overlay_base_class_data(navObj)
	overlayClassName = _sanitize_identifier("{app}_{role}".format(app=appname, role=roleToken), "generated_overlay")
	labelsDictName = _sanitize_identifier("{app}_labels".format(app=appname), "scriptmanager_labels")
	getNameLines = _build_get_name_lines(method, label, overlayClassName, labelsDictName)
	startMarker = "# ScriptManagerLabelRuleStart:{overlayClass}".format(overlayClass=overlayClassName)
	endMarker = "# ScriptManagerLabelRuleEnd:{overlayClass}".format(overlayClass=overlayClassName)
	legacyPattern = r"\n?# ScriptManagerLabelRuleStart\n.*?# ScriptManagerLabelRuleEnd\n?"
	content = re.sub(legacyPattern, "\n", content, flags=re.S)
	pattern = r"\n?%s.*?%s\n?" % (re.escape(startMarker), re.escape(endMarker))
	existingBlockMatch = re.search(pattern, content, flags=re.S)
	controlId = _get_control_id(navObj)
	manualDictLine = ""
	if _method_code(method) == "D" and controlId:
		labelDict = {}
		if existingBlockMatch:
			dictMatch = re.search(r"\b{dictName}\s*=\s*(\{{.*?\}})".format(dictName=re.escape(labelsDictName)), existingBlockMatch.group(0), flags=re.S)
			if dictMatch:
				try:
					loaded = ast.literal_eval(dictMatch.group(1))
					if isinstance(loaded, dict):
						labelDict = loaded
				except Exception:
					labelDict = {}
		labelDict[controlId] = label
		orderedItems = ", ".join(["{key}: {value!r}".format(key=key, value=labelDict[key]) for key in sorted(labelDict)])
		manualDictLine = "\t{labelsDict} = {{{items}}}".format(labelsDict=labelsDictName, items=orderedItems)

	content = re.sub(pattern, "\n", content, flags=re.S)

	rule = [
		"",
		startMarker,
		"# ScriptManagerLabelRuleMethod: {method}".format(method=method),
	]
	if _method_code(method) == "B" and "import threading" not in content:
		rule.append("import threading")
	if importLine and importLine not in content:
		rule.append(importLine)
	rule += [
		"class {overlayClass}({overlayBaseClass}):".format(
			overlayClass=overlayClassName,
			overlayBaseClass=overlayBaseClass,
		),
	]
	rule += getNameLines
	rule += [
		"",
		"class AppModule(AppModule):",
	]
	if manualDictLine:
		rule.append(manualDictLine)
	rule += [
		"\tdef chooseNVDAObjectOverlayClasses(self, obj, clsList):",
		"\t\tsuper().chooseNVDAObjectOverlayClasses(obj, clsList)",
		"\t\tif obj.role == {roleExpression}:".format(roleExpression=roleExpression),
		"\t\t\tclsList.insert(0, {overlayClass})".format(overlayClass=overlayClassName),
		"",
		endMarker,
		"",
	]

	content = content.rstrip() + "\n" + "\n".join(rule)

	writeEncodings = []
	if moduleEncoding:
		writeEncodings.append(moduleEncoding)
	for fallbackEncoding in ("utf-8", "utf-8-sig", "mbcs", "cp1252", "latin-1"):
		if fallbackEncoding not in writeEncodings:
			writeEncodings.append(fallbackEncoding)

	for currentEncoding in writeEncodings:
		try:
			with open(modulePath, "w", encoding=currentEncoding) as f:
				f.write(content)
			return True
		except Exception:
			continue
	return False


def _write_highlight_marker_rule(modulePath, navObj, markerData):
	content = None
	moduleEncoding = None

	try:
		with tokenize.open(modulePath) as f:
			content = f.read()
			moduleEncoding = getattr(f, "encoding", None)
	except Exception:
		for fallbackEncoding in ("utf-8", "utf-8-sig", "mbcs", "cp1252", "latin-1"):
			try:
				with open(modulePath, "r", encoding=fallbackEncoding) as f:
					content = f.read()
				moduleEncoding = fallbackEncoding
				break
			except Exception:
				continue

	if content is None:
		return False

	for requiredImport in (
		"import appModuleHandler",
		"import api",
		"import ui",
		"import wx",
		"import textInfos",
		"from scriptHandler import script",
	):
		if requiredImport not in content:
			content = requiredImport + "\n" + content

	if "class AppModule(" not in content:
		content += "\n\nclass AppModule(appModuleHandler.AppModule):\n\tpass\n"

	startMarker = "# ScriptManagerHighlightColorStart"
	endMarker = "# ScriptManagerHighlightColorEnd"
	pattern = r"\n?%s.*?%s\n?" % (re.escape(startMarker), re.escape(endMarker))
	content = re.sub(pattern, "\n", content, flags=re.S)

	featureKey = markerData.get("featureKey")
	featureValue = markerData.get("featureValue")
	roleText = str(getattr(navObj, "role", "") or "")
	windowClassName = str(getattr(navObj, "windowClassName", "") or getattr(navObj, "className", "") or "")
	controlId = _get_control_id(navObj)

	rule = [
		"",
		startMarker,
		"class AppModule(AppModule):",
		"\tscriptManagerHighlightFeatureKey = {featureKey!r}".format(featureKey=featureKey),
		"\tscriptManagerHighlightFeatureValue = {featureValue!r}".format(featureValue=featureValue),
		"\tscriptManagerHighlightRoleText = {roleText!r}".format(roleText=roleText),
		"\tscriptManagerHighlightWindowClassName = {windowClass!r}".format(windowClass=windowClassName),
		"\tscriptManagerHighlightControlId = {controlId!r}".format(controlId=controlId),
		"\t_scriptManagerLastSpokenLine = ''",
		"\tdef _scriptManagerNormalizeColor(self, colorValue):",
		"\t\tif colorValue is None:",
		"\t\t\treturn None",
		"\t\tif hasattr(colorValue, 'red') and hasattr(colorValue, 'green') and hasattr(colorValue, 'blue'):",
		"\t\t\ttry:",
		"\t\t\t\treturn (int(colorValue.red), int(colorValue.green), int(colorValue.blue))",
		"\t\t\texcept Exception:",
		"\t\t\t\treturn None",
		"\t\tif isinstance(colorValue, (tuple, list)) and len(colorValue) >= 3:",
		"\t\t\ttry:",
		"\t\t\t\treturn (int(colorValue[0]), int(colorValue[1]), int(colorValue[2]))",
		"\t\t\texcept Exception:",
		"\t\t\t\treturn None",
		"\t\treturn None",
		"\tdef _scriptManagerNormalizeFeatureValue(self, featureKey, featureValue):",
		"\t\tif featureValue is None:",
		"\t\t\treturn None",
		"\t\tif featureKey in ('color', 'background-color'):",
		"\t\t\treturn self._scriptManagerNormalizeColor(featureValue)",
		"\t\tif featureKey == 'color-pair' and isinstance(featureValue, (tuple, list)) and len(featureValue) >= 2:",
		"\t\t\tfirst = self._scriptManagerNormalizeColor(featureValue[0])",
		"\t\t\tsecond = self._scriptManagerNormalizeColor(featureValue[1])",
		"\t\t\tif first is None or second is None:",
		"\t\t\t\treturn None",
		"\t\t\treturn (first, second)",
		"\t\tif isinstance(featureValue, bool):",
		"\t\t\treturn bool(featureValue)",
		"\t\tif isinstance(featureValue, (int, float)):",
		"\t\t\treturn featureValue",
		"\t\tif isinstance(featureValue, str):",
		"\t\t\tfeatureValue = featureValue.strip()",
		"\t\t\treturn featureValue if featureValue else None",
		"\t\treturn None",
		"\tdef scriptManagerObjectMatchesHighlightTarget(self, obj):",
		"\t\tif obj is None:",
		"\t\t\treturn False",
		"\t\tif self.scriptManagerHighlightRoleText:",
		"\t\t\tif str(getattr(obj, 'role', '') or '') != self.scriptManagerHighlightRoleText:",
		"\t\t\t\treturn False",
		"\t\tif self.scriptManagerHighlightWindowClassName:",
		"\t\t\tobjClass = str(getattr(obj, 'windowClassName', '') or getattr(obj, 'className', '') or '')",
		"\t\t\tif objClass != self.scriptManagerHighlightWindowClassName:",
		"\t\t\t\treturn False",
		"\t\tif self.scriptManagerHighlightControlId:",
		"\t\t\tobjControlId = getattr(obj, 'windowControlID', 0) or getattr(obj, 'controlId', 0)",
		"\t\t\ttry:",
		"\t\t\t\tobjControlId = int(objControlId)",
		"\t\t\texcept Exception:",
		"\t\t\t\tobjControlId = 0",
		"\t\t\tif objControlId != self.scriptManagerHighlightControlId:",
		"\t\t\t\treturn False",
		"\t\treturn True",
		"\tdef scriptManagerFindHighlightedLine(self, obj):",
		"\t\tif not self.scriptManagerObjectMatchesHighlightTarget(obj):",
		"\t\t\treturn ''",
		"\t\ttry:",
		"\t\t\tinfo = obj.makeTextInfo(textInfos.POSITION_ALL)",
		"\t\texcept Exception:",
		"\t\t\treturn ''",
		"\t\ttry:",
		"\t\t\titems = list(info.getTextWithFields({}))",
		"\t\texcept TypeError:",
		"\t\t\ttry:",
		"\t\t\t\titems = list(info.getTextWithFields())",
		"\t\t\texcept Exception:",
		"\t\t\t\treturn ''",
		"\t\texcept Exception:",
		"\t\t\treturn ''",
		"\t\tcurrentFeatures = {}",
		"\t\tlineTextParts = []",
		"\t\tlineHasMarker = False",
		"\t\ttargetKey = self.scriptManagerHighlightFeatureKey",
		"\t\ttargetValue = self._scriptManagerNormalizeFeatureValue(targetKey, self.scriptManagerHighlightFeatureValue)",
		"\t\tif targetValue is None:",
		"\t\t\treturn ''",
		"\t\tdef _flush_line():",
		"\t\t\tnonlocal lineTextParts, lineHasMarker",
		"\t\t\tlineText = ''.join(lineTextParts).strip()",
		"\t\t\tlineTextParts = []",
		"\t\t\tif lineHasMarker and lineText:",
		"\t\t\t\treturn lineText",
		"\t\t\tlineHasMarker = False",
		"\t\t\treturn ''",
		"\t\tfor item in items:",
		"\t\t\tif isinstance(item, textInfos.FieldCommand):",
		"\t\t\t\tif item.command != 'formatChange':",
		"\t\t\t\t\tcontinue",
		"\t\t\t\tfieldData = getattr(item, 'field', None)",
		"\t\t\t\tif not fieldData:",
		"\t\t\t\t\tcontinue",
		"\t\t\t\tfor key in ('color', 'background-color', 'bold', 'italic', 'underline', 'strikethrough', 'invalid-spelling', 'font-name', 'font-size', 'text-position'):",
		"\t\t\t\t\tif key not in fieldData:",
		"\t\t\t\t\t\tcontinue",
		"\t\t\t\t\tnormalized = self._scriptManagerNormalizeFeatureValue(key, fieldData.get(key))",
		"\t\t\t\t\tif normalized is None:",
		"\t\t\t\t\t\tcontinue",
		"\t\t\t\t\tcurrentFeatures[key] = normalized",
		"\t\t\t\tif 'color' in currentFeatures and 'background-color' in currentFeatures:",
		"\t\t\t\t\tcurrentFeatures['color-pair'] = (currentFeatures['color'], currentFeatures['background-color'])",
		"\t\t\t\tcontinue",
		"\t\t\tif not isinstance(item, str) or not item:",
		"\t\t\t\tcontinue",
		"\t\t\tfor chunk in item.splitlines(True):",
		"\t\t\t\ttextPart = chunk.rstrip('\\r\\n')",
		"\t\t\t\tif textPart:",
		"\t\t\t\t\tlineTextParts.append(textPart)",
		"\t\t\t\t\tif targetKey in currentFeatures and currentFeatures[targetKey] == targetValue:",
		"\t\t\t\t\t\tlineHasMarker = True",
		"\t\t\t\tif chunk.endswith('\\n') or chunk.endswith('\\r'):",
		"\t\t\t\t\tline = _flush_line()",
		"\t\t\t\t\tif line:",
		"\t\t\t\t\t\treturn line",
		"\t\tline = _flush_line()",
		"\t\tif line:",
		"\t\t\treturn line",
		"\t\treturn ''",
		"\tdef scriptManagerMaybeSpeakHighlightedLine(self, obj):",
		"\t\tline = self.scriptManagerFindHighlightedLine(obj)",
		"\t\tif not line:",
		"\t\t\treturn",
		"\t\tif line == self._scriptManagerLastSpokenLine:",
		"\t\t\treturn",
		"\t\tself._scriptManagerLastSpokenLine = line",
		"\t\tui.message(line)",
		"\tdef _scriptManagerHandleArrow(self, gesture):",
		"\t\tgesture.send()",
		"\t\tfocus = api.getFocusObject()",
		"\t\tif not self.scriptManagerObjectMatchesHighlightTarget(focus):",
		"\t\t\treturn",
		"\t\twx.CallLater(30, self.scriptManagerMaybeSpeakHighlightedLine, focus)",
		"\t@script(gesture='kb:upArrow')",
		"\tdef script_scriptManagerUpArrow(self, gesture):",
		"\t\tself._scriptManagerHandleArrow(gesture)",
		"\t@script(gesture='kb:downArrow')",
		"\tdef script_scriptManagerDownArrow(self, gesture):",
		"\t\tself._scriptManagerHandleArrow(gesture)",
		"\t@script(gesture='kb:pageUp')",
		"\tdef script_scriptManagerPageUp(self, gesture):",
		"\t\tself._scriptManagerHandleArrow(gesture)",
		"\t@script(gesture='kb:pageDown')",
		"\tdef script_scriptManagerPageDown(self, gesture):",
		"\t\tself._scriptManagerHandleArrow(gesture)",
		"\t@script(gesture='kb:home')",
		"\tdef script_scriptManagerHome(self, gesture):",
		"\t\tself._scriptManagerHandleArrow(gesture)",
		"\t@script(gesture='kb:end')",
		"\tdef script_scriptManagerEnd(self, gesture):",
		"\t\tself._scriptManagerHandleArrow(gesture)",
		"\tdef event_valueChange(self, obj, nextHandler):",
		"\t\tnextHandler()",
		"\t\tif self.scriptManagerObjectMatchesHighlightTarget(obj):",
		"\t\t\twx.CallLater(30, self.scriptManagerMaybeSpeakHighlightedLine, obj)",
		"\tdef event_gainFocus(self, obj, nextHandler):",
		"\t\tnextHandler()",
		"\t\tif self.scriptManagerObjectMatchesHighlightTarget(obj):",
		"\t\t\twx.CallLater(30, self.scriptManagerMaybeSpeakHighlightedLine, obj)",
		endMarker,
		"",
	]

	content = content.rstrip() + "\n" + "\n".join(rule)

	writeEncodings = []
	if moduleEncoding:
		writeEncodings.append(moduleEncoding)
	for fallbackEncoding in ("utf-8", "utf-8-sig", "mbcs", "cp1252", "latin-1"):
		if fallbackEncoding not in writeEncodings:
			writeEncodings.append(fallbackEncoding)

	for currentEncoding in writeEncodings:
		try:
			with open(modulePath, "w", encoding=currentEncoding) as f:
				f.write(content)
			return True
		except Exception:
			continue
	return False
