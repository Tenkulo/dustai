#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║          DUST AI v4.0 — MEGA PATCH INSTALLER                 ║
║  Scrive tutti i file src/, installa dipendenze, git push     ║
║  Esegui da: A:\\dustai> python DUST_MEGA_PATCH.py            ║
╚══════════════════════════════════════════════════════════════╝
"""
import os
import sys
import subprocess
import textwrap
from pathlib import Path

# ─── PATHS ───────────────────────────────────────────────────
BASE   = Path(r"A:\dustai")
SRC    = BASE / "src"
TOOLS  = SRC / "tools"
UI     = SRC / "ui"

def mkdirs():
    for d in [SRC, TOOLS, UI]:
        d.mkdir(parents=True, exist_ok=True)
    for d in [SRC, TOOLS, UI]:
        init = d / "__init__.py"
        if not init.exists():
            init.write_text("")

# ═══════════════════════════════════════════════════════════════
#   FILE CONTENTS
# ═══════════════════════════════════════════════════════════════

FILES = {}

# ─── config.py ───────────────────────────────────────────────
FILES["src/config.py"] = r'''
import os
import pathlib

BASE_PATH  = pathlib.Path(r"A:\dustai")
STUFF_PATH = pathlib.Path(r"A:\dustai_stuff")

# Load .env from dustai_stuff
_env_file = STUFF_PATH / ".env"
if _env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_file, override=True)
    except ImportError:
        # Manual parse fallback
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


# ── Gemini keys (cascade KEY1 → KEY2 → KEY3) ────────────────
GEMINI_KEYS: list[str] = [
    k for k in [
        os.environ.get("GOOGLE_API_KEY"),
        os.environ.get("GOOGLE_API_KEY_2"),
        os.environ.get("GOOGLE_API_KEY_3"),
    ] if k
]

GEMINI_MODEL      = "gemini-2.5-flash-preview-04-17"
GITHUB_TOKEN      = os.environ.get("GITHUB_TOKEN", "")
GITHUB_USER       = os.environ.get("GITHUB_USER", "Tenkulo")
GITHUB_REPO       = "dustai"
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODELS   = ["qwen3:8b", "mistral-small3.1"]
'''

# ─── memory.py ───────────────────────────────────────────────
FILES["src/memory.py"] = r'''
import json
import time
from pathlib import Path

try:
    from config import BASE_PATH
except ImportError:
    import pathlib; BASE_PATH = pathlib.Path(r"A:\dustai")

MEMORY_FILE  = BASE_PATH / "dustai_stuff" / "memory.json"
SKILLS_FILE  = BASE_PATH / "dustai_stuff" / "skills.json"


class Memory:
    """Persistent key-value memory store."""

    def __init__(self):
        self._data: dict = {}
        self._load()

    def _load(self):
        if MEMORY_FILE.exists():
            try:
                self._data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
            except Exception:
                self._data = {}

    def _flush(self):
        MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        MEMORY_FILE.write_text(json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8")

    def save(self, key: str, value) -> None:
        self._data[key] = {"value": value, "ts": time.time()}
        self._flush()

    def get(self, key: str, default=None):
        item = self._data.get(key)
        return item["value"] if item else default

    def delete(self, key: str) -> None:
        self._data.pop(key, None)
        self._flush()

    def all(self) -> dict:
        return {k: v["value"] for k, v in self._data.items()}

    def recent(self, n: int = 10) -> list[tuple]:
        items = sorted(self._data.items(), key=lambda x: x[1].get("ts", 0), reverse=True)
        return [(k, v["value"]) for k, v in items[:n]]


class SkillForge:
    """Learned skills/code snippets store."""

    def __init__(self):
        self._skills: dict = {}
        self._load()

    def _load(self):
        if SKILLS_FILE.exists():
            try:
                self._skills = json.loads(SKILLS_FILE.read_text(encoding="utf-8"))
            except Exception:
                self._skills = {}

    def _flush(self):
        SKILLS_FILE.parent.mkdir(parents=True, exist_ok=True)
        SKILLS_FILE.write_text(json.dumps(self._skills, indent=2, ensure_ascii=False), encoding="utf-8")

    def learn(self, name: str, code: str, description: str = "") -> None:
        self._skills[name] = {"code": code, "desc": description, "uses": 0}
        self._flush()

    def get(self, name: str) -> dict | None:
        skill = self._skills.get(name)
        if skill:
            skill["uses"] += 1
            self._flush()
        return skill

    def list_skills(self) -> list[str]:
        return list(self._skills.keys())


class TaskQueue:
    """Simple in-memory task queue."""

    def __init__(self):
        self._q: list = []

    def push(self, task) -> None:
        self._q.append(task)

    def pop(self):
        return self._q.pop(0) if self._q else None

    def peek(self):
        return self._q[0] if self._q else None

    def is_empty(self) -> bool:
        return len(self._q) == 0

    def all(self) -> list:
        return list(self._q)

    def clear(self) -> None:
        self._q.clear()
'''

# ─── agent.py ────────────────────────────────────────────────
FILES["src/agent.py"] = r'''
"""DUST Agent — cascade AI: Gemini KEY1→KEY2→KEY3→BrowserAI→Ollama."""
import json
import re
import time
import logging
from typing import Any

logger = logging.getLogger("dust.agent")

try:
    from config import GEMINI_KEYS, GEMINI_MODEL, OLLAMA_BASE_URL, OLLAMA_MODELS
except ImportError:
    GEMINI_KEYS = []; GEMINI_MODEL = "gemini-2.5-flash-preview-04-17"
    OLLAMA_BASE_URL = "http://localhost:11434"; OLLAMA_MODELS = ["qwen3:8b"]

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


class GeminiClient:
    def __init__(self, api_key: str):
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        self._genai = genai
        self._model = genai.GenerativeModel(GEMINI_MODEL)
        self.api_key = api_key

    def chat(self, messages: list[dict], system: str = None) -> str:
        parts = []
        if system:
            parts.append(f"[SYSTEM]\n{system}")
        for m in messages:
            role = m.get("role", "user").upper()
            content = m.get("content", "")
            parts.append(f"[{role}]\n{content}")
        prompt = "\n\n".join(parts)

        try:
            response = self._model.generate_content(prompt)
            try:
                return response.text
            except Exception:
                # finish_reason=10 (RECITATION) or other non-text responses
                return json.dumps({"type": "done", "message": "Risposta non disponibile."})
        except Exception as exc:
            err = str(exc)
            if "429" in err or "quota" in err.lower() or "RATE_LIMIT" in err:
                # Extract retry-after seconds safely
                m = re.search(r"retry_delay[^0-9]*(\d+)", err)
                wait = int(m.group(1)) if m else 62
                wait = min(65, int(wait) + 3)   # CLAMP: mai 550M secondi
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
        self._gemini:  list[GeminiClient] = []
        self._cooldowns: dict[str, float] = {}   # key → available_after ts
        self._init_gemini()

    # ── Init ────────────────────────────────────────────────
    def _init_gemini(self):
        for key in GEMINI_KEYS:
            try:
                self._gemini.append(GeminiClient(key))
                logger.info(f"Gemini key ...{key[-6:]} OK")
            except Exception as exc:
                logger.warning(f"Gemini init failed: {exc}")

    # ── Cascade ─────────────────────────────────────────────
    def _next_gemini(self) -> GeminiClient | None:
        now = time.time()
        for c in self._gemini:
            if now >= self._cooldowns.get(c.api_key, 0):
                return c
        return None

    def _cooldown(self, api_key: str, seconds: int):
        self._cooldowns[api_key] = time.time() + seconds
        logger.warning(f"Key ...{api_key[-6:]} in cooldown {seconds}s")

    def chat(self, messages: list[dict], **kwargs) -> str:
        """Cascade: Gemini(1→2→3) → BrowserAI → Ollama qwen3 → Ollama mistral"""
        # ① Gemini keys
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

        # ② BrowserAI bridge
        if self.browser_bridge:
            try:
                return self.browser_bridge.chat(messages)
            except Exception as exc:
                logger.warning(f"BrowserAI: {exc}")

        # ③ Ollama models
        for model in OLLAMA_MODELS:
            try:
                return OllamaClient(model).chat(messages, system=SYSTEM_PROMPT)
            except Exception as exc:
                logger.warning(f"Ollama {model}: {exc}")

        return json.dumps({"type": "done", "message": "⚠️ Tutti i modelli AI non disponibili."})

    # ── Turn ────────────────────────────────────────────────
    def run_turn(self, user_msg: str, history: list[dict] = None, **kwargs) -> tuple[str, list]:
        if history is None:
            history = []
        messages = history + [{"role": "user", "content": user_msg}]
        tool_results = []

        for _ in range(8):          # max 8 tool loops
            raw = self.chat(messages, **kwargs)
            parsed = self._parse(raw)

            if parsed.get("type") == "tool_call":
                tool  = parsed.get("tool", "")
                params = parsed.get("params", {})
                result = self._run_tool(tool, params)
                tool_results.append({"tool": tool, "result": result})
                messages.append({"role": "assistant", "content": raw})
                messages.append({"role": "user",      "content": f"[TOOL RESULT: {tool}]\n{json.dumps(result, ensure_ascii=False)}"})
                continue

            # type == "done" or plain text
            return parsed.get("message", raw), tool_results

        return "Ho completato le operazioni.", tool_results

    def _parse(self, raw: str) -> dict:
        try:
            m = re.search(r'\{.*\}', raw, re.DOTALL)
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

# ─── tools/registry.py ───────────────────────────────────────
FILES["src/tools/registry.py"] = r'''
"""Tool registry with _safe_params v4 — filters private keys, non-scalars, class/callable distinction."""
import inspect
import logging
from typing import Any, Callable

logger = logging.getLogger("dust.registry")

_SINGLETON_CACHE: dict = {}


def _safe_params(fn: Callable, params: dict) -> dict:
    """Keep only params accepted by fn; drop _xxx keys and non-JSON-serializable values."""
    try:
        sig = inspect.signature(fn)
        accepted = set(sig.parameters.keys())
        # Check for **kwargs — if present, pass everything (filtered)
        has_kwargs = any(
            p.kind == inspect.Parameter.VAR_KEYWORD
            for p in sig.parameters.values()
        )
    except (ValueError, TypeError):
        accepted = set(); has_kwargs = True

    out = {}
    for k, v in params.items():
        if k.startswith("_"):
            continue
        if not has_kwargs and k not in accepted:
            continue
        if isinstance(v, (str, int, float, bool, list, dict, type(None))):
            out[k] = v
        # silently drop non-scalar values (e.g. Config._cfg dicts with non-serializable items)
    return out


class Registry:
    def __init__(self):
        self._tools: dict[str, dict] = {}

    def register_function(self, name: str, fn: Callable, description: str = "") -> None:
        self._tools[name] = {"fn": fn, "desc": description}
        logger.debug(f"Registered tool: {name}")

    def register_module(self, module) -> None:
        """Auto-register all public callables (functions, not classes) from a module."""
        for attr_name in dir(module):
            if attr_name.startswith("_"):
                continue
            attr = getattr(module, attr_name)
            # callable but NOT a class
            if callable(attr) and not isinstance(attr, type):
                desc = (getattr(attr, "__doc__", "") or "").strip().split("\n")[0]
                self._tools[attr_name] = {"fn": attr, "desc": desc}

    def call(self, name: str, **kwargs) -> Any:
        if name not in self._tools:
            available = ", ".join(self._tools.keys())
            raise ValueError(f"Tool '{name}' not found. Available: {available}")

        entry = self._tools[name]
        fn    = entry["fn"]

        # Lazy singleton for classes
        if isinstance(fn, type):
            if fn not in _SINGLETON_CACHE:
                _SINGLETON_CACHE[fn] = fn()
            instance = _SINGLETON_CACHE[fn]
            safe = _safe_params(instance.__call__, kwargs)
            return instance(**safe)

        safe = _safe_params(fn, kwargs)
        return fn(**safe)

    def list_tools(self) -> dict[str, str]:
        return {name: t["desc"] for name, t in self._tools.items()}

    def tools_prompt(self) -> str:
        lines = ["Strumenti disponibili:"]
        for name, t in self._tools.items():
            lines.append(f"  {name}: {t['desc']}")
        return "\n".join(lines)
'''

# ─── tools/computer_use.py ───────────────────────────────────
FILES["src/tools/computer_use.py"] = r'''
"""Computer-use tools: screen_read, screen_do, app_open, browser_go."""
import io
import json
import logging
import subprocess
import time
import webbrowser

logger = logging.getLogger("dust.computer_use")


def screen_read(region: list = None) -> dict:
    """Take a screenshot and describe it using Gemini Vision."""
    try:
        import pyautogui
        from PIL import Image
        screenshot = pyautogui.screenshot(region=region)

        buf = io.BytesIO()
        screenshot.save(buf, format="PNG")
        buf.seek(0)

        from config import GEMINI_KEYS, GEMINI_MODEL
        import google.generativeai as genai

        for key in GEMINI_KEYS:
            try:
                genai.configure(api_key=key)
                model = genai.GenerativeModel(GEMINI_MODEL)
                img   = Image.open(buf); buf.seek(0)
                resp  = model.generate_content([
                    "Descrivi dettagliatamente questo screenshot: finestre aperte, "
                    "testo visibile, bottoni, icone, stato del sistema.", img
                ])
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
    """Execute a GUI action: click | type | key | scroll | move | drag | screenshot."""
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

        elif action == "typewrite":          # alias
            pyautogui.typewrite(text or "", interval=0.04)
            return {"status": "ok"}

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
    """Open a Windows application by common name or exe path."""
    KNOWN = {
        "notepad":    "notepad.exe",
        "explorer":   "explorer.exe",
        "calc":       "calc.exe",
        "calculator": "calc.exe",
        "chrome":     "chrome.exe",
        "edge":       "msedge.exe",
        "firefox":    "firefox.exe",
        "cmd":        "cmd.exe",
        "powershell": "powershell.exe",
        "vscode":     "code.exe",
        "code":       "code.exe",
        "paint":      "mspaint.exe",
        "word":       "winword.exe",
        "excel":      "excel.exe",
    }
    try:
        exe = KNOWN.get(app_name.lower(), app_name)
        cmd = [exe] + (args or [])
        subprocess.Popen(cmd, shell=True)
        time.sleep(0.8)
        return {"status": "ok", "app": app_name}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def browser_go(url: str) -> dict:
    """Open a URL in the default browser."""
    try:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        webbrowser.open(url)
        time.sleep(0.5)
        return {"status": "ok", "url": url}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}
'''

# ─── tools/browser_ai_bridge.py ──────────────────────────────
FILES["src/tools/browser_ai_bridge.py"] = r'''
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
'''

# ─── tools/github_tool.py ────────────────────────────────────
FILES["src/tools/github_tool.py"] = r'''
"""GitHub REST API tool — no gh CLI required."""
import base64
import logging
import requests

logger = logging.getLogger("dust.github_tool")

try:
    from config import GITHUB_TOKEN, GITHUB_USER, GITHUB_REPO
except ImportError:
    GITHUB_TOKEN = ""; GITHUB_USER = "Tenkulo"; GITHUB_REPO = "dustai"

_BASE = "https://api.github.com"


def _h() -> dict:
    h = {"Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN:
        h["Authorization"] = f"token {GITHUB_TOKEN}"
    return h


def github_list_repos(user: str = None) -> dict:
    """List GitHub repositories for a user."""
    u = user or GITHUB_USER
    r = requests.get(f"{_BASE}/users/{u}/repos", headers=_h(), timeout=10)
    if r.ok:
        return {"status": "ok", "repos": [
            {"name": x["name"], "url": x["html_url"], "desc": x["description"]}
            for x in r.json()
        ]}
    return {"status": "error", "error": r.text[:300]}


def github_get_file(path: str, repo: str = None, branch: str = "master") -> dict:
    """Get a file's content from GitHub."""
    rp = repo or GITHUB_REPO
    r  = requests.get(f"{_BASE}/repos/{GITHUB_USER}/{rp}/contents/{path}",
                      headers=_h(), params={"ref": branch}, timeout=10)
    if r.ok:
        data    = r.json()
        content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        return {"status": "ok", "content": content, "sha": data["sha"]}
    return {"status": "error", "error": r.text[:300]}


