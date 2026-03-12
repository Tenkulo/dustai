"""DUST AI – AIGateway v2.0
Chiama qualsiasi provider: Gemini, OpenRouter, Ollama, Browser.
"""
import os, time, json, logging
from pathlib import Path
log = logging.getLogger("AIGateway")

try:
    from .ai_router import AIRouter, MODELS
except ImportError:
    from ai_router import AIRouter, MODELS


class AIGateway:
    def __init__(self, config):
        self.config = config
        self.router = AIRouter(config)
        self._has_litellm = self._init_litellm()
        self._log_f = config.get_base_path() / "logs" / "gateway_usage.jsonl"

    # ─── API pubblica ──────────────────────────────────────────────────
    def call(self, model_id: str, prompt: str, system="", max_tokens=2000) -> dict:
        if model_id.startswith("browser/"):
            return self._browser_call(model_id, prompt)
        if model_id.startswith("ollama/"):
            return self._ollama(model_id, prompt, system, max_tokens)
        if self._has_litellm and not model_id.startswith("gemini/"):
            r = self._litellm(model_id, prompt, system, max_tokens)
            if r.get("ok"):
                return r
        if model_id.startswith("gemini/"):
            return self._gemini_direct(model_id, prompt, system, max_tokens)
        if "openrouter" in model_id:
            return self._openrouter(model_id, prompt, system, max_tokens)
        return {"ok": False, "error": "Nessun provider per: " + model_id}

    def call_auto(self, prompt: str, task="auto", free_only=False) -> dict:
        if task == "auto":
            task = self.router.classify(prompt)
        route = self.router.get_route(task, free_only)
        for model_name in route:
            mid = MODELS[model_name]["id"]
            t0  = time.time()
            r   = self.call(mid, prompt)
            lat = round(time.time() - t0, 2)
            if r.get("ok"):
                self._log(mid, task, True, lat)
                r["model_name"] = model_name
                return r
            err = r.get("error", "")
            if any(x in err for x in ["429","RESOURCE_EXHAUSTED","quota","rate"]):
                self.router.set_cooldown(mid, 65)
        return {"ok": False, "error": "Tutti i modelli falliti per: " + task}

    def call_parallel(self, prompt: str, model_names: list) -> list:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        results = []
        with ThreadPoolExecutor(max_workers=len(model_names)) as ex:
            futs = {ex.submit(self.call, MODELS[m]["id"], prompt): m
                    for m in model_names if m in MODELS}
            for f in as_completed(futs, timeout=60):
                name = futs[f]
                try:
                    r = f.result(timeout=5)
                    r["model_name"] = name
                    results.append(r)
                except Exception as e:
                    results.append({"ok": False, "model_name": name, "error": str(e)})
        return results

    # ─── Provider: LiteLLM ────────────────────────────────────────────
    def _litellm(self, model_id, prompt, system, max_tokens):
        try:
            from litellm import completion
            msgs = ([{"role":"system","content":system}] if system else []) + \
                   [{"role":"user","content":prompt}]
            resp = completion(model=model_id, messages=msgs,
                              max_tokens=max_tokens, timeout=60)
            text = resp.choices[0].message.content or ""
            return {"ok": True, "text": text.strip(), "model_id": model_id}
        except Exception as e:
            return {"ok": False, "error": str(e)[:300], "model_id": model_id}

    # ─── Provider: Gemini diretto ─────────────────────────────────────
    def _gemini_direct(self, model_id, prompt, system, max_tokens):
        model_name = model_id.replace("gemini/", "")
        # Prova KEY1 → KEY2 → KEY3
        for env in ("GOOGLE_API_KEY", "GOOGLE_API_KEY_2", "GOOGLE_API_KEY_3"):
            key = os.environ.get(env, "")
            if not key:
                continue
            try:
                import google.generativeai as genai
                genai.configure(api_key=key)
                m = genai.GenerativeModel(
                    model_name,
                    system_instruction=system if system else None)
                cfg = genai.types.GenerationConfig(max_output_tokens=max_tokens)
                resp = m.generate_content(prompt, generation_config=cfg)
                try:
                    text = resp.text.strip()
                except Exception:
                    text = ""
                if text:
                    log.info("Gemini OK via %s (%d chars)", env, len(text))
                    return {"ok": True, "text": text, "model_id": model_id, "key_used": env}
            except Exception as e:
                err = str(e)
                if any(x in err for x in ["429","RESOURCE_EXHAUSTED","quota"]):
                    self.router.set_cooldown(model_id, 65)
                    continue
                return {"ok": False, "error": err[:300], "model_id": model_id}
        return {"ok": False, "error": "Tutte le chiavi Gemini esaurite/mancanti", "model_id": model_id}

    # ─── Provider: OpenRouter ─────────────────────────────────────────
    def _openrouter(self, model_id, prompt, system, max_tokens):
        key = os.environ.get("OPENROUTER_API_KEY", "")
        if not key:
            return {"ok": False, "error": "OPENROUTER_API_KEY mancante"}
        try:
            import requests
            or_model = model_id.replace("openrouter/", "")
            msgs = ([{"role":"system","content":system}] if system else []) + \
                   [{"role":"user","content":prompt}]
            resp = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": "Bearer "+key, "Content-Type": "application/json"},
                json={"model": or_model, "messages": msgs, "max_tokens": max_tokens},
                timeout=60)
            if resp.status_code == 429:
                return {"ok": False, "error": "429 OpenRouter"}
            data = resp.json()
            if resp.status_code != 200:
                return {"ok": False, "error": str(data.get("error", resp.text))[:200]}
            text = data["choices"][0]["message"]["content"].strip()
            return {"ok": True, "text": text, "model_id": model_id}
        except Exception as e:
            return {"ok": False, "error": str(e)[:300]}

    # ─── Provider: Ollama locale ──────────────────────────────────────
    def _ollama(self, model_id, prompt, system, max_tokens):
        model_name = model_id.replace("ollama/", "")
        try:
            import ollama
            msgs = ([{"role":"system","content":system}] if system else []) + \
                   [{"role":"user","content":prompt}]
            resp = ollama.chat(model=model_name, messages=msgs,
                               options={"num_predict": max_tokens}, stream=False)
            return {"ok": True, "text": resp["message"]["content"].strip(), "model_id": model_id}
        except Exception as e:
            return {"ok": False, "error": str(e)[:300]}

    # ─── Provider: Browser AI ─────────────────────────────────────────
    def _browser_call(self, model_id, prompt):
        provider = model_id.replace("browser/", "")
        try:
            from .tools.browser_ai_bridge import BrowserAIBridge
        except ImportError:
            try:
                from tools.browser_ai_bridge import BrowserAIBridge
            except ImportError:
                return {"ok": False, "error": "BrowserAIBridge non installato"}
        try:
            bridge = BrowserAIBridge(self.config)
            r = bridge.query(prompt, provider=provider)
            if r.get("ok"):
                return {"ok": True, "text": r["text"], "model_id": model_id}
            return {"ok": False, "error": r.get("error", "browser fallito")}
        except Exception as e:
            return {"ok": False, "error": str(e)[:200]}

    # ─── Utility ──────────────────────────────────────────────────────
    def _init_litellm(self):
        try:
            import litellm
            litellm.suppress_debug_info = True
            key = os.environ.get("GOOGLE_API_KEY", "")
            if key:
                os.environ.setdefault("GEMINI_API_KEY", key)
            return True
        except ImportError:
            return False

    def _log(self, model, task, ok, lat):
        try:
            entry = json.dumps({"ts": datetime.now().isoformat(), "model": model,
                                "task": task, "ok": ok, "lat": lat})
            with open(self._log_f, "a", encoding="utf-8") as f:
                f.write(entry + "\n")
        except Exception:
            pass
