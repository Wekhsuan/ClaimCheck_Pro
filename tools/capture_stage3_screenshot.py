"""截取阶段3：BYOK 与 LocalModel 前端配置界面的真实渲染截图
"""

import asyncio
import base64
import json
import subprocess
import time
from pathlib import Path
import requests
import websockets

SCREENSHOTS_DIR = Path(r"D:\ClaimCheck_Pro\screenshots")
CACHE_DIR = Path(r"D:\ClaimCheck_Pro\.cache\edge_profile")
EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"


async def capture_stage3_screenshots():
    cmd = [
        EDGE_PATH,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        f"--user-data-dir={CACHE_DIR}",
        "--remote-debugging-port=9222",
        "--window-size=1280,1800",
        "http://127.0.0.1:8501",
    ]
    proc = subprocess.Popen(cmd)

    try:
        ws_url = None
        for _ in range(15):
            time.sleep(1)
            try:
                res = requests.get("http://127.0.0.1:9222/json", timeout=2).json()
                if res and len(res) > 0:
                    ws_url = res[0].get("webSocketDebuggerUrl")
                    if ws_url:
                        break
            except Exception:
                pass

        if not ws_url:
            print("Failed to acquire WebSocket URL")
            return False

        async with websockets.connect(ws_url) as ws:
            await ws.send(json.dumps({"id": 1, "method": "Page.enable"}))
            await ws.send(json.dumps({"id": 2, "method": "Runtime.enable"}))

            # 等待 4 秒完全渲染
            await asyncio.sleep(4.0)

            # 点击“测试连接 (Mock端点)”按钮以展示连接测试能力矩阵卡片
            click_test_btn = """
            (() => {
                const buttons = Array.from(document.querySelectorAll('button'));
                const btn = buttons.find(b => b.innerText.includes('测试连接'));
                if (btn) {
                    btn.click();
                    return true;
                }
                return false;
            })()
            """
            await ws.send(json.dumps({"id": 3, "method": "Runtime.evaluate", "params": {"expression": click_test_btn}}))
            await asyncio.sleep(2.5)

            # 截图保存
            await ws.send(json.dumps({
                "id": 4,
                "method": "Page.captureScreenshot",
                "params": {"format": "png", "captureBeyondViewport": True}
            }))
            resp = json.loads(await ws.recv())
            while resp.get("id") != 4:
                resp = json.loads(await ws.recv())

            img_bytes = base64.b64decode(resp["result"]["data"])
            p = SCREENSHOTS_DIR / "stage3_byok_gateway.png"
            with open(p, "wb") as f:
                f.write(img_bytes)
            print(f"✅ Stage 3 screenshot saved: {p} ({len(img_bytes)} bytes)")

            return True
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    asyncio.run(capture_stage3_screenshots())
