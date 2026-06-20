"""Saf yardımcılar: URL çıkarma, hedef ayıklama, proxy ayrıştırma.

Tarayıcıya bağımlılığı yok -> birim testlerle kolayca doğrulanır.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

# Gate domainleri, reklam ağları ve trackerlar. Yakalanan URL bunlardan biriyse
# gerçek hedef DEĞİLDİR.
IGNORE_HOST_PARTS: tuple[str, ...] = (
    "google.com", "gstatic.com", "googleapis.com", "recaptcha",
    "cloudflare.com", "challenges.cloudflare", "jsdelivr.net", "jquery.com",
    "yandex", "doubleclick", "googlesyndication", "googletagmanager",
    "firebase", "ppcnt", "popcent", "facebook", "fbcdn", "adservice", "adsterra",
)

URL_RE = re.compile(r"https?://[^\s\"'<>]+")

# JSON cevaplarında hedefin tutulduğu yaygın alan adları (öncelik sırasıyla).
URL_KEYS: tuple[str, ...] = ("url", "link", "destination", "real_url", "target", "go")


def base_domain(host: str) -> str:
    """ 'sub.aylink.co' -> 'aylink.co' (son iki etiket). """
    host = (host or "").lower()
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def is_real_target(url: str, gate_base_host: str) -> bool:
    """url gerçek hedef mi, yoksa gate/reklam/tracker mı?"""
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    if not host:
        return False
    if gate_base_host and (host == gate_base_host or host.endswith("." + gate_base_host)):
        return False
    return not any(part in host for part in IGNORE_HOST_PARTS)


def find_url_in_json(obj) -> str | None:
    """JSON yapısı içinde (dict/list/str) ilk URL benzeri stringi bul.

    Önce bilinen alan adlarına (URL_KEYS) bakar, sonra derinlemesine tarar.
    """
    if isinstance(obj, str):
        m = URL_RE.search(obj)
        return m.group(0) if m else None
    if isinstance(obj, dict):
        for key in URL_KEYS:
            val = obj.get(key)
            if isinstance(val, str) and (m := URL_RE.search(val)):
                return m.group(0)
        for val in obj.values():
            if (found := find_url_in_json(val)):
                return found
    if isinstance(obj, list):
        for val in obj:
            if (found := find_url_in_json(val)):
                return found
    return None


def parse_proxy(raw: str | None) -> dict | None:
    """'http://user:pass@host:port' -> Playwright proxy dict ya da None."""
    if not raw:
        return None
    u = urlparse(raw)
    if not u.hostname:
        return None
    scheme = u.scheme or "http"
    server = f"{scheme}://{u.hostname}:{u.port}" if u.port else f"{scheme}://{u.hostname}"
    proxy: dict[str, str] = {"server": server}
    if u.username:
        proxy["username"] = u.username
    if u.password:
        proxy["password"] = u.password
    return proxy
