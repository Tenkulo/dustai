"""
DUST AI – Core Agent v1.2
Novità rispetto a v1.1:
- Rilevamento loop/stallo: se il modello ripete "in attesa" o testo identico → abort con messaggio chiaro
- Rilevamento errori tool: se sys_exec restituisce stderr/exit code !=0 → segnala subito all'utente
- Non dichiara mai "completato" su risultati vuoti o in errore
- Abort esplicito con causa quando supera max_steps o entra in stallo
"""
import json
import logging
import time
import re
from typing import Optional

import google.generativeai as genai

from .tools.registry import ToolRegistry
from .memory import Memory


SYSTEM_PROMPT = """Sei DUST AI, un agente autonomo avanzato su Windows 11 (Ryzen 5 5600G, 16 GB RAM).

## Regole Operative Fondamentali

### Filesystem Windows
- Usa SEMPRE sys_exec con `cmd /c` per operazioni su filesystem
- Per verificare file/cartelle usa: cmd /c dir percorso (SENZA virgolette doppie attorno al percorso)
- DOPO ogni operazione file, VERIFICA sempre con cmd /c dir o cmd /c type
- Se un tool restituisce errore (stderr / exit code 1), NON ignorarlo: segnala l'errore e fermati

### Regole di comportamento
- Se non riesci a completare un task, dì esattamente PERCHÉ e fermati
- Non entrare mai in loop di attesa: se hai già inviato un comando, NON ripetere "sto aspettando il risultato"
- Se il risultato di un tool è vuoto o in errore, prova UN'alternativa, poi se fallisce segnala l'errore
- Dichiara completato SOLO dopo aver verificato il risultato reale

### Formato risposte
- Tool call: rispondi SOLO con JSON  {"tool": "nome", "params": {...}}
- Risposta finale: testo libero in italiano, inizia con ✅ se successo o ❌ se fallito con la causa

### Tool disponibili
sys_exec, file_read, file_write, file_list, file_exists, file_delete,
browser_open, browser_click, browser_type, browser_get_text,
mouse_move, mouse_click, keyboard_type, keyboard_hotkey,
app_launch, app_focus, app_list, web_search, code_run
"""

MIN_CALL_INTERVAL = 13  # secondi tra chiamate (free tier: 5 req/min)

# Parole chiave che indicano stallo del modello
STALL_KEYWORDS = [
    "in attesa", "sto aspettando", "sono in attesa", "aspetto il risultato",
    "waiting for", "finché non mi fornisci", "non posso proseguire senza",
    "non posso continuare senza", "senza questo output",
]


