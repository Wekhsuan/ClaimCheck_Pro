"""使用 Playwright (Edge) 截取第四阶段报告界面截图
严格符合第十三阶段 6 大板块规范：
01_phase4_overall_report_summary.png
02_phase4_four_level_verdict_cards.png
03_phase4_claim_inspection_and_evidence_details.png
04_phase4_excluded_evidence_and_self_check.png
"""

import os
import sys
import time
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright

OUTPUT_DIR = Path(r"D:\ClaimCheck_Pro\screenshots\evidence_verification_phase4")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def capture_phase4_ui():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(viewport={"width": 1366, "height": 900})
        page = context.new_page()

        print("[NAV] Opening Streamlit Mock mode at http://127.0.0.1:8501/?mode=mock ...")
        page.goto("http://127.0.0.1:8501/?mode=mock", timeout=30000)
        page.wait_for_timeout(3000)

        # 填入测试链接并触发核验
        inp = page.locator("input[type='text']").first
        print("[ACTION] Filling input URL...")
        inp.fill("https://item.jd.com/mock-soundpro-x1.html")
        inp.press("Enter")
        time.sleep(1)

        print("[ACTION] Clicking '🚀 开始核验分析' ...")
        btn = page.locator("button:has-text('开始核验分析')").first
        if btn.count() > 0:
            btn.click()
            time.sleep(5)
            page.wait_for_load_state("networkidle")
        else:
            print("[WARN] Start button not found!")

        time.sleep(2)

        # 展开折叠的声明卡片以展示凭证细节
        print("[ACTION] Expanding claim cards ...")
        expanders = page.locator(".streamlit-expanderHeader")
        for i in range(expanders.count()):
            try:
                text = expanders.nth(i).inner_text()
                if "声明" in text:
                    expanders.nth(i).click()
                    time.sleep(0.4)
            except Exception:
                pass

        time.sleep(2)

        # Helper to scroll stMain container
        def scroll_main_to(y):
            page.evaluate(f"""
                const el = document.querySelector('[data-testid="stMain"]') || document.querySelector('.stMain');
                if (el) {{ el.scrollTop = {y}; }}
            """)
            time.sleep(1.2)

        # 1. 截图 1: 板块 1 分析模式与来源标识 与 板块 3 总体综合核验结论
        print("[CAPTURE] Capturing 01_phase4_overall_report_summary.png ...")
        scroll_main_to(500)
        page.screenshot(path=str(OUTPUT_DIR / "01_phase4_overall_report_summary.png"))

        # 2. 截图 2: 板块 2 四级核验结论分布指标卡片与板块 4 商品身份档案
        print("[CAPTURE] Capturing 02_phase4_four_level_verdict_cards.png ...")
        scroll_main_to(950)
        page.screenshot(path=str(OUTPUT_DIR / "02_phase4_four_level_verdict_cards.png"))

        # 3. 截图 3: 板块 5 逐项声明核验明细、支撑凭证原句、真实 URL 与来源分级 Badge
        print("[CAPTURE] Capturing 03_phase4_claim_inspection_and_evidence_details.png ...")
        scroll_main_to(1450)
        page.screenshot(path=str(OUTPUT_DIR / "03_phase4_claim_inspection_and_evidence_details.png"))

        # 4. 截图 4: 排除证据线索、自检通过状态、人工清单、购买建议与板块 6 导出按钮合规承诺
        print("[CAPTURE] Capturing 04_phase4_excluded_evidence_and_self_check.png ...")
        page.evaluate("""
            const el = document.querySelector('[data-testid="stMain"]') || document.querySelector('.stMain');
            if (el) { el.scrollTop = el.scrollHeight; }
        """)
        time.sleep(1.2)
        page.screenshot(path=str(OUTPUT_DIR / "04_phase4_excluded_evidence_and_self_check.png"))

        browser.close()
        print(f"✅ All 4 screenshots captured successfully into {OUTPUT_DIR}")

if __name__ == "__main__":
    capture_phase4_ui()
