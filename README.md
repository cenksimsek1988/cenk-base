# cenk-base

The shared base of the cenk plugins for Claude Code (cenk-jobs, cenk-overtime and those to come). You do not use it on its own: a cenk plugin installs it as its parent, so that every cenk plugin reads and writes your own facts in one place, the same way.

## What it stores, and where

Everything the cenk plugins share lives in one folder, the **cenk folder**:

| Inside the cenk folder | What |
|---|---|
| `profile.json` | your profile: your own facts (name, contact, languages, people you name as referees or your lawyer, your jobs, the accounts you use) and the settings you chose for the cenk plugins |
| `developer.json` | developer settings, only if you develop plugins |
| `<plugin>/` | one subfolder per cenk plugin that keeps its working data there |

Where the cenk folder is, first match wins:

1. the folder the environment variable `CENK_HOME` names (then nothing else is looked at);
2. `cenk/` in your Google Drive "My Drive" folder (Google Drive for desktop), when it holds `profile.json`;
3. `cenk/` in Claude's own config folder (`~/.claude/cenk/`), when it holds `profile.json`.

No profile yet: Claude asks where to create it, suggesting `My Drive/cenk/`, and after your yes sets `CENK_HOME` in your Claude settings so every cenk plugin finds it.

Moving from an older version: a profile at `My Drive/claude/profile.json`, `~/.claude/claude/profile.json` or the file `CENK_PROFILE` names is still read, and Claude offers to copy it to the cenk folder. The old file stays until you say to delete it.

## What it holds itself

**No personal data.** The plugin is a script, a skill and a start-up hook; your profile is a file in your own Drive or on your computer. Who else sees it: [PRIVACY.md](PRIVACY.md).

## Using it

Say it in plain words: "show my profile", "where is my profile", "change my phone number in my profile", "erase my address", "move my profile". Claude asks before it changes a setting or your Claude settings, and never stores ID numbers, passwords or card numbers. After an erase, Claude tells you how to delete the earlier versions Google Drive keeps.

## Needs

Claude Code 2.1.284 or later, and Python 3 on your computer.

## For plugin developers

A plugin builds on it by declaring it in `dependencies` in its `plugin.json`:

- `"dependencies": [{ "name": "cenk-base", "marketplace": "cenk" }]` works both in the `cenk` catalog and in a plugin's own local marketplace (with the allowlist below); installing the plugin installs and enables cenk-base. In the same marketplace the plain `"cenk-base"` works too.
- In another marketplace, `{ "name": "cenk-base", "marketplace": "<cenk-base's marketplace>" }`: cenk-base is installed with it only when the plugin's `marketplace.json` has `"allowCrossMarketplaceDependenciesOn": ["<cenk-base's marketplace>"]` and that marketplace is added too; otherwise the plugin fails to load until cenk-base is installed.
- An installed plugin updated to a version that adds the dependency: `claude plugin update` does not install cenk-base, and the plugin fails to load until `claude plugin install <plugin>` runs again. Its set-up step checks this and re-runs the install or tells the person.

The start-up hook puts `CENK_BASE=<this plugin's folder>` into each session's environment, so a script run from the Bash tool can call `python -I "$CENK_BASE/lib/profile.py" get person.name`, or load it as a module by its path (see the top of [lib/profile.py](lib/profile.py)). Only Bash tool commands get `CENK_BASE`: not PowerShell tool commands on Windows, and not other hooks. A script that finds it missing says so plainly and names the cause: cenk-base not installed or enabled, its start-up hook failed (Claude Code shows no error for that), or a session started before it was; the fix is `claude plugin install <plugin>@<marketplace>` and a new session. Tests: `sh tests/run.sh`.

Privacy: [PRIVACY.md](PRIVACY.md). License: MIT.
