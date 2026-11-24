"""Windows 原生窗口操作（ctypes，无需 pywin32）。

这里只做几件事：枚举窗口、按进程名 / 标题找窗口、隐藏和恢复窗口、
给窗口开深色标题栏。所有函数在非 Windows 上安全地返回空值。
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import logging
import sys
from dataclasses import dataclass

log = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"

_user32 = ctypes.WinDLL("user32", use_last_error=True) if IS_WINDOWS else None
_dwmapi = ctypes.WinDLL("dwmapi") if IS_WINDOWS else None
_shell32 = ctypes.WinDLL("shell32") if IS_WINDOWS else None
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True) if IS_WINDOWS else None

SW_HIDE = 0
SW_SHOWNORMAL = 1
SW_SHOW = 5
SW_RESTORE = 9
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
GA_ROOT = 2

# 窗口样式（嵌入用）
GWL_STYLE = -16
GWL_EXSTYLE = -20
GWLP_HWNDPARENT = -8
WS_CHILD = 0x40000000
WS_POPUP = 0x80000000
WS_CAPTION = 0x00C00000
WS_THICKFRAME = 0x00040000
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000
WS_SYSMENU = 0x00080000
WS_BORDER = 0x00800000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
SWP_FRAMECHANGED = 0x0020
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010

# 系统级热键
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312

if IS_WINDOWS:
    _WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    _user32.RegisterHotKey.argtypes = [wt.HWND, ctypes.c_int, wt.UINT, wt.UINT]
    _user32.RegisterHotKey.restype = wt.BOOL
    _user32.UnregisterHotKey.argtypes = [wt.HWND, ctypes.c_int]
    _user32.UnregisterHotKey.restype = wt.BOOL
    _GetWindowLong = getattr(_user32, "GetWindowLongPtrW", _user32.GetWindowLongW)
    _SetWindowLong = getattr(_user32, "SetWindowLongPtrW", _user32.SetWindowLongW)
    _GetWindowLong.argtypes = [wt.HWND, ctypes.c_int]
    _GetWindowLong.restype = ctypes.c_ssize_t
    _SetWindowLong.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_ssize_t]
    _SetWindowLong.restype = ctypes.c_ssize_t


@dataclass
class WindowInfo:
    hwnd: int
    pid: int
    title: str
    class_name: str
    visible: bool
    minimized: bool
    exe: str = ""

    @property
    def exe_name(self) -> str:
        return self.exe.rsplit("\\", 1)[-1].lower() if self.exe else ""


# ---------------------------------------------------------------------- 基础
def is_window(hwnd: int) -> bool:
    return _is_window(hwnd)


def _is_window(hwnd: int) -> bool:
    return bool(_user32 and hwnd and _user32.IsWindow(hwnd))


def is_visible(hwnd: int) -> bool:
    if not _is_window(hwnd):
        return False
    return bool(_user32.IsWindowVisible(hwnd))


def is_minimized(hwnd: int) -> bool:
    if not _is_window(hwnd):
        return False
    return bool(_user32.IsIconic(hwnd))


def window_rect(hwnd: int) -> tuple[int, int, int, int]:
    if not _is_window(hwnd):
        return (0, 0, 0, 0)
    rect = wt.RECT()
    try:
        _user32.GetWindowRect(wt.HWND(hwnd), ctypes.byref(rect))
        return (rect.left, rect.top, rect.right, rect.bottom)
    except Exception:
        return (0, 0, 0, 0)


def window_title(hwnd: int) -> str:
    if not _is_window(hwnd):
        return ""
    length = _user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    _user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def class_name(hwnd: int) -> str:
    if not _is_window(hwnd):
        return ""
    buf = ctypes.create_unicode_buffer(256)
    _user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def window_pid(hwnd: int) -> int:
    if not _is_window(hwnd):
        return 0
    pid = wt.DWORD(0)
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


def process_path(pid: int) -> str:
    """拿进程的可执行文件完整路径，失败返回空串（权限不足很常见）。"""
    if not IS_WINDOWS or not pid:
        return ""
    handle = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = wt.DWORD(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        ok = _kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size))
        return buf.value if ok else ""
    finally:
        _kernel32.CloseHandle(handle)


def enumerate_windows(visible_only: bool = False) -> list[WindowInfo]:
    """枚举所有顶层窗口。"""
    result: list[WindowInfo] = []
    if not IS_WINDOWS:
        return result

    def _callback(hwnd, _lparam):
        try:
            visible = bool(_user32.IsWindowVisible(hwnd))
            if visible_only and not visible:
                return True
            title = window_title(hwnd)
            cls = class_name(hwnd)
            pid = window_pid(hwnd)
            result.append(
                WindowInfo(
                    hwnd=int(hwnd),
                    pid=pid,
                    title=title,
                    class_name=cls,
                    visible=visible,
                    minimized=bool(_user32.IsIconic(hwnd)),
                )
            )
        except Exception:
            pass
        return True

    _user32.EnumWindows(_WNDENUMPROC(_callback), 0)
    return result


# ---------------------------------------------------------------------- 隐藏
def hide_window(hwnd: int) -> bool:
    if not is_visible(hwnd) or is_minimized(hwnd):
        return False
    try:
        return bool(_user32.ShowWindow(hwnd, SW_HIDE))
    except Exception:
        return False


def show_window(hwnd: int) -> bool:
    if not _is_window(hwnd):
        return False
    try:
        if is_minimized(hwnd):
            _user32.ShowWindow(hwnd, SW_RESTORE)
        else:
            _user32.ShowWindow(hwnd, SW_SHOW)
        return True
    except Exception:
        return False


def hide_windows(hwnds) -> list[int]:
    """批量隐藏，返回真正被隐藏的窗口句柄。"""
    hidden = []
    for hwnd in hwnds:
        if hide_window(hwnd):
            hidden.append(hwnd)
    return hidden


def show_windows(hwnds) -> None:
    for hwnd in hwnds:
        show_window(hwnd)


def find_client_windows(
    exe_names: frozenset[str] | set[str] | tuple[str, ...] = (),
    title_keywords: tuple[str, ...] = (),
    exclude_pids: frozenset[int] | set[int] = frozenset(),
    require_visible: bool = True,
) -> list[WindowInfo]:
    """找属于某个客户端的窗口：按进程名或窗口标题匹配。"""
    wanted_names = {n.lower() for n in exe_names}
    keywords = tuple(k.lower() for k in title_keywords if k)
    found: list[WindowInfo] = []
    exe_cache: dict[int, str] = {}
    for info in enumerate_windows(visible_only=require_visible):
        if info.pid in exclude_pids:
            continue
        if require_visible and not info.visible:
            continue
        if info.class_name in ("Progman", "WorkerW", "Shell_TrayWnd", "Windows.UI.Core.CoreWindow"):
            continue
        if wanted_names and info.pid not in exe_cache:
            exe_cache[info.pid] = process_path(info.pid)
        if wanted_names:
            info.exe = exe_cache.get(info.pid, "")
        matched = False
        if info.exe_name and info.exe_name in wanted_names:
            matched = True
        if not matched and keywords:
            title = info.title.lower()
            if any(k in title for k in keywords):
                matched = True
        if matched:
            found.append(info)
    return found


# ---------------------------------------------------------------------- 热键
def register_hotkey(hwnd: int, hotkey_id: int, modifiers: int, vk: int) -> bool:
    """注册系统级热键（RegisterHotKey），失败通常是组合已被别的程序占用。"""
    if not IS_WINDOWS or not hwnd:
        return False
    try:
        return bool(_user32.RegisterHotKey(wt.HWND(hwnd), hotkey_id, modifiers | MOD_NOREPEAT, vk))
    except Exception:
        return False


def unregister_hotkey(hwnd: int, hotkey_id: int) -> None:
    if not IS_WINDOWS or not hwnd:
        return
    try:
        _user32.UnregisterHotKey(wt.HWND(hwnd), hotkey_id)
    except Exception:
        pass


# ---------------------------------------------------------------------- 嵌入
def get_parent(hwnd: int) -> int:
    if not _is_window(hwnd):
        return 0
    return int(_user32.GetParent(hwnd) or 0)


def set_parent(hwnd: int, parent: int) -> bool:
    if not _is_window(hwnd):
        return False
    try:
        _user32.SetParent(wt.HWND(hwnd), wt.HWND(parent))
        if not parent:
            # 分离时 GetParent 可能返回原来的 owner，不要求一定为 0
            return True
        current = get_parent(hwnd)
        if current != int(parent):
            log.warning(
                "SetParent(%s -> %s) 后 GetParent=%s，GetLastError=%s",
                hwnd, parent, current, ctypes.get_last_error(),
            )
            return False
        return True
    except Exception:
        return False


def get_window_style(hwnd: int) -> int:
    if not _is_window(hwnd):
        return 0
    try:
        return int(_GetWindowLong(hwnd, GWL_STYLE))
    except Exception:
        return 0


def set_window_style(hwnd: int, style: int) -> None:
    if not _is_window(hwnd):
        return
    try:
        _SetWindowLong(hwnd, GWL_STYLE, style)
        _user32.SetWindowPos(
            wt.HWND(hwnd), None, 0, 0, 0, 0,
            SWP_FRAMECHANGED | SWP_NOZORDER | SWP_NOACTIVATE,
        )
    except Exception:
        pass


def get_window_exstyle(hwnd: int) -> int:
    if not _is_window(hwnd):
        return 0
    try:
        return int(_GetWindowLong(hwnd, GWL_EXSTYLE))
    except Exception:
        return 0


def set_window_exstyle(hwnd: int, style: int) -> None:
    if not _is_window(hwnd):
        return
    try:
        _SetWindowLong(hwnd, GWL_EXSTYLE, style)
        _user32.SetWindowPos(
            wt.HWND(hwnd), None, 0, 0, 0, 0,
            SWP_FRAMECHANGED | SWP_NOZORDER | SWP_NOACTIVATE,
        )
    except Exception:
        pass


def set_window_owner(hwnd: int, owner: int) -> bool:
    if not _is_window(hwnd):
        return False
    try:
        _SetWindowLong(hwnd, GWLP_HWNDPARENT, owner)
        return True
    except Exception:
        return False


def get_window_owner(hwnd: int) -> int:
    if not _is_window(hwnd):
        return 0
    try:
        return int(_GetWindowLong(hwnd, GWLP_HWNDPARENT) or 0)
    except Exception:
        return 0


def move_window(hwnd: int, x: int, y: int, width: int, height: int) -> None:
    if not _is_window(hwnd):
        return
    try:
        _user32.MoveWindow(wt.HWND(hwnd), int(x), int(y), int(width), int(height), True)
    except Exception:
        pass


def set_foreground(hwnd: int) -> None:
    if not _is_window(hwnd):
        return
    try:
        _user32.SetForegroundWindow(wt.HWND(hwnd))
    except Exception:
        pass


def switch_to_window(hwnd: int) -> None:
    """比 SetForegroundWindow 更容易抢到前台（用于截图/调试）。"""
    if not _is_window(hwnd):
        return
    try:
        _user32.SwitchToThisWindow(wt.HWND(hwnd), True)
    except Exception:
        pass


def post_close(hwnd: int) -> None:
    if not _is_window(hwnd):
        return
    try:
        _user32.PostMessageW(wt.HWND(hwnd), 0x0010, 0, 0)  # WM_CLOSE
    except Exception:
        pass


# ---------------------------------------------------------------------- 外观
def set_dark_titlebar(hwnd: int) -> None:
    """Win10 1809+ / Win11 的深色标题栏。失败无所谓。"""
    if not (IS_WINDOWS and _dwmapi and hwnd):
        return
    try:
        value = ctypes.c_int(1)
        for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE（新旧编号）
            if _dwmapi.DwmSetWindowAttribute(
                hwnd, attr, ctypes.byref(value), ctypes.sizeof(value)
            ) == 0:
                break
    except Exception:
        pass


def set_app_user_model_id(app_id: str) -> None:
    """让任务栏图标不被归类到 python.exe 下面。"""
    if not (IS_WINDOWS and _shell32):
        return
    try:
        _shell32.SetCurrentProcessExplicitAppUserModelID(ctypes.c_wchar_p(app_id))
    except Exception:
        pass
