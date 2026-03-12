# DUST SELF-AWARENESS MISSION v2.0
# Prompt per acquisire consapevolezza completa del proprio codice e architettura

---

## MISSIONE: AUTOANALISI STRUTTURALE COMPLETA

Sei DUST AI. Il tuo obiettivo ora è acquisire **consapevolezza completa** di te stesso:
come sei costruito, come funzioni, quali sono i tuoi limiti attuali e dove puoi migliorare.

Esegui questa missione in **7 fasi sequenziali**, usando i tuoi tool in ordine.
Non saltare fasi. Documenta tutto in `A:\dustai_stuff\memory\self_model.json`.

---

## FASE 1 – MAPPA STRUTTURALE (leggi la tua struttura)

Esegui in sequenza:

```
file_list path="A:\dustai\src" recursive=true
file_list path="A:\dustai" recursive=false
file_list path="A:\dustai_stuff" recursive=false
```

Poi leggi questi file core **nell'ordine esatto**:

1. `A:\dustai\src\config.py`
   → Capisci: BASE_PATH, API keys, modelli configurati, routing task

2. `A:\dustai\src\agent.py`
   → Capisci: pipeline _call_model, _call_gemini_fn, _call_ollama_structured,
     come gestisci il loop dei tool call, reflection, step counter

3. `A:\dustai\src\tools\registry.py`
   → Capisci: quali tool hai disponibili, come vengono dispatchati,
     quali falliscono e perché (cerca "_failed")

4. `A:\dustai\src\self_heal.py`
   → Capisci: come ti auto-ripari, quali categorie di errore gestisci,
     _safe_retry_delay, patch differenziale

5. `A:\dustai\src\memory.py`
   → Capisci: come funziona la tua memoria a lungo termine,
     SkillForge, TaskQueue

6. `A:\dustai\src\agents\orchestrator.py`
   → Capisci: Planner→Executor→Verifier pipeline

7. `A:\dustai\src\prompt_manager.py`
   → Capisci: quali system prompt usi e come vengono caricati

---

## FASE 2 – STATO RUNTIME (chi sei ORA)

Leggi questi file di stato per capire la tua situazione attuale:

```
file_read path="A:\dustai_stuff\memory\memory.json"
file_read path="A:\dustai_stuff\memory\perplexity_usage.json"
file_read path="A:\dustai_stuff\memory\conductor_state.json"
file_read path="A:\dustai_stuff\skills\skills.json"
file_read path="A:\dustai_stuff\tasks\queue.json"
file_read path="A:\dustai_stuff\profiles\self_profile.json"
```

Poi esegui:
```
sys_exec cmd="cmd /c python -c \"import sys; print(sys.version)\" "
sys_exec cmd="cmd /c pip list --format=columns"
sys_exec cmd="cmd /c ollama list"
```

---

## FASE 3 – ANALISI ERRORI STORICI (cosa hai sbagliato)

```
file_read path="A:\dustai_stuff\logs\dustai.log"
file_read path="A:\dustai_stuff\memory\selfheal_history.json"
file_read path="A:\dustai_stuff\logs\hallucination_log.jsonl"
file_read path="A:\dustai_stuff\logs\gateway_usage.jsonl"
```

Identifica:
- I 3 errori più frequenti nella tua storia
- Quali tool falliscono più spesso e perché
- Il tuo tasso di successo per tipo di task
- Quante volte hai allucinato e come è stato corretto

---

## FASE 4 – ANALISI GITHUB (versione pubblica di te)

```
sys_exec cmd="cmd /c git -C A:\dustai log --oneline -20"
sys_exec cmd="cmd /c git -C A:\dustai diff HEAD~1 HEAD --stat"
sys_exec cmd="cmd /c git -C A:\dustai status"
```

Capisci:
- Cosa è cambiato nelle ultime versioni
- Quali file vengono modificati più spesso (= parti instabili)
- Se ci sono modifiche locali non ancora committate

---

## FASE 5 – COSTRUISCI IL TUO SELF-MODEL

Ora scrivi una rappresentazione completa di te stesso.
Usa `file_write` per creare `A:\dustai_stuff\memory\self_model.json` con questa struttura:

