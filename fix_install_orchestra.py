"""
DUST AI – fix_install_orchestra.py
Scrive direttamente tutti i file Orchestra + patcha registry in modo sicuro.
Esegui: python A:\dustai\fix_install_orchestra.py
"""
import ast, shutil, time, subprocess, sys
from pathlib import Path

BASE  = Path(r"A:\dustai")
SRC   = BASE / "src"
STUFF = Path(r"A:\dustai_stuff")
BAK   = STUFF / "patches"
BAK.mkdir(parents=True, exist_ok=True)

print("=" * 60)
print("DUST AI – Orchestra v2.0 Fix Install")
print("=" * 60)

# ══════════════════════════════════════════════════════════════
# STEP 1: Scrivi ai_router.py
# ══════════════════════════════════════════════════════════════
print("\n[1/5] Scrivo ai_router.py...")

AI_ROUTER = r'''"""DUST AI – AIRouter v2.0 (Mar 2026 benchmarks)"""
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
'''

(SRC / "ai_router.py").write_text(AI_ROUTER, encoding="utf-8")
print("  OK ai_router.py")

# ══════════════════════════════════════════════════════════════
# STEP 2: Scrivi ai_gateway.py
# ══════════════════════════════════════════════════════════════
print("[2/5] Scrivo ai_gateway.py...")

