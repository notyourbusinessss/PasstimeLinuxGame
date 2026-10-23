#!/usr/bin/env python3
"""Opens the built web version (build/web, see packaging/build_web.sh) in a headless browser that looks like a phone held sideways, and checks
that the game starts, draws, moves, reacts to taps and keeps its save in the browser's storage across a reload.
    python3 tools/web_check.py build/web [--out DIR] [--browser chromium|webkit] [--timeout 420]
Needs `pip install playwright` and `playwright install chromium`. Writes screenshots and the browser's console to --out. Exit status 1 on a failure."""
import argparse
import functools
import http.server
import json
import os
import re
import sys
import threading
import time

from playwright.sync_api import sync_playwright

UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1")
SAVE_KEY = "space-miner:.space_miner_save.json"
FRAMES = re.compile(r"space-miner: (\d+) frames, (\d+) fps")


def serve(directory):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=directory)
    handler.log_message = lambda *a, **k: None
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def stored_clicks(page):
    raw = page.evaluate(f"localStorage.getItem({SAVE_KEY!r})")
    return None if not raw else json.loads(raw).get("clicks")


def wait_for_game(page, logs, since, timeout):
    """Tap the page (it waits for a tap before it starts) until the game says it is running. Returns (seconds, the fps line) or None."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        page.touchscreen.tap(422, 195)
        page.wait_for_timeout(2000)
        for line in logs[since:]:
            if FRAMES.search(line):
                return time.time() - t0, line
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("web")
    ap.add_argument("--out", default="web-check-out")
    ap.add_argument("--browser", default="chromium")
    ap.add_argument("--timeout", type=int, default=420)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    httpd = serve(os.path.abspath(args.web))
    url = f"http://127.0.0.1:{httpd.server_address[1]}/index.html"
    logs, failures, report = [], [], []

    def say(text):
        print(text, flush=True)
        report.append(text)

    with sync_playwright() as p:
        browser = getattr(p, args.browser).launch()
        ctx = browser.new_context(viewport={"width": 844, "height": 390}, has_touch=True, is_mobile=True, user_agent=UA, device_scale_factor=1)
        page = ctx.new_page()
        page.on("console", lambda m: logs.append(f"[{m.type}] {m.text}"))
        page.on("pageerror", lambda e: logs.append(f"[pageerror] {e}"))
        page.goto(url)
        up = wait_for_game(page, logs, 0, args.timeout)
        if up is None:
            page.screenshot(path=os.path.join(args.out, "timeout.png"))
            failures.append(f"the game did not start within {args.timeout} s")
        else:
            say(f"started after {up[0]:.0f} s: {up[1]}")
            say(f"viewport touch interface / canvas: {page.evaluate('[matchMedia(\"(pointer: coarse)\").matches, document.querySelector(\"canvas\").width, document.querySelector(\"canvas\").height, document.querySelector(\"canvas\").style.width, document.querySelector(\"canvas\").style.height]')}")
            page.wait_for_timeout(1500)
            first = page.screenshot(type="jpeg", quality=70)
            open(os.path.join(args.out, "1-start.jpg"), "wb").write(first)
            page.wait_for_timeout(1500)
            second = page.screenshot(type="jpeg", quality=70)
            say(f"screenshot sizes: {len(first)} and {len(second)} bytes (a blank page is under 5000)")
            if len(first) < 8000:
                failures.append("the page looks blank")
            if first == second:
                failures.append("nothing moved between two screenshots")
            for _ in range(25):
                page.touchscreen.tap(300, 200)
                page.wait_for_timeout(80)
            page.wait_for_timeout(1500)
            open(os.path.join(args.out, "2-after-taps.jpg"), "wb").write(page.screenshot(type="jpeg", quality=70))
            clicks = None
            for _ in range(14):                              # the game saves every 15 seconds
                page.wait_for_timeout(2000)
                clicks = stored_clicks(page)
                if clicks:
                    break
            say(f"clicks in the browser's storage: {clicks}")
            if not clicks or clicks < 10:
                failures.append(f"the save did not reach localStorage with the taps (clicks={clicks})")
            else:
                page.reload()
                mark = len(logs)
                logs.append("[check] reloaded")
                back = wait_for_game(page, logs, mark, args.timeout)
                if back is None:
                    failures.append("the game did not start again after a reload")
                else:
                    page.wait_for_timeout(20000)
                    after = stored_clicks(page)
                    say(f"after a reload ({back[0]:.0f} s): clicks in storage {after}")
                    open(os.path.join(args.out, "3-after-reload.jpg"), "wb").write(page.screenshot(type="jpeg", quality=70))
                    if not after or after < clicks:
                        failures.append(f"the save was not restored after a reload ({clicks} -> {after})")
            bad = [l for l in logs if "Traceback" in l or l.startswith("[pageerror]")]
            failures += [f"error in the console: {l[:300]}" for l in bad[:5]]
        browser.close()
    httpd.shutdown()
    with open(os.path.join(args.out, "console.log"), "w", encoding="utf-8") as f:
        f.write("\n".join(logs))
    say(f"{len(logs)} console lines; failures: {failures or 'none'}")
    if os.environ.get("GITHUB_ACTIONS"):                    # the run's annotations are the quickest place to read the result
        tail = "\n".join(l[:240] for l in logs[-60:])
        text = "\n".join(report + ["--- console (last lines) ---", tail])[:30000]
        print("::notice title=web-check::" + text.replace("%", "%25").replace("\r", "").replace("\n", "%0A"))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
