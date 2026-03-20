import datetime
import addonHandler
import addonAPIVersion
import os
import config
import sys
import api
import appModuleHandler
import ui
import config
import py_compile
import tempfile
import traceback
import re
import logging
import threading
import shutil
import json
import html
addonHandler.initTranslation()

RUNTIME_MANIFEST_FIELDS = (
	'name',
	'summary',
	'description',
	'author',
	'version',
	'minimumNVDAVersion',
	'lastTestedNVDAVersion',
	'url',
	'docFileName',
)

LABEL_RULES_START = '# scriptmanager-label-rules-start'
LABEL_RULES_END = '# scriptmanager-label-rules-end'
LABEL_SUPPORT_START = '# scriptmanager-label-support-start'
LABEL_SUPPORT_END = '# scriptmanager-label-support-end'

# Global error collector for the current script
_script_error_collector = None
_error_collector_lock = threading.RLock()


class ScriptErrorCollector(logging.Handler):
	"""A custom log handler that collects errors for the current script."""
	
	def __init__(self):
		super().__init__()
		self.errors = []
		self.is_active = False
		self.script_file_path = None
		
	def emit(self, record):
		"""Called when a log entry is created."""
		if not self.is_active:
			return
		
		# Filter only ERROR and CRITICAL messages
		if record.levelno < logging.ERROR:
			return
		
		try:
			# Try to extract line number from traceback
			line_num = 1
			message = record.getMessage()
			
			if record.exc_info and record.exc_info[1]:
				exc = record.exc_info[1]
				if hasattr(exc, 'lineno'):
					line_num = exc.lineno
				# Try to extract from traceback
				tb = record.exc_info[2]
				if tb:
					while tb.tb_next:
						tb = tb.tb_next
					line_num = tb.tb_lineno
			
			error_dict = {
				'line': line_num,
				'message': message,
				'type': record.exc_type.__name__ if record.exc_type else 'Error',
				'timestamp': record.created,
				'logger': record.name
			}
			
			self.errors.append(error_dict)
		except:
			pass
	
	def clear(self):
		"""Clears the error list."""
		with _error_collector_lock:
			self.errors = []
	
	def activate(self, script_file_path=None):
		"""Activates the error collector."""
		with _error_collector_lock:
			self.is_active = True
			self.script_file_path = script_file_path
			self.clear()
	
	def deactivate(self):
		"""Deactivates the error collector."""
		with _error_collector_lock:
			self.is_active = False
	
	def get_errors(self):
		"""Returns a copy of the collected errors."""
		with _error_collector_lock:
			return self.errors.copy()


def get_script_error_collector():
	"""Returns the global ScriptErrorCollector, creates it if necessary."""
	global _script_error_collector
	if _script_error_collector is None:
		_script_error_collector = ScriptErrorCollector()
		# Register the handler with NVDA's logger
		try:
			from logHandler import log
			log.logger.addHandler(_script_error_collector)
		except:
			pass
	return _script_error_collector


def userappmoduleexists(appname):
	userconfigfile = config.getScratchpadDir(True) + os.sep + 'appModules' + os.sep + appname + '.py'
	if os.access(userconfigfile, os.F_OK): return userconfigfile
	else: return None


def get_user_appmodule_path(appname):
	return config.getScratchpadDir(True) + os.sep + 'appModules' + os.sep + appname + '.py'


def appmoduleprovidedbyaddon(appname):
	ret = None
	for addon in addonHandler.getRunningAddons():
		if os.access(addon.path + os.sep + 'appmodules' + os.sep + appname + '.py', os.F_OK): ret = addon
	return ret


def copyappmodulefromaddon(appname, addon):
	addonname = addon.manifest['name']
	addonfullpath = addon.path + os.sep + 'appmodules' + os.sep + appname + '.py'
	os.makedirs(config.getScratchpadDir(True) + os.sep + 'appModules', exist_ok=True)
	userconfigfile = config.getScratchpadDir(True) + os.sep + 'appModules' + os.sep + appname + '.py'
	fd1 = open(addonfullpath, 'r')
	fd2 = open(userconfigfile, 'a')
	ui.message(_("copying appmodule for {appname} from addon {addonname} to user's config folder...").format(addonname=addonname, appname=appname))
	for line in fd1:
		fd2.write(line)
	fd2.close()
	fd1.close()


