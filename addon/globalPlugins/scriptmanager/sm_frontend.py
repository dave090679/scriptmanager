import datetime
import sys
import os
import shutil
import threading
import time
impPath = os.path.abspath(os.path.dirname(__file__))
sys.path.append(impPath)
import sm_backend
import ui
import gui
import wx
import inspect
import addonHandler
import addonAPIVersion
import re
from gui import guiHelper
addonHandler.initTranslation()


class insertfunctionsdialog(wx.Dialog):
    functionstring = ""

    def __init__(self, parent, id, title, includeBlacklistedModules=False, translateDocstrings=False):
        super(insertfunctionsdialog, self).__init__(parent, id, title)
        self.tree_initialized = False
        self.dialog_closed = False
        self.includeBlacklistedModules = bool(includeBlacklistedModules)
        self.translateDocstrings = bool(translateDocstrings)
        self._doc_translation_cache = {}

        # Blacklist certain modules that cause problems
        self.blacklist = {
            "ctypes",
            "ctypes.wintypes",
            "pythoncom",
            "pywintypes",
            "win32api",
            "win32con",
            "comtypes",
            "numpy",
            "pandas",
        }

        # Marker for loaded nodes
        self.loaded_nodes = set()

        mainSizer = wx.BoxSizer(wx.VERTICAL)
        sHelper = guiHelper.BoxSizerHelper(self, wx.VERTICAL)

        self.tree = wx.TreeCtrl(self, style=wx.TR_SINGLE | wx.TR_NO_BUTTONS)
        sHelper.addItem(self.tree, flag=wx.EXPAND, proportion=1)
        rootnode = self.tree.AddRoot(text="root")
        self.rootnode = rootnode
        # Create a placeholder child for root so it's expandable
        placeholder = self.tree.AppendItem(parent=self.rootnode, text="[Loading modules...]")
        self.tree.SetItemData(placeholder, "placeholder")

        self.help_text = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP)
        sHelper.addItem(self.help_text, flag=wx.EXPAND, proportion=1)

        sHelper.addDialogDismissButtons(wx.OK | wx.CANCEL, separated=True)
        mainSizer.Add(sHelper.sizer, border=guiHelper.BORDER_FOR_DIALOGS, flag=wx.ALL)
        mainSizer.Fit(self)
        self.SetSizer(mainSizer)
        self.SetAffirmativeId(wx.ID_OK)
        self.Bind(wx.EVT_BUTTON, self.onOk, id=wx.ID_OK)
        self.Bind(wx.EVT_BUTTON, self.onCancel, id=wx.ID_CANCEL)
        self.Bind(wx.EVT_TREE_SEL_CHANGED, self.on_selection_changed)
        self.Bind(wx.EVT_TREE_ITEM_EXPANDING, self.on_tree_item_expanding)
        self.Bind(wx.EVT_WINDOW_DESTROY, self.OnDestroy)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_char_hook)

        # Show initial message
        self.help_text.SetValue(_("Expand the root node to load modules..."))

    def _load_root_modules(self):
        """Load the modules as children of the root node"""
        if self.dialog_closed:
            return
        
        # Remove the placeholder
        root_child = self.tree.GetFirstChild(self.rootnode)[0]
        if root_child and self.tree.GetItemData(root_child) == "placeholder":
            self.tree.Delete(root_child)
        
        ml = sys.modules
        mlk = sorted(ml.keys())
        
        for m in mlk:
            if self.dialog_closed:
                return
            
            if (not self.includeBlacklistedModules and m in self.blacklist) or m.startswith("_"):
                continue
            
            try:
                il = ml[m].__dict__ if hasattr(ml[m], "__dict__") else {}
                ilk = sorted(il.keys())
                
                has_items = False
                
                # Check if module has functions or classes
                for i in ilk:
                    try:
                        obj = il[i]
                        if inspect.isfunction(obj) or inspect.isclass(obj):
                            has_items = True
                            break
                    except:
                        pass
                
                if has_items:
                    # Create module node with placeholder child (so it's expandable)
                    modulenode = self.tree.AppendItem(
                        parent=self.rootnode, text=m
                    )
                    self.tree.SetItemData(modulenode, "module")
                    # Placeholder so it's expandable
                    placeholder = self.tree.AppendItem(
                        parent=modulenode, text="[Loading...]"
                    )
                    self.tree.SetItemData(placeholder, "placeholder")
                    
            except:
                pass
        
        # Mark root as loaded
        self.loaded_nodes.add(id(self.rootnode))
        self.tree_initialized = True
    
    def _load_module_content(self, module_node):
        """Load the content of a module (functions and classes)"""
        module_name = self.tree.GetItemText(module_node)
        
        # Entferne Platzhalter
        child = self.tree.GetFirstChild(module_node)[0]
        while child:
            if self.tree.GetItemData(child) == "placeholder":
                self.tree.Delete(child)
            child = self.tree.GetNextSibling(child)
        
        ml = sys.modules
        if module_name not in ml:
            return
        
        il = ml[module_name].__dict__ if hasattr(ml[module_name], "__dict__") else {}
        ilk = sorted(il.keys())
        
        for i in ilk:
            try:
                obj = il[i]
                
                if inspect.isfunction(obj):
                    self.tree.AppendItem(
                        parent=module_node, text=i, data="function"
                    )
                
                elif inspect.isclass(obj):
                    classnode = self.tree.AppendItem(
                        parent=module_node, text=i, data="class"
                    )
                    # Platzhalter damit es expandierbar ist
                    try:
                        class_dict = obj.__dict__
                        if class_dict:
                            placeholder = self.tree.AppendItem(
                                parent=classnode, text="[Loading...]"
                            )
                            self.tree.SetItemData(placeholder, "placeholder")
                    except:
                        pass
            except:
                pass
        
        # Mark module as loaded
        self.loaded_nodes.add(id(module_node))
    
    def _load_class_content(self, class_node):
        """Load the content of a class (methods and properties)"""
        parent_module_node = self.tree.GetItemParent(class_node)
        module_name = self.tree.GetItemText(parent_module_node)
        class_name = self.tree.GetItemText(class_node)
        
        # Entferne Platzhalter
        child = self.tree.GetFirstChild(class_node)[0]
        while child:
            if self.tree.GetItemData(child) == "placeholder":
                self.tree.Delete(child)
            child = self.tree.GetNextSibling(child)
        
        ml = sys.modules
        if module_name not in ml:
            return
        
        mod = ml[module_name]
        if not hasattr(mod, class_name):
            return
        
        cls = getattr(mod, class_name)
        
        try:
            for ci in sorted(cls.__dict__.keys()):
                try:
                    member = cls.__dict__[ci]
                    if inspect.ismethod(member) or inspect.isfunction(member):
                        self.tree.AppendItem(
                            parent=class_node, text=ci, data="method"
                        )
                    else:
                        self.tree.AppendItem(
                            parent=class_node, text=ci, data="property"
                        )
                except:
                    pass
        except:
            pass
        
        # Mark class as loaded
        self.loaded_nodes.add(id(class_node))
    
    def on_tree_item_expanding(self, event):
        """Event handler for tree node expansion"""
        if self.dialog_closed:
            return
        
        item = event.GetItem()
        item_data = self.tree.GetItemData(item)
        
        # If node already loaded, do nothing
        if id(item) in self.loaded_nodes:
            return
        
        # Root expand - load modules
        if item == self.rootnode:
            self._load_root_modules()
        
        # Module expand - load its content
        elif item_data == "module":
            self._load_module_content(item)
        
        # Class expand - load its content
        elif item_data == "class":
            self._load_class_content(item)

    def onOk(self, event):
        selection = self.tree.GetSelection()
        if selection == self.tree.GetRootItem():
            return

        parent = self.tree.GetItemParent(selection)
        item_data = self.tree.GetItemData(selection)
        item_text = self.tree.GetItemText(selection)

        # Module selected (direct child of root)
        if parent == self.tree.GetRootItem():
            self.functionstring = f"import {item_text}"
        # Function or class selected (child of a module)
        elif self.tree.GetItemParent(parent) == self.tree.GetRootItem():
            module_name = self.tree.GetItemText(parent)
            if item_data == "class":
                self.functionstring = f"from {module_name} import {item_text}"
            elif item_data == "function":
                self.functionstring = self._format_function_call(module_name, item_text)
        # Method selected (child of a class)
        else:
            grandparent = self.tree.GetItemParent(parent)
            module_name = self.tree.GetItemText(grandparent)
            class_name = self.tree.GetItemText(parent)
            if item_data == "method":
                self.functionstring = self._format_method_call(
                    module_name, class_name, item_text
                )

        self.EndModal(wx.ID_OK)

    def onCancel(self, event):
        self.functionstring = ""
        self.EndModal(wx.ID_CANCEL)

    def on_char_hook(self, event):
        """Handle character input in the dialog, particularly Enter key"""
        keycode = event.GetKeyCode()
        # Enter key
        if keycode == wx.WXK_RETURN:
            # Trigger OK action
            evt = wx.CommandEvent(wx.wxEVT_COMMAND_BUTTON_CLICKED, wx.ID_OK)
            self.ProcessEvent(evt)
            return
        # Allow other keys to propagate
        event.Skip()

    def OnDestroy(self, event):
        """Wird aufgerufen wenn der Dialog zerstört wird"""
        self.dialog_closed = True
        event.Skip()

    def _format_function_call(self, module_name, function_name):
        """Erzeugt einen Funktionsaufruf mit Typ- und Parameternamen."""
        try:
            mod = sys.modules.get(module_name)
            if not mod or not hasattr(mod, function_name):
                return f"{function_name}()"

            func = getattr(mod, function_name)
            sig = inspect.signature(func)
            params = []

            for param_name, param in sig.parameters.items():
                if param_name in ("self", "cls"):
                    continue

                type_annotation = ""
                if param.annotation != inspect.Parameter.empty:
                    if hasattr(param.annotation, "__name__"):
                        type_annotation = param.annotation.__name__
                    else:
                        type_annotation = str(param.annotation)

                if type_annotation:
                    params.append(f"{type_annotation} {param_name}")
                else:
                    params.append(param_name)

            return f"{function_name}({', '.join(params)})"
        except:
            return f"{function_name}()"

    def _format_method_call(self, module_name, class_name, method_name):
        """Erzeugt einen Methodenaufruf mit Typ- und Parameternamen."""
        try:
            mod = sys.modules.get(module_name)
            if not mod or not hasattr(mod, class_name):
                return f"{method_name}()"

            cls = getattr(mod, class_name)
            if not hasattr(cls, method_name):
                return f"{method_name}()"

            method = getattr(cls, method_name)
            sig = inspect.signature(method)
            params = []

            for param_name, param in sig.parameters.items():
                if param_name in ("self", "cls"):
                    continue

                type_annotation = ""
                if param.annotation != inspect.Parameter.empty:
                    if hasattr(param.annotation, "__name__"):
                        type_annotation = param.annotation.__name__
                    else:
                        type_annotation = str(param.annotation)

                if type_annotation:
                    params.append(f"{type_annotation} {param_name}")
                else:
                    params.append(param_name)

            return f"{method_name}({', '.join(params)})"
        except:
            return f"{method_name}()"

    def on_selection_changed(self, event):
        # Schütze vor Aufrufen während der Initialisierung oder nach dem Schließen
        if self.dialog_closed:
            return

        # Überprüfe ob die Controls noch existieren
        try:
            if not self.tree or not self.help_text:
                return
        except:
            return

        item = self.tree.GetSelection()
        if not item or item == self.tree.GetRootItem():
            self.help_text.SetValue(_("Select a module or function to display help"))
        else:
            item_data = self.tree.GetItemData(item)
            
            # Ignoriere Platzhalter und bereits geladene Items
            if item_data == "placeholder":
                return
            
            parent = self.tree.GetItemParent(item)

            if parent == self.tree.GetRootItem() and item_data == "module":
                # Modul
                mod_name = self.tree.GetItemText(item)
                mod = sys.modules.get(mod_name)
                if mod and mod.__doc__:
                    self._set_help_text(mod.__doc__)
                else:
                    self.help_text.SetValue(_("No help available"))
            else:
                # Funktion, Klasse, Methode oder Eigenschaft
                if item_data == "function":
                    # Funktion
                    mod_name = self.tree.GetItemText(parent)
                    func_name = self.tree.GetItemText(item)
                    mod = sys.modules.get(mod_name)
                    if mod and hasattr(mod, func_name):
                        func = getattr(mod, func_name)
                        doc = inspect.getdoc(func)
                        if doc:
                            self._set_help_text(doc)
                        else:
                            self.help_text.SetValue(_("No help available"))
                    else:
                        self.help_text.SetValue(_("Error"))
                elif item_data == "class":
                    # Klasse
                    mod_name = self.tree.GetItemText(parent)
                    class_name = self.tree.GetItemText(item)
                    mod = sys.modules.get(mod_name)
                    if mod and hasattr(mod, class_name):
                        cls = getattr(mod, class_name)
                        doc = inspect.getdoc(cls)
                        if doc:
                            self._set_help_text(doc)
                        else:
                            self.help_text.SetValue(_("No help available"))
                    else:
                        self.help_text.SetValue(_("Error"))
                elif item_data in ("method", "property"):
                    # Methode oder Eigenschaft
                    grandparent = self.tree.GetItemParent(parent)
                    mod_name = self.tree.GetItemText(grandparent)
                    class_name = self.tree.GetItemText(parent)
                    member_name = self.tree.GetItemText(item)

                    mod = sys.modules.get(mod_name)
                    if mod and hasattr(mod, class_name):
                        cls = getattr(mod, class_name)
                        if hasattr(cls, member_name):
                            member = getattr(cls, member_name)
                            doc = inspect.getdoc(member)
                            if doc:
                                self._set_help_text(doc)
                            else:
                                self.help_text.SetValue(_("No help available"))
                        else:
                            self.help_text.SetValue(_("Error"))
                    else:
                        self.help_text.SetValue(_("Error"))
                else:
                    self.help_text.SetValue(_("No help available"))

    def _set_help_text(self, text):
        if not text:
            self.help_text.SetValue("")
            return
        if not self.translateDocstrings:
            self.help_text.SetValue(text)
            return
        cached = self._doc_translation_cache.get(text)
        if cached is None:
            translated = sm_backend.translate_text_with_google(text, targetLanguage=sm_backend.get_nvda_ui_language_code())
            cached = translated if translated else text
            self._doc_translation_cache[text] = cached
        self.help_text.SetValue(cached)