class Agent:
    def __init__(self, config):
        self.config = config
        self.log = logging.getLogger("Agent")
        self.memory = Memory(config)
        self.tools = ToolRegistry(config)
        self._model = None
        self._ollama_available = False
        self._last_call_time = 0
        self._setup_gemini()
        self._setup_ollama()

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
            system_instruction=SYSTEM_PROMPT,
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

    # ─── Rate limit + chiamate ────────────────────────────────────────────────

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
                response = self._model.generate_content(messages)
                return response.text.strip()
            except Exception as e:
                error_msg = str(e)
                if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                    m = re.search(r"retry.*?(\d+)[\.\d]*s", error_msg, re.IGNORECASE)
                    wait = int(m.group(1)) + 3 if m else 65
                    if attempt < max_retry - 1:
                        print(f"   ⏳ 429 – attendo {wait}s (tentativo {attempt+1}/{max_retry})...")
                        time.sleep(wait)
                        continue
                    raise RuntimeError("SWITCH_TO_OLLAMA")
                raise
        raise RuntimeError("Retry Gemini esauriti")

    def _call_ollama(self, messages: list) -> str:
        try:
            import ollama
            ollama_msgs = []
            for m in messages:
                role = "assistant" if m.get("role") == "model" else m.get("role", "user")
                parts = m.get("parts", [""])
                content = parts[0] if isinstance(parts, list) else parts
                ollama_msgs.append({"role": role, "content": content})
            resp = ollama.chat(model=self._ollama_model, messages=ollama_msgs)
            return resp["message"]["content"].strip()
        except Exception as e:
            return f"❌ Errore Ollama: {e}"

    def _call_model(self, messages: list) -> str:
        if self._model:
            try:
                return self._call_gemini(messages)
            except RuntimeError as e:
                if "SWITCH_TO_OLLAMA" in str(e) and self._ollama_available:
                    print("   🔄 Gemini esaurito → switch Ollama locale")
                    return self._call_ollama(messages)
                raise
        elif self._ollama_available:
            return self._call_ollama(messages)
        raise RuntimeError("Nessun modello disponibile. Configura GOOGLE_API_KEY o installa Ollama.")

    # ─── Loop principale ──────────────────────────────────────────────────────

    def run_task(self, task: str, max_steps: int = None) -> str:
        max_steps = max_steps or self.config.get("agent", {}).get("max_steps", 20)
        self.log.info(f"Task: {task[:80]}")

        context = self.memory.get_context()
        messages = []
        if context:
            messages.append({"role": "user", "parts": [f"Contesto:\n{context}"]})
            messages.append({"role": "model", "parts": ["Ok."]})
        messages.append({"role": "user", "parts": [task]})

        step = 0
        final_response = ""
        stall_count = 0          # contatore risposte senza tool call
        last_responses = []      # ultime 3 risposte per rilevare ripetizioni

        while step < max_steps:
            step += 1
            self.log.info(f"Step {step}/{max_steps}")

            try:
                text = self._call_model(messages)
            except Exception as e:
                return f"❌ Errore modello: {e}"

            messages.append({"role": "model", "parts": [text]})

            # ── Rilevamento loop/stallo ────────────────────────────────────
            text_lower = text.lower()

            # 1. Il modello dice esplicitamente che aspetta un risultato
            if any(kw in text_lower for kw in STALL_KEYWORDS):
                stall_count += 1
                if stall_count >= 2:
                    msg = (
                        "❌ Task interrotto: l'agente è entrato in stallo.\n"
                        "Causa: il modello attendeva un risultato tool che non è arrivato.\n"
                        "Suggerimento: riprova il task con un comando più semplice."
                    )
                    self.memory.add(task, msg)
                    return msg
            else:
                stall_count = 0

            # 2. Risposta identica per 2 volte di fila → loop
            last_responses.append(text[:200])
            if len(last_responses) > 3:
                last_responses.pop(0)
            if len(last_responses) >= 2 and last_responses[-1] == last_responses[-2]:
                msg = (
                    "❌ Task interrotto: l'agente ha ripetuto la stessa risposta due volte.\n"
                    "Causa: probabilmente il tool precedente ha restituito un risultato ambiguo."
                )
                self.memory.add(task, msg)
                return msg

            # ── Gestione tool call ─────────────────────────────────────────
            tool_call = self._parse_tool_call(text)

            if tool_call:
                stall_count = 0
                name = tool_call.get("tool")
                params = tool_call.get("params", {})
                print(f"\n🔧 [{name}] {params}")
                result = self.tools.execute(name, params)
                result_str = str(result)
                print(f"   → {result_str[:300]}")

                # Rilevamento errore tool
                tool_failed = self._is_tool_error(result_str)
                if tool_failed:
                    error_note = (
                        f"⚠️ Il tool '{name}' ha restituito un errore:\n{result_str}\n\n"
                        "Se è un errore critico, dì ❌ e spiega il motivo. "
                        "Se puoi provare un'alternativa, fallo UNA sola volta."
                    )
                    messages.append({"role": "user", "parts": [error_note]})
                else:
                    messages.append({
                        "role": "user",
                        "parts": [f"Risultato '{name}':\n{result_str}\n\nContinua o dichiara completato."],
                    })

            else:
                # Nessun tool call → risposta finale o testo libero
                final_response = text
                if any(kw in text_lower for kw in ["completato", "fatto", "terminato", "✅", "❌", "goal raggiunto"]):
                    break
                if step >= max_steps:
                    break
                messages.append({"role": "user", "parts": ["Continua oppure dichiara ✅ completato o ❌ fallito con la causa."]})

        # ── Fine loop ──────────────────────────────────────────────────────
        if not final_response:
            final_response = (
                f"❌ Task non completato: raggiunto il limite di {max_steps} step senza una risposta definitiva.\n"
                "Prova a semplificare il task o aumenta max_steps in config.json."
            )

        self.memory.add(task, final_response)
        return final_response

    # ─── Helpers ─────────────────────────────────────────────────────────────

    def _is_tool_error(self, result: str) -> bool:
        """Ritorna True se il risultato del tool indica un errore."""
        result_lower = result.lower()
        error_signals = [
            "[stderr]",
            "[exit code: 1]",
            "[exit code: 2]",
            "accesso negato",
            "access is denied",
            "impossibile trovare",
            "cannot find",
            "the system cannot find",
            "sintassi del nome",       # errore dir con virgolette
            "errore di sintassi",
        ]
        return any(sig in result_lower for sig in error_signals)

    def _parse_tool_call(self, text: str) -> Optional[dict]:
        text = text.strip()
        # Rimuovi markdown code block
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if len(lines) > 2 else text

        # JSON puro
        try:
            data = json.loads(text)
            if "tool" in data:
                return data
        except json.JSONDecodeError:
            pass

        # JSON embedded nel testo
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