def createnewmodule(moduletype, modulename, createfile):
	l = moduletype[0].lower()
	u = moduletype[0].upper()
	module_template = [
		'#' + moduletype + 's/' + modulename + '.py',
		'# ' + _('A part of NonVisual Desktop Access (NVDA)'),
		'# ' + _('Copyright (C) 2006-{year} NVDA Contributors').format(year=datetime.date.today().year),
		'# ' + _('This file is covered by the GNU General Public License.'),
		'# ' + _('See the file COPYING for more details.'),
		'import ' + moduletype + 'Handler',
		'import controlTypes',
		'import api',
		'from scriptHandler import script',
		'import addonHandler',
		'# ' + _('remove the comment (#) sign from the next line if (and when) the file belongs to an addon. This will enable localization (translation) features. in your file. See NVDA addon development guide for more info.'),
		'#addonHandler.initTranslation()',
		'class ' + moduletype.replace(l, u, 1) + '(' + moduletype + 'Handler.' + moduletype.replace(l, u, 1) + '):']
	if moduletype in ['appModule', 'globalPlugin']:
		module_template += [chr(9) + '# ' + _('some snapshot variables similar to these in the python console'),
			chr(9) + 'nav = api.getNavigatorObject()',
			chr(9) + 'focus = api.getFocusObject()',
			chr(9) + 'fg = api.getForegroundObject()',
			chr(9) + 'rp = api.getReviewPosition()',
			chr(9) + 'caret = api.getCaretObject()',
			chr(9) + 'desktop = api.getDesktopObject()',
			chr(9) + 'mouse = api.getMouseObject()'
	]
	text = os.linesep.join(module_template)
	if createfile:
		os.makedirs(config.getScratchpadDir(True) + os.sep + moduletype + 's', exist_ok=True)
		userconfigfile = config.getScratchpadDir(True) + os.sep + moduletype + 's' + os.sep + modulename + '.py'
		fd1 = open(userconfigfile, 'w')
		ui.message(_('Creating a new {moduletype}  {modulename}').format(moduletype=moduletype, modulename=modulename))
		fd1.write(text)
		fd1.close()
	else:
		return text


def get_object_base_class_info(focus):
	"""Determines the NVDA driver base class of the given NVDAObject.

	Returns a tuple (dotted_module, short_classname, import_statement), e.g.
	('NVDAObjects.UIA', 'UIA', 'import NVDAObjects.UIA').
	"""
	try:
		import NVDAObjects.UIA
		if isinstance(focus, NVDAObjects.UIA.UIA):
			return ('NVDAObjects.UIA', 'UIA', 'import NVDAObjects.UIA')
	except Exception:
		pass
	try:
		import NVDAObjects.IAccessible
		if isinstance(focus, NVDAObjects.IAccessible.IAccessible):
			return ('NVDAObjects.IAccessible', 'IAccessible', 'import NVDAObjects.IAccessible')
	except Exception:
		pass
	return ('NVDAObjects', 'NVDAObject', 'import NVDAObjects')


def createlabelmodule(appname, focus, createfile):
	"""Creates an AppModule template with a labeling class for an unlabeled object.

	The label class is named 'appname_rolename' and inherits from the real
	NVDA driver base class of *focus* (e.g. NVDAObjects.UIA.UIA for UIA objects).
	"""
	role_name = focus.role.name.lower()
	base_module, base_classname, import_line = get_object_base_class_info(focus)
	base_full = base_module + '.' + base_classname
	class_name = appname + '_' + role_name
	module_template = [
		'#appModules/' + appname + '.py',
		'# ' + _('A part of NonVisual Desktop Access (NVDA)'),
		'# ' + _('Copyright (C) 2006-{year} NVDA Contributors').format(year=datetime.date.today().year),
		'# ' + _('This file is covered by the GNU General Public License.'),
		'# ' + _('See the file COPYING for more details.'),
		'import appModuleHandler',
		'import controlTypes',
		import_line,
		'import api',
		'from scriptHandler import script',
		'import addonHandler',
		'# ' + _('remove the comment (#) sign from the next line if (and when) the file belongs to an addon. This will enable localization (translation) features. in your file. See NVDA addon development guide for more info.'),
		'#addonHandler.initTranslation()',
		'',
		'',
		'class ' + class_name + '(' + base_full + '):',
		chr(9) + '@property',
		chr(9) + 'def name(self):',
		chr(9) + chr(9) + 'return ""  # ' + _('Add the label here'),
		'',
		'',
		'class AppModule(appModuleHandler.AppModule):',
		chr(9) + 'pass',
	]
	text = os.linesep.join(module_template)
	if createfile:
		os.makedirs(config.getScratchpadDir(True) + os.sep + 'appModules', exist_ok=True)
		userconfigfile = config.getScratchpadDir(True) + os.sep + 'appModules' + os.sep + appname + '.py'
		with open(userconfigfile, 'w') as fd:
			ui.message(_('Creating a new appModule for labeling: {appname}').format(appname=appname))
			fd.write(text)
	else:
		return text


