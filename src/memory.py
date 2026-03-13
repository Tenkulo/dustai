import json
import time
from pathlib import Path

try:
    from config import BASE_PATH
except ImportError:
    import pathlib; BASE_PATH = pathlib.Path(r"A:\dustai")

MEMORY_FILE  = BASE_PATH / "dustai_stuff" / "memory.json"
SKILLS_FILE  = BASE_PATH / "dustai_stuff" / "skills.json"


class Memory:
    """Persistent key-value memory store."""

    def __init__(self):
        self._data: dict = {}
        self._load()

    def _load(self):
        if MEMORY_FILE.exists():
            try:
                self._data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
            except Exception:
                self._data = {}

    def _flush(self):
        MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        MEMORY_FILE.write_text(json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8")

    def save(self, key: str, value) -> None:
        self._data[key] = {"value": value, "ts": time.time()}
        self._flush()

    def get(self, key: str, default=None):
        item = self._data.get(key)
        return item["value"] if item else default

    def delete(self, key: str) -> None:
        self._data.pop(key, None)
        self._flush()

    def all(self) -> dict:
        return {k: v["value"] for k, v in self._data.items()}

    def recent(self, n: int = 10) -> list[tuple]:
        items = sorted(self._data.items(), key=lambda x: x[1].get("ts", 0), reverse=True)
        return [(k, v["value"]) for k, v in items[:n]]


class SkillForge:
    """Learned skills/code snippets store."""

    def __init__(self):
        self._skills: dict = {}
        self._load()

    def _load(self):
        if SKILLS_FILE.exists():
            try:
                self._skills = json.loads(SKILLS_FILE.read_text(encoding="utf-8"))
            except Exception:
                self._skills = {}

    def _flush(self):
        SKILLS_FILE.parent.mkdir(parents=True, exist_ok=True)
        SKILLS_FILE.write_text(json.dumps(self._skills, indent=2, ensure_ascii=False), encoding="utf-8")

    def learn(self, name: str, code: str, description: str = "") -> None:
        self._skills[name] = {"code": code, "desc": description, "uses": 0}
        self._flush()

    def get(self, name: str) -> dict | None:
        skill = self._skills.get(name)
        if skill:
            skill["uses"] += 1
            self._flush()
        return skill

    def list_skills(self) -> list[str]:
        return list(self._skills.keys())


class TaskQueue:
    """Simple in-memory task queue."""

    def __init__(self):
        self._q: list = []

    def push(self, task) -> None:
        self._q.append(task)

    def pop(self):
        return self._q.pop(0) if self._q else None

    def peek(self):
        return self._q[0] if self._q else None

    def is_empty(self) -> bool:
        return len(self._q) == 0

    def all(self) -> list:
        return list(self._q)

    def clear(self) -> None:
        self._q.clear()
