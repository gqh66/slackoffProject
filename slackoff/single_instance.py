"""单实例保护：重复启动时唤回已有窗口，而不是再开一个进程。"""

from __future__ import annotations

import hashlib
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


def instance_name(root: Path) -> str:
    digest = hashlib.md5(str(root.resolve()).lower().encode("utf-8")).hexdigest()[:12]
    return f"SlackOff-{digest}"


class SingleInstance(QObject):
    activated = Signal()

    def __init__(self, root: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.name = instance_name(root)
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._on_connection)

    def acquire(self) -> bool:
        """拿到单实例锁返回 True；已有实例时通知它并返回 False。"""
        if self._notify_existing(400):
            return False
        QLocalServer.removeServer(self.name)
        if self._server.listen(self.name):
            return True
        # 极小概率的启动竞争：对方刚好在 listen，再试一次通知
        if self._notify_existing(800):
            return False
        return True

    def _notify_existing(self, timeout_ms: int = 400) -> bool:
        socket = QLocalSocket()
        socket.connectToServer(self.name)
        if not socket.waitForConnected(timeout_ms):
            return False
        socket.write(b"show")
        socket.flush()
        socket.waitForBytesWritten(timeout_ms)
        socket.disconnectFromServer()
        return True

    def _on_connection(self) -> None:
        connection = self._server.nextPendingConnection()
        if connection is None:
            return
        connection.readyRead.connect(lambda conn=connection: self._read(conn))
        connection.disconnected.connect(connection.deleteLater)

    def _read(self, connection) -> None:
        data = bytes(connection.readAll())
        if not data or b"show" in data:
            self.activated.emit()

    def close(self) -> None:
        self._server.close()
        QLocalServer.removeServer(self.name)
