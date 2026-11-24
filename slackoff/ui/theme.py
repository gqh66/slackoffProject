"""配色、图标与全局样式表。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import QApplication

BG = "#0D1016"
SURFACE = "#141922"
SURFACE_2 = "#1A2029"
SURFACE_3 = "#202836"
BORDER = "#242C38"
BORDER_SOFT = "#1B222D"
TEXT = "#E9EFF7"
TEXT_MUTED = "#8FA0B5"
TEXT_DIM = "#64748B"
ACCENT = "#5EEAD4"
ACCENT_SOFT = "#123B36"
ACCENT_DEEP = "#0F766E"
INDIGO = "#7C9CFF"
DANGER = "#FF6B6B"
WARN = "#FFB020"
GREEN = "#4ADE80"

UI_FONT = "Microsoft YaHei UI"
MONO_FONT = "Consolas"


def _pick_font() -> str:
    families = set(QFontDatabase.families())
    for name in (UI_FONT, "Microsoft YaHei", "PingFang SC", "Noto Sans SC", "Segoe UI"):
        if name in families:
            return name
    return "Segoe UI"


QSS = f"""
QWidget {{
    color: {TEXT};
    font-size: 13px;
}}
QMainWindow, QDialog {{
    background: {BG};
}}
QFrame#sidebar {{
    background: #10151D;
    border-right: 1px solid {BORDER_SOFT};
}}
QFrame#topbar {{
    background: {BG};
    border-bottom: 1px solid {BORDER_SOFT};
}}
QFrame#statusbar {{
    background: #0B0E14;
    border-top: 1px solid {BORDER_SOFT};
}}
QFrame#card {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 14px;
}}
QFrame#card[hovered="true"] {{
    background: #161D27;
    border-color: {ACCENT_DEEP};
}}
QFrame#hero {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #12242B, stop:0.55 #121A24, stop:1 #161A2A);
    border: 1px solid #23333D;
    border-radius: 16px;
}}
QFrame#tip {{
    background: #121A16;
    border: 1px solid #1F3A31;
    border-radius: 12px;
}}
QFrame#dropZone {{
    background: #10151D;
    border: 1px dashed #2E3A4A;
    border-radius: 12px;
}}
QLabel#h1 {{
    font-size: 25px;
    font-weight: 700;
}}
QLabel#h2 {{
    font-size: 17px;
    font-weight: 700;
}}
QLabel#section {{
    color: {TEXT_DIM};
    font-size: 11px;
    font-weight: 600;
    padding: 2px 4px;
}}
QLabel#muted {{
    color: {TEXT_MUTED};
    font-size: 12px;
}}
QLabel#dim {{
    color: {TEXT_DIM};
    font-size: 11px;
}}
QLabel#pill {{
    background: {SURFACE_2};
    border: 1px solid {BORDER};
    border-radius: 9px;
    color: {TEXT_MUTED};
    font-size: 11px;
    padding: 3px 8px;
}}
QLabel#pillAccent {{
    background: {ACCENT_SOFT};
    border: 1px solid #1C5A50;
    border-radius: 9px;
    color: {ACCENT};
    font-size: 11px;
    padding: 3px 8px;
}}
QLineEdit {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 8px 12px;
    color: {TEXT};
    selection-background-color: #2C4A5A;
}}
QLineEdit:focus {{
    border-color: #2E6E63;
    background: #151B24;
}}
QLineEdit:disabled {{
    color: {TEXT_DIM};
}}
QPushButton {{
    background: {SURFACE_2};
    border: 1px solid #2A3441;
    border-radius: 9px;
    padding: 7px 14px;
    color: {TEXT};
}}
QPushButton:hover {{
    background: #222B37;
    border-color: #3A4757;
}}
QPushButton:pressed {{
    background: #18202A;
}}
QPushButton:disabled {{
    color: {TEXT_DIM};
    border-color: {BORDER};
    background: {SURFACE};
}}
QPushButton#primary {{
    background: {ACCENT};
    border: none;
    color: #062420;
    font-weight: 600;
}}
QPushButton#primary:hover {{
    background: #7FF3E0;
}}
QPushButton#ghost {{
    background: transparent;
    border: 1px solid #2A3441;
}}
QPushButton#ghost:hover {{
    background: {SURFACE_2};
}}
QPushButton#danger {{
    background: transparent;
    border: 1px solid #4A2626;
    color: {DANGER};
}}
QPushButton#danger:hover {{
    background: #2A1616;
}}
QToolButton {{
    background: transparent;
    border: none;
    border-radius: 8px;
    padding: 6px;
    color: #A9B8CB;
}}
QToolButton:hover {{
    background: {SURFACE_2};
    color: {TEXT};
}}
QToolButton:pressed {{
    background: #10151D;
}}
QToolButton:checked {{
    background: {ACCENT_SOFT};
    color: {ACCENT};
}}
QToolButton:disabled {{
    color: #3C4756;
}}
QScrollArea {{
    border: none;
    background: transparent;
}}
QScrollArea > QWidget > QWidget {{
    background: transparent;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #2A3441;
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: #3A4757;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: #2A3441;
    border-radius: 4px;
    min-width: 30px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}
QCheckBox {{
    spacing: 8px;
    color: {TEXT};
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid #33404F;
    border-radius: 5px;
    background: {SURFACE};
}}
QCheckBox::indicator:hover {{
    border-color: #46586B;
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}
QComboBox, QSpinBox, QDoubleSpinBox {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 6px 10px;
    min-height: 20px;
    color: {TEXT};
}}
QComboBox {{
    padding-right: 26px;
}}
QSpinBox, QDoubleSpinBox {{
    padding-right: 26px;
}}
QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {{
    border-color: #34414F;
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    border: none;
    width: 24px;
}}
QComboBox::down-arrow {{
    image: url("__ARROW_DOWN__");
    width: 12px;
    height: 12px;
    margin-right: 8px;
}}
QComboBox::down-arrow:on {{
    image: url("__ARROW_DOWN_ACCENT__");
}}
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 20px;
    background: {SURFACE_2};
    border-left: 1px solid {BORDER};
    border-top-right-radius: 8px;
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 20px;
    background: {SURFACE_2};
    border-left: 1px solid {BORDER};
    border-bottom-right-radius: 8px;
}}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
    background: {SURFACE_3};
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: url("__ARROW_UP__");
    width: 10px;
    height: 8px;
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: url("__ARROW_DOWN__");
    width: 10px;
    height: 8px;
}}
QComboBox QAbstractItemView {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
    selection-background-color: {SURFACE_3};
    selection-color: {TEXT};
    outline: none;
    padding: 4px;
}}
QTabWidget::pane {{
    border: none;
    background: transparent;
    top: -1px;
}}
QTabBar::tab {{
    background: transparent;
    color: {TEXT_MUTED};
    padding: 10px 16px;
    margin-right: 4px;
    border: none;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:hover {{
    color: #D6E2F0;
}}
QTabBar::tab:selected {{
    color: {TEXT};
    border-bottom: 2px solid {ACCENT};
}}
QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: 12px;
    margin-top: 14px;
    padding: 14px 14px 10px 14px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: {TEXT_MUTED};
}}
QMenu {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 6px;
}}
QMenu::item {{
    padding: 7px 20px;
    border-radius: 6px;
}}
QMenu::item:selected {{
    background: {SURFACE_3};
}}
QMenu::separator {{
    height: 1px;
    background: {BORDER};
    margin: 6px 8px;
}}
QToolTip {{
    background: #10151D;
    color: #D6E2F0;
    border: 1px solid #2A3441;
    padding: 5px 8px;
    border-radius: 6px;
    font-size: 12px;
}}
QProgressBar {{
    background: {SURFACE_2};
    border: none;
    border-radius: 2px;
    height: 3px;
}}
QProgressBar::chunk {{
    background: {ACCENT};
    border-radius: 2px;
}}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    family = _pick_font()
    font = QFont(family, 10)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(font)

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(BG))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Base, QColor(SURFACE))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(SURFACE_2))
    palette.setColor(QPalette.ColorRole.Text, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Button, QColor(SURFACE_2))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT_DEEP))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#10151D"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(TEXT_DIM))
    palette.setColor(QPalette.ColorRole.Link, QColor(ACCENT))
    app.setPalette(palette)

    arrows = _ensure_arrows()
    stylesheet = (
        QSS.replace("__ARROW_DOWN_ACCENT__", arrows["down_accent"])
        .replace("__ARROW_DOWN__", arrows["down"])
        .replace("__ARROW_UP__", arrows["up"])
    )
    app.setStyleSheet(stylesheet)


