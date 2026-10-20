"""ClaimCheck Pro 第五阶段最终验收 12 张完整浏览器高清截图自动化采集脚本
使用 Playwright Chromium (msedge channel) 直接驱动本地 Streamlit 界面 (http://127.0.0.1:8501)
保存至 screenshots/final_acceptance/
"""

import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import time
from pathlib import Path
from playwright.sync_api import sync_playwright

WORKSPACE_ROOT = Path(r"D:\ClaimCheck_Pro").resolve()
OUTPUT_DIR = WORKSPACE_ROOT / "screenshots" / "final_acceptance"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "http://127.0.0.1:8501"


def run_capture():
    print(f"[START] Starting Playwright capture against {BASE_URL}...")
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 960})
        page = context.new_page()

        # =====================================================================
        # 01_homepage.png: 首页整体视图，突出三大输入方式与服务状态
        # =====================================================================
        print("[01] Capturing 01_homepage.png...")
        page.goto(f"{BASE_URL}/?mode=mock", wait_until="networkidle")
        page.wait_for_selector("button:has-text('开始核验分析')", timeout=10000)
        page.wait_for_timeout(1000)
        page.screenshot(path=str(OUTPUT_DIR / "01_homepage.png"), full_page=False)
        print("  -> Saved 01_homepage.png")

        # =====================================================================
        # 02_service_settings.png: 服务模式与高级设置，展示三服务分离
        # =====================================================================
        print("[02] Capturing 02_service_settings.png...")
        settings_expander = page.locator("details summary:has-text('服务模式与端点设置')")
        if settings_expander.count() > 0:
            settings_expander.first.click()
            page.wait_for_timeout(800)
        page.screenshot(path=str(OUTPUT_DIR / "02_service_settings.png"), full_page=False)
        print("  -> Saved 02_service_settings.png")

        # 收起设置
        if settings_expander.count() > 0:
            settings_expander.first.click()
            page.wait_for_timeout(500)

        # =====================================================================
        # 03_three_inputs.png: 输入区域：详情文本展开状态
        # =====================================================================
        print("[03] Capturing 03_three_inputs.png...")
        text_radio = page.locator("label:has-text('商品详情文本')")
        if text_radio.count() > 0:
            text_radio.first.click()
            page.wait_for_timeout(800)
        page.screenshot(path=str(OUTPUT_DIR / "03_three_inputs.png"), full_page=False)
        print("  -> Saved 03_three_inputs.png")

        # =====================================================================
        # 04_identity_confirmation.png & 05_claims_confirmation.png
        # =====================================================================
        print("[04 & 05] Capturing Identity and Claims Confirmation in BYOK mode...")
        page.goto(f"{BASE_URL}/?mode=byok&key=sk-test-demo-key-for-ui-capture-only", wait_until="networkidle")
        page.wait_for_selector("button:has-text('开始核验分析')", timeout=10000)

        # 切换文本模式并填充
        page.locator("label:has-text('商品详情文本')").click()
        page.wait_for_timeout(800)

        t = page.locator("textarea")
        t.first.fill("品牌：弱水时砂 型号：琉璃X 旗舰真无线耳机 支持45dB主动降噪 综合续航30小时")
        t.first.press("Control+Enter")
        page.wait_for_timeout(800)

        page.locator("button:has-text('开始核验分析')").click()
        page.wait_for_timeout(2500)

        # 04 截图: 商品身份确认卡片 (滚动居中)
        page.evaluate("""() => {
            const el = document.querySelector("div[class*='saas-card']");
            if (el) el.scrollIntoView({block: 'start'});
        }""")
        page.wait_for_timeout(600)
        page.screenshot(path=str(OUTPUT_DIR / "04_identity_confirmation.png"), full_page=False)
        print("  -> Saved 04_identity_confirmation.png")

        # 05 截图: 展开未采用内容展示质量评分与分类
        unadopted = page.locator("details summary:has-text('查看未采用内容')")
        if unadopted.count() > 0:
            unadopted.first.click()
            page.wait_for_timeout(600)

        page.evaluate("""() => {
            const el = document.querySelector("div[class*='saas-card']");
            if (el) el.scrollIntoView({block: 'center'});
        }""")
        page.wait_for_timeout(600)
        page.screenshot(path=str(OUTPUT_DIR / "05_claims_confirmation.png"), full_page=False)
        print("  -> Saved 05_claims_confirmation.png")

        # =====================================================================
        # 06_search_budget_confirmation.png: 搜索预算与策略确认
        # =====================================================================
        print("[06] Capturing search budget confirmation...")
        conf_claims_btn = page.locator("button:has-text('确认以上声明')")
        if conf_claims_btn.count() > 0:
            conf_claims_btn.first.click()
            page.wait_for_timeout(2500)

        page.evaluate("""() => {
            const el = Array.from(document.querySelectorAll('div')).find(d => d.innerText && d.innerText.includes('第三阶段：网络搜索与候选正文提取前置确认'));
            if (el) el.scrollIntoView({block: 'start'});
        }""")
        page.wait_for_timeout(600)
        page.screenshot(path=str(OUTPUT_DIR / "06_search_budget_confirmation.png"), full_page=False)
        print("  -> Saved 06_search_budget_confirmation.png")

        # =====================================================================
        # 07_search_execution.png: 搜索执行看板
        # =====================================================================
        print("[07] Capturing search execution...")
        exec_search_btn = page.locator("button:has-text('确认并开始网络搜索与证据提取')")
        if exec_search_btn.count() > 0:
            exec_search_btn.first.click()
            page.wait_for_timeout(3500)

        page.evaluate("""() => {
            const el = Array.from(document.querySelectorAll('div')).find(d => d.innerText && d.innerText.includes('第三阶段：网络搜索与正文提取执行成果看板'));
            if (el) el.scrollIntoView({block: 'start'});
        }""")
        page.wait_for_timeout(600)
        page.screenshot(path=str(OUTPUT_DIR / "07_search_execution.png"), full_page=False)
        print("  -> Saved 07_search_execution.png")

        # =====================================================================
        # 08_overall_results.png, 09_claim_expanded_evidence.png, 10_report_export.png
        # =====================================================================
        print("[08, 09, 10] Running Mock Case 1 to capture complete results...")
        page.goto(f"{BASE_URL}/?mode=mock", wait_until="networkidle")
        page.wait_for_selector("button:has-text('开始核验分析')", timeout=10000)

        url_in = page.locator("input[placeholder*='jd.com']")
        if url_in.count() > 0:
            url_in.first.fill("https://item.jd.com/1008695271.html")
            url_in.first.press("Tab")
            page.wait_for_timeout(600)

        page.locator("button:has-text('开始核验分析')").click()
        page.wait_for_timeout(3500)

        # 08: 结果总览卡片 (四级统计与总体摘要)
        page.evaluate("document.querySelector('main').scrollTop = 950")
        page.wait_for_timeout(800)
        page.screenshot(path=str(OUTPUT_DIR / "08_overall_results.png"), full_page=False)
        print("  -> Saved 08_overall_results.png")

        # 09: 展开单项声明证据
        first_claim_expander = page.locator("details summary:has-text('声明 1：')")
        if first_claim_expander.count() > 0:
            first_claim_expander.first.click()
            page.wait_for_timeout(800)

        page.evaluate("document.querySelector('main').scrollTop = 1850")
        page.wait_for_timeout(800)
        page.screenshot(path=str(OUTPUT_DIR / "09_claim_expanded_evidence.png"), full_page=False)
        print("  -> Saved 09_claim_expanded_evidence.png")

        # 10: 报告导出区
        page.evaluate("document.querySelector('main').scrollTop = document.querySelector('main').scrollHeight")
        page.wait_for_timeout(800)
        page.screenshot(path=str(OUTPUT_DIR / "10_report_export.png"), full_page=False)
        print("  -> Saved 10_report_export.png")

        # =====================================================================
        # 11_restricted_fallback.png: 平台受限降级提示，友好错误界面
        # =====================================================================
        print("[11] Capturing 11_restricted_fallback.png in BYOK mode...")
        page.goto(f"{BASE_URL}/?mode=byok&key=sk-test-demo-key-for-ui-capture-only", wait_until="networkidle")
        page.wait_for_selector("button:has-text('开始核验分析')", timeout=10000)

        url_input = page.locator("input[placeholder*='jd.com']")
        if url_input.count() > 0:
            url_input.first.fill("https://item.jd.com/1008695271.html")
            url_input.first.press("Tab")
            page.wait_for_timeout(600)

        page.locator("button:has-text('开始核验分析')").click()
        page.wait_for_timeout(3000)

        page.evaluate("document.querySelector('main').scrollTop = 750")
        page.wait_for_timeout(800)
        page.screenshot(path=str(OUTPUT_DIR / "11_restricted_fallback.png"), full_page=False)
        print("  -> Saved 11_restricted_fallback.png")

        # =====================================================================
        # 12_no_valid_claims.png: 无有效声明阻断提示界面
        # =====================================================================
        print("[12] Capturing 12_no_valid_claims.png in BYOK mode...")
        page.goto(f"{BASE_URL}/?mode=byok&key=sk-test-demo-key-for-ui-capture-only", wait_until="networkidle")
        page.wait_for_selector("button:has-text('开始核验分析')", timeout=10000)

        page.locator("label:has-text('商品详情文本')").click()
        page.wait_for_timeout(800)

        text_input = page.locator("textarea")
        if text_input.count() > 0:
            text_input.first.fill("【截图1提取内容】 品牌：弱水时砂 商品编号：1008695271 尊贵奢华极致体验 暂无数据")
            text_input.first.press("Control+Enter")
            page.wait_for_timeout(800)

        page.locator("button:has-text('开始核验分析')").click()
        page.wait_for_timeout(3000)

        page.evaluate("document.querySelector('main').scrollTop = 450")
        page.wait_for_timeout(800)
        page.screenshot(path=str(OUTPUT_DIR / "12_no_valid_claims.png"), full_page=False)
        print("  -> Saved 12_no_valid_claims.png")

        browser.close()
        print("[SUCCESS] All 12 screenshots captured with high fidelity!")


if __name__ == "__main__":
    run_capture()
