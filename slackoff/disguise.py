"""外观伪装：把左上角图标 / 名称 / 窗口标题包装成常用软件。"""

from __future__ import annotations

from dataclasses import dataclass

from . import __version__


@dataclass(frozen=True)
class Disguise:
    id: str
    name: str          # 窗口 / 托盘里的程序名
    short: str         # 左上角显示的名称
    subtitle: str      # 左上角的小字
    base_title: str    # 首页时的窗口标题


PRESETS: dict[str, Disguise] = {
    "default": Disguise(
        "default", "摸鱼神器", "摸鱼神器", f"SlackOff · v{__version__}", "摸鱼神器"
    ),
    "excel": Disguise(
        "excel", "Microsoft Excel", "Excel", "Microsoft 365", "工作簿1 - Excel"
    ),
    "wps": Disguise(
        "wps", "WPS Office", "WPS", "WPS Office", "工作簿1 - WPS Office"
    ),
    "word": Disguise(
        "word", "Microsoft Word", "Word", "Microsoft 365", "文档1 - Word"
    ),
    "notepad": Disguise(
        "notepad", "记事本", "记事本", "文本编辑器", "无标题 - 记事本"
    ),
    "vscode": Disguise(
        "vscode", "Visual Studio Code", "VS Code", "Editor", "main.py - Visual Studio Code"
    ),
}

DEFAULT = PRESETS["default"]


def get(preset: str | None) -> Disguise:
    return PRESETS.get(preset or "default", DEFAULT)
