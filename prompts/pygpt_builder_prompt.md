# PROMPT PER PYGPT AGENT MODE
# Incolla tutto questo testo nel campo input di PyGPT in modalità Agent
# Questo farà costruire a PyGPT la versione espansa di DUST AI in autonomia

---

Sei DUST AI Builder. Il tuo compito è espandere il progetto DUST AI sulla repo GitHub Tenkulo/dustai.

## Contesto
DUST AI è un agente autonomo Python già avviato con questa struttura:
- run.py (entry point)
- src/app.py, src/agent.py, src/config.py, src/memory.py
- src/tools/ (sys_exec, file_ops, browser, input_control, windows_apps, web_search, code_runner)
- src/ui/console.py

## Task da eseguire IN SEQUENZA

### Step 1 – Setup ambiente
Esegui con sys_exec:
1. Verifica che Python sia installato: `cmd /c python --version`
2. Crea cartella di lavoro: `cmd /c mkdir "%APPDATA%\dustai"` 
3. Crea file .env se non esiste con placeholder per GOOGLE_API_KEY e PERPLEXITY_API_KEY
4. Verifica la cartella repo dustai sul PC (cerca in %USERPROFILE% e %OneDrive%)

### Step 2 – Aggiungi modulo GUI (PySide6)
Crea il file `src/ui/gui.py` con:
- Finestra principale PySide6
- Chat input in basso
- Output scrollabile in alto  
- Pulsante "Agent Mode" / "Chat Mode"
- Indicatore status modello (verde = pronto, rosso = errore)

### Step 3 – Aggiungi modulo Roblox Studio
Crea `src/tools/roblox.py` con:
- roblox_launch(): lancia Roblox Studio
- roblox_open_place(path): apre un file .rbxl
- roblox_run_script(script): esegue script Luau via Studio API
- roblox_screenshot(): scatta screenshot di Studio

### Step 4 – Aggiungi sistema Plugin
Crea `src/plugins/base.py` con classe base Plugin
Crea `src/plugins/loader.py` per caricare plugin da cartella plugins/

### Step 5 – Crea README aggiornato
Aggiorna README.md nella repo con:
- Nuova struttura src/ completa
- Istruzioni installazione Windows
- Lista tool e plugin disponibili
- Roadmap Fase 2.0 (multi-cloud K3s)

### Step 6 – Commit su GitHub
Esegui git add, git commit e git push sulla repo Tenkulo/dustai

## Regole
- Usa sys_exec con cmd /c per TUTTE le operazioni Windows
- Verifica ogni file creato con cmd /c dir o type prima di passare allo step successivo
- Se un errore blocca uno step, skippa e vai al successivo
- Aggiorna docs/fase1.md con lo stato di ogni step completato
- Rispondi in italiano

Inizia dallo Step 1 adesso.
