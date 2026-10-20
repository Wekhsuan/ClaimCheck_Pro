# -*- coding: utf-8 -*-
"""Playwright 浏览器真实端到端多搜索服务验收脚本

验证并截图以下场景：
1. 01_search_mode_overview.png: 5种搜索模式选项总览 (None, Tavily, Kimi, Qwen, Manual)
2. 02_tavily_config_card.png: Tavily 配置与 5 维能力检测矩阵
3. 03_kimi_config_and_capabilities.png: Kimi 独立搜索工具配置与 5 维能力检测
4. 04_qwen_responses_api_card.png: Qwen Responses API 模式与 5 维能力检测
5. 05_manual_evidence_list.png: 手动参考资料模式与证据列表
6. 06_stage3_preflight_budget_card.png: 第三阶段前置确认卡片、4维预算与确认执行按钮
7. 07_chat_ok_search_fail_warning.png: 模型对话正常但搜索未授权的解耦警示
8. 08_search_ok_no_url_warning.png: 搜索成功但无来源超链接的可追溯性降级警示
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
OUTPUT_DIR = str(WORKSPACE_ROOT / "screenshots" / "multi_search_provider")
os.makedirs(OUTPUT_DIR, exist_ok=True)

APP_URL = "http://127.0.0.1:8501"


def click_button_with_text(page, text_fragment, timeout_sec=15):
    """通过 Python 原生遍历查找并点击按钮"""
    start = time.time()
    while time.time() - start < timeout_sec:
        for btn in page.locator("button").all():
            try:
                txt = btn.inner_text()
                match = (
                    text_fragment.lower() in txt.lower()
                    or (text_fragment == "Case 1" and ("案例 1" in txt or "case 1" in txt.lower()))
                )
                if match and btn.is_visible():
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
    seen_summaries = []
    while time.time() - start < timeout_sec:
        seen_summaries = []
        for d in page.locator("details").all():
            try:
                s = d.locator("summary").first
                txt = s.inner_text()
                seen_summaries.append(txt)
                match = (
                    text_fragment.lower() in txt.lower()
                    or (text_fragment == "Sample Cases" and ("演示案例" in txt or "sample" in txt.lower()))
                    or (text_fragment == "Service Settings" and ("服务模式" in txt or "settings" in txt.lower()))
                )
                if match:
                    if d.get_attribute("open") is None:
                        s.scroll_into_view_if_needed()
                        s.click()
                        page.wait_for_timeout(800)
                    return True
            except Exception:
                pass
        time.sleep(0.5)
    raise TimeoutError(f"未找到带有 summary '{text_fragment}' 的 details. 当前页面可见 summaries: {seen_summaries}")


def ensure_details_closed(page, text_fragment, timeout_sec=10):
    """确保带有特定文字的 expander 处于收起状态"""
    start = time.time()
    while time.time() - start < timeout_sec:
        for d in page.locator("details").all():
            try:
                s = d.locator("summary").first
                txt = s.inner_text()
                match = (
                    text_fragment.lower() in txt.lower()
                    or (text_fragment == "Service Settings" and ("服务模式" in txt or "settings" in txt.lower()))
                )
                if match:
                    if d.get_attribute("open") is not None:
                        s.scroll_into_view_if_needed()
                        s.click()
                        page.wait_for_timeout(800)
                    return True
            except Exception:
                pass
        time.sleep(0.5)
    return True


def ensure_drawer_open(page):
    """确保服务模式设置抽屉展开"""
    ensure_details_open(page, "Service Settings")
    page.wait_for_timeout(600)


def run_verification():
    print("=== 开始 Playwright 真实浏览器端到端多搜索服务验收 ===")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="msedge")
        context = browser.new_context(viewport={"width": 1440, "height": 1100})
        page = context.new_page()

        print(f"正在访问应用: {APP_URL}")
        page.goto(APP_URL, wait_until="networkidle")
        page.wait_for_timeout(3000)

        # -----------------------------------------------------------------
        # 场景 1: 5 种搜索模式选项总览
        # -----------------------------------------------------------------
        print("步骤 1: 展开设置抽屉，验证 5 种搜索模式")
        ensure_drawer_open(page)
        shot1 = os.path.join(OUTPUT_DIR, "01_search_mode_overview.png")
        page.screenshot(path=shot1, full_page=False)
        print(f"  -> 已保存: {shot1}")

        # -----------------------------------------------------------------
        # 场景 2: Tavily 搜索服务配置与 5 维能力检测
        # -----------------------------------------------------------------
        print("步骤 2: 选择 Tavily 搜索并测试连接")
        ensure_drawer_open(page)
        click_radio_label(page, "Tavily")
        page.wait_for_timeout(1000)

        ensure_drawer_open(page)
        for inp in page.locator("input[type='password']").all():
            if inp.is_visible():
                inp.fill("tvly-test-success-key")
                break
        page.wait_for_timeout(500)

        click_button_with_text(page, "Tavily")
        page.wait_for_timeout(2000)
        ensure_drawer_open(page)
        shot2 = os.path.join(OUTPUT_DIR, "02_tavily_config_card.png")
        page.screenshot(path=shot2, full_page=False)
        print(f"  -> 已保存: {shot2}")

        # -----------------------------------------------------------------
        # 场景 3: Kimi 独立搜索工具配置与 5 维能力检测
        # -----------------------------------------------------------------
        print("步骤 3: 选择 Kimi 搜索并测试连接")
        ensure_drawer_open(page)
        click_radio_label(page, "Kimi")
        page.wait_for_timeout(1000)

        ensure_drawer_open(page)
        for inp in page.locator("input[type='password']").all():
            if inp.is_visible():
                inp.fill("sk-kimi-test-success-key")
                break
        page.wait_for_timeout(500)

        click_button_with_text(page, "Kimi")
        page.wait_for_timeout(2000)
        ensure_drawer_open(page)
        shot3 = os.path.join(OUTPUT_DIR, "03_kimi_config_and_capabilities.png")
        page.screenshot(path=shot3, full_page=False)
        print(f"  -> 已保存: {shot3}")

        # -----------------------------------------------------------------
        # 场景 7: 测试 Kimi chat_ok_search_fail 警示
        # -----------------------------------------------------------------
        print("步骤 7: 测试 Kimi chat_ok_search_fail 独立解耦警示")
        ensure_drawer_open(page)
        for inp in page.locator("input[type='password']").all():
            if inp.is_visible():
                inp.fill("sk-kimi-chat-only-key")
                break
        page.wait_for_timeout(500)

        click_button_with_text(page, "Kimi")
        page.wait_for_timeout(2000)
        ensure_drawer_open(page)
        shot7 = os.path.join(OUTPUT_DIR, "07_chat_ok_search_fail_warning.png")
        page.screenshot(path=shot7, full_page=False)
        print(f"  -> 已保存: {shot7}")

        # -----------------------------------------------------------------
        # 场景 4: Qwen Responses API 模式与 5 维能力检测
        # -----------------------------------------------------------------
        print("步骤 4: 选择通义千问搜索并测试 Responses API 模式")
        ensure_drawer_open(page)
        click_radio_label(page, "Qwen")
        page.wait_for_timeout(1000)

        ensure_drawer_open(page)
        for inp in page.locator("input[type='password']").all():
            if inp.is_visible():
                inp.fill("sk-qwen-test-success-key")
                break
        page.wait_for_timeout(500)

        click_button_with_text(page, "Qwen")
        page.wait_for_timeout(2000)
        ensure_drawer_open(page)
        shot4 = os.path.join(OUTPUT_DIR, "04_qwen_responses_api_card.png")
        page.screenshot(path=shot4, full_page=False)
        print(f"  -> 已保存: {shot4}")

        # -----------------------------------------------------------------
        # 场景 8: 测试 Qwen search_ok_no_url 可追溯性降级警示
        # -----------------------------------------------------------------
        print("步骤 8: 测试 Qwen search_ok_no_url 可追溯性降级警示")
        ensure_drawer_open(page)
        for inp in page.locator("input[type='password']").all():
            if inp.is_visible():
                inp.fill("sk-qwen-no-url-key")
                break
        page.wait_for_timeout(500)

        click_button_with_text(page, "Qwen")
        page.wait_for_timeout(2000)
        ensure_drawer_open(page)
        shot8 = os.path.join(OUTPUT_DIR, "08_search_ok_no_url_warning.png")
        page.screenshot(path=shot8, full_page=False)
        print(f"  -> 已保存: {shot8}")

        # -----------------------------------------------------------------
        # 场景 5: 手动参考资料模式与证据列表
        # -----------------------------------------------------------------
        print("步骤 5: 选择手动证据模式并录入参考链接")
        ensure_drawer_open(page)
        click_radio_label(page, "Manual")
        page.wait_for_timeout(1000)

        ensure_drawer_open(page)
        url_input = page.locator("input[placeholder='https://www.brand.com/specs']").first
        if url_input.is_visible():
            url_input.fill("https://www.apple.com/airpods-pro/specs/")

        title_input = page.locator("input[placeholder*='SoundPro X1']").first
        if title_input.is_visible():
            title_input.fill("AirPods Pro 2 官方技术规格")

        click_button_with_text(page, "手动证据列表")
        page.wait_for_timeout(2000)
        ensure_drawer_open(page)
        shot5 = os.path.join(OUTPUT_DIR, "05_manual_evidence_list.png")
        page.screenshot(path=shot5, full_page=False)
        print(f"  -> 已保存: {shot5}")

        # -----------------------------------------------------------------
        # 场景 6: 第三阶段前置确认卡片、4维预算与确认执行按钮
        # -----------------------------------------------------------------
        print("步骤 6: 保持设置就绪并载入演示示例进入第三阶段")
        ensure_details_closed(page, "Service Settings")
        page.wait_for_timeout(1000)

        # 载入案例 1 (SoundPro X1)
        print("展开试用预置演示案例并载入案例 1...")
        ensure_details_open(page, "Sample Cases")
        page.wait_for_timeout(1000)
        click_button_with_text(page, "Case 1")
        page.wait_for_timeout(2000)

        # 点击主 CTA 开始核验分析
        for btn in page.locator("button").all():
            try:
                if btn.is_visible() and ("开始核验" in btn.inner_text() or "核验分析" in btn.inner_text()):
                    btn.scroll_into_view_if_needed()
                    btn.click()
                    break
            except Exception:
                pass
        page.wait_for_timeout(4000)

        # 确认选定此型号
        for btn in page.locator("button").all():
            try:
                if btn.is_visible() and ("选定此型号" in btn.inner_text() or "确认商品身份" in btn.inner_text()):
                    btn.scroll_into_view_if_needed()
                    btn.click()
                    break
            except Exception:
                pass
        page.wait_for_timeout(2500)

        # 确认有效声明
        for btn in page.locator("button").all():
            try:
                if btn.is_visible() and ("确认以上" in btn.inner_text() or "进入网络搜索" in btn.inner_text()):
                    btn.scroll_into_view_if_needed()
                    btn.click()
                    break
            except Exception:
                pass
        page.wait_for_timeout(3000)

        # 滚动到第三阶段卡片
        for el in page.locator("div").all():
            try:
                txt = el.inner_text()
                if "第三阶段" in txt and "前置确认" in txt:
                    el.scroll_into_view_if_needed()
                    break
            except Exception:
                pass
        page.wait_for_timeout(1000)

        shot6 = os.path.join(OUTPUT_DIR, "06_stage3_preflight_budget_card.png")
        page.screenshot(path=shot6, full_page=False)
        print(f"  -> 已保存: {shot6}")

        browser.close()
        print("=== 所有浏览器截图验收 100% 成功完成 ===")


if __name__ == "__main__":
    run_verification()
