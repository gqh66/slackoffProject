"""界面里可复用的小部件。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFileInfo, QRectF, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QPainter
from PySide6.QtWidgets import (
    QAbstractButton,
    QFileIconProvider,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .. import books

_ICON_PROVIDER: QFileIconProvider | None = None


def app_icon_pixmap(exe: str, size: int = 64):
    """直接取 exe 自带的图标；拿不到返回 None。"""
    global _ICON_PROVIDER
    try:
        if _ICON_PROVIDER is None:
            _ICON_PROVIDER = QFileIconProvider()
        icon = _ICON_PROVIDER.icon(QFileInfo(exe))
        if icon.isNull():
            return None
        pixmap = icon.pixmap(size, size)
        return None if pixmap.isNull() else pixmap
    except Exception:
        return None


def app_icon(app, size: int = 64):
    pixmap = app_icon_pixmap(getattr(app, "exe", ""), size)
    if pixmap is not None:
        return pixmap
    return theme.letter_pixmap(getattr(app, "name", "?")[:1], getattr(app, "color", theme.INDIGO), size)


def _repolish(widget: QWidget) -> None:
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def elide(text: str, limit: int = 64) -> str:
    text = text or ""
    return text if len(text) <= limit else "…" + text[-(limit - 1):]


def shorten(text: str, limit: int = 20) -> str:
    """从尾部截断，保留开头（适合程序名 / 文件名）。"""
    text = text or ""
    return text if len(text) <= limit else text[: max(1, limit - 1)] + "…"


def divider() -> QFrame:
    line = QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet(f"background: {theme.BORDER_SOFT};")
    return line


class HoverCard(QFrame):
    """带悬停高亮与点击事件的卡片。"""

    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pressed = False

    def enterEvent(self, event) -> None:  # noqa: N802
        self.setProperty("hovered", True)
        _repolish(self)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.setProperty("hovered", False)
        _repolish(self)
        self._pressed = False
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._pressed and event.button() == Qt.MouseButton.LeftButton:
            self._pressed = False
            if self.rect().contains(event.position().toPoint()):
                self.clicked.emit()
        super().mouseReleaseEvent(event)


class AppRow(HoverCard):
    """侧栏里的一行应用：exe 图标 + 名字 + 文件名。"""

    removeRequested = Signal(str)
    revealRequested = Signal(str)

    def __init__(self, app, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app = app
        self.setFixedHeight(54)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 10, 6)
        layout.setSpacing(10)

        self._icon = QLabel()
        self._icon.setFixedSize(32, 32)
        self._icon.setPixmap(
            app_icon(app, 64).scaled(
                32, 32, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
        )
        layout.addWidget(self._icon)

        text_box = QVBoxLayout()
        text_box.setSpacing(1)
        text_box.setContentsMargins(0, 0, 0, 0)
        self._name = QLabel(shorten(app.name, 14))
        self._name.setStyleSheet("font-size:13px; font-weight:600; background:transparent;")
        self._status = QLabel()
        self._status.setStyleSheet("font-size:11px; background:transparent;")
        text_box.addWidget(self._name)
        text_box.addWidget(self._status)
        layout.addLayout(text_box, 1)

        self._arrow = QLabel("›")
        self._arrow.setStyleSheet(f"color:{theme.TEXT_DIM}; font-size:16px; background:transparent;")
        layout.addWidget(self._arrow)

        if app.exists:
            self._status.setText(f"● {shorten(Path(app.exe).name, 22)}")
            self._status.setStyleSheet(
                f"color:{theme.GREEN}; font-size:11px; background:transparent;"
            )
        else:
            self._status.setText("○ 文件不见了")
            self._status.setStyleSheet(
                f"color:{theme.DANGER}; font-size:11px; background:transparent;"
            )
        self.setToolTip(f"{app.name}\n{app.exe}\n\n单击打开 · 右键可移除")

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        menu = QMenu(self)
        open_action = menu.addAction("打开")
        open_action.triggered.connect(self.clicked.emit)
        reveal_action = menu.addAction("在资源管理器中显示")
        reveal_action.triggered.connect(self._reveal)
        menu.addSeparator()
        remove_action = menu.addAction("从列表移除")
        remove_action.triggered.connect(lambda: self.removeRequested.emit(self.app.id))
        menu.exec(event.globalPos())

    def _reveal(self) -> None:
        try:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self.app.exe).parent)))
        except Exception:
            pass


class BookRow(HoverCard):
    """侧栏「我的书」里的一行。"""

    removeRequested = Signal(str)

    def __init__(self, book, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.book = book
        self.setFixedHeight(48)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 5, 10, 5)
        layout.setSpacing(10)

        icon = QLabel()
        icon.setFixedSize(28, 28)
        icon.setPixmap(
            theme.book_pixmap(56).scaled(
                28, 28, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
        )
        layout.addWidget(icon)

        text_box = QVBoxLayout()
        text_box.setSpacing(1)
        text_box.setContentsMargins(0, 0, 0, 0)
        name = QLabel(shorten(book.name, 14))
        name.setStyleSheet("font-size:12.5px; font-weight:600; background:transparent;")
        status = QLabel(
            f"TXT · {books.format_size(book.path)}" if book.exists else "○ 文件不见了"
        )
        status.setStyleSheet(
            f"color:{theme.TEXT_MUTED if book.exists else theme.DANGER};"
            "font-size:10.5px; background:transparent;"
        )
        text_box.addWidget(name)
        text_box.addWidget(status)
        layout.addLayout(text_box, 1)

        arrow = QLabel("›")
        arrow.setStyleSheet(f"color:{theme.TEXT_DIM}; font-size:16px; background:transparent;")
        layout.addWidget(arrow)
        self.setToolTip(f"{book.name}\n{book.path}\n\n单击阅读 · 右键可移除")

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        menu = QMenu(self)
        open_action = menu.addAction("阅读")
        open_action.triggered.connect(self.clicked.emit)
        reveal_action = menu.addAction("在资源管理器中显示")
        reveal_action.triggered.connect(self._reveal)
        menu.addSeparator()
        remove_action = menu.addAction("从书架移除")
        remove_action.triggered.connect(lambda: self.removeRequested.emit(self.book.id))
        menu.exec(event.globalPos())

    def _reveal(self) -> None:
        try:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self.book.path).parent)))
        except Exception:
            pass


class SiteRow(HoverCard):
    """侧栏里的一行网站。"""

    def __init__(self, site, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.site = site
        self.setFixedHeight(40)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 10, 4)
        layout.setSpacing(10)

        icon = QLabel()
        icon.setFixedSize(24, 24)
        icon.setPixmap(
            theme.letter_pixmap(site.initial, site.color).scaled(
                24, 24, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
        )
        layout.addWidget(icon)

        name = QLabel(site.name)
        name.setStyleSheet("font-size:12.5px; background:transparent;")
        layout.addWidget(name, 1)

        dot = QLabel("↗")
        dot.setStyleSheet(f"color:{theme.TEXT_DIM}; font-size:11px; background:transparent;")
        layout.addWidget(dot)
        self.setToolTip(site.url)


class SiteTile(HoverCard):
    """首页上的网站大卡片。"""

    def __init__(self, site, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.site = site
        self.setMinimumHeight(94)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 10)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(8)
        icon = QLabel()
        icon.setFixedSize(36, 36)
        icon.setPixmap(
            theme.letter_pixmap(site.initial, site.color).scaled(
                36, 36, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
        )
        header.addWidget(icon)
        header.addStretch(1)
        arrow = QLabel("↗")
        arrow.setStyleSheet(f"color:{theme.TEXT_DIM}; font-size:12px; background:transparent;")
        header.addWidget(arrow)
        layout.addLayout(header)

        name = QLabel(site.name)
        name.setStyleSheet("font-size:13.5px; font-weight:600; background:transparent;")
        note = QLabel(site.note or site.url)
        note.setStyleSheet(f"color:{theme.TEXT_DIM}; font-size:11px; background:transparent;")
        layout.addWidget(name)
        layout.addWidget(note)
        self.setToolTip(site.url)


class ClickableLabel(QLabel):
    """看起来像普通文字、但可以点击的 QLabel。"""

    clicked = Signal()

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            if self.rect().contains(event.position().toPoint()):
                self.clicked.emit()
        super().mouseReleaseEvent(event)

    def enterEvent(self, event) -> None:  # noqa: N802
        font = self.font()
        font.setUnderline(True)
        self.setFont(font)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        font = self.font()
        font.setUnderline(False)
        self.setFont(font)
        super().leaveEvent(event)


class SectionHeader(QWidget):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 6, 4, 2)
        layout.setSpacing(6)
        label = QLabel(title)
        label.setObjectName("section")
        layout.addWidget(label)
        self.count = QLabel("")
        self.count.setObjectName("dim")
        layout.addWidget(self.count)
        layout.addStretch(1)

    def set_count(self, value: int | str) -> None:
        self.count.setText(str(value))


class Switch(QAbstractButton):
    """iOS 风格的开关。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(40, 22)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(40, 22)

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        enabled = self.isEnabled()
        checked = self.isChecked()
        rect = QRectF(1, 2, self.width() - 2, self.height() - 4)
        track = QColor(theme.ACCENT if checked else "#2B3542")
        if not enabled:
            track.setAlpha(90)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)

        knob_d = rect.height() - 4
        knob_x = rect.right() - knob_d - 2 if checked else rect.left() + 2
        painter.setBrush(QColor("#FFFFFF") if checked else QColor("#A9B8CB"))
        painter.drawEllipse(QRectF(knob_x, rect.top() + 2, knob_d, knob_d))
        painter.end()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.toggle()
            return
        super().keyPressEvent(event)