def get_label_method_candidates(obj):
	"""Collects selector candidates for the given object."""
	role_name = ''
	try:
		role_name = str(obj.role.name).lower()
	except Exception:
		role_name = ''
	return {
		'role': role_name,
		'automationId': _normalize_label_candidate(_get_object_attribute(obj, ('UIAAutomationId', 'automationID', 'automationId'))),
		'controlId': _normalize_label_candidate(_get_object_attribute(obj, ('windowControlID', 'controlID', 'IAccessibleChildID'))),
		'windowClassName': _normalize_label_candidate(_get_object_attribute(obj, ('windowClassName',))),
	}


def save_label_rule(appmodule_path, rule):
	"""Adds or updates a labeling rule in the given AppModule file."""
	if not rule:
		raise ValueError(_('No labeling rule was provided.'))
	selectors = dict(rule.get('selectors') or {})
	selectors = {
		key: value
		for key, value in selectors.items()
		if value not in (None, '')
	}
	if not selectors.get('role'):
		raise ValueError(_('The labeling rule has no role selector.'))
	rule_to_store = {
		'label': str(rule.get('label') or '').strip(),
		'method': str(rule.get('method') or '').strip(),
		'methodCode': str(rule.get('methodCode') or '').strip(),
		'selectors': selectors,
	}
	if not rule_to_store['label']:
		raise ValueError(_('The labeling rule has no label text.'))

	base_text = _read_existing_appmodule_text(appmodule_path)
	rules = _extract_label_rules(base_text)
	existing_index = _find_existing_rule_index(rules, selectors)
	if existing_index is None:
		rules.append(rule_to_store)
		action = 'created'
	else:
		rules[existing_index] = rule_to_store
		action = 'updated'

	updated_text = _replace_or_append_block(base_text, LABEL_RULES_START, LABEL_RULES_END, _render_label_rules_block(rules))
	updated_text = _replace_or_append_block(updated_text, LABEL_SUPPORT_START, LABEL_SUPPORT_END, _render_label_support_block())
	_write_appmodule_text(appmodule_path, updated_text)
	return action


def _normalize_label_candidate(value):
	if value is None:
		return ''
	value = str(value).strip()
	if value.lower() == 'none':
		return ''
	return value


def _get_object_attribute(obj, attribute_names):
	for attribute_name in attribute_names:
		try:
			value = getattr(obj, attribute_name)
			value = _normalize_label_candidate(value)
			if value:
				return value
		except Exception:
			pass
	try:
		uia_element = getattr(obj, 'UIAElement')
		if 'UIAAutomationId' in attribute_names:
			return _normalize_label_candidate(getattr(uia_element, 'currentAutomationId', ''))
	except Exception:
		pass
	return ''


def _read_existing_appmodule_text(appmodule_path):
	if os.path.exists(appmodule_path):
		with open(appmodule_path, 'r', encoding='utf-8') as appmodule_file:
			return appmodule_file.read()
	os.makedirs(os.path.dirname(appmodule_path), exist_ok=True)
	return createnewmodule('appModule', os.path.splitext(os.path.basename(appmodule_path))[0], False) + os.linesep


def _write_appmodule_text(appmodule_path, text):
	os.makedirs(os.path.dirname(appmodule_path), exist_ok=True)
	with open(appmodule_path, 'w', encoding='utf-8') as appmodule_file:
		appmodule_file.write(text)


def _extract_label_rules(text):
	block = _extract_block(text, LABEL_RULES_START, LABEL_RULES_END)
	if not block:
		return []
	match = re.search(r'SCRIPT_MANAGER_LABEL_RULES_JSON\s*=\s*r?"""\n?(.*?)\n?"""', block, re.DOTALL)
	if not match:
		return []
	try:
		data = json.loads(match.group(1))
		if isinstance(data, list):
			return data
	except Exception:
		return []
	return []


def _extract_block(text, start_marker, end_marker):
	start_index = text.find(start_marker)
	if start_index == -1:
		return None
	end_index = text.find(end_marker, start_index)
	if end_index == -1:
		return None
	end_index += len(end_marker)
	return text[start_index:end_index]


