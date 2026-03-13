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