class newscriptdialog(wx.Dialog):
    """Dialog zum Erstellen eines neuen Scripts mit Vorlage."""
    
    # Liste der verfügbaren Scriptkategorien
    SCRIPT_CATEGORIES = [
        _("Miscellaneous"),
        _("Browse mode"),
        _("Emulated system keyboard keys"),
        _("Text review"),
        _("Object navigation"),
        _("System caret"),
        _("Mouse"),
        _("Speech"),
        _("Configuration"),
        _("Configuration profiles"),
        _("Braille"),
        _("Vision"),
        _("Tools"),
        _("Touch screen"),
        _("System focus"),
        _("System status"),
        _("Input"),
        _("Document formatting"),
    ]
    
    def __init__(self, parent, id, title):
        super(newscriptdialog, self).__init__(parent, id, title, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        
        self.script_name = ""
        self.script_description = ""
        self.script_gesture = ""
        self.script_gestures = []
        self.script_category = ""
        self.script_canPropagate = False
        self.script_bypassInputHelp = False
        self.script_allowInSleepMode = False
        self.script_resumeSayAllMode = ""
        self.script_speakOnDemand = False
        self.captured_key = None
        self.key_capture_active = False
        self.gesture_identifiers = []
        self._capture_mode = None
        self._capture_target_index = None
        self._active_capture_func = None
        
        mainSizer = wx.BoxSizer(wx.VERTICAL)
        sHelper = guiHelper.BoxSizerHelper(self, wx.VERTICAL)

        # Script-Name
        self.name_ctrl = sHelper.addLabeledControl(_("&Script name:"), wx.TextCtrl)

        # Beschreibung
        self.desc_ctrl = sHelper.addLabeledControl(
            _("&Description:"), wx.TextCtrl, style=wx.TE_MULTILINE | wx.TE_WORDWRAP
        )
        self.desc_ctrl.SetMinSize((300, 80))

        # Tastenkombinationen als Liste mit Add/Edit/Delete.
        gestureSizer = wx.StaticBoxSizer(
            wx.StaticBox(self, label=_("&Gestures:")), wx.VERTICAL
        )
        gestureRowSizer = wx.BoxSizer(wx.HORIZONTAL)
        self.gestures_list = wx.ListBox(self, style=wx.LB_SINGLE)
        self.gestures_list.SetMinSize((320, 90))
        gestureButtonSizer = wx.BoxSizer(wx.VERTICAL)
        self.gesture_add_btn = wx.Button(self, label=_("&Add (Ins)"))
        self.gesture_edit_btn = wx.Button(self, label=_("&Edit"))
        self.gesture_delete_btn = wx.Button(self, label=_("&Delete (Del)"))
        gestureButtonSizer.Add(self.gesture_add_btn, flag=wx.BOTTOM, border=5)
        gestureButtonSizer.Add(self.gesture_edit_btn, flag=wx.BOTTOM, border=5)
        gestureButtonSizer.Add(self.gesture_delete_btn)
        gestureRowSizer.Add(self.gestures_list, proportion=1, flag=wx.EXPAND)
        gestureRowSizer.AddSpacer(guiHelper.SPACE_BETWEEN_BUTTONS_HORIZONTAL)
        gestureRowSizer.Add(gestureButtonSizer, flag=wx.EXPAND)
        gestureSizer.Add(gestureRowSizer, proportion=1, flag=wx.EXPAND)
        self.gesture_status_ctrl = wx.TextCtrl(self, style=wx.TE_READONLY)
        self.gesture_status_ctrl.SetValue(_("Press Add to capture a gesture."))
        gestureSizer.Add(
            self.gesture_status_ctrl,
            flag=wx.EXPAND | wx.TOP,
            border=guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_VERTICAL,
        )
        sHelper.addItem(gestureSizer, flag=wx.EXPAND)

        # Kategorie
        self.category_ctrl = sHelper.addLabeledControl(
            _("&Category:"),
            wx.ComboBox,
            choices=self.SCRIPT_CATEGORIES,
            value=self.SCRIPT_CATEGORIES[0] if self.SCRIPT_CATEGORIES else "",
            style=wx.CB_DROPDOWN,
        )

        # Erweiterte Script-Optionen
        advancedSizer = wx.StaticBoxSizer(
            wx.StaticBox(self, label=_("Advanced script options")), wx.VERTICAL
        )
        advHelper = guiHelper.BoxSizerHelper(self, sizer=advancedSizer)
        self.can_propagate_ctrl = advHelper.addItem(
            wx.CheckBox(self, label=_("Script can &propagate to focus ancestors"))
        )
        self.bypass_input_help_ctrl = advHelper.addItem(
            wx.CheckBox(self, label=_("&Bypass input help"))
        )
        self.allow_sleep_mode_ctrl = advHelper.addItem(
            wx.CheckBox(self, label=_("Allow in &sleep mode"))
        )
        self.speak_on_demand_ctrl = advHelper.addItem(
            wx.CheckBox(self, label=_("Speak in &on-demand mode"))
        )
        self.resume_say_all_ctrl = advHelper.addLabeledControl(
            _("&Resume say all mode:"),
            wx.ComboBox,
            choices=["", "sayAll.CURSOR_CARET", "sayAll.CURSOR_REVIEW"],
            value="",
            style=wx.CB_DROPDOWN,
        )
        sHelper.addItem(advancedSizer)

        sHelper.addDialogDismissButtons(wx.OK | wx.CANCEL, separated=True)
        mainSizer.Add(sHelper.sizer, border=guiHelper.BORDER_FOR_DIALOGS, flag=wx.ALL)
        mainSizer.Fit(self)
        self.SetSizer(mainSizer)
        self.SetSize((500, 400))

        # Event-Bindungen
        self.Bind(wx.EVT_BUTTON, self.onAddGesture, self.gesture_add_btn)
        self.Bind(wx.EVT_BUTTON, self.onEditGesture, self.gesture_edit_btn)
        self.Bind(wx.EVT_BUTTON, self.onDeleteGesture, self.gesture_delete_btn)
        self.Bind(wx.EVT_LISTBOX, self.onGestureSelectionChanged, self.gestures_list)
        self.Bind(wx.EVT_LISTBOX_DCLICK, self.onEditGesture, self.gestures_list)
        self.Bind(wx.EVT_BUTTON, self.onOk, id=wx.ID_OK)
        self.Bind(wx.EVT_BUTTON, self.onCancel, id=wx.ID_CANCEL)
        self.Bind(wx.EVT_CHAR_HOOK, self.onCharHook)
        self.Bind(wx.EVT_WINDOW_DESTROY, self.onDestroy)
        self._updateGestureControlsState()

        # Fokus auf Name-Feld
        self.name_ctrl.SetFocus()

    def onAddGesture(self, event):
        """Startet den Capture-Modus zum Hinzufügen einer Tastenkombination."""
        if self.key_capture_active:
            self._stopCaptureGesture(canceled=True)
            return
        self._startCaptureGesture(mode="add")

    def onEditGesture(self, event):
        """Startet den Capture-Modus zum Ändern der selektierten Tastenkombination."""
        if self.key_capture_active:
            self._stopCaptureGesture(canceled=True)
            return
        index = self.gestures_list.GetSelection()
        if index == -1:
            wx.MessageBox(
                _("Please select a gesture to edit."),
                _("Missing Information"),
                wx.OK | wx.ICON_INFORMATION,
            )
            self.gestures_list.SetFocus()
            return
        self._startCaptureGesture(mode="edit", targetIndex=index)

    def onDeleteGesture(self, event):
        """Löscht die selektierte Tastenkombination."""
        if self.key_capture_active:
            self._stopCaptureGesture(canceled=True)
            return
        index = self.gestures_list.GetSelection()
        if index == -1:
            return
        self.gestures_list.Delete(index)
        del self.gesture_identifiers[index]
        if self.gesture_identifiers:
            next_index = min(index, len(self.gesture_identifiers) - 1)
            self.gestures_list.SetSelection(next_index)
        self._updateGestureControlsState()

    def onGestureSelectionChanged(self, event):
        """Aktualisiert Status und Button-Zustände nach Selektionswechsel."""
        self._updateGestureControlsState()
        event.Skip()

    def _startCaptureGesture(self, mode, targetIndex=None):
        """Aktiviert die Erfassung für neue oder bestehende Tastenkombinationen."""
        inputCore = __import__("inputCore")
        if inputCore.manager._captureFunc:
            wx.MessageBox(
                _("Another gesture capture is already active."),
                _("Capture in progress"),
                wx.OK | wx.ICON_INFORMATION,
            )
            return
        self.key_capture_active = True
        self._capture_mode = mode
        self._capture_target_index = targetIndex
        self.gesture_status_ctrl.SetValue(_("Press a key..."))
        self.gesture_status_ctrl.SetBackgroundColour(wx.Colour(255, 255, 200))
        self.gesture_status_ctrl.Refresh()
        self._updateGestureControlsState()
        self.SetFocus()

        def _captureFunc(gesture):
            # Reuse NVDA's input gesture pipeline (keyboard, braille, etc.).
            if gesture.isModifier:
                return False
            inputCore.manager._captureFunc = None
            self._active_capture_func = None
            wx.CallAfter(self._handleCapturedGesture, gesture)
            return False

        self._active_capture_func = _captureFunc
        inputCore.manager._captureFunc = _captureFunc

    def _stopCaptureGesture(self, canceled=False, updateUI=True):
        """Deaktiviert die Gestenerfassung."""
        inputCore = __import__("inputCore")
        if inputCore.manager._captureFunc == self._active_capture_func:
            inputCore.manager._captureFunc = None
        self._active_capture_func = None
        self.key_capture_active = False
        self._capture_mode = None
        self._capture_target_index = None
        if updateUI:
            if canceled:
                self.gesture_status_ctrl.SetValue(_("Capture canceled."))
            else:
                self.gesture_status_ctrl.SetValue(_("Ready."))
            self.gesture_status_ctrl.SetBackgroundColour(
                wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW)
            )
            self.gesture_status_ctrl.Refresh()
            self._updateGestureControlsState()

    def _updateGestureControlsState(self):
        """Aktualisiert aktiv/deaktiviert-Status der Gesten-Bedienelemente."""
        hasSelection = self.gestures_list.GetSelection() != -1
        self.gesture_add_btn.Enable(True)
        self.gesture_edit_btn.Enable((not self.key_capture_active) and hasSelection)
        self.gesture_delete_btn.Enable((not self.key_capture_active) and hasSelection)
        self.gestures_list.Enable(not self.key_capture_active)

    def _handleCapturedGesture(self, gesture):
        """Verarbeitet eine mit dem NVDA-Capture-Handler erfasste Geste."""
        gids = list(getattr(gesture, "normalizedIdentifiers", []))
        if not gids:
            self._stopCaptureGesture(canceled=True)
            return
        if len(gids) == 1:
            self._addOrReplaceGesture(gids[0])
            return

        selected = {"done": False}
        menu = wx.Menu()
        for gid in gids:
            item = menu.Append(wx.ID_ANY, self._getDisplayTextForGestureIdentifier(gid))

            def _choose(evt, chosenGid=gid):
                selected["done"] = True
                self._addOrReplaceGesture(chosenGid)

            self.Bind(wx.EVT_MENU, _choose, item)
        self.PopupMenu(menu)
        menu.Destroy()
        if not selected["done"]:
            self._addOrReplaceGesture(gids[0])

    def _addOrReplaceGesture(self, gesture_identifier):
        """Fügt eine erfasste Geste hinzu oder ersetzt die selektierte Geste."""
        display_text = self._getDisplayTextForGestureIdentifier(gesture_identifier)
        if self._capture_mode == "edit" and self._capture_target_index is not None:
            if 0 <= self._capture_target_index < len(self.gesture_identifiers):
                self.gesture_identifiers[self._capture_target_index] = gesture_identifier
                self.gestures_list.SetString(self._capture_target_index, display_text)
                self.gestures_list.SetSelection(self._capture_target_index)
        else:
            self.gesture_identifiers.append(gesture_identifier)
            self.gestures_list.Append(display_text)
            self.gestures_list.SetSelection(len(self.gesture_identifiers) - 1)
        self.gesture_status_ctrl.SetValue(display_text)
        self._stopCaptureGesture(canceled=False)
    
    def onCharHook(self, event):
        """Event-Handler für Tasteneingaben während der Erfassung."""
        if not self.key_capture_active:
            if self.gestures_list.HasFocus():
                key_code = event.GetKeyCode()
                if key_code == wx.WXK_INSERT:
                    self.onAddGesture(None)
                    return
                if key_code == wx.WXK_DELETE:
                    self.onDeleteGesture(None)
                    return
                if key_code in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
                    self.onEditGesture(None)
                    return
            event.Skip()
            return

        # Während aktivem Capture nur Esc lokal behandeln; alles andere via NVDA Capture-Pipeline.
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self._stopCaptureGesture(canceled=True)
            return
        event.Skip()

    def _getDisplayTextForGestureIdentifier(self, identifier):
        """Liefert menschenlesbaren Text für einen Gesture-Identifier im Format 'Tastenkombination (Schema)'."""
        try:
            inputCore = __import__("inputCore")
            source, gesture_text = inputCore.getDisplayTextForGestureIdentifier(identifier)
            if gesture_text:
                if source:
                    return f"{gesture_text} ({source})"
                return gesture_text
        except Exception:
            pass
        return identifier
    
    def onOk(self, event):
        """Event-Handler für OK-Button."""
        if self.key_capture_active:
            self._stopCaptureGesture(canceled=True)
        self.script_name = self.name_ctrl.GetValue().strip()
        self.script_description = self.desc_ctrl.GetValue().strip()
        gesture_count = len(self.gesture_identifiers)
        if gesture_count == 0:
            self.script_gesture = ""
            self.script_gestures = []
        elif gesture_count == 1:
            self.script_gesture = self.gesture_identifiers[0]
            self.script_gestures = []
        else:
            self.script_gesture = ""
            self.script_gestures = list(self.gesture_identifiers)
        # Freie Eingabe aus dem ComboBox-Feld unterstützen.
        self.script_category = self.category_ctrl.GetValue().strip()
        self.script_canPropagate = self.can_propagate_ctrl.GetValue()
        self.script_bypassInputHelp = self.bypass_input_help_ctrl.GetValue()
        self.script_allowInSleepMode = self.allow_sleep_mode_ctrl.GetValue()
        self.script_resumeSayAllMode = self.resume_say_all_ctrl.GetValue().strip()
        self.script_speakOnDemand = self.speak_on_demand_ctrl.GetValue()
        
        if not self.script_name:
            wx.MessageBox(_("Please enter a script name."), _("Missing Information"))
            self.name_ctrl.SetFocus()
            return
        
        self.EndModal(wx.ID_OK)
    
    def onCancel(self, event):
        """Event-Handler für Cancel-Button."""
        if self.key_capture_active:
            self._stopCaptureGesture(canceled=True)
        self.EndModal(wx.ID_CANCEL)

    def onDestroy(self, event):
        """Räumt aktive Gesture-Capture-Callbacks bei Dialogzerstörung auf."""
        if self.key_capture_active:
            self._stopCaptureGesture(canceled=True, updateUI=False)
        event.Skip()


