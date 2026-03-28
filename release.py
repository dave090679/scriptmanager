# coding=utf-8
# Copyright (C) 2019 Larry Wang <larry.wang.801@gmail.com>
# This file is covered by the GNU General Public License.
# See the file COPYING for more details.
import os
import subprocess
import sys

import buildVars

name = buildVars.addon_info["addon-name"]
version = buildVars.addon_info["addon-version"]
asset_path = os.path.join(os.path.dirname(__file__), name + "-" + version + ".nvda-addon")


def run_command(command, allow_failure=False):
	result = subprocess.run(command, capture_output=True, text=True)
	if result.returncode != 0 and not allow_failure:
		message = result.stderr.strip() or result.stdout.strip() or "Command failed"
		raise RuntimeError(message)
	return result


def tag_exists(tag_name):
	result = run_command(["git", "rev-parse", "-q", "--verify", "refs/tags/{0}".format(tag_name)], allow_failure=True)
	return result.returncode == 0


def release_exists(tag_name):
	result = run_command(["gh", "release", "view", tag_name], allow_failure=True)
	return result.returncode == 0


def ensure_tag(tag_name):
	if tag_exists(tag_name):
		print("Tag already exists: {0}".format(tag_name))
		return
	run_command(["git", "tag", "-a", tag_name, "-m", tag_name])
	print("Created tag: {0}".format(tag_name))


def push_tags():
	run_command(["git", "push", "--tags"])
	print("Pushed tags to origin")


def ensure_release(tag_name, addon_asset_path):
	if release_exists(tag_name):
		run_command(["gh", "release", "upload", tag_name, addon_asset_path, "--clobber"])
		print("Updated existing release asset: {0}".format(tag_name))
		return
	run_command(["gh", "release", "create", tag_name, "--generate-notes", addon_asset_path])
	print("Created release: {0}".format(tag_name))


def main():
	if not os.path.isfile(asset_path):
		raise FileNotFoundError("Add-on package not found: {0}".format(asset_path))
	ensure_tag(version)
	push_tags()
	ensure_release(version, asset_path)


if __name__ == "__main__":
	try:
		main()
	except Exception as error:
		print(str(error), file=sys.stderr)
		sys.exit(1)
