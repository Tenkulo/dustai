"""
DUST AI – OllamaCaller v2.0
Soluzione definitiva al problema tool calling su modelli locali.

PROBLEMA REALE:
  - format="json" forza output JSON ma NON garantisce lo schema
  - qwen3:8b ha reasoning attivo di default → produce <think>...</think> PRIMA del JSON
  - Il parser di agent.py v1.x riceveva il blocco <think> come testo → parse fail
  - SelfHeal non scattava → loop infinito

SOLUZIONE (research-backed, 2025-2026):
  1. format=ToolCall.model_json_schema()  → schema enforcement a livello motore
  2. Pydantic validation + retry loop     → rigetta JSON malformato e richiede
  3. Two-phase qwen3 thinking:
       - Fase 1: lascia pensare il modello (stop su </think>)
       - Fase 2: pre-fill del reasoning + richiede JSON puro
  4. instructor library come fallback avanzato (TOOLS mode)
  5. temperature=0 per determinismo massimo

REFERENCES:
  - https://docs.ollama.com/capabilities/structured-outputs
  - https://python.useinstructor.com/integrations/ollama/
  - https://medium.com/@maganuriyev/ollama-on-cpu-qwen3...
  - https://www.glukhov.org/post/2025/09/llm-structured-output-with-ollama...
"""
import json
import logging
import re
import time
from typing import Optional, Any, Literal

log = logging.getLogger("OllamaCaller")

# ─── Pydantic schemas (cuore della soluzione) ─────────────────────────────────
try:
    from pydantic import BaseModel, Field
    _PYDANTIC_OK = True
except ImportError:
    _PYDANTIC_OK = False
    BaseModel = object


if _PYDANTIC_OK:
    class ToolCallParams(BaseModel):
        """Parametri generici per una chiamata tool."""
        cmd:      Optional[str] = Field(None, description="Comando shell")
        path:     Optional[str] = Field(None, description="Path file/directory")
        content:  Optional[str] = Field(None, description="Contenuto da scrivere")
        url:      Optional[str] = Field(None, description="URL da aprire")
        query:    Optional[str] = Field(None, description="Query di ricerca")
        text:     Optional[str] = Field(None, description="Testo da digitare")
        code:     Optional[str] = Field(None, description="Codice Python da eseguire")
        app:      Optional[str] = Field(None, description="App da avviare")
        x:        Optional[int] = Field(None, description="Coordinata X mouse")
        y:        Optional[int] = Field(None, description="Coordinata Y mouse")
        mode:     Optional[str] = Field(None, description="Modalità operazione")
        timeout:  Optional[int] = Field(None, description="Timeout in secondi")
        region:   Optional[str] = Field(None, description="Regione screenshot")
        cwd:      Optional[str] = Field(None, description="Working directory")

    class ToolCall(BaseModel):
        """Schema DUST AI per tool call — passato direttamente a Ollama format=."""
        tool: Literal[
            "sys_exec", "file_read", "file_write", "file_list", "file_delete",
            "web_search", "browser_open", "browser_click", "browser_type",
            "browser_get_text", "screenshot", "vision_analyze",
            "mouse_click", "keyboard_type", "keyboard_hotkey",
            "app_launch", "code_run"
        ] = Field(..., description="Nome del tool da chiamare")
        params: ToolCallParams = Field(
            default_factory=ToolCallParams,
            description="Parametri del tool"
        )

    class DoneSignal(BaseModel):
        """Schema per dichiarazione completamento task."""
        status:  Literal["done"] = Field("done")
        summary: str = Field(..., description="Cosa è stato fatto e verificato")

    class AgentResponse(BaseModel):
        """Schema unificato: tool call O segnale done."""
        action:  Literal["tool_call", "done"] = Field(
            ..., description="'tool_call' se devi eseguire un tool, 'done' se il task è completato"
        )
        tool:    Optional[str]  = Field(None, description="Nome tool (solo se action=tool_call)")
        params:  Optional[dict] = Field(None, description="Parametri tool (solo se action=tool_call)")
        summary: Optional[str] = Field(None, description="Riepilogo (solo se action=done)")

    _TOOL_CALL_SCHEMA     = ToolCall.model_json_schema()
    _AGENT_RESPONSE_SCHEMA = AgentResponse.model_json_schema()

