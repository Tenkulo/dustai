"""Self-healing system v2 — categorized error recovery."""
import importlib
import json
import logging
import re
import subprocess
import sys
import time

logger = logging.getLogger("dust.self_heal")


class Cat:
    RATE_LIMIT = "rate_limit"
    PARSE      = "parse"
    SYNTAX     = "syntax"
    IMPORT_ERR = "import"
    NETWORK    = "network"
    UNKNOWN    = "unknown"


def categorize(exc: Exception) -> str:
    s = str(exc)
    if "429" in s or "quota" in s.lower() or "RATE_LIMIT" in s:
        return Cat.RATE_LIMIT
    if isinstance(exc, (json.JSONDecodeError,)) or "json" in s.lower():
        return Cat.PARSE
    if isinstance(exc, SyntaxError):
        return Cat.SYNTAX
    if isinstance(exc, (ImportError, ModuleNotFoundError)):
        return Cat.IMPORT_ERR
    if any(k in s.lower() for k in ("connection", "timeout", "network", "socket")):
        return Cat.NETWORK
    return Cat.UNKNOWN


class SelfHeal:
    PKG_MAP = {
        "cv2": "opencv-python", "PIL": "Pillow", "PIL.Image": "Pillow",
        "sklearn": "scikit-learn", "bs4": "beautifulsoup4",
        "yaml": "pyyaml", "dotenv": "python-dotenv",
        "pyautogui": "pyautogui", "playwright": "playwright",
        "google.generativeai": "google-generativeai",
        "litellm": "litellm", "requests": "requests",
    }

    def __init__(self):
        self._history: list[dict] = []

    def heal(self, exc: Exception, context=None) -> dict:
        cat     = categorize(exc)
        handler = {
            Cat.RATE_LIMIT: self._rate_limit,
            Cat.PARSE:      self._parse,
            Cat.SYNTAX:     self._syntax,
            Cat.IMPORT_ERR: self._import,
            Cat.NETWORK:    self._network,
            Cat.UNKNOWN:    self._unknown,
        }.get(cat, self._unknown)

        result = handler(exc, context)
        self._history.append({"exc": str(exc), "cat": cat, "result": result, "ts": time.time()})
        logger.info(f"Heal [{cat}] → {result}")
        return result

    def _rate_limit(self, exc, _ctx) -> dict:
        m    = re.search(r"(\d+)", str(exc))
        wait = min(65, int(m.group(1)) + 3) if m else 62
        logger.warning(f"Rate limit — attendo {wait}s")
        time.sleep(wait)
        return {"healed": True, "action": "sleep", "seconds": wait}

    def _parse(self, exc, ctx) -> dict:
        if isinstance(ctx, str):
            try:
                m = re.search(r'\{.*\}', ctx, re.DOTALL)
                if m:
                    return {"healed": True, "action": "json_extract", "data": json.loads(m.group())}
            except Exception:
                pass
            return {"healed": True, "action": "fallback", "data": {"type": "done", "message": ctx}}
        return {"healed": False}

    def _syntax(self, exc, _ctx) -> dict:
        logger.error(f"SyntaxError: {exc}")
        return {"healed": False, "action": "report", "error": str(exc)}

    def _import(self, exc, _ctx) -> dict:
        m = re.search(r"No module named '([^']+)'", str(exc))
        if not m:
            return {"healed": False}
        raw_mod = m.group(1).split(".")[0]
        pkg = self.PKG_MAP.get(raw_mod, raw_mod)
        logger.info(f"Auto-install: {pkg}")
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", pkg, "--break-system-packages", "-q"],
                timeout=90, check=True, capture_output=True,
            )
            importlib.import_module(raw_mod)
            return {"healed": True, "action": "install", "package": pkg}
        except Exception as e:
            return {"healed": False, "action": "install_failed", "error": str(e)}

    def _network(self, exc, _ctx) -> dict:
        time.sleep(5)
        return {"healed": True, "action": "sleep", "seconds": 5}

    def _unknown(self, exc, _ctx) -> dict:
        logger.error(f"Unhandled: {exc}")
        return {"healed": False, "error": str(exc)}

    def history(self, n: int = 10) -> list:
        return self._history[-n:]


_instance: SelfHeal | None = None

def get() -> SelfHeal:
    global _instance
    if _instance is None:
        _instance = SelfHeal()
    return _instance

def heal(exc: Exception, ctx=None) -> dict:
    return get().heal(exc, ctx)
