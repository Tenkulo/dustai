# DUST AI v2.0 — Desktop Unified Smart Tool AI

Agente desktop autonomo per Windows 11. Esegue task reali sul PC: file system, browser, mouse/tastiera, app, ricerche web. Zero supervisione umana.

---

## Novità v2.0 (rispetto alla v1.x)

| Problema v1.x | Soluzione v2.0 |
|---|---|
| Ollama genera testo narrativo invece di JSON → tool mai chiamati | Gemini: native function calling SDK. Ollama: `format="json"` + schema + parser 4-layer |
| Parser fragile con regex | Parser multi-layer: JSON diretto → estrazione blocco → narrative extraction → fallback |
| SelfHeal solo su errori tool | SelfHeal anche su parse failure, rate limit, syntax error nel codice sorgente |
| Path sparsi su Desktop e %APPDATA% | Tutto in `A:\dustai_stuff` (configurabile via `DUSTAI_BASE`) |
| Nessuna memoria procedurale | SkillForge: apprende da ogni task completato |
| Nessuna task queue | TaskQueue persistente JSON con priorità |
| Nessuna reflection | Reflective loop post-tool ogni 3 step |

---

## Struttura repo

```
dustai/
├── run.py              ← entry point con pre-boot self-healing
├── run.bat             ← avvio GUI (default)
├── install.bat         ← installazione completa
├── src/
│   ├── config.py       ← BASE_PATH + tutti i percorsi
│   ├── agent.py        ← loop agente + tool calling robusto + reflection
│   ├── memory.py       ← Memory + SkillForge + TaskQueue
│   ├── self_heal.py    ← heal tool/parse/rate-limit/src-code
│   ├── bootstrap.py    ← auto-install dipendenze
│   ├── crash_recovery.py ← persist crash → Gemini patch → restart
│   ├── app.py          ← orchestrator GUI/console
│   ├── tools/
│   │   ├── registry.py ← tool dispatcher con timeout + normalizzazione
│   │   ├── sys_exec.py
│   │   ├── file_ops.py
│   │   ├── browser.py
│   │   ├── input_control.py
│   │   ├── windows_apps.py
│   │   ├── web_search.py
│   │   ├── code_runner.py
│   │   └── vision.py   ← screenshot + Gemini/Qwen-VL analysis
│   └── ui/
│       ├── gui.py      ← PySide6 dark UI
│       └── console.py
└── A:\dustai_stuff\    ← BASE_PATH (tutto qui)
    ├── .env            ← API keys
    ├── config.json     ← override configurazione
    ├── logs/           ← debug_YYYY-MM-DD.jsonl
    ├── memory/         ← memory.json
    ├── skills/         ← skills.json (SkillForge)
    ├── profiles/       ← self_profile.json
    ├── tasks/          ← queue.json (TaskQueue)
    ├── screenshots/
    ├── patches/        ← backup file prima di ogni patch
    └── backups/
```

---

## Quick Start

```powershell
# 1. Installa tutto
.\install.bat

# 2. Inserisci API key in A:\dustai_stuff\.env
#    GOOGLE_API_KEY=la_tua_key

# 3. Avvia
.\run.bat            # GUI (default)
.\run.bat --console  # terminale
```

---

## ⚠️ WARNING: Ollama + Tool Calling

**Il problema:** la maggior parte dei modelli Ollama non rispetta il formato JSON richiesto per i tool call, generando testo narrativo inutilizzabile.

**La soluzione v2.0:**
1. Gemini usa **native function calling** (niente JSON manuale, niente parser)
2. Ollama usa `format="json"` + schema enforcement
3. Parser 4-layer con estrazione da testo narrativo come fallback
4. SelfHeal.heal_parse_fail() riformatta via Gemini se tutto fallisce

**Modelli Ollama consigliati (tool-friendly):**
- `qwen3:8b` ✅ (predefinito)
- `qwen2.5-coder:7b` ✅
- `llama3.1:8b` ✅
- `mistral-small3.1` ⚠️ (limitato)

**Modelli da evitare per tool calling:**
- Qualsiasi modello base non-instruct
- Modelli < 7B parametri

---

## Stack Tecnico

| Componente | Tecnologia |
|---|---|
| LLM primario | Gemini 2.5 Flash (native function calling) |
| LLM locale | Ollama qwen3:8b / llama3.1:8b |
| LLM heavy | Gemini 2.5 Pro |
| Research | Perplexity Sonar Pro |
| GUI | PySide6 6.6+ |
| Browser automation | Playwright |
| Vision | mss + Gemini Vision |
| Memory | JSON su disco (A:\dustai_stuff) |

---

## Configurazione BASE_PATH

```powershell
# Cambia il percorso base (default A:\dustai_stuff)
setx DUSTAI_BASE "D:\mio_percorso"
```

O modifica `A:\dustai_stuff\config.json`:
```json
{
  "base_path": "D:\\mio_percorso"
}
```

---

## Autonomia

| Feature | v1.x | v2.0 |
|---|---|---|
| Tool calling reale | ❌ | ✅ |
| Fallback Ollama funzionante | ❌ | ✅ |
| Self-healing parse fail | ❌ | ✅ |
| Pre-boot crash recovery | ✅ | ✅ |
| Reflective loop | ❌ | ✅ |
| SkillForge (experience replay) | ❌ | ✅ |
| Task queue persistente | ❌ | ✅ |
| Vision tool | ❌ | ✅ |
| BASE_PATH unificato | ❌ | ✅ |

Autonomia stimata: **~96%** (v1.x: ~88%)
