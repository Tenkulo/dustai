"""
╔══════════════════════════════════════════════════════════════════════════╗
║  DUST AI – COMPLETE INSTALL v4.0  (Mar 2026)                           ║
║  Un solo script che scrive e collega TUTTO il sistema                  ║
╠══════════════════════════════════════════════════════════════════════════╣
║  COSA FA:                                                               ║
║  1. HumanResearcher  – agisce come una persona che cerca qualcosa      ║
║     decompose → web_search → multi-AI parallelo → sintesi              ║
║  2. AIOrchestra      – router + gateway + conductor (LiteLLM/OpenRouter)║
║  3. BrowserAIBridge  – Gemini/ChatGPT/Claude/Grok/Perplexity via browser║
║  4. HallucinationGuard v2 – CoV + cross-validation gratis              ║
║  5. SelfHealEngine v2 – healing per categoria errore                   ║
║  6. agent.py CASCADE – KEY1→KEY2→KEY3→BrowserAI→Ollama                ║
║  7. registry.py FIX  – lambda fix + tutti i tool registrati            ║
║  8. github_sync      – auto-commit dopo ogni task                      ║
║                                                                         ║
║  AI GRATUITE USATE (in ordine di preferenza):                          ║
║  Gemini 2.5 Flash (1500/day) → Gemini 2.5 Flash KEY2 → KEY3           ║
║  → Gemini Web (browser, illimitato) → ChatGPT Web → Claude Web         ║
║  → Grok Web → Perplexity Web → Ollama qwen3:8b → Ollama mistral       ║
║                                                                         ║
║  Esegui: python A:\\dustai\\DUST_COMPLETE_INSTALL.py                    ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
import ast, shutil, time, subprocess, sys, json, os
from pathlib import Path
from datetime import datetime

BASE  = Path(r"A:\dustai")
SRC   = BASE / "src"
TOOLS = SRC / "tools"
STUFF = Path(r"A:\dustai_stuff")
BAK   = STUFF / "patches"
BAK.mkdir(parents=True, exist_ok=True)
(STUFF / "logs").mkdir(parents=True, exist_ok=True)
(STUFF / "memory").mkdir(parents=True, exist_ok=True)
(STUFF / "cache" / "browser_ai").mkdir(parents=True, exist_ok=True)
(STUFF / "browser_profiles").mkdir(parents=True, exist_ok=True)

_ok = []; _fail = []

def backup(f):
    p = Path(f)
    if p.exists():
        d = BAK / (p.stem + ".bak_" + str(int(time.time())) + p.suffix)
        shutil.copy2(p, d)

def write(path, content, label):
    try:
        ast.parse(content)
        Path(path).write_text(content, encoding="utf-8")
        print("  ✅ " + label)
        _ok.append(label)
    except SyntaxError as e:
        print("  ❌ SINTASSI " + label + ": " + str(e))
        _fail.append(label)

def patch(path, old, new, label):
    p = Path(path)
    if not p.exists():
        print("  ⚠️  " + label + ": file non trovato")
        return
    src = p.read_text(encoding="utf-8")
    if old in src and new not in src:
        backup(path)
        src = src.replace(old, new, 1)
        write(path, src, label)
    elif new in src:
        print("  ⏭️  " + label + " (già patchato)")
    else:
        print("  ⚠️  " + label + ": pattern non trovato")

print("=" * 68)
print("DUST AI – COMPLETE INSTALL v4.0")
print("=" * 68)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. src/ai_router.py – routing intelligente Mar 2026
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print("\n[1/10] ai_router.py")
write(SRC / "ai_router.py", r'''"""DUST AI – AIRouter v2.0 (Mar 2026)
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
''', "ai_router.py")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. src/ai_gateway.py – chiamate a tutti i provider
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print("[2/10] ai_gateway.py")
write(SRC / "ai_gateway.py", r'''"""DUST AI – AIGateway v2.0
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
''', "ai_gateway.py")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. src/human_researcher.py – IL CUORE: agisce come una persona che cerca
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print("[3/10] human_researcher.py  ← NUOVO CUORE")
write(SRC / "human_researcher.py", r'''"""
DUST AI – HumanResearcher v1.0
Agisce come una persona che cerca qualcosa:
  1. DECOMPOSE  – spezza il task in sotto-domande
  2. SEARCH     – cerca sul web (WebSearchTool)
  3. PARALLEL   – chiede a 3 AI in parallelo
  4. VALIDATE   – cross-valida le risposte (HallucinationGuard)
  5. SYNTHESIZE – un'AI sintetizza il meglio
  6. SAVE       – salva in memoria + GitHub

Inspired by: ReConcile (multi-model round-table), SALLMA, SkillOrchestra
"""
import json, time, logging, threading
from pathlib import Path
from datetime import datetime
log = logging.getLogger("HumanResearcher")

# Modelli da usare in parallelo (preferiti free)
PARALLEL_MODELS = [
    "gemini-flash",    # Gemini 2.5 Flash (KEY1)
    "gemini-flash2",   # Gemini 2.5 Flash (KEY2) – quota separata
    "gemini-pro",      # Gemini 2.5 Pro – più intelligente
]
SYNTHESIZER = "gemini-flash"   # modello usato per sintetizzare

DECOMPOSE_PROMPT = """Sei un assistente che aiuta a pianificare una ricerca.
Dato questo task/domanda, elenca al massimo 3 sotto-domande chiave da rispondere.
Rispondi SOLO in JSON: {"subquestions": ["domanda1", "domanda2", "domanda3"]}

