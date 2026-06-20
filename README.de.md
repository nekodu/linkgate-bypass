# linkgate-bypass

[![CI](https://github.com/nekodu/linkgate-bypass/actions/workflows/ci.yml/badge.svg)](https://github.com/nekodu/linkgate-bypass/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Findet das echte Ziel hinter einem "Ad-Gate"-Linkverkürzer (der
adlinkfly-/aylink-Familie) heraus, ohne Werbung anzuklicken, Tracker auszulösen
oder einen Browser deinen Bildschirm übernehmen zu lassen.

🇬🇧 [English version](README.md) · 📓 [Engineering-Log](docs/engineering-log.de.md)

> Security-Research- und Lernprojekt. Es löst jeweils einen Link auf, damit du
> sehen kannst, wohin ein Verkürzer zeigt, bevor du draufklickst. Es ist kein
> Massen-Scraping-Tool. Siehe [Verantwortungsvolle Nutzung](#verantwortungsvolle-nutzung).

---

## Warum

Diese Verkürzer zeigen das Ziel nie auf der Seite. Sie verstecken es hinter einer
Cloudflare-Turnstile-Challenge, einem Countdown und einem mehrstufigen
Token-Austausch und vergraben die URL dann in einem DOM-Attribut, das erst beim
zweiten Klick feuert. Wer das Gate von Hand besucht, leakt Daten an Werbenetzwerke
und Notification-Permission-Fallen, und das Endziel ist manchmal feindselig.

Dieses Tool löst die Challenge in einem versteckten virtuellen Display, liest das
Ziel direkt von der Stelle, an der das Gate es ablegt, folgt jedem
Zwischen-Redirect bis zum Schluss und gibt die echte URL aus. Es klickt nie den
Werbe-Button.

Die ganze Geschichte, wie ich dahin gekommen bin, inklusive jedem Ansatz, der
gescheitert ist, steht im [Engineering-Log](docs/engineering-log.de.md). Dieser
Log ist der interessanteste Teil dieses Repositories.

---

## Was hier drin ist, technisch

- An Cloudflare Turnstile vorbeikommen mit SeleniumBase UC Mode, das während der
  Challenge die DevTools-Verbindung kappt, sodass der Browser sauber aussieht
- Reverse Engineering des minifizierten JavaScripts des Gates, um den zweistufigen
  Token-Austausch zu finden und die Stelle, an der es das Ziel tatsächlich ablegt
- Secrets draußen halten: Proxy-Credentials nur in `.env`, WebRTC-Leak-Schutz,
  Sandbox bleibt an, gescrapter Seiteninhalt wird als nicht vertrauenswürdig
  behandelt
- Ein Engine-Interface mit zwei Backends, und die URL-Logik in reine Funktionen
  ausgelagert, die ohne Browser laufen, damit sie sich unit-testen lassen
- pytest und ruff laufen über GitHub Actions

Wenn du die echte Geschichte willst, inklusive aller Ansätze, die zuerst
gescheitert sind, ist der [Engineering-Log](docs/engineering-log.de.md) die
ehrliche Version.

---

## Installation

```bash
git clone https://github.com/nekodu/linkgate-bypass
cd linkgate-bypass
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# system dependency for the hidden virtual display
sudo apt install -y xvfb
```

Optional, nur falls du einen Proxy brauchst:

```bash
cp .env.example .env
# edit .env and set PROXY_URL
```

---

## Nutzung

```bash
# default: hidden virtual display, fully automatic, prints the real URL
python scripts/bypass.py https://ay.live/dzpal2

# watch it on a real screen (debugging)
python scripts/bypass.py https://ay.live/dzpal2 --show

# resolve several at once
python scripts/bypass.py --batch links.txt

# JSON output, with a VirusTotal reputation check on the result
python scripts/bypass.py https://ay.live/dzpal2 --json --check

# turn the proxy off for one run
python scripts/bypass.py https://ay.live/dzpal2 --no-proxy
```

Die aufgelöste URL geht nach `stdout`, alle Log-Meldungen gehen nach `stderr`,
also lässt es sich pipen:

```bash
xdg-open "$(python scripts/bypass.py https://ay.live/dzpal2)"
```

---

## Wie es funktioniert

1. SeleniumBase UC Mode öffnet ein echtes Chromium in einem versteckten
   `xvfb`-Display. Während der Turnstile-Challenge trennt es die
   DevTools-Verbindung, sodass der Browser sauber aussieht, verbindet sich dann
   wieder und klickt die Checkbox mit PyAutoGUI von außerhalb von chromedriver.
2. Nachdem der Countdown durch ist (`#go-link` bekommt die Klasse `go-link`),
   klickt es einmal den echten "Go to link"-Button. Das stößt die
   Token-Validierung `POST /get/tk` des Gates an und einen zweiten POST, der das
   Ziel zurückgibt.
3. Das Gate öffnet das Ziel nicht. Es schreibt es in das `onclick` von `#main` als
   `window.open("REAL_URL","_blank")`. Das Tool liest dieses Attribut und
   extrahiert die URL. Kein Popup, kein zweiter Klick, kein Race.
4. Ist die URL ein Zwischenstopp (zum Beispiel eine Notification-Permission-Seite),
   folgt das Tool der Redirect-Kette bis zum Endziel.
5. Gate-Domains, Werbenetzwerke und Tracker werden herausgefiltert, sodass nur das
   echte Ziel zurückkommt.

Es gibt auch eine schnellere zweite Engine (`--engine fast`, patchright), die
Network-Response-Interception für Gates nutzt, die kein Cloudflare verwenden.

---

## Engines

| | `stealth` (default) | `fast` |
|---|---|---|
| Backend | SeleniumBase UC Mode | patchright |
| Cloudflare Turnstile | löst es | kann nicht |
| Geschwindigkeit | langsamer (~30s) | schneller (~5s) |
| Capture | liest `#main` onclick, folgt Redirects | JSON-Response-Hook |
| Einsatz wenn | Cloudflare-geschützte Gates | Gates ohne Cloudflare |

---

## Security

- Proxy-Credentials liegen nur in einer gitignorierten `.env`, nie im Code, und
  nur der Proxy-Host wird geloggt.
- SeleniumBase schreibt eine Proxy-Auth-Browser-Extension mit den Credentials im
  Klartext auf die Platte; dieses Verzeichnis ist gitignoriert, damit es nicht
  leaken kann.
- WebRTC-UDP wird durch den Proxy gezwungen
  (`--force-webrtc-ip-handling-policy=disable_non_proxied_udp`), damit die echte IP
  nicht leakt.
- Die Browser-Sandbox bleibt aktiviert; Downloads sind in der fast-Engine
  deaktiviert.
- Seiteninhalt, der beim Reverse Engineering gelesen wird, wird als nicht
  vertrauenswürdige Daten behandelt, nicht als Anweisungen.

---

## Entwicklung

```bash
pip install -e ".[dev]"
pytest        # unit tests, no browser required
ruff check linkgate tests
```

Die reinen Helfer in `linkgate/extract.py` tragen die Logik, die sich ohne
Browser testen lässt (Zielerkennung, JSON-URL-Extraktion, Proxy-Parsing), sodass
die Testsuite schnell und deterministisch bleibt.

---

## Verantwortungsvolle Nutzung

Dieses Projekt existiert, um zu verstehen, wie Ad-Gate-Verkürzer funktionieren,
und um zu prüfen, wohin ein Link zeigt, bevor man ihm vertraut.

- jeweils ein Link, zur Inspektion, nicht zum massenhaften Abgreifen
- kein Betrug an Werbenetzwerken und kein Erzeugen falscher Impressions
- kein Tool, um an Inhalte zu kommen, auf die du keinen Anspruch hast
- halte dich an die Bedingungen der beteiligten Dienste und an das Recht an deinem
  Ort

---

## Lizenz

MIT