def _replace_or_append_block(text, start_marker, end_marker, new_block):
	existing_block = _extract_block(text, start_marker, end_marker)
	if existing_block is not None:
		return text.replace(existing_block, new_block)
	if text and not text.endswith(os.linesep):
		text += os.linesep
	if text and not text.endswith(os.linesep * 2):
		text += os.linesep
	return text + new_block + os.linesep


def _find_existing_rule_index(rules, selectors):
	for index, existing_rule in enumerate(rules):
		if dict(existing_rule.get('selectors') or {}) == selectors:
			return index
	return None


def _render_label_rules_block(rules):
	json_text = json.dumps(rules, indent=2, ensure_ascii=False, sort_keys=True)
	return os.linesep.join([
		LABEL_RULES_START,
		'SCRIPT_MANAGER_LABEL_RULES_JSON = r"""',
		json_text,
		'"""',
		'try:',
			chr(9) + 'SCRIPT_MANAGER_LABEL_RULES = json.loads(SCRIPT_MANAGER_LABEL_RULES_JSON)',
		'except Exception:',
			chr(9) + 'SCRIPT_MANAGER_LABEL_RULES = []',
		LABEL_RULES_END,
	])


def _render_label_support_block():
	return os.linesep.join([
		LABEL_SUPPORT_START,
		'import appModuleHandler',
		'import json',
		'try:',
			chr(9) + 'import NVDAObjects',
		'except Exception:',
			chr(9) + 'NVDAObjects = None',
		'try:',
			chr(9) + 'import NVDAObjects.UIA',
		'except Exception:',
			chr(9) + 'pass',
		'try:',
			chr(9) + 'import NVDAObjects.IAccessible',
		'except Exception:',
			chr(9) + 'pass',
		'',
		'def _scriptManager_getObjectProperty(obj, key):',
			chr(9) + 'if key == "role":',
			chr(9) + chr(9) + 'try:',
			chr(9) + chr(9) + chr(9) + 'return str(obj.role.name).lower()',
			chr(9) + chr(9) + 'except Exception:',
			chr(9) + chr(9) + chr(9) + 'return ""',
			chr(9) + 'try:',
			chr(9) + chr(9) + 'value = getattr(obj, key)',
			chr(9) + 'except Exception:',
			chr(9) + chr(9) + 'value = ""',
			chr(9) + 'if not value and key == "automationId":',
			chr(9) + chr(9) + 'for attrName in ("UIAAutomationId", "automationID", "automationId"):',
			chr(9) + chr(9) + chr(9) + 'try:',
			chr(9) + chr(9) + chr(9) + chr(9) + 'value = getattr(obj, attrName)',
			chr(9) + chr(9) + chr(9) + chr(9) + 'if value:',
			chr(9) + chr(9) + chr(9) + chr(9) + chr(9) + 'break',
			chr(9) + chr(9) + chr(9) + 'except Exception:',
			chr(9) + chr(9) + chr(9) + chr(9) + 'pass',
			chr(9) + chr(9) + 'if not value:',
			chr(9) + chr(9) + chr(9) + 'try:',
			chr(9) + chr(9) + chr(9) + chr(9) + 'value = obj.UIAElement.currentAutomationId',
			chr(9) + chr(9) + chr(9) + 'except Exception:',
			chr(9) + chr(9) + chr(9) + chr(9) + 'value = ""',
			chr(9) + 'elif not value and key == "controlId":',
			chr(9) + chr(9) + 'for attrName in ("windowControlID", "controlID", "IAccessibleChildID"):',
			chr(9) + chr(9) + chr(9) + 'try:',
			chr(9) + chr(9) + chr(9) + chr(9) + 'value = getattr(obj, attrName)',
			chr(9) + chr(9) + chr(9) + chr(9) + 'if value not in (None, ""):',
			chr(9) + chr(9) + chr(9) + chr(9) + chr(9) + 'break',
			chr(9) + chr(9) + chr(9) + 'except Exception:',
			chr(9) + chr(9) + chr(9) + chr(9) + 'pass',
			chr(9) + 'elif not value and key == "windowClassName":',
			chr(9) + chr(9) + 'try:',
			chr(9) + chr(9) + chr(9) + 'value = obj.windowClassName',
			chr(9) + chr(9) + 'except Exception:',
			chr(9) + chr(9) + chr(9) + 'value = ""',
			chr(9) + 'if value is None:',
			chr(9) + chr(9) + 'return ""',
			chr(9) + 'value = str(value).strip()',
			chr(9) + 'if value.lower() == "none":',
			chr(9) + chr(9) + 'return ""',
			chr(9) + 'return value',
		'',
		'def _scriptManager_ruleMatches(obj, rule):',
			chr(9) + 'selectors = dict(rule.get("selectors") or {})',
			chr(9) + 'for key, expected in selectors.items():',
			chr(9) + chr(9) + 'if _scriptManager_getObjectProperty(obj, key) != str(expected):',
			chr(9) + chr(9) + chr(9) + 'return False',
			chr(9) + 'return True',
		'',
		'def _scriptManager_getLabelForObject(obj):',
			chr(9) + 'for rule in SCRIPT_MANAGER_LABEL_RULES:',
			chr(9) + chr(9) + 'if _scriptManager_ruleMatches(obj, rule):',
			chr(9) + chr(9) + chr(9) + 'return str(rule.get("label") or "")',
			chr(9) + 'return ""',
		'',
		'class ScriptManagerLabelNVDAObject(NVDAObjects.NVDAObject if NVDAObjects else object):',
			chr(9) + '@property',
			chr(9) + 'def name(self):',
			chr(9) + chr(9) + 'label = _scriptManager_getLabelForObject(self)',
			chr(9) + chr(9) + 'if label:',
			chr(9) + chr(9) + chr(9) + 'return label',
			chr(9) + chr(9) + 'try:',
			chr(9) + chr(9) + chr(9) + 'return super(ScriptManagerLabelNVDAObject, self).name',
			chr(9) + chr(9) + 'except Exception:',
			chr(9) + chr(9) + chr(9) + 'return ""',
		'',
		'class ScriptManagerLabelUIA(NVDAObjects.UIA.UIA if "NVDAObjects" in globals() and hasattr(NVDAObjects, "UIA") else ScriptManagerLabelNVDAObject):',
			chr(9) + '@property',
			chr(9) + 'def name(self):',
			chr(9) + chr(9) + 'label = _scriptManager_getLabelForObject(self)',
			chr(9) + chr(9) + 'if label:',
			chr(9) + chr(9) + chr(9) + 'return label',
			chr(9) + chr(9) + 'try:',
			chr(9) + chr(9) + chr(9) + 'return super(ScriptManagerLabelUIA, self).name',
			chr(9) + chr(9) + 'except Exception:',
			chr(9) + chr(9) + chr(9) + 'return ""',
		'',
		'class ScriptManagerLabelIAccessible(NVDAObjects.IAccessible.IAccessible if "NVDAObjects" in globals() and hasattr(NVDAObjects, "IAccessible") else ScriptManagerLabelNVDAObject):',
			chr(9) + '@property',
			chr(9) + 'def name(self):',
			chr(9) + chr(9) + 'label = _scriptManager_getLabelForObject(self)',
			chr(9) + chr(9) + 'if label:',
			chr(9) + chr(9) + chr(9) + 'return label',
			chr(9) + chr(9) + 'try:',
			chr(9) + chr(9) + chr(9) + 'return super(ScriptManagerLabelIAccessible, self).name',
			chr(9) + chr(9) + 'except Exception:',
			chr(9) + chr(9) + chr(9) + 'return ""',
		'',
		'def _scriptManager_getOverlayClassForObject(obj):',
			chr(9) + 'try:',
			chr(9) + chr(9) + 'if "NVDAObjects" in globals() and hasattr(NVDAObjects, "UIA") and isinstance(obj, NVDAObjects.UIA.UIA):',
			chr(9) + chr(9) + chr(9) + 'return ScriptManagerLabelUIA',
			chr(9) + 'except Exception:',
			chr(9) + chr(9) + 'pass',
			chr(9) + 'try:',
			chr(9) + chr(9) + 'if "NVDAObjects" in globals() and hasattr(NVDAObjects, "IAccessible") and isinstance(obj, NVDAObjects.IAccessible.IAccessible):',
			chr(9) + chr(9) + chr(9) + 'return ScriptManagerLabelIAccessible',
			chr(9) + 'except Exception:',
			chr(9) + chr(9) + 'pass',
			chr(9) + 'if _scriptManager_getLabelForObject(obj):',
			chr(9) + chr(9) + 'return ScriptManagerLabelNVDAObject',
			chr(9) + 'return None',
		'',
		'try:',
			chr(9) + 'AppModule',
		'except NameError:',
			chr(9) + 'class AppModule(appModuleHandler.AppModule):',
			chr(9) + chr(9) + 'pass',
		'',
		'_scriptManager_original_chooseNVDAObjectOverlayClasses = getattr(AppModule, "chooseNVDAObjectOverlayClasses", None)',
		'',
		'def _scriptManager_chooseNVDAObjectOverlayClasses(self, obj, clsList):',
			chr(9) + 'if _scriptManager_original_chooseNVDAObjectOverlayClasses:',
			chr(9) + chr(9) + '_scriptManager_original_chooseNVDAObjectOverlayClasses(self, obj, clsList)',
			chr(9) + 'overlayClass = _scriptManager_getOverlayClassForObject(obj)',
			chr(9) + 'if overlayClass and overlayClass not in clsList:',
			chr(9) + chr(9) + 'clsList.insert(0, overlayClass)',
		'',
		'AppModule.chooseNVDAObjectOverlayClasses = _scriptManager_chooseNVDAObjectOverlayClasses',
		LABEL_SUPPORT_END,
	])


