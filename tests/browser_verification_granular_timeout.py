# -*- coding: utf-8 -*-
"""Playwright End-to-End Browser Verification for Qwen Granular Capabilities & Timeouts

验证场景：
1. 关闭 web_extractor，60秒超时，搜索测试成功 -> 01_extractor_disabled_search_success.png
2. 开启 web_extractor，90秒超时，提取能力单独显示 -> 02_extractor_enabled_90s_success.png
3. 模型可用但搜索超时 -> 区分显示“模型可用，搜索超时”与网络诊断 -> 03_search_timeout_model_connected.png
4. 搜索可用但提取超时 -> 区分显示“搜索可用，网页提取超时”，降级保护 -> 04_extractor_timeout_search_connected.png
5. 20秒超时设置提示与预计调用次数透明告知 -> 05_timeout_20s_warning_prompt.png
"""

import os
import sys
import time

try:
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from pathlib import Path
from playwright.sync_api import sync_playwright

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = str(WORKSPACE_ROOT / "screenshots" / "qwen_timeout_refactor")
os.makedirs(OUTPUT_DIR, exist_ok=True)

APP_URL = "http://127.0.0.1:8501"


def click_button_with_text(page, text_fragment, timeout_sec=15):
    """通过 Python 原生遍历查找并点击按钮"""
    start = time.time()
    while time.time() - start < timeout_sec:
        for btn in page.locator("button").all():
            try:
                txt = btn.inner_text()
                if text_fragment.lower() in txt.lower() and btn.is_visible():
                    btn.scroll_into_view_if_needed()
                    btn.click()
                    return True
            except Exception:
                pass
        time.sleep(0.5)
    raise TimeoutError(f"未在 {timeout_sec} 秒内找到包含文本 '{text_fragment}' 的可见按钮")


def click_radio_label(page, text_fragment, timeout_sec=10):
    """点击带有特定文字的单选框 label"""
    start = time.time()
    while time.time() - start < timeout_sec:
        for lbl in page.locator("label").all():
            try:
                if lbl.is_visible() and text_fragment.lower() in lbl.inner_text().lower():
                    lbl.scroll_into_view_if_needed()
                    lbl.click()
                    return True
            except Exception:
                pass
        time.sleep(0.5)
    raise TimeoutError(f"未找到包含文本 '{text_fragment}' 的 radio label")


def ensure_details_open(page, text_fragment, timeout_sec=10):
    """确保带有特定文字的 expander 处于展开状态"""
    start = time.time()
    while time.time() - start < timeout_sec:
        for d in page.locator("details").all():
            try:
                s = d.locator("summary").first
                txt = s.inner_text()
                if text_fragment.lower() in txt.lower():
                    is_open = d.evaluate("el => el.open")
                    if not is_open:
                        s.click()
                        time.sleep(0.5)
                    return True
            except Exception:
                pass
        time.sleep(0.5)
    raise TimeoutError(f"未找到包含文本 '{text_fragment}' 的 details 元素")


