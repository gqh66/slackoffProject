import unittest

from PySide6.QtCore import QRect

from slackoff.stealth import hot_corner_rect

SCREEN = QRect(0, 0, 1920, 1080)


class HotCornerRectTest(unittest.TestCase):
    def test_left(self):
        rect = hot_corner_rect(SCREEN, "left", 4, 0.45)
        self.assertEqual(rect.left(), 0)
        self.assertEqual(rect.width(), 4)
        self.assertGreaterEqual(rect.height(), 40)
        self.assertAlmostEqual(rect.center().y(), SCREEN.center().y(), delta=2)

    def test_right(self):
        rect = hot_corner_rect(SCREEN, "right", 4, 0.45)
        self.assertEqual(rect.right(), SCREEN.right())

    def test_top(self):
        rect = hot_corner_rect(SCREEN, "top", 6, 0.5)
        self.assertEqual(rect.top(), 0)
        self.assertEqual(rect.height(), 6)

    def test_bottom(self):
        rect = hot_corner_rect(SCREEN, "bottom", 6, 0.5)
        self.assertEqual(rect.bottom(), SCREEN.bottom())

    def test_offsets_are_respected(self):
        screen = QRect(1920, 100, 1280, 720)
        rect = hot_corner_rect(screen, "left", 5, 0.5)
        self.assertEqual(rect.left(), 1920)
        self.assertGreaterEqual(rect.top(), 100)
        self.assertLessEqual(rect.bottom(), 100 + 720 - 1)

    def test_none_is_empty(self):
        self.assertTrue(hot_corner_rect(SCREEN, "none", 4, 0.5).isEmpty())
        self.assertTrue(hot_corner_rect(QRect(), "left", 4, 0.5).isEmpty())

    def test_span_and_size_are_clamped(self):
        rect = hot_corner_rect(SCREEN, "left", 0, 5.0)
        self.assertGreaterEqual(rect.width(), 2)
        self.assertLessEqual(rect.height(), SCREEN.height())


if __name__ == "__main__":
    unittest.main()
