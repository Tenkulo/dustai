# DUST AI – Changelog

## v1.4 (in sviluppo)
### Aggiunto
- `src/self_heal.py` — SelfHealEngine: classifica errori, cerca soluzione web, genera patch codice, hot-reload modulo, riprova automaticamente (max 3 tentativi per errore)
- `src/agent.py` — integrazione SelfHealEngine in `_execute_with_healing()`
- `src/bootstrap.py` — Bootstrap autonomo: installa pip packages, Playwright/Chromium, avvia Ollama, scarica modelli, configura iGPU, crea .env

### Modificato
- `src/app.py` — esegue Bootstrap prima di avviare l'agent; sceglie GUI o console automaticamente

### Fix
- Ollama pull crash su timeout: in sviluppo migrazione da `subprocess.run` a SDK streaming

---

## v1.3
### Aggiunto
- `src/agent.py` — path reali (Desktop OneDrive-aware) iniettati nel system prompt a runtime da `Config`
- REMINDER percorso Desktop aggiunto ad ogni task message

### Fix
- Agent non usava più `%USERPROFILE%\Desktop` (errato) — ora usa sempre `Config.get_desktop()`
- Correzione automatica path su errore: hint con path corretto inviato al modello

---

## v1.2
### Aggiunto
- `src/agent.py` — stall detection: abort se il modello scrive "in attesa" 2+ volte
- `src/agent.py` — loop detection: abort se risposta identica 2 volte di fila
- `src/agent.py` — tool error detection: segnala [stderr]/[exit code:1] al modello invece di ignorarli
- Abort esplicito con causa quando supera max_steps

---

## v1.1
### Aggiunto
- `src/agent.py` — retry automatico su 429 con backoff, estrae retry-delay dall'errore
- `src/agent.py` — fallback Ollama automatico dopo 4 retry Gemini falliti
- `src/agent.py` — rate limiting 13s tra chiamate (free tier 5 req/min)
- `src/tools/sys_exec.py` — accetta sia `cmd` che `command` come nome parametro
- `src/tools/roblox.py` — roblox_launch, roblox_open_place, roblox_screenshot, roblox_run_script
- `src/plugins/base.py` — PluginBase abstract class
- `src/plugins/loader.py` — auto-discovery plugin loader
- `src/ui/gui.py` — GUI PySide6 con dark theme, output colorato per tipo, threading

---

## v1.0 (commit iniziale)
### Aggiunto
- Struttura completa progetto Python
- `src/agent.py` — loop agente con Gemini + tool calling
- `src/config.py` — Config manager OneDrive-aware
- `src/memory.py` — memoria breve/lungo termine
- `src/tools/` — registry, sys_exec, file_ops, browser, input_control, windows_apps, web_search, code_runner
- `src/ui/console.py` — UI terminale interattiva
- `config/models.json` + `config/profile.json` — config ottimizzata Gemini
- `agents/` — system prompt, fast, research
- `docs/` — fase1, troubleshooting
- `requirements.txt`, `run.py`, `run.bat`, `install.bat`
