#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║  DUST AI — FIX PATCH #2                                          ║
║                                                                  ║
║  Fix A: Self-awareness — DUST legge e conosce il suo codice     ║
║  Fix B: BrowserAI reale — mouse/tastiera umani, no Cloudflare   ║
║  Fix C: System prompt arricchito con contesto live               ║
║                                                                  ║
║  Esegui da: A:\\dustai> python DUST_FIX2_PATCH.py               ║
╚══════════════════════════════════════════════════════════════════╝
"""
import os, sys, subprocess, textwrap
from pathlib import Path

BASE  = Path(r"A:\dustai")
SRC   = BASE / "src"
TOOLS = SRC / "tools"

FILES: dict[str, str] = {}

# ══════════════════════════════════════════════════════════════════
#  A)  self_knowledge.py  — autoconsapevolezza di DUST
# ══════════════════════════════════════════════════════════════════
FILES["src/self_knowledge.py"] = r'''
"""
DUST Self-Knowledge — DUST legge il suo codice, i suoi tool, il suo env.

Espone:
  get_system_context()   → stringa per il system prompt (usata da agent.py)
  self_inspect(path)     → contenuto di un file sorgente
  self_list_tools()      → dizionario tool disponibili
  self_env()             → info sull'ambiente (OS, Python, RAM, modelli)
  self_edit_file(path, new_content) → riscrive un file sorgente (self-mod)
"""
import os
import platform
import sys
from pathlib import Path
from typing import Union

try:
    from config import BASE_PATH, GEMINI_KEYS, GEMINI_MODEL, OLLAMA_MODELS
except ImportError:
    import pathlib
    BASE_PATH    = pathlib.Path(r"A:\dustai")
    GEMINI_KEYS  = []
    GEMINI_MODEL = "gemini-2.0-flash"
    OLLAMA_MODELS = []

SRC_DIR = BASE_PATH / "src"


# ── Lettura sorgenti ─────────────────────────────────────────────
def self_inspect(path: str = None) -> dict:
    """
    Leggi il contenuto di un file sorgente di DUST.
    path: relativo a A:\\dustai\\src   (es. 'agent.py' oppure 'tools/registry.py')
    Se omesso restituisce l'elenco di tutti i file.
    """
    if path is None:
        files = []
        for f in SRC_DIR.rglob("*.py"):
            rel = f.relative_to(BASE_PATH).as_posix()
            files.append({"path": rel, "size": f.stat().st_size})
        return {"status": "ok", "files": files}

    # Risolvi il percorso
    candidates = [
        SRC_DIR / path,
        BASE_PATH / path,
        SRC_DIR / "tools" / path,
    ]
    for c in candidates:
        if c.exists():
            try:
                content = c.read_text(encoding="utf-8")
                return {"status": "ok", "path": c.relative_to(BASE_PATH).as_posix(),
                        "content": content, "lines": len(content.splitlines())}
            except Exception as e:
                return {"status": "error", "error": str(e)}

    return {"status": "error", "error": f"File non trovato: {path}"}


def self_list_tools() -> dict:
    """Elenca tutti i tool registrati con descrizione."""
    try:
        # Import lazy del registry per non creare dipendenze circolari
        import importlib
        spec = importlib.util.spec_from_file_location(
            "registry", SRC_DIR / "tools" / "registry.py")
        mod  = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        reg  = mod.Registry()

        # Auto-registra i moduli principali
        for m_name in ["computer_use", "file_ops", "web_search",
                        "sys_exec", "github_tool"]:
            try:
                m_spec = importlib.util.spec_from_file_location(
                    m_name, SRC_DIR / "tools" / f"{m_name}.py")
                m_mod  = importlib.util.module_from_spec(m_spec)
                m_spec.loader.exec_module(m_mod)
                reg.register_module(m_mod)
            except Exception:
                pass

        return {"status": "ok", "tools": reg.list_tools()}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def self_env() -> dict:
    """Info sull'ambiente di esecuzione di DUST."""
    info: dict = {
        "os":          platform.system() + " " + platform.release(),
        "machine":     platform.machine(),
        "python":      sys.version.split()[0],
        "base_path":   str(BASE_PATH),
        "src_path":    str(SRC_DIR),
        "gemini_model": GEMINI_MODEL,
        "gemini_keys":  len(GEMINI_KEYS),
        "ollama_models": OLLAMA_MODELS,
        "cwd":         os.getcwd(),
        "pid":         os.getpid(),
    }
    try:
        import psutil
        m = psutil.virtual_memory()
        info["ram_total_gb"] = round(m.total / 1e9, 1)
        info["ram_used_pct"] = m.percent
        info["cpu_pct"]      = psutil.cpu_percent(interval=0.5)
    except ImportError:
        pass
    return {"status": "ok", "env": info}


