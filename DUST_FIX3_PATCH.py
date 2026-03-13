#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║  DUST AI — FIX PATCH #3  (definitivo)                           ║
║                                                                  ║
║  Fix A: Groq API gratuito (14.400 req/day) livello 4 cascade    ║
║  Fix B: Playwright profilo persistente — login Google 1 sola    ║
║         volta, sessione salvata per sempre                       ║
║  Fix C: Selettori AI Studio corretti (CSS auto-pierce ShadowDOM)║
║  Fix D: Ollama timeout 300s + check se è attivo                 ║
║                                                                  ║
║  .env → aggiungi GROQ_API_KEY=gsk_...                           ║
║  Registrati gratis su: console.groq.com                         ║
║                                                                  ║
║  Esegui: cd A:\\dustai && python DUST_FIX3_PATCH.py             ║
╚══════════════════════════════════════════════════════════════════╝
"""
import os, sys, subprocess, textwrap
from pathlib import Path

BASE  = Path(r"A:\dustai")
SRC   = BASE / "src"
TOOLS = SRC / "tools"

FILES: dict[str, str] = {}

# ══════════════════════════════════════════════════════════════════
#  config.py
# ══════════════════════════════════════════════════════════════════
FILES["src/config.py"] = r'''
import os
import pathlib

BASE_PATH   = pathlib.Path(r"A:\dustai")
STUFF_PATH  = pathlib.Path(r"A:\dustai_stuff")

# Profilo browser persistente per BrowserAI (diverso da Chrome utente)
BROWSER_PROFILE_DIR = STUFF_PATH / "browser_profile"

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

GEMINI_MODEL       = "gemini-2.0-flash"
GROQ_API_KEY       = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL         = "llama-3.3-70b-versatile"   # 14.400 req/day free
GITHUB_TOKEN       = os.environ.get("GITHUB_TOKEN", "")
GITHUB_USER        = os.environ.get("GITHUB_USER", "Tenkulo")
GITHUB_REPO        = "dustai"
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODELS   = ["qwen3:8b", "mistral-small3.1"]
OLLAMA_TIMEOUT  = 300   # 5 minuti: prima load del modello può essere lenta
'''

# ══════════════════════════════════════════════════════════════════
#  agent.py — cascade: Gemini → Groq → BrowserAI → Ollama
# ══════════════════════════════════════════════════════════════════
FILES["src/agent.py"] = r'''
"""DUST Agent v4.2 — cascade 7 livelli: Gemini×3 → Groq → BrowserAI → Ollama×2."""
import json
import re
import time
import logging
import threading
from typing import Any

logger = logging.getLogger("dust.agent")

try:
    from config import (GEMINI_KEYS, GEMINI_MODEL, GROQ_API_KEY, GROQ_MODEL,
                        OLLAMA_BASE_URL, OLLAMA_MODELS, OLLAMA_TIMEOUT)
except ImportError:
    GEMINI_KEYS = []; GEMINI_MODEL = "gemini-2.0-flash"
    GROQ_API_KEY = ""; GROQ_MODEL = "llama-3.3-70b-versatile"
    OLLAMA_BASE_URL = "http://localhost:11434"
    OLLAMA_MODELS = ["qwen3:8b"]; OLLAMA_TIMEOUT = 300

# ── Lazy system prompt (caricato al primo uso) ────────────────────
_PROMPT_LOCK = threading.Lock()
_SYSTEM_PROMPT: str = ""

def _build_prompt() -> str:
    base = """Sei DUST AI, un assistente personale universale intelligente su Windows.
Rispondi in italiano in modo naturale e conversazionale.
Hai piena autoconsapevolezza: conosci il tuo codice, i tuoi tool, la tua architettura.

"""
    try:
        from self_knowledge import get_system_context
        base += get_system_context() + "\n\n"
    except Exception:
        pass
    base += """REGOLE RISPOSTA — usa SOLO uno di questi formati JSON:

Tool call:
{"type": "tool_call", "tool": "nome_tool", "params": {"chiave": "valore"}}

Risposta:
{"type": "done", "message": "testo risposta completa in italiano"}

