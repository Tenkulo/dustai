"""
DUST AI – Config v2.0
Unica fonte di verità per tutti i percorsi e le impostazioni.

BASE_PATH (default A:\\dustai_stuff) è l'unica cartella che conta.
Tutto (log, memory, skills, profiles, backups, cache) vive lì dentro.
Modificabile via env var DUSTAI_BASE o config.json.
"""
import os
import json
import platform
import sys
from pathlib import Path


# ─── Costante master ─────────────────────────────────────────────────────────

_DEFAULT_BASE = r"A:\dustai_stuff" if platform.system() == "Windows" else str(Path.home() / "dustai_stuff")


class Config:
    DEFAULT = {
        "version":      "2.0.0",
        "base_path":    _DEFAULT_BASE,

        # Modelli
        "model_primary":   "gemini/gemini-2.5-flash",
        "model_heavy":     "gemini/gemini-2.5-pro",
        "model_research":  "perplexity/sonar-pro",
        "model_local":     "ollama/qwen3:8b",
        # Ordine fallback: primary → local → heavy
        "model_fallback":  ["primary", "local", "heavy"],

        # Ollama: modelli con tool-calling nativo
        "ollama_tool_models": [
            "qwen3:8b",
            "qwen2.5-coder:7b",
            "llama3.1:8b",
            "mistral-small3.1",
        ],

        "agent": {
            "max_steps":       25,
            "auto_verify":     True,
            "auto_run":        True,
            "language":        "it",
            "memory_enabled":  True,
            "reflective_loop": True,   # pre/post action reflection
            "vision_enabled":  True,   # screenshot + Gemini analysis
            "skill_forge":     True,   # auto skill extraction from logs
        },

        "tools": {
            "sys_exec":      {"enabled": True,  "timeout": 30},
            "file_ops":      {"enabled": True},
            "browser":       {"enabled": True,  "headless": False},
            "input_control": {"enabled": True},
            "windows_apps":  {"enabled": True},
            "web_search":    {"enabled": True},
            "code_runner":   {"enabled": True},
            "vision":        {"enabled": True},
        },

        "rate_limit": {
            "gemini_rpm":       5,      # free tier
            "min_interval_s":   13,
            "retry_on_429":     True,
            "max_retries":      4,
        },

        "self_heal": {
            "enabled":          True,
            "heal_parse_fail":  True,   # heal anche su JSON parse fail
            "heal_rate_limit":  True,
            "max_attempts":     5,
            "auto_patch_src":   True,   # patcha il codice sorgente stesso
        },

        "paths": {
            # tutti derivati da base_path — non editare qui
            "workdir":    None,
            "desktop":    None,
            "downloads":  None,
        },
    }

    def __init__(self, base_path: str = None):
        self._cfg = self._deep_copy(self.DEFAULT)

        # 1. Risolvi base_path: arg > env > config file > default
        bp = (
            base_path
            or os.environ.get("DUSTAI_BASE")
            or self._DEFAULT_BASE
        )
        self._cfg["base_path"] = bp

        # 2. Risolvi path OS
        self._resolve_paths()

        # 3. Crea tutte le cartelle necessarie
        self._ensure_dirs()

        # 4. Carica override da file se esiste
        self._load_file()

        # 5. Carica API keys
        self._load_api_keys()

    # ─── Path resolution ──────────────────────────────────────────────────────

    def _resolve_paths(self):
        system = platform.system()
        if system == "Windows":
            appdata     = os.environ.get("APPDATA", "")
            userprofile = os.environ.get("USERPROFILE", "")
            onedrive    = os.environ.get("OneDrive", "")

            if onedrive and Path(onedrive, "Desktop").exists():
                desktop = Path(onedrive) / "Desktop"
            elif userprofile:
                desktop = Path(userprofile) / "Desktop"
            else:
                desktop = Path.home() / "Desktop"

            downloads = Path(userprofile) / "Downloads" if userprofile else Path.home() / "Downloads"
            workdir   = Path(appdata) / "dustai" if appdata else Path.home() / ".dustai"
        else:
            desktop   = Path.home() / "Desktop"
            downloads = Path.home() / "Downloads"
            workdir   = Path.home() / ".dustai"

        self._cfg["paths"]["desktop"]   = str(desktop)
        self._cfg["paths"]["downloads"] = str(downloads)
        self._cfg["paths"]["workdir"]   = str(workdir)

    def _ensure_dirs(self):
        """Crea tutta la struttura di cartelle sotto BASE_PATH."""
        base = self.get_base_path()
        subdirs = [
            base,
            base / "logs",
            base / "memory",
            base / "skills",
            base / "profiles",
            base / "backups",
            base / "cache",
            base / "tasks",
            base / "screenshots",
            base / "patches",
            # Workdir legacy (per compatibilità bootstrap)
            Path(self._cfg["paths"]["workdir"]),
            Path(self._cfg["paths"]["workdir"]) / "logs",
        ]
        for d in subdirs:
            try:
                d.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass

    def _load_file(self):
        cfg_file = self.get_base_path() / "config.json"
        if not cfg_file.exists():
            # Prova legacy location
            cfg_file = Path(self._cfg["paths"]["workdir"]) / "config.json"
        if cfg_file.exists():
            try:
                with open(cfg_file, "r", encoding="utf-8") as f:
                    self._deep_merge(self._cfg, json.load(f))
            except Exception as e:
                print("Config load warning: " + str(e))

    def _load_api_keys(self):
        self._cfg["api_keys"] = {
            "google":     os.environ.get("GOOGLE_API_KEY", ""),
            "perplexity": os.environ.get("PERPLEXITY_API_KEY", ""),
            "anthropic":  os.environ.get("ANTHROPIC_API_KEY", ""),
            "openai":     os.environ.get("OPENAI_API_KEY", ""),
        }
        # Cerca .env in base_path prima, poi workdir
        for env_path in [
            self.get_base_path() / ".env",
            Path(self._cfg["paths"]["workdir"]) / ".env",
        ]:
            if env_path.exists():
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if "=" in line and not line.startswith("#"):
                            key, val = line.split("=", 1)
                            key = key.strip()
                            val = val.strip().strip('"').strip("'")
                            if "GOOGLE" in key and val and "inserisci" not in val:
                                self._cfg["api_keys"]["google"] = val
                            elif "PERPLEXITY" in key and val:
                                self._cfg["api_keys"]["perplexity"] = val
                            elif "ANTHROPIC" in key and val:
                                self._cfg["api_keys"]["anthropic"] = val
                break

    def save(self):
        cfg_file = self.get_base_path() / "config.json"
        save_cfg = {k: v for k, v in self._cfg.items() if k != "api_keys"}
        with open(cfg_file, "w", encoding="utf-8") as f:
            json.dump(save_cfg, f, indent=4, ensure_ascii=False)

    # ─── Accessors ────────────────────────────────────────────────────────────

    def get_base_path(self) -> Path:
        return Path(self._cfg["base_path"])

    def get_workdir(self) -> Path:
        """Legacy compat — punta a base_path."""
        return self.get_base_path()

    def get_desktop(self) -> Path:
        return Path(self._cfg["paths"]["desktop"])

    def get_downloads(self) -> Path:
        return Path(self._cfg["paths"]["downloads"])

    def get_log_dir(self) -> Path:
        return self.get_base_path() / "logs"

    def get_memory_dir(self) -> Path:
        return self.get_base_path() / "memory"

    def get_skills_dir(self) -> Path:
        return self.get_base_path() / "skills"

    def get_profiles_dir(self) -> Path:
        return self.get_base_path() / "profiles"

    def get_tasks_file(self) -> Path:
        return self.get_base_path() / "tasks" / "queue.json"

    def get_screenshots_dir(self) -> Path:
        return self.get_base_path() / "screenshots"

    def get_api_key(self, provider: str) -> str:
        return self._cfg.get("api_keys", {}).get(provider, "")

    def get_model(self, role: str = "primary") -> str:
        key = "model_" + role
        return self._cfg.get(key, self._cfg["model_primary"])

    def get(self, key, default=None):
        return self._cfg.get(key, default)

    def is_tool_enabled(self, tool: str) -> bool:
        return self._cfg.get("tools", {}).get(tool, {}).get("enabled", False)

    def get_agent_cfg(self, key: str, default=None):
        return self._cfg.get("agent", {}).get(key, default)

    def get_rate_limit(self, key: str, default=None):
        return self._cfg.get("rate_limit", {}).get(key, default)

    def get_self_heal_cfg(self, key: str, default=None):
        return self._cfg.get("self_heal", {}).get(key, default)

    # ─── Helpers ──────────────────────────────────────────────────────────────

    def _deep_copy(self, d):
        return json.loads(json.dumps(d))

    def _deep_merge(self, base, override):
        for key, val in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(val, dict):
                self._deep_merge(base[key], val)
            else:
                base[key] = val