def github_put_file(path: str, content: str, message: str = "Update via DUST AI",
                    repo: str = None, branch: str = "master") -> dict:
    """Create or update a file on GitHub."""
    rp  = repo or GITHUB_REPO
    sha = None
    ex  = github_get_file(path, repo=rp, branch=branch)
    if ex["status"] == "ok":
        sha = ex["sha"]

    payload: dict = {
        "message": message,
        "content": base64.b64encode(content.encode()).decode(),
        "branch":  branch,
    }
    if sha:
        payload["sha"] = sha

    r = requests.put(f"{_BASE}/repos/{GITHUB_USER}/{rp}/contents/{path}",
                     headers=_h(), json=payload, timeout=15)
    if r.ok:
        return {"status": "ok", "path": path}
    return {"status": "error", "error": r.text[:300]}


def github_create_issue(title: str, body: str = "", labels: list = None,
                        repo: str = None) -> dict:
    """Create a GitHub issue."""
    rp      = repo or GITHUB_REPO
    payload = {"title": title, "body": body}
    if labels:
        payload["labels"] = labels
    r = requests.post(f"{_BASE}/repos/{GITHUB_USER}/{rp}/issues",
                      headers=_h(), json=payload, timeout=10)
    if r.ok:
        return {"status": "ok", "url": r.json()["html_url"]}
    return {"status": "error", "error": r.text[:300]}


