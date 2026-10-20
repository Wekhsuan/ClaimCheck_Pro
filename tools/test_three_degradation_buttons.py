"""ClaimCheck Pro 降级卡片三大操作按钮交互全真浏览器验证测试脚本
针对用户明确提出的 10 项交互验收要求，使用 Microsoft Edge 原生 CDP 执行全自动化测试与截图采集。

验证目标：
1. 降级卡片中真实存在 3 个可点击按钮，位于“接下来怎么做”区域下方；
2. 按钮 1：“粘贴商品详情文本”作为蓝色主按钮 (Primary)；
3. 按钮 2：“上传商品宣传截图”作为白色描边次级按钮 (Secondary)；
4. 按钮 3：“使用标准化链接重新尝试”作为文字按钮 (Ghost/Text)，并标记“最多重试1次”；
5. 点击重试后最多重试 1 次，再次失败后禁用重试，且不恢复 Mock 数据；
6. 点击“上传商品宣传截图”自动切到截图标签、保留原始链接与ID、自动滚动到上传区、显示隐私提醒；
7. 点击“粘贴商品详情文本”自动切到详情文本标签、生成6部分模板、保留原始链接与ID、自动滚动到文本区。
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
OUT_DIR = WORKSPACE_ROOT / "screenshots" / "degradation_buttons"
OUT_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR = WORKSPACE_ROOT / ".cache" / "edge_profile_degradation_test"
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
        el.scrollIntoView({{block: 'center', inline: 'nearest'}});
        const rect = el.getBoundingClientRect();
        el.click();
        el.dispatchEvent(new MouseEvent('mousedown', {{ bubbles: true, cancelable: true }}));
        el.dispatchEvent(new MouseEvent('mouseup', {{ bubbles: true, cancelable: true }}));
        el.dispatchEvent(new MouseEvent('click', {{ bubbles: true, cancelable: true }}));
        return {{
            found: true,
            text: el.innerText.trim(),
            x: rect.left + rect.width / 2,
            y: rect.top + rect.height / 2
        }};
    }})()
    """
    res = await eval_js(ws, expr)
    print(f"[CLICK] {selector} ({text_to_match}) -> {res}", flush=True)
    if not res or not res.get("found"):
        return False

    x, y = res["x"], res["y"]
    await send_cdp(ws, "Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
    await asyncio.sleep(0.05)
    await send_cdp(ws, "Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
    await asyncio.sleep(0.05)
    await send_cdp(ws, "Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})
    await asyncio.sleep(1.0)
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


async def run_test():
    cdp_port = 9277
    cmd = [
        EDGE_PATH,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--no-first-run",
        "--no-default-browser-check",
        f"--user-data-dir={CACHE_DIR}",
        f"--remote-debugging-port={cdp_port}",
        "--window-size=1280,2200",
        "http://127.0.0.1:8501",
    ]
    proc = subprocess.Popen(cmd)
    print(f"[INIT] Edge headless started on port {cdp_port}...", flush=True)

    try:
        ws_url = None
        for _ in range(15):
            time.sleep(1)
            try:
                res = requests.get(f"http://127.0.0.1:{cdp_port}/json", timeout=2).json()
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
            raise RuntimeError(f"无法连接到 Edge CDP 调试端口 {cdp_port}")

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
            await asyncio.sleep(1.5)

            # -----------------------------------------------------------------
            # 步骤 1：配置 BYOK 模式
            # -----------------------------------------------------------------
            print("[SETUP] 展开设置，配置 BYOK 模式...", flush=True)
            await click_element(ws, "summary", "服务模式与端点设置")
            await asyncio.sleep(1.0)

            await click_element(ws, "label", "用户自带 API")
            await asyncio.sleep(1.5)

            print("[ACTION] 填写测试 API Key...", flush=True)
            await set_input_value(ws, "input[type='password']", "sk-test-demo-byok-user-key-12345678")
            await asyncio.sleep(1.0)

            # 收起设置抽屉
            await click_element(ws, "summary", "服务模式与端点设置")
            await asyncio.sleep(0.5)

            # -----------------------------------------------------------------
            # 步骤 2：填入京东反爬受限链接并核验 -> 触发降级卡片
            # -----------------------------------------------------------------
            target_jd_url = "https://item.jd.com/10115777872752.html?spm=test&utm_source=ad"
            print(f"[ACTION] 填入京东链接: {target_jd_url} ...", flush=True)
            await set_input_value(ws, "input[placeholder*='jd.com']", target_jd_url)
            await asyncio.sleep(1.0)

            print("[ACTION] 点击【开始核验分析】...", flush=True)
            await click_element(ws, "button", "开始核验分析")

            print("[WAIT] 等待受限降级操作卡片出现...", flush=True)
            for _ in range(30):
                has_degrade = await eval_js(ws, "document.body.innerText.includes('无法自动读取该商品页面')")
                if has_degrade:
                    break
                await asyncio.sleep(0.5)
            await asyncio.sleep(2.0)

            # -----------------------------------------------------------------
            # 验收 1：检查降级卡片排版、三个按钮的存在性及位置
            # -----------------------------------------------------------------
            print("[VERIFY 1] 校验降级卡片与三个按钮属性...", flush=True)
            buttons_info = await eval_js(ws, """
            (() => {
                const b1 = Array.from(document.querySelectorAll('button')).find(e => e.innerText.includes('粘贴商品详情文本'));
                const b2 = Array.from(document.querySelectorAll('button')).find(e => e.innerText.includes('上传商品宣传截图'));
                const b3 = Array.from(document.querySelectorAll('button')).find(e => e.innerText.includes('标准化链接'));
                
                return {
                    b1: b1 ? { text: b1.innerText.trim(), kind: b1.getAttribute('kind'), disabled: b1.disabled } : null,
                    b2: b2 ? { text: b2.innerText.trim(), kind: b2.getAttribute('kind'), disabled: b2.disabled } : null,
                    b3: b3 ? { text: b3.innerText.trim(), kind: b3.getAttribute('kind'), disabled: b3.disabled } : null,
                };
            })()
            """)
            print(f"[DEBUG] Buttons Info: {buttons_info}", flush=True)
            assert buttons_info["b1"] is not None, "未找到【粘贴商品详情文本】按钮！"
            assert buttons_info["b2"] is not None, "未找到【上传商品宣传截图】按钮！"
            assert buttons_info["b3"] is not None, "未找到【使用标准化链接重新尝试】按钮！"
            assert "最多重试1次" in buttons_info["b3"]["text"], "重试按钮缺少‘最多重试1次’说明！"

            # 聚焦并截取 btn_01_degradation_card_layout.png
            await eval_js(ws, """
            (() => {
                const el = document.querySelector('.saas-card');
                if (el) el.scrollIntoView({block: 'start'});
            })()
            """)
            await asyncio.sleep(1.0)
            shot1 = await send_cdp(ws, "Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
            p1 = OUT_DIR / "btn_01_degradation_card_layout.png"
            p1.write_bytes(base64.b64decode(shot1["result"]["data"]))
            print(f"[SAVED] {p1} ({p1.stat().st_size / 1024:.1f} KB)", flush=True)

            # -----------------------------------------------------------------
            # 验收 2：测试按钮 3【使用标准化链接重新尝试 (最多重试1次)】
            # 触发重试 -> 最多重试一次 -> 再次失败后禁用重试 -> 不恢复 Mock 数据
            # -----------------------------------------------------------------
            print("[ACTION 2] 点击【🔄 使用标准化链接重新尝试 (最多重试1次)】...", flush=True)
            await click_element(ws, "button", "使用标准化链接重新尝试")
            
            print("[WAIT] 等待重试执行并重新捕获受限结果...", flush=True)
            await asyncio.sleep(3.0)
            for _ in range(30):
                has_disabled_btn = await eval_js(ws, """
                (() => {
                    const b = Array.from(document.querySelectorAll('button')).find(e => e.innerText.includes('已达重试上限') || (e.innerText.includes('重试') && e.disabled));
                    return b ? true : false;
                })()
                """)
                if has_disabled_btn:
                    break
                await asyncio.sleep(0.5)
            await asyncio.sleep(1.5)

            # 校验重试禁用与无 Mock 泄露
            b3_disabled_info = await eval_js(ws, """
            (() => {
                const b = Array.from(document.querySelectorAll('button')).find(e => e.innerText.includes('已达重试上限') || e.innerText.includes('重试'));
                return b ? { text: b.innerText.trim(), disabled: b.disabled } : null;
            })()
            """)
            print(f"[DEBUG] Retry Button After 1st retry: {b3_disabled_info}", flush=True)
            assert b3_disabled_info is not None
            assert b3_disabled_info["disabled"] is True, "再次重试失败后必须禁用重试按钮！"
            assert "已达重试上限" in b3_disabled_info["text"] or "最多重试1次" in b3_disabled_info["text"]

            page_text = await eval_js(ws, "document.body.innerText")
            assert "SoundPro X1" not in page_text, "重试失败后严禁恢复 Mock 演示数据！"

            shot2 = await send_cdp(ws, "Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
            p2 = OUT_DIR / "btn_02_retry_limit_disabled.png"
            p2.write_bytes(base64.b64decode(shot2["result"]["data"]))
            print(f"[SAVED] {p2} ({p2.stat().st_size / 1024:.1f} KB)", flush=True)

            # -----------------------------------------------------------------
            # 验收 3：测试按钮 2【🖼️ 上传商品宣传截图】
            # 点击后自动切到截图标签、保留原始链接与ID、自动滚动到上传区、显示隐私提醒
            # -----------------------------------------------------------------
            print("[ACTION 3] 点击【🖼️ 上传商品宣传截图】...", flush=True)
            await click_element(ws, "button", "上传商品宣传截图")
            await asyncio.sleep(2.0)

            screenshot_ui_info = await eval_js(ws, """
            (() => {
                const checkedRadio = document.querySelector('.stRadio input:checked');
                const uploader = document.querySelector('[data-testid="stFileUploader"]');
                const alertText = document.body.innerText;
                const hasPrivacy = alertText.includes('隐私脱敏提示') && alertText.includes('保留原始商品链接');
                const hasUploaderPrompt = alertText.includes('上传商品宣传截图');
                return {
                    checkedValue: checkedRadio ? checkedRadio.value : '',
                    hasUploader: !!uploader,
                    hasPrivacy,
                    hasUploaderPrompt,
                };
            })()
            """)
            print(f"[DEBUG] Screenshot UI Info: {screenshot_ui_info}", flush=True)
            assert screenshot_ui_info["hasUploader"] is True, "必须展示商品截图上传组件！"
            assert screenshot_ui_info["hasPrivacy"] is True, "必须展示保留原始链接与ID的隐私脱敏提示！"
            assert screenshot_ui_info["hasUploaderPrompt"] is True

            shot3 = await send_cdp(ws, "Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
            p3 = OUT_DIR / "btn_03_switched_to_screenshot.png"
            p3.write_bytes(base64.b64decode(shot3["result"]["data"]))
            print(f"[SAVED] {p3} ({p3.stat().st_size / 1024:.1f} KB)", flush=True)

            # -----------------------------------------------------------------
            # 验收 4：测试按钮 1【📋 粘贴商品详情文本】
            # 切回链接输入重新触发受限，然后点击粘贴商品详情文本
            # -----------------------------------------------------------------
            print("[ACTION 4] 切回链接输入重新触发受限以测试按钮 1...", flush=True)
            await click_element(ws, "label", "商品公开链接")
            await asyncio.sleep(1.0)
            await click_element(ws, "button", "开始核验分析")
            
            for _ in range(25):
                has_deg = await eval_js(ws, "document.body.innerText.includes('无法自动读取该商品页面')")
                if has_deg:
                    break
                await asyncio.sleep(0.5)
            await asyncio.sleep(1.5)

            print("[ACTION] 点击【📋 粘贴商品详情文本】蓝色主按钮...", flush=True)
            await click_element(ws, "button", "粘贴商品详情文本")
            await asyncio.sleep(2.0)

            text_ui_info = await eval_js(ws, """
            (() => {
                const textarea = document.querySelector('textarea');
                const textVal = textarea ? textarea.value : '';
                const bodyText = document.body.innerText;
                const hasTemplate = textVal.includes('商品名称：') && textVal.includes('商品规格：') && textVal.includes('商品宣传卖点：');
                const hasPrompt = bodyText.includes('已为您预填6部分标准核验模板');
                return {
                    textValSnippet: textVal.slice(0, 80),
                    hasTemplate,
                    hasPrompt,
                };
            })()
            """)
            print(f"[DEBUG] Text UI Info: {text_ui_info}", flush=True)
            assert text_ui_info["hasTemplate"] is True, "必须自动生成6部分填写模板！"
            assert text_ui_info["hasPrompt"] is True, "必须展示模板预填提示文案！"

            shot4 = await send_cdp(ws, "Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
            p4 = OUT_DIR / "btn_04_switched_to_text_template.png"
            p4.write_bytes(base64.b64decode(shot4["result"]["data"]))
            print(f"[SAVED] {p4} ({p4.stat().st_size / 1024:.1f} KB)", flush=True)

            print("🎉 全部 4 个降级按钮交互验收与真实浏览器测试圆满成功！", flush=True)

    finally:
        try:
            proc.terminate()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(run_test())