def check_script_for_syntax_errors(script_content):
	"""
	Checks the script for syntax errors.
	Returns a list of errors with line numbers.
	
	Returns:
		List of dictionaries with keys: 'line', 'message', 'type'
	"""
	errors = []
	try:
		# Try to check with compile()
		compile(script_content, '<script>', 'exec')
	except SyntaxError as e:
		errors.append({
			'line': e.lineno if e.lineno else 1,
			'message': e.msg or str(e),
			'type': 'SyntaxError',
			'offset': e.offset
		})
	except Exception as e:
		# Other errors
		errors.append({
			'line': 1,
			'message': str(e),
			'type': type(e).__name__
		})
	
	return errors


def collect_runtime_errors_from_log():
	"""
	Collects errors from NVDA's log that occurred during the last plugin reload.
	
	Returns:
		Liste von Fehlern
	"""
	try:
		collector = get_script_error_collector()
		return collector.get_errors()
	except Exception:
		return []


def activate_error_logging(script_file_path=None):
	"""
	Activates error logging for the current script.
	This should be called before reloading plugins.
	
	Args:
		script_file_path: Optional path to the script to filter errors
	"""
	try:
		collector = get_script_error_collector()
		collector.activate(script_file_path)
	except Exception:
		pass


def deactivate_error_logging():
	"""
	Deactivates error logging.
	"""
	try:
		collector = get_script_error_collector()
		collector.deactivate()
	except Exception:
		pass


