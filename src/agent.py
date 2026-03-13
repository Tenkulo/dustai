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
