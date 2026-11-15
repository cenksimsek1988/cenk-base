# Privacy

cenk-base is a script, a skill and a start-up hook that run on your computer. Its author receives no data from it: there are no servers, analytics or tracking. The plugin itself holds no personal data.

- Stores: your profile, `profile.json` in the cenk folder you choose (default `My Drive/cenk/` in your own Google Drive, else `~/.claude/cenk/` on your computer). Each change keeps the replaced value in the file's `history`, until you erase it.
- Changes outside the profile: only after your yes, the `CENK_HOME` line in the `env` block of your Claude settings (`~/.claude/settings.json`), so every cenk plugin finds the folder.
- The start-up hook writes only this plugin's own folder path into the session's environment.
- The skill never asks for or stores ID numbers, passwords, card or bank numbers (the script itself does not check values).
- Who sees your data: you; Google, when the folder is in your Drive; Anthropic, which processes your Claude sessions under its own privacy policy (https://www.anthropic.com/legal/privacy); the cenk plugins you install, which read the profile in your sessions.
- To delete a value: ask Claude to erase it; it removes the value and its history, and tells you how to delete the earlier versions Google Drive keeps for up to 30 days.
- To delete everything: delete the cenk folder (or only `profile.json`), empty the Drive trash, and remove `CENK_HOME` from your Claude settings.
- Contact: https://github.com/cenksimsek1988/cenk-base/issues
