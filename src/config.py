"""
DUST AI – Config Manager
Gestisce tutte le impostazioni, percorsi Windows/OneDrive, API keys.
"""
import os
import json
import platform
from pathlib import Path


class Config:
    DEFAULT_CONFIG = {
        "version": "1.0.0",
        "model_primary": "gemini/gemini-2.5-flash",
        "model_heavy": "gemini/gemini-2.5-pro",
        "model_research": "perplexity/sonar-pro",
        "model_local": "ollama/qwen3:8b",
        "model_fallback_order": ["primary", "local", "heavy"],
        "agent": {
            "max_steps": 20,
            "auto_verify": True,       # verifica sempre dopo ogni tool call
            "auto_run": True,          # non chiedere conferma
            "language": "it",
            "memory_enabled": True,
        },
        "tools": {
            "sys_exec": {"enabled": True},
            "file_ops": {"enabled": True},
            "browser": {"enabled": True, "headless": False},
            "keyboard_mouse": {"enabled": True},
            "windows_apps": {"enabled": True},
            "web_search": {"enabled": True},
            "code_runner": {"enabled": True},
        },
        "cloud": {
            "enabled": False,
            "provider": None,  # "oracle_free" | "cloudflare" | "k3s"
        },
        "paths": {
            "workdir": None,      # auto-rilevato
            "desktop": None,      # auto-rilevato (OneDrive-aware)
            "downloads": None,    # auto-rilevato
        },
    }

    def __init__(self):
        self._config = dict(self.DEFAULT_CONFIG)
        self._resolve_paths()
        self._load_from_file()
        self._load_api_keys()

    # ─── Percorsi ────────────────────────────────────────────────────────────

    def _resolve_paths(self):
        """Risolve percorsi Windows in modo OneDrive-aware."""
        system = platform.system()

        if system == "Windows":
            appdata = os.environ.get("APPDATA", "")
            userprofile = os.environ.get("USERPROFILE", "")
            onedrive = os.environ.get("OneDrive", "")

            # Desktop: preferisci OneDrive se presente
            if onedrive and Path(onedrive, "Desktop").exists():
                desktop = Path(onedrive) / "Desktop"
            elif userprofile:
                desktop = Path(userprofile) / "Desktop"
            else:
                desktop = Path.home() / "Desktop"

            workdir = Path(appdata) / "dustai" if appdata else Path.home() / ".dustai"
            downloads = Path(userprofile) / "Downloads" if userprofile else Path.home() / "Downloads"
        else:
            # Linux/Mac
            desktop = Path.home() / "Desktop"
            workdir = Path.home() / ".dustai"
            downloads = Path.home() / "Downloads"

        self._config["paths"]["workdir"] = str(workdir)
        self._config["paths"]["desktop"] = str(desktop)
        self._config["paths"]["downloads"] = str(downloads)

        # Crea workdir se non esiste
        workdir.mkdir(parents=True, exist_ok=True)

    def _load_from_file(self):
        """Carica config da file JSON se esiste."""
        config_file = self.get_workdir() / "config.json"
        if config_file.exists():
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    user_config = json.load(f)
                self._deep_merge(self._config, user_config)
            except Exception as e:
                print(f"⚠️ Errore caricamento config: {e}")

    def _load_api_keys(self):
        """Carica API keys da env vars o file separato."""
        self._config["api_keys"] = {
            "google": os.environ.get("GOOGLE_API_KEY", ""),
            "perplexity": os.environ.get("PERPLEXITY_API_KEY", ""),
            "anthropic": os.environ.get("ANTHROPIC_API_KEY", ""),
            "openai": os.environ.get("OPENAI_API_KEY", ""),
        }

        # Prova a caricare da file .env nella workdir
        env_file = self.get_workdir() / ".env"
        if env_file.exists():
            with open(env_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        key, val = line.split("=", 1)
                        key = key.strip()
                        val = val.strip().strip('"').strip("'")
                        if "GOOGLE" in key:
                            self._config["api_keys"]["google"] = val
                        elif "PERPLEXITY" in key:
                            self._config["api_keys"]["perplexity"] = val
                        elif "ANTHROPIC" in key:
                            self._config["api_keys"]["anthropic"] = val

    def save(self):
        """Salva config su disco."""
        config_file = self.get_workdir() / "config.json"
        # Non salvare API keys nel config
        save_config = {k: v for k, v in self._config.items() if k != "api_keys"}
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(save_config, f, indent=4, ensure_ascii=False)

    # ─── Helpers ─────────────────────────────────────────────────────────────

    def _deep_merge(self, base, override):
        for key, val in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(val, dict):
                self._deep_merge(base[key], val)
            else:
                base[key] = val

    def get(self, key, default=None):
        return self._config.get(key, default)

    def get_workdir(self) -> Path:
        return Path(self._config["paths"]["workdir"])

    def get_desktop(self) -> Path:
        return Path(self._config["paths"]["desktop"])

    def get_downloads(self) -> Path:
        return Path(self._config["paths"]["downloads"])

    def get_log_dir(self) -> Path:
        return self.get_workdir() / "logs"

    def get_api_key(self, provider: str) -> str:
        return self._config.get("api_keys", {}).get(provider, "")

    def get_model(self, role: str = "primary") -> str:
        return self._config.get(f"model_{role}", self._config["model_primary"])

    def is_tool_enabled(self, tool: str) -> bool:
        return self._config.get("tools", {}).get(tool, {}).get("enabled", False)
