"""把第三方程序的主窗口嵌进摸鱼神器。

Windows 没有官方的「应用内嵌」接口，这里用的是经典的窗口重父化（SetParent）：
启动程序 → 等它的顶层窗口出现 → 去掉标题栏 / 边框，设成 WS_CHILD，挂到 Qt 容器里。

不是所有程序都吃这一套：部分 Chromium / Electron 内核的客户端、UWP 或带 DRM 的播放器
可能黑屏或拒绝成为子窗口。失败时会保留原来的独立窗口，并给出提示。
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import logging
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import QWidget

from . import apps, winapi

log = logging.getLogger(__name__)


@dataclass
class Embedded:
    app: apps.PinnedApp
    hwnd: int
    pid: int
    original_style: int
    original_rect: tuple[int, int, int, int]


class EmbedContainer(QWidget):
    """给外部窗口当宿主的黑底容器；尺寸变化时通知嵌入器。"""

    resized = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)
        self.setAutoFillBackground(True)
        self.setStyleSheet("background: #05070A;")

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.resized.emit()


class WindowEmbedder(QObject):
    ready = Signal(object)   # Embedded
    extraEmbedded = Signal(object)  # 播放器 / 弹窗等次级窗口
    extraBlocked = Signal(str)      # 有独立视频窗口无法嵌入
    failed = Signal(str)
    closed = Signal()

    START_TIMEOUT_MS = 15000
    SETTLE_MS = 700

    def __init__(self, container: QWidget, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._container = container
        self._container.setAttribute(Qt.WidgetAttribute.WA_NativeWindow, True)

        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._tick)

        self._watch = QTimer(self)
        self._watch.setInterval(900)
        self._watch.timeout.connect(self._scan_embedded)

        self._popen: subprocess.Popen | None = None
        self._app: apps.PinnedApp | None = None
        self._embedded: list[Embedded] = []
        self._visible_hwnd = 0
        self._failed: set[int] = set()
        self._candidates: dict[int, float] = {}
        self._family_dir = ""
        self._family_dir_safe = False
        self._target_exe = ""
        self._direct = 0
        self._before: set[int] = set()
        self._started = 0.0
        self._candidate = 0
        self._candidate_since = 0.0
        self._container_hwnd = 0
        self._saw_uwp = False

    # ------------------------------------------------------------------ 状态
    @property
    def current(self) -> Embedded | None:
        for item in self._embedded:
            if item.hwnd == self._visible_hwnd:
                return item
        return self._embedded[0] if self._embedded else None

    def pids(self) -> set[int]:
        result: set[int] = set()
        if self._popen is not None:
            try:
                result.add(int(self._popen.pid))
            except Exception:
                pass
        result.update(item.pid for item in self._embedded)
        try:
            import psutil  # noqa: PLC0415

            for pid in list(result):
                try:
                    proc = psutil.Process(pid)
                    result.update(child.pid for child in proc.children(recursive=True))
                except Exception:
                    continue
        except Exception:
            pass
        return result

    # ------------------------------------------------------------------ 打开
    def start(self, app: apps.PinnedApp) -> bool:
        self.detach()
        self._app = app
        self._candidate = 0
        self._popen = None
        self._direct = 0
        self._saw_uwp = False
        self._failed.clear()
        self._candidates.clear()
        self._family_dir = os.path.normcase(str(Path(app.exe).parent))
        self._target_exe = os.path.normcase(os.path.abspath(app.exe))
        broad_dirs = {
            os.path.normcase(os.environ.get("SystemRoot", "C:\\Windows")),
            os.path.normcase(os.environ.get("ProgramFiles", "C:\\Program Files")),
            os.path.normcase(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")),
        }
        self._family_dir_safe = self._family_dir not in broad_dirs
        self._before = {w.hwnd for w in winapi.enumerate_windows(visible_only=True)}

        existing = self._find_existing(app)
        if existing:
            log.info("发现 %s 已经在运行，直接嵌入现有窗口", app.name)
            self._direct = existing
            self._started = time.monotonic()
            self._timer.start()
            return True

        try:
            self._popen = subprocess.Popen(
                [app.exe], cwd=str(Path(app.exe).parent), close_fds=True
            )
        except OSError as exc:
            self.failed.emit(f"启动 {app.name} 失败：{exc}")
            return False

        self._started = time.monotonic()
        self._timer.start()
        log.info("准备嵌入 %s（pid=%s）", app.name, self._popen.pid)
        return True

    def _find_existing(self, app: apps.PinnedApp) -> int:
        target = os.path.normcase(os.path.abspath(app.exe))
        best_hwnd = 0
        best_area = 0
        for window in winapi.enumerate_windows(visible_only=True):
            if not window.title or window.pid == os.getpid() or winapi.get_parent(window.hwnd):
                continue
            left, top, right, bottom = winapi.window_rect(window.hwnd)
            width, height = right - left, bottom - top
            if width < 200 or height < 120:
                continue
            exe_path = winapi.process_path(window.pid)
            if not exe_path:
                continue
            if os.path.normcase(os.path.abspath(exe_path)) != target:
                continue
            area = width * height
            if area > best_area:
                best_area = area
                best_hwnd = window.hwnd
        return best_hwnd

    def _tick(self) -> None:
        if self._embedded:
            self._timer.stop()
            return
        if self._app is None:
            self._timer.stop()
            return
        now = time.monotonic()
        if (now - self._started) * 1000 > self.START_TIMEOUT_MS:
            self._timer.stop()
            log.warning("等待 %s 的窗口超时", self._app.name)
            if self._saw_uwp:
                self.failed.emit(
                    "这是 Windows 商店应用（UWP，例如新版记事本 / 画图），"
                    "系统不允许把它嵌进别的窗口，请用独立窗口打开。"
                )
            else:
                self.failed.emit(
                    "没有等到程序的主窗口。它可能还在启动、只有托盘图标，或者被安全软件拦住了。"
                )
            return

        if self._direct:
            hwnd = self._direct
            self._direct = 0
            if winapi.is_window(hwnd) and not winapi.get_parent(hwnd):
                self._embed(hwnd)
            return

        candidate = self._find_candidate()
        if candidate == 0:
            return
        if candidate != self._candidate:
            self._candidate = candidate
            self._candidate_since = now
            return
        if (now - self._candidate_since) * 1000 < self.SETTLE_MS:
            return
        self._embed(candidate)

    def _find_candidate(self) -> int:
        assert self._app is not None
        target = os.path.normcase(os.path.abspath(self._app.exe))
        app_name = self._app.name.lower()
        stem = Path(self._app.exe).stem.lower()
        launched_pid = int(self._popen.pid) if self._popen is not None else -1

        best_hwnd = 0
        best_score = -1.0
        for window in winapi.enumerate_windows(visible_only=True):
            if not window.title or window.hwnd in self._before:
                continue
            if window.pid == os.getpid():
                continue
            if window.class_name in ("Progman", "WorkerW", "Shell_TrayWnd", "Windows.UI.Core.CoreWindow"):
                continue
            if window.class_name == "ApplicationFrameWindow":
                self._saw_uwp = True
                continue
            if winapi.get_parent(window.hwnd):
                continue
            left, top, right, bottom = winapi.window_rect(window.hwnd)
            width, height = right - left, bottom - top
            if width < 200 or height < 120:
                continue

            score = 0.0
            if window.pid == launched_pid:
                score += 100
            exe_path = winapi.process_path(window.pid)
            if exe_path:
                normalised = os.path.normcase(os.path.abspath(exe_path))
                if normalised == target:
                    score += 60
            title = window.title.lower()
            if app_name and app_name in title:
                score += 30
            if stem and stem in title:
                score += 20
            score += min(20.0, (width * height) / 200000.0)

            if score > best_score:
                best_score = score
                best_hwnd = window.hwnd
        return best_hwnd if best_score >= 40 else 0

    def _embed(self, hwnd: int) -> bool:
        if self._app is None:
            return False
        primary = not self._embedded
        if winapi.class_name(hwnd) == "ApplicationFrameWindow":
            if primary:
                self._timer.stop()
                self.failed.emit(
                    "这是 Windows 商店应用（UWP），系统不允许嵌入，请用独立窗口打开。"
                )
            return False
        self._container_hwnd = int(self._container.winId())
        if not self._container_hwnd:
            if primary:
                self._timer.stop()
                self.failed.emit("窗口容器还没有准备好，无法嵌入。")
            return False

        original_style = winapi.get_window_style(hwnd)
        original_rect = winapi.window_rect(hwnd)
        if not original_style:
            if primary:
                self._timer.stop()
                self.failed.emit("拿不到程序窗口的样式，无法嵌入。")
            return False

        try:
            user32 = ctypes.windll.user32
            target_ctx = user32.GetWindowDpiAwarenessContext(wt.HWND(hwnd))
            container_ctx = user32.GetWindowDpiAwarenessContext(wt.HWND(self._container_hwnd))
            log.debug(
                "embed: target hwnd=%s pid=%s style=0x%x parent=%s class=%s dpi=%s; "
                "container hwnd=%s style=0x%x parent=%s class=%s dpi=%s",
                hwnd, winapi.window_pid(hwnd), original_style, winapi.get_parent(hwnd),
                winapi.class_name(hwnd), user32.GetAwarenessFromDpiAwarenessContext(target_ctx),
                self._container_hwnd, winapi.get_window_style(self._container_hwnd),
                winapi.get_parent(self._container_hwnd), winapi.class_name(self._container_hwnd),
                user32.GetAwarenessFromDpiAwarenessContext(container_ctx),
            )
        except Exception:
            pass

        child_style = (original_style | winapi.WS_CHILD) & ~(
            winapi.WS_POPUP
            | winapi.WS_CAPTION
            | winapi.WS_THICKFRAME
            | winapi.WS_BORDER
            | winapi.WS_SYSMENU
            | winapi.WS_MINIMIZEBOX
            | winapi.WS_MAXIMIZEBOX
        )
        winapi.set_window_style(hwnd, child_style)
        if not winapi.set_parent(hwnd, self._container_hwnd):
            winapi.set_window_style(hwnd, original_style)
            if primary:
                self._timer.stop()
                log.warning("SetParent 失败：%s", self._app.name)
                self.failed.emit(
                    "这个程序拒绝被嵌入（可能是 UWP / 受保护程序），已保持独立窗口。"
                )
            else:
                log.warning("次级窗口拒绝嵌入：hwnd=%s", hwnd)
            return False

        info = Embedded(
            app=self._app,
            hwnd=hwnd,
            pid=winapi.window_pid(hwnd),
            original_style=original_style,
            original_rect=original_rect,
        )
        self._embedded.append(info)
        if primary:
            self._visible_hwnd = hwnd
            self._show_only(info)
            self._timer.stop()
            self._watch.start()
            log.info("已嵌入 %s（hwnd=%s）", self._app.name, hwnd)
            self.ready.emit(info)
        else:
            self._show_only(info)
            self._watch.start()
            log.info("已嵌入 %s 的次级窗口（hwnd=%s，%s）", self._app.name, hwnd,
                     winapi.window_title(hwnd))
            self.extraEmbedded.emit(info)
        return True

    def _show_only(self, target: Embedded) -> None:
        for item in self._embedded:
            if item is not target and winapi.is_window(item.hwnd):
                winapi.hide_window(item.hwnd)
        self._visible_hwnd = target.hwnd
        width, height = self._container_pixels()
        winapi.move_window(target.hwnd, 0, 0, width, height)
        winapi.show_window(target.hwnd)

    # ------------------------------------------------------------------ 维护
    def _container_pixels(self) -> tuple[int, int]:
        ratio = float(self._container.devicePixelRatioF() or 1.0)
        return (
            max(1, int(self._container.width() * ratio)),
            max(1, int(self._container.height() * ratio)),
        )

    def resize(self) -> None:
        width, height = self._container_pixels()
        for item in self._embedded:
            if winapi.is_window(item.hwnd):
                winapi.move_window(item.hwnd, 0, 0, width, height)

    def _is_child(self, hwnd: int) -> bool:
        return bool(winapi.get_window_style(hwnd) & winapi.WS_CHILD)

    def _belongs_to_family(self, window) -> bool:
        if not self._target_exe:
            return False
        exe_path = winapi.process_path(window.pid)
        if not exe_path:
            return False
        normalised = os.path.normcase(os.path.abspath(exe_path))
        if normalised == self._target_exe:
            return True
        if self._family_dir_safe and normalised.startswith(self._family_dir + os.sep):
            return True
        return os.path.basename(normalised) == os.path.basename(self._target_exe)

    def _scan_embedded(self) -> None:
        if not self._embedded:
            self._watch.stop()
            return

        alive = [item for item in self._embedded if winapi.is_window(item.hwnd)]
        if not alive:
            log.info("嵌入的程序已退出")
            self._embedded = []
            self._visible_hwnd = 0
            self._watch.stop()
            self.closed.emit()
            return
        if len(alive) != len(self._embedded):
            self._embedded = alive
            if self._visible_hwnd not in {item.hwnd for item in alive}:
                self._show_only(alive[-1])

        # 当前显示的子窗口被程序自己隐藏了（比如播放器关闭），切回主界面
        container_shown = (
            self._container.isVisible()
            and self._container.window().isVisible()
            and not self._container.window().isMinimized()
        )
        if container_shown:
            visible_item = next(
                (item for item in alive if item.hwnd == self._visible_hwnd), None
            )
            if visible_item is not None and not winapi.is_visible(visible_item.hwnd):
                fallback = next(
                    (item for item in reversed(alive) if winapi.is_visible(item.hwnd)),
                    alive[0],
                )
                self._show_only(fallback)

        self._scan_new_windows()

    def _scan_new_windows(self) -> None:
        if self._app is None:
            return
        now = time.monotonic()
        candidates: dict[int, int] = {}
        embedded = {item.hwnd for item in self._embedded}
        for window in winapi.enumerate_windows(visible_only=True):
            if window.hwnd in self._before or window.hwnd in self._failed:
                continue
            if window.hwnd in embedded or window.pid == os.getpid():
                continue
            if not window.title:
                continue
            if any(
                junk in window.title
                for junk in ("PayMask", "MaskBrowser", "Advert", "广告", "Tips", "Toast")
            ):
                continue
            if self._is_child(window.hwnd):
                continue
            if window.class_name in (
                "Progman", "WorkerW", "Shell_TrayWnd", "Windows.UI.Core.CoreWindow",
                "ApplicationFrameWindow", "Intermediate D3D Window",
            ):
                continue
            left, top, right, bottom = winapi.window_rect(window.hwnd)
            width, height = right - left, bottom - top
            if width < 200 or height < 120:
                continue
            if not self._belongs_to_family(window):
                continue
            candidates[window.hwnd] = width * height

        # 只保留连续 1.6 秒都存在的窗口，避免把启动瞬间的辅助窗口当成播放器
        stable: dict[int, int] = {}
        for hwnd, area in candidates.items():
            first_seen = self._candidates.get(hwnd)
            if first_seen is None:
                self._candidates[hwnd] = now
                continue
            if now - first_seen >= 1.6:
                stable[hwnd] = area
        self._candidates = {
            hwnd: first_seen
            for hwnd, first_seen in self._candidates.items()
            if hwnd in candidates or hwnd in stable
        }

        # 先嵌小的，最后嵌最大的，让播放器 / 主内容显示在最前面
        for hwnd, _area in sorted(stable.items(), key=lambda item: item[1]):
            if self._embed(hwnd):
                self._candidates.pop(hwnd, None)
            else:
                self._failed.add(hwnd)
                title = winapi.window_title(hwnd)
                if title:
                    self.extraBlocked.emit(title)

    # ------------------------------------------------------------------ 分离
    def detach(self) -> None:
        self._timer.stop()
        self._watch.stop()
        self._candidates.clear()
        items = list(self._embedded)
        self._embedded = []
        self._visible_hwnd = 0
        for item in reversed(items):
            try:
                if winapi.is_window(item.hwnd):
                    winapi.set_parent(item.hwnd, 0)
                    winapi.set_window_style(item.hwnd, item.original_style)
                    left, top, right, bottom = item.original_rect
                    if right > left and bottom > top:
                        winapi.move_window(item.hwnd, left, top, right - left, bottom - top)
                    winapi.show_window(item.hwnd)
            except Exception:
                log.exception("恢复独立窗口失败")
        if items:
            winapi.set_foreground(items[0].hwnd)
            log.info("已从摸鱼神器中分离 %s", items[0].app.name)

    def stop(self) -> None:
        self.detach()
        self._app = None
        self._popen = None
