"""The person's profile: one JSON file with their own facts (person, private, contacts, employment, accounts) and the
settings they chose (settings.<plugin>, settings.common), shared by every cenk-* plugin. Each plugin keeps its own
working data apart, in its own subfolder of the cenk folder or wherever it says; only the person's own facts go here.

The cenk folder holds everything the cenk-* plugins share, with fixed names inside: profile.json (this file),
developer.json (developer settings) and one subfolder per plugin. Where it is, first match wins:
  1. the environment variable CENK_HOME names the folder; when it is set, nothing else is looked at;
  2. cenk/ in a Google Drive "My Drive" folder holding cenk/profile.json: <letter>:\\My Drive for C to Z on Windows,
     ~/Library/CloudStorage/GoogleDrive-*/My Drive sorted by name on a Mac;
  3. cenk/ in the Claude config folder (CLAUDE_CONFIG_DIR, else ~/.claude) holding cenk/profile.json;
  4. old installs only, read so the profile can move: the file CENK_PROFILE names, the cenk-workbench setting
     profile_path, claude/profile.json in a "My Drive" folder, then in the Claude config folder. Reading one prints a
     note to move it; set and erase refuse it; create copies it to the new place.
None found: nothing is written. The session asks the person where to create it, suggesting the first "My Drive"
folder's cenk/ (else the Claude config folder's cenk/), runs create after their answer, then pin after their yes.

python -I profile.py <command>          (python3 where python is not there)
  home                               the cenk folder in use, else the one suggested for a new profile
  path                               the profile in use, or nothing
  get <plugin> <key>                 a setting: settings.<plugin>, then settings.common; a list joined by ", "; nothing
                                     when unset. Example: get cenk-jobs form_facts
  get <key>                          one value: a string as it is, anything else as JSON; [n] picks a list item.
                                     Example: get person.languages[0].level
  set <key> <json|-> [--old <json>] [--yes]
                                     compare-and-set: writes only when the file holds the --old value there (absent
                                     when --old is not given); - reads the value or the --old value from stdin, for
                                     a private value; with - for both, stdin holds {"old": <json>, "new": <json>}.
                                     Example: set person.phone '"+1 555 0100"'
  erase <key> [--yes]                the value and every trace of it in history
  create [<folder>]                  a new profile.json in the folder the person chose (default: the suggested one);
                                     a copy of the old profile when only an old place holds one. Refused when a
                                     profile exists, inside a case folder, and when CENK_HOME names another folder
  pin <folder> [--yes]               sets CENK_HOME to the folder in the env block of <Claude config folder>/
                                     settings.json, keeping everything else there; only with --yes, after the person's
                                     yes, because it changes their Claude settings. Claude Code reads it at its next start
Exit: 0 done (or nothing to change), 1 refused (no profile, unreadable, a key not found, a setting without --yes),
2 bad arguments, 3 the file holds another value than --old says: nothing was written; show the person both values and
ask which is right.

A key under settings decides what sessions may do: set and erase change one only with --yes, given after the person's
yes for that key and value in the chat. Without it they write nothing, exit 1 and print the key, the old and the new
value to ask about.

Keys are dotted parts of letters, digits, - and _ (contacts.referee-sam.email). set and erase read the file right
before writing, keep each replaced value in history as {date, field, old, new}, and replace the file through a
temporary file in the same folder, so a reader never sees half a file.

From another plugin's script (the SessionStart hook of cenk-base sets CENK_BASE to its folder; the stdlib has a module
named profile, so load this one by its path):
  spec = importlib.util.spec_from_file_location("cenk_profile", os.path.join(os.environ["CENK_BASE"], "lib", "profile.py"))
  cenk_profile = importlib.util.module_from_spec(spec); spec.loader.exec_module(cenk_profile)
Standard library only.
"""
import datetime
import json
import os
import re
import shutil
import sys
import time

HOME_ENV = "CENK_HOME"
OLD_ENV = "CENK_PROFILE"
FOLDER = "cenk"
PROFILE = "profile.json"
DEVELOPER = "developer.json"
OLD_RELATIVE = os.path.join("claude", "profile.json")
PART = re.compile(r"^([A-Za-z0-9_-]+)((?:\[\d+\])*)$")
FORBIDDEN = {"__proto__", "constructor", "prototype"}
ABSENT = object()  # no value at a key
BOM = chr(0xFEFF)  # a byte-order mark some editors put before JSON


