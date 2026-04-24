import datetime
import sys
import os
import shutil
import time
import ast
import importlib
import typing
import math
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

# Fallback for analysis/runtime contexts where initTranslation does not expose _.
_ = globals().get("_", lambda text: text)


class _TextCallRef(object):
    """Text-based fallback reference for a method call in editor content."""

    __slots__ = ("start_pos", "end_pos", "args_start", "args_end", "func_text")

    def __init__(self, start_pos, end_pos, args_start, args_end, func_text):
        self.start_pos = int(start_pos)
        self.end_pos = int(end_pos)
        self.args_start = int(args_start)
        self.args_end = int(args_end)
        self.func_text = str(func_text or "")


def _ast_string_value(node):
    """Extract string value from an AST node (handles literals and _('...') calls)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if hasattr(ast, "Str") and isinstance(node, ast.Str):
        return node.s
    if isinstance(node, ast.Call):
        func = node.func
        if (isinstance(func, ast.Name) and func.id == "_"
                and len(node.args) == 1 and not node.keywords):
            return _ast_string_value(node.args[0])
    return ""


def _ast_bool_value(node):
    """Extract bool value from an AST node."""
    if isinstance(node, ast.Constant):
        return bool(node.value)
    if hasattr(ast, "NameConstant") and isinstance(node, ast.NameConstant):
        return bool(node.value)
    return False


def _ast_attribute_value(node):
    """Extract dotted attribute chain as string, e.g. 'sayAll.CURSOR_CARET'."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _ast_attribute_value(node.value)
        if parent:
            return f"{parent}.{node.attr}"
        return node.attr
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return ""


def _ast_value_to_python(node, source_text=""):
    """Convert an AST value node to a Python value, or a source string."""
    if isinstance(node, ast.Constant):
        return node.value
    if hasattr(ast, "Str") and isinstance(node, ast.Str):
        return node.s
    if hasattr(ast, "Num") and isinstance(node, ast.Num):
        return node.n
    if hasattr(ast, "NameConstant") and isinstance(node, ast.NameConstant):
        return node.value
    if isinstance(node, ast.Call):
        func = node.func
        if (isinstance(func, ast.Name) and func.id == "_"
                and len(node.args) == 1 and not node.keywords):
            return _ast_value_to_python(node.args[0], source_text)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        val = _ast_value_to_python(node.operand, source_text)
        if isinstance(val, (int, float)):
            return -val
    if source_text and hasattr(node, "lineno"):
        try:
            seg = ast.get_source_segment(source_text, node)
            if seg is not None:
                return seg
        except Exception:
            pass
    return None


def _get_call_func_name(func_node):
    """Get the dotted name string of a Call's function node, or None."""
    if isinstance(func_node, ast.Name):
        return func_node.id
    if isinstance(func_node, ast.Attribute):
        parent = _get_call_func_name(func_node.value)
        if parent is not None:
            return f"{parent}.{func_node.attr}"
    return None


def _build_import_alias_map(source_text, package_name=""):
    """Build an alias map from import statements in source_text."""
    alias_map = {}
    if not source_text:
        return alias_map
    try:
        tree = ast.parse(source_text)
    except Exception:
        return alias_map

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    alias_map[alias.asname] = alias.name
        elif isinstance(node, ast.ImportFrom):
            resolved_module = node.module or ""
            if node.level:
                if not package_name:
                    continue
                try:
                    resolved_module = importlib.util.resolve_name(
                        "." * node.level + (node.module or ""), package_name
                    )
                except Exception:
                    continue
            elif not resolved_module:
                continue
            for alias in node.names:
                if alias.name == "*":
                    continue
                if alias.asname:
                    alias_map[alias.asname] = f"{resolved_module}.{alias.name}"
    return alias_map


def _resolve_callable_by_name(name, source_text="", package_name=""):
    """Try to resolve a callable for a dotted name via modules and import aliases."""
    if not name:
        return None

    candidate_names = [name]
    alias_map = _build_import_alias_map(source_text, package_name)
    if alias_map:
        if "." in name:
            root, rest = name.split(".", 1)
            target = alias_map.get(root)
            if target:
                candidate_names.append(f"{target}.{rest}")
        else:
            target = alias_map.get(name)
            if target:
                candidate_names.append(target)

    seen = set()
    unique_candidates = []
    for cand in candidate_names:
        if cand in seen:
            continue
        seen.add(cand)
        unique_candidates.append(cand)

    for candidate in unique_candidates:
        parts = candidate.split(".")

        # First, try already loaded modules.
        for i in range(len(parts), 0, -1):
            module_key = ".".join(parts[:i])
            mod = sys.modules.get(module_key)
            if mod is None:
                continue
            obj = mod
            try:
                for attr in parts[i:]:
                    obj = getattr(obj, attr)
                if callable(obj):
                    return obj
            except AttributeError:
                continue

        # If not loaded yet, try importing module prefixes on demand.
        for i in range(len(parts), 0, -1):
            module_key = ".".join(parts[:i])
            try:
                mod = importlib.import_module(module_key)
            except Exception:
                continue
            obj = mod
            try:
                for attr in parts[i:]:
                    obj = getattr(obj, attr)
                if callable(obj):
                    return obj
            except AttributeError:
                continue

    return None


def _classify_param_for_dialog(param):
    """Classify an inspect.Parameter and return a pinfo dict for MethodCallEditDialog."""
    annotation = param.annotation
    default = param.default if param.default != inspect.Parameter.empty else None

    pinfo = {
        "default": default,
        "type": "str",
        "choices": [],
        "choices_raw": [],
        "min":-2 ** 16,
        "max": 2 ** 16,
        "required": (param.default == inspect.Parameter.empty),
        "pattern": None,
        "minLength": None,
        "maxLength": None,
        "allowEmpty": True,
        "raw_hint": None,
    }

    ann = annotation
    origin = typing.get_origin(ann)
    args = typing.get_args(ann)

    # Support typing.Annotated metadata for constraints.
    if origin is typing.Annotated and args:
        ann = args[0]
        origin = typing.get_origin(ann)
        args = typing.get_args(ann)
        for meta in args[1:]:
            if isinstance(meta, dict):
                if "required" in meta:
                    pinfo["required"] = bool(meta.get("required"))
                if "min" in meta:
                    pinfo["min"] = meta.get("min")
                if "max" in meta:
                    pinfo["max"] = meta.get("max")
                if "inc" in meta:
                    pinfo["inc"] = meta.get("inc")
                if "pattern" in meta:
                    pinfo["pattern"] = str(meta.get("pattern") or "")
                if "minLength" in meta:
                    pinfo["minLength"] = meta.get("minLength")
                if "maxLength" in meta:
                    pinfo["maxLength"] = meta.get("maxLength")
                if "allowEmpty" in meta:
                    pinfo["allowEmpty"] = bool(meta.get("allowEmpty"))
            elif isinstance(meta, str) and meta.startswith("regex:"):
                pinfo["pattern"] = meta[6:]

    if ann is inspect.Parameter.empty:
        if isinstance(default, bool):
            pinfo["type"] = "bool"
        elif isinstance(default, int):
            pinfo["type"] = "int"
        elif isinstance(default, float):
            pinfo["type"] = "float"
        return pinfo

    origin = typing.get_origin(ann)
    args = typing.get_args(ann)

    if origin is typing.Union:
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            ann = non_none[0]
            origin = typing.get_origin(ann)
            args = typing.get_args(ann)

    if origin is typing.Literal:
        choices_raw = list(args)
        choices_str = [str(c) for c in choices_raw]
        pinfo["type"] = "choices"
        pinfo["choices"] = choices_str
        pinfo["choices_raw"] = choices_raw
        return pinfo

    if ann is bool or ann == "bool":
        pinfo["type"] = "bool"
    elif ann is int or ann == "int":
        pinfo["type"] = "int"
    elif ann is float or ann == "float":
        pinfo["type"] = "float"
    elif ann is str or ann == "str":
        pinfo["type"] = "str"
    elif isinstance(ann, type) and issubclass(ann, int):
        try:
            members = [e.value for e in ann]
            if members:
                pinfo["type"] = "choices"
                pinfo["choices"] = [str(m) for m in members]
                pinfo["choices_raw"] = members
                return pinfo
        except Exception:
            pass
        pinfo["type"] = "int"
    else:
        # Complex type: list, dict, tuple, set, Any, or unknown → raw Python expression
        pinfo["type"] = "raw"
        if origin in (list, tuple, set):
            pinfo["raw_hint"] = origin.__name__
        elif origin is dict:
            pinfo["raw_hint"] = "dict"
        elif ann is list or ann == "list":
            pinfo["raw_hint"] = "list"
        elif ann is dict or ann == "dict":
            pinfo["raw_hint"] = "dict"
        elif ann is tuple or ann == "tuple":
            pinfo["raw_hint"] = "tuple"
        elif ann is set or ann == "set":
            pinfo["raw_hint"] = "set"
        elif hasattr(ann, "__name__"):
            pinfo["raw_hint"] = ann.__name__
        else:
            pinfo["raw_hint"] = str(ann)
    return pinfo


def _python_value_to_source(ptype, val, pinfo):
    """Convert a Python value to a source code string for the given param type."""
    if val is None:
        return None
    if ptype == "bool":
        return "True" if val else "False"
    if ptype == "int":
        try:
            return str(int(val))
        except (ValueError, TypeError):
            return None
    if ptype == "float":
        try:
            return repr(float(val))
        except (ValueError, TypeError):
            return None
    if ptype == "choices":
        choices_raw = pinfo.get("choices_raw", [])
        choices_str = pinfo.get("choices", [])
        val_str = str(val)
        for raw, s in zip(choices_raw, choices_str):
            if s == val_str:
                if isinstance(raw, str):
                    return repr(raw)
                return str(raw)
        return repr(val) if isinstance(val, str) else str(val)
    if ptype == "raw":
        # The value is already a verbatim Python expression string
        return str(val)
    # str
    return repr(str(val))


