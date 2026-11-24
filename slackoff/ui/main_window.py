"""主窗口：侧栏、地址栏、内嵌浏览器、老板键与隐身模式的调度中心。"""

from __future__ import annotations

import copy
import logging
import os
from pathlib import Path

from PySide6.QtCore import QEvent, QRect, Qt, QTimer, QUrl
from PySide6.QtGui import QCloseEvent, QDesktopServices, QFont, QKeySequence, QShortcut, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QSystemTrayIcon,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .. import (
    __app_name__,
    apps,
    audio,
    books,
    browser,
    catalog,
    decoy,
    disguise,
    edge_web,
    embed,
    hotkeys,
    paths,
    stealth,
    urls,
    winapi,
)
from ..config import Settings
from . import dashboard, theme, widgets
from .settings_dialog import SettingsDialog

log = logging.getLogger(__name__)


def _tool_button(glyph: str, tip: str, slot) -> QToolButton:
    button = QToolButton()
    button.setText(glyph)
    button.setToolTip(tip)
    button.setFixedSize(34, 34)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.clicked.connect(slot)
    return button


class MainWindow(QMainWindow):
    def __init__(
        self,
        settings: Settings,
        headless: bool = False,
        start_hidden: bool = False,
    ) -> None:
        super().__init__()
        self.settings = settings
        self.headless = bool(headless or os.environ.get("SLACKOFF_HEADLESS"))
        self._brand = disguise.get(settings.disguise.preset)

        self._hidden_reason: str | None = None
        self._saved_geometry: QRect | None = None
        self._was_maximized = False
        self._was_fullscreen = False
        self._web_muted_before = False
        self._saved_audio: list = []
        self._hidden_external: list[int] = []
        self._decoy: decoy.DecoyWindow | None = None
        self._quitting = False
        self._asking_close = False
        self._theater = False
        self._theater_prev_max = False
        self._local_shortcuts: list[QShortcut] = []
        self._tray_tip_shown = False
        self._flash_token = 0
        self._start_hidden = start_hidden
        self._edge_site: edge_web.EdgeSiteWindow | None = None
        self._edge_site_active = False
        self._edge_route_pending = False
        self._edge_sync_timer = QTimer(self)
        self._edge_sync_timer.setSingleShot(True)
        self._edge_sync_timer.setInterval(60)
        self._edge_sync_timer.timeout.connect(self._sync_edge_overlay)

        self.audio = None if self.headless else audio.AudioMuter()

        self.setWindowTitle(self._brand.base_title)
        self.setWindowIcon(theme.disguise_icon(self._brand.id))
        self.setMinimumSize(980, 620)
        self.resize(1320, 860)

        # 给 RegisterHotKey 用的隐藏宿主窗口；不随主窗口的 flags 变化而重建句柄
        self._hotkey_host = QWidget(self)
        self._hotkey_host.setWindowFlags(
            Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
        )
        self._hotkey_host.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        self._hotkey_host.resize(1, 1)

        self._build_ui()
        self.setAcceptDrops(True)
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        self._setup_hotkeys()
        self._setup_tray()
        self._setup_stealth()
        self._install_global_ui_shortcuts()
        self._restore_window_state()

        self._apply_window_prefs()
        self._sync_stealth_switch()
        self._update_hints()
        self._populate_sidebar()
        self._apply_disguise()
        self._set_status("就绪 · 把视频软件的 exe 拖进窗口即可添加")

        if self._start_hidden:
            QTimer.singleShot(300, self.hide_everything)

    # ================================================================== 界面
    def _build_ui(self) -> None:
        central = QWidget()
        outer = QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._sidebar = self._build_sidebar()
        outer.addWidget(self._sidebar)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        self._topbar = self._build_topbar()
        right.addWidget(self._topbar)
        right.addWidget(self._build_content(), 1)
        self._statusbar = self._build_statusbar()
        right.addWidget(self._statusbar)
        outer.addLayout(right, 1)

        self.setCentralWidget(central)

    # ------------------------------------------------------------------ 侧栏
    def _build_sidebar(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("sidebar")
        frame.setFixedWidth(248)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 16, 12, 14)
        layout.setSpacing(12)

        brand = QHBoxLayout()
        brand.setSpacing(10)
        self._brand_logo = QLabel()
        self._brand_logo.setFixedSize(36, 36)
        self._brand_logo.setPixmap(
            theme.disguise_pixmap(self._brand.id, 144).scaled(
                36, 36, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
        )
        brand.addWidget(self._brand_logo)
        brand_text = QVBoxLayout()
        brand_text.setSpacing(0)
        self._brand_name = QLabel(self._brand.short)
        self._brand_name.setStyleSheet("font-size:15px; font-weight:700; background:transparent;")
        self._brand_sub = QLabel(self._brand.subtitle)
        self._brand_sub.setObjectName("dim")
        brand_text.addWidget(self._brand_name)
        brand_text.addWidget(self._brand_sub)
        brand.addLayout(brand_text)
        brand.addStretch(1)
        layout.addLayout(brand)
        layout.addWidget(widgets.divider())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 2, 0, 2)
        body_layout.setSpacing(2)

        self._apps_header = widgets.SectionHeader("我的应用")
        body_layout.addWidget(self._apps_header)
        self._apps_box = QVBoxLayout()
        self._apps_box.setSpacing(4)
        self._apps_box.setContentsMargins(0, 0, 0, 0)
        body_layout.addLayout(self._apps_box)

        self._apps_empty = QFrame()
        self._apps_empty.setObjectName("dropZone")
        empty_layout = QVBoxLayout(self._apps_empty)
        empty_layout.setContentsMargins(12, 14, 12, 12)
        empty_layout.setSpacing(4)
        drop_glyph = QLabel("＋")
        drop_glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_glyph.setStyleSheet(f"color:{theme.ACCENT}; font-size:22px; background:transparent;")
        drop_title = QLabel("把 exe 拖到这里")
        drop_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_title.setStyleSheet("font-size:12.5px; font-weight:600; background:transparent;")
        drop_hint = QLabel("松手即加入，点一下才打开")
        drop_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_hint.setWordWrap(True)
        drop_hint.setStyleSheet(f"color:{theme.TEXT_DIM}; font-size:10.5px; background:transparent;")
        pick = QPushButton("选择 exe…")
        pick.setObjectName("ghost")
        pick.setFixedHeight(28)
        pick.setCursor(Qt.CursorShape.PointingHandCursor)
        pick.clicked.connect(self.choose_app_file)
        empty_layout.addWidget(drop_glyph)
        empty_layout.addWidget(drop_title)
        empty_layout.addWidget(drop_hint)
        empty_layout.addSpacing(4)
        empty_layout.addWidget(pick)
        body_layout.addWidget(self._apps_empty)

        self._add_app_button = QPushButton("＋ 添加应用")
        self._add_app_button.setObjectName("ghost")
        self._add_app_button.setFixedHeight(30)
        self._add_app_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_app_button.clicked.connect(self.choose_app_file)
        body_layout.addWidget(self._add_app_button)

        body_layout.addSpacing(10)
        self._books_header = widgets.SectionHeader("我的书")
        body_layout.addWidget(self._books_header)
        self._books_box = QVBoxLayout()
        self._books_box.setSpacing(2)
        self._books_box.setContentsMargins(0, 0, 0, 0)
        body_layout.addLayout(self._books_box)

        self._books_empty = QLabel("把 .txt 电子书拖进来")
        self._books_empty.setObjectName("dim")
        self._books_empty.setWordWrap(True)
        self._books_empty.setContentsMargins(6, 2, 6, 2)
        body_layout.addWidget(self._books_empty)

        self._add_book_button = QPushButton("＋ 添加 txt")
        self._add_book_button.setObjectName("ghost")
        self._add_book_button.setFixedHeight(30)
        self._add_book_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_book_button.clicked.connect(self.choose_book_file)
        body_layout.addWidget(self._add_book_button)

        body_layout.addSpacing(10)
        self._sites_header = widgets.SectionHeader("常用网站")
        body_layout.addWidget(self._sites_header)
        self._sites_box = QVBoxLayout()
        self._sites_box.setSpacing(2)
        self._sites_box.setContentsMargins(0, 0, 0, 0)
        body_layout.addLayout(self._sites_box)
        body_layout.addStretch(1)
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)

        boss_card = QFrame()
        boss_card.setObjectName("tip")
        boss_layout = QVBoxLayout(boss_card)
        boss_layout.setContentsMargins(12, 10, 12, 12)
        boss_layout.setSpacing(4)
        caption = QLabel("老板键")
        caption.setObjectName("dim")
        self._boss_key_label = QLabel(hotkeys.format_hotkey(self.settings.boss_key))
        self._boss_key_label.setStyleSheet(
            f"font-size:14px; font-weight:700; color:{theme.ACCENT}; background:transparent;"
        )
        self._boss_button = QPushButton("立即隐身")
        self._boss_button.setObjectName("primary")
        self._boss_button.setFixedHeight(32)
        self._boss_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._boss_button.clicked.connect(self.toggle_boss)
        boss_layout.addWidget(caption)
        boss_layout.addWidget(self._boss_key_label)
        boss_layout.addSpacing(4)
        boss_layout.addWidget(self._boss_button)
        layout.addWidget(boss_card)
        return frame

    # ------------------------------------------------------------------ 顶栏
    def _build_topbar(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("topbar")
        frame.setFixedHeight(60)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 12, 16, 12)
        layout.setSpacing(4)

        self._btn_back = _tool_button("←", "后退", self._go_back)
        self._btn_forward = _tool_button("→", "前进", self._go_forward)
        self._btn_reload = _tool_button("⟳", "刷新", self._reload)
        self._btn_home = _tool_button("⌂", "回到首页", self.go_home)
        for button in (self._btn_back, self._btn_forward, self._btn_reload, self._btn_home):
            layout.addWidget(button)
        self._btn_edge = _tool_button(
            "E", "用系统 Edge 内核打开当前网页（视频网站）", self._open_current_in_edge
        )
        self._btn_edge.setVisible(edge_web.available())
        layout.addWidget(self._btn_edge)

        layout.addSpacing(6)
        self._address = QLineEdit()
        self._address.setPlaceholderText("搜索或输入网址，回车打开")
        self._address.setClearButtonEnabled(True)
        self._address.setFixedHeight(36)
        self._address.returnPressed.connect(self._navigate_from_address)
        layout.addWidget(self._address, 1)
        layout.addSpacing(8)

        self._stealth_label = QLabel("隐身")
        self._stealth_label.setObjectName("muted")
        self._stealth_label.setToolTip("鼠标移出窗口自动隐藏；关闭后只能手动隐藏")
        layout.addWidget(self._stealth_label)
        self._stealth_switch = widgets.Switch()
        self._stealth_switch.setToolTip("隐身模式：鼠标移出窗口后自动隐藏")
        self._stealth_switch.toggled.connect(self._on_stealth_switch)
        layout.addWidget(self._stealth_switch)
        layout.addSpacing(4)

        self._btn_settings = _tool_button("⚙", "设置", self.open_settings)
        self._btn_settings.setFixedSize(38, 34)
        layout.addWidget(self._btn_settings)
        return frame

    # ------------------------------------------------------------------ 内容
    def _build_content(self) -> QWidget:
        self._stack = QStackedWidget()

        self._dashboard = dashboard.Dashboard(self.settings)
        self._dashboard.openSite.connect(self.open_site)
        self._dashboard.openSettings.connect(self.open_settings)
        self._dashboard.dismissFirstRun.connect(self.settings.save)
        self._stack.addWidget(self._dashboard)

        if browser.WEBENGINE_AVAILABLE:
            self._browser = browser.BrowserView(self.settings)
            self._browser.urlChanged.connect(self._on_url_changed)
            self._browser.pageTitleChanged.connect(self._on_page_title)
            self._browser.fullScreenToggled.connect(self._on_fullscreen_toggled)
            self._browser.loadFailed.connect(self._on_load_failed)
            self._browser.downloadStarted.connect(self._on_download)
        else:
            self._browser = browser.FallbackBrowser(self.settings)
        self._stack.addWidget(self._browser)

        self._app_page = self._build_app_page()
        self._stack.addWidget(self._app_page)

        self._reader_page = self._build_reader_page()
        self._stack.addWidget(self._reader_page)

        self._error_page = self._build_error_page()
        self._stack.addWidget(self._error_page)
        self._stack.setCurrentIndex(0)
        self._stack.currentChanged.connect(self._on_stack_changed)
        return self._stack

    def _build_app_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        bar = QFrame()
        bar.setObjectName("topbar")
        bar.setFixedHeight(46)
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(12, 6, 12, 6)
        bar_layout.setSpacing(8)

        back = QPushButton("← 返回首页")
        back.setObjectName("ghost")
        back.setFixedHeight(30)
        back.setCursor(Qt.CursorShape.PointingHandCursor)
        back.clicked.connect(self._back_from_app)

        self._app_title = QLabel("应用")
        self._app_title.setStyleSheet("font-size:13px; font-weight:600; background:transparent;")
        self._app_detach = QPushButton("独立窗口")
        self._app_detach.setObjectName("ghost")
        self._app_detach.setFixedHeight(30)
        self._app_detach.setCursor(Qt.CursorShape.PointingHandCursor)
        self._app_detach.setToolTip("如果嵌入后黑屏 / 没有声音，点这里把它放回独立窗口")
        self._app_detach.clicked.connect(self._detach_embedded)

        bar_layout.addWidget(back)
        bar_layout.addWidget(self._app_title)
        bar_layout.addStretch(1)
        bar_layout.addWidget(self._app_detach)
        layout.addWidget(bar)

        self._app_notice = QFrame()
        self._app_notice.setStyleSheet(
            "QFrame { background:#2B2413; border-bottom:1px solid #4A3D1B; }"
        )
        notice_layout = QHBoxLayout(self._app_notice)
        notice_layout.setContentsMargins(12, 7, 12, 7)
        notice_layout.setSpacing(8)
        self._app_notice_text = QLabel("")
        self._app_notice_text.setStyleSheet(
            f"color:{theme.TEXT}; font-size:12px; background:transparent;"
        )
        self._app_notice_text.setWordWrap(True)
        notice_layout.addWidget(self._app_notice_text, 1)
        self._app_notice_web = QPushButton("在浏览器打开")
        self._app_notice_web.setObjectName("ghost")
        self._app_notice_web.setFixedHeight(26)
        self._app_notice_web.setCursor(Qt.CursorShape.PointingHandCursor)
        self._app_notice_web.clicked.connect(self._open_web_version)
        notice_layout.addWidget(self._app_notice_web)
        notice_detach = QPushButton("独立窗口")
        notice_detach.setObjectName("ghost")
        notice_detach.setFixedHeight(26)
        notice_detach.setCursor(Qt.CursorShape.PointingHandCursor)
        notice_detach.clicked.connect(self._detach_embedded)
        notice_layout.addWidget(notice_detach)
        self._app_notice.setVisible(False)
        layout.addWidget(self._app_notice)

        self._app_container = embed.EmbedContainer()
        container_layout = QVBoxLayout(self._app_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._app_placeholder = QLabel("正在启动…")
        self._app_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._app_placeholder.setWordWrap(True)
        self._app_placeholder.setStyleSheet(
            f"color:{theme.TEXT_MUTED}; font-size:13px; background:transparent;"
        )
        container_layout.addWidget(self._app_placeholder)
        layout.addWidget(self._app_container, 1)

        self._embedder = embed.WindowEmbedder(self._app_container, self)
        self._embedder.ready.connect(self._on_embedded)
        self._embedder.extraEmbedded.connect(self._on_extra_embedded)
        self._embedder.extraBlocked.connect(self._on_extra_blocked)
        self._embedder.failed.connect(self._on_embed_failed)
        self._embedder.closed.connect(self._on_embedded_closed)
        self._app_container.resized.connect(self._embedder.resize)
        self._app_detach.setVisible(False)
        return page

    def _build_reader_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        bar = QFrame()
        bar.setObjectName("topbar")
        bar.setFixedHeight(46)
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(12, 6, 12, 6)
        bar_layout.setSpacing(8)

        back = QPushButton("← 返回首页")
        back.setObjectName("ghost")
        back.setFixedHeight(30)
        back.setCursor(Qt.CursorShape.PointingHandCursor)
        back.clicked.connect(self._back_from_reader)

        self._reader_title = QLabel("电子书")
        self._reader_title.setStyleSheet("font-size:13px; font-weight:600; background:transparent;")

        self._reader_yellow = QToolButton()
        self._reader_yellow.setText("护眼黄")
        self._reader_yellow.setCheckable(True)
        self._reader_yellow.setFixedHeight(28)
        self._reader_yellow.setMinimumWidth(58)
        self._reader_yellow.setCursor(Qt.CursorShape.PointingHandCursor)
        self._reader_yellow.setToolTip("暖黄色护眼背景")
        self._reader_yellow.clicked.connect(lambda: self._set_reader_theme("yellow"))

        self._reader_dark = QToolButton()
        self._reader_dark.setText("暗色")
        self._reader_dark.setCheckable(True)
        self._reader_dark.setFixedHeight(28)
        self._reader_dark.setMinimumWidth(48)
        self._reader_dark.setCursor(Qt.CursorShape.PointingHandCursor)
        self._reader_dark.setToolTip("和摸鱼神器一致的黑色背景")
        self._reader_dark.clicked.connect(lambda: self._set_reader_theme("dark"))

        theme_group = QButtonGroup(self)
        theme_group.setExclusive(True)
        theme_group.addButton(self._reader_yellow)
        theme_group.addButton(self._reader_dark)

        minus = QToolButton()
        minus.setText("A−")
        minus.setToolTip("缩小字号")
        minus.setFixedSize(34, 30)
        minus.setCursor(Qt.CursorShape.PointingHandCursor)
        minus.clicked.connect(lambda: self._reader_zoom(-1))

        plus = QToolButton()
        plus.setText("A+")
        plus.setToolTip("放大字号")
        plus.setFixedSize(34, 30)
        plus.setCursor(Qt.CursorShape.PointingHandCursor)
        plus.clicked.connect(lambda: self._reader_zoom(1))

        bar_layout.addWidget(back)
        bar_layout.addWidget(self._reader_title)
        bar_layout.addStretch(1)
        bar_layout.addWidget(self._reader_yellow)
        bar_layout.addWidget(self._reader_dark)
        bar_layout.addSpacing(4)
        bar_layout.addWidget(minus)
        bar_layout.addWidget(plus)
        layout.addWidget(bar)

        self._reader_font_size = 17
        self._reader_theme = self.settings.reader.theme
        self._reader_editor = QPlainTextEdit()
        self._reader_editor.setReadOnly(True)
        self._reader_editor.setFrameShape(QFrame.Shape.NoFrame)
        self._reader_editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self._apply_reader_font()
        self._apply_reader_theme()
        layout.addWidget(self._reader_editor, 1)
        return page

    def _set_reader_theme(self, name: str) -> None:
        name = "dark" if name == "dark" else "yellow"
        self._reader_theme = name
        self.settings.reader.theme = name
        self.settings.save()
        self._apply_reader_theme()
        self._flash("阅读背景：暗色" if name == "dark" else "阅读背景：护眼黄", 2500)

    def _apply_reader_theme(self) -> None:
        if self._reader_theme == "dark":
            background, foreground = theme.BG, theme.TEXT
            selection, selection_text = "#2C4A5A", "#FFFFFF"
        else:
            background, foreground = "#F6E7B8", "#3B3222"
            selection, selection_text = "#E2C271", "#2B2418"
        self._reader_editor.setStyleSheet(
            "QPlainTextEdit {"
            f" background: {background};"
            f" color: {foreground};"
            " border: none;"
            " padding: 18px 26px;"
            f" selection-background-color: {selection};"
            f" selection-color: {selection_text};"
            "}"
        )
        self._reader_yellow.setChecked(self._reader_theme != "dark")
        self._reader_dark.setChecked(self._reader_theme == "dark")

    def _apply_reader_font(self) -> None:
        font = QFont("Microsoft YaHei UI")
        font.setPixelSize(self._reader_font_size)
        self._reader_editor.setFont(font)
        self._reader_editor.document().setDefaultFont(font)

    def _reader_zoom(self, delta: int) -> None:
        self._reader_font_size = max(13, min(30, self._reader_font_size + delta))
        self._apply_reader_font()

    def _build_error_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(60, 40, 60, 40)
        layout.setSpacing(10)
        layout.addStretch(1)

        glyph = QLabel("⚠")
        glyph.setStyleSheet(f"font-size:38px; color:{theme.WARN}; background:transparent;")
        glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title = QLabel("这个页面没有打开")
        title.setObjectName("h2")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._error_url = QLabel("")
        self._error_url.setObjectName("muted")
        self._error_url.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._error_url.setWordWrap(True)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        retry = QPushButton("重试")
        retry.setObjectName("primary")
        retry.setCursor(Qt.CursorShape.PointingHandCursor)
        retry.clicked.connect(self._retry_page)
        home = QPushButton("回首页")
        home.setObjectName("ghost")
        home.setCursor(Qt.CursorShape.PointingHandCursor)
        home.clicked.connect(self.go_home)
        buttons.addWidget(retry)
        buttons.addWidget(home)
        buttons.addStretch(1)

        hint = QLabel("如果是网络问题，检查一下代理或防火墙；也可能是站点拦截了内嵌浏览器。")
        hint.setObjectName("dim")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)

        layout.addWidget(glyph)
        layout.addWidget(title)
        layout.addWidget(self._error_url)
        layout.addSpacing(8)
        layout.addLayout(buttons)
        layout.addWidget(hint)
        layout.addStretch(2)
        return page

    # ------------------------------------------------------------------ 状态栏
    def _build_statusbar(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("statusbar")
        frame.setFixedHeight(28)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(8)
        self._status_label = QLabel("就绪")
        self._status_label.setObjectName("dim")
        self._hint_label = QLabel("")
        self._hint_label.setObjectName("dim")
        layout.addWidget(self._status_label, 1)
        layout.addWidget(self._hint_label)
        return frame

    # ================================================================== 侧栏数据
    @staticmethod
    def _clear_layout(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            elif item.layout() is not None:
                MainWindow._clear_layout(item.layout())

    def _populate_sidebar(self) -> None:
        self._clear_layout(self._apps_box)
        self._clear_layout(self._books_box)
        self._clear_layout(self._sites_box)

        pinned = apps.load_apps(self.settings)
        for app in pinned:
            row = widgets.AppRow(app)
            row.clicked.connect(lambda app_id=app.id: self.open_app(app_id))
            row.removeRequested.connect(self.remove_app)
            self._apps_box.addWidget(row)
        self._apps_empty.setVisible(not pinned)
        self._add_app_button.setVisible(bool(pinned))
        self._apps_header.set_count(f"{len(pinned)} 个")
        self._dashboard.set_app_count(len(pinned))

        pinned_books = books.load_books(self.settings)
        for book in pinned_books:
            row = widgets.BookRow(book)
            row.clicked.connect(lambda book_id=book.id: self.open_book(book_id))
            row.removeRequested.connect(self.remove_book)
            self._books_box.addWidget(row)
        self._books_empty.setVisible(not pinned_books)
        self._books_header.set_count(f"{len(pinned_books)} 本")

        sites = catalog.custom_sites(self.settings) + list(catalog.SITES)
        shown = sites[:6]
        for site in shown:
            row = widgets.SiteRow(site)
            row.clicked.connect(lambda url=site.url: self.open_site(url))
            self._sites_box.addWidget(row)
        self._sites_header.set_count(f"{len(shown)}/{len(sites)} · 全部在首页")

    # ================================================================== 我的应用
    def open_app(self, app_id: str) -> None:
        app = apps.find_app(self.settings, app_id)
        if app is None:
            return
        if self._edge_site_active:
            self._close_edge_site()
        if self.settings.apps.embed and not self.headless:
            self._open_embedded(app)
            return
        ok, message = apps.launch(app)
        self._flash(message, 5000)
        if ok:
            self._set_status(f"已启动 {app.name} · {app.exe}")

    def _open_embedded(self, app) -> None:
        current = self._embedder.current
        if current is not None and current.app.id == app.id:
            self._stack.setCurrentWidget(self._app_page)
            self._set_app_mode(True)
            return
        self._app_title.setText(app.name)
        self._app_placeholder.setText(f"正在启动 {app.name}…")
        self._app_placeholder.show()
        self._app_notice.setVisible(False)
        self._app_detach.setVisible(False)
        self._set_app_mode(True)
        self._stack.setCurrentWidget(self._app_page)
        self._set_status(f"正在把 {app.name} 嵌入摸鱼神器…")
        if not self._embedder.start(app):
            self._on_embed_failed(f"无法启动 {app.name}")

    def _set_app_mode(self, on: bool) -> None:
        """嵌入应用时把网页地址栏收起来，给应用更多空间。"""
        self._topbar.setVisible(not on)

    def _apply_disguise(self) -> None:
        """把左上角、窗口图标、托盘和标题换成伪装身份。"""
        self._brand = disguise.get(self.settings.disguise.preset)
        icon = theme.disguise_icon(self._brand.id)
        self.setWindowIcon(icon)
        if self.tray is not None:
            self.tray.setIcon(icon)
            self.tray.setToolTip(self._brand.name)
            self._update_tray()
        self._brand_logo.setPixmap(
            theme.disguise_pixmap(self._brand.id, 144).scaled(
                36, 36, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
        )
        self._brand_name.setText(self._brand.short)
        self._brand_sub.setText(self._brand.subtitle)
        if self._stack.currentWidget() is self._dashboard:
            self.setWindowTitle(self._brand.base_title)
        self._dashboard.apply_brand(self._brand)

    def _on_embedded(self, info) -> None:
        self._app_title.setText(info.app.name)
        self._app_placeholder.hide()
        self._app_detach.setVisible(True)
        self._app_notice.setVisible(False)
        self._embedder.resize()
        self._flash(f"{info.app.name} 已在摸鱼神器内打开", 4000)

    def _on_extra_embedded(self, info) -> None:
        self._app_title.setText(info.app.name)
        self._flash(f"{info.app.name} 的播放窗口已内嵌", 3500)

    def _on_extra_blocked(self, title: str) -> None:
        app_name = self._app_title.text()
        self._app_notice_text.setText(
            f"{app_name} 把播放画面放在独立的视频窗口里，没法完整内嵌。"
            "可以点「独立窗口」正常播放，或用浏览器打开网页版。"
        )
        self._app_notice_web.setVisible("腾讯视频" in app_name or "腾讯视频" in title)
        self._app_notice.setVisible(True)

    def _open_web_version(self) -> None:
        self._app_notice.setVisible(False)
        QDesktopServices.openUrl(QUrl("https://v.qq.com"))
        self._flash("已用浏览器打开腾讯视频网页版", 4000)

    def _on_embed_failed(self, message: str) -> None:
        self._app_notice.setVisible(False)
        self._app_placeholder.setText(
            message + "\n\n可以返回首页；或在「设置 → 应用」里关闭嵌入，改为独立窗口。"
        )
        self._app_placeholder.show()
        self._app_detach.setVisible(False)
        self._flash(message, 6000)

    def _on_embedded_closed(self) -> None:
        self._app_title.setText("应用")
        self._app_notice.setVisible(False)
        self._app_placeholder.setText("应用已退出。\n回到左侧点一下可以重新打开。")
        self._app_placeholder.show()
        self._app_detach.setVisible(False)
        self._flash("嵌入的应用已退出", 4000)

    def _back_from_app(self) -> None:
        if self._edge_site_active:
            self._close_edge_site()
            self._app_title.setText("应用")
            self._app_placeholder.setText("正在启动…")
            self._app_placeholder.show()
            self._app_detach.setVisible(False)
            self._flash("系统内核网页已关闭", 3500)
        self._app_notice.setVisible(False)
        self._set_app_mode(False)
        self._stack.setCurrentWidget(self._dashboard)

    def _detach_embedded(self) -> None:
        if self._edge_site_active:
            self._detach_edge_site()
            return
        current = self._embedder.current
        self._embedder.detach()
        self._app_notice.setVisible(False)
        self._set_app_mode(False)
        self._stack.setCurrentWidget(self._dashboard)
        if current is not None:
            self._flash(f"{current.app.name} 已放到独立窗口", 4000)

    # ================================================================== 系统内核网页
    def _should_use_edge(self, url: str) -> bool:
        return edge_web.available() and edge_web.is_video_url(url)

    def _open_current_in_edge(self) -> None:
        if self._edge_site_active:
            self._flash("当前网页已经在系统内核里播放", 3000)
            return
        if self._stack.currentWidget() is not self._browser:
            self._flash("先打开一个网页，再切换到系统内核", 3500)
            return
        url = self._browser.current_url
        if not url.lower().startswith(("http://", "https://")):
            self._flash("先打开一个网页，再切换到系统内核", 3500)
            return
        self._open_edge_site(url)

    def _ensure_edge_site(self) -> edge_web.EdgeSiteWindow:
        if self._edge_site is None:
            self._edge_site = edge_web.EdgeSiteWindow(self, self._app_container, self)
            self._edge_site.ready.connect(self._on_edge_site_ready)
            self._edge_site.failed.connect(self._on_edge_site_failed)
            self._edge_site.closed.connect(self._on_edge_site_closed)
        return self._edge_site

    def _open_edge_site(self, url: str) -> None:
        if not url:
            return
        if not edge_web.available():
            if browser.WEBENGINE_AVAILABLE:
                self._flash("没有找到系统 Edge / Chrome，视频可能无法播放", 6500)
                self._set_app_mode(False)
                self._stack.setCurrentWidget(self._browser)
                self._address.setText(urls.display_url(url))
                self._browser.go_url(url)
            else:
                QDesktopServices.openUrl(QUrl(url))
            return

        self._close_edge_site()
        if self._embedder.current is not None:
            self._embedder.detach()
        try:
            self._browser.stop()
        except Exception:
            pass
        site = self._ensure_edge_site()
        name = edge_web.site_label(url)
        self._edge_site_active = True
        self._app_title.setText(name)
        self._app_placeholder.setText(f"正在用系统内核打开 {name}…")
        self._app_placeholder.show()
        self._app_notice.setVisible(False)
        self._app_detach.setVisible(False)
        self._set_app_mode(True)
        self._stack.setCurrentWidget(self._app_page)
        self._set_status(f"正在用系统内核打开 {name}…")
        if not site.open(url):
            self._edge_site_active = False
            self._flash("系统内核打开失败", 5000)

    def _on_edge_site_ready(self, _title: str) -> None:
        if not self._edge_site_active:
            return
        self._app_placeholder.hide()
        self._app_detach.setVisible(True)
        self._queue_edge_sync()
        self._flash(
            f"{self._app_title.text()} 已用系统内核打开，老板键 / 隐身照常", 5000
        )

    def _on_edge_site_failed(self, message: str) -> None:
        self._edge_site_active = False
        self._app_placeholder.setText(
            message + "\n\n可以返回首页重试；或在系统浏览器里打开这个网站。"
        )
        self._app_placeholder.show()
        self._app_detach.setVisible(False)
        self._flash(message, 7000)

    def _on_edge_site_closed(self) -> None:
        if not self._edge_site_active:
            return
        self._edge_site_active = False
        self._app_placeholder.setText("网页已关闭。\n回到左侧点一下可以重新打开。")
        self._app_placeholder.show()
        self._app_detach.setVisible(False)
        self._flash("系统内核网页已关闭", 4000)

    def _close_edge_site(self) -> None:
        self._edge_sync_timer.stop()
        if self._edge_site is not None:
            self._edge_site.close()
        self._edge_site_active = False

    def _detach_edge_site(self) -> None:
        self._edge_sync_timer.stop()
        if self._edge_site is not None:
            self._edge_site.detach()
        self._edge_site_active = False
        self._app_title.setText("应用")
        self._app_placeholder.setText("网页已放到桌面窗口。\n回到左侧可以重新打开。")
        self._app_placeholder.show()
        self._app_detach.setVisible(False)
        self._set_app_mode(False)
        self._stack.setCurrentWidget(self._dashboard)
        self._flash("视频窗口已放到桌面", 4000)

    def _edge_pids(self) -> set[int]:
        if self._edge_site is None or not self._edge_site_active:
            return set()
        return self._edge_site.pids()

    def _edge_screen_rect(self) -> QRect:
        if self._edge_site is None or not self._edge_site_active:
            return QRect()
        if self._stack.currentWidget() is not self._app_page:
            return QRect()
        return self._edge_site.screen_rect()

    def _queue_edge_sync(self) -> None:
        if self._edge_site_active:
            self._edge_sync_timer.start()

    def _sync_edge_overlay(self) -> None:
        if (
            self._edge_site is not None
            and self._edge_site_active
            and self._stack.currentWidget() is self._app_page
        ):
            self._edge_site.sync()

    def _on_stack_changed(self, _index: int) -> None:
        if not self._edge_site_active:
            return
        if self._stack.currentWidget() is not self._app_page:
            self._close_edge_site()
        else:
            self._queue_edge_sync()

    def choose_app_file(self) -> None:
        start = os.environ.get("ProgramFiles", "C:\\Program Files")
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "选择要添加的应用",
            start,
            "程序或快捷方式 (*.exe *.lnk);;所有文件 (*)",
        )
        if filename:
            self.add_app_path(filename, launch=False)

    def add_app_path(self, path: str, launch: bool = False):
        """加入「我的应用」；只有显式要求时才立即启动（默认只入列表）。"""
        try:
            app, is_new = apps.add_path(self.settings, path)
        except ValueError as exc:
            self._flash(str(exc), 5000)
            return None

        self.settings.save()
        if is_new:
            self._populate_sidebar()
            self._flash(f"已加入「我的应用」：{app.name} · 点击左侧图标即可打开", 4500)
        else:
            self._set_status(f"{app.name} 已经在列表里")

        if launch:
            ok, message = apps.launch(app)
            self._flash(message, 5000)
            if ok:
                self._set_status(f"已启动 {app.name} · {app.exe}")
        return app

    def remove_app(self, app_id: str) -> None:
        if apps.remove(self.settings, app_id):
            self.settings.save()
            self._populate_sidebar()
            self._flash("已从「我的应用」移除")

    # ================================================================== 我的书
    def open_book(self, book_id: str) -> None:
        book = books.find_book(self.settings, book_id)
        if book is None:
            return
        if not book.exists:
            self._flash(f"找不到这本书：{book.path}")
            return
        try:
            content = books.read_text(book.path)
        except (OSError, ValueError) as exc:
            self._flash(f"打开失败：{exc}", 5000)
            return

        self._reader_title.setText(book.name)
        self._reader_editor.setPlainText(content.text)
        cursor = self._reader_editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self._reader_editor.setTextCursor(cursor)
        self._reader_editor.verticalScrollBar().setValue(0)
        self._set_app_mode(True)
        self._stack.setCurrentWidget(self._reader_page)
        message = f"《{book.name}》· {content.encoding}"
        if content.truncated:
            message += " · 文件较大，只载入前 8MB"
        self._flash(message, 5000)

    def _back_from_reader(self) -> None:
        self._set_app_mode(False)
        self._stack.setCurrentWidget(self._dashboard)

    def choose_book_file(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "选择 txt 电子书",
            str(Path.home()),
            "文本文件 (*.txt);;所有文件 (*)",
        )
        if filename:
            self.add_book_path(filename, open_now=True)

    def add_book_path(self, path: str, open_now: bool = False):
        try:
            book, is_new = books.add_path(self.settings, path)
        except ValueError as exc:
            self._flash(str(exc), 5000)
            return None
        self.settings.save()
        if is_new:
            self._populate_sidebar()
            self._flash(f"已加入「我的书」：{book.name}", 3500)
        if open_now or is_new:
            self.open_book(book.id)
        return book

    def remove_book(self, book_id: str) -> None:
        if books.remove(self.settings, book_id):
            self.settings.save()
            self._populate_sidebar()
            if self._stack.currentWidget() is self._reader_page:
                self._back_from_reader()
            self._flash("已从「我的书」移除")

    # ================================================================== 拖拽
    @staticmethod
    def _mime_paths(mime) -> list[str]:
        if mime is None or not mime.hasUrls():
            return []
        supported = set(apps.SUPPORTED_SUFFIXES) | set(books.SUPPORTED_SUFFIXES)
        paths: list[str] = []
        for url in mime.urls():
            if not url.isLocalFile():
                continue
            path = url.toLocalFile()
            if Path(path).suffix.lower() in supported:
                paths.append(path)
        return paths

    def _handle_drop_paths(self, paths: list[str]) -> None:
        for path in paths[:3]:
            if Path(path).suffix.lower() in books.SUPPORTED_SUFFIXES:
                self.add_book_path(path, open_now=True)
            else:
                self.add_app_path(path, launch=False)

    def eventFilter(self, obj, event):  # noqa: N802
        try:
            if isinstance(obj, QWidget) and obj.window() is self:
                event_type = event.type()
                if event_type in (QEvent.Type.DragEnter, QEvent.Type.DragMove):
                    if self._mime_paths(event.mimeData()):
                        event.acceptProposedAction()
                        self._set_status("松开鼠标：加入程序 / 打开电子书")
                        return True
                elif event_type == QEvent.Type.Drop:
                    paths = self._mime_paths(event.mimeData())
                    if paths:
                        event.acceptProposedAction()
                        self._handle_drop_paths(paths)
                        return True
                elif event_type == QEvent.Type.DragLeave:
                    self._reset_idle_status()
        except Exception:
            log.exception("处理拖拽失败")
        return super().eventFilter(obj, event)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if self._mime_paths(event.mimeData()):
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if self._mime_paths(event.mimeData()):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        paths = self._mime_paths(event.mimeData())
        if paths:
            event.acceptProposedAction()
            self._handle_drop_paths(paths)

    def _reset_idle_status(self) -> None:
        count = len(apps.load_apps(self.settings))
        if count:
            self._set_status(f"就绪 · 我的应用 {count} 个")
        else:
            self._set_status("就绪 · 把视频软件的 exe 拖进窗口即可添加")

    def open_site(self, url: str) -> None:
        if not url:
            return
        if self._should_use_edge(url):
            self._open_edge_site(url)
            return
        if not browser.WEBENGINE_AVAILABLE:
            QDesktopServices.openUrl(QUrl(url))
            self._flash("内嵌浏览器不可用，已用系统浏览器打开")
            return
        self._set_app_mode(False)
        self._stack.setCurrentWidget(self._browser)
        self._address.setText(urls.display_url(url))
        self._browser.go_url(url)

    def _navigate_from_address(self) -> None:
        text = self._address.text().strip()
        if not text:
            self.go_home()
            return
        target = urls.normalize_input(text, self.settings.browser.search_engine)
        if target and self._should_use_edge(target):
            self._open_edge_site(target)
            return
        if not browser.WEBENGINE_AVAILABLE:
            if target:
                QDesktopServices.openUrl(QUrl(target))
            return
        self._set_app_mode(False)
        self._stack.setCurrentWidget(self._browser)
        self._browser.go(text)

    def go_home(self) -> None:
        home_url = self.settings.browser.home_url.strip()
        if home_url:
            self.open_site(home_url)
            return
        self._set_app_mode(False)
        self._stack.setCurrentWidget(self._dashboard)
        self._address.clear()
        self.setWindowTitle(self._brand.base_title)

    def _go_back(self) -> None:
        if self._stack.currentWidget() is self._browser and hasattr(self._browser, "history"):
            self._browser.history().back()

    def _go_forward(self) -> None:
        if self._stack.currentWidget() is self._browser and hasattr(self._browser, "history"):
            self._browser.history().forward()

    def _reload(self) -> None:
        if self._stack.currentWidget() is self._browser:
            self._browser.reload_page()
        else:
            self._dashboard.apply_settings(self.settings)

    def _retry_page(self) -> None:
        self._set_app_mode(False)
        self._stack.setCurrentWidget(self._browser)
        try:
            self._browser.reload_page()
        except Exception:
            self.go_home()

    def _on_url_changed(self, url: QUrl) -> None:
        if self._stack.currentWidget() is self._browser:
            target = url.toString()
            self._address.setText(urls.display_url(target))
            if self._should_use_edge(target) and not self._edge_route_pending:
                self._edge_route_pending = True
                QTimer.singleShot(0, lambda value=target: self._route_to_edge(value))
        self._update_nav_buttons()

    def _route_to_edge(self, url: str) -> None:
        self._edge_route_pending = False
        if self._stack.currentWidget() is self._browser and self._should_use_edge(url):
            self._open_edge_site(url)

    def _on_page_title(self, title: str) -> None:
        if title and self._brand.id == "default":
            self.setWindowTitle(f"{title} · {__app_name__}")
        elif title:
            self.setWindowTitle(title)
        else:
            self.setWindowTitle(self._brand.base_title)

    def _update_nav_buttons(self) -> None:
        if not hasattr(self._browser, "history"):
            return
        history = self._browser.history()
        self._btn_back.setEnabled(history.canGoBack())
        self._btn_forward.setEnabled(history.canGoForward())

    def _on_load_failed(self, url: str) -> None:
        if self._stack.currentWidget() is not self._browser:
            return
        self._error_url.setText(url)
        self._stack.setCurrentWidget(self._error_page)

    def _on_download(self, path: str) -> None:
        self._flash(f"开始下载：{path}", 6000)

    # ================================================================== 老板键
    def _capture_state(self) -> None:
        self._was_maximized = self.isMaximized()
        self._was_fullscreen = self.isFullScreen()
        self._saved_geometry = self.geometry()
        try:
            self._web_muted_before = bool(self._browser.is_muted())
        except Exception:
            self._web_muted_before = False

    def _mute_web(self) -> None:
        try:
            self._browser.pause_media()
            self._browser.set_muted(True)
        except Exception:
            pass

    def _unmute_web(self) -> None:
        try:
            self._browser.set_muted(self._web_muted_before)
        except Exception:
            pass

    def _exit_theater_for_hide(self) -> None:
        if self._theater:
            self._set_theater(False)
            self._was_fullscreen = False
        try:
            self._browser.exit_html_fullscreen()
        except Exception:
            pass

    def _hide_clients(self) -> list[int]:
        try:
            exe_names, titles = apps.window_targets(self.settings)
            windows = winapi.find_client_windows(
                exe_names=exe_names,
                title_keywords=titles,
                exclude_pids={os.getpid()},
                require_visible=True,
            )
            hidden = winapi.hide_windows([w.hwnd for w in windows])
            if hidden:
                log.info("隐藏了 %d 个客户端窗口", len(hidden))
            return hidden
        except Exception:
            log.exception("隐藏客户端窗口失败")
            return []

    def toggle_boss(self) -> None:
        if self._hidden_reason:
            self.restore_window()
        elif not self.isVisible():
            # 之前用关闭按钮缩到了托盘，老板键应该先把它叫回来
            self._show_from_tray()
        else:
            self.hide_everything()

    def hide_everything(self) -> None:
        """老板键：隐藏窗口、静音、藏起客户端，必要时放伪装画面。"""
        if self._hidden_reason:
            return
        modal = QApplication.activeModalWidget()
        if modal is not None and modal is not self:
            try:
                modal.reject()
            except Exception:
                modal.hide()
        self._capture_state()
        self._mute_web()
        self._exit_theater_for_hide()
        self._hidden_reason = "boss"
        self.stealth.set_visible(False)
        if self.settings.boss.hide_external:
            self._hidden_external = self._hide_clients()
        if self.audio is not None and self.audio.available:
            if self.settings.boss.mute_others:
                self._saved_audio = self.audio.mute_others({os.getpid()})
            else:
                pids = self._edge_pids()
                if self._embedder.current is not None:
                    pids |= self._embedder.pids()
                if pids:
                    self._saved_audio = self.audio.mute_pids(pids)
        if self.settings.boss.decoy:
            self._show_decoy()
        self.hide()
        self._update_tray()
        log.info("老板键：窗口已隐藏")

    def hide_for_stealth(self, reason: str = "leave") -> None:
        if self._hidden_reason:
            return
        self._capture_state()
        self._mute_web()
        if self.audio is not None and self.audio.available:
            pids = self._edge_pids()
            if self._embedder.current is not None:
                pids |= self._embedder.pids()
            if pids:
                self._saved_audio.extend(self.audio.mute_pids(pids))
        self._exit_theater_for_hide()
        self._hidden_reason = "stealth"
        self.stealth.set_visible(False)
        self.hide()
        self.stealth.notify_hidden_by_stealth()
        self._update_tray()
        log.info("隐身模式触发（%s）", reason)
        if not self._tray_tip_shown and self.tray is not None and self.settings.first_run:
            self._tray_tip_shown = True
            if self._brand.id == "default":
                self.tray.showMessage(
                    self._brand.name,
                    f"已进入隐身。鼠标贴到屏幕边缘，或按 {hotkeys.format_hotkey(self.settings.stealth_key)} 唤回。",
                    QSystemTrayIcon.MessageIcon.Information,
                    4000,
                )
            else:
                self.tray.showMessage(
                    self._brand.name,
                    "已最小化。双击托盘图标恢复。",
                    QSystemTrayIcon.MessageIcon.Information,
                    3000,
                )

    def restore_window(self, focus: bool = True) -> None:
        if not self._hidden_reason:
            return
        reason = self._hidden_reason
        self._hidden_reason = None

        if self._decoy is not None:
            decoy_window = self._decoy
            self._decoy = None
            try:
                decoy_window.closed.disconnect(self._on_decoy_closed)
            except Exception:
                pass
            decoy_window.close()

        self.stealth.set_visible(True)
        self._unmute_web()
        if self._saved_audio and self.audio is not None:
            self.audio.restore(self._saved_audio)
            self._saved_audio = []
        if self._hidden_external:
            winapi.show_windows(self._hidden_external)
            self._hidden_external = []

        if self._was_fullscreen:
            self.showFullScreen()
        elif self._was_maximized:
            self.showMaximized()
        else:
            self.show()
            if self._saved_geometry is not None:
                self.setGeometry(self._saved_geometry)
        if focus:
            self.raise_()
            self.activateWindow()
        self._update_tray()
        self._update_nav_buttons()
        log.info("窗口唤回（%s）", reason)
        self._flash("已回来，继续摸鱼" if reason == "boss" else "隐身结束，欢迎回来")

    def _show_decoy(self) -> None:
        old = self._decoy
        self._decoy = None
        if old is not None:
            try:
                old.closed.disconnect(self._on_decoy_closed)
            except Exception:
                pass
            old.close()
        self._decoy = decoy.DecoyWindow(self.settings.boss.decoy_style)
        self._decoy.closed.connect(self._on_decoy_closed)
        self._decoy.present(self.screen())

    def _on_decoy_closed(self) -> None:
        self._decoy = None
        if self._hidden_reason:
            self.restore_window()

    # ================================================================== 隐身
    def _setup_stealth(self) -> None:
        self.stealth = stealth.StealthController(self, self.settings, self)
        self.stealth.set_extra_inside(self._edge_screen_rect)
        self.stealth.hideRequested.connect(self.hide_for_stealth)
        self.stealth.showRequested.connect(lambda _reason: self.restore_window())
        if not self.headless:
            self.stealth.start()

    def _on_stealth_switch(self, checked: bool) -> None:
        self.settings.stealth.enabled = bool(checked)
        self.settings.save()
        self.stealth.refresh()
        self._dashboard.apply_settings(self.settings)
        self._update_hints()
        self._update_tray()
        if checked:
            self._flash(
                f"隐身模式已开启：鼠标移出窗口 {self.settings.stealth.leave_delay_ms / 1000:g} 秒后自动隐藏"
            )
        else:
            self._flash("隐身模式已关闭，仍可用老板键手动隐藏")

    def _sync_stealth_switch(self) -> None:
        self._stealth_switch.blockSignals(True)
        self._stealth_switch.setChecked(bool(self.settings.stealth.enabled))
        self._stealth_switch.blockSignals(False)

    def _toggle_stealth_hotkey(self) -> None:
        if self._hidden_reason:
            self.restore_window()
        elif not self.isVisible():
            self._show_from_tray()
        else:
            self.hide_for_stealth("hotkey")

    # ================================================================== 热键
    def _setup_hotkeys(self) -> None:
        self.hotkeys = hotkeys.GlobalHotkeys(self, hwnd=int(self._hotkey_host.winId()))
        self.hotkeys.bossPressed.connect(self.toggle_boss)
        self.hotkeys.stealthPressed.connect(self._toggle_stealth_hotkey)
        self.hotkeys.availabilityChanged.connect(self._on_hotkey_availability)
        if self.headless:
            return
        ok = self.hotkeys.attach(self.settings.boss_key, self.settings.stealth_key)
        if not ok:
            self._install_local_shortcuts(True)

    def _register_hotkeys(self) -> None:
        if self.headless:
            return
        ok = self.hotkeys.attach(self.settings.boss_key, self.settings.stealth_key)
        self._install_local_shortcuts(not ok)
        if ok:
            self._flash("热键已更新：" + hotkeys.format_hotkey(self.settings.boss_key))
        else:
            self._flash("全局热键注册失败，只能在窗口内使用", 6000)

    def _install_local_shortcuts(self, enabled: bool) -> None:
        for shortcut in self._local_shortcuts:
            shortcut.setEnabled(False)
            shortcut.deleteLater()
        self._local_shortcuts.clear()
        if not enabled:
            return
        for key, handler in (
            (self.settings.boss_key, self.toggle_boss),
            (self.settings.stealth_key, self._toggle_stealth_hotkey),
        ):
            sequence = hotkeys.hotkey_to_qt(key)
            if not sequence:
                continue
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(handler)
            self._local_shortcuts.append(shortcut)

    def _on_hotkey_availability(self, available: bool, message: str) -> None:
        self._update_hints()
        if not available and message:
            self._set_status(f"提示：{message}", warn=True)

    def _install_global_ui_shortcuts(self) -> None:
        for sequence, handler in (
            ("Ctrl+L", self._focus_address),
            ("Ctrl+R", self._reload),
            ("F11", lambda: self._set_theater(not self._theater)),
            ("Escape", self._on_escape),
        ):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(handler)

    def _focus_address(self) -> None:
        self._address.setFocus()
        self._address.selectAll()

    def _on_escape(self) -> None:
        if self._theater:
            self._set_theater(False)
        elif self._stack.currentWidget() is self._app_page:
            self._back_from_app()
        elif self._stack.currentWidget() is self._reader_page:
            self._back_from_reader()

    # ================================================================== 托盘
    def _setup_tray(self) -> None:
        self.tray: QSystemTrayIcon | None = None
        if self.headless or not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(theme.disguise_icon(self._brand.id), self)
        self.tray.setToolTip(self._brand.name)
        menu = QMenu()
        self._tray_show_action = menu.addAction("显示窗口")
        self._tray_show_action.triggered.connect(self._show_from_tray)
        self._tray_boss_action = menu.addAction("隐藏窗口")
        self._tray_boss_action.triggered.connect(self.hide_everything)
        self._tray_stealth_action = menu.addAction("鼠标移出自动隐藏")
        self._tray_stealth_action.setCheckable(True)
        self._tray_stealth_action.toggled.connect(self._on_stealth_switch)
        menu.addSeparator()
        settings_action = menu.addAction("设置…")
        settings_action.triggered.connect(self.open_settings)
        data_action = menu.addAction("打开数据目录")
        data_action.triggered.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(paths.data_dir())))
        )
        menu.addSeparator()
        quit_action = menu.addAction("退出")
        quit_action.triggered.connect(self.quit_app)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()
        self._update_tray()

    def _on_tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            if self._hidden_reason:
                self.restore_window()
            else:
                self._show_from_tray()

    def _show_from_tray(self) -> None:
        if self._hidden_reason:
            self.restore_window()
            return
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.stealth.set_visible(True)
        self.raise_()
        self.activateWindow()

    def activate_from_external(self) -> None:
        """另一个进程启动时，把已有窗口叫到前面，而不是再开一个。"""
        if self._hidden_reason:
            self.restore_window()
            return
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.stealth.set_visible(True)
        self.raise_()
        self.activateWindow()

    def _update_tray(self) -> None:
        self._boss_button.setText("结束隐身" if self._hidden_reason else "立即隐身")
        if self.tray is None:
            return
        if self._hidden_reason:
            self.tray.setToolTip(f"{self._brand.name} · 已最小化")
            self._tray_show_action.setText("显示窗口")
        else:
            self.tray.setToolTip(f"{self._brand.name} · 运行中")
            self._tray_show_action.setText("显示窗口")
        self._tray_stealth_action.blockSignals(True)
        self._tray_stealth_action.setChecked(self.settings.stealth.enabled)
        self._tray_stealth_action.blockSignals(False)

    # ================================================================== 设置
    def open_settings(self) -> None:
        dialog = SettingsDialog(
            copy.deepcopy(self.settings),
            self,
            hotkey_available=self.hotkeys.available,
            hotkey_message=self.hotkeys.message,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.apply_settings(dialog.result_settings())

    def apply_settings(self, new_settings: Settings) -> None:
        self.settings = new_settings
        self.settings.normalize()
        self.settings.save()
        self._reader_theme = self.settings.reader.theme
        self._apply_reader_theme()
        if not self.settings.apps.embed and self._embedder.current is not None:
            self._detach_embedded()
        try:
            self._browser.apply_settings(self.settings)
        except Exception:
            pass
        self._dashboard.apply_settings(self.settings)
        self._apply_window_prefs()
        self.stealth.set_settings(self.settings)
        self._sync_stealth_switch()
        self._register_hotkeys()
        self._populate_sidebar()
        self._update_hints()
        self._update_tray()
        self._apply_disguise()

    def _apply_window_prefs(self) -> None:
        self.setWindowOpacity(self.settings.window.opacity)
        want_top = bool(self.settings.window.always_on_top)
        # 不要用 flags &= ~WindowStaysOnTopHint：PySide6 的 QFlags 取反结果会
        # 截断高位，把 WindowCloseButtonHint 一起清掉，右上角 × 会变成灰色。
        if bool(self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint) != want_top:
            was_visible = self.isVisible()
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, want_top)
            if was_visible:
                self.show()
        if self._edge_site_active and self._edge_site is not None:
            self._edge_site.set_topmost(want_top)

    # ================================================================== 影院模式
    def _on_fullscreen_toggled(self, on: bool) -> None:
        self._set_theater(on)

    def _set_theater(self, on: bool) -> None:
        if on == self._theater:
            return
        self._theater = on
        if on:
            self._theater_prev_max = self.isMaximized()
            self._sidebar.hide()
            self._topbar.hide()
            self._statusbar.hide()
            self.showFullScreen()
        else:
            self._sidebar.show()
            self._topbar.show()
            self._statusbar.show()
            if self._theater_prev_max:
                self.showMaximized()
            else:
                self.showNormal()

    # ================================================================== 杂项
    def _set_status(self, text: str, warn: bool = False) -> None:
        self._status_label.setText(text)
        color = theme.WARN if warn else theme.TEXT_DIM
        self._status_label.setStyleSheet(f"color:{color}; font-size:11.5px; background:transparent;")

    def _flash(self, message: str, timeout_ms: int = 4500) -> None:
        self._flash_token += 1
        token = self._flash_token
        was_hidden = self._hidden_reason is not None
        if not was_hidden:
            self._status_label.setText(message)
            self._status_label.setStyleSheet(
                f"color:{theme.TEXT_MUTED}; font-size:11.5px; background:transparent;"
            )
        QTimer.singleShot(timeout_ms, lambda: self._restore_status(token))

    def _restore_status(self, token: int) -> None:
        if token != self._flash_token:
            return
        count = len(apps.load_apps(self.settings))
        if count:
            self._set_status(f"就绪 · 我的应用 {count} 个")
        else:
            self._set_status("就绪 · 把视频软件的 exe 拖进窗口即可添加")

    def _update_hints(self) -> None:
        boss = hotkeys.format_hotkey(self.settings.boss_key)
        stealth_key = hotkeys.format_hotkey(self.settings.stealth_key)
        hint = f"老板键 {boss} · 隐身 {stealth_key}"
        if not self.headless and not self.hotkeys.available:
            hint += " · 全局热键不可用"
        self._hint_label.setText(hint)
        self._hint_label.setStyleSheet(
            f"color:{theme.WARN if (not self.headless and not self.hotkeys.available) else theme.TEXT_DIM};"
            "font-size:11px; background:transparent;"
        )
        self._boss_key_label.setText(boss)
        enabled = self.settings.stealth.enabled
        self._stealth_label.setText("隐身")
        self._stealth_label.setStyleSheet(
            f"color:{theme.ACCENT if enabled else theme.TEXT_DIM}; font-size:12px;"
        )
        self._stealth_label.setToolTip(
            "隐身模式已开启：鼠标移出窗口自动隐藏" if enabled else "隐身模式已关闭，点击右侧开关启用"
        )

    # ================================================================== 生命周期
    def _restore_window_state(self) -> None:
        geometry = self.settings.window.geometry
        if geometry and len(geometry) == 4:
            try:
                rect = QRect(*geometry)
            except (TypeError, ValueError):
                rect = QRect()
            if not rect.isEmpty():
                screens = QApplication.screens()
                if any(screen.availableGeometry().intersects(rect) for screen in screens):
                    self.setGeometry(rect)
        if self.settings.window.start_maximized:
            self.showMaximized()

    def ensure_on_screen(self) -> None:
        """窗口跑到屏幕外（换了显示器 / 分辨率）时拉回主屏中央。"""
        screens = QApplication.screens()
        if not screens:
            return
        rect = self.frameGeometry()
        if any(screen.availableGeometry().intersects(rect) for screen in screens):
            return
        target = QApplication.primaryScreen().availableGeometry()
        self.move(target.center() - self.rect().center())

    def _apply_native_bits(self) -> None:
        try:
            winapi.set_dark_titlebar(int(self.winId()))
        except Exception:
            pass

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._apply_native_bits()
        self._queue_edge_sync()

    def hideEvent(self, event) -> None:  # noqa: N802
        super().hideEvent(event)
        if self._edge_site is not None and self._edge_site_active:
            self._edge_site.hide()

    def moveEvent(self, event) -> None:  # noqa: N802
        super().moveEvent(event)
        self._queue_edge_sync()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._queue_edge_sync()

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self._queue_edge_sync()

    def _save_window_state(self) -> None:
        if self.isMaximized() or self.isFullScreen():
            self.settings.window.start_maximized = self.isMaximized()
            return
        rect = self.geometry()
        self.settings.window.geometry = [rect.x(), rect.y(), rect.width(), rect.height()]
        self.settings.window.start_maximized = False

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        action = self.settings.window.close_action
        if self._quitting or action == "quit":
            self.shutdown()
            event.accept()
            QApplication.quit()
            return
        event.ignore()
        if action == "tray":
            self._minimize_to_tray()
        else:
            QTimer.singleShot(0, self._ask_close_action)

    def _minimize_to_tray(self) -> None:
        if self.tray is None:
            self.quit_app()
            return
        self.hide()
        self.stealth.set_visible(False)
        self._update_tray()
        if not self._tray_tip_shown:
            self._tray_tip_shown = True
            if self._brand.id == "default":
                self.tray.showMessage(
                    self._brand.name,
                    "已缩到托盘。老板键可以随时唤回，托盘图标右键退出。",
                    QSystemTrayIcon.MessageIcon.Information,
                    4000,
                )
            else:
                self.tray.showMessage(
                    self._brand.name,
                    "已最小化，双击托盘图标恢复。",
                    QSystemTrayIcon.MessageIcon.Information,
                    3000,
                )

    def _ask_close_action(self) -> None:
        if self._quitting or self._asking_close:
            return
        self._asking_close = True
        action = ""
        try:
            box = QMessageBox(self)
            box.setWindowTitle("退出")
            box.setIcon(QMessageBox.Icon.Question)
            box.setText("要最小化到托盘，还是彻底关闭？")
            tray_button = None
            if self.tray is not None:
                tray_button = box.addButton(
                    "最小化到托盘", QMessageBox.ButtonRole.AcceptRole
                )
                box.setInformativeText("最小化后仍可用老板键或托盘图标唤回。")
                box.setDefaultButton(tray_button)
            else:
                box.setText("系统托盘不可用，要彻底关闭吗？")
            quit_button = box.addButton("彻底关闭", QMessageBox.ButtonRole.DestructiveRole)
            box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
            remember = QCheckBox("记住我的选择，下次不再询问")
            remember.setChecked(True)
            box.setCheckBox(remember)
            box.exec()
            clicked = box.clickedButton()
            if tray_button is not None and clicked is tray_button:
                action = "tray"
            elif clicked is quit_button:
                action = "quit"
            else:
                return
            if remember.isChecked():
                self.settings.window.close_action = action
                self.settings.save()
        finally:
            self._asking_close = False
        if action == "quit":
            self.quit_app()
        else:
            self._minimize_to_tray()

    def quit_app(self) -> None:
        if self._decoy is not None:
            decoy_window = self._decoy
            self._decoy = None
            try:
                decoy_window.closed.disconnect(self._on_decoy_closed)
            except Exception:
                pass
            decoy_window.close()
        self.shutdown()
        QApplication.quit()

    def shutdown(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        if self._decoy is not None:
            decoy_window = self._decoy
            self._decoy = None
            try:
                decoy_window.closed.disconnect(self._on_decoy_closed)
            except Exception:
                pass
            try:
                decoy_window.close()
            except Exception:
                pass
        try:
            self.hotkeys.detach()
        except Exception:
            pass
        if self._saved_audio and self.audio is not None:
            self.audio.restore(self._saved_audio)
        if self._hidden_external:
            winapi.show_windows(self._hidden_external)
        try:
            self._close_edge_site()
        except Exception:
            pass
        try:
            self._embedder.stop()
        except Exception:
            pass
        try:
            self.stealth.stop()
            self.stealth.marker.close()
        except Exception:
            pass
        self._save_window_state()
        self.settings.save()
        if self.tray is not None:
            self.tray.hide()
        log.info("应用退出")
