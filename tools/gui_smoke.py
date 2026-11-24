"""整窗冒烟测试：老板键 → 隐身 → 唤回 → 退出。

    python tools/gui_smoke.py

离屏运行，不需要显示器；使用独立的 SLACKOFF_HOME。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox --disable-gpu --single-process")
os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
os.environ["SLACKOFF_HEADLESS"] = "1"
os.environ["SLACKOFF_HOME"] = str(ROOT / "data" / "guitest")

from PySide6.QtCore import QEventLoop, QMimeData, QPointF, QTimer, Qt, QUrl  # noqa: E402
from PySide6.QtGui import QDropEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from slackoff.config import Settings  # noqa: E402
from slackoff.ui import theme  # noqa: E402
from slackoff.ui.main_window import MainWindow  # noqa: E402


def wait(ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print("ok -", message)


def main() -> int:
    app = QApplication(sys.argv[:1])
    theme.apply_theme(app)

    settings = Settings.load()
    settings.pinned_apps = []
    settings.pinned_books = []
    settings.save()
    window = MainWindow(settings, headless=True)
    window.resize(1200, 760)
    window.show()
    wait(1800)

    check(window.isVisible(), "主窗口显示")
    check(window._hidden_reason is None, "初始未隐藏")
    check(
        bool(window.windowFlags() & Qt.WindowType.WindowCloseButtonHint),
        "右上角关闭按钮可用",
    )

    window._dashboard.set_work_end("17:30")
    check(window.settings.dashboard.work_end == "17:30", "下班时间已保存")
    check("17:30" in window._dashboard._countdown_label.text(), "倒计时使用新时间")
    window._dashboard.set_work_end("18:00")

    window.settings.disguise.preset = "excel"
    window._apply_disguise()
    check(window._brand_name.text() == "Excel", "伪装成 Excel")
    check(window.windowTitle() == "工作簿1 - Excel", "窗口标题同步伪装")
    check(not window.windowIcon().isNull(), "任务栏图标已切换")
    window.settings.disguise.preset = "default"
    window._apply_disguise()

    window.hide_everything()
    wait(300)
    check(not window.isVisible(), "老板键隐藏窗口")
    check(window._hidden_reason == "boss", "隐藏原因记录为 boss")

    window.restore_window(focus=False)
    wait(400)
    check(window.isVisible(), "老板键唤回窗口")
    check(window._hidden_reason is None, "隐藏状态已清除")

    window.hide_for_stealth("test")
    wait(300)
    check(not window.isVisible(), "隐身模式隐藏窗口")
    check(window._hidden_reason == "stealth", "隐藏原因记录为 stealth")

    window.stealth.showRequested.emit("hotcorner")
    wait(400)
    check(window.isVisible(), "边缘唤回")

    # 浏览器加载一个本地页面
    html = ROOT / "data" / "guitest" / "page.html"
    html.parent.mkdir(parents=True, exist_ok=True)
    html.write_text("<html><body><h1>hello</h1></body></html>", encoding="utf-8")
    window.open_site(html.as_uri())
    wait(1200)
    check(window._stack.currentIndex() == 1, "切到浏览器页")
    check(window._browser.url().toString().endswith("page.html"), "本地页面已加载")

    # 浏览器静音 / 恢复
    window._browser.set_muted(True)
    check(window._browser.is_muted(), "网页静音")
    window._browser.set_muted(False)
    check(not window._browser.is_muted(), "网页取消静音")

    # 设置窗口能构造并保存
    from slackoff.ui.settings_dialog import SettingsDialog

    dialog = SettingsDialog(window.settings, window, hotkey_available=True)
    dialog.resize(800, 680)
    dialog.show()
    wait(300)
    dialog._on_save()
    check(dialog.result() == dialog.DialogCode.Accepted, "设置保存成功")

    # 模拟把 exe 拖进窗口
    from unittest.mock import patch

    exe = ROOT / "data" / "guitest" / "测试播放器.exe"
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_bytes(b"MZ" + b"\x00" * 32)
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(exe))])
    with patch("slackoff.apps.launch", return_value=(True, "正在打开 测试播放器…")) as launch_mock:
        drop = QDropEvent(
            QPointF(200, 200),
            Qt.DropAction.CopyAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        handled = window.eventFilter(window, drop)
    check(handled, "拖拽事件被接收")
    check(not launch_mock.called, "拖入后不自动启动")
    wait(300)
    check(len(window.settings.pinned_apps) == 1, "拖入 exe 后加入「我的应用」")
    check(window.settings.pinned_apps[0]["name"] == "测试播放器", "应用名取自文件名")

    # 不支持的格式不应该被接受
    bad = ROOT / "data" / "guitest" / "note.pdf"
    bad.write_bytes(b"%PDF-1.4")
    bad_mime = QMimeData()
    bad_mime.setUrls([QUrl.fromLocalFile(str(bad))])
    bad_drop = QDropEvent(
        QPointF(200, 200),
        Qt.DropAction.CopyAction,
        bad_mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    window.eventFilter(window, bad_drop)
    check(len(window.settings.pinned_apps) == 1, "不支持的格式被忽略")

    # 拖入 txt 电子书：加入书架并打开护眼阅读页
    book_file = ROOT / "data" / "guitest" / "测试电子书.txt"
    book_file.write_text("第一章 摸鱼\n第二章 下班\n第三章 明天见", encoding="utf-8")
    book_mime = QMimeData()
    book_mime.setUrls([QUrl.fromLocalFile(str(book_file))])
    book_drop = QDropEvent(
        QPointF(200, 200),
        Qt.DropAction.CopyAction,
        book_mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    window.eventFilter(window, book_drop)
    wait(300)
    check(len(window.settings.pinned_books) == 1, "拖入 txt 后加入「我的书」")
    check(window._stack.currentWidget() is window._reader_page, "自动打开阅读页")
    check("第一章 摸鱼" in window._reader_editor.toPlainText(), "电子书内容已载入")
    check("#F6E7B8" in window._reader_editor.styleSheet(), "阅读背景是护眼黄")
    check(window.settings.reader.theme == "yellow", "默认使用护眼黄")

    window._set_reader_theme("dark")
    wait(200)
    check("#0D1016" in window._reader_editor.styleSheet(), "可切换成暗色黑底")
    check(window.settings.reader.theme == "dark", "暗色选择已保存")
    window._set_reader_theme("yellow")

    window.quit_app()
    wait(600)
    print("all good")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
