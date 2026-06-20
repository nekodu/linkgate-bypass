# Engineering log

Notes from building this thing. Kept honest on purpose, including the parts where
I went in circles. If you only read one file in the repo, read this one, because
the dead ends are where the actual learning happened.

> This is a security-research / learning project. It resolves one link at a time
> so you can see where a shortener points before clicking. Not a scraper. There's
> a [responsible use](#responsible-use) note at the bottom.

## Why I started

I had a link behind an `ay.link/...` shortener. You click it and you get a few ad
redirects, a Cloudflare page, a wall of trackers, then finally wherever it was
going. Sometimes that destination is sketchy. I wanted to know where a link
actually points before clicking, and the gate page itself already pings ad
networks and tries to get you to allow notifications.

So: can I get the real destination automatically, without clicking any ads and
without sitting there driving the browser myself? Short answer yes. Long answer is
the rest of this file.

## What the gate actually does

First thing I did was open DevTools and watch the network tab. The shape of it:

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

There's a nasty bit in the DOM:

```html
<main onclick="mainClick()" id="main" data-ppcnt_ads="https://ppcnt.eu/go.php?...">
  <a id="go-link">Go to link</a>
</main>
```

If you click anywhere on `#main` it runs `mainClick()` and opens the ad network.
The real button is `#go-link`, and it starts dead. `link.js` only adds the
`.go-link` / `.btn-go` classes after the countdown. Click it before that and
nothing happens. Took me a bit to notice that the two are completely separate code
paths and clicking the wrong one just feeds the ads.

## Things I tried that didn't work

**requests + BeautifulSoup.** My first guess was that the URL is sitting in the
HTML somewhere. It isn't. It's encrypted server-side and only comes back from
`/get/tk` once you have a valid Turnstile token. No browser, no URL. Moving on.

**Plain Playwright.** Cloudflare said "verification failed" basically
immediately. Turnstile looks at `navigator.webdriver`, whether there's a live CDP
(DevTools) connection during the challenge, headless fingerprint gaps, how regular
your mouse movement is, canvas/WebGL stuff. Stock Playwright fails all of that.

**playwright-stealth.** Patches `navigator.webdriver` and a few other tells.
Still failed Turnstile. The library is using older tricks and Turnstile is doing
something much heavier.

**patchright.** This one patches the Chromium binary itself, strips automation
flags. It beats simpler bot checks but not Turnstile, because Turnstile's real
move is spotting the live CDP connection and a binary patch doesn't touch that. I
didn't throw it away though, it's still the "fast" engine for gates that don't
have Cloudflare in front.

At this point I went and read a bunch of GitHub repos and forum threads about
Cloudflare. Half of them are AI-generated and don't actually work, some are just
old. I treated all of it as stuff to verify, not gospel. Two things came out of
it: SeleniumBase UC Mode (open source, actually handles Turnstile), and paid
captcha services (no thanks, this was supposed to cost nothing).

## SeleniumBase UC Mode, and the screen problem

UC Mode does the thing nothing else did. During the challenge it disconnects CDP
so the browser looks clean, then reconnects. It clicks the checkbox with PyAutoGUI
from outside chromedriver.

```python
with SB(uc=True, headless=False) as sb:
    sb.uc_open_with_reconnect(url, reconnect_time=4)
    sb.uc_gui_click_captcha()
```

Turnstile: passed. But the browser opened on my actual screen, full size, in front
of everything, so I couldn't even type. Also `uc_gui_click_captcha()` doesn't
always land on the checkbox on Linux, the coordinates drift, so I added a fallback
to try the other method:

```python
for attempt in ("uc_gui_click_captcha", "uc_gui_handle_captcha"):
    try:
        getattr(sb, attempt)()
        break
    except Exception:
        pass
```

The screen thing was the real annoyance.

## xvfb

UC Mode can't go truly headless (gets detected), it has to run headed, and headed
grabs the real display. The fix is a fake display. `xvfb` makes an X11 screen with
no monitor behind it, the browser renders into that, nothing shows up on my actual
desktop.

```bash
sudo apt install -y xvfb
```

SeleniumBase takes it directly:

```python
SB(uc=True, headless=False, xvfb=True)
```

I set it up as `xvfb=not opts.show` so hidden is the default and I can pass
`--show` when I want to watch it. After this it stopped hijacking my desktop, which
is the whole reason this was usable while I worked.

## Proxy, WebRTC, sandbox

Cloudflare blocks a lot of IP ranges outright. Datacenter IPs especially, because
that's where bot traffic comes from. Going through a residential proxy cut down the
"verification failed" responses a lot.

Credentials: I'm not putting the proxy user/pass in the code or in git. It goes in
a `.env` that's gitignored, read with `os.environ.get`, and I only ever log the
host, never the credentials.

```
# .env (gitignored)
PROXY_URL="http://USER:PASS@HOST:PORT"
```

WebRTC was a separate trap. Even with a proxy, WebRTC UDP can go around it and leak
your real IP. One Chrome flag shuts that down:

```
--force-webrtc-ip-handling-policy=disable_non_proxied_udp
```

There was also a sandbox warning. patchright adds `--no-sandbox` by default and the
system browser refuses it. The fix isn't to disable the sandbox, it's to turn it
back on:

```python
p.chromium.launch_persistent_context(chromium_sandbox=True, ...)
```

One thing that almost bit me: when you give SeleniumBase an authenticated proxy it
generates a little browser extension with the proxy username and password sitting
in plaintext on disk (`downloaded_files/proxy_ext_dir/`). That whole directory is
gitignored now so it can't leak out that way.

## The window.open detour (where I wasted the most time)

The first run that worked grabbed the destination off a new tab. Then I got clever
and tried to "harden" it by intercepting `window.open` so the ad popups couldn't
open:

```javascript
window.open = function(u) {
  if (u) window.__captured.push(String(u));
  return null;   // kill the window
};
```

This made everything worse. Returning `null` killed the gate's own `window.open`
call, its JS hit an error path, and it opened the ad fallback (`popcent.org`)
instead. So I "captured" the ad server. Two bugs stacked: the override broke the
flow, and `popcent` wasn't even in my ignore list.

So I made the hook non-destructive, call the original and just record the arg. Now
it captured `aylink.co`, which is the gate itself. Turns out `ay.live` is a short
alias that redirects to `aylink.co`, same family. So I added dynamic gate-family
learning: anything the main tab lands on counts as gate, and the real target is
whatever's left over.

Then the button got clicked and... nothing. `window.open` never fired, no new tab,
main tab just sat on `aylink.co`. At that point I was clearly just poking it and
hoping, and that wasn't getting me anywhere.

## Stopping the guessing and reading the code

I gave up on poke-and-watch and wrote `inspect_gate.py`. It opens the page with UC
Mode, passes Turnstile, then dumps the full DOM, all 16 scripts (inline and the
`src` ones, fetched with the page's own session), and the button/token/form
structure into `probe.json`.

`probe.json` had the good stuff:

- `#go-link` has a `data-token` (looks like a JWT, the visitor token)
- a hidden form with `_method=POST`, `alias=dzpal2`, `csrf=<hash>`
- global functions called `getReqToken`, `saveToken`, `setTokenSentToServer`

The actual logic was in `go-lnk.min.js`. Here's what happens when `.btn-go` gets
clicked:

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

And there's the answer to "why do I have to click twice". First click on
`.btn-go` runs the two AJAX calls and stuffs the real URL into `#main`'s `onclick`
as `window.open("REAL_URL","_blank")`. The second click, on `#main`, is what
actually fires that and opens the tab.

This is also exactly why my `window.open` override was doomed. The URL isn't an
argument to `window.open` at the point I cared about, it's a string sitting in a
DOM attribute. `window.open` doesn't get called until the second click, and the
URL is already written down before that.

## The fix that actually works

No second click needed. Click the button once, then just read `#main`'s `onclick`
and pull the URL out:

```python
onclick = driver.execute_script(
    "var m=document.querySelector('#main'); return m?m.getAttribute('onclick'):null;")
m = re.search(r'window\.open\(\s*[\'"]([^\'"]+)[\'"]', onclick)
real_url = m.group(1)
```

No popup, no second click, no window.open hook, no timing race. And I'm checking
readiness the right way now: the button's ready when `#go-link` has the `go-link`
class, not by guessing at element visibility like before.

## One more hop: bildirim.online

The URL I read off `#main` came out as `bildirim.online/ph/...` the first time.
That's not the content, it's an in-between stop (a notification-permission ad
page). A real user hits that on the second click and then gets bounced to the real
site. So I follow the redirect chain until it stops moving:

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

Full run, start to finish:

```
[*] Opening (UC Mode): https://ay.live/dzpal2
[*] Captcha attempt: uc_gui_click_captcha()
[*] Waiting for countdown + button...
[*] "Go to link" clicked: .complete .btn-go
[+] Target (#main onclick): https://bildirim.online/ph/cmFZRzdz...
[*] Final stop: https://dizipal1029.com/
https://dizipal1029.com/
```

The lesson I actually walked away with: "don't touch the gate's JS" wasn't the
real rule. The real rule was read what the page does, grab the output from where it
actually lives (a DOM attribute, not a function call), and follow the hops to the
end. I'd have saved hours by reading `go-lnk.min.js` on day one instead of poking
at buttons.

## Stuff worth remembering

Bot detection is no joke. Turnstile is checking `navigator.webdriver`, the live
CDP connection, mouse patterns, headless API gaps, canvas/WebGL. UC Mode is the
only thing that got through and it does it by actually cutting CDP during the
challenge. Patching flags or monkeypatching functions doesn't cut it.

Reading the system beats probing it. I lost most of my time clicking and watching.
The second I dumped and read the JS, the answer was right there.

Overriding DOM globals like `window.open` is a trap. The page doesn't expect it,
the error paths go somewhere else, and Cloudflare can notice. Watch the output,
don't rewrite the flow.

Headed browser plus a virtual display is the clean answer to "headless gets
detected but I don't want it on my screen". One parameter instead of a pile of
headless workarounds.

Keep secrets out by construction. `.env`, gitignore the proxy extension dir, log
the host only. It's easy to leak the proxy through that auto-generated extension if
you're not watching.

## How it's laid out

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

Two engines because they're good at different things:

| | stealth (SeleniumBase) | fast (patchright) |
|---|---|---|
| Turnstile | clears it | can't |
| Speed | slower (~30s) | faster (~5s) |
| Captcha | UC Mode + PyAutoGUI | binary patch only |
| Capture | reads #main onclick, follows redirects | JSON response hook |
| Use when | Cloudflare gates | gates without Cloudflare |

## How it actually went, in order

1. requests + BeautifulSoup, URL not in the HTML, dead end
2. Playwright, Turnstile failed
3. playwright-stealth, still failed
4. patchright, still failed, kept it as the fast engine
5. found SeleniumBase UC Mode
6. UC Mode headed, worked but took over the screen
7. xvfb, screen problem gone
8. residential proxy, fewer Cloudflare blocks
9. WebRTC flag added
10. sandbox warning fixed with chromium_sandbox=True
11. first success off a new tab, got the destination
12. window.open override, captured the ad server instead, oops
13. non-destructive hook, captured the gate itself (aylink.co)
14. dynamic gate-family learning, button clicked but nothing came back
15. stopped guessing, wrote inspect_gate.py, dumped DOM + 16 scripts
16. read go-lnk.min.js, found the real mechanism (URL goes into #main onclick)
17. read the onclick, got the bildirim.online hop
18. followed the redirects, landed on the real target, deterministic
19. rewrote this log from what actually happened

## Responsible use

This is here to understand how ad-gate shorteners work and to check where a link
goes before trusting it.

- one link at a time, for inspection, not bulk harvesting
- not for defrauding ad networks or faking impressions
- not for getting at content you're not allowed to have
- stay within the terms of the services involved and the law where you are