class ProfileError(Exception):
    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


def config_dir():
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")


def read_json(path):
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def same_file(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def drive_roots():
    """The Google Drive "My Drive" folders on this computer, in lookup order."""
    if sys.platform == "win32":
        candidates = [f"{chr(code)}:\\My Drive" for code in range(ord("C"), ord("Z") + 1)]
    elif sys.platform == "darwin":
        storage = os.path.join(os.path.expanduser("~"), "Library", "CloudStorage")
        try:
            candidates = [os.path.join(storage, e, "My Drive") for e in sorted(os.listdir(storage))
                          if e.startswith("GoogleDrive-")]
        except OSError:
            candidates = []
    else:
        candidates = []
    return [root for root in candidates if os.path.isdir(root)]


def workbench_profile_path(claude_dir):
    """The old cenk-workbench setting profile_path, or ''."""
    if "CLAUDE_PLUGIN_OPTION_PROFILE_PATH" in os.environ:
        return os.environ["CLAUDE_PLUGIN_OPTION_PROFILE_PATH"].strip()
    try:
        options = read_json(os.path.join(claude_dir, "settings.json"))["pluginConfigs"]["cenk-workbench@cenk-workbench"]
        return str((options.get("options") or {}).get("profile_path") or "").strip()
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return ""


def locate(roots=None, claude_dir=None):
    """{home, path, scope, old, suggested}. home is the cenk folder in use (else the suggested one); path the profile
    found, else None; scope env, cloud, computer, or for an old install old-env, old-setting, old-cloud, old-computer;
    old is True for those. suggested is the folder for a new profile. roots and claude_dir replace the computer's own
    drive folders and Claude config folder (tests pass made-up ones)."""
    named = os.path.expanduser(os.environ.get(HOME_ENV, "").strip())
    if named:
        home = os.path.abspath(named)
        return {"home": home, "path": os.path.join(home, PROFILE), "scope": "env", "old": False, "suggested": home}
    claude_dir = config_dir() if claude_dir is None else claude_dir
    roots = drive_roots() if roots is None else [r for r in roots if os.path.isdir(r)]
    suggested = os.path.join(roots[0], FOLDER) if roots else os.path.join(claude_dir, FOLDER)
    places = [(os.path.join(root, FOLDER), "cloud") for root in roots] + [(os.path.join(claude_dir, FOLDER), "computer")]
    for home, scope in places:
        if os.path.exists(os.path.join(home, PROFILE)):
            return {"home": home, "path": os.path.join(home, PROFILE), "scope": scope, "old": False,
                    "suggested": suggested}
    old = [(os.environ.get(OLD_ENV, "").strip(), "old-env"), (workbench_profile_path(claude_dir), "old-setting")]
    old += [(os.path.join(root, OLD_RELATIVE), "old-cloud") for root in roots]
    old.append((os.path.join(claude_dir, OLD_RELATIVE), "old-computer"))
    for path, scope in old:
        if path and os.path.exists(path):
            return {"home": suggested, "path": path, "scope": scope, "old": True, "suggested": suggested}
    return {"home": suggested, "path": None, "scope": None, "old": False, "suggested": suggested}


def home(**where):
    """The cenk folder in use, else the one suggested for a new profile."""
    return locate(**where)["home"]


def plugin_folder(plugin, **where):
    """A plugin's own subfolder of the cenk folder (not created here)."""
    return os.path.join(home(**where), plugin)


def load(**where):
    """{home, path, scope, old, suggested, exists, data, error}: data is {} without a readable profile."""
    found = locate(**where)
    if not found["path"] or not os.path.exists(found["path"]):
        return dict(found, exists=False, data={}, error=None)
    try:
        data = read_json(found["path"])
    except (OSError, ValueError) as e:
        return dict(found, exists=True, data={}, error=str(e))
    if not isinstance(data, dict):
        return dict(found, exists=True, data={}, error="not a JSON object")
    return dict(found, exists=True, data=data, error=None)


def missing_message(profile):
    if profile["scope"] == "env":
        return (f"No profile at {profile['path']}, the folder {HOME_ENV} names: nothing was read or written. Ask the "
                f"person whether to create it there; then: profile.py create {profile['home']}.")
    return (f"No profile yet: nothing was read or written. Ask the person where to create it, suggesting "
            f"{profile['suggested']}; then: profile.py create <folder>.")


def move_message(profile):
    return (f"The profile is at an old place ({profile['path']}, found by {profile['scope']}). Ask the person to move "
            f"it to {profile['suggested']}: profile.py create copies it there, then pin after their yes.")


def setting(profile, key, default=None, plugin="common"):
    """A setting's raw value: settings.<plugin>, then settings.common, then the default."""
    settings = (profile.get("data") or {}).get("settings") or {}
    for section in (plugin, "common"):
        values = settings.get(section)
        if isinstance(values, dict) and key in values:
            return values[key]
    return default


def text_of(value):
    """A value as a setting is printed: a string as it is, a list joined by ", "."""
    if isinstance(value, list):
        return ", ".join("" if v is None else text_of(v) for v in value)
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def parse_key(key, indexes):
    """'person.languages[0].level' -> ['person', 'languages', 0, 'level']; [n] only where indexes is true."""
    parts = []
    for piece in str(key or "").split("."):
        match = PART.match(piece)
        if not match or match.group(1) in FORBIDDEN or (match.group(2) and not indexes):
            raise ProfileError(f'Bad key "{key}": use dotted names of letters, digits, - and _'
                               + (", and [n] for a list item" if indexes else "")
                               + ". Example: contacts.referee-sam.email", 2)
        parts.append(match.group(1))
        parts += [int(n) for n in re.findall(r"\d+", match.group(2))]
    return parts


def writable_key(key):
    parts = parse_key(key, False)
    if parts[0] == "history":
        raise ProfileError("history is written by set and erase only.", 2)
    return parts


def is_setting(parts):
    return parts[0] == "settings"


def same(a, b):
    """Equal JSON values, whatever the order of an object's keys; ABSENT equals only ABSENT."""
    if a is ABSENT or b is ABSENT:
        return a is b
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def shown(value):
    return "nothing" if value is ABSENT else json.dumps(value, ensure_ascii=False)


def ask_first(key, old, new):
    """The refusal for a settings change without the person's yes: the key and both values, to show them."""
    return ProfileError(f"{key} is a setting: nothing was written. Ask the person first, showing the key, the old value "
                        f"({shown(old)}) and the new one ({shown(new)}); after their yes, run again with --yes.", 1)


def readable(**where):
    """The loaded profile, or ProfileError when there is none or it cannot be read."""
    profile = load(**where)
    if not profile["exists"]:
        raise ProfileError(missing_message(profile), 1)
    if profile["error"]:
        raise ProfileError(f"The profile {profile['path']} cannot be read ({profile['error']}). Tell the person.", 1)
    return profile


def read_for_write(**where):
    profile = readable(**where)
    if profile["old"]:
        raise ProfileError("Nothing was written. " + move_message(profile), 1)
    data = profile["data"]
    if "history" in data and not isinstance(data["history"], list):
        raise ProfileError(f"history in {profile['path']} is not a list: nothing was written. Tell the person.", 1)
    return profile["path"], data


def write_atomic(path, data):
    """A temporary file in the same folder, renamed over the profile. A cloud drive's sync can hold the file for a
    moment: the rename is tried up to 4 times, 0.2 s apart. history goes last."""
    ordered = {k: v for k, v in data.items() if k != "history"}
    if "history" in data:
        ordered["history"] = data["history"]
    text = json.dumps(ordered, ensure_ascii=False, indent=2) + "\n"
    temp = os.path.join(os.path.dirname(path), f".{os.path.basename(path)}.{os.getpid()}.{int(time.time() * 1000)}.tmp")
    try:
        with open(temp, "xb") as f:
            f.write(text.encode("utf-8"))
        if os.path.exists(path):
            shutil.copymode(path, temp)  # keep the file's own permissions
        for attempt in range(1, 5):
            try:
                os.replace(temp, path)
                return
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.2)
    except OSError as e:
        try:
            os.remove(temp)
        except OSError:
            pass
        raise ProfileError(f"{path} could not be written ({e}); it is unchanged.", 1)