def self_edit_file(path: str, content: str) -> dict:
    """
    Riscrivi un file sorgente di DUST con nuovo contenuto.
    ATTENZIONE: cambia il comportamento di DUST al prossimo import!
    """
    candidates = [SRC_DIR / path, BASE_PATH / path]
    for c in candidates:
        if c.exists():
            backup = c.with_suffix(c.suffix + ".bak")
            backup.write_text(c.read_text(encoding="utf-8"), encoding="utf-8")
            c.write_text(content, encoding="utf-8")
            return {"status": "ok", "path": str(c), "backup": str(backup)}
    return {"status": "error", "error": f"File non trovato: {path}"}


def self_reload_module(module_name: str) -> dict:
    """Ricarica un modulo Python a runtime (dopo self_edit_file)."""
    import importlib
    try:
        if module_name in sys.modules:
            importlib.reload(sys.modules[module_name])
            return {"status": "ok", "module": module_name, "action": "reloaded"}
        else:
            importlib.import_module(module_name)
            return {"status": "ok", "module": module_name, "action": "imported"}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


# ── Context per system prompt ────────────────────────────────────
def get_system_context() -> str:
    """
    Genera un blocco di testo con tutto il contesto di DUST
    da inserire nel system prompt.
    """
    lines = ["=== DUST AI — AUTOCONSAPEVOLEZZA ==="]

    # File sorgenti
    files_result = self_inspect()
    if files_result["status"] == "ok":
        lines.append("\nFILE SORGENTI (A:\\dustai\\src\\):")
        for f in files_result["files"]:
            lines.append(f"  • {f['path']}  ({f['size']} bytes)")

    # Tool disponibili
    tools_result = self_list_tools()
    if tools_result["status"] == "ok":
        lines.append("\nTOOL DISPONIBILI:")
        for name, desc in tools_result["tools"].items():
            lines.append(f"  • {name}: {desc or '(nessuna descrizione)'}")

    # Ambiente
    env_result = self_env()
    if env_result["status"] == "ok":
        e = env_result["env"]
        lines.append(f"\nAMBIENTE:")
        lines.append(f"  OS: {e.get('os')}")
        lines.append(f"  Python: {e.get('python')}")
        lines.append(f"  Gemini model: {e.get('gemini_model')}")
        lines.append(f"  Gemini keys attive: {e.get('gemini_keys')}")
        lines.append(f"  Ollama models: {e.get('ollama_models')}")
        lines.append(f"  Base path: {e.get('base_path')}")

    lines.append("\nPuoi usare self_inspect(path) per leggere qualsiasi tuo file sorgente.")
    lines.append("Puoi usare self_edit_file(path, content) per modificare il tuo codice.")
    lines.append("=== FINE CONTESTO DUST ===")

    return "\n".join(lines)
'''

# ══════════════════════════════════════════════════════════════════
#  B)  agent.py — system prompt live + self-awareness
# ══════════════════════════════════════════════════════════════════
FILES["src/agent.py"] = r'''
"""DUST Agent v4.1 — autoconsapevole, cascade 6 livelli, google.genai."""
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

