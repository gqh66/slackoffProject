"""真实注册一次系统级热键，再模拟按下，确认 Qt 能收到 WM_HOTKEY。

    python tools/hotkey_live.py

注意：会短暂占用 Ctrl+Alt+B，并向系统发送一次该组合键。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import Qt, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from slackoff.hotkeys import GlobalHotkeys  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv[:1])

    host = QWidget()
    host.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
    host.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    host.resize(1, 1)

    received: list[str] = []
    manager = GlobalHotkeys(hwnd=int(host.winId()))
    manager.bossPressed.connect(lambda: received.append("boss"))
    manager.stealthPressed.connect(lambda: received.append("stealth"))
    ok = manager.attach("ctrl+alt+b", "ctrl+alt+h")
    print("attach:", ok, "|", manager.message)
    if not ok:
        return 1

    import keyboard

    QTimer.singleShot(600, lambda: keyboard.send("ctrl+alt+b"))
    QTimer.singleShot(1800, app.quit)
    app.exec()
    manager.detach()
    print("received:", received)
    return 0 if received == ["boss"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