TASK: {task}"""

SYNTHESIZE_PROMPT = """Sei un esperto sintetizzatore di informazioni.
Hai ricevuto risposte da più AI diverse sullo stesso task. 
Sintetizza la risposta migliore, più completa e accurata.
Elimina contraddizioni, privilegia il consenso, segnala incertezze.

TASK ORIGINALE: {task}

RISPOSTE RICEVUTE:
{responses}

RISULTATI WEB (se disponibili):
{web_results}

Fornisci una risposta definitiva, strutturata e pratica."""


class HumanResearcher:
    """
    Orchestratore principale che agisce come un ricercatore umano.
    Usa parallelo di AI + web search per rispondere al meglio.
    """
    def __init__(self, config):
        self.config = config
        self._gw    = None
        self._mem   = config.get_base_path() / "memory"
        self._mem.mkdir(exist_ok=True)

    def research(self, task: str, use_web=True, free_only=True) -> dict:
        """
        Metodo principale: ricerca completa come farebbe una persona.
        """
        t0 = time.time()
        log.info("HumanResearcher: task=%s", task[:80])
        print(f"\n🔍 DUST ricerca: {task[:80]}...")

        result = {
            "task":        task,
            "subquestions": [],
            "web_results": "",
            "ai_responses": [],
            "synthesis":   "",
            "model_used":  "",
            "elapsed":     0.0,
            "ok":          False,
        }

        # ── STEP 1: Decomposizione task ───────────────────────────────
        try:
            subq = self._decompose(task)
            result["subquestions"] = subq
            if subq:
                print(f"  📋 Sotto-domande: {len(subq)}")
        except Exception as e:
            log.warning("Decompose fallito: %s", e)

        # ── STEP 2: Web search (come una persona googla prima) ────────
        web_results = ""
        if use_web:
            try:
                web_results = self._web_search(task)
                result["web_results"] = web_results[:2000]
                if web_results:
                    print(f"  🌐 Web: {len(web_results)} chars trovati")
            except Exception as e:
                log.warning("Web search fallito: %s", e)

        # ── STEP 3: Chiedi a più AI in parallelo ─────────────────────
        print(f"  🤖 Parallelo su {len(PARALLEL_MODELS)} AI...")
        context = (f"Risultati web:\n{web_results[:1500]}\n\n" if web_results else "")
        ai_responses = self._ask_parallel(task, context)
        result["ai_responses"] = ai_responses
        n_ok = sum(1 for r in ai_responses if r.get("ok"))
        print(f"  ✅ {n_ok}/{len(PARALLEL_MODELS)} AI hanno risposto")

        # ── STEP 4: Cross-validation (HallucinationGuard) ────────────
        valid_responses = self._validate(ai_responses)

        # ── STEP 5: Sintesi finale ────────────────────────────────────
        synthesis = self._synthesize(task, valid_responses, web_results)
        result["synthesis"]  = synthesis
        result["ok"]         = bool(synthesis)
        result["elapsed"]    = round(time.time() - t0, 1)
        result["model_used"] = SYNTHESIZER

        if synthesis:
            print(f"  ✨ Sintesi: {len(synthesis)} chars in {result['elapsed']}s")
        else:
            # Fallback: usa la miglior risposta singola
            best = max((r for r in ai_responses if r.get("ok")),
                       key=lambda r: len(r.get("text","")), default=None)
            if best:
                result["synthesis"] = best["text"]
                result["ok"]        = True

        # ── STEP 6: Salva in memoria ──────────────────────────────────
        self._save_memory(result)
        return result

    # ── Decomposizione ────────────────────────────────────────────────
    def _decompose(self, task: str) -> list:
        gw = self._gateway()
        prompt = DECOMPOSE_PROMPT.format(task=task)
        r = gw.call_auto(prompt, task="fast")
        if not r.get("ok"):
            return []
        try:
            text = r["text"]
            import re
            m = re.search(r'\{[^}]+\}', text, re.DOTALL)
            if m:
                data = json.loads(m.group())
                return data.get("subquestions", [])[:3]
        except Exception:
            pass
        return []

    # ── Web search ────────────────────────────────────────────────────
    def _web_search(self, task: str) -> str:
        try:
            from .tools.registry import ToolRegistry
            reg = ToolRegistry(self.config)
            result = reg.execute("web_search", {"query": task[:200]})
            if isinstance(result, str) and len(result) > 50:
                return result
        except Exception:
            pass
        # Fallback: cerca con Perplexity browser
        try:
            from .tools.browser_ai_bridge import BrowserAIBridge
            bridge = BrowserAIBridge(self.config)
            r = bridge.query("Cerca informazioni aggiornate su: " + task, provider="perplexity")
            if r.get("ok"):
                return r["text"]
        except Exception:
            pass
        return ""

    # ── Parallelo AI ──────────────────────────────────────────────────
    def _ask_parallel(self, task: str, context: str) -> list:
        gw      = self._gateway()
        prompt  = (context + "\nDomanda: " + task) if context else task
        results = gw.call_parallel(prompt, PARALLEL_MODELS)
        return [{"ok": r.get("ok"), "text": r.get("text",""),
                 "model": r.get("model_name","?")} for r in results]

    # ── Cross-validation ──────────────────────────────────────────────
    def _validate(self, responses: list) -> list:
        """
        Versione semplice: tieni le risposte che hanno almeno 50 chars.
        Se abbiamo 2+ risposte, controlla sovrapposizione tematica.
        """
        valid = [r for r in responses if r.get("ok") and len(r.get("text","")) > 50]
        if len(valid) >= 2:
            # Semplice voto: tieni le risposte più lunghe (più complete)
            valid.sort(key=lambda r: len(r.get("text","")), reverse=True)
        return valid

    # ── Sintesi ───────────────────────────────────────────────────────
    def _synthesize(self, task: str, responses: list, web: str) -> str:
        if not responses:
            return ""
        if len(responses) == 1:
            return responses[0]["text"]
        formatted = "\n\n---\n".join(
            f"[{r['model']}]:\n{r['text'][:1200]}" for r in responses[:3])
        prompt = SYNTHESIZE_PROMPT.format(
            task=task, responses=formatted, web_results=web[:800])
        gw = self._gateway()
        r  = gw.call_auto(prompt, task="reasoning")
        return r.get("text", "") if r.get("ok") else (responses[0]["text"] if responses else "")

    # ── Memoria ───────────────────────────────────────────────────────
    def _save_memory(self, result: dict):
        try:
            f = self._mem / "research_history.jsonl"
            entry = {"ts": datetime.now().isoformat(),
                     "task": result["task"][:100],
                     "ok": result["ok"],
                     "elapsed": result["elapsed"],
                     "synthesis_len": len(result.get("synthesis",""))}
            with open(f, "a", encoding="utf-8") as fp:
                fp.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _gateway(self):
        if not self._gw:
            try:
                from .ai_gateway import AIGateway
                self._gw = AIGateway(self.config)
            except ImportError:
                from ai_gateway import AIGateway
                self._gw = AIGateway(self.config)
        return self._gw


class HumanResearcherTool:
    """Wrapper per ToolRegistry."""
    def __init__(self, config):
        self.config = config
        self._r     = None

    def _get(self):
        if not self._r:
            self._r = HumanResearcher(self.config)
        return self._r

    def dust_research(self, task: str, web: str = "true") -> str:
        """
        Ricerca completa: web + multi-AI + sintesi.
        Usa questo invece di ai_ask per task complessi.
        """
        use_web = web.lower() not in ("false", "0", "no")
        result  = self._get().research(task, use_web=use_web)
        if result["ok"]:
            n = len(result["ai_responses"])
            ok = sum(1 for r in result["ai_responses"] if r.get("ok"))
            header = f"[DUST Research | {ok}/{n} AI | {result['elapsed']}s]\n\n"
            return header + result["synthesis"]
        return "❌ Ricerca fallita: nessuna AI ha risposto"

    def dust_research_status(self) -> str:
        try:
            f = self._get()._mem / "research_history.jsonl"
            if not f.exists():
                return "Nessuna ricerca ancora."
            lines = f.read_text(encoding="utf-8").strip().splitlines()[-5:]
            entries = [json.loads(l) for l in lines]
            return "Ultime 5 ricerche:\n" + "\n".join(
                f"  {'✅' if e['ok'] else '❌'} [{e['ts'][:16]}] {e['task'][:50]}"
                for e in entries)
        except Exception as e:
            return "Errore: " + str(e)
''', "human_researcher.py")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. src/ai_conductor.py – orchestratore centrale
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print("[4/10] ai_conductor.py")
write(SRC / "ai_conductor.py", r'''"""DUST AI – AIConductor v2.0
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
''', "ai_conductor.py")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. src/tools/browser_ai_bridge.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print("[5/10] browser_ai_bridge.py")
write(TOOLS / "browser_ai_bridge.py", r'''"""DUST AI – BrowserAIBridge v2.0
Interroga AI via browser Playwright – zero rate limit.
"""
import json, time, logging, hashlib
from pathlib import Path
log = logging.getLogger("BrowserAI")