def github_get_commits(repo: str = None, n: int = 10) -> dict:
    """Get recent commits from a repo."""
    rp = repo or GITHUB_REPO
    r  = requests.get(f"{_BASE}/repos/{GITHUB_USER}/{rp}/commits",
                      headers=_h(), params={"per_page": n}, timeout=10)
    if r.ok:
        return {"status": "ok", "commits": [
            {"sha": c["sha"][:7], "msg": c["commit"]["message"].split("\n")[0]}
            for c in r.json()
        ]}
    return {"status": "error", "error": r.text[:300]}
'''

# ─── ai_gateway.py ───────────────────────────────────────────
FILES["src/ai_gateway.py"] = r'''
"""Unified AI gateway — wraps Gemini / OpenRouter / Ollama with fallback."""
import logging
import os
import re
import time

logger = logging.getLogger("dust.ai_gateway")

try:
    from config import GEMINI_KEYS, GEMINI_MODEL, OPENROUTER_API_KEY, OLLAMA_BASE_URL, OLLAMA_MODELS
except ImportError:
    GEMINI_KEYS = []; GEMINI_MODEL = "gemini-2.5-flash-preview-04-17"
    OPENROUTER_API_KEY = ""; OLLAMA_BASE_URL = "http://localhost:11434"; OLLAMA_MODELS = []