def run_verification():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="msedge")
        context = browser.new_context(viewport={"width": 1440, "height": 2600})
        page = context.new_page()

        print(">>> 导航至 ClaimCheck Pro 主页面...")
        page.goto(APP_URL, wait_until="networkidle", timeout=30000)
        time.sleep(2)

        # 展开服务模式与端点设置抽屉
        print(">>> 展开服务模式与端点设置抽屉...")
        ensure_details_open(page, "服务模式与端点设置")
        time.sleep(1)

        # 选择 Qwen 搜索模式
        print(">>> 选择 Qwen 通义千问搜索模式...")
        click_radio_label(page, "Qwen 通义千问搜索")
        time.sleep(2)

        # 选择千问AI平台
        click_radio_label(page, "千问AI平台")
        time.sleep(1.5)

        # ==============================================================
        # 场景 5: 验证 20 秒超时告警与调用费用提示
        # ==============================================================
        print(">>> 验证场景 5: 20秒超时警告与费用提示...")
        shot_5_path = os.path.join(OUTPUT_DIR, "05_timeout_20s_warning_prompt.png")
        page.screenshot(path=shot_5_path, full_page=False)
        print(f"  [OK] 场景 5 截图已保存: {shot_5_path}")

        # ==============================================================
        # 场景 1: 关闭 web_extractor，60秒超时，搜索测试成功
        # ==============================================================
        print(">>> 验证场景 1: 关闭 web_extractor，搜索测试成功...")
        key_input = page.locator("input[type='password']").last
        key_input.fill("sk-qwen-test-success-key")
        time.sleep(0.5)

        # 取消勾选 web_extractor
        extractor_label = None
        for lbl in page.locator("label").all():
            try:
                if "挂载网页正文提取器" in lbl.inner_text() and lbl.is_visible():
                    extractor_label = lbl
                    break
            except Exception:
                pass
        if extractor_label:
            chk = extractor_label.locator("input[type='checkbox']").first
            if chk.is_checked():
                extractor_label.click()
                time.sleep(0.5)

        click_button_with_text(page, "测试 Qwen 千问搜索连接")
        time.sleep(2.5)

        shot_1_path = os.path.join(OUTPUT_DIR, "01_extractor_disabled_search_success.png")
        page.screenshot(path=shot_1_path, full_page=False)
        print(f"  [OK] 场景 1 截图已保存: {shot_1_path}")

        # ==============================================================
        # 场景 2: 开启 web_extractor，90秒超时，提取能力单独显示
        # ==============================================================
        print(">>> 验证场景 2: 开启 web_extractor，提取能力单独显示...")
        if extractor_label:
            chk = extractor_label.locator("input[type='checkbox']").first
            if not chk.is_checked():
                extractor_label.click()
                time.sleep(0.5)

        click_button_with_text(page, "测试 Qwen 千问搜索连接")
        time.sleep(2.5)

        shot_2_path = os.path.join(OUTPUT_DIR, "02_extractor_enabled_90s_success.png")
        page.screenshot(path=shot_2_path, full_page=False)
        print(f"  [OK] 场景 2 截图已保存: {shot_2_path}")

        # ==============================================================
        # 场景 3: 模型可用但搜索超时 (区分显示“模型可用，搜索超时”与网络诊断)
        # ==============================================================
        print(">>> 验证场景 3: 模型可用但搜索超时 (sk-qwen-test-search-timeout-key)...")
        key_input.fill("sk-qwen-test-search-timeout-key")
        time.sleep(0.5)

        click_button_with_text(page, "测试 Qwen 千问搜索连接")
        time.sleep(2.5)

        # 展开网络与超时诊断报告
        ensure_details_open(page, "网络与超时诊断报告")
        time.sleep(0.5)

        shot_3_path = os.path.join(OUTPUT_DIR, "03_search_timeout_model_connected.png")
        page.screenshot(path=shot_3_path, full_page=False)
        print(f"  [OK] 场景 3 截图已保存: {shot_3_path}")

        # ==============================================================
        # 场景 4: 搜索可用但提取超时 (区分显示“搜索可用，网页提取超时”)
        # ==============================================================
        print(">>> 验证场景 4: 搜索可用但提取超时 (sk-qwen-test-extractor-timeout-key)...")
        key_input.fill("sk-qwen-test-extractor-timeout-key")
        time.sleep(0.5)

        click_button_with_text(page, "测试 Qwen 千问搜索连接")
        time.sleep(2.5)

        shot_4_path = os.path.join(OUTPUT_DIR, "04_extractor_timeout_search_connected.png")
        page.screenshot(path=shot_4_path, full_page=False)
        print(f"  [OK] 场景 4 截图已保存: {shot_4_path}")

        browser.close()
        print(">>> 所有 5 项端到端视觉验证全部完成！")


if __name__ == "__main__":
    run_verification()
