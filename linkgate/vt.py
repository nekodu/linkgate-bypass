"""VirusTotal ile çıkarılan hedef URL'nin itibar kontrolü.

Ücretsiz VirusTotal API anahtarı yeterli. Anahtar VT_API_KEY env / .env'den okunur.
Anahtar yoksa kontrol atlanır (araç yine çalışır).
"""
from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

VT_API = "https://www.virustotal.com/api/v3/urls"


@dataclass
class VTResult:
    harmless: int = 0
    malicious: int = 0
    suspicious: int = 0
    undetected: int = 0
    checked: bool = False
    error: str | None = None

    @property
    def is_safe(self) -> bool:
        return self.checked and self.malicious == 0 and self.suspicious == 0

    def summary(self) -> str:
        if not self.checked:
            return f"VirusTotal: kontrol edilmedi ({self.error or 'anahtar yok'})"
        verdict = "GÜVENLİ" if self.is_safe else "RİSKLİ"
        return (f"VirusTotal: {verdict} — zararlı={self.malicious} "
                f"şüpheli={self.suspicious} zararsız={self.harmless}")


def _url_id(url: str) -> str:
    """VT v3 URL kimliği: base64url (padding'siz)."""
    return base64.urlsafe_b64encode(url.encode()).decode().strip("=")


def check_url(url: str, api_key: str | None = None, timeout: int = 30) -> VTResult:
    """URL'yi VirusTotal'da sorgula. Önce var olan raporu çeker; yoksa hata döner.

    Not: Yeni bir tarama tetiklemek yerine var olan raporu okur (tek istek, hızlı).
    """
    api_key = api_key or os.environ.get("VT_API_KEY")
    if not api_key:
        return VTResult(error="VT_API_KEY tanımlı değil")

    req = urllib.request.Request(
        f"{VT_API}/{_url_id(url)}",
        headers={"x-apikey": api_key, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return VTResult(error="VT'de kayıt yok (henüz taranmamış)")
        return VTResult(error=f"VT HTTP {e.code}")
    except Exception as e:  # ağ/zaman aşımı
        return VTResult(error=str(e)[:120])

    stats = (data.get("data", {})
                 .get("attributes", {})
                 .get("last_analysis_stats", {}))
    return VTResult(
        harmless=stats.get("harmless", 0),
        malicious=stats.get("malicious", 0),
        suspicious=stats.get("suspicious", 0),
        undetected=stats.get("undetected", 0),
        checked=True,
    )
