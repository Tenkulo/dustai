# 🤖 DUST AI — Desktop Unified Smart Tool AI

> **v1.4** · Windows 11 · Ryzen 5 5600G + 16 GB RAM  
> Gemini 2.5 Flash · Perplexity Sonar · Ollama locale · PySide6 GUI · Self-Healing autonomo

---

## Cos'è DUST AI

DUST AI è un agente AI autonomo nativo Windows che:

- **Esegue task** sul tuo PC (file, cartelle, browser, app, mouse/tastiera)
- **Si auto-ripara**: su ogni errore cerca la soluzione online, genera una patch, hot-ricarica il modulo e riprova — senza intervento umano
- **Non dipende da un solo modello**: usa Gemini 2.5 Flash come primario, switcha automaticamente su Ollama locale se il rate limit è esaurito
- **Si installa da solo**: il Bootstrap installa pip packages, Playwright/Chromium, scarica i modelli Ollama, configura le variabili iGPU

---

## Architettura

```
┌─────────────────────────────────────────────────────────────┐
│                    DUST AI v1.4                             │
│                                                             │
│  ┌──────────┐    ┌───────────┐    ┌─────────────────────┐  │
│  │ GUI      │    │  Agent    │    │   SelfHealEngine    │  │
│  │ PySide6  │───▶│  v1.4     │───▶│  web search + patch │  │
│  │          │    │           │    │  + hot-reload        │  │
│  └──────────┘    └─────┬─────┘    └─────────────────────┘  │
│                        │                                    │
│              ┌─────────▼──────────┐                        │
│              │    Tool Registry   │                        │
│              │  sys_exec          │                        │
│              │  file_ops          │                        │
│              │  browser (PW)      │                        │
│              │  input_control     │                        │
│              │  web_search        │                        │
│              │  code_runner       │                        │
│              │  windows_apps      │                        │
│              │  roblox            │                        │
│              └─────────┬──────────┘                        │
│                        │                                    │
│         ┌──────────────▼──────────────┐                    │
│         │         LLM Layer           │                    │
│         │  gemini-2.5-flash (primario)│                    │
│         │  gemini-2.5-pro  (pesante)  │                    │
│         │  qwen3:8b via Ollama        │◀── fallback auto   │
│         │  mistral-small3.1 (backup)  │                    │
│         └─────────────────────────────┘                    │
└─────────────────────────────────────────────────────────────┘
```

---

## Struttura Repository

```
dustai/
├── README.md
├── CHANGELOG.md
├── .gitignore
├── requirements.txt           # dipendenze Python
├── run.py                     # entry point
├── run.bat                    # launcher Windows
├── install.bat                # setup iniziale (esegui una volta)
│
├── src/
│   ├── app.py                 # orchestratore: bootstrap → agent → UI
│   ├── agent.py               # loop agente v1.4 con self-healing integrato
│   ├── config.py              # config + path OneDrive-aware
│   ├── memory.py              # memoria breve/lungo termine
│   ├── bootstrap.py           # auto-install dipendenze all'avvio
│   ├── self_heal.py           # SelfHealEngine: search + patch + hot-reload
│   │
│   ├── tools/
│   │   ├── registry.py        # dispatcher tool
│   │   ├── sys_exec.py        # shell Windows (cmd /c)
│   │   ├── file_ops.py        # file read/write/list/delete
│   │   ├── browser.py         # Playwright browser
│   │   ├── input_control.py   # PyAutoGUI mouse + tastiera
│   │   ├── windows_apps.py    # launch/focus app Windows
│   │   ├── web_search.py      # Perplexity / DuckDuckGo
│   │   ├── code_runner.py     # esecuzione Python
│   │   └── roblox.py          # integrazione Roblox Studio
│   │
│   ├── ui/
│   │   ├── gui.py             # GUI PySide6 con output ragionamenti
│   │   └── console.py         # UI terminale fallback
│   │
│   └── plugins/
│       ├── base.py            # PluginBase abstract class
│       └── loader.py          # auto-discovery plugin
│
├── agents/
│   ├── agent_system_prompt.md
│   ├── agent_fast.md
│   └── agent_research.md
│
├── config/
│   ├── models.json            # config modelli (legacy PyGPT reference)
│   └── profile.json
│
├── docs/
│   ├── fase1.md               # stato Fase 1.0
│   ├── fase2.md               # piano K3s cloud
│   └── troubleshooting.md     # fix problemi noti
│
└── prompts/
    ├── file_ops.md
    └── pygpt_builder_prompt.md
```

