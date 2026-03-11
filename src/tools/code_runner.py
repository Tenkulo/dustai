"""
DUST AI – CodeRunnerTool v2.0
Esecuzione Python sicura con timeout e capture output.
"""
import sys
import logging
import subprocess
import tempfile
from pathlib import Path

log = logging.getLogger("CodeRunnerTool")


class CodeRunnerTool:
    def __init__(self, config):
        self.config = config

    def code_run(self, code: str, timeout: int = 60) -> str:
        if not code:
            return "❌ Codice vuoto"
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False,
                encoding="utf-8", dir=str(self.config.get_base_path() / "cache")
            ) as f:
                f.write(code)
                tmp_path = f.name

            result = subprocess.run(
                [sys.executable, tmp_path],
                capture_output=True, text=True,
                timeout=timeout, encoding="utf-8", errors="replace",
            )
            Path(tmp_path).unlink(missing_ok=True)

            stdout = result.stdout.strip()
            stderr = result.stderr.strip()
            code_r = result.returncode

            if code_r != 0:
                out = "❌ [exit " + str(code_r) + "]"
                if stderr:
                    out += "\n" + stderr[:800]
                return out

            return stdout or "(nessun output)"

        except subprocess.TimeoutExpired:
            return "❌ Timeout (" + str(timeout) + "s)"
        except Exception as e:
            return "❌ code_run: " + str(e)
