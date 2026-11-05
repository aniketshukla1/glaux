"""Render frames of a 3D logo through headless Chrome over CDP.

    render.py OUTDIR W H T1,T2,...          stills at the given loop positions
    render.py OUTDIR W H --frames N         a full loop of N frames
Extra `key=value` args go to stage.html's query string (mark=, name=, tag=, distance=, ...).
"""
import base64
import json
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

from websockets.sync.client import connect

HERE = Path(__file__).parent.resolve()
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9334


class Tab:
    def __init__(self, url):
        self.ws = connect(url, max_size=None, open_timeout=20)
        self.n = 0

    def send(self, method, **params):
        self.n += 1
        self.ws.send(json.dumps({"id": self.n, "method": method, "params": params}))
        while True:
            m = json.loads(self.ws.recv())
            if m.get("id") == self.n:
                if "error" in m:
                    raise RuntimeError(f"{method}: {m['error']}")
                return m.get("result", {})

    def js(self, expr):
        r = self.send("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True)
        if "exceptionDetails" in r:
            raise RuntimeError(json.dumps(r["exceptionDetails"])[:600])
        return r.get("result", {}).get("value")


def main():
    args = sys.argv[1:]
    out, w, h = Path(args[0]), int(args[1]), int(args[2])
    rest = args[3:]
    out.mkdir(parents=True, exist_ok=True)
    if rest[0] == "--frames":
        n = int(rest[1])
        times = [i / n for i in range(n)]
        extra = rest[2:]
    else:
        times = [float(x) for x in rest[0].split(",")]
        extra = rest[1:]
    query = dict(a.split("=", 1) for a in extra)
    query.update(w=w, h=h)
    url = f"file://{HERE}/stage.html?" + urllib.parse.urlencode(query)

    profile = tempfile.mkdtemp(prefix="logo3d-chrome-")
    proc = subprocess.Popen(
        [CHROME, "--headless=new", f"--remote-debugging-port={PORT}", f"--user-data-dir={profile}",
         "--allow-file-access-from-files", "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
         "--ignore-gpu-blocklist", "--no-first-run", "--hide-scrollbars", "--disable-extensions", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(80):
            try:
                targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=1))
                page = next(t for t in targets if t["type"] == "page")
                break
            except Exception:
                time.sleep(0.25)
        else:
            raise RuntimeError("Chrome did not start")
        tab = Tab(page["webSocketDebuggerUrl"])
        tab.send("Page.enable")
        tab.send("Runtime.enable")
        tab.send("Log.enable")
        dsf = float(query.get("dpr", 1))
        tab.send("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=dsf, mobile=False)
        tab.send("Page.navigate", url=url)
        end = time.time() + 60
        while not tab.js("!!window.ready"):
            if time.time() > end:
                raise TimeoutError("stage never became ready; console: " + str(tab.js("document.title")))
            time.sleep(0.2)
        start = time.time()
        for i, t in enumerate(times):
            tab.js(f"window.frame({t})")
            data = tab.send("Page.captureScreenshot", format="png", fromSurface=True)["data"]
            (out / f"f{i:04d}.png").write_bytes(base64.b64decode(data))
        print(f"{len(times)} frames in {time.time() - start:.1f}s -> {out}")
    finally:
        try:
            tab.send("Browser.close")
        except Exception:
            pass
        time.sleep(0.3)
        proc.kill()


if __name__ == "__main__":
    main()
