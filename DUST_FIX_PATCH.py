#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║  DUST AI — FIX PATCH                                         ║
║  Fix 1: google.generativeai → google.genai (nuovo SDK)       ║
║  Fix 2: Modello gemini-2.5-flash-preview → gemini-2.0-flash  ║
║  Fix 3: BrowserAI autonomo (terms + captcha stealth)         ║
║                                                              ║
║  Esegui da: A:\\dustai> python DUST_FIX_PATCH.py             ║
╚══════════════════════════════════════════════════════════════╝
"""
import os, sys, subprocess, textwrap
from pathlib import Path

BASE  = Path(r"A:\dustai")
SRC   = BASE / "src"
TOOLS = SRC / "tools"

FILES = {}

# ─────────────────────────────────────────────────────────────
# config.py — solo il modello cambia
# ─────────────────────────────────────────────────────────────
FILES["src/config.py"] = r'''
import os
import pathlib

BASE_PATH  = pathlib.Path(r"A:\dustai")
STUFF_PATH = pathlib.Path(r"A:\dustai_stuff")

_env_file = STUFF_PATH / ".env"
if _env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_file, override=True)
    except ImportError:
        for line in _env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


class Config:
    _cfg: dict = {}

    @classmethod
    def get(cls, key, default=None):
        return os.environ.get(key, cls._cfg.get(key, default))

    @classmethod
    def set(cls, key, value):
        cls._cfg[key] = value


GEMINI_KEYS: list[str] = [
    k for k in [
        os.environ.get("GOOGLE_API_KEY"),
        os.environ.get("GOOGLE_API_KEY_2"),
        os.environ.get("GOOGLE_API_KEY_3"),
    ] if k
]

# ✅ Modello aggiornato — gemini-2.0-flash è disponibile gratis su v1beta
GEMINI_MODEL       = "gemini-2.0-flash"
GITHUB_TOKEN       = os.environ.get("GITHUB_TOKEN", "")
GITHUB_USER        = os.environ.get("GITHUB_USER", "Tenkulo")
GITHUB_REPO        = "dustai"
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODELS   = ["qwen3:8b", "mistral-small3.1"]
'''

# ─────────────────────────────────────────────────────────────
# agent.py — usa google.genai (nuovo SDK ufficiale)
# ─────────────────────────────────────────────────────────────
FILES["src/agent.py"] = r'''
"""DUST Agent — cascade: Gemini KEY1→KEY2→KEY3→BrowserAI→Ollama.
Usa il nuovo SDK google.genai (google-genai package).
"""
import json
import re
import time
import logging
from typing import Any

logger = logging.getLogger("dust.agent")

try:
    from config import GEMINI_KEYS, GEMINI_MODEL, OLLAMA_BASE_URL, OLLAMA_MODELS
except ImportError:
    GEMINI_KEYS = []
    GEMINI_MODEL = "gemini-2.0-flash"
    OLLAMA_BASE_URL = "http://localhost:11434"
    OLLAMA_MODELS = ["qwen3:8b"]

SYSTEM_PROMPT = """Sei DUST AI, un assistente personale universale intelligente che gira su Windows.
Rispondi in modo naturale e conversazionale in italiano.
Puoi eseguire azioni sul PC (file, browser, mouse, tastiera, app) quando l'utente lo richiede.

Quando devi usare un tool, rispondi SOLO con questo JSON (nessun altro testo):
{"type": "tool_call", "tool": "nome_tool", "params": {"param1": "valore1"}}

Quando hai finito o vuoi rispondere normalmente, rispondi SOLO con:
{"type": "done", "message": "la tua risposta conversazionale completa"}

