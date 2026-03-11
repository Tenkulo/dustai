"""
DUST AI – Agent v2.0
Riscrittura completa. Fix critici:

1. Tool calling robusto:
   - Gemini: native function calling via genai SDK (niente JSON manuale)
   - Ollama: format="json" + schema enforcement + retry su parse fail
   - Parser multi-layer con fallback progressivo

2. Reflective loop pre/post ogni azione

3. Fallback chain: Gemini → Ollama tool-friendly → Ollama text+parse

4. SelfHeal su parse failure (non solo su errori di esecuzione)

5. Rate limiting corretto + retry automatico 429
"""
import json
import logging
import time
import re
import sys
import copy
from typing import Optional, Any

log = logging.getLogger("Agent")

# ─── Rate limiting ────────────────────────────────────────────────────────────
_MIN_INTERVAL = 13   # secondi tra chiamate Gemini (free tier = 5 rpm)


# ─── System prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Sei DUST AI, agente autonomo desktop su Windows 11 (Ryzen 5 5600G, 16 GB RAM).

## Regole Operative

### OBBLIGATORIO: usa sempre i tool reali
- NON descrivere mai azioni che "faresti" — eseguile con i tool
- NON scrivere "Ho creato..." senza aver chiamato il tool
- NON usare testo narrativo tipo "🔧 [SysExecTool] cmd=..."
- Ogni azione = una chiamata tool JSON strutturata

### Filesystem Windows
- Desktop reale: {desktop}
- Workdir: {base_path}
- Per operazioni file usa SEMPRE sys_exec con cmd /c
- DOPO ogni operazione VERIFICA con dir o type

### Pianificazione
1. Analizza il task (max 2 righe)
2. Esegui UN tool alla volta
3. Valuta risultato reale prima del prossimo step
4. Dichiara completato SOLO dopo verifica

### Formato tool call (UNICO formato accettato)
{"tool": "nome_tool", "params": {"param1": "valore1"}}

### Dichiarazione completamento
{"status": "done", "summary": "cosa è stato fatto"}

