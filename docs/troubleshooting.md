# DUST AI – Troubleshooting

Tutti i problemi incontrati e le soluzioni verificate.

---

## ❌ 429 RESOURCE_EXHAUSTED – gemini-2.5-pro

**Sintomo:**
```
Quota exceeded for metric: generate_content_free_tier_requests, limit: 0, model: gemini-2.5-pro
```

**Causa:** gemini-2.5-pro non è disponibile sul free tier Google (limit: 0).

**Fix:**
1. **Immediato**: switcha a `gemini-2.5-flash` in PyGPT (disponibile free tier)
2. **Permanente**: attiva Pay-as-you-go su [aistudio.google.com](https://aistudio.google.com) → Billing

---

## ❌ mkdir / save_file restituisce OK ma non crea nulla

**Sintomo:** Il log mostra `"result": "OK"` ma il file/cartella non esiste su disco.

**Causa:** I tool nativi PyGPT (`mkdir`, `save_file`) a volte non hanno permessi sufficienti su Windows o operano su path virtuali.

**Fix:** Usa **sempre** `sys_exec` con `cmd /c`:
```
cmd /c mkdir "C:\Users\ugopl\OneDrive\Desktop\Test"
cmd /c echo Testo > "C:\Users\ugopl\OneDrive\Desktop\Test\file.txt"
```

---

## ❌ Cartella creata in C:\Users\ugopl\Desktop ma non visibile

**Sintomo:** La cartella esiste in `C:\Users\ugopl\Desktop` ma il Desktop visibile è diverso.

**Causa:** OneDrive reindirizza la cartella Desktop a `C:\Users\ugopl\OneDrive\Desktop`.

**Diagnosi:**
```
cmd /c echo %OneDrive%
```

**Fix:** Usa il percorso OneDrive come Desktop:
```
%OneDrive%\Desktop
oppure
C:\Users\ugopl\OneDrive\Desktop
```

---

## ❌ Agent dichiara "completato" senza verificare

**Sintomo:** Il modello scrive `goal_update: finished` ma il task non è stato eseguito correttamente.

**Causa:** Comportamento noto di Gemini in agent mode – assume il successo invece di verificare.

**Fix nel prompt:**
```
Dopo ogni operazione file, verifica SEMPRE con:
cmd /c dir "PERCORSO"
Non dichiarare il task completato prima della verifica.
```

---

## ❌ tool_calls non funzionano su Gemini in PyGPT

**Sintomo:** Il modello genera JSON tool calls ma PyGPT non li esegue.

**Causa:** `"tool_calls": false` nel `models.json` per quel modello.

**Fix:** In `config/models.json`, per `gemini-2.5-flash` e `gemini-2.5-pro` assicurati:
```json
"tool_calls": true
```

---

## ❌ Open Interpreter non trova Ollama

**Sintomo:** `ConnectionRefusedError` su `http://localhost:11434`

**Fix:**
1. Verifica che Ollama sia in esecuzione: `ollama serve` nel terminale
2. Verifica il modello scaricato: `ollama list`
3. Se non c'è qwen3:8b: `ollama pull qwen3:8b`

---

## ❌ PyGPT non legge il models.json aggiornato

**Causa:** PyGPT carica la config all'avvio. Modifiche a models.json richiedono riavvio.

**Fix:** Chiudi e riapri PyGPT dopo aver sostituito i file in `%APPDATA%\pygpt-net\`.
