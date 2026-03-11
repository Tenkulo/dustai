"""
DUST AI – DebugSystem v2.0 (COMPLETO)
Sessione precedente tagliata a metà. Riscrittura completa.

Componenti:
  DebugMonitor    - JSONL event log strutturato
  HealthChecker   - check periodico API/disco/RAM/Ollama/sintassi
  AnomalyDetector - loop detection, stall, cascade fail
  DiagnoseEngine  - classifica 7 pattern di errore con fix hints
  AutoRepair      - pip install, fstring fix, LLM patch, reload
  DebugSystem     - facade pubblica usata da agent.py e gui.py
"""
import json
import logging
import os
import sys
import ast
import re
import time
import threading
import traceback
import psutil
from pathlib import Path
from datetime import datetime
from typing import Optional, Any

log = logging.getLogger("DebugSystem")


# ─── DebugMonitor ─────────────────────────────────────────────────────────────

class DebugMonitor:
    """Log eventi strutturati in JSONL. Un file per giorno."""

    def __init__(self, config):
        self.log_dir  = config.get_log_dir()
        self._session = datetime.now().strftime("%H%M%S")
        self._file    = None
        self._lock    = threading.Lock()
        self._open_file()

    def _open_file(self):
        today    = datetime.now().strftime("%Y-%m-%d")
        log_path = self.log_dir / ("debug_" + today + ".jsonl")
        try:
            self._file = open(log_path, "a", encoding="utf-8")
        except Exception as e:
            log.warning("DebugMonitor open: " + str(e))
            self._file = None

    def event(self, event_type: str, data: dict, severity: str = "info"):
        entry = {
            "ts":       datetime.now().isoformat(),
            "session":  self._session,
            "type":     event_type,
            "severity": severity,
            "data":     data,
        }
        with self._lock:
            if self._file:
                try:
                    self._file.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    self._file.flush()
                except Exception:
                    pass

    def tool_call(self, tool: str, params: dict):
        self.event("tool_call", {"tool": tool, "params": params})

    def tool_ok(self, tool: str, params: dict, result: Any, elapsed_ms: int):
        self.event("tool_ok", {
            "tool": tool, "params": params,
            "result": str(result)[:300], "elapsed_ms": elapsed_ms
        })

    def tool_error(self, tool: str, params: dict, error: str):
        self.event("tool_error", {"tool": tool, "params": params, "error": error},
                   severity="error")

    def model_call(self, model: str, messages_len: int, last_user: str):
        self.event("model_call", {
            "model": model, "messages_len": messages_len,
            "last_user": last_user[:200]
        })

    def model_response(self, model: str, response_type: str, tool: str = ""):
        self.event("model_response", {
            "model": model, "type": response_type, "tool": tool
        })

    def model_error(self, model: str, error: str):
        self.event("model_error", {"model": model, "error": error}, severity="error")

    def parse_fail(self, raw: str, model: str):
        self.event("parse_fail", {"raw": raw[:300], "model": model}, severity="warning")

    def crash(self, error: str, tb: str):
        self.event("crash", {"error": error, "traceback": tb[-2000:]}, severity="fatal")

    def heal(self, heal_type: str, result: str, success: bool):
        self.event("heal", {"type": heal_type, "result": result[:200], "success": success})

    def boot(self, task: str, step: int, max_steps: int):
        self.event("boot", {"task": task[:200], "step": step, "max_steps": max_steps})

    def close(self):
        if self._file:
            try:
                self._file.close()
            except Exception:
                pass


# ─── HealthChecker ────────────────────────────────────────────────────────────