class AIGateway:
    def __init__(self):
        self._providers: list[dict] = []
        self._cooldowns: dict[str, float] = {}
        self._build_providers()

    def _build_providers(self):
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

    def complete(self, messages: list[dict], system: str = None, provider: str = None) -> str:
        providers = [p for p in self._available() if not provider or p["name"] == provider]
        last_err  = None
        for p in providers:
            try:
                return self._call(p, messages, system)
            except Exception as exc:
                err = str(exc)
                if "429" in err or "quota" in err.lower():
                    wait = 65
                    m = re.search(r"(\d+)", err)
                    if m:
                        wait = min(65, int(m.group(1)) + 3)
                    self._cooldowns[p["name"]] = time.time() + wait
                    logger.warning(f"Provider {p['name']} rate-limited {wait}s")
                else:
                    logger.warning(f"Provider {p['name']}: {exc}")
                last_err = exc
        raise RuntimeError(f"All providers failed: {last_err}")

    def _call(self, p: dict, messages: list[dict], system: str) -> str:
        t = p["type"]
        if t == "gemini":
            return self._gemini(p["key"], messages, system)
        if t == "openrouter":
            return self._openrouter(p["key"], messages, system)
        if t == "ollama":
            return self._ollama(p["model"], messages, system)
        raise ValueError(f"Unknown type: {t}")

    def _gemini(self, key: str, messages: list[dict], system: str) -> str:
        import google.generativeai as genai
        genai.configure(api_key=key)
        mdl   = genai.GenerativeModel(GEMINI_MODEL)
        parts = []
        if system:
            parts.append(f"[SYSTEM]\n{system}")
        for m in messages:
            parts.append(f"[{m['role'].upper()}]\n{m.get('content','')}")
        resp = mdl.generate_content("\n\n".join(parts))
        try:
            return resp.text
        except Exception:
            return ""

    def _openrouter(self, key: str, messages: list[dict], system: str) -> str:
        import requests
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)
        r = requests.post("https://openrouter.ai/api/v1/chat/completions",
                          headers={"Authorization": f"Bearer {key}",
                                   "Content-Type": "application/json"},
                          json={"model": "openai/gpt-4o-mini", "messages": msgs},
                          timeout=30)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    def _ollama(self, model: str, messages: list[dict], system: str) -> str:
        import requests
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)
        r = requests.post(f"{OLLAMA_BASE_URL}/api/chat",
                          json={"model": model, "messages": msgs, "stream": False},
                          timeout=120)
        r.raise_for_status()
        return r.json()["message"]["content"]

    def list_providers(self) -> list[str]:
        return [p["name"] for p in self._providers]
'''

# ─── ai_conductor.py ─────────────────────────────────────────
FILES["src/ai_conductor.py"] = r'''
"""AI Conductor — higher-level AI utilities (ai_ask, ai_parallel, ai_summarize…)."""
import json
import logging
import re
import concurrent.futures

logger = logging.getLogger("dust.ai_conductor")
_gw = None

def _gateway():
    global _gw
    if _gw is None:
        from ai_gateway import AIGateway
        _gw = AIGateway()
    return _gw


def ai_ask(prompt: str, system: str = None, provider: str = None,
           json_response: bool = False) -> str | dict:
    """Ask a single question to the best available AI."""
    try:
        if json_response:
            system = (system or "") + "\nRespondi SOLO con JSON valido, nessun testo extra."
        result = _gateway().complete([{"role": "user", "content": prompt}], system=system,
                                     provider=provider)
        if json_response:
            try:
                m = re.search(r'\{.*\}', result, re.DOTALL)
                if m:
                    return json.loads(m.group())
            except Exception:
                pass
        return result
    except Exception as exc:
        logger.error(f"ai_ask: {exc}")
        return {"error": str(exc)} if json_response else f"Errore: {exc}"


