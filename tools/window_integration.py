"""真实窗口集成测试：启动记事本，按标题找到它、隐藏、再恢复。

    python tools/window_integration.py
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from slackoff import winapi  # noqa: E402


def main() -> int:
    process = subprocess.Popen(["notepad.exe"])
    try:
        time.sleep(2.0)
        windows = winapi.find_client_windows(
            title_keywords=("记事本", "Notepad"),
            exclude_pids=set(),
            require_visible=True,
        )
        print("found windows:", [(w.hwnd, w.title, w.pid) for w in windows])
        if not windows:
            print("SKIP: 没有找到记事本窗口（可能是无交互桌面环境）")
            return 0

        hwnds = [w.hwnd for w in windows]
        hidden = winapi.hide_windows(hwnds)
        time.sleep(0.6)
        print("hidden:", hidden)
        print("visible after hide:", [h for h in hwnds if winapi.is_visible(h)])
        assert hidden, "没有隐藏任何窗口"
        assert not any(winapi.is_visible(h) for h in hidden), "隐藏后仍然可见"

        winapi.show_windows(hidden)
        time.sleep(0.6)
        print("visible after show:", [h for h in hwnds if winapi.is_visible(h)])
        assert any(winapi.is_visible(h) for h in hidden), "恢复后不可见"
        print("window hide/show OK")
        return 0
    finally:
        try:
            process.kill()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
