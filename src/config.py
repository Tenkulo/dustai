import os
import pathlib

BASE_PATH  = pathlib.Path(r"A:\dustai")
STUFF_PATH = pathlib.Path(r"A:\dustai_stuff")

_env_file = STUFF_PATH / ".env"
if _env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_file, override=True)
    except ImportError:
        for line in _env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


class Config:
    _cfg: dict = {}

    @classmethod
    def get(cls, key, default=None):
        return os.environ.get(key, cls._cfg.get(key, default))

    @classmethod
    def set(cls, key, value):
        cls._cfg[key] = value


GEMINI_KEYS: list[str] = [
    k for k in [
        os.environ.get("GOOGLE_API_KEY"),
        os.environ.get("GOOGLE_API_KEY_2"),
        os.environ.get("GOOGLE_API_KEY_3"),
    ] if k
]

# ✅ Modello aggiornato — gemini-2.0-flash è disponibile gratis su v1beta
GEMINI_MODEL       = "gemini-2.0-flash"
GITHUB_TOKEN       = os.environ.get("GITHUB_TOKEN", "")
GITHUB_USER        = os.environ.get("GITHUB_USER", "Tenkulo")
GITHUB_REPO        = "dustai"
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODELS   = ["qwen3:8b", "mistral-small3.1"]