### Linguaggio: italiano sempre
"""

REFLECTION_PROMPT = """Analizza brevemente (2-3 righe) l'ultimo step:
- Cosa ha fatto il tool?
- Il risultato è quello atteso?
- Il prossimo step ha senso o devo correggere il piano?
Rispondi in italiano, conciso."""


# ─── Tool schema per Gemini native function calling ──────────────────────────

TOOL_SCHEMAS = [
    {
        "name": "sys_exec",
        "description": "Esegui comandi shell Windows (cmd /c) o Linux. Per qualsiasi operazione OS.",
        "parameters": {
            "type": "object",
            "properties": {
                "cmd": {"type": "string", "description": "Comando da eseguire"},
                "cwd": {"type": "string", "description": "Working directory (opzionale)"},
                "timeout": {"type": "integer", "description": "Timeout secondi (default 30)"},
            },
            "required": ["cmd"],
        },
    },
    {
        "name": "file_read",
        "description": "Leggi contenuto di un file",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "file_write",
        "description": "Scrivi o sovrascrivi un file",
        "parameters": {
            "type": "object",
            "properties": {
                "path":    {"type": "string"},
                "content": {"type": "string"},
                "mode":    {"type": "string", "description": "w=sovrascrivi, a=append"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "file_list",
        "description": "Lista file in una directory",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "web_search",
        "description": "Cerca informazioni sul web tramite Perplexity",
        "parameters": {
            "type": "object",
            "properties": {
                "query":       {"type": "string"},
                "max_results": {"type": "integer"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "browser_open",
        "description": "Apri un URL nel browser",
        "parameters": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    {
        "name": "screenshot",
        "description": "Cattura screenshot dello schermo per analisi visiva",
        "parameters": {
            "type": "object",
            "properties": {
                "region": {"type": "string", "description": "full|window|region (default full)"},
            },
        },
    },
    {
        "name": "code_run",
        "description": "Esegui codice Python",
        "parameters": {
            "type": "object",
            "properties": {
                "code":    {"type": "string"},
                "timeout": {"type": "integer"},
            },
            "required": ["code"],
        },
    },
    {
        "name": "app_launch",
        "description": "Avvia un'applicazione Windows",
        "parameters": {
            "type": "object",
            "properties": {"app": {"type": "string"}},
            "required": ["app"],
        },
    },
    {
        "name": "mouse_click",
        "description": "Click del mouse a coordinate x,y",
        "parameters": {
            "type": "object",
            "properties": {
                "x": {"type": "integer"},
                "y": {"type": "integer"},
            },
            "required": ["x", "y"],
        },
    },
    {
        "name": "keyboard_type",
        "description": "Digita testo con la tastiera",
        "parameters": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
]


# ─── Agent ────────────────────────────────────────────────────────────────────

class Agent:
    def __init__(self, config):
        self.config = config
        self.log    = logging.getLogger("Agent")

        from .memory import Memory
        from .tools.registry import ToolRegistry

        self.memory = Memory(config)
        self.tools  = ToolRegistry(config)

        self._gemini_model     = None
        self._gemini_fn_model  = None   # modello con function calling
        self._ollama_model     = None
        self._ollama_available = False
        self._last_call_time   = 0.0
        self._heal_engine      = None


        # HallucinationGuard v2
        self._hall_guard = None
        self._setup_gemini()
        self._setup_ollama()

    # ─── Setup ───────────────────────────────────────────────────────────────

    def _setup_gemini(self):
        api_key = self.config.get_api_key("google")
        if not api_key:
            self.log.warning("GOOGLE_API_KEY non trovata")
            return
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            model_name = self.config.get_model("primary").replace("gemini/", "")

            # Modello base per chat/reflection
            desktop   = str(self.config.get_desktop())
            base_path = str(self.config.get_base_path())
            sys_prompt = SYSTEM_PROMPT.replace("{desktop}", desktop).replace("{base_path}", base_path)

            self._gemini_model = genai.GenerativeModel(
                model_name=model_name,
                system_instruction=sys_prompt,
            )

            # Modello con function calling nativo
            tools_for_gemini = [
                genai.protos.Tool(function_declarations=[
                    genai.protos.FunctionDeclaration(
                        name=t["name"],
                        description=t["description"],
                        parameters=genai.protos.Schema(
                            type=genai.protos.Type.OBJECT,
                            properties={
                                k: genai.protos.Schema(
                                    type=genai.protos.Type.STRING
                                    if v.get("type") == "string"
                                    else genai.protos.Type.INTEGER
                                    if v.get("type") == "integer"
                                    else genai.protos.Type.STRING
                                )
                                for k, v in t["parameters"].get("properties", {}).items()
                            },
                            required=t["parameters"].get("required", []),
                        ),
                    )
                    for t in TOOL_SCHEMAS
                ])
            ]

            self._gemini_fn_model = genai.GenerativeModel(
                model_name=model_name,
                system_instruction=sys_prompt,
                tools=tools_for_gemini,
            )
            self.log.info("Gemini pronto: " + model_name)
        except Exception as e:
            self.log.error("Gemini setup fallito: " + str(e))
            self._gemini_model    = None
            self._gemini_fn_model = None

    def _setup_ollama(self):
        try:
            import ollama
            resp = ollama.list()
            if hasattr(resp, "models"):
                names = [m.model for m in resp.models if hasattr(m, "model")]
            elif isinstance(resp, dict):
                names = [m.get("name", m.get("model", "")) for m in resp.get("models", [])]
            else:
                names = []

            preferred = self.config.get("ollama_tool_models", [])
            selected = None
            for pref in preferred:
                for n in names:
                    if pref.split(":")[0] in n:
                        selected = n
                        break
                if selected:
                    break
            if not selected and names:
                selected = names[0]

            self._ollama_model     = selected
            self._ollama_available = bool(selected)

            if selected:
                # Usa OllamaCaller con schema enforcement e two-phase thinking
                from .ollama_caller import OllamaCaller
                self._ollama_caller = OllamaCaller(model=selected, config=self.config)
                self.log.info("Ollama pronto: " + selected + " (OllamaCaller v2)")
            else:
                self._ollama_caller = None
        except Exception as e:
            self._ollama_available = False
            self._ollama_caller    = None
            self.log.warning("Ollama setup: " + str(e))

    def _get_heal_engine(self):
        if self._heal_engine is None:
            try:
                from .self_heal import SelfHealEngine
                self._heal_engine = SelfHealEngine(
                    config=self.config,
                    gemini_model=self._gemini_model,
                )
            except Exception as e:
                self.log.warning("SelfHealEngine non disponibile: " + str(e))
        return self._heal_engine

    # ─── Rate limiting ────────────────────────────────────────────────────────

    def _rate_limit_wait(self):
        min_interval = self.config.get_rate_limit("min_interval_s") or _MIN_INTERVAL
        elapsed = time.time() - self._last_call_time
        if elapsed < min_interval:
            wait = min_interval - elapsed
            self.log.info("Rate limit wait: " + str(round(wait, 1)) + "s")
            print("   ⏳ Rate limit: " + str(round(wait, 1)) + "s...")
            time.sleep(wait)

    # ─── Chiamate modello ────────────────────────────────────────────────────

    def _call_gemini_fn(self, messages: list) -> dict:
        """
        Chiama Gemini con function calling nativo.
        Ritorna {"type": "tool_call", "tool": "...", "params": {...}}
             o  {"type": "text", "text": "..."}
        """
        max_retries = self.config.get_rate_limit("max_retries") or 4

        for attempt in range(max_retries):
            self._rate_limit_wait()
            try:
                self._last_call_time = time.time()
                response = self._gemini_fn_model.generate_content(messages)

                # Cerca function call nativa
                for candidate in response.candidates:
                    for part in candidate.content.parts:
                        if hasattr(part, "function_call") and part.function_call:
                            fc = part.function_call
                            params = {}
                            if hasattr(fc, "args"):
                                for k, v in fc.args.items():
                                    params[k] = v
                            return {"type": "tool_call", "tool": fc.name, "params": params}

                # Nessuna function call → testo
                try:
                    txt = response.text.strip()
                except Exception:
                    txt = ""
                if not txt:
                    return {"type": "done", "summary": "task completato"}
                return {"type": "text", "text": txt}

            except Exception as e:
                err = str(e)
                if "429" in err or "RESOURCE_EXHAUSTED" in err:
                    wait_match = re.search(r"(\d+)[\s]*s", err)
                    wait = min(65, int(wait_match.group(1)) + 5) if wait_match else 65
                    if attempt < max_retries - 1:
                        print("   ⏳ 429 — riprovo in " + str(wait) + "s...")
                        time.sleep(wait)
                        continue
                    raise RuntimeError("SWITCH_TO_OLLAMA")
                raise

        raise RuntimeError("Gemini retry esauriti")

    def _call_gemini_text(self, messages: list) -> str:
        """Chiamata Gemini semplice (per reflection, chat)."""
        max_retries = self.config.get_rate_limit("max_retries") or 4
        for attempt in range(max_retries):
            self._rate_limit_wait()
            try:
                self._last_call_time = time.time()
                return self._gemini_model.generate_content(messages).text.strip()
            except Exception as e:
                err = str(e)
                if ("429" in err or "RESOURCE_EXHAUSTED" in err) and attempt < max_retries - 1:
                    time.sleep(65)
                    continue
                raise
        raise RuntimeError("Gemini text retry esauriti")

    def _call_ollama_structured(self, messages: list, task_hint: str = "") -> dict:
        """
        Chiama Ollama con format=json e schema enforcement.
        Ritorna {"type": "tool_call", ...} o {"type": "text", ...}
        """
        if not self._ollama_available:
            raise RuntimeError("Ollama non disponibile")

        tool_names = ", ".join(t["name"] for t in TOOL_SCHEMAS)
        schema_example = '{"tool": "sys_exec", "params": {"cmd": "dir C:\\\\"}}'
        done_example   = '{"status": "done", "summary": "operazione completata"}'

        system_msg = (
            "Sei DUST AI. Rispondi SEMPRE con JSON puro, mai testo narrativo.\n"
            "Tool disponibili: " + tool_names + "\n"
            "Per chiamare un tool: " + schema_example + "\n"
            "Per dichiarare completamento: " + done_example + "\n"
            "Nient'altro. Solo JSON valido."
        )

        try:
            import ollama
            ollama_msgs = [{"role": "system", "content": system_msg}]
            for m in messages:
                role    = "assistant" if m.get("role") == "model" else m.get("role", "user")
                parts   = m.get("parts", [""])
                content = parts[0] if isinstance(parts, list) else str(parts)
                ollama_msgs.append({"role": role, "content": content})

            resp = ollama.chat(
                model=self._ollama_model,
                messages=ollama_msgs,
                format="json",
                options={"temperature": 0.1},
                stream=False,
            )
            raw = resp["message"]["content"].strip()
            return self._parse_model_output(raw)

        except Exception as e:
            raise RuntimeError("Ollama call fallita: " + str(e))


    def _get_hall_guard(self):
        """Lazy init HallucinationGuard."""
        if self._hall_guard is None:
            try:
                from .hallucination_guard import HallucinationGuard
                self._hall_guard = HallucinationGuard(
                    self.config,
                    gateway=self._gateway if hasattr(self, "_gateway") else None
                )
                self.log.info("HallucinationGuard v2 pronto")
            except Exception as e:
                self.log.warning("HallucinationGuard N/D: " + str(e))
                self._hall_guard = False
        return self._hall_guard if self._hall_guard else None

    def _call_model(self, messages: list, task_hint: str = "") -> dict:
        """
        Chiama il modello migliore disponibile.
        Ritorna sempre un dict: {"type": "tool_call"|"text"|"done"|"parse_error", ...}

        Pipeline:
          1. Gemini con function calling nativo (zero parse fail)
          2. OllamaCaller (two-phase + schema enforcement + instructor + retry)
          3. SelfHeal su parse_error
        """
        # 1. Gemini con function calling nativo
        if self._gemini_fn_model:
            try:
                return self._call_gemini_fn(messages)
            except RuntimeError as e:
                if "SWITCH_TO_OLLAMA" in str(e):
                    self.log.warning("Gemini 429 → switch Ollama")
                    print("   🔄 Gemini esaurito → Ollama locale")
                else:
                    raise

        # 2. OllamaCaller con schema enforcement
        if self._ollama_available and self._ollama_caller:
            result = self._ollama_caller.call(messages, task_hint)

            # Se parse fail → SelfHeal immediato (non "Continua")
            if result.get("type") == "parse_error":
                raw = result.get("raw", "")
                self.log.warning("Ollama parse_error → SelfHeal.heal_parse_fail()")
                print("   🔧 Parse fail rilevato → SelfHeal attivo")
                healer = self._get_heal_engine()
                if healer:
                    healed = healer.heal_parse_fail(raw, messages)
                    if healed and healed.get("tool"):
                        return {"type": "tool_call", "tool": healed["tool"], "params": healed.get("params", {})}
                    if healed and healed.get("status") == "done":
                        return {"type": "done", "summary": healed.get("summary", "")}
                # SelfHeal fallito → testo esplicito invece di loop
                return {"type": "text", "text": "[parse_error] Impossibile estrarre tool call. Raw: " + raw[:200]}


                # HallucinationGuard: processa risposta prima di usarla
                guard = self._get_hall_guard()
                if guard and isinstance(result, dict) and result.get("type") == "text":
                    _text = result.get("text", "")
                    if _text and len(_text) > 30:
                        _prompt_ctx = messages[-1].get("parts", [""])[0] if messages else ""
                        _guarded = guard.process(str(_prompt_ctx), _text, level="standard")
                        if _guarded.get("corrected"):
                            self.log.info("HallucinationGuard: risposta corretta (conf=%d)", _guarded.get("confidence", 0))
                            result["text"] = _guarded["text"]
                            result["_hall_confidence"] = _guarded["confidence"]
            return result

        raise RuntimeError("Nessun modello disponibile. Configura GOOGLE_API_KEY o installa Ollama.")

    # ─── Parser multi-layer ──────────────────────────────────────────────────

    def _parse_model_output(self, text: str) -> dict:
        """
        Parser robusto con 4 livelli di fallback.
        Ritorna: {"type": "tool_call", "tool": str, "params": dict}
              o: {"type": "done", "summary": str}
              o: {"type": "text", "text": str}
        """
        if not text:
            return {"type": "text", "text": ""}

        # Livello 1: JSON diretto
        clean = text.strip()
        for fence in ["```json", "```"]:
            if clean.startswith(fence):
                clean = clean[len(fence):]
                if clean.endswith("```"):
                    clean = clean[:-3]
                clean = clean.strip()

        try:
            data = json.loads(clean)
            return self._classify_json(data)
        except json.JSONDecodeError:
            pass

        # Livello 2: cerca JSON nel testo (primo blocco {...})
        for match in re.finditer(r'\{[^{}]*\}|\{(?:[^{}]|\{[^{}]*\})*\}', text, re.DOTALL):
            try:
                data = json.loads(match.group(0))
                result = self._classify_json(data)
                if result["type"] in ("tool_call", "done"):
                    return result
            except json.JSONDecodeError:
                continue

        # Livello 3: estrazione da testo narrativo Ollama
        # Detecta pattern tipo: "sys_exec(cmd='dir C:\\')" o "[sys_exec] cmd=dir C:\"
        narrative = self._extract_from_narrative(text)
        if narrative:
            return narrative

        # Livello 4: testo puro
        return {"type": "text", "text": text}

    def _classify_json(self, data: dict) -> dict:
        """Classifica un JSON come tool_call, done o text."""
        # Tool call esplicita
        if "tool" in data and isinstance(data.get("tool"), str):
            return {
                "type":   "tool_call",
                "tool":   data["tool"],
                "params": data.get("params", data.get("parameters", {})),
            }

        # Done/completato
        if data.get("status") in ("done", "completed", "completato"):
            return {"type": "done", "summary": data.get("summary", data.get("message", ""))}

        if any(k in data for k in ("completato", "fatto", "terminato")):
            return {"type": "done", "summary": str(data)}

        # Qualsiasi dict con una chiave che è un nome tool
        tool_names = {t["name"] for t in TOOL_SCHEMAS}
        for key in data:
            if key in tool_names:
                return {
                    "type":   "tool_call",
                    "tool":   key,
                    "params": data[key] if isinstance(data[key], dict) else {"cmd": str(data[key])},
                }

        return {"type": "text", "text": json.dumps(data)}

    def _extract_from_narrative(self, text: str) -> Optional[dict]:
        """
        Estrae tool call da output narrativo Ollama.
        Gestisce pattern come:
          [sys_exec] cmd=dir C:\
          sys_exec(cmd="dir C:\\")
          🔧 sys_exec: dir C:\
        """
        tool_names = {t["name"] for t in TOOL_SCHEMAS}

        # Pattern [tool_name] param=value
        m = re.search(r'\[(\w+)\]\s*(\w+)=(.+?)(?:\n|$)', text)
        if m and m.group(1) in tool_names:
            return {
                "type":   "tool_call",
                "tool":   m.group(1),
                "params": {m.group(2): m.group(3).strip()},
            }

        # Pattern tool_name(param="value")
        m = re.search(r'(\w+)\(([^)]+)\)', text)
        if m and m.group(1) in tool_names:
            raw_params = m.group(2)
            params = {}
            for pm in re.finditer(r'(\w+)\s*=\s*["\']?([^,"\']+)["\']?', raw_params):
                params[pm.group(1)] = pm.group(2).strip()
            if params:
                return {"type": "tool_call", "tool": m.group(1), "params": params}

        # Pattern "🔧 tool_name: value" o "tool_name: value"
        m = re.search(r'(?:🔧\s+)?(\w+):\s+(.+?)(?:\n|$)', text)
        if m and m.group(1) in tool_names:
            tool = m.group(1)
            # Cerca il primo parametro richiesto per questo tool
            schema = next((t for t in TOOL_SCHEMAS if t["name"] == tool), None)
            if schema:
                required = schema["parameters"].get("required", [])
                if required:
                    return {
                        "type":   "tool_call",
                        "tool":   tool,
                        "params": {required[0]: m.group(2).strip()},
                    }

        return None

    # ─── Reflective loop ─────────────────────────────────────────────────────

    def _reflect(self, tool_name: str, params: dict, result: str, messages: list) -> str:
        """
        Micro-reflection post-tool: chiede al modello di valutare il risultato.
        Usa il modello base (non function calling) per risparmio token.
        """
        if not self.config.get_agent_cfg("reflective_loop", True):
            return ""
        try:
            reflection_msgs = messages + [{
                "role": "user",
                "parts": [
                    "Tool eseguito: " + tool_name + "\n"
                    "Params: " + json.dumps(params) + "\n"
                    "Risultato: " + result[:500] + "\n\n"
                    + REFLECTION_PROMPT
                ]
            }]
            if self._gemini_model:
                return self._call_gemini_text(reflection_msgs)
            return ""
        except Exception:
            return ""

    # ─── Task execution ──────────────────────────────────────────────────────

    def run_task(self, task: str, max_steps: int = None) -> str:
        """
        Loop agente autonomo.
        1. Prepara contesto
        2. Chiama modello (Gemini FN → Ollama JSON → fallback)
        3. Esegui tool reale
        4. Reflection
        5. Ripeti fino a completamento o max_steps
        """
        max_steps = max_steps or self.config.get_agent_cfg("max_steps") or 25
        self.log.info("Task: " + task[:80])

        context  = self.memory.get_context()
        desktop  = str(self.config.get_desktop())
        base     = str(self.config.get_base_path())

        # Costruisci messaggi iniziali
        messages = []
        if context:
            messages.append({"role": "user",  "parts": ["Contesto sessione:\n" + context]})
            messages.append({"role": "model", "parts": ["Contesto caricato."]})

        # Aggiungi reminder percorsi
        reminder = (
            "[PERCORSI: Desktop=" + desktop + " | Base=" + base + "]\n" + task
        )
        messages.append({"role": "user", "parts": [reminder]})

        step           = 0
        final_response = ""
        loop_guard     = {}       # risposta → count per rilevare loop
        tool_fail_count: dict = {}  # tool → count fail consecutivi

        while step < max_steps:
            step += 1
            self.log.info("Step " + str(step) + "/" + str(max_steps))

            # ── Chiama modello ─────────────────────────────────────────────
            try:
                result = self._call_model(messages, task_hint=task)
            except Exception as e:
                return "❌ Modello non disponibile: " + str(e)

            rtype = result.get("type", "text")

            # ── Done ──────────────────────────────────────────────────────
            if rtype == "done":
                final_response = result.get("summary", "Task completato.")
                self.log.info("Task completato al step " + str(step))
                break

            # ── Text (non è un tool call) ─────────────────────────────────
            if rtype == "text":
                text = result.get("text", "")

                # Controlla keyword di completamento nel testo
                if any(kw in text.lower() for kw in [
                    "completato", "fatto", "terminato", "✅", "goal raggiunto", "ho finito"
                ]):
                    final_response = text
                    break

                # Loop guard
                text_key = text[:80]
                loop_guard[text_key] = loop_guard.get(text_key, 0) + 1
                if loop_guard[text_key] >= 3:
                    self.log.warning("Loop rilevato — interrompo")
                    final_response = "⚠️ Loop rilevato. Ultimo output: " + text[:200]
                    break

                messages.append({"role": "model",  "parts": [text]})
                messages.append({"role": "user",   "parts": ["Continua con il prossimo step o dichiara completato se il task è terminato."]})
                final_response = text
                continue

            # ── Tool call ────────────────────────────────────────────────
            tool_name = result.get("tool", "")
            params    = result.get("params", {})

            if not tool_name:
                messages.append({"role": "user", "parts": ["Errore: tool call senza nome. Riprova."]})
                continue

            print("\n🔧 [" + tool_name + "] " + json.dumps(params, ensure_ascii=False)[:200])
            self.log.info("Tool: " + tool_name + " | " + str(params)[:100])

            # ── Esecuzione tool con self-heal ─────────────────────────────
            t0          = time.time()
            tool_result = self._execute_with_heal(tool_name, params, task, messages)
            elapsed_ms  = round((time.time() - t0) * 1000)

            result_str = str(tool_result)
            print("   → " + result_str[:300])
            self.log.info("Tool result (" + str(elapsed_ms) + "ms): " + result_str[:150])

            # Fail counter
            is_error = result_str.startswith("❌")
            if is_error:
                tool_fail_count[tool_name] = tool_fail_count.get(tool_name, 0) + 1
                if tool_fail_count[tool_name] >= 4:
                    messages.append({
                        "role": "user",
                        "parts": [
                            "ATTENZIONE: il tool '" + tool_name + "' ha fallito " +
                            str(tool_fail_count[tool_name]) + " volte. "
                            "Usa un approccio diverso o dichiara il task non completabile."
                        ]
                    })
                    continue
            else:
                tool_fail_count[tool_name] = 0

            # Aggiungi tool call e risultato ai messaggi
            messages.append({
                "role": "model",
                "parts": [json.dumps({"tool": tool_name, "params": params})]
            })

            # ── Reflection ────────────────────────────────────────────────
            reflection = ""
            if not is_error and step % 3 == 0:
                reflection = self._reflect(tool_name, params, result_str, messages)
                if reflection:
                    print("   💭 " + reflection[:100])

            feedback = "Risultato '" + tool_name + "':\n" + result_str
            if reflection:
                feedback += "\n\nAnalisi step:\n" + reflection
            feedback += "\n\nContinua o dichiara completato se il goal è raggiunto."

            messages.append({"role": "user", "parts": [feedback]})

        # Salva in memoria
        self.memory.add(task, final_response or "Eseguito.")
        return final_response or "Task eseguito."

    # ─── Esecuzione tool con self-heal ────────────────────────────────────────

    def _execute_with_heal(self, tool_name: str, params: dict,
                           task: str, messages: list, attempt: int = 0) -> Any:
        """Esegue un tool. Su errore attiva SelfHealEngine."""
        result = self.tools.execute(tool_name, params)
        result_str = str(result)

        if result_str.startswith("❌") and attempt < 3:
            healer = self._get_heal_engine()
            if healer:
                heal = healer.heal(
                    error=result_str,
                    context={
                        "operation": tool_name,
                        "params":    params,
                        "task":      task,
                        "attempt":   attempt,
                    }
                )
                if not heal.get("give_up") and heal.get("retry_params"):
                    new_params = heal["retry_params"]
                    print("   🔧 SelfHeal: " + heal.get("message", "")[:100])
                    self.log.info("SelfHeal retry: " + str(new_params)[:100])
                    return self._execute_with_heal(tool_name, new_params, task, messages, attempt + 1)

        return result

    # ─── Chat semplice ────────────────────────────────────────────────────────

    def chat(self, message: str) -> str:
        """Chat senza loop agente — risposta singola."""
        try:
            msgs = [{"role": "user", "parts": [message]}]
            result = self._call_model(msgs)
            if result["type"] == "text":
                return result["text"]
            if result["type"] == "done":
                return result.get("summary", "")
            # È un tool call in chat mode — esegui e ritorna risultato
            tr = self.tools.execute(result["tool"], result.get("params", {}))
            return str(tr)
        except Exception as e:
            return "❌ " + str(e)
