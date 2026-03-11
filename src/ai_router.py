"""DUST AI – AIRouter v2.0 (Mar 2026 benchmarks)"""
import os, json, time, logging
from pathlib import Path

log = logging.getLogger("AIRouter")

MODELS_2026 = {
    "gemini/gemini-2.5-flash": {
        "display": "Gemini 2.5 Flash", "provider": "google", "tier": 1,
        "intelligence": 49, "cost_in": 0.075, "cost_out": 0.30,
        "context_k": 1000, "free_tier": True, "rpm_free": 15, "rpd_free": 1500,
        "api_key_env": "GOOGLE_API_KEY",
        "strengths": ["general", "vision", "speed", "free", "function_calling"],
        "litellm_id": "gemini/gemini-2.5-flash",
        "openrouter_id": "google/gemini-2.5-flash",
    },
    "gemini/gemini-2.5-pro": {
        "display": "Gemini 2.5 Pro", "provider": "google", "tier": 1,
        "intelligence": 57, "cost_in": 2.0, "cost_out": 12.0,
        "context_k": 2000, "free_tier": True, "rpm_free": 5, "rpd_free": 50,
        "api_key_env": "GOOGLE_API_KEY_3",
        "strengths": ["reasoning", "math", "coding", "context_2m", "benchmark_leader"],
        "litellm_id": "gemini/gemini-2.5-pro",
        "openrouter_id": "google/gemini-2.5-pro",
    },
    "openrouter/anthropic/claude-sonnet-4-6": {
        "display": "Claude Sonnet 4.6", "provider": "anthropic", "tier": 1,
        "intelligence": 52, "cost_in": 3.0, "cost_out": 15.0,
        "context_k": 200, "free_tier": False,
        "api_key_env": "OPENROUTER_API_KEY",
        "strengths": ["coding", "refactoring", "analysis", "swebench_leader"],
        "litellm_id": "openrouter/anthropic/claude-sonnet-4-6",
        "openrouter_id": "anthropic/claude-sonnet-4-6",
    },
    "openrouter/openai/gpt-5.2": {
        "display": "GPT-5.2", "provider": "openai", "tier": 1,
        "intelligence": 55, "cost_in": 2.5, "cost_out": 10.0,
        "context_k": 128, "free_tier": False,
        "api_key_env": "OPENROUTER_API_KEY",
        "strengths": ["complex_reasoning", "math", "creative", "general"],
        "litellm_id": "openrouter/openai/gpt-5.2",
        "openrouter_id": "openai/gpt-5.2",
    },
    "openrouter/x-ai/grok-4": {
        "display": "Grok 4", "provider": "xai", "tier": 2,
        "intelligence": 50, "cost_in": 3.0, "cost_out": 15.0,
        "context_k": 128, "free_tier": False,
        "api_key_env": "OPENROUTER_API_KEY",
        "strengths": ["real_time_search", "current_events", "multi_agent_native"],
        "litellm_id": "openrouter/x-ai/grok-4",
        "openrouter_id": "x-ai/grok-4",
    },
    "openrouter/deepseek/deepseek-v3": {
        "display": "DeepSeek V3", "provider": "deepseek", "tier": 2,
        "intelligence": 48, "cost_in": 0.07, "cost_out": 0.28,
        "context_k": 64, "free_tier": False,
        "api_key_env": "OPENROUTER_API_KEY",
        "strengths": ["cost_efficient", "coding", "math", "open_source_quality"],
        "litellm_id": "openrouter/deepseek/deepseek-v3",
        "openrouter_id": "deepseek/deepseek-v3",
    },
    "gemini/gemini-2.5-flash-lite": {
        "display": "Gemini 2.5 Flash Lite", "provider": "google", "tier": 3,
        "intelligence": 42, "cost_in": 0.01, "cost_out": 0.04,
        "context_k": 1000, "free_tier": True, "rpm_free": 30, "rpd_free": 3000,
        "api_key_env": "GOOGLE_API_KEY_2",
        "strengths": ["ultra_fast", "cheap", "free", "high_volume"],
        "litellm_id": "gemini/gemini-2.5-flash-lite",
    },
    "ollama/qwen3:8b": {
        "display": "Qwen3 8B (locale)", "provider": "ollama_local", "tier": 3,
        "intelligence": 35, "cost_in": 0.0, "cost_out": 0.0,
        "context_k": 32, "free_tier": True, "rpm_free": 9999, "rpd_free": 999999,
        "api_key_env": None,
        "strengths": ["offline", "privacy", "no_rate_limit", "no_cost"],
        "litellm_id": None,
    },
}

