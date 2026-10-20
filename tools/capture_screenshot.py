"""使用 Chrome DevTools Protocol (CDP) 驱动 Edge 截取 Streamlit 渲染后的完整页面
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

SCREENSHOTS_DIR = Path(r"D:\ClaimCheck_Pro\screenshots")
CACHE_DIR = Path(r"D:\ClaimCheck_Pro\.cache\edge_profile")
EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"


async def capture_cdp_screenshot():
    # 启动 Edge 浏览器附带调试端口
    cmd = [
        EDGE_PATH,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        f"--user-data-dir={CACHE_DIR}",
        "--remote-debugging-port=9222",
        "--window-size=1280,2600",
        "http://127.0.0.1:8501",
    ]
    proc = subprocess.Popen(cmd)
    print("Edge headless process started with debugging port 9222...")

    try:
        # 等待调试端口就绪
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
            print("Failed to acquire Edge DevTools WebSocket URL")
            return False

        print(f"Connecting to CDP WebSocket: {ws_url}")
        async with websockets.connect(ws_url) as ws:
            # 开启网络和页面域
            await ws.send(json.dumps({"id": 1, "method": "Page.enable"}))
            await ws.send(json.dumps({"id": 2, "method": "Runtime.enable"}))

            # 等待 4 秒，确保 Streamlit 前端完成数据加载与组件渲染
            print("Waiting for Streamlit page hydration...")
            await asyncio.sleep(4.5)

            # 截图 1：主界面初始状态（包含提示横幅、输入Tab、示例选择与预算信息）
            await ws.send(json.dumps({"id": 3, "method": "Page.captureScreenshot", "params": {"format": "png"}}))
            resp1 = json.loads(await ws.recv())
            # 处理可能的响应序号对齐
            while resp1.get("id") != 3:
                resp1 = json.loads(await ws.recv())

            img_bytes1 = base64.b64decode(resp1["result"]["data"])
            p1 = SCREENSHOTS_DIR / "v0.1_mock_ui_initial.png"
            with open(p1, "wb") as f:
                f.write(img_bytes1)
            print(f"✅ Initial page screenshot saved: {p1} ({len(img_bytes1)} bytes)")

            # 模拟在前端点击“开始核验分析”按钮
            click_expr = """
            (() => {
                const buttons = Array.from(document.querySelectorAll('button'));
                const btn = buttons.find(b => b.innerText.includes('开始核验分析'));
                if (btn) {
                    btn.click();
                    return true;
                }
                return false;
            })()
            """
            await ws.send(json.dumps({
                "id": 4,
                "method": "Runtime.evaluate",
                "params": {"expression": click_expr}
            }))
            resp_click = json.loads(await ws.recv())
            print(f"Clicked '开始核验分析' button...")

            # 等待结果渲染（约 3 秒）
            await asyncio.sleep(3.5)

            # 截图 2：核验完成后的看板状态（包含商品身份、四级分布卡片、声明明细、证据列表与下载按钮）
            await ws.send(json.dumps({
                "id": 5,
                "method": "Page.captureScreenshot",
                "params": {"format": "png", "captureBeyondViewport": True}
            }))
            resp2 = json.loads(await ws.recv())
            while resp2.get("id") != 5:
                resp2 = json.loads(await ws.recv())

            img_bytes2 = base64.b64decode(resp2["result"]["data"])
            p2 = SCREENSHOTS_DIR / "v0.1_mock_results_dashboard.png"
            with open(p2, "wb") as f:
                f.write(img_bytes2)
            print(f"✅ Results dashboard screenshot saved: {p2} ({len(img_bytes2)} bytes)")

            return True

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    asyncio.run(capture_cdp_screenshot())
