"""
DUST AI – Memory v2.0 + SkillForge
Memory: short-term (sessione) + long-term (disco) + self_profile persistente
SkillForge: analizza i log, estrae skills riusabili, le indicizza per tag
TaskQueue: coda JSON persistente in A:\\dustai_stuff\\tasks\\queue.json
"""
import json
import logging
import re
import time
from pathlib import Path
from datetime import datetime
from typing import Optional

log = logging.getLogger("Memory")


# ─────────────────────────────────────────────────────────────────────────────
# Memory
# ─────────────────────────────────────────────────────────────────────────────

class Memory:
    MAX_SHORT_TERM = 30

    def __init__(self, config):
        self.config           = config
        self.log              = logging.getLogger("Memory")
        self._short_term      = []
        self._mem_file        = config.get_memory_dir() / "memory.json"
        self._profile_file    = config.get_profiles_dir() / "self_profile.json"
        self._long_term       = []
        self._facts           = []
        self._profile         = {}
        self._load_long_term()
        self._load_profile()

    # ── Long-term ─────────────────────────────────────────────────────────────

    def _load_long_term(self):
        if self._mem_file.exists():
            try:
                data = json.loads(self._mem_file.read_text(encoding="utf-8"))
                self._long_term = data.get("summaries", [])
                self._facts     = data.get("facts", [])
                self.log.info("Memoria: " + str(len(self._long_term)) + " sommari, " + str(len(self._facts)) + " fatti")
            except Exception as e:
                self.log.warning("Memoria load error: " + str(e))
                self._long_term = []
                self._facts     = []
        else:
            self._long_term = []
            self._facts     = []

    def _save_long_term(self):
        try:
            data = {
                "updated_at": datetime.now().isoformat(),
                "summaries":  self._long_term[-100:],
                "facts":      self._facts[-200:],
            }
            self._mem_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            self.log.warning("Memoria save error: " + str(e))

    # ── Self profile ──────────────────────────────────────────────────────────

    def _load_profile(self):
        if self._profile_file.exists():
            try:
                self._profile = json.loads(self._profile_file.read_text(encoding="utf-8"))
            except Exception:
                self._profile = {}
        if not self._profile:
            self._profile = {
                "created_at":    datetime.now().isoformat(),
                "tasks_done":    0,
                "tasks_failed":  0,
                "tools_used":    {},
                "learned_facts": [],
                "strengths":     [],
                "weaknesses":    [],
            }
            self._save_profile()

    def _save_profile(self):
        try:
            self._profile_file.write_text(
                json.dumps(self._profile, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except Exception as e:
            self.log.warning("Profile save error: " + str(e))

    def update_profile(self, task: str, success: bool, tools_used: list = None):
        if success:
            self._profile["tasks_done"] = self._profile.get("tasks_done", 0) + 1
        else:
            self._profile["tasks_failed"] = self._profile.get("tasks_failed", 0) + 1

        for tool in (tools_used or []):
            d = self._profile.setdefault("tools_used", {})
            d[tool] = d.get(tool, 0) + 1

        self._save_profile()

    # ── Pubblici ──────────────────────────────────────────────────────────────

    def add(self, task: str, response: str, success: bool = True, tools_used: list = None):
        entry = {
            "ts":       datetime.now().isoformat(),
            "task":     task[:500],
            "response": response[:500],
            "success":  success,
        }
        self._short_term.append(entry)
        if len(self._short_term) > self.MAX_SHORT_TERM:
            self._short_term = self._short_term[-self.MAX_SHORT_TERM:]

        ts_short = entry["ts"][:10]
        self._long_term.append("[" + ts_short + "] " + task[:120])
        self._save_long_term()
        self.update_profile(task, success, tools_used)

    def add_fact(self, fact: str):
        if fact not in self._facts:
            self._facts.append(fact)
            self._save_long_term()

    def get_context(self) -> str:
        parts = []

        if self._facts:
            parts.append("Fatti noti:\n" + "\n".join("• " + f for f in self._facts[-15:]))

        if self._short_term:
            recent = self._short_term[-5:]
            hist   = "\n".join("[" + e["ts"][:16] + "] " + e["task"][:80] for e in recent)
            parts.append("Task recenti:\n" + hist)

        profile_info = self._get_profile_summary()
        if profile_info:
            parts.append("Profilo agente:\n" + profile_info)

        return "\n\n".join(parts) if parts else ""

    def _get_profile_summary(self) -> str:
        done   = self._profile.get("tasks_done", 0)
        failed = self._profile.get("tasks_failed", 0)
        if done + failed == 0:
            return ""
        top_tools = sorted(self._profile.get("tools_used", {}).items(), key=lambda x: x[1], reverse=True)[:3]
        tools_str = ", ".join(t[0] + "(" + str(t[1]) + ")" for t in top_tools)
        return "Task: " + str(done) + " ok / " + str(failed) + " falliti | Top tools: " + tools_str

    def clear(self):
        self._short_term = []
        self.log.info("Short-term memory svuotata")

    def get_profile(self) -> dict:
        return dict(self._profile)


# ─────────────────────────────────────────────────────────────────────────────
# TaskQueue: coda task persistente
# ─────────────────────────────────────────────────────────────────────────────

class TaskQueue:
    """
    Coda JSON persistente: A:\\dustai_stuff\\tasks\\queue.json
    Supporta priorità (0=urgente, 9=bassa) e status tracking.
    """
    STATUS_PENDING   = "pending"
    STATUS_RUNNING   = "running"
    STATUS_DONE      = "done"
    STATUS_FAILED    = "failed"

    def __init__(self, config):
        self.queue_file = config.get_tasks_file()
        self.queue_file.parent.mkdir(parents=True, exist_ok=True)
        self._tasks: list = []
        self._load()

    def _load(self):
        if self.queue_file.exists():
            try:
                self._tasks = json.loads(self.queue_file.read_text(encoding="utf-8"))
            except Exception:
                self._tasks = []

    def _save(self):
        self.queue_file.write_text(
            json.dumps(self._tasks, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def enqueue(self, task: str, priority: int = 5, source: str = "user") -> str:
        import hashlib
        task_id = hashlib.md5((task + str(time.time())).encode()).hexdigest()[:8]
        entry = {
            "id":         task_id,
            "task":       task,
            "priority":   priority,
            "source":     source,
            "status":     self.STATUS_PENDING,
            "created_at": datetime.now().isoformat(),
            "started_at": None,
            "done_at":    None,
            "result":     None,
        }
        self._tasks.append(entry)
        self._tasks.sort(key=lambda x: (x["priority"], x["created_at"]))
        self._save()
        log.info("Task enqueued: [" + task_id + "] " + task[:60])
        return task_id

    def next(self) -> Optional[dict]:
        for t in self._tasks:
            if t["status"] == self.STATUS_PENDING:
                t["status"]     = self.STATUS_RUNNING
                t["started_at"] = datetime.now().isoformat()
                self._save()
                return t
        return None

    def complete(self, task_id: str, result: str, success: bool = True):
        for t in self._tasks:
            if t["id"] == task_id:
                t["status"]  = self.STATUS_DONE if success else self.STATUS_FAILED
                t["done_at"] = datetime.now().isoformat()
                t["result"]  = result[:500]
                self._save()
                return

    def pending(self) -> list:
        return [t for t in self._tasks if t["status"] == self.STATUS_PENDING]

    def all_tasks(self) -> list:
        return list(self._tasks)

    def clear_done(self):
        self._tasks = [t for t in self._tasks if t["status"] not in (self.STATUS_DONE, self.STATUS_FAILED)]
        self._save()


# ─────────────────────────────────────────────────────────────────────────────
# SkillForge: estrae skill dai log, indicizza per tag
# ─────────────────────────────────────────────────────────────────────────────

class SkillForge:
    """
    Analizza i log DUST AI e i task completati.
    Estrae pattern riusabili come "Skills" (sequenze di tool che hanno funzionato).
    Indicizza per tag (file_ops, browser, system, ecc.).
    """

    def __init__(self, config, gemini_model=None):
        self.config      = config
        self.gemini      = gemini_model
        self.skills_dir  = config.get_skills_dir()
        self.skills_file = self.skills_dir / "skills.json"
        self._skills: list = []
        self._load()

    def _load(self):
        if self.skills_file.exists():
            try:
                self._skills = json.loads(self.skills_file.read_text(encoding="utf-8"))
                log.info("SkillForge: " + str(len(self._skills)) + " skills caricate")
            except Exception:
                self._skills = []

    def _save(self):
        self.skills_file.write_text(
            json.dumps(self._skills, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def learn_from_task(self, task: str, steps: list, success: bool):
        """
        Registra i passi di un task completato come potenziale skill.
        steps = lista di {"tool": ..., "params": ..., "result": ...}
        """
        if not success or len(steps) < 2:
            return

        skill_id = self._hash(task)
        # Non duplicare
        if any(s["id"] == skill_id for s in self._skills):
            return

        tags = self._auto_tag(task, steps)
        skill = {
            "id":         skill_id,
            "name":       task[:80],
            "tags":       tags,
            "steps":      steps[:20],
            "learned_at": datetime.now().isoformat(),
            "used_count": 0,
        }
        self._skills.append(skill)
        self._skills = self._skills[-500:]   # max 500 skills
        self._save()
        log.info("SkillForge: nuova skill appresa — " + task[:60] + " [" + ", ".join(tags) + "]")

    def search(self, query: str, top_k: int = 3) -> list:
        """Cerca skills rilevanti per query (matching per parole chiave + tag)."""
        if not self._skills:
            return []

        query_words = set(query.lower().split())
        scored = []
        for skill in self._skills:
            name_words = set(skill["name"].lower().split())
            tag_words  = set(skill.get("tags", []))
            overlap    = len(query_words & (name_words | tag_words))
            if overlap > 0:
                scored.append((overlap + skill.get("used_count", 0) * 0.1, skill))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [s[1] for s in scored[:top_k]]

    def get_skill_context(self, task: str) -> str:
        """Ritorna contesto skills rilevanti formattato per il prompt dell'agent."""
        relevant = self.search(task, top_k=2)
        if not relevant:
            return ""

        lines = ["Skills rilevanti dalla memoria procedurale:"]
        for skill in relevant:
            lines.append("• " + skill["name"])
            for step in skill["steps"][:3]:
                tool   = step.get("tool", "?")
                params = json.dumps(step.get("params", {}))[:100]
                lines.append("  → " + tool + " " + params)
        return "\n".join(lines)

    def extract_from_logs(self, max_entries: int = 50) -> int:
        """
        Analizza i log recenti e prova a estrarre nuove skills.
        Ritorna il numero di nuove skills aggiunte.
        """
        log_dir   = self.config.get_log_dir()
        new_count = 0

        for log_file in sorted(log_dir.glob("debug_*.jsonl"))[-3:]:
            try:
                entries = []
                for line in log_file.read_text(encoding="utf-8").splitlines():
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

                # Raggruppa per sessione
                sessions: dict = {}
                for entry in entries:
                    sid = entry.get("session", "")
                    sessions.setdefault(sid, []).append(entry)

                for sid, evs in sessions.items():
                    task_name = self._extract_task_from_events(evs)
                    steps     = self._extract_steps_from_events(evs)
                    success   = self._was_successful(evs)
                    if task_name and steps:
                        prev_count = len(self._skills)
                        self.learn_from_task(task_name, steps, success)
                        if len(self._skills) > prev_count:
                            new_count += 1

            except Exception as e:
                log.warning("SkillForge extract error: " + str(e))

        return new_count

    def _extract_task_from_events(self, events: list) -> str:
        for ev in events:
            if ev.get("type") == "boot":
                data = ev.get("data", {})
                return data.get("task", "")
        # Fallback: cerca nel primo model_call
        for ev in events:
            if ev.get("type") == "model_call":
                parts = ev.get("data", {}).get("last_user", "")
                if parts:
                    return str(parts)[:80]
        return ""

    def _extract_steps_from_events(self, events: list) -> list:
        steps = []
        for ev in events:
            if ev.get("type") == "tool_ok":
                data = ev.get("data", {})
                steps.append({
                    "tool":   data.get("tool", ""),
                    "params": data.get("params", {}),
                    "result": str(data.get("result", ""))[:200],
                })
        return steps

    def _was_successful(self, events: list) -> bool:
        error_count = sum(1 for e in events if e.get("severity") in ("error", "fatal"))
        ok_count    = sum(1 for e in events if e.get("type") == "tool_ok")
        return ok_count > 0 and error_count == 0

    def _auto_tag(self, task: str, steps: list) -> list:
        tags = set()
        task_lower = task.lower()
        tools_used = {s.get("tool", "") for s in steps}

        if any(t in tools_used for t in ["file_read", "file_write", "file_list"]):
            tags.add("file_ops")
        if any(t in tools_used for t in ["browser_open", "browser_click", "browser_type"]):
            tags.add("browser")
        if "sys_exec" in tools_used:
            tags.add("system")
        if any(t in tools_used for t in ["mouse_click", "keyboard_type"]):
            tags.add("gui_control")
        if "web_search" in tools_used:
            tags.add("research")
        if "code_run" in tools_used:
            tags.add("coding")
        if "screenshot" in tools_used or "vision_analyze" in tools_used:
            tags.add("vision")

        # Tag da parole chiave nel task
        keyword_tags = {
            "file": "file_ops", "cartella": "file_ops", "crea": "file_ops",
            "apri": "browser",  "sito": "browser", "web": "browser",
            "installa": "system", "comando": "system",
            "cerca": "research", "ricerca": "research",
        }
        for kw, tag in keyword_tags.items():
            if kw in task_lower:
                tags.add(tag)

        return sorted(tags)

    def _hash(self, text: str) -> str:
        import hashlib
        return hashlib.md5(text[:100].encode()).hexdigest()[:10]
