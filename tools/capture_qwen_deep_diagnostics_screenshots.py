# -*- coding: utf-8 -*-
"""自动化截取千问 Responses API 增强诊断与细分状态标签截图
保存至 screenshots/qwen_deep_diagnostics/
"""

import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

WORKSPACE_ROOT = Path(r"D:\ClaimCheck_Pro").resolve()
OUTPUT_DIR = WORKSPACE_ROOT / "screenshots" / "qwen_deep_diagnostics"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "http://127.0.0.1:8501"


def run_capture():
    print(f"[START] Capturing enhanced diagnostics screenshots against {BASE_URL}...")
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 2200})
        page = context.new_page()

        page.goto(BASE_URL, wait_until="networkidle")
        page.wait_for_timeout(1000)

        # 展开"服务模式与端点设置"
        settings_expander = page.locator("details summary:has-text('服务模式与端点设置')")
        if settings_expander.count() > 0:
            settings_expander.first.click()
            page.wait_for_timeout(800)

        # 切换网络搜索服务提供商为 Qwen (radio 控件)
        qwen_radio = page.locator("label:has-text('Qwen 通义千问搜索')")
        if qwen_radio.count() > 0:
            qwen_radio.first.click()
            page.wait_for_timeout(1000)

        key_input = page.locator("input[type='password']").first

        # -------------------------------------------------------------
        # 01: sk-qwen-no-tool-call-key (web_search_tool_not_called + 增强诊断)
        # -------------------------------------------------------------
        print("[01] Capturing 01_web_search_tool_not_called_enhanced_diagnostics.png...")
        key_input.fill("sk-qwen-no-tool-call-key")
        page.keyboard.press("Enter")
        page.wait_for_timeout(600)

        test_btn = page.locator("button:has-text('千问搜索连接')").first
        test_btn.click()
        page.wait_for_timeout(2000)

        # 向上滚动一点并截图主体
        page.screenshot(path=str(OUTPUT_DIR / "01_web_search_tool_not_called_enhanced_diagnostics.png"), full_page=False)
        print("  -> Saved 01_web_search_tool_not_called_enhanced_diagnostics.png")

        # 专门聚焦诊断展开项
        diag_expander = page.locator("details summary:has-text('搜索来源结构与模式诊断')")
        if diag_expander.count() > 0:
            diag_expander.first.scroll_into_view_if_needed()
            page.wait_for_timeout(600)
            page.screenshot(path=str(OUTPUT_DIR / "01b_diagnostic_panel_detailed.png"), full_page=True)
            print("  -> Saved 01b_diagnostic_panel_detailed.png")

        # -------------------------------------------------------------
        # 02: sk-qwen-tool-not-attached-key (web_search_tool_not_attached)
        # -------------------------------------------------------------
        print("[02] Capturing 02_web_search_tool_not_attached.png...")
        key_input.fill("sk-qwen-tool-not-attached-key")
        page.keyboard.press("Enter")
        page.wait_for_timeout(600)

        test_btn.click()
        page.wait_for_timeout(2000)

        page.screenshot(path=str(OUTPUT_DIR / "02_web_search_tool_not_attached.png"), full_page=False)
        print("  -> Saved 02_web_search_tool_not_attached.png")

        # -------------------------------------------------------------
        # 03: sk-qwen-called-no-sources-key (web_search_called_no_sources)
        # -------------------------------------------------------------
        print("[03] Capturing 03_web_search_called_no_sources.png...")
        key_input.fill("sk-qwen-called-no-sources-key")
        page.keyboard.press("Enter")
        page.wait_for_timeout(600)

        test_btn.click()
        page.wait_for_timeout(2000)

        page.screenshot(path=str(OUTPUT_DIR / "03_web_search_called_no_sources.png"), full_page=False)
        print("  -> Saved 03_web_search_called_no_sources.png")

        # -------------------------------------------------------------
        # 04: sk-qwen-test-success-key (connected_searchable)
        # -------------------------------------------------------------
        print("[04] Capturing 04_connected_searchable_success.png...")
        key_input.fill("sk-qwen-test-success-key")
        page.keyboard.press("Enter")
        page.wait_for_timeout(600)

        test_btn.click()
        page.wait_for_timeout(2000)

        page.screenshot(path=str(OUTPUT_DIR / "04_connected_searchable_success.png"), full_page=False)
        print("  -> Saved 04_connected_searchable_success.png")

        browser.close()
        print("[DONE] All 4 enhanced diagnostics screenshots captured.")


if __name__ == "__main__":
    run_capture()