def ai_parallel(prompts, system: str = None, max_workers: int = 3) -> dict:
    """Execute multiple prompts in parallel. prompts can be dict or list."""
    if isinstance(prompts, dict):
        items = list(prompts.items())
    else:
        items = list(enumerate(prompts))

    results = {}

    def _ask(item):
        k, p = item
        try:
            return k, ai_ask(p, system=system)
        except Exception as exc:
            return k, f"Errore: {exc}"

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
        for k, v in ex.map(_ask, items):
            results[k] = v
    return results


def ai_models() -> dict:
    """List available AI models/providers."""
    try:
        return {"providers": _gateway().list_providers()}
    except Exception as exc:
        return {"error": str(exc)}


def ai_summarize(text: str, language: str = "italiano", max_words: int = 150) -> str:
    """Summarize text using AI."""
    return ai_ask(f"Riassumi in {language} in max {max_words} parole:\n\n{text}")


def ai_classify(text: str, categories: list[str]) -> str:
    """Classify text into one of the given categories."""
    cats = ", ".join(categories)
    return ai_ask(
        f"Classifica il testo in UNA categoria tra: {cats}\n\nTesto: {text}\n\n"
        f"Rispondi SOLO con il nome della categoria."
    )
'''

# ─── github_sync.py ──────────────────────────────────────────
FILES["src/github_sync.py"] = r'''
"""GitHub auto-sync — git add -A && commit && push via subprocess."""
import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger("dust.github_sync")

try:
    from config import BASE_PATH, GITHUB_TOKEN, GITHUB_USER, GITHUB_REPO
except ImportError:
    import pathlib
    BASE_PATH = pathlib.Path(r"A:\dustai")
    GITHUB_TOKEN = ""; GITHUB_USER = "Tenkulo"; GITHUB_REPO = "dustai"

REPO_DIR = BASE_PATH


def _git(args: list, cwd: Path = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    # Inject credentials silently
    if GITHUB_TOKEN and GITHUB_USER:
        env["GIT_TERMINAL_PROMPT"] = "0"
    return subprocess.run(
        ["git"] + args,
        cwd=str(cwd or REPO_DIR),
        capture_output=True, text=True, env=env
    )


def _set_remote_url():
    url = f"https://{GITHUB_USER}:{GITHUB_TOKEN}@github.com/{GITHUB_USER}/{GITHUB_REPO}.git"
    _git(["remote", "set-url", "origin", url])


def sync_push(message: str = "Auto-sync DUST AI", add_all: bool = True) -> dict:
    """git add -A && commit && push."""
    if add_all:
        r = _git(["add", "-A"])
        if r.returncode:
            return {"status": "error", "step": "add", "error": r.stderr[:300]}

    status = _git(["status", "--porcelain"])
    if not status.stdout.strip():
        return {"status": "ok", "message": "Nothing to commit."}

    r = _git(["commit", "-m", message])
    if r.returncode:
        return {"status": "error", "step": "commit", "error": r.stderr[:300]}

    _set_remote_url()
    r = _git(["push", "origin", "master"])
    if r.returncode:
        return {"status": "error", "step": "push", "error": r.stderr[:300]}

    return {"status": "ok", "message": f"Pushed: {message}"}


def sync_pull() -> dict:
    """git pull origin master."""
    _set_remote_url()
    r = _git(["pull", "origin", "master"])
    if r.returncode:
        return {"status": "error", "error": r.stderr[:300]}
    return {"status": "ok", "output": r.stdout[:500]}


def get_status() -> dict:
    """git status --short."""
    r = _git(["status", "--short"])
    return {"status": "ok", "changes": r.stdout}
'''

# ─── self_heal_v2.py ─────────────────────────────────────────
FILES["src/self_heal_v2.py"] = r'''
"""Self-healing system v2 — categorized error recovery."""
import importlib
import json
import logging
import re
import subprocess
import sys
import time

logger = logging.getLogger("dust.self_heal")


class Cat:
    RATE_LIMIT = "rate_limit"
    PARSE      = "parse"
    SYNTAX     = "syntax"
    IMPORT_ERR = "import"
    NETWORK    = "network"
    UNKNOWN    = "unknown"


def categorize(exc: Exception) -> str:
    s = str(exc)
    if "429" in s or "quota" in s.lower() or "RATE_LIMIT" in s:
        return Cat.RATE_LIMIT
    if isinstance(exc, (json.JSONDecodeError,)) or "json" in s.lower():
        return Cat.PARSE
    if isinstance(exc, SyntaxError):
        return Cat.SYNTAX
    if isinstance(exc, (ImportError, ModuleNotFoundError)):
        return Cat.IMPORT_ERR
    if any(k in s.lower() for k in ("connection", "timeout", "network", "socket")):
        return Cat.NETWORK
    return Cat.UNKNOWN


class SelfHeal:
    PKG_MAP = {
        "cv2": "opencv-python", "PIL": "Pillow", "PIL.Image": "Pillow",
        "sklearn": "scikit-learn", "bs4": "beautifulsoup4",
        "yaml": "pyyaml", "dotenv": "python-dotenv",
        "pyautogui": "pyautogui", "playwright": "playwright",
        "google.generativeai": "google-generativeai",
        "litellm": "litellm", "requests": "requests",
    }

    def __init__(self):
        self._history: list[dict] = []

    def heal(self, exc: Exception, context=None) -> dict:
        cat     = categorize(exc)
        handler = {
            Cat.RATE_LIMIT: self._rate_limit,
            Cat.PARSE:      self._parse,
            Cat.SYNTAX:     self._syntax,
            Cat.IMPORT_ERR: self._import,
            Cat.NETWORK:    self._network,
            Cat.UNKNOWN:    self._unknown,
        }.get(cat, self._unknown)

        result = handler(exc, context)
        self._history.append({"exc": str(exc), "cat": cat, "result": result, "ts": time.time()})
        logger.info(f"Heal [{cat}] → {result}")
        return result

    def _rate_limit(self, exc, _ctx) -> dict:
        m    = re.search(r"(\d+)", str(exc))
        wait = min(65, int(m.group(1)) + 3) if m else 62
        logger.warning(f"Rate limit — attendo {wait}s")
        time.sleep(wait)
        return {"healed": True, "action": "sleep", "seconds": wait}

    def _parse(self, exc, ctx) -> dict:
        if isinstance(ctx, str):
            try:
                m = re.search(r'\{.*\}', ctx, re.DOTALL)
                if m:
                    return {"healed": True, "action": "json_extract", "data": json.loads(m.group())}
            except Exception:
                pass
            return {"healed": True, "action": "fallback", "data": {"type": "done", "message": ctx}}
        return {"healed": False}

    def _syntax(self, exc, _ctx) -> dict:
        logger.error(f"SyntaxError: {exc}")
        return {"healed": False, "action": "report", "error": str(exc)}

    def _import(self, exc, _ctx) -> dict:
        m = re.search(r"No module named '([^']+)'", str(exc))
        if not m:
            return {"healed": False}
        raw_mod = m.group(1).split(".")[0]
        pkg = self.PKG_MAP.get(raw_mod, raw_mod)
        logger.info(f"Auto-install: {pkg}")
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", pkg, "--break-system-packages", "-q"],
                timeout=90, check=True, capture_output=True,
            )
            importlib.import_module(raw_mod)
            return {"healed": True, "action": "install", "package": pkg}
        except Exception as e:
            return {"healed": False, "action": "install_failed", "error": str(e)}

    def _network(self, exc, _ctx) -> dict:
        time.sleep(5)
        return {"healed": True, "action": "sleep", "seconds": 5}

    def _unknown(self, exc, _ctx) -> dict:
        logger.error(f"Unhandled: {exc}")
        return {"healed": False, "error": str(exc)}

    def history(self, n: int = 10) -> list:
        return self._history[-n:]


