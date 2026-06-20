"""Komut satırı arayüzü: tekil/batch çözme, JSON çıktı, VirusTotal kontrolü."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__
from .engines import ResolveOptions, get_engine
from .extract import parse_proxy
from .vt import check_url

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROFILE = ROOT / ".profile"
DOTENV = ROOT / ".env"

BROWSER_CANDIDATES = [
    "/usr/bin/brave-browser", "/usr/bin/brave-browser-stable",
    "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium", "/snap/bin/chromium", "/usr/bin/chromium-browser",
]


def load_dotenv() -> None:
    if not DOTENV.exists():
        return
    for line in DOTENV.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def find_browser() -> str | None:
    return next((c for c in BROWSER_CANDIDATES if Path(c).exists()), None)


def read_urls(args) -> list[str]:
    urls: list[str] = list(args.url)
    if args.batch:
        text = sys.stdin.read() if args.batch == "-" else Path(args.batch).read_text()
        urls += [ln.strip() for ln in text.splitlines() if ln.strip()
                 and not ln.startswith("#")]
    return urls


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="linkgate-bypass",
        description="Ad-gate link kısaltıcıların gerçek hedefini güvenle çıkarır.",
    )
    ap.add_argument("url", nargs="*", help="Bir veya daha fazla gate linki")
    ap.add_argument("--batch", metavar="DOSYA",
                    help="Satır başına bir URL içeren dosya ('-' = stdin)")
    ap.add_argument("--engine", default="stealth",
                    choices=["stealth", "fast"],
                    help="stealth=SeleniumBase UC (Cloudflare), fast=patchright")
    ap.add_argument("--timeout", type=int, default=120,
                    help="Hedef için maksimum bekleme (saniye)")
    ap.add_argument("--proxy", default=os.environ.get("PROXY_URL"),
                    help="http://user:pass@host:port (varsayılan: .env PROXY_URL)")
    ap.add_argument("--no-proxy", action="store_true", help="Proxy'yi kapat")
    ap.add_argument("--profile", default=str(DEFAULT_PROFILE),
                    help="Kalıcı tarayıcı profili (doğrulama hatırlanır)")
    ap.add_argument("--browser-path", default=None,
                    help="Tarayıcı binary'si (varsayılan: Brave/Chrome otomatik)")
    ap.add_argument("--bundled", action="store_true",
                    help="Sistem tarayıcısı yerine patchright chromium'u (fast motor)")
    ap.add_argument("--headless", action="store_true",
                    help="fast motoru için gerçek headless")
    ap.add_argument("--show", action="store_true",
                    help="stealth motoru gerçek ekranda izlensin (varsayılan: gizli xvfb)")
    ap.add_argument("--check", action="store_true",
                    help="Çıkarılan URL'yi VirusTotal'da tara (VT_API_KEY gerekir)")
    ap.add_argument("--json", action="store_true", help="Sonuçları JSON olarak bas")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return ap


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = build_parser().parse_args(argv)
    urls = read_urls(args)
    if not urls:
        print("[!] En az bir URL ver (argüman ya da --batch).", file=sys.stderr)
        return 2

    proxy = None if args.no_proxy else parse_proxy(args.proxy)
    exe = None if args.bundled else (args.browser_path or find_browser())
    engine = get_engine(args.engine)

    if proxy and not args.json:
        print(f"[*] Proxy: {proxy['server']}", file=sys.stderr)
    if exe and not args.json:
        print(f"[*] Tarayıcı: {exe}  | Motor: {engine.name}", file=sys.stderr)

    results = []
    for u in urls:
        opts = ResolveOptions(
            url=u, headless=args.headless, show=args.show, timeout=args.timeout,
            proxy=proxy, profile_dir=Path(args.profile), executable_path=exe,
            verbose=not args.json,
        )
        target = engine.resolve(opts)
        entry = {"source": u, "target": target}
        if target and args.check:
            vt = check_url(target)
            entry["virustotal"] = {
                "checked": vt.checked, "safe": vt.is_safe,
                "malicious": vt.malicious, "suspicious": vt.suspicious,
                "harmless": vt.harmless, "error": vt.error,
            }
            if not args.json:
                print(f"[*] {vt.summary()}", file=sys.stderr)
        results.append(entry)

        if not args.json:
            print(target if target else f"[!] Çözülemedi: {u}",
                  file=sys.stdout if target else sys.stderr)

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))

    return 0 if all(r["target"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
