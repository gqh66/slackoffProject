"""整窗验证：在摸鱼神器主界面里打开并嵌入一个真实程序。"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import os

os.environ["SLACKOFF_HOME"] = str(ROOT / "data" / "appembed")
os.environ.pop("QT_QPA_PLATFORM", None)

import logging

logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")

from PIL import ImageGrab  # noqa: E402
from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from slackoff import apps, winapi  # noqa: E402
from slackoff.config import Settings  # noqa: E402
from slackoff.ui import theme  # noqa: E402
from slackoff.ui.main_window import MainWindow  # noqa: E402


def wait(ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def main() -> int:
    exe = Path(r"C:\Windows\System32\mstsc.exe")
    if not exe.is_file():
        exe = Path(r"C:\Windows\System32\regedit.exe")
    if not exe.is_file():
        print("没有可测试的系统程序")
        return 1

    app = QApplication(sys.argv[:1])
    theme.apply_theme(app)

    settings = Settings()
    settings.pinned_apps = []
    pinned, _ = apps.add_path(settings, exe, name="远程桌面")

    window = MainWindow(settings, headless=True)
    window.headless = False  # 允许走嵌入路径
    window.resize(1200, 800)
    window.move(60, 60)
    window.show()
    wait(500)

    window.open_app(pinned.id)
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline and window._embedder.current is None:
        app.processEvents()
        time.sleep(0.05)

    info = window._embedder.current
    if info is None:
        print("EMBED FAILED. page text:", window._app_placeholder.text())
        window.quit_app()
        return 2

    wait(400)
    container_hwnd = int(window._app_container.winId())
    parent = winapi.get_parent(info.hwnd)
    print("embedded:", info.hwnd, "parent:", parent, "container:", container_hwnd)
    print("on app page:", window._stack.currentWidget() is window._app_page)
    print("child size:", winapi.window_rect(info.hwnd))
    print("container:", window._app_container.width(), window._app_container.height())

    winapi.set_foreground(int(window.winId()))
    wait(700)
    window_rect = winapi.window_rect(int(window.winId()))
    ImageGrab.grab(bbox=window_rect).save(ROOT / "app-embed-shot.png")
    print("saved app-embed-shot.png")

    window.resize(1000, 680)
    wait(500)
    child = winapi.window_rect(info.hwnd)
    ratio = float(window._app_container.devicePixelRatioF() or 1.0)
    expected = window._app_container.width() * ratio
    print("after resize child:", child, "expected width:", expected)
    follows = abs((child[2] - child[0]) - expected) <= 4

    window._detach_embedded()
    wait(400)
    detached = winapi.get_parent(info.hwnd) == 0
    print("detached:", detached)
    winapi.post_close(info.hwnd)
    wait(300)
    window.quit_app()
    wait(400)
    return 0 if (parent == container_hwnd and follows and detached) else 3


if __name__ == "__main__":
    raise SystemExit(main())