def get(key, **where):
    """The value at a key, or ABSENT. Raises ProfileError without a readable profile."""
    parts = parse_key(key, True)
    node = readable(**where)["data"]
    for part in parts:
        if isinstance(part, int):
            if not isinstance(node, list) or part >= len(node):
                return ABSENT
        elif not isinstance(node, dict) or part not in node:
            return ABSENT
        node = node[part]
    return node


def set_value(key, value, old=ABSENT, yes=False, **where):
    """Compare-and-set: writes the value only when the file holds old at the key (ABSENT: no value there). A replaced
    value goes into history. Returns (path, changed); raises ProfileError with code 3 when the file holds another, and
    with code 1 for a change under settings without yes (the person's yes in the chat)."""
    parts = writable_key(key)
    path, data = read_for_write(**where)
    parent = data
    for i, part in enumerate(parts[:-1]):
        if part not in parent:
            parent[part] = {}
        elif not isinstance(parent[part], dict):
            raise ProfileError(f"{'.'.join(parts[:i + 1])} is not an object: nothing was written.", 1)
        parent = parent[part]
    last = parts[-1]
    current = parent.get(last, ABSENT)
    if same(current, value):
        return path, False
    if not same(current, old):
        raise ProfileError(f"{key} holds {shown(current)}, not {shown(old)}: nothing was written. Show the person both "
                           "values and ask which is right.", 3)
    if is_setting(parts) and not yes:
        raise ask_first(key, current, value)
    parent[last] = value
    if current is not ABSENT:
        data.setdefault("history", []).append(
            {"date": datetime.date.today().isoformat(), "field": key, "old": current, "new": value})
    write_atomic(path, data)
    return path, True


