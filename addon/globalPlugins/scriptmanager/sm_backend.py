import datetime
import addonHandler
import addonAPIVersion
import os
import config
import languageHandler
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
import urllib.parse
import urllib.request
import wx
import gui
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

SCRATCHPAD_REQUIRED_SUBDIRS = (
	'appModules',
	'globalPlugins',
	'brailleDisplayDrivers',
	'synthDrivers',
	'visionEnhancementProviders',
)

SCRIPTMANAGER_CONFIG_SECTION = "scriptmanager"
SCRATCHPAD_ACTIVATION_ASK = "ask"
SCRATCHPAD_ACTIVATION_ALWAYS = "alwaysEnable"
SCRATCHPAD_ACTIVATION_NEVER = "neverEnable"
SCRATCHPAD_ACTIVATION_VALUES = (
	SCRATCHPAD_ACTIVATION_ASK,
	SCRATCHPAD_ACTIVATION_ALWAYS,
	SCRATCHPAD_ACTIVATION_NEVER,
)

SCRIPTMANAGER_CONFIG_SPEC = {
	"scratchpadActivation": "string(default='neverEnable')",
	"includeBlacklistedModules": "boolean(default=False)",
	"translateDocstrings": "boolean(default=False)",
	"showAddonFolderHint": "boolean(default=True)",
	"jumpMode": "string(default='scripts')",
	"indentWithSpaces": "boolean(default=False)",
	"indentWidth": "integer(default=4,min=1,max=12)",
}

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


def ensure_scriptmanager_config_spec():
	"""Ensure Script Manager keys exist in NVDA profile config."""
	spec = config.conf.spec
	if SCRIPTMANAGER_CONFIG_SECTION not in spec:
		spec[SCRIPTMANAGER_CONFIG_SECTION] = {}
	section = spec[SCRIPTMANAGER_CONFIG_SECTION]
	for key, value in SCRIPTMANAGER_CONFIG_SPEC.items():
		if key not in section:
			section[key] = value


def _get_scriptmanager_conf():
	ensure_scriptmanager_config_spec()
	return config.conf[SCRIPTMANAGER_CONFIG_SECTION]


def normalize_scratchpad_activation_mode(mode):
	mode = str(mode or "").strip()
	if mode in SCRATCHPAD_ACTIVATION_VALUES:
		return mode
	lower_mode = mode.lower()
	if lower_mode in ("yes", "true", "always", "enable", "alwaysenable"):
		return SCRATCHPAD_ACTIVATION_ALWAYS
	return SCRATCHPAD_ACTIVATION_NEVER


def get_scratchpad_activation_mode():
	try:
		value = _get_scriptmanager_conf().get("scratchpadActivation", SCRATCHPAD_ACTIVATION_NEVER)
	except Exception:
		return SCRATCHPAD_ACTIVATION_NEVER
	return normalize_scratchpad_activation_mode(value)


def set_scratchpad_activation_mode(mode):
	_get_scriptmanager_conf()["scratchpadActivation"] = normalize_scratchpad_activation_mode(mode)


def get_include_blacklisted_modules():
	try:
		return bool(_get_scriptmanager_conf().get("includeBlacklistedModules", False))
	except Exception:
		return False


def set_include_blacklisted_modules(enabled):
	_get_scriptmanager_conf()["includeBlacklistedModules"] = bool(enabled)


def get_translate_docstrings_enabled():
	try:
		return bool(_get_scriptmanager_conf().get("translateDocstrings", False))
	except Exception:
		return False


def set_translate_docstrings_enabled(enabled):
	_get_scriptmanager_conf()["translateDocstrings"] = bool(enabled)


def get_show_addon_folder_hint():
	try:
		return bool(_get_scriptmanager_conf().get("showAddonFolderHint", True))
	except Exception:
		return True


def set_show_addon_folder_hint(enabled):
	_get_scriptmanager_conf()["showAddonFolderHint"] = bool(enabled)


_VALID_JUMP_MODES = ("scripts", "functionsOnly", "allDefinitions")


def get_jump_mode():
	try:
		value = _get_scriptmanager_conf().get("jumpMode", "scripts")
		if value not in _VALID_JUMP_MODES:
			return "scripts"
		return value
	except Exception:
		return "scripts"


def set_jump_mode(mode):
	if mode not in _VALID_JUMP_MODES:
		mode = "scripts"
	_get_scriptmanager_conf()["jumpMode"] = mode


def get_indent_with_spaces_enabled():
	try:
		return bool(_get_scriptmanager_conf().get("indentWithSpaces", False))
	except Exception:
		return False


def set_indent_with_spaces_enabled(enabled):
	_get_scriptmanager_conf()["indentWithSpaces"] = bool(enabled)


def get_indent_width():
	try:
		value = int(_get_scriptmanager_conf().get("indentWidth", 4))
	except Exception:
		value = 4
	return max(1, min(12, value))


def set_indent_width(width):
	try:
		width = int(width)
	except Exception:
		width = 4
	_get_scriptmanager_conf()["indentWidth"] = max(1, min(12, width))


