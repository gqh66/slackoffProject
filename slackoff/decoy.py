"""伪装界面：老板键按下后，屏幕上出现的「我很忙」画面。

两个风格：
* ``code``  —— 一个假的编辑器，带终端构建日志（默认）
* ``excel`` —— 一个假的表格

纯本地绘制，不联网、不读文件，按 Esc 或再按一次老板键即可离开。
"""

from __future__ import annotations

import random
from datetime import datetime

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

CODE_BG = "#1E1E1E"
CODE_BG_ALT = "#252526"
TITLE_BG = "#323233"
GUTTER = "#1E1E1E"
STATUS_BG = "#007ACC"

TOKEN = {
    "kw": "#C586C0",
    "def": "#569CD6",
    "str": "#CE9178",
    "num": "#B5CEA8",
    "com": "#6A9955",
    "fn": "#DCDCAA",
    "var": "#9CDCFE",
    "txt": "#D4D4D4",
}


def _line(indent: int, *tokens: tuple[str, str]) -> list:
    return [indent, list(tokens)]


FAKE_CODE = [
    _line(0, ("# 摸鱼指数监控 · 别让老板发现", "com")),
    _line(0, ("from __future__ import annotations", "kw")),
    _line(0),
    _line(0, ("import ", "kw"), ("time", "var"), (", ", "txt"), ("random", "var")),
    _line(0, ("from ", "kw"), ("dataclasses", "var"), (" import ", "kw"), ("dataclass", "def")),
    _line(0),
    _line(0),
    _line(0, ("@dataclass", "fn")),
    _line(0, ("class ", "kw"), ("SlackMetrics", "def"), (":", "txt")),
    _line(1, ('"""今天也要开心地写代码。"""', "str")),
    _line(1),
    _line(1, ("video_time", "var"), (": ", "txt"), ("float", "def"), (" = ", "txt"), ("0.0", "num")),
    _line(1, ("work_time", "var"), (": ", "txt"), ("float", "def"), (" = ", "txt"), ("0.0", "num")),
    _line(1, ("boss_distance", "var"), (": ", "txt"), ("int", "def"), (" = ", "txt"), ("12", "num")),
    _line(1),
    _line(1, ("def ", "kw"), ("ratio", "fn"), ("(self) -> ", "txt"), ("float", "def"), (":", "txt")),
    _line(2, ("total = self.video_time + self.work_time", "txt")),
    _line(2, ("if ", "kw"), ("total <= ", "txt"), ("0", "num"), (":", "txt")),
    _line(3, ("return ", "kw"), ("0.0", "num")),
    _line(2, ("return ", "kw"), ("self.video_time / total", "txt")),
    _line(1),
    _line(1, ("def ", "kw"), ("tick", "fn"), ("(self, seconds: ", "txt"), ("float", "def"), (") -> ", "txt"), ("None", "def"), (":", "txt")),
    _line(2, ('"""每秒钟刷新一次，假装在算东西。"""', "str")),
    _line(2, ("self.work_time += seconds", "txt")),
    _line(2, ("if ", "kw"), ("self.boss_distance < ", "txt"), ("3", "num"), (":", "txt")),
    _line(3, ("self.video_time += ", "txt"), ("0", "num")),
    _line(2, ("else", "kw"), (":", "txt")),
    _line(3, ("self.video_time += seconds", "txt")),
    _line(1),
    _line(0),
    _line(0, ("def ", "kw"), ("build_report", "fn"), ("(metrics: SlackMetrics) -> ", "txt"), ("str", "def"), (":", "txt")),
    _line(1, ("lines = [", "txt")),
    _line(2, ('f"video_time = {metrics.video_time:.1f}s",', "str")),
    _line(2, ('f"work_time  = {metrics.work_time:.1f}s",', "str")),
    _line(2, ('f"ratio      = {metrics.ratio():.2%}",', "str")),
    _line(1, ("]", "txt")),
    _line(1, ('return ', "kw"), ('"\\n"', "str"), (".join(lines)", "txt")),
    _line(0),
    _line(0),
    _line(0, ("if ", "kw"), ('__name__ == "__main__":', "str")),
    _line(1, ("metrics = SlackMetrics()", "txt")),
    _line(1, ("while ", "kw"), ("True", "def"), (":", "txt")),
    _line(2, ("metrics.tick(", "txt"), ("1.0", "num"), (")", "txt")),
    _line(2, ("print", "fn"), ("(build_report(metrics))", "txt")),
    _line(2, ("time.sleep(", "txt"), ("1.0", "num"), (")", "txt")),
]