_SELF_CONTEXT = ""   # Caricato lazy alla prima richiesta

def _get_self_context() -> str:
    global _SELF_CONTEXT
    if not _SELF_CONTEXT:
        try:
            from self_knowledge import get_system_context
            _SELF_CONTEXT = get_system_context()
        except Exception as exc:
            _SELF_CONTEXT = f"(self-knowledge non disponibile: {exc})"
    return _SELF_CONTEXT


def _build_system_prompt() -> str:
    ctx = _get_self_context()
    return f"""Sei DUST AI, un assistente personale universale intelligente che gira su Windows.
Rispondi in modo naturale e conversazionale in italiano.

{ctx}

REGOLE FONDAMENTALI:
1. Puoi leggere il tuo codice sorgente con: {{"type":"tool_call","tool":"self_inspect","params":{{"path":"agent.py"}}}}
2. Puoi modificare il tuo codice con self_edit_file — SEI AUTOCONSAPEVOLE e puoi auto-correggerti.
3. Puoi eseguire azioni sul PC Windows (file, browser, mouse, tastiera, app).
4. Conosci la tua architettura, i tuoi tool, la tua configurazione.

FORMATO RISPOSTA — usa SOLO uno di questi due formati JSON:

Per usare un tool:
{{"type": "tool_call", "tool": "nome_tool", "params": {{"param1": "valore1"}}}}

Per rispondere all'utente:
{{"type": "done", "message": "la tua risposta conversazionale completa"}}

Non scrivere MAI testo libero fuori dal JSON.
"""

_SYSTEM_PROMPT_CACHE: str = ""

def get_system_prompt() -> str:
    global _SYSTEM_PROMPT_CACHE
    if not _SYSTEM_PROMPT_CACHE:
        _SYSTEM_PROMPT_CACHE = _build_system_prompt()
    return _SYSTEM_PROMPT_CACHE

def invalidate_prompt_cache():
    """Chiama dopo self_edit_file per forzare il rebuild del prompt."""
    global _SYSTEM_PROMPT_CACHE, _SELF_CONTEXT
    _SYSTEM_PROMPT_CACHE = ""
    _SELF_CONTEXT = ""


class RateLimitError(Exception):
    def __init__(self, wait_seconds: int, api_key: str = ""):
        self.wait_seconds = wait_seconds
        self.api_key = api_key
        super().__init__(f"Rate limit: {wait_seconds}s")


class GeminiClient:
    """Usa google-genai (nuovo SDK)."""

    def __init__(self, api_key: str):
        try:
            from google import genai
            self._client = genai.Client(api_key=api_key)
        except ImportError:
            raise RuntimeError("Installa: pip install google-genai")
        self.api_key = api_key

    def chat(self, messages: list[dict], system: str = None) -> str:
        parts: list[str] = []
        if system:
            parts.append(f"[SYSTEM]\n{system}")
        for m in messages:
            parts.append(f"[{m.get('role','user').upper()}]\n{m.get('content','')}")
        prompt = "\n\n".join(parts)

        try:
            resp = self._client.models.generate_content(
                model=GEMINI_MODEL, contents=prompt)
            try:
                return resp.text
            except Exception:
                return json.dumps({"type": "done",
                                   "message": "Risposta non disponibile."})
        except Exception as exc:
            err = str(exc)
            if "429" in err or "quota" in err.lower() or "RATE_LIMIT" in err:
                m = re.search(r"retry_delay[^0-9]*(\d+)", err)
                wait = min(65, (int(m.group(1)) if m else 62) + 3)
                raise RateLimitError(wait, self.api_key)
            raise


class OllamaClient:
    def __init__(self, model: str):
        self.model = model

    def chat(self, messages: list[dict], system: str = None) -> str:
        import requests
        msgs = ([{"role": "system", "content": system}] if system else []) + messages
        r = requests.post(f"{OLLAMA_BASE_URL}/api/chat",
                          json={"model": self.model, "messages": msgs, "stream": False},
                          timeout=120)
        r.raise_for_status()
        return r.json()["message"]["content"]