def check_script_for_errors(script_content):
	"""
	Extended error checking for a script.
	Checks for syntax errors, compile errors and tries to execute the script.
	Also collects errors from NVDA's log.
	
	Returns:
		Tuple: (errors_list, error_details_dict)
	"""
	errors = []
	
	# 1. Check for syntax errors
	syntax_errors = check_script_for_syntax_errors(script_content)
	if syntax_errors:
		errors.extend(syntax_errors)
		return errors, _format_errors_for_display(errors)
	
	# 2. Try to compile the script
	try:
		with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as tmp:
			tmp.write(script_content)
			tmp_path = tmp.name
		
		try:
			# Try to compile
			py_compile.compile(tmp_path, doraise=True)
		except py_compile.PyCompileError as e:
			errors.append({
				'line': _extract_line_number_from_error(str(e)),
				'message': str(e),
				'type': 'CompileError'
			})
		finally:
				# Delete temporary file
			try:
				os.unlink(tmp_path)
			except Exception:
				pass
	except Exception as e:
		errors.append({
			'line': 1,
			'message': str(e),
			'type': type(e).__name__
		})
	
	# 3. If no compile errors, try to execute the script
	if not errors:
		execution_errors = try_execute_script(script_content)
		if execution_errors:
			errors.extend(execution_errors)
	
	# 4. Also collect errors from the log (e.g., from plugin reload)
	log_errors = collect_runtime_errors_from_log()
	if log_errors:
		# Filter duplicates and add log errors
		for log_error in log_errors:
			# Check if this error is already in the list
			is_duplicate = any(
				e.get('line') == log_error.get('line') and 
				e.get('message') == log_error.get('message')
				for e in errors
			)
			if not is_duplicate:
				errors.append(log_error)
	
	return errors, _format_errors_for_display(errors)


def _extract_line_number_from_error(error_string):
	"""Extracts the line number from an error message."""
	match = re.search(r'line (\d+)', error_string, re.IGNORECASE)
	if match:
		return int(match.group(1))
	return 1


def _format_errors_for_display(errors):
	"""
	Formats errors for display.
	
	Returns:
		A formatted string for display
	"""
	if not errors:
		return None
	
	formatted_lines = []
	for error in errors:
		line_num = error.get('line', 1)
		message = error.get('message', _('Unknown error'))
		error_type = error.get('type', 'Error')
		
		formatted_lines.append(_("Line {line}: {error_type} - {message}").format(line=line_num, error_type=error_type, message=message))
	
	return "\n".join(formatted_lines)


