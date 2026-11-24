"""内嵌浏览器（QtWebEngine）。

用独立的持久化 Profile（Cookie / 登录状态都存在 data/webengine 里），
伪装成桌面 Chrome，顺手处理全屏视频、弹窗、下载和静音。

如果当前环境没有 QtWebEngine（或设置了 SLACKOFF_NO_WEB=1），
会退化成一个「用系统浏览器打开」的占位页，程序照常能跑。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QVBoxLayout, QWidget

from . import paths
from .urls import normalize_input

log = logging.getLogger(__name__)

CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_3 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.3 Mobile/15E148 Safari/604.1"
)

WEBENGINE_AVAILABLE = False
WEBENGINE_ERROR = ""

if not os.environ.get("SLACKOFF_NO_WEB"):
    try:
        from PySide6.QtWebEngineCore import (  # noqa: E402
            QWebEnginePage,
            QWebEngineProfile,
            QWebEngineSettings,
        )
        from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: E402

        WEBENGINE_AVAILABLE = True
    except Exception as exc:  # pragma: no cover - 取决于安装环境
        WEBENGINE_ERROR = str(exc)
        log.warning("QtWebEngine 不可用：%s", exc)
else:
    WEBENGINE_ERROR = "已通过 SLACKOFF_NO_WEB 禁用内嵌浏览器"


if WEBENGINE_AVAILABLE:

    class SlackPage(QWebEnginePage):
        """把弹窗留在同一个视图里，并统一拒绝权限申请。"""

        def createWindow(self, _window_type):  # noqa: N802 - Qt 命名
            return self

        def javaScriptConsoleMessage(self, level, message, line, source):  # noqa: N802
            log.debug("JS[%s] %s:%s %s", level, source, line, message)

        def certificateError(self, error) -> bool:  # noqa: N802
            log.info("证书错误：%s", error.description())
            return False

    class BrowserView(QWebEngineView):
        loadFailed = Signal(str)
        pageTitleChanged = Signal(str)
        fullScreenToggled = Signal(bool)
        downloadStarted = Signal(str)

        def __init__(self, settings, parent: QWidget | None = None) -> None:
            super().__init__(parent)
            self._settings = settings
            self._muted_by_us = False

            cache_dir = paths.webengine_dir()
            # Profile 挂在 QApplication 上，保证它比窗口 / 页面活得久，
            # 否则退出时会报「Release of profile requested but page not deleted」。
            owner = QApplication.instance() or self
            profile = QWebEngineProfile("slackoff", owner)
            profile.setPersistentStoragePath(str(cache_dir / "storage"))
            profile.setCachePath(str(cache_dir / "cache"))
            profile.setPersistentCookiesPolicy(
                QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies
            )
            profile.setHttpAcceptLanguage("zh-CN,zh;q=0.9,en;q=0.8")
            profile.setSpellCheckEnabled(False)
            profile.downloadRequested.connect(self._on_download)
            self._profile = profile

            page = SlackPage(profile, self)
            self.setPage(page)
            self.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)
            page.setBackgroundColor(QColor("#0F1115"))

            engine_settings = page.settings()
            engine_settings.setAttribute(
                QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True
            )
            engine_settings.setAttribute(
                QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, True
            )
            engine_settings.setAttribute(
                QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, True
            )
            engine_settings.setAttribute(
                QWebEngineSettings.WebAttribute.ErrorPageEnabled, True
            )
            page.fullScreenRequested.connect(self._on_fullscreen)
            page.featurePermissionRequested.connect(
                lambda _origin, _feature: page.setFeaturePermission(
                    _origin, _feature, QWebEnginePage.PermissionPolicy.Deny
                )
            )

            page.titleChanged.connect(self._on_title)
            page.linkHovered.connect(self._on_hover)
            self.loadFinished.connect(self._on_load_finished)

            self.apply_settings(settings)
            self._fullscreen = False

        # -------------------------------------------------------------- 设置
        def apply_settings(self, settings) -> None:
            self._settings = settings
            mode = settings.browser.ua_mode
            if mode == "mobile":
                ua = MOBILE_UA
            elif mode == "default":
                ua = QWebEngineProfile.defaultProfile().httpUserAgent()
            else:
                ua = CHROME_UA
            self._profile.setHttpUserAgent(ua)
            self.setZoomFactor(max(0.5, min(2.5, settings.browser.zoom)))
            self.set_muted(settings.browser.mute_on_start)

        @property
        def current_url(self) -> str:
            return self.url().toString()

        @property
        def profile(self) -> QWebEngineProfile:
            return self._profile

        # -------------------------------------------------------------- 导航
        def go(self, text: str) -> bool:
            target = normalize_input(text, self._settings.browser.search_engine)
            if not target:
                return False
            self.setUrl(QUrl(target))
            return True

        def go_url(self, url: str) -> None:
            self.setUrl(QUrl(url))

        def reload_page(self) -> None:
            self.reload()

        # -------------------------------------------------------------- 声音
        def set_muted(self, muted: bool) -> None:
            try:
                self.page().setAudioMuted(bool(muted))
            except Exception:
                pass

        def is_muted(self) -> bool:
            try:
                return bool(self.page().isAudioMuted())
            except Exception:
                return False

        def pause_media(self) -> None:
            js = (
                "(function(){var n=0;document.querySelectorAll('video,audio').forEach(function(m){"
                "try{if(!m.paused){m.pause();n++;}}catch(e){}});return n;})()"
            )
            try:
                self.page().runJavaScript(js, lambda count: log.debug("暂停了 %s 个媒体元素", count))
            except Exception:
                pass

        def exit_html_fullscreen(self) -> None:
            if self._fullscreen:
                self._fullscreen = False
                self.fullScreenToggled.emit(False)

        # -------------------------------------------------------------- 事件
        def _on_title(self, title: str) -> None:
            self.pageTitleChanged.emit(title or "")

        def _on_hover(self, link: str) -> None:
            if link:
                self.setToolTip(link[:180])
            else:
                self.setToolTip("")

        def _on_load_finished(self, ok: bool) -> None:
            if ok:
                return
            current = self.current_url
            if not current or current.startswith("about:"):
                return
            self.loadFailed.emit(current)

        def _on_fullscreen(self, request) -> None:
            request.accept()
            self._fullscreen = bool(request.toggleOn())
            self.fullScreenToggled.emit(self._fullscreen)

        def _on_download(self, download) -> None:
            try:
                target_dir = self._settings.browser.download_dir.strip()
                directory = Path(target_dir) if target_dir else paths.user_downloads_dir()
                directory.mkdir(parents=True, exist_ok=True)
                download.setDownloadDirectory(str(directory))
                download.accept()
                suggested = download.downloadFileName()
                self.downloadStarted.emit(str(directory / suggested))
                log.info("开始下载：%s", directory / suggested)
            except Exception as exc:
                log.warning("下载失败：%s", exc)


class FallbackBrowser(QWidget):
    """没有 WebEngine 时的兜底：提示 + 调系统浏览器。"""

    def __init__(self, settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(12)

        title = QLabel("内嵌浏览器无法启动")
        title.setObjectName("h1")
        hint = QLabel(
            "当前环境缺少 QtWebEngine。\n"
            f"原因：{WEBENGINE_ERROR or '未知'}\n\n"
            "可以执行  pip install PySide6  重新安装完整版本，\n"
            "也可以直接用系统浏览器打开视频网站。"
        )
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        open_btn = QPushButton("用系统浏览器打开爱奇艺")
        open_btn.setObjectName("primary")
        open_btn.setFixedWidth(240)
        open_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://www.iqiyi.com/"))
        )
        layout.addStretch(1)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addWidget(open_btn)
        layout.addStretch(2)

    def apply_settings(self, _settings) -> None:
        return

    def set_muted(self, _muted: bool) -> None:
        return

    def pause_media(self) -> None:
        return