class Agent:
    def __init__(self, tools_registry=None, browser_bridge=None):
        self.registry       = tools_registry
        self.browser_bridge = browser_bridge
        self._gemini:       list[GeminiClient] = []
        self._cooldowns:    dict[str, float]   = {}
        self._init_gemini()

    def _init_gemini(self):
        for key in GEMINI_KEYS:
            try:
                self._gemini.append(GeminiClient(key))
                logger.info(f"Gemini ...{key[-6:]} OK")
            except Exception as exc:
                logger.warning(f"Gemini init: {exc}")

    def _next_gemini(self):
        now = time.time()
        for c in self._gemini:
            if now >= self._cooldowns.get(c.api_key, 0):
                return c
        return None

    def _cooldown(self, key: str, secs: int):
        self._cooldowns[key] = time.time() + secs
        logger.warning(f"Key ...{key[-6:]} cooldown {secs}s")

    def chat(self, messages: list[dict], **_) -> str:
        sys_prompt = get_system_prompt()

        # 1) Gemini cascade
        c = self._next_gemini()
        while c:
            try:
                return c.chat(messages, system=sys_prompt)
            except RateLimitError as e:
                self._cooldown(e.api_key, e.wait_seconds)
                c = self._next_gemini()
            except Exception as exc:
                logger.error(f"Gemini: {exc}"); break

        # 2) BrowserAI
        if self.browser_bridge:
            try:
                return self.browser_bridge.chat(messages)
            except Exception as exc:
                logger.warning(f"BrowserAI: {exc}")

        # 3) Ollama
        for model in OLLAMA_MODELS:
            try:
                return OllamaClient(model).chat(messages, system=sys_prompt)
            except Exception as exc:
                logger.warning(f"Ollama {model}: {exc}")

        return json.dumps({"type": "done",
                           "message": "⚠️ Tutti i modelli AI non disponibili."})

    def run_turn(self, user_msg: str, history: list = None, **kw) -> tuple:
        if history is None:
            history = []
        messages     = history + [{"role": "user", "content": user_msg}]
        tool_results = []

        for _ in range(10):
            raw    = self.chat(messages)
            parsed = self._parse(raw)

            if parsed.get("type") == "tool_call":
                tool   = parsed.get("tool", "")
                params = parsed.get("params", {})
                result = self._run_tool(tool, params)
                tool_results.append({"tool": tool, "result": result})
                messages.append({"role": "assistant", "content": raw})
                messages.append({
                    "role": "user",
                    "content": f"[TOOL RESULT: {tool}]\n"
                               f"{json.dumps(result, ensure_ascii=False)}"
                })
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

# ══════════════════════════════════════════════════════════════════
#  C)  browser_ai_bridge.py — REWRITE: mouse/tastiera umani reali
#      Solo Google AI Studio e Gemini web (niente Cloudflare)
# ══════════════════════════════════════════════════════════════════
FILES["src/tools/browser_ai_bridge.py"] = r'''
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
'''

