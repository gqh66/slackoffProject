import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from slackoff.ui.settings_dialog import AddSiteDialog  # noqa: E402

APP = QApplication.instance() or QApplication([])


class AddSiteDialogTest(unittest.TestCase):
    def _dialog(self) -> AddSiteDialog:
        return AddSiteDialog(None, "baidu")

    def test_valid_url_is_normalized(self):
        dialog = self._dialog()
        dialog._name_edit.setText("B站")
        dialog._url_edit.setText("www.bilibili.com")
        dialog._on_ok()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        site = dialog.site()
        self.assertEqual(site["name"], "B站")
        self.assertEqual(site["url"], "https://www.bilibili.com")

    def test_full_url_kept(self):
        dialog = self._dialog()
        dialog._name_edit.setText("内网")
        dialog._url_edit.setText("http://10.0.0.8:8080/wiki")
        dialog._on_ok()
        self.assertEqual(dialog.site()["url"], "http://10.0.0.8:8080/wiki")

    def test_empty_name_stays_open(self):
        dialog = self._dialog()
        dialog._url_edit.setText("www.example.com")
        dialog._on_ok()
        self.assertNotEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertFalse(dialog._error.isHidden())
        self.assertIn("名字", dialog._error.text())

    def test_empty_url_stays_open(self):
        dialog = self._dialog()
        dialog._name_edit.setText("示例")
        dialog._on_ok()
        self.assertNotEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertFalse(dialog._error.isHidden())

    def test_search_words_rejected(self):
        dialog = self._dialog()
        dialog._name_edit.setText("示例")
        dialog._url_edit.setText("随便写点东西")
        dialog._on_ok()
        self.assertNotEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertIn("格式", dialog._error.text())


if __name__ == "__main__":
    unittest.main()
