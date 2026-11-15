#!/bin/sh
# Runs every test of cenk-base on made-up data. Not part of the plugin.
#
#   sh tests/run.sh
set -eu
unset CENK_HOME CENK_PROFILE CLAUDE_PLUGIN_OPTION_PROFILE_PATH 2>/dev/null || true

T=$(cd "$(dirname "$0")" && pwd)
PY=''
for p in python3 python py; do
	# Windows has a python3 stub that only opens the Store: try each one.
	if command -v "$p" >/dev/null 2>&1 && "$p" -c 'import sys; sys.exit(sys.version_info < (3, 8))' >/dev/null 2>&1; then
		PY=$p
		break
	fi
done
[ -n "$PY" ] || { echo 'no Python 3.8 or later' >&2; exit 1; }

"$PY" -I "$T/test_profile.py"
sh "$T/test-hook.sh"