class addonmanifestdialog(wx.Dialog):

    UPDATE_CHANNEL_CHOICES = ["", "dev"]

    def __init__(self, parent, id, title, defaults=None):
        super(addonmanifestdialog, self).__init__(
            parent,
            id,
            title,
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )
        self.manifest_data = sm_backend.get_default_addon_manifest_data()
        if defaults:
            self.manifest_data.update(defaults)

        mainSizer = wx.BoxSizer(wx.VERTICAL)
        panel = wx.ScrolledWindow(self, style=wx.VSCROLL)
        panel.SetScrollRate(20, 20)
        panelSizer = wx.BoxSizer(wx.VERTICAL)
        sHelper = guiHelper.BoxSizerHelper(panel, wx.VERTICAL)

        self.addon_name_ctrl = sHelper.addLabeledControl(
            _("Add-on &name:"), wx.TextCtrl, value=self.manifest_data["addon_name"]
        )
        self.addon_summary_ctrl = sHelper.addLabeledControl(
            _("Add-on &summary:"), wx.TextCtrl, value=self.manifest_data["addon_summary"]
        )
        self.addon_description_ctrl = sHelper.addLabeledControl(
            _("Add-on &description:"),
            wx.TextCtrl,
            value=self.manifest_data["addon_description"],
            style=wx.TE_MULTILINE | wx.TE_WORDWRAP,
        )
        self.addon_description_ctrl.SetMinSize((420, 90))
        self.addon_version_ctrl = sHelper.addLabeledControl(
            _("Add-on &version:"), wx.TextCtrl, value=self.manifest_data["addon_version"]
        )
        self.addon_author_ctrl = sHelper.addLabeledControl(
            _("Add-on &author:"), wx.TextCtrl, value=self.manifest_data["addon_author"]
        )
        self.addon_url_ctrl = sHelper.addLabeledControl(
            _("Support &URL:"), wx.TextCtrl, value=self.manifest_data["addon_url"]
        )
        self.addon_source_url_ctrl = sHelper.addLabeledControl(
            _("Source &URL:"), wx.TextCtrl, value=self.manifest_data["addon_sourceURL"]
        )
        self.addon_doc_file_ctrl = sHelper.addLabeledControl(
            _("&Documentation file:"), wx.TextCtrl, value=self.manifest_data["addon_docFileName"]
        )
        self.addon_minimum_nvda_ctrl = sHelper.addLabeledControl(
            _("&Minimum NVDA version:"),
            wx.TextCtrl,
            value=self.manifest_data["addon_minimumNVDAVersion"],
        )
        self.addon_last_tested_ctrl = sHelper.addLabeledControl(
            _("&Last tested NVDA version:"),
            wx.TextCtrl,
            value=self.manifest_data["addon_lastTestedNVDAVersion"],
        )
        self.addon_update_channel_ctrl = sHelper.addLabeledControl(
            _("&Update channel:"),
            wx.ComboBox,
            choices=self.UPDATE_CHANNEL_CHOICES,
            value=self.manifest_data["addon_updateChannel"],
            style=wx.CB_DROPDOWN,
        )
        self.addon_changelog_ctrl = sHelper.addLabeledControl(
            _("&Changelog:"),
            wx.TextCtrl,
            value=self.manifest_data["addon_changelog"],
            style=wx.TE_MULTILINE | wx.TE_WORDWRAP,
        )
        self.addon_changelog_ctrl.SetMinSize((420, 80))
        self.addon_license_ctrl = sHelper.addLabeledControl(
            _("&License:"), wx.TextCtrl, value=self.manifest_data["addon_license"]
        )
        self.addon_license_url_ctrl = sHelper.addLabeledControl(
            _("License U&RL:"), wx.TextCtrl, value=self.manifest_data["addon_licenseURL"]
        )

        panelSizer.Add(
            sHelper.sizer,
            border=guiHelper.BORDER_FOR_DIALOGS,
            flag=wx.ALL | wx.EXPAND,
        )
        panel.SetSizer(panelSizer)
        panel.FitInside()

        mainSizer.Add(panel, proportion=1, flag=wx.EXPAND)
        mainSizer.Add(
            self.CreateButtonSizer(wx.OK | wx.CANCEL),
            flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            border=guiHelper.BORDER_FOR_DIALOGS,
        )
        self.SetSizer(mainSizer)
        self.SetSize((620, 700))

        self.Bind(wx.EVT_BUTTON, self.onOk, id=wx.ID_OK)
        self.Bind(wx.EVT_BUTTON, self.onCancel, id=wx.ID_CANCEL)
        self.addon_name_ctrl.SetFocus()

    def onOk(self, event):
        manifest_data = {
            "addon_name": self.addon_name_ctrl.GetValue().strip(),
            "addon_summary": self.addon_summary_ctrl.GetValue().strip(),
            "addon_description": self.addon_description_ctrl.GetValue().strip(),
            "addon_version": self.addon_version_ctrl.GetValue().strip(),
            "addon_changelog": self.addon_changelog_ctrl.GetValue().strip(),
            "addon_author": self.addon_author_ctrl.GetValue().strip(),
            "addon_url": self.addon_url_ctrl.GetValue().strip(),
            "addon_sourceURL": self.addon_source_url_ctrl.GetValue().strip(),
            "addon_docFileName": self.addon_doc_file_ctrl.GetValue().strip(),
            "addon_minimumNVDAVersion": self.addon_minimum_nvda_ctrl.GetValue().strip(),
            "addon_lastTestedNVDAVersion": self.addon_last_tested_ctrl.GetValue().strip(),
            "addon_updateChannel": self.addon_update_channel_ctrl.GetValue().strip(),
            "addon_license": self.addon_license_ctrl.GetValue().strip(),
            "addon_licenseURL": self.addon_license_url_ctrl.GetValue().strip(),
        }

        validation_error = self._validate_manifest_data(manifest_data)
        if validation_error:
            wx.MessageBox(validation_error, _("Missing Information"), wx.OK | wx.ICON_ERROR)
            return

        self.manifest_data = manifest_data
        self.EndModal(wx.ID_OK)

    def onCancel(self, event):
        self.EndModal(wx.ID_CANCEL)

    def _validate_manifest_data(self, manifest_data):
        addon_name = manifest_data["addon_name"]
        if not addon_name:
            self.addon_name_ctrl.SetFocus()
            return _("Please enter an add-on name.")
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", addon_name):
            self.addon_name_ctrl.SetFocus()
            return _("The add-on name may only contain letters, digits and underscores, and it must not start with a digit.")
        if not manifest_data["addon_summary"]:
            self.addon_summary_ctrl.SetFocus()
            return _("Please enter an add-on summary.")
        if not manifest_data["addon_version"]:
            self.addon_version_ctrl.SetFocus()
            return _("Please enter an add-on version.")
        if any(char in manifest_data["addon_version"] for char in "\\/:*?\"<>|"):
            self.addon_version_ctrl.SetFocus()
            return _("The add-on version contains invalid filename characters.")
        if not manifest_data["addon_author"]:
            self.addon_author_ctrl.SetFocus()
            return _("Please enter an add-on author.")

        for field_name, ctrl in (
            ("addon_url", self.addon_url_ctrl),
            ("addon_sourceURL", self.addon_source_url_ctrl),
            ("addon_licenseURL", self.addon_license_url_ctrl),
        ):
            value = manifest_data[field_name]
            if value and not value.startswith("https://"):
                ctrl.SetFocus()
                return _("URLs should start with https://.")

        try:
            minimum_version = addonAPIVersion.getAPIVersionTupleFromString(
                manifest_data["addon_minimumNVDAVersion"] or "0.0.0"
            )
        except ValueError:
            self.addon_minimum_nvda_ctrl.SetFocus()
            return _("The minimum NVDA version is invalid.")
        try:
            last_tested_version = addonAPIVersion.getAPIVersionTupleFromString(
                manifest_data["addon_lastTestedNVDAVersion"]
                or manifest_data["addon_minimumNVDAVersion"]
                or "0.0.0"
            )
        except ValueError:
            self.addon_last_tested_ctrl.SetFocus()
            return _("The last tested NVDA version is invalid.")
        if minimum_version > last_tested_version:
            self.addon_last_tested_ctrl.SetFocus()
            return _("The minimum NVDA version must not be greater than the last tested NVDA version.")

        return None


