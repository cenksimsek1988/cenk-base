#!/bin/sh
# SessionStart: writes CENK_BASE=<this plugin's folder> into the session's environment file (CLAUDE_ENV_FILE), so the
# scripts of the plugins built on cenk-base find lib/profile.py in the Bash tool: "$CENK_BASE/lib/profile.py".
# Advisory: it fails open and always exits 0. It prints nothing (no context cost), except one warning line for the
# session when the write fails. Without CLAUDE_ENV_FILE it does nothing.
# Forward slashes, so the value works in Git Bash and in Python on Windows too.
root=${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "$0")/.." 2>/dev/null && pwd)}
[ -n "${CLAUDE_ENV_FILE:-}" ] && [ -n "$root" ] || exit 0
quoted=$(printf '%s' "$root" | sed -e 's|\\|/|g' -e "s/'/'\\\\''/g")
if [ -z "$quoted" ] || ! printf "export CENK_BASE='%s'\n" "$quoted" >>"$CLAUDE_ENV_FILE" 2>/dev/null; then
	printf '%s\n' '{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "cenk-base: CENK_BASE could not be set for this session (the session environment file was not writable), so cenk plugins cannot read the profile in the Bash tool. Tell the person; a new session may fix it."}}'
fi
exit 0