Per risposte semplici senza tool, usa sempre il formato done.
Non uscire mai dal formato JSON nella tua risposta.
"""


class RateLimitError(Exception):
    def __init__(self, wait_seconds: int, api_key: str = ""):
        self.wait_seconds = wait_seconds
        self.api_key = api_key
        super().__init__(f"Rate limit: aspetta {wait_seconds}s")


# ── Nuovo SDK google.genai ────────────────────────────────────
class GeminiClient:
    """
    Usa google-genai (nuovo SDK ufficiale, non più google-generativeai).
    Installazione: pip install google-genai
    """

    def __init__(self, api_key: str):
        try:
            from google import genai
            from google.genai import types
            self._client = genai.Client(api_key=api_key)
            self._types  = types
        except ImportError:
            raise RuntimeError(
                "Installa il nuovo SDK: pip install google-genai\n"
                "NON usare google-generativeai (deprecato)"
            )
        self.api_key = api_key

    def chat(self, messages: list[dict], system: str = None) -> str:
        # Costruisci il prompt unificato
        parts: list[str] = []
        if system:
            parts.append(f"[SYSTEM]\n{system}")
        for m in messages:
            role    = m.get("role", "user").upper()
            content = m.get("content", "")
            parts.append(f"[{role}]\n{content}")
        prompt = "\n\n".join(parts)

        try:
            response = self._client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
            )
            try:
                return response.text
            except Exception:
                # finish_reason RECITATION o altro non-text
                return json.dumps({"type": "done", "message": "Risposta non disponibile."})

        except Exception as exc:
            err = str(exc)
            if "429" in err or "quota" in err.lower() or "RATE_LIMIT" in err:
                m = re.search(r"retry_delay[^0-9]*(\d+)", err)
                wait = int(m.group(1)) if m else 62
                wait = min(65, int(wait) + 3)     # CLAMP
                raise RateLimitError(wait, self.api_key)
            raise


class OllamaClient:
    def __init__(self, model: str):
        self.model = model

    def chat(self, messages: list[dict], system: str = None) -> str:
        import requests
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={"model": self.model, "messages": msgs, "stream": False},
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]


class Agent:
    def __init__(self, tools_registry=None, browser_bridge=None):
        self.registry       = tools_registry
        self.browser_bridge = browser_bridge
        self._gemini: list[GeminiClient] = []
        self._cooldowns: dict[str, float] = {}
        self._init_gemini()

    def _init_gemini(self):
        for key in GEMINI_KEYS:
            try:
                self._gemini.append(GeminiClient(key))
                logger.info(f"Gemini key ...{key[-6:]} OK")
            except Exception as exc:
                logger.warning(f"Gemini init: {exc}")

    def _next_gemini(self) -> "GeminiClient | None":
        now = time.time()
        for c in self._gemini:
            if now >= self._cooldowns.get(c.api_key, 0):
                return c
        return None

    def _cooldown(self, api_key: str, seconds: int):
        self._cooldowns[api_key] = time.time() + seconds
        logger.warning(f"Key ...{api_key[-6:]} cooldown {seconds}s")

    def chat(self, messages: list[dict], **kwargs) -> str:
        # 1) Gemini cascade
        client = self._next_gemini()
        while client:
            try:
                return client.chat(messages, system=SYSTEM_PROMPT)
            except RateLimitError as e:
                self._cooldown(e.api_key, e.wait_seconds)
                client = self._next_gemini()
            except Exception as exc:
                logger.error(f"Gemini error: {exc}")
                break

        # 2) BrowserAI bridge
        if self.browser_bridge:
            try:
                return self.browser_bridge.chat(messages)
            except Exception as exc:
                logger.warning(f"BrowserAI: {exc}")

        # 3) Ollama locale
        for model in OLLAMA_MODELS:
            try:
                return OllamaClient(model).chat(messages, system=SYSTEM_PROMPT)
            except Exception as exc:
                logger.warning(f"Ollama {model}: {exc}")

        return json.dumps({"type": "done",
                           "message": "⚠️ Tutti i modelli AI non disponibili al momento."})

    def run_turn(self, user_msg: str, history: list = None, **kwargs) -> tuple:
        if history is None:
            history = []
        messages     = history + [{"role": "user", "content": user_msg}]
        tool_results = []

        for _ in range(8):
            raw    = self.chat(messages, **kwargs)
            parsed = self._parse(raw)

            if parsed.get("type") == "tool_call":
                tool   = parsed.get("tool", "")
                params = parsed.get("params", {})
                result = self._run_tool(tool, params)
                tool_results.append({"tool": tool, "result": result})
                messages.append({"role": "assistant", "content": raw})
                messages.append({"role": "user",
                                 "content": f"[TOOL RESULT: {tool}]\n"
                                            f"{json.dumps(result, ensure_ascii=False)}"})
                continue

            return parsed.get("message", raw), tool_results

        return "Ho completato le operazioni.", tool_results

    def _parse(self, raw: str) -> dict:
        try:
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                return json.loads(m.group())
        except Exception:
            pass
        return {"type": "done", "message": raw}

    def _run_tool(self, name: str, params: dict) -> Any:
        if self.registry:
            try:
                return self.registry.call(name, **params)
            except Exception as exc:
                return {"error": str(exc)}
        return {"error": "registry not available"}
'''

# ─────────────────────────────────────────────────────────────
# tools/computer_use.py — screen_read con nuovo SDK
# ─────────────────────────────────────────────────────────────
FILES["src/tools/computer_use.py"] = r'''
"""Computer-use tools — screen_read usa google.genai (nuovo SDK)."""
import io
import json
import logging
import subprocess
import time
import webbrowser

logger = logging.getLogger("dust.computer_use")


def screen_read(region: list = None) -> dict:
    """Cattura screenshot e descrivilo con Gemini Vision."""
    try:
        import pyautogui
        from PIL import Image
        screenshot = pyautogui.screenshot(region=region)

        buf = io.BytesIO()
        screenshot.save(buf, format="PNG")
        image_bytes = buf.getvalue()

        from config import GEMINI_KEYS, GEMINI_MODEL
        from google import genai
        from google.genai import types

        for key in GEMINI_KEYS:
            try:
                client = genai.Client(api_key=key)
                resp   = client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=[
                        types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                        "Descrivi dettagliatamente questo screenshot: finestre aperte, "
                        "testo visibile, bottoni, icone, stato del sistema.",
                    ],
                )
                try:
                    return {"status": "ok", "description": resp.text}
                except Exception:
                    return {"status": "ok", "description": "Screenshot acquisito."}
            except Exception as exc:
                if "429" not in str(exc):
                    break
        return {"status": "ok", "description": "Screenshot acquisito (analisi non disponibile)."}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def screen_do(action: str, x: int = None, y: int = None, text: str = None,
              key: str = None, button: str = "left", clicks: int = 1,
              duration: float = 0.3, target: str = None) -> dict:
    """Esegui un'azione GUI: click|type|key|scroll|move|drag|screenshot."""
    try:
        import pyautogui
        pyautogui.FAILSAFE = True
        action = action.lower()

        if action == "click":
            if x is not None and y is not None:
                pyautogui.click(x, y, button=button, clicks=clicks)
            elif target:
                loc = pyautogui.locateCenterOnScreen(target, confidence=0.8)
                if loc:
                    pyautogui.click(loc)
                else:
                    return {"status": "error", "error": f"Target not found: {target}"}
            return {"status": "ok", "action": "click", "pos": [x, y]}

        elif action == "double_click":
            pyautogui.doubleClick(x or 0, y or 0)
            return {"status": "ok", "action": "double_click"}

        elif action in ("type", "write"):
            pyautogui.write(text or "", interval=0.04)
            return {"status": "ok", "action": "type"}

        elif action in ("key", "hotkey", "press"):
            if key:
                if "+" in key:
                    pyautogui.hotkey(*key.split("+"))
                else:
                    pyautogui.press(key)
            return {"status": "ok", "action": "key", "key": key}

        elif action == "scroll":
            pyautogui.scroll(clicks or 3, x=x, y=y)
            return {"status": "ok", "action": "scroll"}

        elif action == "move":
            pyautogui.moveTo(x or 0, y or 0, duration=duration)
            return {"status": "ok", "action": "move"}

        elif action == "drag":
            pyautogui.dragTo(x or 0, y or 0, duration=duration)
            return {"status": "ok", "action": "drag"}

        elif action == "screenshot":
            return screen_read()

        else:
            return {"status": "error", "error": f"Azione sconosciuta: {action}"}

    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def app_open(app_name: str, args: list = None) -> dict:
    """Apri un'applicazione Windows per nome o percorso .exe."""
    KNOWN = {
        "notepad": "notepad.exe", "explorer": "explorer.exe",
        "calc": "calc.exe", "calculator": "calc.exe",
        "chrome": "chrome.exe", "edge": "msedge.exe",
        "firefox": "firefox.exe", "cmd": "cmd.exe",
        "powershell": "powershell.exe", "vscode": "code.exe",
        "code": "code.exe", "paint": "mspaint.exe",
        "word": "winword.exe", "excel": "excel.exe",
    }
    try:
        exe = KNOWN.get(app_name.lower(), app_name)
        subprocess.Popen([exe] + (args or []), shell=True)
        time.sleep(0.8)
        return {"status": "ok", "app": app_name}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def browser_go(url: str) -> dict:
    """Apri un URL nel browser predefinito."""
    try:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        webbrowser.open(url)
        time.sleep(0.5)
        return {"status": "ok", "url": url}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}