class _AddonFolderHintDialog(wx.Dialog):
    """Infobox that appears when user chooses to open the temp addon folder.

    Shows instructions on how to finalize, optionally with a
    'do not show again' checkbox when *show_hint* is True.
    """

    def __init__(self, parent, show_hint=True):
        super().__init__(parent, title=_("Add-on folder opened"))
        self.dont_show_again = False
        self._show_hint = show_hint

        sizer = wx.BoxSizer(wx.VERTICAL)

        if show_hint:
            msg_text = _(
                "The add-on folder has been opened in Explorer.\n"
                "You can now add additional files (e.g. translations, documentation).\n\n"
                "Click OK when you are done to create the add-on file, or Cancel to abort."
            )
        else:
            msg_text = _("Click OK when you are done adding files to the folder.")

        msg_ctrl = wx.StaticText(self, label=msg_text)
        msg_ctrl.Wrap(460)
        sizer.Add(msg_ctrl, 0, wx.ALL, 12)

        if show_hint:
            self._dont_show_cb = wx.CheckBox(self, label=_("Do not show this message again"))
            sizer.Add(self._dont_show_cb, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
        else:
            self._dont_show_cb = None

        btn_sizer = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 8)

        self.SetSizer(sizer)
        sizer.Fit(self)

        self.Bind(wx.EVT_BUTTON, self._on_ok, id=wx.ID_OK)
        self.Bind(wx.EVT_BUTTON, self._on_cancel, id=wx.ID_CANCEL)

    def _on_ok(self, event):
        if self._dont_show_cb is not None:
            self.dont_show_again = self._dont_show_cb.GetValue()
        self.EndModal(wx.ID_OK)

    def _on_cancel(self, event):
        if self._dont_show_cb is not None:
            self.dont_show_again = self._dont_show_cb.GetValue()
        self.EndModal(wx.ID_CANCEL)


