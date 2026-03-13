"""
Browser AI Bridge v3 — navigazione umana REALE via Playwright.

Principi:
  • Solo servizi Google (no Cloudflare): AI Studio → Gemini web
  • page.mouse.move/click con traiettorie Bezier realistiche
  • Typing con variazione casuale per carattere (25-95ms)
  • Auto-accept privacy/terms Google
  • Nessun pyautogui: tutto via Playwright page.mouse / page.keyboard
  • Se Gemini API è disponibile, questo modulo NON viene usato
"""
import json
import logging
import math
import random
import time

logger = logging.getLogger("dust.browser_ai_bridge")

_NAV_MS   = 35_000   # timeout navigazione
_SEL_MS   = 15_000   # timeout selettore


# ── Utilità umane ─────────────────────────────────────────────────
def _bezier(t: float, p0, p1, p2, p3) -> tuple:
    """Punto su curva Bezier cubica."""
    u = 1 - t
    x = u**3*p0[0] + 3*u**2*t*p1[0] + 3*u*t**2*p2[0] + t**3*p3[0]
    y = u**3*p0[1] + 3*u**2*t*p1[1] + 3*u*t**2*p2[1] + t**3*p3[1]
    return round(x), round(y)


def _human_move(page, x: int, y: int, steps: int = 22):
    """
    Muove il mouse con traiettoria Bezier umana.
    Usa page.mouse (coordinate di pagina, sempre corrette).
    """
    cur = page.evaluate("() => ({x: window._dustMouseX||0, y: window._dustMouseY||0})")
    sx, sy = cur.get("x", 0), cur.get("y", 0)

    # Controlli Bezier randomizzati
    cx1 = sx + random.randint(-80, 80)
    cy1 = sy + random.randint(-60, 60)
    cx2 = x  + random.randint(-80, 80)
    cy2 = y  + random.randint(-60, 60)

    for i in range(steps + 1):
        t  = i / steps
        px, py = _bezier(t, (sx, sy), (cx1, cy1), (cx2, cy2), (x, y))
        page.mouse.move(px, py)
        time.sleep(random.uniform(0.008, 0.022))

    # Aggiorna posizione corrente via JS
    page.evaluate(f"() => {{ window._dustMouseX={x}; window._dustMouseY={y}; }}")


def _human_click(page, x: int, y: int, double: bool = False):
    """Click umano con micro-jitter."""
    jx = x + random.randint(-3, 3)
    jy = y + random.randint(-3, 3)
    _human_move(page, jx, jy)
    time.sleep(random.uniform(0.08, 0.22))
    if double:
        page.mouse.dblclick(jx, jy)
    else:
        page.mouse.click(jx, jy)
    time.sleep(random.uniform(0.05, 0.15))


def _human_type(page, text: str):
    """Digita testo con variazione realistica per carattere."""
    for i, ch in enumerate(text):
        page.keyboard.type(ch)
        # Pausa variabile: più lenta su caratteri speciali
        if ch in ".,!?;:":
            time.sleep(random.uniform(0.08, 0.18))
        elif ch == " ":
            time.sleep(random.uniform(0.04, 0.10))
        elif i % random.randint(8, 15) == 0:
            # Pausa "di pensiero" occasionale
            time.sleep(random.uniform(0.15, 0.40))
        else:
            time.sleep(random.uniform(0.025, 0.09))


def _human_scroll(page, delta_y: int = 300):
    """Scroll graduale."""
    steps = abs(delta_y) // 50
    direction = 1 if delta_y > 0 else -1
    for _ in range(steps):
        page.mouse.wheel(0, direction * 50)
        time.sleep(random.uniform(0.02, 0.06))


# ── Accept dialog ─────────────────────────────────────────────────
_ACCEPT_SELS = [
    "button:has-text('Accetta tutto')",
    "button:has-text('Accept all')",
    "button:has-text('Accetto')",
    "button:has-text('I agree')",
    "button:has-text('Continua')",
    "button:has-text('Continue')",
    "button:has-text('Agree')",
    "button:has-text('Got it')",
    "button:has-text('OK')",
    "button:has-text('Confirm')",
    "[data-action='accept']",
    "[aria-label*='Accept']",
    "[aria-label*='Accetta']",
    ".VfPpkd-LgbsSe:has-text('Accetta')",
    "form[action*='consent'] button",
]


