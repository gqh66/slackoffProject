import os
import sys
import unittest
from pathlib import Path

from slackoff import winapi


@unittest.skipIf(sys.platform != "win32", "仅 Windows")
class WinApiTest(unittest.TestCase):
    def test_enumerate_returns_windows(self):
        windows = winapi.enumerate_windows()
        self.assertIsInstance(windows, list)
        self.assertGreater(len(windows), 0)

    def test_visible_only_filter(self):
        windows = winapi.enumerate_windows(visible_only=True)
        self.assertTrue(all(w.visible for w in windows))

    def test_process_path_of_self(self):
        path = winapi.process_path(os.getpid())
        self.assertTrue(path)
        self.assertTrue(Path(path).name.lower().startswith("python"))

    def test_find_client_windows_returns_list(self):
        result = winapi.find_client_windows(
            exe_names={"definitely-not-a-real-process.exe"},
            title_keywords=(),
            exclude_pids=set(),
        )
        self.assertEqual(result, [])

    def test_window_helpers_on_bad_handle(self):
        self.assertFalse(winapi.is_visible(0))
        self.assertFalse(winapi.is_minimized(0))
        self.assertEqual(winapi.window_title(0), "")
        self.assertEqual(winapi.class_name(0), "")
        self.assertEqual(winapi.window_pid(0), 0)
        self.assertFalse(winapi.hide_window(0))
        self.assertFalse(winapi.show_window(0))


if __name__ == "__main__":
    unittest.main()
