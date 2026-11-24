"""隐身模式控制器。

规则很简单：
* 鼠标离开窗口超过 N 毫秒 → 触发隐藏（也可以改成「鼠标静止 N 秒」）。
* 隐藏后在屏幕边缘留一条极细的「回魂条」，鼠标碰到对应边缘就自动回来。
  提示条只在刚隐藏时显示几秒，之后就靠快捷键 / 托盘图标唤回。

隐藏动作本身由主窗口执行（静音、暂停等），这里只负责判断时机。
"""

from __future__ import annotations

import logging
import time

from PySide6.QtCore import QObject, QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QLinearGradient, QPainter
from PySide6.QtWidgets import QApplication, QWidget

log = logging.getLogger(__name__)


def hot_corner_rect(screen_rect: QRect, edge: str, size: int, span: float) -> QRect:
    """算出「回魂条」的命中区域（逻辑像素）。"""
    if edge == "none" or screen_rect.isEmpty():
        return QRect()
    size = max(2, int(size))
    span = min(1.0, max(0.05, float(span)))
    width, height = screen_rect.width(), screen_rect.height()
    if edge in ("left", "right"):
        length = max(40, int(height * span))
        top = screen_rect.top() + (height - length) // 2
        left = screen_rect.left() if edge == "left" else screen_rect.right() - size + 1
        return QRect(left, top, size, length)
    length = max(40, int(width * span))
    left = screen_rect.left() + (width - length) // 2
    top = screen_rect.top() if edge == "top" else screen_rect.bottom() - size + 1
    return QRect(left, top, length, size)


class EdgeMarker(QWidget):
    """隐身时贴在屏幕边缘的一条提示光带（鼠标可穿透）。"""

    def __init__(self) -> None:
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self._edge = "left"

    def place(self, screen_rect: QRect, edge: str, size: int, span: float) -> None:
        self._edge = edge
        hit = hot_corner_rect(screen_rect, edge, size, span)
        if hit.isEmpty():
            self.hide()
            return
        # 命中区可以宽一点，但提示光带保持纤细，不打扰
        thickness = max(2, min(5, int(size)))
        if edge in ("left", "right"):
            self.setGeometry(hit.x(), hit.y(), thickness, hit.height())
        else:
            self.setGeometry(hit.x(), hit.y(), hit.width(), thickness)

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt 命名)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect()
        gradient = QLinearGradient(0, 0, rect.width(), rect.height())
        if self._edge in ("left", "right"):
            gradient = QLinearGradient(0, 0, 0, rect.height())
        accent = QColor("#5EEAD4")
        accent.setAlpha(0)
        gradient.setColorAt(0.0, accent)
        accent.setAlpha(210)
        gradient.setColorAt(0.5, accent)
        gradient.setColorAt(1.0, QColor(94, 234, 212, 0))
        painter.fillRect(rect, gradient)
        painter.end()