BUILD_LOGS = [
    "[14:02:11] $ python -m pytest -q",
    "[14:02:12] .............................",
    "[14:02:13] 28 passed in 1.42s",
    "[14:02:14] $ python main.py --check",
    "[14:02:15] [INFO] loading config.json",
    "[14:02:15] [INFO] 12 modules loaded",
    "[14:02:16] [OK] 全部检查通过",
    "[14:02:17] $ git status --short",
    "[14:02:17]  M src/metrics.py",
    "[14:02:18]  M src/report.py",
    "[14:02:19] $ python -m compileall -q src",
    "[14:02:20] build finished, 0 errors",
]


class _CodeCanvas(QWidget):
    """假编辑器的静态内容 + 滚动终端日志。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self._code_font = QFont("Consolas", 10)
        self._code_font.setStyleHint(QFont.StyleHint.Monospace)
        self._mono = QFont("Consolas", 9)
        self._mono.setStyleHint(QFont.StyleHint.Monospace)
        self._ui_font = QFont("Microsoft YaHei UI", 9)
        self._logs = list(BUILD_LOGS[:4])
        self._timer = QTimer(self)
        self._timer.setInterval(1100)
        self._timer.timeout.connect(self._append_log)
        self._timer.start()

    def _append_log(self) -> None:
        stamp = datetime.now().strftime("[%H:%M:%S] ")
        base = random.choice(BUILD_LOGS).split("] ", 1)[-1]
        self._logs.append(stamp + base)
        if len(self._logs) > 8:
            self._logs.pop(0)
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(CODE_BG))
        width, height = self.width(), self.height()
        title_h = 36
        tab_h = 36
        status_h = 22
        panel_h = 148
        sidebar_w = 232
        activity_w = 44

        # 标题栏
        painter.fillRect(0, 0, width, title_h, QColor(TITLE_BG))
        painter.setFont(self._ui_font)
        painter.setPen(QColor("#CCCCCC"))
        painter.drawText(14, 23, "文件   编辑   选择   查看   转到   运行   终端   帮助")
        painter.setPen(QColor("#BBBBBB"))
        painter.drawText(
            QRectF(0, 0, width - 110, title_h),
            Qt.AlignmentFlag.AlignCenter,
            "main.py — slackoff — Visual Studio Code",
        )
        painter.setPen(QColor("#CCCCCC"))
        painter.drawText(width - 84, 23, "—   □   ✕")

        # 活动栏
        painter.fillRect(0, title_h, activity_w, height - title_h, QColor("#333333"))
        painter.setPen(QColor("#8C8C8C"))
        for index, glyph in enumerate(("≡", "⌕", "⑂", "▷", "⊞")):
            painter.drawText(QRectF(0, title_h + 18 + index * 42, activity_w, 24),
                             Qt.AlignmentFlag.AlignCenter, glyph)

        # 资源管理器
        painter.fillRect(activity_w, title_h, sidebar_w, height - title_h, QColor(CODE_BG_ALT))
        painter.setPen(QColor("#BBBBBB"))
        painter.setFont(self._ui_font)
        painter.drawText(activity_w + 14, title_h + 26, "资源管理器")
        painter.setPen(QColor("#8A8A8A"))
        files = [
            ("▾  slackoff", 0, True),
            ("▸  assets", 1, False),
            ("▸  slackoff", 1, False),
            ("    main.py", 1, True),
            ("    config.json", 1, False),
            ("    README.md", 1, False),
            ("▸  tests", 1, False),
            ("    test_metrics.py", 2, False),
            ("    test_report.py", 2, False),
        ]
        for index, (name, indent, active) in enumerate(files):
            y = title_h + 52 + index * 22
            if active:
                painter.fillRect(activity_w + 8, y - 14, sidebar_w - 16, 20, QColor("#37373D"))
            painter.setPen(QColor("#E0E0E0" if active else "#A8A8A8"))
            painter.drawText(activity_w + 16 + indent * 10, y, name)

        # 编辑区
        editor_x = activity_w + sidebar_w
        editor_w = width - editor_x
        painter.fillRect(editor_x, title_h, editor_w, height - title_h, QColor(CODE_BG))

        # 标签页
        painter.fillRect(editor_x, title_h, editor_w, tab_h, QColor(CODE_BG_ALT))
        tab_rect = QRectF(editor_x, title_h, 150, tab_h)
        painter.fillRect(tab_rect, QColor(CODE_BG))
        painter.setPen(QColor("#FFFFFF"))
        painter.setFont(self._ui_font)
        painter.drawText(editor_x + 16, title_h + 23, "main.py")
        painter.setPen(QColor("#9A9A9A"))
        painter.drawText(editor_x + 166, title_h + 23, "config.py")

        # 代码
        fm = QFontMetrics(self._code_font)
        painter.setFont(self._code_font)
        line_h = 20
        code_top = title_h + tab_h + 10
        indent_width = fm.horizontalAdvance("    ")
        visible_lines = max(0, (height - code_top - status_h - panel_h) // line_h)
        for index, line in enumerate(FAKE_CODE[:visible_lines]):
            y = code_top + index * line_h
            gutter_text = str(index + 1)
            if index == 11:
                painter.fillRect(editor_x, y - 14, editor_w, line_h, QColor("#2A2D2E"))
            painter.setPen(QColor("#6E7681"))
            painter.drawText(QRectF(editor_x, y - 14, 48, line_h),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                             gutter_text)
            if not line[1]:
                continue
            x = editor_x + 58 + line[0] * indent_width
            for text, kind in line[1]:
                painter.setPen(QColor(TOKEN.get(kind, TOKEN["txt"])))
                painter.drawText(int(x), y, text)
                x += fm.horizontalAdvance(text)

        # 终端
        panel_top = height - status_h - panel_h
        painter.fillRect(0, panel_top, width, panel_h, QColor("#181818"))
        painter.setPen(QColor("#E7E7E7"))
        painter.setFont(self._ui_font)
        painter.drawText(16, panel_top + 22, "终端    输出    问题    调试控制台")
        painter.setPen(QColor("#3C3C3C"))
        painter.drawLine(0, panel_top + 30, width, panel_top + 30)
        painter.setFont(self._mono)
        for index, log in enumerate(self._logs[-7:]):
            color = QColor("#4EC9B0") if ("passed" in log or "OK" in log) else QColor("#CCCCCC")
            painter.setPen(color)
            painter.drawText(16, panel_top + 50 + index * 16, log)

        # 状态栏
        painter.fillRect(0, height - status_h, width, status_h, QColor(STATUS_BG))
        painter.setPen(QColor("#FFFFFF"))
        painter.setFont(self._ui_font)
        painter.drawText(14, height - 7, "⑂ main*    ⊗ 0    ⚠ 0")
        painter.drawText(width - 330, height - 7, "Python 3.12.10    UTF-8    LF    main")


class _ExcelCanvas(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setStyleSheet(
            "QWidget { background: #F3F3F3; color: #1F1F1F; font-family: 'Microsoft YaHei UI'; }"
            "QTableWidget { background: #FFFFFF; color: #1F1F1F; gridline-color: #D9D9D9;"
            "  border: none; font-size: 12px; }"
            "QHeaderView::section { background: #F0F0F0; color: #3C3C3C; border: none;"
            "  border-right: 1px solid #D9D9D9; border-bottom: 1px solid #D9D9D9; padding: 3px 6px; }"
            "QLabel { background: transparent; color: #1F1F1F; }"
            "QLineEdit { background: #FFFFFF; border: 1px solid #D0D0D0; border-radius: 0;"
            "  color: #1F1F1F; padding: 3px 6px; }"
        )

        top = QFrame()
        top.setStyleSheet("background: #217346;")
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(14, 8, 14, 8)
        title = QLabel("工资表.xlsx - Excel")
        title.setStyleSheet("color: #FFFFFF; font-size: 12px; font-weight: 600;")
        top_layout.addWidget(title)
        top_layout.addStretch(1)
        top_layout.addWidget(QLabel("  —   □   ✕  "))
        layout.addWidget(top)

        ribbon = QFrame()
        ribbon.setStyleSheet("background: #F3F3F3; border-bottom: 1px solid #D9D9D9;")
        ribbon_layout = QHBoxLayout(ribbon)
        ribbon_layout.setContentsMargins(16, 6, 16, 6)
        tabs = QLabel("文件    开始    插入    页面布局    公式    数据    审阅    视图    帮助")
        tabs.setStyleSheet("color: #3C3C3C; font-size: 12px;")
        ribbon_layout.addWidget(tabs)
        ribbon_layout.addStretch(1)
        layout.addWidget(ribbon)

        formula = QHBoxLayout()
        formula.setContentsMargins(10, 4, 10, 4)
        cell_ref = QLabel("A1")
        cell_ref.setFixedWidth(70)
        cell_ref.setStyleSheet("background:#FFFFFF; border:1px solid #D0D0D0; padding:2px 6px;")
        editor = QLineEdit("=SUM(D2:D29)")
        formula.addWidget(cell_ref)
        formula.addWidget(editor, 1)
        layout.addLayout(formula)

        table = QTableWidget(28, 10)
        table.setHorizontalHeaderLabels(list("ABCDEFGHIJ"))
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setDefaultSectionSize(24)
        table.verticalHeader().setVisible(True)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.setShowGrid(True)

        headers = ["日期", "姓名", "部门", "工时", "基本工资", "绩效", "补贴", "扣款", "实发", "备注"]
        table.setHorizontalHeaderLabels(headers)
        names = ["张伟", "王芳", "李娜", "刘洋", "陈静", "杨帆", "赵磊", "周敏"]
        departments = ["研发部", "产品部", "设计部", "市场部"]
        random.seed(7)
        for row in range(28):
            values = [
                f"2026-11-{row + 1:02d}",
                names[row % len(names)],
                departments[row % len(departments)],
                str(160 + random.randint(0, 24)),
                str(12000 + random.randint(-800, 2600)),
                str(2400 + random.randint(-400, 900)),
                str(300 + random.randint(0, 300)),
                str(random.choice([0, 0, 0, 120, 240])),
                str(14000 + random.randint(-600, 1600)),
                "",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignCenter if column != 1 else Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                )
                table.setItem(row, column, item)
        layout.addWidget(table, 1)

        tabs_bar = QFrame()
        tabs_bar.setStyleSheet("background: #F3F3F3; border-top: 1px solid #D9D9D9;")
        tabs_layout = QHBoxLayout(tabs_bar)
        tabs_layout.setContentsMargins(14, 4, 14, 4)
        for index, name in enumerate(("Sheet1", "Sheet2", "汇总")):
            label = QLabel(name)
            label.setStyleSheet(
                "padding: 3px 12px; color: #1F1F1F;"
                + ("border-bottom: 2px solid #217346; font-weight: 600;" if index == 0 else "")
            )
            tabs_layout.addWidget(label)
        tabs_layout.addStretch(1)
        layout.addWidget(tabs_bar)


class DecoyWindow(QWidget):
    """全屏伪装窗口。"""

    closed = Signal()

    def __init__(self, style: str = "code", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("main.py — slackoff — Visual Studio Code")
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        if style == "excel":
            self.setWindowTitle("工资表.xlsx - Excel")
            self._canvas = _ExcelCanvas(self)
        else:
            self._canvas = _CodeCanvas(self)
        layout.addWidget(self._canvas)

    def present(self, screen) -> None:
        if screen is not None:
            self.setGeometry(screen.geometry())
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        self.closed.emit()
        super().closeEvent(event)
