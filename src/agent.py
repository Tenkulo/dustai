"""
DUST AI – Core Agent v1.4
Integra SelfHealEngine: su ogni errore cerca soluzione web, genera patch,
hot-ricarica il modulo e riprova autonomamente. Max 3 tentativi per errore.
"""
import json
import logging
import time
import re
from typing import Optional

import google.generativeai as genai

from .tools.registry import ToolRegistry
from .memory import Memory
from .self_heal import SelfHealEngine, classify_error

MIN_CALL_INTERVAL = 13

STALL_KEYWORDS = [
    "in attesa", "sto aspettando", "sono in attesa", "aspetto il risultato",
    "waiting for", "finché non mi fornisci", "non posso proseguire senza",
    "non posso continuare senza", "senza questo output",
]

SYSTEM_PROMPT_TEMPLATE = """Sei DUST AI, un agente autonomo su Windows 11 (Ryzen 5 5600G, 16 GB RAM).

## PERCORSI REALI — usa QUESTI, non ri-scoprirli mai via shell
- Desktop:   {desktop}
- Workdir:   {workdir}
- Downloads: {downloads}
- Alternativo Desktop: {desktop_alt}

## Regole

### Filesystem
- Crea cartella:  {{"tool":"sys_exec","params":{{"command":"cmd /c mkdir \\"{desktop}\\\\nomecartella\\""}}}}
- Crea file:      {{"tool":"sys_exec","params":{{"command":"cmd /c echo testo > \\"{desktop}\\\\cartella\\\\file.txt\\""}}}}
- Verifica:       {{"tool":"sys_exec","params":{{"command":"cmd /c dir \\"{desktop}\\\\cartella\\""}}}}
- Se [stderr] o [exit code:1]: NON ignorare, prova path alternativo {desktop_alt}

### Comportamento
- Tool call: SOLO JSON  {{"tool":"nome","params":{{...}}}}
- Risposta finale: ✅ successo o ❌ fallito con causa
- Rispondi SEMPRE in italiano
- NON ripetere "sto aspettando" — ogni risposta deve avere un tool call o una conclusione
"""


