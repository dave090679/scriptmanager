# NVDA Script Manager

NVDA Script Manager is an NVDA add-on with its own editor for creating and editing NVDA Python scripts directly from NVDA.
It is focused on practical daily workflows: open the module of the currently focused app, create templates, insert API calls, and find/fix script errors quickly.

## Documentation

- German user documentation: `addon/doc/de/README.md`
- English user documentation: `addon/doc/en/README.md`

## Quick start

1. Focus the application you want to script.
2. Open Script Manager from NVDA menu: Tools > Script Manager, or press NVDA+Shift+0.
3. Edit or create the script in the Script Manager window.
4. Save with Ctrl+S.
5. Reload plugins with NVDA+Ctrl+F3 to test changes.

## Global shortcuts provided by this add-on

- NVDA+Shift+0: Open Script Manager for the currently focused application.
- NVDA+Shift+R: Create and store an object labeling rule for the current navigator object.

## NVDA menu integration

- NVDA menu > Tools > Script Manager: opens Script Manager for the currently focused application.
- NVDA menu > Preferences > Script Manager labeling methods: configures automatic labeling method priority.

## What is included

- App module loading/creation for the focused process.
- Automatic copy of app modules from running add-ons to user scratchpad when needed.
- Code editor with file handling, find/replace, go to line, and script templates.
- New script wizard with metadata (name, description, gesture, category).
- Function/class/method insertion dialog with live docs from loaded Python modules.
- Multi-stage error checking (syntax, compile, runtime, and NVDA log errors).
- Error navigation with direct jump to the reported line.

## Version

- Current development line in this repository: 1.0-dev
- Last tested NVDA version (manifest): 2025.3.3
