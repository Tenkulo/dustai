"""
Browser AI Bridge v4 — profilo Playwright persistente.

COME FUNZIONA:
  • Al primo avvio apre Chrome e aspetta che l'utente faccia login a Google
  • La sessione viene salvata in A:\\dustai_stuff\\browser_profile
  • Tutti i run successivi: già loggati, AI Studio funziona subito
  • Playwright CSS locator piercea shadow DOM automaticamente
  • Mouse/tastiera con movimenti Bezier umani

SETUP PRIMA VOLTA:
  1. DUST apre Chrome con profilo vuoto
  2. Naviga su aistudio.google.com/app/prompts/new_chat
  3. Utente fa login Google manualmente
  4. Chiude la finestra
  5. Tutti i run successivi funzionano in automatico
"""
import json
import logging
import math
import os
import random
import time
from pathlib import Path

logger = logging.getLogger("dust.browser_ai_bridge")

try:
    from config import BROWSER_PROFILE_DIR, STUFF_PATH
    PROFILE_DIR = Path(BROWSER_PROFILE_DIR)
except ImportError:
    PROFILE_DIR = Path(r"A:\dustai_stuff\browser_profile")

PROFILE_DIR.mkdir(parents=True, exist_ok=True)

_FLAG_LOGGED_IN = PROFILE_DIR / ".google_logged_in"   # marker file

_NAV_MS  = 40_000
_SEL_MS  = 20_000


# ── Movimenti umani ───────────────────────────────────────────────
def _bezier(t, p0, p1, p2, p3):
    u = 1 - t
    x = u**3*p0[0]+3*u**2*t*p1[0]+3*u*t**2*p2[0]+t**3*p3[0]
    y = u**3*p0[1]+3*u**2*t*p1[1]+3*u*t**2*p2[1]+t**3*p3[1]
    return round(x), round(y)


def _human_move(page, x: int, y: int, steps: int = 20):
    cur = page.evaluate(
        "() => ({x: window._dmx||640, y: window._dmy||400})")
    sx, sy = cur.get("x",640), cur.get("y",400)
    cx1 = sx + random.randint(-100, 100)
    cy1 = sy + random.randint(-80, 80)
    cx2 =  x + random.randint(-100, 100)
    cy2 =  y + random.randint(-80, 80)
    for i in range(steps+1):
        px, py = _bezier(i/steps, (sx,sy),(cx1,cy1),(cx2,cy2),(x,y))
        page.mouse.move(px, py)
        time.sleep(random.uniform(0.006, 0.018))
    page.evaluate(f"()=>{{window._dmx={x};window._dmy={y};}}")


def _human_click(page, x: int, y: int):
    jx = x + random.randint(-2, 2)
    jy = y + random.randint(-2, 2)
    _human_move(page, jx, jy)
    time.sleep(random.uniform(0.06, 0.18))
    page.mouse.click(jx, jy)
    time.sleep(random.uniform(0.08, 0.20))


def _human_type(page, text: str):
    for i, ch in enumerate(text):
        page.keyboard.type(ch)
        if ch in ".!?,;:":
            time.sleep(random.uniform(0.09, 0.20))
        elif ch == " ":
            time.sleep(random.uniform(0.04, 0.12))
        elif i % random.randint(9, 18) == 0:
            time.sleep(random.uniform(0.18, 0.45))
        else:
            time.sleep(random.uniform(0.022, 0.088))


# ── Accept Google dialogs ─────────────────────────────────────────
_ACCEPT = [
    "button:has-text('Accetta tutto')",
    "button:has-text('Accept all')",
    "button:has-text('Accetto')",
    "button:has-text('I agree')",
    "button:has-text('Continua')",
    "button:has-text('Continue')",
    "button:has-text('Got it')",
    "button:has-text('Agree')",
    ".VfPpkd-LgbsSe:has-text('Accetta')",
    "[data-action='accept']",
    "form[action*='consent'] button[type='submit']",
]

def _accept_all(page, rounds: int = 3):
    for _ in range(rounds):
        found = False
        for sel in _ACCEPT:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    box = el.bounding_box()
                    if box:
                        cx = int(box["x"]+box["width"]/2)
                        cy = int(box["y"]+box["height"]/2)
                        _human_click(page, cx, cy)
                        logger.info(f"Auto-accept: {sel}")
                        time.sleep(1.0)
                        found = True
                        break
            except Exception:
                continue
        if not found:
            break


# ── AI Studio selectors (Playwright auto-pierces shadow DOM) ─────
# Usa CSS che Playwright piercea automaticamente, senza >>> esplicito
AI_STUDIO_INPUTS = [
    # Angular Material / ai-studio custom elements (auto-pierced)
    "ms-prompt-input textarea",
    "ms-chunk-input textarea",
    "textarea.gmat-body-medium",
    "textarea[placeholder]",
    "textarea",
    # Contenteditable fallback
    "[contenteditable='true'][role='textbox']",
    "[contenteditable='true']",
]

