"""TXT 电子书：加入「我的书」、读取内容（自动识别编码）。

支持 UTF-8（含 BOM）、UTF-16、GB18030/GBK、Big5；太大的文件只读前面一段，避免卡死界面。
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

SUPPORTED_SUFFIXES = (".txt",)
MAX_BYTES = 8 * 1024 * 1024


@dataclass
class PinnedBook:
    id: str
    name: str
    path: str

    @property
    def file(self) -> Path:
        return Path(self.path)

    @property
    def exists(self) -> bool:
        return self.file.is_file()

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "path": self.path}


@dataclass
class BookContent:
    text: str
    encoding: str
    truncated: bool


def _key(path: str | Path) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def _make_id(path: str) -> str:
    digest = hashlib.md5(_key(path).encode("utf-8")).hexdigest()[:8]
    return f"book-{digest}"


def load_books(settings) -> list[PinnedBook]:
    result: list[PinnedBook] = []
    for entry in settings.pinned_books:
        if not isinstance(entry, dict):
            continue
        path = str(entry.get("path") or "").strip()
        if not path:
            continue
        book_id = str(entry.get("id") or "").strip()
        if not book_id:
            book_id = _make_id(path)
            entry["id"] = book_id
        name = str(entry.get("name") or "").strip() or Path(path).stem
        entry["name"] = name
        result.append(PinnedBook(id=book_id, name=name, path=path))
    return result


def find_book(settings, book_id: str) -> PinnedBook | None:
    return next((book for book in load_books(settings) if book.id == book_id), None)


def add_path(settings, raw_path: str | Path, name: str | None = None) -> tuple[PinnedBook, bool]:
    path = Path(str(raw_path)).expanduser()
    if path.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise ValueError("只支持 .txt 文本文件")
    if not path.is_file():
        raise ValueError(f"找不到文件：{path}")
    path = path.resolve()
    existing = next(
        (book for book in load_books(settings) if _key(book.path) == _key(path)),
        None,
    )
    if existing is not None:
        return existing, False
    book = PinnedBook(
        id=_make_id(str(path)),
        name=(name or "").strip() or path.stem,
        path=str(path),
    )
    settings.pinned_books.append(book.to_dict())
    return book, True


def remove(settings, book_id: str) -> bool:
    before = len(settings.pinned_books)
    settings.pinned_books = [
        entry for entry in settings.pinned_books if str(entry.get("id") or "") != book_id
    ]
    return len(settings.pinned_books) != before


def format_size(path: str | Path) -> str:
    try:
        size = Path(path).stat().st_size
    except OSError:
        return "文件不见了"
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / 1024 / 1024:.1f} MB"


def read_text(path: str | Path, max_bytes: int = MAX_BYTES) -> BookContent:
    target = Path(path)
    if not target.is_file():
        raise ValueError(f"找不到文件：{target}")
    with target.open("rb") as handle:
        raw = handle.read(max_bytes + 1)
    truncated = len(raw) > max_bytes
    data = raw[:max_bytes]
    text, encoding = _decode(data)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return BookContent(text=text, encoding=encoding, truncated=truncated)


def _decode(data: bytes) -> tuple[str, str]:
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig", errors="replace"), "UTF-8 BOM"
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace"), "UTF-16"
    for encoding in ("utf-8", "gb18030", "big5"):
        try:
            return data.decode(encoding), encoding.upper()
        except UnicodeDecodeError:
            continue
    return data.decode("gb18030", errors="replace"), "GB18030(容错)"
