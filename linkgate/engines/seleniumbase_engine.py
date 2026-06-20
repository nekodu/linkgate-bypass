"""SeleniumBase UC Mode motoru — Cloudflare Turnstile + adlinkfly/aylink gate.

Turnstile: UC Mode 'disconnect-reconnect' ile challenge anında CDP'yi keser,
tarayıcı temiz görünür. uc_gui_click_captcha() kutuyu PyAutoGUI ile tıklar.

Gate mekanizması (go-lnk.min.js tersine mühendislikten):
  1. Geri sayım bitince #go-link 'go-link' class'ı alır, .btn-go görünür olur.
  2. .btn-go'ya tıklanınca: POST /get/tk -> {status, th}; ardından form action'a
     ikinci POST -> {url: "GERÇEK_HEDEF"}.
  3. Gerçek URL window.open ile AÇILMAZ; #main öğesinin onclick'ine yazılır:
        #main.onclick = 'window.open("GERÇEK_HEDEF","_blank");'
     (Bu yüzden gate "iki tık" ister: 1. tık URL'i çeker, 2. tık #main'i açar.)

Çözüm: .btn-go'ya bir kez tıkla, sonra #main'in onclick'inden URL'i OKU.
İkinci tıka, popup'a, window.open'a gerek yok — tamamen deterministik.
"""
from __future__ import annotations

import re
import sys
import time
from urllib.parse import urlparse

from ..extract import base_domain, is_real_target
from .base import Engine, ResolveOptions

# #main onclick'inden gerçek URL'i çıkar: window.open("URL","_blank")
_OPEN_RE = re.compile(r"""window\.open\(\s*['"]([^'"]+)['"]""")

# #main onclick'inin güvenli okunması (öğe yoksa None döner).
_READ_MAIN_ONCLICK = (
    "var m=document.querySelector('#main');"
    "return m ? m.getAttribute('onclick') : null;"
)

# Geri sayım bitti mi: #go-link 'go-link' class'ı aldıysa buton hazırdır.
_BTN_READY = (
    "var g=document.querySelector('#go-link');"
    "return !!(g && g.classList.contains('go-link'));"
)


def _proxy_to_sb(proxy: dict | None) -> str | None:
    """Playwright proxy dict -> SeleniumBase proxy string (user:pass@host:port)."""
    if not proxy:
        return None
    server = proxy["server"].split("://", 1)[-1]
    if proxy.get("username"):
        return f"{proxy['username']}:{proxy.get('password', '')}@{server}"
    return server


