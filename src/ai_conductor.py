"""DUST AI – AIConductor v2.0"""
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