Non scrivere MAI testo fuori dal JSON.
"""
    return base

def get_system_prompt() -> str:
    global _SYSTEM_PROMPT
    if not _SYSTEM_PROMPT:
        with _PROMPT_LOCK:
            if not _SYSTEM_PROMPT:
                _SYSTEM_PROMPT = _build_prompt()
    return _SYSTEM_PROMPT

def invalidate_prompt():
    global _SYSTEM_PROMPT
    _SYSTEM_PROMPT = ""


# ── Eccezioni ─────────────────────────────────────────────────────
class RateLimitError(Exception):
    def __init__(self, wait: int, key: str = ""):
        self.wait_seconds = wait; self.api_key = key
        super().__init__(f"RateLimit {wait}s")

class ProviderError(Exception):
    pass


# ── Gemini (google.genai nuovo SDK) ──────────────────────────────
class GeminiClient:
    def __init__(self, api_key: str):
        from google import genai
        self._c = genai.Client(api_key=api_key)
        self.api_key = api_key

    def chat(self, messages: list[dict], system: str) -> str:
        parts = [f"[SYSTEM]\n{system}"]
        for m in messages:
            parts.append(f"[{m.get('role','user').upper()}]\n{m.get('content','')}")
        try:
            r = self._c.models.generate_content(
                model=GEMINI_MODEL, contents="\n\n".join(parts))
            try:
                return r.text
            except Exception:
                return json.dumps({"type":"done","message":"Risposta non disponibile."})
        except Exception as exc:
            err = str(exc)
            if "429" in err or "quota" in err.lower():
                m = re.search(r"retry_delay[^0-9]*(\d+)", err)
                raise RateLimitError(min(65, (int(m.group(1)) if m else 62)+3),
                                     self.api_key)
            raise ProviderError(str(exc))


# ── Groq (OpenAI-compatible, 14.400 req/day gratis) ──────────────
class GroqClient:
    URL = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self, api_key: str):
        if not api_key:
            raise ProviderError("GROQ_API_KEY non configurata")
        self.api_key = api_key

    def chat(self, messages: list[dict], system: str) -> str:
        import requests
        msgs = [{"role":"system","content":system}] + messages
        try:
            r = requests.post(
                self.URL,
                headers={"Authorization": f"Bearer {self.api_key}",
                         "Content-Type": "application/json"},
                json={"model": GROQ_MODEL, "messages": msgs, "max_tokens": 2048},
                timeout=30,
            )
        except requests.exceptions.Timeout:
            raise ProviderError("Groq timeout")
        if r.status_code == 429:
            raise RateLimitError(62, "groq")
        if not r.ok:
            raise ProviderError(f"Groq {r.status_code}: {r.text[:100]}")
        return r.json()["choices"][0]["message"]["content"]


# ── Ollama ────────────────────────────────────────────────────────
class OllamaClient:
    def __init__(self, model: str):
        self.model = model

    def is_running(self) -> bool:
        import requests
        try:
            r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3)
            return r.ok
        except Exception:
            return False

    def chat(self, messages: list[dict], system: str) -> str:
        import requests
        msgs = [{"role":"system","content":system}] + messages
        try:
            r = requests.post(
                f"{OLLAMA_BASE_URL}/api/chat",
                json={"model": self.model, "messages": msgs, "stream": False},
                timeout=OLLAMA_TIMEOUT,
            )
        except requests.exceptions.Timeout:
            raise ProviderError(f"Ollama {self.model} timeout ({OLLAMA_TIMEOUT}s)")
        except Exception as exc:
            raise ProviderError(f"Ollama {self.model}: {exc}")
        if not r.ok:
            raise ProviderError(f"Ollama HTTP {r.status_code}")
        return r.json()["message"]["content"]


# ── Agent ────────────────────────────────────────────────────────
class Agent:
    def __init__(self, tools_registry=None, browser_bridge=None):
        self.registry        = tools_registry
        self.browser_bridge  = browser_bridge
        self._gemini:  list[GeminiClient] = []
        self._groq:    GroqClient | None  = None
        self._cooldowns: dict[str, float] = {}
        self._init()

    def _init(self):
        for k in GEMINI_KEYS:
            try:
                self._gemini.append(GeminiClient(k))
                logger.info(f"Gemini ...{k[-6:]} OK")
            except Exception as exc:
                logger.warning(f"Gemini init: {exc}")
        if GROQ_API_KEY:
            try:
                self._groq = GroqClient(GROQ_API_KEY)
                logger.info("Groq OK")
            except Exception as exc:
                logger.warning(f"Groq init: {exc}")

    def _available(self, key: str) -> bool:
        return time.time() >= self._cooldowns.get(key, 0)

    def _cooldown(self, key: str, secs: int):
        self._cooldowns[key] = time.time() + secs
        logger.warning(f"{key} cooldown {secs}s")

    def chat(self, messages: list[dict]) -> str:
        sys = get_system_prompt()

        # ①②③ Gemini keys
        for c in self._gemini:
            if not self._available(c.api_key):
                continue
            try:
                return c.chat(messages, sys)
            except RateLimitError as e:
                self._cooldown(e.api_key, e.wait_seconds)
            except ProviderError as e:
                logger.error(f"Gemini: {e}")
                break
            except Exception as e:
                logger.error(f"Gemini unexpected: {e}")
                break

        # ④ Groq
        if self._groq and self._available("groq"):
            try:
                return self._groq.chat(messages, sys)
            except RateLimitError as e:
                self._cooldown("groq", e.wait_seconds)
            except ProviderError as e:
                logger.warning(f"Groq: {e}")
            except Exception as e:
                logger.error(f"Groq unexpected: {e}")

        # ⑤ BrowserAI
        if self.browser_bridge:
            try:
                return self.browser_bridge.chat(messages)
            except Exception as e:
                logger.warning(f"BrowserAI: {e}")

        # ⑥⑦ Ollama
        for model in OLLAMA_MODELS:
            c = OllamaClient(model)
            if not c.is_running():
                logger.warning("Ollama non attivo (localhost:11434)")
                break
            try:
                return c.chat(messages, sys)
            except ProviderError as e:
                logger.warning(str(e))

        return json.dumps({"type":"done",
            "message":"⚠️ Tutti i modelli AI non disponibili. "
                      "Controlla la connessione o avvia Ollama."})

    def run_turn(self, user_msg: str, history: list = None) -> tuple:
        if history is None:
            history = []
        msgs = history + [{"role":"user","content":user_msg}]
        tool_results = []

        for _ in range(10):
            raw = self.chat(msgs)
            p   = self._parse(raw)
            if p.get("type") == "tool_call":
                tool   = p.get("tool","")
                params = p.get("params",{})
                res    = self._run_tool(tool, params)
                tool_results.append({"tool":tool,"result":res})
                msgs.append({"role":"assistant","content":raw})
                msgs.append({"role":"user",
                             "content":f"[TOOL RESULT: {tool}]\n"
                                       f"{json.dumps(res, ensure_ascii=False)}"})
                continue
            return p.get("message", raw), tool_results

        return "Operazioni completate.", tool_results

    def _parse(self, raw: str) -> dict:
        try:
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                return json.loads(m.group())
        except Exception:
            pass
        return {"type":"done","message":raw}

    def _run_tool(self, name: str, params: dict) -> Any:
        if self.registry:
            try:
                return self.registry.call(name, **params)
            except Exception as exc:
                return {"error": str(exc)}
        return {"error":"registry not available"}
'''

# ══════════════════════════════════════════════════════════════════
#  browser_ai_bridge.py — profilo persistente + selettori corretti
# ══════════════════════════════════════════════════════════════════
FILES["src/tools/browser_ai_bridge.py"] = r'''
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
'''

# ══════════════════════════════════════════════════════════════════
#  ui/gui.py — piccolo aggiornamento: bottone reset login + Groq badge
# ══════════════════════════════════════════════════════════════════
FILES["src/ui/gui.py"] = r'''
"""DUST AI GUI v3.2 — Dark chat, Groq badge, reset login."""
import json
import queue
import sys
import threading
import tkinter as tk
from tkinter import ttk
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

C = {
    "bg":"#1a1a2e","sidebar":"#16213e","chat_bg":"#0d1117",
    "user_bub":"#1f6feb","ai_bub":"#161b22",
    "user_fg":"#f0f6fc","ai_fg":"#c9d1d9",
    "input_bg":"#161b22","input_fg":"#f0f6fc",
    "btn":"#238636","btn_hover":"#2ea043",
    "accent":"#58a6ff","muted":"#8b949e","border":"#30363d",
    "ok":"#3fb950","err":"#f85149","warn":"#d29922",
}
FF = ("Segoe UI",11)
FT = ("Segoe UI",13,"bold")
FS = ("Segoe UI",9)


class AgentWorker(threading.Thread):
    def __init__(self, agent, out_q):
        super().__init__(daemon=True, name="AgentWorker")
        self.agent  = agent
        self.out_q  = out_q
        self._in_q  = queue.Queue()
        self._alive = True

    def submit(self, msg, history):
        self._in_q.put((msg, history))

    def run(self):
        while self._alive:
            try:
                msg, hist = self._in_q.get(timeout=0.5)
            except queue.Empty:
                continue
            self.out_q.put(("thinking",""))
            try:
                text, _ = self.agent.run_turn(msg, hist)
                self.out_q.put(("response", text))
            except Exception as exc:
                self.out_q.put(("error", str(exc)))

    def stop(self):
        self._alive = False


class Bubble(tk.Frame):
    def __init__(self, parent, text, role="user"):
        super().__init__(parent, bg=C["chat_bg"])
        is_u  = role=="user"
        outer = tk.Frame(self, bg=C["chat_bg"])
        outer.pack(fill=tk.X, padx=14, pady=5)
        bub_bg = C["user_bub"] if is_u else C["ai_bub"]
        txt_fg = C["user_fg"] if is_u else C["ai_fg"]
        badge  = tk.Label(outer, text="Tu" if is_u else "⚡ DUST",
                         font=FS, bg=bub_bg,
                         fg=C["user_fg"] if is_u else C["accent"],
                         padx=7, pady=2)
        w = min(70, max(20, max((len(l) for l in text.splitlines()),default=20)))
        h = min(30, max(2, sum(max(1,len(l)//max(w,1)+1) for l in text.splitlines())))
        tw = tk.Text(outer, wrap=tk.WORD, width=w, height=h,
                    bg=bub_bg, fg=txt_fg, font=FF,
                    bd=0, relief="flat", padx=10, pady=8,
                    cursor="arrow", spacing3=2)
        tw.insert("1.0", text)
        tw.configure(state=tk.DISABLED)
        if is_u:
            badge.pack(side=tk.RIGHT, anchor="ne", padx=(6,0))
            tw.pack(side=tk.RIGHT, anchor="ne", padx=4)
        else:
            badge.pack(side=tk.LEFT, anchor="nw", padx=(0,6))
            tw.pack(side=tk.LEFT, anchor="nw", padx=4)


class Thinking(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=C["chat_bg"])
        outer = tk.Frame(self, bg=C["chat_bg"])
        outer.pack(fill=tk.X, padx=14, pady=5)
        tk.Label(outer, text="⚡ DUST", font=FS, bg=C["ai_bub"],
                fg=C["accent"], padx=7, pady=2).pack(side=tk.LEFT, padx=(0,6))
        self._l = tk.Label(outer, text="Sto pensando…", font=FF,
                          bg=C["ai_bub"], fg=C["muted"], padx=10, pady=8)
        self._l.pack(side=tk.LEFT)
        self._n=0; self._on=True; self._tick()

    def _tick(self):
        if self._on:
            self._l.config(text="Sto pensando"+"."*(self._n%4))
            self._n+=1; self.after(420,self._tick)

    def kill(self):
        self._on=False


class DustGUI:
    def __init__(self, root):
        self.root=root; self.history=[]; self.agent=None
        self.worker=None; self._q=queue.Queue(); self._think=None
        root.title("DUST AI v4.2")
        root.configure(bg=C["bg"])
        root.geometry("960x720"); root.minsize(640,480)
        self._build()
        self._set_status("Inizializzazione…","warn")
        threading.Thread(target=self._init_agent, daemon=True).start()
        self._poll()

    def _build(self):
        r=self.root
        r.columnconfigure(0,weight=0,minsize=200)
        r.columnconfigure(1,weight=1); r.rowconfigure(0,weight=1)

        sb=tk.Frame(r,bg=C["sidebar"],width=200)
        sb.grid(row=0,column=0,sticky="nsew"); sb.grid_propagate(False)
        tk.Label(sb,text="⚡  DUST AI",font=FT,bg=C["sidebar"],
                fg=C["accent"],pady=20).pack()
        tk.Frame(sb,bg=C["border"],height=1).pack(fill=tk.X,padx=12)
        tk.Label(sb,text="Assistente Universale v4.2",font=FS,
                bg=C["sidebar"],fg=C["muted"]).pack(pady=(6,12))

        for label, cmd, bg in [
            ("＋  Nuova chat",   self._new_chat,     C["btn"]),
            ("🔍  Ispeziona",    self._inspect_self, C["ai_bub"]),
            ("🔄  Reset login",  self._reset_login,  "#3d1f1f"),
        ]:
            tk.Button(sb, text=label, font=FS, bg=bg,
                     fg="white" if bg!=C["ai_bub"] else C["accent"],
                     relief="flat", padx=10, pady=6, cursor="hand2",
                     command=cmd).pack(fill=tk.X, padx=12, pady=3)

        # Provider badge
        self._pvd = tk.Label(sb, text="AI: —", font=FS,
                            bg=C["sidebar"], fg=C["muted"])
        self._pvd.pack(pady=(8,0))

        sf=tk.Frame(sb,bg=C["sidebar"])
        sf.pack(side=tk.BOTTOM,fill=tk.X,padx=12,pady=14)
        self._dot=tk.Label(sf,text="●",bg=C["sidebar"],fg=C["warn"],font=("Arial",11))
        self._dot.pack(side=tk.LEFT)
        self._slbl=tk.Label(sf,text="…",font=FS,bg=C["sidebar"],fg=C["muted"])
        self._slbl.pack(side=tk.LEFT,padx=4)

        chat=tk.Frame(r,bg=C["chat_bg"])
        chat.grid(row=0,column=1,sticky="nsew")
        chat.rowconfigure(0,weight=1); chat.rowconfigure(1,weight=0)
        chat.columnconfigure(0,weight=1)

        cvf=tk.Frame(chat,bg=C["chat_bg"])
        cvf.grid(row=0,column=0,sticky="nsew")
        cvf.rowconfigure(0,weight=1); cvf.columnconfigure(0,weight=1)
        self._cv=tk.Canvas(cvf,bg=C["chat_bg"],highlightthickness=0)
        vsb=ttk.Scrollbar(cvf,orient="vertical",command=self._cv.yview)
        self._msgs=tk.Frame(self._cv,bg=C["chat_bg"])
        self._cw=self._cv.create_window((0,0),window=self._msgs,anchor="nw")
        self._cv.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT,fill=tk.Y)
        self._cv.pack(side=tk.LEFT,fill=tk.BOTH,expand=True)
        self._msgs.bind("<Configure>",
            lambda e:self._cv.configure(scrollregion=self._cv.bbox("all")))
        self._cv.bind("<Configure>",
            lambda e:self._cv.itemconfig(self._cw,width=e.width))
        self._cv.bind_all("<MouseWheel>",
            lambda e:self._cv.yview_scroll(-1*(e.delta//120),"units"))

        tk.Label(self._msgs,
            text="Ciao! Sono DUST AI v4.2\nSono autoconsapevole e posso agire sul tuo PC.\nCome posso aiutarti?",
            font=FT,bg=C["chat_bg"],fg=C["accent"],pady=40).pack()

        inp=tk.Frame(chat,bg=C["input_bg"],pady=12,padx=14)
        inp.grid(row=1,column=0,sticky="ew"); inp.columnconfigure(0,weight=1)
        self._inp=tk.Text(inp,height=3,font=FF,bg=C["input_bg"],fg=C["input_fg"],
                         relief="flat",bd=0,wrap=tk.WORD,
                         insertbackground=C["accent"],padx=10,pady=8)
        self._inp.grid(row=0,column=0,sticky="ew",padx=(0,10))
        self._inp.bind("<Return>",self._on_enter)
        self._inp.bind("<Shift-Return>",lambda e:None)
        tk.Button(inp,text="Invia  ▶",font=FF,bg=C["accent"],fg=C["bg"],
                 relief="flat",padx=14,pady=8,cursor="hand2",
                 command=self._send).grid(row=0,column=1)
        tk.Label(inp,text="Invio = invia  |  Shift+Invio = a capo",font=FS,
                bg=C["input_bg"],fg=C["muted"]).grid(
            row=1,column=0,columnspan=2,sticky="w",pady=(4,0))

    def _init_agent(self):
        try:
            import importlib
            from agent import Agent
            from tools.registry import Registry
            import tools.computer_use as cu
            from self_knowledge import (self_inspect, self_list_tools,
                                        self_env, self_edit_file,
                                        self_reload_module)

            reg = Registry()
            reg.register_module(cu)
            reg.register_function("self_inspect",    self_inspect,
                "Leggi il codice sorgente di DUST")
            reg.register_function("self_list_tools", self_list_tools,
                "Elenca tutti i tool di DUST")
            reg.register_function("self_env",        self_env,
                "Ambiente OS/Python/RAM/modelli")
            reg.register_function("self_edit_file",  self_edit_file,
                "Modifica un file sorgente di DUST")
            reg.register_function("self_reload",     self_reload_module,
                "Ricarica un modulo Python")

            for mn in ("tools.file_ops","tools.web_search","tools.sys_exec",
                       "tools.browser","tools.input_control",
                       "tools.windows_apps","tools.code_runner",
                       "tools.github_tool"):
                try:
                    m=importlib.import_module(mn); reg.register_module(m)
                except Exception:
                    pass

            try:
                from github_sync import sync_push,sync_pull,get_status
                reg.register_function("github_push",  sync_push,  "Push GitHub")
                reg.register_function("github_pull",  sync_pull,  "Pull GitHub")
                reg.register_function("github_status",get_status, "Git status")
            except Exception:
                pass

            bridge=None
            try:
                from tools.browser_ai_bridge import BrowserAIBridge
                bridge=BrowserAIBridge()
            except Exception:
                pass

            self.agent  = Agent(tools_registry=reg, browser_bridge=bridge)
            self.worker = AgentWorker(self.agent, self._q)
            self.worker.start()

            # Aggiorna badge provider
            from config import GROQ_API_KEY, GEMINI_KEYS
            providers = []
            if GEMINI_KEYS: providers.append(f"Gemini×{len(GEMINI_KEYS)}")
            if GROQ_API_KEY: providers.append("Groq")
            providers.append("Browser")
            providers.append("Ollama")
            self._q.put(("pvd", " → ".join(providers)))
            self._q.put(("status_ok","Pronto"))
        except Exception as exc:
            self._q.put(("status_err",f"Init: {exc}"))

    def _reset_login(self):
        """Elimina il marker di login per forzare re-login Google."""
        try:
            from config import BROWSER_PROFILE_DIR
            from pathlib import Path
            flag = Path(BROWSER_PROFILE_DIR) / ".google_logged_in"
            if flag.exists():
                flag.unlink()
                self._add_bubble(
                    "🔄 Marker di login eliminato.\n"
                    "Al prossimo messaggio che usa BrowserAI,\n"
                    "si aprirà Chrome per fare di nuovo login Google.", "assistant")
            else:
                self._add_bubble("ℹ️ Nessun login salvato.", "assistant")
        except Exception as exc:
            self._add_bubble(f"❌ {exc}", "assistant")

    def _inspect_self(self):
        self._inp.delete("1.0",tk.END)
        self._inp.insert("1.0",
            "Elenca tutti i tuoi file sorgente e i tool disponibili, "
            "poi descrivi brevemente la tua architettura e la cascade AI.")
        self._send()

    def _on_enter(self, event):
        if not (event.state & 0x1):
            self._send(); return "break"

    def _send(self):
        txt=self._inp.get("1.0",tk.END).strip()
        if not txt: return
        self._inp.delete("1.0",tk.END)
        self._add_bubble(txt,"user")
        self.history.append({"role":"user","content":txt})
        self._inp.configure(state=tk.DISABLED)
        self._set_status("Elaborando…","warn")
        if self.worker:
            self.worker.submit(txt, list(self.history[:-1]))
        else:
            self._q.put(("error","Agent non pronto, riprova."))

    def _poll(self):
        try:
            while True:
                kind,data=self._q.get_nowait()
                if kind=="thinking": self._show_think()
                elif kind=="response":
                    self._hide_think()
                    self._add_bubble(data,"assistant")
                    self.history.append({"role":"assistant","content":data})
                    self._inp.configure(state=tk.NORMAL)
                elif kind=="error":
                    self._hide_think()
                    self._add_bubble(f"❌ {data}","assistant")
                    self._inp.configure(state=tk.NORMAL)
                elif kind=="status_ok": self._set_status(data,"ok")
                elif kind=="status_err": self._set_status(data,"err")
                elif kind=="pvd": self._pvd.configure(text=f"AI: {data[:28]}")
        except queue.Empty:
            pass
        self.root.after(80,self._poll)

    def _add_bubble(self, text, role):
        b=Bubble(self._msgs,text,role); b.pack(fill=tk.X)
        self.root.after(120,lambda:self._cv.yview_moveto(1.0))

    def _show_think(self):
        if self._think is None:
            self._think=Thinking(self._msgs); self._think.pack(fill=tk.X)
        self.root.after(120,lambda:self._cv.yview_moveto(1.0))

    def _hide_think(self):
        if self._think:
            self._think.kill(); self._think.destroy(); self._think=None

    def _new_chat(self):
        self.history.clear()
        for w in self._msgs.winfo_children(): w.destroy()
        tk.Label(self._msgs,text="Nuova chat — come posso aiutarti?",
                font=FT,bg=C["chat_bg"],fg=C["accent"],pady=40).pack()

    def _set_status(self, text, level="ok"):
        col={"ok":C["ok"],"err":C["err"],"warn":C["warn"]}.get(level,C["muted"])
        self._dot.configure(fg=col); self._slbl.configure(text=text[:35])


def main():
    root=tk.Tk()
    style=ttk.Style()
    try: style.theme_use("clam")
    except Exception: pass
    style.configure("Vertical.TScrollbar",
        background=C["border"],troughcolor=C["chat_bg"],
        borderwidth=0,arrowsize=12)
    DustGUI(root); root.mainloop()


if __name__=="__main__":
    main()
'''

# ══════════════════════════════════════════════════════════════════
#  ISTRUZIONI .env aggiornate
# ══════════════════════════════════════════════════════════════════
FILES["dustai_stuff_env_sample.txt"] = r'''
# ──────────────────────────────────────────────────────────────────
#  Salva come:  A:\dustai_stuff\.env
# ──────────────────────────────────────────────────────────────────

# Gemini API (3 chiavi × 1.500 req/day gratis ciascuna)
# Crea progetti su: aistudio.google.com > API key
GOOGLE_API_KEY=AIza...
GOOGLE_API_KEY_2=AIza...
GOOGLE_API_KEY_3=AIza...

# ★ GROQ API — 14.400 req/day GRATIS (llama-3.3-70b, velocissimo)
# Registrati su: console.groq.com > API Keys > Create API Key
# È GRATIS, non richiede carta di credito, mai addebitato
GROQ_API_KEY=gsk_...

# GitHub sync (opzionale)
GITHUB_TOKEN=ghp_...
GITHUB_USER=Tenkulo

# OpenRouter (opzionale, modelli aggiuntivi)
OPENROUTER_API_KEY=sk-or-v1-...
'''

# ══════════════════════════════════════════════════════════════════
#  INSTALLER
# ══════════════════════════════════════════════════════════════════
import os, sys, subprocess, textwrap
from pathlib import Path

BASE  = Path(r"A:\dustai")
SRC   = BASE / "src"


def write_files():
    print("\n📁  Scrittura file…")
    for rel, content in FILES.items():
        # il file sample va in dustai_stuff
        if rel == "dustai_stuff_env_sample.txt":
            dest = Path(r"A:\dustai_stuff") / "env_sample.txt"
        else:
            dest = BASE / rel.replace("/", os.sep)
        dest.parent.mkdir(parents=True, exist_ok=True)
        text = textwrap.dedent(content).lstrip("\n")
        dest.write_text(text, encoding="utf-8")
        print(f"  ✅  {dest.relative_to(BASE) if BASE in dest.parents else dest}")


def install_deps():
    print("\n📦  Dipendenze…")
    for pkg in ["google-genai", "playwright", "pyautogui",
                "Pillow", "requests", "python-dotenv", "psutil"]:
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", pkg, "-q",
             "--break-system-packages"],
            capture_output=True, text=True)
        print(f"  {'✅' if r.returncode==0 else '⚠️ '} {pkg}")
    r = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        capture_output=True, text=True)
    print("  ✅  playwright chromium" if r.returncode==0 else "  ⚠️  playwright chromium")


def git_push():
    print("\n🚀  Git…")
    def git(args):
        return subprocess.run(["git"]+args, cwd=str(BASE),
                              capture_output=True, text=True)
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(r"A:\dustai_stuff\.env"), override=True)
    except Exception:
        pass
    token = os.environ.get("GITHUB_TOKEN","")
    user  = os.environ.get("GITHUB_USER","Tenkulo")
    if token:
        git(["remote","set-url","origin",
             f"https://{user}:{token}@github.com/{user}/dustai.git"])
    git(["add","-A"])
    st = git(["status","--porcelain"])
    if not st.stdout.strip():
        print("  ℹ️  Niente da committare."); return
    r = git(["commit","-m","fix: Groq cascade + BrowserAI persistent profile + selectors"])
    print("  ✅  commit" if r.returncode==0 else f"  ❌  {r.stderr[:100]}")
    r = git(["push","origin","master"])
    print("  ✅  push" if r.returncode==0 else f"  ❌  {r.stderr[:100]}")


def print_next_steps():
    print("""