def get_in(obj, parts):
    """The value at parts inside obj (dotted names only), or ABSENT."""
    for part in parts:
        if not isinstance(obj, dict) or part not in obj:
            return ABSENT
        obj = obj[part]
    return obj


def remove_at(obj, parts):
    """Deletes the value at parts inside obj; True when there was one."""
    node = obj
    for part in parts[:-1]:
        if not isinstance(node, dict) or part not in node:
            return False
        node = node[part]
    if not isinstance(node, dict) or parts[-1] not in node:
        return False
    del node[parts[-1]]
    return True


def erase(key, yes=False, **where):
    """Removes the value and every trace of it in history: entries for the key or a key under it, and the erased part
    inside entries recorded on a parent key (dropped when nothing else changed). Returns (path, changed). A key under
    settings is erased only with yes (the person's yes in the chat); without it, ProfileError with code 1."""
    parts = writable_key(key)
    path, data = read_for_write(**where)
    current = get_in(data, parts)
    changed = remove_at(data, parts)
    if "history" in data:
        kept = []
        for entry in data["history"]:
            field = entry.get("field") if isinstance(entry, dict) and isinstance(entry.get("field"), str) else ""
            if field == key or field.startswith(key + "."):
                changed = True
                continue
            if field and key.startswith(field + "."):
                rest = key[len(field) + 1:].split(".")
                scrubbed = any([remove_at(entry, [side, *rest]) for side in ("old", "new")])
                if scrubbed:
                    changed = True
                    if same(entry.get("old", ABSENT), entry.get("new", ABSENT)):
                        continue
            kept.append(entry)
        data["history"] = kept
    if changed and is_setting(parts) and not yes:
        raise ask_first(key, current, ABSENT)
    if changed:
        write_atomic(path, data)
    return path, changed


def cloud_note(path):
    """What the person still has to do after an erase: a cloud drive keeps earlier versions of the file."""
    norm = path.replace("\\", "/")
    if "/My Drive/" in norm or "/GoogleDrive-" in norm:
        return ("Google Drive keeps the earlier versions of this file for up to 30 days, and they still hold the "
                "erased value. After the person's yes (they cannot be restored), they delete them: drive.google.com, "
                "signed in to the account that holds the profile, right-click the file, File information, Manage "
                "versions, delete every version except the current one.")
    if "/OneDrive" in norm:
        return ("OneDrive keeps earlier versions of this file, and they still hold the erased value. After the "
                "person's yes, they delete them in the file's Version history.")
    return ""