_instance: SelfHeal | None = None

def get() -> SelfHeal:
    global _instance
    if _instance is None:
        _instance = SelfHeal()
    return _instance

def heal(exc: Exception, ctx=None) -> dict:
    return get().heal(exc, ctx)
'''

# ─── ui/gui.py ───────────────────────────────────────────────
FILES["src/ui/gui.py"] = r'''
"""DUST AI GUI v3.0 — Dark chat interface (Claude-style bubbles)."""
import json
import queue
import sys
import threading
import tkinter as tk
from tkinter import ttk
from pathlib import Path

# Ensure src is on path
_SRC = Path(__file__).resolve().parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# ─── Palette ─────────────────────────────────────────────────
C = {
    "bg":           "#1a1a2e",
    "sidebar":      "#16213e",
    "chat_bg":      "#0d1117",
    "user_bub":     "#1f6feb",
    "ai_bub":       "#161b22",
    "user_fg":      "#f0f6fc",
    "ai_fg":        "#c9d1d9",
    "input_bg":     "#161b22",
    "input_fg":     "#f0f6fc",
    "btn":          "#238636",
    "btn_hover":    "#2ea043",
    "accent":       "#58a6ff",
    "muted":        "#8b949e",
    "border":       "#30363d",
    "ok":           "#3fb950",
    "err":          "#f85149",
    "warn":         "#d29922",
}
FF = ("Segoe UI", 11)
FM = ("Consolas", 10)
FT = ("Segoe UI", 13, "bold")
FS = ("Segoe UI", 9)


# ─── AgentWorker ─────────────────────────────────────────────
class AgentWorker(threading.Thread):
    """Background thread: consumes tasks, calls agent, emits results."""

    def __init__(self, agent, out_q: queue.Queue):
        super().__init__(daemon=True, name="AgentWorker")
        self.agent   = agent
        self.out_q   = out_q
        self._in_q   = queue.Queue()
        self._alive  = True

    def submit(self, message: str, history: list, **kwargs):
        self._in_q.put((message, history, kwargs))

    def run(self):
        while self._alive:
            try:
                msg, hist, kw = self._in_q.get(timeout=0.5)
            except queue.Empty:
                continue
            self.out_q.put(("thinking", ""))
            try:
                text, _tools = self.agent.run_turn(msg, hist, **kw)
                self.out_q.put(("response", text))
            except Exception as exc:
                self.out_q.put(("error", str(exc)))

    def stop(self):
        self._alive = False