AI_GATEWAY = r'''"""DUST AI – AIGateway v2.0"""
import os, time, json, logging
from pathlib import Path
log = logging.getLogger("AIGateway")

try:
    from .ai_router import MODELS_2026, AIRouter
except ImportError:
    from ai_router import MODELS_2026, AIRouter


class AIGateway:
    def __init__(self, config):
        self.config = config
        self.router = AIRouter(config)
        self._litellm_ok = self._init_litellm()
        self._log_dir = config.get_base_path() / "logs"
        self._log_dir.mkdir(exist_ok=True)
        self._usage_log = self._log_dir / "gateway_usage.jsonl"

    def call(self, model_id, prompt, system="", max_tokens=2000, temperature=0.7):
        meta = MODELS_2026.get(model_id, {})
        provider = meta.get("provider", "")
        if model_id.startswith("ollama/") or provider == "ollama_local":
            return self._call_ollama(model_id, prompt, system, max_tokens)
        litellm_id = meta.get("litellm_id")
        if litellm_id and self._litellm_ok:
            return self._call_litellm(litellm_id, prompt, system, max_tokens, temperature)
        if model_id.startswith("gemini/") or provider == "google":
            return self._call_gemini_direct(model_id.replace("gemini/", ""), prompt, system, max_tokens)
        openrouter_id = meta.get("openrouter_id")
        if openrouter_id:
            return self._call_openrouter_direct(openrouter_id, prompt, system, max_tokens)
        return {"ok": False, "error": "Nessun provider per: " + model_id, "model_id": model_id}

    def call_auto(self, prompt, task_type="auto", mode="best"):
        if task_type == "auto":
            task_type = self.router.classify(prompt)
        models = self.router.get_route(task_type, mode)
        log.info("auto: task=%s route=%s", task_type, [m.split("/")[-1] for m in models])
        for model_id in models:
            t0 = time.time()
            result = self.call(model_id, prompt)
            latency = round(time.time() - t0, 2)
            if result.get("ok"):
                self.router.record(model_id, task_type, True, latency)
                self._log_usage(model_id, task_type, True, latency, len(result.get("text", "")))
                return result
            err = result.get("error", "")
            self.router.record(model_id, task_type, False, latency)
            if "429" in err or "RATE" in err.upper() or "RESOURCE_EXHAUSTED" in err:
                self.router.set_cooldown(model_id, 65)
                log.warning("%s -> 429, provo il prossimo", model_id.split("/")[-1])
                continue
            log.warning("%s -> %s", model_id.split("/")[-1], err[:100])
        return {"ok": False, "error": "Tutti i modelli falliti per: " + task_type}

    def _call_litellm(self, litellm_id, prompt, system, max_tokens, temperature):
        try:
            from litellm import completion
            import litellm
            litellm.suppress_debug_info = True
            msgs = []
            if system:
                msgs.append({"role": "system", "content": system})
            msgs.append({"role": "user", "content": prompt})
            resp = completion(model=litellm_id, messages=msgs, max_tokens=max_tokens,
                              temperature=temperature, timeout=60, num_retries=2)
            text = resp.choices[0].message.content or ""
            usage = resp.usage or type("U", (), {"prompt_tokens": 0, "completion_tokens": 0})()
            return {"ok": True, "text": text.strip(), "model_id": litellm_id,
                    "tokens": {"in": getattr(usage, "prompt_tokens", 0),
                               "out": getattr(usage, "completion_tokens", 0)}}
        except Exception as e:
            err = str(e)
            code = "429" if ("429" in err or "rate" in err.lower() or "RESOURCE_EXHAUSTED" in err) else "error"
            return {"ok": False, "error": err[:300], "error_code": code, "model_id": litellm_id}

    def _call_gemini_direct(self, model_name, prompt, system, max_tokens):
        try:
            import google.generativeai as genai
            api_key = (os.environ.get("GOOGLE_API_KEY") or
                       os.environ.get("GOOGLE_API_KEY_2") or
                       os.environ.get("GOOGLE_API_KEY_3", ""))
            if not api_key:
                return {"ok": False, "error": "GOOGLE_API_KEY mancante", "model_id": "gemini/" + model_name}
            genai.configure(api_key=api_key)
            m = genai.GenerativeModel(model_name=model_name,
                                      system_instruction=system or None)
            resp = m.generate_content(prompt,
                                      generation_config=genai.types.GenerationConfig(max_output_tokens=max_tokens))
            try:
                text = resp.text.strip()
            except Exception:
                text = ""
            if not text:
                return {"ok": False, "error": "Risposta vuota", "model_id": "gemini/" + model_name}
            return {"ok": True, "text": text, "model_id": "gemini/" + model_name}
        except Exception as e:
            return {"ok": False, "error": str(e)[:300], "model_id": "gemini/" + model_name}

    def _call_openrouter_direct(self, openrouter_model, prompt, system, max_tokens):
        try:
            import requests
            api_key = os.environ.get("OPENROUTER_API_KEY", "")
            if not api_key:
                return {"ok": False, "error": "OPENROUTER_API_KEY mancante", "model_id": "openrouter/" + openrouter_model}
            msgs = []
            if system:
                msgs.append({"role": "system", "content": system})
            msgs.append({"role": "user", "content": prompt})
            resp = requests.post("https://openrouter.ai/api/v1/chat/completions",
                                 headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
                                 json={"model": openrouter_model, "messages": msgs, "max_tokens": max_tokens},
                                 timeout=60)
            data = resp.json()
            if resp.status_code != 200:
                return {"ok": False, "error": str(data.get("error", resp.text))[:300], "model_id": "openrouter/" + openrouter_model}
            text = data["choices"][0]["message"]["content"] or ""
            return {"ok": True, "text": text.strip(), "model_id": "openrouter/" + openrouter_model}
        except Exception as e:
            return {"ok": False, "error": str(e)[:300], "model_id": "openrouter/" + openrouter_model}

    def _call_ollama(self, model_id, prompt, system, max_tokens):
        model_name = model_id.replace("ollama/", "")
        try:
            import ollama
            msgs = []
            if system:
                msgs.append({"role": "system", "content": system})
            msgs.append({"role": "user", "content": prompt})
            resp = ollama.chat(model=model_name, messages=msgs,
                               options={"num_predict": max_tokens, "temperature": 0.7}, stream=False)
            return {"ok": True, "text": resp["message"]["content"].strip(), "model_id": model_id}
        except Exception as e:
            return {"ok": False, "error": str(e)[:300], "model_id": model_id}

    def _init_litellm(self):
        try:
            import litellm
            os.environ.setdefault("GEMINI_API_KEY", os.environ.get("GOOGLE_API_KEY", ""))
            return True
        except ImportError:
            log.warning("LiteLLM non installato -> pip install litellm")
            return False

    def _log_usage(self, model_id, task_type, success, latency, chars):
        from datetime import datetime
        entry = {"ts": datetime.now().isoformat(), "model": model_id, "task": task_type,
                 "ok": success, "latency": latency, "chars": chars}
        try:
            with open(self._usage_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def status_report(self):
        lines = ["=== AIGateway Status ===",
                 "LiteLLM: " + ("OK" if self._litellm_ok else "MANCANTE (pip install litellm)"),
                 "OpenRouter: " + ("OK" if os.environ.get("OPENROUTER_API_KEY") else "MANCANTE"),
                 "Gemini: " + ("OK" if os.environ.get("GOOGLE_API_KEY") else "MANCANTE"),
                 "Ollama: locale (sempre disponibile)", ""]
        lines.append(self.router.stats_report())
        return "\n".join(lines)
'''

