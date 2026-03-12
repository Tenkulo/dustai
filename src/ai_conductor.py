"""DUST AI – AIConductor v2.0
Orchestratore centrale: sceglie se usare singolo modello, parallelo, o HumanResearcher.
"""
import logging, time, threading
from pathlib import Path
log = logging.getLogger("AIConductor")

MODEL_ALIASES = {
    "auto":"auto","gemini":"gemini/gemini-2.5-flash","gemini3":"gemini/gemini-2.5-pro",
    "claude":"openrouter/anthropic/claude-sonnet-4-6","gpt":"openrouter/openai/gpt-5.2",
    "grok":"openrouter/x-ai/grok-4","deepseek":"openrouter/deepseek/deepseek-v3",
    "ollama":"ollama/qwen3:8b","local":"ollama/qwen3:8b","free":"auto",
    "browser":"browser/gemini",
}


class AIConductor:
    def __init__(self, config):
        self.config    = config
        self._gw       = None
        self._research = None
        self._n_tasks  = 0

    def ask(self, prompt: str, model="auto", mode="auto") -> dict:
        """Singola domanda a un modello."""
        gw = self._gateway()
        if model != "auto":
            mid = MODEL_ALIASES.get(model.lower(), model)
            r   = gw.call(mid, prompt)
        else:
            r = gw.call_auto(prompt)
        self._n_tasks += 1
        return r

    def ask_parallel(self, prompt: str, models: list = None) -> dict:
        """Chiede a più modelli in parallelo, ritorna la risposta più completa."""
        from .ai_router import MODELS as ALL_MODELS, ROUTES
        gw = self._gateway()
        if not models:
            # Usa i migliori 3 free disponibili
            models = [m for m in ROUTES["parallel"]
                      if gw.router._available(m)][:3]
        results = gw.call_parallel(prompt, models)
        ok = [r for r in results if r.get("ok")]
        if not ok:
            return {"ok": False, "error": "tutti falliti", "text": ""}
        best = max(ok, key=lambda r: len(r.get("text","")))
        self._n_tasks += 1
        return {"ok": True, "text": best["text"],
                "model": best.get("model_id","?"),
                "n_ok": len(ok), "n_total": len(results)}

    def research(self, task: str, use_web=True) -> dict:
        """Ricerca completa (web + multi-AI + sintesi)."""
        return self._researcher().research(task, use_web=use_web)

    def status(self) -> str:
        gw   = self._gateway()
        free = gw.router.available_free()
        return (f"AIConductor: {self._n_tasks} task eseguiti\n"
                f"Modelli free disponibili: {len(free)}\n"
                + "\n".join("  ✅ "+m for m in free[:8]))

    def _gateway(self):
        if not self._gw:
            from .ai_gateway import AIGateway
            self._gw = AIGateway(self.config)
        return self._gw

    def _researcher(self):
        if not self._research:
            from .human_researcher import HumanResearcher
            self._research = HumanResearcher(self.config)
        return self._research


class AIConductorTool:
    """Wrapper per ToolRegistry."""
    def __init__(self, config):
        self.config = config
        self._c     = None

    def _get(self) -> AIConductor:
        if not self._c:
            self._c = AIConductor(self.config)
        return self._c

    def ai_ask(self, prompt: str, model: str = "auto", mode: str = "auto") -> str:
        r = self._get().ask(prompt, model=model, mode=mode)
        if r.get("ok"):
            m = r.get("model_id","?").split("/")[-1]
            return f"[{m}] {r['text']}"
        return "❌ " + r.get("error", "errore")

    def ai_parallel(self, prompt: str, models: str = "") -> str:
        from .ai_router import MODELS as ALL_MODELS
        ALIASES = {"gemini":"gemini-flash","claude":"claude-sonnet","gpt":"gpt-5",
                   "ollama":"ollama-qwen","deepseek":"deepseek"}
        mlist = [ALIASES.get(m.strip(), m.strip())
                 for m in models.split(",") if m.strip()] if models.strip() else None
        r = self._get().ask_parallel(prompt, mlist)
        if r.get("ok"):
            return f"[PARALLELO {r.get('n_ok',1)}/{r.get('n_total',1)}] {r['text']}"
        return "❌ " + r.get("error","tutti falliti")

    def ai_research(self, task: str, web: str = "true") -> str:
        """Ricerca come una persona: web + multi-AI + sintesi."""
        use_web = web.lower() not in ("false","0","no")
        r = self._get().research(task, use_web=use_web)
        if r.get("ok"):
            return f"[Research {r['elapsed']}s] {r['synthesis']}"
        return "❌ Ricerca fallita"

    def ai_status(self) -> str:
        return self._get().status()

    def ai_models(self, filter_available: str = "all") -> str:
        try:
            from .ai_router import MODELS
        except ImportError:
            from ai_router import MODELS
        gw    = self._get()._gateway()
        lines = ["Modelli DUST AI (Mar 2026):","─"*50]
        for name, m in MODELS.items():
            avail = gw.router._available(name)
            if filter_available == "available" and not avail:
                continue
            if filter_available == "free" and not m.get("free"):
                continue
            icon  = "✅" if avail else "❌"
            free  = " [FREE]" if m.get("free") else " [PAID]"
            lines.append(f"  {icon} {name:<18}{free} IQ:{m.get('iq','?'):>3} | {', '.join(m.get('str',[])[:3])}")
        return "\n".join(lines)
