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
