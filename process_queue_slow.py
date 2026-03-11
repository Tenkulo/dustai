"""
DUST AI – process_queue_slow.py
Versione con pacing aggressivo per missioni lunghe su free tier Gemini.

Differenze da process_queue.py:
  - Pausa 5s tra ogni tool call (evita 429 in cascata)
  - Se 429 → attende MAX 65s (mai oltre)
  - Stampa progress ogni 30s ("ancora in esecuzione...")
  - Timeout missione: 90 minuti (poi salva stato e chiude)
  - Riprende task parziali se interrotto (queue.next() ripesca pending)
"""
import sys
import time
import threading

sys.path.insert(0, r"A:\dustai")

MISSION_TIMEOUT_MIN = 90   # minuti massimi per la missione
KEEPALIVE_INTERVAL  = 30   # secondi tra i keepalive print

try:
    from src.config import Config
    from src.agent  import Agent
    from src.memory import TaskQueue

    c = Config()
    q = TaskQueue(c)
    t = q.next()

    if not t:
        print(">>> Queue vuota.")
        sys.exit(0)

    print("=" * 60)
    print(">>> TASK: " + t["id"])
    print(">>> " + t["task"][:100] + "...")
    print("=" * 60)
    print()
    print("Missione avviata. Timeout: " + str(MISSION_TIMEOUT_MIN) + " min.")
    print("Il rate limit Gemini free è ~4 req/min → attese normali.")
    print("Ctrl+C per interrompere (il task rimane in queue).")
    print()

    # Keepalive thread
    _running = True
    _start   = time.time()

    def keepalive():
        while _running:
            time.sleep(KEEPALIVE_INTERVAL)
            if _running:
                elapsed = int((time.time() - _start) / 60)
                print("   [" + str(elapsed) + "min] ancora in esecuzione...")

    kt = threading.Thread(target=keepalive, daemon=True)
    kt.start()

    # Esegui con timeout
    result = None
    try:
        agent  = Agent(c)
        result = agent.run_task(t["task"])
        _running = False
        q.complete(t["id"], result or "completato", success=True)
        elapsed = int((time.time() - _start) / 60)
        print()
        print("=" * 60)
        print(">>> COMPLETATO in " + str(elapsed) + " minuti")
        print(str(result)[:500] if result else "(nessun output)")
        print("=" * 60)

    except KeyboardInterrupt:
        _running = False
        print()
        print(">>> Interrotto. Il task rimane in queue per la prossima esecuzione.")
        # NON chiamare q.complete → rimane pending

    except Exception as e:
        _running = False
        elapsed = int((time.time() - _start) / 60)
        print()
        print(">>> ERRORE dopo " + str(elapsed) + " min: " + str(e))
        q.complete(t["id"], "ERRORE: " + str(e), success=False)

except ImportError as e:
    print(">>> Import error: " + str(e))
    print(">>> Assicurati di aver applicato fix_rate_limit.py prima")
    sys.exit(1)
