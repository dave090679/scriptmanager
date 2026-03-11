import datetime
import config
import sys
import os
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
import re

addonHandler.initTranslation()


class insertfunctionsdialog(wx.Dialog):
    functionstring = ""

    def __init__(self, parent, id, title):
        super(insertfunctionsdialog, self).__init__(parent, id, title)
        mainsizer = wx.BoxSizer(orient=wx.VERTICAL)
        self.tree = wx.TreeCtrl(self, style=wx.TR_SINGLE | wx.TR_NO_BUTTONS)
        rootnode = self.tree.AddRoot(text="root")
        self.rootnode = rootnode
        self.tree_initialized = False
        self.dialog_closed = False
        
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
        
        # Create a placeholder child for root so it's expandable
        placeholder = self.tree.AppendItem(parent=self.rootnode, text="[Loading modules...]")
        self.tree.SetItemData(placeholder, "placeholder")

        self.help_text = wx.TextCtrl(
            self, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP
        )
        mainsizer.Add(self.tree, 1, wx.EXPAND)
        mainsizer.Add(self.help_text, 1, wx.EXPAND)
        buttons = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        mainsizer.Add(buttons)
        self.SetSizer(mainsizer)
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
            
            if m in self.blacklist or m.startswith("_"):
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
                    self.help_text.SetValue(mod.__doc__)
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
                            self.help_text.SetValue(doc)
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
                            self.help_text.SetValue(doc)
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
                                self.help_text.SetValue(doc)
                            else:
                                self.help_text.SetValue(_("No help available"))
                        else:
                            self.help_text.SetValue(_("Error"))
                    else:
                        self.help_text.SetValue(_("Error"))
                else:
                    self.help_text.SetValue(_("No help available"))


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
        self.script_category = ""
        self.captured_key = None
        self.key_capture_active = False
        
        # Hauptsizer
        main_sizer = wx.BoxSizer(orient=wx.VERTICAL)
        
        # Script-Name
        name_sizer = wx.BoxSizer(orient=wx.HORIZONTAL)
        name_label = wx.StaticText(self, label=_("&Script name:"))
        self.name_ctrl = wx.TextCtrl(self, value="")
        name_sizer.Add(name_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        name_sizer.Add(self.name_ctrl, 1, wx.EXPAND)
        main_sizer.Add(name_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        # Beschreibung
        desc_label = wx.StaticText(self, label=_("&Description:"))
        self.desc_ctrl = wx.TextCtrl(self, value="", style=wx.TE_MULTILINE | wx.TE_WORDWRAP)
        self.desc_ctrl.SetMinSize((300, 80))
        main_sizer.Add(desc_label, 0, wx.ALL, 5)
        main_sizer.Add(self.desc_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)
        
        # Tastenkombination
        gesture_sizer = wx.BoxSizer(orient=wx.HORIZONTAL)
        gesture_label = wx.StaticText(self, label=_("&Gesture:"))
        self.gesture_ctrl = wx.TextCtrl(self, value="", style=wx.TE_READONLY)
        self.gesture_capture_btn = wx.Button(self, label=_("&Capture gesture"))
        gesture_sizer.Add(gesture_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        gesture_sizer.Add(self.gesture_ctrl, 1, wx.EXPAND | wx.RIGHT, 5)
        gesture_sizer.Add(self.gesture_capture_btn, 0)
        main_sizer.Add(gesture_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        # Kategorie
        category_sizer = wx.BoxSizer(orient=wx.HORIZONTAL)
        category_label = wx.StaticText(self, label=_("&Category:"))
        self.category_ctrl = wx.ComboBox(
            self,
            choices=self.SCRIPT_CATEGORIES,
            value=self.SCRIPT_CATEGORIES[0] if self.SCRIPT_CATEGORIES else "",
            style=wx.CB_DROPDOWN
        )
        category_sizer.Add(category_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        category_sizer.Add(self.category_ctrl, 1, wx.EXPAND)
        main_sizer.Add(category_sizer, 0, wx.EXPAND | wx.ALL, 5)
        
        # Buttons
        buttons = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        main_sizer.Add(buttons, 0, wx.EXPAND | wx.ALL, 5)
        
        # Sizer setzen
        self.SetSizer(main_sizer)
        self.SetSize((500, 400))
        
        # Event-Bindungen
        self.Bind(wx.EVT_BUTTON, self.onCaptureGesture, self.gesture_capture_btn)
        self.Bind(wx.EVT_BUTTON, self.onOk, id=wx.ID_OK)
        self.Bind(wx.EVT_BUTTON, self.onCancel, id=wx.ID_CANCEL)
        self.Bind(wx.EVT_CHAR_HOOK, self.onCharHook)
        
        # Fokus auf Name-Feld
        self.name_ctrl.SetFocus()
    
    def onCaptureGesture(self, event):
        """Event-Handler für Gestural-Erfassung aktivieren."""
        self.key_capture_active = not self.key_capture_active
        
        if self.key_capture_active:
            self.gesture_capture_btn.SetLabel(_("&Stop capturing"))
            self.gesture_ctrl.SetValue(_("Press a key..."))
            self.gesture_ctrl.SetBackgroundColour(wx.Colour(255, 255, 200))
            self.gesture_capture_btn.SetFocus()
        else:
            self.gesture_capture_btn.SetLabel(_("&Capture gesture"))
            self.gesture_ctrl.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOW))
    
    def onCharHook(self, event):
        """Event-Handler für Tasteneingaben während der Erfassung."""
        if not self.key_capture_active:
            event.Skip()
            return
        
        key_code = event.GetKeyCode()
        
        # Tasten ignorieren, die nicht abgefangen werden sollen
        if key_code in (wx.WXK_TAB, wx.WXK_ESCAPE, wx.WXK_RETURN):
            if key_code == wx.WXK_ESCAPE:
                self.onCaptureGesture(None)
            event.Skip()
            return
        
        # Diese Taste sollte behandelt werden
        event.Skip = lambda: None  # Verhindern, dass die Taste weitergeleitet wird
        
        # Modifikatoren sammeln
        modifiers = []
        
        if event.ControlDown():
            modifiers.append("control")
        if event.ShiftDown():
            modifiers.append("shift")
        if event.AltDown():
            modifiers.append("alt")
        
        # Key name ermitteln
        key_name = self._getKeyName(key_code)
        
        if key_name:
            modifiers.append(key_name)
            gesture_str = "+".join(modifiers)
            self.script_gesture = "kb:" + gesture_str
            self.gesture_ctrl.SetValue(self.script_gesture)
            
            # Erfassung stoppen
            self.onCaptureGesture(None)
    
    def _getKeyName(self, key_code):
        """Übersetzt WX-Key-Code zu NVDA-Key-Name."""
        # Mapping von WX VK-Codes zu NVDA-Namen
        key_mapping = {
            wx.WXK_F1: "f1", wx.WXK_F2: "f2", wx.WXK_F3: "f3", wx.WXK_F4: "f4",
            wx.WXK_F5: "f5", wx.WXK_F6: "f6", wx.WXK_F7: "f7", wx.WXK_F8: "f8",
            wx.WXK_F9: "f9", wx.WXK_F10: "f10", wx.WXK_F11: "f11", wx.WXK_F12: "f12",
            wx.WXK_HOME: "home", wx.WXK_END: "end",
            wx.WXK_PAGEUP: "pageUp", wx.WXK_PAGEDOWN: "pageDown",
            wx.WXK_UP: "upArrow", wx.WXK_DOWN: "downArrow",
            wx.WXK_LEFT: "leftArrow", wx.WXK_RIGHT: "rightArrow",
            wx.WXK_INSERT: "insert", wx.WXK_DELETE: "delete",
            wx.WXK_BACK: "backspace", wx.WXK_SPACE: "space",
        }
        
        if key_code in key_mapping:
            return key_mapping[key_code]
        
        # Für reguläre Zeichen
        if 32 <= key_code < 127:
            return chr(key_code).lower()
        
        return None
    
    def onOk(self, event):
        """Event-Handler für OK-Button."""
        self.script_name = self.name_ctrl.GetValue().strip()
        self.script_description = self.desc_ctrl.GetValue().strip()
        self.script_gesture = self.gesture_ctrl.GetValue().strip()
        self.script_category = self.category_ctrl.GetStringSelection()
        
        if not self.script_name:
            wx.MessageBox(_("Please enter a script name."), _("Missing Information"))
            self.name_ctrl.SetFocus()
            return
        
        self.EndModal(wx.ID_OK)
    
    def onCancel(self, event):
        """Event-Handler für Cancel-Button."""
        self.EndModal(wx.ID_CANCEL)


class scriptmanager_mainwindow(wx.Frame):

    def __init__(self, parent, id, title, scriptfile):
        wx.Frame.__init__(self, parent, id, title)
        menubar = wx.MenuBar()
        self.StatusBar()
        filemenu = wx.Menu()
        filenew = wx.Menu()
        edit = wx.Menu()
        # scripts = wx.Menu()
        # view = wx.Menu()
        help = wx.Menu()
        filemenu.AppendSubMenu(filenew, _("new"))
        filemenu.Append(101, _("&Open") + "\tctrl+o", _("Open an appmodule"))
        filemenu.Append(102, _("&Save") + "\tctrl+s", _("Save the appmodule"))
        filemenu.Append(
            103, _("Save &as...") + "\tctrl+shift+s", _("Save the module as a new file")
        )
        filemenu.AppendSeparator()
        quit = wx.MenuItem(
            filemenu, 105, _("&Quit") + "\tAlt+F4", _("Quit the Application")
        )
        filemenu.AppendItem(quit)
        filenew.Append(110, _("empty file") + "\tctrl+n")
        filenew.Append(111, _("appmodule"))
        filenew.Append(112, _("global plugin"))
        filenew.Append(113, _("braille display driver"))
        filenew.Append(114, _("speech synthesizer driver"))
        filenew.Append(115, _("visual enhancement provider"))
        edit.Append(200, _("undo") + "\tctrl+z")
        edit.Append(212, _("redo") + "\tctrl+y")
        edit.Append(201, _("cut") + "\tctrl+x")
        edit.Append(202, _("copy") + "\tctrl+c")
        edit.Append(203, _("paste") + "\tctrl+v")
        edit.Append(204, _("select all") + "\tctrl+a")
        edit.Append(205, _("delete") + "\tctrl+y")
        edit.Append(206, _("insert function...") + "\tctrl+i")
        edit.Append(223, _("&new script") + "\tctrl+e", _("Create a new script with template"))
        edit.Append(207, _("&find...") + "	ctrl+f")
        findnextitem = wx.MenuItem(edit, 208, _("find next") + "\tf3")
        findnextitem.Enable(True)
        edit.AppendItem(findnextitem)
        findprevitem = wx.MenuItem(edit, 209, _("find previous") + "\tshift+f3")
        findprevitem.Enable(True)
        edit.AppendItem(findprevitem)
        edit.Append(210, _("replace\tctrl+h"))
        edit.Append(211, _("go to Line...\tctrl+g"))
        edit.AppendSeparator()
        edit.Append(220, _("&next error") + "\talt+Down", _("Go to next script error"))
        edit.Append(
            221, _("&previous error") + "\talt+Up", _("Go to previous script error")
        )
        edit.Append(
            222,
            _("check script errors") + "\tctrl+shift+e",
            _("Check and display all script errors"),
        )
        help.Append(901, _("about..."))
        menubar.Append(filemenu, _("&File"))
        menubar.Append(edit, _("&Edit"))
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
        self.Bind(wx.EVT_MENU, self.OnAbout, id=901)
        self.Bind(wx.EVT_MENU, self.OnNextError, id=220)
        self.Bind(wx.EVT_MENU, self.OnPreviousError, id=221)
        self.Bind(wx.EVT_MENU, self.OnCheckErrors, id=222)
        self.Bind(wx.EVT_FIND, self.on_find)
        # self.Bind(wx.EVT_FIND_NEXT, self.findnext)
        self.Bind(wx.EVT_FIND_REPLACE, self.on_replace)
        self.Bind(wx.EVT_FIND_REPLACE_ALL, self.on_find_replace_all)
        self.Bind(wx.EVT_KEY_DOWN, self.OnKeyDown)
        self.text = wx.TextCtrl(
            parent=self,
            id=1000,
            value="",
            size=(-1, -1),
            style=wx.TE_MULTILINE | wx.TE_PROCESS_ENTER | wx.TE_DONTWRAP,
        )
        self.text.Bind(wx.EVT_TEXT, self.OnTextChanged)
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

    def OnNewEmptyFile(self, event):
        file_name = os.path.basename(self.last_name_saved)
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
        self.defaultdir = config.getScratchpadDir(True) + os.sep + "appModules"
        self.defaultfile = _("untitled") + ".py"
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
                    sm_backend.createnewmodule("appModule", _("untitled"), False)
                )
            elif val == wx.ID_CANCEL:
                dlg.Destroy()
            else:
                self.DoNewEmptyFile()
                self.text.SetValue(
                    sm_backend.createnewmodule("appModule", _("untitled"), False)
                )
        else:
            self.DoNewEmptyFile()
            self.text.SetValue(
                sm_backend.createnewmodule("appModule", _("untitled"), False)
            )

    def OnNewGlobalPlugin(self, event):
        self.defaultdir = config.getScratchpadDir(True) + os.sep + "globalPlugins"
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
        self.defaultdir = (
            config.getScratchpadDir(True) + os.sep + "brailleDisplayDrivers"
        )
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
        self.defaultdir = config.getScratchpadDir(True) + os.sep + "synthDrivers"
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
        self.defaultdir = (
            config.getScratchpadDir(True) + os.sep + "visionEnhancementProviders"
        )
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
                dlg.script_category
            )
            
            # Leere Datei vorbereiten
            self.DoNewEmptyFile()
            
            # Script-Template einfügen
            self.text.SetValue(script_content)
            
            # Text als modifiziert markieren
            self.text.MarkDirty()
        
        dlg.Destroy()
    
    def _generateScriptTemplate(self, name, description, gesture, category):
        """Generiert ein Script-Template basierend auf den Eingaben."""
        # Script-Namen bereinigen (nur alphanumerisch und Unterstriche)
        clean_name = re.sub(r'[^a-zA-Z0-9_]', '_', name)
        clean_name = clean_name.lower()
        if not clean_name.startswith('script_'):
            clean_name = 'script_' + clean_name
        
        # Gesture formatieren (wenn vorhanden, sonst auskommentieren)
        if gesture:
            gesture_line = f',\n    gesture="{gesture}"'
        else:
            gesture_line = ''
        
        # Template basierend auf Beschreibung (einzeilig vs mehrzeilig)
        if '\n' in description:
            # Mehrzeilige Beschreibung mit Triple-Quotes
            desc_str = 'Description=_(\"\"\"%s\"\"\")' % description
            template = f'''@scriptHandler.script(
    {desc_str},
    category=_("{category}"){gesture_line}
)
def {clean_name}(self, gesture):
    """Script: {name}"""
    pass
'''
        else:
            # Einzeilige Beschreibung
            template = f'''@scriptHandler.script(
    description=_("{description}"),
    category=_("{category}"){gesture_line}
)
def {clean_name}(self, gesture):
    """Script: {name}"""
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
        ifd = insertfunctionsdialog(self, id=wx.ID_ANY, title=_("insert function"))
        if ifd.ShowModal() == wx.ID_OK:
            self.text.WriteText(ifd.functionstring)
            ifd.Destroy()

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
        dir = os.getcwd()
        try:
            open_dlg = wx.FileDialog(
                self,
                message=_("Choose a file"),
                defaultDir=dir,
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
            except error:
                dlg = wx.MessageDialog(self, _("Error saving file") + "\n" + str(error))
                dlg.ShowModal()
        else:
            self.OnSaveAsFile(event)

    def OnSaveAsFile(self, event):
        wcd = (
            _("All files(*.*)") + "|*.*|" + _("appmodule source files (*.py)") + "|*.py"
        )
        if hasattr(self, "defaultdir"):
            dir = self.defaultdir
        else:
            dir = os.getcwd()
        if hasattr(self, "defaultfile"):
            defaultfile = self.defaultfile
        else:
            defaultfile = _("untitled") + ".py"
        save_dlg = wx.FileDialog(
            self,
            message=_("Save file as..."),
            defaultDir=dir,
            defaultFile=defaultfile,
            wildcard=wcd,
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        )
        if save_dlg.ShowModal() == wx.ID_OK:
            path = save_dlg.GetPath()
            try:
                self.text.SaveFile(path)
                self.last_name_saved = os.path.basename(path)
                self.statusbar.SetStatusText(self.last_name_saved + " " + _("saved"), 0)
                self.statusbar.SetStatusText("", 1)
                self.Modify = False
            except error:
                dlg = wx.MessageDialog(self, _("Error saving file") + "\n" + str(error))
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
        
        self.errors, error_detail_str = sm_backend.check_script_for_errors(
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

    def _goto_error(self, error_index):
        """Springt zu einem Fehler mit gegebenem Index."""
        if error_index < 0 or error_index >= len(self.errors):
            return

        error = self.errors[error_index]
        line_num = error.get("line", 1)
        message = error.get("message", "Unknown error")
        error_type = error.get("type", "Error")

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
