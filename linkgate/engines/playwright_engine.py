"""patchright (yamalı Playwright) motoru — hızlı, ağ-cevabı yakalamalı.

Cloudflare Turnstile'ı OLMAYAN gate'ler için idealdir: sunucunun döndürdüğü
JSON cevabındaki ('url' alanı) gerçek hedefi ağdan yakalar. Turnstile varsa
'stealth' (SeleniumBase) motorunu kullan.
"""
from __future__ import annotations

import json
import sys
import time

from ..extract import base_domain, find_url_in_json, is_real_target
from .base import CLICK_GO_JS, MAIN_FRAME_JS, Engine, ResolveOptions

# Ağ güvenliği: WebRTC UDP'sini proxy dışına çıkarma (gerçek/yerel IP sızmasın).
HARDENING_ARGS = [
    "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
    "--no-default-browser-check",
    "--no-first-run",
    "--disable-background-networking",
    "--disable-sync",
]


class PlaywrightEngine(Engine):
    name = "fast"

    def resolve(self, opts: ResolveOptions) -> str | None:
        from patchright.sync_api import sync_playwright

        gate_base = base_domain(opts.url.split("//", 1)[-1].split("/", 1)[0])
        found = {"url": None}

        def log(msg: str):
            if opts.verbose:
                print(msg, file=sys.stderr)

        with sync_playwright() as p:
            kwargs = dict(
                user_data_dir=str(opts.profile_dir) if opts.profile_dir else "",
                headless=opts.headless,
                locale="tr-TR",
                no_viewport=True,
                accept_downloads=False,    # malware dosyası inmesin
                chromium_sandbox=True,     # renderer izolasyonu (malware)
                args=HARDENING_ARGS,
            )
            if opts.proxy:
                kwargs["proxy"] = opts.proxy
            if opts.executable_path:
                kwargs["executable_path"] = opts.executable_path

            context = p.chromium.launch_persistent_context(**kwargs)
            page = context.pages[0] if context.pages else context.new_page()

            def on_response(resp):
                if found["url"]:
                    return
                ctype = (resp.headers.get("content-type") or "").lower()
                if "json" not in ctype and "javascript" not in ctype:
                    return
                try:
                    data = json.loads(resp.text())
                except Exception:
                    return
                cand = find_url_in_json(data)
                if cand and is_real_target(cand, gate_base):
                    found["url"] = cand
                    log(f"[+] Hedef (ağ cevabı): {cand}")

            def on_popup(popup):
                try:
                    if not found["url"] and is_real_target(popup.url, gate_base):
                        found["url"] = popup.url
                        log(f"[+] Hedef (popup): {popup.url}")
                    if popup is not page:
                        popup.close()
                except Exception:
                    pass

            context.on("response", on_response)
            context.on("page", on_popup)

            log(f"[*] Açılıyor (fast): {opts.url}")
            try:
                page.goto(opts.url, wait_until="domcontentloaded", timeout=60_000)
            except Exception as e:
                log(f"[!] Sayfa açılamadı: {e}")
                context.close()
                return None

            patched = False
            waited, step = 0.0, 1.0
            while not found["url"] and waited < opts.timeout:
                if page.is_closed():
                    break
                try:
                    if not patched and page.query_selector("#main"):
                        page.evaluate(MAIN_FRAME_JS)
                        patched = True
                    for u in page.evaluate("() => (window.__captured || [])") or []:
                        if is_real_target(u, gate_base):
                            found["url"] = u
                            log(f"[+] Hedef (window.open): {u}")
                            break
                    # Geri sayım bittiyse SADECE gerçek #go-link butonuna bas (#main = reklam).
                    if patched and not found["url"]:
                        page.evaluate(f"({CLICK_GO_JS})()")
                except Exception:
                    pass
                time.sleep(step)
                waited += step

            try:
                context.close()
            except Exception:
                pass

        return found["url"]
