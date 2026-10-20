"""采集改版后全新白色专业 UI 的 5 大核心状态页面截图
保存至 screenshots/white_ui_redesign/ 目录:
1. after_homepage.png (白色首页)
2. after_byok_settings.png (展开的白色BYOK设置面板)
3. after_screenshot_input.png (截图上传与本地OCR区)
4. after_analysis_progress.png (白色步进指示器)
5. after_results_dashboard.png (完整核验结果看板全屏长图)
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

WORKSPACE_ROOT = Path(r"D:\ClaimCheck_Pro").resolve()
OUT_DIR = WORKSPACE_ROOT / "screenshots" / "white_ui_redesign"
OUT_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR = WORKSPACE_ROOT / ".cache" / "edge_profile_white_after"
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


async def capture_all_after():
    cmd = [
        EDGE_PATH,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--no-first-run",
        "--no-default-browser-check",
        f"--user-data-dir={CACHE_DIR}",
        "--remote-debugging-port=9245",
        "--window-size=1280,2400",
        "http://127.0.0.1:8501",
    ]
    proc = subprocess.Popen(cmd)
    try:
        ws_url = None
        for _ in range(15):
            time.sleep(1)
            try:
                res = requests.get("http://127.0.0.1:9245/json", timeout=2).json()
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
            raise RuntimeError("无法连接到 Edge CDP 端口 9245")

        async with websockets.connect(ws_url, max_size=25 * 1024 * 1024) as ws:
            await send_cdp(ws, "Page.enable")
            await send_cdp(ws, "Runtime.enable")

            # 等待 Streamlit 页面就绪
            print("[WAIT] 等待页面加载完成...")
            for _ in range(20):
                has_cta = await eval_js(ws, "document.body.innerText.includes('开始核验分析')")
                if has_cta:
                    break
                await asyncio.sleep(0.5)
            await asyncio.sleep(2.0)

            # -----------------------------------------------------------------
            # 1. 白色首页截图 after_homepage.png
            # -----------------------------------------------------------------
            print("[CAPTURE] 1. 截取白色首页 after_homepage.png...")
            shot1 = await send_cdp(ws, "Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
            p1 = OUT_DIR / "after_homepage.png"
            p1.write_bytes(base64.b64decode(shot1["result"]["data"]))
            print(f"[SAVED] {p1} ({p1.stat().st_size / 1024:.1f} KB)")

            # -----------------------------------------------------------------
            # 2. BYOK 设置截图 after_byok_settings.png
            # -----------------------------------------------------------------
            print("[ACTION] 展开服务模式设置并在内部切换为 BYOK...")
            await eval_js(ws, """
            (() => {
                const s = Array.from(document.querySelectorAll('summary')).find(el => el.innerText.includes('服务模式'));
                if (s) s.click();
            })()
            """)
            await asyncio.sleep(1.5)

            await eval_js(ws, """
            (() => {
                const labels = Array.from(document.querySelectorAll('label'));
                const byok = labels.find(l => l.innerText.includes('BYOK'));
                if (byok) byok.click();
            })()
            """)
            await asyncio.sleep(2.0)

            # 点击测试连接按钮
            await eval_js(ws, """
            (() => {
                const btns = Array.from(document.querySelectorAll('button'));
                const btn = btns.find(b => b.innerText.includes('测试连接'));
                if (btn) btn.click();
            })()
            """)
            await asyncio.sleep(2.0)

            shot2 = await send_cdp(ws, "Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
            p2 = OUT_DIR / "after_byok_settings.png"
            p2.write_bytes(base64.b64decode(shot2["result"]["data"]))
            print(f"[SAVED] {p2} ({p2.stat().st_size / 1024:.1f} KB)")

            # 切回 Mock 模式并关闭设置 expander
            await eval_js(ws, """
            (() => {
                const labels = Array.from(document.querySelectorAll('label'));
                const mock = labels.find(l => l.innerText.includes('Mock'));
                if (mock) mock.click();
            })()
            """)
            await asyncio.sleep(1.2)
            await eval_js(ws, """
            (() => {
                const s = Array.from(document.querySelectorAll('summary')).find(el => el.innerText.includes('服务模式'));
                if (s) s.click();
            })()
            """)
            await asyncio.sleep(1.0)

            # -----------------------------------------------------------------
            # 3. 截图上传 after_screenshot_input.png
            # -----------------------------------------------------------------
            print("[ACTION] 切换到【商品宣传截图】Tab...")
            await eval_js(ws, """
            (() => {
                const tabs = Array.from(document.querySelectorAll('[data-testid="stTab"]'));
                const imgTab = tabs.find(t => t.innerText.includes('截图'));
                if (imgTab) imgTab.click();
            })()
            """)
            await asyncio.sleep(1.5)

            shot3 = await send_cdp(ws, "Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
            p3 = OUT_DIR / "after_screenshot_input.png"
            p3.write_bytes(base64.b64decode(shot3["result"]["data"]))
            print(f"[SAVED] {p3} ({p3.stat().st_size / 1024:.1f} KB)")

            # 切回链接 Tab
            await eval_js(ws, """
            (() => {
                const tabs = Array.from(document.querySelectorAll('[data-testid="stTab"]'));
                const linkTab = tabs.find(t => t.innerText.includes('链接'));
                if (linkTab) linkTab.click();
            })()
            """)
            await asyncio.sleep(1.0)

            # -----------------------------------------------------------------
            # 4 & 5. 点击【开始核验分析】并截取分析进度与完整结果
            # -----------------------------------------------------------------
            print("[ACTION] 点击主按钮【开始核验分析】...")
            await eval_js(ws, """
            (() => {
                const btns = Array.from(document.querySelectorAll('button'));
                const startBtn = btns.find(b => b.innerText.includes('开始核验分析'));
                if (startBtn) startBtn.click();
            })()
            """)
            await asyncio.sleep(3.5)

            # 等待结果看板渲染
            for _ in range(15):
                has_res = await eval_js(ws, "document.body.innerText.includes('核验结果看板')")
                if has_res:
                    break
                await asyncio.sleep(0.5)
            await asyncio.sleep(1.5)

            # 4. 步进指示器截图 after_analysis_progress.png
            print("[CAPTURE] 4. 截取分析进度 after_analysis_progress.png...")
            await eval_js(ws, """
            (() => {
                const el = Array.from(document.querySelectorAll('h3, div')).find(e => e.innerText && e.innerText.includes('AI 核验执行进度'));
                if (el) el.scrollIntoView({behavior: 'instant', block: 'start'});
            })()
            """)
            await asyncio.sleep(1.0)
            shot4 = await send_cdp(ws, "Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
            p4 = OUT_DIR / "after_analysis_progress.png"
            p4.write_bytes(base64.b64decode(shot4["result"]["data"]))
            print(f"[SAVED] {p4} ({p4.stat().st_size / 1024:.1f} KB)")

            # 5. 完整核验结果全屏长图 after_results_dashboard.png
            print("[CAPTURE] 5. 截取核验结果全屏长图 after_results_dashboard.png...")
            shot5 = await send_cdp(ws, "Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
            p5 = OUT_DIR / "after_results_dashboard.png"
            p5.write_bytes(base64.b64decode(shot5["result"]["data"]))
            print(f"[SAVED] {p5} ({p5.stat().st_size / 1024:.1f} KB)")

            print("[SUCCESS] 全部 5 张改版后白色页面截图采集完成！")

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    asyncio.run(capture_all_after())
