"""
DUST AI – Agent v4.0
ReAct loop: Gemini native function calling + cascade completo + tutti i fix.

FIXES inclusi:
- response.text safe (finish_reason=10)
- rate limit clamp 65s
- task_hint **kwargs
- google.generativeai (non google.genai, ancora funzionante)
- cascade KEY1→KEY2→KEY3→BrowserAI→Ollama qwen3→Ollama mistral
- _safe_params per dispatcher
"""
import json, logging, time, re, os
from datetime import datetime

import google.generativeai as genai
import google.generativeai.types as genai_types

from .tools.registry import ToolRegistry
from .memory import Memory

log = logging.getLogger("Agent")

SYSTEM_PROMPT = """Sei DUST AI – assistente personale intelligente e agente autonomo su Windows 11.
Sei conversazionale, utile e diretto. Parli sempre in italiano.

Puoi fare QUALSIASI cosa:
- Rispondere a domande, spiegare concetti, scrivere testi
- Cercare informazioni online con web_search
- Gestire file e cartelle (file_read, file_write, file_list, sys_exec)
- Aprire e controllare app (app_open, screen_do)
- Usare il browser e navigare siti (browser_go, browser_do, screen_do)
- Controllare il PC con mouse e tastiera su qualsiasi app (screen_do, screen_click, screen_type)
- Eseguire codice Python (code_run)
- Creare repo GitHub, push file, aprire PR (sys_exec con git, o screen_do)

COME TI COMPORTI:
- Rispondi in modo naturale e conciso
- Per domande e testi: rispondi DIRETTAMENTE senza tool
- Per azioni sul PC: usa i tool, uno alla volta, verifica ogni risultato
- Se mancano info per un'azione (es: nome file, URL) → CHIEDI prima
- Non eseguire azioni irreversibili senza conferma esplicita

REGOLE TOOL:
- Uno alla volta, verifica il risultato prima di proseguire
- sys_exec: usa sempre cmd /c per Windows (es: cmd /c dir "C:\\Users")
- file_write: verifica con file_read dopo
- screen_do: usa quando devi agire su GUI di un'app vera
"""

MAX_STEPS    = 25
MIN_INTERVAL = 6   # secondi min tra chiamate API