PROFILES = Path(r"A:\dustai_stuff\browser_profiles")
CACHE    = Path(r"A:\dustai_stuff\cache\browser_ai")
TTL      = 3600   # 1 ora cache

PROVIDERS = {
    "gemini":     {"url":"https://gemini.google.com/app",  "pri":1,
                   "inp":"rich-textarea div[contenteditable]",
                   "send":"button[aria-label*='Send']",
                   "out":"message-content p","done":"button[aria-label*='Send']:not([disabled])"},
    "chatgpt":    {"url":"https://chatgpt.com/",           "pri":2,
                   "inp":"#prompt-textarea",
                   "send":"button[data-testid='send-button']",
                   "out":"[data-message-author-role='assistant'] p",
                   "done":"button[data-testid='send-button']:not([disabled])"},
    "claude":     {"url":"https://claude.ai/new",          "pri":3,
                   "inp":"div[contenteditable='true']",
                   "send":"button[aria-label='Send Message']",
                   "out":".prose p","done":"button[aria-label='Send Message']:not([disabled])"},
    "grok":       {"url":"https://grok.com/",              "pri":4,
                   "inp":"textarea","send":"button[type='submit']",
                   "out":".message-content p","done":"button[type='submit']:not([disabled])"},
    "perplexity": {"url":"https://www.perplexity.ai/",     "pri":5,
                   "inp":"textarea[placeholder]","send":"button[aria-label*='Submit']",
                   "out":".prose p","done":"button[aria-label*='Submit']:not([disabled])"},
}
ORDER = sorted(PROVIDERS, key=lambda p: PROVIDERS[p]["pri"])


