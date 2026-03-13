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
