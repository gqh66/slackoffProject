"""按进程静音其它程序（pycaw / Windows Core Audio）。

老板键要真正做到「瞬间安静」：网页声音靠 QtWebEngine 自己静音，
客户端（爱奇艺、腾讯视频、QQ 音乐……）的声音就靠这里。
pycaw 是可选依赖，缺失时自动降级，界面会提示。
"""

from __future__ import annotations

import logging
import sys

log = logging.getLogger(__name__)


class AudioMuter:
    def __init__(self) -> None:
        self.available = False
        self.reason = ""
        self._audio_utilities = None
        if sys.platform != "win32":
            self.reason = "仅支持 Windows"
            return
        try:
            import comtypes  # noqa: PLC0415

            comtypes.CoInitialize()
        except Exception:
            pass
        try:
            from pycaw.pycaw import AudioUtilities  # noqa: PLC0415

            self._audio_utilities = AudioUtilities
            self.available = True
        except Exception as exc:
            self.reason = f"未安装 pycaw（{exc}）"
            log.info("音频静音不可用：%s", exc)

    def mute_others(self, keep_pids: set[int]) -> list[tuple[object, bool]]:
        """静音除 ``keep_pids`` 之外所有有声音的进程，返回可恢复的状态列表。"""
        if not self.available:
            return []
        saved: list[tuple[object, bool]] = []
        try:
            sessions = self._audio_utilities.GetAllSessions()
        except Exception as exc:
            log.debug("枚举音频会话失败：%s", exc)
            return []
        for session in sessions:
            try:
                proc = session.Process
                if proc is None or proc.pid in keep_pids:
                    continue
                volume = session.SimpleAudioVolume
                if volume is None:
                    continue
                previous = bool(volume.GetMute())
                if not previous:
                    volume.SetMute(True, None)
                saved.append((volume, previous))
            except Exception:
                continue
        return saved

    def mute_pids(self, pids: set[int]) -> list[tuple[object, bool]]:
        """只静音指定进程（例如被嵌入的那个客户端），返回可恢复状态。"""
        if not self.available or not pids:
            return []
        saved: list[tuple[object, bool]] = []
        try:
            sessions = self._audio_utilities.GetAllSessions()
        except Exception:
            return []
        for session in sessions:
            try:
                proc = session.Process
                if proc is None or proc.pid not in pids:
                    continue
                volume = session.SimpleAudioVolume
                if volume is None:
                    continue
                previous = bool(volume.GetMute())
                if not previous:
                    volume.SetMute(True, None)
                saved.append((volume, previous))
            except Exception:
                continue
        return saved

    def restore(self, saved: list[tuple[object, bool]]) -> None:
        for volume, previous in saved or []:
            try:
                volume.SetMute(bool(previous), None)
            except Exception:
                pass