(SRC / "ai_gateway.py").write_text(AI_GATEWAY, encoding="utf-8")
print("  OK ai_gateway.py")

# ══════════════════════════════════════════════════════════════
# STEP 3: Scrivi ai_conductor.py (punto centrale)
# ══════════════════════════════════════════════════════════════
print("[3/5] Scrivo ai_conductor.py...")

AI_CONDUCTOR = r'''"""DUST AI – AIConductor v2.0"""
import logging, time, json, threading
from pathlib import Path
from datetime import datetime
log = logging.getLogger("AIConductor")

MODEL_ALIASES = {
    "gemini": "gemini/gemini-2.5-flash",
    "gemini_pro": "gemini/gemini-2.5-pro",
    "gemini3": "gemini/gemini-2.5-pro",
    "claude": "openrouter/anthropic/claude-sonnet-4-6",
    "gpt": "openrouter/openai/gpt-5.2",
    "grok": "openrouter/x-ai/grok-4",
    "deepseek": "openrouter/deepseek/deepseek-v3",
    "ollama": "ollama/qwen3:8b",
    "free": "gemini/gemini-2.5-flash",
    "lite": "gemini/gemini-2.5-flash-lite",
}


class AIConductor:
    def __init__(self, config):
        self.config = config
        self._memory = config.get_base_path() / "memory"
        self._memory.mkdir(exist_ok=True)
        self._gateway = None
        self._git_sync = None
        self._task_count = self._load_task_count()

    def _gw(self):
        if not self._gateway:
            from .ai_gateway import AIGateway
            self._gateway = AIGateway(self.config)
        return self._gateway

    def _git(self):
        if not self._git_sync:
            from .github_sync import GitHubSync
            self._git_sync = GitHubSync(self.config)
        return self._git_sync

    def ask(self, prompt, mode="auto", model="auto", task_type="auto", context=""):
        start = time.time()
        full_prompt = ("CONTESTO:\n" + context[:4000] + "\n\nRICHIESTA:\n" + prompt) if context else prompt
        if model != "auto":
            resolved = MODEL_ALIASES.get(model.lower(), model)
            result = self._gw().call(resolved, full_prompt)
        else:
            result = self._gw().call_auto(full_prompt, task_type, mode)
        result["latency_total_s"] = round(time.time() - start, 2)
        self._task_count += 1
        self._save_task_count()
        if self._task_count % 10 == 0:
            self._trigger_self_improvement()
        return self._normalize(result)

    def ask_parallel(self, prompt, models=None, task_type="auto"):
        from concurrent.futures import ThreadPoolExecutor, as_completed
        gw = self._gw()
        if not models:
            router = gw.router
            if task_type == "auto":
                task_type = router.classify(prompt)
            models = router.get_route(task_type, "cascade")[:3]
        if len(models) < 2:
            return self.ask(prompt, task_type=task_type)
        results = {}
        with ThreadPoolExecutor(max_workers=len(models)) as ex:
            futures = {ex.submit(gw.call, m, prompt): m for m in models}
            for future in as_completed(futures, timeout=45):
                mid = futures[future]
                try:
                    r = future.result(timeout=5)
                    if r.get("ok"):
                        results[mid] = r
                except Exception:
                    pass
        if not results:
            return {"ok": False, "text": "", "error": "Tutti i modelli falliti", "model": "?"}
        best = max(results, key=lambda m: len(results[m].get("text", "")))
        res = self._normalize(results[best])
        res["parallel_count"] = len(results)
        res["all_models"] = list(results.keys())
        return res

    def _normalize(self, result):
        if result.get("ok"):
            return {"ok": True, "text": result.get("text", ""),
                    "model": result.get("model_id", result.get("model", "?")),
                    "meta": {k: v for k, v in result.items() if k not in ("ok", "text", "model_id", "model")}}
        return {"ok": False, "text": "", "error": result.get("error", "errore"),
                "model": result.get("model_id", "?"), "meta": {}}

    def sync_github(self, message=""):
        try:
            results = self._git().auto_sync(message)
            out = []
            for step, res in results.items():
                icon = "OK" if res.get("ok") else "FAIL"
                out.append(icon + " " + step + ": " + res.get("msg", res.get("error", "")))
            return "\n".join(out)
        except Exception as e:
            return "FAIL GitHub sync: " + str(e)

    def status(self):
        lines = ["=== AIConductor Status ===", "Task eseguiti: " + str(self._task_count)]
        try:
            lines.append(self._gw().status_report())
        except Exception as e:
            lines.append("Gateway: " + str(e))
        return "\n".join(lines)

    def _trigger_self_improvement(self):
        def run():
            try:
                from .agents.self_improvement_loop import SelfImprovementLoop
                SelfImprovementLoop(self.config).run_cycle()
                self._git().commit("self-improvement: ciclo " + str(self._task_count // 10))
            except Exception as e:
                log.warning("Self-improvement: %s", e)
        threading.Thread(target=run, daemon=True).start()

    def _load_task_count(self):
        f = self._memory / "conductor_state.json"
        if f.exists():
            try:
                return json.loads(f.read_text(encoding="utf-8")).get("task_count", 0)
            except Exception:
                pass
        return 0

    def _save_task_count(self):
        f = self._memory / "conductor_state.json"
        try:
            f.write_text(json.dumps({"task_count": self._task_count}, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass


class AIConductorTool:
    """Tool wrapper per ToolRegistry."""

    def __init__(self, config):
        self.config = config
        self._conductor = None

    def _get(self):
        if not self._conductor:
            self._conductor = AIConductor(self.config)
        return self._conductor

    def ai_ask(self, prompt, model="auto", mode="auto"):
        result = self._get().ask(prompt, model=model, mode=mode)
        if result["ok"]:
            m = result.get("model", "?").split("/")[-1]
            return "[" + m + "] " + result["text"]
        return "FAIL " + result.get("error", "errore")

    def ai_parallel(self, prompt, models=""):
        ALIASES = {
            "gemini": "gemini/gemini-2.5-flash",
            "gemini3": "gemini/gemini-2.5-pro",
            "claude": "openrouter/anthropic/claude-sonnet-4-6",
            "gpt": "openrouter/openai/gpt-5.2",
            "grok": "openrouter/x-ai/grok-4",
            "deepseek": "openrouter/deepseek/deepseek-v3",
            "ollama": "ollama/qwen3:8b",
        }
        model_ids = [ALIASES.get(m.strip(), m.strip()) for m in models.split(",") if m.strip()] if models.strip() else None
        result = self._get().ask_parallel(prompt, models=model_ids)
        if result["ok"]:
            n = result.get("parallel_count", 1)
            return "[PARALLELO " + str(n) + " modelli] " + result["text"]
        return "FAIL " + result.get("error", "errore")

    def ai_status(self):
        return self._get().status()

    def ai_models(self, filter_available="all"):
        try:
            from .ai_router import MODELS_2026
        except ImportError:
            from ai_router import MODELS_2026
        gw = self._get()._gw()
        router = gw.router
        lines = ["Modelli AI (Mar 2026):"]
        for tier in [1, 2, 3]:
            lines.append("\n-- Tier " + str(tier) + " --")
            for mid, meta in MODELS_2026.items():
                if meta["tier"] != tier:
                    continue
                avail = router._is_available(mid)
                if filter_available == "available" and not avail:
                    continue
                if filter_available == "free" and not meta.get("free_tier"):
                    continue
                icon = "OK" if avail else "X "
                free_tag = " [FREE]" if meta.get("free_tier") else ""
                lines.append(icon + " " + meta["display"] + free_tag +
                              " | IQ " + str(meta.get("intelligence", "?")) +
                              " | $" + str(meta["cost_in"]) + "/1M" +
                              " | " + ", ".join(meta.get("strengths", [])[:3]))
        return "\n".join(lines)

    def git_sync(self, message=""):
        return self._get().sync_github(message)
'''

