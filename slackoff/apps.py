"""「我的应用」：用户拖进来的 exe（或桌面快捷方式）。

列表保存在 config.json 的 ``pinned_apps`` 里；每条记录 id / name / exe / color。
这里负责：解析拖进来的文件、读取 exe 的显示名、启动、以及老板键需要的窗口匹配信息。
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import hashlib
import logging
import os
import struct
import subprocess
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

COLORS = (
    "#00C25F", "#00A4FF", "#1E90FF", "#FF6A00", "#FB7299", "#FE2C55",
    "#F04142", "#FF7F00", "#FFA200", "#31C27C", "#2CA2F9", "#7C9CFF",
)

# 只接受这两类文件
SUPPORTED_SUFFIXES = (".exe", ".lnk")


@dataclass
class PinnedApp:
    id: str
    name: str
    exe: str
    color: str = "#7C9CFF"

    @property
    def path(self) -> Path:
        return Path(self.exe)

    @property
    def exists(self) -> bool:
        return self.path.is_file()

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "exe": self.exe, "color": self.color}


def _key(path: str | Path) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def _make_id(exe: str) -> str:
    digest = hashlib.md5(_key(exe).encode("utf-8")).hexdigest()[:8]
    return f"app-{digest}"


def _pick_color(seed: str) -> str:
    digest = hashlib.md5(seed.encode("utf-8")).digest()
    return COLORS[digest[0] % len(COLORS)]


# ---------------------------------------------------------------------- 读取
def load_apps(settings) -> list[PinnedApp]:
    """把 config 里的字典转成对象；顺手补上缺失的 id / 颜色（不落盘）。"""
    result: list[PinnedApp] = []
    for entry in settings.pinned_apps:
        if not isinstance(entry, dict):
            continue
        exe = str(entry.get("exe") or "").strip()
        if not exe:
            continue
        app_id = str(entry.get("id") or "").strip()
        if not app_id:
            app_id = _make_id(exe)
            entry["id"] = app_id
        color = str(entry.get("color") or "").strip()
        if not color:
            color = _pick_color(app_id)
            entry["color"] = color
        name = str(entry.get("name") or "").strip() or Path(exe).stem
        entry["name"] = name
        result.append(PinnedApp(id=app_id, name=name, exe=exe, color=color))
    return result


def find_app(settings, app_id: str) -> PinnedApp | None:
    return next((app for app in load_apps(settings) if app.id == app_id), None)


# ---------------------------------------------------------------------- 增删
def add_path(settings, raw_path: str | Path, name: str | None = None) -> tuple[PinnedApp, bool]:
    """添加一个 exe / 快捷方式；返回 (应用, 是否新增)。已存在时返回原条目。"""
    target = resolve_drop(str(raw_path))
    if target is None:
        raise ValueError("只支持 .exe 程序或它的桌面快捷方式")
    existing = next(
        (app for app in load_apps(settings) if _key(app.exe) == _key(target)),
        None,
    )
    if existing is not None:
        return existing, False

    display = (name or "").strip() or display_name(target)
    app = PinnedApp(
        id=_make_id(str(target)),
        name=display,
        exe=str(target),
        color=_pick_color(_make_id(str(target))),
    )
    settings.pinned_apps.append(app.to_dict())
    return app, True


def remove(settings, app_id: str) -> bool:
    before = len(settings.pinned_apps)
    settings.pinned_apps = [
        entry for entry in settings.pinned_apps if str(entry.get("id") or "") != app_id
    ]
    return len(settings.pinned_apps) != before


# ---------------------------------------------------------------------- 启动
def launch(app: PinnedApp) -> tuple[bool, str]:
    path = app.path
    if not path.is_file():
        return False, f"找不到 {app.name} 的程序文件：{app.exe}"
    try:
        subprocess.Popen(
            [str(path)],
            cwd=str(path.parent),
            close_fds=True,
        )
    except OSError as exc:
        log.warning("启动 %s 失败：%s", app.name, exc)
        return False, f"启动 {app.name} 失败：{exc}"
    return True, f"正在打开 {app.name}…"


def window_targets(settings) -> tuple[frozenset[str], tuple[str, ...]]:
    """老板键隐藏窗口时用：exe 文件名 + 显示名（窗口标题里常包含）。"""
    apps = load_apps(settings)
    exe_names = frozenset(Path(app.exe).name.lower() for app in apps)
    titles: list[str] = []
    for app in apps:
        titles.append(app.name)
        titles.append(Path(app.exe).stem)
    return exe_names, tuple(dict.fromkeys(title for title in titles if title))


# ---------------------------------------------------------------------- 解析
def resolve_drop(raw_path: str) -> Path | None:
    """把拖进来的路径变成可执行的 exe；快捷方式会读取目标。"""
    try:
        path = Path(raw_path).expanduser()
    except Exception:
        return None
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        return None
    if suffix == ".lnk":
        target = _shortcut_target(path)
        if target is None:
            return None
        path = target
        suffix = path.suffix.lower()
    if suffix != ".exe":
        return None
    if not path.is_file():
        return None
    return path.resolve()


def _shortcut_target(path: Path) -> Path | None:
    try:
        import comtypes.client  # noqa: PLC0415

        shell = comtypes.client.CreateObject("WScript.Shell", dynamic=True)
        target = shell.CreateShortcut(str(path)).TargetPath
        if target:
            candidate = Path(str(target))
            if candidate.is_file():
                return candidate
    except Exception as exc:
        log.debug("解析快捷方式失败 %s: %s", path, exc)
    return None


def display_name(exe: str | Path) -> str:
    """优先用 exe 的「文件说明」（例如 QQLive.exe → 腾讯视频），没有就用文件名。"""
    path = Path(exe)
    description = _file_description(str(path)).strip()
    if 0 < len(description) <= 40:
        return description
    return path.stem


def _file_description(path: str) -> str:
    if os.name != "nt":
        return ""
    try:
        version = ctypes.WinDLL("version", use_last_error=True)
        version.GetFileVersionInfoSizeW.argtypes = [wt.LPCWSTR, ctypes.POINTER(wt.DWORD)]
        version.GetFileVersionInfoSizeW.restype = wt.DWORD
        version.GetFileVersionInfoW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.c_void_p]
        version.GetFileVersionInfoW.restype = wt.BOOL
        version.VerQueryValueW.argtypes = [
            ctypes.c_void_p, wt.LPCWSTR, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wt.UINT)
        ]
        version.VerQueryValueW.restype = wt.BOOL

        size = version.GetFileVersionInfoSizeW(path, None)
        if not size:
            return ""
        buffer = ctypes.create_string_buffer(size)
        if not version.GetFileVersionInfoW(path, 0, size, buffer):
            return ""
        pointer = ctypes.c_void_p()
        length = wt.UINT()
        if not version.VerQueryValueW(
            buffer, "\\VarFileInfo\\Translation", ctypes.byref(pointer), ctypes.byref(length)
        ):
            return ""
        if length.value < 4:
            return ""
        lang, codepage = struct.unpack("<HH", ctypes.string_at(pointer, 4))
        sub = f"\\StringFileInfo\\{lang:04x}{codepage:04x}\\FileDescription"
        if not version.VerQueryValueW(buffer, sub, ctypes.byref(pointer), ctypes.byref(length)):
            return ""
        return ctypes.wstring_at(pointer, length.value).rstrip("\x00")
    except Exception:
        return ""