# ─── Bubble ──────────────────────────────────────────────────
class Bubble(tk.Frame):
    MAX_W = 65   # chars per line estimate

    def __init__(self, parent, text: str, role: str = "user"):
        super().__init__(parent, bg=C["chat_bg"])
        is_user = role == "user"

        outer = tk.Frame(self, bg=C["chat_bg"])
        outer.pack(fill=tk.X, padx=14, pady=5)

        bub_bg = C["user_bub"] if is_user else C["ai_bub"]
        txt_fg = C["user_fg"] if is_user else C["ai_fg"]

        # Label badge
        badge_txt = "Tu" if is_user else "⚡ DUST"
        badge = tk.Label(outer, text=badge_txt, font=FS,
                        bg=bub_bg, fg=C["user_fg"] if is_user else C["accent"],
                        padx=7, pady=2, bd=0)

        # Scrollable text widget
        w = min(self.MAX_W, max(20, max((len(ln) for ln in text.splitlines()), default=20)))
        h = self._height(text, w)
        txt_w = tk.Text(outer, wrap=tk.WORD, width=w, height=h,
                       bg=bub_bg, fg=txt_fg, font=FF,
                       bd=0, relief="flat", padx=10, pady=8,
                       cursor="arrow", state=tk.NORMAL, spacing3=2)
        txt_w.insert("1.0", text)
        txt_w.configure(state=tk.DISABLED)

        if is_user:
            badge.pack(side=tk.RIGHT, anchor="ne", padx=(6, 0))
            txt_w.pack(side=tk.RIGHT, anchor="ne", padx=4)
        else:
            badge.pack(side=tk.LEFT, anchor="nw", padx=(0, 6))
            txt_w.pack(side=tk.LEFT, anchor="nw", padx=4)

    @staticmethod
    def _height(text: str, width: int) -> int:
        lines = 0
        for ln in text.splitlines():
            lines += max(1, len(ln) // max(width, 1) + 1)
        return min(max(2, lines), 30)


# ─── Thinking dots ───────────────────────────────────────────
class Thinking(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=C["chat_bg"])
        outer = tk.Frame(self, bg=C["chat_bg"])
        outer.pack(fill=tk.X, padx=14, pady=5)
        tk.Label(outer, text="⚡ DUST", font=FS,
                bg=C["ai_bub"], fg=C["accent"], padx=7, pady=2).pack(side=tk.LEFT, padx=(0, 6))
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


# ─── Main GUI ────────────────────────────────────────────────
class DustGUI:
    def __init__(self, root: tk.Tk):
        self.root     = root
        self.history: list[dict] = []
        self.agent    = None
        self.worker: AgentWorker | None = None
        self._q       = queue.Queue()
        self._think: Thinking | None = None

        root.title("DUST AI — Assistente Universale v4.0")
        root.configure(bg=C["bg"])
        root.geometry("960x720")
        root.minsize(640, 480)

        self._build()
        self._set_status("Inizializzazione…", "warn")
        threading.Thread(target=self._init_agent, daemon=True).start()
        self._poll()

    # ── Layout ───────────────────────────────────────────────
    def _build(self):
        root = self.root
        root.columnconfigure(0, weight=0, minsize=190)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)

        # Sidebar
        sb = tk.Frame(root, bg=C["sidebar"], width=190)
        sb.grid(row=0, column=0, sticky="nsew")
        sb.grid_propagate(False)

        tk.Label(sb, text="⚡  DUST AI", font=FT, bg=C["sidebar"],
                fg=C["accent"], pady=22).pack()
        tk.Frame(sb, bg=C["border"], height=1).pack(fill=tk.X, padx=12)
        tk.Label(sb, text="Assistente Universale", font=FS,
                bg=C["sidebar"], fg=C["muted"]).pack(pady=(6, 0))
        tk.Label(sb, text="v4.0  •  Gemini + Ollama", font=FS,
                bg=C["sidebar"], fg=C["muted"]).pack(pady=(2, 10))

        btn = tk.Button(sb, text="＋  Nuova chat", font=FS,
                       bg=C["btn"], fg="white", relief="flat",
                       activebackground=C["btn_hover"], padx=10, pady=7,
                       cursor="hand2", command=self._new_chat)
        btn.pack(fill=tk.X, padx=12, pady=8)

        # Status bar (bottom of sidebar)
        sf = tk.Frame(sb, bg=C["sidebar"])
        sf.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=14)
        self._dot = tk.Label(sf, text="●", bg=C["sidebar"], fg=C["warn"], font=("Arial", 11))
        self._dot.pack(side=tk.LEFT)
        self._slbl = tk.Label(sf, text="…", font=FS, bg=C["sidebar"], fg=C["muted"])
        self._slbl.pack(side=tk.LEFT, padx=4)

        # Chat panel
        chat = tk.Frame(root, bg=C["chat_bg"])
        chat.grid(row=0, column=1, sticky="nsew")
        chat.rowconfigure(0, weight=1)
        chat.rowconfigure(1, weight=0)
        chat.columnconfigure(0, weight=1)

        # Scrollable message area
        cv_frame = tk.Frame(chat, bg=C["chat_bg"])
        cv_frame.grid(row=0, column=0, sticky="nsew")
        cv_frame.rowconfigure(0, weight=1)
        cv_frame.columnconfigure(0, weight=1)

        self._cv = tk.Canvas(cv_frame, bg=C["chat_bg"], highlightthickness=0)
        vsb = ttk.Scrollbar(cv_frame, orient="vertical", command=self._cv.yview)
        self._msgs = tk.Frame(self._cv, bg=C["chat_bg"])
        self._cw   = self._cv.create_window((0, 0), window=self._msgs, anchor="nw")
        self._cv.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._cv.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._msgs.bind("<Configure>", lambda e: self._cv.configure(
            scrollregion=self._cv.bbox("all")))
        self._cv.bind("<Configure>", lambda e: self._cv.itemconfig(self._cw, width=e.width))
        self._cv.bind_all("<MouseWheel>", lambda e: self._cv.yview_scroll(
            -1 * (e.delta // 120), "units"))

        # Welcome
        tk.Label(self._msgs, text="Ciao! Sono DUST AI.\nCome posso aiutarti oggi?",
                font=FT, bg=C["chat_bg"], fg=C["accent"], pady=40).pack()

        # Input area
        inp = tk.Frame(chat, bg=C["input_bg"], pady=12, padx=14)
        inp.grid(row=1, column=0, sticky="ew")
        inp.columnconfigure(0, weight=1)

        self._inp = tk.Text(inp, height=3, font=FF, bg=C["input_bg"], fg=C["input_fg"],
                           relief="flat", bd=0, wrap=tk.WORD,
                           insertbackground=C["accent"], padx=10, pady=8)
        self._inp.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self._inp.bind("<Return>",       self._on_enter)
        self._inp.bind("<Shift-Return>", lambda e: None)

        send = tk.Button(inp, text="Invia  ▶", font=FF, bg=C["accent"], fg=C["bg"],
                        relief="flat", padx=14, pady=8, cursor="hand2",
                        activebackground=C["btn"], command=self._send)
        send.grid(row=0, column=1)

        tk.Label(inp, text="Invio = invia  |  Shift+Invio = nuova riga",
                font=FS, bg=C["input_bg"], fg=C["muted"]).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))

    # ── Agent init ───────────────────────────────────────────
    def _init_agent(self):
        try:
            from agent import Agent
            from tools.registry import Registry
            import tools.computer_use as cu

            reg = Registry()
            reg.register_module(cu)

            for mod_name in ("tools.file_ops", "tools.web_search", "tools.sys_exec",
                             "tools.browser", "tools.input_control",
                             "tools.windows_apps", "tools.code_runner",
                             "tools.github_tool"):
                try:
                    import importlib
                    m = importlib.import_module(mod_name)
                    reg.register_module(m)
                except Exception:
                    pass

            try:
                from github_sync import sync_push, sync_pull, get_status
                reg.register_function("github_sync_push",  sync_push,  "Push al repo GitHub")
                reg.register_function("github_sync_pull",  sync_pull,  "Pull dal repo GitHub")
                reg.register_function("github_sync_status", get_status, "Status git")
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
            self._q.put(("status_ok", "Pronto"))
        except Exception as exc:
            self._q.put(("status_err", f"Errore init: {exc}"))

    # ── Send / receive ────────────────────────────────────────
    def _on_enter(self, event):
        if not (event.state & 0x1):   # Shift not held
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
        tk.Label(self._msgs, text="Nuova chat — come posso aiutarti?",
                font=FT, bg=C["chat_bg"], fg=C["accent"], pady=40).pack()

    def _set_status(self, text: str, level: str = "ok"):
        col = {"ok": C["ok"], "err": C["err"], "warn": C["warn"]}.get(level, C["muted"])
        self._dot.configure(fg=col)
        self._slbl.configure(text=text[:30])


def main():
    root = tk.Tk()
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

# ─── app.py (root) ───────────────────────────────────────────
FILES["app.py"] = r'''
"""DUST AI entry point."""
import sys
from pathlib import Path

BASE = Path(__file__).parent
SRC  = BASE / "src"
sys.path.insert(0, str(SRC))

def main():
    try:
        import tkinter as tk
        from tkinter import ttk
        from ui.gui import DustGUI, C
        root = tk.Tk()
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        DustGUI(root)
        root.mainloop()
    except ImportError as exc:
        print(f"GUI non disponibile ({exc}), uso console.")
        try:
            from ui.console import ConsoleUI
            ConsoleUI().run()
        except ImportError:
            print("Nessuna UI disponibile.")

if __name__ == "__main__":
    main()
'''

# ─── run.bat ─────────────────────────────────────────────────
FILES["run.bat"] = r'''@echo off
title DUST AI v4.0
cd /d A:\dustai
python app.py
pause
'''

# ═══════════════════════════════════════════════════════════════
#   WRITER
# ═══════════════════════════════════════════════════════════════

def write_files():
    for rel_path, content in FILES.items():
        dest = BASE / rel_path.replace("/", os.sep)
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Dedent (strip leading newline from triple-quote style)
        text = textwrap.dedent(content).lstrip("\n")
        dest.write_text(text, encoding="utf-8")
        print(f"  ✅  {dest.relative_to(BASE)}")


# ═══════════════════════════════════════════════════════════════
#   PIP INSTALL
# ═══════════════════════════════════════════════════════════════

DEPS = [
    "google-generativeai",
    "python-dotenv",
    "pyautogui",
    "Pillow",
    "requests",
    "litellm",
    "playwright",
]

def install_deps():
    print("\n📦  Installazione dipendenze…")
    for pkg in DEPS:
        print(f"  pip install {pkg} …", end=" ", flush=True)
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", pkg, "-q",
             "--break-system-packages"],
            capture_output=True, text=True
        )
        if r.returncode == 0:
            print("ok")
        else:
            print(f"WARN ({r.stderr.strip()[:80]})")

    # Playwright browser
    print("  playwright install chromium …", end=" ", flush=True)
    r = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        capture_output=True, text=True
    )
    print("ok" if r.returncode == 0 else f"WARN ({r.stderr.strip()[:60]})")


