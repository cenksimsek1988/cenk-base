# Changelog

## 0.1.0 (2026-11-15)

- First version: the shared profile reader and writer of the cenk plugins in one place (`lib/profile.py`), merged from the copies in cenk-jobs and cenk-overtime: same file format, compare-and-set, history, erase, settings only with `--yes`, no profile inside a case folder.
- The cenk folder: `CENK_HOME`, else `My Drive/cenk/`, else `~/.claude/cenk/`, with `profile.json`, `developer.json` and one subfolder per plugin. Old places (`CENK_PROFILE`, the cenk-workbench setting `profile_path`, `claude/profile.json`) are read with a note to move; `create` copies the old profile; `pin` sets `CENK_HOME` in the Claude settings after the person's yes.
- A SessionStart hook puts `CENK_BASE` in the session's environment for the plugins built on this one.
- The `profile` skill.
