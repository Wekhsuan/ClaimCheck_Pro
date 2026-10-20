# -*- coding: utf-8 -*-
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from playwright.sync_api import sync_playwright

def test():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="msedge")
        page = browser.new_page()
        page.goto("http://127.0.0.1:8501")
        page.wait_for_timeout(3000)

        # 展开案例抽屉
        for s in page.locator("summary").all():
            if s.is_visible() and "试用预置演示案例" in s.inner_text():
                s.click()
                break

        page.wait_for_timeout(1500)

        for btn in page.locator("button").all():
            if btn.is_visible() and "加载案例 1" in btn.inner_text():
                btn.click()
                print("Clicked 加载案例 1")
                break

        page.wait_for_timeout(3000)

        buttons = []
        for btn in page.locator("button").all():
            if btn.is_visible():
                txt = btn.inner_text().strip()
                buttons.append(txt)

        print("Visible buttons after loading case:", buttons)
        browser.close()

if __name__ == "__main__":
    test()