class StatCard(QFrame):
    def __init__(self, title: str, value: str, hint: str = "", accent: bool = False,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(3)

        self.title = QLabel(title)
        self.title.setObjectName("dim")
        self.value = QLabel(value)
        self.value.setStyleSheet(
            f"font-size:19px; font-weight:700; color:{theme.ACCENT if accent else theme.TEXT};"
            "background:transparent;"
        )
        self.hint = QLabel(hint)
        self.hint.setObjectName("dim")
        layout.addWidget(self.title)
        layout.addWidget(self.value)
        layout.addWidget(self.hint)

    def update_values(self, value: str, hint: str = "") -> None:
        self.value.setText(value)
        self.hint.setText(hint)


class TipRow(QWidget):
    def __init__(self, glyph: str, title: str, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(12)

        badge = QLabel(glyph)
        badge.setFixedSize(28, 28)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(
            f"background:{theme.SURFACE_2}; color:{theme.ACCENT}; border-radius:9px;"
            "font-size:13px; font-weight:600;"
        )
        layout.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)

        box = QVBoxLayout()
        box.setSpacing(2)
        title_label = QLabel(title)
        title_label.setStyleSheet("font-weight:600; font-size:12.5px; background:transparent;")
        text_label = QLabel(text)
        text_label.setWordWrap(True)
        text_label.setStyleSheet(f"color:{theme.TEXT_MUTED}; font-size:12px; background:transparent;")
        box.addWidget(title_label)
        box.addWidget(text_label)
        layout.addLayout(box, 1)


class HotkeyChip(QLabel):
    """展示快捷键的小胶囊。"""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("pill")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_hotkey(text)

    def set_hotkey(self, text: str) -> None:
        self.setText(f"⌨ {text}" if text else "")
        self.setVisible(bool(text))


class StatusDot(QLabel):
    def __init__(self, color: str = theme.GREEN, size: int = 8, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.set_color(color)

    def set_color(self, color: str) -> None:
        self.setStyleSheet(f"background:{color}; border-radius:{self.width() // 2}px;")