def _ensure_arrows() -> dict[str, str]:
    """生成下拉/微调按钮用的小箭头图片（QSS 的 border 三角形在 Fusion 下不可靠）。"""
    from .. import paths

    try:
        folder = paths.data_dir() / "ui"
        folder.mkdir(parents=True, exist_ok=True)
    except Exception:
        return {"down": "", "down_accent": "", "up": ""}

    result: dict[str, str] = {}
    for name, direction, color in (
        ("down", "down", TEXT_MUTED),
        ("down_accent", "down", ACCENT),
        ("up", "up", TEXT_MUTED),
    ):
        path = folder / f"chevron-{name}.png"
        try:
            _draw_chevron(path, direction, color)
            result[name] = path.as_posix()
        except Exception:
            result[name] = ""
    return result


def _draw_chevron(path: Path, direction: str, color: str) -> None:
    size = 48
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(color))
    pen.setWidth(6)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    if direction == "up":
        points = (QPointF(12, 32), QPointF(24, 18), QPointF(36, 32))
    else:
        points = (QPointF(12, 18), QPointF(24, 32), QPointF(36, 18))
    painter.drawPolyline(QPolygonF(list(points)))
    painter.end()
    if not pixmap.save(str(path)):
        raise OSError(f"无法写入 {path}")