class SeleniumBaseEngine(Engine):
    name = "stealth"

    def resolve(self, opts: ResolveOptions) -> str | None:
        from seleniumbase import SB

        gate_base = base_domain(opts.url.split("//", 1)[-1].split("/", 1)[0])

        def log(msg: str):
            if opts.verbose:
                print(msg, file=sys.stderr)

        sb_kwargs = dict(
            uc=True,
            headless=False,
            xvfb=not opts.show,        # varsayılan: gizli sanal ekran
            locale_code="tr",
            ad_block=True,
        )
        if opts.proxy and (sb_proxy := _proxy_to_sb(opts.proxy)):
            sb_kwargs["proxy"] = sb_proxy
        if opts.executable_path:
            sb_kwargs["binary_location"] = opts.executable_path
        if opts.profile_dir:
            sb_kwargs["user_data_dir"] = str(opts.profile_dir)

        # Gate ailesi dinamik öğrenilir (ay.live -> aylink.co aynı aile).
        gate_bases = {gate_base}

        def is_target(u: str) -> bool:
            if not u:
                return False
            if u.startswith(("javascript:", "about:", "data:")):
                return False
            cand = base_domain(urlparse(u).hostname or "")
            if not cand or cand in gate_bases:
                return False
            return is_real_target(u, "")  # sadece reklam/tracker filtresi

        found: str | None = None
        clicked = False
        last_click = -99.0

        with SB(**sb_kwargs) as sb:
            def js(script: str):
                try:
                    return sb.execute_script(script)
                except Exception:
                    return None

            log(f"[*] Açılıyor (UC Mode): {opts.url}")
            sb.uc_open_with_reconnect(opts.url, reconnect_time=4)

            # Turnstile varsa çöz (iki yöntem — Linux uyumluluk).
            for attempt in ("uc_gui_click_captcha", "uc_gui_handle_captcha"):
                try:
                    getattr(sb, attempt)()
                    log(f"[*] Captcha denendi: {attempt}()")
                    break
                except Exception as e:
                    log(f"[-] {attempt} olmadı: {str(e)[:80]}")

            log("[*] Geri sayım + buton bekleniyor...")
            waited, step = 0.0, 1.0
            while found is None and waited < opts.timeout:
                # Yönlendirmelerde domain'i gate ailesine ekle.
                try:
                    h = urlparse(sb.driver.current_url).hostname or ""
                    if h:
                        gate_bases.add(base_domain(h))
                except Exception:
                    pass

                # 1) #main onclick gerçek URL ile silahlandı mı? (asıl yöntem)
                onclick = js(_READ_MAIN_ONCLICK) or ""
                if (m := _OPEN_RE.search(onclick)) and is_target(m.group(1)):
                    found = m.group(1)
                    log(f"[+] Hedef (#main onclick): {found}")
                    break

                # 2) Buton hazırsa bir kez tıkla -> /get/tk akışını tetikler.
                #    Tek tık yeter; handler ilk tıkta go-link class'ını siler.
                #    Tık ıskalar / sayfa reload olursa (token hatası) tekrar dener.
                if not found and js(_BTN_READY) and (waited - last_click) > 4:
                    for sel in (".complete .btn-go", "#go-link.go-link", ".btn-go"):
                        try:
                            if sb.is_element_visible(sel):
                                sb.uc_click(sel)
                                clicked = True
                                last_click = waited
                                log(f"[*] 'Linke Git' tıklandı: {sel}")
                                break
                        except Exception:
                            continue

                # 3) Yedek: yeni sekme açıldıysa (bazı varyantlar) oradan yakala.
                if not found:
                    try:
                        handles = sb.driver.window_handles
                        if len(handles) > 1:
                            for handle in handles[1:]:
                                sb.driver.switch_to.window(handle)
                                u = sb.driver.current_url
                                if is_target(u):
                                    found = u
                                    log(f"[+] Hedef (yeni sekme): {u}")
                                sb.driver.close()
                            sb.driver.switch_to.window(handles[0])
                    except Exception:
                        pass

                if found is None:
                    time.sleep(step)
                    waited += step

            # Gate'in verdiği URL bir ara durak olabilir (bildirim.online gibi).
            # Asıl içeriğe gidene kadar yönlendirme zincirini takip et.
            if found:
                final = self._follow_to_final(sb, found, gate_bases, log)
                if final:
                    found = final

            # Bulunamadıysa durumu göster (debug).
            if found is None and opts.verbose:
                log(f"[debug] tıklandı={clicked} gate_aile={sorted(gate_bases)}")
                log(f"[debug] #main onclick = {js(_READ_MAIN_ONCLICK)!r}")
                log(f"[debug] go-link hazır = {js(_BTN_READY)}")
                log(f"[debug] ana url = {sb.driver.current_url}")

        return found

    @staticmethod
    def _follow_to_final(sb, url: str, gate_bases: set[str], log) -> str | None:
        """Yakalanan URL'e git, yönlendirmeler dursun, son durağı döndür.

        bildirim.online gibi ara duraklar asıl içeriğe yönlendirir. En fazla
        birkaç hop takip ederiz; URL stabilize olunca veya hop bitince döneriz.
        """
        try:
            sb.driver.switch_to.new_window("tab")
        except Exception:
            pass
        last = url
        try:
            sb.driver.get(url)
        except Exception:
            return None
        for _ in range(8):
            time.sleep(1.5)
            try:
                cur = sb.driver.current_url
            except Exception:
                break
            if cur == last:
                break          # stabilize oldu
            last = cur
        final = last
        log(f"[*] Son durak: {final}")
        return final
