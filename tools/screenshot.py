"""离屏渲染界面截图，方便没有显示器时检查 UI。

    python tools/screenshot.py

生成 docs/preview-main.png、preview-settings.png、preview-decoy-code.png、
preview-decoy-excel.png。使用独立的 SLACKOFF_HOME，不会动你的真实配置。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("SLACKOFF_NO_WEB", "1")
os.environ.setdefault("SLACKOFF_HEADLESS", "1")
os.environ["SLACKOFF_HOME"] = str(ROOT / "data" / "preview")

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from slackoff import decoy  # noqa: E402
from slackoff.config import Settings  # noqa: E402
from slackoff.ui import theme  # noqa: E402
from slackoff.ui.main_window import MainWindow  # noqa: E402
from slackoff.ui.settings_dialog import SettingsDialog  # noqa: E402

DOCS = ROOT / "docs"


def wait(ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def grab(widget, name: str) -> Path:
    DOCS.mkdir(parents=True, exist_ok=True)
    path = DOCS / name
    pixmap = widget.grab()
    pixmap.save(str(path))
    print(f"saved {path} ({pixmap.width()}x{pixmap.height()})")
    return path


def main() -> int:
    DOCS.mkdir(parents=True, exist_ok=True)
    app = QApplication(sys.argv[:1])
    theme.apply_theme(app)

    settings = Settings.load()
    settings.first_run = True

    sample = ROOT / "data" / "preview" / "摸鱼指南.txt"
    sample.parent.mkdir(parents=True, exist_ok=True)
    sample.write_text(
        """第一章  摸鱼的哲学

  上班的本质，是用一段时间换取一点自由。
  既然时间已经卖掉了，那就让这段时间里，偶尔也有点自己的东西。

  摸鱼不是偷懒，是把紧绷的弦松一松。
  一首歌、一集剧、几页书，都是给下午续命的燃料。

第二章  如何优雅地消失

  老板键按下去的那一刻，世界安静了。
  屏幕暗下去，声音停下来，连光标都显得无辜。

  再按一次，一切回来。
  就像什么都没有发生过。


第三章  护眼模式

  这张纸是暖黄色的，像旧书，也像下午四点的阳光。
  字大一点，眼睛就舒服一点。

  把一本 txt 拖进来，它就会安安静静地躺在左边的书架上。
  想看的时候，点一下。

—— 祝你今天准时下班。
""",
        encoding="utf-8",
    )
    settings.pinned_books = [
        {"id": "book-demo", "name": "摸鱼指南", "path": str(sample)}
    ]

    window = MainWindow(settings, headless=True)
    window.resize(1440, 900)
    window.show()
    wait(1600)
    grab(window, "preview-main.png")

    window.resize(1000, 700)
    wait(700)
    grab(window, "preview-small.png")
    window.resize(1440, 900)
    wait(300)

    settings.disguise.preset = "excel"
    window.apply_settings(settings)
    wait(700)
    grab(window, "preview-disguise-excel.png")
    settings.disguise.preset = "default"
    window.apply_settings(settings)
    wait(300)

    window.open_book("book-demo")
    wait(600)
    grab(window, "preview-reader.png")
    window._set_reader_theme("dark")
    wait(400)
    grab(window, "preview-reader-dark.png")
    window._set_reader_theme("yellow")
    window._back_from_reader()
    wait(300)

    dialog = SettingsDialog(
        settings,
        None,
        hotkey_available=True,
        hotkey_message="",
    )
    dialog.resize(800, 700)
    dialog.show()
    wait(400)
    grab(dialog, "preview-settings.png")

    for index, name in (
        (1, "preview-settings-stealth.png"),
        (3, "preview-settings-disguise.png"),
        (4, "preview-settings-apps.png"),
    ):
        dialog._tabs.setCurrentIndex(index)
        wait(250)
        grab(dialog, name)
    dialog.close()

    code_view = decoy.DecoyWindow("code")
    code_view.setGeometry(60, 40, 1280, 800)
    code_view.show()
    wait(1300)
    grab(code_view, "preview-decoy-code.png")
    code_view.close()

    excel_view = decoy.DecoyWindow("excel")
    excel_view.setGeometry(60, 40, 1280, 800)
    excel_view.show()
    wait(600)
    grab(excel_view, "preview-decoy-excel.png")
    excel_view.close()

    window.quit_app()
    wait(200)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
