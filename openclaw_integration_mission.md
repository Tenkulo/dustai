# DUST AI — MISSIONE AUTONOMA: Studia OpenClaw e Riscrivi DUST 2.0
# Questo file va inserito nella TaskQueue come task priorità 0
# DUST lo esegue completamente in autonomia, senza supervisione umana
# Tempo stimato: 45-90 minuti di elaborazione autonoma

---

## CONTESTO

Hai accesso a due progetti:
- **DUST AI** (te stesso): `A:\dustai\` — AI agent Python per Windows 11
- **OpenClaw**: `A:\OpenClaw\openclaw\` — AI assistant TypeScript con architettura avanzata

Il tuo obiettivo è capire OpenClaw a fondo, estrarne i pattern migliori,
e riscrivere DUST 2.0 in `A:\dustai2\` incorporando quei pattern.
DUST 2.0 deve essere installabile ed eseguibile con `A:\dustai2\install.bat`.

---

## FASE 1 — MAPPATURA OPENCLAW (usa file_read + file_list)

### 1.1 Struttura del repo
```
Esegui:
  file_list("A:\OpenClaw\openclaw")
  file_list("A:\OpenClaw\openclaw\src")
```
Obiettivo: capire la struttura top-level e le directory principali.

### 1.2 File identità e architettura
Leggi in sequenza questi file (se esistono):
```
file_read("A:\OpenClaw\openclaw\README.md")
file_read("A:\OpenClaw\openclaw\SOUL.md")
file_read("A:\OpenClaw\openclaw\IDENTITY.md")
file_read("A:\OpenClaw\openclaw\BOOTSTRAP.md")
file_read("A:\OpenClaw\openclaw\HEARTBEAT.md")
file_read("A:\OpenClaw\openclaw\MEMORY.md")
file_read("A:\OpenClaw\openclaw\AGENTS.md")
file_read("A:\OpenClaw\openclaw\TOOLS.md")
file_read("A:\OpenClaw\openclaw\CRON.json")
```
Per ogni file: estrai in 3 righe cosa fa, poi vai avanti.

### 1.3 Codice sorgente — entry points
```
file_list("A:\OpenClaw\openclaw\src")
file_list("A:\OpenClaw\openclaw\src\core")
```
Leggi i primi 3 file .ts o .js più importanti nella root src.
Cerca: come gestisce il loop principale, come chiama i tool, come persiste memoria.

### 1.4 Skills system
```
file_list("A:\OpenClaw\openclaw\skills")
```
Leggi 2-3 SKILL.md di esempio. Comprendi il formato.
Cerca: come definisce i tool, come li invoca, come compone le pipeline.

### 1.5 Gateway / Daemon
Cerca file con: gateway, daemon, server, websocket nel nome.
Leggi il principale. Capisci come rimane in esecuzione persistente.

---

## FASE 2 — ANALISI COMPARATIVA

Dopo aver letto OpenClaw, scrivi in `A:\dustai_stuff\openclaw_analysis.txt`:

```
=== ANALISI OPENCLAW vs DUST ===

## Componenti OpenClaw utili per DUST
Per ogni componente trovato:
  NOME: [nome componente]
  COSA FA: [1 riga]
  COME IMPLEMENTARLO IN PYTHON: [1 riga]
  PRIORITÀ: alta|media|bassa
  FILE OPENCLAW: [path]

## Pattern architetturali superiori a DUST
[lista con spiegazione]

## Cose che DUST fa già meglio
[lista]