class HealthChecker:
    """Check periodico ogni 60s in thread daemon."""

    CHECK_INTERVAL = 60

    def __init__(self, config, monitor: DebugMonitor):
        self.config  = config
        self.monitor = monitor
        self._thread = None
        self._stop   = threading.Event()

    def start(self):
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="HealthChecker"
        )
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        while not self._stop.wait(self.CHECK_INTERVAL):
            self.check_all()

    def check_all(self) -> dict:
        results = {
            "ts":      datetime.now().isoformat(),
            "api_key": self._check_api_key(),
            "disk":    self._check_disk(),
            "ram":     self._check_ram(),
            "ollama":  self._check_ollama(),
            "src":     self._check_src_syntax(),
        }
        all_ok = all(v.get("ok", False) for v in results.values() if isinstance(v, dict))
        self.monitor.event("health_check", results,
                           severity="info" if all_ok else "warning")
        return results

    def _check_api_key(self) -> dict:
        key = self.config.get_api_key("google")
        ok  = bool(key) and "inserisci" not in key.lower()
        return {"ok": ok, "message": "presente" if ok else "mancante o placeholder"}

    def _check_disk(self) -> dict:
        try:
            base  = self.config.get_base_path()
            usage = psutil.disk_usage(str(base))
            free_gb = usage.free / (1024 ** 3)
            ok   = free_gb > 0.5
            return {"ok": ok, "free_gb": round(free_gb, 2),
                    "message": "OK" if ok else "Disco quasi pieno"}
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def _check_ram(self) -> dict:
        try:
            ram     = psutil.virtual_memory()
            free_mb = ram.available / (1024 ** 2)
            ok      = free_mb > 200
            return {"ok": ok, "free_mb": round(free_mb),
                    "message": "OK" if ok else "RAM < 200MB"}
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def _check_ollama(self) -> dict:
        try:
            import ollama
            resp   = ollama.list()
            models = []
            if hasattr(resp, "models"):
                models = [m.model for m in resp.models if hasattr(m, "model")]
            elif isinstance(resp, dict):
                models = [m.get("name", "") for m in resp.get("models", [])]
            return {"ok": bool(models), "models": models[:5]}
        except Exception as e:
            return {"ok": False, "message": str(e)}

    def _check_src_syntax(self) -> dict:
        src_dir = Path(__file__).parent
        errors  = []
        for py_file in src_dir.rglob("*.py"):
            try:
                ast.parse(py_file.read_text(encoding="utf-8", errors="replace"))
            except SyntaxError as e:
                errors.append(str(py_file.name) + ":" + str(e.lineno))
        return {"ok": not errors, "syntax_errors": errors}


# ─── AnomalyDetector ─────────────────────────────────────────────────────────

class AnomalyDetector:
    """Rileva anomalie nel comportamento dell'agente."""

    def __init__(self, monitor: DebugMonitor):
        self.monitor         = monitor
        self._response_hist: list = []
        self._last_action_ts = time.time()
        self._tool_errors:   dict = {}

    def record_response(self, text: str) -> Optional[str]:
        """Ritorna tipo di anomalia se rilevata, None se ok."""
        key = text[:80]
        self._response_hist.append(key)
        if len(self._response_hist) > 20:
            self._response_hist = self._response_hist[-20:]

        # Loop detection: stessa risposta 3+ volte di fila
        if len(self._response_hist) >= 3:
            last3 = self._response_hist[-3:]
            if len(set(last3)) == 1:
                self.monitor.event("anomaly", {"type": "loop", "text": key[:100]},
                                   severity="warning")
                return "loop"

        return None

    def record_tool_error(self, tool: str) -> Optional[str]:
        """Ritorna 'cascade_fail' se lo stesso tool fallisce 3+ volte."""
        self._tool_errors[tool] = self._tool_errors.get(tool, 0) + 1
        if self._tool_errors[tool] >= 3:
            self.monitor.event("anomaly",
                               {"type": "cascade_fail", "tool": tool,
                                "count": self._tool_errors[tool]},
                               severity="error")
            return "cascade_fail"
        return None

    def record_action(self):
        self._last_action_ts = time.time()

    def check_stall(self) -> bool:
        """True se nessuna azione da più di 120s."""
        elapsed = time.time() - self._last_action_ts
        if elapsed > 120:
            self.monitor.event("anomaly",
                               {"type": "stall", "seconds": round(elapsed)},
                               severity="warning")
            return True
        return False

    def reset_tool_errors(self, tool: str):
        self._tool_errors.pop(tool, None)


# ─── DiagnoseEngine ──────────────────────────────────────────────────────────

