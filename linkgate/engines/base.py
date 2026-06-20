"""Motor arayüzü ve ortak ayarlar."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

# Gate sayfası yüklendikten SONRA ana çerçeveye uygulanır (Turnstile iframe'ine DEĞİL).
# ÖNEMLİ: window.open'ı YUTMAYIZ — orijinali çağırırız. Sadece URL'i kaydederiz.
# (Önceki hata: null döndürmek gate JS'ini bozuyordu -> popcent fallback'e düşüyordu.)
# Ayrıca aynı sekmede yönlendirme olursa diye location atamasını da kaydederiz.
MAIN_FRAME_JS = """
(() => {
  if (window.__lgbPatched) return 'already';
  window.__lgbPatched = true;
  window.__captured = window.__captured || [];
  var _open = window.open;
  window.open = function(u) {
    if (u) window.__captured.push(String(u));
    return _open.apply(window, arguments);   // orijinali çağır -> gate bozulmaz
  };
  return 'patched';
})();
"""

# Gerçek "Linke Git" butonuna tıkla — #main'e DEĞİL.
# Gate yapısı: <main onclick="mainClick()" id="main"> reklamı tetikler (popcent.org);
# asıl buton #go-link'tir, geri sayım bitince link.js ona .go-link/.btn-go ekler.
# Bu yüzden SADECE gerçek butonu hedefleriz, reklam alanına asla dokunmayız.
CLICK_GO_JS = """
(() => {
  const sel = '#go-link.go-link, .complete .btn-go, a.go-link, #go-link';
  const btn = document.querySelector(sel);
  if (!btn) return 'not-ready';
  // Geri sayım hâlâ görünüyorsa buton henüz hazır değildir.
  const cd = document.querySelector('.countdown .time');
  if (cd && cd.offsetParent !== null) return 'counting';
  btn.click();
  return 'clicked';
})();
"""


@dataclass
class ResolveOptions:
    url: str
    headless: bool = False        # fast (patchright) motoru için gerçek headless
    show: bool = False            # stealth motoru: True ise gerçek ekran, False ise xvfb
    timeout: int = 120
    proxy: dict | None = None
    profile_dir: Path | None = None
    executable_path: str | None = None
    verbose: bool = True


class Engine(ABC):
    """Bir gate URL'sini çözüp gerçek hedef URL'yi döndüren motor."""

    name: str = "base"

    @abstractmethod
    def resolve(self, opts: ResolveOptions) -> str | None:
        """Gerçek hedef URL'yi döndür ya da bulunamazsa None."""
        raise NotImplementedError