## Gap critici di DUST che OpenClaw risolve
[lista ordinata per impatto]
```

---

## FASE 3 — PIANO DUST 2.0

Basandoti sull'analisi, crea `A:\dustai_stuff\dust2_plan.json`:

```json
{
  "version": "2.0.0",
  "philosophy": "frase che descrive DUST 2.0",
  "openclaw_patterns_adopted": [
    {
      "pattern": "nome pattern",
      "openclaw_source": "file o componente OpenClaw",
      "dust_implementation": "come viene implementato in Python",
      "file_target": "src/... dove va nel codice DUST"
    }
  ],
  "new_components": [
    {
      "name": "nome",
      "description": "cosa fa",
      "inspired_by": "componente OpenClaw",
      "file": "src/..."
    }
  ],
  "directory_structure": {
    "A:\\dustai2\\": "root progetto",
    "...": "..."
  }
}
```

**Pattern minimi da includere (ispirati a OpenClaw):**

1. **SOUL.md** → `A:\dustai2\SOUL.md`
   File identità persistente. Chi è DUST, i suoi valori, i suoi obiettivi.
   OpenClaw lo usa come system prompt permanente. DUST deve leggerlo ad ogni avvio.

2. **HEARTBEAT** → `src/heartbeat.py`
   Processo daemon che ogni 60s: verifica API, aggiorna self_profile, processa queue,
   lancia ciclo di auto-miglioramento se necessario. Come il heartbeat di OpenClaw.

3. **SKILL.md format** → `A:\dustai2\skills\[nome]\SKILL.md`
   Ogni skill di DUST come file .md con: nome, descrizione, tool_calls, esempio.
   SkillForge le legge, le indicizza, le inietta nel contesto.

4. **CRON scheduler** → `src/cron_scheduler.py`
   Come OpenClaw CRON.json: task schedulati (es. ogni ora backup memoria,
   ogni mattina report goal progress, ogni notte self-improvement cycle).

5. **Gateway pattern** → `src/gateway.py`
   Processo persistente in background (Thread daemon). Riceve task via:
   - CLI: `python A:\dustai2\cli.py "task"`
   - TaskQueue file watch
   - (opzionale) HTTP localhost:18790

6. **Channel abstraction** → `src/channels/`
   Come OpenClaw supporta WhatsApp/Telegram/Slack.
   DUST supporta: GUI (PySide6), CLI, TaskQueue file, (opzionale) Telegram bot.

---

## FASE 4 — SCRITTURA DUST 2.0

Ora scrivi DUST 2.0 in `A:\dustai2\`. Usa sys_exec + file_write.

### 4.1 Crea struttura directory
```
sys_exec("cmd /c mkdir A:\dustai2")
sys_exec("cmd /c mkdir A:\dustai2\src")
sys_exec("cmd /c mkdir A:\dustai2\src\agents")
sys_exec("cmd /c mkdir A:\dustai2\src\tools")
sys_exec("cmd /c mkdir A:\dustai2\src\channels")
sys_exec("cmd /c mkdir A:\dustai2\skills")
sys_exec("cmd /c mkdir A:\dustai2\agents")
sys_exec("cmd /c mkdir A:\dustai_stuff\logs")
sys_exec("cmd /c mkdir A:\dustai_stuff\memory")
sys_exec("cmd /c mkdir A:\dustai_stuff\skills")
sys_exec("cmd /c mkdir A:\dustai_stuff\profiles")
sys_exec("cmd /c mkdir A:\dustai_stuff\tasks")
sys_exec("cmd /c mkdir A:\dustai_stuff\screenshots")
sys_exec("cmd /c mkdir A:\dustai_stuff\patches")
```

### 4.2 SOUL.md — identità permanente (ispirato a OpenClaw)
Scrivi `A:\dustai2\SOUL.md` con:
- Chi sei: DUST AI v2.0, AI agent Python per Windows 11
- I tuoi valori: autonomia, precisione, auto-miglioramento continuo
- I tuoi obiettivi: i 8 goal del progetto
- Come lavori: tool calling reale, mai narrativa, sempre verifica
- Come impari: SkillForge dopo ogni task, SelfImprovement ogni 10 task
- Cosa NON fai: simulare azioni, "Eseguirò...", loop infiniti
- Il tuo sistema operativo interiore: HEARTBEAT, TaskQueue, GoalPursuit
Formato: markdown libero, max 200 righe. Scritto in prima persona.

### 4.3 Copia e aggiorna file da DUST 1.x
Copia da `A:\dustai\src\` a `A:\dustai2\src\` i seguenti file
(usando sys_exec con xcopy o copy):
```
config.py, agent.py, ollama_caller.py, self_heal.py, memory.py,
prompt_manager.py, debugger.py
src/tools/: registry.py, sys_exec.py, file_ops.py, vision.py,
            web_search.py, input_control.py, browser.py,
            windows_apps.py, code_runner.py
