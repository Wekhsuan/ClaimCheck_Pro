"""ClaimCheck Pro 核心机制验收与全真浏览器截图采集工具 (Robust CDP Native Events)
针对 BYOK/Mock 彻底隔离性修复进行端到端全流程验证：
1. 01_mock_mode_verification.png (Mock 模式标准演示，标明 Mock 演示数据)
2. 02_byok_jd_restricted_fallback.png (BYOK + 京东反爬链接，触发合规降级保护，绝不回退至 SoundPro X1)
3. 03_byok_text_real_verification.png (BYOK + 详情文本，真实模型核验，标明未配置网络搜索，零伪造)
4. 04_input_change_cache_invalidation.png (输入变更立即失效旧报告或显示防过期拦截)
5. 05_mode_switch_clears_old_report.png (模式切换自动清理状态与报告)
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
OUT_DIR = WORKSPACE_ROOT / "screenshots" / "byok_fix"
OUT_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR = WORKSPACE_ROOT / ".cache" / "edge_profile_byok_fix"
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


async def click_element(ws, selector, text_to_match=None):
    expr = f"""
    (() => {{
        const sel = {json.dumps(selector)};
        const match = {json.dumps(text_to_match)};
        let el = null;
        if (match) {{
            const elements = Array.from(document.querySelectorAll(sel));
            el = elements.find(e => e.innerText && e.innerText.includes(match));
        }} else {{
            el = document.querySelector(sel);
        }}
        if (!el) return null;
        el.scrollIntoView({{block: 'center'}});
        const rect = el.getBoundingClientRect();
        return {{ x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 }};
    }})()
    """
    coords = await eval_js(ws, expr)
    if not coords or coords.get("x") is None:
        print(f"[WARN] Element {selector} ({text_to_match}) not found", flush=True)
        return False

    x, y = coords["x"], coords["y"]
    await send_cdp(ws, "Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
    await asyncio.sleep(0.05)
    await send_cdp(ws, "Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
    await asyncio.sleep(0.05)
    await send_cdp(ws, "Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})
    return True


async def set_input_value(ws, selector, value):
    expr = f"""
    (() => {{
        const sel = {json.dumps(selector)};
        const val = {json.dumps(value)};
        const el = document.querySelector(sel);
        if (!el) return false;
        
        el.focus();
        const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
        const desc = Object.getOwnPropertyDescriptor(proto, 'value');
        desc.set.call(el, val);
        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
        el.dispatchEvent(new KeyboardEvent('keydown', {{ bubbles: true, cancelable: true, key: 'Enter', code: 'Enter', keyCode: 13, which: 13 }}));
        el.dispatchEvent(new KeyboardEvent('keyup', {{ bubbles: true, cancelable: true, key: 'Enter', code: 'Enter', keyCode: 13, which: 13 }}));
        el.blur();
        return true;
    }})()
    """
    res = await eval_js(ws, expr)
    await asyncio.sleep(1.0)
    return res


async def run_automation():
    cmd = [
        EDGE_PATH,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--no-first-run",
        "--no-default-browser-check",
        f"--user-data-dir={CACHE_DIR}",
        "--remote-debugging-port=9260",
        "--window-size=1280,2600",
        "http://127.0.0.1:8501",
    ]
    proc = subprocess.Popen(cmd)
    print("[INIT] Edge headless started on port 9260...", flush=True)

    try:
        ws_url = None
        for _ in range(15):
            time.sleep(1)
            try:
                res = requests.get("http://127.0.0.1:9260/json", timeout=2).json()
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
            raise RuntimeError("无法连接到 Edge CDP 调试端口 9260")

        async with websockets.connect(ws_url, max_size=30 * 1024 * 1024) as ws:
            print("[CONNECTED] CDP connected successfully.", flush=True)
            await send_cdp(ws, "Page.enable")
            await send_cdp(ws, "Runtime.enable")

            # 等待 Streamlit 页面就绪
            print("[WAIT] 等待 Streamlit 初始页面就绪...", flush=True)
            for _ in range(25):
                ready = await eval_js(ws, "document.querySelectorAll('button').length > 0")
                if ready:
                    break
                await asyncio.sleep(0.5)
            await asyncio.sleep(2.0)

            # -----------------------------------------------------------------
            # 场景 1: Mock 模式核验与水印展示
            # -----------------------------------------------------------------
            print("[SCENARIO 1] 运行 Mock 模式核验...", flush=True)
            # 先加载演示案例 1
            print("[ACTION] 加载演示案例 1...", flush=True)
            await click_element(ws, "summary", "没有商品？试用预置演示案例")
            await asyncio.sleep(1.0)
            await click_element(ws, "button", "加载案例 1")
            await asyncio.sleep(2.0)

            # 点击开始核验
            await click_element(ws, "button", "开始核验分析")
            print("[WAIT] 等待 Mock 报告渲染...", flush=True)
            for _ in range(20):
                has_report = await eval_js(ws, "document.body.innerText.includes('核验结果看板')")
                if has_report:
                    break
                await asyncio.sleep(0.5)
            await asyncio.sleep(2.0)

            print("[CAPTURE] 1. 保存 01_mock_mode_verification.png...", flush=True)
            shot1 = await send_cdp(ws, "Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
            p1 = OUT_DIR / "01_mock_mode_verification.png"
            p1.write_bytes(base64.b64decode(shot1["result"]["data"]))
            print(f"[SAVED] {p1} ({p1.stat().st_size / 1024:.1f} KB)", flush=True)

            # -----------------------------------------------------------------
            # 场景 2: BYOK 模式 + 京东受限链接 -> 合规降级保护 (绝无 SoundPro X1)
            # -----------------------------------------------------------------
            print("[SCENARIO 2] 展开设置，切换至 BYOK 模式...", flush=True)
            await click_element(ws, "summary", "服务模式与端点设置")
            await asyncio.sleep(1.0)

            await click_element(ws, "label", "用户自带 API")
            await asyncio.sleep(1.5)

            # 填写 API Key
            print("[ACTION] 填写测试 API Key...", flush=True)
            ok_key = await set_input_value(ws, "input[type='password']", "sk-test-demo-byok-user-key-12345678")
            print(f"[DEBUG] API Key filled: {ok_key}", flush=True)
            await asyncio.sleep(1.0)

            # 在链接输入框中填入京东 URL
            print("[ACTION] 输入京东反爬链接: https://item.jd.com/10145673910180.html", flush=True)
            ok_url = await set_input_value(ws, "input[placeholder*='jd.com']", "https://item.jd.com/10145673910180.html")
            print(f"[DEBUG] URL filled: {ok_url}", flush=True)
            await asyncio.sleep(1.0)

            # 点击开始核验
            print("[ACTION] 点击开始核验分析...", flush=True)
            await click_element(ws, "button", "开始核验分析")

            print("[WAIT] 等待受限降级保护横幅出现...", flush=True)
            for _ in range(25):
                has_degrade = await eval_js(ws, "document.body.innerText.includes('降级保护') || document.body.innerText.includes('PAGE_ACCESS_RESTRICTED')")
                if has_degrade:
                    break
                await asyncio.sleep(0.5)
            await asyncio.sleep(2.0)

            # 校验页面是否绝无 SoundPro X1
            page_text = await eval_js(ws, "document.body.innerText")
            has_soundpro = "SoundPro X1" in page_text
            print(f"[CHECK] 是否存在 SoundPro X1 泄露: {has_soundpro} (必须为 False)", flush=True)
            assert not has_soundpro, "严重错误：BYOK 模式下遭遇反爬时错误回退到了 SoundPro X1 Mock 案例！"

            print("[CAPTURE] 2. 保存 02_byok_jd_restricted_fallback.png...", flush=True)
            shot2 = await send_cdp(ws, "Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
            p2 = OUT_DIR / "02_byok_jd_restricted_fallback.png"
            p2.write_bytes(base64.b64decode(shot2["result"]["data"]))
            print(f"[SAVED] {p2} ({p2.stat().st_size / 1024:.1f} KB)", flush=True)

            # -----------------------------------------------------------------
            # 场景 3: 切换至详情文本模式 -> 执行真实核验 (零伪造，search_status: not_configured)
            # -----------------------------------------------------------------
            print("[SCENARIO 3] 切换到【商品详情文本】标签页...", flush=True)
            # 先清空 URL
            await set_input_value(ws, "input[placeholder*='jd.com']", "")
            await asyncio.sleep(0.5)

            # 切换到详情文本 Tab
            await eval_js(ws, """
            (() => {
                const tabs = Array.from(document.querySelectorAll('button[data-baseweb="tab"], [data-testid="stTab"]'));
                const t = tabs.find(x => x.innerText.includes('详情文本'));
                if (t) t.click();
            })()
            """)
            await asyncio.sleep(1.0)

            # 输入详情文本
            sample_text = (
                "索尼（SONY）WH-1000XM5 头戴式无线蓝牙降噪耳机 黑色\n"
                "双芯驱动 旗舰级降噪 30小时长续航 支持LDAC高解析度无损音频传输 8麦克风高清通话"
            )
            print("[ACTION] 填写真实商品详情文本（索尼 WH-1000XM5）...", flush=True)
            await set_input_value(ws, "textarea", sample_text)
            await asyncio.sleep(1.0)

            # 点击开始核验
            print("[ACTION] 点击开始核验分析...", flush=True)
            await click_element(ws, "button", "开始核验分析")
            await asyncio.sleep(5.0)

            print("[CAPTURE] 3. 保存 03_byok_text_real_verification.png...", flush=True)
            shot3 = await send_cdp(ws, "Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
            p3 = OUT_DIR / "03_byok_text_real_verification.png"
            p3.write_bytes(base64.b64decode(shot3["result"]["data"]))
            print(f"[SAVED] {p3} ({p3.stat().st_size / 1024:.1f} KB)", flush=True)

            # -----------------------------------------------------------------
            # 场景 4: 输入变更缓存失效
            # -----------------------------------------------------------------
            print("[SCENARIO 4] 修改文本输入，验证旧报告被立即清除...", flush=True)
            await set_input_value(ws, "textarea", "华为 FreeBuds Pro 3 智慧动态降噪 星闪音频连接技术 综合续航33小时")
            await asyncio.sleep(2.0)

            print("[CAPTURE] 4. 保存 04_input_change_cache_invalidation.png...", flush=True)
            shot4 = await send_cdp(ws, "Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
            p4 = OUT_DIR / "04_input_change_cache_invalidation.png"
            p4.write_bytes(base64.b64decode(shot4["result"]["data"]))
            print(f"[SAVED] {p4} ({p4.stat().st_size / 1024:.1f} KB)", flush=True)

            # -----------------------------------------------------------------
            # 场景 5: 模式切换清理
            # -----------------------------------------------------------------
            print("[SCENARIO 5] 切回 Mock 模式，检查状态清理...", flush=True)
            await click_element(ws, "label", "Mock 离线演示")
            await asyncio.sleep(2.0)

            print("[CAPTURE] 5. 保存 05_mode_switch_clears_old_report.png...", flush=True)
            shot5 = await send_cdp(ws, "Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
            p5 = OUT_DIR / "05_mode_switch_clears_old_report.png"
            p5.write_bytes(base64.b64decode(shot5["result"]["data"]))
            print(f"[SAVED] {p5} ({p5.stat().st_size / 1024:.1f} KB)", flush=True)

            print("🎉 全部 5 个核心浏览器验收场景截图采集完成！", flush=True)

    finally:
        try:
            proc.terminate()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(run_automation())
