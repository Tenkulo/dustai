"""
DUST AI – Tool: sys_exec
Esegue comandi shell su Windows (cmd /c) o Linux/Mac.
È il tool più affidabile per operazioni filesystem su Windows.
"""
import subprocess
import platform
import logging
import os


class SysExecTool:
    def __init__(self, config):
        self.config = config
        self.log = logging.getLogger("SysExecTool")
        self.is_windows = platform.system() == "Windows"

    def sys_exec(self, cmd: str, timeout: int = 30, cwd: str = None) -> str:
        """
        Esegue un comando shell e restituisce l'output.
        
        Su Windows usa automaticamente cmd /c se non specificato.
        Esempio: sys_exec(cmd="mkdir C:\\Users\\test\\Desktop\\mia_cartella")
        """
        if not cmd:
            return "❌ Comando vuoto"

        # Su Windows, wrappa in cmd /c se non già presente
        if self.is_windows and not cmd.strip().lower().startswith("cmd"):
            exec_cmd = ["cmd", "/c", cmd]
        elif self.is_windows:
            exec_cmd = cmd.split(None, 2)  # "cmd /c resto"
        else:
            exec_cmd = ["bash", "-c", cmd]

        self.log.info(f"Eseguo: {cmd}")

        try:
            result = subprocess.run(
                exec_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
                encoding="utf-8",
                errors="replace",
            )

            output = ""
            if result.stdout.strip():
                output += result.stdout.strip()
            if result.stderr.strip():
                output += f"\n[stderr] {result.stderr.strip()}"
            if result.returncode != 0:
                output += f"\n[exit code: {result.returncode}]"

            return output.strip() if output.strip() else "[comando eseguito, nessun output]"

        except subprocess.TimeoutExpired:
            return f"❌ Timeout ({timeout}s) superato per: {cmd}"
        except Exception as e:
            return f"❌ Errore esecuzione: {e}"
