"""
DUST AI – process_queue.py
Eseguito da run.bat prima della GUI.
Processa tutti i task pending (o running interrotti) nella TaskQueue.
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, r"A:\dustai")

try:
    from src.config import Config
    from src.agent  import Agent
    from src.memory import TaskQueue

    c = Config()

    # Fix diretto sul file: rimetti "running" → "pending" (task interrotti)
    queue_file = c.get_tasks_file()
    if queue_file.exists():
        data = json.loads(queue_file.read_text(encoding="utf-8"))
        changed = False
        for t in data:
            if t.get("status") == "running":
                t["status"] = "pending"
                t.pop("started_at", None)
                print(">>> Reset interrotto: " + t["id"])
                changed = True
        if changed:
            queue_file.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )

    q     = TaskQueue(c)
    count = 0

    while True:
        t = q.next()
        if not t:
            break
        count += 1
        print(">>> [" + str(count) + "] Task: " + t["id"])
        print("    " + t["task"][:80] + "...")
        print()
        try:
            result = Agent(c).run_task(t["task"])
            q.complete(t["id"], result, success=True)
            print(">>> OK: " + str(result)[:120])
        except Exception as e:
            q.complete(t["id"], str(e), success=False)
            print(">>> ERRORE: " + str(e))
        print()

    if count == 0:
        print(">>> Queue vuota, avvio GUI.")
    else:
        print(">>> " + str(count) + " task completati.")

except Exception as e:
    print(">>> process_queue errore: " + str(e))
    print(">>> Continuo con GUI normale.")
