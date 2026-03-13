"""
Browser AI Bridge — last-resort AI via interfacce web.

Strategie anti-rilevamento:
  • Playwright in modalità non-headless con stealth args
  • Fake user-agent + dimensioni finestra realistiche
  • Auto-accept Google privacy/terms (click su bottoni noti)
  • Auto-bypass Cloudflare: attesa + click sulla checkbox (pyautogui)
  • Servizi ordinati per facilità: AI Studio → Gemini → Perplexity

NON usa ChatGPT (Cloudflare enterprise troppo aggressivo).
"""
import json
import logging
import os
import re
import time

logger = logging.getLogger("dust.browser_ai_bridge")

# Timeout generosi per le pagine web
_NAV_TIMEOUT  = 30_000   # ms per goto
_SEL_TIMEOUT  = 12_000   # ms per wait_for_selector
_REPLY_WAIT   = 45       # secondi attesa risposta AI


# ── Selettori per ogni servizio ───────────────────────────────
SERVICES = {
    "aistudio": {
        "url": "https://aistudio.google.com/prompts/new_chat",
        "input_sel": "textarea, rich-textarea, [contenteditable='true']",
        "output_sel": "ms-chat-turn[role='model'] .model-response-text, "
                      ".response-container, ms-text-chunk",
        "submit_key": "Enter",
    },
    "gemini": {
        "url": "https://gemini.google.com/app",
        "input_sel": "rich-textarea p, rich-textarea, [contenteditable='true']",
        "output_sel": "message-content, model-response .response-content, "
                      ".model-response-text",
        "submit_key": "Enter",
    },
    "perplexity": {
        "url": "https://www.perplexity.ai/",
        "input_sel": "textarea[placeholder*='Ask'], textarea",
        "output_sel": ".prose, [class*='answer'], [data-testid='answer-text']",
        "submit_key": "Enter",
    },
}

# Bottoni "Accetta / Continua" comuni su Google
_ACCEPT_PATTERNS = [
    "button:has-text('Accetta tutto')",
    "button:has-text('Accept all')",
    "button:has-text('Accetto')",
    "button:has-text('I agree')",
    "button:has-text('Continua')",
    "button:has-text('Continue')",
    "button:has-text('Agree')",
    "button:has-text('Got it')",
    "button:has-text('OK')",
    "[aria-label*='Accept']",
    "[data-action='accept']",
]


