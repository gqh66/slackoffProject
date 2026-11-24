"""用系统 Edge / Chrome 内核打开网页视频。

PySide6 自带的 QtWebEngine 在编译时没有启用 H.264 / AAC（也不带 Widevine），
腾讯视频、爱奇艺这类网页播放器会直接提示「视频加载失败 / 不支持」。

这里不碰 QtWebEngine 内核：把系统 Edge 以无地址栏的 App 窗口打开，
作为主窗口的从属窗口（owned window）盖在内容区上方，播放、登录、DRM 都交给
Edge 自己处理。窗口仍是独立进程，但会跟随主窗口移动 / 缩放，老板键隐藏主窗口
时也会一起隐藏；关闭网页时进程一起收掉。
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import logging
import os
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit

from PySide6.QtCore import QObject, QRect, Qt, QTimer, Signal
from PySide6.QtWidgets import QWidget

from . import catalog, paths, winapi

log = logging.getLogger(__name__)

# 这些站点的网页播放器依赖 H.264 / AAC，统一交给系统内核
VIDEO_HOSTS: tuple[str, ...] = (
    "iqiyi.com",
    "v.qq.com",
    "film.qq.com",
    "youku.com",
    "mgtv.com",
    "bilibili.com",
    "b23.tv",
    "douyin.com",
    "ixigua.com",
    "douyu.com",
    "huya.com",
    "tv.sohu.com",
    "youtube.com",
    "youtube-nocookie.com",
    "youtu.be",
    "yangshipin.cn",
    "le.com",
)

WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000


# ---------------------------------------------------------------------- 探测
def _browser_candidates() -> list[tuple[Path, str]]:
    program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    program_files_x86 = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
    local_appdata = os.environ.get("LOCALAPPDATA", "").strip()
    edges = [
        (program_files_x86 / "Microsoft" / "Edge" / "Application" / "msedge.exe", "edge"),
        (program_files / "Microsoft" / "Edge" / "Application" / "msedge.exe", "edge"),
    ]
    chromes = [
        (program_files / "Google" / "Chrome" / "Application" / "chrome.exe", "chrome"),
        (program_files_x86 / "Google" / "Chrome" / "Application" / "chrome.exe", "chrome"),
    ]
    if local_appdata:
        local = Path(local_appdata)
        edges.append((local / "Microsoft" / "Edge" / "Application" / "msedge.exe", "edge"))
        chromes.append((local / "Google" / "Chrome" / "Application" / "chrome.exe", "chrome"))
    return edges + chromes


def find_browser() -> tuple[str, str] | None:
    """返回 (浏览器 exe, "edge" | "chrome")；没装则返回 None。"""
    for path, kind in _browser_candidates():
        try:
            if path.is_file():
                return str(path), kind
        except OSError:
            continue
    return None


def available() -> bool:
    return find_browser() is not None


# ---------------------------------------------------------------------- 网址
def is_video_url(url: str) -> bool:
    value = (url or "").strip()
    if not value:
        return False
    if "://" not in value:
        value = "https://" + value
    try:
        host = (urlsplit(value).hostname or "").lower().strip(".")
    except ValueError:
        return False
    if not host:
        return False
    return any(host == suffix or host.endswith("." + suffix) for suffix in VIDEO_HOSTS)


def site_label(url: str) -> str:
    """给视频站起个短名字，例如 iqiyi.com -> 爱奇艺。"""
    value = (url or "").strip()
    if not value:
        return "网页"
    if "://" not in value:
        value = "https://" + value
    try:
        host = (urlsplit(value).hostname or "").lower()
    except ValueError:
        host = ""
    if not host:
        return "网页"
    for site in catalog.SITES:
        try:
            site_host = (urlsplit(site.url).hostname or "").lower()
        except ValueError:
            continue
        if site_host and (host == site_host or host.endswith("." + site_host)):
            return site.name
    return host.removeprefix("www.")


# ---------------------------------------------------------------------- 配置
def profile_dir() -> Path:
    """给系统内核用的独立配置目录，登录状态可以一直保留。"""
    return paths.data_dir() / "edge-profile"


def _profile_marker() -> str:
    return str(profile_dir()).lower()


def kill_profile_processes() -> None:
    """收掉上一次没退干净的 Edge / Chrome（只认本工具的独立配置目录）。"""
    marker = _profile_marker()
    try:
        import psutil  # noqa: PLC0415
    except Exception:
        return
    killed = []
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            cmdline = " ".join(proc.info.get("cmdline") or []).lower()
        except Exception:
            continue
        if marker and marker in cmdline:
            try:
                proc.kill()
                killed.append(proc)
            except Exception:
                pass
    if killed:
        try:
            psutil.wait_procs(killed, timeout=2)
        except Exception:
            pass


def _pid_uses_profile(pid: int, marker: str) -> bool:
    if not marker:
        return False
    try:
        import psutil  # noqa: PLC0415

        cmdline = " ".join(psutil.Process(pid).cmdline()).lower()
    except Exception:
        return False
    return marker in cmdline


def _is_zoomed(hwnd: int) -> bool:
    try:
        return bool(ctypes.windll.user32.IsZoomed(wt.HWND(hwnd)))
    except Exception:
        return False


def _monitor_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    class MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wt.DWORD),
            ("rcMonitor", wt.RECT),
            ("rcWork", wt.RECT),
            ("dwFlags", wt.DWORD),
        ]

    try:
        monitor = ctypes.windll.user32.MonitorFromWindow(wt.HWND(hwnd), 2)
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if ctypes.windll.user32.GetMonitorInfoW(wt.HWND(monitor), ctypes.byref(info)):
            rect = info.rcMonitor
            return rect.left, rect.top, rect.right, rect.bottom
    except Exception:
        pass
    return None


class EdgeSiteWindow(QObject):
    """一个用系统内核打开的网页窗口（App 模式 + 从属窗口）。"""

    ready = Signal(str)      # 页面标题
    failed = Signal(str)
    closed = Signal()

    POLL_MS = 250
    START_TIMEOUT_MS = 20000

    def __init__(self, main_window: QWidget, slot: QWidget, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._main = main_window
        self._slot = slot
        self._popen: subprocess.Popen | None = None
        self._hwnd = 0
        self._windows: dict[int, int] = {}   # 已接管的窗口，按接管顺序排列
        self._pid = 0
        self._profile_pids: dict[int, bool] = {}
        self._started_at = 0.0
        self._detached = False

        self._timer = QTimer(self)
        self._timer.setInterval(self.POLL_MS)
        self._timer.timeout.connect(self._tick)

    # ------------------------------------------------------------------ 状态
    @property
    def active(self) -> bool:
        return not self._detached and bool(self._hwnd) and winapi.is_window(self._hwnd)

    @property
    def hwnd(self) -> int:
        return self._hwnd

    def pids(self) -> set[int]:
        """当前网页进程树（老板键 / 隐身静音用）。"""
        result: set[int] = set()
        if self._detached:
            return result
        owners = {self._pid}
        owners.update(winapi.window_pid(hwnd) for hwnd in self._windows)
        owners.discard(0)
        for pid in owners:
            result.add(pid)
            try:
                import psutil  # noqa: PLC0415

                proc = psutil.Process(pid)
                result.update(child.pid for child in proc.children(recursive=True))
            except Exception:
                pass
        return result

    def is_fullscreen_like(self) -> bool:
        """窗口被最大化 / 全屏——此时隐身模式不应再把鼠标判成「离开」。"""
        if not self.active:
            return False
        hwnd = self._hwnd
        if not winapi.is_visible(hwnd):
            return False
        if _is_zoomed(hwnd):
            return True
        rect = winapi.window_rect(hwnd)
        monitor = _monitor_rect(hwnd)
        if not monitor:
            return False
        width, height = rect[2] - rect[0], rect[3] - rect[1]
        mwidth, mheight = monitor[2] - monitor[0], monitor[3] - monitor[1]
        return width >= mwidth * 0.98 and height >= mheight * 0.98

    # ------------------------------------------------------------------ 打开
    def open(self, url: str) -> bool:
        self.close()
        found = find_browser()
        if found is None:
            self.failed.emit("没有找到系统 Edge / Chrome，无法用系统内核播放。")
            return False
        exe, kind = found
        kill_profile_processes()
        profile = profile_dir()
        try:
            profile.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        args = [
            exe,
            f"--app={url}",
            f"--user-data-dir={profile}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-sync",
            "--disable-background-mode",
            "--disable-session-crashed-bubble",
            "--hide-crash-restore-bubble",
        ]
        try:
            self._popen = subprocess.Popen(
                args, cwd=str(Path(exe).parent), close_fds=True
            )
        except OSError as exc:
            self.failed.emit(f"启动系统内核失败：{exc}")
            return False
        self._pid = int(self._popen.pid)
        self._started_at = time.monotonic()
        self._detached = False
        self._timer.start()
        log.info("准备用 %s 内核打开：%s（pid=%s）", kind, url, self._pid)
        return True

    def _tick(self) -> None:
        if self._detached:
            self._timer.stop()
            return
        if not self._windows:
            self._tick_initial()
            return
        self._sync_windows()

    def _tick_initial(self) -> None:
        if self._popen is None:
            self._timer.stop()
            return
        if (time.monotonic() - self._started_at) * 1000 > self.START_TIMEOUT_MS:
            self._timer.stop()
            self._kill()
            self.failed.emit("系统内核没有启动起来（等待窗口超时），请检查 Edge 是否正常。")
            return
        hwnd = self._find_window()
        if hwnd:
            self._track(hwnd, first=True)

    def _sync_windows(self) -> None:
        """跟踪已接管的窗口，并把网页新开的顶层窗口也收进来。"""
        alive = [hwnd for hwnd in self._windows if winapi.is_window(hwnd)]
        if len(alive) != len(self._windows):
            self._windows = {hwnd: index for index, hwnd in enumerate(alive)}
        if not alive:
            self._hwnd = 0
            self._timer.stop()
            self._kill()
            self.closed.emit()
            return
        fresh = self._find_new_windows()
        for hwnd in fresh:
            self._track(hwnd)
        if fresh:
            self._activate(fresh[-1])
        elif self._hwnd not in self._windows:
            self._activate(next(reversed(self._windows)))

    def _find_window(self) -> int:
        found = self._best_window(lambda window: window.pid == self._pid)
        if found:
            return found
        # Edge 有时会把新窗口交给「同一配置目录」的已有实例，启动进程随即退出
        marker = _profile_marker()
        found = self._best_window(
            lambda window: _pid_uses_profile(window.pid, marker)
        )
        if found:
            new_pid = winapi.window_pid(found)
            if new_pid:
                self._pid = new_pid
        return found

    @staticmethod
    def _best_window(predicate) -> int:
        best = 0
        best_area = 0
        for window in winapi.enumerate_windows(visible_only=True):
            if not window.title or winapi.get_parent(window.hwnd):
                continue
            if window.class_name != "Chrome_WidgetWin_1":
                continue
            try:
                if not predicate(window):
                    continue
            except Exception:
                continue
            left, top, right, bottom = winapi.window_rect(window.hwnd)
            width, height = right - left, bottom - top
            if width < 300 or height < 200:
                continue
            area = width * height
            if area > best_area:
                best, best_area = window.hwnd, area
        return best

    def _find_new_windows(self) -> list[int]:
        """找同一 Edge 实例里新出现的网页顶层窗口（target=_blank / window.open）。"""
        found: list[int] = []
        for window in winapi.enumerate_windows(visible_only=True):
            if window.hwnd in self._windows:
                continue
            if not window.title or winapi.get_parent(window.hwnd):
                continue
            if window.class_name != "Chrome_WidgetWin_1":
                continue
            if not self._owns_pid(window.pid):
                continue
            left, top, right, bottom = winapi.window_rect(window.hwnd)
            if right - left < 300 or bottom - top < 200:
                continue
            found.append(window.hwnd)
        return found

    def _owns_pid(self, pid: int) -> bool:
        """窗口进程是否属于本工具的 Edge 实例（直接用启动 pid 或同一配置目录）。"""
        if not pid:
            return False
        if pid == self._pid:
            return True
        if pid in self._profile_pids:
            return self._profile_pids[pid]
        try:
            value = _pid_uses_profile(pid, _profile_marker())
        except Exception:
            value = False
        self._profile_pids[pid] = value
        return value

    def _track(self, hwnd: int, first: bool = False) -> None:
        if hwnd in self._windows or not winapi.is_window(hwnd):
            return
        self._windows[hwnd] = len(self._windows)
        try:
            exstyle = winapi.get_window_exstyle(hwnd)
            winapi.set_window_exstyle(
                hwnd, (exstyle | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW
            )
            winapi.set_window_owner(hwnd, int(self._main.winId()))
        except Exception:
            log.debug("设置系统内核窗口样式失败", exc_info=True)
        if not first:
            winapi.hide_window(hwnd)
            log.info("接管系统内核新窗口（hwnd=%s）", hwnd)
            return
        self._activate(hwnd)
        title = winapi.window_title(hwnd) or ""
        log.info("系统内核窗口已就绪（hwnd=%s，%s）", hwnd, title)
        self.ready.emit(title)

    def _activate(self, hwnd: int) -> None:
        if not winapi.is_window(hwnd):
            return
        for other in self._windows:
            if other != hwnd and winapi.is_window(other):
                winapi.hide_window(other)
        self._hwnd = hwnd
        self._place()
        self.set_topmost(
            bool(self._main.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        )
        if not self._main.isVisible() or self._main.isMinimized():
            return
        winapi.show_window(hwnd)
        try:
            winapi.set_foreground(hwnd)
        except Exception:
            pass

    # ------------------------------------------------------------------ 位置
    def _slot_rect(self) -> tuple[int, int, int, int]:
        try:
            return winapi.window_rect(int(self._slot.winId()))
        except Exception:
            return (0, 0, 0, 0)

    def _place(self) -> None:
        if not self._hwnd or not winapi.is_window(self._hwnd):
            return
        if self.is_fullscreen_like():
            return
        left, top, right, bottom = self._slot_rect()
        if right <= left or bottom <= top:
            return
        winapi.move_window(self._hwnd, left, top, right - left, bottom - top)

    def sync(self) -> None:
        """主窗口移动 / 缩放 / 重新显示时，把内核窗口贴回内容区。"""
        if not self.active:
            return
        if not self._main.isVisible() or self._main.isMinimized():
            self.hide()
            return
        if not winapi.is_visible(self._hwnd):
            winapi.show_window(self._hwnd)
        self._place()

    def set_topmost(self, on: bool) -> None:
        """主窗口「置顶」时，从属窗口也要置顶，否则会被主窗口盖住。"""
        if not self.active:
            return
        try:
            ctypes.windll.user32.SetWindowPos(
                wt.HWND(self._hwnd),
                wt.HWND(-1 if on else -2),
                0, 0, 0, 0,
                0x0001 | 0x0002 | 0x0010,  # NOSIZE | NOMOVE | NOACTIVATE
            )
        except Exception:
            pass

    def hide(self) -> None:
        for hwnd in self._windows:
            if winapi.is_window(hwnd):
                winapi.hide_window(hwnd)

    def show(self) -> None:
        if self.active:
            winapi.show_window(self._hwnd)

    # ------------------------------------------------------------------ 分离
    def detach(self) -> None:
        """把窗口放回桌面（保留进程），之后由用户自己关。"""
        active = self._hwnd
        windows = [hwnd for hwnd in self._windows if hwnd != active and winapi.is_window(hwnd)]
        if active and winapi.is_window(active):
            windows.append(active)
        if not windows:
            return
        self._timer.stop()
        self._hwnd = 0
        self._windows.clear()
        screen = self._main.screen()
        available = screen.availableGeometry() if screen is not None else None
        if available is not None:
            width = min(1280, max(900, available.width() // 2))
            height = min(820, max(600, available.height() // 2))
            left = available.left() + (available.width() - width) // 2
            top = available.top() + (available.height() - height) // 2
        else:
            width = height = left = top = 0
        for index, hwnd in enumerate(windows):
            try:
                exstyle = winapi.get_window_exstyle(hwnd)
                winapi.set_window_exstyle(
                    hwnd, (exstyle | WS_EX_APPWINDOW) & ~WS_EX_TOOLWINDOW
                )
                winapi.set_window_owner(hwnd, 0)
                ctypes.windll.user32.SetWindowPos(
                    wt.HWND(hwnd), wt.HWND(-2), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010
                )
                winapi.show_window(hwnd)
                if width > 0:
                    offset = 0 if hwnd == active else 40 * (index + 1)
                    winapi.move_window(
                        hwnd, left + offset, top + offset, width, height
                    )
            except Exception:
                log.debug("把系统内核窗口放回桌面失败", exc_info=True)
        if active and winapi.is_window(active):
            try:
                winapi.set_foreground(active)
            except Exception:
                pass
        self._detached = True
        self._popen = None
        self._pid = 0
        self._profile_pids.clear()
        log.info("系统内核窗口已放到桌面")

    # ------------------------------------------------------------------ 关闭
    def close(self) -> None:
        self._timer.stop()
        for hwnd in self._windows:
            if winapi.is_window(hwnd):
                try:
                    winapi.hide_window(hwnd)
                except Exception:
                    pass
        self._hwnd = 0
        self._windows.clear()
        self._profile_pids.clear()
        if not self._detached:
            self._kill()
        self._detached = False
        self._popen = None
        self._pid = 0

    def _kill(self) -> None:
        pid = self._pid
        if not pid:
            return
        try:
            import psutil  # noqa: PLC0415

            proc = psutil.Process(pid)
            children = proc.children(recursive=True)
            for child in children:
                try:
                    child.kill()
                except Exception:
                    pass
            proc.kill()
            psutil.wait_procs(children + [proc], timeout=2)
            return
        except Exception:
            pass
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            log.debug("结束系统内核进程失败（pid=%s）", pid, exc_info=True)

    # ------------------------------------------------------------------ 快捷
    def screen_rect(self) -> QRect:
        """全屏 / 最大化时返回主窗口所在屏幕的区域（给隐身判断用）。"""
        if not self.is_fullscreen_like():
            return QRect()
        screen = self._main.screen()
        return screen.geometry() if screen is not None else QRect()
