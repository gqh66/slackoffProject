import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTime  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from slackoff.ui.dashboard import WorkEndDialog  # noqa: E402

APP = QApplication.instance() or QApplication([])


class WorkEndDialogTest(unittest.TestCase):
    def test_round_trip(self):
        dialog = WorkEndDialog("17:30")
        self.assertEqual(dialog.value(), "17:30")

    def test_edit_value(self):
        dialog = WorkEndDialog("18:00")
        dialog._time.setTime(QTime(19, 5))
        self.assertEqual(dialog.value(), "19:05")

    def test_invalid_falls_back(self):
        dialog = WorkEndDialog("not-a-time")
        self.assertEqual(dialog.value(), "18:00")


if __name__ == "__main__":
    unittest.main()