class Agent:
    def __init__(self, config):
        self.config  = config
        self.memory  = Memory(config)
        self.tools   = ToolRegistry(config)
        self._gemini = {}   # env_key → GenerativeModel
        self._browser_ai = None
        self._ollama_models = []
        self._last_call = 0.0

        self._setup_gemini()
        self._setup_browser_ai()
        self._setup_ollama()
        log.info("Agent pronto. Gemini keys: %d  Ollama: %s",
                 len(self._gemini), self._ollama_models)

    # ── Setup ──────────────────────────────────────────────────────────────────

    def _setup_gemini(self):
        for env, key in self.config.get_all_google_keys():
            try:
                genai.configure(api_key=key)
                name = self.config.get_model("primary")
                m = genai.GenerativeModel(
                    model_name=name,
                    system_instruction=SYSTEM_PROMPT,
                    tools=self._build_tool_defs(),
                )
                self._gemini[env] = m
                log.info("Gemini OK [%s]: %s", env, name)
            except Exception as e:
                log.warning("Gemini setup [%s]: %s", env, str(e)[:60])

    def _setup_browser_ai(self):
        try:
            from .tools.browser_ai_bridge import BrowserAIBridge
            self._browser_ai = BrowserAIBridge(self.config)
            log.info("BrowserAI bridge pronto")
        except Exception as e:
            log.debug("BrowserAI N/D: %s", str(e)[:60])

    def _setup_ollama(self):
        try:
            import ollama
            models = ollama.list()
            names  = [m.model for m in models.models] if hasattr(models, "models") else []
            prefer = ["qwen3:8b", "mistral-small3.1", "llama3.1:8b", "mistral:7b"]
            for p in prefer:
                if any(p in n for n in names):
                    self._ollama_models.append(p)
            if not self._ollama_models and names:
                self._ollama_models = names[:2]
            if self._ollama_models:
                log.info("Ollama: %s", self._ollama_models)
        except Exception:
            pass

    def _build_tool_defs(self):
        try:
            tools = self.tools.list_tools()
            if not tools:
                return None
            decls = []
            for name in tools[:60]:   # limite Gemini
                desc = self.tools.get_description(name)
                decls.append(genai_types.FunctionDeclaration(
                    name=name,
                    description=desc[:200],
                    parameters=genai_types.Schema(
                        type=genai_types.Type.OBJECT,
                        properties={
                            k: genai_types.Schema(type=genai_types.Type.STRING)
                            for k in _params_from_desc(desc)
                        }
                    )
                ))
            return [genai_types.Tool(function_declarations=decls)] if decls else None
        except Exception as e:
            log.warning("Tool defs: %s", str(e)[:60])
            return None

    # ── Cascade chiamate AI ────────────────────────────────────────────────────

    def _call_model(self, messages: list, **kwargs) -> dict:
        """
        Cascade: KEY1 → KEY2 → KEY3 → BrowserAI → Ollama → Ollama-2
        Ritorna dict: {type: text|tool_call|done, ...}
        """
        # ── Gemini API keys ──
        for env, model in self._gemini.items():
            self._rate_wait()
            try:
                self._last_call = time.time()
                response = model.generate_content(messages)

                # Controlla function call
                fc = self._extract_fc(response)
                if fc:
                    return {"type": "tool_call", "name": fc["name"], "params": fc["args"]}

                # Testo normale
                try:
                    text = response.text.strip()
                except Exception:
                    # finish_reason=10: FunctionCall invalido → ignora, continua
                    log.debug("finish_reason=10 su [%s], ignoro", env)
                    return {"type": "done", "summary": ""}

                return {"type": "text", "text": text} if text else {"type": "done", "summary": ""}

            except Exception as e:
                err = str(e)
                if any(x in err for x in ["429", "RESOURCE_EXHAUSTED", "quota"]):
                    m = re.search(r"(\d+)\s*s", err)
                    wait = min(65, int(m.group(1)) + 3) if m else 20
                    log.info("429 [%s] → next key, wait=%ds", env, wait)
                    print(f"   ⏳ Quota [{env[-1:]}]: attendo {wait}s…")
                    time.sleep(wait)
                    continue
                elif "500" in err or "internal" in err.lower():
                    log.warning("500 [%s], provo next key", env)
                    continue
                else:
                    log.error("Gemini [%s]: %s", env, err[:100])
                    break

        # ── BrowserAI fallback ──
        if self._browser_ai:
            try:
                print("   🌐 Gemini API esaurita → BrowserAI…")
                q = _messages_to_text(messages)
                result = self._browser_ai.ask(q)
                if result:
                    return {"type": "text", "text": result}
            except Exception as e:
                log.warning("BrowserAI: %s", str(e)[:60])

        # ── Ollama fallback ──
        for ollama_model in self._ollama_models:
            try:
                print(f"   🔄 Ollama {ollama_model}…")
                return self._call_ollama(messages, ollama_model)
            except Exception as e:
                log.warning("Ollama [%s]: %s", ollama_model, str(e)[:60])
                continue

        return {"type": "done", "summary": "Nessun modello disponibile"}

    def _call_ollama(self, messages: list, model: str) -> dict:
        import ollama as _ollama
        # Converti formato Gemini → Ollama
        ollama_msgs = []
        for m in messages:
            if isinstance(m, dict):
                role    = m.get("role", "user")
                parts   = m.get("parts", [])
                content = parts[0] if parts and isinstance(parts[0], str) else str(parts[0]) if parts else ""
                ollama_msgs.append({"role": role, "content": content})
            else:
                ollama_msgs.append({"role": "user", "content": str(m)})

        resp = _ollama.chat(
            model=model,
            messages=ollama_msgs,
            stream=False,
            options={"temperature": 0.3, "num_predict": 2000},
        )
        text = resp["message"]["content"].strip()
        return {"type": "text", "text": text} if text else {"type": "done", "summary": ""}

    # ── Loop principale ────────────────────────────────────────────────────────

    def run_task(self, user_input: str, **kwargs) -> str:
        """
        Loop ReAct: chiama modello → se tool → esegui → osserva → ripeti.
        Termina quando il modello risponde con testo senza tool call.
        """
        log.info("Task: %s", user_input[:80])
        self.memory.add_interaction("user", user_input)

        # Costruisci history
        ctx = self.memory.get_context()
        messages = []
        if ctx:
            messages.append({"role": "user",  "parts": [ctx]})
            messages.append({"role": "model", "parts": ["Contesto caricato."]})
        messages.append({"role": "user", "parts": [user_input]})

        final = ""

        for step in range(1, MAX_STEPS + 1):
            log.debug("Step %d/%d", step, MAX_STEPS)
            result = self._call_model(messages)
            rtype  = result.get("type", "done")

            if rtype == "text":
                text = result["text"]
                messages.append({"role": "model", "parts": [text]})
                final = text
                # Se testo non è pianificazione intermedia → finisci
                if not _is_planning(text):
                    break

            elif rtype == "tool_call":
                name   = result["name"]
                params = result.get("params") or {}
                log.info("Tool: %s %s", name, str(params)[:80])
                print(f"⚙ [{name}] {json.dumps(params, ensure_ascii=False)[:100]}")

                try:
                    tool_result = self.tools.execute(name, params)
                except Exception as e:
                    tool_result = f"Errore tool: {str(e)[:200]}"

                tres = str(tool_result)[:3000] if tool_result is not None else ""
                print(f"  → {tres[:120]}")
                log.debug("Tool result: %s", tres[:120])

                # Aggiungi function call + result alla conversazione
                messages.append({
                    "role": "model",
                    "parts": [genai_types.Part(
                        function_call=genai_types.FunctionCall(name=name, args=params)
                    )]
                })
                messages.append({
                    "role": "user",
                    "parts": [genai_types.Part(
                        function_response=genai_types.FunctionResponse(
                            name=name, response={"result": tres}
                        )
                    )]
                })

            elif rtype == "done":
                if result.get("summary"):
                    final = result["summary"]
                break

        self.memory.add_interaction("assistant", final)
        return final

    # ── Utility ───────────────────────────────────────────────────────────────

    def _extract_fc(self, response) -> dict | None:
        try:
            for cand in response.candidates:
                for part in cand.content.parts:
                    if hasattr(part, "function_call") and part.function_call:
                        fc = part.function_call
                        return {"name": fc.name, "args": dict(fc.args) if fc.args else {}}
        except Exception:
            pass
        return None

    def _rate_wait(self):
        elapsed = time.time() - self._last_call
        if elapsed < MIN_INTERVAL:
            wait = MIN_INTERVAL - elapsed
            log.debug("Rate wait %.1fs", wait)
            time.sleep(wait)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _params_from_desc(desc: str) -> list:
    """Estrae nomi parametri dalla descrizione es 'params: cmd, path'"""
    import re
    m = re.search(r"params?:\s*([^\)]+)", desc, re.IGNORECASE)
    if m:
        raw = m.group(1)
        return [p.strip().split("=")[0].strip()
                for p in raw.split(",") if p.strip() and p.strip() != "(nessuno)"]
    return ["input"]

def _messages_to_text(messages: list) -> str:
    parts = []
    for m in messages:
        role = m.get("role", "user")
        ps   = m.get("parts", [])
        for p in ps:
            if isinstance(p, str) and p.strip():
                parts.append(f"{role}: {p[:200]}")
    return "\n".join(parts[-4:])

def _is_planning(text: str) -> bool:
    lower = text.lower()
    return len(text) < 200 and any(x in lower for x in [
        "prima di tutto", "come prima cosa", "step 1",
        "procedo con", "inizierò con", "vediamo prima",
    ])
