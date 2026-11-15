#!/bin/sh
# Tests hooks/set-base.sh in a throwaway folder: it appends CENK_BASE to CLAUDE_ENV_FILE, quotes the path, prints
# nothing, and does nothing without CLAUDE_ENV_FILE. Not part of the plugin.
#
#   sh tests/test-hook.sh
set -eu

T=$(cd "$(dirname "$0")" && pwd)
HOOK=$T/../hooks/set-base.sh
W=$(mktemp -d "${TMPDIR:-/tmp}/test-hook.XXXXXX")
trap 'rm -rf "$W"' EXIT
fail=0
check() { if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1: got [$2], want [$3]"; fail=1; fi; }

mkdir -p "$W/plug in's"
out=$(CLAUDE_ENV_FILE="$W/env" CLAUDE_PLUGIN_ROOT="$W/plug in's" sh "$HOOK" </dev/null)
check "prints nothing" "$out" ""
got=$(env -i PATH="$PATH" sh -c ". '$W/env'; printf '%s' \"\$CENK_BASE\"")
check "exports the root with a space and a quote" "$got" "$W/plug in's"

printf 'export OTHER=1\n' >"$W/env2"
CLAUDE_ENV_FILE="$W/env2" CLAUDE_PLUGIN_ROOT='C:\Plugins\cenk-base' sh "$HOOK" </dev/null
check "appends, forward slashes" "$(cat "$W/env2")" "export OTHER=1
export CENK_BASE='C:/Plugins/cenk-base'"

status=0
env -u CLAUDE_ENV_FILE CLAUDE_PLUGIN_ROOT="$W" sh "$HOOK" </dev/null || status=$?
check "no env file: exit 0" "$status" "0"

status=0
out=$(CLAUDE_ENV_FILE="$W/missing/dir/env" CLAUDE_PLUGIN_ROOT="$W" sh "$HOOK" </dev/null 2>/dev/null) || status=$?
check "unwritable env file: exit 0" "$status" "0"
case $out in *'"additionalContext": "cenk-base: CENK_BASE could not be set'*) warned=yes ;; *) warned=no ;; esac
check "unwritable env file: one warning for the session" "$warned" "yes"

[ "$fail" = 0 ] && echo "test-hook: all passed" || { echo "test-hook: FAILED"; exit 1; }
