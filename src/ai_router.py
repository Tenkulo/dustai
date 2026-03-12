"""DUST AI – AIRouter v2.0 (Mar 2026)
Router intelligente: classifica il task e sceglie il modello migliore disponibile.
"""
import os, json, time, logging
from pathlib import Path
log = logging.getLogger("AIRouter")

# Catalogo modelli Mar 2026 – tutti FREE inclusi
MODELS = {
    # --- GOOGLE GEMINI (free tier) ---
    "gemini-flash":  {"id":"gemini/gemini-2.5-flash",    "free":True, "rpd":1500, "iq":49, "env":"GOOGLE_API_KEY",   "str":["general","speed","vision","coding"]},
    "gemini-flash2": {"id":"gemini/gemini-2.5-flash",    "free":True, "rpd":1500, "iq":49, "env":"GOOGLE_API_KEY_2", "str":["general","speed"]},
    "gemini-flash3": {"id":"gemini/gemini-2.5-flash",    "free":True, "rpd":1500, "iq":49, "env":"GOOGLE_API_KEY_3", "str":["general","speed"]},
    "gemini-pro":    {"id":"gemini/gemini-2.5-pro",      "free":True, "rpd":50,   "iq":57, "env":"GOOGLE_API_KEY",   "str":["reasoning","coding","math","analysis"]},
    "gemini-lite":   {"id":"gemini/gemini-2.5-flash-lite","free":True,"rpd":3000, "iq":42, "env":"GOOGLE_API_KEY",   "str":["fast","cheap","simple"]},
    # --- OPENROUTER (pay) ---
    "claude-sonnet": {"id":"openrouter/anthropic/claude-sonnet-4-6","free":False,"iq":52,"env":"OPENROUTER_API_KEY","str":["coding","analysis","writing"]},
    "gpt-5":         {"id":"openrouter/openai/gpt-5.2",             "free":False,"iq":55,"env":"OPENROUTER_API_KEY","str":["reasoning","math","general"]},
    "grok":          {"id":"openrouter/x-ai/grok-4",                "free":False,"iq":50,"env":"OPENROUTER_API_KEY","str":["search","realtime","news"]},
    "deepseek":      {"id":"openrouter/deepseek/deepseek-v3",       "free":False,"iq":48,"env":"OPENROUTER_API_KEY","str":["coding","math","cost"]},
    # --- OPENROUTER FREE ---
    "gemini-free-or":{"id":"openrouter/google/gemini-2.0-flash-exp:free","free":True,"iq":46,"env":"OPENROUTER_API_KEY","str":["general","free"]},
    "llama-free-or": {"id":"openrouter/meta-llama/llama-4-scout:free",  "free":True,"iq":44,"env":"OPENROUTER_API_KEY","str":["general","free"]},
    # --- BROWSER AI (zero rate limit, usa account web) ---
    "browser-gemini":{"id":"browser/gemini", "free":True,"rpd":999999,"iq":49,"env":None,"str":["fallback","unlimited"]},
    "browser-chatgpt":{"id":"browser/chatgpt","free":True,"rpd":99999, "iq":48,"env":None,"str":["fallback","unlimited"]},
    "browser-claude": {"id":"browser/claude", "free":True,"rpd":99999, "iq":50,"env":None,"str":["fallback","unlimited"]},
    # --- OLLAMA locale ---
    "ollama-qwen":   {"id":"ollama/qwen3:8b",          "free":True,"rpd":999999,"iq":35,"env":None,"str":["offline","local","always"]},
    "ollama-mistral":{"id":"ollama/mistral-small3.1",  "free":True,"rpd":999999,"iq":36,"env":None,"str":["offline","local","always"]},
}

# Route per tipo di task – ordine di preferenza
ROUTES = {
    "coding":    ["gemini-pro","gemini-flash","claude-sonnet","deepseek","gemini-flash2","browser-gemini","ollama-qwen"],
    "reasoning": ["gemini-pro","gpt-5","claude-sonnet","gemini-flash","gemini-flash2","browser-gemini","ollama-qwen"],
    "math":      ["gemini-pro","gpt-5","deepseek","gemini-flash","browser-gemini","ollama-qwen"],
    "search":    ["grok","gemini-flash","gemini-flash2","browser-chatgpt","ollama-qwen"],
    "vision":    ["gemini-flash","gemini-pro","gemini-flash2"],
    "creative":  ["gpt-5","claude-sonnet","gemini-flash","gemini-flash2","browser-chatgpt","ollama-qwen"],
    "fast":      ["gemini-lite","gemini-flash","gemini-flash2","ollama-qwen"],
    "free":      ["gemini-flash","gemini-flash2","gemini-flash3","gemini-lite","gemini-free-or","llama-free-or","browser-gemini","browser-chatgpt","ollama-qwen","ollama-mistral"],
    "parallel":  ["gemini-flash","gemini-flash2","claude-sonnet","gpt-5","deepseek","browser-gemini"],
    "general":   ["gemini-flash","gemini-flash2","claude-sonnet","deepseek","gemini-pro","browser-gemini","ollama-qwen"],
}

KEYWORDS = {
    "coding":    ["python","codice","bug","script","def ","class ","import","refactor","github","fix","errore","debug"],
    "reasoning": ["perche","analizza","spiega","why","explain","logic","strategia","piano","confronta"],
    "math":      ["calcola","equazione","matematica","formula","math","compute","percentuale"],
    "search":    ["cerca","notizie","oggi","attuale","search","news","latest","2026","2025","chi è","cos'è"],
    "vision":    ["screenshot","immagine","schermo","image","visual","foto"],
    "creative":  ["scrivi","crea","storia","write","create","blog","articolo","testo"],
    "fast":      ["veloce","rapido","breve","quick","short","in 1 riga"],
}

class AIRouter:
    def __init__(self, config):
        self.config    = config
        self._cooldown = {}   # model_name -> timestamp_fine_cooldown

    def classify(self, prompt: str) -> str:
        p = prompt.lower()
        scores = {t: sum(1 for k in kws if k in p) for t, kws in KEYWORDS.items()}
        best = max(scores, key=scores.get)
        return best if scores[best] > 0 else "general"

    def get_route(self, task="general", free_only=False) -> list:
        key = "free" if free_only else task
        candidates = ROUTES.get(key, ROUTES["general"])
        return [m for m in candidates if self._available(m)]

    def best_model_id(self, prompt: str, free_only=False) -> str:
        route = self.get_route(self.classify(prompt), free_only)
        if not route:
            return "ollama/qwen3:8b"
        return MODELS[route[0]]["id"]

    def available_free(self) -> list:
        return [MODELS[n]["id"] for n in ROUTES["free"] if self._available(n)]

    def set_cooldown(self, model_id: str, secs=65):
        for name, m in MODELS.items():
            if m["id"] == model_id:
                self._cooldown[name] = time.time() + secs
                log.info("Cooldown %s per %ds", name, secs)
                return

    def _available(self, name: str) -> bool:
        if self._cooldown.get(name, 0) > time.time():
            return False
        env = MODELS[name].get("env")
        if env is None:
            return True
        return bool(os.environ.get(env, "").strip())