class insertfunctionsdialog(wx.Dialog):
    functionstring = ""

    def __init__(self, parent, dialogId, title, includeBlacklistedModules=False, translateDocstrings=False):
        super(insertfunctionsdialog, self).__init__(parent, dialogId, title)
        self.tree_initialized = False
        self.dialog_closed = False
        self.importstring = ""
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
                    except Exception:
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
                    
            except Exception:
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
                    except Exception:
                        pass
            except Exception:
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
                except Exception:
                    pass
        except Exception:
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

        self.importstring = ""
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
                self.importstring = f"import {module_name}"
                self.functionstring = self._format_function_call(module_name, item_text)
        # Method selected (child of a class)
        else:
            grandparent = self.tree.GetItemParent(parent)
            module_name = self.tree.GetItemText(grandparent)
            class_name = self.tree.GetItemText(parent)
            if item_data == "method":
                self.importstring = f"from {module_name} import {class_name}"
                self.functionstring = self._format_method_call(
                    module_name, class_name, item_text
                )

        self.EndModal(wx.ID_OK)

    def onCancel(self, event):
        self.functionstring = ""
        self.importstring = ""
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

    def _annotation_to_text(self, annotation):
        if annotation == inspect.Parameter.empty:
            return ""
        if isinstance(annotation, str):
            text = annotation
        elif hasattr(annotation, "__name__"):
            text = annotation.__name__
        else:
            text = str(annotation)

        text = text.replace("typing.", "")
        text = re.sub(r"^<class '(.+)'>$", r"\1", text)
        text = text.replace("NoneType", "None")

        union_match = re.match(r"Union\[(.+)\]$", text)
        if union_match:
            parts = [p.strip() for p in union_match.group(1).split(",") if p.strip()]
            if parts:
                text = " | ".join(parts)

        optional_match = re.match(r"Optional\[(.+)\]$", text)
        if optional_match:
            text = f"{optional_match.group(1).strip()} | None"

        return text

    def _build_signatures(self, target, display_name):
        sig = inspect.signature(target)
        required_call_params = []
        all_params = []

        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls"):
                continue

            type_annotation = self._annotation_to_text(param.annotation)
            name = param_name
            if param.kind == inspect.Parameter.VAR_POSITIONAL:
                name = f"*{name}"
            elif param.kind == inspect.Parameter.VAR_KEYWORD:
                name = f"**{name}"

            parameter_text = f"{type_annotation} {name}".strip() if type_annotation else name

            has_default = param.default != inspect.Parameter.empty
            is_optional = has_default or param.kind in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            )

            if not is_optional:
                # Keep inserted code as valid call syntax (no type prefixes like "str message").
                required_call_params.append(name)
                all_params.append(parameter_text)
            else:
                all_params.append(f"[{parameter_text}]")

        required_call = f"{display_name}({', '.join(required_call_params)})"
        syntax_line = f"Syntax: {display_name}({', '.join(all_params)})"
        return required_call, syntax_line

    def _build_help_with_syntax(self, doc_text, syntax_line):
        help_text = doc_text.strip() if doc_text else _("No help available")
        if not syntax_line:
            return help_text
        if re.search(r"^\s*syntax\s*:", help_text, re.IGNORECASE | re.MULTILINE):
            return help_text
        return f"{help_text}\n\n{syntax_line}" if help_text else syntax_line

    def _format_function_call(self, module_name, function_name):
        """Erzeugt einen Funktionsaufruf mit nur Pflichtparametern."""
        try:
            mod = sys.modules.get(module_name)
            if not mod or not hasattr(mod, function_name):
                return f"{module_name}.{function_name}()"

            func = getattr(mod, function_name)
            required_call, _ = self._build_signatures(
                func, f"{module_name}.{function_name}"
            )
            return required_call
        except Exception:
            return f"{module_name}.{function_name}()"

    def _format_function_syntax(self, module_name, function_name):
        try:
            mod = sys.modules.get(module_name)
            if not mod or not hasattr(mod, function_name):
                return f"Syntax: {function_name}()"
            func = getattr(mod, function_name)
            _, syntax_line = self._build_signatures(func, function_name)
            return syntax_line
        except Exception:
            return f"Syntax: {function_name}()"

    def _format_method_call(self, module_name, class_name, method_name):
        """Erzeugt einen Methodenaufruf mit nur Pflichtparametern."""
        try:
            mod = sys.modules.get(module_name)
            if not mod or not hasattr(mod, class_name):
                return f"{class_name}.{method_name}()"

            cls = getattr(mod, class_name)
            if not hasattr(cls, method_name):
                return f"{class_name}.{method_name}()"

            method = getattr(cls, method_name)
            required_call, _ = self._build_signatures(
                method, f"{class_name}.{method_name}"
            )
            return required_call
        except Exception:
            return f"{class_name}.{method_name}()"

    def _format_method_syntax(self, module_name, class_name, method_name):
        try:
            mod = sys.modules.get(module_name)
            if not mod or not hasattr(mod, class_name):
                return f"Syntax: {method_name}()"

            cls = getattr(mod, class_name)
            if not hasattr(cls, method_name):
                return f"Syntax: {method_name}()"

            method = getattr(cls, method_name)
            _, syntax_line = self._build_signatures(method, method_name)
            return syntax_line
        except Exception:
            return f"Syntax: {method_name}()"

    def on_selection_changed(self, event):
        # Schütze vor Aufrufen während der Initialisierung oder nach dem Schließen
        if self.dialog_closed:
            return

        # Überprüfe ob die Controls noch existieren
        try:
            if not self.tree or not self.help_text:
                return
        except Exception:
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
                        syntax_line = self._format_function_syntax(mod_name, func_name)
                        self._set_help_text(self._build_help_with_syntax(doc, syntax_line))
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
                            if item_data == "method":
                                syntax_line = self._format_method_syntax(mod_name, class_name, member_name)
                                self._set_help_text(self._build_help_with_syntax(doc, syntax_line))
                            elif doc:
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
    """Dialog for creating a new script or function definition."""

    SCRIPT_CATEGORY_KEYS = [
        "Miscellaneous",
        "Browse mode",
        "Emulated system keyboard keys",
        "Text review",
        "Object navigation",
        "System caret",
        "Mouse",
        "Speech",
        "Configuration",
        "Configuration profiles",
        "Braille",
        "Vision",
        "Tools",
        "Touch screen",
        "System focus",
        "System status",
        "Input",
        "Document formatting",
    ]
    SCRIPT_CATEGORIES = [_(categoryKey) for categoryKey in SCRIPT_CATEGORY_KEYS]
    DEFINITION_TYPE_SCRIPT = "script"
    DEFINITION_TYPE_FUNCTION = "function"
    TYPE_CHOICES = ["", "str", "int", "float", "bool", "list", "dict", "tuple", "set", "Any", "None"]

    @classmethod
    def normalizeCategoryForCode(cls, categoryText):
        """Return canonical (English) category for known NVDA categories."""
        categoryText = str(categoryText or "").strip()
        if not categoryText:
            return ""
        for categoryKey in cls.SCRIPT_CATEGORY_KEYS:
            translatedLabel = _(categoryKey)
            if categoryText == translatedLabel or categoryText == categoryKey:
                return categoryKey
        return categoryText

    @classmethod
    def localizeCategoryForDisplay(cls, categoryText):
        """Return localized label for known canonical category values."""
        categoryText = str(categoryText or "").strip()
        if not categoryText:
            return ""
        for categoryKey in cls.SCRIPT_CATEGORY_KEYS:
            translatedLabel = _(categoryKey)
            if categoryText == categoryKey or categoryText == translatedLabel:
                return translatedLabel
        return categoryText

    def __init__(self, parent, dialogId, title, initialDefinitionType="script", allowDefinitionTypeChange=True):
        super(newscriptdialog, self).__init__(parent, dialogId, title, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)

        self.definition_type = (
            initialDefinitionType
            if initialDefinitionType in (self.DEFINITION_TYPE_SCRIPT, self.DEFINITION_TYPE_FUNCTION)
            else self.DEFINITION_TYPE_SCRIPT
        )
        self.allowDefinitionTypeChange = bool(allowDefinitionTypeChange)
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
        self.function_name = ""
        self.function_return_type = ""
        self.function_params = []
        self.captured_key = None
        self.key_capture_active = False
        self.gesture_identifiers = []
        self._capture_mode = None
        self._capture_target_index = None
        self._active_capture_func = None

        mainSizer = wx.BoxSizer(wx.VERTICAL)
        sHelper = guiHelper.BoxSizerHelper(self, wx.VERTICAL)

        self.definition_type_ctrl = sHelper.addLabeledControl(
            _("Definition &type:"),
            wx.Choice,
            choices=[_("Script"), _("Function")],
        )
        self.name_ctrl = sHelper.addLabeledControl(_("Definition &name:"), wx.TextCtrl)

        self.script_panel = wx.Panel(self)
        scriptSizer = wx.BoxSizer(wx.VERTICAL)
        scriptHelper = guiHelper.BoxSizerHelper(self.script_panel, wx.VERTICAL)

        self.desc_ctrl = scriptHelper.addLabeledControl(
            _("&Description:"), wx.TextCtrl, style=wx.TE_MULTILINE | wx.TE_WORDWRAP
        )
        self.desc_ctrl.SetMinSize((300, 80))

        gestureSizer = wx.StaticBoxSizer(
            wx.StaticBox(self.script_panel, label=_("&Gestures:")), wx.VERTICAL
        )
        gestureRowSizer = wx.BoxSizer(wx.HORIZONTAL)
        self.gestures_list = wx.ListBox(self.script_panel, style=wx.LB_SINGLE)
        self.gestures_list.SetMinSize((320, 90))
        gestureButtonSizer = wx.BoxSizer(wx.VERTICAL)
        self.gesture_add_btn = wx.Button(self.script_panel, label=_("&Add (Ins)"))
        self.gesture_edit_btn = wx.Button(self.script_panel, label=_("&Edit"))
        self.gesture_delete_btn = wx.Button(self.script_panel, label=_("&Delete (Del)"))
        gestureButtonSizer.Add(self.gesture_add_btn, flag=wx.BOTTOM, border=5)
        gestureButtonSizer.Add(self.gesture_edit_btn, flag=wx.BOTTOM, border=5)
        gestureButtonSizer.Add(self.gesture_delete_btn)
        gestureRowSizer.Add(self.gestures_list, proportion=1, flag=wx.EXPAND)
        gestureRowSizer.AddSpacer(guiHelper.SPACE_BETWEEN_BUTTONS_HORIZONTAL)
        gestureRowSizer.Add(gestureButtonSizer, flag=wx.EXPAND)
        gestureSizer.Add(gestureRowSizer, proportion=1, flag=wx.EXPAND)
        self.gesture_status_ctrl = wx.TextCtrl(self.script_panel, style=wx.TE_READONLY)
        self.gesture_status_ctrl.SetValue(_("Press Add to capture a gesture."))
        gestureSizer.Add(
            self.gesture_status_ctrl,
            flag=wx.EXPAND | wx.TOP,
            border=guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_VERTICAL,
        )
        scriptHelper.addItem(gestureSizer, flag=wx.EXPAND)

        self.category_ctrl = scriptHelper.addLabeledControl(
            _("&Category:"),
            wx.ComboBox,
            choices=self.SCRIPT_CATEGORIES,
            value=self.SCRIPT_CATEGORIES[0] if self.SCRIPT_CATEGORIES else "",
            style=wx.CB_DROPDOWN,
        )

        advancedSizer = wx.StaticBoxSizer(
            wx.StaticBox(self.script_panel, label=_("Advanced script options")), wx.VERTICAL
        )
        advHelper = guiHelper.BoxSizerHelper(self.script_panel, sizer=advancedSizer)
        self.can_propagate_ctrl = advHelper.addItem(
            wx.CheckBox(self.script_panel, label=_("Script can &propagate to focus ancestors"))
        )
        self.bypass_input_help_ctrl = advHelper.addItem(
            wx.CheckBox(self.script_panel, label=_("&Bypass input help"))
        )
        self.allow_sleep_mode_ctrl = advHelper.addItem(
            wx.CheckBox(self.script_panel, label=_("Allow in &sleep mode"))
        )
        self.speak_on_demand_ctrl = advHelper.addItem(
            wx.CheckBox(self.script_panel, label=_("Speak in &on-demand mode"))
        )
        self.resume_say_all_ctrl = advHelper.addLabeledControl(
            _("&Resume say all mode:"),
            wx.ComboBox,
            choices=["", "sayAll.CURSOR_CARET", "sayAll.CURSOR_REVIEW"],
            value="",
            style=wx.CB_DROPDOWN,
        )
        scriptHelper.addItem(advancedSizer, flag=wx.EXPAND)
        scriptSizer.Add(scriptHelper.sizer, proportion=1, flag=wx.EXPAND)
        self.script_panel.SetSizer(scriptSizer)
        sHelper.addItem(self.script_panel, flag=wx.EXPAND, proportion=1)

        self.function_panel = wx.Panel(self)
        functionSizer = wx.BoxSizer(wx.VERTICAL)
        functionHelper = guiHelper.BoxSizerHelper(self.function_panel, wx.VERTICAL)
        self.return_type_ctrl = functionHelper.addLabeledControl(
            _("Return &type:"),
            wx.ComboBox,
            choices=self.TYPE_CHOICES,
            value="",
            style=wx.CB_DROPDOWN,
        )

        parameterSizer = wx.StaticBoxSizer(
            wx.StaticBox(self.function_panel, label=_("&Parameters")), wx.VERTICAL
        )
        parameterRowSizer = wx.BoxSizer(wx.HORIZONTAL)
        self.params_list = wx.ListBox(self.function_panel, style=wx.LB_SINGLE)
        self.params_list.SetMinSize((320, 110))
        parameterButtonSizer = wx.BoxSizer(wx.VERTICAL)
        self.param_add_btn = wx.Button(self.function_panel, label=_("&Add"))
        self.param_remove_btn = wx.Button(self.function_panel, label=_("&Remove"))
        parameterButtonSizer.Add(self.param_add_btn, flag=wx.BOTTOM, border=5)
        parameterButtonSizer.Add(self.param_remove_btn)
        parameterRowSizer.Add(self.params_list, proportion=1, flag=wx.EXPAND)
        parameterRowSizer.AddSpacer(guiHelper.SPACE_BETWEEN_BUTTONS_HORIZONTAL)
        parameterRowSizer.Add(parameterButtonSizer, flag=wx.EXPAND)
        parameterSizer.Add(parameterRowSizer, proportion=1, flag=wx.EXPAND)

        parameterEditHelper = guiHelper.BoxSizerHelper(self.function_panel, wx.VERTICAL)
        self.param_name_ctrl = parameterEditHelper.addLabeledControl(
            _("Parameter &name:"),
            wx.TextCtrl,
        )
        self.param_type_ctrl = parameterEditHelper.addLabeledControl(
            _("Parameter t&ype:"),
            wx.ComboBox,
            choices=self.TYPE_CHOICES,
            value="",
            style=wx.CB_DROPDOWN,
        )
        self.param_default_ctrl = parameterEditHelper.addLabeledControl(
            _("Default &value:"),
            wx.TextCtrl,
        )
        parameterSizer.Add(
            parameterEditHelper.sizer,
            flag=wx.EXPAND | wx.TOP,
            border=guiHelper.SPACE_BETWEEN_ASSOCIATED_CONTROL_VERTICAL,
        )
        functionHelper.addItem(parameterSizer, flag=wx.EXPAND, proportion=1)
        functionSizer.Add(functionHelper.sizer, proportion=1, flag=wx.EXPAND)
        self.function_panel.SetSizer(functionSizer)
        sHelper.addItem(self.function_panel, flag=wx.EXPAND, proportion=1)

        sHelper.addDialogDismissButtons(wx.OK | wx.CANCEL, separated=True)
        mainSizer.Add(sHelper.sizer, border=guiHelper.BORDER_FOR_DIALOGS, flag=wx.ALL | wx.EXPAND, proportion=1)
        self.SetSizer(mainSizer)
        mainSizer.Fit(self)
        self.SetMinSize((520, 420))
        self.SetSize((560, 520))

        self.Bind(wx.EVT_CHOICE, self.onDefinitionTypeChanged, self.definition_type_ctrl)
        self.Bind(wx.EVT_BUTTON, self.onAddGesture, self.gesture_add_btn)
        self.Bind(wx.EVT_BUTTON, self.onEditGesture, self.gesture_edit_btn)
        self.Bind(wx.EVT_BUTTON, self.onDeleteGesture, self.gesture_delete_btn)
        self.Bind(wx.EVT_LISTBOX, self.onGestureSelectionChanged, self.gestures_list)
        self.Bind(wx.EVT_LISTBOX_DCLICK, self.onEditGesture, self.gestures_list)
        self.Bind(wx.EVT_BUTTON, self.onAddParameter, self.param_add_btn)
        self.Bind(wx.EVT_BUTTON, self.onRemoveParameter, self.param_remove_btn)
        self.Bind(wx.EVT_LISTBOX, self.onParameterSelectionChanged, self.params_list)
        self.Bind(wx.EVT_BUTTON, self.onOk, id=wx.ID_OK)
        self.Bind(wx.EVT_BUTTON, self.onCancel, id=wx.ID_CANCEL)
        self.Bind(wx.EVT_CHAR_HOOK, self.onCharHook)
        self.Bind(wx.EVT_WINDOW_DESTROY, self.onDestroy)

        self._applyDefinitionTypeUI()
        self._updateGestureControlsState()
        self._updateParameterControlsState()
        self.name_ctrl.SetFocus()

    def _applyDefinitionTypeUI(self):
        is_script = self.definition_type == self.DEFINITION_TYPE_SCRIPT
        self.definition_type_ctrl.SetSelection(0 if is_script else 1)
        self.definition_type_ctrl.Enable(self.allowDefinitionTypeChange)
        self.script_panel.Show(is_script)
        self.function_panel.Show(not is_script)
        self.Layout()

    def onDefinitionTypeChanged(self, event):
        selection = self.definition_type_ctrl.GetSelection()
        self.definition_type = (
            self.DEFINITION_TYPE_FUNCTION if selection == 1 else self.DEFINITION_TYPE_SCRIPT
        )
        self._applyDefinitionTypeUI()
        event.Skip()

    def onAddGesture(self, event):
        """Start gesture capture for adding a shortcut."""
        if self.key_capture_active:
            self._stopCaptureGesture(canceled=True)
            return
        self._startCaptureGesture(mode="add")

    def onEditGesture(self, event):
        """Start gesture capture for editing the selected shortcut."""
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
        """Delete the selected shortcut."""
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
        self._updateGestureControlsState()
        event.Skip()

    def _startCaptureGesture(self, mode, targetIndex=None):
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
            if gesture.isModifier:
                return False
            inputCore.manager._captureFunc = None
            self._active_capture_func = None
            wx.CallAfter(self._handleCapturedGesture, gesture)
            return False

        self._active_capture_func = _captureFunc
        inputCore.manager._captureFunc = _captureFunc

    def _stopCaptureGesture(self, canceled=False, updateUI=True):
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
        hasSelection = self.gestures_list.GetSelection() != -1
        self.gesture_add_btn.Enable(True)
        self.gesture_edit_btn.Enable((not self.key_capture_active) and hasSelection)
        self.gesture_delete_btn.Enable((not self.key_capture_active) and hasSelection)
        self.gestures_list.Enable(not self.key_capture_active)

    def _handleCapturedGesture(self, gesture):
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

    def _formatParameterDisplay(self, param_data):
        text = str(param_data.get("name", "")).strip()
        param_type = str(param_data.get("type", "")).strip()
        default_value = str(param_data.get("default", "")).strip()
        if param_type:
            text += f": {param_type}"
        if default_value:
            text += f" = {default_value}"
        return text

    def _updateParameterControlsState(self):
        hasSelection = self.params_list.GetSelection() != wx.NOT_FOUND
        self.param_remove_btn.Enable(hasSelection)

    def _loadSelectedParameter(self):
        index = self.params_list.GetSelection()
        if index == wx.NOT_FOUND or index >= len(self.function_params):
            return
        param_data = self.function_params[index]
        self.param_name_ctrl.SetValue(str(param_data.get("name", "")))
        self.param_type_ctrl.SetValue(str(param_data.get("type", "")))
        self.param_default_ctrl.SetValue(str(param_data.get("default", "")))
        self._updateParameterControlsState()

    def onParameterSelectionChanged(self, event):
        self._loadSelectedParameter()
        event.Skip()

    def onAddParameter(self, event):
        param_name = self.param_name_ctrl.GetValue().strip()
        if not param_name:
            wx.MessageBox(
                _("Please enter a parameter name."),
                _("Missing Information"),
                wx.OK | wx.ICON_INFORMATION,
            )
            self.param_name_ctrl.SetFocus()
            return
        param_data = {
            "name": param_name,
            "type": self.param_type_ctrl.GetValue().strip(),
            "default": self.param_default_ctrl.GetValue().strip(),
        }
        selected_index = self.params_list.GetSelection()
        existing_index = next(
            (i for i, existing in enumerate(self.function_params) if existing.get("name") == param_name),
            wx.NOT_FOUND,
        )
        target_index = existing_index if existing_index != wx.NOT_FOUND else selected_index
        if target_index != wx.NOT_FOUND and 0 <= target_index < len(self.function_params):
            self.function_params[target_index] = param_data
        else:
            self.function_params.append(param_data)
            target_index = len(self.function_params) - 1
        self.params_list.Clear()
        for item in self.function_params:
            self.params_list.Append(self._formatParameterDisplay(item))
        self.params_list.SetSelection(target_index)
        self._loadSelectedParameter()
        self.params_list.SetFocus()

    def onRemoveParameter(self, event):
        index = self.params_list.GetSelection()
        if index == wx.NOT_FOUND or index >= len(self.function_params):
            return
        del self.function_params[index]
        self.params_list.Delete(index)
        if self.function_params:
            next_index = min(index, len(self.function_params) - 1)
            self.params_list.SetSelection(next_index)
            self._loadSelectedParameter()
        else:
            self.param_name_ctrl.SetValue("")
            self.param_type_ctrl.SetValue("")
            self.param_default_ctrl.SetValue("")
            self._updateParameterControlsState()

    def onCharHook(self, event):
        if not self.key_capture_active:
            key_code = event.GetKeyCode()
            if self.params_list.HasFocus() and key_code == wx.WXK_DELETE:
                self.onRemoveParameter(None)
                return
            if self.gestures_list.HasFocus():
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

        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self._stopCaptureGesture(canceled=True)
            return
        event.Skip()

    def _getDisplayTextForGestureIdentifier(self, identifier):
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
        if self.key_capture_active:
            self._stopCaptureGesture(canceled=True)

        if self.definition_type == self.DEFINITION_TYPE_FUNCTION:
            self.function_name = self.name_ctrl.GetValue().strip()
            self.function_return_type = self.return_type_ctrl.GetValue().strip()
            if self.param_name_ctrl.GetValue().strip():
                self.onAddParameter(None)
            if not self.function_name:
                wx.MessageBox(_("Please enter a definition name."), _("Missing Information"))
                self.name_ctrl.SetFocus()
                return
            self._safeEndModal(wx.ID_OK)
            return

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
        self.script_category = self.normalizeCategoryForCode(self.category_ctrl.GetValue())
        self.script_canPropagate = self.can_propagate_ctrl.GetValue()
        self.script_bypassInputHelp = self.bypass_input_help_ctrl.GetValue()
        self.script_allowInSleepMode = self.allow_sleep_mode_ctrl.GetValue()
        self.script_resumeSayAllMode = self.resume_say_all_ctrl.GetValue().strip()
        self.script_speakOnDemand = self.speak_on_demand_ctrl.GetValue()

        if not self.script_name:
            wx.MessageBox(_("Please enter a definition name."), _("Missing Information"))
            self.name_ctrl.SetFocus()
            return

        self._safeEndModal(wx.ID_OK)

    def onCancel(self, event):
        if self.key_capture_active:
            self._stopCaptureGesture(canceled=True)
        self._safeEndModal(wx.ID_CANCEL)

    def _safeEndModal(self, code):
        try:
            if self.IsModal():
                self.EndModal(code)
                return
        except Exception:
            pass
        try:
            self.SetReturnCode(code)
        except Exception:
            pass
        try:
            self.Close()
        except Exception:
            pass

    def onDestroy(self, event):
        if self.key_capture_active:
            self._stopCaptureGesture(canceled=True, updateUI=False)
        event.Skip()

    def populate_from_data(self, data):
        if not data:
            return
        self.definition_type = self.DEFINITION_TYPE_SCRIPT
        self._applyDefinitionTypeUI()
        name = data.get("name", "")
        if name:
            try:
                self.name_ctrl.SetValue(name)
            except Exception:
                pass
        description = data.get("description", "")
        if description is not None:
            try:
                self.desc_ctrl.SetValue(description)
            except Exception:
                pass
        category = data.get("category", "")
        if category is not None:
            try:
                self.category_ctrl.SetValue(self.localizeCategoryForDisplay(category))
            except Exception:
                pass
        gestures = data.get("gestures", [])
        gesture = data.get("gesture", "")
        if not gestures and gesture:
            gestures = [gesture]
        self.gesture_identifiers = []
        if gestures:
            try:
                self.gestures_list.Clear()
                for g in gestures:
                    if g:
                        self.gesture_identifiers.append(g)
                        self.gestures_list.Append(self._getDisplayTextForGestureIdentifier(g))
                if self.gestures_list.GetCount() > 0:
                    self.gestures_list.SetSelection(0)
            except Exception:
                pass
        for key, ctrl_name in [
            ("canPropagate", "can_propagate_ctrl"),
            ("bypassInputHelp", "bypass_input_help_ctrl"),
            ("allowInSleepMode", "allow_sleep_mode_ctrl"),
            ("speakOnDemand", "speak_on_demand_ctrl"),
        ]:
            val = data.get(key)
            if val is not None:
                try:
                    
                    ctrl = getattr(self, ctrl_name)
                    ctrl.SetValue(bool(val))
                except Exception:
                    pass
        resume_val = data.get("resumeSayAllMode")
        if resume_val is not None:
            try:
                self.resume_say_all_ctrl.SetValue(str(resume_val))
            except Exception:
                pass
        try:
            self._updateGestureControlsState()
        except Exception:
            pass


