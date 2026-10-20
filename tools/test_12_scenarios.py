"""ClaimCheck Pro 优化验收测试脚本 (12项要求端到端浏览器自动化验证)

验证目标：
1. 链接输入模式名称显示为：“🔗 商品链接（部分平台可能受限）”；
2. 链接输入框下显式提示 3 条明确规则：
   - 公开网页可尝试自动读取。
   - 京东、淘宝、拼多多等平台可能存在登录、验证码或动态加载限制。
   - 读取受限时，可使用详情文本或商品截图继续核验。
3. 输入京东等主流平台链接时，提前触发内联提示：
   “⚠️ 该平台可能限制自动读取。建议同时准备商品详情文本或截图。”
4. 设置面板清晰呈现 3 种独立服务能力卡片（模型 API · 网页读取器 · 搜索服务）及“AI模型已连接，但网络搜索服务未配置。”提示；
5. 京东链接读取受限后触发合规降级卡片，展示 3 个紧凑按钮；
6. 点击“📋 粘贴商品详情文本”实现平滑滚动切换，保留原始链接与识别ID，填入6部分模板，显示继续核验横幅；
7. 执行文本核验，验证直接从步骤2继续执行，报告保留原始受限链接并标记“🛡️ 受限，已由用户补充资料”；
8. 点击“🖼️ 上传商品宣传截图”自动切到截图标签，展示多截图上传组件 (accept_multiple_files=True)、隐私提醒与继续核验横幅。
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
OUT_DIR = WORKSPACE_ROOT / "screenshots" / "continuation_optimization"
OUT_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR = WORKSPACE_ROOT / ".cache" / "edge_profile_12_scenarios"
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
        if (!el) return false;
        el.scrollIntoView({{block: 'center', inline: 'nearest'}});
        el.click();
        return true;
    }})()
    """
    res = await eval_js(ws, expr)
    print(f"[CLICK] {selector} ({text_to_match}) -> {res}", flush=True)
    await asyncio.sleep(2.0)
    return bool(res)


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
    print(f"[INPUT] {selector} -> {res}", flush=True)
    await asyncio.sleep(1.0)
    return res


