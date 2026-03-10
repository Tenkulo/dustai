"""
DUST AI – Core Agent v1.1
Loop agente con retry automatico su 429 + fallback Ollama locale.
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
- Usa SEMPRE lo strumento sys_exec con `cmd /c` per operazioni su filesystem
- Percorso Desktop reale: usa sys_exec `cmd /c echo %OneDrive%\\Desktop`
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
- sys_exec: esegui comandi shell Windows
- file_read / file_write / file_list / file_exists / file_delete: operazioni file
- browser_open / browser_click / browser_type / browser_get_text: browser
- mouse_move / mouse_click / keyboard_type / keyboard_hotkey: input
- app_launch / app_focus / app_list: app Windows
- web_search: ricerca Perplexity
- code_run: esegui Python

Quando usi un tool, rispondi SOLO con JSON, nessun testo aggiuntivo.
Formato: {"tool": "nome_tool", "params": {...}}
"""

# Rate limiting: free tier = 5 req/min → 1 ogni 13s (margine sicurezza)
MIN_CALL_INTERVAL = 13


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
            names = [m.model for m in models.models] if hasattr(models, 'models') else []
            self._ollama_available = bool(names)
            self._ollama_model = next(
                (n for n in names if "qwen3" in n),
                next((n for n in names if "mistral" in n or "llama" in n), names[0] if names else None)
            )
            if self._ollama_available:
                self.log.info(f"Ollama: {self._ollama_model}")
        except Exception:
            self._ollama_model = None

    def _rate_limit_wait(self):
        """Aspetta il tempo necessario per rispettare il rate limit."""
        elapsed = time.time() - self._last_call_time
        if elapsed < MIN_CALL_INTERVAL:
            wait = MIN_CALL_INTERVAL - elapsed
            self.log.info(f"Rate limit: attendo {wait:.1f}s")
            print(f"   ⏳ Rate limit: attendo {wait:.1f}s...")
            time.sleep(wait)

    def _call_gemini(self, messages: list, max_retry: int = 4) -> str:
        """Chiama Gemini con retry automatico su 429."""
        for attempt in range(max_retry):
            self._rate_limit_wait()
            try:
                self._last_call_time = time.time()
                response = self._model.generate_content(messages)
                return response.text.strip()
            except Exception as e:
                error_msg = str(e)
                if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                    # Estrai retry delay
                    m = re.search(r"retry.*?(\d+)[\.\d]*s", error_msg, re.IGNORECASE)
                    wait = int(m.group(1)) + 3 if m else 65
                    if attempt < max_retry - 1:
                        print(f"   ⏳ 429 rate limit – attendo {wait}s e riprovo (tentativo {attempt+1}/{max_retry})...")
                        self.log.warning(f"429 – attendo {wait}s")
                        time.sleep(wait)
                        continue
                    # Ultimo tentativo fallito
                    raise RuntimeError("SWITCH_TO_OLLAMA")
                raise
        raise RuntimeError("Retry Gemini esauriti")

    def _call_ollama(self, messages: list) -> str:
        """Chiamata a Ollama locale."""
        try:
            import ollama
            ollama_msgs = []
            for m in messages:
                role = "assistant" if m.get("role") == "model" else m.get("role", "user")
                parts = m.get("parts", [""])
                content = parts[0] if isinstance(parts, list) else parts
                ollama_msgs.append({"role": role, "content": content})

            resp = ollama.chat(model=self._ollama_model, messages=ollama_msgs)
            return resp['message']['content'].strip()
        except Exception as e:
            return f"❌ Errore Ollama: {e}"

    def _call_model(self, messages: list) -> str:
        """Chiama il modello migliore disponibile con fallback automatico."""
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

    def run_task(self, task: str, max_steps: int = None) -> str:
        """Loop agente autonomo con retry e fallback."""
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

        while step < max_steps:
            step += 1
            self.log.info(f"Step {step}/{max_steps}")

            try:
                text = self._call_model(messages)
            except Exception as e:
                return f"❌ {e}"

            messages.append({"role": "model", "parts": [text]})
            tool_call = self._parse_tool_call(text)

            if tool_call:
                name = tool_call.get("tool")
                params = tool_call.get("params", {})
                print(f"\n🔧 [{name}] {params}")
                result = self.tools.execute(name, params)
                print(f"   → {str(result)[:300]}")
                messages.append({
                    "role": "user",
                    "parts": [f"Risultato '{name}':\n{result}\n\nContinua o completa."]
                })
            else:
                final_response = text
                if any(kw in text.lower() for kw in ["completato", "fatto", "terminato", "✅", "goal raggiunto"]):
                    break
                if step >= max_steps:
                    break
                messages.append({"role": "user", "parts": ["Continua o dichiara completato."]})

        self.memory.add(task, final_response)
        return final_response or "Task eseguito."

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
