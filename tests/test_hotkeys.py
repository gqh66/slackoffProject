import unittest

from slackoff.hotkeys import (
    backend_hotkey,
    format_hotkey,
    hotkey_to_qt,
    normalize_hotkey,
    to_native,
)


class NormalizeHotkeyTest(unittest.TestCase):
    def test_variants(self):
        cases = {
            "Ctrl+Shift+B": "ctrl+shift+b",
            "ctrl + shift + b": "ctrl+shift+b",
            "CONTROL+ALT+F5": "ctrl+alt+f5",
            "alt+ctrl+space": "ctrl+alt+space",
            "shift+ctrl+win+`": "ctrl+shift+win+`",
            "windows+b": "win+b",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(normalize_hotkey(raw), expected)

    def test_modifier_order_is_canonical(self):
        self.assertEqual(normalize_hotkey("win+shift+alt+ctrl+b"), "ctrl+alt+shift+win+b")

    def test_requires_main_modifier(self):
        for raw in ("b", "shift+b", "ctrl", "ctrl+shift", "", None, "ctrl+a+b", "ctrl+f25", "ctrl+??"):
            with self.subTest(raw=raw):
                self.assertIsNone(normalize_hotkey(raw))

    def test_named_keys(self):
        self.assertEqual(normalize_hotkey("ctrl+page up"), "ctrl+page up")
        self.assertEqual(normalize_hotkey("ctrl+pgdn"), "ctrl+page down")
        self.assertEqual(normalize_hotkey("alt+esc"), "alt+escape")
        self.assertEqual(normalize_hotkey("win+f12"), "win+f12")


class FormatHotkeyTest(unittest.TestCase):
    def test_display(self):
        self.assertEqual(format_hotkey("ctrl+shift+b"), "Ctrl + Shift + B")
        self.assertEqual(format_hotkey("alt+f5"), "Alt + F5")
        self.assertEqual(format_hotkey("ctrl+win+space"), "Ctrl + Win + Space")
        self.assertEqual(format_hotkey("ctrl+page down"), "Ctrl + PgDn")

    def test_invalid(self):
        self.assertEqual(format_hotkey("b"), "b")
        self.assertEqual(format_hotkey(""), "未设置")


class QtSequenceTest(unittest.TestCase):
    def test_qt_string(self):
        self.assertEqual(hotkey_to_qt("ctrl+shift+b"), "Ctrl+Shift+B")
        self.assertEqual(hotkey_to_qt("ctrl+win+`"), "Ctrl+Meta+`")
        self.assertEqual(hotkey_to_qt("ctrl+page up"), "Ctrl+PgUp")
        self.assertEqual(hotkey_to_qt("bad"), "")

    def test_backend_string(self):
        self.assertEqual(backend_hotkey("ctrl+win+b"), "ctrl+windows+b")
        self.assertEqual(backend_hotkey("ctrl+alt+f1"), "ctrl+alt+f1")


class NativeHotkeyTest(unittest.TestCase):
    def test_letters_and_digits(self):
        self.assertEqual(to_native("ctrl+alt+b"), (0x0003, ord("B")))
        self.assertEqual(to_native("ctrl+shift+1"), (0x0006, ord("1")))

    def test_function_keys(self):
        self.assertEqual(to_native("ctrl+f1"), (0x0002, 0x70))
        self.assertEqual(to_native("alt+shift+f12"), (0x0005, 0x7B))

    def test_named_and_punctuation(self):
        self.assertEqual(to_native("ctrl+space"), (0x0002, 0x20))
        self.assertEqual(to_native("ctrl+page up"), (0x0002, 0x21))
        self.assertEqual(to_native("ctrl+`"), (0x0002, 0xC0))
        self.assertEqual(to_native("ctrl+win+escape"), (0x000A, 0x1B))

    def test_invalid(self):
        self.assertIsNone(to_native("b"))
        self.assertIsNone(to_native(""))


if __name__ == "__main__":
    unittest.main()
