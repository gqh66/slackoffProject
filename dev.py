"""开发热重载启动器。

    python dev.py            # 和 run.bat 一样启动，但会监视源码
    python dev.py --debug    # 额外参数会透传给 main.py

修改 slackoff/ 下的 .py 或 main.py 后，会杀掉旧的进程树并自动重启。
这只影响开发；普通用户直接 run.bat 即可。
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = ROOT / "main.py"
IGNORE_PARTS = {
    "__pycache__", ".venv", "venv", "data", "docs", ".git",
    "build", "dist", ".ruff_cache",
}


def _setup_console() -> None:
    """用 pythonw 启动时没有控制台，把输出写到 data/dev.log。"""
    if sys.stdout is not None:
        return
    log_dir = ROOT / "data"
    log_dir.mkdir(parents=True, exist_ok=True)
    stream = open(log_dir / "dev.log", "a", encoding="utf-8", buffering=1)
    sys.stdout = stream
    sys.stderr = stream


def _log(message: str) -> None:
    print(message, flush=True)


def snapshot() -> dict[str, int]:
    result: dict[str, int] = {}
    for base in (ROOT, ROOT / "slackoff"):
        for path in base.rglob("*.py"):
            if any(part in IGNORE_PARTS for part in path.parts):
                continue
            try:
                result[str(path)] = path.stat().st_mtime_ns
            except OSError:
                pass
    return result


def start_app() -> subprocess.Popen:
    command = [sys.executable, str(APP), *sys.argv[1:]]
    _log("[dev] 启动: " + " ".join(command))
    return subprocess.Popen(command, cwd=str(ROOT))


def stop_app(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                timeout=10,
            )
        else:
            process.terminate()
        process.wait(timeout=5)
    except Exception:
        try:
            process.kill()
        except Exception:
            pass


def main() -> int:
    _setup_console()
    _log("[dev] 热重载已开启，监视 slackoff/*.py 与 main.py")
    process = start_app()
    started_at = time.monotonic()
    baseline = snapshot()

    try:
        while True:
            time.sleep(0.6)
            code = process.poll()
            if code is not None:
                if time.monotonic() - started_at < 2.0 and code == 0:
                    _log("[dev] 应用启动后立即退出：可能已有实例在运行，请先从托盘退出再试")
                else:
                    _log(f"[dev] 应用已退出（code={code}），停止热重载")
                return int(code or 0)

            current = snapshot()
            if current == baseline:
                continue

            changed = [Path(key).name for key in current if current.get(key) != baseline.get(key)]
            _log("[dev] 检测到修改：" + "、".join(changed[:5]) + "，重启中…")
            time.sleep(0.25)  # 等编辑器写完
            stop_app(process)
            time.sleep(0.6)   # 等旧实例彻底释放单实例锁
            process = start_app()
            started_at = time.monotonic()
            baseline = snapshot()
    except KeyboardInterrupt:
        _log("[dev] 收到 Ctrl+C，关闭应用")
        stop_app(process)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
