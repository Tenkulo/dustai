# DUST AI – Ollama Tool Calling: Soluzione Definitiva v2.0
# Documento tecnico + prompt operativo per modelli locali
# Research-backed: Marzo 2026

---

## DIAGNOSI DEL PROBLEMA ORIGINALE

Il fallback Ollama in agent.py v1.x era rotto per tre cause precise:

### Causa 1: format="json" non garantisce lo schema

`format="json"` istruisce il modello a produrre JSON, ma non specifica QUALE JSON.
Il modello decide autonomamente i nomi dei campi.

qwen3:8b con `format="json"` produceva:
```json
{"azione": "creazione_file", "descrizione": "creerò il file..."}
```
invece di `{"tool": "file_write", "params": {...}}`.

**Soluzione certificata**: passare `format=json_schema_dict` dove il dizionario
è un JSON Schema completo (Pydantic `model_json_schema()`).
Ollama usa llama.cpp internamente → **constrained decoding** = i token non
conformi allo schema vengono fisicamente filtrati dal sampler.
Source: https://docs.ollama.com/capabilities/structured-outputs

### Causa 2: qwen3:8b genera <think> prima del JSON

qwen3 è un modello di reasoning. Parte sempre con `<think>...</think>`:
```
<think>
Devo analizzare il task. L'utente vuole creare un file...
...500 token di ragionamento...
</think>
{"tool": "file_write", "params": {...}}
```

Il `json.loads()` diretto di agent.py v1.x falliva sul `<think>` →
parse error → SelfHeal non scattava → l'agent passava "Continua" →
qwen3 ricominciava a pensare → loop infinito.

**Soluzione**: two-phase approach + regex strip `<think>` + `/nothink` in system.

### Causa 3: SelfHeal mai attivato sui parse fail

`tools.execute()` non veniva mai chiamato (il JSON non veniva mai parsato),
quindi non c'era errore tool da healpare. SelfHeal non aveva un hook sul
parse failure — riceveva solo errori post-esecuzione.

**Soluzione**: aggiunta di `heal_parse_fail()` in SelfHealEngine, chiamata
direttamente da agent.py quando `_call_model()` ritorna `{"type":"parse_error"}`.

---

## SOLUZIONE TECNICA (src/ollama_caller.py)

### Layer 1: Two-phase thinking per qwen3

```python
# FASE 1: lascia pensare liberamente, stop subito dopo </think>
think_resp = ollama.chat(
    model="qwen3:8b",
    messages=messages,
    options={"stop": ["</think>"], "temperature": 0.3, "num_predict": 512},
)
reasoning = think_resp["message"]["content"] + "</think>"

# FASE 2: pre-fill del reasoning → il modello "sa già cosa fare"
# format=schema → constrained decoding garantisce JSON valido
resp = ollama.chat(
    model="qwen3:8b",
    messages=messages + [{"role": "assistant", "content": reasoning + "\n\n"}],
    format=AgentResponse.model_json_schema(),
    options={"temperature": 0, "num_predict": 256},
)
```

Il pre-fill forza il modello a continuare da dove ha terminato il thinking,
producendo direttamente il JSON senza nuovi blocchi `<think>`.
Source: https://medium.com/@maganuriyev/ollama-on-cpu-qwen3-with-reasoning-structured-output

### Layer 2: Pydantic schema enforcement

```python
from pydantic import BaseModel, Field
from typing import Literal, Optional

class AgentResponse(BaseModel):
    action:  Literal["tool_call", "done"]
    tool:    Optional[str]  = None
    params:  Optional[dict] = None
    summary: Optional[str]  = None

# CRITICO: non format="json" (stringa) ma format=schema_dict
resp = ollama.chat(
    model="qwen3:8b",
    messages=messages,
    format=AgentResponse.model_json_schema(),
    options={"temperature": 0},
)

# Pydantic valida struttura e tipi — ValueError su mismatch
result = AgentResponse.model_validate_json(resp.message.content)
```

Source: https://www.glukhov.org/post/2025/09/llm-structured-output-with-ollama-in-python-and-go/

### Layer 3: instructor con retry automatico

```python
import instructor
from openai import OpenAI

client = instructor.from_openai(
    OpenAI(base_url="http://localhost:11434/v1", api_key="ollama"),
    mode=instructor.Mode.TOOLS,
)

result = client.chat.completions.create(
    model="qwen3:8b",
    messages=messages,
    response_model=AgentResponse,
    max_retries=3,   # iniezione automatica degli errori di validazione
    timeout=30.0,
)
```

instructor intercetta `ValidationError` Pydantic, inietta il messaggio di errore
nel contesto e chiama il modello di nuovo. Risolve il 95%+ dei casi residui.
Source: https://python.useinstructor.com/integrations/ollama/

