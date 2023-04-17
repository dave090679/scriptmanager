# -*- coding: UTF-8 -*-

# Build customizations
# Change this file instead of sconstruct or manifest files, whenever possible.

# Full getext (please don't change)
_ = lambda x : x

# Add-on information variables
addon_info = {
	# for previously unpublished addons, please follow the community guidelines at:
	# https://bitbucket.org/nvdaaddonteam/todo/src/37bd08d42c17e72ae303fee4a60821ea0c2f4c5a/guideLines.txt?at=master
	# add-on Name, internal for nvda
	"addon-name" : "scriptmanager",
	# Add-on summary, usually the user visible name of the addon.
	# TRANSLATORS: Summary for this add-on to be shown on installation and add-on information.
	"addon-summary" : _("script manager"),
	# Add-on description
	# Translators: Long description to be shown for this add-on on add-on information from add-ons manager
	"addon-description" : _("""This add-on uses an own-built editor to create an appmodule for the currently running aplication.
"""),
	# version
	"addon-version" : "0.2.2",
	# Author(s)
	"addon-author" : "David Parduhn <xkill85@gmx.net>",
	# URL for the add-on documentation support
	"addon-url" : None,
	"lastTestedNVDAVersion": "2023.1"
}


import os.path

# Define the python files that are the sources of your add-on.
# You can use glob expressions here, they will be expanded.
pythonSources = []

# Files that contain strings for translation. Usually your python sources
i18nSources = pythonSources + ["buildVars.py", "docHandler.py"]

# Files that will be ignored when building the nvda-addon file
# Paths are relative to the addon directory, not to the root directory of your addon sources.
excludedFiles = []