TASK_ROUTES = {
    "coding":    ["openrouter/anthropic/claude-sonnet-4-6", "openrouter/openai/gpt-5.2",
                  "gemini/gemini-2.5-pro", "openrouter/deepseek/deepseek-v3",
                  "gemini/gemini-2.5-flash", "ollama/qwen3:8b"],
    "reasoning": ["gemini/gemini-2.5-pro", "openrouter/openai/gpt-5.2",
                  "openrouter/anthropic/claude-sonnet-4-6", "gemini/gemini-2.5-flash",
                  "ollama/qwen3:8b"],
    "math":      ["gemini/gemini-2.5-pro", "openrouter/openai/gpt-5.2",
                  "openrouter/deepseek/deepseek-v3", "gemini/gemini-2.5-flash",
                  "ollama/qwen3:8b"],
    "search":    ["openrouter/x-ai/grok-4", "gemini/gemini-2.5-flash", "ollama/qwen3:8b"],
    "vision":    ["gemini/gemini-2.5-flash", "gemini/gemini-2.5-pro"],
    "fast":      ["gemini/gemini-2.5-flash-lite", "gemini/gemini-2.5-flash", "ollama/qwen3:8b"],
    "free_only": ["gemini/gemini-2.5-flash", "gemini/gemini-2.5-flash-lite", "ollama/qwen3:8b"],
    "creative":  ["openrouter/openai/gpt-5.2", "openrouter/anthropic/claude-sonnet-4-6",
                  "gemini/gemini-2.5-flash", "ollama/qwen3:8b"],
    "general":   ["gemini/gemini-2.5-flash", "openrouter/anthropic/claude-sonnet-4-6",
                  "openrouter/deepseek/deepseek-v3", "ollama/qwen3:8b"],
    "parallel_top3": ["gemini/gemini-2.5-pro", "openrouter/anthropic/claude-sonnet-4-6",
                      "openrouter/openai/gpt-5.2"],
}

TASK_KEYWORDS = {
    "coding":    ["codice","python","bug","funzione","script","def ","class ",
                  "import","refactor","debug","errore","syntax","code","fix","github"],
    "reasoning": ["perche","analizza","spiega","ragiona","why","explain","analyze",
                  "reason","logic","strategia","piano","valuta"],
    "math":      ["calcola","equazione","matematica","formula","calculate","equation",
                  "math","compute","numero","algebra"],
    "search":    ["cerca","ricerca","notizie","aggiornamento","oggi","attuale",
                  "search","news","current","latest","2026","internet"],
    "vision":    ["screenshot","immagine","schermo","vedi","image","visual","foto"],
    "creative":  ["scrivi","crea","storia","poesia","write","create","story","blog"],
    "fast":      ["veloce","rapido","breve","quick","short","semplice"],
}


class AIRouter:
    def __init__(self, config):
        self.config = config
        self._usage_file = config.get_memory_dir() / "router_usage.json"
        self._usage = self._load_usage()
        self._cooldown = {}

    def classify(self, prompt):
        p = prompt.lower()
        scores = {t: sum(1 for k in kws if k in p) for t, kws in TASK_KEYWORDS.items()}
        best_task = max(scores, key=scores.get)
        return best_task if scores[best_task] > 0 else "general"

    def get_route(self, task_type="general", mode="best"):
        if mode == "parallel":
            candidates = TASK_ROUTES.get("parallel_top3", [])
        elif mode == "free_only":
            candidates = TASK_ROUTES["free_only"]
        else:
            candidates = TASK_ROUTES.get(task_type, TASK_ROUTES["general"])
        available = [m for m in candidates if self._is_available(m)]
        if not available:
            return ["ollama/qwen3:8b"]
        return available if mode != "best" else [available[0]]

    def best_model(self, prompt, force_free=False):
        task_type = self.classify(prompt)
        mode = "free_only" if force_free else "best"
        return self.get_route(task_type, mode)[0]

    def _is_available(self, model_id):
        if model_id in self._cooldown:
            if time.time() < self._cooldown[model_id]:
                return False
            del self._cooldown[model_id]
        meta = MODELS_2026.get(model_id, {})
        key_env = meta.get("api_key_env")
        if not key_env:
            return True
        return bool(os.environ.get(key_env, "").strip())

    def set_cooldown(self, model_id, seconds=65):
        self._cooldown[model_id] = time.time() + seconds
        log.info("Cooldown %s per %ds", model_id, seconds)

    def available_models(self):
        return [m for m in MODELS_2026 if self._is_available(m)]

    def record(self, model_id, task_type, success, latency_s=0.0):
        from datetime import datetime
        month = datetime.now().strftime("%Y-%m")
        key = model_id + "|" + task_type
        self._usage.setdefault(month, {}).setdefault(key, {"calls": 0, "ok": 0, "fail": 0, "avg_latency": 0.0})
        rec = self._usage[month][key]
        rec["calls"] += 1
        if success:
            rec["ok"] += 1
            rec["avg_latency"] = (rec["avg_latency"] * (rec["ok"] - 1) + latency_s) / rec["ok"]
        else:
            rec["fail"] += 1
        self._save_usage()

    def stats_report(self):
        from datetime import datetime
        month = datetime.now().strftime("%Y-%m")
        data = self._usage.get(month, {})
        lines = ["=== AIRouter Stats " + month + " ===",
                 "Modelli disponibili: " + str(len(self.available_models())), ""]
        for key, rec in sorted(data.items(), key=lambda x: x[1]["calls"], reverse=True)[:8]:
            model, task = key.split("|", 1)
            name = MODELS_2026.get(model, {}).get("display", model.split("/")[-1])
            rate = round(rec["ok"] / max(rec["calls"], 1) * 100)
            lines.append("  " + name + " [" + task + "] " + str(rec["calls"]) + " calls " + str(rate) + "% ok")
        lines += ["", "Modelli mancanti:"]
        for m, meta in MODELS_2026.items():
            env = meta.get("api_key_env")
            if env and not os.environ.get(env, "").strip():
                lines.append("  x " + meta["display"] + " -> " + env)
        return "\n".join(lines)

    def _load_usage(self):
        if self._usage_file.exists():
            try:
                return json.loads(self._usage_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save_usage(self):
        try:
            self._usage_file.write_text(json.dumps(self._usage, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
