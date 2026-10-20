import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=True)
    page = b.new_page()
    page.goto("http://127.0.0.1:8501/?mode=byok&input_mode=text", wait_until="commit")
    page.wait_for_selector("[data-testid='stAppViewContainer']", timeout=20000)
    page.wait_for_selector("button", timeout=20000)
    scroll_els = page.evaluate("""() => {
        let els = Array.from(document.querySelectorAll('*')).filter(e => {
            const style = window.getComputedStyle(e);
            return (style.overflowY === 'auto' || style.overflowY === 'scroll') && e.scrollHeight > e.clientHeight;
        });
        return els.map(e => ({ tag: e.tagName, id: e.id, className: e.className, scrollHeight: e.scrollHeight }));
    }""")
    print("Scrollable elements:", scroll_els)
    b.close()