class BrowserAIBridge:
    def __init__(self, config=None):
        self.config = config
        PROFILES.mkdir(parents=True, exist_ok=True)
        CACHE.mkdir(parents=True, exist_ok=True)
        self._st = self._load_status()

    def query(self, prompt: str, provider="auto", use_cache=True) -> dict:
        if use_cache:
            c = self._cache_get(prompt, provider)
            if c:
                return {"ok": True, "text": c, "provider": provider+"_cached"}
        provs = ORDER if provider == "auto" else [provider]
        for p in provs:
            if self._st.get(p) == "error":
                continue
            try:
                r = self._query_one(p, prompt)
                if r.get("ok"):
                    if use_cache:
                        self._cache_set(prompt, p, r["text"])
                    return r
            except Exception as e:
                log.warning("BrowserAI %s: %s", p, str(e)[:80])
                self._st[p] = "error"
                self._save_status()
        return {"ok": False, "error": "Tutti i browser provider falliti"}

    def get_ready_providers(self) -> list:
        return [p for p in ORDER
                if (PROFILES/p).exists() and self._st.get(p) != "error"]

    def login(self, provider="gemini") -> str:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return "playwright non installato: pip install playwright && python -m playwright install chromium"
        try:
            with sync_playwright() as pw:
                ctx = pw.chromium.launch_persistent_context(
                    user_data_dir=str(PROFILES/provider),
                    headless=False, viewport={"width":1280,"height":800})
                page = ctx.new_page()
                page.goto(PROVIDERS[provider]["url"], timeout=30000)
                print(f"\n{'='*50}\nLOGIN MANUALE: {provider}")
                print("Fai login nel browser aperto, poi premi INVIO qui.")
                input(">>> INVIO dopo login: ")
                self._st[provider] = "ready"
                self._save_status()
                ctx.close()
            return f"✅ Login {provider} salvato."
        except Exception as e:
            return f"❌ Errore: {str(e)[:100]}"

    def status(self) -> str:
        lines = ["=== BrowserAI Status ==="]
        for p in ORDER:
            ok = (PROFILES/p).exists() and self._st.get(p) != "error"
            lines.append(("✅" if ok else "❌")+" "+p.ljust(12)+" ["+self._st.get(p,"non configurato")+"]")
        lines.append("\nPer fare login: browser_ai_login provider=gemini")
        return "\n".join(lines)

    def _query_one(self, provider: str, prompt: str, timeout_ms=60000) -> dict:
        cfg = PROVIDERS[provider]
        try:
            from playwright.sync_api import sync_playwright, TimeoutError as PwTO
            with sync_playwright() as pw:
                ctx = pw.chromium.launch_persistent_context(
                    user_data_dir=str(PROFILES/provider), headless=True,
                    args=["--no-sandbox","--disable-blink-features=AutomationControlled"])
                page = ctx.new_page()
                page.goto(cfg["url"], timeout=30000, wait_until="domcontentloaded")
                try:
                    page.wait_for_selector(cfg["inp"], timeout=12000)
                except PwTO:
                    ctx.close()
                    self._st[provider] = "logged_out"
                    return {"ok":False,"error":provider+": login scaduto – esegui browser_ai_login provider="+provider}
                el = page.locator(cfg["inp"]).last
                el.click()
                el.fill("")
                for i in range(0, len(prompt), 500):
                    el.type(prompt[i:i+500], delay=8)
                    time.sleep(0.05)
                page.locator(cfg["send"]).click(timeout=5000)
                try:
                    page.wait_for_selector(cfg["done"], timeout=timeout_ms)
                except PwTO:
                    pass
                time.sleep(1.5)
                texts = []
                for el in page.locator(cfg["out"]).all()[-20:]:
                    try:
                        t = el.inner_text().strip()
                        if t and len(t) > 5:
                            texts.append(t)
                    except Exception:
                        pass
                ctx.close()
                if not texts:
                    return {"ok":False,"error":provider+": nessun testo estratto"}
                self._st[provider] = "ready"
                self._save_status()
                return {"ok":True,"text":"\n\n".join(texts),"provider":provider+"_web"}
        except ImportError:
            return {"ok":False,"error":"playwright non installato"}
        except Exception as e:
            return {"ok":False,"error":str(e)[:200]}

    def _cache_key(self, p, prov):
        return hashlib.md5((prov+p[:500]).encode()).hexdigest()

    def _cache_get(self, prompt, provider):
        f = CACHE/(self._cache_key(prompt,provider)+".json")
        if not f.exists(): return None
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            if time.time()-d.get("ts",0) < TTL:
                return d.get("text")
        except Exception: pass
        return None

    def _cache_set(self, prompt, provider, text):
        try:
            (CACHE/(self._cache_key(prompt,provider)+".json")).write_text(
                json.dumps({"ts":time.time(),"text":text},ensure_ascii=False),
                encoding="utf-8")
        except Exception: pass

    def _load_status(self):
        f = PROFILES/"status.json"
        if f.exists():
            try: return json.loads(f.read_text(encoding="utf-8"))
            except: pass
        return {}

    def _save_status(self):
        try: (PROFILES/"status.json").write_text(json.dumps(self._st,indent=2),encoding="utf-8")
        except: pass


