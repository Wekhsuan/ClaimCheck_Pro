import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path
import requests
import websockets

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
CACHE_DIR = Path(r"D:\ClaimCheck_Pro\.cache\test_edge")

cmd = [
    EDGE_PATH,
    "--headless=new",
    "--disable-gpu",
    "--no-sandbox",
    f"--user-data-dir={CACHE_DIR}",
    "--remote-debugging-port=9229",
    "http://127.0.0.1:8501",
]
proc = subprocess.Popen(cmd)
time.sleep(3)

try:
    targets = requests.get("http://127.0.0.1:9229/json").json()
    ws_url = None
    for t in targets:
        if "8501" in t.get("url", ""):
            ws_url = t.get("webSocketDebuggerUrl")
            break
    if not ws_url:
        ws_url = targets[0]["webSocketDebuggerUrl"]

    async def main():
        async with websockets.connect(ws_url) as ws:
            await ws.send(json.dumps({"id": 1, "method": "Runtime.enable"}))
            for _ in range(20):
                await ws.send(json.dumps({"id": 99, "method": "Runtime.evaluate", "params": {"expression": "document.body.innerText.includes('开始核验分析')", "returnByValue": True}}))
                msg = json.loads(await ws.recv())
                if msg.get("id") == 99 and msg.get("result", {}).get("result", {}).get("value") is True:
                    break
                await asyncio.sleep(0.5)

            # Dump buttons
            expr = "Array.from(document.querySelectorAll('button')).map((b, i) => i + ': ' + b.innerText)"
            await ws.send(json.dumps({"id": 2, "method": "Runtime.evaluate", "params": {"expression": expr, "returnByValue": True}}))

            # Dump tabs
            expr_tabs = "Array.from(document.querySelectorAll('[data-testid=\"stTab\"]')).map((t, i) => i + ': ' + t.innerText)"
            await ws.send(json.dumps({"id": 3, "method": "Runtime.evaluate", "params": {"expression": expr_tabs, "returnByValue": True}}))

            # Dump expanders
            expr_exp = "Array.from(document.querySelectorAll('[data-testid=\"stExpander\"] summary')).map((e, i) => i + ': ' + e.innerText)"
            await ws.send(json.dumps({"id": 4, "method": "Runtime.evaluate", "params": {"expression": expr_exp, "returnByValue": True}}))

            received = 0
            while received < 3:
                msg = json.loads(await ws.recv())
                if msg.get("id") == 2:
                    print("Buttons:", msg["result"]["result"]["value"])
                    received += 1
                elif msg.get("id") == 3:
                    print("Tabs:", msg["result"]["result"]["value"])
                    received += 1
                elif msg.get("id") == 4:
                    print("Expanders:", msg["result"]["result"]["value"])
                    received += 1

    asyncio.run(main())
finally:
    proc.terminate()
