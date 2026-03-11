# DUST AI – Troubleshooting

Tutti i problemi incontrati e le soluzioni verificate. Aggiornato a v1.4.

---

## ❌ 429 RESOURCE_EXHAUSTED – Gemini

**Sintomo:**
```
Quota exceeded for metric: generate_content_free_tier_requests
```

**Causa:** Free tier Gemini 2.5 Flash: 5 req/min. Gemini 2.5 Pro: limite 0 su free tier.

**Fix automatico (v1.1+):** l'agent aspetta il retry-delay estratto dall'errore e riprova.  
**Fix manuale:** aspetta qualche minuto, oppure attiva pay-as-you-go su [aistudio.google.com](https://aistudio.google.com).  
**Fallback:** se Ollama è installato, l'agent switcha automaticamente su `qwen3:8b` locale.

---

## ❌ Desktop non trovato / path sbagliato

**Sintomo:** L'agent crea file in `C:\Users\ugopl\Desktop` invece di `C:\Users\ugopl\OneDrive\Desktop`.

**Causa:** OneDrive reindirizza il Desktop. `%USERPROFILE%\Desktop` è vuoto, quello reale è su OneDrive.

**Fix (v1.3+):** `Config.get_desktop()` rileva automaticamente il path OneDrive e lo inietta nel system prompt. L'agent non deve più usare `echo %USERPROFILE%\Desktop`.

**Verifica manuale:**
```powershell
echo %OneDrive%\Desktop
# deve stampare: C:\Users\ugopl\OneDrive\Desktop
```

---

## ❌ Agent in loop "sto aspettando il risultato"

**Sintomo:** L'agent ripete 10+ volte "sono in attesa del risultato del comando sys_exec".

**Causa:** Tool call eseguita ma risultato non tornato correttamente al modello.

**Fix (v1.2+):** stall detection — dopo 2 risposte consecutive con "in attesa", l'agent fa abort e mostra il messaggio di errore.

---

## ❌ Ollama pull crasha a metà download

**Sintomo:** Il Bootstrap va in crash durante `ollama pull qwen3:8b`.

**Causa:** `subprocess.run` con timeout fisso — se la rete è lenta o il modello è grande, il processo viene killato.

**Fix temporaneo:** esegui il pull manualmente dal terminale:
```powershell
ollama pull qwen3:8b
# oppure il modello più leggero:
ollama pull qwen2.5:3b
```
**Fix permanente (v1.5 in sviluppo):** migrazione a Ollama SDK con streaming, nessun timeout fisso.

---

## ❌ `No module named 'src'`

**Sintomo:** DUST AI crasha all'avvio con `ModuleNotFoundError: No module named 'src'`.

**Causa:** `gui.py` o `run.py` avviati dalla directory sbagliata, oppure `ROOT` nel path non punta alla root del progetto.

**Fix:** avvia sempre da `A:\dustai`:
```powershell
cd A:\dustai
python run.py
```
Oppure usa `run.bat` che imposta la directory correttamente.

---

## ❌ PySide6 non trovato

**Sintomo:** `ImportError: No module named 'PySide6'`

**Fix:** il Bootstrap lo installa automaticamente. Se vuoi farlo manualmente:
```powershell
pip install PySide6>=6.6.0
```

---

## ❌ Playwright / Chromium non installato

**Sintomo:** `playwright._impl._errors.Error: Executable doesn't exist`

**Fix:**
```powershell
pip install playwright
python -m playwright install chromium
```

---

## ❌ Ollama non raggiungibile (porta 11434)

**Sintomo:** `ConnectionRefusedError` o `httpx.ConnectError`

**Fix:**
```powershell
# Avvia il servizio Ollama
ollama serve
# Verifica modelli
ollama list
# Se qwen3:8b non c'è
ollama pull qwen3:8b
```

---

## ❌ iGPU AMD non utilizzata da Ollama

**Sintomo:** Ollama usa solo CPU, inferenza lenta.

**Fix:** imposta le variabili d'ambiente (il Bootstrap lo fa automaticamente):
```powershell
[System.Environment]::SetEnvironmentVariable("OLLAMA_GPU_LAYERS", "18", "User")
[System.Environment]::SetEnvironmentVariable("OLLAMA_NUM_GPU", "1", "User")
```
Poi riavvia Ollama.

---

## ❌ GUI apre ma non genera output

**Causa nota pre-v1.2:** `send_message()` nella GUI non chiamava l'agent.  
**Fix (v1.2+):** `AgentWorker` thread collegato all'agent con hook su `tools.execute` e `_call_model` per output in tempo reale.

---

## ❌ git `&&` non funziona in PowerShell

**Causa:** PowerShell non supporta `&&` come separatore.

**Fix:** esegui i comandi separati:
```powershell
git add .
git commit -m "messaggio"
git push origin master
```
