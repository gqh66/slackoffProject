"""全局快捷键。

解析部分（``normalize_hotkey`` / ``format_hotkey`` / ``hotkey_to_qt``）是纯函数，
方便单独测试。注册部分优先使用 Windows 自带的 ``RegisterHotKey``：
系统级生效、窗口隐藏也能用、还能发现组合键被别的程序占用；
失败时退回 ``keyboard`` 低级钩子；再失败就由主窗口注册窗口内快捷键。
"""

from __future__ import annotations

import logging
from typing import Callable

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal
from PySide6.QtWidgets import QApplication

log = logging.getLogger(__name__)

BOSS_HOTKEY_ID = 0xB0B0
STEALTH_HOTKEY_ID = 0x5EA7

MODIFIER_ORDER = ("ctrl", "alt", "shift", "win")

_MODIFIER_ALIASES = {
    "ctrl": "ctrl",
    "control": "ctrl",
    "ctl": "ctrl",
    "alt": "alt",
    "option": "alt",
    "shift": "shift",
    "win": "win",
    "windows": "win",
    "super": "win",
    "meta": "win",
    "cmd": "win",
}

_NAMED_KEYS = {
    "space": ("space", "Space"),
    "tab": ("tab", "Tab"),
    "enter": ("enter", "Return"),
    "return": ("enter", "Return"),
    "escape": ("escape", "Esc"),
    "esc": ("escape", "Esc"),
    "backspace": ("backspace", "Backspace"),
    "insert": ("insert", "Ins"),
    "ins": ("insert", "Ins"),
    "delete": ("delete", "Del"),
    "del": ("delete", "Del"),
    "home": ("home", "Home"),
    "end": ("end", "End"),
    "page up": ("page up", "PgUp"),
    "pgup": ("page up", "PgUp"),
    "page down": ("page down", "PgDn"),
    "pgdn": ("page down", "PgDn"),
    "up": ("up", "Up"),
    "down": ("down", "Down"),
    "left": ("left", "Left"),
    "right": ("right", "Right"),
    "print screen": ("print screen", "PrtSc"),
    "prtsc": ("print screen", "PrtSc"),
    "pause": ("pause", "Pause"),
    "scroll lock": ("scroll lock", "ScrollLock"),
    "caps lock": ("caps lock", "CapsLock"),
    "num lock": ("num lock", "NumLock"),
    "menu": ("menu", "Menu"),
}

_PUNCT_KEYS = {
    "-": ("-", "-"),
    "=": ("=", "="),
    "[": ("[", "["),
    "]": ("]", "]"),
    "\\": ("\\", "\\"),
    ";": (";", ";"),
    "'": ("'", "'"),
    ",": (",", ","),
    ".": (".", "."),
    "/": ("/", "/"),
    "`": ("`", "`"),
}

_DISPLAY_MOD = {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "win": "Win"}


def _canonical_key(token: str) -> tuple[str, str] | None:
    """把单个按键名转成 (keyboard 写法, Qt 写法)。"""
    t = token.strip().lower()
    if not t:
        return None
    if len(t) == 1 and (t.isalpha() or t.isdigit()):
        return t, t.upper()
    if t.startswith("f") and t[1:].isdigit() and 1 <= int(t[1:]) <= 24:
        return t, t.upper()
    if t in _NAMED_KEYS:
        return _NAMED_KEYS[t]
    if t in _PUNCT_KEYS:
        return _PUNCT_KEYS[t]
    return None


def normalize_hotkey(text: str | None) -> str | None:
    """把用户输入规范成 ``ctrl+shift+b`` 形式；非法组合返回 None。

    规则：至少含 ctrl / alt / win 中的一个（避免单键热键把正常打字吞掉），
    且必须有一个非修饰键。
    """
    if not text or not isinstance(text, str):
        return None
    parts = [p.strip().lower() for p in text.split("+") if p.strip()]
    if not parts:
        return None

    mods: list[str] = []
    keys: list[str] = []
    for part in parts:
        if part in _MODIFIER_ALIASES:
            mod = _MODIFIER_ALIASES[part]
            if mod not in mods:
                mods.append(mod)
        else:
            keys.append(part)

    if len(keys) != 1:
        return None
    if not any(m in ("ctrl", "alt", "win") for m in mods):
        return None
    key = _canonical_key(keys[0])
    if key is None:
        return None

    ordered = [m for m in MODIFIER_ORDER if m in mods]
    return "+".join(ordered + [key[0]])


def format_hotkey(text: str | None) -> str:
    """给界面用的漂亮写法，例如 ``Ctrl + Shift + B``。"""
    normalized = normalize_hotkey(text)
    if not normalized:
        return (text or "").strip() or "未设置"
    pieces = []
    for part in normalized.split("+"):
        if part in _DISPLAY_MOD:
            pieces.append(_DISPLAY_MOD[part])
        else:
            key = _canonical_key(part)
            pieces.append(key[1] if key else part.upper())
    return " + ".join(pieces)