src/agents/: orchestrator.py, self_improvement_loop.py, goal_pursuit.py
src/ui/: gui.py
budget_monitor.py
```

### 4.4 Scrivi i nuovi file (pattern OpenClaw)

**`A:\dustai2\src\heartbeat.py`**
Daemon thread che ogni 60s esegue in sequenza:
1. HealthChecker.check_all() → se fallisce → SelfHeal
2. TaskQueue.pending_count() → se > 0 → avvisa GUI
3. self._task_counter += 1 → se >= 10 → SelfImprovementLoop.run_cycle()
4. GoalPursuit.generate_tasks_for_gaps() → ogni 600s (10 cicli)
5. CronScheduler.check_due() → esegui job schedulati
6. Scrive A:\dustai_stuff\heartbeat.json con timestamp + stato

Avviato in background da `run.py` con `heartbeat.start()`.
Si ferma con `heartbeat.stop()` o Ctrl+C.

**`A:\dustai2\src\cron_scheduler.py`**
Legge `A:\dustai2\CRON.json` (formato ispirato a OpenClaw):
```json
[
  {
    "id": "morning_report",
    "schedule": "0 8 * * *",
    "task": "Genera report giornaliero: goal progress + budget token + task completati ieri",
    "enabled": true
  },
  {
    "id": "nightly_backup",
    "schedule": "0 2 * * *",
    "task": "Backup A:\\dustai_stuff\\memory\\ in A:\\dustai_stuff\\backups\\",
    "enabled": true
  },
  {
    "id": "self_improve",
    "schedule": "0 */6 * * *",
    "task": "Esegui ciclo auto-miglioramento se task_count >= 5",
    "enabled": true
  },
  {
    "id": "goal_check",
    "schedule": "0 12 * * *",
    "task": "Valuta stato goal e genera task per quelli non raggiunti",
    "enabled": true
  }
]
```
Usa `croniter` per calcolare next run. Persiste last_run in JSON.

**`A:\dustai2\src\gateway.py`**
Gateway daemon (ispirato a OpenClaw gateway):
- Avvia un server HTTP minimale su localhost:18790 (usa `http.server`)
- Endpoint POST /task → aggiunge task alla queue
- Endpoint GET /status → ritorna stato agente (modello, task_count, goal_score)
- Endpoint GET /heartbeat → ritorna ultimo heartbeat.json
- CLI: `python A:\dustai2\cli.py "task"` → POST a gateway
- Opzionale: watch file `A:\dustai_stuff\tasks\incoming.txt` ogni 5s

**`A:\dustai2\src\channels\cli_channel.py`**
Interfaccia CLI minimale (ispirato a OpenClaw CLI):
```
python A:\dustai2\cli.py "che ore sono"
python A:\dustai2\cli.py --mode chat "dimmi qualcosa"
python A:\dustai2\cli.py --queue "task da aggiungere alla coda"
python A:\dustai2\cli.py --status
python A:\dustai2\cli.py --goals
python A:\dustai2\cli.py --budget
```

**`A:\dustai2\skills\`** — skill library format OpenClaw
Crea queste skill in formato SKILL.md (compatibile con OpenClaw):

`A:\dustai2\skills\file_manager\SKILL.md`:
```markdown
# file_manager
Gestisce operazioni su file e directory Windows.
## Tools
- file_read(path) → legge file
- file_write(path, content) → scrive file
- file_list(path) → lista directory
- file_copy(src, dst) → copia
- file_move(src, dst) → sposta
- file_delete(path) → elimina
## Esempio
Task: "Crea un file report.txt sul desktop"
→ file_write("C:\Users\ugopl\OneDrive\Desktop\report.txt", contenuto)
```

`A:\dustai2\skills\system_control\SKILL.md`:
```markdown
# system_control
Esegue comandi Windows, gestisce processi, controlla applicazioni.
## Tools
- sys_exec(cmd) → esegue comando shell
- app_launch(name) → avvia applicazione
- app_focus(name) → porta in primo piano
- kill_process(name) → termina processo
## Pattern chiave
- Usa sempre cmd /c per comandi Windows
- Per path con spazi: "cmd /c dir \"C:\Program Files\""
```

`A:\dustai2\skills\web_researcher\SKILL.md`:
```markdown
# web_researcher
Ricerca informazioni online con budget ottimizzato.
## Tools
- web_search(query) → Perplexity Sonar (auto routing sonar/pro)
- browser_open(url) → apre pagina
- browser_get_text(selector) → estrae testo
## Budget
- sonar: ~€0.006/query
- sonar-pro: max 10/mese, solo per query complesse
```

`A:\dustai2\skills\vision_gui\SKILL.md`:
```markdown
# vision_gui
Automatizza GUI Windows tramite screenshot + analisi visiva.
## Tools
- screenshot() → cattura schermo
- vision_analyze(task) → analizza screenshot con Gemini Vision
- find_element(description) → trova elemento UI
- mouse_click(x, y) → click
- keyboard_type(text) → digita
- keyboard_hotkey(keys) → combinazione tasti
## Workflow
1. screenshot() → vedi stato schermo
2. find_element("pulsante OK") → ottieni coordinate
3. mouse_click(x, y) → clicca
```

### 4.5 Aggiorna run.py
`A:\dustai2\run.py` deve:
1. Importare Config, Agent, Heartbeat, Gateway, GUI
2. Avviare Heartbeat in background
3. Avviare Gateway in background
4. Processare TaskQueue pending (bootstrap se primo avvio)
5. Avviare GUI (blocca fino a chiusura)
6. All'uscita: fermare Heartbeat e Gateway

### 4.6 Crea install.bat
`A:\dustai2\install.bat`:
```batch
@echo off
echo === DUST AI 2.0 - Installazione ===

