import tempfile
import unittest
from pathlib import Path

from slackoff import apps
from slackoff.config import Settings


class PinnedAppsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.exe = Path(self.tmp.name) / "QQLive.exe"
        self.exe.write_bytes(b"MZ" + b"\x00" * 32)
        self.settings = Settings()

    def test_add_exe(self):
        app, created = apps.add_path(self.settings, self.exe)
        self.assertTrue(created)
        self.assertEqual(app.exe, str(self.exe.resolve()))
        self.assertEqual(app.name, "QQLive")
        self.assertTrue(app.id.startswith("app-"))
        self.assertEqual(len(self.settings.pinned_apps), 1)
        self.assertEqual(self.settings.pinned_apps[0]["id"], app.id)

    def test_duplicate_is_not_added_twice(self):
        app1, created1 = apps.add_path(self.settings, self.exe)
        app2, created2 = apps.add_path(self.settings, self.exe)
        self.assertTrue(created1)
        self.assertFalse(created2)
        self.assertEqual(app1.id, app2.id)
        self.assertEqual(len(self.settings.pinned_apps), 1)

    def test_custom_name(self):
        app, _ = apps.add_path(self.settings, self.exe, name="腾讯视频")
        self.assertEqual(app.name, "腾讯视频")

    def test_remove(self):
        app, _ = apps.add_path(self.settings, self.exe)
        self.assertTrue(apps.remove(self.settings, app.id))
        self.assertEqual(self.settings.pinned_apps, [])
        self.assertFalse(apps.remove(self.settings, "app-does-not-exist"))

    def test_find_app(self):
        app, _ = apps.add_path(self.settings, self.exe)
        found = apps.find_app(self.settings, app.id)
        self.assertIsNotNone(found)
        self.assertEqual(found.name, "QQLive")
        self.assertIsNone(apps.find_app(self.settings, "nope"))

    def test_window_targets(self):
        apps.add_path(self.settings, self.exe, name="腾讯视频")
        exe_names, titles = apps.window_targets(self.settings)
        self.assertIn("qqlive.exe", exe_names)
        self.assertIn("腾讯视频", titles)
        self.assertIn("QQLive", titles)

    def test_launch_missing_file(self):
        marker = apps.PinnedApp(id="app-x", name="不见了", exe=str(Path(self.tmp.name) / "missing.exe"))
        ok, message = apps.launch(marker)
        self.assertFalse(ok)
        self.assertIn("找不到", message)

    def test_rejects_non_exe(self):
        text = Path(self.tmp.name) / "note.txt"
        text.write_text("hi", encoding="utf-8")
        with self.assertRaises(ValueError):
            apps.add_path(self.settings, text)
        self.assertIsNone(apps.resolve_drop(str(text)))

    def test_load_apps_fills_missing_ids(self):
        self.settings.pinned_apps = [{"name": "播放器", "exe": str(self.exe)}]
        loaded = apps.load_apps(self.settings)
        self.assertEqual(len(loaded), 1)
        self.assertTrue(loaded[0].id.startswith("app-"))
        self.assertTrue(self.settings.pinned_apps[0]["id"])
        self.assertTrue(self.settings.pinned_apps[0]["color"])

    def test_existing_file_property(self):
        app, _ = apps.add_path(self.settings, self.exe)
        self.assertTrue(app.exists)
        self.exe.unlink()
        self.assertFalse(app.exists)


if __name__ == "__main__":
    unittest.main()