def is_scratchpad_enabled():
	try:
		return bool(config.conf["development"]["enableScratchpadDir"])
	except Exception:
		return False


def set_scratchpad_enabled(enabled):
	try:
		config.conf["development"]["enableScratchpadDir"] = bool(enabled)
		return True
	except Exception:
		return False


def get_scratchpad_disabled_message(reasonText=""):
	message = _(
		"Scratchpad processing is disabled. Enable it in NVDA's Advanced settings to use this action."
	)
	if reasonText:
		return "{reason}\n\n{message}".format(reason=reasonText, message=message)
	return message


def ensure_scratchpad_available(parent=None, reasonText=""):
	"""Return True only when NVDA scratchpad processing is already enabled."""
	ensure_scriptmanager_config_spec()
	return is_scratchpad_enabled()


def _normalize_target_language_code(languageCode):
	languageCode = str(languageCode or "").replace("-", "_")
	parts = [part for part in languageCode.split("_") if part]
	if not parts:
		return "en"
	return parts[0].lower()


def get_nvda_ui_language_code():
	try:
		return _normalize_target_language_code(languageHandler.getLanguage())
	except Exception:
		return "en"


def translate_text_with_google(text, targetLanguage=None, timeoutSeconds=4):
	"""Translate text via Google Translate web endpoint.

	Returns the original text on failure.
	"""
	text = str(text or "")
	if not text.strip():
		return text
	targetLanguage = _normalize_target_language_code(targetLanguage or get_nvda_ui_language_code())
	query = urllib.parse.urlencode(
		{
			"client": "gtx",
			"sl": "auto",
			"tl": targetLanguage,
			"dt": "t",
			"q": text,
		}
	)
	url = "https://translate.googleapis.com/translate_a/single?{query}".format(query=query)
	request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
	try:
		with urllib.request.urlopen(request, timeout=timeoutSeconds) as response:
			payload = response.read().decode("utf-8", "replace")
		data = json.loads(payload)
		segments = data[0] if isinstance(data, list) and data else []
		translated = "".join([segment[0] for segment in segments if isinstance(segment, list) and segment and segment[0]])
		return translated.strip() or text
	except Exception:
		return text


def get_scratchpad_dir(ensure_exists=True, ensure_subdirs=True):
	"""Return the NVDA scratchpad directory and ensure its structure when requested."""
	scratchpad_dir = config.getScratchpadDir(bool(ensure_exists))
	if ensure_exists:
		os.makedirs(scratchpad_dir, exist_ok=True)
		if ensure_subdirs:
			for subdir in SCRATCHPAD_REQUIRED_SUBDIRS:
				os.makedirs(os.path.join(scratchpad_dir, subdir), exist_ok=True)
	return scratchpad_dir


def get_scratchpad_subdir(subdir_name, ensure_exists=True):
	"""Return a scratchpad subdirectory and create it if requested."""
	scratchpad_dir = get_scratchpad_dir(ensure_exists=ensure_exists, ensure_subdirs=True)
	subdir_path = os.path.join(scratchpad_dir, subdir_name)
	if ensure_exists:
		os.makedirs(subdir_path, exist_ok=True)
	return subdir_path


def get_running_application_names(include_focus=True):
	"""Return sorted app names currently known by NVDA.

	This uses appModuleHandler internals when available and falls back to the
	focused object's process name.
	"""
	names = set()

	def _add_name(value):
		value = str(value or '').strip()
		if not value:
			return
		if value.lower() == 'unknown':
			return
		names.add(value)

	def _extract_name_from_entry(entry):
		if entry is None:
			return ''
		# Resolve weakrefs where present.
		try:
			if hasattr(entry, '__call__') and hasattr(entry, '__class__') and entry.__class__.__name__.lower().endswith('reference'):
				entry = entry()
		except Exception:
			pass

		if isinstance(entry, (list, tuple)) and len(entry) >= 2:
			entry = entry[1]

		for attr_name in ('appName', 'appModuleName', 'name'):
			candidate = getattr(entry, attr_name, None)
			if candidate:
				return candidate

		module_name = getattr(entry, '__module__', '')
		if module_name.startswith('appModules.'):
			return module_name.split('.', 1)[1]
		return ''

	for attr_name in ('runningTable', 'runningAppModules', 'runningApplications'):
		running = getattr(appModuleHandler, attr_name, None)
		if not running:
			continue
		try:
			entries = running.values() if hasattr(running, 'values') else running
		except Exception:
			entries = running
		try:
			for entry in entries:
				_add_name(_extract_name_from_entry(entry))
		except Exception:
			pass

	if include_focus:
		try:
			focus = api.getFocusObject()
			process_id = getattr(focus, 'processID', 0) if focus else 0
			if process_id:
				_add_name(appModuleHandler.getAppNameFromProcessID(process_id, False))
		except Exception:
			pass

	return sorted(names, key=lambda value: value.lower())


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
		userconfigfile = os.path.join(get_scratchpad_subdir(moduletype + 's'), modulename + '.py')
		fd1 = open(userconfigfile, 'w')
		ui.message(_('Creating a new {moduletype}  {modulename}').format(moduletype=moduletype, modulename=modulename))
		fd1.write(text)
		fd1.close()
	else:
		return text


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