def hotkey_to_qt(text: str | None) -> str:
    """转成 QKeySequence 认得的字符串，例如 ``Ctrl+Shift+B``。"""
    normalized = normalize_hotkey(text)
    if not normalized:
        return ""
    pieces = []
    for part in normalized.split("+"):
        if part in _DISPLAY_MOD:
            pieces.append("Meta" if part == "win" else _DISPLAY_MOD[part])
        else:
            key = _canonical_key(part)
            pieces.append(key[1] if key else part.upper())
    return "+".join(pieces)


def backend_hotkey(text: str | None) -> str:
    """``keyboard`` 库把 Windows 键叫做 ``windows``，这里做一次转换。"""
    normalized = normalize_hotkey(text)
    if not normalized:
        return ""
    return "+".join("windows" if part == "win" else part for part in normalized.split("+"))


_VK_CODES = {
    "space": 0x20,
    "tab": 0x09,
    "enter": 0x0D,
    "escape": 0x1B,
    "backspace": 0x08,
    "insert": 0x2D,
    "delete": 0x2E,
    "home": 0x24,
    "end": 0x23,
    "page up": 0x21,
    "page down": 0x22,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
    "print screen": 0x2C,
    "pause": 0x13,
    "scroll lock": 0x91,
    "caps lock": 0x14,
    "num lock": 0x90,
    "menu": 0x5D,
    "-": 0xBD,
    "=": 0xBB,
    "[": 0xDB,
    "]": 0xDD,
    "\\": 0xDC,
    ";": 0xBA,
    "'": 0xDE,
    ",": 0xBC,
    ".": 0xBE,
    "/": 0xBF,
    "`": 0xC0,
}

_MODIFIER_BITS = {"alt": 0x0001, "ctrl": 0x0002, "shift": 0x0004, "win": 0x0008}


def to_native(text: str | None) -> tuple[int, int] | None:
    """把 ``ctrl+shift+b`` 转成 RegisterHotKey 需要的 (modifiers, vk)。"""
    normalized = normalize_hotkey(text)
    if not normalized:
        return None
    modifiers = 0
    vk = None
    for part in normalized.split("+"):
        if part in _MODIFIER_BITS:
            modifiers |= _MODIFIER_BITS[part]
        elif len(part) == 1 and part.isalpha():
            vk = ord(part.upper())
        elif len(part) == 1 and part.isdigit():
            vk = ord(part)
        elif part.startswith("f") and part[1:].isdigit() and 1 <= int(part[1:]) <= 24:
            vk = 0x6F + int(part[1:])
        else:
            vk = _VK_CODES.get(part)
    if vk is None:
        return None
    return modifiers, vk


class _HotkeyFilter(QAbstractNativeEventFilter):
    """接收窗口消息里的 WM_HOTKEY。"""

    def __init__(self, callback) -> None:
        super().__init__()
        self._callback = callback

    def nativeEventFilter(self, event_type, message):  # noqa: N802 - Qt 命名
        try:
            if event_type in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
                import ctypes.wintypes as wt  # noqa: PLC0415

                msg = wt.MSG.from_address(int(message))
                if msg.message == 0x0312:  # WM_HOTKEY
                    self._callback(int(msg.wParam))
                    return True, 0
        except Exception:
            pass
        return False, 0