def _accept_dialogs(page):
    """Clicca su tutti i dialog di accettazione presenti."""
    for _ in range(4):
        accepted = False
        for sel in _ACCEPT_SELS:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    box = el.bounding_box()
                    if box:
                        cx = int(box["x"] + box["width"]  / 2)
                        cy = int(box["y"] + box["height"] / 2)
                        _human_click(page, cx, cy)
                        logger.info(f"Auto-accept: {sel}")
                        time.sleep(1.2)
                        accepted = True
                        break
            except Exception:
                continue
        if not accepted:
            break


# ── Servizi (solo Google, no Cloudflare) ─────────────────────────
SERVICES = [
    {
        "name": "aistudio",
        "url":  "https://aistudio.google.com/app/prompts/new_chat",
        # Selettori in ordine di priorità
        "inputs": [
            "ms-chunk-input textarea",
            "textarea.message-input",
            ".prompt-textarea textarea",
            "textarea",
            "[contenteditable='true'][role='textbox']",
            "rich-textarea",
            "[contenteditable='true']",
        ],
        "outputs": [
            "ms-chat-turn[role='model'] .model-response-text",
            "ms-chat-turn:last-child .response-container",
            ".model-response-text",
            "ms-text-chunk",
            "[data-message-author-role='assistant']",
        ],
    },
    {
        "name": "gemini",
        "url":  "https://gemini.google.com/",
        "inputs": [
            "rich-textarea p",
            "rich-textarea div[contenteditable]",
            "[data-test-id='user-prompt']",
            "div.ql-editor",
            "[contenteditable='true']",
            "textarea",
        ],
        "outputs": [
            "message-content model-response",
            ".model-response-text",
            "div.response-content",
            "message-content",
            "[data-response-index]:last-child",
        ],
    },
]


