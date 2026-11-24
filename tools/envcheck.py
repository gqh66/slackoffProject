"""检查运行环境里的可选能力：全局热键、按进程静音、窗口枚举。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from slackoff import winapi  # noqa: E402
from slackoff.audio import AudioMuter  # noqa: E402


def check_keyboard() -> None:
    try:
        import keyboard
    except Exception as exc:
        print("keyboard import failed:", exc)
        return
    try:
        handle = keyboard.add_hotkey("ctrl+alt+b", lambda: None, suppress=False)
        print("hotkey registered ok:", handle is not None)
        keyboard.remove_hotkey(handle)
    except Exception as exc:
        print("hotkey registration failed:", type(exc).__name__, exc)


def check_audio() -> None:
    muter = AudioMuter()
    print("audio available:", muter.available, muter.reason)
    if muter.available:
        saved = muter.mute_others({os.getpid()})
        print("sessions muted:", len(saved))
        muter.restore(saved)
        print("sessions restored")


def check_windows() -> None:
    windows = winapi.enumerate_windows()
    visible = [w for w in windows if w.visible and w.title]
    print("top-level windows:", len(windows), "visible with title:", len(visible))
    my_pid = os.getpid()
    path = winapi.process_path(my_pid)
    print("own process path:", path)
    found = winapi.find_client_windows(
        exe_names={"python.exe"}, title_keywords=(), exclude_pids=set()
    )
    print("visible python windows:", len(found))


if __name__ == "__main__":
    check_keyboard()
    check_audio()
    check_windows()
