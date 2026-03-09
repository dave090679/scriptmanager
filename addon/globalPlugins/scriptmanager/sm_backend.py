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
addonHandler.initTranslation()

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
	Überprüft das Script auf Syntaxfehler.
	Gibt eine Liste von Fehlern mit Zeilennummern zurück.
	
	Returns:
		Liste von Dictionaries mit Keys: 'line', 'message', 'type'
	"""
	errors = []
	try:
		# Versuche mit compile() zu überprüfen
		compile(script_content, '<script>', 'exec')
	except SyntaxError as e:
		errors.append({
			'line': e.lineno if e.lineno else 1,
			'message': e.msg or str(e),
			'type': 'SyntaxError',
			'offset': e.offset
		})
	except Exception as e:
		# Andere Fehler
		errors.append({
			'line': 1,
			'message': str(e),
			'type': type(e).__name__
		})
	
	return errors


def check_script_for_errors(script_content):
	"""
	Erweiterte Fehlerprüfung für ein Script.
	Überprüft Syntaxfehler und versucht, das Script zu importieren.
	
	Returns:
		Tuple: (errors_list, error_details_dict)
	"""
	errors = []
	
	# 1. Syntaxfehler überprüfen
	syntax_errors = check_script_for_syntax_errors(script_content)
	if syntax_errors:
		errors.extend(syntax_errors)
		return errors, _format_errors_for_display(errors)
	
	# 2. Versuche, das Script in einem temporären Verzeichnis zu schreiben und zu importieren
	try:
		with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as tmp:
			tmp.write(script_content)
			tmp_path = tmp.name
		
		try:
			# Versuche zu kompilieren
			py_compile.compile(tmp_path, doraise=True)
		except py_compile.PyCompileError as e:
			errors.append({
				'line': _extract_line_number_from_error(str(e)),
				'message': str(e),
				'type': 'CompileError'
			})
		finally:
			# Temporäre Datei löschen
			try:
				os.unlink(tmp_path)
			except:
				pass
	except Exception as e:
		errors.append({
			'line': 1,
			'message': str(e),
			'type': type(e).__name__
		})
	
	return errors, _format_errors_for_display(errors)


def _extract_line_number_from_error(error_string):
	"""Extrahiert die Zeilennummer aus einer Fehlermeldung."""
	match = re.search(r'line (\d+)', error_string, re.IGNORECASE)
	if match:
		return int(match.group(1))
	return 1


def _format_errors_for_display(errors):
	"""
	Formatiert Fehler für die Anzeige.
	
	Returns:
		Ein formatierter String für die Anzeige
	"""
	if not errors:
		return None
	
	formatted_lines = []
	for error in errors:
		line_num = error.get('line', 1)
		message = error.get('message', 'Unbekannter Fehler')
		error_type = error.get('type', 'Error')
		
		formatted_lines.append(f"Zeile {line_num}: {error_type} - {message}")
	
	return "\n".join(formatted_lines)



