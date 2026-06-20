"""Çözücü motorlar. Her motor bir gate URL'sini alır, gerçek hedefi döndürür."""
from .base import Engine, ResolveOptions

__all__ = ["Engine", "ResolveOptions", "get_engine"]


def get_engine(name: str) -> Engine:
    """İsimle motor seç: 'stealth' (SeleniumBase UC) ya da 'fast' (patchright)."""
    name = (name or "stealth").lower()
    if name in ("stealth", "seleniumbase", "sb", "uc"):
        from .seleniumbase_engine import SeleniumBaseEngine
        return SeleniumBaseEngine()
    if name in ("fast", "playwright", "patchright"):
        from .playwright_engine import PlaywrightEngine
        return PlaywrightEngine()
    raise ValueError(f"Bilinmeyen motor: {name}")