---

## PIPELINE COMPLETA IN AGENT.PY V2.0

```
Input: messages[]
    │
    ├─► Gemini (native function calling SDK)
    │       ↓ success → execute tool
    │       ↓ 429 → switch Ollama
    │
    ├─► OllamaCaller.call(messages)
    │       ├─ is qwen3? → Layer 1: two-phase thinking
    │       │       ↓ fail
    │       ├─ Layer 2: format=Pydantic.schema + retry ×3
    │       │       ↓ fail
    │       ├─ Layer 3: instructor (TOOLS/JSON mode + retry)
    │       │       ↓ fail
    │       └─ return {"type":"parse_error","raw":...}
    │               ↓
    │   HOOK CRITICO: if result["type"] == "parse_error":
    │       SelfHealEngine.heal_parse_fail(raw, messages)
    │               ├─ regex extraction da testo narrativo
    │               └─ Gemini riformatta (se disponibile)
    │                       ↓ success → tool call
    │                       ↓ fail → testo + log warning
    │
    └─► final fallback: {"type":"text","text":...}
```

---

## SYSTEM MESSAGE OTTIMIZZATO PER OLLAMA

```
Sei DUST AI, agente autonomo desktop.
Devi SEMPRE rispondere con JSON che segue esattamente questo schema:
- Per chiamare un tool: {"action":"tool_call","tool":"nome","params":{...}}
- Per dichiarare completamento: {"action":"done","summary":"..."}

Tool disponibili:
sys_exec, file_read, file_write, file_list, web_search,
browser_open, screenshot, vision_analyze, mouse_click,
keyboard_type, app_launch, code_run

Desktop: {desktop}
Base: {base_path}

REGOLE ASSOLUTE:
1. Solo JSON. Zero testo narrativo prima o dopo.
2. Non scrivere "Ho eseguito..." o "Creerò...": chiama il tool.
3. sys_exec per Windows: {"tool":"sys_exec","params":{"cmd":"cmd /c dir C:\\"}}
4. Dopo ogni modifica verifica sempre con un secondo tool call.
/nothink
```

Il token `/nothink` alla fine disabilita il reasoning esplicito in qwen3
(documentato nel repo ufficiale Qwen https://github.com/QwenLM/Qwen3).

---

## PARAMETRI OLLAMA CONSIGLIATI

```python
# Per tool calling (schema enforcement)
tool_call_options = {
    "temperature":    0,      # CRITICO: 0 = massima aderenza schema
    "num_predict":    256,    # tool call brevi, non servono token extra
    "num_ctx":        4096,
    "top_p":          0.9,
    "repeat_penalty": 1.1,    # riduce loop nel reasoning
}

# Per reasoning (fase 1 two-phase)
thinking_options = {
    "stop":        ["</think>"],
    "temperature": 0.3,       # un po' più creativo per il pensiero
    "num_predict": 512,
}
```

---

## SEGNALI DI PARSE FAILURE (→ attiva SelfHeal)

Questi pattern nel raw output indicano che il modello ha ignorato il formato.
Rilevati in agent.py → `heal_parse_fail()` immediato, MAI "Continua":

```python
PARSE_FAIL_SIGNALS = [
    "<think>",       # thinking non terminato prima del JSON
    "🔧 [",          # output narrativo stile DUST v1.x
    "Ho eseguito",   # simulazione narrativa
    "Eseguirò",      # piano futuro non-action
    "Creerò",        # altra forma di simulazione
    "CREATO_OK",     # output narrativo esplicito
    "```json",       # markdown fencing (non JSON puro)
    "```",           # code block invece di JSON raw
]
```

---

## INSTALLAZIONE DIPENDENZE

```powershell
pip install "pydantic>=2.0.0"     # OBBLIGATORIO
pip install "instructor>=1.0.0"   # consigliato per retry avanzato
pip install "openai>=1.0.0"       # richiesto da instructor
```

---

## COMPATIBILITÀ MODELLI

| Modello | Two-Phase | format=schema | instructor | Consigliato |
|---|---|---|---|---|
| `qwen3:8b` | Obbligatorio | Funziona | Non ufficiale | Sì, con two-phase |
| `qwen2.5-coder:7b` | Non serve | Funziona | TOOLS mode | Ottimo per file/code |
| `llama3.1:8b` | Non serve | Funziona | TOOLS mode | Buon bilanciamento |
| `llama4` (scout/maverick) | Non serve | Funziona | TOOLS mode | Migliore disponibile |
| `mistral-small3.1` | Non serve | Variabile | Variabile | Non affidabile |
| Qualsiasi modello < 4B | N/A | Inaffidabile | No | Non usare |
