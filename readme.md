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

Important: If the navigator follows keyboard focus, press NVDA+7 (top number row) first to detach the navigator from focus before running NVDA+Shift+R. This ensures preview names are detected correctly and manual labeling works reliably.

## NVDA menu integration

- NVDA menu > Tools > Script Manager: opens Script Manager for the currently focused application.
- NVDA menu > Preferences > Script Manager labeling methods: configures automatic labeling method priority.
- NVDA settings > Script Manager: configures scratchpad activation policy, insert-function blacklist visibility, and docstring translation.

## Scratchpad activation policy

Several Script Manager actions require NVDA scratchpad processing (for example creating appModules, drivers, or building add-ons from scratchpad).

- Default behavior: ask before enabling scratchpad.
- If you choose Yes + "Do not show this prompt again", scratchpad is enabled automatically when needed.
- If you choose No + "Do not show this prompt again", scratchpad is never enabled automatically and the prompt is no longer shown.

When policy is set to "no" and scratchpad is currently disabled, scratchpad-required menu items are disabled.

## What is included

- App module loading/creation for the focused process.
- Automatic copy of app modules from running add-ons to user scratchpad when needed.
- Code editor with file handling, find/replace, go to line, and script templates.
- New script wizard with metadata (name, description, gesture, category).
- Function/class/method insertion dialog with optional blacklist filtering and optional docstring translation to NVDA UI language.
- Multi-stage error checking (syntax, compile, runtime, and NVDA log errors).
- Error navigation with direct jump to the reported line.

## Version

- Current development line in this repository: 1.0-dev
- Last tested NVDA version (manifest): 2025.3.3

## Release automation

- A push to master always runs the build workflow.
- On pushes to master, GitHub Actions reads the version from buildVars.py.
- Tag and release creation only run when addon-version in buildVars.py changed compared with the previous commit on master.
- If no Git tag with that version exists yet, the workflow creates the tag, builds the add-on, and publishes a GitHub Release with the generated .nvda-addon file.
- If the version did not change, the workflow still builds but skips tag and release creation.
