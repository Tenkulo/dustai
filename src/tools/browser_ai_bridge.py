"""Browser AI Bridge: Gemini web / ChatGPT web via Playwright (last-resort AI fallback)."""
import json
import logging
import time

logger = logging.getLogger("dust.browser_ai_bridge")


class BrowserAIBridge:
    """Use web-based AI UIs when all API quotas are exhausted."""

    SERVICES = ["gemini_web", "chatgpt_web"]

    def __init__(self):
        self._pw      = None
        self._browser = None
        self._ctx     = None

    # ── Browser lifecycle ────────────────────────────────────
    def _ensure(self):
        if self._browser is not None:
            return
        from playwright.sync_api import sync_playwright
        self._pw      = sync_playwright().__enter__()
        self._browser = self._pw.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled",
                  "--start-maximized"],
        )
        self._ctx = self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
        )

    def close(self):
        try:
            if self._browser:
                self._browser.close()
            if self._pw:
                self._pw.__exit__(None, None, None)
        except Exception:
            pass

    # ── Public API ───────────────────────────────────────────
    def chat(self, messages: list[dict], timeout: int = 45) -> str:
        self._ensure()
        prompt = self._format(messages)
        for svc in self.SERVICES:
            try:
                if svc == "gemini_web":
                    return self._gemini(prompt, timeout)
                elif svc == "chatgpt_web":
                    return self._chatgpt(prompt, timeout)
            except Exception as exc:
                logger.warning(f"BrowserAI {svc}: {exc}")
        raise RuntimeError("Tutti i servizi BrowserAI non disponibili.")

    @staticmethod
    def _format(messages: list[dict]) -> str:
        return "\n".join(
            m.get("content", "") for m in messages if m.get("role") == "user"
        )

    # ── Gemini web ───────────────────────────────────────────
    def _gemini(self, prompt: str, timeout: int) -> str:
        page = self._ctx.new_page()
        try:
            page.goto("https://gemini.google.com/app", wait_until="networkidle", timeout=20_000)
            time.sleep(2)
            sel = "rich-textarea, textarea, [contenteditable='true']"
            page.wait_for_selector(sel, timeout=8_000)
            el = page.query_selector(sel)
            if not el:
                raise RuntimeError("Input non trovato")
            el.click()
            el.type(prompt, delay=18)
            page.keyboard.press("Enter")
            time.sleep(min(timeout, 30))
            els = page.query_selector_all("message-content, .response-content, model-response")
            if els:
                text = els[-1].text_content().strip()
                return json.dumps({"type": "done", "message": text})
            raise RuntimeError("Risposta non trovata")
        finally:
            page.close()

    # ── ChatGPT web ──────────────────────────────────────────
    def _chatgpt(self, prompt: str, timeout: int) -> str:
        page = self._ctx.new_page()
        try:
            page.goto("https://chat.openai.com", wait_until="networkidle", timeout=20_000)
            time.sleep(2)
            ta = page.wait_for_selector("textarea#prompt-textarea", timeout=8_000)
            if not ta:
                raise RuntimeError("Textarea non trovata")
            ta.click(); ta.type(prompt, delay=18)
            page.keyboard.press("Enter")
            time.sleep(min(timeout, 35))
            msgs = page.query_selector_all("[data-message-author-role='assistant']")
            if msgs:
                text = msgs[-1].text_content().strip()
                return json.dumps({"type": "done", "message": text})
            raise RuntimeError("Risposta non trovata")
        finally:
            page.close()
