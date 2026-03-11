"""DUST AI – AIGateway v2.0"""
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
