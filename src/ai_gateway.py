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
