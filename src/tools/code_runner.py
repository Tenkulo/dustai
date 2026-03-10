"""
DUST AI – Tool: code_runner
Esegue codice Python in un processo separato.
Output catturato e restituito all'agente.
"""
import subprocess
import sys
import logging
import tempfile
import os
from pathlib import Path


class CodeRunnerTool:
    def __init__(self, config):
        self.config = config
        self.log = logging.getLogger("CodeRunnerTool")

    def code_run(self, code: str, timeout: int = 30, language: str = "python") -> str:
        """
        Esegue codice Python e restituisce l'output.
        
        Il codice gira in un processo separato per sicurezza.
        Lavora nella workdir dell'utente.
        """
        if language.lower() not in ("python", "py"):
            return f"❌ Linguaggio non supportato: {language}. Usa 'python'."

        # Scrivi codice in file temporaneo
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".py",
                delete=False,
                encoding="utf-8",
                dir=str(self.config.get_workdir())
            ) as f:
                f.write(code)
                temp_path = f.name

            self.log.info(f"Eseguo codice Python: {temp_path}")

            result = subprocess.run(
                [sys.executable, temp_path],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(self.config.get_workdir()),
                encoding="utf-8",
                errors="replace",
            )

            output = ""
            if result.stdout.strip():
                output += result.stdout.strip()
            if result.stderr.strip():
                output += f"\n[stderr]\n{result.stderr.strip()}"
            if result.returncode != 0:
                output += f"\n[exit code: {result.returncode}]"

            return output.strip() if output.strip() else "[codice eseguito, nessun output]"

        except subprocess.TimeoutExpired:
            return f"❌ Timeout ({timeout}s) superato"
        except Exception as e:
            return f"❌ Errore esecuzione codice: {e}"
        finally:
            # Pulisci file temporaneo
            try:
                os.unlink(temp_path)
            except Exception:
                pass