def case_folder_of(path):
    """The cenk-overtime case folder holding path (a folder with master.sqlite, or an evidence folder <case>-evidence,
    shared with lawyers), or None."""
    folder = os.path.abspath(path)
    while True:
        if os.path.exists(os.path.join(folder, "master.sqlite")) or os.path.basename(folder).endswith("-evidence"):
            return folder
        parent = os.path.dirname(folder)
        if parent == folder:
            return None
        folder = parent


def folder_of(path):
    """A folder argument; a path ending in profile.json stands for its folder."""
    path = os.path.abspath(path)
    return os.path.dirname(path) if os.path.basename(path).lower() == PROFILE else path


def create(folder=None, **where):
    """A new profile.json in folder (default: the suggested one): empty, or a copy of the old profile when only an
    old place holds one. Refuses when a profile exists already, inside a case folder, and when CENK_HOME names
    another folder. Returns (path, copied from or None, found by the lookup without pin)."""
    profile = load(**where)
    if profile["exists"] and not profile["old"]:
        raise ProfileError(f"A profile exists already at {profile['path']}: nothing was created.", 1)
    if profile["old"] and profile["error"]:
        raise ProfileError(f"The old profile {profile['path']} cannot be read ({profile['error']}): nothing was "
                           "created. Tell the person.", 1)
    folder = folder_of(folder or profile["suggested"])
    path = os.path.join(folder, PROFILE)
    if os.path.exists(path):
        raise ProfileError(f"{path} exists already: nothing was created.", 1)
    case = case_folder_of(folder)
    if case:
        raise ProfileError(f"{folder} is inside the case folder {case}: nothing was created. The profile holds the "
                           f"person's own facts and stays out of every case; suggest {profile['suggested']}.", 1)
    named = os.path.expanduser(os.environ.get(HOME_ENV, "").strip())
    if named and not same_file(named, folder):
        raise ProfileError(f"{HOME_ENV} names {named}, not {folder}: nothing was created. Ask the person which is "
                           f"right; pin changes {HOME_ENV}.", 1)
    os.makedirs(folder, exist_ok=True)
    write_atomic(path, profile["data"] if profile["old"] else {})
    found = locate(**where)
    return path, (profile["path"] if profile["old"] else None), bool(found["path"]) and same_file(found["path"], path)