def try_execute_script(script_content, script_name='<script>'):
	"""
	Tries to execute the script and captures runtime errors.
	This is used to capture errors when plugins are reloaded.
	
	Args:
		script_content: The Python code as a string
		script_name: A name for the script (for error reporting)
	
	Returns:
		List of errors (or empty list if no errors occurred)
	"""
	errors = []
	
	try:
		# Try to execute the code
		code_obj = compile(script_content, script_name, 'exec')
		
		# Create a safe execution environment
		exec_globals = {
			'__name__': '__addon__',
			'__builtins__': __builtins__,
		}
		
		# Try to execute
		exec(code_obj, exec_globals)
		
	except SyntaxError as e:
		errors.append({
			'line': e.lineno if e.lineno else 1,
			'message': e.msg or str(e),
			'type': 'SyntaxError',
			'offset': e.offset
		})
	except Exception as e:
		# Extract line number from traceback
		import traceback
		tb = traceback.extract_tb(e.__traceback__)
		line_num = 1
		
		# Go through the stack and find the relevant line
		for frame in tb:
			if script_name in frame.filename or '<script>' in frame.filename:
				line_num = frame.lineno
				break
		
		errors.append({
			'line': line_num,
			'message': str(e),
			'type': type(e).__name__
		})
	
	return errors


def get_default_addon_manifest_data():
	return {
		'addon_name': '',
		'addon_summary': '',
		'addon_description': '',
		'addon_version': '1.0.0',
		'addon_changelog': '',
		'addon_author': '',
		'addon_url': '',
		'addon_sourceURL': '',
		'addon_docFileName': 'readme.html',
		'addon_minimumNVDAVersion': addonAPIVersion.formatForGUI(addonAPIVersion.BACK_COMPAT_TO),
		'addon_lastTestedNVDAVersion': addonAPIVersion.formatForGUI(addonAPIVersion.CURRENT),
		'addon_updateChannel': '',
		'addon_license': '',
		'addon_licenseURL': '',
	}


def build_addon_from_scratchpad(manifest_data, output_path):
	manifest_data = _prepare_manifest_data(manifest_data)
	output_path = os.path.abspath(output_path)
	output_dir = os.path.dirname(output_path)
	os.makedirs(output_dir, exist_ok=True)

	with tempfile.TemporaryDirectory(prefix='scriptmanagerAddonBuild_') as temp_dir:
		addon_dir = os.path.join(temp_dir, manifest_data['addon_name'])
		os.makedirs(addon_dir, exist_ok=True)
		_copy_scratchpad_to_addon(addon_dir)
		_write_runtime_manifest(addon_dir, manifest_data)
		_write_builder_metadata(addon_dir, manifest_data)
		_ensure_documentation_file(addon_dir, manifest_data)
		bundle = addonHandler.createAddonBundleFromPath(addon_dir, destDir=output_dir)
		bundle_path = getattr(bundle, '_path', None)
		if not bundle_path:
			bundle_path = os.path.join(
				output_dir,
				'{name}-{version}.{extension}'.format(
					name=manifest_data['addon_name'],
					version=manifest_data['addon_version'],
					extension=addonHandler.BUNDLE_EXTENSION,
				),
			)
		if os.path.normcase(bundle_path) != os.path.normcase(output_path):
			if os.path.exists(output_path):
				os.remove(output_path)
			shutil.move(bundle_path, output_path)
			bundle_path = output_path
		return bundle_path


def install_addon_bundle_for_testing(bundle_path, parent_window):
	from gui import addonGui
	config.conf['development']['enableScratchpadDir'] = False
	config.conf.save()
	installed = addonGui.installAddon(parent_window, bundle_path)
	if installed:
		addonGui.promptUserForRestart()
	return installed


def _prepare_manifest_data(manifest_data):
	prepared = get_default_addon_manifest_data()
	for key, value in (manifest_data or {}).items():
		prepared[key] = _clean_manifest_value(value)
	if not prepared['addon_minimumNVDAVersion']:
		prepared['addon_minimumNVDAVersion'] = '0.0.0'
	if not prepared['addon_lastTestedNVDAVersion']:
		prepared['addon_lastTestedNVDAVersion'] = prepared['addon_minimumNVDAVersion']
	return prepared


def _clean_manifest_value(value):
	if value is None:
		return ''
	return str(value).strip()


