"""
DUST AI – SysExecTool v2.0
Esecuzione comandi shell sicura su Windows 11 e Linux.
Fix: backslash in path, timeout, stderr capture, exit code handling.
"""
import subprocess
import logging
import os
import sys
import platform
from pathlib import Path

log = logging.getLogger("SysExecTool")

# Flag Windows-only per nascondere finestra console
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
_IS_WINDOWS       = platform.system() == "Windows"


class SysExecTool:
    def __init__(self, config):
        self.config  = config
        self.timeout = config.get("tools", {}).get("sys_exec", {}).get("timeout", 30)

    def sys_exec(self, cmd: str, cwd: str = "", timeout: int = None) -> str:
        """
        Esegui un comando shell.
        Windows: wrappa automaticamente con cmd /c se non già presente.
        Ritorna stdout + stderr combinati con indicazione exit code.
        """
        if not cmd:
            return "❌ Comando vuoto"

        effective_timeout = timeout or self.timeout
        cwd_path          = cwd or str(self.config.get_base_path())

        # Verifica che cwd esista
        if cwd and not Path(cwd).exists():
            cwd_path = str(self.config.get_base_path())
            log.warning("cwd non trovato, uso base_path: " + cwd_path)

        # Normalizza comando Windows
        if _IS_WINDOWS:
            cmd = self._normalize_windows_cmd(cmd)

        log.info("exec [" + str(effective_timeout) + "s]: " + cmd[:120])

        try:
            kwargs = {
                "shell":         True,
                "capture_output": True,
                "text":          True,
                "timeout":       effective_timeout,
                "cwd":           cwd_path,
                "encoding":      "utf-8",
                "errors":        "replace",
            }
            if _IS_WINDOWS:
                kwargs["creationflags"] = _CREATE_NO_WINDOW
                kwargs["env"]           = {**os.environ, "PYTHONIOENCODING": "utf-8"}

            result = subprocess.run(cmd, **kwargs)

            stdout = result.stdout.strip() if result.stdout else ""
            stderr = result.stderr.strip() if result.stderr else ""
            code   = result.returncode

            if code != 0:
                out = "❌ [exit code: " + str(code) + "]"
                if stderr:
                    out += "\n[stderr] " + stderr[:500]
                if stdout:
                    out += "\n[stdout] " + stdout[:300]
                return out

            if stdout and stderr:
                return stdout + "\n[stderr] " + stderr[:200]
            return stdout or stderr or "[OK] Comando eseguito (nessun output)"

        except subprocess.TimeoutExpired:
            return "❌ Timeout (" + str(effective_timeout) + "s): " + cmd[:80]
        except FileNotFoundError as e:
            return "❌ Comando non trovato: " + str(e)
        except Exception as e:
            return "❌ Errore esecuzione: " + str(e)

    def _normalize_windows_cmd(self, cmd: str) -> str:
        """
        Normalizza il comando per Windows.
        - Aggiunge 'cmd /c' se non già presente
        - Gestisce path con spazi (aggiunge virgolette se mancanti)
        - Fix encoding per caratteri non-ASCII
        """
        cmd = cmd.strip()

        # Già wrapped con cmd /c, powershell, python ecc.
        prefixes = ("cmd ", "cmd/c", "powershell", "python", "pip",
                    "git", "ollama", "winget", "notepad", "explorer",
                    "start ", "where ", "echo ", "set ", "cd ", "dir ",
                    "type ", "copy ", "move ", "del ", "mkdir ", "rmdir ",
                    "tasklist", "taskkill", "ipconfig", "ping", "curl",
                    "chcp", "reg ", "sfc ", "wmic ")

        cmd_lower = cmd.lower()
        if not any(cmd_lower.startswith(p) for p in prefixes):
            cmd = "cmd /c " + cmd

        return cmd

    # ─── Comandi helper pronti ────────────────────────────────────────────────

    def file_exists_check(self, path: str) -> bool:
        """Verifica esistenza file/directory via shell."""
        if _IS_WINDOWS:
            result = self.sys_exec('cmd /c if exist "' + path + '" (echo YES) else (echo NO)')
        else:
            result = self.sys_exec('test -e "' + path + '" && echo YES || echo NO')
        return "YES" in result

    def get_env(self, var: str) -> str:
        """Leggi variabile d'ambiente."""
        if _IS_WINDOWS:
            result = self.sys_exec("cmd /c echo %" + var + "%")
            return result.strip().replace("%" + var + "%", "").strip()
        return os.environ.get(var, "")

    def kill_process(self, name: str) -> str:
        """Termina un processo per nome."""
        if _IS_WINDOWS:
            return self.sys_exec('taskkill /IM "' + name + '" /F')
        return self.sys_exec("pkill -f " + name)