else:
    # Fallback se pydantic non installato — schema manuale
    _TOOL_CALL_SCHEMA = {
        "type": "object",
        "properties": {
            "tool": {"type": "string"},
            "params": {"type": "object"},
        },
        "required": ["tool", "params"],
    }
    _AGENT_RESPONSE_SCHEMA = _TOOL_CALL_SCHEMA


# ─── OllamaCaller ─────────────────────────────────────────────────────────────

class OllamaCaller:
    """
    Wrapper Ollama con schema enforcement, two-phase thinking e retry loop.

    Metodo principale: call(messages, task) → dict
    """

    MAX_RETRIES   = 3
    RETRY_DELAY_S = 2

    def __init__(self, model: str, config=None):
        self.model  = model
        self.config = config
        self.log    = logging.getLogger("OllamaCaller")
        self._is_thinking_model = self._check_thinking_model(model)
        self._instructor_client = None
        self._setup_instructor()

    def _check_thinking_model(self, model: str) -> bool:
        """qwen3 e altri modelli hanno thinking attivo di default."""
        thinking_models = ["qwen3", "deepseek-r1", "phi4-reasoning", "cogito"]
        return any(t in model.lower() for t in thinking_models)

    def _setup_instructor(self):
        """Prova a usare instructor come backend avanzato (fallback)."""
        try:
            import instructor
            from openai import OpenAI
            client = OpenAI(
                base_url="http://localhost:11434/v1",
                api_key="ollama",
            )
            # TOOLS mode per modelli che lo supportano (qwen2.5, llama3.1 ecc.)
            # JSON mode per tutti gli altri
            try:
                self._instructor_client = instructor.from_openai(
                    client,
                    mode=instructor.Mode.TOOLS,
                )
                self.log.info("instructor: TOOLS mode attivo")
            except Exception:
                self._instructor_client = instructor.from_openai(
                    client,
                    mode=instructor.Mode.JSON,
                )
                self.log.info("instructor: JSON mode attivo")
        except ImportError:
            self.log.debug("instructor non disponibile — uso ollama SDK diretto")

    # ─── Metodo principale ───────────────────────────────────────────────────

    def call(self, messages: list, task: str = "") -> dict:
        """
        Chiama Ollama e ritorna SEMPRE un dict strutturato:
          {"type": "tool_call", "tool": str, "params": dict}
          {"type": "done", "summary": str}
          {"type": "text", "text": str}

        Pipeline:
          1. Two-phase (qwen3): thinking → structured JSON
          2. Schema enforcement via format=model_json_schema()
          3. Pydantic validation + retry
          4. instructor fallback
          5. Parser testuale come ultima risorsa
        """
        # Prepara system message rafforzato
        ollama_messages = self._build_messages(messages, task)

        # 1. Two-phase per modelli thinking (qwen3:8b)
        if self._is_thinking_model:
            result = self._call_two_phase(ollama_messages, task)
            if result and result.get("type") in ("tool_call", "done"):
                return result

        # 2. Schema enforcement diretto (approccio principale)
        result = self._call_with_schema(ollama_messages)
        if result and result.get("type") in ("tool_call", "done"):
            return result

        # 3. Instructor fallback
        if self._instructor_client and _PYDANTIC_OK:
            result = self._call_with_instructor(messages, task)
            if result and result.get("type") in ("tool_call", "done"):
                return result

        # 4. Testo grezzo come ultimo fallback
        return result or {"type": "text", "text": "Nessun output valido da Ollama"}

    # ─── Two-phase qwen3 ─────────────────────────────────────────────────────

    def _call_two_phase(self, messages: list, task: str) -> Optional[dict]:
        """
        Tecnica specifica per qwen3 (e modelli thinking).

        Fase 1: lascia il modello ragionare liberamente
                stop=["</think>"] interrompe subito dopo il reasoning
        Fase 2: pre-fill del reasoning nell'history, poi richiede JSON puro
                con format=schema → il modello "sa già cosa fare" e produce JSON

        Source: https://medium.com/@maganuriyev/ollama-on-cpu-qwen3...
        """
        try:
            import ollama

            # FASE 1: reasoning libero
            think_resp = ollama.chat(
                model=self.model,
                messages=messages,
                options={
                    "stop":        ["</think>"],
                    "temperature": 0.3,   # lievemente creativo per il reasoning
                    "num_predict": 512,   # reasoning corto
                },
                stream=False,
            )
            reasoning = think_resp["message"]["content"]
            if not reasoning.endswith("</think>"):
                reasoning += "</think>"

            self.log.debug("Qwen3 reasoning: " + reasoning[:100].replace("\n", " "))

            # FASE 2: JSON strutturato con reasoning pre-filled
            messages_phase2 = messages + [
                {
                    "role":    "assistant",
                    "content": reasoning + "\n\n",  # pre-fill thinking
                }
            ]

            json_resp = ollama.chat(
                model=self.model,
                messages=messages_phase2,
                format=_AGENT_RESPONSE_SCHEMA,
                options={
                    "temperature": 0,     # deterministico per output strutturato
                    "num_predict": 256,   # tool call brevi
                },
                stream=False,
            )

            raw = json_resp["message"]["content"]
            return self._validate_and_parse(raw)

        except Exception as e:
            self.log.warning("Two-phase failed: " + str(e))
            return None

    # ─── Schema enforcement diretto ──────────────────────────────────────────

    def _call_with_schema(self, messages: list) -> Optional[dict]:
        """
        Chiama Ollama passando il JSON Schema direttamente a format=.
        Questo vincola il motore a generare solo token conformi allo schema.
        NON dipende dal prompt — è enforcement a livello di sampling.

        Source: https://docs.ollama.com/capabilities/structured-outputs
        """
        import ollama

        for attempt in range(self.MAX_RETRIES):
            try:
                resp = ollama.chat(
                    model=self.model,
                    messages=messages,
                    format=_AGENT_RESPONSE_SCHEMA,
                    options={
                        "temperature": 0,
                        "num_predict": 256,
                        "num_ctx":     4096,
                    },
                    stream=False,
                )
                raw    = resp["message"]["content"]
                result = self._validate_and_parse(raw)

                if result and result.get("type") in ("tool_call", "done"):
                    return result

                if attempt < self.MAX_RETRIES - 1:
                    self.log.warning(
                        "Schema attempt " + str(attempt + 1) + " invalid: " + raw[:80]
                    )
                    # Inietta feedback nel messaggio
                    messages = messages + [{
                        "role":    "user",
                        "content": (
                            "La risposta non era valida. Riprova. "
                            "action deve essere 'tool_call' o 'done'. "
                            "Se tool_call, specifica tool e params. "
                            "Se done, specifica summary."
                        )
                    }]
                    time.sleep(self.RETRY_DELAY_S)

            except Exception as e:
                self.log.warning("Schema call attempt " + str(attempt + 1) + ": " + str(e))
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(self.RETRY_DELAY_S)

        return None

    # ─── Instructor fallback ─────────────────────────────────────────────────

    def _call_with_instructor(self, messages: list, task: str) -> Optional[dict]:
        """
        instructor gestisce retry, validation e mode switching automaticamente.
        Source: https://python.useinstructor.com/integrations/ollama/
        """
        try:
            openai_msgs = []
            for m in messages:
                role    = "assistant" if m.get("role") == "model" else m.get("role", "user")
                parts   = m.get("parts", [""])
                content = parts[0] if isinstance(parts, list) else str(parts)
                openai_msgs.append({"role": role, "content": content})

            resp = self._instructor_client.chat.completions.create(
                model=self.model,
                messages=openai_msgs,
                response_model=AgentResponse,
                max_retries=2,
                timeout=30.0,
            )

            return self._from_agent_response(resp)

        except Exception as e:
            self.log.warning("instructor fallback failed: " + str(e))
            return None

    # ─── Helpers ─────────────────────────────────────────────────────────────

    def _build_messages(self, messages: list, task: str) -> list:
        """Costruisce la lista messaggi Ollama con system message rinforzato."""
        desktop   = str(self.config.get_desktop())   if self.config else "C:\\Users\\ugopl\\OneDrive\\Desktop"
        base_path = str(self.config.get_base_path()) if self.config else "A:\\dustai_stuff"

        system_content = (
            "Sei DUST AI, agente autonomo desktop.\n"
            "Devi SEMPRE rispondere con JSON valido che segue questo schema:\n"
            '- Per chiamare un tool: {"action":"tool_call","tool":"nome","params":{...}}\n'
            '- Per dichiarare completamento: {"action":"done","summary":"..."}\n\n'
            "Tool disponibili: sys_exec, file_read, file_write, file_list, "
            "web_search, browser_open, screenshot, vision_analyze, "
            "mouse_click, keyboard_type, app_launch, code_run\n\n"
            "Desktop: " + desktop + "\n"
            "Base: " + base_path + "\n\n"
            "REGOLE:\n"
            "1. Rispondi SOLO con JSON. Niente testo narrativo.\n"
            "2. Non descrivere azioni: eseguile tramite tool.\n"
            "3. Usa sys_exec con 'cmd /c ...' per operazioni Windows.\n"
            "4. Verifica sempre il risultato con un secondo tool call.\n"
            "/nothink"   # disabilita thinking esplicito in qwen3
        )

        ollama_msgs = [{"role": "system", "content": system_content}]

        for m in messages:
            role    = "assistant" if m.get("role") == "model" else m.get("role", "user")
            parts   = m.get("parts", [""])
            content = parts[0] if isinstance(parts, list) else str(parts)
            # Rimuovi blocchi <think>...</think> residui da messaggi precedenti
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
            if content:
                ollama_msgs.append({"role": role, "content": content})

        return ollama_msgs

    def _validate_and_parse(self, raw: str) -> Optional[dict]:
        """Valida e normalizza l'output del modello."""
        if not raw:
            return None

        # Rimuovi blocchi think residui
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Cerca il primo JSON valido nel testo
            for m in re.finditer(r"\{[^{}]{10,}\}", raw, re.DOTALL):
                try:
                    data = json.loads(m.group(0))
                    break
                except json.JSONDecodeError:
                    continue
            else:
                return None

        # Normalizza da AgentResponse schema a formato DUST interno
        if "action" in data:
            if data["action"] == "tool_call":
                tool   = data.get("tool", "")
                params = data.get("params") or {}
                if tool:
                    # Normalizza params: rimuovi None
                    if isinstance(params, dict):
                        params = {k: v for k, v in params.items() if v is not None}
                    return {"type": "tool_call", "tool": tool, "params": params}
            elif data["action"] == "done":
                return {"type": "done", "summary": data.get("summary", "")}

        # Formato legacy {"tool": ..., "params": ...}
        if "tool" in data:
            return {
                "type":   "tool_call",
                "tool":   data["tool"],
                "params": {k: v for k, v in (data.get("params") or {}).items() if v is not None},
            }

        if data.get("status") in ("done", "completed"):
            return {"type": "done", "summary": data.get("summary", "")}

        # Pydantic validation come verifica finale
        if _PYDANTIC_OK:
            try:
                ar = AgentResponse.model_validate(data)
                return self._from_agent_response(ar)
            except Exception:
                pass

        return None

    def _from_agent_response(self, ar) -> dict:
        """Converte AgentResponse Pydantic a dict DUST."""
        if ar.action == "done":
            return {"type": "done", "summary": ar.summary or ""}
        params = {}
        if ar.params:
            if isinstance(ar.params, dict):
                params = {k: v for k, v in ar.params.items() if v is not None}
            elif hasattr(ar.params, "model_dump"):
                params = {k: v for k, v in ar.params.model_dump().items() if v is not None}
        return {"type": "tool_call", "tool": ar.tool or "", "params": params}
