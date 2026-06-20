# linkgate-bypass

Resolve the real destination behind an "ad-gate" link shortener (the
adlinkfly / aylink family) without clicking ads, tripping trackers, or letting a
browser take over your screen.

🇩🇪 [Deutsche Version](README.de.md) · 📓 [Engineering log](docs/engineering-log.md)

> Security-research and learning project. It resolves one link at a time so you
> can see where a shortener points before clicking it. It is not a mass-scraping
> tool. See [Responsible use](#responsible-use).

---

## Why

These shorteners never expose the destination in the page. They hide it behind a
Cloudflare Turnstile challenge, a countdown, and a multi-step token exchange, then
bury the URL in a DOM attribute that only fires on a second click. Visiting the
gate by hand leaks data to ad networks and notification-permission traps, and the
final destination is sometimes hostile.

This tool clears the challenge in a hidden virtual display, reads the destination
straight from where the gate stores it, follows any intermediate redirect to the
end, and prints the real URL. It never clicks the ad button.

The full story of how I got there, including every approach that failed, is in the
[engineering log](docs/engineering-log.md). That log is the most interesting part
of this repository.

---

## What's in here, technically

- Getting past Cloudflare Turnstile with SeleniumBase UC Mode, which cuts the
  DevTools connection during the challenge so the browser looks clean
- Reverse engineering the gate's minified JavaScript to find the two-step token
  exchange and the spot where it actually stores the destination
- Keeping secrets out: proxy credentials in `.env` only, WebRTC leak prevention,
  the sandbox left on, scraped page content treated as untrusted
- An engine interface with two backends, and the URL logic split out into pure
  functions that run without a browser so they can be unit-tested
- pytest and ruff running on GitHub Actions

If you want the real story, including all the approaches that failed first, the
[engineering log](docs/engineering-log.md) is the honest version.

---

## Install

```bash
git clone https://github.com/nekodu/linkgate-bypass
cd linkgate-bypass
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# system dependency for the hidden virtual display
sudo apt install -y xvfb
```

Optional, only if you need a proxy:

```bash
cp .env.example .env
# edit .env and set PROXY_URL
```

---

## Usage

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

The resolved URL goes to `stdout`, all log messages go to `stderr`, so it pipes:

```bash
xdg-open "$(python scripts/bypass.py https://ay.live/dzpal2)"
```

---

## How it works

1. SeleniumBase UC Mode opens a real Chromium in a hidden `xvfb` display. During
   the Turnstile challenge it disconnects the DevTools connection so the browser
   looks clean, then reconnects, and clicks the checkbox with PyAutoGUI from
   outside chromedriver.
2. After the countdown finishes (`#go-link` gains the `go-link` class), it clicks
   the real "Go to link" button once. That triggers the gate's `POST /get/tk`
   token validation and a second POST that returns the destination.
3. The gate does not open the destination. It writes it into `#main`'s `onclick`
   as `window.open("REAL_URL","_blank")`. The tool reads that attribute and
   extracts the URL. No popup, no second click, no race.
4. If the URL is an intermediate hop (for example a notification-permission page),
   the tool follows the redirect chain to the final destination.
5. Gate domains, ad networks, and trackers are filtered out so only the real
   target is returned.

There is also a faster secondary engine (`--engine fast`, patchright) that uses
network-response interception for gates that do not use Cloudflare.

---

## Engines

| | `stealth` (default) | `fast` |
|---|---|---|
| Backend | SeleniumBase UC Mode | patchright |
| Cloudflare Turnstile | clears it | cannot |
| Speed | slower (~30s) | faster (~5s) |
| Capture | reads `#main` onclick, follows redirects | JSON response hook |
| Use when | Cloudflare-protected gates | gates without Cloudflare |

---

## Security

- Proxy credentials live only in a gitignored `.env`, never in code, and only the
  proxy host is logged.
- SeleniumBase writes a proxy-auth browser extension with the credentials in
  plaintext on disk; that directory is gitignored so it cannot leak.
- WebRTC UDP is forced through the proxy
  (`--force-webrtc-ip-handling-policy=disable_non_proxied_udp`) so the real IP
  does not leak.
- The browser sandbox stays enabled; downloads are disabled in the fast engine.
- Page content read during reverse engineering is treated as untrusted data, not
  as instructions.

---

## Development

```bash
pip install -e ".[dev]"
pytest        # unit tests, no browser required
ruff check linkgate tests
```

The pure helpers in `linkgate/extract.py` carry the logic that can be tested
without a browser (target detection, JSON URL extraction, proxy parsing), so the
test suite stays fast and deterministic.

---

## Responsible use

This project exists to understand how ad-gate shorteners work and to check where a
link points before trusting it.

- one link at a time, for inspection, not bulk harvesting
- no defrauding ad networks or generating fake impressions
- not a tool for accessing content you are not entitled to
- keep within the terms of the services involved and the law where you are

---

## License

MIT