def prepare_addon_build(manifest_data, output_path):
	"""Prepare addon build in a persistent temporary directory.

	Copies scratchpad content and writes manifest files, but does not create
	the final .nvda-addon bundle yet.  The caller is responsible for cleaning
	up *temp_dir* (e.g. via ``shutil.rmtree``) after calling
	:func:`finalize_addon_build`.

	Returns (addon_dir, temp_dir, prepared_manifest_data).
	"""
	manifest_data = _prepare_manifest_data(manifest_data)
	output_path = os.path.abspath(output_path)
	output_dir = os.path.dirname(output_path)
	os.makedirs(output_dir, exist_ok=True)

	temp_dir = tempfile.mkdtemp(prefix='scriptmanagerAddonBuild_')
	addon_dir = os.path.join(temp_dir, manifest_data['addon_name'])
	os.makedirs(addon_dir, exist_ok=True)
	_copy_scratchpad_to_addon(addon_dir)
	_ensure_addon_builder_subfolders(addon_dir)
	_write_runtime_manifest(addon_dir, manifest_data)
	_write_builder_metadata(addon_dir, manifest_data)
	_ensure_documentation_file(addon_dir, manifest_data)
	return addon_dir, temp_dir, manifest_data


def finalize_addon_build(addon_dir, temp_dir, prepared_manifest_data, output_path):
	"""Create the .nvda-addon bundle from a previously prepared addon_dir.

	Cleans up *temp_dir* regardless of success or failure.
	Returns the path of the created bundle.
	"""
	output_path = os.path.abspath(output_path)
	output_dir = os.path.dirname(output_path)
	try:
		bundle = addonHandler.createAddonBundleFromPath(addon_dir, destDir=output_dir)
		bundle_path = getattr(bundle, '_path', None)
		if not bundle_path:
			bundle_path = os.path.join(
				output_dir,
				'{name}-{version}.{extension}'.format(
					name=prepared_manifest_data['addon_name'],
					version=prepared_manifest_data['addon_version'],
					extension=addonHandler.BUNDLE_EXTENSION,
				),
			)
		if os.path.normcase(bundle_path) != os.path.normcase(output_path):
			if os.path.exists(output_path):
				os.remove(output_path)
			shutil.move(bundle_path, output_path)
			bundle_path = output_path
		return bundle_path
	finally:
		shutil.rmtree(temp_dir, ignore_errors=True)


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
	scratchpad_dir = get_scratchpad_dir(ensure_exists=True, ensure_subdirs=True)
	if not _scratchpad_contains_files(scratchpad_dir):
		raise ValueError(_('The scratchpad directory does not contain any files to package.'))
	for entry in os.listdir(scratchpad_dir):
		if entry.lower() == addonHandler.MANIFEST_FILENAME:
			continue
		source_path = os.path.join(scratchpad_dir, entry)
		target_path = os.path.join(addon_dir, entry)
		if os.path.isdir(source_path):
			_copy_directory_without_empty_folders(source_path, target_path)
		else:
			os.makedirs(os.path.dirname(target_path), exist_ok=True)
			shutil.copy2(source_path, target_path)


def _copy_directory_without_empty_folders(source_dir, target_dir):
	"""Copy directory contents while skipping empty folders."""
	for root, _dirs, files in os.walk(source_dir):
		if not files:
			continue
		relative_root = os.path.relpath(root, source_dir)
		target_root = target_dir if relative_root == '.' else os.path.join(target_dir, relative_root)
		os.makedirs(target_root, exist_ok=True)
		for filename in files:
			source_file = os.path.join(root, filename)
			target_file = os.path.join(target_root, filename)
			shutil.copy2(source_file, target_file)


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


def _ensure_addon_builder_subfolders(addon_dir):
	"""Create common locale/doc subfolders in prepared addon directory."""
	ui_language = get_nvda_ui_language_code() or 'en'
	doc_languages = ['en']
	locale_languages = ['en']
	if ui_language not in doc_languages:
		doc_languages.append(ui_language)
	if ui_language not in locale_languages:
		locale_languages.append(ui_language)

	for language_code in doc_languages:
		os.makedirs(os.path.join(addon_dir, 'doc', language_code), exist_ok=True)

	for language_code in locale_languages:
		os.makedirs(os.path.join(addon_dir, 'locale', language_code, 'LC_MESSAGES'), exist_ok=True)


def _quote_manifest_string(value):
	return '"{value}"'.format(value=str(value).replace('\\', '\\\\').replace('"', '\\"'))


def _quote_manifest_multiline(value):
	return '"""{value}"""'.format(value=str(value).replace('"""', '\\"\\"\\"'))

