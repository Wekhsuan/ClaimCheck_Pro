"""ClaimCheck Pro 受限页面降级交互与白色高对比度 UI 全真浏览器截图采集脚本
使用 Microsoft Edge 原生 CDP (Chrome DevTools Protocol) 执行自动化端到端测试并截图。

覆盖场景：
1. 01_restricted_degradation_card.png (BYOK + 京东反爬链接 -> 白色受限页面降级卡片与元数据网格)
2. 02_auto_switched_prefilled_text.png (点击【粘贴详情文本】后自动切换标签页并预填6部分标准模板)
3. 03_text_cleaning_diff_preview.png (粘贴含噪声文本后，点击【清洗页面文字】展示对比差异卡片与过滤确认)
4. 04_continuation_report_metadata.png (确认清洗后开始核验，完成全流程分析，展示【受限已由用户补充】与【未配置网络搜索】元数据)
5. 05_two_line_stepper_responsive.png (两行高对比度 6 步状态步进指示器)
6. 06_search_and_llm_separated_drawer.png (展开设置抽屉，展示 AI 模型服务与网络检索服务明确隔离的卡片)
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
OUT_DIR = WORKSPACE_ROOT / "screenshots" / "restricted_fallback_white_ui"
OUT_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR = WORKSPACE_ROOT / ".cache" / "edge_profile_restricted_fallback"
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


async def run_automation():
    cdp_port = 9265
    cmd = [
        EDGE_PATH,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--no-first-run",
        "--no-default-browser-check",
        f"--user-data-dir={CACHE_DIR}",
        f"--remote-debugging-port={cdp_port}",
        "--window-size=1280,2400",
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
            await asyncio.sleep(2.0)

            # -----------------------------------------------------------------
            # 准备工作：配置 BYOK 模式
            # -----------------------------------------------------------------
            print("[SETUP] 展开设置，配置 BYOK 模式...", flush=True)
            await click_element(ws, "summary", "服务模式与端点设置")
            await asyncio.sleep(1.0)

            await click_element(ws, "label", "用户自带 API")
            await asyncio.sleep(1.5)

            # 填写 API Key
            print("[ACTION] 填写测试 API Key...", flush=True)
            await set_input_value(ws, "input[type='password']", "sk-test-demo-byok-user-key-12345678")
            await asyncio.sleep(1.0)

            # 折叠回设置抽屉以展示主界面
            await click_element(ws, "summary", "服务模式与端点设置")
            await asyncio.sleep(0.5)

            # -----------------------------------------------------------------
            # 场景 1: 01_restricted_degradation_card.png
            # 填入京东受限链接并执行核验 -> 触发合规降级操作卡片
            # -----------------------------------------------------------------
            target_jd_url = "https://item.jd.com/10115777872752.html"
            print(f"[SCENARIO 1] 填入京东受限链接: {target_jd_url} ...", flush=True)
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

            # 验证页面包含核心元数据与三个操作按钮
            page_text = await eval_js(ws, "document.body.innerText")
            assert "无法自动读取该商品页面" in page_text
            assert "10115777872752" in page_text
            assert "京东" in page_text
            assert "粘贴商品详情文本" in page_text
            assert "上传商品宣传截图" in page_text
            assert "SoundPro X1" not in page_text, "禁止泄漏 SoundPro X1 演示数据！"

            # 滚动到降级卡片中央进行截屏
            await eval_js(ws, """
            (() => {
                const el = document.querySelector('.saas-card');
                if (el) el.scrollIntoView({block: 'start'});
            })()
            """)
            await asyncio.sleep(1.0)

            print("[CAPTURE] 1. 保存 01_restricted_degradation_card.png...", flush=True)
            shot1 = await send_cdp(ws, "Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
            p1 = OUT_DIR / "01_restricted_degradation_card.png"
            p1.write_bytes(base64.b64decode(shot1["result"]["data"]))
            print(f"[SAVED] {p1} ({p1.stat().st_size / 1024:.1f} KB)", flush=True)

            # -----------------------------------------------------------------
            # 场景 2: 02_auto_switched_prefilled_text.png
            # 点击【📋 粘贴商品详情文本】后自动切换至文本标签页并预填6部分标准模板
            # -----------------------------------------------------------------
            print("[SCENARIO 2] 点击降级卡片中的【📋 粘贴商品详情文本】按钮...", flush=True)
            await click_element(ws, "button", "粘贴商品详情文本")
            textarea_val = ""
            for _ in range(25):
                textarea_val = await eval_js(ws, "document.querySelector('textarea') ? document.querySelector('textarea').value : ''")
                if "商品名称：" in textarea_val:
                    break
                await asyncio.sleep(0.5)
            await asyncio.sleep(1.0)

            print(f"[DEBUG] Textarea value:\n{textarea_val}", flush=True)
            assert "商品名称：" in textarea_val
            assert "商品宣传卖点：" in textarea_val

            print("[CAPTURE] 2. 保存 02_auto_switched_prefilled_text.png...", flush=True)
            shot2 = await send_cdp(ws, "Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
            p2 = OUT_DIR / "02_auto_switched_prefilled_text.png"
            p2.write_bytes(base64.b64decode(shot2["result"]["data"]))
            print(f"[SAVED] {p2} ({p2.stat().st_size / 1024:.1f} KB)", flush=True)

            # -----------------------------------------------------------------
            # 场景 3: 03_text_cleaning_diff_preview.png
            # 粘贴商品文本并点击【清洗页面文字】展示对比差异卡片
            # -----------------------------------------------------------------
            print("[SCENARIO 3] 补充粘贴含噪声的详情文本...", flush=True)
            sample_dirty_text = (
                "商品名称：极客声学 SoundPro X1 曜石黑 降噪耳机\n"
                "品牌：声学极客\n"
                "型号：SoundPro X1\n"
                "加入购物车\n"
                "店铺首页\n"
                "商品规格：双馈主动降噪48dB，40小时长续航，蓝牙5.3\n"
                "官方正品\n"
                "商品宣传卖点：48dB旗舰降噪，LHDC 5.0超清音频解码\n"
                "猜你喜欢\n"
                "同类热卖\n"
                "使用条件或补充说明：需在开启ANC且AAC协议下达成标称续航\n"
                "版权所有 侵权必究\n"
            )
            await set_input_value(ws, "textarea", sample_dirty_text)
            await asyncio.sleep(1.0)

            print("[ACTION] 点击【🧹 清洗页面文字】按钮...", flush=True)
            await click_element(ws, "button", "清洗页面文字")
            await asyncio.sleep(2.0)

            # 验证清洗差异预览卡片出现
            page_text = await eval_js(ws, "document.body.innerText")
            assert "页面文字清洗预览与过滤确认" in page_text
            assert "已过滤" in page_text

            print("[CAPTURE] 3. 保存 03_text_cleaning_diff_preview.png...", flush=True)
            shot3 = await send_cdp(ws, "Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
            p3 = OUT_DIR / "03_text_cleaning_diff_preview.png"
            p3.write_bytes(base64.b64decode(shot3["result"]["data"]))
            print(f"[SAVED] {p3} ({p3.stat().st_size / 1024:.1f} KB)", flush=True)

            # -----------------------------------------------------------------
            # 场景 4: 04_continuation_report_metadata.png
            # 确认应用清洗结果后点击开始核验 -> 产出包含【受限已补充】与【未配置网络搜索】报告
            # -----------------------------------------------------------------
            print("[SCENARIO 4] 点击【✅ 确认应用清洗结果】...", flush=True)
            await click_element(ws, "button", "确认应用清洗结果")
            await asyncio.sleep(1.5)

            print("[ACTION] 点击【开始核验分析】继续核验全流程...", flush=True)
            await click_element(ws, "button", "开始核验分析")

            # 检查是否需要人工确认候选型号
            for _ in range(15):
                needs_cand = await eval_js(ws, "document.body.innerText.includes('确认选定此型号')")
                if needs_cand:
                    print("[ACTION] 检测到多候选型号选择卡片，点击【✅ 确认选定此型号】...", flush=True)
                    await click_element(ws, "button", "确认选定此型号")
                    await asyncio.sleep(1.5)
                    await click_element(ws, "button", "开始核验分析")
                    break
                has_rep = await eval_js(ws, "document.body.innerText.includes('核验结果看板')")
                if has_rep:
                    break
                await asyncio.sleep(0.5)

            print("[WAIT] 等待核验分析完成并渲染看板...", flush=True)
            for _ in range(30):
                has_report = await eval_js(ws, "document.body.innerText.includes('核验结果看板')")
                if has_report:
                    break
                await asyncio.sleep(0.5)
            await asyncio.sleep(2.5)

            # 校验报告元数据
            report_text = await eval_js(ws, "document.body.innerText")
            print(f"[DEBUG] Report text snippet: {report_text[:300]}...", flush=True)
            assert "核验结果看板" in report_text
            assert "受限，已由用户补充资料" in report_text
            assert "未配置" in report_text
            assert "仅用户提供的文本与截图" in report_text
            assert "SoundPro X1" in report_text

            print("[CAPTURE] 4. 保存 04_continuation_report_metadata.png...", flush=True)
            shot4 = await send_cdp(ws, "Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
            p4 = OUT_DIR / "04_continuation_report_metadata.png"
            p4.write_bytes(base64.b64decode(shot4["result"]["data"]))
            print(f"[SAVED] {p4} ({p4.stat().st_size / 1024:.1f} KB)", flush=True)

            # -----------------------------------------------------------------
            # 场景 5: 05_two_line_stepper_responsive.png
            # 聚焦展示两行高对比度 6 步状态步进器
            # -----------------------------------------------------------------
            print("[SCENARIO 5] 滚动聚焦到 6 步双行步进指示器...", flush=True)
            await eval_js(ws, """
            (() => {
                const el = document.querySelector('.stepper-container-v2');
                if (el) el.scrollIntoView({block: 'center'});
            })()
            """)
            await asyncio.sleep(1.0)

            print("[CAPTURE] 5. 保存 05_two_line_stepper_responsive.png...", flush=True)
            shot5 = await send_cdp(ws, "Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
            p5 = OUT_DIR / "05_two_line_stepper_responsive.png"
            p5.write_bytes(base64.b64decode(shot5["result"]["data"]))
            print(f"[SAVED] {p5} ({p5.stat().st_size / 1024:.1f} KB)", flush=True)

            # -----------------------------------------------------------------
            # 场景 6: 06_search_and_llm_separated_drawer.png
            # 展开设置抽屉，展示 AI 模型服务与网络检索服务明确隔离卡片
            # -----------------------------------------------------------------
            print("[SCENARIO 6] 滚动到顶部并展开设置抽屉...", flush=True)
            await eval_js(ws, "window.scrollTo(0, 0);")
            await asyncio.sleep(0.5)

            await click_element(ws, "summary", "服务模式与端点设置")
            await asyncio.sleep(1.5)

            # 校验抽屉内包含隔离内容
            drawer_text = await eval_js(ws, "document.body.innerText")
            assert ("AI 模型服务" in drawer_text) or ("AI 语言模型服务" in drawer_text)
            assert "网络搜索服务" in drawer_text
            assert "手动添加证据材料" in drawer_text
            assert "配置搜索服务说明" in drawer_text

            print("[CAPTURE] 6. 保存 06_search_and_llm_separated_drawer.png...", flush=True)
            shot6 = await send_cdp(ws, "Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
            p6 = OUT_DIR / "06_search_and_llm_separated_drawer.png"
            p6.write_bytes(base64.b64decode(shot6["result"]["data"]))
            print(f"[SAVED] {p6} ({p6.stat().st_size / 1024:.1f} KB)", flush=True)

            print("🎉 全部 6 个高对比度受限降级全流程验收截图已成功采集！", flush=True)

    finally:
        try:
            proc.terminate()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(run_automation())
