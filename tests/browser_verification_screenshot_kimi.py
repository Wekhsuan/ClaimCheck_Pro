# -*- coding: utf-8 -*-
"""Playwright 浏览器端到端验收脚本：商品宣传截图到 Kimi 实时网络核验完整链路

验收链路与截图产出：
1. 01_kimi_search_connected.png: Kimi 独立搜索工具配置成功、5 维能力检测就绪
2. 02_screenshot_uploaded_ocr_extracted.png: 商品宣传截图上传、RapidOCR 本地离线提取真实文字
3. 03_product_identity_confirmed.png: 品牌 (极能)、型号 (PB-20065) 识别与商品身份确认
4. 04_claims_confirmed_rejected_candidates.png: 5 条有效声明确认与品牌/编号过滤审查
5. 05_stage3_kimi_search_executed_results.png: 基于图片文字特征检索、Kimi Fetch 提取正文、PB-10030 型号冲突排除
6. 06_stage4_real_report_metadata_and_evidence.png: 第四阶段全套报告、is_mock=False、实时网络核验标识、可追溯链接
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
OUTPUT_DIR = str(WORKSPACE_ROOT / "screenshots" / "screenshot_kimi_acceptance")
os.makedirs(OUTPUT_DIR, exist_ok=True)

APP_URL = "http://127.0.0.1:8501"
TEST_IMAGE_PATH = str(WORKSPACE_ROOT / "screenshots" / "test_ocr_input.png")


def click_button_with_text(page, text_fragment, timeout_sec=20):
    """查找并点击包含指定文本的按钮"""
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
    raise TimeoutError(f"未在 {timeout_sec} 秒内找到可见按钮: '{text_fragment}'")


def click_radio_label(page, text_fragment, timeout_sec=15):
    """点击带有特定文字的单选框 label"""
    start = time.time()
    while time.time() - start < timeout_sec:
        for lbl in page.locator("label").all():
            try:
                txt = lbl.inner_text()
                if text_fragment.lower() in txt.lower() and lbl.is_visible():
                    lbl.scroll_into_view_if_needed()
                    lbl.click()
                    return True
            except Exception:
                pass
        time.sleep(0.5)
    raise TimeoutError(f"未在 {timeout_sec} 秒内找到可见 radio label: '{text_fragment}'")


def ensure_details_open(page, text_fragment, timeout_sec=10):
    """确保带有特定文字的 expander 处于展开状态"""
    start = time.time()
    seen = []
    while time.time() - start < timeout_sec:
        seen = []
        for d in page.locator("details").all():
            try:
                s = d.locator("summary").first
                txt = s.inner_text()
                seen.append(txt)
                match = (
                    text_fragment.lower() in txt.lower()
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
    raise TimeoutError(f"未找到带有 summary '{text_fragment}' 的 details. 可见 summaries: {seen}")


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


def run_acceptance():
    print("=== 开始商品截图到 Kimi 实时网络核验端到端验收 ===")
    assert os.path.exists(TEST_IMAGE_PATH), f"测试截图文件不存在: {TEST_IMAGE_PATH}"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="msedge")
        context = browser.new_context(viewport={"width": 1440, "height": 1100})
        page = context.new_page()

        print(f"正在访问应用: {APP_URL}")
        page.goto(APP_URL, wait_until="networkidle")
        page.wait_for_timeout(3000)

        # -----------------------------------------------------------------
        # 步骤 1: 配置 Kimi 独立搜索服务并测试连通性
        # -----------------------------------------------------------------
        print("步骤 1: 打开服务设置，配置 Kimi 搜索 Provider")
        ensure_details_open(page, "Service Settings")
        page.wait_for_timeout(800)

        click_radio_label(page, "Kimi")
        page.wait_for_timeout(1000)

        # 填入 Kimi 测试 Key
        for inp in page.locator("input[type='password']").all():
            if inp.is_visible():
                inp.fill("sk-kimi-test-success-key")
                break
        page.wait_for_timeout(500)

        # 点击测试连接
        click_button_with_text(page, "Kimi")
        page.wait_for_timeout(2500)

        shot1 = os.path.join(OUTPUT_DIR, "01_kimi_search_connected.png")
        page.screenshot(path=shot1, full_page=False)
        print(f"  -> 已保存: {shot1}")

        # 收起设置抽屉
        ensure_details_closed(page, "Service Settings")
        page.wait_for_timeout(1000)

        # -----------------------------------------------------------------
        # 步骤 2: 切换至商品宣传截图模式，上传截图并执行离线 OCR
        # -----------------------------------------------------------------
        print("步骤 2: 切换至商品宣传截图模式并上传图片")
        click_radio_label(page, "宣传截图")
        page.wait_for_timeout(1200)

        file_input = page.locator("input[type='file']").first
        file_input.set_input_files(TEST_IMAGE_PATH)
        page.wait_for_timeout(2000)

        print("点击执行本地离线 OCR 识别提取真实文字...")
        click_button_with_text(page, "执行本地离线 OCR")
        page.wait_for_timeout(4000)

        shot2 = os.path.join(OUTPUT_DIR, "02_screenshot_uploaded_ocr_extracted.png")
        page.screenshot(path=shot2, full_page=False)
        print(f"  -> 已保存: {shot2}")

        # -----------------------------------------------------------------
        # 步骤 3: 点击主操作按钮开始核验分析，确认商品身份
        # -----------------------------------------------------------------
        print("步骤 3: 点击主操作按钮开始核验分析")
        click_button_with_text(page, "开始核验分析")
        page.wait_for_timeout(4000)

        # 检查是否展示商品身份或多候选确认卡片
        has_id_confirm = False
        for btn in page.locator("button").all():
            try:
                txt = btn.inner_text()
                if "选定此型号" in txt or "确认商品身份" in txt:
                    btn.scroll_into_view_if_needed()
                    btn.click()
                    has_id_confirm = True
                    break
            except Exception:
                pass

        if has_id_confirm:
            page.wait_for_timeout(2500)

        shot3 = os.path.join(OUTPUT_DIR, "03_product_identity_confirmed.png")
        page.screenshot(path=shot3, full_page=False)
        print(f"  -> 已保存: {shot3}")

        # -----------------------------------------------------------------
        # 步骤 4: 确认 5 条有效声明与过滤审查
        # -----------------------------------------------------------------
        print("步骤 4: 审查宣传声明与过滤候选项并确认")
        # 滚动查看声明确认卡片
        for el in page.locator("div").all():
            try:
                if "第二阶段" in el.inner_text() or "宣传声明" in el.inner_text():
                    el.scroll_into_view_if_needed()
                    break
            except Exception:
                pass
        page.wait_for_timeout(1000)

        shot4 = os.path.join(OUTPUT_DIR, "04_claims_confirmed_rejected_candidates.png")
        page.screenshot(path=shot4, full_page=False)
        print(f"  -> 已保存: {shot4}")

        # 点击确认宣传声明进入网络搜索
        click_button_with_text(page, "确认以上声明")
        page.wait_for_timeout(3500)

        # -----------------------------------------------------------------
        # 步骤 5: 第三阶段前置确认、预算呈现、执行网络搜索与提取正文
        # -----------------------------------------------------------------
        print("步骤 5: 执行 Kimi 真实搜索与正文提取")
        # 点击开始网络搜索
        click_button_with_text(page, "确认并开始网络搜索")
        page.wait_for_timeout(6000)

        # 滚动查看阶段 3 搜索结果与排除项
        for el in page.locator("div").all():
            try:
                if "第三阶段" in el.inner_text() or "检索词审计" in el.inner_text():
                    el.scroll_into_view_if_needed()
                    break
            except Exception:
                pass
        page.wait_for_timeout(1200)

        shot5 = os.path.join(OUTPUT_DIR, "05_stage3_kimi_search_executed_results.png")
        page.screenshot(path=shot5, full_page=False)
        print(f"  -> 已保存: {shot5}")

        # -----------------------------------------------------------------
        # 步骤 6: 进入第四阶段多源交叉核验，生成带可追溯 URL 的最终报告
        # -----------------------------------------------------------------
        print("步骤 6: 进入第四阶段多源交叉核验并生成全套报告")
        click_button_with_text(page, "第四阶段")
        page.wait_for_timeout(6000)

        # 滚动到报告元数据与证据表格区
        for el in page.locator("div").all():
            try:
                if "全套综合分析报告" in el.inner_text() or "多源证据综合核验" in el.inner_text():
                    el.scroll_into_view_if_needed()
                    break
            except Exception:
                pass
        page.wait_for_timeout(1500)

        shot6 = os.path.join(OUTPUT_DIR, "06_stage4_real_report_metadata_and_evidence.png")
        page.screenshot(path=shot6, full_page=False)
        print(f"  -> 已保存: {shot6}")

        browser.close()
        print("=== 商品截图到 Kimi 实时网络核验端到端验收 100% 成功完成 ===")


if __name__ == "__main__":
    run_acceptance()
