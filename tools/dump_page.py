import asyncio
import json
import subprocess
import time
from pathlib import Path
import requests
import websockets

EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
CACHE_DIR = Path(r"D:\ClaimCheck_Pro\.cache\edge_dump")

cmd = [
    EDGE_PATH,
    "--headless=new",
    "--disable-gpu",
    "--no-sandbox",
    f"--user-data-dir={CACHE_DIR}",
    "--remote-debugging-port=9233",
    "http://127.0.0.1:8501",
]
proc = subprocess.Popen(cmd)
time.sleep(3)

try:
    r = requests.get("http://127.0.0.1:9233/json").json()
    ws_url = None
    for t in r:
        if "8501" in t.get("url", ""):
            ws_url = t.get("webSocketDebuggerUrl")
            break

    async def main():
        async with websockets.connect(ws_url) as ws:
            await ws.send(json.dumps({"id": 1, "method": "Runtime.enable"}))
            await asyncio.sleep(4)
            await ws.send(json.dumps({
                "id": 2,
                "method": "Runtime.evaluate",
                "params": {"expression": "document.body.innerText", "returnByValue": True}
            }))
            while True:
                msg = json.loads(await ws.recv())
                if msg.get("id") == 2:
                    val = msg.get("result", {}).get("result", {}).get("value", "")
                    with open(r"D:\ClaimCheck_Pro\.cache\dump_body.txt", "w", encoding="utf-8") as f:
                        f.write(val)
                    print("DUMP DONE. Length:", len(val))
                    break

    asyncio.run(main())
finally:
    proc.terminate()