REM Crea struttura
mkdir A:\dustai_stuff\logs 2>nul
mkdir A:\dustai_stuff\memory 2>nul
mkdir A:\dustai_stuff\skills 2>nul
mkdir A:\dustai_stuff\profiles 2>nul
mkdir A:\dustai_stuff\tasks 2>nul
mkdir A:\dustai_stuff\screenshots 2>nul
mkdir A:\dustai_stuff\patches 2>nul
mkdir A:\dustai_stuff\backups 2>nul

REM Dipendenze Python
pip install --upgrade pip
pip install google-generativeai==0.8.0
pip install ollama pydantic>=2.0.0 instructor>=1.0.0
pip install PySide6 pyautogui pyperclip
pip install mss pillow psutil requests
pip install croniter
pip install playwright && python -m playwright install chromium

REM Copia .env template se non esiste
if not exist A:\dustai_stuff\.env (
  copy A:\dustai2\.env.example A:\dustai_stuff\.env
  echo ATTENZIONE: Configura le API keys in A:\dustai_stuff\.env
)

echo === Installazione completata ===
echo Avvia con: python A:\dustai2\run.py
pause
```

### 4.7 Crea .env.example
`A:\dustai2\.env.example`:
```
# DUST AI 2.0 — Configurazione API Keys
# Copia questo file in A:\dustai_stuff\.env e compila

# Google Gemini — Progetto 1 (primary, Flash, task principali)
GOOGLE_API_KEY=inserisci_qui

# Google Gemini — Progetto 2 (research, Flash-Lite, reflection/verify)
GOOGLE_API_KEY_2=inserisci_qui

# Google Gemini — Progetto 3 (heavy, Pro, planning complesso)
GOOGLE_API_KEY_3=inserisci_qui

# Perplexity — ricerche web (€5/mese budget)
PERPLEXITY_API_KEY=inserisci_qui

