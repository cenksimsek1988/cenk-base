---
name: profile
description: "Read or change the person's shared cenk profile (own facts and settings for every cenk-* plugin). Use for \"show my profile\", \"where is my profile\", \"change my phone in my profile\", \"erase my address\", \"move my profile\". Never stores ID numbers or passwords."
---

# The shared profile

One JSON file, `profile.json`, in the cenk folder (default `<My Drive>/cenk/`, or the folder `CENK_HOME` names) holds the person's own facts (`person`, `private`, `contacts`, `employment`, `accounts`) and their settings (`settings.<plugin>`, `settings.common`). Each plugin's working data stays in its own place, never here.

Run every command as `python -I "${CLAUDE_PLUGIN_ROOT}/lib/profile.py" <command>` (`python3` where `python` is missing or opens the Store). In another plugin's script the same file is `"$CENK_BASE/lib/profile.py"`.

| Command | Does |
|---|---|
| `path` / `home` | the profile in use / the cenk folder |
| `get <key>` | one value; `[n]` picks a list item: `get person.languages[0].level` |
| `get <plugin> <key>` | a setting, `settings.<plugin>` then `settings.common` |
| `set <key> <json\|-> [--old <json>] [--yes]` | compare-and-set; `-` reads the value from stdin (use it for a private value) |
| `erase <key> [--yes]` | the value and its history |
| `create [<folder>]` | a new profile, or a copy of an old one |
| `pin <folder> [--yes]` | sets `CENK_HOME` in the person's Claude settings |

## Rules

- Exit 3 means the file holds another value than `--old`: nothing was written. Show the person both values and ask which is right.
- `--yes` only after the person's yes in the chat for that exact change: every key under `settings`, and `pin` (it changes their Claude settings; Claude must restart).
- A value the person gave goes in at once, with `--old` set to what you read before; never a guess. A private value never goes on the command line: `set <key> - --old -` with `{"old": ..., "new": ...}` on stdin.
- Never store ID numbers, passwords, card or bank numbers, or anything about other people they did not give.
- No profile: ask where to create it, suggesting the folder the error names; run `create` after their answer, then ask before `pin` when the output says nothing finds it yet.
- A note that the profile is at an old place: ask the person to move it; `create` copies it, `pin` after their yes, and delete the old file only after they say so.
- After `erase`, pass on the note about the cloud drive's earlier versions.
- Show values only to the person; never write them into logs, commit messages or another plugin's files.

End by saying what changed and where, or that nothing did.