(SRC / "ai_conductor.py").write_text(AI_CONDUCTOR, encoding="utf-8")
print("  OK ai_conductor.py")

# ══════════════════════════════════════════════════════════════
# STEP 4: Scrivi github_sync.py
# ══════════════════════════════════════════════════════════════
print("[4/5] Scrivo github_sync.py...")

GITHUB_SYNC = r'''"""DUST AI – GitHubSync v2.0"""
import subprocess, logging, json, shutil, time
from pathlib import Path
from datetime import datetime
log = logging.getLogger("GitHubSync")

REPO_PATH  = Path(r"A:\dustai")
BACKUP_DIR = Path(r"A:\dustai_stuff\backups")
REMOTE     = "origin"
BRANCH     = "master"


class GitHubSync:
    def __init__(self, config):
        self.config = config
        self.repo_dir = REPO_PATH
        self._last_push = 0.0
        self._push_interval = 30 * 60

    def auto_sync(self, commit_msg=""):
        results = {}
        results["pull"] = self.pull()
        if self.has_uncommitted_changes():
            msg = commit_msg or self._auto_commit_message()
            results["commit"] = self.commit(msg)
        else:
            results["commit"] = {"ok": True, "msg": "Niente da committare"}
        if time.time() - self._last_push > self._push_interval or commit_msg:
            results["push"] = self.push()
            if results["push"].get("ok"):
                self._last_push = time.time()
        else:
            wait = int((self._push_interval - (time.time() - self._last_push)) / 60)
            results["push"] = {"ok": True, "msg": "Prossimo push tra " + str(wait) + " min"}
        return results

    def commit(self, message, files=None):
        try:
            self._run(["git", "add", "-A"] if not files else ["git", "add"] + [str(f) for f in files])
            status = self._run(["git", "status", "--porcelain"])
            if not status.get("stdout", "").strip():
                return {"ok": True, "msg": "Niente da committare"}
            ts = datetime.now().strftime("%Y-%m-%d %H:%M")
            full_msg = "[DUST " + ts + "] " + message[:60]
            result = self._run(["git", "commit", "-m", full_msg])
            if result.get("ok"):
                return {"ok": True, "msg": full_msg, "hash": self._last_commit_hash()}
            return {"ok": False, "error": result.get("stderr", "errore commit")}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def push(self):
        try:
            self._backup()
            result = self._run(["git", "push", REMOTE, BRANCH])
            if result.get("ok"):
                return {"ok": True, "msg": "Push OK -> github.com/Tenkulo/dustai"}
            if "non-fast-forward" in result.get("stderr", ""):
                result2 = self._run(["git", "push", "--force-with-lease", REMOTE, BRANCH])
                if result2.get("ok"):
                    return {"ok": True, "msg": "Force push OK"}
                return {"ok": False, "error": result2.get("stderr", "")}
            return {"ok": False, "error": result.get("stderr", "errore push")}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def pull(self):
        try:
            result = self._run(["git", "pull", REMOTE, BRANCH, "--rebase"])
            stdout = result.get("stdout", "")
            if result.get("ok"):
                if "Already up to date" in stdout or "Aggiornato" in stdout:
                    return {"ok": True, "msg": "Gia aggiornato"}
                return {"ok": True, "msg": "Pull OK:\n" + stdout[:200]}
            return {"ok": False, "error": result.get("stderr", "")}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def status(self):
        lines = ["=== GitHub Sync ===", "Repo: " + str(self.repo_dir), ""]
        branch = self._run(["git", "branch", "--show-current"])
        lines.append("Branch: " + branch.get("stdout", "?").strip())
        last = self._run(["git", "log", "--oneline", "-3"])
        lines.append("Ultimi commit:\n" + last.get("stdout", "?").strip())
        dirty = self._run(["git", "status", "--short"])
        dirty_out = dirty.get("stdout", "").strip()
        if dirty_out:
            lines.append("\nModifiche non committate:\n" + dirty_out[:300])
        else:
            lines.append("\nWorking tree pulito")
        return "\n".join(lines)

    def has_uncommitted_changes(self):
        return bool(self._run(["git", "status", "--porcelain"]).get("stdout", "").strip())

    def _auto_commit_message(self):
        result = self._run(["git", "status", "--short"])
        changes = result.get("stdout", "").strip().splitlines()
        if not changes:
            return "auto: sync"
        modified = [l[3:] for l in changes if l.startswith(" M ") or l.startswith("M ")]
        new_files = [l[3:] for l in changes if l.startswith("?? ")]
        parts = []
        if modified:
            parts.append("edit: " + ", ".join(modified[:3]))
        if new_files:
            parts.append("add: " + ", ".join(new_files[:3]))
        return (" | ".join(parts) or "auto: modifiche")[:72]

    def _last_commit_hash(self):
        return self._run(["git", "rev-parse", "--short", "HEAD"]).get("stdout", "").strip()

    def _backup(self):
        try:
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            dst = BACKUP_DIR / ("dustai_" + ts)
            shutil.copytree(self.repo_dir, dst,
                            ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
            backups = sorted(BACKUP_DIR.glob("dustai_*"))
            for old in backups[:-5]:
                shutil.rmtree(old, ignore_errors=True)
        except Exception as e:
            log.warning("Backup fallito: %s", e)

    def _run(self, cmd):
        try:
            result = subprocess.run(cmd, cwd=str(self.repo_dir), capture_output=True,
                                    text=True, encoding="utf-8", errors="replace", timeout=60)
            return {"ok": result.returncode == 0, "stdout": result.stdout,
                    "stderr": result.stderr, "code": result.returncode}
        except Exception as e:
            return {"ok": False, "error": str(e), "stdout": "", "stderr": ""}


class GitSyncTool:
    """Tool wrapper per ToolRegistry."""

    def __init__(self, config):
        self.config = config
        self._sync = None

    def _get(self):
        if not self._sync:
            self._sync = GitHubSync(self.config)
        return self._sync

    def git_sync(self, message=""):
        results = self._get().auto_sync(message)
        return "\n".join(
            ("OK" if r.get("ok") else "FAIL") + " " + step + ": " + r.get("msg", r.get("error", ""))
            for step, r in results.items()
        )

    def git_commit(self, message):
        r = self._get().commit(message)
        return ("OK: " if r.get("ok") else "FAIL: ") + r.get("msg", r.get("error", ""))

    def git_push(self):
        r = self._get().push()
        return ("OK: " if r.get("ok") else "FAIL: ") + r.get("msg", r.get("error", ""))

    def git_pull(self):
        r = self._get().pull()
        return ("OK: " if r.get("ok") else "FAIL: ") + r.get("msg", r.get("error", ""))

    def git_status(self):
        return self._get().status()
'''

