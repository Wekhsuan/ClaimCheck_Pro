"""截取当前版本 UI 截图作为 Before 存档
保存至 screenshots/ui_redesign/ 目录
"""

import asyncio
import base64
import json
import subprocess
import sys
import time
from pathlib import Path
import requests
import websockets

WORKSPACE_ROOT = Path(r"D:\ClaimCheck_Pro").resolve()
OUT_DIR = WORKSPACE_ROOT / "screenshots" / "ui_redesign"
OUT_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR = WORKSPACE_ROOT / ".cache" / "edge_profile_before"
EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

req_counter = 0


async def send_cdp(ws, method, params=None):
    global req_counter
    req_counter += 1
    cid = req_counter
    msg = {"id": cid, "method": method}
    if params:
        msg["params"] = params
    await ws.send(json.dumps(msg))

    while True:
        raw = await ws.recv()
        resp = json.loads(raw)
        if resp.get("id") == cid:
            return resp


async def eval_js(ws, expr):
    resp = await send_cdp(ws, "Runtime.evaluate", {"expression": expr, "returnByValue": True})
    return resp.get("result", {}).get("result", {}).get("value")


async def click_element(ws, selector_type, text_to_match):
    expr = f"""
    (() => {{
        const elements = Array.from(document.querySelectorAll('{selector_type}'));
        const el = elements.find(e => e.innerText && e.innerText.includes('{text_to_match}'));
        if (!el) return null;
        el.scrollIntoView({{block: 'center'}});
        const rect = el.getBoundingClientRect();
        return {{ x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 }};
    }})()
    """
    coords = await eval_js(ws, expr)
    if not coords or coords.get("x") is None:
        return False
    x, y = coords["x"], coords["y"]
    await send_cdp(ws, "Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
    await asyncio.sleep(0.05)
    await send_cdp(ws, "Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
    await asyncio.sleep(0.05)
    await send_cdp(ws, "Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})
    return True


async def capture_before():
    cmd = [
        EDGE_PATH,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--no-first-run",
        "--no-default-browser-check",
        f"--user-data-dir={CACHE_DIR}",
        "--remote-debugging-port=9227",
        "--window-size=1280,2400",
        "http://127.0.0.1:8501",
    ]
    proc = subprocess.Popen(cmd)
    try:
        ws_url = None
        for _ in range(15):
            time.sleep(1)
            try:
                res = requests.get("http://127.0.0.1:9227/json", timeout=2).json()
                if res and len(res) > 0:
                    for target in res:
                        if "8501" in target.get("url", ""):
                            ws_url = target.get("webSocketDebuggerUrl")
                            break
                    if ws_url:
                        break
            except Exception:
                pass

        if not ws_url:
            raise RuntimeError("无法连接到 Edge CDP 端口 9227")

        async with websockets.connect(ws_url, max_size=20 * 1024 * 1024) as ws:
            await send_cdp(ws, "Page.enable")
            await send_cdp(ws, "Runtime.enable")
            await asyncio.sleep(3)

            # 1. 截取初始首页 Before
            shot1 = await send_cdp(ws, "Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
            p1 = OUT_DIR / "before_homepage.png"
            p1.write_bytes(base64.b64decode(shot1["result"]["data"]))
            print(f"[SAVED] {p1} ({p1.stat().st_size / 1024:.1f} KB)")

            # 2. 点击开始核验，截取结果看板 Before
            await click_element(ws, "button", "开始核验分析")
            await asyncio.sleep(3)
            shot2 = await send_cdp(ws, "Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
            p2 = OUT_DIR / "before_results_dashboard.png"
            p2.write_bytes(base64.b64decode(shot2["result"]["data"]))
            print(f"[SAVED] {p2} ({p2.stat().st_size / 1024:.1f} KB)")

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    asyncio.run(capture_before())