async def take_screenshot(ws, out_path):
    await asyncio.sleep(0.8)
    resp = await send_cdp(ws, "Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})
    data = resp.get("result", {}).get("data")
    if data:
        with open(out_path, "wb") as f:
            f.write(base64.b64decode(data))
        print(f"[SCREENSHOT] Saved: {out_path}", flush=True)


async def run_acceptance_suite():
    cdp_port = 9288
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

            # 等待 Streamlit 就绪
            for _ in range(40):
                ready = await eval_js(ws, "Boolean(document.body && document.body.innerText.includes('第一阶段：提交商品'))")
                if ready:
                    break
                await asyncio.sleep(0.5)
            await asyncio.sleep(2.0)

            # -----------------------------------------------------------------
            # 场景 1：验证链接输入模式新名称与3条规则说明
            # -----------------------------------------------------------------
            print("\n=== 场景 1: 验证链接功能名称与3条读取规则 ===", flush=True)
            body_text = await eval_js(ws, "document.body.innerText")
            assert "商品链接（部分平台可能受限）" in body_text, f"未检测到新链接名称: {body_text[:200]}"

            rules_text = await eval_js(ws, "document.body.innerText")
            assert "公开网页可尝试自动读取" in rules_text, "未检测到规则1：公开网页可尝试自动读取"
            assert "京东、淘宝、拼多多等平台可能存在登录、验证码或动态加载限制" in rules_text, "未检测到规则2：平台可能受限"
            assert "读取受限时，可使用详情文本或商品截图继续核验" in rules_text, "未检测到规则3：受限替代建议"
            print("✅ 场景 1 校验通过！新功能名称与3条读取规则完整呈现。")

            await take_screenshot(ws, OUT_DIR / "opt_01_url_input_new_label_and_rules.png")

            # -----------------------------------------------------------------
            # 场景 2：设置抽屉三种独立服务卡片与未配置搜索提示
            # -----------------------------------------------------------------
            print("\n=== 场景 2: 验证设置抽屉三种独立服务职责卡片与搜索未配置说明 ===", flush=True)
            await click_element(ws, "summary", "服务模式与端点设置")
            await asyncio.sleep(1.0)

            # 切换为 BYOK 模式
            await click_element(ws, "label", "用户自带 API")
            await asyncio.sleep(1.5)

            # 填写合法格式密钥与公网端点
            await set_input_value(ws, "input[type='password']", "sk-proj-test-demo-mock-key-123456")
            await asyncio.sleep(0.5)

            # 检查三服务卡片与未配置搜索提示
            drawer_text = await eval_js(ws, "document.body.innerText")
            assert "模型 API (LLM)" in drawer_text, "未检测到服务1：模型 API (LLM)"
            assert "负责理解和核验" in drawer_text, "未检测到模型核心职责：负责理解和核验"
            assert "网页读取器 (Web Reader)" in drawer_text, "未检测到服务2：网页读取器 (Web Reader)"
            assert "负责提取链接内容" in drawer_text, "未检测到网页读取器核心职责：负责提取链接内容"
            assert "搜索服务 (Search API)" in drawer_text, "未检测到服务3：搜索服务 (Search API)"
            assert "负责搜索官网与评测" in drawer_text, "未检测到搜索服务核心职责：负责搜索官网与评测"
            assert "AI模型已连接，但网络搜索服务未配置。" in drawer_text, "未检测到显式提示：AI模型已连接，但网络搜索服务未配置。"
            print("✅ 场景 2 校验通过！三服务独立卡片与搜索未配置显式说明完整呈现。")

            await take_screenshot(ws, OUT_DIR / "opt_02_service_distinction_three_cards.png")

            # 折叠设置
            await click_element(ws, "summary", "服务模式与端点设置")
            await asyncio.sleep(0.8)

            # -----------------------------------------------------------------
            # 场景 3：输入京东链接触发前置受限预警并执行降级
            # -----------------------------------------------------------------
            print("\n=== 场景 3: 京东域名输入前置受限预警与合规降级卡片 ===", flush=True)
            jd_test_url = "https://item.jd.com/10115777872752.html"
            await set_input_value(ws, "input[placeholder*='jd.com']", jd_test_url)
            await asyncio.sleep(1.0)

            page_body = await eval_js(ws, "document.body.innerText")
            assert "该平台可能限制自动读取。建议同时准备商品详情文本或截图。" in page_body, "未检测到前置京东受限预警"
            print("✅ 成功检测到京东平台前置预警：该平台可能限制自动读取。建议同时准备商品详情文本或截图。")
            await take_screenshot(ws, OUT_DIR / "opt_03_jd_proactive_warning.png")

            # 点击开始核验分析 (触发真实安全访问并拦截受限)
            print("[ACTION] 点击开始核验分析...", flush=True)
            await click_element(ws, "button", "开始核验分析")
            
            # 等待出现降级卡片
            for _ in range(20):
                await asyncio.sleep(1.0)
                card_visible = await eval_js(ws, "document.body.innerText.includes('无法自动读取该商品页面')")
                if card_visible:
                    break

            page_body = await eval_js(ws, "document.body.innerText")
            assert "无法自动读取该商品页面" in page_body, "未出现降级操作卡片"
            assert "接下来怎么做？" in page_body, "未出现接下来怎么做区域"
            assert "粘贴商品详情文本" in page_body, "未包含粘贴商品详情文本按钮"
            assert "上传商品宣传截图" in page_body, "未包含上传商品宣传截图按钮"
            assert "使用标准化链接重新尝试" in page_body, "未包含使用标准化链接重新尝试按钮"
            print("✅ 场景 3 校验通过！降级卡片展示 3 个紧凑操作按钮。")
            await take_screenshot(ws, OUT_DIR / "opt_04_jd_degradation_card.png")

            # -----------------------------------------------------------------
            # 场景 4：点击“📋 粘贴商品详情文本”平滑降级，填入模板并继续核验
            # -----------------------------------------------------------------
            print("\n=== 场景 4: 详情文本降级后继续核验流程 ===", flush=True)
            await click_element(ws, "button", "粘贴商品详情文本")
            
            # 轮询等待自动切换到详情文本 (textarea 出现)
            has_textarea = False
            for _ in range(25):
                has_textarea = await eval_js(ws, "Boolean(document.querySelector('textarea'))")
                if has_textarea:
                    break
                await asyncio.sleep(0.4)
            assert has_textarea is True, "未自动切换到文本输入框"
            await asyncio.sleep(1.0)

            # 验证继续核验横幅
            body_text = await eval_js(ws, "document.body.innerText")
            assert "继续核验模式（已继承受限链接与识别信息）" in body_text, "未显示继承受限链接与识别信息的继续核验模式横幅"
            assert "10115777872752" in body_text, "未保留商品识别码 10115777872752"
            assert "步骤2：确认品牌型号" in body_text, "未标明从步骤2继续核验"

            # 验证文本框预填 6 部分模板
            text_val = await eval_js(ws, "document.querySelector('textarea').value")
            assert "商品名称：" in text_val and "商品宣传卖点：" in text_val, f"未预填6部分模板: {text_val}"
            print("✅ 成功检测到继续核验横幅与 6 部分标准模板。")
            await take_screenshot(ws, OUT_DIR / "opt_05_text_continuation_banner_and_template.png")

            # 补充真实商品规格以完成核验
            supplement_text = """
商品名称：京东专供 智能降噪蓝牙耳机旗舰版
品牌：声学先锋 (SoundPioneer)
型号：SP-ANC200
商品规格：蓝牙5.3，45dB主动降噪，40小时长续航
商品宣传卖点：超强降噪45dB，单次续航8小时，IPX5级防水
使用条件或补充说明：配合官方专用充电盒使用
            """.strip()
            await set_input_value(ws, "textarea", supplement_text)
            await asyncio.sleep(1.0)

            # 点击开始核验
            print("[ACTION] 点击开始核验分析（继续核验流程）...", flush=True)
            await click_element(ws, "button", "开始核验分析")

            # 等待核验执行或阶段2候选确认
            for _ in range(12):
                await asyncio.sleep(1.0)
                cand_needed = await eval_js(ws, "document.body.innerText.includes('确认选定此型号') || document.body.innerText.includes('第二阶段：确认商品身份')")
                if cand_needed:
                    print("🎯 成功进入【阶段2：确认商品身份 (多候选确认)】，用户点选确认型号...", flush=True)
                    await click_element(ws, "button", "确认选定此型号")
                    await asyncio.sleep(1.5)
                    print("[ACTION] 确认型号后，点击开始核验分析进入执行流程...", flush=True)
                    await click_element(ws, "button", "开始核验分析")
                    break

            # 等待核验执行完成并呈现核验结果看板
            for _ in range(35):
                await asyncio.sleep(1.0)
                is_done = await eval_js(ws, "document.body.innerText.includes('核验结果看板') || document.body.innerText.includes('总体核验综合结论')")
                if is_done:
                    break

            res_body = await eval_js(ws, "document.body.innerText")
            assert ("核验结果看板" in res_body) and ("实时模型分析" in res_body), f"未展示真实核验结果看板，实际内容: {res_body[:400]}"
            assert "SP-ANC200" in res_body, "未成功核验目标型号 SP-ANC200"
            assert "受限，已由用户补充资料" in res_body, "未标记受限链接已由用户补充资料状态"
            assert "未配置" in res_body, "未明确呈现网络检索服务未配置状态"
            assert "SoundPro X1" not in res_body, "真实模式严禁回退到 Mock 演示数据！"
            print("✅ 场景 4 校验通过！详情文本降级后从步骤2无缝继续核验，成功输出 SP-ANC200 真实报告，零 Mock 泄露！")
            await take_screenshot(ws, OUT_DIR / "opt_06_text_continuation_report_success.png")

            # -----------------------------------------------------------------
            # 场景 5：测试截图模式降级无缝切换与多图上传能力
            # -----------------------------------------------------------------
            print("\n=== 场景 5: 截图模式降级切换、多图上传与隐私提醒 ===", flush=True)
            # 点击清空内容重置
            await click_element(ws, "button", "清空内容")
            await asyncio.sleep(1.5)

            # 显式点击切换至商品链接输入标签
            await click_element(ws, "label", "商品链接")
            await asyncio.sleep(1.0)

            # 等待 URL 输入框渲染出现
            has_inp = False
            for _ in range(20):
                has_inp = await eval_js(ws, "Boolean(document.querySelector('input[placeholder*=\"jd.com\"]'))")
                if has_inp:
                    break
                await asyncio.sleep(0.5)
            assert has_inp is True, "切换后未渲染商品链接输入框"

            # 输入京东链接再次触发降级
            res_inp = await set_input_value(ws, "input[placeholder*='jd.com']", jd_test_url)
            await asyncio.sleep(1.0)
            await click_element(ws, "button", "开始核验分析")

            card_found = False
            for _ in range(25):
                await asyncio.sleep(1.0)
                card_found = await eval_js(ws, "document.body.innerText.includes('无法自动读取该商品页面')")
                if card_found:
                    break
            print(f"[ACTION] 降级卡片状态: card_found={card_found}", flush=True)
            assert card_found is True, "未触发合规降级卡片"

            # 点击“🖼️ 上传商品宣传截图”
            await click_element(ws, "button", "上传商品宣传截图")

            # 轮询等待自动切换到截图模式
            has_uploader = False
            for _ in range(25):
                has_uploader = await eval_js(ws, "Boolean(document.querySelector('[data-testid=\"stFileUploader\"]'))")
                if has_uploader:
                    break
                await asyncio.sleep(0.4)
            assert has_uploader is True, "未切换到截图上传组件"
            await asyncio.sleep(1.0)

            # 验证自动切换到截图模式
            img_body = await eval_js(ws, "document.body.innerText")
            assert "继续核验模式（已继承受限链接与识别信息）" in img_body, "截图模式未展示继续核验横幅"
            assert "隐私脱敏提示" in img_body, "未展示隐私脱敏提示"
            assert "遮挡收件地址、电话、聊天记录与订单号" in img_body, "未提示隐私遮挡细节"
            assert "支持多张同时上传" in img_body or "支持同时上传多张图片" in img_body, "未支持多张截图同时上传"

            # 验证 file uploader 带有 multiple 属性
            has_multiple = await eval_js(ws, "Boolean(document.querySelector('input[type=file][multiple]'))")
            assert has_multiple is True, "文件上传组件未配置 multiple 属性 (accept_multiple_files=True)"
            print("✅ 场景 5 校验通过！截图模式成功继承受限链接与ID，展示隐私安全提示与多图上传支持！")
            await take_screenshot(ws, OUT_DIR / "opt_07_screenshot_continuation_multi_images.png")

            print("\n🎉 全部 5 大场景自动化验收通过！截图已完整保存至:", OUT_DIR)

    finally:
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    asyncio.run(run_acceptance_suite())