def pin(folder, yes=False, claude_dir=None):
    """Sets CENK_HOME to folder in the env block of the Claude settings.json, keeping every other key. Only with yes:
    it changes the person's Claude settings. Returns (settings file, changed)."""
    claude_dir = config_dir() if claude_dir is None else claude_dir
    settings = os.path.join(claude_dir, "settings.json")
    folder = folder_of(folder).replace("\\", "/")
    try:
        data = read_json(settings) if os.path.exists(settings) else {}
    except (OSError, ValueError) as e:
        raise ProfileError(f"{settings} cannot be read ({e}): nothing was written. Tell the person.", 1)
    if not isinstance(data, dict) or not isinstance(data.get("env", {}), dict):
        raise ProfileError(f"{settings} is not a JSON object with an env object: nothing was written. Tell the person.",
                           1)
    old = data.get("env", {}).get(HOME_ENV, ABSENT)
    if isinstance(old, str) and old and same_file(old, folder):
        return settings, False
    if not yes:
        raise ProfileError(f"pin changes the person's Claude settings ({settings}): nothing was written. Ask them "
                           f"first, showing {HOME_ENV}, the old value ({shown(old)}) and the new one ({shown(folder)}); "
                           "after their yes, run again with --yes.", 1)
    data.setdefault("env", {})[HOME_ENV] = folder
    os.makedirs(claude_dir, exist_ok=True)
    temp = f"{settings}.{os.getpid()}.tmp"
    try:
        with open(temp, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        os.replace(temp, settings)
    except OSError as e:
        try:
            os.remove(temp)
        except OSError:
            pass
        raise ProfileError(f"{settings} could not be written ({e}); it is unchanged.", 1)
    return settings, True


def parse_value(text, what):
    try:
        return json.loads(text[1:] if text.startswith(BOM) else text)
    except ValueError as e:
        raise ProfileError(f"{what} is not JSON ({e}). A string needs its quotes: '\"Ada\"'.", 2)


USAGE = ("usage: profile.py home | path | get <plugin> <key> | get <key> | set <key> <json|-> [--old <json>] [--yes] "
         "| erase <key> [--yes] | create [<folder>] | pin <folder> [--yes]")


def main(argv):
    command, rest = (argv[0], list(argv[1:])) if argv else ("", [])
    # --yes: the person said yes in the chat to this change; only set, erase and pin take it.
    yes = command in ("set", "erase", "pin") and "--yes" in rest
    if yes:
        rest = [a for a in rest if a != "--yes"]
    if command in ("home", "path") and not rest:
        found = locate()
        print(found["home"] if command == "home" else (found["path"] if found["old"] or (
            found["path"] and os.path.exists(found["path"])) else ""))
        if found["old"]:
            print(move_message(found), file=sys.stderr)
    elif command == "get" and len(rest) in (1, 2):
        profile = load()
        if len(rest) == 2:
            if profile["exists"] and profile["error"]:
                raise ProfileError(f"The profile {profile['path']} cannot be read ({profile['error']}). "
                                   "Tell the person.", 1)
            value = setting(profile, rest[1], None, rest[0])
            print("" if value is None else text_of(value))
        else:
            value = get(rest[0])
            if value is ABSENT:
                raise ProfileError(f"{rest[0]} is not in the profile.", 1)
            print(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2))
        if profile["old"]:
            print(move_message(profile), file=sys.stderr)
    elif command == "set" and (len(rest) == 2 or (len(rest) == 4 and rest[2] == "--old")):
        key, text = rest[0], rest[1]
        old_text = rest[3] if len(rest) == 4 else None
        if text == "-" and old_text == "-":  # both private: stdin holds {"old": ..., "new": ...}
            both = parse_value(sys.stdin.read(), "stdin")
            if not isinstance(both, dict) or "new" not in both or "old" not in both:
                raise ProfileError('With "-" for both, stdin holds {"old": <json>, "new": <json>}.', 2)
            value, old = both["new"], both["old"]
        else:
            stdin = sys.stdin.read() if "-" in (text, old_text) else ""
            value = parse_value(stdin if text == "-" else text, "The value")
            old = ABSENT if old_text is None else parse_value(stdin if old_text == "-" else old_text, "The --old value")
        path, changed = set_value(key, value, old, yes)
        print(f"set {key} in {path}" if changed else f"unchanged: {key} already holds this value")
    elif command == "erase" and len(rest) == 1:
        path, changed = erase(rest[0], yes)
        if changed:
            print(f"erased {rest[0]} and its history in {path}")
            note = cloud_note(path)
            if note:
                print(note)
        else:
            print(f"nothing to erase: {rest[0]} is not in the profile")
    elif command == "create" and len(rest) <= 1:
        path, copied, found = create(rest[0] if rest else None)
        print(f"created {path}" + (f" as a copy of {copied}" if copied else ""))
        if copied:
            print(f"The old file stays at {copied}. After the person has checked the new one, ask whether to delete "
                  f"the old file, and remove {OLD_ENV} or the cenk-workbench setting profile_path if one names it.")
        if not found:
            print(f"Next: nothing finds it yet. Ask the person whether to set {HOME_ENV} to {os.path.dirname(path)} "
                  f"in their Claude settings; after their yes: profile.py pin {os.path.dirname(path)} --yes. "
                  "Claude must restart to see it.")
    elif command == "pin" and len(rest) == 1:
        settings, changed = pin(rest[0], yes)
        print(f"{HOME_ENV} set in {settings}; restart Claude for it to apply" if changed else
              f"unchanged: {HOME_ENV} already names this folder in {settings}")
    else:
        raise ProfileError(USAGE, 2)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
        sys.stdin.reconfigure(encoding="utf-8")
    try:
        main(sys.argv[1:])
    except ProfileError as e:
        print(e, file=sys.stderr)
        sys.exit(e.code)