'''

# ─────────────────────────────────────────────────────────────
# tools/browser_ai_bridge.py — autonomo: risolve captcha,
# accetta terms, usa stealth, fallback su più servizi
# ─────────────────────────────────────────────────────────────
FILES["src/tools/browser_ai_bridge.py"] = r'''
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
'''

# ─────────────────────────────────────────────────────────────
# ai_gateway.py — usa google.genai
# ─────────────────────────────────────────────────────────────
FILES["src/ai_gateway.py"] = r'''
"""Unified AI gateway — google.genai + OpenRouter + Ollama."""
import logging
import os
import re
import time

logger = logging.getLogger("dust.ai_gateway")

try:
    from config import GEMINI_KEYS, GEMINI_MODEL, OPENROUTER_API_KEY, \
                       OLLAMA_BASE_URL, OLLAMA_MODELS
except ImportError:
    GEMINI_KEYS = []; GEMINI_MODEL = "gemini-2.0-flash"
    OPENROUTER_API_KEY = ""; OLLAMA_BASE_URL = "http://localhost:11434"
    OLLAMA_MODELS = []


class AIGateway:
    def __init__(self):
        self._providers: list[dict] = []
        self._cooldowns: dict[str, float] = {}
        self._build()

    def _build(self):
        for i, k in enumerate(GEMINI_KEYS):
            self._providers.append({"name": f"gemini_{i+1}", "type": "gemini",
                                    "key": k, "priority": i})
        if OPENROUTER_API_KEY:
            self._providers.append({"name": "openrouter", "type": "openrouter",
                                    "key": OPENROUTER_API_KEY, "priority": 10})
        for i, m in enumerate(OLLAMA_MODELS):
            self._providers.append({"name": f"ollama_{m}", "type": "ollama",
                                    "model": m, "priority": 20 + i})

    def _available(self) -> list[dict]:
        now = time.time()
        return [p for p in sorted(self._providers, key=lambda x: x["priority"])
                if now >= self._cooldowns.get(p["name"], 0)]

    def complete(self, messages: list[dict], system: str = None,
                 provider: str = None) -> str:
        for p in self._available():
            if provider and p["name"] != provider:
                continue
            try:
                return self._call(p, messages, system)
            except Exception as exc:
                err = str(exc)
                if "429" in err or "quota" in err.lower():
                    m = re.search(r"(\d+)", err)
                    wait = min(65, int(m.group(1)) + 3) if m else 65
                    self._cooldowns[p["name"]] = time.time() + wait
                    logger.warning(f"{p['name']}: rate-limit {wait}s")
                else:
                    logger.warning(f"{p['name']}: {exc}")
        raise RuntimeError("All providers failed")

    def _call(self, p, messages, system):
        if p["type"] == "gemini":
            return self._gemini(p["key"], messages, system)
        if p["type"] == "openrouter":
            return self._openrouter(p["key"], messages, system)
        if p["type"] == "ollama":
            return self._ollama(p["model"], messages, system)

    def _gemini(self, key, messages, system):
        from google import genai
        client = genai.Client(api_key=key)
        parts  = []
        if system:
            parts.append(f"[SYSTEM]\n{system}")
        for m in messages:
            parts.append(f"[{m['role'].upper()}]\n{m.get('content','')}")
        r = client.models.generate_content(
            model=GEMINI_MODEL, contents="\n\n".join(parts))
        try:
            return r.text
        except Exception:
            return ""

    def _openrouter(self, key, messages, system):
        import requests
        msgs = ([] if not system else [{"role": "system", "content": system}]) + messages
        r = requests.post("https://openrouter.ai/api/v1/chat/completions",
                          headers={"Authorization": f"Bearer {key}",
                                   "Content-Type": "application/json"},
                          json={"model": "openai/gpt-4o-mini", "messages": msgs},
                          timeout=30)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    def _ollama(self, model, messages, system):
        import requests
        msgs = ([] if not system else [{"role": "system", "content": system}]) + messages
        r = requests.post(f"{OLLAMA_BASE_URL}/api/chat",
                          json={"model": model, "messages": msgs, "stream": False},
                          timeout=120)
        r.raise_for_status()
        return r.json()["message"]["content"]

    def list_providers(self):
        return [p["name"] for p in self._providers]