def _scratchpad_contains_files(scratchpad_dir):
	for root, _dirs, files in os.walk(scratchpad_dir):
		for filename in files:
			if root == scratchpad_dir and filename.lower() == addonHandler.MANIFEST_FILENAME:
				continue
			return True
	return False


def _copy_scratchpad_to_addon(addon_dir):
	scratchpad_dir = config.getScratchpadDir(True)
	if not _scratchpad_contains_files(scratchpad_dir):
		raise ValueError(_('The scratchpad directory does not contain any files to package.'))
	for entry in os.listdir(scratchpad_dir):
		if entry.lower() == addonHandler.MANIFEST_FILENAME:
			continue
		source_path = os.path.join(scratchpad_dir, entry)
		target_path = os.path.join(addon_dir, entry)
		if os.path.isdir(source_path):
			shutil.copytree(source_path, target_path, dirs_exist_ok=True)
		else:
			os.makedirs(os.path.dirname(target_path), exist_ok=True)
			shutil.copy2(source_path, target_path)


def _write_runtime_manifest(addon_dir, manifest_data):
	manifest_lines = [
		'name = {name}'.format(name=manifest_data['addon_name']),
		'summary = {summary}'.format(summary=_quote_manifest_string(manifest_data['addon_summary'])),
		'description = {description}'.format(description=_quote_manifest_multiline(manifest_data['addon_description'])),
		'author = {author}'.format(author=_quote_manifest_string(manifest_data['addon_author'])),
		'version = {version}'.format(version=_quote_manifest_string(manifest_data['addon_version'])),
		'minimumNVDAVersion = {version}'.format(version=manifest_data['addon_minimumNVDAVersion']),
		'lastTestedNVDAVersion = {version}'.format(version=manifest_data['addon_lastTestedNVDAVersion']),
	]
	if manifest_data['addon_url']:
		manifest_lines.append('url = {url}'.format(url=_quote_manifest_string(manifest_data['addon_url'])))
	if manifest_data['addon_docFileName']:
		manifest_lines.append('docFileName = {doc}'.format(doc=_quote_manifest_string(manifest_data['addon_docFileName'])))
	manifest_path = os.path.join(addon_dir, addonHandler.MANIFEST_FILENAME)
	with open(manifest_path, 'w', encoding='utf-8') as manifest_file:
		manifest_file.write('\n'.join(manifest_lines) + '\n')


def _write_builder_metadata(addon_dir, manifest_data):
	metadata_path = os.path.join(addon_dir, 'addonBuilderMetadata.json')
	with open(metadata_path, 'w', encoding='utf-8') as metadata_file:
		json.dump(manifest_data, metadata_file, indent=2, ensure_ascii=False, sort_keys=True)


def _ensure_documentation_file(addon_dir, manifest_data):
	doc_file_name = manifest_data.get('addon_docFileName', '')
	if not doc_file_name:
		return
	doc_root = os.path.join(addon_dir, 'doc')
	if os.path.isdir(doc_root):
		for root, _dirs, files in os.walk(doc_root):
			if doc_file_name in files:
				return
	target_dir = os.path.join(doc_root, 'en')
	os.makedirs(target_dir, exist_ok=True)
	target_path = os.path.join(target_dir, doc_file_name)
	if os.path.exists(target_path):
		return
	title = html.escape(manifest_data.get('addon_summary') or manifest_data.get('addon_name') or 'NVDA Add-on')
	description = html.escape(manifest_data.get('addon_description') or '')
	changelog = html.escape(manifest_data.get('addon_changelog') or '')
	author = html.escape(manifest_data.get('addon_author') or '')
	html_text = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
</head>
<body>
<h1>{title}</h1>
<p>{description}</p>
<p><strong>{authorLabel}</strong> {author}</p>
{changelogBlock}
</body>
</html>
""".format(
		title=title,
		description=description.replace('\n', '<br>'),
		authorLabel=html.escape(_('Author:')),
		author=author,
		changelogBlock=(
			'<h2>{heading}</h2><p>{content}</p>'.format(
				heading=html.escape(_('Changelog')),
				content=changelog.replace('\n', '<br>'),
			)
			if changelog else ''
		),
	)
	with open(target_path, 'w', encoding='utf-8') as doc_file:
		doc_file.write(html_text)


def _quote_manifest_string(value):
	return '"{value}"'.format(value=str(value).replace('\\', '\\\\').replace('"', '\\"'))


def _quote_manifest_multiline(value):
	return '"""{value}"""'.format(value=str(value).replace('"""', '\\"\\"\\"'))

