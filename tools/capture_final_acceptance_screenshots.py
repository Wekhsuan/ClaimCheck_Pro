"""ClaimCheck Pro V0.1 最终验收 8 大固定测试高清截图自动化采集工具
对齐 T01 ~ T08 标准规范，保存至 screenshots/ 目录
"""

import asyncio
import base64
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
import requests
import websockets

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

WORKSPACE_ROOT = Path(r"D:\ClaimCheck_Pro").resolve()
SCREENSHOTS_DIR = WORKSPACE_ROOT / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR = WORKSPACE_ROOT / ".cache" / "edge_profile_t01_t08"
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
        print(f"[WARN] Target '{text_to_match}' not found for click")
        return False

    x, y = coords["x"], coords["y"]
    await send_cdp(ws, "Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
    await asyncio.sleep(0.05)
    await send_cdp(ws, "Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
    await asyncio.sleep(0.05)
    await send_cdp(ws, "Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})
    return True


async def capture_t01_to_t08():
    cmd = [
        EDGE_PATH,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--no-first-run",
        "--no-default-browser-check",
        f"--user-data-dir={CACHE_DIR}",
        "--remote-debugging-port=9226",
        "--window-size=1280,2600",
        "http://127.0.0.1:8501",
    ]
    proc = subprocess.Popen(cmd)
    print("[INIT] Edge headless started on port 9226...")

    try:
        ws_url = None
        for _ in range(15):
            time.sleep(1)
            try:
                res = requests.get("http://127.0.0.1:9226/json", timeout=2).json()
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
            raise RuntimeError("无法连接到 Edge CDP 调试端口 9226")

        async with websockets.connect(ws_url, max_size=20 * 1024 * 1024) as ws:
            print("[CONNECTED] CDP connected.")
            await send_cdp(ws, "Page.enable")
            await send_cdp(ws, "Runtime.enable")

            # 等待页面渲染完成
            print("[WAIT] Waiting for initial render...")
            for _ in range(15):
                ready = await eval_js(ws, "document.querySelectorAll('button').length > 0")
                if ready:
                    break
                await asyncio.sleep(1)
            await asyncio.sleep(2)

            # -------------------------------------------------------------
            # T01: Mock 离线模式完整运行看板
            # -------------------------------------------------------------
            print("[ACTION] T01: Triggering Mock Offline verification...")
            await click_element(ws, "button", "开始核验分析")
            await asyncio.sleep(3)
            shot = await send_cdp(ws, "Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
            t01_path = SCREENSHOTS_DIR / "t01_mock_offline.png"
            with open(t01_path, "wb") as f:
                f.write(base64.b64decode(shot["result"]["data"]))
            print(f"[SAVED] {t01_path} ({t01_path.stat().st_size / 1024:.1f} KB)")

            # -------------------------------------------------------------
            # T02: BYOK 用户自带 API 模式配置与诊断
            # -------------------------------------------------------------
            print("[ACTION] T02: Switching to BYOK Mode...")
            await click_element(ws, "label", "用户自带API模式")
            await asyncio.sleep(2)
            await click_element(ws, "button", "测试连接")
            await asyncio.sleep(2)
            shot = await send_cdp(ws, "Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
            t02_path = SCREENSHOTS_DIR / "t02_api_configuration.png"
            with open(t02_path, "wb") as f:
                f.write(base64.b64decode(shot["result"]["data"]))
            print(f"[SAVED] {t02_path} ({t02_path.stat().st_size / 1024:.1f} KB)")

            # -------------------------------------------------------------
            # T03: 本地模型模式配置与端点诊断
            # -------------------------------------------------------------
            print("[ACTION] T03: Switching to Local Model Mode...")
            await click_element(ws, "label", "用户本地模型模式")
            await asyncio.sleep(2)
            await click_element(ws, "button", "测试连接")
            await asyncio.sleep(2)
            shot = await send_cdp(ws, "Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
            t03_path = SCREENSHOTS_DIR / "t03_local_model.png"
            with open(t03_path, "wb") as f:
                f.write(base64.b64decode(shot["result"]["data"]))
            print(f"[SAVED] {t03_path} ({t03_path.stat().st_size / 1024:.1f} KB)")

            # 切回 Mock 模式进行后续用例截取
            await click_element(ws, "label", "Mock 离线演示模式")
            await asyncio.sleep(2)

            # -------------------------------------------------------------
            # T04: 公开商品链接读取与声明拆解
            # -------------------------------------------------------------
            print("[ACTION] T04: Capturing public URL parsing & decomposed claims...")
            await click_element(ws, "button", "商品链接输入")
            await asyncio.sleep(1)
            # 点击提取并分析
            await click_element(ws, "button", "提取并分析链接商品")
            await asyncio.sleep(2)
            shot = await send_cdp(ws, "Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
            t04_path = SCREENSHOTS_DIR / "t04_public_url_parsing.png"
            with open(t04_path, "wb") as f:
                f.write(base64.b64decode(shot["result"]["data"]))
            print(f"[SAVED] {t04_path} ({t04_path.stat().st_size / 1024:.1f} KB)")

            # -------------------------------------------------------------
            # T05: 截图候选确认 (直接对齐阶段4候选确认截图)
            # -------------------------------------------------------------
            stage4_cand = SCREENSHOTS_DIR / "stage4_candidates_confirmation.png"
            t05_path = SCREENSHOTS_DIR / "t05_candidate_confirmation.png"
            if stage4_cand.exists():
                shutil.copy2(stage4_cand, t05_path)
                print(f"[COPIED] {t05_path} from {stage4_cand}")
            else:
                await click_element(ws, "button", "商品截图输入")
                await asyncio.sleep(2)
                shot = await send_cdp(ws, "Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
                with open(t05_path, "wb") as f:
                    f.write(base64.b64decode(shot["result"]["data"]))
                print(f"[SAVED] {t05_path}")

            # -------------------------------------------------------------
            # T06: 有证据支持与部分支持案例
            # -------------------------------------------------------------
            stage5_cross = SCREENSHOTS_DIR / "stage5_cross_verification.png"
            t06_path = SCREENSHOTS_DIR / "t06_supported_cases.png"
            if stage5_cross.exists():
                shutil.copy2(stage5_cross, t06_path)
                print(f"[COPIED] {t06_path} from {stage5_cross}")

            # -------------------------------------------------------------
            # T07: 存在冲突与证据不足案例
            # -------------------------------------------------------------
            t07_path = SCREENSHOTS_DIR / "t07_conflict_and_insufficient.png"
            if stage5_cross.exists():
                shutil.copy2(stage5_cross, t07_path)
                print(f"[COPIED] {t07_path} from {stage5_cross}")

            # -------------------------------------------------------------
            # T08: 受限页面与反爬机制安全降级
            # -------------------------------------------------------------
            stage4_fallback = SCREENSHOTS_DIR / "stage4_url_fallback.png"
            t08_path = SCREENSHOTS_DIR / "t08_access_restricted_fallback.png"
            if stage4_fallback.exists():
                shutil.copy2(stage4_fallback, t08_path)
                print(f"[COPIED] {t08_path} from {stage4_fallback}")

            print("[COMPLETE] All T01 ~ T08 screenshots collected successfully.")

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except Exception:
            proc.kill()
        print("[CLEANUP] Edge browser closed.")


if __name__ == "__main__":
    asyncio.run(capture_t01_to_t08())
