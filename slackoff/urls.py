"""地址栏输入的解析：网址、域名、本地文件、还是搜索词。"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote_plus

from .catalog import SEARCH_ENGINES

_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.\-]*://", re.IGNORECASE)
_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}"
    r"(?::\d{1,5})?(?:[/?#].*)?$",
    re.IGNORECASE,
)
_IP_RE = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}(?::\d{1,5})?(?:[/?#].*)?$")
_LOCALHOST_RE = re.compile(r"^localhost(?::\d{1,5})?(?:[/?#].*)?$", re.IGNORECASE)
_HOSTISH_RE = re.compile(r"^[\w.\-]+:\d{1,5}(?:/.*)?$")


def looks_like_url(text: str) -> bool:
    value = (text or "").strip()
    if not value or " " in value:
        return False
    if _SCHEME_RE.match(value):
        return True
    if _DOMAIN_RE.match(value) or _IP_RE.match(value) or _LOCALHOST_RE.match(value):
        return True
    if _HOSTISH_RE.match(value) and "." in value:
        return True
    return False


def search_url(query: str, engine: str = "baidu") -> str:
    template = SEARCH_ENGINES.get(engine, SEARCH_ENGINES["baidu"])[1]
    return template.format(quote_plus(query.strip()))


def normalize_input(text: str, engine: str = "baidu") -> str | None:
    """把地址栏输入变成可以直接加载的 URL；空输入返回 None。"""
    value = (text or "").strip()
    if not value:
        return None
    if _SCHEME_RE.match(value):
        return value
    if value.lower().startswith(("www.", "m.")) or _DOMAIN_RE.match(value):
        return "https://" + value
    if _LOCALHOST_RE.match(value) or _IP_RE.match(value):
        return "http://" + value
    path = Path(value).expanduser()
    if path.is_file() and path.suffix.lower() in (".html", ".htm", ".mht", ".mhtml"):
        return path.resolve().as_uri()
    return search_url(value, engine)


def display_url(url: str) -> str:
    """地址栏里省略 https:// 前缀，读起来干净些。"""
    return re.sub(r"^https?://", "", url or "", flags=re.IGNORECASE)
