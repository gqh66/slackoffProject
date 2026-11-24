"""配置模型与持久化。

配置存在 ``data/config.json``（可用环境变量 ``SLACKOFF_HOME`` 换位置）。
读取时对缺失 / 类型错误 / 未知字段都尽量宽容，避免升级后启动失败。
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from . import paths
from .disguise import PRESETS
from .hotkeys import normalize_hotkey

log = logging.getLogger(__name__)

CONFIG_VERSION = 2


@dataclass
class BossSettings:
    """老板键行为。"""

    mute_audio: bool = True          # 隐藏时静音内嵌浏览器
    mute_others: bool = True         # 顺带静音其它程序的音频（爱奇艺等客户端）
    hide_external: bool = True       # 隐藏由本工具启动的外部播放器窗口
    pause_media: bool = True         # 尽量暂停网页里的 <video>
    decoy: bool = False              # 隐藏后显示伪装工作界面
    decoy_style: str = "code"        # code / excel


@dataclass
class StealthSettings:
    """隐身模式：鼠标移开（或长时间不动）自动隐藏。"""

    enabled: bool = True
    trigger: str = "leave"           # leave | idle
    leave_delay_ms: int = 1200
    idle_seconds: int = 180
    hot_corner: str = "left"         # left | right | top | bottom | none
    hot_corner_size: int = 12        # 感应条宽度（像素），大一点更好命中
    hot_corner_span: float = 0.6
    dwell_ms: int = 250
    show_edge_marker: bool = True    # 隐藏时在屏幕边缘留一条极细的提示条


@dataclass
class BrowserSettings:
    home_url: str = ""               # 留空则显示内置首页
    start_url: str = ""              # 启动时自动打开
    search_engine: str = "baidu"     # baidu | bing | google | sogou
    ua_mode: str = "chrome"          # chrome | default | mobile
    download_dir: str = ""
    mute_on_start: bool = False
    zoom: float = 1.0


@dataclass
class AppsSettings:
    """「我的应用」的行为。"""

    embed: bool = True               # 尽量把程序窗口嵌进摸鱼神器


@dataclass
class ReaderSettings:
    """TXT 阅读页的外观。"""

    theme: str = "yellow"            # yellow（护眼黄）| dark（暗色）


@dataclass
class DashboardSettings:
    """首页的小设置。"""

    work_end: str = "18:00"          # 下班时间 HH:MM


@dataclass
class DisguiseSettings:
    """左上角品牌 / 窗口外观的伪装。"""

    preset: str = "default"


@dataclass
class WindowSettings:
    always_on_top: bool = False
    start_maximized: bool = False
    close_action: str = "ask"   # ask（每次询问）/ tray（缩到托盘）/ quit（彻底退出）
    opacity: float = 1.0
    geometry: list[int] | None = None


@dataclass
class Settings:
    boss_key: str = "ctrl+alt+b"
    stealth_key: str = "ctrl+alt+h"
    boss: BossSettings = field(default_factory=BossSettings)
    stealth: StealthSettings = field(default_factory=StealthSettings)
    browser: BrowserSettings = field(default_factory=BrowserSettings)
    apps: AppsSettings = field(default_factory=AppsSettings)
    reader: ReaderSettings = field(default_factory=ReaderSettings)
    dashboard: DashboardSettings = field(default_factory=DashboardSettings)
    disguise: DisguiseSettings = field(default_factory=DisguiseSettings)
    window: WindowSettings = field(default_factory=WindowSettings)
    pinned_apps: list[dict] = field(default_factory=list)
    pinned_books: list[dict] = field(default_factory=list)
    custom_sites: list[dict] = field(default_factory=list)
    first_run: bool = True
    version: int = CONFIG_VERSION

    # ------------------------------------------------------------------ 读写
    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        path = path or paths.config_path()
        settings = cls()
        try:
            if path.is_file():
                raw = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    settings = cls.from_dict(raw)
        except Exception as exc:
            log.warning("读取配置失败（将使用默认值）：%s", exc)
        settings.normalize()
        return settings

    def save(self, path: Path | None = None) -> bool:
        path = path or paths.config_path()
        self.normalize()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
            fd, tmp = tempfile.mkstemp(prefix=".config-", suffix=".json", dir=str(path.parent))
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(payload)
                os.replace(tmp, path)
            finally:
                if os.path.exists(tmp):
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass
            return True
        except Exception as exc:
            log.error("保存配置失败：%s", exc)
            return False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    # ------------------------------------------------------------------ 解析
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Settings":
        s = cls()
        s.boss_key = _str(data.get("boss_key"), s.boss_key)
        s.stealth_key = _str(data.get("stealth_key"), s.stealth_key)
        s.first_run = _bool(data.get("first_run"), s.first_run)
        s.boss = _load_section(BossSettings, data.get("boss"))
        s.stealth = _load_section(StealthSettings, data.get("stealth"))
        s.browser = _load_section(BrowserSettings, data.get("browser"))
        s.apps = _load_section(AppsSettings, data.get("apps"))
        s.reader = _load_section(ReaderSettings, data.get("reader"))
        s.dashboard = _load_section(DashboardSettings, data.get("dashboard"))
        s.disguise = _load_section(DisguiseSettings, data.get("disguise"))
        s.window = _load_section(WindowSettings, data.get("window"))
        s.pinned_apps = _list_of_dicts(data.get("pinned_apps"))
        s.pinned_books = _list_of_dicts(data.get("pinned_books"))
        if not s.pinned_apps:
            # 旧版（v1）的「自定义应用」直接迁移成置顶应用
            s.pinned_apps = [
                {
                    "name": str(item.get("name") or ""),
                    "exe": str(item.get("exe") or ""),
                    "color": str(item.get("color") or ""),
                }
                for item in _list_of_dicts(data.get("custom_apps"))
                if str(item.get("exe") or "").strip()
            ]
        s.custom_sites = _list_of_dicts(data.get("custom_sites"))
        geometry = data.get("window", {}).get("geometry") if isinstance(data.get("window"), dict) else None
        if isinstance(geometry, (list, tuple)) and len(geometry) == 4:
            try:
                s.window.geometry = [int(v) for v in geometry]
            except (TypeError, ValueError):
                s.window.geometry = None
        return s

    # ------------------------------------------------------------------ 校验
    def normalize(self) -> None:
        self.boss_key = normalize_hotkey(self.boss_key) or "ctrl+alt+b"
        self.stealth_key = normalize_hotkey(self.stealth_key) or "ctrl+alt+h"
        if self.boss_key == self.stealth_key:
            self.stealth_key = "ctrl+alt+h" if self.boss_key != "ctrl+alt+h" else "ctrl+alt+j"

        b = self.boss
        b.decoy_style = b.decoy_style if b.decoy_style in ("code", "excel") else "code"

        self.reader.theme = self.reader.theme if self.reader.theme in ("yellow", "dark") else "yellow"
        self.dashboard.work_end = _normalise_time(self.dashboard.work_end, "18:00")
        if self.disguise.preset not in PRESETS:
            self.disguise.preset = "default"

        st = self.stealth
        st.trigger = st.trigger if st.trigger in ("leave", "idle") else "leave"
        st.hot_corner = st.hot_corner if st.hot_corner in ("left", "right", "top", "bottom", "none") else "left"
        st.leave_delay_ms = _clamp_int(st.leave_delay_ms, 200, 15000, 1200)
        st.idle_seconds = _clamp_int(st.idle_seconds, 10, 7200, 180)
        st.hot_corner_size = _clamp_int(st.hot_corner_size, 2, 40, 12)
        st.hot_corner_span = _clamp_float(st.hot_corner_span, 0.1, 1.0, 0.6)
        st.dwell_ms = _clamp_int(st.dwell_ms, 100, 5000, 250)

        br = self.browser
        br.search_engine = br.search_engine if br.search_engine in ("baidu", "bing", "google", "sogou") else "baidu"
        br.ua_mode = br.ua_mode if br.ua_mode in ("chrome", "default", "mobile") else "chrome"
        br.zoom = _clamp_float(br.zoom, 0.5, 2.5, 1.0)

        w = self.window
        w.close_action = w.close_action if w.close_action in ("ask", "tray", "quit") else "ask"
        w.opacity = _clamp_float(w.opacity, 0.35, 1.0, 1.0)
        if w.geometry and len(w.geometry) != 4:
            w.geometry = None

        # 去重、去掉空条目，保证左侧列表稳定
        cleaned: list[dict] = []
        seen: set[str] = set()
        for entry in self.pinned_apps:
            if not isinstance(entry, dict):
                continue
            exe = str(entry.get("exe") or "").strip()
            if not exe:
                continue
            key = os.path.normcase(os.path.abspath(exe))
            if key in seen:
                continue
            seen.add(key)
            name = str(entry.get("name") or "").strip() or Path(exe).stem
            cleaned.append(
                {
                    "id": str(entry.get("id") or "").strip(),
                    "name": name,
                    "exe": exe,
                    "color": str(entry.get("color") or "").strip(),
                }
            )
        self.pinned_apps = cleaned

        # 电子书同样去重
        book_cleaned: list[dict] = []
        book_seen: set[str] = set()
        for entry in self.pinned_books:
            if not isinstance(entry, dict):
                continue
            path = str(entry.get("path") or "").strip()
            if not path:
                continue
            key = os.path.normcase(os.path.abspath(path))
            if key in book_seen:
                continue
            book_seen.add(key)
            book_cleaned.append(
                {
                    "id": str(entry.get("id") or "").strip(),
                    "name": str(entry.get("name") or "").strip() or Path(path).stem,
                    "path": path,
                }
            )
        self.pinned_books = book_cleaned

    # ------------------------------------------------------------------ 便捷


# ---------------------------------------------------------------------- 工具
def _normalise_time(value: Any, default: str) -> str:
    text = str(value or "").strip()
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", text)
    if not match:
        return default
    hour, minute = int(match.group(1)), int(match.group(2))
    if not (0 <= hour < 24 and 0 <= minute < 60):
        return default
    return f"{hour:02d}:{minute:02d}"


def _str(value: Any, default: str) -> str:
    return value if isinstance(value, str) else default


def _bool(value: Any, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _int(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _float(value: Any, default: float) -> float:
    if isinstance(value, bool):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp_int(value: Any, low: int, high: int, default: int) -> int:
    return max(low, min(high, _int(value, default)))


def _clamp_float(value: Any, low: float, high: float, default: float) -> float:
    return max(low, min(high, _float(value, default)))


def _list_of_dicts(value: Any) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _load_section(cls, data: Any):
    section = cls()
    if not isinstance(data, dict):
        return section
    for f in section.__dataclass_fields__.values():  # type: ignore[attr-defined]
        if f.name not in data:
            continue
        raw = data[f.name]
        default = getattr(section, f.name)
        if isinstance(default, bool):
            setattr(section, f.name, _bool(raw, default))
        elif isinstance(default, int):
            setattr(section, f.name, _int(raw, default))
        elif isinstance(default, float):
            setattr(section, f.name, _float(raw, default))
        elif isinstance(default, str):
            setattr(section, f.name, _str(raw, default))
        elif default is None:
            setattr(section, f.name, raw if isinstance(raw, list) else None)
    return section
