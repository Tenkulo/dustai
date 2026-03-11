"""
DUST AI – BrowserTool v2.0
Automazione browser tramite Playwright (Chromium).
"""
import logging
from typing import Optional

log = logging.getLogger("BrowserTool")


class BrowserTool:
    def __init__(self, config):
        self.config   = config
        self._browser = None
        self._page    = None
        self._pw      = None

    def _ensure_browser(self) -> Optional[str]:
        if self._page and not self._page.is_closed():
            return None
        try:
            from playwright.sync_api import sync_playwright
            self._pw      = sync_playwright().start()
            headless      = self.config.get("tools", {}).get("browser", {}).get("headless", False)
            self._browser = self._pw.chromium.launch(headless=headless)
            self._page    = self._browser.new_page()
            self._page.set_default_timeout(15000)
            return None
        except ImportError:
            return "❌ Playwright non installato: python -m playwright install chromium"
        except Exception as e:
            return "❌ Browser setup: " + str(e)

    def browser_open(self, url: str) -> str:
        err = self._ensure_browser()
        if err:
            return err
        try:
            if not url.startswith("http"):
                url = "https://" + url
            self._page.goto(url, wait_until="domcontentloaded", timeout=20000)
            return "✅ Aperto: " + self._page.title() + " | " + url
        except Exception as e:
            return "❌ browser_open: " + str(e)

    def browser_click(self, selector: str = "", text: str = "") -> str:
        err = self._ensure_browser()
        if err:
            return err
        try:
            if text:
                self._page.get_by_text(text, exact=False).first.click()
                return "✅ Click su testo: " + text
            elif selector:
                self._page.click(selector)
                return "✅ Click su: " + selector
            return "❌ Fornire selector o text"
        except Exception as e:
            return "❌ browser_click: " + str(e)

    def browser_type(self, selector: str, text: str) -> str:
        err = self._ensure_browser()
        if err:
            return err
        try:
            self._page.fill(selector, text)
            return "✅ Digitato in '" + selector + "': " + text[:50]
        except Exception as e:
            return "❌ browser_type: " + str(e)

    def browser_get_text(self, selector: str = "body") -> str:
        err = self._ensure_browser()
        if err:
            return err
        try:
            text = self._page.text_content(selector) or ""
            return text[:2000]
        except Exception as e:
            return "❌ browser_get_text: " + str(e)

    def browser_screenshot(self, path: str = "") -> str:
        err = self._ensure_browser()
        if err:
            return err
        try:
            if not path:
                from datetime import datetime
                path = str(self.config.get_screenshots_dir() /
                           ("browser_" + datetime.now().strftime("%H%M%S") + ".png"))
            self._page.screenshot(path=path, full_page=False)
            return "✅ Screenshot browser: " + path
        except Exception as e:
            return "❌ browser_screenshot: " + str(e)

    def __del__(self):
        try:
            if self._browser:
                self._browser.close()
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