(SRC / "github_sync.py").write_text(GITHUB_SYNC, encoding="utf-8")
print("  OK github_sync.py")

# ══════════════════════════════════════════════════════════════
# STEP 5: Patcha registry.py in modo sicuro
# ══════════════════════════════════════════════════════════════
print("[5/5] Patch registry.py...")

REGISTRY = SRC / "tools" / "registry.py"
if not REGISTRY.exists():
    print("  SKIP: registry.py non trovato")
else:
    reg_src = REGISTRY.read_text(encoding="utf-8")

    # Backup
    bak = BAK / ("registry.bak_clean_" + str(int(time.time())) + ".py")
    shutil.copy2(REGISTRY, bak)
    print("  Backup: " + str(bak))

    NEED_METHODS = "_get_conductor_tool" not in reg_src
    NEED_DISPATCH = '"ai_ask"' not in reg_src

    if NEED_METHODS:
        # Trova l'ultimo metodo della classe (cerca "def execute" o fine classe)
        # Inserisci prima del primo metodo "def execute" o alla fine
        METHOD_BLOCK = (
            "\n"
            "    # ── Orchestra AI / GitHub tools (v2.0) ──\n"
            "    def _get_conductor_tool(self):\n"
            "        if not hasattr(self, '_conductor_tool_inst'):\n"
            "            try:\n"
            "                from ..ai_conductor import AIConductorTool\n"
            "                self._conductor_tool_inst = AIConductorTool(self.config)\n"
            "            except Exception as e:\n"
            "                self._conductor_tool_inst = None\n"
            "                self._failed['conductor'] = str(e)\n"
            "        return self._conductor_tool_inst\n"
            "\n"
            "    def _get_git_sync_tool(self):\n"
            "        if not hasattr(self, '_git_sync_tool_inst'):\n"
            "            try:\n"
            "                from ..github_sync import GitSyncTool\n"
            "                self._git_sync_tool_inst = GitSyncTool(self.config)\n"
            "            except Exception as e:\n"
            "                self._git_sync_tool_inst = None\n"
            "                self._failed['git_sync'] = str(e)\n"
            "        return self._git_sync_tool_inst\n"
        )
        # Inserisci prima di "def execute"
        if "    def execute(" in reg_src:
            reg_src = reg_src.replace("    def execute(", METHOD_BLOCK + "    def execute(", 1)
            print("  OK metodi _get_conductor_tool / _get_git_sync_tool")
        else:
            reg_src += "\n" + METHOD_BLOCK
            print("  OK metodi aggiunti in fondo")

    if NEED_DISPATCH:
        # Trova il dizionario di dispatch (contiene "sys_exec" o "file_read")
        # e aggiungi le voci orchestra
        DISPATCH_ENTRIES = (
            "\n"
            "            # Orchestra AI\n"
            "            'ai_ask':     lambda p: (self._get_conductor_tool().ai_ask(**p) if self._get_conductor_tool() else 'N/D'),\n"
            "            'ai_parallel':lambda p: (self._get_conductor_tool().ai_parallel(**p) if self._get_conductor_tool() else 'N/D'),\n"
            "            'ai_status':  lambda p: (self._get_conductor_tool().ai_status() if self._get_conductor_tool() else 'N/D'),\n"
            "            'ai_models':  lambda p: (self._get_conductor_tool().ai_models(**p) if self._get_conductor_tool() else 'N/D'),\n"
            "            'git_sync':   lambda p: (self._get_git_sync_tool().git_sync(**p) if self._get_git_sync_tool() else 'N/D'),\n"
            "            'git_commit': lambda p: (self._get_git_sync_tool().git_commit(**p) if self._get_git_sync_tool() else 'N/D'),\n"
            "            'git_status': lambda p: (self._get_git_sync_tool().git_status() if self._get_git_sync_tool() else 'N/D'),\n"
            "            'git_push':   lambda p: (self._get_git_sync_tool().git_push() if self._get_git_sync_tool() else 'N/D'),\n"
        )

        # Cerca un anchor sicuro nel dispatch dict
        ANCHORS = ['"sys_exec":', "'sys_exec':", '"file_read":', "'file_read':"]
        inserted = False
        for anchor in ANCHORS:
            if anchor in reg_src:
                reg_src = reg_src.replace(anchor, DISPATCH_ENTRIES + "            " + anchor, 1)
                print("  OK dispatch voci orchestra inserite dopo anchor: " + anchor)
                inserted = True
                break
        if not inserted:
            print("  WARN: anchor dispatch non trovato - aggiungi manualmente ai_ask in registry")

    # Verifica sintassi
    try:
        ast.parse(reg_src)
        REGISTRY.write_text(reg_src, encoding="utf-8")
        print("  OK registry.py salvato (sintassi verificata)")
    except SyntaxError as e:
        print("  ERRORE sintassi: " + str(e))
        print("  Ripristino backup...")
        shutil.copy2(bak, REGISTRY)
        print("  Backup ripristinato. Aggiungi i tool a registry.py manualmente.")

