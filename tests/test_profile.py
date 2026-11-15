"""Tests lib/profile.py on made-up data in a throwaway folder: lookup order, old places, get, set with compare-and-set,
history, settings only with --yes, erase, create (and the copy of an old profile), pin. Not part of the plugin.

    python -I tests/test_profile.py

Clears CENK_HOME, CENK_PROFILE and the workbench's profile_path first, so the person's real profile is never read.
Function tests pass made-up drive folders and Claude config folder; command-line tests set CENK_HOME, so the lookup
looks nowhere else.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB = os.path.join(ROOT, "lib", "profile.py")
for name in ("CENK_HOME", "CENK_PROFILE", "CLAUDE_PLUGIN_OPTION_PROFILE_PATH"):
    os.environ.pop(name, None)
spec = importlib.util.spec_from_file_location("cenk_profile", LIB)
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cenk-base-test.")
        self.drive = os.path.join(self.tmp, "My Drive")
        self.drive2 = os.path.join(self.tmp, "Other Drive")
        self.claude = os.path.join(self.tmp, "claude-config")
        os.makedirs(self.drive)
        os.makedirs(self.claude)
        self.where = {"roots": [self.drive, self.drive2], "claude_dir": self.claude}
        os.environ["CLAUDE_CONFIG_DIR"] = self.claude
        for name in ("CENK_HOME", "CENK_PROFILE", "CLAUDE_PLUGIN_OPTION_PROFILE_PATH"):
            os.environ.pop(name, None)

    def tearDown(self):
        for name in ("CENK_HOME", "CENK_PROFILE", "CLAUDE_CONFIG_DIR"):
            os.environ.pop(name, None)
        shutil.rmtree(self.tmp, ignore_errors=True)


class Lookup(Base):
    def test_nothing(self):
        found = P.locate(**self.where)
        self.assertIsNone(found["path"])
        self.assertEqual(found["suggested"], os.path.join(self.drive, "cenk"))

    def test_no_drive_suggests_config(self):
        found = P.locate(roots=[], claude_dir=self.claude)
        self.assertEqual(found["suggested"], os.path.join(self.claude, "cenk"))

    def test_order(self):
        local = os.path.join(self.claude, "cenk", "profile.json")
        write(local, {"a": 1})
        self.assertEqual(P.locate(**self.where)["scope"], "computer")
        cloud = os.path.join(self.drive, "cenk", "profile.json")
        write(cloud, {"a": 2})
        self.assertEqual(P.locate(**self.where)["path"], cloud)
        home = os.path.join(self.tmp, "elsewhere")
        os.environ["CENK_HOME"] = home
        found = P.locate(**self.where)
        self.assertEqual((found["scope"], found["path"]), ("env", os.path.join(home, "profile.json")))
        self.assertFalse(P.load(**self.where)["exists"])  # named folder without a profile: nothing else looked at
        os.environ["CENK_HOME"] = os.path.join("~", "cenk-test")
        self.assertEqual(P.locate(**self.where)["home"], os.path.join(os.path.expanduser("~"), "cenk-test"))

    def test_old_places(self):
        old_local = os.path.join(self.claude, "claude", "profile.json")
        write(old_local, {"person": {"name": "Ada Lovelace"}})
        found = P.locate(**self.where)
        self.assertEqual((found["scope"], found["old"], found["home"]), ("old-computer", True, os.path.join(self.drive, "cenk")))
        old_cloud = os.path.join(self.drive, "claude", "profile.json")
        write(old_cloud, {})
        self.assertEqual(P.locate(**self.where)["scope"], "old-cloud")
        named = os.path.join(self.tmp, "named.json")
        write(named, {})
        write(os.path.join(self.claude, "settings.json"),
              {"pluginConfigs": {"cenk-workbench@cenk-workbench": {"options": {"profile_path": named}}}})
        self.assertEqual(P.locate(**self.where)["scope"], "old-setting")
        os.environ["CENK_PROFILE"] = named
        self.assertEqual(P.locate(**self.where)["scope"], "old-env")
        write(os.path.join(self.claude, "cenk", "profile.json"), {})
        self.assertEqual(P.locate(**self.where)["scope"], "computer")  # every new place before any old one

    def test_old_read_not_written(self):
        write(os.path.join(self.claude, "claude", "profile.json"), {"person": {"name": "Ada Lovelace"}})
        self.assertEqual(P.get("person.name", **self.where), "Ada Lovelace")
        with self.assertRaises(P.ProfileError) as e:
            P.set_value("person.phone", "+1 555 0100", **self.where)
        self.assertEqual(e.exception.code, 1)
        self.assertIn("old place", str(e.exception))

    def test_plugin_folder(self):
        self.assertEqual(P.plugin_folder("cenk-jobs", **self.where), os.path.join(self.drive, "cenk", "cenk-jobs"))


class Writing(Base):
    def setUp(self):
        super().setUp()
        self.path = os.path.join(self.drive, "cenk", "profile.json")
        write(self.path, {"person": {"name": "Ada Lovelace", "languages": [{"name": "English", "level": "C2"}]},
                          "settings": {"common": {"mode": "draft"}, "cenk-jobs": {"form_facts": ["a", "b"]}}})

    def test_get(self):
        self.assertEqual(P.get("person.languages[0].level", **self.where), "C2")
        self.assertIs(P.get("person.phone", **self.where), P.ABSENT)
        profile = P.load(**self.where)
        self.assertEqual(P.text_of(P.setting(profile, "form_facts", None, "cenk-jobs")), "a, b")
        self.assertEqual(P.setting(profile, "mode", None, "cenk-overtime"), "draft")

    def test_set_cas_history(self):
        self.assertEqual(P.set_value("person.phone", "+1 555 0100", **self.where), (self.path, True))
        self.assertEqual(P.set_value("person.phone", "+1 555 0100", **self.where), (self.path, False))
        with self.assertRaises(P.ProfileError) as e:
            P.set_value("person.phone", "+1 555 0199", **self.where)
        self.assertEqual(e.exception.code, 3)
        P.set_value("person.phone", "+1 555 0199", old="+1 555 0100", **self.where)
        data = read(self.path)
        self.assertEqual(data["person"]["phone"], "+1 555 0199")
        self.assertEqual(data["history"][-1]["old"], "+1 555 0100")
        self.assertEqual(list(data)[-1], "history")

    def test_bad_keys(self):
        for key in ("history.x", "a..b", "__proto__.x", "person.languages[0]"):
            with self.assertRaises(P.ProfileError) as e:
                P.set_value(key, 1, **self.where)
            self.assertEqual(e.exception.code, 2, key)

    def test_settings_need_yes(self):
        with self.assertRaises(P.ProfileError) as e:
            P.set_value("settings.common.mode", "confirm", old="draft", **self.where)
        self.assertEqual(e.exception.code, 1)
        self.assertEqual(read(self.path)["settings"]["common"]["mode"], "draft")
        P.set_value("settings.common.mode", "confirm", old="draft", yes=True, **self.where)
        with self.assertRaises(P.ProfileError):
            P.erase("settings.common.mode", **self.where)
        P.erase("settings.common.mode", yes=True, **self.where)
        self.assertNotIn("mode", read(self.path)["settings"]["common"])

    def test_erase_scrubs_history(self):
        P.set_value("person.phone", "+1 555 0100", **self.where)
        P.set_value("person.phone", "+1 555 0199", old="+1 555 0100", **self.where)
        P.set_value("person", {"name": "Ada King"}, old=read(self.path)["person"], **self.where)
        P.erase("person.phone", **self.where)
        with open(self.path, encoding="utf-8") as f:
            text = f.read()
        self.assertNotIn("555", text)
        self.assertIn("Ada King", text)
        self.assertEqual(P.erase("person.phone", **self.where), (self.path, False))

    def test_cloud_note(self):
        self.assertIn("Google Drive", P.cloud_note(self.path))
        self.assertEqual(P.cloud_note(os.path.join(self.claude, "cenk", "profile.json")), "")


class Create(Base):
    def test_create_suggested(self):
        path, copied, found = P.create(**self.where)
        self.assertEqual((path, copied, found), (os.path.join(self.drive, "cenk", "profile.json"), None, True))
        self.assertEqual(read(path), {})
        with self.assertRaises(P.ProfileError):
            P.create(**self.where)

    def test_create_elsewhere_needs_pin(self):
        folder = os.path.join(self.tmp, "chosen", "cenk")
        path, _, found = P.create(os.path.join(folder, "profile.json"), **self.where)
        self.assertEqual(path, os.path.join(folder, "profile.json"))
        self.assertFalse(found)

    def test_create_copies_old(self):
        old = os.path.join(self.drive, "claude", "profile.json")
        write(old, {"person": {"name": "Ada Lovelace"}})
        path, copied, found = P.create(**self.where)
        self.assertEqual((copied, found), (old, True))
        self.assertEqual(read(path)["person"]["name"], "Ada Lovelace")
        self.assertTrue(os.path.exists(old))
        self.assertFalse(P.locate(**self.where)["old"])

    def test_create_refused_in_case(self):
        case = os.path.join(self.drive, "overtime-billing")
        write(os.path.join(case, "master.sqlite"), {})
        with self.assertRaises(P.ProfileError) as e:
            P.create(os.path.join(case, "notes"), **self.where)
        self.assertIn("case folder", str(e.exception))
        with self.assertRaises(P.ProfileError):
            P.create(os.path.join(self.drive, "billing-evidence"), **self.where)

    def test_create_refused_other_than_home(self):
        os.environ["CENK_HOME"] = os.path.join(self.tmp, "named")
        with self.assertRaises(P.ProfileError) as e:
            P.create(os.path.join(self.tmp, "other"), **self.where)
        self.assertIn("CENK_HOME", str(e.exception))
        path, _, found = P.create(os.path.join(self.tmp, "named"), **self.where)
        self.assertTrue(found)


class Pin(Base):
    def test_pin(self):
        settings = os.path.join(self.claude, "settings.json")
        write(settings, {"env": {"OTHER": "1"}, "theme": "dark"})
        folder = os.path.join(self.tmp, "chosen")
        with self.assertRaises(P.ProfileError) as e:
            P.pin(folder, claude_dir=self.claude)
        self.assertEqual(e.exception.code, 1)
        self.assertNotIn("CENK_HOME", read(settings)["env"])
        self.assertEqual(P.pin(folder, yes=True, claude_dir=self.claude), (settings, True))
        data = read(settings)
        self.assertEqual(data["env"]["CENK_HOME"], folder.replace("\\", "/"))
        self.assertEqual((data["env"]["OTHER"], data["theme"]), ("1", "dark"))
        self.assertEqual(P.pin(os.path.join(folder, "profile.json"), claude_dir=self.claude), (settings, False))

    def test_pin_bad_settings(self):
        with open(os.path.join(self.claude, "settings.json"), "w") as f:
            f.write("{not json")
        with self.assertRaises(P.ProfileError):
            P.pin(self.tmp, yes=True, claude_dir=self.claude)


class Command(Base):
    """The command line, with CENK_HOME set so nothing else on this computer is looked at."""

    def run_cli(self, *args, stdin=""):
        env = dict(os.environ, CENK_HOME=os.path.join(self.tmp, "home"), CLAUDE_CONFIG_DIR=self.claude)
        env.pop("CENK_PROFILE", None)
        r = subprocess.run([sys.executable, "-I", LIB, *args], input=stdin, capture_output=True, text=True,
                           encoding="utf-8", env=env)
        return r.returncode, r.stdout.strip(), r.stderr.strip()

    def test_flow(self):
        home = os.path.join(self.tmp, "home")
        self.assertEqual(self.run_cli("path"), (0, "", ""))
        self.assertEqual(self.run_cli("home")[1], os.path.abspath(home))
        self.assertEqual(self.run_cli("get", "person.name")[0], 1)
        code, out, _ = self.run_cli("create")
        self.assertEqual(code, 0)
        self.assertNotIn("pin", out)
        self.assertEqual(self.run_cli("set", "person.name", "-", stdin='"Ada Lovelace"')[0], 0)
        self.assertEqual(self.run_cli("get", "person.name")[1], "Ada Lovelace")
        self.assertEqual(self.run_cli("set", "person.name", '"Ada King"')[0], 3)
        self.assertEqual(self.run_cli("set", "person.name", '"Ada King"', "--old", '"Ada Lovelace"')[0], 0)
        self.assertEqual(self.run_cli("set", "person.name", "Ada")[0], 2)
        both = '{"old": "Ada King", "new": "Ada Byron"}'
        self.assertEqual(self.run_cli("set", "person.name", "-", "--old", "-", stdin=both)[0], 0)
        self.assertEqual(self.run_cli("get", "person.name")[1], "Ada Byron")
        self.assertEqual(self.run_cli("set", "person.name", '"Ada"', "--old", "-", stdin='"Ada King"')[0], 3)
        self.assertEqual(self.run_cli("set", "person.name", "-", "--old", "-", stdin='"x"')[0], 2)
        self.assertEqual(self.run_cli("set", "settings.common.mode", '"draft"')[0], 1)
        self.assertEqual(self.run_cli("set", "settings.common.mode", '"draft"', "--yes")[0], 0)
        self.assertEqual(self.run_cli("get", "cenk-jobs", "mode")[1], "draft")
        self.assertEqual(self.run_cli("get", "cenk-jobs", "nothing"), (0, "", ""))
        self.assertEqual(self.run_cli("erase", "person.name")[0], 0)
        with open(os.path.join(home, "profile.json"), encoding="utf-8") as f:
            self.assertNotIn("Ada", f.read())
        self.assertEqual(self.run_cli("pin", home)[0], 1)
        self.assertEqual(self.run_cli("pin", home, "--yes")[0], 0)
        self.assertEqual(read(os.path.join(self.claude, "settings.json"))["env"]["CENK_HOME"],
                         os.path.abspath(home).replace("\\", "/"))
        self.assertEqual(self.run_cli("bogus")[0], 2)


if __name__ == "__main__":
    unittest.main(verbosity=1)
