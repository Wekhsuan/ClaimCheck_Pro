import time
from pathlib import Path
from playwright.sync_api import sync_playwright

OUTPUT_DIR = Path(r"D:\ClaimCheck_Pro\screenshots\search_provider_phase2")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def capture_screenshots():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            channel="msedge"
        )
        context = browser.new_context(viewport={"width": 1366, "height": 950})
        page = context.new_page()

        print("Navigating to http://127.0.0.1:8501?mode=byok...")
        page.goto("http://127.0.0.1:8501?mode=byok", wait_until="networkidle")
        time.sleep(2)

        # 1. 展开设置抽屉
        print("Expanding settings drawer...")
        expander_header = page.locator("text=服务模式与端点设置")
        if expander_header.count() > 0:
            expander_header.first.click()
            time.sleep(1)

        # 2. 先切换到手动证据模式并添加一条合法参考资料
        print("Testing Manual Evidence UI...")
        manual_radio = page.locator("label:has-text('手动证据列表')")
        if manual_radio.count() > 0:
            manual_radio.first.click()
            time.sleep(1)

        m_url_input = page.locator("input[aria-label='证据页面 URL (仅限 HTTP/HTTPS)']")
        if m_url_input.count() > 0:
            m_url_input.first.fill("https://brand-audio.com/products/soundpro-x1/specs")
            m_title_input = page.locator("input[aria-label='材料名称/标题 (选填)']")
            m_title_input.first.fill("SoundPro X1 官方声学实验室规格参数")
            m_note_input = page.locator("input[aria-label='用户批注/关注点 (选填)']")
            m_note_input.first.fill("第3页表格标注最大降噪深度48dB")
            time.sleep(0.5)
            page.locator("button:has-text('添加到手动证据列表')").first.click()
            time.sleep(1.5)

        # 3. 再选择 Tavily 搜索模式，填写 API Key 并展示脱敏
        print("Selecting Tavily Search Mode...")
        tavily_radio = page.locator("label:has-text('Tavily 搜索')")
        if tavily_radio.count() > 0:
            tavily_radio.first.click()
            time.sleep(1)

        key_input = page.locator("input[aria-label='Tavily API Key (临时会话凭据)']")
        if key_input.count() > 0:
            key_input.first.fill("tvly-prod-demo-account-9A2B")
            key_input.first.press("Enter")
            time.sleep(1)

        # 截取设置抽屉与搜索配置界面
        page.evaluate("document.querySelector('main#stMain')?.scrollTo({top: 180, behavior: 'instant'});")
        time.sleep(1)
        screenshot1_path = OUTPUT_DIR / "01_search_settings_drawer.png"
        page.screenshot(path=str(screenshot1_path))
        print(f"Captured: {screenshot1_path}")

        # 4. 截取服务能力与边界隔离三卡片
        print("Scrolling to service boundary cards...")
        page.evaluate("document.querySelector('main#stMain')?.scrollTo({top: 550, behavior: 'instant'});")
        time.sleep(1)
        screenshot2_path = OUTPUT_DIR / "02_service_boundary_cards.png"
        page.screenshot(path=str(screenshot2_path))
        print(f"Captured: {screenshot2_path}")

        # 5. 展开调用预算详情并截取 preflight budget pill
        print("Scrolling to preflight budget pill...")
        page.evaluate("document.querySelector('main#stMain')?.scrollTo({top: 880, behavior: 'instant'});")
        time.sleep(1)
        budget_expander = page.locator("text=查看调用预算与防超额规则详情")
        if budget_expander.count() > 0:
            budget_expander.first.click()
            time.sleep(1)

        screenshot3_path = OUTPUT_DIR / "03_preflight_budget_pill.png"
        page.screenshot(path=str(screenshot3_path))
        print(f"Captured: {screenshot3_path}")

        browser.close()
        print("Browser screenshots updated successfully!")

if __name__ == "__main__":
    capture_screenshots()