class Agent:
    def __init__(self, config):
        self.config = config
        self.log = logging.getLogger("Agent")
        self.memory = Memory(config)
        self.tools = ToolRegistry(config)
        self._model = None
        self._ollama_available = False
        self._last_call_time = 0
        self._system_prompt = self._build_system_prompt()
        self._setup_gemini()
        self._setup_ollama()
        self._healer: Optional[SelfHealEngine] = None  # lazy init dopo setup

    # ─── System prompt con path iniettati ────────────────────────────────────

    def _build_system_prompt(self) -> str:
        import os, platform
        desktop  = str(self.config.get_desktop())
        workdir  = str(self.config.get_workdir())
        downloads = str(self.config.get_downloads())
        desktop_alt = (
            f"{os.environ.get('USERPROFILE','C:\\Users\\User')}\\Desktop"
            if platform.system() == "Windows" else desktop
        )
        return SYSTEM_PROMPT_TEMPLATE.format(
            desktop=desktop, workdir=workdir,
            downloads=downloads, desktop_alt=desktop_alt,
        )

    # ─── Setup modelli ────────────────────────────────────────────────────────

    def _setup_gemini(self):
        api_key = self.config.get_api_key("google")
        if not api_key:
            self.log.warning("GOOGLE_API_KEY non trovata.")
            return
        genai.configure(api_key=api_key)
        model_name = self.config.get_model("primary").replace("gemini/", "")
        self._model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=self._system_prompt,
        )
        self.log.info(f"Gemini: {model_name}")

    def _setup_ollama(self):
        try:
            import ollama
            models = ollama.list()
            names = [m.model for m in models.models] if hasattr(models, "models") else []
            self._ollama_available = bool(names)
            self._ollama_model = next(
                (n for n in names if "qwen3" in n),
                next((n for n in names if "mistral" in n or "llama" in n), names[0] if names else None),
            )
            if self._ollama_available:
                self.log.info(f"Ollama: {self._ollama_model}")
        except Exception:
            self._ollama_model = None

    def _get_healer(self) -> SelfHealEngine:
        """Inizializza SelfHealEngine la prima volta che serve."""
        if self._healer is None and self._model:
            self._healer = SelfHealEngine(
                config=self.config,
                gemini_model=self._model,
                web_search_fn=lambda params: self.tools.execute("web_search", params),
            )
        return self._healer

    # ─── Chiamate modello ─────────────────────────────────────────────────────

    def _rate_limit_wait(self):
        elapsed = time.time() - self._last_call_time
        if elapsed < MIN_CALL_INTERVAL:
            wait = MIN_CALL_INTERVAL - elapsed
            self.log.info(f"Rate limit: attendo {wait:.1f}s")
            print(f"   ⏳ Rate limit: attendo {wait:.1f}s...")
            time.sleep(wait)

    def _call_gemini(self, messages: list, max_retry: int = 4) -> str:
        for attempt in range(max_retry):
            self._rate_limit_wait()
            try:
                self._last_call_time = time.time()
                return self._model.generate_content(messages).text.strip()
            except Exception as e:
                err = str(e)
                if "429" in err or "RESOURCE_EXHAUSTED" in err:
                    m = re.search(r"retry.*?(\d+)[\.\d]*s", err, re.IGNORECASE)
                    wait = int(m.group(1)) + 3 if m else 65
                    if attempt < max_retry - 1:
                        print(f"   ⏳ 429 – attendo {wait}s ({attempt+1}/{max_retry})...")
                        time.sleep(wait)
                        continue
                    raise RuntimeError("SWITCH_TO_OLLAMA")
                raise
        raise RuntimeError("Retry Gemini esauriti")

    def _call_ollama(self, messages: list) -> str:
        try:
            import ollama
            msgs = []
            for m in messages:
                role = "assistant" if m.get("role") == "model" else m.get("role", "user")
                parts = m.get("parts", [""])
                content = parts[0] if isinstance(parts, list) else parts
                msgs.append({"role": role, "content": content})
            resp = ollama.chat(model=self._ollama_model, messages=msgs)
            return resp["message"]["content"].strip()
        except Exception as e:
            return f"❌ Errore Ollama: {e}"

    def _call_model(self, messages: list) -> str:
        if self._model:
            try:
                return self._call_gemini(messages)
            except RuntimeError as e:
                if "SWITCH_TO_OLLAMA" in str(e) and self._ollama_available:
                    print("   🔄 Gemini esaurito → switch Ollama")
                    return self._call_ollama(messages)
                raise
        elif self._ollama_available:
            return self._call_ollama(messages)
        raise RuntimeError("Nessun modello disponibile.")

    # ─── Esecuzione tool con self-healing ────────────────────────────────────

    def _execute_with_healing(self, name: str, params: dict,
                               task: str, max_heal_attempts: int = 3) -> str:
        """
        Esegue un tool. Se fallisce, attiva SelfHealEngine che:
        - cerca soluzione web
        - genera patch
        - riprova con params corretti o codice patchato
        Max max_heal_attempts tentativi di healing.
        """
        for attempt in range(max_heal_attempts + 1):
            result = self.tools.execute(name, params)
            result_str = str(result)

            if not self._is_tool_error(result_str):
                return result_str  # successo

            if attempt >= max_heal_attempts:
                return f"{result_str}\n[SelfHeal: esauriti {max_heal_attempts} tentativi]"

            # Attiva healing
            healer = self._get_healer()
            if not healer:
                return result_str  # no healer disponibile

            print(f"\n🚑 [SelfHeal] Tentativo {attempt+1}/{max_heal_attempts}...")
            heal_result = healer.heal(
                error=result_str,
                context={
                    "operation": f"{name}({params})",
                    "params": params,
                    "task": task,
                    "file": self._error_to_file(result_str, name),
                }
            )

            print(f"   {heal_result['message']}")

            if heal_result["give_up"]:
                return f"{result_str}\n{heal_result['message']}"

            if heal_result["retry_params"]:
                params = heal_result["retry_params"]
                print(f"   🔁 Riprovo con params: {params}")
            # Se patch_applied=True, il modulo è già stato ricaricato → riprova

        return result_str

    def _error_to_file(self, error: str, tool_name: str) -> str:
        """Mappa tool name → file sorgente per il patching."""
        mapping = {
            "sys_exec": "src/tools/sys_exec.py",
            "file_read": "src/tools/file_ops.py",
            "file_write": "src/tools/file_ops.py",
            "web_search": "src/tools/web_search.py",
            "code_run": "src/tools/code_runner.py",
        }
        return mapping.get(tool_name, "")

    # ─── Loop principale ──────────────────────────────────────────────────────

    def run_task(self, task: str, max_steps: int = None) -> str:
        max_steps = max_steps or self.config.get("agent", {}).get("max_steps", 20)
        self.log.info(f"Task: {task[:80]}")

        desktop = str(self.config.get_desktop())
        task_msg = f"{task}\n\n[REMINDER: Desktop={desktop}]"

        context = self.memory.get_context()
        messages = []
        if context:
            messages.append({"role": "user",  "parts": [f"Contesto:\n{context}"]})
            messages.append({"role": "model", "parts": ["Ok."]})
        messages.append({"role": "user", "parts": [task_msg]})

        step = 0
        final_response = ""
        stall_count = 0
        last_responses = []

        while step < max_steps:
            step += 1
            self.log.info(f"Step {step}/{max_steps}")

            try:
                text = self._call_model(messages)
            except Exception as e:
                return f"❌ Errore modello: {e}"

            messages.append({"role": "model", "parts": [text]})
            text_lower = text.lower()

            # Stall detection
            if any(kw in text_lower for kw in STALL_KEYWORDS):
                stall_count += 1
                if stall_count >= 2:
                    return (
                        "❌ Task interrotto: agente in stallo.\n"
                        "Il modello attendeva un risultato che non è arrivato.\n"
                        "Riprova con un task più semplice."
                    )
            else:
                stall_count = 0

            # Loop detection
            last_responses.append(text[:200])
            if len(last_responses) > 3:
                last_responses.pop(0)
            if len(last_responses) >= 2 and last_responses[-1] == last_responses[-2]:
                return "❌ Task interrotto: risposta identica ripetuta (loop rilevato)."

            # Tool call
            tool_call = self._parse_tool_call(text)

            if tool_call:
                stall_count = 0
                name   = tool_call.get("tool")
                params = tool_call.get("params", {})
                print(f"\n🔧 [{name}] {params}")

                # Esegui con self-healing automatico
                result_str = self._execute_with_healing(name, params, task)
                print(f"   → {result_str[:300]}")

                messages.append({"role": "user", "parts": [
                    f"Risultato '{name}':\n{result_str}\n\nContinua o dichiara completato."
                ]})

            else:
                final_response = text
                if any(kw in text_lower for kw in ["completato","fatto","terminato","✅","❌","goal raggiunto"]):
                    break
                if step >= max_steps:
                    break
                messages.append({"role": "user", "parts": [
                    "Continua oppure dichiara ✅ completato o ❌ fallito con la causa."
                ]})

        if not final_response:
            final_response = (
                f"❌ Task non completato: raggiunto il limite di {max_steps} step.\n"
                "Aumenta max_steps in config.json o semplifica il task."
            )

        self.memory.add(task, final_response)
        return final_response

    # ─── Helpers ─────────────────────────────────────────────────────────────

    def _is_tool_error(self, result: str) -> bool:
        return any(s in result.lower() for s in [
            "[stderr]", "[exit code: 1]", "[exit code: 2]",
            "accesso negato", "access is denied",
            "impossibile trovare", "cannot find",
            "the system cannot find", "sintassi del nome",
            "errore di sintassi",
        ])

    def _parse_tool_call(self, text: str) -> Optional[dict]:
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if len(lines) > 2 else text
        try:
            data = json.loads(text)
            if "tool" in data:
                return data
        except json.JSONDecodeError:
            pass
        for match in re.findall(r'\{[^{}]*"tool"[^{}]*\}', text, re.DOTALL):
            try:
                data = json.loads(match)
                if "tool" in data:
                    return data
            except json.JSONDecodeError:
                continue
        return None

    def chat(self, message: str) -> str:
        try:
            return self._call_model([{"role": "user", "parts": [message]}])
        except Exception as e:
            return f"❌ {e}"
