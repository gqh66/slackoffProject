"""真实桌面验证窗口嵌入：启动 charmap -> 嵌入容器 -> 截图 -> 分离。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from PIL import ImageGrab  # noqa: E402
from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget  # noqa: E402

from slackoff import apps, embed, winapi  # noqa: E402
from slackoff.ui import theme  # noqa: E402


def wait(ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def main() -> int:
    exe = Path(r"C:\Windows\System32\mstsc.exe")
    if not exe.is_file():
        exe = Path(r"C:\Windows\System32\regedit.exe")
    if not exe.is_file():
        print("没有找到可测试的系统程序")
        return 1
    print("test exe:", exe)

    app = QApplication(sys.argv[:1])
    theme.apply_theme(app)

    window = QWidget()
    window.setWindowTitle("嵌入测试容器")
    layout = QVBoxLayout(window)
    container = embed.EmbedContainer()
    layout.addWidget(container, 1)
    label = QLabel("等待程序窗口…")
    layout.addWidget(label)
    window.resize(900, 620)
    window.move(100, 100)
    window.show()
    wait(300)
    container_hwnd = int(container.winId())

    embedder = embed.WindowEmbedder(container)
    container.resized.connect(embedder.resize)
    result: dict = {}
    loop = QEventLoop()
    embedder.ready.connect(lambda info: (result.update(info=info), loop.quit()))
    embedder.failed.connect(lambda msg: (result.update(error=msg), loop.quit()))
    QTimer.singleShot(12000, loop.quit)
    embedder.start(apps.PinnedApp(id="test", name="字符映射表", exe=str(exe)))
    loop.exec()

    if "error" in result:
        print("EMBED FAILED:", result["error"])
        window.close()
        return 2
    info = result.get("info")
    if info is None:
        print("TIMEOUT")
        window.close()
        return 3

    wait(500)
    parent = winapi.get_parent(info.hwnd)
    print("embedded hwnd:", info.hwnd, "parent:", parent, "container:", container_hwnd)
    rect = winapi.window_rect(info.hwnd)
    print("child rect:", rect, "container size:", (container.width(), container.height()))
    print("is child:", parent == container_hwnd)

    window.resize(1100, 720)
    wait(500)
    rect2 = winapi.window_rect(info.hwnd)
    print("after resize, child rect:", rect2)
    ok_size = abs((rect2[2] - rect2[0]) - container.width()) <= 4
    print("size follows container:", ok_size)

    # 截容器区域
    left, top, right, bottom = winapi.window_rect(info.hwnd)
    image = ImageGrab.grab(bbox=(left, top, right, bottom))
    image.save(ROOT / "embed-shot.png")
    print("saved embed-shot.png", image.size)

    embedder.detach()
    wait(400)
    print("after detach parent:", winapi.get_parent(info.hwnd))
    winapi.post_close(info.hwnd)
    wait(300)
    window.close()
    return 0 if (parent == container_hwnd and ok_size) else 4


if __name__ == "__main__":
    raise SystemExit(main())
