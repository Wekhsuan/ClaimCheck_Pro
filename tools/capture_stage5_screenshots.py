"""使用 CDP 精准截取阶段 5 交叉验证、声明拆解、8项证据规范与自检看板截图
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

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

SCREENSHOTS_DIR = Path(r"D:\ClaimCheck_Pro\screenshots")
CACHE_DIR = Path(r"D:\ClaimCheck_Pro\.cache\edge_profile_stage5")
EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

req_counter = 0


async def send_cdp(ws, method, params=None):
    """发送 CDP 命令并精准阻塞等待对应的响应 ID"""
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
    """执行 JavaScript 表达式并返回 value"""
    resp = await send_cdp(ws, "Runtime.evaluate", {"expression": expr, "returnByValue": True})
    return resp.get("result", {}).get("result", {}).get("value")


async def click_element(ws, selector_type, text_to_match):
    """通过 CDP 物理鼠标事件精准点击元素"""
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
        print(f"[WARN] Target '{text_to_match}' not found for clicking")
        return False

    x, y = coords["x"], coords["y"]
    print(f"[ACTION] Physical click on '{text_to_match}' at ({x:.1f}, {y:.1f})")
    await send_cdp(ws, "Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
    await asyncio.sleep(0.05)
    await send_cdp(ws, "Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
    await asyncio.sleep(0.05)
    await send_cdp(ws, "Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})
    return True


async def capture_stage5():
    cmd = [
        EDGE_PATH,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--no-first-run",
        "--no-default-browser-check",
        f"--user-data-dir={CACHE_DIR}",
        "--remote-debugging-port=9225",
        "--window-size=1280,4800",
        "http://127.0.0.1:8501",
    ]
    proc = subprocess.Popen(cmd)
    print("[INIT] Edge headless started on port 9225...")

    try:
        ws_url = None
        for _ in range(15):
            time.sleep(1)
            try:
                res = requests.get("http://127.0.0.1:9225/json", timeout=2).json()
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
            raise RuntimeError("无法连接到 Edge CDP 调试端口 9225")

        async with websockets.connect(ws_url, max_size=20 * 1024 * 1024) as ws:
            print("[CONNECTED] CDP WebSocket connected.")
            await send_cdp(ws, "Page.enable")
            await send_cdp(ws, "Runtime.enable")

            # 等待 Streamlit 页面完全就绪
            print("[WAIT] Waiting for Streamlit application to render...")
            for _ in range(15):
                ready = await eval_js(ws, "document.querySelectorAll('button').length > 0")
                if ready:
                    break
                await asyncio.sleep(1)

            await asyncio.sleep(2)

            # 点击“开始核验分析”按钮
            print("[ACTION] Triggering verification analysis...")
            clicked = await click_element(ws, "button", "开始核验分析")
            if not clicked:
                # 尝试再次查找按钮
                await click_element(ws, "button", "核验分析")

            # 等待核验看板呈现
            print("[WAIT] Waiting for verification board & evidence cards to render...")
            for _ in range(15):
                has_board = await eval_js(ws, "document.body.innerText.includes('核验结果看板')")
                if has_board:
                    break
                await asyncio.sleep(1)

            await asyncio.sleep(2)

            # 截图保存为 stage5_cross_verification.png
            print("[CAPTURE] Capturing Stage 5 Cross Verification Dashboard...")
            shot_res = await send_cdp(ws, "Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
            img_data = base64.b64decode(shot_res["result"]["data"])
            out_path = SCREENSHOTS_DIR / "stage5_cross_verification.png"
            with open(out_path, "wb") as f:
                f.write(img_data)
            print(f"[SUCCESS] Saved screenshot to {out_path} ({len(img_data) / 1024:.1f} KB)")

            # 滚动到页面底部截取购买建议、人工核验与报告导出卡片
            print("[ACTION] Scrolling to bottom for advice and report export...")
            await eval_js(ws, """
            (() => {
                const target = Array.from(document.querySelectorAll('h3, h4, div')).find(e => e.innerText && e.innerText.includes('人工确认清单与购买前建议'));
                if (target) {
                    target.scrollIntoView({behavior: 'instant', block: 'start'});
                }
            })()
            """)
            await asyncio.sleep(1.5)

            shot_bottom = await send_cdp(ws, "Page.captureScreenshot", {"format": "png"})
            img_bottom_data = base64.b64decode(shot_bottom["result"]["data"])
            out_bottom_path = SCREENSHOTS_DIR / "stage5_advice_and_export.png"
            with open(out_bottom_path, "wb") as f:
                f.write(img_bottom_data)
            print(f"[SUCCESS] Saved bottom screenshot to {out_bottom_path} ({len(img_bottom_data) / 1024:.1f} KB)")

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except Exception:
            proc.kill()
        print("[CLEANUP] Edge browser process terminated.")


if __name__ == "__main__":
    asyncio.run(capture_stage5())