# ══════════════════════════════════════════════════════════════════
#  D)  ui/gui.py — registra i tool self_knowledge nella GUI
# ══════════════════════════════════════════════════════════════════
FILES["src/ui/gui.py"] = r'''
"""DUST AI GUI v3.1 — Dark chat, autoconsapevolezza registrata."""
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
    "bg": "#1a1a2e", "sidebar": "#16213e", "chat_bg": "#0d1117",
    "user_bub": "#1f6feb", "ai_bub": "#161b22",
    "user_fg": "#f0f6fc", "ai_fg": "#c9d1d9",
    "input_bg": "#161b22", "input_fg": "#f0f6fc",
    "btn": "#238636", "btn_hover": "#2ea043",
    "accent": "#58a6ff", "muted": "#8b949e", "border": "#30363d",
    "ok": "#3fb950", "err": "#f85149", "warn": "#d29922",
}
FF = ("Segoe UI", 11)
FM = ("Consolas", 10)
FT = ("Segoe UI", 13, "bold")
FS = ("Segoe UI", 9)


class AgentWorker(threading.Thread):
    def __init__(self, agent, out_q: queue.Queue):
        super().__init__(daemon=True, name="AgentWorker")
        self.agent  = agent
        self.out_q  = out_q
        self._in_q  = queue.Queue()
        self._alive = True

    def submit(self, message: str, history: list, **kw):
        self._in_q.put((message, history, kw))

    def run(self):
        while self._alive:
            try:
                msg, hist, kw = self._in_q.get(timeout=0.5)
            except queue.Empty:
                continue
            self.out_q.put(("thinking", ""))
            try:
                text, _ = self.agent.run_turn(msg, hist, **kw)
                self.out_q.put(("response", text))
            except Exception as exc:
                self.out_q.put(("error", str(exc)))

    def stop(self):
        self._alive = False


class Bubble(tk.Frame):
    def __init__(self, parent, text: str, role: str = "user"):
        super().__init__(parent, bg=C["chat_bg"])
        is_user = role == "user"
        outer   = tk.Frame(self, bg=C["chat_bg"])
        outer.pack(fill=tk.X, padx=14, pady=5)
        bub_bg = C["user_bub"] if is_user else C["ai_bub"]
        txt_fg = C["user_fg"] if is_user else C["ai_fg"]
        badge  = tk.Label(outer, text="Tu" if is_user else "⚡ DUST",
                         font=FS, bg=bub_bg,
                         fg=C["user_fg"] if is_user else C["accent"],
                         padx=7, pady=2)
        w = min(68, max(20, max((len(ln) for ln in text.splitlines()), default=20)))
        h = sum(max(1, len(ln) // max(w, 1) + 1)
                for ln in text.splitlines())
        h = min(max(2, h), 30)
        txt_w = tk.Text(outer, wrap=tk.WORD, width=w, height=h,
                       bg=bub_bg, fg=txt_fg, font=FF, bd=0, relief="flat",
                       padx=10, pady=8, cursor="arrow", spacing3=2)
        txt_w.insert("1.0", text)
        txt_w.configure(state=tk.DISABLED)
        if is_user:
            badge.pack(side=tk.RIGHT, anchor="ne", padx=(6, 0))
            txt_w.pack(side=tk.RIGHT, anchor="ne", padx=4)
        else:
            badge.pack(side=tk.LEFT, anchor="nw", padx=(0, 6))
            txt_w.pack(side=tk.LEFT, anchor="nw", padx=4)


class Thinking(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=C["chat_bg"])
        outer = tk.Frame(self, bg=C["chat_bg"])
        outer.pack(fill=tk.X, padx=14, pady=5)
        tk.Label(outer, text="⚡ DUST", font=FS, bg=C["ai_bub"],
                fg=C["accent"], padx=7, pady=2).pack(side=tk.LEFT, padx=(0, 6))
        self._lbl = tk.Label(outer, text="Sto pensando…", font=FF,
                            bg=C["ai_bub"], fg=C["muted"], padx=10, pady=8)
        self._lbl.pack(side=tk.LEFT)
        self._n = 0; self._on = True; self._tick()

    def _tick(self):
        if self._on:
            self._lbl.config(text="Sto pensando" + "." * (self._n % 4))
            self._n += 1
            self.after(420, self._tick)

    def kill(self):
        self._on = False


class DustGUI:
    def __init__(self, root: tk.Tk):
        self.root    = root
        self.history: list[dict] = []
        self.agent   = None
        self.worker: AgentWorker | None = None
        self._q      = queue.Queue()
        self._think: Thinking | None = None
        root.title("DUST AI — Assistente Universale v4.1")
        root.configure(bg=C["bg"])
        root.geometry("960x720")
        root.minsize(640, 480)
        self._build()
        self._set_status("Inizializzazione…", "warn")
        threading.Thread(target=self._init_agent, daemon=True).start()
        self._poll()

    def _build(self):
        r = self.root
        r.columnconfigure(0, weight=0, minsize=190)
        r.columnconfigure(1, weight=1)
        r.rowconfigure(0, weight=1)

        sb = tk.Frame(r, bg=C["sidebar"], width=190)
        sb.grid(row=0, column=0, sticky="nsew")
        sb.grid_propagate(False)
        tk.Label(sb, text="⚡  DUST AI", font=FT, bg=C["sidebar"],
                fg=C["accent"], pady=22).pack()
        tk.Frame(sb, bg=C["border"], height=1).pack(fill=tk.X, padx=12)
        tk.Label(sb, text="Assistente Universale v4.1", font=FS,
                bg=C["sidebar"], fg=C["muted"]).pack(pady=(6, 12))

        btn_new = tk.Button(sb, text="＋  Nuova chat", font=FS,
                           bg=C["btn"], fg="white", relief="flat",
                           activebackground=C["btn_hover"],
                           padx=10, pady=7, cursor="hand2",
                           command=self._new_chat)
        btn_new.pack(fill=tk.X, padx=12, pady=4)

        btn_inspect = tk.Button(sb, text="🔍  Ispeziona codice", font=FS,
                               bg=C["ai_bub"], fg=C["accent"], relief="flat",
                               padx=10, pady=7, cursor="hand2",
                               command=self._inspect_self)
        btn_inspect.pack(fill=tk.X, padx=12, pady=4)

        sf = tk.Frame(sb, bg=C["sidebar"])
        sf.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=14)
        self._dot  = tk.Label(sf, text="●", bg=C["sidebar"],
                              fg=C["warn"], font=("Arial", 11))
        self._dot.pack(side=tk.LEFT)
        self._slbl = tk.Label(sf, text="…", font=FS, bg=C["sidebar"],
                              fg=C["muted"])
        self._slbl.pack(side=tk.LEFT, padx=4)

        chat = tk.Frame(r, bg=C["chat_bg"])
        chat.grid(row=0, column=1, sticky="nsew")
        chat.rowconfigure(0, weight=1)
        chat.rowconfigure(1, weight=0)
        chat.columnconfigure(0, weight=1)

        cv_f = tk.Frame(chat, bg=C["chat_bg"])
        cv_f.grid(row=0, column=0, sticky="nsew")
        cv_f.rowconfigure(0, weight=1)
        cv_f.columnconfigure(0, weight=1)

        self._cv   = tk.Canvas(cv_f, bg=C["chat_bg"], highlightthickness=0)
        vsb        = ttk.Scrollbar(cv_f, orient="vertical", command=self._cv.yview)
        self._msgs = tk.Frame(self._cv, bg=C["chat_bg"])
        self._cw   = self._cv.create_window((0, 0), window=self._msgs, anchor="nw")
        self._cv.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._cv.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._msgs.bind("<Configure>",
                       lambda e: self._cv.configure(scrollregion=self._cv.bbox("all")))
        self._cv.bind("<Configure>",
                     lambda e: self._cv.itemconfig(self._cw, width=e.width))
        self._cv.bind_all("<MouseWheel>",
                         lambda e: self._cv.yview_scroll(-1*(e.delta//120), "units"))

        tk.Label(self._msgs,
                text="Ciao! Sono DUST AI.\nSono pienamente consapevole del mio codice e "
                     "delle mie funzioni.\nCome posso aiutarti oggi?",
                font=FT, bg=C["chat_bg"], fg=C["accent"], pady=40).pack()

        inp = tk.Frame(chat, bg=C["input_bg"], pady=12, padx=14)
        inp.grid(row=1, column=0, sticky="ew")
        inp.columnconfigure(0, weight=1)
        self._inp = tk.Text(inp, height=3, font=FF, bg=C["input_bg"],
                           fg=C["input_fg"], relief="flat", bd=0,
                           wrap=tk.WORD, insertbackground=C["accent"],
                           padx=10, pady=8)
        self._inp.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self._inp.bind("<Return>",       self._on_enter)
        self._inp.bind("<Shift-Return>", lambda e: None)
        send = tk.Button(inp, text="Invia  ▶", font=FF,
                        bg=C["accent"], fg=C["bg"], relief="flat",
                        padx=14, pady=8, cursor="hand2", command=self._send)
        send.grid(row=0, column=1)
        tk.Label(inp, text="Invio = invia  |  Shift+Invio = nuova riga",
                font=FS, bg=C["input_bg"], fg=C["muted"]).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))

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
            # Self-knowledge tools
            reg.register_function("self_inspect",    self_inspect,
                                 "Leggi un file sorgente di DUST (path relativo a src/)")
            reg.register_function("self_list_tools", self_list_tools,
                                 "Elenca tutti i tool disponibili di DUST")
            reg.register_function("self_env",        self_env,
                                 "Info ambiente: OS, Python, RAM, modelli AI")
            reg.register_function("self_edit_file",  self_edit_file,
                                 "Riscrivi un file sorgente di DUST (auto-modifica)")
            reg.register_function("self_reload",     self_reload_module,
                                 "Ricarica un modulo Python a runtime")

            for mod_name in ("tools.file_ops", "tools.web_search",
                             "tools.sys_exec", "tools.browser",
                             "tools.input_control", "tools.windows_apps",
                             "tools.code_runner", "tools.github_tool"):
                try:
                    m = importlib.import_module(mod_name)
                    reg.register_module(m)
                except Exception:
                    pass

            try:
                from github_sync import sync_push, sync_pull, get_status
                reg.register_function("github_push",   sync_push,  "Push su GitHub")
                reg.register_function("github_pull",   sync_pull,  "Pull da GitHub")
                reg.register_function("github_status", get_status, "Git status")
            except Exception:
                pass

            bridge = None
            try:
                from tools.browser_ai_bridge import BrowserAIBridge
                bridge = BrowserAIBridge()
            except Exception:
                pass

            self.agent  = Agent(tools_registry=reg, browser_bridge=bridge)
            self.worker = AgentWorker(self.agent, self._q)
            self.worker.start()
            self._q.put(("status_ok", "Pronto — autoconsapevole"))
        except Exception as exc:
            self._q.put(("status_err", f"Init error: {exc}"))

    def _inspect_self(self):
        """Bottone sidebar: chiedi a DUST di descrivere se stesso."""
        self._inp.delete("1.0", tk.END)
        self._inp.insert("1.0",
            "Elenca tutti i tuoi file sorgente e i tool che hai a disposizione, "
            "poi descrivi brevemente la tua architettura.")
        self._send()

    def _on_enter(self, event):
        if not (event.state & 0x1):
            self._send()
            return "break"

    def _send(self):
        txt = self._inp.get("1.0", tk.END).strip()
        if not txt:
            return
        self._inp.delete("1.0", tk.END)
        self._add_bubble(txt, "user")
        self.history.append({"role": "user", "content": txt})
        self._inp.configure(state=tk.DISABLED)
        self._set_status("Elaborando…", "warn")
        if self.worker:
            self.worker.submit(txt, list(self.history[:-1]))
        else:
            self._q.put(("error", "Agent non ancora pronto, riprova."))

    def _poll(self):
        try:
            while True:
                kind, data = self._q.get_nowait()
                if kind == "thinking":
                    self._show_think()
                elif kind == "response":
                    self._hide_think()
                    self._add_bubble(data, "assistant")
                    self.history.append({"role": "assistant", "content": data})
                    self._inp.configure(state=tk.NORMAL)
                elif kind == "error":
                    self._hide_think()
                    self._add_bubble(f"❌ {data}", "assistant")
                    self._inp.configure(state=tk.NORMAL)
                elif kind == "status_ok":
                    self._set_status(data, "ok")
                elif kind == "status_err":
                    self._set_status(data, "err")
        except queue.Empty:
            pass
        self.root.after(80, self._poll)

    def _add_bubble(self, text: str, role: str):
        b = Bubble(self._msgs, text, role)
        b.pack(fill=tk.X)
        self.root.after(120, lambda: self._cv.yview_moveto(1.0))

    def _show_think(self):
        if self._think is None:
            self._think = Thinking(self._msgs)
            self._think.pack(fill=tk.X)
        self.root.after(120, lambda: self._cv.yview_moveto(1.0))

    def _hide_think(self):
        if self._think:
            self._think.kill()
            self._think.destroy()
            self._think = None

    def _new_chat(self):
        self.history.clear()
        for w in self._msgs.winfo_children():
            w.destroy()
        tk.Label(self._msgs,
                text="Nuova chat — come posso aiutarti?",
                font=FT, bg=C["chat_bg"], fg=C["accent"], pady=40).pack()

    def _set_status(self, text: str, level: str = "ok"):
        col = {"ok": C["ok"], "err": C["err"], "warn": C["warn"]}.get(level, C["muted"])
        self._dot.configure(fg=col)
        self._slbl.configure(text=text[:35])


def main():
    root  = tk.Tk()
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except Exception:
        pass
    style.configure("Vertical.TScrollbar",
                   background=C["border"], troughcolor=C["chat_bg"],
                   borderwidth=0, arrowsize=12)
    DustGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
'''