class StealthController(QObject):
    hideRequested = Signal(str)   # "leave" / "idle"
    showRequested = Signal(str)   # "hotcorner"

    def __init__(self, window: QWidget, settings, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._window = window
        self._settings = settings
        self._timer = QTimer(self)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self._tick)

        self._visible = True
        self._hidden_by_stealth = False
        self._armed = False
        self._left_at: float | None = None
        self._corner_since: float | None = None
        self._last_cursor: QPoint | None = None
        self._last_move = time.monotonic()

        self.marker = EdgeMarker()
        self._marker_timer = QTimer(self)
        self._marker_timer.setSingleShot(True)
        self._marker_timer.timeout.connect(self.marker.hide)
        self._extra_inside = None

    # ------------------------------------------------------------------ 控制
    def set_extra_inside(self, provider) -> None:
        """额外算作「窗口内」的区域（例如盖在内容区的系统内核窗口）。"""
        self._extra_inside = provider

    def set_settings(self, settings) -> None:
        """设置对话框保存后，主窗口换成了新的 Settings 对象，这里要同步过来。"""
        self._settings = settings
        self.refresh()

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()
        self._last_cursor = QCursor.pos()
        self._last_move = time.monotonic()

    def stop(self) -> None:
        self._timer.stop()
        self.marker.hide()

    def set_visible(self, visible: bool) -> None:
        self._visible = visible
        if visible:
            self._armed = False
            self._left_at = None
            self._hidden_by_stealth = False
            self._corner_since = None
            self.marker.hide()
        else:
            self._armed = False
            self._left_at = None

    def notify_hidden_by_stealth(self) -> None:
        self._hidden_by_stealth = True
        cfg = self._settings.stealth
        if cfg.hot_corner != "none" and cfg.show_edge_marker:
            self._place_marker()
            self.marker.show()
            self._marker_timer.start(4000)

    def refresh(self) -> None:
        """设置改变后调用，让隐藏中的提示条跟着变化。"""
        if self._hidden_by_stealth and not self._visible:
            cfg = self._settings.stealth
            if cfg.hot_corner != "none" and cfg.show_edge_marker:
                self._place_marker()
            else:
                self.marker.hide()

    # ------------------------------------------------------------------ 判断
    def _place_marker(self) -> None:
        screen = self._window.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        cfg = self._settings.stealth
        self.marker.place(screen.availableGeometry(), cfg.hot_corner, cfg.hot_corner_size, cfg.hot_corner_span)

    def _corner_rect(self) -> QRect:
        screen = self._window.screen() or QApplication.primaryScreen()
        if screen is None:
            return QRect()
        cfg = self._settings.stealth
        return hot_corner_rect(screen.availableGeometry(), cfg.hot_corner, cfg.hot_corner_size, cfg.hot_corner_span)

    def _inside_window(self, pos: QPoint) -> bool:
        if not self._window.isVisible():
            return False
        if self._window.frameGeometry().adjusted(-2, -2, 2, 2).contains(pos):
            return True
        if self._extra_inside is not None:
            try:
                rect = self._extra_inside()
            except Exception:
                return False
            if rect is not None and not rect.isEmpty() and rect.contains(pos):
                return True
        return False

    def _tick(self) -> None:
        cfg = self._settings.stealth
        now = time.monotonic()
        pos = QCursor.pos()
        if self._last_cursor != pos:
            self._last_cursor = pos
            self._last_move = now

        if not self._visible:
            if not self._hidden_by_stealth or cfg.hot_corner == "none" or not cfg.enabled:
                return
            rect = self._corner_rect()
            if rect.contains(pos):
                if self._corner_since is None:
                    self._corner_since = now
                    log.debug("回魂条命中 %s（区域 %s）", pos, rect)
                elif (now - self._corner_since) * 1000 >= cfg.dwell_ms:
                    self._corner_since = None
                    log.info("鼠标停在回魂条上，唤回窗口")
                    self.showRequested.emit("hotcorner")
            else:
                if self._corner_since is not None:
                    log.debug("离开回魂条")
                self._corner_since = None
            return

        self._corner_since = None
        if not cfg.enabled:
            self._left_at = None
            self._armed = False
            return
        if self._window.isMinimized():
            self._left_at = None
            self._armed = False
            return
        if QApplication.activeModalWidget() is not None or QApplication.activePopupWidget() is not None:
            self._left_at = None
            self._armed = False
            return
        if QApplication.mouseButtons() != Qt.MouseButton.NoButton:
            self._left_at = None
            return

        if cfg.trigger == "idle":
            if (now - self._last_move) >= cfg.idle_seconds:
                log.debug("鼠标静止 %d 秒，进入隐身", cfg.idle_seconds)
                self._last_move = now
                self.hideRequested.emit("idle")
            return

        if self._inside_window(pos):
            self._armed = True
            self._left_at = None
            return
        if not self._armed:
            # 刚从隐身状态回来时鼠标还在窗口外，等它进来过一次再开始计时，
            # 否则会「一唤回就马上又隐藏」。
            return
        if self._left_at is None:
            self._left_at = now
        elif (now - self._left_at) * 1000 >= cfg.leave_delay_ms:
            self._left_at = None
            self._armed = False
            log.debug("鼠标离开窗口 %d ms，进入隐身", cfg.leave_delay_ms)
            self.hideRequested.emit("leave")
