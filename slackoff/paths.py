"""统一管理运行期目录。

默认把配置、缓存、日志都放在项目目录下的 ``data/`` 里，整个文件夹可以直接拷走。
需要放到别处时设置环境变量 ``SLACKOFF_HOME`` 即可。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR_NAME = "SlackOff"


def is_windows() -> bool:
    return sys.platform == "win32"


def project_root() -> Path:
    """源码根目录（slackoff 包的上一级）。"""
    return Path(__file__).resolve().parent.parent


def home_dir() -> Path:
    """数据根目录，可通过 SLACKOFF_HOME 覆盖。"""
    override = os.environ.get("SLACKOFF_HOME", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return project_root() / "data"


def data_dir() -> Path:
    p = home_dir()
    p.mkdir(parents=True, exist_ok=True)
    return p


def config_path() -> Path:
    return data_dir() / "config.json"


def log_path() -> Path:
    return data_dir() / "slackoff.log"


def webengine_dir() -> Path:
    """WebEngine 的缓存 / Cookie 目录。"""
    p = data_dir() / "webengine"
    p.mkdir(parents=True, exist_ok=True)
    return p


def downloads_dir() -> Path:
    p = data_dir() / "downloads"
    p.mkdir(parents=True, exist_ok=True)
    return p


def user_downloads_dir() -> Path:
    """系统「下载」文件夹，拿不到时退回 data/downloads。"""
    try:
        import winreg  # noqa: PLC0415

        key = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            value, _ = winreg.QueryValueEx(k, "{374DE290-123F-4565-9164-39C4925E467B}")
            path = Path(os.path.expandvars(value))
            if path.is_dir():
                return path
    except Exception:
        pass
    return downloads_dir()


def asset(name: str) -> Path:
    return project_root() / "assets" / name
