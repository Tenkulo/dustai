"""
DUST AI – Memory v2.0
Short-term (messaggi sessione) + Long-term (JSON disco) + SkillForge + TaskQueue.
"""
import json, logging, time
from datetime import datetime
from pathlib import Path

log = logging.getLogger("Memory")

class Memory:
    MAX_SHORT = 30

    def __init__(self, config):
        self.config = config
        self._short = []
        self._long  = []
        self._facts = []
        self._load()

    def _load(self):
        f = self.config.get_memory_file()
        if f.exists():
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                self._long  = d.get("summaries", [])
                self._facts = d.get("facts", [])
                log.info("Memoria: %d sommari, %d fatti", len(self._long), len(self._facts))
            except Exception as e:
                log.warning("Memoria non caricata: %s", e)

    def _save(self):
        try:
            self.config.get_memory_file().write_text(
                json.dumps({
                    "updated": datetime.now().isoformat(),
                    "summaries": self._long[-100:],
                    "facts":     self._facts[-200:],
                }, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
        except Exception as e:
            log.warning("Memoria non salvata: %s", e)

    def add_interaction(self, role: str, content: str):
        self._short.append({"role": role, "content": content[:500],
                             "ts": datetime.now().isoformat()})
        if len(self._short) > self.MAX_SHORT:
            self._short = self._short[-self.MAX_SHORT:]
        if role == "user":
            self._long.append(f"[{datetime.now().strftime('%m-%d %H:%M')}] {content[:100]}")
            self._save()

    # alias per retrocompatibilità
    def add(self, task, response):
        self.add_interaction("user", task)
        self.add_interaction("assistant", response)

    def add_fact(self, fact: str):
        self._facts.append(fact[:200])
        self._save()

    def get_context(self) -> str:
        parts = []
        if self._facts:
            parts.append("Fatti noti: " + "; ".join(self._facts[-5:]))
        if self._long:
            parts.append("Storico recente: " + " | ".join(self._long[-5:]))
        return "\n".join(parts) if parts else ""

    def get_messages(self) -> list:
        return list(self._short)


class SkillForge:
    def __init__(self, config):
        self.config = config
        self._skills = {}
        self._load()

    def _load(self):
        f = self.config.get_skills_file()
        if f.exists():
            try:
                self._skills = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                pass

    def _save(self):
        try:
            self.config.get_skills_file().write_text(
                json.dumps(self._skills, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
        except Exception:
            pass

    def learn(self, task_type: str, pattern: str, result: str):
        if task_type not in self._skills:
            self._skills[task_type] = []
        self._skills[task_type].append({
            "pattern": pattern[:100],
            "result":  result[:100],
            "ts":      datetime.now().isoformat(),
        })
        self._skills[task_type] = self._skills[task_type][-20:]
        self._save()

    def recall(self, task_type: str) -> list:
        return self._skills.get(task_type, [])


class TaskQueue:
    def __init__(self, config):
        self.config = config
        self._f = config.get_tasks_file()

    def _load(self):
        if self._f.exists():
            try:
                return json.loads(self._f.read_text(encoding="utf-8"))
            except Exception:
                pass
        return []

    def _save(self, tasks):
        self._f.write_text(
            json.dumps(tasks, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def add(self, task_id: str, task_text: str, priority: int = 5):
        tasks = self._load()
        if not any(t["id"] == task_id for t in tasks):
            tasks.append({
                "id": task_id, "task": task_text,
                "status": "pending", "priority": priority,
                "created_at": datetime.now().isoformat(),
            })
            self._save(tasks)

    def next(self):
        tasks = self._load()
        pending = [t for t in tasks if t.get("status") == "pending"]
        pending.sort(key=lambda t: t.get("priority", 5))
        if pending:
            t = pending[0]
            for task in tasks:
                if task["id"] == t["id"]:
                    task["status"] = "running"
                    task["started_at"] = datetime.now().isoformat()
            self._save(tasks)
            return t
        return None

    def complete(self, task_id: str, result: str, success: bool = True):
        tasks = self._load()
        for t in tasks:
            if t["id"] == task_id:
                t["status"] = "done" if success else "failed"
                t["result"] = result[:300]
                t["completed_at"] = datetime.now().isoformat()
        self._save(tasks)

    def reset_stuck(self):
        tasks = self._load()
        for t in tasks:
            if t.get("status") in ("running",):
                t["status"] = "pending"
                t.pop("started_at", None)
        self._save(tasks)
