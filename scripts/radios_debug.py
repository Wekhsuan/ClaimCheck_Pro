import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=True)
    page = b.new_page()
    page.goto("http://127.0.0.1:8501/?mode=byok&input_mode=text", wait_until="commit")
    page.wait_for_selector("[data-testid='stAppViewContainer']", timeout=20000)
    page.wait_for_selector("button", timeout=20000)
    import time
    time.sleep(2)
    labels = page.locator("[data-testid='stRadio'] label").all_text_contents()
    print("Radio labels found:", labels)
    textareas = page.locator("textarea").count()
    print("Textareas found:", textareas)
    buttons = page.locator("button").all_text_contents()
    print("Buttons found:", buttons)
    b.close()
