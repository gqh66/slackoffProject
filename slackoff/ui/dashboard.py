"""首页仪表盘：大标题、下班倒计时、常用网站、使用说明。"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QTime, QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from .. import __version__, catalog
from ..hotkeys import format_hotkey
from . import theme, widgets


class WorkEndDialog(QDialog):
    """点一下倒计时，就在原地选择下班时间。"""

    def __init__(self, current: str = "18:00", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setModal(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        frame = QFrame()
        frame.setObjectName("workEndPopup")
        frame.setStyleSheet(
            "QFrame#workEndPopup {"
            f" background: {theme.SURFACE};"
            f" border: 1px solid {theme.BORDER};"
            " border-radius: 12px;"
            "}"
        )
        outer.addWidget(frame)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        title = QLabel("下班时间")
        title.setStyleSheet("font-size:13px; font-weight:700;")
        hint = QLabel("点击预设，或直接改时间")
        hint.setObjectName("dim")
        layout.addWidget(title)
        layout.addWidget(hint)

        self._time = QTimeEdit()
        self._time.setDisplayFormat("HH:mm")
        self._time.setFixedHeight(34)
        parsed = QTime.fromString(current, "HH:mm")
        self._time.setTime(parsed if parsed.isValid() else QTime(18, 0))
        self._time.lineEdit().returnPressed.connect(self._on_ok)
        self._time.lineEdit().selectAll()
        layout.addWidget(self._time)

        presets = QHBoxLayout()
        presets.setSpacing(6)
        for label in ("17:30", "18:00", "18:30", "19:00"):
            button = QPushButton(label)
            button.setObjectName("ghost")
            button.setFixedHeight(26)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _=False, value=label: self._pick(value))
            presets.addWidget(button)
        layout.addLayout(presets)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("取消")
        cancel.setObjectName("ghost")
        cancel.setFixedHeight(28)
        cancel.clicked.connect(self.reject)
        ok = QPushButton("确定")
        ok.setObjectName("primary")
        ok.setFixedHeight(28)
        ok.setMinimumWidth(72)
        ok.setDefault(True)
        ok.clicked.connect(self._on_ok)
        buttons.addWidget(cancel)
        buttons.addWidget(ok)
        layout.addLayout(buttons)

        self._time.setFocus()

    def _pick(self, value: str) -> None:
        self._time.setTime(QTime.fromString(value, "HH:mm"))
        self.accept()

    def _on_ok(self) -> None:
        self.accept()

    def value(self) -> str:
        return self._time.time().toString("HH:mm")


class Dashboard(QScrollArea):
    openSite = Signal(str)
    openSettings = Signal()
    dismissFirstRun = Signal()
    workEndChanged = Signal(str)

    def __init__(self, settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        body = QWidget()
        body.setObjectName("dashboardBody")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(26, 22, 26, 22)
        layout.setSpacing(16)

        layout.addWidget(self._build_hero())
        self._first_run_card = self._build_first_run()
        layout.addWidget(self._first_run_card)
        layout.addLayout(self._build_stats())
        layout.addWidget(self._build_sites())
        layout.addWidget(self._build_tips())
        layout.addWidget(self._build_footer())
        layout.addStretch(1)

        self.setWidget(body)

        self._clock = QTimer(self)
        self._clock.setInterval(30_000)
        self._clock.timeout.connect(self._update_clock)
        self._clock.start()
        self._update_clock()

        self.apply_settings(settings)

    # ------------------------------------------------------------------ 区块
    def _build_hero(self) -> QWidget:
        hero = QFrame()
        hero.setObjectName("hero")
        hero.setFixedHeight(158)
        layout = QHBoxLayout(hero)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(18)

        left = QVBoxLayout()
        left.setSpacing(6)
        self._hero_pill = QLabel("SLACKOFF · 摸鱼也要讲方法")
        self._hero_pill.setObjectName("pillAccent")
        self._hero_pill.setFixedWidth(190)
        self._hero_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left.addWidget(self._hero_pill, 0, Qt.AlignmentFlag.AlignLeft)

        self._hero_title = QLabel("今天也要好好摸鱼")
        self._hero_title.setObjectName("h1")
        left.addWidget(self._hero_title)

        self._hero_subtitle = QLabel("把视频装进自己的窗口：一键隐身、鼠标移开自动消失。")
        self._hero_subtitle.setObjectName("muted")
        left.addWidget(self._hero_subtitle)
        left.addSpacing(4)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        open_iqiyi = QPushButton("打开爱奇艺")
        open_iqiyi.setObjectName("primary")
        open_iqiyi.setCursor(Qt.CursorShape.PointingHandCursor)
        open_iqiyi.clicked.connect(lambda: self.openSite.emit("https://www.iqiyi.com/"))
        random_btn = QPushButton("随便挑一个")
        random_btn.setObjectName("ghost")
        random_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        random_btn.clicked.connect(self._open_random_site)
        settings_btn = QPushButton("设置老板键")
        settings_btn.setObjectName("ghost")
        settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        settings_btn.clicked.connect(self.openSettings.emit)
        buttons.addWidget(open_iqiyi)
        buttons.addWidget(random_btn)
        buttons.addWidget(settings_btn)
        buttons.addStretch(1)
        left.addLayout(buttons)
        layout.addLayout(left, 1)

        right = QHBoxLayout()
        right.setSpacing(14)
        clock_box = QVBoxLayout()
        clock_box.setSpacing(0)
        clock_box.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._time_label = QLabel("--:--")
        self._time_label.setStyleSheet(
            f"font-size:30px; font-weight:700; color:{theme.TEXT}; background:transparent;"
        )
        self._time_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._date_label = QLabel("")
        self._date_label.setObjectName("dim")
        self._date_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._countdown_label = widgets.ClickableLabel("")
        self._countdown_label.setStyleSheet(
            f"color:{theme.ACCENT}; font-size:11.5px; background:transparent;"
        )
        self._countdown_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._countdown_label.setToolTip("点击设置下班时间")
        self._countdown_label.clicked.connect(self._edit_work_end)
        clock_box.addWidget(self._time_label)
        clock_box.addWidget(self._date_label)
        clock_box.addWidget(self._countdown_label)
        right.addLayout(clock_box)

        fish = QLabel()
        fish.setFixedSize(92, 92)
        fish.setPixmap(
            theme.app_pixmap(184).scaled(
                92, 92, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
        )
        self._hero_logo = fish
        right.addWidget(fish)
        layout.addLayout(right, 0)
        return hero

    def _build_first_run(self) -> QWidget:
        card = QFrame()
        card.setObjectName("tip")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(14, 10, 12, 10)
        layout.setSpacing(12)

        badge = QLabel("新")
        badge.setFixedSize(24, 24)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(
            f"background:{theme.ACCENT}; color:#062420; border-radius:12px; font-weight:700;"
        )
        layout.addWidget(badge)

        self._tip_text = QLabel()
        self._tip_text.setWordWrap(True)
        self._tip_text.setStyleSheet(f"color:{theme.TEXT}; font-size:12.5px; background:transparent;")
        layout.addWidget(self._tip_text, 1)

        close = QPushButton("知道了")
        close.setObjectName("ghost")
        close.setFixedHeight(28)
        close.setCursor(Qt.CursorShape.PointingHandCursor)
        close.clicked.connect(self._dismiss_first_run)
        layout.addWidget(close)
        return card

    def _build_stats(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)
        self._stat_apps = widgets.StatCard("我的应用", "0 个", "拖入 exe 即可添加", accent=True)
        self._stat_boss = widgets.StatCard("老板键", "—", "随时隐身")
        self._stat_stealth = widgets.StatCard("隐身模式", "—", "鼠标移开自动隐藏")
        for card in (self._stat_apps, self._stat_boss, self._stat_stealth):
            row.addWidget(card, 1)
        return row

    def _build_sites(self) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        header = widgets.SectionHeader("常用网站")
        self._sites_header = header
        layout.addWidget(header)

        self._grid_host = QWidget()
        self._grid = QGridLayout(self._grid_host)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(10)
        layout.addWidget(self._grid_host)
        return box

    def _build_tips(self) -> QWidget:
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(6)

        title = QLabel("三种打开方式")
        title.setObjectName("h2")
        layout.addWidget(title)
        layout.addWidget(
            widgets.TipRow(
                "1",
                "内置浏览器",
                "在顶部地址栏输入网址或搜索词，登录状态和 Cookie 会保留在本地。",
            )
        )
        layout.addWidget(
            widgets.TipRow(
                "2",
                "拖入应用",
                "把视频软件的 exe 拖进窗口加入左侧，点一下在工具内打开；"
                "拖入 .txt 电子书则会直接进入护眼阅读页。老板键也会把它们一起藏起来。",
            )
        )
        layout.addWidget(
            widgets.TipRow(
                "3",
                "隐身模式",
                "鼠标移出窗口一会儿就自动隐藏；把鼠标贴到屏幕边缘（默认左侧）就能唤回，"
                "或者按隐身快捷键。",
            )
        )
        return card

    def _build_footer(self) -> QWidget:
        self._footer = QLabel(
            f"摸鱼神器 v{__version__} · 配置与缓存都在 data 目录 · 祝你今天准时下班"
        )
        self._footer.setObjectName("dim")
        self._footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._footer.setContentsMargins(0, 6, 0, 0)
        return self._footer

    def apply_brand(self, brand) -> None:
        """外观伪装时，把首页里明显的品牌字样也一起换掉。"""
        if brand.id == "default":
            self._hero_pill.setText("SLACKOFF · 摸鱼也要讲方法")
            self._hero_title.setText("今天也要好好摸鱼")
            self._hero_subtitle.setText("把视频装进自己的窗口：一键隐身、鼠标移开自动消失。")
            self._footer.setText(
                f"摸鱼神器 v{__version__} · 配置与缓存都在 data 目录 · 祝你今天准时下班"
            )
            self._first_run_card.setVisible(self._settings.first_run)
        else:
            self._hero_pill.setText(brand.subtitle.upper())
            self._hero_title.setText(f"{brand.short} 工作台")
            self._hero_subtitle.setText("本地文档、网页与工具")
            self._footer.setText(f"{brand.name} · 本地数据")
            self._first_run_card.setVisible(False)
        self._hero_logo.setPixmap(
            theme.disguise_pixmap(brand.id, 184).scaled(
                92, 92, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
        )

    # ------------------------------------------------------------------ 行为
    def _dismiss_first_run(self) -> None:
        self._settings.first_run = False
        self._first_run_card.setVisible(False)
        self.dismissFirstRun.emit()

    def _open_random_site(self) -> None:
        import random

        sites = catalog.SITES + tuple(catalog.custom_sites(self._settings))
        if not sites:
            return
        self.openSite.emit(random.choice(sites).url)

    def _update_clock(self) -> None:
        now = datetime.now()
        self._time_label.setText(now.strftime("%H:%M"))
        weekday = "一二三四五六日"[now.weekday()]
        self._date_label.setText(f"{now.month} 月 {now.day} 日 · 周{weekday}")

        end_text = getattr(self._settings.dashboard, "work_end", "18:00")
        end_time = QTime.fromString(end_text, "HH:mm")
        if not end_time.isValid():
            end_time = QTime(18, 0)
            end_text = "18:00"
        end = now.replace(hour=end_time.hour(), minute=end_time.minute(), second=0, microsecond=0)
        if now >= end:
            self._countdown_label.setText("已经下班了，快跑")
            self._countdown_label.setToolTip("点击修改下班时间")
            return
        delta = end - now
        minutes = int(delta.total_seconds() // 60)
        self._countdown_label.setText(
            f"距离 {end_text} 下班还有 {minutes // 60}h{minutes % 60:02d}m"
        )
        self._countdown_label.setToolTip(f"当前下班时间 {end_text} · 点击修改")

    def _edit_work_end(self) -> None:
        dialog = WorkEndDialog(self._settings.dashboard.work_end, self)
        dialog.adjustSize()
        anchor = self._countdown_label.mapToGlobal(self._countdown_label.rect().bottomLeft())
        screen = self.screen().availableGeometry()
        x = min(anchor.x(), screen.right() - dialog.width() - 8)
        x = max(screen.left() + 8, x)
        y = anchor.y() + 6
        if y + dialog.height() > screen.bottom() - 8:
            y = anchor.y() - dialog.height() - 6
        dialog.move(x, y)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.set_work_end(dialog.value())

    def set_work_end(self, value: str, persist: bool = True) -> None:
        parsed = QTime.fromString(str(value), "HH:mm")
        if not parsed.isValid():
            return
        text = parsed.toString("HH:mm")
        self._settings.dashboard.work_end = text
        if persist:
            self._settings.save()
        self._update_clock()
        self.workEndChanged.emit(text)

    def _row_count(self) -> int:
        return 4 if self.width() >= 1080 else 3 if self.width() >= 820 else 2

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if getattr(self, "_last_columns", 0) != self._row_count():
            self._rebuild_sites()

    def _rebuild_sites(self) -> None:
        self._last_columns = self._row_count()
        while self._grid.count():
            item = self._grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        sites = list(catalog.SITES) + catalog.custom_sites(self._settings)
        columns = self._last_columns
        for index, site in enumerate(sites):
            tile = widgets.SiteTile(site)
            tile.clicked.connect(lambda url=site.url: self.openSite.emit(url))
            self._grid.addWidget(tile, index // columns, index % columns)
        self._sites_header.set_count(f"{len(sites)} 个")
        for column in range(columns):
            self._grid.setColumnStretch(column, 1)

    def apply_settings(self, settings) -> None:
        self._settings = settings
        boss = format_hotkey(settings.boss_key)
        stealth_key = format_hotkey(settings.stealth_key)
        self._stat_boss.update_values(boss, "一键隐身 / 静音")
        self._stat_stealth.update_values(
            "已开启" if settings.stealth.enabled else "已关闭",
            f"{stealth_key} 或屏幕边缘唤回" if settings.stealth.enabled else "可在设置中开启",
        )
        delay = settings.stealth.leave_delay_ms / 1000
        corner = {
            "left": "屏幕左边缘",
            "right": "屏幕右边缘",
            "top": "屏幕上边缘",
            "bottom": "屏幕下边缘",
            "none": "快捷键",
        }.get(settings.stealth.hot_corner, "屏幕边缘")
        self._tip_text.setText(
            f"已为你开启隐身模式：鼠标移出窗口 {delay:g} 秒后自动隐藏，"
            f"移到{corner}可唤回；老板键是 {boss}。"
            if settings.stealth.enabled
            else f"隐身模式当前关闭：点顶部「隐身」开关即可开启自动隐藏；老板键 {boss} 随时可用。"
        )
        self._first_run_card.setVisible(settings.first_run)
        self._update_clock()
        self._rebuild_sites()

    def set_app_count(self, count: int) -> None:
        hint = "拖入 exe 即可添加" if count == 0 else "点左侧图标即可打开"
        self._stat_apps.update_values(f"{count} 个", hint)
