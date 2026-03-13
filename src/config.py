"""
DUST AI – Config v3.0
BASE_PATH unificato, multi-key Gemini, carica .env automaticamente.
"""
import os, json, platform
from pathlib import Path

# ─── Carica .env automaticamente ─────────────────────────────────────────────
def _load_dotenv():
    candidates = [
        Path(r"A:\dustai_stuff\.env"),
        Path(__file__).parent.parent / ".env",
        Path.home() / ".env",
    ]
    for f in candidates:
        if f.exists():
            for line in f.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip())
            break

_load_dotenv()

BASE_PATH = Path(os.environ.get("DUSTAI_BASE", r"A:\dustai_stuff"))

class Config:
    def __init__(self):
        BASE_PATH.mkdir(parents=True, exist_ok=True)
        for d in ("logs", "memory", "skills", "tasks", "screenshots",
                  "patches", "backups", "browser_profiles", "cache"):
            (BASE_PATH / d).mkdir(exist_ok=True)

        self._cfg = {
            "model_primary":  "gemini-2.5-flash",
            "model_heavy":    "gemini-2.5-pro",
            "model_local":    "qwen3:8b",
            "max_steps":      25,
            "language":       "it",
            "base_path":      str(BASE_PATH),
        }
        cfg_file = BASE_PATH / "config.json"
        if cfg_file.exists():
            try:
                self._cfg.update(json.loads(cfg_file.read_text(encoding="utf-8")))
            except Exception:
                pass

    def get_model(self, kind="primary"):
        return self._cfg.get(f"model_{kind}", self._cfg.get("model_primary", "gemini-2.5-flash"))

    def get_api_key(self, provider="google", index=1):
        env = "GOOGLE_API_KEY" if provider == "google" else provider.upper() + "_API_KEY"
        if index > 1:
            env = env + f"_{index}"
        return os.environ.get(env, "")

    def get_all_google_keys(self):
        keys = []
        for env in ("GOOGLE_API_KEY", "GOOGLE_API_KEY_2", "GOOGLE_API_KEY_3"):
            k = os.environ.get(env, "")
            if k:
                keys.append((env, k))
        return keys

    def get_workdir(self):      return BASE_PATH
    def get_logs_dir(self):     return BASE_PATH / "logs"
    def get_memory_file(self):  return BASE_PATH / "memory" / "memory.json"
    def get_skills_file(self):  return BASE_PATH / "skills" / "skills.json"
    def get_tasks_file(self):   return BASE_PATH / "tasks" / "queue.json"
    def get_screenshots_dir(self): return BASE_PATH / "screenshots"
    def get_patches_dir(self):  return BASE_PATH / "patches"
    def get_backups_dir(self):  return BASE_PATH / "backups"

    def get(self, key, default=None):
        return self._cfg.get(key, default)
