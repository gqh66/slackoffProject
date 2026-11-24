import json
import tempfile
import unittest
from pathlib import Path

from slackoff.config import Settings


class ConfigDefaultsTest(unittest.TestCase):
    def test_defaults_are_sane(self):
        settings = Settings()
        settings.normalize()
        self.assertEqual(settings.boss_key, "ctrl+alt+b")
        self.assertEqual(settings.stealth_key, "ctrl+alt+h")
        self.assertTrue(settings.stealth.enabled)
        self.assertEqual(settings.stealth.trigger, "leave")
        self.assertEqual(settings.stealth.hot_corner, "left")
        self.assertEqual(settings.window.close_action, "ask")
        self.assertTrue(settings.first_run)

    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            settings = Settings()
            settings.boss_key = "ctrl+alt+m"
            settings.stealth.leave_delay_ms = 777
            settings.browser.home_url = "https://www.bilibili.com/"
            settings.custom_sites = [{"name": "测试站", "url": "https://example.com/"}]
            settings.window.geometry = [10, 20, 800, 600]
            self.assertTrue(settings.save(path))
            self.assertTrue(path.is_file())

            loaded = Settings.load(path)
            self.assertEqual(loaded.boss_key, "ctrl+alt+m")
            self.assertEqual(loaded.stealth.leave_delay_ms, 777)
            self.assertEqual(loaded.browser.home_url, "https://www.bilibili.com/")
            self.assertEqual(loaded.custom_sites[0]["name"], "测试站")
            self.assertEqual(loaded.window.geometry, [10, 20, 800, 600])

    def test_bad_json_falls_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text("{ not valid json", encoding="utf-8")
            loaded = Settings.load(path)
            self.assertEqual(loaded.boss_key, "ctrl+alt+b")

    def test_unknown_fields_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(
                json.dumps({"boss_key": "alt+1", "nonsense": {"a": 1}, "boss": {"unknown": True}}),
                encoding="utf-8",
            )
            loaded = Settings.load(path)
            self.assertEqual(loaded.boss_key, "alt+1")
            self.assertFalse(hasattr(loaded, "nonsense"))

    def test_wrong_types_do_not_crash(self):
        raw = {
            "boss_key": 123,
            "stealth": {"enabled": "yes", "leave_delay_ms": "abc", "hot_corner": ["left"]},
            "boss": {"mute_audio": 0},
            "custom_sites": "nope",
            "pinned_apps": "nope",
        }
        settings = Settings.from_dict(raw)
        settings.normalize()
        self.assertEqual(settings.boss_key, "ctrl+alt+b")
        self.assertTrue(settings.stealth.enabled)
        self.assertEqual(settings.stealth.leave_delay_ms, 1200)
        self.assertEqual(settings.stealth.hot_corner, "left")
        self.assertTrue(settings.boss.mute_audio)
        self.assertEqual(settings.custom_sites, [])
        self.assertEqual(settings.pinned_apps, [])

    def test_values_are_clamped(self):
        settings = Settings.from_dict(
            {
                "stealth": {
                    "leave_delay_ms": 1,
                    "dwell_ms": 99999,
                    "hot_corner_span": 5,
                    "hot_corner_size": 0,
                    "trigger": "teleport",
                },
                "window": {"opacity": 5},
                "browser": {"zoom": 9, "search_engine": "yandex"},
            }
        )
        settings.normalize()
        self.assertGreaterEqual(settings.stealth.leave_delay_ms, 200)
        self.assertLessEqual(settings.stealth.dwell_ms, 5000)
        self.assertEqual(settings.stealth.hot_corner_span, 1.0)
        self.assertGreaterEqual(settings.stealth.hot_corner_size, 1)
        self.assertEqual(settings.stealth.trigger, "leave")
        self.assertEqual(settings.window.opacity, 1.0)
        self.assertEqual(settings.browser.zoom, 2.5)
        self.assertEqual(settings.browser.search_engine, "baidu")

    def test_invalid_hotkeys_fall_back(self):
        settings = Settings.from_dict({"boss_key": "b", "stealth_key": ""})
        settings.normalize()
        self.assertEqual(settings.boss_key, "ctrl+alt+b")
        self.assertEqual(settings.stealth_key, "ctrl+alt+h")

    def test_equal_hotkeys_are_separated(self):
        settings = Settings.from_dict({"boss_key": "ctrl+alt+b", "stealth_key": "ctrl+alt+b"})
        settings.normalize()
        self.assertNotEqual(settings.boss_key, settings.stealth_key)

    def test_apps_embed_setting(self):
        self.assertTrue(Settings().apps.embed)
        loaded = Settings.from_dict({"apps": {"embed": False}})
        self.assertFalse(loaded.apps.embed)

    def test_close_action(self):
        for value in ("tray", "quit", "ask"):
            settings = Settings.from_dict({"window": {"close_action": value}})
            settings.normalize()
            self.assertEqual(settings.window.close_action, value)
        settings = Settings.from_dict({"window": {"close_action": "minimize"}})
        settings.normalize()
        self.assertEqual(settings.window.close_action, "ask")
        # 旧配置里的 close_to_tray 不再生效，升级后先询问一次
        legacy = Settings.from_dict({"window": {"close_to_tray": False}})
        legacy.normalize()
        self.assertEqual(legacy.window.close_action, "ask")

    def test_pinned_apps_are_cleaned(self):
        settings = Settings.from_dict(
            {
                "pinned_apps": [
                    {"name": "播放器", "exe": "C:/Apps/player.exe"},
                    {"name": "重复", "exe": "C:\\Apps\\player.exe"},
                    {"name": "空路径", "exe": ""},
                    "不是字典",
                ]
            }
        )
        settings.normalize()
        self.assertEqual(len(settings.pinned_apps), 1)
        self.assertEqual(settings.pinned_apps[0]["name"], "播放器")

    def test_disguise_preset(self):
        self.assertEqual(Settings().disguise.preset, "default")
        self.assertEqual(Settings.from_dict({"disguise": {"preset": "excel"}}).disguise.preset, "excel")
        broken = Settings.from_dict({"disguise": {"preset": "not-a-brand"}})
        broken.normalize()
        self.assertEqual(broken.disguise.preset, "default")

    def test_work_end_time(self):
        self.assertEqual(Settings().dashboard.work_end, "18:00")
        self.assertEqual(Settings.from_dict({"dashboard": {"work_end": "17:30"}}).dashboard.work_end, "17:30")
        short = Settings.from_dict({"dashboard": {"work_end": "9:05"}})
        short.normalize()
        self.assertEqual(short.dashboard.work_end, "09:05")
        for bad in ("25:00", "18:99", "abc", "", None):
            settings = Settings.from_dict({"dashboard": {"work_end": bad}})
            settings.normalize()
            self.assertEqual(settings.dashboard.work_end, "18:00")

    def test_reader_theme(self):
        self.assertEqual(Settings().reader.theme, "yellow")
        self.assertEqual(Settings.from_dict({"reader": {"theme": "dark"}}).reader.theme, "dark")
        broken = Settings.from_dict({"reader": {"theme": "neon"}})
        broken.normalize()
        self.assertEqual(broken.reader.theme, "yellow")

    def test_pinned_books_are_cleaned(self):
        settings = Settings.from_dict(
            {
                "pinned_books": [
                    {"name": "书一", "path": "C:/Books/a.txt"},
                    {"name": "重复", "path": "C:\\Books\\a.txt"},
                    {"name": "空", "path": ""},
                ]
            }
        )
        settings.normalize()
        self.assertEqual(len(settings.pinned_books), 1)
        self.assertEqual(settings.pinned_books[0]["name"], "书一")

    def test_old_custom_apps_are_migrated(self):
        settings = Settings.from_dict(
            {"custom_apps": [{"name": "旧应用", "exe": "C:/Old/app.exe", "color": "#123456"}]}
        )
        self.assertEqual(len(settings.pinned_apps), 1)
        self.assertEqual(settings.pinned_apps[0]["name"], "旧应用")
        self.assertEqual(settings.pinned_apps[0]["exe"], "C:/Old/app.exe")


if __name__ == "__main__":
    unittest.main()