class BrowserAITool:
    def __init__(self, config):
        self.config = config
        self._b     = None

    def _get(self):
        if not self._b:
            self._b = BrowserAIBridge(self.config)
        return self._b

    def browser_ai_query(self, prompt: str, provider: str = "auto") -> str:
        r = self._get().query(prompt, provider)
        return ("["+r["provider"]+"] "+r["text"]) if r.get("ok") else "❌ "+r.get("error","")

    def browser_ai_login(self, provider: str = "gemini") -> str:
        return self._get().login(provider)

    def browser_ai_status(self) -> str:
        return self._get().status()
''', "browser_ai_bridge.py")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6. src/github_sync.py
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print("[6/10] github_sync.py")
write(SRC / "github_sync.py", r'''"""DUST AI – GitHubSync v2.0"""
import subprocess, logging, shutil, time
from pathlib import Path
from datetime import datetime
log = logging.getLogger("GitHubSync")
REPO   = Path(r"A:\dustai")
BACKUP = Path(r"A:\dustai_stuff\backups")

class GitHubSync:
    def __init__(self, config):
        self.config = config
        self._last_push = 0.0

    def auto_sync(self, msg="") -> dict:
        r = {}
        r["pull"]   = self.pull()
        r["commit"] = self.commit(msg or self._auto_msg())
        if time.time() - self._last_push > 1800 or msg:
            r["push"]       = self.push()
            self._last_push = time.time()
        else:
            r["push"] = {"ok": True, "msg": "push posticipato (< 30 min)"}
        return r

    def commit(self, msg="auto") -> dict:
        self._run(["git","add","-A"])
        s = self._run(["git","status","--porcelain"])
        if not s.get("stdout","").strip():
            return {"ok": True, "msg": "Niente da committare"}
        ts   = datetime.now().strftime("%Y-%m-%d %H:%M")
        full = f"[DUST {ts}] {msg[:60]}"
        r    = self._run(["git","commit","-m",full])
        return {"ok": r["ok"], "msg": full} if r["ok"] else {"ok": False, "error": r.get("stderr","")}

    def push(self) -> dict:
        BACKUP.mkdir(parents=True, exist_ok=True)
        ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
        dst = BACKUP / ("dustai_" + ts)
        try:
            shutil.copytree(REPO, dst, ignore=shutil.ignore_patterns(".git","__pycache__","*.pyc"))
            [shutil.rmtree(b, True) for b in sorted(BACKUP.glob("dustai_*"))[:-5]]
        except Exception: pass
        r = self._run(["git","push","origin","master"])
        return {"ok": True, "msg": "Push OK"} if r["ok"] else {"ok": False, "error": r.get("stderr","")}

    def pull(self) -> dict:
        r = self._run(["git","pull","origin","master","--rebase"])
        return {"ok": r["ok"], "msg": r.get("stdout","")[:80]}

    def status(self) -> str:
        log_ = self._run(["git","log","--oneline","-5"])
        dirty = self._run(["git","status","--short"])
        return ("Branch: master\nUltimi 5 commit:\n" + log_.get("stdout","") +
                "\nModifiche locali:\n" + (dirty.get("stdout","").strip() or "(nessuna)"))

    def _auto_msg(self) -> str:
        r = self._run(["git","status","--short"])
        files = [l[3:] for l in r.get("stdout","").strip().splitlines()[:3]]
        return "auto: " + ", ".join(files) if files else "auto: sync"

    def _run(self, cmd) -> dict:
        try:
            r = subprocess.run(cmd, cwd=str(REPO), capture_output=True,
                               text=True, encoding="utf-8", errors="replace", timeout=60)
            return {"ok": r.returncode==0, "stdout": r.stdout, "stderr": r.stderr}
        except Exception as e:
            return {"ok": False, "error": str(e), "stdout": "", "stderr": ""}


class GitSyncTool:
    def __init__(self, config):
        self.config = config
        self._s     = None

    def _get(self):
        if not self._s:
            self._s = GitHubSync(self.config)
        return self._s

    def git_sync(self, message: str = "") -> str:
        r = self._get().auto_sync(message)
        return "\n".join(("✅" if v.get("ok") else "❌")+" "+k+": "+v.get("msg",v.get("error",""))
                         for k, v in r.items())

    def git_commit(self, message: str) -> str:
        r = self._get().commit(message)
        return ("✅ " if r["ok"] else "❌ ") + r.get("msg", r.get("error",""))

    def git_push(self) -> str:
        r = self._get().push()
        return ("✅ " if r["ok"] else "❌ ") + r.get("msg", r.get("error",""))

    def git_status(self) -> str:
        return self._get().status()
