import datetime
import addonHandler
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
addonHandler.initTranslation()

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
	userconfigfile = config.getScratchpadDir(True)+os.sep+'appModules'+os.sep+appname+'.py'
	if os.access(userconfigfile,os.F_OK): return userconfigfile
	else: return None

def appmoduleprovidedbyaddon(appname):
	ret = None
	for addon in addonHandler.getRunningAddons():
		if os.access(addon.path+os.sep+'appmodules'+os.sep+appname+'.py',os.F_OK): ret = addon
	return ret

def copyappmodulefromaddon(appname, addon):
	addonname = addon.manifest['name']
	addonfullpath = addon.path+os.sep+'appmodules'+os.sep+appname+'.py'
	userconfigfile = config.getScratchpadDir(True)+os.sep+'appModules'+os.sep+appname+'.py'
	fd1 = open(addonfullpath,'r')
	fd2 = open(userconfigfile,'a')
	ui.message(_("copying appmodule for {appname} from addon {addonname} to user's config folder...").format(addonname=addonname, appname=appname))
	for line in fd1:
		fd2.write(line)
	fd2.close()
	fd1.close()

def createnewmodule(moduletype, modulename, createfile):
	l = moduletype[0].lower()
	u = moduletype[0].upper()
	module_template = [
		'#'+moduletype+'s/'+modulename+'.py',
		'# '+_('A part of NonVisual Desktop Access (NVDA)'),
		'# '+_('Copyright (C) 2006-{year} NVDA Contributors').format(year=datetime.date.today().year),
		'# '+_('This file is covered by the GNU General Public License.'),
		'# '+_('See the file COPYING for more details.'),
		'import '+moduletype+'Handler',
		'import controlTypes',
		'import api',
		'from scriptHandler import script',
		'import addonHandler',
		'# '+_('remove the comment (#) sign from the next line if (and when) the file belongs to an addon. This will enable localization (translation) features. in your file. See NVDA addon development guide for more info.'),
		'#addonHandler.initTranslation()',
		'class '+moduletype.replace(l, u, 1)+'('+moduletype+'Handler.'+moduletype.replace(l, u, 1)+'):']
	if moduletype in ['appModule', 'globalPlugin']:
		module_template += [chr(9)+'# '+_('some snapshot variables similar to these in the python console'),
			chr(9)+'nav = api.getNavigatorObject()',
			chr(9)+'focus = api.getFocusObject()',
			chr(9)+'fg = api.getForegroundObject()',
			chr(9)+'rp = api.getReviewPosition()',
			chr(9)+'caret = api.getCaretObject()',
			chr(9)+'desktop = api.getDesktopObject()',
			chr(9)+'mouse = api.getMouseObject()'
	]
	text = os.linesep.join(module_template)
	if createfile:
		userconfigfile = config.getScratchpadDir(True)+os.sep+moduletype+'s'+os.sep+modulename+'.py'
		fd1 = open(userconfigfile,'w')
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