---

## Quick Start

### 1. Clona
```powershell
git clone https://github.com/Tenkulo/dustai.git
cd dustai
```

### 2. Setup (una volta sola)
```powershell
install.bat
```
Il setup:
- Verifica Python 3.10+
- Installa tutte le dipendenze pip
- Installa Playwright + Chromium
- Avvia Bootstrap che installa Ollama e scarica i modelli
- Crea `%APPDATA%\dustai\.env` e lo apre per inserire le API keys

### 3. Configura API keys
Apri `%APPDATA%\dustai\.env` e inserisci:
```
GOOGLE_API_KEY=la_tua_key_da_aistudio.google.com
PERPLEXITY_API_KEY=la_tua_key_da_perplexity.ai
```

### 4. Avvia
```powershell
run.bat
# oppure
python run.py --gui     # GUI PySide6
python run.py --console # terminale
```

---

## Stack Tecnologico

| Layer | Tecnologia | Versione | Costo |
|---|---|---|---|
| GUI | PySide6 | 6.6+ | €0 |
| Modello primario | Gemini 2.5 Flash | API Google | €0 free tier |
| Modello pesante | Gemini 2.5 Pro | API Google | ~€0.001/query |
| Ricerca web | Perplexity Sonar Pro | API | key esistente |
| Modello locale | qwen3:8b | Ollama | €0 |
| Fallback locale | mistral-small3.1 | Ollama | €0 |
| Browser automation | Playwright + Chromium | 1.40+ | €0 |
| Computer Use | PyAutoGUI | 0.9+ | €0 |
| Self-healing | SelfHealEngine custom | v1.0 | €0 |

---

## Funzionalità Self-Healing

Quando un tool fallisce, DUST AI agisce autonomamente:

```
🔧 [sys_exec] {"command": "cmd /c mkdir C:\Users\...\Desktop\test"}
   → [stderr] sintassi del nome non corretta [exit code: 1]

🚑 [SelfHeal] Tentativo 1/3...
   🔍 Ricerca: Python Windows OneDrive Desktop path fix 2024
   🔍 Ricerca: cmd mkdir stderr sintassi Windows fix
   💡 Strategia: params_correction (confidence: 87%)
   📝 Path Desktop errato — OneDrive sposta Desktop
   ✏️  Params corretti: {"command": "cmd /c mkdir \"C:\Users\ugopl\OneDrive\Desktop\test\""}
   🔁 Riprovo...
   → [comando eseguito] ✅
```

Se la correzione params non basta, genera una **code patch** al file sorgente, mostra il diff, fa **hot-reload** del modulo e riprova — tutto senza riavviare.

---

## Roadmap

| Fase | Stato | Autonomia stimata |
|---|---|---|
| 1.0 Bootstrap Locale | ✅ Attiva | ~88% |
| 1.1 GUI + SelfHeal + Bootstrap auto | 🟡 In rilascio | ~93% |
| 1.2 Ollama pull resiliente + crash recovery | 🟡 In sviluppo | ~94% |
| 2.0 Dual-Tenant K3s (Oracle EU-FRA + US-ASH) | ⬜ Pianificata | ~96% |
| 3.0 Zero-Load Permanente | ⬜ Futura | >98% |

---

## Problemi Noti

Vedi [`docs/troubleshooting.md`](docs/troubleshooting.md)

---

## Licenza

MIT — libero uso personale e commerciale.