KNOWN_PATTERNS = [
    {
        "id":      "missing_module",
        "match":   r"No module named '([^']+)'",
        "fix":     "pip install {module}",
        "auto":    True,
    },
    {
        "id":      "fstring_backslash",
        "match":   r"f-string expression part cannot include a backslash",
        "fix":     "Sostituisci backslash in f-string con variabile intermedia",
        "auto":    True,
    },
    {
        "id":      "api_key_missing",
        "match":   r"(API key|GOOGLE_API_KEY|api_key).*?(mancante|not found|invalid|missing)",
        "fix":     "Aggiungi GOOGLE_API_KEY in A:\\dustai_stuff\\.env",
        "auto":    False,
    },
    {
        "id":      "permission_denied",
        "match":   r"(PermissionError|Access is denied|accesso negato|WinError 5)",
        "fix":     "Usa path alternativo o lancia come amministratore",
        "auto":    False,
    },
    {
        "id":      "rate_limit",
        "match":   r"(429|RESOURCE_EXHAUSTED|rate.limit|quota)",
        "fix":     "Attendi o switcha a Ollama locale",
        "auto":    True,
    },
    {
        "id":      "ollama_down",
        "match":   r"(Connection refused|ollama.*not.*found|Cannot connect to Ollama)",
        "fix":     "Avvia Ollama: ollama serve",
        "auto":    False,
    },
    {
        "id":      "disk_full",
        "match":   r"(No space left|disk.*full|spazio.*esaurito)",
        "fix":     "Libera spazio disco",
        "auto":    False,
    },
]


class DiagnoseEngine:
    def __init__(self, monitor: DebugMonitor):
        self.monitor = monitor

    def diagnose(self, error: str, tb: str = "") -> dict:
        combined = (error + " " + tb).lower()
        for pattern in KNOWN_PATTERNS:
            m = re.search(pattern["match"], combined, re.IGNORECASE)
            if m:
                fix = pattern["fix"]
                if "{module}" in fix and m.groups():
                    fix = fix.replace("{module}", m.group(1).split(".")[0])
                result = {
                    "pattern_id": pattern["id"],
                    "fix":        fix,
                    "auto_fix":   pattern["auto"],
                    "match":      m.group(0)[:100],
                }
                self.monitor.event("diagnosis", result)
                return result
        return {"pattern_id": "unknown", "fix": "Analisi manuale richiesta",
                "auto_fix": False, "match": ""}


# ─── AutoRepair ──────────────────────────────────────────────────────────────

class AutoRepair:
    def __init__(self, config, monitor: DebugMonitor, gemini=None):
        self.config  = config
        self.monitor = monitor
        self.gemini  = gemini

    def attempt(self, diagnosis: dict, error: str, tb: str) -> bool:
        """Tenta riparazione automatica basata sulla diagnosi."""
        pid    = diagnosis.get("pattern_id", "")
        result = False

        if pid == "missing_module":
            module  = re.search(r"No module named '([^']+)'", error + " " + tb)
            package = module.group(1).split(".")[0] if module else ""
            result  = self._pip_install(package) if package else False

        elif pid == "fstring_backslash":
            broken  = self._find_broken_file(tb)
            result  = self._fix_fstring(broken) if broken else False

        elif pid == "rate_limit":
            log.info("AutoRepair: rate limit → attendo 65s")
            time.sleep(65)
            result = True

        self.monitor.heal(pid, diagnosis.get("fix", ""), success=result)
        return result

    def _pip_install(self, package: str) -> bool:
        import subprocess
        log.info("AutoRepair: pip install " + package)
        try:
            r = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--quiet", package],
                capture_output=True, timeout=120
            )
            return r.returncode == 0
        except Exception:
            return False

    def _fix_fstring(self, filepath: str) -> bool:
        try:
            source = Path(filepath).read_text(encoding="utf-8")
            lines  = source.splitlines()
            fixed  = []
            changed = False
            for line in lines:
                if re.search(r'f["\'].*\{[^}]*\\[^}]*\}.*["\']', line):
                    line = re.sub(
                        r'\{([^}]*\\[^}]*)\}',
                        lambda m: "{" + m.group(1).replace("\\", "/") + "}",
                        line
                    )
                    changed = True
                fixed.append(line)
            if not changed:
                return False
            patched = "\n".join(fixed)
            ast.parse(patched)
            # Backup
            bak = self.config.get_base_path() / "patches" / (Path(filepath).name + ".bak")
            bak.write_text(source, encoding="utf-8")
            Path(filepath).write_text(patched, encoding="utf-8")
            return True
        except Exception as e:
            log.warning("fstring fix: " + str(e))
            return False

    def _find_broken_file(self, tb: str) -> str:
        for m in re.finditer(r'File "([^"]*\.py)"', tb):
            p = m.group(1)
            if "src" in p and Path(p).exists():
                return p
        return ""