# ---------------------------------------------------------------------- 图标
@lru_cache(maxsize=64)
def letter_pixmap(text: str, color: str, size: int = 128) -> QPixmap:
    """品牌色圆角方块 + 首字，用来代替各家的 logo 图片。"""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    base = QColor(color)
    gradient = QLinearGradient(0, 0, size, size)
    gradient.setColorAt(0.0, base.lighter(118))
    gradient.setColorAt(1.0, base.darker(112))
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), size * 0.28, size * 0.28)
    painter.fillPath(path, gradient)

    pen = QPen(QColor(255, 255, 255, 30))
    pen.setWidth(max(1, size // 64))
    painter.setPen(pen)
    painter.drawPath(path)

    font = QFont(_pick_font())
    font.setPixelSize(int(size * 0.46))
    font.setWeight(QFont.Weight.Bold)
    painter.setFont(font)
    painter.setPen(QColor(255, 255, 255, 235))
    painter.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, text[:1])
    painter.end()
    return pixmap


def letter_icon(text: str, color: str) -> QIcon:
    return QIcon(letter_pixmap(text, color))


@lru_cache(maxsize=4)
def app_pixmap(size: int = 128) -> QPixmap:
    """一条戴耳机的鱼（大概）。"""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    gradient = QLinearGradient(0, 0, size, size)
    gradient.setColorAt(0.0, QColor("#5EEAD4"))
    gradient.setColorAt(1.0, QColor("#6D8BFF"))
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), size * 0.26, size * 0.26)
    painter.fillPath(path, gradient)

    scale = size / 128.0
    painter.scale(scale, scale)
    painter.setPen(Qt.PenStyle.NoPen)

    # 尾巴
    tail = QPainterPath()
    tail.moveTo(66, 64)
    tail.lineTo(100, 42)
    tail.lineTo(100, 86)
    tail.closeSubpath()
    painter.setBrush(QColor(255, 255, 255, 200))
    painter.drawPath(tail)

    # 身体
    body = QPainterPath()
    body.addEllipse(QRectF(22, 38, 66, 52))
    painter.setBrush(QColor(255, 255, 255, 235))
    painter.drawPath(body)

    # 眼睛
    painter.setBrush(QColor("#0D2B28"))
    painter.drawEllipse(QRectF(36, 54, 10, 10))

    # 鳃线
    pen = QPen(QColor(13, 43, 40, 90))
    pen.setWidth(4)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.drawArc(QRectF(48, 46, 30, 36), 60 * 16, 120 * 16)
    painter.end()
    return pixmap


