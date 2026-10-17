"""Screenshot NVIDIA Auto Ontology's UI pages for reports/screenshots using headless Chrome over the
DevTools protocol, after signing in with the local admin test account from vendor/auto-ontology/.env.

    uv run --with websocket-client python scripts/screenshot_auto_ontology.py
"""
from __future__ import annotations

import base64
import json
import subprocess
import sys
import time
from pathlib import Path

import httpx
import websocket  # websocket-client

ROOT = Path(__file__).resolve().parents[1]
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PAGES = {"auto_ontology_terms": "/terms", "auto_ontology_data_catalog": "/data", "auto_ontology_exploration": "/exploration",
         "auto_ontology_chat": "/chat", "auto_ontology_analysis": "/analysis"}
if len(sys.argv) > 1:
    PAGES = {k: v for k, v in PAGES.items() if k in sys.argv[1:]}


def read_env(path: Path) -> dict[str, str]:
    out = {}
    for line in path.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def main() -> int:
    env = read_env(ROOT / "vendor" / "auto-ontology" / ".env")
    r = httpx.post("http://localhost:3000/api/auth/sign-in/email", timeout=120,
                   json={"email": env["AUTO_ONTOLOGY_ADMIN_EMAIL"], "password": env["AUTO_ONTOLOGY_ADMIN_PASSWORD"]})
    r.raise_for_status()
    cookie = r.cookies.get("better-auth.session_token")
    out_dir = ROOT / "reports" / "screenshots"
    out_dir.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--remote-debugging-port=9223",
                             "--window-size=1440,1000", "--user-data-dir=/tmp/kap-chrome-profile", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                targets = httpx.get("http://127.0.0.1:9223/json").json()
                break
            except Exception:  # noqa: BLE001
                time.sleep(0.2)
        page = next(t for t in targets if t["type"] == "page")
        ws = websocket.create_connection(page["webSocketDebuggerUrl"], suppress_origin=True)
        mid = 0

        def send(method, **params):
            nonlocal mid
            mid += 1
            ws.send(json.dumps({"id": mid, "method": method, "params": params}))
            while True:
                msg = json.loads(ws.recv())
                if msg.get("id") == mid:
                    return msg.get("result", {})

        send("Network.enable")
        send("Network.setCookie", name="better-auth.session_token", value=cookie, domain="localhost", path="/", httpOnly=True)
        send("Page.enable")
        for name, path in PAGES.items():
            send("Page.navigate", url=f"http://localhost:3000{path}")
            time.sleep(6)
            if path == "/chat":
                # type a question into the chat box if present and wait for the answer
                send("Runtime.evaluate", expression="""(() => { const ta = document.querySelector('textarea'); if (!ta) return 'no textarea';
                    const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
                    setter.call(ta, 'How many support cases have severity 1?'); ta.dispatchEvent(new Event('input', {bubbles: true}));
                    const form = ta.closest('form'); if (form) { form.requestSubmit(); return 'submitted'; }
                    ta.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true})); return 'enter'; })()""")
                time.sleep(170)
            shot = send("Page.captureScreenshot", format="png")
            (out_dir / f"{name}.png").write_bytes(base64.b64decode(shot["data"]))
            print("wrote", name)
        ws.close()
    finally:
        proc.terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