'''

# ═══════════════════════════════════════════════════════════════
# WRITER + INSTALL + GIT PUSH
# ═══════════════════════════════════════════════════════════════

import os, sys, subprocess, textwrap
from pathlib import Path

BASE  = Path(r"A:\dustai")
SRC   = BASE / "src"
TOOLS = SRC / "tools"

def write_files():
    print("\n📁  Scrittura file…")
    for rel, content in FILES.items():
        dest = BASE / rel.replace("/", os.sep)
        dest.parent.mkdir(parents=True, exist_ok=True)
        text = textwrap.dedent(content).lstrip("\n")
        dest.write_text(text, encoding="utf-8")
        print(f"  ✅  {rel}")


def install_deps():
    print("\n📦  Installazione dipendenze…")
    pkgs = ["google-genai", "playwright", "pyautogui", "Pillow",
            "requests", "python-dotenv"]
    for pkg in pkgs:
        print(f"  pip install {pkg}…", end=" ", flush=True)
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", pkg, "-q",
             "--break-system-packages"],
            capture_output=True, text=True)
        print("ok" if r.returncode == 0 else f"WARN ({r.stderr.strip()[:60]})")

    print("  playwright install chromium…", end=" ", flush=True)
    r = subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"],
                       capture_output=True, text=True)
    print("ok" if r.returncode == 0 else f"WARN ({r.stderr.strip()[:60]})")


def git_push():
    print("\n🚀  Git sync…")
    def git(args):
        return subprocess.run(["git"] + args, cwd=str(BASE),
                              capture_output=True, text=True)

    try:
        from dotenv import load_dotenv
        load_dotenv(Path(r"A:\dustai_stuff\.env"), override=True)
    except Exception:
        pass

    token = os.environ.get("GITHUB_TOKEN", "")
    user  = os.environ.get("GITHUB_USER", "Tenkulo")
    if token:
        url = f"https://{user}:{token}@github.com/{user}/dustai.git"
        git(["remote", "set-url", "origin", url])

    git(["add", "-A"])
    st = git(["status", "--porcelain"])
    if not st.stdout.strip():
        print("  ℹ️  Niente da committare.")
        return
    r = git(["commit", "-m", "fix: google.genai SDK + model + BrowserAI stealth autonomo"])
    if r.returncode:
        print(f"  ❌  commit: {r.stderr[:150]}")
        return
    r = git(["push", "origin", "master"])
    print("  ✅  push ok" if r.returncode == 0 else f"  ❌  push: {r.stderr[:150]}")


if __name__ == "__main__":
    print("=" * 60)
    print("  DUST AI — FIX PATCH")
    print("=" * 60)
    write_files()
    install_deps()
    git_push()
    print("\n✅  Fatto! Avvia con: .\\run.bat")
