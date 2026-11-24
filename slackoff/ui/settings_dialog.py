"""设置对话框：热键录制、隐身参数、浏览器、应用与网站管理。"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import __app_name__, __version__, apps, catalog, disguise, paths
from ..config import Settings
from ..hotkeys import format_hotkey, normalize_hotkey
from ..urls import looks_like_url, normalize_input
from . import theme, widgets

log = logging.getLogger(__name__)

_QT_KEY_NAMES: dict[int, str] = {}


def _build_key_map() -> None:
    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        _QT_KEY_NAMES[getattr(Qt.Key, f"Key_{letter}")] = letter.lower()
    for digit in range(10):
        _QT_KEY_NAMES[getattr(Qt.Key, f"Key_{digit}")] = str(digit)
    for index in range(1, 25):
        _QT_KEY_NAMES[getattr(Qt.Key, f"Key_F{index}")] = f"f{index}"
    named = {
        "Key_Space": "space",
        "Key_Return": "enter",
        "Key_Enter": "enter",
        "Key_Escape": "escape",
        "Key_Backspace": "backspace",
        "Key_Insert": "insert",
        "Key_Delete": "delete",
        "Key_Home": "home",
        "Key_End": "end",
        "Key_PageUp": "page up",
        "Key_PageDown": "page down",
        "Key_Up": "up",
        "Key_Down": "down",
        "Key_Left": "left",
        "Key_Right": "right",
        "Key_Tab": "tab",
        "Key_Print": "print screen",
        "Key_Pause": "pause",
        "Key_ScrollLock": "scroll lock",
        "Key_CapsLock": "caps lock",
        "Key_NumLock": "num lock",
        "Key_Menu": "menu",
    }
    for attr, name in named.items():
        key = getattr(Qt.Key, attr, None)
        if key is not None:
            _QT_KEY_NAMES[int(key)] = name


_build_key_map()


class HotkeyEdit(QLineEdit):
    """点一下，然后按下组合键。"""

    def __init__(self, value: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedWidth(230)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setToolTip("点击后直接按组合键；至少需要 Ctrl / Alt / Win 中的一个")
        self._value = normalize_hotkey(value) or ""
        self.setText(format_hotkey(self._value))

    def value(self) -> str:
        return self._value

    def set_value(self, value: str) -> None:
        self._value = normalize_hotkey(value) or ""
        self.setText(format_hotkey(self._value))
        self.setStyleSheet("")

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = int(event.key())
        if key in (int(Qt.Key.Key_Control), int(Qt.Key.Key_Shift), int(Qt.Key.Key_Alt), int(Qt.Key.Key_Meta)):
            self.setText(self._modifier_preview(event.modifiers()))
            return
        name = _QT_KEY_NAMES.get(key)
        if not name:
            return
        mods = []
        modifiers = event.modifiers()
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            mods.append("ctrl")
        if modifiers & Qt.KeyboardModifier.AltModifier:
            mods.append("alt")
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            mods.append("shift")
        if modifiers & Qt.KeyboardModifier.MetaModifier:
            mods.append("win")
        combo = normalize_hotkey("+".join(mods + [name]))
        if combo:
            self._value = combo
            self.setText(format_hotkey(combo))
            self.setStyleSheet("")
        else:
            self.setText("请加上 Ctrl 或 Alt")
            self.setStyleSheet(f"color:{theme.WARN};")

    @staticmethod
    def _modifier_preview(modifiers) -> str:
        pieces = []
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            pieces.append("Ctrl")
        if modifiers & Qt.KeyboardModifier.AltModifier:
            pieces.append("Alt")
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            pieces.append("Shift")
        if modifiers & Qt.KeyboardModifier.MetaModifier:
            pieces.append("Win")
        pieces.append("…")
        return " + ".join(pieces)


class AddSiteDialog(QDialog):
    """一个对话框里同时填「名称」和「网址」。"""

    def __init__(
        self,
        parent: QWidget | None = None,
        engine: str = "baidu",
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._name = ""
        self._url = ""

        self.setWindowTitle("添加网站")
        self.setModal(True)
        self.setMinimumWidth(470)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(10)

        title = QLabel("添加网站")
        title.setObjectName("h2")
        hint = QLabel("名称会显示在首页卡片上；网址不写 https:// 也可以。")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addSpacing(4)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(10)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("例如：公司培训平台")
        self._name_edit.setFixedHeight(36)
        self._url_edit = QLineEdit()
        self._url_edit.setPlaceholderText("例如：https://www.bilibili.com/")
        self._url_edit.setFixedHeight(36)
        form.addRow("名称", self._name_edit)
        form.addRow("网址", self._url_edit)
        layout.addLayout(form)

        self._error = QLabel("")
        self._error.setWordWrap(True)
        self._error.setStyleSheet(f"color:{theme.WARN}; font-size:11.5px;")
        self._error.setVisible(False)
        layout.addWidget(self._error)

        layout.addSpacing(4)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("取消")
        cancel.setObjectName("ghost")
        cancel.clicked.connect(self.reject)
        confirm = QPushButton("添加")
        confirm.setObjectName("primary")
        confirm.setMinimumWidth(96)
        confirm.clicked.connect(self._on_ok)
        buttons.addWidget(cancel)
        buttons.addWidget(confirm)
        layout.addLayout(buttons)

        self._name_edit.returnPressed.connect(self._url_edit.setFocus)
        self._url_edit.returnPressed.connect(self._on_ok)
        self._name_edit.setFocus()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        try:
            from .. import winapi

            winapi.set_dark_titlebar(int(self.winId()))
        except Exception:
            pass

    def _show_error(self, message: str, field: QLineEdit) -> None:
        self._error.setText(message)
        self._error.setVisible(True)
        field.setFocus()
        field.selectAll()

    def _on_ok(self) -> None:
        name = self._name_edit.text().strip()
        raw = self._url_edit.text().strip()
        if not name:
            self._show_error("给这个网站起个名字吧。", self._name_edit)
            return
        if not raw:
            self._show_error("请输入网址。", self._url_edit)
            return
        if not (looks_like_url(raw) or raw.lower().startswith(("http://", "https://"))):
            self._show_error(
                "网址格式不对，试试 https://www.bilibili.com/ 或 www.bilibili.com。",
                self._url_edit,
            )
            return
        target = normalize_input(raw, self._engine)
        if not target or not target.lower().startswith(("http://", "https://")):
            self._show_error("这个网址没法打开，换一个试试。", self._url_edit)
            return
        self._name = name
        self._url = target
        self.accept()

    def site(self) -> dict:
        return {"name": self._name, "url": self._url, "color": theme.INDIGO}


class SettingsDialog(QDialog):
    def __init__(
        self,
        settings: Settings,
        parent: QWidget | None = None,
        hotkey_available: bool = True,
        hotkey_message: str = "",
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._hotkey_available = hotkey_available
        self._hotkey_message = hotkey_message

        self.setWindowTitle("设置")
        self.setModal(True)
        self.resize(780, 680)
        self.setMinimumSize(720, 580)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 16)
        root.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("设置")
        title.setObjectName("h2")
        subtitle = QLabel("改完记得点「保存设置」，部分选项会立即生效")
        subtitle.setObjectName("muted")
        header_box = QVBoxLayout()
        header_box.setSpacing(0)
        header_box.addWidget(title)
        header_box.addWidget(subtitle)
        header.addLayout(header_box)
        header.addStretch(1)
        root.addLayout(header)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._wrap(self._build_boss_tab()), "老板键")
        self._tabs.addTab(self._wrap(self._build_stealth_tab()), "隐身模式")
        self._tabs.addTab(self._wrap(self._build_browser_tab()), "浏览器")
        self._tabs.addTab(self._wrap(self._build_disguise_tab()), "外观")
        self._tabs.addTab(self._wrap(self._build_apps_tab()), "应用")
        self._tabs.addTab(self._wrap(self._build_sites_tab()), "网站")
        self._tabs.addTab(self._wrap(self._build_about_tab()), "关于")
        root.addWidget(self._tabs, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("取消")
        cancel.setObjectName("ghost")
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        save = QPushButton("保存设置")
        save.setObjectName("primary")
        save.setMinimumWidth(120)
        save.setCursor(Qt.CursorShape.PointingHandCursor)
        save.clicked.connect(self._on_save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        root.addLayout(buttons)

    # ------------------------------------------------------------------ 工具
    @staticmethod
    def _wrap(content: QWidget) -> QScrollArea:
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        area.setWidget(content)
        return area

    @staticmethod
    def _hint(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("dim")
        label.setWordWrap(True)
        return label

    @staticmethod
    def _row(label: str, *widgets_: QWidget, hint: str = "") -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(10)
        name = QLabel(label)
        name.setFixedWidth(118)
        layout.addWidget(name)
        for widget in widgets_:
            layout.addWidget(widget)
        if hint:
            hint_label = QLabel(hint)
            hint_label.setObjectName("dim")
            layout.addWidget(hint_label)
        layout.addStretch(1)
        return row

    def _checkbox(self, text: str, checked: bool):
        box = widgets.Switch()
        box.setChecked(checked)
        label = QLabel(text)
        label.setStyleSheet("font-size:12.5px;")
        return box, label

    # ------------------------------------------------------------------ 老板键
    def _build_boss_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 12, 6, 12)
        layout.setSpacing(14)

        group = QGroupBox("热键")
        group_layout = QVBoxLayout(group)
        group_layout.setSpacing(6)

        self._boss_edit = HotkeyEdit(self._settings.boss_key)
        boss_row = self._row("老板键", self._boss_edit)
        reset_boss = QPushButton("恢复 Ctrl+Alt+B")
        reset_boss.setObjectName("ghost")
        reset_boss.clicked.connect(lambda: self._boss_edit.set_value("ctrl+alt+b"))
        boss_row.layout().insertWidget(2, reset_boss)
        group_layout.addWidget(boss_row)

        self._stealth_edit = HotkeyEdit(self._settings.stealth_key)
        stealth_row = self._row("隐身键", self._stealth_edit)
        reset_stealth = QPushButton("恢复 Ctrl+Alt+H")
        reset_stealth.setObjectName("ghost")
        reset_stealth.clicked.connect(lambda: self._stealth_edit.set_value("ctrl+alt+h"))
        stealth_row.layout().insertWidget(2, reset_stealth)
        group_layout.addWidget(stealth_row)

        status_text = (
            "全局热键已生效，窗口隐藏时也可以使用。"
            if self._hotkey_available
            else f"全局热键不可用：{self._hotkey_message or '注册失败'}；目前只能在窗口内使用。"
        )
        status = QLabel(status_text)
        status.setWordWrap(True)
        status.setStyleSheet(
            f"color:{theme.GREEN if self._hotkey_available else theme.WARN}; font-size:11.5px;"
        )
        group_layout.addWidget(status)
        group_layout.addWidget(self._hint("快捷键在别的程序里也生效；如果和输入法冲突，换一个组合即可。"))
        layout.addWidget(group)

        behavior = QGroupBox("按下老板键时")
        behavior_layout = QVBoxLayout(behavior)
        behavior_layout.setSpacing(8)

        self._chk_mute_audio, row1 = self._checkbox("静音内嵌网页的音频", self._settings.boss.mute_audio)
        behavior_layout.addWidget(self._with_switch(row1, self._chk_mute_audio))
        self._chk_pause, row2 = self._checkbox("暂停网页里的视频", self._settings.boss.pause_media)
        behavior_layout.addWidget(self._with_switch(row2, self._chk_pause))
        self._chk_mute_others, row3 = self._checkbox(
            "静音其它程序（爱奇艺客户端、音乐软件等）", self._settings.boss.mute_others
        )
        behavior_layout.addWidget(self._with_switch(row3, self._chk_mute_others))
        self._chk_hide_external, row4 = self._checkbox(
            "隐藏本工具启动的客户端窗口", self._settings.boss.hide_external
        )
        behavior_layout.addWidget(self._with_switch(row4, self._chk_hide_external))
        layout.addWidget(behavior)

        decoy_group = QGroupBox("伪装界面")
        decoy_layout = QVBoxLayout(decoy_group)
        decoy_layout.setSpacing(8)
        self._chk_decoy, row6 = self._checkbox(
            "隐藏后显示一个「正在认真工作」的全屏画面", self._settings.boss.decoy
        )
        decoy_layout.addWidget(self._with_switch(row6, self._chk_decoy))
        self._decoy_style = QComboBox()
        self._decoy_style.addItem("代码编辑器（VS Code 风格）", "code")
        self._decoy_style.addItem("表格（Excel 风格）", "excel")
        index = self._decoy_style.findData(self._settings.boss.decoy_style)
        self._decoy_style.setCurrentIndex(max(0, index))
        decoy_layout.addWidget(self._row("样式", self._decoy_style))
        decoy_layout.addWidget(self._hint("按 Esc 或再按一次老板键就能关掉伪装画面。谨慎使用，别吓到同事。"))
        layout.addWidget(decoy_group)

        window_group = QGroupBox("窗口")
        window_layout = QVBoxLayout(window_group)
        window_layout.setSpacing(8)
        self._chk_topmost, row7 = self._checkbox("窗口置顶显示", self._settings.window.always_on_top)
        window_layout.addWidget(self._with_switch(row7, self._chk_topmost))
        self._chk_start_max, row8 = self._checkbox("启动时最大化", self._settings.window.start_maximized)
        window_layout.addWidget(self._with_switch(row8, self._chk_start_max))
        self._close_combo = QComboBox()
        self._close_combo.addItem("每次询问", "ask")
        self._close_combo.addItem("最小化到托盘", "tray")
        self._close_combo.addItem("彻底退出", "quit")
        self._close_combo.setCurrentIndex(
            max(0, self._close_combo.findData(self._settings.window.close_action))
        )
        window_layout.addWidget(
            self._row("点关闭按钮时", self._close_combo, hint="选「每次询问」会弹出选择框")
        )
        self._opacity = QDoubleSpinBox()
        self._opacity.setRange(0.35, 1.0)
        self._opacity.setSingleStep(0.05)
        self._opacity.setDecimals(2)
        self._opacity.setValue(self._settings.window.opacity)
        self._opacity.setFixedWidth(110)
        window_layout.addWidget(self._row("不透明度", self._opacity, hint="透明到能看见后面的窗口，适合双屏摸鱼"))
        layout.addWidget(window_group)
        layout.addStretch(1)
        return page

    @staticmethod
    def _with_switch(label: QLabel, switch: QWidget) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(10)
        layout.addWidget(switch)
        layout.addWidget(label, 1)
        return row

    # ------------------------------------------------------------------ 隐身
    def _build_stealth_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 12, 6, 12)
        layout.setSpacing(14)

        group = QGroupBox("自动隐身")
        group_layout = QVBoxLayout(group)
        group_layout.setSpacing(8)

        self._chk_stealth, row = self._checkbox("启用隐身模式", self._settings.stealth.enabled)
        group_layout.addWidget(self._with_switch(row, self._chk_stealth))

        self._trigger_combo = QComboBox()
        self._trigger_combo.addItem("鼠标移出窗口时", "leave")
        self._trigger_combo.addItem("鼠标长时间不动时", "idle")
        self._trigger_combo.setCurrentIndex(max(0, self._trigger_combo.findData(self._settings.stealth.trigger)))
        group_layout.addWidget(self._row("触发方式", self._trigger_combo))

        self._leave_delay = QSpinBox()
        self._leave_delay.setRange(200, 15000)
        self._leave_delay.setSingleStep(100)
        self._leave_delay.setSuffix(" 毫秒")
        self._leave_delay.setValue(self._settings.stealth.leave_delay_ms)
        self._leave_delay.setFixedWidth(150)
        group_layout.addWidget(self._row("移出后等待", self._leave_delay, hint="太短容易误触"))

        self._idle_seconds = QSpinBox()
        self._idle_seconds.setRange(10, 7200)
        self._idle_seconds.setSingleStep(10)
        self._idle_seconds.setSuffix(" 秒")
        self._idle_seconds.setValue(self._settings.stealth.idle_seconds)
        self._idle_seconds.setFixedWidth(150)
        group_layout.addWidget(self._row("静止多久后隐身", self._idle_seconds))
        layout.addWidget(group)

        corner_group = QGroupBox("唤回方式")
        corner_layout = QVBoxLayout(corner_group)
        corner_layout.setSpacing(8)

        self._corner_combo = QComboBox()
        for label, value in (
            ("屏幕左边缘", "left"),
            ("屏幕右边缘", "right"),
            ("屏幕上边缘", "top"),
            ("屏幕下边缘", "bottom"),
            ("关闭边缘唤回（只用热键）", "none"),
        ):
            self._corner_combo.addItem(label, value)
        self._corner_combo.setCurrentIndex(max(0, self._corner_combo.findData(self._settings.stealth.hot_corner)))
        corner_layout.addWidget(self._row("鼠标贴边", self._corner_combo))

        self._corner_size = QSpinBox()
        self._corner_size.setRange(2, 40)
        self._corner_size.setSuffix(" 像素")
        self._corner_size.setValue(self._settings.stealth.hot_corner_size)
        self._corner_size.setFixedWidth(130)
        corner_layout.addWidget(self._row("感应宽度", self._corner_size))

        self._corner_span = QDoubleSpinBox()
        self._corner_span.setRange(0.1, 1.0)
        self._corner_span.setSingleStep(0.05)
        self._corner_span.setDecimals(2)
        self._corner_span.setValue(self._settings.stealth.hot_corner_span)
        self._corner_span.setFixedWidth(130)
        corner_layout.addWidget(self._row("感应长度", self._corner_span, hint="占屏幕边长的比例"))

        self._dwell = QSpinBox()
        self._dwell.setRange(100, 5000)
        self._dwell.setSingleStep(50)
        self._dwell.setSuffix(" 毫秒")
        self._dwell.setValue(self._settings.stealth.dwell_ms)
        self._dwell.setFixedWidth(150)
        corner_layout.addWidget(self._row("停留多久唤回", self._dwell))

        self._chk_marker, row2 = self._checkbox(
            "刚隐身时在边缘亮一条细光带（4 秒后消失）", self._settings.stealth.show_edge_marker
        )
        corner_layout.addWidget(self._with_switch(row2, self._chk_marker))
        corner_layout.addWidget(
            self._hint("提示：隐身只隐藏本工具的窗口，不会动其它程序；老板键才会连客户端一起藏。")
        )
        layout.addWidget(corner_group)
        layout.addStretch(1)
        return page

    # ------------------------------------------------------------------ 浏览器
    def _build_browser_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 12, 6, 12)
        layout.setSpacing(14)

        group = QGroupBox("启动与首页")
        group_layout = QVBoxLayout(group)
        group_layout.setSpacing(8)

        self._home_edit = QLineEdit(self._settings.browser.home_url)
        self._home_edit.setPlaceholderText("留空则显示内置首页，例如 https://www.iqiyi.com/")
        group_layout.addWidget(self._row("首页地址", self._home_edit))

        self._start_edit = QLineEdit(self._settings.browser.start_url)
        self._start_edit.setPlaceholderText("启动后自动打开，留空则不自动打开")
        group_layout.addWidget(self._row("启动时打开", self._start_edit))

        self._search_combo = QComboBox()
        for key, (label, _url) in catalog.SEARCH_ENGINES.items():
            self._search_combo.addItem(label, key)
        self._search_combo.setCurrentIndex(max(0, self._search_combo.findData(self._settings.browser.search_engine)))
        group_layout.addWidget(self._row("搜索引擎", self._search_combo))
        layout.addWidget(group)

        group2 = QGroupBox("渲染")
        group2_layout = QVBoxLayout(group2)
        group2_layout.setSpacing(8)

        self._ua_combo = QComboBox()
        self._ua_combo.addItem("桌面 Chrome（推荐，兼容性最好）", "chrome")
        self._ua_combo.addItem("QtWebEngine 默认", "default")
        self._ua_combo.addItem("手机浏览器（部分站点更省流量）", "mobile")
        self._ua_combo.setCurrentIndex(max(0, self._ua_combo.findData(self._settings.browser.ua_mode)))
        group2_layout.addWidget(self._row("浏览器标识", self._ua_combo))

        self._zoom_spin = QDoubleSpinBox()
        self._zoom_spin.setRange(0.5, 2.5)
        self._zoom_spin.setSingleStep(0.1)
        self._zoom_spin.setDecimals(1)
        self._zoom_spin.setValue(self._settings.browser.zoom)
        self._zoom_spin.setFixedWidth(120)
        group2_layout.addWidget(self._row("页面缩放", self._zoom_spin))

        self._chk_mute_start, row = self._checkbox("启动时默认静音", self._settings.browser.mute_on_start)
        group2_layout.addWidget(self._with_switch(row, self._chk_mute_start))
        layout.addWidget(group2)

        group3 = QGroupBox("下载")
        group3_layout = QVBoxLayout(group3)
        group3_layout.setSpacing(8)
        download_row = QWidget()
        download_layout = QHBoxLayout(download_row)
        download_layout.setContentsMargins(0, 0, 0, 0)
        download_layout.setSpacing(8)
        name = QLabel("保存到")
        name.setFixedWidth(118)
        self._download_edit = QLineEdit(self._settings.browser.download_dir)
        self._download_edit.setPlaceholderText("留空则保存到系统「下载」文件夹")
        browse = QPushButton("浏览…")
        browse.setObjectName("ghost")
        browse.clicked.connect(self._pick_download_dir)
        download_layout.addWidget(name)
        download_layout.addWidget(self._download_edit, 1)
        download_layout.addWidget(browse)
        group3_layout.addWidget(download_row)
        group3_layout.addWidget(self._hint("登录状态、Cookie 与缓存都保存在 data/webengine 下，不会上传。"))
        layout.addWidget(group3)
        layout.addStretch(1)
        return page

    def _pick_download_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择下载目录", self._download_edit.text() or str(Path.home()))
        if directory:
            self._download_edit.setText(directory)

    # ------------------------------------------------------------------ 外观
    def _build_disguise_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 12, 6, 12)
        layout.setSpacing(10)

        layout.addWidget(
            self._hint(
                "把左上角图标、窗口标题和任务栏图标伪装成常用软件。"
                "重启一次后，任务栏的分组身份也会完全换成新的。"
            )
        )

        self._disguise_list = QListWidget()
        self._disguise_list.setIconSize(QSize(38, 38))
        self._disguise_list.setSpacing(2)
        self._disguise_list.setMinimumHeight(330)
        self._disguise_list.setStyleSheet(
            "QListWidget { background:#141922; border:1px solid #242C38;"
            " border-radius:10px; padding:6px; outline:none; }"
            "QListWidget::item { padding:8px 10px; border-radius:8px; color:#E9EFF7; }"
            "QListWidget::item:hover { background:#1A2029; }"
            "QListWidget::item:selected { background:#123B36; color:#5EEAD4; }"
        )
        for item_data in disguise.PRESETS.values():
            item = QListWidgetItem(
                theme.disguise_icon(item_data.id),
                f"{item_data.short}    ·    {item_data.subtitle}",
            )
            item.setData(Qt.ItemDataRole.UserRole, item_data.id)
            item.setSizeHint(QSize(0, 52))
            self._disguise_list.addItem(item)
            if item_data.id == self._settings.disguise.preset:
                self._disguise_list.setCurrentItem(item)
        self._disguise_list.currentItemChanged.connect(self._update_disguise_preview)
        layout.addWidget(self._disguise_list)

        preview = QFrame()
        preview.setObjectName("card")
        preview_layout = QHBoxLayout(preview)
        preview_layout.setContentsMargins(14, 10, 14, 10)
        preview_layout.setSpacing(12)
        self._disguise_preview_icon = QLabel()
        self._disguise_preview_icon.setFixedSize(36, 36)
        preview_layout.addWidget(self._disguise_preview_icon)
        preview_text = QVBoxLayout()
        preview_text.setSpacing(2)
        self._disguise_preview_name = QLabel("")
        self._disguise_preview_name.setStyleSheet("font-size:13px; font-weight:600;")
        self._disguise_preview_title = QLabel("")
        self._disguise_preview_title.setObjectName("dim")
        preview_text.addWidget(self._disguise_preview_name)
        preview_text.addWidget(self._disguise_preview_title)
        preview_layout.addLayout(preview_text, 1)
        layout.addWidget(preview)

        layout.addWidget(
            self._hint("切换后左侧品牌、窗口图标和托盘图标会一起变化；应用内的内容不会被改动。")
        )
        layout.addStretch(1)
        self._update_disguise_preview(self._disguise_list.currentItem(), None)
        return page

    def _update_disguise_preview(self, current, _previous) -> None:
        item_id = current.data(Qt.ItemDataRole.UserRole) if current is not None else "default"
        brand = disguise.get(item_id)
        self._disguise_preview_icon.setPixmap(
            theme.disguise_pixmap(brand.id, 72).scaled(
                36, 36, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
        )
        self._disguise_preview_name.setText(brand.name)
        self._disguise_preview_title.setText(f"窗口标题：{brand.base_title}")

    # ------------------------------------------------------------------ 应用
    def _build_apps_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 12, 6, 12)
        layout.setSpacing(10)

        layout.addWidget(
            self._hint("把 exe 拖进主窗口即可添加；老板键会把这些程序的窗口一起藏起来。")
        )

        self._apps_container = QVBoxLayout()
        self._apps_container.setSpacing(6)
        layout.addLayout(self._apps_container)

        add_button = QPushButton("＋ 添加应用…")
        add_button.setObjectName("ghost")
        add_button.setCursor(Qt.CursorShape.PointingHandCursor)
        add_button.clicked.connect(self._add_pinned_app)
        layout.addWidget(add_button, 0, Qt.AlignmentFlag.AlignLeft)

        self._chk_embed, embed_label = self._checkbox(
            "在摸鱼神器内打开（嵌入程序窗口）", self._settings.apps.embed
        )
        layout.addWidget(self._with_switch(embed_label, self._chk_embed))
        layout.addWidget(
            self._hint(
                "部分 Chromium / Electron 内核的客户端嵌入后可能黑屏或没有声音；"
                "失败时会自动保持独立窗口。关掉这个开关就全部按独立窗口启动。"
            )
        )
        layout.addStretch(1)
        self._rebuild_app_list()
        return page

    def _rebuild_app_list(self) -> None:
        self._clear_layout(self._apps_container)
        pinned = apps.load_apps(self._settings)
        if not pinned:
            empty = QLabel("还没有添加应用。\n把 exe 拖进主窗口，或点「添加应用…」。")
            empty.setObjectName("dim")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setMinimumHeight(96)
            self._apps_container.addWidget(empty)
            return
        for app in pinned:
            self._apps_container.addWidget(self._app_row(app))

    def _app_row(self, app) -> QWidget:
        card = QFrame()
        card.setObjectName("card")
        card.setFixedHeight(58)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(12, 8, 10, 8)
        layout.setSpacing(10)

        icon = QLabel()
        icon.setFixedSize(30, 30)
        icon.setPixmap(
            widgets.app_icon(app, 60).scaled(
                30, 30, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
        )
        layout.addWidget(icon)

        text_box = QVBoxLayout()
        text_box.setSpacing(0)
        name = QLabel(app.name)
        name.setStyleSheet("font-weight:600; font-size:12.5px; background:transparent;")
        path_text = app.exe if app.exists else f"{app.exe}（文件不见了）"
        path_label = QLabel(widgets.elide(path_text, 56))
        path_label.setStyleSheet(
            f"color:{theme.TEXT_MUTED if app.exists else theme.DANGER};"
            "font-size:10.5px; background:transparent;"
        )
        path_label.setToolTip(path_text)
        text_box.addWidget(name)
        text_box.addWidget(path_label)
        layout.addLayout(text_box, 1)

        browse = QPushButton("更换…")
        browse.setObjectName("ghost")
        browse.setFixedHeight(28)
        browse.setCursor(Qt.CursorShape.PointingHandCursor)
        browse.clicked.connect(lambda _=False, app_id=app.id: self._change_app_exe(app_id))
        layout.addWidget(browse)

        remove = QPushButton("移除")
        remove.setObjectName("danger")
        remove.setFixedHeight(28)
        remove.setCursor(Qt.CursorShape.PointingHandCursor)
        remove.clicked.connect(lambda _=False, app_id=app.id: self._remove_pinned_app(app_id))
        layout.addWidget(remove)
        return card

    def _add_pinned_app(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "选择应用",
            os_environ_program_files(),
            "程序或快捷方式 (*.exe *.lnk);;所有文件 (*)",
        )
        if not filename:
            return
        try:
            app, created = apps.add_path(self._settings, filename)
        except ValueError as exc:
            QMessageBox.warning(self, "无法添加", str(exc))
            return
        if not created:
            QMessageBox.information(self, "已经在列表里", f"{app.name} 已经添加过了。")
        self._rebuild_app_list()

    def _change_app_exe(self, app_id: str) -> None:
        app = apps.find_app(self._settings, app_id)
        if app is None:
            return
        filename, _ = QFileDialog.getOpenFileName(
            self,
            f"更换 {app.name} 的程序",
            str(Path(app.exe).parent),
            "程序或快捷方式 (*.exe *.lnk);;所有文件 (*)",
        )
        if not filename:
            return
        try:
            new_app, created = apps.add_path(self._settings, filename)
        except ValueError as exc:
            QMessageBox.warning(self, "无法更换", str(exc))
            return
        if not created:
            QMessageBox.information(self, "已经在列表里", f"{new_app.name} 已经添加过了。")
            return
        apps.remove(self._settings, app_id)
        self._rebuild_app_list()

    def _remove_pinned_app(self, app_id: str) -> None:
        apps.remove(self._settings, app_id)
        self._rebuild_app_list()

    # ------------------------------------------------------------------ 网站
    def _build_sites_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 12, 6, 12)
        layout.setSpacing(10)
        layout.addWidget(self._hint("内置网站会出现在首页；这里添加的网站也会同步到首页与侧栏。"))

        self._sites_container = QVBoxLayout()
        self._sites_container.setSpacing(6)
        layout.addLayout(self._sites_container)

        add_button = QPushButton("＋ 添加网站")
        add_button.setObjectName("ghost")
        add_button.setCursor(Qt.CursorShape.PointingHandCursor)
        add_button.clicked.connect(self._add_custom_site)
        layout.addWidget(add_button, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)
        self._rebuild_site_list()
        return page

    def _rebuild_site_list(self) -> None:
        self._clear_layout(self._sites_container)
        for entry in list(self._settings.custom_sites):
            card = QFrame()
            card.setObjectName("card")
            card.setFixedHeight(52)
            layout = QHBoxLayout(card)
            layout.setContentsMargins(12, 8, 10, 8)
            layout.setSpacing(10)
            icon = QLabel()
            icon.setFixedSize(26, 26)
            icon.setPixmap(
                theme.letter_pixmap(str(entry.get("name", "?"))[:1], str(entry.get("color") or theme.INDIGO)).scaled(
                    26, 26, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                )
            )
            layout.addWidget(icon)
            box = QVBoxLayout()
            box.setSpacing(0)
            name = QLabel(str(entry.get("name", "")))
            name.setStyleSheet("font-weight:600; font-size:12.5px; background:transparent;")
            url = QLabel(widgets.elide(str(entry.get("url", "")), 60))
            url.setStyleSheet(f"color:{theme.TEXT_DIM}; font-size:10.5px; background:transparent;")
            box.addWidget(name)
            box.addWidget(url)
            layout.addLayout(box, 1)
            remove = QPushButton("移除")
            remove.setObjectName("danger")
            remove.setFixedHeight(28)
            remove.setCursor(Qt.CursorShape.PointingHandCursor)
            remove.clicked.connect(lambda _=False, item=entry: self._remove_custom_site(item))
            layout.addWidget(remove)
            self._sites_container.addWidget(card)

    def _add_custom_site(self) -> None:
        dialog = AddSiteDialog(self, self._settings.browser.search_engine)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._settings.custom_sites.append(dialog.site())
        self._rebuild_site_list()

    def _remove_custom_site(self, entry: dict) -> None:
        self._settings.custom_sites = [item for item in self._settings.custom_sites if item != entry]
        self._rebuild_site_list()

    # ------------------------------------------------------------------ 关于
    def _build_about_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 16, 6, 12)
        layout.setSpacing(12)

        head = QHBoxLayout()
        logo = QLabel()
        logo.setFixedSize(64, 64)
        logo.setPixmap(
            theme.app_pixmap(192).scaled(
                64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
        )
        head.addWidget(logo)
        box = QVBoxLayout()
        box.setSpacing(2)
        name = QLabel(__app_name__)
        name.setObjectName("h2")
        version = QLabel(f"版本 {__version__} · 仅本地运行，不收集任何数据")
        version.setObjectName("muted")
        box.addWidget(name)
        box.addWidget(version)
        head.addLayout(box)
        head.addStretch(1)
        layout.addLayout(head)

        info = QGroupBox("数据位置")
        info_layout = QVBoxLayout(info)
        info_layout.setSpacing(6)
        path_label = QLabel(str(paths.data_dir()))
        path_label.setStyleSheet(f"color:{theme.TEXT_MUTED}; font-size:11.5px;")
        path_label.setWordWrap(True)
        open_button = QPushButton("打开数据目录")
        open_button.setObjectName("ghost")
        open_button.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(paths.data_dir())))
        )
        info_layout.addWidget(path_label)
        info_layout.addWidget(open_button, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(info)

        keys = QGroupBox("当前快捷键")
        keys_layout = QVBoxLayout(keys)
        keys_layout.setSpacing(4)
        for label, value in (
            ("老板键", self._settings.boss_key),
            ("隐身键", self._settings.stealth_key),
            ("刷新页面", "ctrl+r"),
            ("聚焦地址栏", "ctrl+l"),
            ("全屏视频", "f11"),
        ):
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.addWidget(QLabel(label), 0)
            row_layout.addStretch(1)
            chip = QLabel(format_hotkey(value))
            chip.setObjectName("pill")
            row_layout.addWidget(chip)
            keys_layout.addWidget(row)
        layout.addWidget(keys)

        note = self._hint(
            "本工具只是把视频网站放进一个自己的窗口，方便你在合适的时间休息。"
            "上班时间请以工作为先，遵守公司的网络与设备使用规定。"
        )
        layout.addWidget(note)
        layout.addStretch(1)
        return page

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        try:
            from .. import winapi

            winapi.set_dark_titlebar(int(self.winId()))
        except Exception:
            pass

    # ------------------------------------------------------------------ 保存
    def _on_save(self) -> None:
        boss_key = self._boss_edit.value()
        stealth_key = self._stealth_edit.value()
        if not boss_key or not stealth_key:
            QMessageBox.warning(self, "快捷键无效", "热键至少需要 Ctrl / Alt / Win 中的一个，再加一个按键。")
            return
        if boss_key == stealth_key:
            QMessageBox.warning(self, "快捷键冲突", "老板键和隐身键不能是同一个组合。")
            return

        settings = self._settings
        settings.boss_key = boss_key
        settings.stealth_key = stealth_key

        settings.boss.mute_audio = self._chk_mute_audio.isChecked()
        settings.boss.pause_media = self._chk_pause.isChecked()
        settings.boss.mute_others = self._chk_mute_others.isChecked()
        settings.boss.hide_external = self._chk_hide_external.isChecked()
        settings.boss.decoy = self._chk_decoy.isChecked()
        settings.boss.decoy_style = self._decoy_style.currentData()

        stealth = settings.stealth
        stealth.enabled = self._chk_stealth.isChecked()
        stealth.trigger = self._trigger_combo.currentData()
        stealth.leave_delay_ms = self._leave_delay.value()
        stealth.idle_seconds = self._idle_seconds.value()
        stealth.hot_corner = self._corner_combo.currentData()
        stealth.hot_corner_size = self._corner_size.value()
        stealth.hot_corner_span = self._corner_span.value()
        stealth.dwell_ms = self._dwell.value()
        stealth.show_edge_marker = self._chk_marker.isChecked()

        browser_settings = settings.browser
        engine = self._search_combo.currentData()
        home = self._home_edit.text().strip()
        start = self._start_edit.text().strip()
        for label, value in (("首页地址", home), ("启动时打开", start)):
            if value and not looks_like_url(value) and not value.lower().startswith("file://"):
                QMessageBox.warning(
                    self,
                    "网址无效",
                    f"{label}看起来不是有效网址。\n可以写 https://www.iqiyi.com/ 或 www.iqiyi.com。",
                )
                return
        browser_settings.home_url = normalize_input(home, engine) if home else ""
        browser_settings.start_url = normalize_input(start, engine) if start else ""
        browser_settings.search_engine = engine
        browser_settings.ua_mode = self._ua_combo.currentData()
        browser_settings.zoom = self._zoom_spin.value()
        browser_settings.download_dir = self._download_edit.text().strip()
        browser_settings.mute_on_start = self._chk_mute_start.isChecked()

        settings.window.always_on_top = self._chk_topmost.isChecked()
        settings.window.start_maximized = self._chk_start_max.isChecked()
        settings.window.close_action = self._close_combo.currentData()
        settings.window.opacity = self._opacity.value()
        settings.apps.embed = self._chk_embed.isChecked()

        item = self._disguise_list.currentItem()
        settings.disguise.preset = (
            item.data(Qt.ItemDataRole.UserRole) if item is not None else "default"
        )

        settings.normalize()
        self.accept()

    def result_settings(self) -> Settings:
        return self._settings

    @staticmethod
    def _clear_layout(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            elif item.layout() is not None:
                SettingsDialog._clear_layout(item.layout())


def os_environ_program_files() -> str:
    import os

    return os.environ.get("ProgramFiles", "C:\\Program Files")