class BrowserAIBridge:
    def __init__(self):
        self._pw      = None
        self._browser = None
        self._ctx     = None
        self._ready   = False

    # ── Lifecycle ─────────────────────────────────────────────
    def _ensure(self):
        if self._ready:
            return
        from playwright.sync_api import sync_playwright

        self._pw      = sync_playwright().__enter__()
        self._browser = self._pw.chromium.launch(
            headless=False,
            args=[
                # Stealth: maschera Playwright come browser normale
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--no-default-browser-check",
                "--no-first-run",
                "--disable-popup-blocking",
                "--start-maximized",
                "--window-size=1280,900",
                "--disable-web-security",        # per iframe captcha
                "--allow-running-insecure-content",
                "--disable-features=IsolateOrigins,site-per-process",
            ],
            slow_mo=50,   # rallenta le azioni per sembrare umano
        )
        self._ctx = self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="it-IT",
            timezone_id="Europe/Rome",
            # Maschera le proprietà navigator che identificano Playwright
            java_script_enabled=True,
            bypass_csp=True,
        )
        # ← Inietta script anti-fingerprint in ogni pagina
        self._ctx.add_init_script(_STEALTH_JS)
        self._ready = True

    def close(self):
        try:
            if self._browser:
                self._browser.close()
            if self._pw:
                self._pw.__exit__(None, None, None)
        except Exception:
            pass
        self._ready = False

    # ── Public API ────────────────────────────────────────────
    def chat(self, messages: list[dict], timeout: int = _REPLY_WAIT) -> str:
        self._ensure()
        prompt = self._format(messages)

        for svc_name, cfg in SERVICES.items():
            try:
                logger.info(f"BrowserAI: provo {svc_name}")
                result = self._query(svc_name, cfg, prompt, timeout)
                if result:
                    return json.dumps({"type": "done", "message": result})
            except Exception as exc:
                logger.warning(f"BrowserAI {svc_name}: {exc}")
                continue

        raise RuntimeError("Tutti i servizi BrowserAI non disponibili.")

    # ── Core query logic ──────────────────────────────────────
    def _query(self, svc_name: str, cfg: dict,
               prompt: str, timeout: int) -> str:
        page = self._ctx.new_page()
        try:
            # 1. Naviga
            page.goto(cfg["url"], wait_until="domcontentloaded",
                      timeout=_NAV_TIMEOUT)
            time.sleep(2.5)   # attesa rendering JS

            # 2. Auto-accept tutti i dialog (terms, privacy, cookies)
            self._accept_all(page)

            # 3. Gestisci Cloudflare se presente
            if self._is_cloudflare(page):
                logger.warning(f"{svc_name}: Cloudflare rilevato, provo bypass…")
                self._bypass_cloudflare(page)

            # 4. Trova input
            el = self._find_input(page, cfg["input_sel"])
            if el is None:
                raise RuntimeError("Input non trovato")

            # 5. Digita il prompt in modo umano
            el.click()
            time.sleep(0.4)
            self._human_type(page, el, prompt)
            time.sleep(0.6)
            page.keyboard.press(cfg["submit_key"])

            # 6. Attendi risposta
            reply = self._wait_reply(page, cfg["output_sel"], timeout)
            return reply

        finally:
            try:
                page.close()
            except Exception:
                pass

    # ── Input helpers ─────────────────────────────────────────
    def _find_input(self, page, selector: str):
        for sel in selector.split(", "):
            sel = sel.strip()
            try:
                el = page.wait_for_selector(sel, timeout=_SEL_TIMEOUT,
                                            state="visible")
                if el:
                    return el
            except Exception:
                continue
        return None

    def _human_type(self, page, el, text: str):
        """Digita testo con piccoli ritardi casuali per sembrare umano."""
        import random
        # Per testi lunghi usa clipboard (più veloce)
        if len(text) > 120:
            page.evaluate(
                "(text) => navigator.clipboard.writeText(text).catch(()=>{})",
                text,
            )
            el.focus()
            page.keyboard.press("Control+v")
        else:
            for char in text:
                el.type(char, delay=random.randint(25, 80))

    # ── Accept dialog helpers ─────────────────────────────────
    def _accept_all(self, page):
        """Clicca automaticamente su tutti i bottoni di accettazione noti."""
        for _ in range(3):    # cicla perché possono apparire più dialog
            clicked = False
            for pattern in _ACCEPT_PATTERNS:
                try:
                    btn = page.query_selector(pattern)
                    if btn and btn.is_visible():
                        btn.click()
                        logger.info(f"Auto-accept: {pattern}")
                        time.sleep(0.8)
                        clicked = True
                        break
                except Exception:
                    continue
            if not clicked:
                break

    # ── Cloudflare bypass ─────────────────────────────────────
    def _is_cloudflare(self, page) -> bool:
        """Controlla se siamo sulla challenge page di Cloudflare."""
        title = page.title().lower()
        content = page.content().lower()
        return (
            "just a moment" in title
            or "cloudflare" in content
            or "cf-challenge" in content
            or "checking your browser" in content
        )

    def _bypass_cloudflare(self, page):
        """
        Strategia Cloudflare:
        1. Attende che il challenge si risolva da solo (spesso auto-passa in 5s)
        2. Se non passa, cerca la checkbox "I am human" e ci clicca via pyautogui
        3. Attende fino a 30 secondi per il redirect
        """
        # Fase 1: attesa auto-risoluzione
        logger.info("Cloudflare: attendo auto-risoluzione (5s)…")
        time.sleep(5)
        if not self._is_cloudflare(page):
            logger.info("Cloudflare: risolto automaticamente ✓")
            return

        # Fase 2: cerca la checkbox interattiva
        logger.info("Cloudflare: cerco checkbox turnstile…")
        try:
            # Il iframe Cloudflare ha un titolo specifico
            iframe = None
            for frame in page.frames:
                if "challenge" in frame.url or "turnstile" in frame.url:
                    iframe = frame
                    break

            if iframe:
                cb = iframe.query_selector("input[type='checkbox'], .cb-lb")
                if cb:
                    box = cb.bounding_box()
                    if box:
                        # Centro del checkbox in coordinate assolute
                        cx = int(box["x"] + box["width"]  / 2)
                        cy = int(box["y"] + box["height"] / 2)
                        try:
                            import pyautogui
                            pyautogui.moveTo(cx, cy, duration=0.5)
                            time.sleep(0.3)
                            pyautogui.click(cx, cy)
                            logger.info(f"Cloudflare: click checkbox ({cx},{cy})")
                        except Exception as e:
                            logger.warning(f"pyautogui click failed: {e}")
        except Exception as exc:
            logger.warning(f"Cloudflare iframe search: {exc}")

        # Fase 3: attesa redirect
        for i in range(12):
            time.sleep(2.5)
            if not self._is_cloudflare(page):
                logger.info("Cloudflare: superato ✓")
                return
            logger.debug(f"Cloudflare: attendo… ({(i+1)*2.5:.0f}s)")

        logger.warning("Cloudflare: non superato, continuo comunque")

    # ── Reply helper ──────────────────────────────────────────
    def _wait_reply(self, page, output_sel: str, timeout: int) -> str:
        """
        Attende che la risposta AI smetta di crescere.
        Controlla ogni 3s se il testo cambia; dopo 2 controlli stabili → restituisce.
        """
        last_text = ""
        stable    = 0
        deadline  = time.time() + timeout

        while time.time() < deadline:
            time.sleep(3)
            text = self._extract_text(page, output_sel)
            if text and text == last_text and len(text) > 20:
                stable += 1
                if stable >= 2:
                    return text
            elif text:
                stable    = 0
                last_text = text

        return last_text or ""

    def _extract_text(self, page, selector: str) -> str:
        """Estrai testo dall'ultimo elemento trovato."""
        for sel in selector.split(", "):
            sel = sel.strip()
            try:
                els = page.query_selector_all(sel)
                if els:
                    texts = [e.text_content() or "" for e in els]
                    combined = " ".join(t.strip() for t in texts if t.strip())
                    if combined:
                        return combined
            except Exception:
                continue
        return ""

    # ── Utilities ─────────────────────────────────────────────
    @staticmethod
    def _format(messages: list[dict]) -> str:
        parts = []
        for m in messages:
            if m.get("role") == "user":
                parts.append(m.get("content", ""))
        return "\n".join(parts)


# ── Stealth JS (iniettato in ogni pagina) ────────────────────
_STEALTH_JS = """
// Maschera navigator.webdriver
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});

// Maschera Chrome automation
if (window.chrome) {
    window.chrome.runtime = window.chrome.runtime || {};
}

// Plugin array realistico
Object.defineProperty(navigator, 'plugins', {
    get: () => [
        {name: 'Chrome PDF Plugin'},
        {name: 'Chrome PDF Viewer'},
        {name: 'Native Client'},
    ]
});

// Lingua corretta
Object.defineProperty(navigator, 'languages', {
    get: () => ['it-IT', 'it', 'en-US', 'en']
});

// Permissions realistiche
const origQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) =>
    parameters.name === 'notifications'
    ? Promise.resolve({state: Notification.permission})
    : origQuery(parameters);
"""
