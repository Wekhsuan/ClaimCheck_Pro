# -*- coding: utf-8 -*-
"""Playwright 浏览器自动化验收脚本：千问搜索服务改造 (Qwen Provider Refactor Acceptance)

场景覆盖：
1. 01_qianwen_ai_platform.png: 千问AI平台预设、Base URL (maas...)、Responses API 模式与 qwen3.8-flash
2. 02_dashscope_platform.png: 阿里云百炼DashScope预设、Base URL (dashscope...)、Chat Completions 模式与 qwen-plus
3. 03_platform_mismatch_warning.png: 服务平台与 Key 不匹配防误配拦截与诊断提示 (platform_mismatch)
4. 04_responses_api_6dim_capabilities.png: Responses API 6维独立能力检测矩阵全部绿色展示
5. 05_search_ok_no_url_warning.png: 联网搜索有总结但无来源超链接的可追溯性降级警示 (search_ok_no_url)
6. 06_screenshot_vision_notice.png: 商品截图区多模态视觉模型支持与本地 OCR 降级提示
"""

import os
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from pathlib import Path
from playwright.sync_api import sync_playwright

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = str(WORKSPACE_ROOT / "screenshots" / "qwen_refactor")
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


def run_qwen_refactor_verification():
    with sync_playwright() as p:
        # 使用足够大的视口高度，确保设置抽屉与能力矩阵完整展示
        browser = p.chromium.launch(headless=True, channel="msedge")
        context = browser.new_context(viewport={"width": 1440, "height": 2200})
        page = context.new_page()

        print(">>> 导航至 ClaimCheck Pro 主页面...")
        page.goto(APP_URL, wait_until="networkidle", timeout=30000)
        time.sleep(2)

        # 展开服务设置抽屉
        print(">>> 展开服务模式与端点设置抽屉...")
        ensure_details_open(page, "服务模式与端点设置")
        time.sleep(1)

        # 选择 Qwen 搜索模式
        print(">>> 选择 Qwen 搜索模式...")
        click_radio_label(page, "Qwen 通义千问搜索")
        time.sleep(2)

        # -------------------------------------------------------------
        # 场景 A: 千问AI平台预设、Base URL、Responses API 与 qwen3.8-flash
        # -------------------------------------------------------------
        print(">>> 验证场景 A: 千问AI平台预设配置...")
        click_radio_label(page, "千问AI平台")
        time.sleep(1.5)

        shot_a_path = os.path.join(OUTPUT_DIR, "01_qianwen_ai_platform.png")
        page.screenshot(path=shot_a_path, full_page=False)
        print(f"  [OK] 场景 A 截图已保存: {shot_a_path}")

        # -------------------------------------------------------------
        # 场景 B: 阿里云百炼DashScope预设、Base URL、Chat Completions 与 qwen-plus
        # -------------------------------------------------------------
        print(">>> 验证场景 B: 切换为阿里云百炼 DashScope 平台...")
        click_radio_label(page, "阿里云百炼DashScope")
        time.sleep(2)

        shot_b_path = os.path.join(OUTPUT_DIR, "02_dashscope_platform.png")
        page.screenshot(path=shot_b_path, full_page=False)
        print(f"  [OK] 场景 B 截图已保存: {shot_b_path}")

        # -------------------------------------------------------------
        # 场景 C: 服务平台与 Key 不匹配防误配拦截
        # -------------------------------------------------------------
        print(">>> 验证场景 C: 输入平台不匹配测试 Key (sk-qwen-mismatch-platform-key)...")
        # 切换回千问AI平台
        click_radio_label(page, "千问AI平台")
        time.sleep(1.5)

        # 填入不匹配 Key 并测试
        key_input = page.locator("input[type='password']").last
        key_input.fill("sk-qwen-mismatch-platform-key")
        time.sleep(0.5)

        click_button_with_text(page, "测试 Qwen 千问搜索连接")
        time.sleep(2.5)

        shot_c_path = os.path.join(OUTPUT_DIR, "03_platform_mismatch_warning.png")
        page.screenshot(path=shot_c_path, full_page=False)
        print(f"  [OK] 场景 C 截图已保存: {shot_c_path}")

        # -------------------------------------------------------------
        # 场景 D: Responses API 6维独立能力检测矩阵全部绿色展示
        # -------------------------------------------------------------
        print(">>> 验证场景 D: 测试 Responses API 6维能力矩阵 (sk-qwen-test-success-key)...")
        key_input = page.locator("input[type='password']").last
        key_input.fill("sk-qwen-test-success-key")
        time.sleep(0.5)

        click_button_with_text(page, "测试 Qwen 千问搜索连接")
        time.sleep(2.5)

        shot_d_path = os.path.join(OUTPUT_DIR, "04_responses_api_6dim_capabilities.png")
        page.screenshot(path=shot_d_path, full_page=False)
        print(f"  [OK] 场景 D 截图已保存: {shot_d_path}")

        # -------------------------------------------------------------
        # 场景 E: 联网搜索有总结但无来源超链接的可追溯性降级警示
        # -------------------------------------------------------------
        print(">>> 验证场景 E: 测试无来源超链接的追溯降级警示 (sk-qwen-no-url-key)...")
        key_input = page.locator("input[type='password']").last
        key_input.fill("sk-qwen-no-url-key")
        time.sleep(0.5)

        click_button_with_text(page, "测试 Qwen 千问搜索连接")
        time.sleep(2.5)

        shot_e_path = os.path.join(OUTPUT_DIR, "05_search_ok_no_url_warning.png")
        page.screenshot(path=shot_e_path, full_page=False)
        print(f"  [OK] 场景 E 截图已保存: {shot_e_path}")

        # -------------------------------------------------------------
        # 场景 F: 商品截图区多模态视觉模型支持与本地 OCR 降级提示
        # -------------------------------------------------------------
        print(">>> 验证场景 F: 检查第一阶段商品宣传截图的多模态视觉提示...")
        key_input = page.locator("input[type='password']").last
        key_input.fill("sk-qwen-test-success-key")
        time.sleep(0.5)
        click_button_with_text(page, "测试 Qwen 千问搜索连接")
        time.sleep(2)

        # 切换到商品宣传截图输入模式
        click_radio_label(page, "商品宣传截图")
        time.sleep(1.5)

        shot_f_path = os.path.join(OUTPUT_DIR, "06_screenshot_vision_notice.png")
        page.screenshot(path=shot_f_path, full_page=False)
        print(f"  [OK] 场景 F 截图已保存: {shot_f_path}")

        browser.close()
        print(">>> 浏览器验收全部完成！")


if __name__ == "__main__":
    run_qwen_refactor_verification()
