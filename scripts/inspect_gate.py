"""Gate sayfasının GERÇEK mekanizmasını tersine mühendislikle çıkar.

Tahmin etmeyi bırak: sayfayı UC Mode ile aç (Turnstile geç), sonra
- tüm DOM HTML'ini
- tüm <script> içeriklerini (inline + src)
- token / data-* attribute'larını
- buton ve form yapısını
dök. Çıktıyı okuyup /get/tk gibi gerçek endpoint'i ve token akışını bul.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from linkgate.cli import find_browser, load_dotenv  # noqa: E402
from linkgate.engines.seleniumbase_engine import _proxy_to_sb  # noqa: E402
from linkgate.extract import parse_proxy  # noqa: E402

import os  # noqa: E402

OUT = ROOT / "docs" / "gate-dump"


def main() -> int:
    load_dotenv()
    url = sys.argv[1] if len(sys.argv) > 1 else "https://ay.live/dzpal2"
    OUT.mkdir(parents=True, exist_ok=True)

    from seleniumbase import SB

    proxy = parse_proxy(os.environ.get("PROXY_URL"))
    kwargs = dict(uc=True, headless=False, xvfb=True, locale_code="tr")
    if proxy and (sp := _proxy_to_sb(proxy)):
        kwargs["proxy"] = sp
    if (exe := find_browser()):
        kwargs["binary_location"] = exe

    with SB(**kwargs) as sb:
        print(f"[*] Açılıyor: {url}", file=sys.stderr)
        sb.uc_open_with_reconnect(url, reconnect_time=4)
        for attempt in ("uc_gui_click_captcha", "uc_gui_handle_captcha"):
            try:
                getattr(sb, attempt)()
                print(f"[*] Captcha: {attempt}", file=sys.stderr)
                break
            except Exception as e:
                print(f"[-] {attempt}: {str(e)[:60]}", file=sys.stderr)

        import time
        time.sleep(8)  # geri sayım + JS yerleşsin

        final_url = sb.driver.current_url
        print(f"[*] Final url: {final_url}", file=sys.stderr)

        # 1) Tam DOM
        html = sb.driver.page_source
        (OUT / "dom.html").write_text(html, encoding="utf-8")
        print(f"[+] dom.html ({len(html)} bytes)", file=sys.stderr)

        # 2) Tüm script kaynakları (src) ve inline içerik
        scripts = sb.execute_script("""
            return Array.from(document.scripts).map(s => ({
                src: s.src || null,
                inline: s.src ? null : s.textContent
            }));
        """)
        manifest = []
        for i, s in enumerate(scripts or []):
            if s.get("src"):
                manifest.append(f"SRC: {s['src']}")
                # Sayfanın kendi origin'inden fetch et (cookie/oturum dahil)
                try:
                    content = sb.execute_script(
                        "var r=arguments[0];"
                        "var x=new XMLHttpRequest();"
                        "x.open('GET', r, false); x.send(); return x.responseText;",
                        s["src"],
                    )
                    if content:
                        (OUT / f"script_{i}.js").write_text(content, encoding="utf-8")
                        manifest.append(f"  -> script_{i}.js ({len(content)} bytes)")
                except Exception as e:
                    manifest.append(f"  -> fetch hata: {str(e)[:60]}")
            elif s.get("inline"):
                (OUT / f"inline_{i}.js").write_text(s["inline"], encoding="utf-8")
                manifest.append(f"INLINE: inline_{i}.js ({len(s['inline'])} bytes)")
        (OUT / "scripts_manifest.txt").write_text("\n".join(manifest), encoding="utf-8")
        print(f"[+] {len(scripts or [])} script dökümlendi", file=sys.stderr)

        # 3) Buton / token / data-* keşfi
        probe = sb.execute_script(r"""
            const out = {};
            const go = document.querySelector('#go-link, .btn-go, a.go-link');
            out.go_link = go ? {
                id: go.id, cls: go.className, href: go.href || null,
                onclick: go.getAttribute('onclick'),
                dataset: Object.assign({}, go.dataset), text: go.textContent.trim()
            } : null;
            const main = document.querySelector('#main');
            out.main = main ? {
                onclick: main.getAttribute('onclick'),
                dataset: Object.assign({}, main.dataset)
            } : null;
            // Sayfadaki olası token/anahtar global değişkenleri
            out.globals = Object.keys(window).filter(k =>
                /token|tk|key|link|ad|gate|secret|hash/i.test(k)).slice(0, 50);
            // Tüm input/hidden alanları
            out.inputs = Array.from(document.querySelectorAll('input')).map(i => ({
                name: i.name, type: i.type, value: i.value
            }));
            // Sayfa HTML'inde /get/ veya token geçen yerler
            out.html_hints = (document.documentElement.outerHTML.match(
                /['"][^'"]*(get\/tk|\/get\/|token|csrf)[^'"]*['"]/gi) || []).slice(0, 30);
            return out;
        """)
        import json
        (OUT / "probe.json").write_text(
            json.dumps(probe, ensure_ascii=False, indent=2), encoding="utf-8")
        print("[+] probe.json yazıldı", file=sys.stderr)
        print(json.dumps(probe, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
