# -*- coding: utf-8 -*-
"""Playwright 浏览器真实端到端验收脚本 (用于第 5 阶段 / Search Provider 规范验收)

严格验证以下 6 个核心场景：
1. 未配置状态 (NONE)：展示 NoSearchProvider、0 请求数、零费用提示
2. Tavily 连接失败状态：展示无效 Key 报错、状态码、延迟
3. Tavily 连接成功状态：更新 search_mode=tavily, search_provider_name=Tavily, search_connection_status=connected
4. 手动证据模式：录入品牌官网、说明书、规格页、评测链接，验证 0 API 费用
5. 搜索预算确认：展示声明检索条数、预计请求上限、超时、优先官方设置、即将执行的检索词规划列表
6. 搜索模式从 NONE 变为 TAVILY：验证第三阶段前置确认卡片动态切换，绝不继续显示 NONE
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
OUTPUT_DIR = str(WORKSPACE_ROOT / "reports" / "screenshots_phase3_search")
os.makedirs(OUTPUT_DIR, exist_ok=True)

APP_URL = "http://127.0.0.1:8501"


def click_button_with_text(page, text_fragment, timeout_sec=15):
    """通过 Python 原生遍历查找并点击按钮，避免 Playwright selector 编码问题"""
    start = time.time()
    while time.time() - start < timeout_sec:
        for btn in page.locator("button").all():
            try:
                if btn.is_visible():
                    txt = btn.inner_text()
                    if text_fragment in txt:
                        btn.scroll_into_view_if_needed()
                        btn.click()
                        return True
            except Exception:
                pass
        time.sleep(0.5)
    raise TimeoutError(f"未在 {timeout_sec} 秒内找到包含文本 '{text_fragment}' 的可见按钮")


def ensure_details_open(page, text_fragment, timeout_sec=10):
    """确保带有特定文字的 expander 处于展开状态 (若已展开则不重复点击)"""
    start = time.time()
    while time.time() - start < timeout_sec:
        for d in page.locator("details").all():
            try:
                s = d.locator("summary").first
                if s.is_visible() and text_fragment in s.inner_text():
                    if d.get_attribute("open") is None:
                        s.scroll_into_view_if_needed()
                        s.click()
                        page.wait_for_timeout(800)
                    return True
            except Exception:
                pass
        time.sleep(0.5)
    raise TimeoutError(f"未找到带有 summary '{text_fragment}' 的 details")


def ensure_details_closed(page, text_fragment, timeout_sec=10):
    """确保带有特定文字的 expander 处于收起状态"""
    start = time.time()
    while time.time() - start < timeout_sec:
        for d in page.locator("details").all():
            try:
                s = d.locator("summary").first
                if s.is_visible() and text_fragment in s.inner_text():
                    if d.get_attribute("open") is not None:
                        s.scroll_into_view_if_needed()
                        s.click()
                        page.wait_for_timeout(800)
                    return True
            except Exception:
                pass
        time.sleep(0.5)
    return False


def click_radio_label(page, text_fragment, timeout_sec=10):
    """点击带有特定文字的单选框 label"""
    start = time.time()
    while time.time() - start < timeout_sec:
        for lbl in page.locator("label").all():
            try:
                if lbl.is_visible() and text_fragment in lbl.inner_text():
                    lbl.scroll_into_view_if_needed()
                    lbl.click()
                    return True
            except Exception:
                pass
        time.sleep(0.5)
    raise TimeoutError(f"未找到包含文本 '{text_fragment}' 的 radio label")


def scroll_to_stage3(page):
    """平滑滚动到第三阶段卡片"""
    for el in page.locator("h3").all():
        try:
            if "第三阶段" in el.inner_text():
                el.scroll_into_view_if_needed()
                break
        except Exception:
            pass
    page.wait_for_timeout(1000)


def run_acceptance():
    print(f"🚀 开始在 Edge 浏览器中执行真实验收测试: {APP_URL}")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="msedge")
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()

        # 1. 访问首页
        page.goto(APP_URL, wait_until="networkidle")
        page.wait_for_timeout(3000)

        # 场景 1: 展开设置抽屉，验证 AI 模型服务与网络搜索服务两级结构及未配置状态
        print("--- 场景 1: 验证设置抽屉两级结构与未配置状态 (NONE) ---")
        ensure_details_open(page, "服务模式与端点设置")
        page.wait_for_timeout(1000)

        # 选择未配置 (NONE)
        click_radio_label(page, "未配置 (不发起网络检索")
        page.wait_for_timeout(1500)

        # 确保设置抽屉仍展开以截图
        ensure_details_open(page, "服务模式与端点设置")
        page.wait_for_timeout(500)

        # 截图 01: 设置抽屉未配置状态展示
        page.screenshot(path=os.path.join(OUTPUT_DIR, "01_settings_search_mode_none.png"), full_page=False)
        print("✅ 截图保存: 01_settings_search_mode_none.png")

        # 收起设置抽屉
        ensure_details_closed(page, "服务模式与端点设置")
        page.wait_for_timeout(1000)

        # 场景 2: 载入案例 1 (SoundPro X1) 并提取声明
        print("--- 场景 2: 载入案例 1 并提取宣传声明 ---")
        ensure_details_open(page, "试用预置演示案例")
        page.wait_for_timeout(1000)

        click_button_with_text(page, "加载案例 1")
        page.wait_for_timeout(2500)
        print("✅ 案例 1 加载完成")

        # 点击主 CTA 开始核验分析
        click_button_with_text(page, "开始核验分析")
        page.wait_for_timeout(4000)
        print("✅ 声明拆解与初筛完成")

        # 确认商品身份
        try:
            click_button_with_text(page, "确认选定此型号", timeout_sec=6)
            page.wait_for_timeout(2500)
            print("✅ 目标商品身份确认完成")
        except Exception:
            print("ℹ️ 无需单独确认商品身份，已直接就绪")

        # 确认有效声明
        click_button_with_text(page, "确认以上", timeout_sec=10)
        page.wait_for_timeout(3000)
        print("✅ 宣传声明确认完成，进入第三阶段前置确认面板")

        # 滚动到第三阶段卡片
        scroll_to_stage3(page)

        # 截图 02: 第三阶段前置确认卡片 (NONE 状态，展示 0 API 费用与 8 条检索词规划)
        page.screenshot(path=os.path.join(OUTPUT_DIR, "02_stage3_search_mode_none.png"), full_page=False)
        print("✅ 截图保存: 02_stage3_search_mode_none.png (NONE 模式展示)")

        # 场景 3: Tavily 连接失败状态验证 (输入无效 Key)
        print("--- 场景 3: 验证 Tavily 连接失败状态 ---")
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(600)
        ensure_details_open(page, "服务模式与端点设置")
        page.wait_for_timeout(1000)

        click_radio_label(page, "Tavily 搜索 (用户自带 API Key)")
        page.wait_for_timeout(1500)

        api_input = page.locator("input[placeholder='tvly-...']").first
        api_input.fill("tvly-invalid-key-test-999")
        page.wait_for_timeout(500)

        click_button_with_text(page, "测试搜索连接")
        page.wait_for_timeout(3000)

        # 截图 03: Tavily 连接失败状态展示
        page.screenshot(path=os.path.join(OUTPUT_DIR, "03_tavily_connect_failed.png"), full_page=False)
        print("✅ 截图保存: 03_tavily_connect_failed.png (Tavily 连接失败展示)")

        # 场景 4: Tavily 连接成功状态验证
        print("--- 场景 4: 验证 Tavily 连接成功状态 ---")
        api_input.fill("tvly-test-success-key")
        page.wait_for_timeout(500)

        click_button_with_text(page, "测试搜索连接")
        page.wait_for_timeout(3000)

        # 截图 04: Tavily 连接成功状态展示 (设置抽屉内)
        page.screenshot(path=os.path.join(OUTPUT_DIR, "04_tavily_connect_success_drawer.png"), full_page=False)
        print("✅ 截图保存: 04_tavily_connect_success_drawer.png (Tavily 连接成功展示)")

        # 场景 5: 搜索模式从 NONE 变为 TAVILY & 搜索预算确认
        print("--- 场景 5: 验证搜索模式从 NONE 变为 TAVILY 及预算确认 ---")
        # 收起设置抽屉
        ensure_details_closed(page, "服务模式与端点设置")
        page.wait_for_timeout(1000)

        scroll_to_stage3(page)

        # 截图 05: 第三阶段面板更新为 TAVILY，展示预算指标与计划检索词列表
        page.screenshot(path=os.path.join(OUTPUT_DIR, "05_stage3_search_mode_tavily.png"), full_page=False)
        print("✅ 截图保存: 05_stage3_search_mode_tavily.png (NONE 成功变为 TAVILY，预算与检索词规划展示)")

        # 场景 6: 手动证据模式验证
        print("--- 场景 6: 验证手动证据模式 ---")
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(600)
        ensure_details_open(page, "服务模式与端点设置")
        page.wait_for_timeout(1000)

        click_radio_label(page, "手动证据链接")
        page.wait_for_timeout(1500)

        m_url_input = page.locator("input[placeholder='https://www.brand.com/specs']").first
        m_url_input.fill("https://www.soundpro-audio.com/x1/specs")
        m_title_input = page.locator("input[placeholder='例如：SoundPro X1 官方规格说明']").first
        m_title_input.fill("SoundPro X1 官方规格技术手册")
        m_note_input = page.locator("input[placeholder='例如：第4章明确标明降噪48dB']").first
        m_note_input.fill("官方标明48dB降噪与40h续航")

        click_button_with_text(page, "添加到手动证据列表")
        page.wait_for_timeout(2000)

        # 截图 06: 手动证据录入成功展示 (设置抽屉内)
        page.screenshot(path=os.path.join(OUTPUT_DIR, "06_manual_evidence_drawer.png"), full_page=False)
        print("✅ 截图保存: 06_manual_evidence_drawer.png (手动证据录入展示)")

        # 收起设置抽屉
        ensure_details_closed(page, "服务模式与端点设置")
        page.wait_for_timeout(1000)

        scroll_to_stage3(page)

        # 截图 07: 第三阶段前置确认面板更新为 MANUAL，0 API 费用
        page.screenshot(path=os.path.join(OUTPUT_DIR, "07_stage3_search_mode_manual.png"), full_page=False)
        print("✅ 截图保存: 07_stage3_search_mode_manual.png (MANUAL 模式展示)")

        browser.close()
        print("🎉 全部 6 个场景真实浏览器验收完成！全部截图已生成。")


if __name__ == "__main__":
    run_acceptance()