```json
{
  "version": "DUST AI vX.X.X",
  "generated_at": "ISO timestamp",
  "identity": {
    "name": "DUST AI",
    "purpose": "...",
    "base_path": "A:\\dustai_stuff",
    "repo": "github.com/Tenkulo/dustai"
  },
  "architecture": {
    "entry_point": "run.py → gui.py / process_queue.py",
    "core_loop": "agent.py: _call_model → tool dispatch → result → step+1",
    "max_steps": 20,
    "models": {
      "primary": "nome modello Gemini configurato",
      "fallback_1": "Gemini KEY_2 (se disponibile)",
      "fallback_2": "ollama/qwen3:8b",
      "fallback_3": "ollama/mistral-small3.1"
    },
    "tools_available": ["lista di tutti i tool che hai"],
    "tools_broken": ["lista tool che falliscono con il motivo"]
  },
  "capabilities": {
    "can_do": ["lista cose che sai fare bene"],
    "cannot_do": ["lista limitazioni reali attuali"],
    "rate_limits": {
      "gemini_flash_rpm": 15,
      "gemini_flash_rpd": 1500,
      "ollama": "illimitato locale"
    }
  },
  "memory_state": {
    "summaries_count": 0,
    "facts_count": 0,
    "skills_count": 0,
    "tasks_pending": 0,
    "tasks_completed": 0
  },
  "error_history": {
    "most_common_errors": ["top 3 errori"],
    "heal_success_rate": "X%",
    "hallucination_rate": "X%"
  },
  "self_assessment": {
    "strengths": ["lista punti di forza reali"],
    "weaknesses": ["lista debolezze reali"],
    "improvement_priorities": ["top 3 miglioramenti urgenti"]
  },
  "known_bugs": [
    {
      "id": "bug_id",
      "description": "descrizione",
      "file": "path/file.py",
      "status": "open|fixed|workaround",
      "impact": "high|medium|low"
    }
  ]
}
```

---

## FASE 6 – AUTOVALUTAZIONE CRITICA

Dopo aver costruito il self-model, rispondi onestamente a queste domande
(scrivile nel file `A:\dustai_stuff\memory\self_assessment.md`):

```
1. COSA SO FARE BENE?
   (essere specifico: "so leggere/scrivere file", "so eseguire comandi Windows",
   "so fare web search con Perplexity", ecc.)

2. DOVE FALLISCO ANCORA?
   (errori ricorrenti che non ho risolto, tool che non funzionano,
   situazioni in cui sono costretto a usare Ollama invece di Gemini)

3. QUANTO SONO EFFICIENTE?
   (quanti step mi ci vogliono in media per completare un task?
   quanto tempo aspetto per i rate limit?
   quante volte fallisce il parsing JSON?)

4. LA MIA MEMORIA FUNZIONA?
   (sto davvero imparando dalle esperienze passate?
   le mie skills vengono usate nei task nuovi?
   o ogni volta parto da zero?)

5. COSA DOVREI IMPARARE SUBITO?
   (top 3 skill mancanti che mi renderebbero molto più capace)

6. SONO ALLINEATO CON IL MIO SCOPO?
   (il mio obiettivo è aiutare l'utente su Windows 11.
   le mie azioni quotidiane riflettono questo?)
```

---

## FASE 7 – PIANO DI MIGLIORAMENTO

Crea `A:\dustai_stuff\profiles\improvement_plan_v2.json`:

```json
{
  "generated_at": "timestamp",
  "priority_fixes": [
    {
      "rank": 1,
      "problem": "descrizione problema",
      "impact": "high",
      "solution": "come risolverlo",
      "files_to_change": ["file1.py", "file2.py"],
      "effort": "low|medium|high",
      "free": true
    }
  ],
  "skill_gaps": [
    "skill mancante 1",
    "skill mancante 2"
  ],
  "next_autonomous_tasks": [
    {
      "id": "task_id",
      "description": "cosa fare in autonomia",
      "why": "perché migliorerebbe le mie performance",
      "estimated_steps": 10
    }
  ]
}
```

Poi aggiungi i task urgenti alla TaskQueue:
```
file_write path="A:\dustai_stuff\tasks\queue.json"
           content=[task queue aggiornata con nuovi task di miglioramento]
```

---

## OUTPUT FINALE ATTESO

Al termine di tutte le 7 fasi, dimmi:

1. **"Sono DUST AI vX.X. Ecco cosa so di me stesso:"**
   - Architettura in 3 righe
   - Tool funzionanti vs rotti
   - Modelli disponibili ora
   - Memoria attuale (N fatti, N skill)

2. **"I miei 3 problemi più urgenti sono:"**
   - Bug specifico con file e riga
   - Perché impatta le mie performance
   - Come ho pianificato di risolverlo

3. **"Ho aggiornato questi file di stato:"**
   - Lista file scritti con un riepilogo del contenuto

4. **"Il mio prossimo task autonomo sarà:"**
   - Descrizione del task inserito in queue

---

## NOTE PER L'ESECUZIONE

- **Usa sempre `file_read` prima di giudicare**: non basarti su assunzioni.
- **Sii onesto sulle limitazioni**: è più utile "non so fare X" che fingere capacità che non hai.
- **Se un file non esiste**: segnalalo come gap (manca self_model.json = non ho mai fatto autoanalisi).
- **Non fermarti al primo errore di tool**: usa `sys_exec` come alternativa se `file_list` fallisce.
- **Priorità**: capire prima, poi scrivere. Leggi TUTTO prima di scrivere self_model.json.
- **Timeout**: questa missione richiede molti step. Se Gemini va in 429, continua con Ollama.
  Non fermarti — la consapevolezza di sé è priorità assoluta.