╔══════════════════════════════════════════════════════════════╗
║  COSA FARE ORA:                                              ║
║                                                              ║
║  1) Aggiungi GROQ_API_KEY in A:\\dustai_stuff\\.env          ║
║     → console.groq.com > API Keys > Create (GRATIS)         ║
║                                                              ║
║  2) Avvia DUST:  .\\run.bat                                  ║
║                                                              ║
║  3) PRIMA VOLTA con BrowserAI:                               ║
║     → Si apre Chrome, fai login Google                      ║
║     → Sessione salvata in dustai_stuff\\browser_profile      ║
║     → Tutti i run successivi: automatico                     ║
║                                                              ║
║  CASCADE FINALE:                                             ║
║    ① Gemini KEY1  (1.500 req/day)                           ║
║    ② Gemini KEY2  (1.500 req/day)                           ║
║    ③ Gemini KEY3  (1.500 req/day)                           ║
║    ④ Groq llama-3.3-70b  (14.400 req/day) ← NUOVO          ║
║    ⑤ BrowserAI  (Chrome profilo persistente) ← FIX         ║
║    ⑥ Ollama qwen3:8b  (locale, 300s timeout)               ║
║    ⑦ Ollama mistral-small3.1                                ║
╚══════════════════════════════════════════════════════════════╝
""")


if __name__ == "__main__":
    print("="*62)
    print("  DUST AI — FIX PATCH #3  (Groq + BrowserAI persistente)")
    print("="*62)
    write_files()
    install_deps()
    git_push()
    print_next_steps()
