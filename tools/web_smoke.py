"""离屏测一下 QtWebEngine 能不能真的渲染网页（没有显示器也能跑）。

    python tools/web_smoke.py
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
os.environ["SLACKOFF_HOME"] = str(ROOT / "data" / "webtest")

from PySide6.QtCore import QEventLoop, QTimer, QUrl  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from slackoff import browser  # noqa: E402
from slackoff.config import Settings  # noqa: E402
from slackoff.ui import theme  # noqa: E402


def wait(ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def main() -> int:
    print("WEBENGINE_AVAILABLE:", browser.WEBENGINE_AVAILABLE, browser.WEBENGINE_ERROR)
    if not browser.WEBENGINE_AVAILABLE:
        return 1

    app = QApplication(sys.argv[:1])
    theme.apply_theme(app)

    settings = Settings()
    view = browser.BrowserView(settings)
    view.resize(1000, 620)
    view.show()

    html = (
        "<html><body style='background:#0d1016;color:#5eead4;font-family:sans-serif;"
        "padding:40px'><h1>SlackOff WebEngine 正常</h1>"
        "<p style='color:#e9eff7'>如果你看到这行字，说明内嵌浏览器可以工作。</p></body></html>"
    )
    view.setHtml(html, QUrl("https://example.invalid/"))
    wait(2500)

    print("title:", view.page().title())
    result = {}
    view.page().runJavaScript("document.body.innerText", lambda text: result.setdefault("text", text))
    wait(500)
    print("innerText:", result.get("text"))

    docs = ROOT / "docs"
    docs.mkdir(exist_ok=True)
    view.grab().save(str(docs / "webengine-smoke.png"))
    print("saved", docs / "webengine-smoke.png")

    view.stop()
    view.deleteLater()
    wait(300)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