# ══════════════════════════════════════════════════════════════════
#  INSTALLER
# ══════════════════════════════════════════════════════════════════
import os, sys, subprocess, textwrap
from pathlib import Path

BASE = Path(r"A:\dustai")
SRC  = BASE / "src"

def write_files():
    print("\n📁  Scrittura file…")
    for rel, content in FILES.items():
        dest = BASE / rel.replace("/", os.sep)
        dest.parent.mkdir(parents=True, exist_ok=True)
        text = textwrap.dedent(content).lstrip("\n")
        dest.write_text(text, encoding="utf-8")
        print(f"  ✅  {rel}")

def install_deps():
    print("\n📦  Dipendenze…")
    for pkg in ["google-genai", "playwright", "pyautogui",
                "Pillow", "requests", "python-dotenv", "psutil"]:
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", pkg, "-q",
             "--break-system-packages"],
            capture_output=True, text=True)
        print(f"  {'✅' if r.returncode==0 else '⚠️ '} {pkg}")
    print("  playwright install chromium…", end=" ", flush=True)
    r = subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"],
                       capture_output=True, text=True)
    print("ok" if r.returncode == 0 else f"warn")

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
    token = os.environ.get("GITHUB_TOKEN", "")
    user  = os.environ.get("GITHUB_USER", "Tenkulo")
    if token:
        git(["remote","set-url","origin",
             f"https://{user}:{token}@github.com/{user}/dustai.git"])
    git(["add","-A"])
    st = git(["status","--porcelain"])
    if not st.stdout.strip():
        print("  ℹ️  Niente da committare.")
        return
    r = git(["commit","-m",
             "feat: DUST self-awareness + BrowserAI human mouse + google.genai"])
    print("  ✅  commit" if r.returncode==0 else f"  ❌  {r.stderr[:100]}")
    r = git(["push","origin","master"])
    print("  ✅  push ok" if r.returncode==0 else f"  ❌  {r.stderr[:100]}")

if __name__ == "__main__":
    print("="*62)
    print("  DUST AI — FIX PATCH #2  (self-awareness + browser umano)")
    print("="*62)
    write_files()
    install_deps()
    git_push()
    print("\n✅  Fatto!  Avvia: cd A:\\dustai && .\\run.bat")