class BrowserAIBridge:
    def __init__(self):
        self._pw      = None
        self._browser = None
        self._ctx     = None
        self._ready   = False

    # ── Setup ──────────────────────────────────────────────────────
    def _ensure(self):
        if self._ready:
            return
        from playwright.sync_api import sync_playwright

        self._pw      = sync_playwright().__enter__()
        self._browser = self._pw.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--disable-popup-blocking",
                "--start-maximized",
                "--disable-features=IsolateOrigins",
                "--disable-infobars",
            ],
            slow_mo=30,
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
        )
        self._ctx.add_init_script(_STEALTH_JS)
        self._ready = True

    def close(self):
        self._ready = False
        try:
            if self._browser:
                self._browser.close()
            if self._pw:
                self._pw.__exit__(None, None, None)
        except Exception:
            pass

    # ── Public ────────────────────────────────────────────────────
    def chat(self, messages: list[dict], timeout: int = 55) -> str:
        self._ensure()
        prompt = "\n".join(
            m.get("content", "") for m in messages if m.get("role") == "user"
        )

        for svc in SERVICES:
            try:
                logger.info(f"BrowserAI: provo {svc['name']}")
                ans = self._query(svc, prompt, timeout)
                if ans and len(ans) > 10:
                    return json.dumps({"type": "done", "message": ans})
            except Exception as exc:
                logger.warning(f"BrowserAI {svc['name']}: {exc}")
                continue

        raise RuntimeError("BrowserAI: nessun servizio disponibile.")

    # ── Core ──────────────────────────────────────────────────────
    def _query(self, svc: dict, prompt: str, timeout: int) -> str:
        page = self._ctx.new_page()
        try:
            # 1. Navigazione
            page.goto(svc["url"], wait_until="domcontentloaded", timeout=_NAV_MS)
            logger.info(f"  Navigato su {svc['name']}, attendo caricamento…")
            time.sleep(3)

            # 2. Auto-accept privacy/terms Google
            _accept_dialogs(page)

            # 3. Attendi che la pagina sia interattiva
            time.sleep(2)
            _accept_dialogs(page)   # secondo giro (cookie banner post-login)

            # 4. Trova il campo di input
            inp_el = self._find_input(page, svc["inputs"])
            if inp_el is None:
                raise RuntimeError(f"Input non trovato su {svc['name']}")

            # 5. Clicca sul campo input in modo umano
            box = inp_el.bounding_box()
            if box:
                cx = int(box["x"] + box["width"]  / 2)
                cy = int(box["y"] + box["height"] / 2)
                _human_click(page, cx, cy)
            else:
                inp_el.click()
            time.sleep(0.5)

            # 6. Cancella eventuale placeholder
            page.keyboard.press("Control+a")
            time.sleep(0.1)
            page.keyboard.press("Delete")
            time.sleep(0.2)

            # 7. Digita il prompt in modo umano
            _human_type(page, prompt)
            time.sleep(0.7)

            # 8. Invia (Enter)
            page.keyboard.press("Enter")
            logger.info(f"  Prompt inviato, attendo risposta (max {timeout}s)…")

            # 9. Attendi risposta stabile
            reply = self._wait_stable_reply(page, svc["outputs"], timeout)
            return reply

        finally:
            try:
                page.close()
            except Exception:
                pass

    # ── Input finder ──────────────────────────────────────────────
    def _find_input(self, page, selectors: list[str]):
        """Prova ogni selettore, restituisce il primo elemento visibile."""
        for sel in selectors:
            try:
                el = page.wait_for_selector(
                    sel, timeout=4_000, state="visible")
                if el:
                    logger.info(f"  Input trovato: {sel}")
                    return el
            except Exception:
                continue
        # Fallback: trova qualsiasi contenteditable
        try:
            els = page.query_selector_all("[contenteditable='true']")
            for el in els:
                if el.is_visible():
                    logger.info("  Input: contenteditable fallback")
                    return el
        except Exception:
            pass
        return None

    # ── Reply waiter ──────────────────────────────────────────────
    def _wait_stable_reply(self, page, selectors: list[str],
                           timeout: int) -> str:
        """
        Attende che la risposta smetta di crescere.
        2 letture identiche distanziate da 3s → risposta completa.
        """
        last   = ""
        stable = 0
        t0     = time.time()

        while time.time() - t0 < timeout:
            time.sleep(3)
            text = self._extract(page, selectors)
            if text and len(text) > 15:
                if text == last:
                    stable += 1
                    if stable >= 2:
                        logger.info(f"  Risposta stabile ({len(text)} chars)")
                        return text
                else:
                    stable = 0
                    last   = text
            # Scroll giù per stimolare il rendering
            _human_scroll(page, 200)

        return last

    def _extract(self, page, selectors: list[str]) -> str:
        for sel in selectors:
            try:
                els = page.query_selector_all(sel)
                if els:
                    txts = [e.text_content() or "" for e in els]
                    out  = " ".join(t.strip() for t in txts if t.strip())
                    if out:
                        return out
            except Exception:
                continue
        return ""


# ── Stealth JS ────────────────────────────────────────────────────
_STEALTH_JS = """
// Tracker posizione mouse per _human_move
window._dustMouseX = 0;
window._dustMouseY = 0;
document.addEventListener('mousemove', e => {
    window._dustMouseX = e.clientX;
    window._dustMouseY = e.clientY;
}, {passive: true});

// Maschera webdriver
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});

// Plugin realistici
Object.defineProperty(navigator, 'plugins', {
    get: () => [
        {name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer'},
        {name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai'},
        {name: 'Native Client',     filename: 'internal-nacl-plugin'},
    ]
});

// Lingue italiane
Object.defineProperty(navigator, 'languages', {
    get: () => ['it-IT', 'it', 'en-US', 'en']
});

// Permissions
const _origPerms = window.navigator.permissions.query.bind(navigator.permissions);
window.navigator.permissions.query = params =>
    params.name === 'notifications'
    ? Promise.resolve({state: Notification.permission})
    : _origPerms(params);

// Chrome runtime stub
if (!window.chrome) window.chrome = {};
window.chrome.runtime = window.chrome.runtime || {
    connect: () => ({onMessage: {addListener: ()=>{}}, postMessage: ()=>{}}),
    sendMessage: () => {}
};
"""