class addonmanifestdialog(wx.Dialog):

    UPDATE_CHANNEL_CHOICES = ["", "dev"]

    def __init__(self, parent, dialogId, title, defaults=None):
        super(addonmanifestdialog, self).__init__(
            parent,
            dialogId,
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


class AccessibleSpinCtrlDouble(wx.Panel):
    """NVDA-friendly floating-point spin control with an announced label."""

    def __init__(self, parent, label_text, initial_val=0.0, min_val=-1e9, max_val=1e9, inc=0.1):
        super().__init__(parent)
        self.min_val = float(min_val)
        self.max_val = float(max_val)
        try:
            self.inc = abs(float(inc))
        except (TypeError, ValueError):
            self.inc = 0.1
        if self.inc <= 0:
            self.inc = 0.1

        self._digits = self._get_digits_from_increment(self.inc)
        self._spin_min = int(math.floor(self.min_val / self.inc))
        self._spin_max = int(math.ceil(self.max_val / self.inc))

        value = self._clamp(self._parse_float(initial_val, default=0.0))
        spoken_label = str(label_text or "").replace("*", "").replace(":", "").strip()

        sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.label = wx.StaticText(self, label=label_text)
        sizer.Add(self.label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)

        self.text_ctrl = wx.TextCtrl(self, value=self._format_value(value))
        if spoken_label:
            self.text_ctrl.SetName(spoken_label)
        self.text_ctrl.SetMinSize((120, -1))
        sizer.Add(self.text_ctrl, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)

        self.spin_btn = wx.SpinButton(self, style=wx.SP_VERTICAL)
        self.spin_btn.SetRange(self._spin_min, self._spin_max)
        self.spin_btn.SetValue(self._value_to_position(value))
        sizer.Add(self.spin_btn, 0, wx.ALIGN_CENTER_VERTICAL)

        self.SetSizer(sizer)

        self.spin_btn.Bind(wx.EVT_SPIN, self._on_spin)
        self.text_ctrl.Bind(wx.EVT_TEXT, self._on_text_entry)
        self.text_ctrl.Bind(wx.EVT_KEY_DOWN, self._on_key_down)

    def _get_digits_from_increment(self, inc):
        text = ("{:.10f}").format(float(inc)).rstrip("0")
        if "." in text:
            return len(text.split(".", 1)[1])
        return 0

    def _format_value(self, value):
        return ("{0:." + str(self._digits) + "f}").format(float(value))

    def _parse_float(self, value, default=None):
        if isinstance(value, str):
            value = value.strip().replace(",", ".")
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _clamp(self, value):
        return max(self.min_val, min(self.max_val, float(value)))

    def _value_to_position(self, value):
        pos = int(round(float(value) / self.inc))
        return max(self._spin_min, min(self._spin_max, pos))

    def _set_numeric_value(self, value, notify=True):
        value = self._clamp(value)
        formatted = self._format_value(value)
        if notify:
            self.text_ctrl.SetValue(formatted)
        else:
            self.text_ctrl.ChangeValue(formatted)
        self.spin_btn.SetValue(self._value_to_position(value))
        return value

    def _adjust_value(self, steps):
        current = self._parse_float(self.text_ctrl.GetValue(), default=self.min_val)
        if current is None:
            current = self.min_val
        self._set_numeric_value(current + (steps * self.inc), notify=True)

    def _on_spin(self, event):
        value = self._clamp(event.GetPosition() * self.inc)
        self._set_numeric_value(value, notify=False)
        event.Skip()

    def _on_text_entry(self, event):
        value = self._parse_float(self.text_ctrl.GetValue(), default=None)
        if value is not None:
            self.spin_btn.SetValue(self._value_to_position(self._clamp(value)))
        event.Skip()

    def _on_key_down(self, event):
        key = event.GetKeyCode()
        if key == wx.WXK_UP:
            self._adjust_value(1)
            return
        if key == wx.WXK_DOWN:
            self._adjust_value(-1)
            return
        event.Skip()

    def GetValue(self):
        value = self._parse_float(self.text_ctrl.GetValue(), default=None)
        if value is None:
            return self.text_ctrl.GetValue()
        return self._clamp(value)

    def SetFocus(self):
        self.text_ctrl.SetFocus()


class MethodCallEditDialog(wx.Dialog):
    """Dynamic dialog for editing the parameters of a method call."""

    def __init__(self, parent, call_name, params_info, current_values):
        super().__init__(parent, title=_("Edit method call: {name}").format(name=call_name))
        self._params_info = params_info
        self._controls = {}
        self._validated_values = None
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        guiHelper.BoxSizerHelper(self, sizer=main_sizer)

        scroll = wx.ScrolledWindow(self, style=wx.VSCROLL)
        scroll.SetScrollRate(0, 20)
        scroll_sizer = wx.BoxSizer(wx.VERTICAL)

        for pinfo in params_info:
            pname = pinfo["name"]
            ptype = pinfo["type"]
            pdefault = pinfo.get("default")
            cur_val = current_values.get(pname, pdefault)

            label_text = pname + (" *:" if pinfo.get("required") else ":")
            if ptype != "float":
                label = wx.StaticText(scroll, label=label_text)
                scroll_sizer.Add(label, 0, wx.TOP | wx.LEFT, 6)

            if ptype == "bool":
                ctrl = wx.CheckBox(scroll)
                ctrl.SetValue(bool(cur_val) if cur_val is not None else False)
                scroll_sizer.Add(ctrl, 0, wx.LEFT | wx.BOTTOM, 6)

            elif ptype == "int":
                mn = pinfo.get("min", -2 ** 16)
                mx = pinfo.get("max", 2 ** 16)
                try:
                    init_val = int(cur_val) if cur_val is not None else (int(pdefault) if pdefault is not None else 0)
                except (ValueError, TypeError):
                    init_val = 0
                ctrl = wx.SpinCtrl(scroll, min=mn, max=mx, initial=init_val)
                scroll_sizer.Add(ctrl, 0, wx.LEFT | wx.BOTTOM, 6)

            elif ptype == "float":
                mn = float(pinfo.get("min", -1e9))
                mx = float(pinfo.get("max", 1e9))
                try:
                    init_val = float(cur_val) if cur_val is not None else (float(pdefault) if pdefault is not None else 0.0)
                except (ValueError, TypeError):
                    init_val = 0.0
                ctrl = AccessibleSpinCtrlDouble(
                    scroll,
                    label_text=label_text,
                    initial_val=init_val,
                    min_val=mn,
                    max_val=mx,
                    inc=pinfo.get("inc", 0.1),
                )
                scroll_sizer.Add(ctrl, 0, wx.TOP | wx.LEFT | wx.BOTTOM | wx.EXPAND, 6)

            elif ptype == "choices":
                choices = pinfo.get("choices", [])
                ctrl = wx.ComboBox(scroll, choices=choices, style=wx.CB_READONLY)
                cur_str = str(cur_val) if cur_val is not None else (str(pdefault) if pdefault is not None else "")
                if cur_str in choices:
                    ctrl.SetSelection(choices.index(cur_str))
                elif choices:
                    ctrl.SetSelection(0)
                scroll_sizer.Add(ctrl, 0, wx.LEFT | wx.BOTTOM | wx.EXPAND, 6)

            elif ptype == "raw":
                raw_hint = pinfo.get("raw_hint") or ""
                cur_str = str(cur_val) if cur_val is not None else (str(pdefault) if pdefault is not None else "")
                ctrl = wx.TextCtrl(
                    scroll,
                    value=cur_str,
                    style=wx.TE_MULTILINE | wx.TE_DONTWRAP,
                )
                ctrl.SetMinSize((-1, ctrl.GetCharHeight() * 4))
                if raw_hint:
                    ctrl.SetToolTip(_("{hint} (Python expression)").format(hint=raw_hint))
                scroll_sizer.Add(ctrl, 0, wx.LEFT | wx.BOTTOM | wx.EXPAND, 6)

            else:  # str
                cur_str = str(cur_val) if cur_val is not None else (str(pdefault) if pdefault is not None else "")
                ctrl = wx.TextCtrl(scroll, value=cur_str)
                scroll_sizer.Add(ctrl, 0, wx.LEFT | wx.BOTTOM | wx.EXPAND, 6)

            self._controls[pname] = ctrl

        scroll.SetSizer(scroll_sizer)
        scroll_sizer.FitInside(scroll)
        scroll.SetMinSize((400, min(500, scroll_sizer.GetMinSize().height + 20)))

        main_sizer.Add(scroll, 1, wx.EXPAND | wx.ALL, 8)
        btn_sizer = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        main_sizer.Add(btn_sizer, 0, wx.ALIGN_RIGHT | wx.ALL, 8)
        self.SetSizer(main_sizer)
        main_sizer.Fit(self)
        self.CenterOnParent()
        self.Bind(wx.EVT_BUTTON, self._on_ok, id=wx.ID_OK)

    def _on_ok(self, event):
        ok, values, errors = self.validate_values()
        if ok:
            self._validated_values = values
            self.EndModal(wx.ID_OK)
            return

        wx.Bell()
        msg = _("Please correct the following parameter errors:\n{errors}").format(
            errors="\n".join(errors)
        )
        wx.MessageBox(msg, _("Validation error"), wx.OK | wx.ICON_ERROR, self)

        if errors:
            first_name = errors[0].split(":", 1)[0]
            ctrl = self._controls.get(first_name)
            if ctrl is not None:
                ctrl.SetFocus()

    def get_values(self):
        """Return dict of {param_name: python_value} from controls."""
        if self._validated_values is not None:
            return dict(self._validated_values)

        result = {}
        for pinfo in self._params_info:
            pname = pinfo["name"]
            ptype = pinfo["type"]
            ctrl = self._controls.get(pname)
            if ctrl is None:
                continue
            if ptype == "bool":
                result[pname] = ctrl.GetValue()
            elif ptype == "int":
                result[pname] = ctrl.GetValue()
            elif ptype == "float":
                result[pname] = ctrl.GetValue()
            elif ptype == "choices":
                idx = ctrl.GetSelection()
                choices_raw = pinfo.get("choices_raw", [])
                choices_str = pinfo.get("choices", [])
                if 0 <= idx < len(choices_raw):
                    result[pname] = choices_raw[idx]
                elif 0 <= idx < len(choices_str):
                    result[pname] = choices_str[idx]
                else:
                    result[pname] = ctrl.GetValue()
            elif ptype == "raw":
                result[pname] = ctrl.GetValue().strip()
            else:
                result[pname] = ctrl.GetValue()
        return result

    def validate_values(self):
        """Validate current dialog values and return (ok, values, errors)."""
        values = self.get_values()
        errors = []

        for pinfo in self._params_info:
            pname = pinfo["name"]
            ptype = pinfo["type"]
            value = values.get(pname)

            if pinfo.get("required"):
                if ptype == "str" and str(value or "").strip() == "":
                    errors.append(_("{name}: value is required").format(name=pname))
                    continue

            if ptype == "int":
                try:
                    iv = int(value)
                except (TypeError, ValueError):
                    errors.append(_("{name}: invalid integer value").format(name=pname))
                    continue
                mn = pinfo.get("min")
                mx = pinfo.get("max")
                if mn is not None and iv < int(mn):
                    errors.append(_("{name}: must be >= {min}").format(name=pname, min=mn))
                if mx is not None and iv > int(mx):
                    errors.append(_("{name}: must be <= {max}").format(name=pname, max=mx))

            elif ptype == "float":
                try:
                    fv = float(value)
                except (TypeError, ValueError):
                    errors.append(_("{name}: invalid floating-point value").format(name=pname))
                    continue
                if not math.isfinite(fv):
                    errors.append(_("{name}: value must be finite").format(name=pname))
                    continue
                mn = pinfo.get("min")
                mx = pinfo.get("max")
                if mn is not None and fv < float(mn):
                    errors.append(_("{name}: must be >= {min}").format(name=pname, min=mn))
                if mx is not None and fv > float(mx):
                    errors.append(_("{name}: must be <= {max}").format(name=pname, max=mx))

            elif ptype == "str":
                sv = str(value or "")
                if not pinfo.get("allowEmpty", True) and sv.strip() == "":
                    errors.append(_("{name}: value must not be empty").format(name=pname))
                    continue

                min_len = pinfo.get("minLength")
                max_len = pinfo.get("maxLength")
                if min_len is not None and len(sv) < int(min_len):
                    errors.append(_("{name}: minimum length is {length}").format(name=pname, length=min_len))
                if max_len is not None and len(sv) > int(max_len):
                    errors.append(_("{name}: maximum length is {length}").format(name=pname, length=max_len))

                pattern = pinfo.get("pattern")
                if pattern and sv:
                    try:
                        if re.fullmatch(pattern, sv) is None:
                            errors.append(_("{name}: value does not match required pattern").format(name=pname))
                    except re.error:
                        errors.append(_("{name}: invalid validator pattern configuration").format(name=pname))

            elif ptype == "choices":
                choices_raw = pinfo.get("choices_raw", [])
                choices_str = pinfo.get("choices", [])
                if pinfo.get("required") and not choices_raw and str(value or "").strip() == "":
                    errors.append(_("{name}: value is required").format(name=pname))
                elif choices_raw and value not in choices_raw and str(value) not in choices_str:
                    errors.append(_("{name}: invalid selection").format(name=pname))

            elif ptype == "raw":
                sv = str(value or "").strip()
                if pinfo.get("required") and sv == "":
                    errors.append(_("{name}: value is required").format(name=pname))
                    continue
                if sv:
                    try:
                        ast.parse(sv, mode="eval")
                    except SyntaxError as exc:
                        errors.append(
                            _("{name}: invalid Python expression ({detail})").format(
                                name=pname, detail=str(exc.msg)
                            )
                        )

        return len(errors) == 0, values, errors


class EditorSettingsDialog(wx.Dialog):
    """Settings dialog for Script Manager editor behavior."""

    _JUMP_MODE_CHOICES = (
        ("scripts", _("scripts")),
        ("functionsOnly", _("functions only")),
        ("allDefinitions", _("all definitions")),
    )
    _TRANSLATION_OPTION_CHOICES = (
        ("translateDocstrings", _("Translate docstrings")),
        ("translateErrorMessages", _("Translate error messages")),
    )

    def __init__(self, parent):
        super(EditorSettingsDialog, self).__init__(
            parent,
            title=_("Settings"),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
        )

        mainSizer = wx.BoxSizer(wx.VERTICAL)
        sHelper = guiHelper.BoxSizerHelper(self, wx.VERTICAL)

        self.jumpModeChoice = sHelper.addLabeledControl(
            _("Definition &filter:"),
            wx.Choice,
            choices=[label for _value, label in self._JUMP_MODE_CHOICES],
        )
        current_jump_mode = sm_backend.get_jump_mode()
        selected_index = 0
        for index, (mode_value, _label) in enumerate(self._JUMP_MODE_CHOICES):
            if mode_value == current_jump_mode:
                selected_index = index
                break
        self.jumpModeChoice.SetSelection(selected_index)

        self.includeBlacklistCheckBox = sHelper.addItem(
            wx.CheckBox(
                self,
                label=_("Include module blacklist in 'Insert function' dialog"),
            )
        )
        self.includeBlacklistCheckBox.SetValue(sm_backend.get_include_blacklisted_modules())

        translation_values = {
            "translateDocstrings": sm_backend.get_translate_docstrings_enabled(),
            "translateErrorMessages": sm_backend.get_translate_error_messages_enabled(),
        }
        self.translationOptionCheckBoxes = {}
        translationSizer = wx.StaticBoxSizer(wx.VERTICAL, self, _("Translation &options"))
        for key, label in self._TRANSLATION_OPTION_CHOICES:
            checkBox = wx.CheckBox(self, label=label)
            checkBox.SetValue(bool(translation_values.get(key, False)))
            translationSizer.Add(checkBox, 0, wx.ALL, 5)
            self.translationOptionCheckBoxes[key] = checkBox
        sHelper.addItem(translationSizer)

        self.replaceTabsCheckBox = sHelper.addItem(
            wx.CheckBox(self, label=_("Replace tabs with &spaces"))
        )
        self.replaceTabsCheckBox.SetValue(sm_backend.get_indent_with_spaces_enabled())

        self.indentWidthSpin = sHelper.addLabeledControl(
            _("Spaces per &tab:"),
            wx.SpinCtrl,
            min=1,
            max=12,
            initial=sm_backend.get_indent_width(),
        )

        sHelper.addDialogDismissButtons(wx.OK | wx.CANCEL, separated=True)
        mainSizer.Add(sHelper.sizer, border=guiHelper.BORDER_FOR_DIALOGS, flag=wx.ALL | wx.EXPAND, proportion=1)
        self.SetSizer(mainSizer)
        mainSizer.Fit(self)

        self.Bind(wx.EVT_CHECKBOX, self._onReplaceTabsChanged, self.replaceTabsCheckBox)
        self._updateIndentControls()

    def _onReplaceTabsChanged(self, event):
        self._updateIndentControls()
        event.Skip()

    def _updateIndentControls(self):
        self.indentWidthSpin.Enable(self.replaceTabsCheckBox.GetValue())

    def getValues(self):
        selection = self.jumpModeChoice.GetSelection()
        if selection < 0 or selection >= len(self._JUMP_MODE_CHOICES):
            selection = 0
        jump_mode = self._JUMP_MODE_CHOICES[selection][0]
        translation_values = {
            key: checkbox.GetValue()
            for key, checkbox in self.translationOptionCheckBoxes.items()
        }
        return {
            "jumpMode": jump_mode,
            "includeBlacklistedModules": self.includeBlacklistCheckBox.GetValue(),
            "translateDocstrings": translation_values.get("translateDocstrings", False),
            "translateErrorMessages": translation_values.get("translateErrorMessages", False),
            "indentWithSpaces": self.replaceTabsCheckBox.GetValue(),
            "indentWidth": self.indentWidthSpin.GetValue(),
        }


class scriptmanager_mainwindow(wx.Frame):

    ID_OPEN_FILE = 101
    ID_SAVE_FILE = 102
    ID_SAVE_AS_FILE = 103
    ID_BUILD_ADDON = 104
    ID_QUIT = 105
    ID_CLOSE_FILE = 106
    ID_NEXT_TAB = 107
    ID_PREVIOUS_TAB = 108
    TAB_MENU_ID_BASE = 8000

    SCRATCHPAD_REQUIRED_MENU_IDS = (104, 111, 112, 113, 114, 115)
    _SCRATCHPAD_SUBDIR_BY_FILE_TYPE = {
        "appModule": "appModules",
        "globalPlugin": "globalPlugins",
        "brailleDisplayDriver": "brailleDisplayDrivers",
        "synthDriver": "synthDrivers",
        "visionEnhancementProvider": "visionEnhancementProviders",
    }
    _TITLE_FILE_TYPE_LABELS = {
        "empty": _("&empty file\tctrl+n"),
        "appModule": _("&appmodule"),
        "globalPlugin": _("&global plugin"),
        "brailleDisplayDriver": _("&braille display driver"),
        "synthDriver": _("&speech synthesizer driver"),
        "visionEnhancementProvider": _("&visual enhancement provider"),
    }
    JUMP_MODE_SCRIPTS = "scripts"
    JUMP_MODE_FUNCTIONS_ONLY = "functionsOnly"
    JUMP_MODE_ALL_DEFINITIONS = "allDefinitions"
    _JUMP_MODE_ORDER = (
        JUMP_MODE_SCRIPTS,
        JUMP_MODE_FUNCTIONS_ONLY,
        JUMP_MODE_ALL_DEFINITIONS,
    )
    _FOCUS_RETRY_DELAYS_MS = (0, 80, 200, 400)

    def __init__(self, parent, frameId, title, scriptfile):
        wx.Frame.__init__(self, parent, frameId, title)
        self._base_window_title = title or _("NVDA Script Manager")
        self._single_state = {
            "last_name_saved": "",
            "modify": False,
            "_current_file_type": "empty",
            "defaultdir": "",
            "defaultfile": _("untitled") + ".py",
            "errors": [],
            "current_error_index":-1,
            "replace": False,
        }

        menubar = wx.MenuBar()
        self.StatusBar()
        filemenu = wx.Menu()
        filenew = wx.Menu()
        edit = wx.Menu()
        scripts = wx.Menu()
        tabsMenu = wx.Menu()
        # view = wx.Menu()
        helpMenu = wx.Menu()
        filemenu.AppendSubMenu(filenew, _("&new"))
        filemenu.Append(self.ID_OPEN_FILE, _("&Open\tctrl+o"), _("Open an appmodule"))
        filemenu.Append(self.ID_SAVE_FILE, _("&Save\tctrl+s"), _("Save the appmodule"))
        filemenu.Append(
            self.ID_SAVE_AS_FILE, _("Save &as...\tctrl+shift+s"), _("Save the module as a new file"))
        filemenu.Append(self.ID_CLOSE_FILE, _("&Close file\tctrl+f4"), _("Close the current file tab"))
        filemenu.Append(self.ID_BUILD_ADDON, _("&build add-on..."), _("Create a distributable add-on from scratchpad contents"))
        filemenu.AppendSeparator()
        quitItem = wx.MenuItem(
            filemenu, self.ID_QUIT, _("&Quit\tAlt+F4"), _("Quit the Application"))
        filemenu.AppendItem(quitItem)
        filenew.Append(110, _("&empty file\tctrl+n"))
        filenew.Append(111, _("&appmodule"))
        filenew.Append(112, _("&global plugin"))
        filenew.Append(113, _("&braille display driver"))
        filenew.Append(114, _("&speech synthesizer driver"))
        filenew.Append(115, _("&visual enhancement provider"))
        edit.Append(200, _("&undo\tctrl+z"))
        edit.Append(212, _("&redo\tctrl+y"))
        edit.Append(201, _("cu&t\tctrl+x"))
        edit.Append(202, _("&copy\tctrl+c"))
        edit.Append(203, _("&paste\tctrl+v"))
        edit.Append(204, _("select &all\tctrl+a"))
        edit.Append(205, _("&delete\tDel"))
        edit.Append(206, _("&insert function...\tctrl+i"))
        edit.Append(213, _("insert &file...\tctrl+r"))
        edit.Append(214, _("save se&lection\tctrl+w"))
        edit.Append(215, _("se&ttings...\tctrl+,"), _("Configure Script Manager editor settings"))
        scripts.Append(223, _("&new definition...\tctrl+e"), _("Create a new script or function definition"))
        edit.Append(207, _("&find...\tctrl+f"))
        findnextitem = wx.MenuItem(edit, 208, _("find &next\tf3"))
        findnextitem.Enable(True)
        edit.AppendItem(findnextitem)
        findprevitem = wx.MenuItem(edit, 209, _("find previous\tshift+f3"))
        findprevitem.Enable(True)
        edit.AppendItem(findprevitem)
        edit.Append(210, _("r&eplace\tctrl+h"))
        edit.Append(211, _("go to &line...\tctrl+g"))
        scripts.Append(
            224,
            _("next definition\tf2"),
            _("Go to next definition"),
        )
        scripts.Append(
            225,
            _("previous definition\tshift+f2"),
            _("Go to previous definition"),
        )
        scripts.Append(
            236,
            _("next class definition\tctrl+f2"),
            _("Jump to next class definition"),
        )
        scripts.Append(
            237,
            _("previous class definition\tctrl+shift+f2"),
            _("Jump to previous class definition"),
        )
        scripts.Append(
            235,
            _("enclosing &class\talt+f2"),
            _("Jump to the enclosing class definition"),
        )
        # Definition filter is configured in Edit > Settings (Ctrl+,).
        scripts.Append(
            226,
            _("definition &list\tctrl+l"),
            _("Show all definitions with line numbers"),
        )
        scripts.Append(
            227,
            _("&delete definition\tctrl+d"),
            _("Delete the current definition"),
        )
        scripts.AppendSeparator()
        scripts.Append(
            229,
            _("script &properties...\tAlt+Return"),
            _("Edit the @script decorator of the current script"),
        )
        scripts.Append(
            230,
            _("edit method &call\tF4"),
            _("Edit the parameters of the method call at the cursor"),
        )
        edit.AppendSeparator()
        scripts.Append(220, _("&next error\talt+Down"), _("Go to next script error"))
        scripts.Append(
            221, _("&previous error\talt+Up"), _("Go to previous script error")
        )
        scripts.Append(
            222,
            _("check script errors\tctrl+shift+e"),
            _("Check and display all script errors"),
        )
        scripts.Append(
            228,
            _("error &list\tctrl+shift+l"),
            _("Show all errors in a list"),
        )
        helpMenu.Append(901, _("&about..."))
        menubar.Append(filemenu, _("&File"))
        menubar.Append(edit, _("&Edit"))
        menubar.Append(scripts, _('&Scripts'))
        menubar.Append(tabsMenu, _("&Tabs"))
        menubar.Append(helpMenu, _("&Help"))
        self.tabsMenu = tabsMenu
        self.SetMenuBar(menubar)
        self.Centre()
        self.Bind(wx.EVT_MENU, self.OnQuit, id=self.ID_QUIT)
        self.Bind(wx.EVT_MENU, self.OnCloseFile, id=self.ID_CLOSE_FILE)
        self.Bind(wx.EVT_MENU, self.OnNewEmptyFile, id=110)
        self.Bind(wx.EVT_MENU, self.OnNewAppModule, id=111)
        self.Bind(wx.EVT_MENU, self.OnNewGlobalPlugin, id=112)
        self.Bind(wx.EVT_MENU, self.OnNewBrailleDisplayDriver, id=113)
        self.Bind(wx.EVT_MENU, self.OnNewSynthDriver, id=114)
        self.Bind(wx.EVT_MENU, self.OnNewVisionEnhancementProvider, id=115)
        self.Bind(wx.EVT_MENU, self.OnOpenFile, id=self.ID_OPEN_FILE)
        self.Bind(wx.EVT_MENU, self.OnSaveFile, id=self.ID_SAVE_FILE)
        self.Bind(wx.EVT_MENU, self.OnSaveAsFile, id=self.ID_SAVE_AS_FILE)
        self.Bind(wx.EVT_MENU, self.OnNextTab, id=self.ID_NEXT_TAB)
        self.Bind(wx.EVT_MENU, self.OnPreviousTab, id=self.ID_PREVIOUS_TAB)
        self.Bind(wx.EVT_MENU, self.OnSelectTabFromMenu, id=self.TAB_MENU_ID_BASE, id2=self.TAB_MENU_ID_BASE + 999)
        self.SetAcceleratorTable(
            wx.AcceleratorTable(
                [
                    (wx.ACCEL_CTRL, ord("S"), self.ID_SAVE_FILE),
                    (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord("S"), self.ID_SAVE_AS_FILE),
                    (wx.ACCEL_CTRL, wx.WXK_F4, self.ID_CLOSE_FILE),
                    (wx.ACCEL_CTRL, wx.WXK_TAB, self.ID_NEXT_TAB),
                    (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, wx.WXK_TAB, self.ID_PREVIOUS_TAB),
                    (wx.ACCEL_ALT, ord("1"), self._get_tab_menu_id_for_index(0)),
                    (wx.ACCEL_ALT, ord("2"), self._get_tab_menu_id_for_index(1)),
                    (wx.ACCEL_ALT, ord("3"), self._get_tab_menu_id_for_index(2)),
                    (wx.ACCEL_ALT, ord("4"), self._get_tab_menu_id_for_index(3)),
                    (wx.ACCEL_ALT, ord("5"), self._get_tab_menu_id_for_index(4)),
                    (wx.ACCEL_ALT, ord("6"), self._get_tab_menu_id_for_index(5)),
                    (wx.ACCEL_ALT, ord("7"), self._get_tab_menu_id_for_index(6)),
                    (wx.ACCEL_ALT, ord("8"), self._get_tab_menu_id_for_index(7)),
                    (wx.ACCEL_ALT, ord("9"), self._get_tab_menu_id_for_index(8)),
                    (wx.ACCEL_ALT, ord("0"), self._get_tab_menu_id_for_index(9)),
                    (wx.ACCEL_CTRL, ord("I"), 206),
                    (wx.ACCEL_CTRL, ord("R"), 213),
                    (wx.ACCEL_CTRL, ord("W"), 214),
                    (wx.ACCEL_CTRL, ord(","), 215),
                    (wx.ACCEL_CTRL, ord("L"), 226),
                    (wx.ACCEL_CTRL, ord("D"), 227),
                    (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord("L"), 228),
                    (wx.ACCEL_ALT, wx.WXK_RETURN, 229),
                    (wx.ACCEL_ALT, getattr(wx, "WXK_NUMPAD_ENTER", wx.WXK_RETURN), 229),
                    (wx.ACCEL_ALT, wx.WXK_F2, 235),
                ]
            )
        )
        self.Bind(wx.EVT_MENU, self.OnCreateAddon, id=self.ID_BUILD_ADDON)
        self.Bind(wx.EVT_MENU, self.OnUndo, id=200)
        self.Bind(wx.EVT_MENU, self.OnRedo, id=212)
        self.Bind(wx.EVT_MENU, self.OnCut, id=201)
        self.Bind(wx.EVT_MENU, self.OnCopy, id=202)
        self.Bind(wx.EVT_MENU, self.OnPaste, id=203)
        self.Bind(wx.EVT_MENU, self.OnDelete, id=204)
        self.Bind(wx.EVT_MENU, self.OnSelectAll, id=205)
        self.Bind(wx.EVT_MENU, self.OnInsertFunction, id=206)
        self.Bind(wx.EVT_MENU, self.OnInsertFile, id=213)
        self.Bind(wx.EVT_MENU, self.OnSaveSelection, id=214)
        self.Bind(wx.EVT_MENU, self.OnSettings, id=215)
        self.Bind(wx.EVT_MENU, self.OnNewScript, id=223)
        self.Bind(wx.EVT_MENU, self.OnFinditem, id=207)
        self.Bind(wx.EVT_MENU, self.OnFindnextitem, id=208)
        self.Bind(wx.EVT_MENU, self.OnFindpreviousitem, id=209)
        self.Bind(wx.EVT_MENU, self.OnReplaceitem, id=210)
        self.Bind(wx.EVT_MENU, self.OnGotoLineItem, id=211)
        self.Bind(wx.EVT_MENU, self.OnNextScriptDefinition, id=224)
        self.Bind(wx.EVT_MENU, self.OnPreviousScriptDefinition, id=225)
        self.Bind(wx.EVT_MENU, self.OnNextClassDefinition, id=236)
        self.Bind(wx.EVT_MENU, self.OnPreviousClassDefinition, id=237)
        
        self.Bind(wx.EVT_MENU, self.OnGotoEnclosingClass, id=235)
        self.Bind(wx.EVT_MENU, self.OnSetJumpModeScripts, id=232)
        self.Bind(wx.EVT_MENU, self.OnSetJumpModeFunctionsOnly, id=233)
        self.Bind(wx.EVT_MENU, self.OnSetJumpModeAllDefinitions, id=234)
        self.Bind(wx.EVT_MENU, self.OnShowScriptList, id=226)
        self.Bind(wx.EVT_MENU, self.OnDeleteCurrentScriptDefinition, id=227)
        self.Bind(wx.EVT_MENU, self.OnScriptProperties, id=229)
        self.Bind(wx.EVT_MENU, self.OnEditMethodCall, id=230)
        self.Bind(wx.EVT_MENU, self.OnAbout, id=901)
        self.Bind(wx.EVT_MENU, self.OnNextError, id=220)
        self.Bind(wx.EVT_MENU, self.OnPreviousError, id=221)
        self.Bind(wx.EVT_MENU, self.OnCheckErrors, id=222)
        self.Bind(wx.EVT_MENU, self.OnShowErrorList, id=228)
        self.Bind(wx.EVT_FIND, self.on_find)
        self.Bind(wx.EVT_FIND_CLOSE, self.on_find_close)
        # self.Bind(wx.EVT_FIND_NEXT, self.findnext)
        self.Bind(wx.EVT_FIND_REPLACE, self.on_replace)
        self.Bind(wx.EVT_FIND_REPLACE_ALL, self.on_find_replace_all)
        self.Bind(wx.EVT_KEY_DOWN, self.OnKeyDown)
        self.Bind(wx.EVT_ACTIVATE, self._onWindowActivate)
        self.Bind(wx.EVT_MENU_OPEN, self._onMenuOpen)
        self.notebook = wx.Notebook(self, id=1001)
        self.notebook.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self._onNotebookPageChanged)
        self.text = self._create_editor_control()
        self.notebook.AddPage(self.text, _("untitled"), True)
        self._initialize_editor_state(
            self.text,
            file_path="",
            file_type="empty",
            default_dir=self._get_default_file_dialog_dir(),
            default_file=_("untitled") + ".py",
        )
        if scriptfile != "":
            self.text.LoadFile(scriptfile)
            self._initialize_editor_state(
                self.text,
                file_path=scriptfile,
                file_type=self._detect_file_type_from_path(scriptfile),
                default_dir=os.path.dirname(scriptfile),
                default_file=os.path.basename(scriptfile),
            )
            self.text.SetModified(False)
        self.modify = False
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.notebook, 1, wx.EXPAND)
        self.SetSizer(sizer)
        self._update_window_title()
        self._update_tab_label(self.text)
        self.text.SelectNone()
        self.text.SetFocus()
        self._update_caret_status()
        # Error-Liste Initialisierung
        self.errors = []
        self.current_error_index = -1
        self.replace = False
        self._jump_mode = sm_backend.get_jump_mode()
        self._update_jump_mode_menu_checks()
        # Aktiviere Error Logging für das aktuelle Script
        sm_backend.activate_error_logging(scriptfile if scriptfile else None)
        self._update_scratchpad_required_menu_state()
        self._rebuild_tabs_menu()

    def _create_editor_control(self):
        text_ctrl = wx.TextCtrl(
            parent=self.notebook,
            id=wx.ID_ANY,
            value="",
            size=(-1, -1),
            style=wx.TE_MULTILINE | wx.TE_PROCESS_ENTER | wx.TE_DONTWRAP,
        )
        # Capture shortcuts while editor has focus (e.g. Alt+Enter / F4).
        text_ctrl.Bind(wx.EVT_KEY_DOWN, self.OnKeyDown)
        text_ctrl.Bind(wx.EVT_KEY_UP, self.OnTextCaretChanged)
        text_ctrl.Bind(wx.EVT_LEFT_UP, self.OnTextCaretChanged)
        text_ctrl.Bind(wx.EVT_SET_FOCUS, self.OnTextCaretChanged)
        text_ctrl.Bind(wx.EVT_TEXT, self.OnTextChanged)
        return text_ctrl

    def _get_next_unsaved_default_file_name(self, requested_name=""):
        requested = os.path.basename(str(requested_name or _("untitled") + ".py"))
        base_name, extension = os.path.splitext(requested)
        extension = extension or ".py"
        untitled_base = _("untitled")

        used_names = set()
        notebook = getattr(self, "notebook", None)
        if notebook is not None:
            for index in range(notebook.GetPageCount()):
                editor = notebook.GetPage(index)
                state = getattr(editor, "_sm_state", None) or {}
                if state.get("last_name_saved"):
                    continue
                used_name = os.path.basename(str(state.get("defaultfile") or "")).lower()
                if used_name:
                    used_names.add(used_name)

        if base_name == untitled_base:
            pattern = re.compile(
                r"^{base}(?: (\\d+))?{ext}$".format(
                    base=re.escape(untitled_base.lower()),
                    ext=re.escape(extension.lower()),
                )
            )
            next_index = 1
            for used_name in used_names:
                match = pattern.match(used_name)
                if not match:
                    continue
                used_index = int(match.group(1) or "1")
                next_index = max(next_index, used_index + 1)
            return "{base} {index}{ext}".format(
                base=untitled_base,
                index=next_index,
                ext=extension,
            )

        if requested.lower() not in used_names:
            return requested

        suffix = 2
        while True:
            candidate = "{base} {index}{ext}".format(
                base=base_name,
                index=suffix,
                ext=extension,
            )
            if candidate.lower() not in used_names:
                return candidate
            suffix += 1

    def _initialize_editor_state(self, editor, file_path="", file_type="empty", default_dir="", default_file=""):
        default_file_name = default_file or _("untitled") + ".py"
        if not file_path:
            default_file_name = self._get_next_unsaved_default_file_name(default_file_name)
        editor._sm_state = {
            "last_name_saved": file_path or "",
            "modify": False,
            "_current_file_type": file_type or "empty",
            "defaultdir": default_dir or self._get_default_file_dialog_dir(),
            "defaultfile": default_file_name,
            "errors": [],
            "current_error_index":-1,
            "replace": False,
        }

    def _get_active_editor(self):
        notebook = getattr(self, "notebook", None)
        if notebook and notebook.GetPageCount() > 0:
            page = notebook.GetCurrentPage()
            if page is not None:
                return page
        return getattr(self, "text", None)

    def _get_active_editor_state(self):
        editor = self._get_active_editor()
        if editor is not None and hasattr(editor, "_sm_state"):
            return editor._sm_state
        return self._single_state

    def _get_state_value(self, key, default=None):
        return self._get_active_editor_state().get(key, default)

    def _set_state_value(self, key, value):
        self._get_active_editor_state()[key] = value

    @property
    def last_name_saved(self):
        return self._get_state_value("last_name_saved", "")

    @last_name_saved.setter
    def last_name_saved(self, value):
        self._set_state_value("last_name_saved", value or "")

    @property
    def modify(self):
        return bool(self._get_state_value("modify", False))

    @modify.setter
    def modify(self, value):
        self._set_state_value("modify", bool(value))

    @property
    def _current_file_type(self):
        return self._get_state_value("_current_file_type", "empty")

    @_current_file_type.setter
    def _current_file_type(self, value):
        self._set_state_value("_current_file_type", value or "empty")

    @property
    def defaultdir(self):
        return self._get_state_value("defaultdir", self._get_default_file_dialog_dir())

    @defaultdir.setter
    def defaultdir(self, value):
        self._set_state_value("defaultdir", value or self._get_default_file_dialog_dir())

    @property
    def defaultfile(self):
        return self._get_state_value("defaultfile", _("untitled") + ".py")

    @defaultfile.setter
    def defaultfile(self, value):
        self._set_state_value("defaultfile", value or _("untitled") + ".py")

    @property
    def errors(self):
        return self._get_state_value("errors", [])

    @errors.setter
    def errors(self, value):
        self._set_state_value("errors", list(value) if value else [])

    @property
    def current_error_index(self):
        return int(self._get_state_value("current_error_index", -1))

    @current_error_index.setter
    def current_error_index(self, value):
        self._set_state_value("current_error_index", int(value))

    @property
    def replace(self):
        return bool(self._get_state_value("replace", False))

    @replace.setter
    def replace(self, value):
        self._set_state_value("replace", bool(value))

    def _get_editor_title_filename(self, editor):
        state = getattr(editor, "_sm_state", self._single_state)
        if state.get("last_name_saved"):
            file_name = os.path.basename(state["last_name_saved"])
            label, _extension = os.path.splitext(file_name)
            return label or file_name
        default_name = os.path.basename(str(state.get("defaultfile") or ""))
        if default_name:
            label, _extension = os.path.splitext(default_name)
            return label or default_name
        return _("untitled")

    def _get_notebook_page_index(self, editor):
        notebook = getattr(self, "notebook", None)
        if notebook is None or editor is None:
            return -1
        if hasattr(notebook, "GetPageIndex"):
            try:
                return notebook.GetPageIndex(editor)
            except Exception:
                pass
        if hasattr(notebook, "FindPage"):
            try:
                return notebook.FindPage(editor)
            except Exception:
                pass
        try:
            page_count = notebook.GetPageCount()
        except Exception:
            return -1
        for index in range(page_count):
            try:
                if notebook.GetPage(index) is editor:
                    return index
            except Exception:
                continue
        return -1

    def _update_tab_label(self, editor):
        page_index = self._get_notebook_page_index(editor)
        if page_index < 0:
            return
        label = self._get_editor_title_filename(editor)
        if editor.IsModified():
            label = "* " + label
        self.notebook.SetPageText(page_index, label)

    def _get_tab_shortcut_suffix(self, index):
        if 0 <= index <= 8:
            return "\tAlt+{n}".format(n=index + 1)
        if index == 9:
            return "\tAlt+0"
        return ""

    def _get_tab_menu_id_for_index(self, index):
        return self.TAB_MENU_ID_BASE + int(index)

    def _rebuild_tabs_menu(self):
        if not hasattr(self, "tabsMenu") or self.tabsMenu is None:
            return
        for item in list(self.tabsMenu.GetMenuItems()):
            self.tabsMenu.DestroyItem(item)

        page_count = self.notebook.GetPageCount() if hasattr(self, "notebook") else 0
        if page_count <= 0:
            no_tabs_item = self.tabsMenu.Append(wx.ID_ANY, _("(no open files)"))
            no_tabs_item.Enable(False)
            return

        current_selection = self.notebook.GetSelection()
        for index in range(page_count):
            editor = self.notebook.GetPage(index)
            label = self._get_editor_title_filename(editor)
            label += self._get_tab_shortcut_suffix(index)
            menu_item = self.tabsMenu.Append(self._get_tab_menu_id_for_index(index), label)
            if index == current_selection:
                menu_item.SetItemLabel(_("{label} (current)").format(label=label))

    def _onNotebookPageChanged(self, event):
        self.text = self._get_active_editor()
        self._update_window_title()
        self._update_caret_status()
        self._update_edit_menu_state()
        self._rebuild_tabs_menu()
        event.Skip()

    def _find_tab_index_by_path(self, path):
        normalized_target = os.path.abspath(str(path or ""))
        if not normalized_target:
            return -1
        for index in range(self.notebook.GetPageCount()):
            editor = self.notebook.GetPage(index)
            state = getattr(editor, "_sm_state", None) or {}
            saved_path = str(state.get("last_name_saved") or "")
            if saved_path and os.path.abspath(saved_path) == normalized_target:
                return index
        return -1

    def _open_file_in_new_tab(self, path):
        existing_index = self._find_tab_index_by_path(path)
        if existing_index >= 0:
            self.notebook.SetSelection(existing_index)
            self.text = self._get_active_editor()
            self.text.SetFocus()
            self._update_window_title()
            return False

        current_editor = self._get_active_editor()
        current_state = getattr(current_editor, "_sm_state", None) or {}
        can_reuse_current = (
            self.notebook.GetPageCount() == 1
            and current_editor is not None
            and not current_editor.IsModified()
            and not str(current_state.get("last_name_saved") or "")
            and not current_editor.GetValue()
        )
        if can_reuse_current:
            current_editor.LoadFile(path)
            self._initialize_editor_state(
                current_editor,
                file_path=path,
                file_type=self._detect_file_type_from_path(path),
                default_dir=os.path.dirname(path),
                default_file=os.path.basename(path),
            )
            current_editor.SetModified(False)
            self.text = current_editor
            self.modify = False
            self.text.SetSelection(0, 0)
            self._update_tab_label(current_editor)
            self._update_window_title()
            self._update_caret_status()
            self._rebuild_tabs_menu()
            self.text.SetFocus()
            return True

        editor = self._create_editor_control()
        editor.LoadFile(path)
        self._initialize_editor_state(
            editor,
            file_path=path,
            file_type=self._detect_file_type_from_path(path),
            default_dir=os.path.dirname(path),
            default_file=os.path.basename(path),
        )
        editor.SetModified(False)
        self.notebook.AddPage(editor, os.path.basename(path), True)
        self.text = editor
        self.modify = False
        self.text.SetSelection(0, 0)
        self._update_tab_label(editor)
        self._update_window_title()
        self._update_caret_status()
        self._rebuild_tabs_menu()
        self.text.SetFocus()
        return True

    def _ensure_empty_tab_if_needed(self):
        if self.notebook.GetPageCount() > 0:
            return
        self.text = self._create_editor_control()
        self.notebook.AddPage(self.text, _("untitled"), True)
        self._initialize_editor_state(
            self.text,
            file_path="",
            file_type="empty",
            default_dir=self._get_default_file_dialog_dir(),
            default_file=_("untitled") + ".py",
        )
        self._update_tab_label(self.text)

    def _create_new_editor_tab(self, file_type="empty", default_file=None, content=""):
        editor = self._create_editor_control()
        self._initialize_editor_state(
            editor,
            file_path="",
            file_type=file_type,
            default_dir=self._get_default_dir_for_file_type(file_type),
            default_file=default_file or _("untitled") + ".py",
        )
        self.notebook.AddPage(editor, self._get_editor_title_filename(editor), True)
        self.text = editor
        if content:
            self.text.SetValue(content)
        else:
            self.text.SetModified(False)
            self.modify = False
        self.text.SetSelection(0, 0)
        self._update_tab_label(editor)
        self._update_window_title()
        self._update_caret_status()
        self._rebuild_tabs_menu()
        self.text.SetFocus()
        return editor

    def _confirm_save_for_active_tab(self, event=None):
        if not self._has_unsaved_changes():
            return True
        file_name = self._get_current_title_filename()
        dlg = wx.MessageDialog(
            self,
            _("Save changes to {name}?").format(name=file_name),
            "",
            wx.YES_NO | wx.YES_DEFAULT | wx.CANCEL | wx.ICON_QUESTION,
        )
        val = dlg.ShowModal()
        dlg.Destroy()
        if val == wx.ID_YES:
            return bool(self.OnSaveFile(event))
        if val == wx.ID_CANCEL:
            return False
        return True

    def _close_active_tab(self, event=None):
        if not self._confirm_save_for_active_tab(event):
            return False
        selection = self.notebook.GetSelection()
        if selection < 0:
            return True
        self.notebook.DeletePage(selection)
        self._ensure_empty_tab_if_needed()
        self.text = self._get_active_editor()
        self._update_window_title()
        self._update_caret_status()
        self._rebuild_tabs_menu()
        if self.text is not None:
            self.text.SetFocus()
        return True

    def OnCloseFile(self, event):
        self._close_active_tab(event)

    def OnNextTab(self, event):
        page_count = self.notebook.GetPageCount()
        if page_count <= 1:
            return
        current = self.notebook.GetSelection()
        self.notebook.SetSelection((current + 1) % page_count)

    def OnPreviousTab(self, event):
        page_count = self.notebook.GetPageCount()
        if page_count <= 1:
            return
        current = self.notebook.GetSelection()
        self.notebook.SetSelection((current - 1) % page_count)

    def OnSelectTabFromMenu(self, event):
        menu_id = event.GetId()
        index = int(menu_id) - self.TAB_MENU_ID_BASE
        if index < 0:
            return
        if index >= self.notebook.GetPageCount():
            wx.Bell()
            return
        self.notebook.SetSelection(index)

    def _has_unsaved_changes(self):
        try:
            return bool(self.text.IsModified())
        except Exception:
            return bool(getattr(self, "modify", False))

    def _get_current_title_filename(self):
        if self.last_name_saved:
            return os.path.basename(self.last_name_saved)
        default_file_name = os.path.basename(getattr(self, "defaultfile", "") or "")
        if default_file_name:
            return default_file_name
        return _("untitled")

    def _get_current_title_file_type_label(self):
        raw_label = self._TITLE_FILE_TYPE_LABELS.get(
            getattr(self, "_current_file_type", "empty"),
            "",
        )
        return str(raw_label or "").split("\t", 1)[0].replace("&", "").strip()

    def _update_window_title(self):
        dirty_prefix = "* " if self._has_unsaved_changes() else ""
        title_file_name = self._get_current_title_filename()
        title_file_type = self._get_current_title_file_type_label()
        if hasattr(self, "text") and self.text is not None:
            self._update_tab_label(self.text)
        if title_file_type:
            self.SetTitle(f"{dirty_prefix}{title_file_type}: {title_file_name} - {self._base_window_title}")
            return
        self.SetTitle(f"{dirty_prefix}{title_file_name} - {self._base_window_title}")

    def _onWindowActivate(self, event):
        if event.GetActive():
            self._update_scratchpad_required_menu_state()
        event.Skip()

    def _focus_editor_now(self):
        try:
            if self.IsIconized():
                self.Iconize(False)
        except Exception:
            pass
        try:
            self.Show(True)
        except Exception:
            pass
        try:
            self.Raise()
        except Exception:
            pass
        try:
            self.RequestUserAttention(wx.USER_ATTENTION_INFO)
        except Exception:
            pass
        try:
            self.SetFocus()
        except Exception:
            pass
        try:
            self.text.SetFocus()
        except Exception:
            pass

    def bring_to_foreground(self):
        # Retry briefly because Windows may ignore the first foreground request.
        for delay in self._FOCUS_RETRY_DELAYS_MS:
            if delay <= 0:
                self._focus_editor_now()
            else:
                wx.CallLater(delay, self._focus_editor_now)

    def _onMenuOpen(self, event):
        self._update_scratchpad_required_menu_state()
        self._update_edit_menu_state()
        self._rebuild_tabs_menu()
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

        # save selection (214) – only if something is selected
        item = menuBar.FindItemById(214)
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
        item = menuBar.FindItemById(226)
        if item is not None:
            item.Enable(has_scripts)
        item = menuBar.FindItemById(227)
        if item is not None:
            item.Enable(self._get_current_script_entry() is not None)
        # script properties (229) – only when cursor is inside a script
        item = menuBar.FindItemById(229)
        if item is not None:
            item.Enable(self._get_current_script_entry() is not None)
        # edit method call (230) – only when editor has text
        item = menuBar.FindItemById(230)
        if item is not None:
            item.Enable(has_text)

        # next error (220) / previous error (221)
        item = menuBar.FindItemById(220)
        if item is not None:
            item.Enable(has_errors)
        item = menuBar.FindItemById(221)
        if item is not None:
            item.Enable(has_errors)

    def _scratchpad_locked_by_policy(self):
        return not sm_backend.is_scratchpad_enabled()

    def _update_scratchpad_required_menu_state(self):
        shouldEnable = sm_backend.is_scratchpad_enabled()
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
            sm_backend.get_scratchpad_disabled_message(reasonText),
            _("Script Manager"),
            wx.OK | wx.ICON_INFORMATION,
        )
        return False

    def _get_default_file_dialog_dir(self):
        if sm_backend.is_scratchpad_enabled():
            return sm_backend.get_scratchpad_dir(ensure_exists=True, ensure_subdirs=True)
        return os.path.expanduser("~")

    def _get_default_dir_for_file_type(self, file_type):
        if not sm_backend.is_scratchpad_enabled():
            return os.path.expanduser("~")
        if file_type == "empty":
            return sm_backend.get_scratchpad_dir(ensure_exists=True, ensure_subdirs=True)
        subdir_name = self._SCRATCHPAD_SUBDIR_BY_FILE_TYPE.get(file_type)
        if subdir_name:
            return sm_backend.get_scratchpad_subdir(subdir_name)
        return sm_backend.get_scratchpad_dir(ensure_exists=True, ensure_subdirs=True)

    def _set_new_file_context(self, file_type, default_file=None):
        self._current_file_type = file_type
        self.defaultdir = self._get_default_dir_for_file_type(file_type)
        if default_file:
            self.defaultfile = default_file
        elif not getattr(self, "defaultfile", ""):
            self.defaultfile = _("untitled") + ".py"

    def _detect_file_type_from_path(self, path):
        path = str(path or "").strip()
        if not path:
            return "empty"
        if not sm_backend.is_scratchpad_enabled():
            return "empty"
        scratchpad_dir = os.path.abspath(
            sm_backend.get_scratchpad_dir(ensure_exists=True, ensure_subdirs=True)
        )
        normalized_path = os.path.abspath(path)
        try:
            in_scratchpad = os.path.commonpath([scratchpad_dir, normalized_path]) == scratchpad_dir
        except ValueError:
            in_scratchpad = False
        if not in_scratchpad:
            return "empty"

        reverse_map = {value: key for key, value in self._SCRATCHPAD_SUBDIR_BY_FILE_TYPE.items()}
        rel_path = os.path.relpath(normalized_path, scratchpad_dir)
        top_level = rel_path.split(os.sep, 1)[0]
        return reverse_map.get(top_level, "empty")

    def OnNewEmptyFile(self, event):
        self._create_new_editor_tab(
            file_type="empty",
            default_file=_("untitled") + ".py",
        )

    def OnNewAppModule(self, event):
        if not self._ensure_scratchpad_for_action(_("Creating appModules requires scratchpad.")):
            return
        appmodule_name = self._choose_appmodule_name_for_new_file()
        if appmodule_name is None:
            return
        self._create_new_editor_tab(
            file_type="appModule",
            default_file=appmodule_name + ".py",
            content=sm_backend.createnewmodule("appModule", appmodule_name, False),
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
        self._create_new_editor_tab(
            file_type="globalPlugin",
            default_file=_("untitled") + ".py",
            content=sm_backend.createnewmodule("globalPlugin", _("untitled"), False),
        )

    def OnNewBrailleDisplayDriver(self, event):
        if not self._ensure_scratchpad_for_action(_("Creating braille display drivers requires scratchpad.")):
            return
        self._create_new_editor_tab(
            file_type="brailleDisplayDriver",
            default_file=_("untitled") + ".py",
            content=sm_backend.createnewmodule("brailleDisplayDriver", _("untitled"), False),
        )

    def OnNewSynthDriver(self, event):
        if not self._ensure_scratchpad_for_action(_("Creating synth drivers requires scratchpad.")):
            return
        self._create_new_editor_tab(
            file_type="synthDriver",
            default_file=_("untitled") + ".py",
            content=sm_backend.createnewmodule("synthDriver", _("untitled"), False),
        )

    def OnNewVisionEnhancementProvider(self, event):
        if not self._ensure_scratchpad_for_action(_("Creating vision enhancement providers requires scratchpad.")):
            return
        self._create_new_editor_tab(
            file_type="visionEnhancementProvider",
            default_file=_("untitled") + ".py",
            content=sm_backend.createnewmodule(
                "visionEnhancementProvider", _("untitled"), False
            ),
        )

    def DoNewEmptyFile(self):
        self._create_new_editor_tab(
            file_type="empty",
            default_file=_("untitled") + ".py",
        )

    def OnSettings(self, event):
        dlg = EditorSettingsDialog(self)
        try:
            if dlg.ShowModal() == wx.ID_OK:
                values = dlg.getValues()
                sm_backend.set_jump_mode(values["jumpMode"])
                sm_backend.set_include_blacklisted_modules(values["includeBlacklistedModules"])
                sm_backend.set_translate_docstrings_enabled(values["translateDocstrings"])
                sm_backend.set_translate_error_messages_enabled(values["translateErrorMessages"])
                sm_backend.set_indent_with_spaces_enabled(values["indentWithSpaces"])
                sm_backend.set_indent_width(values["indentWidth"])
                self._set_jump_mode(values["jumpMode"], announce=False)
                msg = _("Settings saved")
                self.statusbar.SetStatusText(msg, 1)
                ui.message(msg)
        finally:
            dlg.Destroy()

    def OnNewScript(self, event):
        """Open the definition dialog and insert a script or function template."""
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

        dlg = newscriptdialog(self, -1, _("Create new definition"))
        result = dlg.ShowModal()

        if result == wx.ID_OK:
            indent = self._get_definition_insertion_indent()
            self._prepare_definition_insertion_point()
            if dlg.definition_type == dlg.DEFINITION_TYPE_FUNCTION:
                definition_content = self._normalize_snippet_newlines(
                    self._generateFunctionTemplate(
                        dlg.function_name,
                        dlg.function_return_type,
                        dlg.function_params,
                        indent=indent,
                    )
                )
                self.text.WriteText(definition_content)
            else:
                definition_content = self._normalize_snippet_newlines(
                    self._generateScriptTemplate(
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
                        indent=indent,
                    )
                )
                insertion_point = self.text.GetInsertionPoint()
                inserted_chars = self._ensure_import_line_at_top("from scriptHandler import script")
                self.text.SetInsertionPoint(insertion_point + inserted_chars)
                self.text.WriteText(definition_content)

            self.text.MarkDirty()
            self._update_window_title()

        dlg.Destroy()

    def _sanitize_identifier(self, name, fallback="value"):
        clean_name = re.sub(r"[^a-zA-Z0-9_]", "_", str(name or "").strip())
        if not clean_name:
            clean_name = fallback
        if clean_name[0].isdigit():
            clean_name = "_" + clean_name
        return clean_name

    def _get_definition_insertion_indent(self):
        try:
            _col, line = self._get_line_col_from_position(self.text.GetInsertionPoint())
        except Exception:
            line = 0

        try:
            entries = self._get_definition_entries(self.JUMP_MODE_ALL_DEFINITIONS)
        except Exception:
            entries = []

        current_entry = None
        previous_entry = None
        for entry in entries:
            start_line = int(entry.get("startLine", 0))
            end_line = int(entry.get("endLine", start_line))
            if start_line <= line <= end_line:
                current_entry = entry
                break
            if end_line < line:
                previous_entry = entry

        for entry in (current_entry, previous_entry):
            if entry is None:
                continue
            def_line = int(entry.get("defLine", entry.get("startLine", 0)))
            try:
                def_text = self.text.GetLineText(def_line) or ""
            except Exception:
                def_text = ""
            return self._get_line_leading_tabs(def_text)

        try:
            line_text = self.text.GetLineText(line) or ""
            indent = self._get_line_leading_tabs(line_text)
            if indent:
                return indent
            for previous_line in range(line - 1, -1, -1):
                previous_text = self.text.GetLineText(previous_line) or ""
                if not previous_text.strip():
                    continue
                return self._get_line_leading_tabs(previous_text)
        except Exception:
            pass
        return ""

    def _prepare_definition_insertion_point(self):
        try:
            insertion_point = self.text.GetInsertionPoint()
            _col, line = self._get_line_col_from_position(insertion_point)
            line_start = self.text.XYToPosition(0, line)
            prefix_text = self.text.GetRange(line_start, insertion_point)
            if prefix_text and not prefix_text.strip():
                self.text.Remove(line_start, insertion_point)
                self.text.SetInsertionPoint(line_start)
        except Exception:
            pass

    def _generateFunctionTemplate(self, name, return_type, parameters, indent=""):
        clean_name = self._sanitize_identifier(name, fallback="function_name")
        parameter_parts = []
        for index, param in enumerate(parameters or []):
            param_name = self._sanitize_identifier(param.get("name", ""), fallback=f"param{index + 1}")
            param_type = str(param.get("type", "")).strip()
            default_value = str(param.get("default", "")).strip()
            parameter_text = param_name
            if param_type:
                parameter_text += f": {param_type}"
            if default_value:
                parameter_text += f" = {default_value}"
            parameter_parts.append(parameter_text)
        return_annotation = str(return_type or "").strip()
        if return_annotation:
            return_annotation = f" -> {return_annotation}"
        indent = str(indent or "")
        body_indent = indent + self._get_indent_unit_text(indent_text=indent)
        return f"{indent}def {clean_name}({', '.join(parameter_parts)}){return_annotation}:\n{body_indent}pass\n"

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
        indent="",
    ):
        """Generiert ein Script-Template basierend auf den Eingaben."""
        clean_name = re.sub(r'[^a-zA-Z0-9_]', '_', name)
        clean_name = clean_name.lower()
        if not clean_name.startswith('script_'):
            clean_name = 'script_' + clean_name

        args = []
        if '\n' in description:
            safe_description = description.replace('"""', '\\"\\"\\"')
            args.append(f'description=_("""{safe_description}""")')
        else:
            safe_description = description.replace('"', '\\"')
            args.append(f'description=_("{safe_description}")')

        if category:
            canonical_category = newscriptdialog.normalizeCategoryForCode(category)
            safe_category = canonical_category.replace('"', '\\"')
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

        indent = str(indent or "")
        inner_indent = indent + self._get_indent_unit_text(indent_text=indent)
        args_str = (',\n' + inner_indent).join(args)
        safe_name = name.replace('"', '\\"')
        template = (
            f"{indent}@script(\n"
            f"{inner_indent}{args_str}\n"
            f"{indent})\n"
            f"{indent}def {clean_name}(self, gesture):\n"
            f"{inner_indent}\"\"\"Script: {safe_name}\"\"\"\n"
            f"{inner_indent}pass\n"
        )

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
        _col, line = self._get_line_col_from_position(self.text.GetInsertionPoint())
        value = line + 1
        maxLine = self.text.GetNumberOfLines()
        ned = wx.NumberEntryDialog(
            parent=self,
            message=message,
            prompt=prompt,
            caption=caption,
            value=value,
            min=1,
            max=maxLine,
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
        if not hasattr(self, "frdata") or not hasattr(self, "searchresults") or not self.searchresults:
            self.OnFinditem(event)
            return
        fstring = self._rebuild_search_results()
        if not self.searchresults:
            gui.messageBox(message=_("text not found"), caption=_("find"))
            return
        self.frdata.Flags = self.frdata.Flags | wx.FR_DOWN
        self.searchresultindex = self._get_search_result_index_from_caret(forward=True)
        pos = self.text.XYToPosition(
            self.searchresults[self.searchresultindex][1],
            self.searchresults[self.searchresultindex][0],
        )
        self.text.SetSelection(pos, pos + len(fstring))
        self.text.SetInsertionPoint(pos)

    def OnFindpreviousitem(self, event):
        if not hasattr(self, "frdata") or not hasattr(self, "searchresults") or not self.searchresults:
            self.OnFinditem(event)
            return
        fstring = self._rebuild_search_results()
        if not self.searchresults:
            gui.messageBox(message=_("text not found"), caption=_("find"))
            return
        self.frdata.Flags = self.frdata.Flags & ~wx.FR_DOWN
        self.searchresultindex = self._get_search_result_index_from_caret(forward=False)
        pos = self.text.XYToPosition(
            self.searchresults[self.searchresultindex][1],
            self.searchresults[self.searchresultindex][0],
        )
        self.text.SetSelection(pos, pos + len(fstring))
        self.text.SetInsertionPoint(pos)

    def _get_search_result_index_from_caret(self, forward=True):
        """Return the next/previous search-result index using current caret position as anchor."""
        if not getattr(self, "searchresults", None):
            return 0

        caret_pos = self.text.GetInsertionPoint()
        indexed_positions = []
        for index, result in enumerate(self.searchresults):
            line, col = result
            result_pos = self.text.XYToPosition(col, line)
            indexed_positions.append((index, result_pos))

        if forward:
            for index, result_pos in indexed_positions:
                if result_pos > caret_pos:
                    return index
            return indexed_positions[0][0]

        for index, result_pos in reversed(indexed_positions):
            if result_pos < caret_pos:
                return index
        return indexed_positions[-1][0]

    def on_find_close(self, event):
        dlg = getattr(self, "dlg", None)
        try:
            if event is not None and hasattr(event, "GetDialog"):
                dlg = event.GetDialog() or dlg
        except Exception:
            pass
        if dlg is not None:
            try:
                dlg.Destroy()
            except Exception:
                pass
        self.dlg = None

    def _rebuild_search_results(self):
        fstring = str(getattr(self.frdata, "FindString", "") or "")
        wordborder = ""
        searchflags = 0
        if self.frdata.Flags & wx.FR_NOMATCHCASE:
            searchflags = searchflags | re.I
        if self.frdata.Flags & wx.FR_WHOLEWORD:
            wordborder = r"\b"
        if not fstring:
            self.searchpattern = None
            self.searchresults = []
            self.searchresultindex = 0
            return ""
        self.searchpattern = re.compile(
            pattern=wordborder + re.escape(fstring) + wordborder,
            flags=searchflags,
        )
        self.searchresults = []
        for line in range(self.text.GetNumberOfLines()):
            for match in self.searchpattern.finditer(self.text.GetLineText(line)):
                column = match.start()
                self.searchresults.append((line, column))
        if self.searchresults:
            current_index = int(getattr(self, "searchresultindex", 0))
            self.searchresultindex = max(0, min(current_index, len(self.searchresults) - 1))
        else:
            self.searchresultindex = 0
        return fstring

    def _close_find_dialog_after_success(self):
        dlg = getattr(self, "dlg", None)
        if dlg is None:
            return
        try:
            if dlg.GetWindowStyleFlag() & wx.FR_REPLACEDIALOG:
                return
        except Exception:
            pass
        self.on_find_close(None)

    def _replace_matches_stable(self, matches, find_length, replace_text):
        """Replace precomputed matches bottom-up to keep offsets stable."""
        if not matches or find_length <= 0:
            return 0
        replaced_count = 0
        for line, col in sorted(matches, key=lambda item: (item[0], item[1]), reverse=True):
            try:
                pos = self.text.XYToPosition(col, line)
            except Exception:
                continue
            self.text.SetSelection(pos, pos + find_length)
            self.text.ReplaceSelection(replace_text)
            replaced_count += 1
        return replaced_count

    def on_find(self, event):
        fstring = self._rebuild_search_results()
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
            self.text.SetInsertionPoint(pos)
            wx.CallAfter(self._close_find_dialog_after_success)
            self.searchresultindex += direction
        else:
            gui.messageBox(message=_("text not found"), caption=_("find"))

    def on_replace(self, event):
        fstring = self._rebuild_search_results()
        rstring = self.frdata.ReplaceString
        if not fstring:
            gui.messageBox(message=_("text not found"), caption=_("find"))
            return
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
            self.text.Remove(pos, pos + len(fstring))
            self.text.WriteText(rstring)
            self.searchresultindex += direction
        else:
            gui.messageBox(message=_("text not found"), caption=_("find"))

    def on_find_replace_all(self, event):
        fstring = self._rebuild_search_results()
        rstring = self.frdata.ReplaceString
        if not fstring:
            gui.messageBox(message=_("text not found"), caption=_("find"))
            return
        if len(self.searchresults) > 0:
            self._replace_matches_stable(self.searchresults, len(fstring), rstring)
            self._rebuild_search_results()
        else:
            gui.messageBox(message=_("text not found"), caption=_("find"))

    def _is_import_line_present(self, import_line):
        content = self.text.GetValue()
        lines = content.splitlines()

        if import_line.startswith("import "):
            module_name = import_line[len("import "):].strip()
            for line in lines:
                stripped = line.strip()
                if not stripped.startswith("import "):
                    continue
                imported = stripped[len("import "):]
                for item in imported.split(","):
                    plain_item = item.strip().split(" as ", 1)[0].strip()
                    if plain_item == module_name:
                        return True
            return False

        match = re.match(r"from\s+([A-Za-z0-9_\.]+)\s+import\s+([A-Za-z0-9_]+)$", import_line)
        if not match:
            return import_line in lines

        module_name, member_name = match.groups()
        prefix = f"from {module_name} import "
        for line in lines:
            stripped = line.strip()
            if not stripped.startswith(prefix):
                continue
            imported = stripped[len(prefix):]
            if "*" in imported:
                return True
            imported_names = [item.strip().split(" as ", 1)[0].strip() for item in imported.split(",")]
            if member_name in imported_names:
                return True
        return False

    def _ensure_import_line_at_top(self, import_line):
        if not import_line:
            return 0
        import_line = import_line.replace("\r", "").replace("\n", "").strip()
        if not import_line:
            return 0
        if self._is_import_line_present(import_line):
            return 0

        current_text = self.text.GetValue()
        import_prefix = import_line.rstrip() + "\n"
        self.text.SetValue(import_prefix + current_text)
        # Use actual control text length delta to stay correct across line-ending conversions.
        return len(self.text.GetValue()) - len(current_text)

    def _normalize_snippet_newlines(self, text):
        """Normalize snippet line endings to match current editor content."""
        if not text:
            return text
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        editor_text = self.text.GetValue()
        if "\r\n" in editor_text:
            return normalized.replace("\n", "\r\n")
        return normalized

    def _get_line_indent_at_position(self, pos):
        """Return the leading indentation of the line containing a text position."""
        try:
            _col, line = self._get_line_col_from_position(pos)
            line_text = self.text.GetLineText(line) or ""
        except Exception:
            return ""
        return self._get_line_leading_tabs(line_text)

    def _indent_inserted_helper_text(self, text, indent=""):
        """Apply the current line indentation to fallback helper lines like ``Syntax: ...``."""
        if not text:
            return text
        indent = str(indent or "")
        if not indent:
            return text

        lines = text.splitlines(keepends=True)
        formatted = []
        for line in lines:
            content = line.rstrip("\r\n")
            newline = line[len(content):]
            if content.strip():
                formatted.append(indent + content.lstrip("\t ") + newline)
            else:
                formatted.append(line)
        return "".join(formatted)

    def _split_call_snippet_and_syntax(self, text):
        """Split inserted text into call snippet and optional syntax-description tail."""
        if not text:
            return text, ""

        lines = text.splitlines(keepends=True)
        syntax_lines = []

        while lines:
            candidate = lines[-1].strip()
            if not candidate:
                syntax_lines.insert(0, lines.pop())
                continue
            if re.match(r"^syntax\s*:", candidate, re.IGNORECASE):
                syntax_lines.insert(0, lines.pop())
                break
            break

        call_snippet = "".join(lines)
        syntax_tail = "".join(syntax_lines)
        return call_snippet, syntax_tail

    def _get_call_text_range(self, call_node):
        """Return the absolute text start/end positions for a detected call."""
        if isinstance(call_node, _TextCallRef):
            return call_node.start_pos, call_node.end_pos

        start_line = call_node.lineno - 1
        start_col = call_node.col_offset
        end_line = call_node.end_lineno - 1
        end_col = call_node.end_col_offset
        start_pos = self.text.XYToPosition(start_col, start_line)
        end_pos = self.text.XYToPosition(end_col, end_line)
        return start_pos, end_pos

    def _find_call_end_near_position(self, pos):
        """Return the current end position of a call around a text position."""
        content = self.text.GetValue()
        if not content:
            return None
        pos = max(0, min(int(pos), len(content)))
        call_node, _ = self._find_text_call_at_cursor(content, pos)
        if call_node is None:
            return None
        _start_pos, end_pos = self._get_call_text_range(call_node)
        return end_pos

    def _is_find_replace_dialog_active(self):
        """Return True when a Find/Replace dialog exists and is currently shown."""
        dlg = getattr(self, "dlg", None)
        if dlg is None:
            return False
        try:
            return bool(dlg.IsShown())
        except Exception:
            return False

    def OnInsertFunction(self, event):
        ifd = insertfunctionsdialog(
            self,
            dialogId=wx.ID_ANY,
            title=_("insert function"),
            includeBlacklistedModules=sm_backend.get_include_blacklisted_modules(),
            translateDocstrings=sm_backend.get_translate_docstrings_enabled(),
        )
        try:
            if ifd.ShowModal() != wx.ID_OK:
                return

            normalized_insert_text = self._normalize_snippet_newlines(ifd.functionstring or "")
            text_to_insert, syntax_tail = self._split_call_snippet_and_syntax(normalized_insert_text)
            import_line = (ifd.importstring or "").replace("\r", "").replace("\n", "").strip()
            inserted_start = None
            syntax_indent = ""

            if import_line and text_to_insert and text_to_insert != import_line:
                insertion_point = self.text.GetInsertionPoint()
                inserted_chars = self._ensure_import_line_at_top(import_line)
                self.text.SetInsertionPoint(insertion_point + inserted_chars)
                inserted_start = self.text.GetInsertionPoint()
                syntax_indent = self._get_line_indent_at_position(inserted_start)
                if not syntax_indent:
                    syntax_indent = self._get_definition_insertion_indent()
                self.text.WriteText(text_to_insert)
            elif text_to_insert:
                inserted_start = self.text.GetInsertionPoint()
                syntax_indent = self._get_line_indent_at_position(inserted_start)
                if not syntax_indent:
                    syntax_indent = self._get_definition_insertion_indent()
                self.text.WriteText(text_to_insert)

            if inserted_start is not None and text_to_insert and "(" in text_to_insert and ")" in text_to_insert:
                # Temporarily move into the call so F4/call-edit detection can resolve it,
                # but restore the caret to the natural end position afterwards.
                call_open_offset = text_to_insert.find("(")
                if call_open_offset >= 0:
                    caret_pos = inserted_start + call_open_offset
                else:
                    caret_pos = inserted_start + len(text_to_insert)
                restore_caret_pos = self._find_call_end_near_position(caret_pos)
                if restore_caret_pos is None:
                    restore_caret_pos = inserted_start + len(text_to_insert)

                self.text.SetInsertionPoint(caret_pos)
                self.text.SetSelection(caret_pos, caret_pos)
                self.text.SetFocus()
                dialog_opened = self._edit_method_call_at_cursor(announceErrors=False)

                updated_call_end = self._find_call_end_near_position(caret_pos)
                if updated_call_end is not None:
                    restore_caret_pos = updated_call_end

                if not dialog_opened and syntax_tail:
                    formatted_syntax_tail = self._indent_inserted_helper_text(
                        syntax_tail,
                        indent=syntax_indent,
                    )
                    self.text.SetInsertionPoint(inserted_start + len(text_to_insert))
                    self.text.WriteText(formatted_syntax_tail)
                    restore_caret_pos = self.text.GetInsertionPoint()

                self.text.SetInsertionPoint(restore_caret_pos)
                self.text.SetSelection(restore_caret_pos, restore_caret_pos)
                self.text.SetFocus()
        finally:
            ifd.Destroy()

    def OnInsertFile(self, event):
        wildcard = _("All files (*.*)") + "|*.*|" + _("Text files (*.txt)|*.txt")
        default_dir = self._get_default_file_dialog_dir()
        file_dialog = wx.FileDialog(
            self,
            message=_("Choose a file to insert"),
            defaultDir=default_dir,
            defaultFile="",
            wildcard=wildcard,
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        )
        try:
            if file_dialog.ShowModal() != wx.ID_OK:
                return

            path = file_dialog.GetPath()
            errors = []
            encodings = ["utf-8", "utf-8-sig", "mbcs", sys.getdefaultencoding()]
            tried = set()
            content = None

            for encoding in encodings:
                if not encoding or encoding in tried:
                    continue
                tried.add(encoding)
                try:
                    with open(path, "r", encoding=encoding) as source_file:
                        content = source_file.read()
                    break
                except Exception as error:
                    errors.append(str(error))

            if content is None:
                raise IOError("\n".join(errors) if errors else _("Unknown read error"))

            insertion_point = self.text.GetInsertionPoint()
            self.text.SetSelection(insertion_point, insertion_point)
            self.text.WriteText(content)
            self.statusbar.SetStatusText(
                _("Inserted file: {filename}").format(filename=os.path.basename(path)),
                0,
            )
        except Exception as error:
            dlg = wx.MessageDialog(self, _("Error inserting file") + "\n" + str(error))
            try:
                dlg.ShowModal()
            finally:
                dlg.Destroy()
        finally:
            file_dialog.Destroy()

    def OnSaveSelection(self, event):
        frm, to = self.text.GetSelection()
        if frm == to:
            wx.MessageBox(
                _("Please select text first."),
                _("Save selection"),
                wx.OK | wx.ICON_INFORMATION,
            )
            return

        wildcard = _("Text files (*.txt)") + "|*.txt|" + _("All files (*.*)") + "|*.*"
        default_dir = self._get_default_file_dialog_dir()
        save_dialog = wx.FileDialog(
            self,
            message=_("Save selected text as..."),
            defaultDir=default_dir,
            defaultFile="selection.txt",
            wildcard=wildcard,
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        )
        try:
            if save_dialog.ShowModal() != wx.ID_OK:
                return

            path = save_dialog.GetPath()
            selected_text = self.text.GetStringSelection()
            with open(path, "w", encoding="utf-8") as target_file:
                target_file.write(selected_text)
            self.statusbar.SetStatusText(
                _("Selection saved: {filename}").format(filename=os.path.basename(path)),
                0,
            )
        except Exception as error:
            dlg = wx.MessageDialog(self, _("Error saving selection") + "\n" + str(error))
            try:
                dlg.ShowModal()
            finally:
                dlg.Destroy()
        finally:
            save_dialog.Destroy()

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
        except Exception:
            return
        if open_dlg.ShowModal() == wx.ID_OK:
            path = open_dlg.GetDirectory() + os.sep + open_dlg.GetFilename()
            ui.message(path)
            if self._open_file_in_new_tab(path):
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
                self.text.SetModified(False)
                self._update_tab_label(self.text)
                self._update_window_title()
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
        if self.last_name_saved:
            default_dir = os.path.dirname(self.last_name_saved)
            defaultfile = os.path.basename(self.last_name_saved)
        else:
            default_dir = self._get_default_dir_for_file_type(
                getattr(self, "_current_file_type", "empty")
            )
            defaultfile = getattr(self, "defaultfile", _("untitled") + ".py")
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
                self._current_file_type = self._detect_file_type_from_path(path)
                self.defaultdir = os.path.dirname(path)
                self.defaultfile = os.path.basename(path)
                self.statusbar.SetStatusText(os.path.basename(path) + " " + _("saved"), 0)
                self.statusbar.SetStatusText("", 1)
                self.modify = False
                self.text.SetModified(False)
                self._update_tab_label(self.text)
                self._update_window_title()
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
        if hasattr(self, "searchpattern") and getattr(self, "searchpattern", None) is not None and hasattr(self, "frdata"):
            self._rebuild_search_results()
        self.statusbar.SetStatusText(_(" modified"), 1)
        self._update_caret_status()
        self.modify = True
        self._update_tab_label(self.text)
        self._update_window_title()
        event.Skip()

    def OnTextCaretChanged(self, event):
        self._update_caret_status()
        event.Skip()

    def _get_line_col_from_position(self, pos):
        """Return (col, line) from TextCtrl position for wx variants with 2 or 3 return values."""
        try:
            xy = self.text.PositionToXY(pos)
        except Exception:
            return 0, 0

        if not isinstance(xy, tuple):
            return 0, 0

        if len(xy) == 2:
            col, line = xy
            return int(col), int(line)

        if len(xy) >= 3:
            success, col, line = xy[:3]
            if success is False:
                return 0, 0
            return int(col), int(line)

        return 0, 0

    def _update_caret_status(self):
        try:
            col, line = self._get_line_col_from_position(self.text.GetInsertionPoint())
            self.statusbar.SetStatusText(_("Ln {line}, Col {col}").format(line=line + 1, col=col + 1), 3)
        except Exception:
            self.statusbar.SetStatusText("", 3)

    def _get_line_leading_tabs(self, line_text):
        match = re.match(r"^[\t ]*", line_text or "")
        return match.group(0) if match else ""

    def _detect_space_indent_width(self, line=None, indent_text=""):
        configured_width = sm_backend.get_indent_width()
        candidate_lengths = []
        if indent_text and "\t" not in indent_text:
            candidate_lengths.append(len(indent_text))
        try:
            if line is not None:
                total_lines = self.text.GetNumberOfLines()
                start_line = max(0, line - 40)
                end_line = min(total_lines, line + 41)
                for scan_line in range(start_line, end_line):
                    scan_text = self.text.GetLineText(scan_line) or ""
                    if not scan_text.strip():
                        continue
                    scan_indent = self._get_line_leading_tabs(scan_text)
                    if scan_indent and "\t" not in scan_indent:
                        candidate_lengths.append(len(scan_indent))
        except Exception:
            pass
        candidate_lengths = sorted({length for length in candidate_lengths if length > 0})
        if len(candidate_lengths) >= 2:
            diffs = [
                right - left
                for left, right in zip(candidate_lengths, candidate_lengths[1:])
                if (right - left) > 0
            ]
            if diffs:
                return max(1, min(diffs))
        if candidate_lengths:
            length = candidate_lengths[0]
            if configured_width > 0 and length % configured_width == 0:
                return configured_width
            return max(1, length)
        return configured_width

    def _get_indent_unit_text(self, line=None, indent_text=""):
        if indent_text:
            if "\t" in indent_text:
                return "\t"
            if " " in indent_text:
                return " " * self._detect_space_indent_width(line=line, indent_text=indent_text)
        try:
            if line is not None:
                for previous_line in range(line, -1, -1):
                    previous_text = self.text.GetLineText(previous_line) or ""
                    if not previous_text.strip():
                        continue
                    previous_indent = self._get_line_leading_tabs(previous_text)
                    if previous_indent:
                        if "\t" in previous_indent:
                            return "\t"
                        if " " in previous_indent:
                            return " " * self._detect_space_indent_width(
                                line=previous_line,
                                indent_text=previous_indent,
                            )
        except Exception:
            pass
        if sm_backend.get_indent_with_spaces_enabled():
            return " " * sm_backend.get_indent_width()
        return "\t"

    def _get_current_line_leading_tabs(self):
        try:
            _col, line = self._get_line_col_from_position(self.text.GetInsertionPoint())
            line_text = self.text.GetLineText(line)
        except Exception:
            return ""
        return self._get_line_leading_tabs(line_text)

    def _maybe_auto_outdent_current_line(self, line, line_text, indent):
        stripped = str(line_text or "").lstrip("\t ").strip()
        if not re.match(r"^(elif\b.*|else|except\b.*|finally)\s*:\s*(#.*)?$", stripped):
            return line_text, indent
        if not indent:
            return line_text, indent
        current_leading = self._get_line_leading_tabs(line_text)
        previous_indent = None
        for previous_line in range(line - 1, -1, -1):
            previous_text = self.text.GetLineText(previous_line) or ""
            if not previous_text.strip():
                continue
            previous_indent = self._get_line_leading_tabs(previous_text)
            break
        if previous_indent is None or len(indent) < len(previous_indent):
            return line_text, indent
        indent_unit = self._get_indent_unit_text(line=line, indent_text=indent)
        if indent_unit and indent.endswith(indent_unit):
            adjusted_indent = indent[:-len(indent_unit)]
        else:
            adjusted_indent = indent[:-1]
        adjusted_line_text = adjusted_indent + str(line_text or "")[len(current_leading):]
        return adjusted_line_text, adjusted_indent

    def _get_smart_indent_text(self):
        try:
            _col, line = self._get_line_col_from_position(self.text.GetInsertionPoint())
            line_text = self.text.GetLineText(line) or ""
        except Exception:
            return "", ""
        indent = self._get_line_leading_tabs(line_text)
        line_text, indent = self._maybe_auto_outdent_current_line(line, line_text, indent)
        if line_text.rstrip().endswith(":"):
            indent += self._get_indent_unit_text(line=line, indent_text=indent)
        return line_text, indent

    def _handle_indent_with_spaces(self):
        if not sm_backend.get_indent_with_spaces_enabled():
            return False
        indent_text = " " * sm_backend.get_indent_width()
        selection_start, selection_end = self.text.GetSelection()
        if selection_start != selection_end:
            self.text.Replace(selection_start, selection_end, indent_text)
        else:
            self.text.WriteText(indent_text)
        self._update_caret_status()
        return True

    def _handle_smart_indent(self):
        try:
            selection_start, selection_end = self.text.GetSelection()
            insertion_point = self.text.GetInsertionPoint()
            if selection_start != selection_end:
                _line_text, indent = self._get_smart_indent_text()
                self.text.Replace(selection_start, selection_end, "\n" + indent)
                self._update_caret_status()
                return True
            _col, line = self._get_line_col_from_position(insertion_point)
            line_start = self.text.XYToPosition(0, line)
            line_text, indent = self._get_smart_indent_text()
            cursor_in_line = max(0, insertion_point - line_start)
            cursor_in_line = min(cursor_in_line, len(line_text))
            replacement = line_text[:cursor_in_line] + "\n" + indent
            self.text.Replace(line_start, insertion_point, replacement)
            self._update_caret_status()
            return True
        except Exception:
            return False

    def OnKeyDown(self, event):
        keycode = event.GetKeyCode()
        numpad_enter = getattr(wx, "WXK_NUMPAD_ENTER", -1)
        if event.ControlDown() and keycode == wx.WXK_TAB:
            if event.ShiftDown():
                self.OnPreviousTab(None)
            else:
                self.OnNextTab(None)
            return
        if event.ControlDown() and keycode == wx.WXK_F4:
            self.OnCloseFile(None)
            return
        if event.ControlDown() and keycode in (ord("I"), ord("i")):
            if self._is_find_replace_dialog_active():
                event.Skip()
                return
            self.OnInsertFunction(None)
            return
        if event.ControlDown() and keycode in (ord("R"), ord("r")):
            if self._is_find_replace_dialog_active():
                event.Skip()
                return
            self.OnInsertFile(None)
            return
        if event.AltDown() and keycode in (wx.WXK_RETURN, numpad_enter):
            self.OnScriptProperties(None)
            return
        if (
            keycode == wx.WXK_TAB
            and not event.ControlDown()
            and not event.AltDown()
            and not event.ShiftDown()
            and (event.GetEventObject() is self.text or self.FindFocus() is self.text)
        ):
            if self._handle_indent_with_spaces():
                return
        if (
            keycode in (wx.WXK_RETURN, numpad_enter)
            and not event.ControlDown()
            and not event.AltDown()
            and (event.GetEventObject() is self.text or self.FindFocus() is self.text)
        ):
            if self._handle_smart_indent():
                return
        if keycode == wx.WXK_F2:
            if event.ControlDown():
                if event.ShiftDown():
                    self.OnPreviousClassDefinition(None)
                else:
                    self.OnNextClassDefinition(None)
                return
            if event.AltDown():
                self.OnGotoEnclosingClass(None)
                return
            if event.ShiftDown():
                self.OnPreviousScriptDefinition(None)
            else:
                self.OnNextScriptDefinition(None)
            return
        if keycode == wx.WXK_F4:
            self.OnEditMethodCall(None)
            return
        if hasattr(self, "searchresults") and hasattr(self, "frdata"):
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
                    x = int(getattr(self, "searchresultindex", 0))
                    x = max(0, min(x, len(self.searchresults) - 1))
                    while (
                        x + 1 < len(self.searchresults)
                        and (
                            self.text.XYToPosition(
                                self.searchresults[x][1], self.searchresults[x][0]
                            )
                            +len(self.frdata.FindString)
                        ) < self.text.GetInsertionPoint()
                    ):
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
        self.statusbar.SetFieldsCount(4)
        self.statusbar.SetStatusWidths([-5, -2, -1, -2])

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

        self.current_error_index = self._get_error_index_from_caret(forward=True)

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

        self.current_error_index = self._get_error_index_from_caret(forward=False)

        self._goto_error(self.current_error_index)

    def _get_error_index_from_caret(self, forward=True):
        """Return the next/previous error index using current caret line as anchor."""
        if not getattr(self, "errors", None):
            return -1

        try:
            _col, current_line = self._get_line_col_from_position(self.text.GetInsertionPoint())
        except Exception:
            current_line = 0

        parsed_errors = []
        for index, error in enumerate(self.errors):
            try:
                error_line = max(0, int(error.get("line", 1)) - 1)
            except Exception:
                error_line = 0
            parsed_errors.append((index, error_line))

        if forward:
            candidates = [item for item in parsed_errors if item[1] > current_line]
            if candidates:
                return min(candidates, key=lambda item: item[1])[0]
            return min(parsed_errors, key=lambda item: item[1])[0]

        candidates = [item for item in parsed_errors if item[1] < current_line]
        if candidates:
            return max(candidates, key=lambda item: item[1])[0]
        return max(parsed_errors, key=lambda item: item[1])[0]

    def OnNextScriptDefinition(self, event):
        """Springt zur nächsten Scriptdefinition (def script_...)."""
        self._goto_script_definition(forward=True)

    def OnPreviousScriptDefinition(self, event):
        """Springt zur vorherigen Scriptdefinition (def script_...)."""
        self._goto_script_definition(forward=False)

    def OnGotoEnclosingClass(self, event):
        entry = self._get_current_script_entry()
        if entry is not None and entry.get("className"):
            class_name = str(entry.get("className") or "")
            target = {
                "entryType": "class",
                "name": class_name,
                "qualifiedName": class_name,
                "defLine": int(entry.get("classDefLine", entry.get("classStartLine", 0)) or 0),
                "startLine": int(entry.get("classStartLine", entry.get("classDefLine", 0)) or 0),
                "endLine": int(entry.get("classEndLine", entry.get("classDefLine", 0)) or 0),
            }
            self._goto_script_entry(target)
            return

        target = self._get_current_class_entry()
        if target is None:
            wx.Bell()
            msg = _("no enclosing class found at the current position")
            self.statusbar.SetStatusText(msg, 1)
            ui.message(msg)
            return

        self._goto_script_entry(target)

    def OnCycleJumpMode(self, event):
        self._cycle_jump_mode()

    def OnNextClassDefinition(self, event):
        """Springt zur nächsten Klassendefinition."""
        self._goto_class_definition(forward=True)

    def OnPreviousClassDefinition(self, event):
        """Springt zur vorigen Klassendefinition."""
        self._goto_class_definition(forward=False)

    def OnSetJumpModeScripts(self, event):
        self._set_jump_mode(self.JUMP_MODE_SCRIPTS)

    def OnSetJumpModeFunctionsOnly(self, event):
        self._set_jump_mode(self.JUMP_MODE_FUNCTIONS_ONLY)

    def OnSetJumpModeAllDefinitions(self, event):
        self._set_jump_mode(self.JUMP_MODE_ALL_DEFINITIONS)

    def OnShowScriptList(self, event):
        """Shows all script definitions and allows jumping/deleting."""
        entries = self._get_script_entries()
        if not entries:
            wx.Bell()
            msg = _("no definitions found for filter: {mode}").format(
                mode=self._get_jump_mode_label()
            )
            self.statusbar.SetStatusText(msg, 1)
            ui.message(msg)
            return

        choices = [entry["display"] for entry in entries]
        dlg = wx.Dialog(self, title=_("definition list"))
        listBox = wx.ListBox(dlg, choices=choices, style=wx.LB_SINGLE)
        currentEntry = self._get_current_script_entry(entries)
        if currentEntry is not None:
            for index, entry in enumerate(entries):
                if entry["startLine"] == currentEntry["startLine"]:
                    listBox.SetSelection(index)
                    break
        elif choices:
            listBox.SetSelection(0)

        gotoButton = wx.Button(dlg, wx.ID_OK, _("&Go to"))
        deleteButton = wx.Button(dlg, wx.ID_DELETE, _("&Delete"))
        cancelButton = wx.Button(dlg, wx.ID_CANCEL, _("&Close"))
        gotoButton.SetDefault()

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(listBox, 1, wx.ALL | wx.EXPAND, 10)
        buttonSizer = wx.BoxSizer(wx.HORIZONTAL)
        buttonSizer.Add(gotoButton, 0, wx.RIGHT, 8)
        buttonSizer.Add(deleteButton, 0, wx.RIGHT, 8)
        buttonSizer.Add(cancelButton, 0)
        sizer.Add(buttonSizer, 0, wx.ALL | wx.ALIGN_RIGHT, 10)
        dlg.SetSizerAndFit(sizer)

        listBox.Bind(wx.EVT_LISTBOX_DCLICK, lambda evt: dlg.EndModal(wx.ID_OK))

        def _onScriptListCharHook(evt):
            if evt.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
                dlg.EndModal(wx.ID_OK)
                return
            evt.Skip()

        listBox.Bind(wx.EVT_CHAR_HOOK, _onScriptListCharHook)

        result = dlg.ShowModal()
        selection = listBox.GetSelection()
        dlg.Destroy()

        if selection < 0 or selection >= len(entries):
            return

        selectedEntry = entries[selection]
        if result == wx.ID_OK:
            self._goto_script_entry(selectedEntry)
            return
        if result == wx.ID_DELETE:
            self._delete_script_entry(selectedEntry)

    def OnDeleteCurrentScriptDefinition(self, event):
        """Deletes the script definition at the current caret position."""
        entry = self._get_current_script_entry()
        if entry is None:
            wx.Bell()
            msg = _("cursor is not inside a definition for current filter")
            self.statusbar.SetStatusText(msg, 1)
            ui.message(msg)
            return
        self._delete_script_entry(entry)

    def OnShowErrorList(self, event):
        """Shows all current script errors in a list and allows jumping."""
        script_content = self.text.GetValue()
        if not script_content.strip():
            ui.message(_("No script content to check"))
            return

        sm_backend.activate_error_logging(self.last_name_saved if self.last_name_saved else None)
        self.errors, _error_detail_str = sm_backend.check_script_for_errors(script_content)
        if not self.errors:
            wx.Bell()
            msg = _("no errors found")
            self.statusbar.SetStatusText(msg, 1)
            ui.message(msg)
            return

        choices = []
        for err in self.errors:
            line_num = err.get("line", 1)
            message = str(err.get("message", _("Unknown error")))
            choices.append(_("Line {line}: {msg}").format(line=line_num, msg=message))

        dlg = wx.Dialog(self, title=_("Error list"))
        listBox = wx.ListBox(dlg, choices=choices, style=wx.LB_SINGLE)
        listBox.SetSelection(0)
        gotoButton = wx.Button(dlg, wx.ID_OK, _("&Go to"))
        closeButton = wx.Button(dlg, wx.ID_CANCEL, _("&Close"))
        gotoButton.SetDefault()

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(listBox, 1, wx.ALL | wx.EXPAND, 10)
        buttonSizer = wx.BoxSizer(wx.HORIZONTAL)
        buttonSizer.Add(gotoButton, 0, wx.RIGHT, 8)
        buttonSizer.Add(closeButton, 0)
        sizer.Add(buttonSizer, 0, wx.ALL | wx.ALIGN_RIGHT, 10)
        dlg.SetSizerAndFit(sizer)

        listBox.Bind(wx.EVT_LISTBOX_DCLICK, lambda evt: dlg.EndModal(wx.ID_OK))

        def _onErrorListCharHook(evt):
            if evt.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
                dlg.EndModal(wx.ID_OK)
                return
            evt.Skip()

        listBox.Bind(wx.EVT_CHAR_HOOK, _onErrorListCharHook)

        result = dlg.ShowModal()
        selection = listBox.GetSelection()
        dlg.Destroy()

        if result != wx.ID_OK:
            return
        if selection < 0 or selection >= len(self.errors):
            return
        self.current_error_index = selection
        self._goto_error(selection)

    def _is_script_definition_name(self, name):
        return str(name or "").lower().startswith("script_")

    def _definition_has_script_decorator(self, node):
        for decorator in getattr(node, "decorator_list", []):
            target = decorator.func if isinstance(decorator, ast.Call) else decorator
            if isinstance(target, ast.Name) and target.id == "script":
                return True
            if isinstance(target, ast.Attribute) and target.attr == "script":
                return True
        return False

    def _get_definition_display_name(self, entry):
        name = str(entry.get("qualifiedName") or entry.get("name") or "")
        raw_name = str(entry.get("name") or "")
        class_name = str(entry.get("className") or "")
        if entry.get("isScript") and raw_name.lower().startswith("script_"):
            trimmed_name = raw_name[len("script_"):]
            if trimmed_name:
                return f"{class_name}.{trimmed_name}" if class_name else trimmed_name
        return name or _("unnamed definition")

    def _definition_matches_jump_mode(self, name, jump_mode=None, is_script=None):
        mode = jump_mode if jump_mode in self._JUMP_MODE_ORDER else getattr(self, "_jump_mode", self.JUMP_MODE_SCRIPTS)
        if is_script is None:
            is_script = self._is_script_definition_name(name)
        if mode == self.JUMP_MODE_SCRIPTS:
            return bool(is_script)
        if mode == self.JUMP_MODE_FUNCTIONS_ONLY:
            return not bool(is_script)
        return True

    def _get_jump_mode_label(self, jump_mode=None):
        mode = jump_mode if jump_mode in self._JUMP_MODE_ORDER else getattr(self, "_jump_mode", self.JUMP_MODE_SCRIPTS)
        if mode == self.JUMP_MODE_SCRIPTS:
            return _("scripts")
        if mode == self.JUMP_MODE_FUNCTIONS_ONLY:
            return _("functions only")
        return _("all definitions")

    def _update_jump_mode_menu_checks(self):
        menuBar = self.GetMenuBar()
        if not menuBar:
            return
        mode = getattr(self, "_jump_mode", self.JUMP_MODE_SCRIPTS)
        item = menuBar.FindItemById(232)
        if item is not None:
            item.Check(mode == self.JUMP_MODE_SCRIPTS)
        item = menuBar.FindItemById(233)
        if item is not None:
            item.Check(mode == self.JUMP_MODE_FUNCTIONS_ONLY)
        item = menuBar.FindItemById(234)
        if item is not None:
            item.Check(mode == self.JUMP_MODE_ALL_DEFINITIONS)

    def _set_jump_mode(self, jump_mode, announce=True):
        if jump_mode not in self._JUMP_MODE_ORDER:
            jump_mode = self.JUMP_MODE_SCRIPTS
        self._jump_mode = jump_mode
        sm_backend.set_jump_mode(jump_mode)
        self._update_jump_mode_menu_checks()
        self._update_edit_menu_state()
        if announce:
            msg = _("definition filter: {mode}").format(mode=self._get_jump_mode_label(jump_mode))
            self.statusbar.SetStatusText(msg, 1)
            ui.message(msg)

    def _cycle_jump_mode(self):
        current = getattr(self, "_jump_mode", self.JUMP_MODE_SCRIPTS)
        try:
            current_index = self._JUMP_MODE_ORDER.index(current)
        except ValueError:
            current_index = 0
        next_mode = self._JUMP_MODE_ORDER[(current_index + 1) % len(self._JUMP_MODE_ORDER)]
        self._set_jump_mode(next_mode, announce=True)

    def _get_class_entries(self):
        """Returns class definition entries with name, range and display text."""
        content = self.text.GetValue()
        entries = []
        try:
            module = ast.parse(content)
        except Exception:
            return entries

        # Extract top-level and nested class definitions
        def process_body(body, parent_class=None):
            """Recursively process body to find class definitions."""
            for node in body:
                if isinstance(node, ast.ClassDef):
                    class_start_line = getattr(node, "lineno", 1) - 1
                    for decorator in getattr(node, "decorator_list", []):
                        class_start_line = min(
                            class_start_line,
                            getattr(decorator, "lineno", class_start_line + 1) - 1,
                        )
                    class_def_line = max(0, getattr(node, "lineno", 1) - 1)
                    class_end_line = getattr(node, "end_lineno", getattr(node, "lineno", 1)) - 1
                    class_name = str(getattr(node, "name", ""))
                    
                    # Build qualified name if this is a nested class
                    if parent_class:
                        qualified_name = f"{parent_class}.{class_name}"
                    else:
                        qualified_name = class_name
                    
                    entries.append(
                        {
                            "name": class_name,
                            "qualifiedName": qualified_name,
                            "defLine": class_def_line,
                            "startLine": max(0, class_start_line),
                            "endLine": max(0, class_end_line),
                        }
                    )
                    
                    # Recursively process nested classes
                    process_body(node.body, parent_class=qualified_name)

        process_body(module.body)
        return entries

    def _goto_class_definition(self, forward=True):
        """Springt zur nächsten/vorherigen Klassendefinition und signalisiert Umbruch."""
        entries = self._get_class_entries()
        if not entries:
            wx.Bell()
            msg = _("no class definitions found")
            self.statusbar.SetStatusText(msg, 1)
            ui.message(msg)
            return

        _col, current_line = self._get_line_col_from_position(self.text.GetInsertionPoint())
        wrapped = False

        def _entry_line(entry):
            return int(entry.get("defLine", entry.get("startLine", 0)))

        if forward:
            target_candidates = [entry for entry in entries if _entry_line(entry) > current_line]
            if target_candidates:
                target_entry = target_candidates[0]
            else:
                target_entry = entries[0]
                wrapped = True
        else:
            target_candidates = [entry for entry in entries if _entry_line(entry) < current_line]
            if target_candidates:
                target_entry = target_candidates[-1]
            else:
                target_entry = entries[-1]
                wrapped = True

        if wrapped:
            wx.Bell()

        self._goto_script_entry(target_entry)

    def _get_script_entries(self):
        """Returns script entries with name, range and display text."""
        return self._get_definition_entries(
            jump_mode=getattr(self, "_jump_mode", self.JUMP_MODE_SCRIPTS)
        )

    def _get_definition_entries(self, jump_mode=None):
        """Returns definition entries filtered by the selected jump mode."""
        content = self.text.GetValue()
        entries = []
        try:
            module = ast.parse(content)
        except Exception:
            module = None

        if module is not None:

            def _make_class_info(node):
                class_start_line = getattr(node, "lineno", 1) - 1
                for decorator in getattr(node, "decorator_list", []):
                    class_start_line = min(
                        class_start_line,
                        getattr(decorator, "lineno", class_start_line + 1) - 1,
                    )
                class_def_line = max(0, getattr(node, "lineno", 1) - 1)
                class_end_line = getattr(node, "end_lineno", getattr(node, "lineno", 1)) - 1
                return {
                    "name": str(getattr(node, "name", "")),
                    "defLine": class_def_line,
                    "startLine": max(0, class_start_line),
                    "endLine": max(0, class_end_line),
                }

            # Extract both top-level functions and methods in classes.
            def process_body(body, parent_class=None):
                """Recursively process body to find function definitions."""
                for node in body:
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        function_name = str(getattr(node, "name", ""))
                        is_script = self._is_script_definition_name(function_name) or self._definition_has_script_decorator(node)
                        if self._definition_matches_jump_mode(function_name, jump_mode, is_script=is_script):
                            start_line = getattr(node, "lineno", 1) - 1
                            for decorator in getattr(node, "decorator_list", []):
                                start_line = min(start_line, getattr(decorator, "lineno", start_line + 1) - 1)
                            end_line = getattr(node, "end_lineno", getattr(node, "lineno", 1)) - 1
                            class_name = parent_class.get("name") if isinstance(parent_class, dict) else None
                            qualified_name = f"{class_name}.{function_name}" if class_name else function_name
                            entries.append(
                                {
                                    "name": function_name,
                                    "qualifiedName": qualified_name,
                                    "className": class_name,
                                    "classDefLine": parent_class.get("defLine") if isinstance(parent_class, dict) else None,
                                    "classStartLine": parent_class.get("startLine") if isinstance(parent_class, dict) else None,
                                    "classEndLine": parent_class.get("endLine") if isinstance(parent_class, dict) else None,
                                    "isScript": bool(is_script),
                                    "defLine": max(0, getattr(node, "lineno", 1) - 1),
                                    "startLine": max(0, start_line),
                                    "endLine": max(0, end_line),
                                }
                            )
                    elif isinstance(node, ast.ClassDef):
                        # Also process class methods.
                        process_body(node.body, parent_class=_make_class_info(node))

            process_body(module.body)
        else:
            # Fallback regex approach - include all function names and filter by mode.
            pattern = re.compile(r"^\s*(?:async\s+)?def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(")
            raw_lines = content.splitlines()
            def_lines = []
            for line_index, raw_line in enumerate(raw_lines):
                match = pattern.match(raw_line)
                if match:
                    function_name = match.group(1)
                    is_script = self._is_script_definition_name(function_name)
                    if self._definition_matches_jump_mode(function_name, jump_mode, is_script=is_script):
                        def_lines.append((line_index, function_name, is_script))
            for idx, (line_index, function_name, is_script) in enumerate(def_lines):
                start_line = line_index
                while start_line > 0:
                    previous = raw_lines[start_line - 1].strip()
                    if previous.startswith("@") or previous == "":
                        start_line -= 1
                        continue
                    break
                end_line = (def_lines[idx + 1][0] - 1) if idx + 1 < len(def_lines) else max(0, len(raw_lines) - 1)
                entries.append(
                    {
                        "name": function_name,
                        "qualifiedName": function_name,
                        "className": None,
                        "classDefLine": None,
                        "classStartLine": None,
                        "classEndLine": None,
                        "isScript": bool(is_script),
                        "defLine": line_index,
                        "startLine": start_line,
                        "endLine": max(start_line, end_line),
                    }
                )

        entries = sorted(entries, key=lambda item: item["startLine"])
        for entry in entries:
            entry["display"] = _("{name} (line {line})").format(
                name=self._get_definition_display_name(entry),
                line=int(entry.get("defLine", entry.get("startLine", 0))) + 1,
            )
        return entries

    def _get_current_script_entry(self, entries=None):
        entries = entries if entries is not None else self._get_script_entries()
        if not entries:
            return None
        try:
            _col, current_line = self._get_line_col_from_position(self.text.GetInsertionPoint())
        except Exception:
            current_line = 0
        for entry in entries:
            if entry["startLine"] <= current_line <= entry["endLine"]:
                return entry
        return None

    def _get_current_class_entry(self):
        content = self.text.GetValue()
        try:
            _col, current_line = self._get_line_col_from_position(self.text.GetInsertionPoint())
        except Exception:
            current_line = 0
        try:
            module = ast.parse(content)
        except Exception:
            return None

        matches = []

        def process_body(body):
            for node in body:
                if not isinstance(node, ast.ClassDef):
                    continue
                start_line = getattr(node, "lineno", 1) - 1
                for decorator in getattr(node, "decorator_list", []):
                    start_line = min(start_line, getattr(decorator, "lineno", start_line + 1) - 1)
                entry = {
                    "entryType": "class",
                    "name": str(getattr(node, "name", "")),
                    "qualifiedName": str(getattr(node, "name", "")),
                    "defLine": max(0, getattr(node, "lineno", 1) - 1),
                    "startLine": max(0, start_line),
                    "endLine": max(0, getattr(node, "end_lineno", getattr(node, "lineno", 1)) - 1),
                }
                if entry["startLine"] <= current_line <= entry["endLine"]:
                    matches.append(entry)
                process_body(node.body)

        process_body(module.body)
        if not matches:
            return None
        return sorted(matches, key=lambda item: (item["startLine"], item["endLine"] - item["startLine"]))[-1]

    def _goto_script_entry(self, entry):
        def_line = max(0, int(entry.get("defLine", entry.get("startLine", 0))))
        pos = self.text.XYToPosition(0, def_line)
        self.text.SetInsertionPoint(pos)
        self.text.SetSelection(pos, pos)
        try:
            self.text.ShowPosition(pos)
        except Exception:
            pass
        display_name = self._get_definition_display_name(entry)
        entry_type = str(entry.get("entryType", "") or "")
        if entry_type == "class":
            msg = _("class {name}, line {line}").format(name=display_name, line=def_line + 1)
        elif entry.get("isScript"):
            msg = _("script {name}, line {line}").format(name=display_name, line=def_line + 1)
        else:
            msg = _("definition {name}, line {line}").format(name=display_name, line=def_line + 1)
        self.statusbar.SetStatusText(msg, 1)
        ui.message(msg)

    def _delete_script_entry(self, entry):
        start_line = max(0, int(entry.get("startLine", 0)))
        end_line = max(start_line, int(entry.get("endLine", start_line)))

        delete_name = str(entry.get("name", "script"))
        if entry.get("isScript"):
            confirm_template = _("Delete script {name}?")
            deleted_template = _("script {name} deleted")
        else:
            confirm_template = _("Delete definition {name}?")
            deleted_template = _("definition {name} deleted")
        if (
            wx.MessageBox(
                confirm_template.format(name=delete_name),
                _("Script Manager"),
                wx.YES_NO | wx.ICON_QUESTION,
            )
            != wx.YES
        ):
            return

        start_pos = self.text.XYToPosition(0, start_line)
        total_lines = self.text.GetNumberOfLines()
        if end_line + 1 < total_lines:
            end_pos = self.text.XYToPosition(0, end_line + 1)
        else:
            end_pos = self.text.GetLastPosition()

        self.text.Remove(start_pos, end_pos)
        new_pos = min(start_pos, self.text.GetLastPosition())
        self.text.SetInsertionPoint(new_pos)
        self.text.SetSelection(new_pos, new_pos)
        self.modify = True
        self._update_window_title()
        self._update_edit_menu_state()

        msg = deleted_template.format(name=delete_name)
        self.statusbar.SetStatusText(msg, 1)
        ui.message(msg)

    def OnScriptProperties(self, event):
        """Opens properties dialog for the @script decorator of the current script."""
        entry = self._get_current_script_entry()
        if entry is None:
            wx.Bell()
            msg = _("Cursor is not inside a script definition")
            self.statusbar.SetStatusText(msg, 1)
            ui.message(msg)
            return

        data = self._parse_decorator_values(entry)
        dlg = newscriptdialog(
            self,
            -1,
            _("Script properties"),
            initialDefinitionType=newscriptdialog.DEFINITION_TYPE_SCRIPT,
            allowDefinitionTypeChange=False,
        )
        dlg.populate_from_data(data)
        result = dlg.ShowModal()

        if result == wx.ID_OK:
            content = self.text.GetValue()
            raw_lines = content.splitlines()
            def_line_idx = entry["defLine"]
            indent = ""
            if def_line_idx < len(raw_lines):
                def_text = raw_lines[def_line_idx]
                stripped = def_text.lstrip()
                indent = def_text[: len(def_text) - len(stripped)]
            new_decorator = self._generate_decorator_only(
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
                indent=indent,
            )
            self._replace_script_decorator(entry, new_decorator)
        dlg.Destroy()

    def _parse_decorator_values(self, entry):
        """Parse @script decorator arguments from the source. Returns dict."""
        content = self.text.GetValue()
        try:
            module = ast.parse(content)
        except Exception:
            return {}
        entry_def_line = int(entry.get("defLine", -1))
        for node in ast.walk(module):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name != entry["name"]:
                continue
            node_def_line = int(getattr(node, "lineno", 1) - 1)
            if entry_def_line >= 0 and node_def_line != entry_def_line:
                continue
            for dec in node.decorator_list:
                if not isinstance(dec, ast.Call):
                    continue
                func = dec.func
                is_script = (isinstance(func, ast.Name) and func.id == "script") or (
                    isinstance(func, ast.Attribute) and func.attr == "script"
                )
                if not is_script:
                    continue
                result = {}
                for kw in dec.keywords:
                    key = kw.arg
                    val = kw.value
                    if key == "description":
                        result["description"] = _ast_string_value(val)
                    elif key == "category":
                        result["category"] = _ast_string_value(val)
                    elif key == "gesture":
                        result["gesture"] = _ast_string_value(val)
                    elif key == "gestures":
                        if isinstance(val, ast.List):
                            result["gestures"] = [_ast_string_value(elt) for elt in val.elts]
                        else:
                            result["gestures"] = []
                    elif key == "canPropagate":
                        result["canPropagate"] = _ast_bool_value(val)
                    elif key == "bypassInputHelp":
                        result["bypassInputHelp"] = _ast_bool_value(val)
                    elif key == "allowInSleepMode":
                        result["allowInSleepMode"] = _ast_bool_value(val)
                    elif key == "resumeSayAllMode":
                        result["resumeSayAllMode"] = _ast_attribute_value(val)
                    elif key == "speakOnDemand":
                        result["speakOnDemand"] = _ast_bool_value(val)
                raw_name = entry["name"]
                if raw_name.startswith("script_"):
                    raw_name = raw_name[len("script_"):]
                result["name"] = raw_name
                return result
        raw_name = entry["name"]
        if raw_name.startswith("script_"):
            raw_name = raw_name[len("script_"):]
        return {"name": raw_name}

    def _generate_decorator_only(
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
        indent="",
    ):
        """Generate @script(...) decorator text without the def line."""
        args = []
        if chr(10) in description:
            safe_desc = description.replace('"""', '\"\"\"')
            args.append(f'description=_("""{safe_desc}""")')
        else:
            safe_desc = description.replace('"', '\"')
            args.append(f'description=_("{safe_desc}")')
        if category:
            canonical_category = newscriptdialog.normalizeCategoryForCode(category)
            safe_cat = canonical_category.replace('"', '\"')
            args.append(f'category=_("{safe_cat}")')
        normalized = [g for g in (gestures or []) if g]
        if len(normalized) > 1:
            entries = ", ".join(['"' + g.replace('"', '\"') + '"' for g in normalized])
            args.append(f"gestures=[{entries}]")
        elif len(normalized) == 1:
            g = normalized[0].replace('"', '\"')
            args.append(f'gesture="{g}"')
        elif gesture:
            g = gesture.replace('"', '\"')
            args.append(f'gesture="{g}"')
        if canPropagate:
            args.append("canPropagate=True")
        if bypassInputHelp:
            args.append("bypassInputHelp=True")
        if allowInSleepMode:
            args.append("allowInSleepMode=True")
        if resumeSayAllMode:
            args.append(f"resumeSayAllMode={resumeSayAllMode}")
        if speakOnDemand:
            args.append("speakOnDemand=True")
        if not args:
            args.append('description=_("")')
        inner = indent + self._get_indent_unit_text(indent_text=indent)
        nl = chr(10)
        args_str = ("," + nl + inner).join(args)
        return f"{indent}@script({nl}{inner}{args_str}{nl}{indent})"

    def _replace_script_decorator(self, entry, new_decorator):
        """Replace the @script decorator lines of a script entry."""
        start_line = entry["startLine"]
        def_line = entry["defLine"]
        decorator_start_pos = self.text.XYToPosition(0, start_line)
        decorator_end_pos = self.text.XYToPosition(0, def_line)
        if start_line < def_line:
            self.text.Remove(decorator_start_pos, decorator_end_pos)
        self.text.SetInsertionPoint(decorator_start_pos)
        self.text.WriteText(new_decorator + "\n")
        self.modify = True
        self._update_window_title()
        msg = _("script decorator updated")
        self.statusbar.SetStatusText(msg, 1)
        ui.message(msg)

    def OnEditMethodCall(self, event):
        """Edit the parameters of the method call at the cursor position."""
        self._edit_method_call_at_cursor(announceErrors=True)

    def _edit_method_call_at_cursor(self, announceErrors=True):
        """Edit parameters for the call at the current cursor position."""
        call_node, func_name = self._find_call_at_cursor()
        if call_node is None:
            if announceErrors:
                wx.Bell()
                msg = _("No method call found at cursor position")
                self.statusbar.SetStatusText(msg, 1)
                ui.message(msg)
            return False
        if func_name is None:
            if announceErrors:
                wx.Bell()
                msg = _("Could not determine method name")
                self.statusbar.SetStatusText(msg, 1)
                ui.message(msg)
            return False
        callable_obj = _resolve_callable_by_name(func_name, self.text.GetValue(), __name__)
        if callable_obj is None:
            if announceErrors:
                wx.Bell()
                msg = _("Could not resolve method: {name}").format(name=func_name)
                self.statusbar.SetStatusText(msg, 1)
                ui.message(msg)
            return False
        try:
            sig = inspect.signature(callable_obj)
        except (ValueError, TypeError):
            if announceErrors:
                wx.Bell()
                msg = _("Could not get signature for: {name}").format(name=func_name)
                self.statusbar.SetStatusText(msg, 1)
                ui.message(msg)
            return False
        params_info = []
        for pname, param in sig.parameters.items():
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue
            if pname in ("self", "cls"):
                continue
            pinfo = _classify_param_for_dialog(param)
            pinfo["name"] = pname
            params_info.append(pinfo)
        if not params_info:
            if announceErrors:
                wx.Bell()
                msg = _("Method {name} has no editable parameters").format(name=func_name)
                self.statusbar.SetStatusText(msg, 1)
                ui.message(msg)
            return False
        current_values = self._parse_call_arguments(call_node, params_info)
        dlg = MethodCallEditDialog(self, func_name, params_info, current_values)
        result = dlg.ShowModal()
        if result == wx.ID_OK:
            new_values = dlg.get_values()
            new_call_text = self._build_method_call_text(call_node, params_info, new_values)
            self._replace_call_in_text(call_node, new_call_text)
        dlg.Destroy()
        return True

    def _find_call_at_cursor(self):
        """Find the innermost Call AST node at the current cursor position."""
        content = self.text.GetValue()
        pos = self.text.GetInsertionPoint()
        col, line = self._get_line_col_from_position(pos)
        cursor_line_1 = line + 1  # 1-based (AST)
        cursor_col = col
        
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return self._find_text_call_at_cursor(content, pos)
        
        best_func_call = None
        best_func_size = None
        best_range_call = None
        best_range_size = None
        
        # Also track calls where the cursor is in the function part (name/attribute)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            
            n_start_line = getattr(node, "lineno", None)
            n_end_line = getattr(node, "end_lineno", None)
            n_start_col = getattr(node, "col_offset", 0)
            n_end_col = getattr(node, "end_col_offset", None)
            
            if n_start_line is None or n_end_line is None:
                continue
            
            in_range = False
            in_func = False
            
            # Check if cursor is within the Call node's full range
            if n_start_line < cursor_line_1 < n_end_line:
                in_range = True
            elif n_start_line == n_end_line == cursor_line_1:
                if n_end_col is not None:
                    in_range = n_start_col <= cursor_col <= n_end_col
                else:
                    in_range = cursor_col >= n_start_col
            elif n_start_line == cursor_line_1 < n_end_line:
                in_range = cursor_col >= n_start_col
            elif n_start_line < cursor_line_1 == n_end_line:
                in_range = n_end_col is None or cursor_col <= n_end_col
            
            # If not in call range, check if cursor is in the func node (name/attribute part)
            if isinstance(node.func, (ast.Name, ast.Attribute)):
                func_start_line = getattr(node.func, "lineno", None)
                func_end_line = getattr(node.func, "end_lineno", None)
                func_start_col = getattr(node.func, "col_offset", 0)
                func_end_col = getattr(node.func, "end_col_offset", None)
                
                if func_start_line is not None and func_end_line is not None:
                    # Check if cursor is in the function name/attribute part
                    if func_start_line == cursor_line_1 == func_end_line:
                        if func_end_col is not None:
                            in_func = func_start_col <= cursor_col <= func_end_col
                        else:
                            in_func = cursor_col >= func_start_col
            
            if not (in_range or in_func):
                continue
            
            size = (n_end_line - n_start_line) * 10000 + (n_end_col or 0) - n_start_col
            if in_func:
                if best_func_size is None or size < best_func_size:
                    best_func_call = node
                    best_func_size = size
            if best_range_size is None or size > best_range_size:
                best_range_call = node
                best_range_size = size

        selected_call = best_func_call if best_func_call is not None else best_range_call
        if selected_call is None:
            return self._find_text_call_at_cursor(content, pos)

        func_name = _get_call_func_name(selected_call.func)
        return selected_call, func_name

    def _find_text_call_at_cursor(self, content, cursor_pos):
        """Fallback call detection for syntactically incomplete placeholder calls."""
        if not content:
            return None, None

        n = len(content)
        if n <= 0:
            return None, None
        cursor_pos = max(0, min(int(cursor_pos), n))

        stack = []
        call_ranges = []
        for idx, ch in enumerate(content):
            if ch == "(":
                stack.append(idx)
            elif ch == ")" and stack:
                open_idx = stack.pop()
                call_ranges.append((open_idx, idx))

        if not call_ranges:
            return None, None

        best_func_call = None
        best_func_size = None
        best_range_call = None
        best_range_size = None

        for open_idx, close_idx in call_ranges:
            i = open_idx - 1
            while i >= 0 and content[i].isspace():
                i -= 1
            if i < 0:
                continue

            func_end = i + 1
            while i >= 0 and (content[i].isalnum() or content[i] in "._"):
                i -= 1
            func_start = i + 1
            if func_start >= func_end:
                continue

            func_text = content[func_start:func_end].strip()
            if not re.match(r"^[A-Za-z_][A-Za-z0-9_\.]*$", func_text):
                continue

            call_start = func_start
            call_end = close_idx + 1
            in_range = call_start <= cursor_pos <= call_end
            in_func = func_start <= cursor_pos <= func_end
            if not (in_range or in_func):
                continue

            call_ref = _TextCallRef(
                start_pos=call_start,
                end_pos=call_end,
                args_start=open_idx + 1,
                args_end=close_idx,
                func_text=func_text,
            )
            size = call_end - call_start
            if in_func:
                if best_func_size is None or size < best_func_size:
                    best_func_call = call_ref
                    best_func_size = size
            if best_range_size is None or size > best_range_size:
                best_range_call = call_ref
                best_range_size = size

        selected_call = best_func_call if best_func_call is not None else best_range_call
        if selected_call is None:
            return None, None
        return selected_call, selected_call.func_text

    def _parse_call_arguments(self, call_node, params_info):
        """Extract current arguments of a Call node as dict {param_name: value}."""
        source = self.text.GetValue()
        result = {}
        if isinstance(call_node, _TextCallRef):
            args_text = source[call_node.args_start:call_node.args_end]
            if not args_text.strip():
                return result
            try:
                parsed = ast.parse(f"_f({args_text})", mode="eval")
                call_expr = parsed.body
                if not isinstance(call_expr, ast.Call):
                    return result
            except Exception:
                return result
            for i, arg in enumerate(call_expr.args):
                if i < len(params_info):
                    pname = params_info[i]["name"]
                    result[pname] = _ast_value_to_python(arg, args_text)
            for kw in call_expr.keywords:
                if kw.arg is not None:
                    result[kw.arg] = _ast_value_to_python(kw.value, args_text)
            return result

        for i, arg in enumerate(call_node.args):
            if i < len(params_info):
                pname = params_info[i]["name"]
                result[pname] = _ast_value_to_python(arg, source)
        for kw in call_node.keywords:
            if kw.arg is not None:
                result[kw.arg] = _ast_value_to_python(kw.value, source)
        return result

    def _build_method_call_text(self, call_node, params_info, new_values):
        """Build new method call text from edited parameter values.

        Only params that differ from their defaults are included.
        """
        source = self.text.GetValue()
        if isinstance(call_node, _TextCallRef):
            func_text = call_node.func_text or "unknown"
        else:
            try:
                func_text = ast.get_source_segment(source, call_node.func) or _get_call_func_name(call_node.func) or "unknown"
            except Exception:
                func_text = _get_call_func_name(call_node.func) or "unknown"
        args_parts = []
        for pinfo in params_info:
            pname = pinfo["name"]
            pdefault = pinfo.get("default")
            ptype = pinfo["type"]
            prequired = bool(pinfo.get("required"))
            val = new_values.get(pname)
            if not prequired and ptype in ("str", "raw") and str(val or "").strip() == "":
                continue
            if not prequired and ptype == "choices" and str(val or "").strip() == "":
                continue
            if val is None and pdefault is None:
                continue
            if val == pdefault:
                continue
            if ptype == "choices" and (val is None or val == "") and pdefault is None:
                continue
            val_str = _python_value_to_source(ptype, val, pinfo)
            if val_str is not None:
                args_parts.append(f"{pname}={val_str}")
        return f"{func_text}({', '.join(args_parts)})"

    def _replace_call_in_text(self, call_node, new_call_text):
        """Replace a method call in the editor with new_call_text."""
        start_pos, end_pos = self._get_call_text_range(call_node)
        self.text.Remove(start_pos, end_pos)
        self.text.SetInsertionPoint(start_pos)
        self.text.WriteText(new_call_text)
        self.modify = True
        self._update_window_title()
        msg = _("method call updated")
        self.statusbar.SetStatusText(msg, 1)
        ui.message(msg)

    def _get_script_definition_lines(self):
        """Liefert alle Zeilenindizes mit Definitionen entsprechend dem Sprungmodus."""
        entries = self._get_definition_entries(jump_mode=getattr(self, "_jump_mode", self.JUMP_MODE_SCRIPTS))
        return [int(entry.get("defLine", entry["startLine"])) for entry in entries]

    def _goto_script_definition(self, forward=True):
        """Springt zur nächsten/vorherigen Definition und signalisiert Umbruch."""
        entries = self._get_script_entries()
        if not entries:
            wx.Bell()
            msg = _("no definitions found for filter: {mode}").format(
                mode=self._get_jump_mode_label()
            )
            self.statusbar.SetStatusText(msg, 1)
            ui.message(msg)
            return

        _col, current_line = self._get_line_col_from_position(self.text.GetInsertionPoint())
        wrapped = False

        def _entry_line(entry):
            return int(entry.get("defLine", entry.get("startLine", 0)))

        if forward:
            target_candidates = [entry for entry in entries if _entry_line(entry) > current_line]
            if target_candidates:
                target_entry = target_candidates[0]
            else:
                target_entry = entries[0]
                wrapped = True
        else:
            target_candidates = [entry for entry in entries if _entry_line(entry) < current_line]
            if target_candidates:
                target_entry = target_candidates[-1]
            else:
                target_entry = entries[-1]
                wrapped = True

        if wrapped:
            wx.Bell()

        self._goto_script_entry(target_entry)

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
        except Exception:
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
        page_count = self.notebook.GetPageCount() if hasattr(self, "notebook") else 0
        for index in range(page_count):
            self.notebook.SetSelection(index)
            self.text = self._get_active_editor()
            if not self._confirm_save_for_active_tab(event):
                return
        self.Close()