# ══════════════════════════════════════════════════════════════
# STEP 6: litellm
# ══════════════════════════════════════════════════════════════
print("\nInstallo litellm...")
r = subprocess.run([sys.executable, "-m", "pip", "install", "litellm", "--quiet"],
                   capture_output=True, text=True)
print("  OK litellm" if r.returncode == 0 else "  WARN litellm: " + r.stderr[:100])

# ══════════════════════════════════════════════════════════════
# STEP 7: Commit e push
# ══════════════════════════════════════════════════════════════
print("\nCommit e push...")
from datetime import datetime
ts = datetime.now().strftime("%Y-%m-%d %H:%M")
for cmd in [
    ["git", "add", "-A"],
    ["git", "commit", "-m", "feat: AIOrchestra v2.0 router+gateway+conductor+github (" + ts + ")"],
    ["git", "push", "origin", "master"],
]:
    r = subprocess.run(cmd, cwd=str(BASE), capture_output=True, text=True, encoding="utf-8")
    label = " ".join(cmd[:2])
    out = (r.stderr or r.stdout or "")
    if r.returncode == 0 or "nothing to commit" in out or "up to date" in out:
        print("  OK " + label)
    else:
        print("  WARN " + label + ": " + out[:150])

print("""
==================================================
Orchestra v2.0 installata!

PROSSIMO PASSO – aggiungi in A:\\dustai_stuff\\.env:
  OPENROUTER_API_KEY=sk-or-v1-...
  GOOGLE_API_KEY_2=AIza...
  GOOGLE_API_KEY_3=AIza...

POI USA nella GUI DUST:
  ai_ask prompt="spiega questo bug" model=auto
  ai_ask prompt="fix veloce" model=free
  ai_parallel prompt="miglior approccio?"
  ai_models filter_available=available
  git_sync message="update"
==================================================
""")
