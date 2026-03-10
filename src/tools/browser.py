"""
DUST AI – Tool: browser
Controllo browser via Playwright: apri URL, click, digita, screenshot, leggi testo.
Installa: pip install playwright && playwright install chromium
"""
import logging
import base64
from pathlib import Path


class BrowserTool:
    def __init__(self, config):
        self.config = config
        self.log = logging.getLogger("BrowserTool")
        self._browser = None
        self._page = None
        self._playwright = None
        self._available = self._check_availability()

    def _check_availability(self) -> bool:
        try:
            import playwright
            return True
        except ImportError:
            self.log.warning("Playwright non installato. Esegui: pip install playwright && playwright install chromium")
            return False

    def _ensure_browser(self):
        """Avvia il browser se non è già aperto."""
        if self._page and not self._page.is_closed():
            return

        from playwright.sync_api import sync_playwright
        self._playwright = sync_playwright().start()
        headless = self.config.get("tools", {}).get("browser", {}).get("headless", False)
        self._browser = self._playwright.chromium.launch(headless=headless)
        self._page = self._browser.new_page()
        self.log.info("Browser avviato")

    def browser_open(self, url: str, wait_ms: int = 2000) -> str:
        """Apre un URL nel browser."""
        if not self._available:
            return "❌ Playwright non disponibile. pip install playwright && playwright install chromium"
        try:
            self._ensure_browser()
            self._page.goto(url, timeout=30000)
            self._page.wait_for_timeout(wait_ms)
            title = self._page.title()
            return f"✅ Aperto: {url}\nTitolo: {title}"
        except Exception as e:
            return f"❌ Errore apertura browser: {e}"

    def browser_click(self, selector: str = None, text: str = None, x: int = None, y: int = None) -> str:
        """Clicca su un elemento per selector CSS, testo o coordinate."""
        if not self._page:
            return "❌ Browser non aperto. Usa browser_open prima."
        try:
            if selector:
                self._page.click(selector, timeout=10000)
                return f"✅ Click su: {selector}"
            elif text:
                self._page.get_by_text(text).first.click(timeout=10000)
                return f"✅ Click su testo: {text}"
            elif x is not None and y is not None:
                self._page.mouse.click(x, y)
                return f"✅ Click su coordinate: ({x}, {y})"
            return "❌ Specifica selector, text o coordinate x,y"
        except Exception as e:
            return f"❌ Errore click: {e}"

    def browser_type(self, selector: str, text: str, clear_first: bool = True) -> str:
        """Digita testo in un campo."""
        if not self._page:
            return "❌ Browser non aperto."
        try:
            el = self._page.locator(selector).first
            if clear_first:
                el.fill(text)
            else:
                el.type(text)
            return f"✅ Digitato '{text[:50]}' in: {selector}"
        except Exception as e:
            return f"❌ Errore digitazione: {e}"

    def browser_get_text(self, selector: str = "body") -> str:
        """Ottiene il testo visibile della pagina o di un elemento."""
        if not self._page:
            return "❌ Browser non aperto."
        try:
            text = self._page.locator(selector).inner_text(timeout=5000)
            # Limita output
            return text[:3000] + "..." if len(text) > 3000 else text
        except Exception as e:
            return f"❌ Errore get_text: {e}"

    def browser_screenshot(self, save_path: str = None) -> str:
        """Scatta uno screenshot della pagina corrente."""
        if not self._page:
            return "❌ Browser non aperto."
        try:
            if not save_path:
                screenshots_dir = self.config.get_workdir() / "screenshots"
                screenshots_dir.mkdir(exist_ok=True)
                save_path = str(screenshots_dir / "screenshot.png")

            self._page.screenshot(path=save_path, full_page=False)
            return f"✅ Screenshot salvato: {save_path}"
        except Exception as e:
            return f"❌ Errore screenshot: {e}"

    def __del__(self):
        """Chiudi browser alla fine."""
        try:
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