@lru_cache(maxsize=8)
def book_pixmap(size: int = 128, color: str = "#C99A3C") -> QPixmap:
    """一本小书，用来当 txt 电子书的图标。"""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    scale = size / 128.0
    painter.scale(scale, scale)

    cover = QLinearGradient(18, 14, 110, 114)
    cover.setColorAt(0.0, QColor(color).lighter(115))
    cover.setColorAt(1.0, QColor(color).darker(112))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(cover)
    painter.drawRoundedRect(QRectF(18, 14, 92, 100), 10, 10)

    painter.setBrush(QColor("#F7E9C4"))
    painter.drawRoundedRect(QRectF(36, 22, 62, 84), 3, 3)

    line_pen = QPen(QColor("#D8C48E"))
    line_pen.setWidth(2)
    painter.setPen(line_pen)
    for y in (38, 50, 62, 74, 86):
        painter.drawLine(46, y, 88, y)

    spine = QPen(QColor("#8C6420"))
    spine.setWidth(3)
    painter.setPen(spine)
    painter.drawLine(36, 22, 36, 106)

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#E06B5A"))
    painter.drawRoundedRect(QRectF(84, 14, 13, 26), 2, 2)
    painter.end()
    return pixmap


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(app_pixmap(size))
    return icon


@lru_cache(maxsize=64)
def disguise_pixmap(preset: str, size: int = 128) -> QPixmap:
    """伪装成常用软件时用的图标（全部本地绘制，不依赖是否安装 Office）。"""
    if preset == "default":
        return app_pixmap(size)

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.scale(size / 128.0, size / 128.0)

    def background(top: str, bottom: str) -> None:
        gradient = QLinearGradient(0, 0, 128, 128)
        gradient.setColorAt(0.0, QColor(top))
        gradient.setColorAt(1.0, QColor(bottom))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawRoundedRect(QRectF(0, 0, 128, 128), 26, 26)

    def text(content: str, pixel: int) -> None:
        font = QFont("Segoe UI")
        font.setPixelSize(pixel)
        font.setWeight(QFont.Weight.Bold)
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255, 240))
        painter.drawText(QRectF(0, 0, 128, 128), Qt.AlignmentFlag.AlignCenter, content)

    if preset == "excel":
        background("#217346", "#185C37")
        grid = QPen(QColor(255, 255, 255, 70))
        grid.setWidth(2)
        painter.setPen(grid)
        for value in (34, 62, 90):
            painter.drawLine(value, 18, value, 110)
            painter.drawLine(18, value, 110, value)
        painter.setPen(Qt.PenStyle.NoPen)
        text("X", 62)
    elif preset == "wps":
        background("#E23B2E", "#B92A20")
        text("WPS" if size >= 96 else "W", 32 if size >= 96 else 66)
    elif preset == "word":
        background("#2B579A", "#1E3F73")
        text("W", 64)
    elif preset == "notepad":
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#F7F9FC"))
        painter.drawRoundedRect(QRectF(10, 10, 108, 108), 14, 14)
        painter.setBrush(QColor("#4A90D9"))
        painter.drawRoundedRect(QRectF(10, 10, 108, 26), 14, 14)
        painter.setBrush(QColor("#F7F9FC"))
        painter.drawRect(QRectF(10, 24, 108, 12))
        line = QPen(QColor("#9AA7B8"))
        line.setWidth(3)
        painter.setPen(line)
        for y in (52, 70, 88):
            painter.drawLine(26, y, 102, y)
    elif preset == "vscode":
        background("#007ACC", "#005A9E")
        pen = QPen(QColor(255, 255, 255, 235))
        pen.setWidth(7)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.drawPolyline(
            QPolygonF([QPointF(53, 40), QPointF(30, 64), QPointF(53, 88)])
        )
        painter.drawPolyline(
            QPolygonF([QPointF(75, 40), QPointF(98, 64), QPointF(75, 88)])
        )
    else:
        painter.end()
        return app_pixmap(size)

    painter.end()
    return pixmap


def disguise_icon(preset: str) -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(disguise_pixmap(preset, size))
    return icon
