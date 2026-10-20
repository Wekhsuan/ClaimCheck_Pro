"""使用 CDP 严格对齐响应机制截取阶段 4 界面真实交互状态
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
CACHE_DIR = Path(r"D:\ClaimCheck_Pro\.cache\edge_profile_stage4")
EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

req_counter = 0


async def send_cdp(ws, method, params=None):
    """发送 CDP 命令并精准阻塞等待对应的响应 ID，杜绝消息队列错位"""
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


async def capture_stage4():
    cmd = [
        EDGE_PATH,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--no-first-run",
        "--no-default-browser-check",
        f"--user-data-dir={CACHE_DIR}",
        "--remote-debugging-port=9223",
        "--window-size=1280,2400",
        "http://127.0.0.1:8501",
    ]
    proc = subprocess.Popen(cmd)
    print("[INIT] Edge headless started on port 9223...")

    try:
        ws_url = None
        for _ in range(15):
            time.sleep(1)
            try:
                res = requests.get("http://127.0.0.1:9223/json", timeout=2).json()
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
            print("[ERROR] Failed to acquire DevTools URL for 8501")
            return False

        print(f"[CDP] Connecting to: {ws_url}")
        async with websockets.connect(ws_url) as ws:
            await send_cdp(ws, "Page.enable")
            await send_cdp(ws, "Runtime.enable")

            # 等待 Streamlit 页面水合完成
            print("[WAIT] Waiting for Streamlit page hydration...")
            await asyncio.sleep(4.5)

            # -------------------------------------------------------------
            # 截图 1: 阶段 4 初始界面总览（含三个输入 Tab）
            # -------------------------------------------------------------
            r1 = await send_cdp(ws, "Page.captureScreenshot", {"format": "png"})
            p1 = SCREENSHOTS_DIR / "stage4_inputs_overview.png"
            p1.write_bytes(base64.b64decode(r1["result"]["data"]))
            print(f"[SUCCESS] Saved screenshot 1: {p1} ({p1.stat().st_size} bytes)")

            # -------------------------------------------------------------
            # 切换到 Tab 2: 商品详情文本
            # -------------------------------------------------------------
            print("[ACTION] Switching to '商品详情文本' tab...")
            await click_element(ws, 'div[data-testid="stTab"]', "商品详情文本")
            await asyncio.sleep(1.5)

            # 聚焦文本框并填入多候选宣传文案
            print("[ACTION] Focusing textarea and typing multi-model text...")
            focus_ok = await eval_js(ws, """
            (() => {
                const ta = document.querySelector('textarea');
                if (!ta) return false;
                ta.focus();
                return true;
            })()
            """)
            print(f"[DEBUG] Focus textarea: {focus_ok}")
            await asyncio.sleep(0.5)

            sample_text = (
                "【声学极客】SoundPro X1 与 SoundPro X1-Pro 旗舰对比专场\n"
                "标准版 SoundPro X1 配备 42dB 深度降噪\n"
                "旗舰版 SoundPro X1-Pro 配备 48dB 深度降噪与空间音频\n"
                "另有发烧友专属 SoundPro Max 可供选择\n"
                "加入购物车\n"
                "立即购买\n"
                "联系客户电话：13800138000"
            )
            # 使用原生 CDP 键盘输入
            await send_cdp(ws, "Input.insertText", {"text": sample_text})
            await asyncio.sleep(1.0)

            # 点击“清洗文本并抽取身份”
            print("[ACTION] Clicking '清洗文本并抽取身份' button...")
            await click_element(ws, 'button[data-testid="stBaseButton-secondary"]', "清洗文本并抽取身份")
            await asyncio.sleep(4.0)

            # -------------------------------------------------------------
            # 截图 2: 触发多候选识别、单选确认卡片及拦截核验锁定状态
            # -------------------------------------------------------------
            r2 = await send_cdp(ws, "Page.captureScreenshot", {"format": "png"})
            p2 = SCREENSHOTS_DIR / "stage4_candidates_confirmation.png"
            p2.write_bytes(base64.b64decode(r2["result"]["data"]))
            print(f"[SUCCESS] Saved screenshot 2: {p2} ({p2.stat().st_size} bytes)")

            # -------------------------------------------------------------
            # 点击“确认选定此型号”
            # -------------------------------------------------------------
            print("[ACTION] Clicking '确认选定此型号' button...")
            await click_element(ws, 'button[data-testid="stBaseButton-primary"]', "确认选定此型号")
            await asyncio.sleep(4.0)

            # -------------------------------------------------------------
            # 截图 3: 确认选定型号后身份指标就绪，核验按钮已解锁状态
            # -------------------------------------------------------------
            r3 = await send_cdp(ws, "Page.captureScreenshot", {"format": "png"})
            p3 = SCREENSHOTS_DIR / "stage4_identity_confirmed.png"
            p3.write_bytes(base64.b64decode(r3["result"]["data"]))
            print(f"[SUCCESS] Saved screenshot 3: {p3} ({p3.stat().st_size} bytes)")

            return True

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    asyncio.run(capture_stage4())