# ─── DebugSystem (facade pubblica) ───────────────────────────────────────────

class DebugSystem:
    """
    Facade unificata. Usata da agent.py, gui.py, orchestrator.py.

    Esempio:
        debug = DebugSystem(config, gemini_model)
        debug.start()
        debug.tool_call("sys_exec", {"cmd": "dir"})
        result = tools.execute(...)
        debug.tool_ok("sys_exec", {}, result, elapsed_ms=150)
    """

    def __init__(self, config, gemini=None):
        self.config   = config
        self.monitor  = DebugMonitor(config)
        self.health   = HealthChecker(config, self.monitor)
        self.anomaly  = AnomalyDetector(self.monitor)
        self.diagnose = DiagnoseEngine(self.monitor)
        self.repair   = AutoRepair(config, self.monitor, gemini)
        self._started = False

    def start(self):
        """Avvia health checker in background."""
        if not self._started:
            self.health.start()
            self._started = True
            self.monitor.event("system_start", {"pid": os.getpid()})

    def stop(self):
        self.health.stop()
        self.monitor.close()

    # ── Proxy eventi ─────────────────────────────────────────────────────────

    def tool_call(self, tool: str, params: dict):
        self.anomaly.record_action()
        self.monitor.tool_call(tool, params)

    def tool_ok(self, tool: str, params: dict, result: Any, elapsed_ms: int = 0):
        self.anomaly.reset_tool_errors(tool)
        self.monitor.tool_ok(tool, params, result, elapsed_ms)

    def tool_error(self, tool: str, params: dict, error: str) -> Optional[str]:
        """Registra errore tool e ritorna tipo anomalia se rilevata."""
        self.monitor.tool_error(tool, params, error)
        anomaly = self.anomaly.record_tool_error(tool)
        return anomaly

    def model_call(self, model: str, messages: list):
        last_user = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                parts    = m.get("parts", [""])
                last_user = parts[0] if isinstance(parts, list) else str(parts)
                break
        self.monitor.model_call(model, len(messages), last_user[:200])

    def model_response(self, model: str, result: dict):
        self.monitor.model_response(
            model,
            result.get("type", "unknown"),
            result.get("tool", ""),
        )
        if result.get("type") == "text":
            anomaly = self.anomaly.record_response(result.get("text", ""))
            return anomaly
        return None

    def model_error(self, model: str, error: str):
        self.monitor.model_error(model, error)
        diag = self.diagnose.diagnose(error)
        if diag.get("auto_fix"):
            self.repair.attempt(diag, error, "")
        return diag

    def parse_fail(self, raw: str, model: str):
        self.monitor.parse_fail(raw, model)

    def crash(self, error: str, tb: str = "") -> dict:
        if not tb:
            tb = traceback.format_exc()
        self.monitor.crash(error, tb)
        diag = self.diagnose.diagnose(error, tb)
        if diag.get("auto_fix"):
            fixed = self.repair.attempt(diag, error, tb)
            return {"diagnosed": diag, "auto_fixed": fixed}
        return {"diagnosed": diag, "auto_fixed": False}

    def get_report(self) -> dict:
        """Report completo per GUI debug panel."""
        health_status = self.health.check_all()
        stall         = self.anomaly.check_stall()

        # Ultime 20 righe del log corrente
        recent_events = []
        today    = datetime.now().strftime("%Y-%m-%d")
        log_path = self.config.get_log_dir() / ("debug_" + today + ".jsonl")
        if log_path.exists():
            try:
                lines = log_path.read_text(encoding="utf-8").splitlines()
                for line in lines[-20:]:
                    try:
                        recent_events.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
            except Exception:
                pass

        return {
            "health":       health_status,
            "stall":        stall,
            "recent_events": recent_events,
            "session":      self.monitor._session,
        }