class scriptmanager_mainwindow(wx.Frame):

    SCRATCHPAD_REQUIRED_MENU_IDS = (104, 111, 112, 113, 114, 115)

    def __init__(self, parent, id, title, scriptfile):
        wx.Frame.__init__(self, parent, id, title)

        uiLanguage = sm_backend.get_nvda_ui_language_code()

        def localizedShortcut(shortcut):
            shortcut = str(shortcut or "")
            shortcutTerms = {
                "ctrl": "Strg" if uiLanguage == "de" else "Ctrl",
                "shift": "Umschalt" if uiLanguage == "de" else "Shift",
                "alt": "Alt",
                "up": "Pfeil hoch" if uiLanguage == "de" else "Up",
                "down": "Pfeil runter" if uiLanguage == "de" else "Down",
            }

            def normalizeShortcutPart(part):
                normalized = str(part or "").strip()
                lowered = normalized.lower()
                if lowered in shortcutTerms:
                    return shortcutTerms[lowered]
                if re.match(r"^f\d+$", lowered):
                    return lowered.upper()
                if len(normalized) == 1 and normalized.isalpha():
                    return normalized.upper()
                return normalized

            parts = [normalizeShortcutPart(part) for part in shortcut.split("+")]
            return "+".join(parts)

        def withShortcut(label, shortcut):
            return label + "\t" + localizedShortcut(shortcut)

        menubar = wx.MenuBar()
        self.StatusBar()
        filemenu = wx.Menu()
        filenew = wx.Menu()
        edit = wx.Menu()
        scripts = wx.Menu()
        # view = wx.Menu()
        help = wx.Menu()
        filemenu.AppendSubMenu(filenew, _("&new"))
        filemenu.Append(101, withShortcut(_("&Open"), "ctrl+o"), _("Open an appmodule"))
        filemenu.Append(102, withShortcut(_("&Save"), "ctrl+s"), _("Save the appmodule"))
        filemenu.Append(
            103, withShortcut(_("Save &as..."), "ctrl+shift+s"), _("Save the module as a new file")
        )
        filemenu.Append(104, _("&build add-on..."), _("Create a distributable add-on from scratchpad contents"))
        filemenu.AppendSeparator()
        quit = wx.MenuItem(
            filemenu, 105, withShortcut(_("&Quit"), "Alt+F4"), _("Quit the Application")
        )
        filemenu.AppendItem(quit)
        filenew.Append(110, withShortcut(_("&empty file"), "ctrl+n"))
        filenew.Append(111, _("&appmodule"))
        filenew.Append(112, _("&global plugin"))
        filenew.Append(113, _("&braille display driver"))
        filenew.Append(114, _("&speech synthesizer driver"))
        filenew.Append(115, _("&visual enhancement provider"))
        edit.Append(200, withShortcut(_("&undo"), "ctrl+z"))
        edit.Append(212, withShortcut(_("&redo"), "ctrl+y"))
        edit.Append(201, withShortcut(_("cu&t"), "ctrl+x"))
        edit.Append(202, withShortcut(_("&copy"), "ctrl+c"))
        edit.Append(203, withShortcut(_("&paste"), "ctrl+v"))
        edit.Append(204, withShortcut(_("select &all"), "ctrl+a"))
        edit.Append(205, withShortcut(_("&delete"), "ctrl+y"))
        edit.Append(206, withShortcut(_("&insert function..."), "ctrl+i"))
        scripts.Append(223, withShortcut(_("&new script"), "ctrl+e"), _("Create a new script with template"))
        edit.Append(207, withShortcut(_("&find..."), "ctrl+f"))
        findnextitem = wx.MenuItem(edit, 208, withShortcut(_("find &next"), "f3"))
        findnextitem.Enable(True)
        edit.AppendItem(findnextitem)
        findprevitem = wx.MenuItem(edit, 209, withShortcut(_("find previous"), "shift+f3"))
        findprevitem.Enable(True)
        edit.AppendItem(findprevitem)
        edit.Append(210, withShortcut(_("r&eplace"), "ctrl+h"))
        edit.Append(211, withShortcut(_("go to &line..."), "ctrl+g"))
        scripts.Append(
            224,
            withShortcut(_("next script"), "f2"),
            _("Go to next script definition"),
        )
        scripts.Append(
            225,
            withShortcut(_("previous script"), "shift+f2"),
            _("Go to previous script definition"),
        )
        edit.AppendSeparator()
        scripts.Append(220, withShortcut(_("&next error"), "alt+Down"), _("Go to next script error"))
        scripts.Append(
            221, withShortcut(_("&previous error"), "alt+Up"), _("Go to previous script error")
        )
        scripts.Append(
            222,
            withShortcut(_("check script errors"), "ctrl+shift+e"),
            _("Check and display all script errors"),
        )
        help.Append(901, _("&about..."))
        menubar.Append(filemenu, _("&File"))
        menubar.Append(edit, _("&Edit"))
        menubar.Append(scripts, _('&Scripts'))
        menubar.Append(help, _("&Help"))
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
        self.SetAcceleratorTable(
            wx.AcceleratorTable(
                [
                    (wx.ACCEL_CTRL, ord("S"), 102),
                    (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord("S"), 103),
                ]
            )
        )
        self.Bind(wx.EVT_MENU, self.OnCreateAddon, id=104)
        self.Bind(wx.EVT_MENU, self.OnUndo, id=200)
        self.Bind(wx.EVT_MENU, self.OnRedo, id=212)
        self.Bind(wx.EVT_MENU, self.OnCut, id=201)
        self.Bind(wx.EVT_MENU, self.OnCopy, id=202)
        self.Bind(wx.EVT_MENU, self.OnPaste, id=203)
        self.Bind(wx.EVT_MENU, self.OnDelete, id=204)
        self.Bind(wx.EVT_MENU, self.OnSelectAll, id=205)
        self.Bind(wx.EVT_MENU, self.OnInsertFunction, id=206)
        self.Bind(wx.EVT_MENU, self.OnNewScript, id=223)
        self.Bind(wx.EVT_MENU, self.OnFinditem, id=207)
        self.Bind(wx.EVT_MENU, self.OnFindnextitem, id=208)
        self.Bind(wx.EVT_MENU, self.OnFindpreviousitem, id=209)
        self.Bind(wx.EVT_MENU, self.OnReplaceitem, id=210)
        self.Bind(wx.EVT_MENU, self.OnGotoLineItem, id=211)
        self.Bind(wx.EVT_MENU, self.OnNextScriptDefinition, id=224)
        self.Bind(wx.EVT_MENU, self.OnPreviousScriptDefinition, id=225)
        self.Bind(wx.EVT_MENU, self.OnAbout, id=901)
        self.Bind(wx.EVT_MENU, self.OnNextError, id=220)
        self.Bind(wx.EVT_MENU, self.OnPreviousError, id=221)
        self.Bind(wx.EVT_MENU, self.OnCheckErrors, id=222)
        self.Bind(wx.EVT_FIND, self.on_find)
        # self.Bind(wx.EVT_FIND_NEXT, self.findnext)
        self.Bind(wx.EVT_FIND_REPLACE, self.on_replace)
        self.Bind(wx.EVT_FIND_REPLACE_ALL, self.on_find_replace_all)
        self.Bind(wx.EVT_KEY_DOWN, self.OnKeyDown)
        self.Bind(wx.EVT_ACTIVATE, self._onWindowActivate)
        self.Bind(wx.EVT_MENU_OPEN, self._onMenuOpen)
        self.text = wx.TextCtrl(
            parent=self,
            id=1000,
            value="",
            size=(-1, -1),
            style=wx.TE_MULTILINE | wx.TE_PROCESS_ENTER | wx.TE_DONTWRAP,
        )
        self.text.Bind(wx.EVT_TEXT, self.OnTextChanged)
        self.last_name_saved = ""
        if scriptfile != "":
            self.text.LoadFile(scriptfile)
            self.last_name_saved = scriptfile
        self.modify = False
        self.text.SelectNone()
        self.text.SetFocus()
        # Error-Liste Initialisierung
        self.errors = []
        self.current_error_index = -1
        self.replace = False
        # Aktiviere Error Logging für das aktuelle Script
        sm_backend.activate_error_logging(scriptfile if scriptfile else None)
        self._update_scratchpad_required_menu_state()

    def _onWindowActivate(self, event):
        if event.GetActive():
            self._update_scratchpad_required_menu_state()
        event.Skip()

    def _onMenuOpen(self, event):
        self._update_scratchpad_required_menu_state()
        self._update_edit_menu_state()
        event.Skip()

    def _update_edit_menu_state(self):
        """Enable/disable edit and scripts menu items according to editor state."""
        menuBar = self.GetMenuBar()
        if not menuBar:
            return

        has_text = bool(self.text.GetValue())

        frm, to = self.text.GetSelection()
        has_selection = frm != to

        has_clipboard = False
        try:
            if wx.TheClipboard.Open():
                has_clipboard = wx.TheClipboard.IsSupported(wx.DataFormat(wx.DF_TEXT))
                wx.TheClipboard.Close()
        except Exception:
            pass

        has_scripts = bool(self._get_script_definition_lines())
        has_errors = bool(self.errors)

        # select all (204) – only if editor has text
        item = menuBar.FindItemById(204)
        if item is not None:
            item.Enable(has_text)

        # cut (201) and copy (202) – only if something is selected
        item = menuBar.FindItemById(201)
        if item is not None:
            item.Enable(has_selection)
        item = menuBar.FindItemById(202)
        if item is not None:
            item.Enable(has_selection)

        # paste (203) – only if clipboard contains text
        item = menuBar.FindItemById(203)
        if item is not None:
            item.Enable(has_clipboard)

        # next script (224) / previous script (225)
        item = menuBar.FindItemById(224)
        if item is not None:
            item.Enable(has_scripts)
        item = menuBar.FindItemById(225)
        if item is not None:
            item.Enable(has_scripts)

        # next error (220) / previous error (221)
        item = menuBar.FindItemById(220)
        if item is not None:
            item.Enable(has_errors)
        item = menuBar.FindItemById(221)
        if item is not None:
            item.Enable(has_errors)

    def _scratchpad_locked_by_policy(self):
        return (
            not sm_backend.is_scratchpad_enabled()
            and sm_backend.get_scratchpad_activation_mode() == sm_backend.SCRATCHPAD_ACTIVATION_NEVER
        )

    def _update_scratchpad_required_menu_state(self):
        shouldEnable = not self._scratchpad_locked_by_policy()
        menuBar = self.GetMenuBar()
        for itemId in self.SCRATCHPAD_REQUIRED_MENU_IDS:
            menuItem = menuBar.FindItemById(itemId) if menuBar else None
            if menuItem is not None:
                menuItem.Enable(shouldEnable)

    def _ensure_scratchpad_for_action(self, reasonText):
        if sm_backend.ensure_scratchpad_available(parent=self, reasonText=reasonText):
            self._update_scratchpad_required_menu_state()
            return True
        self._update_scratchpad_required_menu_state()
        wx.MessageBox(
            _("Scratchpad processing is disabled. This action is not available."),
            _("Script Manager"),
            wx.OK | wx.ICON_INFORMATION,
        )
        return False

    def _get_default_file_dialog_dir(self):
        if sm_backend.is_scratchpad_enabled():
            return sm_backend.get_scratchpad_dir(ensure_exists=True, ensure_subdirs=True)
        return os.path.expanduser("~")

    def OnNewEmptyFile(self, event):
        if self.text.IsModified and self.text.GetValue():
            dlg = wx.MessageDialog(
                self,
                _("Save changes?"),
                "",
                wx.YES_NO | wx.YES_DEFAULT | wx.CANCEL | wx.ICON_QUESTION,
            )
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
        if not self._ensure_scratchpad_for_action(_("Creating appModules requires scratchpad.")):
            return
        appmodule_name = self._choose_appmodule_name_for_new_file()
        if appmodule_name is None:
            return
        self.defaultdir = sm_backend.get_scratchpad_subdir("appModules")
        self.defaultfile = appmodule_name + ".py"
        if self.text.IsModified and self.text.GetValue():
            dlg = wx.MessageDialog(
                self,
                _("Save changes?"),
                "",
                wx.YES_NO | wx.YES_DEFAULT | wx.CANCEL | wx.ICON_QUESTION,
            )
            val = dlg.ShowModal()
            if val == wx.ID_YES:
                self.OnSaveFile(event)
                self.DoNewEmptyFile()
                self.text.SetValue(
                    sm_backend.createnewmodule("appModule", appmodule_name, False)
                )
            elif val == wx.ID_CANCEL:
                dlg.Destroy()
            else:
                self.DoNewEmptyFile()
                self.text.SetValue(
                    sm_backend.createnewmodule("appModule", appmodule_name, False)
                )
        else:
            self.DoNewEmptyFile()
            self.text.SetValue(
                sm_backend.createnewmodule("appModule", appmodule_name, False)
            )

    def _normalize_appmodule_name(self, name):
        normalized = re.sub(r"[^A-Za-z0-9_]", "_", str(name or "").strip())
        if not normalized:
            return "untitled"
        if normalized[0].isdigit():
            normalized = "app_" + normalized
        return normalized

    def _choose_appmodule_name_for_new_file(self):
        app_names = sm_backend.get_running_application_names(include_focus=True)
        choices = [_("untitled")]
        mapped_names = ["untitled"]
        for app_name in app_names:
            choices.append(_("Running application: {appname}").format(appname=app_name))
            mapped_names.append(app_name)

        dlg = wx.SingleChoiceDialog(
            self,
            _("Choose the application for which an appModule should be created:"),
            _("New appModule"),
            choices,
        )
        try:
            if dlg.ShowModal() != wx.ID_OK:
                return None
            selected_index = dlg.GetSelection()
            if selected_index < 0:
                return None
            return self._normalize_appmodule_name(mapped_names[selected_index])
        finally:
            dlg.Destroy()

    def OnNewGlobalPlugin(self, event):
        if not self._ensure_scratchpad_for_action(_("Creating global plugins requires scratchpad.")):
            return
        self.defaultdir = sm_backend.get_scratchpad_subdir("globalPlugins")
        if self.text.IsModified and self.text.GetValue():
            dlg = wx.MessageDialog(
                self,
                _("Save changes?"),
                "",
                wx.YES_NO | wx.YES_DEFAULT | wx.CANCEL | wx.ICON_QUESTION,
            )
            val = dlg.ShowModal()
            if val == wx.ID_YES:
                self.OnSaveFile(event)
                self.DoNewEmptyFile()
                self.text.SetValue(
                    sm_backend.createnewmodule("globalPlugin", _("untitled"), False)
                )
            elif val == wx.ID_CANCEL:
                dlg.Destroy()
            else:
                self.DoNewEmptyFile()
                self.text.SetValue(
                    sm_backend.createnewmodule("globalPlugin", _("untitled"), False)
                )
        else:
            self.DoNewEmptyFile()
            self.text.SetValue(
                sm_backend.createnewmodule("globalPlugin", _("untitled"), False)
            )

    def OnNewBrailleDisplayDriver(self, event):
        if not self._ensure_scratchpad_for_action(_("Creating braille display drivers requires scratchpad.")):
            return
        self.defaultdir = sm_backend.get_scratchpad_subdir("brailleDisplayDrivers")
        if self.text.IsModified and self.text.GetValue():
            dlg = wx.MessageDialog(
                self,
                _("Save changes?"),
                "",
                wx.YES_NO | wx.YES_DEFAULT | wx.CANCEL | wx.ICON_QUESTION,
            )
            val = dlg.ShowModal()
            if val == wx.ID_YES:
                self.OnSaveFile(event)
                self.DoNewEmptyFile()
                self.text.SetValue(
                    sm_backend.createnewmodule(
                        "brailleDisplayDriver", _("untitled"), False
                    )
                )
            elif val == wx.ID_CANCEL:
                dlg.Destroy()
            else:
                self.DoNewEmptyFile()
                self.text.SetValue(
                    sm_backend.createnewmodule(
                        "brailleDisplayDriver", _("untitled"), False
                    )
                )
        else:
            self.DoNewEmptyFile()
            self.text.SetValue(
                sm_backend.createnewmodule("brailleDisplayDriver", _("untitled"), False)
            )

    def OnNewSynthDriver(self, event):
        if not self._ensure_scratchpad_for_action(_("Creating synth drivers requires scratchpad.")):
            return
        self.defaultdir = sm_backend.get_scratchpad_subdir("synthDrivers")
        if self.text.IsModified and self.text.GetValue():
            dlg = wx.MessageDialog(
                self,
                _("Save changes?"),
                "",
                wx.YES_NO | wx.YES_DEFAULT | wx.CANCEL | wx.ICON_QUESTION,
            )
            val = dlg.ShowModal()
            if val == wx.ID_YES:
                self.OnSaveFile(event)
                self.DoNewEmptyFile()
                self.text.SetValue(
                    sm_backend.createnewmodule("synthDriver", _("untitled"), False)
                )
            elif val == wx.ID_CANCEL:
                dlg.Destroy()
            else:
                self.DoNewEmptyFile()
                self.text.SetValue(
                    sm_backend.createnewmodule("synthDriver", _("untitled"), False)
                )
        else:
            self.DoNewEmptyFile()
            self.text.SetValue(
                sm_backend.createnewmodule("synthDriver", _("untitled"), False)
            )

    def OnNewVisionEnhancementProvider(self, event):
        if not self._ensure_scratchpad_for_action(_("Creating vision enhancement providers requires scratchpad.")):
            return
        self.defaultdir = sm_backend.get_scratchpad_subdir("visionEnhancementProviders")
        if self.text.IsModified and self.text.GetValue():
            dlg = wx.MessageDialog(
                self,
                _("Save changes?"),
                "",
                wx.YES_NO | wx.YES_DEFAULT | wx.CANCEL | wx.ICON_QUESTION,
            )
            val = dlg.ShowModal()
            if val == wx.ID_YES:
                self.OnSaveFile(event)
                self.DoNewEmptyFile()
                self.text.SetValue(
                    sm_backend.createnewmodule(
                        "visionEnhancementProvider", _("untitled"), False
                    )
                )
            elif val == wx.ID_CANCEL:
                dlg.Destroy()
            else:
                self.DoNewEmptyFile()
                self.text.SetValue(
                    sm_backend.createnewmodule(
                        "visionEnhancementProvider", _("untitled"), False
                    )
                )
        else:
            self.DoNewEmptyFile()
            self.text.SetValue(
                sm_backend.createnewmodule(
                    "visionEnhancementProvider", _("untitled"), False
                )
            )

    def DoNewEmptyFile(self):
        self.last_name_saved = ""
        self.text.Clear()

    def OnNewScript(self, event):
        """Event-Handler für das Erstellen eines neuen Scripts."""
        # Check für ungespeicherte Änderungen
        if self.text.IsModified() and self.text.GetValue():
            dlg = wx.MessageDialog(
                self,
                _("Save changes?"),
                "",
                wx.YES_NO | wx.YES_DEFAULT | wx.CANCEL | wx.ICON_QUESTION,
            )
            val = dlg.ShowModal()
            dlg.Destroy()
            
            if val == wx.ID_YES:
                self.OnSaveFile(event)
            elif val == wx.ID_CANCEL:
                return
        
        # Dialog zum Erstellen des Scripts öffnen
        dlg = newscriptdialog(self, -1, _("Create new script"))
        result = dlg.ShowModal()
        
        if result == wx.ID_OK:
            # Script basierend auf Dialogeingaben generieren
            script_content = self._generateScriptTemplate(
                dlg.script_name,
                dlg.script_description,
                dlg.script_gesture,
                dlg.script_category,
                dlg.script_gestures,
                dlg.script_canPropagate,
                dlg.script_bypassInputHelp,
                dlg.script_allowInSleepMode,
                dlg.script_resumeSayAllMode,
                dlg.script_speakOnDemand,
            )
            
            # Leere Datei vorbereiten
            # self.DoNewEmptyFile()
            
            # Script-Template einfügen
            self.text.SetValue(script_content)
            
            # Text als modifiziert markieren
            self.text.MarkDirty()
        
        dlg.Destroy()
    
    def _generateScriptTemplate(
        self,
        name,
        description,
        gesture,
        category,
        gestures,
        canPropagate,
        bypassInputHelp,
        allowInSleepMode,
        resumeSayAllMode,
        speakOnDemand,
    ):
        """Generiert ein Script-Template basierend auf den Eingaben."""
        # Script-Namen bereinigen (nur alphanumerisch und Unterstriche)
        clean_name = re.sub(r'[^a-zA-Z0-9_]', '_', name)
        clean_name = clean_name.lower()
        if not clean_name.startswith('script_'):
            clean_name = 'script_' + clean_name

        # Dekorator-Parameter dynamisch aus Dialogfeldern zusammensetzen.
        args = []
        if '\n' in description:
            safe_description = description.replace('"""', '\\"\\"\\"')
            args.append(f'description=_("""{safe_description}""")')
        else:
            safe_description = description.replace('"', '\\"')
            args.append(f'description=_("{safe_description}")')

        if category:
            safe_category = category.replace('"', '\\"')
            args.append(f'category=_("{safe_category}")')

        normalized_gestures = [g for g in gestures if g]
        if len(normalized_gestures) > 1:
            gesture_entries = ', '.join(
                ['"%s"' % g.replace('"', '\\"') for g in normalized_gestures]
            )
            args.append(f'gestures=[{gesture_entries}]')
        elif len(normalized_gestures) == 1:
            safe_gesture = normalized_gestures[0].replace('"', '\\"')
            args.append(f'gesture="{safe_gesture}"')
        elif gesture:
            safe_gesture = gesture.replace('"', '\\"')
            args.append(f'gesture="{safe_gesture}"')
        if canPropagate:
            args.append('canPropagate=True')
        if bypassInputHelp:
            args.append('bypassInputHelp=True')
        if allowInSleepMode:
            args.append('allowInSleepMode=True')
        if resumeSayAllMode:
            args.append(f'resumeSayAllMode={resumeSayAllMode}')
        if speakOnDemand:
            args.append('speakOnDemand=True')

        if not args:
            args.append('description=_("")')

        args_str = ',\n    '.join(args)
        safe_name = name.replace('"', '\\"')
        template = f'''@script(
    {args_str}
)
def {clean_name}(self, gesture):
    """Script: {safe_name}"""
    pass
'''

        return template

    def OnFinditem(self, event):
        if not hasattr(self, "frdata"):
            self.frdata = wx.FindReplaceData()
            self.frdata.Flags = self.frdata.Flags | wx.FR_DOWN | wx.FR_NOMATCHCASE
        self.dlg = wx.FindReplaceDialog(
            parent=self, data=self.frdata, title=_("Find"), style=0
        )
        self.dlg.Show()

    def OnGotoLineItem(self, event):
        caption = _("go to line number")
        prompt = _("line number:")
        message = _("enter the line number to go to")
        value = self.text.PositionToXY(self.text.GetInsertionPoint())[1] + 1
        max = self.text.GetNumberOfLines()
        ned = wx.NumberEntryDialog(
            parent=self,
            message=message,
            prompt=prompt,
            caption=caption,
            value=value,
            min=1,
            max=max,
            pos=wx.DefaultPosition,
        )
        if ned.ShowModal() == wx.ID_OK:
            self.text.SetInsertionPoint(self.text.XYToPosition(0, ned.Value - 1))
            ned.Destroy()

    def OnReplaceitem(self, event):
        if not hasattr(self, "frdata"):
            self.frdata = wx.FindReplaceData()
            self.frdata.Flags = self.frdata.Flags | wx.FR_DOWN | wx.FR_NOMATCHCASE
        self.dlg = wx.FindReplaceDialog(
            parent=self,
            data=self.frdata,
            title=_("Find and replace"),
            style=wx.FR_REPLACEDIALOG,
        )
        self.dlg.Show()

    def OnFindnextitem(self, event):
        if not hasattr(self, "frdata") or not hasattr(self, "searchresults"):
            self.OnFinditem(event)
            return
        self.frdata.Flags = self.frdata.Flags or FR_DOWN
        self.searchresultindex += 1
        if self.searchresultindex == len(self.searchresults):
            self.searchresultindex = 0
        pos = self.text.XYToPosition(
            self.searchresults[self.searchresultindex][1],
            self.searchresults[self.searchresultindex][0],
        )
        self.text.SetSelection(pos, pos + len(self.frdata.FindString))

    def OnFindpreviousitem(self, event):
        if not hasattr(self, "frdata") or not hasattr(self, "searchresults"):
            self.OnFinditem(event)
            return
        self.frdata.Flags = self.frdata.Flags or not FR_DOWN
        self.searchresultindex -= 1
        if self.searchresultindex < 0:
            self.searchresultindex = len(self.searchresults) - 1
        pos = self.text.XYToPosition(
            self.searchresults[self.searchresultindex][1],
            self.searchresults[self.searchresultindex][0],
        )
        self.text.SetSelection(pos, pos + len(self.frdata.FindString))

    def on_find(self, event):
        fstring = self.frdata.FindString  # also from event.GetFindString()
        wordborder = ""
        searchflags = 0
        if self.frdata.Flags & wx.FR_NOMATCHCASE:
            searchflags = searchflags | re.I
        if self.frdata.Flags & wx.FR_WHOLEWORD:
            wordborder = r"\b"
        self.searchpattern = re.compile(
            pattern=wordborder + fstring + wordborder, flags=searchflags
        )
        if not hasattr(self, "searchresults"):
            self.searchresults = []
            for line in range(self.text.GetNumberOfLines()):
                for m in self.searchpattern.finditer(self.text.GetLineText(line)):
                    column = m.start()
                    self.searchresults.append((line, column))
        if len(self.searchresults) > 0:
            if hasattr(self, "searchresultindex"):
                if self.searchresultindex >= len(self.searchresults):
                    self.searchresultindex = 0
                elif self.searchresultindex < 0:
                    self.searchresultindex = len(self.searchresults) - 1
            if self.frdata.Flags & wx.FR_DOWN:
                direction = 1
                if not hasattr(self, "searchresultindex"):
                    self.searchresultindex = 0
            else:
                direction = -1
                if not hasattr(self, "searchresultindex"):
                    self.searchresultindex = len(self.searchresults) - 1
            pos = self.text.XYToPosition(
                self.searchresults[self.searchresultindex][1],
                self.searchresults[self.searchresultindex][0],
            )
            self.text.SetSelection(pos, pos + len(fstring))
            self.searchresultindex += direction
        else:
            gui.messageBox(message=_("text not found"), caption=_("find"))

    def on_replace(self, event):
        fstring = self.frdata.FindString  # also from event.GetFindString()
        rstring = self.frdata.ReplaceString
        wordborder = ""
        searchflags = 0
        if self.frdata.Flags & wx.FR_NOMATCHCASE:
            searchflags = searchflags | re.I
        if self.frdata.Flags & wx.FR_WHOLEWORD:
            wordborder = r"\b"
        self.searchpattern = re.compile(
            pattern=wordborder + fstring + wordborder, flags=searchflags
        )
        self.searchresults = []
        for line in range(self.text.GetNumberOfLines()):
            for m in self.searchpattern.finditer(self.text.GetLineText(line)):
                column = m.start()
                self.searchresults.append((line, column))
        if len(self.searchresults) > 0:
            if hasattr(self, "searchresultindex"):
                if self.searchresultindex >= len(self.searchresults):
                    self.searchresultindex = 0
                elif self.searchresultindex < 0:
                    self.searchresultindex = len(self.searchresults) - 1
            if self.frdata.Flags & wx.FR_DOWN:
                direction = 1
                if not hasattr(self, "searchresultindex"):
                    self.searchresultindex = 0
            else:
                end = 0
                direction = -1
                if not hasattr(self, "searchresultindex"):
                    self.searchresultindex = len(self.searchresults) - 1
            pos = self.text.XYToPosition(
                self.searchresults[self.searchresultindex][1],
                self.searchresults[self.searchresultindex][0],
            )
            self.text.Remove(pos, pos + len(fstring))
            self.text.WriteText(rstring)
            self.searchresultindex += direction
        else:
            gui.messageBox(message=_("text not found"), caption=_("find"))

    def on_find_replace_all(self, event):
        fstring = self.frdata.FindString  # also from event.GetFindString()
        rstring = self.frdata.ReplaceString
        wordborder = ""
        searchflags = 0
        if self.frdata.Flags & wx.FR_NOMATCHCASE:
            searchflags = searchflags | re.I
        if self.frdata.Flags & wx.FR_WHOLEWORD:
            wordborder = r"\b"
        self.searchpattern = re.compile(
            pattern=wordborder + fstring + wordborder, flags=searchflags
        )
        self.searchresults = []
        for line in range(self.text.GetNumberOfLines()):
            for m in self.searchpattern.finditer(self.text.GetLineText(line)):
                column = m.start()
                self.searchresults.append((line, column))
        if len(self.searchresults) > 0:
            for r in self.searchresults:
                pos = self.text.XYToPosition(r[1], r[0])
                self.text.Remove(pos, pos + len(fstring))
                self.text.WriteText(rstring)
        else:
            gui.messageBox(message=_("text not found"), caption=_("find"))

    def OnInsertFunction(self, event):
        ifd = insertfunctionsdialog(
            self,
            id=wx.ID_ANY,
            title=_("insert function"),
            includeBlacklistedModules=sm_backend.get_include_blacklisted_modules(),
            translateDocstrings=sm_backend.get_translate_docstrings_enabled(),
        )
        if ifd.ShowModal() == wx.ID_OK:
            self.text.WriteText(ifd.functionstring)
            ifd.Destroy()

    def _save_if_needed_for_build(self, event):
        if not self.modify or not self.text.GetValue():
            return True
        dlg = wx.MessageDialog(
            self,
            _("Save changes before creating the add-on?"),
            _("Create add-on"),
            wx.YES_NO | wx.YES_DEFAULT | wx.CANCEL | wx.ICON_QUESTION,
        )
        try:
            result = dlg.ShowModal()
        finally:
            dlg.Destroy()
        if result == wx.ID_YES:
            return self.OnSaveFile(event)
        if result == wx.ID_NO:
            return True
        return False

    def _is_path_in_scratchpad(self, path):
        if not path:
            return False
        scratchpad_dir = os.path.abspath(
            sm_backend.get_scratchpad_dir(ensure_exists=True, ensure_subdirs=True)
        )
        normalized_path = os.path.abspath(path)
        try:
            return os.path.commonpath([scratchpad_dir, normalized_path]) == scratchpad_dir
        except ValueError:
            return False

    def _get_addon_output_path(self, manifest_data):
        default_file = "{name}-{version}.{extension}".format(
            name=manifest_data["addon_name"],
            version=manifest_data["addon_version"],
            extension=addonHandler.BUNDLE_EXTENSION,
        )
        save_dialog = wx.FileDialog(
            self,
            message=_("Save add-on as..."),
            defaultDir=sm_backend.get_scratchpad_dir(ensure_exists=True, ensure_subdirs=True),
            defaultFile=default_file,
            wildcard=_("NVDA add-on files (*.{extension})").format(extension=addonHandler.BUNDLE_EXTENSION)
            +"|*.{extension}".format(extension=addonHandler.BUNDLE_EXTENSION),
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        )
        try:
            if save_dialog.ShowModal() != wx.ID_OK:
                return None
            path = save_dialog.GetPath()
            expected_extension = ".{extension}".format(extension=addonHandler.BUNDLE_EXTENSION)
            if not path.lower().endswith(expected_extension.lower()):
                path += expected_extension
            return path
        finally:
            save_dialog.Destroy()

    def OnCreateAddon(self, event):
        if not self._ensure_scratchpad_for_action(_("Building an add-on requires scratchpad.")):
            return
        if not self._save_if_needed_for_build(event):
            return

        if self.last_name_saved and not self._is_path_in_scratchpad(self.last_name_saved):
            wx.MessageBox(
                _("The currently open file is not inside the scratchpad directory. Only files from the scratchpad will be included in the add-on."),
                _("Create add-on"),
                wx.OK | wx.ICON_INFORMATION,
            )

        manifest_dialog = addonmanifestdialog(self, wx.ID_ANY, _("Create add-on"))
        try:
            if manifest_dialog.ShowModal() != wx.ID_OK:
                return
            output_path = self._get_addon_output_path(manifest_dialog.manifest_data)
            if not output_path:
                return
            # Phase 1: prepare files in a temporary directory
            try:
                addon_dir, temp_dir, prepared_manifest = sm_backend.prepare_addon_build(
                    manifest_dialog.manifest_data,
                    output_path,
                )
            except Exception as error:
                wx.MessageBox(
                    _("The add-on could not be prepared.\n{error}").format(error=str(error)),
                    _("Error"),
                    wx.OK | wx.ICON_ERROR,
                )
                return
        finally:
            manifest_dialog.Destroy()

        # Ask whether to finalise immediately or open the temp folder first
        ask_dlg = wx.MessageDialog(
            self,
            _("The add-on folder has been prepared. Do you want to finalize the add-on now or open the folder to add additional files first?"),
            _("Create add-on"),
            wx.YES_NO | wx.CANCEL | wx.ICON_QUESTION,
        )
        ask_dlg.SetYesNoCancelLabels(
            _("&Finalize"),
            _("&Open folder"),
            _("&Cancel"),
        )
        choice = ask_dlg.ShowModal()
        ask_dlg.Destroy()

        if choice == wx.ID_CANCEL:
            shutil.rmtree(temp_dir, ignore_errors=True)
            return

        if choice == wx.ID_NO:
            # Open the prepared folder in Explorer so the user can add files
            os.startfile(addon_dir)

            show_hint = sm_backend.get_show_addon_folder_hint()
            hint_dlg = _AddonFolderHintDialog(self, show_hint=show_hint)
            hint_result = hint_dlg.ShowModal()
            dont_show_again = hint_dlg.dont_show_again
            hint_dlg.Destroy()

            if dont_show_again and show_hint:
                sm_backend.set_show_addon_folder_hint(False)

            if hint_result != wx.ID_OK:
                shutil.rmtree(temp_dir, ignore_errors=True)
                return

        # Phase 2: create the bundle from the (possibly modified) folder
        try:
            bundle_path = sm_backend.finalize_addon_build(
                addon_dir, temp_dir, prepared_manifest, output_path
            )
        except Exception as error:
            wx.MessageBox(
                _("The add-on could not be created.\n{error}").format(error=str(error)),
                _("Error"),
                wx.OK | wx.ICON_ERROR,
            )
            return

        if wx.MessageBox(
            _("The add-on was created successfully at:\n{path}\n\nWould you like to test it now?").format(path=bundle_path),
            _("Add-on created"),
            wx.YES_NO | wx.ICON_QUESTION,
        ) == wx.YES:
            try:
                sm_backend.install_addon_bundle_for_testing(bundle_path, gui.mainFrame)
            except Exception as error:
                wx.MessageBox(
                    _("The add-on was created, but testing could not be started.\n{error}").format(error=str(error)),
                    _("Error"),
                    wx.OK | wx.ICON_ERROR,
                )
        else:
            ui.message(_("Add-on created"))

    def OnOpenFile(self, event):
        if self.text.IsModified and self.text.GetValue():
            dlg = wx.MessageDialog(
                self,
                _("Save changes?"),
                "",
                wx.YES_NO | wx.YES_DEFAULT | wx.CANCEL | wx.ICON_QUESTION,
            )
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
        wcd = (
            _("All files (*.*)")
            +"|*.*|"
            +_("appmodule source files (*.py)")
            +"|*.py"
        )
        default_dir = self._get_default_file_dialog_dir()
        try:
            open_dlg = wx.FileDialog(
                self,
                message=_("Choose a file"),
                defaultDir=default_dir,
                defaultFile="",
                wildcard=wcd,
                style=wx.FD_OPEN | wx.FD_CHANGE_DIR | wx.FD_FILE_MUST_EXIST,
            )
        except:
            pass
        if open_dlg.ShowModal() == wx.ID_OK:
            path = open_dlg.GetDirectory() + os.sep + open_dlg.GetFilename()
            ui.message(path)
            if self.text.GetLastPosition():
                self.text.Clear()
            self.text.LoadFile(path)
            self.last_name_saved = path
            self.modify = False
            self.text.SetSelection(0, 0)
            # Automatische Fehlerprüfung beim Laden
            wx.CallAfter(self._check_errors_on_load)
        open_dlg.Destroy()

    def OnSaveFile(self, event):
        if self.last_name_saved:
            try:
                # Aktiviere Error Logging vor dem Speichern
                sm_backend.activate_error_logging(self.last_name_saved)
                
                self.text.SaveFile(self.last_name_saved)
                self.statusbar.SetStatusText(
                    os.path.basename(self.last_name_saved) + " " + _("saved"), 0
                )
                self.statusbar.SetStatusText("", 1)
                self.modify = False
                return True
            except Exception as error:
                dlg = wx.MessageDialog(self, _("Error saving file") + "\n" + str(error))
                try:
                    dlg.ShowModal()
                finally:
                    dlg.Destroy()
                return False
        else:
            return self.OnSaveAsFile(event)

    def OnSaveAsFile(self, event):
        wcd = (
            _("All files(*.*)") + "|*.*|" + _("appmodule source files (*.py)") + "|*.py"
        )
        if hasattr(self, "defaultdir"):
            default_dir = self.defaultdir
        else:
            default_dir = self._get_default_file_dialog_dir()
        if hasattr(self, "defaultfile"):
            defaultfile = self.defaultfile
        else:
            defaultfile = _("untitled") + ".py"
        save_dlg = wx.FileDialog(
            self,
            message=_("Save file as..."),
            defaultDir=default_dir,
            defaultFile=defaultfile,
            wildcard=wcd,
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        )
        try:
            if save_dlg.ShowModal() != wx.ID_OK:
                return False
            path = save_dlg.GetPath()
            try:
                self.text.SaveFile(path)
                self.last_name_saved = path
                self.statusbar.SetStatusText(os.path.basename(path) + " " + _("saved"), 0)
                self.statusbar.SetStatusText("", 1)
                self.modify = False
                return True
            except Exception as error:
                dlg = wx.MessageDialog(self, _("Error saving file") + "\n" + str(error))
                try:
                    dlg.ShowModal()
                finally:
                    dlg.Destroy()
                return False
        finally:
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
        if hasattr(self, "searchpattern"):
            self.searchresults = []
            for x in range(self.text.GetNumberOfLines()):
                for m in self.searchpattern.finditer(self.text.GetLineText(x)):
                    column = m.start()
                    self.searchresults.append((x, column))
        self.statusbar.SetStatusText(_(" modified"), 1)
        self.modify = True
        event.Skip()

    def OnKeyDown(self, event):
        keycode = event.GetKeyCode()
        if keycode == wx.WXK_F2:
            if event.ShiftDown():
                self.OnPreviousScriptDefinition(None)
            else:
                self.OnNextScriptDefinition(None)
            return
        if hasattr(self, "searchresults"):
            if len(self.searchresults) > 0:
                navkeylist = [
                    wx.WXK_DOWN,
                    wx.WXK_END,
                    wx.WXK_HOME,
                    wx.WXK_LEFT,
                    wx.WXK_NUMPAD_DOWN,
                    wx.WXK_NUMPAD_END,
                    wx.WXK_NUMPAD_HOME,
                    wx.WXK_NUMPAD_LEFT,
                    wx.WXK_NUMPAD_PAGEDOWN,
                    wx.WXK_NUMPAD_PAGEUP,
                    wx.WXK_NUMPAD_RIGHT,
                    wx.WXK_NUMPAD_UP,
                    wx.WXK_PAGEDOWN,
                    wx.WXK_PAGEUP,
                    wx.WXK_RIGHT,
                    wx.WXK_UP,
                ]
                if keycode in navkeylist:
                    x = 0
                    while (
                        self.text.XYToPosition(
                            self.searchresults[x][1], self.searchresults[x][0]
                        )
                        +len(self.frdata.FindString)
                    ) < self.text.GetInsertionPoint():
                        x += 1
                self.searchresultindex = x
        if keycode == wx.WXK_INSERT:
            if not self.replace:
                self.statusbar.SetStatusText(_("INS"), 2)
                self.replace = True
            else:
                self.statusbar.SetStatusText("", 2)
                self.replace = False
        event.Skip()

    def StatusBar(self):
        self.statusbar = self.CreateStatusBar()
        self.statusbar.SetFieldsCount(3)
        self.statusbar.SetStatusWidths([-5, -2, -1])

    def OnAbout(self, event):
        dlg = wx.MessageDialog(
            self,
            _(
                "\tNVDA Script-manager\t\n (c) 2011-{year} by David Parduhn\n portions copyright (C) jan bodnar 2005-2006"
            ).format(year=datetime.date.today().year),
            _("About nvda Script Manager"),
            wx.OK | wx.ICON_INFORMATION,
        )
        dlg.ShowModal()
        dlg.Destroy()

    def OnCheckErrors(self, event):
        """Überprüft das aktuelle Script auf Fehler."""
        script_content = self.text.GetValue()
        if not script_content.strip():
            ui.message(_("No script content to check"))
            return

        # Aktiviere Error Logging bevor wir die Fehler prüfen
        sm_backend.activate_error_logging(self.last_name_saved if self.last_name_saved else None)
        
        self.errors, _error_detail_str = sm_backend.check_script_for_errors(
            script_content
        )

        if not self.errors:
            # Signalton abspielen (Beep)
            wx.Bell()
            msg = _("no errors found")
            self.statusbar.SetStatusText(msg, 1)
            ui.message(msg)
            self.current_error_index = -1
        else:
            self.current_error_index = 0
            msg = _("{count} error(s) found").format(count=len(self.errors))
            self.statusbar.SetStatusText(msg, 1)
            ui.message(msg)
            # Zum ersten Fehler springen
            self._goto_error(self.current_error_index)

    def OnNextError(self, event):
        """Springt zum nächsten Fehler."""
        # Wenn noch keine Fehler geprüft wurden, prüfe sie jetzt
        if not self.errors and self.current_error_index == -1:
            # Trigger OnCheckErrors automatisch
            check_event = None
            self.OnCheckErrors(check_event)
            # Wenn keine Fehler gefunden wurden, beende hier
            if not self.errors:
                return
        
        if not self.errors:
            wx.Bell()
            msg = _("no errors found")
            self.statusbar.SetStatusText(msg, 1)
            ui.message(msg)
            return

        if self.current_error_index < 0:
            self.current_error_index = 0
        else:
            self.current_error_index += 1
            if self.current_error_index >= len(self.errors):
                self.current_error_index = 0

        self._goto_error(self.current_error_index)

    def OnPreviousError(self, event):
        """Springt zum vorherigen Fehler."""
        # Wenn noch keine Fehler geprüft wurden, prüfe sie jetzt
        if not self.errors and self.current_error_index == -1:
            # Trigger OnCheckErrors automatisch
            check_event = None
            self.OnCheckErrors(check_event)
            # Wenn keine Fehler gefunden wurden, beende hier
            if not self.errors:
                return
        
        if not self.errors:
            wx.Bell()
            msg = _("no errors found")
            self.statusbar.SetStatusText(msg, 1)
            ui.message(msg)
            return

        if self.current_error_index < 0:
            self.current_error_index = len(self.errors) - 1
        else:
            self.current_error_index -= 1
            if self.current_error_index < 0:
                self.current_error_index = len(self.errors) - 1

        self._goto_error(self.current_error_index)

    def OnNextScriptDefinition(self, event):
        """Springt zur nächsten Scriptdefinition (def script_...)."""
        self._goto_script_definition(forward=True)

    def OnPreviousScriptDefinition(self, event):
        """Springt zur vorherigen Scriptdefinition (def script_...)."""
        self._goto_script_definition(forward=False)

    def _get_script_definition_lines(self):
        """Liefert alle Zeilenindizes mit Scriptdefinitionen."""
        lines = []
        pattern = re.compile(r"^\s*def\s+script_[a-zA-Z0-9_]*\s*\(")
        for line_index in range(self.text.GetNumberOfLines()):
            if pattern.match(self.text.GetLineText(line_index)):
                lines.append(line_index)
        return lines

    def _goto_script_definition(self, forward=True):
        """Springt zur nächsten/vorherigen Scriptdefinition und signalisiert Umbruch."""
        script_lines = self._get_script_definition_lines()
        if not script_lines:
            wx.Bell()
            msg = _("no script definitions found")
            self.statusbar.SetStatusText(msg, 1)
            ui.message(msg)
            return

        current_line = self.text.PositionToXY(self.text.GetInsertionPoint())[1]
        wrapped = False

        if forward:
            target_candidates = [line for line in script_lines if line > current_line]
            if target_candidates:
                target_line = target_candidates[0]
            else:
                target_line = script_lines[0]
                wrapped = True
        else:
            target_candidates = [line for line in script_lines if line < current_line]
            if target_candidates:
                target_line = target_candidates[-1]
            else:
                target_line = script_lines[-1]
                wrapped = True

        pos = self.text.XYToPosition(0, target_line)
        self.text.SetInsertionPoint(pos)
        self.text.SetSelection(pos, pos)

        if wrapped:
            wx.Bell()

        msg = _("script definition line {line}").format(line=target_line + 1)
        self.statusbar.SetStatusText(msg, 1)
        ui.message(msg)

    def _goto_error(self, error_index):
        """Springt zu einem Fehler mit gegebenem Index."""
        if error_index < 0 or error_index >= len(self.errors):
            return

        error = self.errors[error_index]
        line_num = error.get("line", 1)
        message = error.get("message", "Unknown error")
        # Zur Zeile springen
        try:
            pos = self.text.XYToPosition(0, line_num - 1)
            self.text.SetInsertionPoint(pos)
            self.text.SetSelection(pos, pos)
        except:
            # Falls Zeilennummer ungültig ist
            self.text.SetInsertionPoint(0)

        # Fehlermeldung in Statusleiste anzeigen
        msg = _("Error {current}/{total}: Line {line} - {msg}").format(
            current=error_index + 1, total=len(self.errors), line=line_num, msg=message
        )
        self.statusbar.SetStatusText(msg, 1)

        # Fehlermeldung als Blitzmeldung
        brief_msg = _("Line {line}: {msg}").format(line=line_num, msg=message)
        ui.message(brief_msg)

    def _check_errors_on_load(self):
        """Wird automatisch beim Laden einer Datei aufgerufen."""
        # Kleine Verzögerung, um sicherzustellen, dass die Datei vollständig geladen ist
        time.sleep(0.2)
        event = None
        self.OnCheckErrors(event)

    def OnQuit(self, event):
        if self.modify == True:
            dlg = wx.MessageDialog(
                self,
                _("Save before Exit?"),
                "",
                wx.YES_NO | wx.YES_DEFAULT | wx.CANCEL | wx.ICON_QUESTION,
            )
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