# Ollama — URL locale (default: http://localhost:11434)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:8b
```

---

## FASE 5 — VERIFICA E TEST

Dopo aver scritto tutti i file:

### 5.1 Verifica sintassi Python
```
sys_exec("python -c \"import ast; import os; errors=[];\n[errors.append(f) for f in __import__('glob').glob('A:/dustai2/src/**/*.py', recursive=True) if ast.parse(open(f).read()) or False]; print('OK' if not errors else errors)")
```
Oppure: `sys_exec("python -m py_compile A:\dustai2\run.py")`

### 5.2 Test import base
```
code_run("import sys; sys.path.insert(0,'A:/dustai2'); from src.config import Config; c=Config(); print('Config OK:', c.get_base_path())")
```

### 5.3 Test agent minimale
```
code_run("import sys; sys.path.insert(0,'A:/dustai2'); from src.config import Config; from src.agent import Agent; a=Agent(Config()); r=a.chat('rispondi solo: DUST_2_OK'); print(r)")
```

### 5.4 Test heartbeat avvio
```
code_run("import sys,time; sys.path.insert(0,'A:/dustai2'); from src.config import Config; from src.heartbeat import Heartbeat; h=Heartbeat(Config(),None); h.start(); time.sleep(3); h.stop(); print('Heartbeat OK')")
```

---

## FASE 6 — REPORT FINALE

Scrivi `A:\dustai_stuff\dust2_completion_report.txt` con:

```
=== DUST AI 2.0 — Report Completamento ===
Data: [timestamp]

## File scritti
[lista con path e dimensione]

## Pattern OpenClaw integrati
[lista con descrizione]

## Stato verifiche
- Sintassi Python: OK/FAIL
- Import Config: OK/FAIL
- Test agent: OK/FAIL
- Test heartbeat: OK/FAIL

## Come avviare
1. python A:\dustai2\install.bat  (prima installazione)
2. python A:\dustai2\run.py       (avvio normale)
3. python A:\dustai2\cli.py "task" (da terminale)

## Differenze DUST 1.x → 2.0
[lista delle differenze principali]

## Prossimi miglioramenti autonomi pianificati
[lista da GoalPursuit]
```

---

## REGOLE OPERATIVE (per questa missione)

1. **Leggi prima di scrivere**: leggi TUTTO il repo OpenClaw prima di scrivere una riga di DUST 2.0
2. **Ogni file_write → verifica con file_read** che il contenuto sia stato scritto correttamente
3. **Niente narrativa**: ogni output deve essere il risultato di un tool call reale
4. **Se un file OpenClaw non esiste**: adatta il piano, non fermarti
5. **Se un tool fallisce**: usa SelfHeal, prova approccio alternativo, non ignorare
6. **Mantieni DUST 1.x intatto**: scrivi DUST 2.0 SOLO in `A:\dustai2\`, mai sovrascrivere `A:\dustai\`
7. **Git finale**: se git è disponibile, commit tutto su branch `v2.0-openclaw`

---

## CRITERI DI SUCCESSO

La missione è completata quando:
- [ ] `A:\dustai2\install.bat` esiste ed è eseguibile
- [ ] `A:\dustai2\run.py` avvia senza errori
- [ ] `A:\dustai2\SOUL.md` esiste con identità DUST
- [ ] `A:\dustai2\src\heartbeat.py` esiste e si avvia
- [ ] `A:\dustai2\src\cron_scheduler.py` esiste con CRON.json
- [ ] `A:\dustai2\src\gateway.py` esiste con CLI
- [ ] `A:\dustai2\skills\` ha almeno 4 skill in formato SKILL.md
- [ ] `A:\dustai_stuff\openclaw_analysis.txt` documenta cosa hai imparato
- [ ] `A:\dustai_stuff\dust2_completion_report.txt` esiste

Dichiari completato con:
{"status": "done", "summary": "DUST 2.0 scritto in A:\\dustai2\\. Pattern OpenClaw integrati: [lista]. Avvia con: python A:\\dustai2\\run.py"}
