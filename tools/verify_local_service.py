import asyncio
import json
import os
import subprocess
import sys
import time
import urllib.request
import websockets

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
CACHE_DIR = r"D:\ClaimCheck_Pro\.cache\test_verify_edge"

async def inspect_homepage():
    # 1. First verify HTTP response directly
    resp = urllib.request.urlopen("http://127.0.0.1:8501")
    assert resp.getcode() == 200, f"HTTP status code was {resp.getcode()}"
    print("✅ HTTP 200 OK from http://127.0.0.1:8501")

    # 2. Launch headless Edge with CDP
    cdp_port = 9399
    cmd = [
        EDGE_PATH,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--no-first-run",
        "--no-default-browser-check",
        f"--user-data-dir={CACHE_DIR}",
        f"--remote-debugging-port={cdp_port}",
        "--window-size=1280,1200",
        "http://127.0.0.1:8501",
    ]
    proc = subprocess.Popen(cmd)
    print(f"[INIT] Edge started on port {cdp_port}...")

    try:
        ws_url = None
        for _ in range(15):
            time.sleep(1)
            try:
                res = urllib.request.urlopen(f"http://127.0.0.1:{cdp_port}/json").read()
                pages = json.loads(res)
                if pages:
                    for target in pages:
                        if "8501" in target.get("url", ""):
                            ws_url = target.get("webSocketDebuggerUrl")
                            break
                    if ws_url:
                        break
            except Exception:
                pass

        assert ws_url, "Failed to connect to Edge CDP endpoint for 8501"
        print("[CONNECTED] CDP connected to target 8501:", ws_url)

        async with websockets.connect(ws_url, max_size=20 * 1024 * 1024) as ws:
            msg_id = 0
            async def send_cdp(method, params=None):
                nonlocal msg_id
                msg_id += 1
                payload = {"id": msg_id, "method": method, "params": params or {}}
                await ws.send(json.dumps(payload))
                while True:
                    raw = await ws.recv()
                    r = json.loads(raw)
                    if r.get("id") == msg_id:
                        return r

            async def eval_js(expr):
                r = await send_cdp("Runtime.evaluate", {"expression": expr, "returnByValue": True})
                return r.get("result", {}).get("result", {}).get("value")

            await send_cdp("Page.enable")
            await send_cdp("Runtime.enable")

            # 等待 Streamlit 页面渲染完成
            print("[WAIT] Waiting for Streamlit page to render...")
            for _ in range(25):
                await asyncio.sleep(1.0)
                body = await eval_js("document.body.innerText")
                if body and "ClaimCheck Pro" in body and "第一阶段" in body:
                    break

            body_text = await eval_js("document.body.innerText")
            print("\n=== DOM 页面内容校验 ===")
            
            # 1. 页面正常加载
            assert "ClaimCheck Pro" in body_text, "未检测到系统标题 ClaimCheck Pro"
            print("✅ 1. 页面正常加载，主标题正常呈现")

            # 2. 没有 Python 异常
            has_exception = await eval_js("Boolean(document.querySelector('.stException') || document.querySelector('[data-testid=\"stException\"]'))")
            assert not has_exception, "检测到 Python 异常报错！"
            assert "Traceback" not in body_text, "检测到未捕获的 Traceback"
            print("✅ 2. 无任何 Python 异常或 Traceback")

            # 3. Mock 模式可打开与显示
            assert "Mock" in body_text, "未检测到 Mock 模式标识"
            print("✅ 3. Mock 模式状态胶囊正常加载")

            # 4. BYOK 设置可展开
            # 点击展开设置抽屉
            click_res = await eval_js("""
                (() => {
                    const el = Array.from(document.querySelectorAll('summary')).find(s => s.innerText.includes('服务模式与端点设置'));
                    if (el) { el.click(); return true; }
                    return false;
                })()
            """)
            print(f"[ACTION] 点击展开服务设置抽屉 -> {click_res}")
            await asyncio.sleep(1.5)
            drawer_text = await eval_js("document.body.innerText")
            assert "用户自带 API" in drawer_text or "BYOK" in drawer_text, "未能成功展开或未找到 BYOK 设置"
            print("✅ 4. 服务模式与端点设置（BYOK/Local）可正常展开并交互")

            # 5. 链接、文本、截图三个入口存在
            assert "商品链接" in body_text, "未找到【商品链接】输入入口"
            assert "商品详情文本" in body_text, "未找到【商品详情文本】输入入口"
            assert "商品宣传截图" in body_text, "未找到【商品宣传截图】输入入口"
            print("✅ 5. 链接、文本、截图三大输入方式完整就绪")

            # 截图保存为证据
            out_img = r"D:\ClaimCheck_Pro\screenshots\service_recovery_verification.png"
            os.makedirs(os.path.dirname(out_img), exist_ok=True)
            shot_res = await send_cdp("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
            import base64
            img_data = shot_res.get("result", {}).get("data")
            if img_data:
                with open(out_img, "wb") as f:
                    f.write(base64.b64decode(img_data))
                print(f"📸 验收长图已保存: {out_img}")

            print("\n🎉 本地页面健康检查与全量功能诊断全部通过！")

    finally:
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            proc.kill()

if __name__ == "__main__":
    asyncio.run(inspect_homepage())
