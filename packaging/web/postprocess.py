"""Makes pygbag's page fit a phone: the viewport and the Home Screen app tags, a manifest and icons, a black page, no scrolling or
zooming, and a message to turn the phone sideways. Usage: postprocess.py <web folder> <version> <icon-512.png>"""
import json
import os
import re
import shutil
import sys

HEAD = """
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="Space Miner">
    <meta name="theme-color" content="#06080f">
    <meta name="description" content="Space Miner {version}: an idle game about mining the solar system and conquering the Milky Way.">
    <link rel="apple-touch-icon" href="icon-512.png">
    <link rel="manifest" href="manifest.webmanifest">
    <style>
        html, body { background: #06080f !important; height: 100%; margin: 0; overflow: hidden; overscroll-behavior: none; touch-action: none;
                     -webkit-user-select: none; user-select: none; -webkit-touch-callout: none; -webkit-tap-highlight-color: transparent; }
        canvas.emscripten { touch-action: none; outline: none; }
        #infobox { background: #16213a !important; color: #cfe3ff !important; border-radius: 10px; font-family: sans-serif; }
        #status { color: #8fa3c8 !important; }
        #rotate { display: none; position: fixed; inset: 0; z-index: 2000000; background: #06080f; color: #cfe3ff; font: 600 20px/1.5 sans-serif;
                  align-items: center; justify-content: center; text-align: center; padding: 24px; }
        @media (orientation: portrait) and (pointer: coarse) { #rotate { display: flex; } }
    </style>
"""
BODY = '<div id="rotate"><div>Turn your phone sideways<br><span style="font-weight:400;font-size:16px">Space Miner is played in landscape.</span></div></div>\n'


def main(web, version, icon):
    path = os.path.join(web, "index.html")
    with open(path, encoding="utf-8") as f:
        html = f.read()
    html, n = re.subn(r'\s*<meta name="viewport"[^>]*>', "", html)
    assert "</head>" in html and "</body>" in html, "unexpected page from pygbag"
    html = html.replace("</head>", HEAD.replace("{version}", version) + "</head>", 1)
    html = html.replace("</body>", BODY + "</body>", 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    shutil.copy(icon, os.path.join(web, "icon-512.png"))
    manifest = dict(name="Space Miner", short_name="Space Miner", start_url="./", display="fullscreen", orientation="landscape",
                    background_color="#06080f", theme_color="#06080f",
                    icons=[dict(src="icon-512.png", sizes="512x512", type="image/png", purpose="any")])
    with open(os.path.join(web, "manifest.webmanifest"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    open(os.path.join(web, ".nojekyll"), "w").close()         # (GitHub Pages: serve every file as it is)
    print(f"Page ready for phones ({n} old viewport tag(s) replaced).")


if __name__ == "__main__":
    main(*sys.argv[1:4])