class GlobalHotkeys(QObject):
    """系统级热键。窗口隐藏时也有效；注册失败时降级为窗口内快捷键。"""

    bossPressed = Signal()
    stealthPressed = Signal()
    availabilityChanged = Signal(bool, str)

    def __init__(self, parent: QObject | None = None, hwnd: int = 0) -> None:
        super().__init__(parent)
        self._hwnd = int(hwnd or 0)
        self._keyboard = None
        self._handles: list[object] = []
        self._native_ids: list[int] = []
        self._filter: _HotkeyFilter | None = None
        self._native_problem = ""
        self._boss_key: str | None = None
        self._stealth_key: str | None = None
        self._available = False
        self._message = "尚未初始化"

    # ------------------------------------------------------------------ 属性
    @property
    def available(self) -> bool:
        return self._available

    @property
    def message(self) -> str:
        return self._message

    # ------------------------------------------------------------------ 注册
    def attach(self, boss_key: str, stealth_key: str) -> bool:
        """（重新）注册老板键与隐身热键，返回是否全部成功。"""
        self._unhook_all()
        self._boss_key = normalize_hotkey(boss_key)
        self._stealth_key = normalize_hotkey(stealth_key)
        if self._attach_native():
            return True
        return self._attach_keyboard()

    def _attach_native(self) -> bool:
        if not self._hwnd:
            return False
        try:
            from . import winapi  # noqa: PLC0415
        except Exception:
            return False
        if not winapi.IS_WINDOWS:
            return False

        self._native_problem = ""
        problems: list[str] = []
        for hotkey_id, key in (
            (BOSS_HOTKEY_ID, self._boss_key),
            (STEALTH_HOTKEY_ID, self._stealth_key),
        ):
            native = to_native(key)
            if native is None:
                problems.append(f"{format_hotkey(key)} 无法转换为系统热键")
                continue
            if not winapi.register_hotkey(self._hwnd, hotkey_id, native[0], native[1]):
                problems.append(f"{format_hotkey(key)} 可能已被其它程序占用")
                continue
            self._native_ids.append(hotkey_id)

        if problems:
            for hotkey_id in self._native_ids:
                winapi.unregister_hotkey(self._hwnd, hotkey_id)
            self._native_ids.clear()
            self._native_problem = "；".join(problems)
            log.warning("原生热键注册失败：%s", self._native_problem)
            return False

        self._install_filter()
        self._set_available(True, "系统级热键已生效，窗口隐藏时也可以使用")
        return True

    def _install_filter(self) -> None:
        if self._filter is not None:
            return
        app = QApplication.instance()
        if app is None:
            return
        self._filter = _HotkeyFilter(self._on_native_hotkey)
        app.installNativeEventFilter(self._filter)

    def _on_native_hotkey(self, hotkey_id: int) -> None:
        if hotkey_id == BOSS_HOTKEY_ID:
            self.bossPressed.emit()
        elif hotkey_id == STEALTH_HOTKEY_ID:
            self.stealthPressed.emit()

    def _attach_keyboard(self) -> bool:
        kb = self._load_backend()
        if kb is None:
            self._set_available(False, self._native_problem or self._message)
            return False

        ok = True
        problems: list[str] = []
        for key, callback, label in (
            (self._boss_key, self.bossPressed.emit, "老板键"),
            (self._stealth_key, self.stealthPressed.emit, "隐身键"),
        ):
            if not key:
                ok = False
                problems.append(f"{label}格式无效")
                continue
            try:
                handle = kb.add_hotkey(backend_hotkey(key), self._make_callback(callback), suppress=False)
                self._handles.append(handle)
            except Exception as exc:
                ok = False
                problems.append(f"{label} {format_hotkey(key)} 注册失败：{exc}")
                log.warning("注册热键失败 %s: %s", key, exc)

        if ok:
            self._set_available(True, "全局热键已生效（键盘钩子）")
        else:
            # 有任何一个注册失败就把已注册的清掉，避免和窗口内快捷键重复触发
            self._unhook_all()
            message = "；".join(problems) or "热键注册失败"
            if self._native_problem:
                message = f"{message}（系统热键：{self._native_problem}）"
            self._set_available(False, message)
        return ok

    def _load_backend(self):
        if self._keyboard is not None:
            return self._keyboard
        try:
            import keyboard  # noqa: PLC0415

            self._keyboard = keyboard
        except Exception as exc:  # pragma: no cover - 依赖环境
            self._message = f"无法加载 keyboard：{exc}"
            log.warning("无法加载 keyboard：%s", exc)
            return None
        return self._keyboard

    def _make_callback(self, emit: Callable[[], None]):
        def _cb() -> None:
            try:
                emit()
            except Exception:  # pragma: no cover - 防御钩子线程异常
                log.exception("热键回调出错")

        return _cb

    def _set_available(self, value: bool, message: str) -> None:
        self._available = value
        self._message = message
        self.availabilityChanged.emit(value, message)

    # ------------------------------------------------------------------ 清理
    def _unhook_all(self) -> None:
        if self._native_ids:
            try:
                from . import winapi  # noqa: PLC0415

                for hotkey_id in self._native_ids:
                    winapi.unregister_hotkey(self._hwnd, hotkey_id)
            except Exception:
                pass
            self._native_ids.clear()
        if self._filter is not None:
            app = QApplication.instance()
            if app is not None:
                try:
                    app.removeNativeEventFilter(self._filter)
                except Exception:
                    pass
            self._filter = None

        kb = self._keyboard
        if kb is not None:
            for handle in self._handles:
                try:
                    kb.remove_hotkey(handle)
                except Exception:  # pragma: no cover
                    pass
        self._handles.clear()

    def detach(self) -> None:
        self._unhook_all()
        self._set_available(False, "已停止监听全局热键")


def suggested_keys() -> list[str]:
    """设置界面里给用户参考的推荐组合。"""
    return ["ctrl+alt+b", "ctrl+alt+h", "alt+shift+b", "ctrl+shift+f9", "ctrl+alt+`"]