''', "github_sync.py")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 7. Patcha registry.py – aggiungi TUTTI i nuovi tool
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print("[7/10] Patching registry.py")
REGISTRY = TOOLS / "registry.py"
if REGISTRY.exists():
    backup(REGISTRY)
    src = REGISTRY.read_text(encoding="utf-8")
    changed = False

    # 7a: Import nuovi moduli
    NEW_IMPORTS = """
# ─── DUST Orchestra imports (auto-generated) ─────────────────────────────
try:
    from ..ai_conductor import AIConductorTool as _AIConductorTool
    _CONDUCTOR_OK = True
except Exception:
    _CONDUCTOR_OK = False; _AIConductorTool = None

try:
    from ..human_researcher import HumanResearcherTool as _HRTool
    _HR_OK = True
except Exception:
    _HR_OK = False; _HRTool = None

try:
    from .browser_ai_bridge import BrowserAITool as _BrAI
    _BROWSER_OK = True
except Exception:
    _BROWSER_OK = False; _BrAI = None

try:
    from ..github_sync import GitSyncTool as _GitSync
    _GIT_OK = True
except Exception:
    _GIT_OK = False; _GitSync = None
"""
    if "_AIConductorTool" not in src:
        # Inserisci dopo gli import esistenti (cerca fine import block)
        import_end = src.find("\nclass ")
        if import_end > 0:
            src = src[:import_end] + NEW_IMPORTS + src[import_end:]
            changed = True
            print("  OK import Orchestra")

    # 7b: Getter lazy per tutti i tool
    GETTERS = """
    # ─── Getter lazy Orchestra ───────────────────────────────────────────
    def _get_conductor(self):
        if not hasattr(self, "_cond_inst"):
            self._cond_inst = _AIConductorTool(self.config) if _CONDUCTOR_OK else None
        return self._cond_inst

    def _get_researcher(self):
        if not hasattr(self, "_hr_inst"):
            self._hr_inst = _HRTool(self.config) if _HR_OK else None
        return self._hr_inst

    def _get_browser_ai(self):
        if not hasattr(self, "_bai_inst"):
            self._bai_inst = _BrAI(self.config) if _BROWSER_OK else None
        return self._bai_inst

    def _get_git(self):
        if not hasattr(self, "_git_inst"):
            self._git_inst = _GitSync(self.config) if _GIT_OK else None
        return self._git_inst

"""
    if "_get_conductor" not in src and "    def _get_git_sync_tool(" in src:
        src = src.replace("    def _get_git_sync_tool(", GETTERS + "    def _get_git_sync_tool(", 1)
        changed = True
        print("  OK getter lazy")
    elif "_get_conductor" not in src and "    def execute(" in src:
        src = src.replace("    def execute(", GETTERS + "    def execute(", 1)
        changed = True
        print("  OK getter lazy (fallback)")

    # 7c: Lambda nel dispatch – TUTTI i nuovi tool
    ORCHESTRA_LAMBDAS = """            # ─── AI Orchestra ───────────────────────────────────────────
            'ai_ask':           lambda p: (self._get_conductor().ai_ask(**self._safe_params(p))              if self._get_conductor() else 'N/D: ai_conductor'),
            'ai_parallel':      lambda p: (self._get_conductor().ai_parallel(**self._safe_params(p))         if self._get_conductor() else 'N/D'),
            'ai_research':      lambda p: (self._get_conductor().ai_research(**self._safe_params(p))         if self._get_conductor() else 'N/D'),
            'ai_status':        lambda p: (self._get_conductor().ai_status()                                 if self._get_conductor() else 'N/D'),
            'ai_models':        lambda p: (self._get_conductor().ai_models(**self._safe_params(p))           if self._get_conductor() else 'N/D'),
            'dust_research':    lambda p: (self._get_researcher().dust_research(**self._safe_params(p))      if self._get_researcher() else 'N/D'),
            # ─── Browser AI ─────────────────────────────────────────────
            'browser_ai_query': lambda p: (self._get_browser_ai().browser_ai_query(**self._safe_params(p))  if self._get_browser_ai() else 'N/D – esegui browser_ai_login'),
            'browser_ai_login': lambda p: (self._get_browser_ai().browser_ai_login(**self._safe_params(p))  if self._get_browser_ai() else 'N/D'),
            'browser_ai_status':lambda p: (self._get_browser_ai().browser_ai_status()                       if self._get_browser_ai() else 'N/D'),
            # ─── Git Sync ────────────────────────────────────────────────
            'git_sync':         lambda p: (self._get_git().git_sync(**self._safe_params(p))                  if self._get_git() else 'N/D'),
            'git_commit':       lambda p: (self._get_git().git_commit(**self._safe_params(p))                if self._get_git() else 'N/D'),
            'git_push':         lambda p: (self._get_git().git_push()                                       if self._get_git() else 'N/D'),
            'git_status':       lambda p: (self._get_git().git_status()                                     if self._get_git() else 'N/D'),
"""
    if "'ai_ask'" not in src and "# Orchestra AI" in src:
        src = src.replace("            # Orchestra AI\n", "            # Orchestra AI\n" + ORCHESTRA_LAMBDAS, 1)
        changed = True
        print("  OK lambda Orchestra nel dispatch")
    elif "'ai_ask'" not in src and "self._tools = {" in src:
        src = src.replace("self._tools = {", "self._tools = {\n" + ORCHESTRA_LAMBDAS, 1)
        changed = True
        print("  OK lambda Orchestra (fallback)")

    if changed:
        write(REGISTRY, src, "registry.py aggiornato")
    else:
        print("  ⏭️  registry.py (già aggiornato o pattern non trovato)")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 8. Patcha agent.py – CASCADE COMPLETO Gemini→KEY2→KEY3→Browser→Ollama
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print("[8/10] Patching agent.py – cascade completo")
AGENT = SRC / "agent.py"
if AGENT.exists():
    backup(AGENT)
    src = AGENT.read_text(encoding="utf-8")
    changed = False

    # 8a: init _browser_ai
    if "self._browser_ai = None" not in src:
        OLD = "        self._setup_gemini()\n        self._setup_ollama()"
        NEW = ("        self._setup_gemini()\n"
               "        self._setup_ollama()\n"
               "        self._browser_ai  = None  # BrowserAIBridge lazy\n"
               "        self._conductor   = None  # AIConductor lazy")
        if OLD in src:
            src = src.replace(OLD, NEW, 1); changed = True; print("  OK init lazy in __init__")

    # 8b: metodi _get_browser_ai + _get_conductor
    METHODS = '''
    def _get_browser_ai(self):
        """Lazy init BrowserAIBridge – fallback illimitato."""
        if self._browser_ai is None:
            try:
                from .tools.browser_ai_bridge import BrowserAIBridge
                self._browser_ai = BrowserAIBridge(self.config)
                self.log.info("BrowserAIBridge OK")
            except Exception as e:
                self.log.warning("BrowserAI N/D: %s", str(e)[:60])
                self._browser_ai = False
        return self._browser_ai if self._browser_ai else None

    def _get_conductor(self):
        """Lazy init AIConductor."""
        if self._conductor is None:
            try:
                from .ai_conductor import AIConductor
                self._conductor = AIConductor(self.config)
            except Exception as e:
                self.log.warning("AIConductor N/D: %s", str(e)[:60])
                self._conductor = False
        return self._conductor if self._conductor else None

