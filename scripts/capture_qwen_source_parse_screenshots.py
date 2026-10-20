# -*- coding: utf-8 -*-
"""Playwright automation script: Capture visual evidence for Qwen Responses API source parsing fix and status tagging.

Screenshots:
1. 01_responses_mode_selected_diagnostics.png: Responses API selected, source structure diagnostics & endpoint tracking
2. 02_search_ok_no_url_responses_mode_banner.png: search_ok_no_url without contradictory mode switch prompt
3. 03_source_parse_failed_status.png: source_parse_failed tag when URLs are invalid
4. 04_web_search_tool_not_called_status.png: web_search_tool_not_called tag when no web_search_call in output
5. 05_responses_mode_not_applied_status.png: responses_mode_not_applied tag when routing failed
6. 06_immediate_state_reset_on_config_change.png: test state instantly reset on model/platform/mode change
"""

import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from playwright.sync_api import sync_playwright

OUTPUT_DIR = r"D:\ClaimCheck_Pro\screenshots\qwen_source_parse_fix"
os.makedirs(OUTPUT_DIR, exist_ok=True)

APP_URL = "http://127.0.0.1:8501"


def run():
    print("Launching browser...")
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(viewport={"width": 1400, "height": 1100})
        page = context.new_page()

        print(f"Opening app: {APP_URL}")
        page.goto(APP_URL, wait_until="networkidle")
        time.sleep(2)

        # 1. 打开服务设置抽屉
        print("Expanding settings drawer...")
        settings_expander = page.locator("details summary:has-text('服务模式与端点设置')").first
        if settings_expander.is_visible():
            settings_expander.click()
            time.sleep(1)

        # 2. 选择 Qwen 通义千问搜索
        print("Selecting Qwen search provider...")
        qwen_radio = page.locator("label:has-text('Qwen 通义千问搜索')").first
        if qwen_radio.is_visible():
            qwen_radio.click()
            time.sleep(2)

        # -------------------------------------------------------------
        # 场景 1: sk-qwen-test-success-key (诊断面板与正常响应)
        # -------------------------------------------------------------
        print("Testing Scenario 1: success key with source diagnostics...")
        key_input = page.locator("input[type='password'][aria-label*='API Key']").last
        key_input.fill("sk-qwen-test-success-key")
        time.sleep(1)

        test_btn = page.locator("button:has-text('测试 Qwen 千问搜索连接')").first
        test_btn.click()
        time.sleep(2)

        # 确保诊断面板展开
        diag_expander = page.locator("details summary:has-text('搜索来源结构与模式诊断')").first
        if diag_expander.is_visible():
            # 查看是否已展开
            parent_details = page.locator("details:has(summary:has-text('搜索来源结构与模式诊断'))").first
            is_open = parent_details.get_attribute("open") is not None
            if not is_open:
                diag_expander.click()
                time.sleep(1)

        shot1_path = os.path.join(OUTPUT_DIR, "01_responses_mode_selected_diagnostics.png")
        page.screenshot(path=shot1_path, full_page=False)
        print(f"Captured: {shot1_path}")

        # -------------------------------------------------------------
        # 场景 2: sk-qwen-no-url-key (search_ok_no_url 提示语不矛盾)
        # -------------------------------------------------------------
        print("Testing Scenario 2: no url key (search_ok_no_url)...")
        key_input.fill("sk-qwen-no-url-key")
        time.sleep(1)
        test_btn.click()
        time.sleep(2)

        shot2_path = os.path.join(OUTPUT_DIR, "02_search_ok_no_url_responses_mode_banner.png")
        page.screenshot(path=shot2_path, full_page=False)
        print(f"Captured: {shot2_path}")

        # -------------------------------------------------------------
        # 场景 3: sk-qwen-source-parse-fail-key (source_parse_failed)
        # -------------------------------------------------------------
        print("Testing Scenario 3: source_parse_failed key...")
        key_input.fill("sk-qwen-source-parse-fail-key")
        time.sleep(1)
        test_btn.click()
        time.sleep(2)

        shot3_path = os.path.join(OUTPUT_DIR, "03_source_parse_failed_status.png")
        page.screenshot(path=shot3_path, full_page=False)
        print(f"Captured: {shot3_path}")

        # -------------------------------------------------------------
        # 场景 4: sk-qwen-no-tool-call-key (web_search_tool_not_called)
        # -------------------------------------------------------------
        print("Testing Scenario 4: web_search_tool_not_called key...")
        key_input.fill("sk-qwen-no-tool-call-key")
        time.sleep(1)
        test_btn.click()
        time.sleep(2)

        shot4_path = os.path.join(OUTPUT_DIR, "04_web_search_tool_not_called_status.png")
        page.screenshot(path=shot4_path, full_page=False)
        print(f"Captured: {shot4_path}")

        # -------------------------------------------------------------
        # 场景 5: sk-qwen-responses-not-applied-key (responses_mode_not_applied)
        # -------------------------------------------------------------
        print("Testing Scenario 5: responses_mode_not_applied key...")
        key_input.fill("sk-qwen-responses-not-applied-key")
        time.sleep(1)
        test_btn.click()
        time.sleep(2)

        shot5_path = os.path.join(OUTPUT_DIR, "05_responses_mode_not_applied_status.png")
        page.screenshot(path=shot5_path, full_page=False)
        print(f"Captured: {shot5_path}")

        # -------------------------------------------------------------
        # 场景 6: 修改配置即时重置测试状态 (例如切换网页提取器开关)
        # -------------------------------------------------------------
        print("Testing Scenario 6: immediate state reset on config change...")
        # 切换网页提取器开关或模型以触发即时状态清除
        extractor_chk = page.locator("label:has-text('挂载网页正文提取器')").first
        if extractor_chk.is_visible():
            extractor_chk.click()
            time.sleep(1.5)

        shot6_path = os.path.join(OUTPUT_DIR, "06_immediate_state_reset_on_config_change.png")
        page.screenshot(path=shot6_path, full_page=False)
        print(f"Captured: {shot6_path}")

        browser.close()
        print("All 6 screenshots successfully captured!")


if __name__ == "__main__":
    run()