AI_STUDIO_OUTPUTS = [
    # Risposta del modello
    "ms-chat-turn[role='model'] ms-text-chunk",
    "ms-chat-turn[role='model'] .model-response-text",
    "ms-chat-turn:last-child .response-container",
    ".model-response-text",
    "ms-text-chunk",
]

GEMINI_WEB_INPUTS = [
    "rich-textarea p",
    "rich-textarea [contenteditable]",
    "div.ql-editor",
    "[data-placeholder] p",
    "[contenteditable='true']",
    "textarea",
]

GEMINI_WEB_OUTPUTS = [
    "message-content model-response .model-response-text",
    ".response-container",
    "message-content",
    ".model-response-text",
]


# ── BrowserAIBridge ───────────────────────────────────────────────
class BrowserAIBridge:
    """
    Usa un profilo Playwright persistente.
    Prima volta: utente fa login Google manualmente.
    Poi: tutto automatico.
    """

    def __init__(self):
        self._ctx    = None
        self._pw     = None
        self._ready  = False
        self._first  = not _FLAG_LOGGED_IN.exists()

    # ── Setup ──────────────────────────────────────────────────────
    def _ensure(self):
        if self._ready:
            return
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().__enter__()

        launch_kw = dict(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--no-first-run",
                "--start-maximized",
                "--disable-features=IsolateOrigins",
            ],
            slow_mo=40,
        )

        # Prova prima con Chrome installato (fingerprint migliore)
        chrome_exe = self._find_chrome()
        if chrome_exe:
            launch_kw["executable_path"] = chrome_exe

        # Profilo persistente: login Google sopravvive al riavvio
        self._ctx = self._pw.chromium.launch_persistent_context(
            str(PROFILE_DIR),
            **launch_kw,
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

        if self._first:
            self._do_first_login()

    def _find_chrome(self) -> str | None:
        paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
        for p in paths:
            if Path(p).exists():
                return p
        return None

    def _do_first_login(self):
        """
        Primo avvio: apre AI Studio e aspetta che l'utente faccia login.
        Mostra un banner nella pagina con istruzioni.
        """
        logger.info("PRIMA VOLTA — aspetto login Google su AI Studio…")
        page = self._ctx.new_page()
        page.goto("https://aistudio.google.com/app/prompts/new_chat",
                  wait_until="domcontentloaded", timeout=_NAV_MS)

        # Inietta banner istruzioni
        page.evaluate("""() => {
            const d = document.createElement('div');
            d.id = 'dust-banner';
            d.style = 'position:fixed;top:0;left:0;right:0;background:#1f6feb;'
                    + 'color:white;padding:12px;text-align:center;z-index:99999;'
                    + 'font-size:15px;font-family:sans-serif;';
            d.textContent = '⚡ DUST AI: Fai login a Google. '
                          + 'Quando sei nella chat, chiudi questa finestra.';
            document.body.prepend(d);
        }""")

        # Attendi che la textarea appaia (significa: login fatto, siamo in chat)
        logger.info("In attesa che l'utente faccia login (max 5 minuti)…")
        try:
            page.wait_for_selector("textarea, ms-prompt-input textarea",
                                   timeout=300_000, state="visible")
            _FLAG_LOGGED_IN.touch()
            logger.info("Login Google completato ✓ — sessione salvata")
            self._first = False
        except Exception:
            logger.warning("Login non completato nel tempo limite")
        finally:
            try:
                page.close()
            except Exception:
                pass

    def close(self):
        self._ready = False
        try:
            if self._ctx:
                self._ctx.close()
            if self._pw:
                self._pw.__exit__(None, None, None)
        except Exception:
            pass

    # ── Public ────────────────────────────────────────────────────
    def chat(self, messages: list[dict], timeout: int = 60) -> str:
        self._ensure()
        prompt = "\n".join(m.get("content","")
                           for m in messages if m.get("role")=="user")

        # AI Studio (meglio: più potente, richiede login Google)
        try:
            ans = self._aistudio(prompt, timeout)
            if ans:
                return json.dumps({"type":"done","message":ans})
        except Exception as exc:
            logger.warning(f"AI Studio: {exc}")

        # Gemini web (fallback)
        try:
            ans = self._gemini_web(prompt, timeout)
            if ans:
                return json.dumps({"type":"done","message":ans})
        except Exception as exc:
            logger.warning(f"Gemini web: {exc}")

        raise RuntimeError("BrowserAI: nessun servizio disponibile")

    # ── AI Studio ─────────────────────────────────────────────────
    def _aistudio(self, prompt: str, timeout: int) -> str:
        page = self._ctx.new_page()
        try:
            page.goto("https://aistudio.google.com/app/prompts/new_chat",
                      wait_until="domcontentloaded", timeout=_NAV_MS)
            time.sleep(3)
            _accept_all(page)
            time.sleep(1.5)

            # Controlla se siamo nella pagina di login (non chat)
            if page.query_selector("input[type='email']"):
                raise RuntimeError(
                    "AI Studio: richiede login. "
                    "Elimina A:\\dustai_stuff\\browser_profile\\.google_logged_in "
                    "e riavvia per fare login.")

            # Trova input (Playwright CSS piercea shadow DOM automaticamente)
            inp = self._find_input(page, AI_STUDIO_INPUTS)
            if inp is None:
                raise RuntimeError("Input non trovato")

            # Click umano
            box = inp.bounding_box()
            if box:
                _human_click(page,
                             int(box["x"]+box["width"]/2),
                             int(box["y"]+box["height"]/2))
            else:
                inp.click()
            time.sleep(0.4)

            # Cancella testo esistente
            page.keyboard.press("Control+a")
            time.sleep(0.1)
            page.keyboard.press("Delete")
            time.sleep(0.2)

            # Digita prompt
            _human_type(page, prompt)
            time.sleep(0.6)
            page.keyboard.press("Enter")
            logger.info("AI Studio: prompt inviato, attendo risposta…")

            return self._wait_reply(page, AI_STUDIO_OUTPUTS, timeout)
        finally:
            try:
                page.close()
            except Exception:
                pass

    # ── Gemini web ────────────────────────────────────────────────
    def _gemini_web(self, prompt: str, timeout: int) -> str:
        page = self._ctx.new_page()
        try:
            page.goto("https://gemini.google.com/",
                      wait_until="domcontentloaded", timeout=_NAV_MS)
            time.sleep(3)
            _accept_all(page)
            time.sleep(1.5)

            if page.query_selector("input[type='email']"):
                raise RuntimeError("Gemini web: richiede login")

            inp = self._find_input(page, GEMINI_WEB_INPUTS)
            if inp is None:
                raise RuntimeError("Input non trovato su Gemini web")

            box = inp.bounding_box()
            if box:
                _human_click(page,
                             int(box["x"]+box["width"]/2),
                             int(box["y"]+box["height"]/2))
            else:
                inp.click()
            time.sleep(0.4)
            page.keyboard.press("Control+a")
            time.sleep(0.1)
            _human_type(page, prompt)
            time.sleep(0.6)
            page.keyboard.press("Enter")
            logger.info("Gemini web: prompt inviato, attendo risposta…")
            return self._wait_reply(page, GEMINI_WEB_OUTPUTS, timeout)
        finally:
            try:
                page.close()
            except Exception:
                pass

    # ── Helpers ───────────────────────────────────────────────────
    def _find_input(self, page, selectors: list[str]):
        """
        Prova ogni selettore CSS.
        Playwright piercea automaticamente shadow DOM aperto con CSS.
        """
        for sel in selectors:
            try:
                # Timeout breve: se non c'è in 4s, prova il prossimo
                el = page.wait_for_selector(sel, timeout=4_000, state="visible")
                if el:
                    logger.info(f"Input trovato: {sel}")
                    return el
            except Exception:
                continue

        # Ultimo fallback: trova qualsiasi elemento interattivo visibile
        try:
            for tag in ["textarea", "input[type='text']",
                        "[contenteditable='true']", "[role='textbox']"]:
                els = page.query_selector_all(tag)
                for el in els:
                    if el.is_visible():
                        box = el.bounding_box()
                        if box and box["width"] > 80 and box["height"] > 20:
                            logger.info(f"Input fallback: {tag}")
                            return el
        except Exception:
            pass
        return None

    def _wait_reply(self, page, selectors: list[str], timeout: int) -> str:
        """Attendi risposta stabile (2 letture uguali a 3s di distanza)."""
        last   = ""
        stable = 0
        t0     = time.time()
        while time.time() - t0 < timeout:
            time.sleep(3)
            text = ""
            for sel in selectors:
                try:
                    els  = page.query_selector_all(sel)
                    text = " ".join(
                        e.text_content().strip() for e in els
                        if e.text_content().strip()
                    )
                    if text:
                        break
                except Exception:
                    continue
            if text and len(text) > 15:
                if text == last:
                    stable += 1
                    if stable >= 2:
                        logger.info(f"Risposta stabile ({len(text)} chars)")
                        return text
                else:
                    stable = 0
                    last   = text
        return last or ""


# ── Stealth JS ────────────────────────────────────────────────────
_STEALTH_JS = """
window._dmx = 640; window._dmy = 400;
document.addEventListener('mousemove', e=>{
    window._dmx=e.clientX; window._dmy=e.clientY;
}, {passive:true});
Object.defineProperty(navigator,'webdriver',{get:()=>undefined});
Object.defineProperty(navigator,'plugins',{get:()=>[
    {name:'Chrome PDF Plugin'},{name:'Chrome PDF Viewer'},{name:'Native Client'}
]});
Object.defineProperty(navigator,'languages',{get:()=>['it-IT','it','en-US','en']});
if(!window.chrome)window.chrome={};
window.chrome.runtime=window.chrome.runtime||{
    connect:()=>({onMessage:{addListener:()=>{}},postMessage:()=>{}}),
    sendMessage:()=>{}
};
"""