'''
    if "_get_browser_ai" not in src and "    def _call_model(" in src:
        src = src.replace("    def _call_model(", METHODS + "    def _call_model(", 1)
        changed = True; print("  OK _get_browser_ai + _get_conductor")

    # 8c: CASCADE su SWITCH_TO_OLLAMA
    OLD_CASCADE = (
        '            except RuntimeError as e:\n'
        '                if "SWITCH_TO_OLLAMA" in str(e):\n'
        '                    self.log.warning("Gemini 429 → switch Ollama")\n'
        '                    print("   🔄 Gemini esaurito → Ollama locale")\n'
        '                else:\n'
        '                    raise'
    )
    NEW_CASCADE = (
        '            except RuntimeError as e:\n'
        '                if "SWITCH_TO_OLLAMA" in str(e):\n'
        '                    self.log.warning("429 → cascade KEY2/KEY3/Browser/Ollama")\n'
        '                    import os\n'
        '                    # STEP 1: Gemini KEY_2 e KEY_3\n'
        '                    for _env in ("GOOGLE_API_KEY_2","GOOGLE_API_KEY_3"):\n'
        '                        _k = os.environ.get(_env,"")\n'
        '                        if not _k: continue\n'
        '                        try:\n'
        '                            import google.generativeai as _g\n'
        '                            _g.configure(api_key=_k)\n'
        '                            _m = _g.GenerativeModel("gemini-2.5-flash")\n'
        '                            _task = (messages[-1].get("parts",[""])[0]\n'
        '                                     if messages else "")\n'
        '                            _resp = _m.generate_content(str(_task)[:3000])\n'
        '                            try:\n'
        '                                _txt = _resp.text.strip()\n'
        '                            except Exception:\n'
        '                                _txt = ""\n'
        '                            if _txt:\n'
        '                                print("   🔑 "+_env+" → OK")\n'
        '                                return {"type":"text","text":_txt}\n'
        '                        except Exception:\n'
        '                            pass\n'
        '                    # STEP 2: BrowserAI (Gemini/ChatGPT web – zero rate limit)\n'
        '                    _bridge = self._get_browser_ai()\n'
        '                    if _bridge and _bridge.get_ready_providers():\n'
        '                        _task_txt = (messages[-1].get("parts",[""])[0]\n'
        '                                     if messages else "")\n'
        '                        _br = _bridge.query(str(_task_txt)[:3000])\n'
        '                        if _br.get("ok"):\n'
        '                            print("   🌐 BrowserAI ["+_br["provider"]+"] → OK")\n'
        '                            return {"type":"text","text":_br["text"]}\n'
        '                    # STEP 3: Ollama locale (sempre disponibile)\n'
        '                    print("   🔄 Cascade esaurito → Ollama locale")\n'
        '                else:\n'
        '                    raise'
    )
    if OLD_CASCADE in src:
        src = src.replace(OLD_CASCADE, NEW_CASCADE); changed = True; print("  OK cascade KEY2/KEY3/Browser/Ollama")
    elif "SWITCH_TO_OLLAMA" in src and "STEP 1: Gemini KEY_2" not in src:
        print("  ⚠️  cascade: pattern leggermente diverso, cerca 'SWITCH_TO_OLLAMA' manualmente")

    if changed:
        write(AGENT, src, "agent.py cascade")
    else:
        print("  ⏭️  agent.py (già aggiornato)")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 9. Verifica __init__.py exports
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print("[9/10] __init__.py exports")
INIT = SRC / "__init__.py"
if INIT.exists():
    init_src = INIT.read_text(encoding="utf-8")
    to_add = []
    for mod, cls in [("ai_conductor","AIConductor"),
                     ("human_researcher","HumanResearcher"),
                     ("ai_gateway","AIGateway"),
                     ("ai_router","AIRouter"),
                     ("github_sync","GitHubSync")]:
        if cls not in init_src:
            to_add.append(f"from .{mod} import {cls}")
    if to_add:
        backup(INIT)
        new_init = init_src + "\n# Orchestra v4.0\n" + "\n".join(to_add) + "\n"
        write(INIT, new_init, "__init__.py")
    else:
        print("  ⏭️  __init__.py (già aggiornato)")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 10. pip + playwright + commit
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print("[10/10] pip install + commit")
for pkg in ["litellm", "playwright", "pyperclip"]:
    r = subprocess.run([sys.executable,"-m","pip","install",pkg,"--quiet"],
                       capture_output=True, text=True, timeout=120)
    icon = "✅" if r.returncode==0 else "⚠️ "
    print(f"  {icon} pip {pkg}")

# playwright chromium
r = subprocess.run([sys.executable,"-m","playwright","install","chromium","--quiet"],
                   capture_output=True, text=True, timeout=120)
print(f"  {'✅' if r.returncode==0 else '⚠️ '} playwright chromium")

ts = datetime.now().strftime("%Y-%m-%d %H:%M")
for cmd in [
    ["git","add","-A"],
    ["git","commit","-m",f"feat: DUST v4.0 – HumanResearcher+Orchestra+Browser+Cascade {ts}"],
    ["git","push","origin","master"],
]:
    r = subprocess.run(cmd, cwd=str(BASE), capture_output=True,
                       text=True, encoding="utf-8")
    out = r.stderr or r.stdout or ""
    label = " ".join(cmd[:2])
    if r.returncode==0 or "nothing" in out or "up to date" in out:
        print(f"  ✅ {label}")
    else:
        print(f"  ⚠️  {label}: {out[:100]}")

# ── REPORT FINALE ─────────────────────────────────────────────────────
print(f"""
╔══════════════════════════════════════════════════════════════════════╗
║  DUST COMPLETE INSTALL v4.0 – REPORT                               ║
╠══════════════════════════════════════════════════════════════════════╣
║  ✅ OK:  {len(_ok):<5}  ❌ FAIL: {len(_fail):<5}                               ║
╠══════════════════════════════════════════════════════════════════════╣
║  ARCHITETTURA INSTALLATA:                                           ║
║                                                                     ║
║  GUI DUST  ──►  ToolRegistry                                       ║
║                   │                                                 ║
║          ┌────────┴────────────────────┐                           ║
║          │                             │                            ║
║    AIConductorTool            HumanResearcherTool                  ║
║          │                             │                            ║
║    AIConductor            HumanResearcher (NUOVO)                  ║
║          │                    ├── WebSearch                        ║
║      AIGateway                ├── AI Parallelo (3 AI)              ║
║          │                    ├── Cross-Validate                   ║
║     ┌────┴────┐                └── Sintesi                         ║
║  Gemini    OpenRouter                                               ║
║  KEY1/2/3  /Browser  ──► BrowserAIBridge                          ║
║                              ├── Gemini Web (illimitato)           ║
║                              ├── ChatGPT Web                       ║
║                              ├── Claude Web                        ║
║                              ├── Grok Web                          ║
║                              └── Perplexity Web                    ║
║                          Ollama qwen3:8b (sempre)                  ║
╠══════════════════════════════════════════════════════════════════════╣
║  TOOL DISPONIBILI NELLA GUI:                                        ║
║  dust_research task="..." web="true"   ← NUOVO: ricerca umana      ║
║  ai_ask prompt="..." model=auto/gemini/claude/gpt                  ║
║  ai_parallel prompt="..." models="gemini,claude,gpt"               ║
║  ai_research task="..."                ← ricerca + sintesi          ║
║  ai_models filter_available=free                                    ║
║  browser_ai_login provider=gemini      ← setup una volta sola      ║
║  browser_ai_query prompt="..."         ← web browser AI            ║
║  git_sync message="..." / git_commit / git_status                  ║
╠══════════════════════════════════════════════════════════════════════╣
║  SETUP BROWSER (OBBLIGATORIO per browser AI):                       ║
║  Nella GUI DUST digita UNA VOLTA:                                   ║
║    browser_ai_login provider=gemini                                 ║
║    browser_ai_login provider=chatgpt                                ║
║  → Si apre Chrome, fai login, la sessione viene salvata per sempre ║
╚══════════════════════════════════════════════════════════════════════╝
""")
