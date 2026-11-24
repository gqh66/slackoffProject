import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QRect, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from slackoff import stealth  # noqa: E402
from slackoff.config import Settings  # noqa: E402

APP = QApplication.instance() or QApplication([])


class FakeScreen:
    def availableGeometry(self):
        return QRect(0, 0, 1000, 800)


class FakeApp:
    @staticmethod
    def activeModalWidget():
        return None

    @staticmethod
    def activePopupWidget():
        return None

    @staticmethod
    def mouseButtons():
        return Qt.MouseButton.NoButton

    @staticmethod
    def primaryScreen():
        return FakeScreen()


class FakeWindow:
    def __init__(self, rect=None):
        self._rect = rect or QRect(100, 100, 600, 400)

    def frameGeometry(self):
        return self._rect

    def isVisible(self):
        return True

    def isMinimized(self):
        return False

    def screen(self):
        return FakeScreen()


class StealthControllerTest(unittest.TestCase):
    def tearDown(self):
        for widget in QApplication.topLevelWidgets():
            if isinstance(widget, stealth.EdgeMarker):
                widget.hide()

    def test_set_settings_replaces_reference(self):
        """回归：设置对话框保存后必须让控制器拿到新的 Settings 对象。"""
        old = Settings()
        old.stealth.enabled = False
        new = Settings()
        new.stealth.enabled = True

        controller = stealth.StealthController(FakeWindow(), old)
        controller.set_settings(new)
        self.assertIs(controller._settings, new)

    def test_leave_hide_uses_new_settings(self):
        old = Settings()
        old.stealth.enabled = False
        new = Settings()
        new.stealth.enabled = True
        new.stealth.leave_delay_ms = 1000

        controller = stealth.StealthController(FakeWindow(), old)
        controller.set_settings(new)
        events: list[str] = []
        controller.hideRequested.connect(events.append)

        cursor = mock.Mock()
        cursor.pos.return_value = QPoint(950, 750)  # 窗口外
        now = [100.0]

        with mock.patch.object(stealth, "QCursor", cursor), \
                mock.patch.object(stealth, "QApplication", FakeApp), \
                mock.patch.object(stealth.time, "monotonic", lambda: now[0]):
            controller._armed = True
            controller._tick()
            now[0] += 1.05
            controller._tick()

        self.assertEqual(events, ["leave"])

    def test_hot_corner_restores(self):
        settings = Settings()
        settings.stealth.enabled = True
        settings.stealth.hot_corner = "left"
        settings.stealth.hot_corner_size = 12
        settings.stealth.hot_corner_span = 0.6
        settings.stealth.dwell_ms = 250

        controller = stealth.StealthController(FakeWindow(), settings)
        controller.set_visible(False)
        controller.notify_hidden_by_stealth()
        events: list[str] = []
        controller.showRequested.connect(events.append)

        cursor = mock.Mock()
        cursor.pos.return_value = QPoint(5, 400)  # 左侧感应条内
        now = [200.0]

        with mock.patch.object(stealth, "QCursor", cursor), \
                mock.patch.object(stealth, "QApplication", FakeApp), \
                mock.patch.object(stealth.time, "monotonic", lambda: now[0]):
            controller._corner_since = None
            for _ in range(4):
                now[0] += 0.1
                controller._tick()

        self.assertEqual(events, ["hotcorner"])

    def test_cursor_outside_corner_does_not_restore(self):
        settings = Settings()
        settings.stealth.enabled = True
        settings.stealth.hot_corner = "left"
        settings.stealth.dwell_ms = 250

        controller = stealth.StealthController(FakeWindow(), settings)
        controller.set_visible(False)
        controller.notify_hidden_by_stealth()
        events: list[str] = []
        controller.showRequested.connect(events.append)

        cursor = mock.Mock()
        cursor.pos.return_value = QPoint(500, 400)  # 屏幕中间，不在左边缘
        now = [300.0]

        with mock.patch.object(stealth, "QCursor", cursor), \
                mock.patch.object(stealth, "QApplication", FakeApp), \
                mock.patch.object(stealth.time, "monotonic", lambda: now[0]):
            for _ in range(6):
                now[0] += 0.1
                controller._tick()

        self.assertEqual(events, [])


if __name__ == "__main__":
    unittest.main()