# ═══════════════════════════════════════════════════════════════
#   GIT PUSH
# ═══════════════════════════════════════════════════════════════

def git_push():
    print("\n🚀  Git add → commit → push…")

    def git(args):
        return subprocess.run(
            ["git"] + args, cwd=str(BASE),
            capture_output=True, text=True
        )

    # Set remote with token if available
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(r"A:\dustai_stuff\.env"), override=True)
    except Exception:
        pass

    token = os.environ.get("GITHUB_TOKEN", "")
    user  = os.environ.get("GITHUB_USER", "Tenkulo")
    repo  = "dustai"

    if token:
        url = f"https://{user}:{token}@github.com/{user}/{repo}.git"
        git(["remote", "set-url", "origin", url])

    git(["add", "-A"])

    status = git(["status", "--porcelain"])
    if not status.stdout.strip():
        print("  ℹ️  Nothing to commit.")
        return

    r = git(["commit", "-m", "feat: DUST AI v4.0 — mega patch (gui, agent, cascade, tools)"])
    if r.returncode:
        print(f"  ❌  commit failed: {r.stderr[:200]}")
        return
    print("  ✅  commit ok")

    r = git(["push", "origin", "master"])
    if r.returncode:
        print(f"  ❌  push failed: {r.stderr[:200]}")
    else:
        print("  ✅  push ok → github.com/Tenkulo/dustai")


# ═══════════════════════════════════════════════════════════════
#   MAIN
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import subprocess

    print("=" * 62)
    print("   DUST AI v4.0 — MEGA PATCH INSTALLER")
    print("=" * 62)

    print("\n📁  Creazione directory e file…")
    mkdirs()
    write_files()

    install_deps()
    git_push()

    print("\n" + "=" * 62)
    print("  ✅  DUST AI v4.0 installato!")
    print("  ▶   Avvia con:  cd A:\\dustai && .\\run.bat")
    print("=" * 62)
