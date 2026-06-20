# Engineering-Log

Notizen vom Bauen dieses Dings. Bewusst ehrlich gehalten, inklusive der Stellen,
an denen ich mich im Kreis gedreht habe. Wenn du nur eine Datei im Repo liest,
lies diese, denn in den Sackgassen ist das eigentliche Lernen passiert.

> Das ist ein Security-Research-/Lernprojekt. Es löst jeweils einen Link auf,
> damit du sehen kannst, wohin ein Verkürzer zeigt, bevor du draufklickst. Kein
> Scraper. Unten steht eine Notiz zur [verantwortungsvollen Nutzung](#verantwortungsvolle-nutzung).

## Warum ich angefangen habe

Ich hatte einen Link hinter einem `ay.link/...`-Verkürzer. Du klickst drauf und
bekommst ein paar Werbe-Redirects, eine Cloudflare-Seite, eine Wand aus Trackern
und schließlich, wohin es auch ging. Manchmal ist dieses Ziel zwielichtig. Ich
wollte wissen, wohin ein Link tatsächlich zeigt, bevor ich draufklicke, und schon
die Gate-Seite selbst pingt Werbenetzwerke an und versucht, dich dazu zu bringen,
Benachrichtigungen zu erlauben.

Also: Komme ich automatisch an das echte Ziel, ohne Werbung anzuklicken und ohne
selbst dazusitzen und den Browser zu steuern? Kurze Antwort: ja. Lange Antwort ist
der Rest dieser Datei.

## Was das Gate eigentlich macht

Das Erste, was ich gemacht habe, war DevTools öffnen und den Network-Tab
beobachten. So sieht es aus:

```
GET /linkk2
  HTML loads
  Cloudflare Turnstile challenge (in an iframe)
  a countdown starts, 5-10s
  countdown ends, the "Go to link" button turns on
  you click it
  behind the scenes: POST /get/tk?token=<turnstile-token>
  server replies with JSON: { "url": "https://real-destination.com" }
  destination opens in a new tab
```

Im DOM gibt es eine fiese Stelle:

```html
<main onclick="mainClick()" id="main" data-ppcnt_ads="https://ppcnt.eu/go.php?...">
  <a id="go-link">Go to link</a>
</main>
```

Wenn du irgendwo auf `#main` klickst, läuft `mainClick()` und öffnet das
Werbenetzwerk. Der echte Button ist `#go-link`, und der startet tot. `link.js`
fügt die Klassen `.go-link` / `.btn-go` erst nach dem Countdown hinzu. Klick davor,
und nichts passiert. Es hat eine Weile gedauert, bis mir aufgefallen ist, dass die
beiden komplett getrennte Code-Pfade sind und das Klicken des falschen einfach die
Werbung füttert.

## Sachen, die ich versucht habe und die nicht funktioniert haben

**requests + BeautifulSoup.** Meine erste Vermutung war, dass die URL irgendwo im
HTML steckt. Tut sie nicht. Sie ist serverseitig verschlüsselt und kommt erst von
`/get/tk` zurück, sobald du ein gültiges Turnstile-Token hast. Kein Browser, keine
URL. Weiter.

**Schlichtes Playwright.** Cloudflare sagte praktisch sofort "verification
failed". Turnstile schaut sich `navigator.webdriver` an, ob es während der
Challenge eine laufende CDP-(DevTools-)Verbindung gibt, Lücken im
Headless-Fingerprint, wie regelmäßig deine Mausbewegung ist, Canvas-/WebGL-Kram.
Stock-Playwright fällt bei all dem durch.

**playwright-stealth.** Patcht `navigator.webdriver` und ein paar andere Tells.
Scheiterte trotzdem an Turnstile. Die Bibliothek nutzt ältere Tricks, und
Turnstile macht etwas viel Schwereres.

**patchright.** Das hier patcht das Chromium-Binary selbst, entfernt
Automatisierungs-Flags. Es schlägt einfachere Bot-Checks, aber nicht Turnstile,
denn Turnstiles eigentlicher Move ist das Erkennen der laufenden CDP-Verbindung,
und ein Binary-Patch fasst das nicht an. Ich habe es trotzdem nicht weggeworfen,
es ist immer noch die "fast"-Engine für Gates, die kein Cloudflare davor haben.

An diesem Punkt habe ich mir einen Haufen GitHub-Repos und Forenthreads zu
Cloudflare durchgelesen. Die Hälfte davon ist KI-generiert und funktioniert gar
nicht, manche sind einfach alt. Ich habe alles als Zeug behandelt, das zu
verifizieren ist, nicht als heilige Wahrheit. Zwei Dinge sind dabei
herausgekommen: SeleniumBase UC Mode (Open Source, bewältigt Turnstile
tatsächlich) und kostenpflichtige Captcha-Dienste (nein danke, das sollte nichts
kosten).

## SeleniumBase UC Mode, und das Bildschirm-Problem

UC Mode macht das, was sonst nichts gemacht hat. Während der Challenge trennt es
CDP, sodass der Browser sauber aussieht, und verbindet sich dann wieder. Es klickt
die Checkbox mit PyAutoGUI von außerhalb von chromedriver.

```python
with SB(uc=True, headless=False) as sb:
    sb.uc_open_with_reconnect(url, reconnect_time=4)
    sb.uc_gui_click_captcha()
```

Turnstile: bestanden. Aber der Browser öffnete sich auf meinem echten Bildschirm,
in voller Größe, vor allem anderen, sodass ich nicht einmal tippen konnte.
Außerdem trifft `uc_gui_click_captcha()` unter Linux nicht immer die Checkbox, die
Koordinaten driften, also habe ich einen Fallback hinzugefügt, der die andere
Methode versucht:

```python
for attempt in ("uc_gui_click_captcha", "uc_gui_handle_captcha"):
    try:
        getattr(sb, attempt)()
        break
    except Exception:
        pass
```

Das Bildschirm-Ding war der eigentliche Ärger.

## xvfb

UC Mode kann nicht wirklich headless laufen (wird erkannt), es muss headed laufen,
und headed greift das echte Display. Die Lösung ist ein Fake-Display. `xvfb` baut
einen X11-Bildschirm ohne Monitor dahinter, der Browser rendert dort hinein,
nichts taucht auf meinem echten Desktop auf.

```bash
sudo apt install -y xvfb
```

SeleniumBase nimmt es direkt:

```python
SB(uc=True, headless=False, xvfb=True)
```

Ich habe es als `xvfb=not opts.show` eingerichtet, sodass versteckt der Standard
ist und ich `--show` übergeben kann, wenn ich zuschauen will. Danach hat es
aufgehört, meinen Desktop zu kapern, was der ganze Grund ist, warum das benutzbar
war, während ich gearbeitet habe.

## Proxy, WebRTC, Sandbox

Cloudflare blockiert eine Menge IP-Bereiche rundheraus. Datacenter-IPs besonders,
weil von dort der Bot-Traffic kommt. Das Routing über einen Residential-Proxy hat
die "verification failed"-Antworten deutlich reduziert.

Credentials: Ich packe den Proxy-User/-Pass nicht in den Code oder in git. Das
landet in einer `.env`, die gitignored ist, wird mit `os.environ.get` gelesen, und
ich logge immer nur den Host, nie die Credentials.

```
# .env (gitignored)
PROXY_URL="http://USER:PASS@HOST:PORT"
```

WebRTC war eine eigene Falle. Selbst mit einem Proxy kann WebRTC-UDP drum herum
gehen und deine echte IP leaken. Ein Chrome-Flag legt das lahm:

```
--force-webrtc-ip-handling-policy=disable_non_proxied_udp
```

Es gab außerdem eine Sandbox-Warnung. patchright fügt standardmäßig `--no-sandbox`
hinzu, und der System-Browser lehnt das ab. Die Lösung ist nicht, die Sandbox zu
deaktivieren, sondern sie wieder anzuschalten:

```python
p.chromium.launch_persistent_context(chromium_sandbox=True, ...)
```

Eine Sache, die mich fast erwischt hätte: Wenn du SeleniumBase einen
authentifizierten Proxy gibst, generiert es eine kleine Browser-Extension mit dem
Proxy-Benutzernamen und -Passwort im Klartext auf der Platte
(`downloaded_files/proxy_ext_dir/`). Dieses ganze Verzeichnis ist jetzt
gitignored, damit es nicht auf diesem Weg leaken kann.

## Der window.open-Umweg (wo ich am meisten Zeit verschwendet habe)

Der erste Lauf, der funktioniert hat, hat das Ziel von einem neuen Tab gegriffen.
Dann wurde ich clever und habe versucht, das Ganze zu "härten", indem ich
`window.open` abfange, damit die Werbe-Popups nicht aufgehen können:

```javascript
window.open = function(u) {
  if (u) window.__captured.push(String(u));
  return null;   // kill the window
};
```

Das hat alles schlimmer gemacht. Das Zurückgeben von `null` hat das eigene
`window.open` des Gates getötet, sein JS ist in einen Fehlerpfad gelaufen und hat
stattdessen den Werbe-Fallback (`popcent.org`) geöffnet. Also habe ich den
Werbeserver "erfasst". Zwei Bugs gestapelt: Das Override hat den Ablauf kaputt
gemacht, und `popcent` war nicht mal auf meiner Ignore-Liste.

Also habe ich den Hook nicht-destruktiv gemacht, das Original aufrufen und einfach
das Argument aufzeichnen. Jetzt hat er `aylink.co` erfasst, was das Gate selbst
ist. Stellt sich heraus, `ay.live` ist ein kurzer Alias, der auf `aylink.co`
weiterleitet, dieselbe Familie. Also habe ich dynamisches Lernen der Gate-Familie
hinzugefügt: Alles, wo der Haupt-Tab landet, zählt als Gate, und das echte Ziel
ist, was übrig bleibt.

Dann wurde der Button geklickt und... nichts. `window.open` ist nie gefeuert, kein
neuer Tab, der Haupt-Tab saß einfach auf `aylink.co`. An diesem Punkt habe ich
ganz offensichtlich nur dran herumgestochert und gehofft, und das hat mich nirgends
hingebracht.

## Aufhören zu raten und den Code lesen

Ich habe das Stochern-und-Zuschauen aufgegeben und `inspect_gate.py` geschrieben.
Es öffnet die Seite mit UC Mode, passiert Turnstile und dumpt dann das
vollständige DOM, alle 16 Skripte (inline und die mit `src`, mit der eigenen
Session der Seite abgerufen) und die Button-/Token-/Form-Struktur in `probe.json`.

`probe.json` hatte das gute Zeug:

- `#go-link` hat ein `data-token` (sieht aus wie ein JWT, das Besucher-Token)
- ein verstecktes Formular mit `_method=POST`, `alias=dzpal2`, `csrf=<hash>`
- globale Funktionen namens `getReqToken`, `saveToken`, `setTokenSentToServer`

Die eigentliche Logik steckte in `go-lnk.min.js`. Hier ist, was passiert, wenn
`.btn-go` geklickt wird:

```javascript
$(document).on("click", ".btn-go", function(e){
  const $form = $("#go-link");
  if($form.hasClass("go-link")){            // countdown has to be done
    $form.removeClass("go-link");           // first click strips the class
    $.ajax({
      type: "POST", async: false,
      url: "/get/tk",                        // request 1: token check
      data: {_a: _a, _t: _t, _d: _d},
      success: function(res){
        if(res.status){
          $.ajax({
            type: "POST", async: false,
            url: $form.attr("action"),        // request 2: the real URL
            data: $form.serialize() + "&tkn=" + res.th +
                  "&visitor_token=" + $btn.data("token") +
                  "&signal=" + JSON.stringify(window.__visitorSignal()),
            success: function(response){
              if(response.url){
                // it does NOT open the URL. it writes it into #main's onclick:
                $("#main").attr("onclick",
                  'window.open("' + response.url + '","_blank");');
                $(".skip-ad a").attr("href", $("#main").data("ppcnt_ads"));
              }
            }
          });
        }
      }
    });
    return false;
  }
});
```

Und da ist die Antwort auf "Warum muss ich zweimal klicken". Der erste Klick auf
`.btn-go` lässt die zwei AJAX-Aufrufe laufen und stopft die echte URL in das
`onclick` von `#main` als `window.open("REAL_URL","_blank")`. Der zweite Klick, auf
`#main`, ist das, was das tatsächlich feuert und den Tab öffnet.

Das ist auch genau der Grund, warum mein `window.open`-Override zum Scheitern
verurteilt war. Die URL ist an der Stelle, die mich interessiert hat, kein Argument
von `window.open`, sie ist ein String, der in einem DOM-Attribut sitzt.
`window.open` wird erst beim zweiten Klick aufgerufen, und die URL ist davor schon
hingeschrieben.

## Der Fix, der tatsächlich funktioniert

Kein zweiter Klick nötig. Den Button einmal klicken, dann einfach das `onclick`
von `#main` lesen und die URL herausziehen:

```python
onclick = driver.execute_script(
    "var m=document.querySelector('#main'); return m?m.getAttribute('onclick'):null;")
m = re.search(r'window\.open\(\s*[\'"]([^\'"]+)[\'"]', onclick)
real_url = m.group(1)
```

Kein Popup, kein zweiter Klick, kein window.open-Hook, kein Timing-Race. Und ich
prüfe die Bereitschaft jetzt richtig: Der Button ist bereit, wenn `#go-link` die
Klasse `go-link` hat, nicht durch Raten an der Element-Sichtbarkeit wie vorher.

## Noch ein Hop: bildirim.online

Die URL, die ich von `#main` gelesen habe, kam beim ersten Mal als
`bildirim.online/ph/...` raus. Das ist nicht der Inhalt, das ist ein
Zwischenstopp (eine Werbe-Seite für Benachrichtigungsberechtigungen). Ein echter
Nutzer landet beim zweiten Klick dort und wird dann auf die echte Seite
weitergeleitet. Also folge ich der Redirect-Kette, bis sie sich nicht mehr bewegt:

```python
driver.get(captured_url)
last = captured_url
for _ in range(8):
    time.sleep(1.5)
    if driver.current_url == last:
        break
    last = driver.current_url
# -> https://dizipal1029.com/
```

Voller Lauf, von Anfang bis Ende:

```
[*] Opening (UC Mode): https://ay.live/dzpal2
[*] Captcha attempt: uc_gui_click_captcha()
[*] Waiting for countdown + button...
[*] "Go to link" clicked: .complete .btn-go
[+] Target (#main onclick): https://bildirim.online/ph/cmFZRzdz...
[*] Final stop: https://dizipal1029.com/
https://dizipal1029.com/
```

Die Lektion, mit der ich tatsächlich rausgegangen bin: "Fass das JS des Gates
nicht an" war nicht die echte Regel. Die echte Regel war, zu lesen, was die Seite
macht, die Ausgabe von der Stelle zu greifen, an der sie tatsächlich liegt (einem
DOM-Attribut, nicht einem Funktionsaufruf), und den Hops bis zum Ende zu folgen.
Ich hätte Stunden gespart, wenn ich `go-lnk.min.js` am ersten Tag gelesen hätte,
statt an Buttons herumzustochern.

## Sachen, die man sich merken sollte

Bot-Erkennung ist kein Spaß. Turnstile prüft `navigator.webdriver`, die laufende
CDP-Verbindung, Mausmuster, Headless-API-Lücken, Canvas/WebGL. UC Mode ist das
Einzige, das durchgekommen ist, und es macht das, indem es CDP während der
Challenge tatsächlich kappt. Flags zu patchen oder Funktionen zu monkeypatchen
reicht nicht.

Das System zu lesen schlägt es zu sondieren. Ich habe den Großteil meiner Zeit
mit Klicken und Zuschauen verloren. In dem Moment, in dem ich das JS gedumpt und
gelesen habe, war die Antwort direkt da.

DOM-Globals wie `window.open` zu überschreiben ist eine Falle. Die Seite rechnet
nicht damit, die Fehlerpfade gehen woanders hin, und Cloudflare kann es bemerken.
Schau dir die Ausgabe an, schreib den Ablauf nicht um.

Headed-Browser plus virtuelles Display ist die saubere Antwort auf "headless wird
erkannt, aber ich will es nicht auf meinem Bildschirm". Ein Parameter statt eines
Haufens Headless-Workarounds.

Secrets per Konstruktion draußen halten. `.env`, das Proxy-Extension-Verzeichnis
gitignoren, nur den Host loggen. Es ist leicht, den Proxy über diese
automatisch generierte Extension zu leaken, wenn man nicht aufpasst.

## Wie es aufgebaut ist

```
linkgate/
  __init__.py                 version
  cli.py                      argparse, .env loading, engine pick, batch mode
  extract.py                  pure helpers, no browser, unit-tested
    is_real_target()          real destination, or gate/ad/tracker?
    find_url_in_json()        dig a URL out of a JSON response
    parse_proxy()             proxy string -> dict
  vt.py                       VirusTotal reputation check (free API)
  engines/
    base.py                   Engine interface, ResolveOptions
    seleniumbase_engine.py    primary, clears Turnstile, reads #main onclick
    playwright_engine.py      secondary, fast, network capture, no Cloudflare
scripts/
  bypass.py                   thin CLI wrapper
  inspect_gate.py             the reverse-engineering tool that cracked it open
```

Zwei Engines, weil sie in verschiedenen Dingen gut sind:

| | stealth (SeleniumBase) | fast (patchright) |
|---|---|---|
| Turnstile | löst es | kann nicht |
| Geschwindigkeit | langsamer (~30s) | schneller (~5s) |
| Captcha | UC Mode + PyAutoGUI | nur Binary-Patch |
| Capture | liest #main onclick, folgt Redirects | JSON-Response-Hook |
| Einsatz wenn | Cloudflare-Gates | Gates ohne Cloudflare |

## Wie es tatsächlich gelaufen ist, der Reihe nach

1. requests + BeautifulSoup, URL nicht im HTML, Sackgasse
2. Playwright, Turnstile gescheitert
3. playwright-stealth, weiterhin gescheitert
4. patchright, weiterhin gescheitert, als fast-Engine behalten
5. SeleniumBase UC Mode gefunden
6. UC Mode headed, hat funktioniert, aber den Bildschirm übernommen
7. xvfb, Bildschirm-Problem weg
8. Residential-Proxy, weniger Cloudflare-Blockaden
9. WebRTC-Flag hinzugefügt
10. Sandbox-Warnung mit chromium_sandbox=True gefixt
11. erster Erfolg von einem neuen Tab, das Ziel bekommen
12. window.open-Override, stattdessen den Werbeserver erfasst, ups
13. nicht-destruktiver Hook, das Gate selbst erfasst (aylink.co)
14. dynamisches Lernen der Gate-Familie, Button geklickt, aber nichts kam zurück
15. mit dem Raten aufgehört, inspect_gate.py geschrieben, DOM + 16 Skripte gedumpt
16. go-lnk.min.js gelesen, den echten Mechanismus gefunden (URL geht ins #main onclick)
17. das onclick gelesen, den bildirim.online-Hop bekommen
18. den Redirects gefolgt, auf dem echten Ziel gelandet, deterministisch
19. dieses Log aus dem neu geschrieben, was tatsächlich passiert ist

## Verantwortungsvolle Nutzung

Das hier ist da, um zu verstehen, wie Ad-Gate-Verkürzer funktionieren, und um zu
prüfen, wohin ein Link geht, bevor man ihm vertraut.

- jeweils ein Link, zur Inspektion, nicht zum massenhaften Abgreifen
- nicht, um Werbenetzwerke zu betrügen oder Impressions zu fälschen
- nicht, um an Inhalte zu kommen, die du nicht haben darfst
- halte dich an die Bedingungen der beteiligten Dienste und an das Recht an deinem
  Ort
