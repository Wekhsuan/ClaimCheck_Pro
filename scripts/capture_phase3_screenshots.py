"""Playwright 浏览器自动化脚本：捕获第三阶段端到端运行截图

截图清单：
1. 01_search_preflight_confirmation.png (第三阶段前置搜索确认卡片，展示有效声明数、检索模式、费用承担方声明、分层策略与操作按钮)
2. 02_layered_queries_audit.png (第三阶段分层检索词规划与执行审计明细表，展示 Layer 1 官方与 Layer 2 评测词及执行状态)
3. 03_extracted_evidence_inspection.png (候选证据正文与结构化展示看板，展示客观真实证据核验状态、阶段边界保护告示)
"""

import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from playwright.sync_api import sync_playwright

OUTPUT_DIR = r"D:\ClaimCheck_Pro\screenshots\search_execution_phase3"
os.makedirs(OUTPUT_DIR, exist_ok=True)

APP_URL = "http://127.0.0.1:8501/?mode=byok&input_mode=text"

def capture_screenshots():
    print("[1/5] Launching Microsoft Edge...")
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(viewport={"width": 1366, "height": 900})
        page = context.new_page()

        print(f"[2/5] Visiting: {APP_URL}")
        page.goto(APP_URL, wait_until="networkidle")
        time.sleep(2)

        sample_text = (
            "声学极客 SoundPro X1 曜石黑 降噪旗舰版，双馈主动降噪高达48dB，"
            "支持LHDC 5.0超高清音频传输，搭配充电盒综合续航长达40小时，整机具备IPX5级防水。"
        )
        print("Filling product text...")
        textarea = page.locator("textarea[aria-label='商品详情文本']").first
        if textarea.count() == 0:
            textarea = page.locator("textarea").first
        textarea.fill(sample_text)
        time.sleep(1)

        # 2. 点击【开始核验分析】提取声明
        print("Submitting product text to extract claims...")
        start_btn = page.locator("button:has-text('开始核验分析')").first
        start_btn.click()

        # 等待第一阶段声明提取确认卡片出现
        print("Waiting for claims confirmation card...")
        page.wait_for_selector("text=第一阶段：宣传声明提取确认", timeout=15000)
        time.sleep(1)

        # 3. 点击【确认以上声明，开始证据核验】
        print("Clicking confirm claims button...")
        confirm_claim_btn = page.locator("button:has-text('确认以上声明')").first
        confirm_claim_btn.click()

        # 等待第三阶段前置搜索确认卡片渲染
        print("Waiting for Phase 3 preflight search confirmation card...")
        page.wait_for_selector("text=第三阶段：网络搜索与候选正文提取前置确认", timeout=15000)
        time.sleep(1.5)

        # 截图 1：前置搜索确认卡片
        path_01 = os.path.join(OUTPUT_DIR, "01_search_preflight_confirmation.png")
        page.screenshot(path=path_01)
        print(f"Saved screenshot 1: {path_01}")

        # 4. 点击【确认并开始网络搜索与证据提取】
        print("Clicking execute search button...")
        exec_search_btn = page.locator("button:has-text('确认并开始网络搜索')").first
        exec_search_btn.click()

        # 等待第三阶段结果看板与审计表渲染
        print("Waiting for Phase 3 results audit dashboard...")
        page.wait_for_selector("text=第三阶段：网络搜索与正文提取执行成果看板", timeout=20000)
        time.sleep(2)

        # 截图 2：分层检索词执行审计表
        path_02 = os.path.join(OUTPUT_DIR, "02_layered_queries_audit.png")
        page.screenshot(path=path_02)
        print(f"Saved screenshot 2: {path_02}")

        # 5. 向下滚动展示提取证据明细与阶段边界提示
        print("Scrolling page to capture structured evidence and boundary callout...")
        boundary_el = page.locator("text=第三阶段任务已达成").first
        if boundary_el.count() > 0:
            boundary_el.scroll_into_view_if_needed()
        else:
            page.locator("button:has-text('重新执行搜索')").first.scroll_into_view_if_needed()
        time.sleep(1.5)

        # 截图 3：结构化证据与阶段边界告示
        path_03 = os.path.join(OUTPUT_DIR, "03_extracted_evidence_inspection.png")
        page.screenshot(path=path_03)
        print(f"Saved screenshot 3: {path_03}")

        browser.close()
        print("Phase 3 screenshot capture completed successfully!")

if __name__ == "__main__":
    capture_screenshots()
