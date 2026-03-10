"""
DUST AI – Core Agent
Loop agente: riceve task → pianifica → chiama tool → verifica → completa.
Provider: Gemini Flash (primario), Perplexity (research), Ollama (locale)
"""
import json
import logging
import time
from typing import Optional

import google.generativeai as genai

from .tools.registry import ToolRegistry
from .memory import Memory


SYSTEM_PROMPT = """Sei DUST AI, un agente autonomo avanzato su Windows 11 (Ryzen 5 5600G, 16 GB RAM).

## Regole Operative Fondamentali

### Filesystem Windows
- Usa SEMPRE lo strumento sys_exec con `cmd /c` per operazioni su filesystem
- Percorso Desktop reale: usa file_ops.get_desktop() oppure chiedi con sys_exec `cmd /c echo %OneDrive%\\Desktop`  
- DOPO ogni operazione file, VERIFICA sempre con `cmd /c dir "percorso"` o `cmd /c type "file"`
- NON dichiarare mai un task completato senza aver verificato il risultato reale

### Pianificazione
1. Prima di agire, elenca il piano in max 3 bullet
2. Esegui UN tool alla volta
3. Valuta il risultato di ogni step
4. Solo dopo verifica positiva, passa allo step successivo

### Linguaggio
- Rispondi SEMPRE in italiano
- Sii conciso: azioni > spiegazioni verbose
- In caso di errore: 1 riga di causa + fix immediato

### Tool disponibili
- sys_exec: esegui comandi shell Windows/Linux
- file_read / file_write: leggi e scrivi file
- browser_open / browser_click / browser_type: controllo browser
- mouse_move / mouse_click / keyboard_type: controllo input
- app_launch / app_focus: avvio e focus applicazioni Windows
- web_search: ricerca web via Perplexity
- code_run: esegui codice Python

Quando usi un tool, rispondi SOLO con il JSON del tool call, senza testo aggiuntivo.
Formato: {"tool": "nome_tool", "params": {...}}
"""


class Agent:
    def __init__(self, config):
        self.config = config
        self.log = logging.getLogger("Agent")
        self.memory = Memory(config)
        self.tools = ToolRegistry(config)
        self._setup_model()

    def _setup_model(self):
        """Inizializza il modello Gemini."""
        api_key = self.config.get_api_key("google")
        if not api_key:
            self.log.warning("⚠️ GOOGLE_API_KEY non trovata. Imposta la variabile d'ambiente.")
            self._model = None
            return

        genai.configure(api_key=api_key)
        model_name = self.config.get_model("primary").replace("gemini/", "")
        self._model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=SYSTEM_PROMPT,
        )
        self.log.info(f"Modello inizializzato: {model_name}")

    def run_task(self, task: str, max_steps: int = None) -> str:
        """
        Esegue un task in loop autonomo:
        task → pianifica → chiama tool → verifica → loop fino a completamento
        """
        if not self._model:
            return "❌ Nessun modello configurato. Imposta GOOGLE_API_KEY."

        max_steps = max_steps or self.config.get("agent", {}).get("max_steps", 20)
        self.log.info(f"Task avviato: {task[:80]}...")

        # Carica memoria contesto
        context = self.memory.get_context()
        messages = []

        if context:
            messages.append({
                "role": "user",
                "parts": [f"Contesto sessione precedente:\n{context}"]
            })
            messages.append({
                "role": "model",
                "parts": ["Contesto caricato. Pronto per il task."]
            })

        messages.append({"role": "user", "parts": [task]})

        step = 0
        final_response = ""

        while step < max_steps:
            step += 1
            self.log.info(f"Step {step}/{max_steps}")

            try:
                response = self._model.generate_content(messages)
                text = response.text.strip()
            except Exception as e:
                error_msg = str(e)
                self.log.error(f"Errore modello: {error_msg}")

                # Gestione 429 - fallback a flash se su pro
                if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                    return f"⚠️ Rate limit raggiunto. Riprova tra qualche secondo.\n{error_msg}"
                return f"❌ Errore: {error_msg}"

            messages.append({"role": "model", "parts": [text]})

            # Controlla se è una tool call
            tool_call = self._parse_tool_call(text)

            if tool_call:
                tool_name = tool_call.get("tool")
                params = tool_call.get("params", {})

                self.log.info(f"Tool call: {tool_name}({params})")
                print(f"\n🔧 [{tool_name}] {params}")

                # Esegui il tool
                result = self.tools.execute(tool_name, params)
                print(f"   → {str(result)[:200]}")
                self.log.info(f"Risultato tool: {str(result)[:200]}")

                # Aggiunge risultato come context
                messages.append({
                    "role": "user",
                    "parts": [f"Risultato tool '{tool_name}':\n{result}\n\nContinua o completa se il goal è raggiunto."]
                })

            else:
                # Risposta testuale = task completato o risposta finale
                final_response = text

                # Controlla se il modello ha dichiarato completamento
                if any(kw in text.lower() for kw in ["completato", "fatto", "terminato", "✅", "goal raggiunto"]):
                    self.log.info("Task completato con successo")
                    break

                # Se non è un tool call e non dichiara completamento,
                # potrebbe essere una risposta intermedia - continua
                if step >= max_steps:
                    self.log.warning("Max steps raggiunto")
                    break

                # Chiedi al modello di continuare
                messages.append({
                    "role": "user",
                    "parts": ["Continua con il prossimo step o dichiara completato se il task è terminato."]
                })

        # Salva in memoria
        self.memory.add(task, final_response)

        return final_response or "Task eseguito."

    def _parse_tool_call(self, text: str) -> Optional[dict]:
        """Cerca un JSON tool call nel testo del modello."""
        text = text.strip()

        # Rimuovi markdown fences se presenti
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if len(lines) > 2 else text

        # Cerca JSON diretto
        try:
            data = json.loads(text)
            if "tool" in data:
                return data
        except json.JSONDecodeError:
            pass

        # Cerca JSON embedded nel testo
        import re
        pattern = r'\{[^{}]*"tool"[^{}]*\}'
        matches = re.findall(pattern, text, re.DOTALL)
        for match in matches:
            try:
                data = json.loads(match)
                if "tool" in data:
                    return data
            except json.JSONDecodeError:
                continue

        return None

    def chat(self, message: str) -> str:
        """Chat semplice senza loop agente (risposta singola)."""
        if not self._model:
            return "❌ Nessun modello configurato."

        try:
            response = self._model.generate_content(message)
            return response.text
        except Exception as e:
            return f"❌ Errore: {e}"
