"""
DUST AI – CrashRecovery v1.0
Sistema di crash recovery persistente.

Flusso:
  AL CRASH:
    1. Intercetta l'eccezione ovunque nel bootstrap
    2. Salva crash report completo su disco (JSON + traceback)
    3. Tenta fix immediato se classificabile
    4. Segnala all'utente

  AL PROSSIMO AVVIO:
    1. Legge tutti i crash report non risolti
    2. Per ogni crash: usa Gemini per analizzare causa + generare patch
    3. Applica la patch al file sorgente (con backup)
    4. Marca il crash come risolto
    5. Riprova l'operazione che aveva crashato
"""

import os
import sys
import json
import time
import logging
import traceback
import subprocess
import hashlib
import difflib
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable

log = logging.getLogger("CrashRecovery")

CRASH_DIR_NAME = "crash_reports"
MAX_REPORTS_KEPT = 50

# ─── Classificazione crash ────────────────────────────────────────────────────

CRASH_PATTERNS = {
    "ollama_pull_buffer":   ["capture_output", "timeout", "ollama", "pull", "MemoryError", "TimeoutExpired"],
    "ollama_sdk_struct":    ["ol.list", "models", "AttributeError", "has no attribute"],
    "subprocess_no_window": ["CREATE_NO_WINDOW", "AttributeError", "subprocess"],
    "import_error":         ["ModuleNotFoundError", "ImportError", "No module named"],
    "pip_install":          ["pip", "install", "ERROR", "Could not"],
    "playwright":           ["playwright", "chromium", "Executable", "TimeoutExpired"],
    "ollama_not_running":   ["ConnectionRefusedError", "11434", "ollama", "serve"],
    "permission_error":     ["PermissionError", "Access is denied", "WinError 5"],
    "network_error":        ["ConnectionError", "Timeout", "SSLError", "requests"],
    "json_parse":           ["json.decoder", "JSONDecodeError", "Expecting value"],
}

QUICK_FIXES = {
    "ollama_pull_buffer": {
        "description": "Pull Ollama con subprocess+capture_output bufferizza in RAM → crash",
        "fix": "migrate_to_streaming_pull",
    },
    "ollama_sdk_struct": {
        "description": "Struttura risposta Ollama SDK cambiata in v0.2+",
        "fix": "add_hasattr_fallback",
    },
    "subprocess_no_window": {
        "description": "CREATE_NO_WINDOW non disponibile come attributo diretto",
        "fix": "use_getattr_fallback",
    },
    "import_error": {
        "description": "Modulo Python mancante",
        "fix": "pip_install_missing",
    },
    "ollama_not_running": {
        "description": "Ollama serve non avviato o lento ad avviarsi",
        "fix": "increase_wait_and_retry",
    },
}


def classify_crash(error_text: str, traceback_text: str) -> str:
    combined = (error_text + " " + traceback_text).lower()
    for crash_type, patterns in CRASH_PATTERNS.items():
        if sum(1 for p in patterns if p.lower() in combined) >= 2:
            return crash_type
    return "unknown"


# ─── CrashReport ─────────────────────────────────────────────────────────────

class CrashReport:
    def __init__(self, workdir: Path):
        self.workdir = workdir
        self.crash_dir = workdir / CRASH_DIR_NAME
        self.crash_dir.mkdir(parents=True, exist_ok=True)

    def save(self, error: Exception, context: dict, phase: str) -> Path:
        """Salva un crash report su disco e ritorna il path."""
        tb = traceback.format_exc()
        error_str = str(error)
        crash_type = classify_crash(error_str, tb)

        report = {
            "id":           hashlib.md5(f"{error_str}{time.time()}".encode()).hexdigest()[:8],
            "timestamp":    datetime.now().isoformat(),
            "phase":        phase,
            "crash_type":   crash_type,
            "error":        error_str,
            "error_class":  type(error).__name__,
            "traceback":    tb,
            "context":      context,
            "python":       sys.version,
            "platform":     sys.platform,
            "resolved":     False,
            "fix_attempts": [],
        }

        filename = f"crash_{report['id']}_{phase}_{crash_type}.json"
        path = self.crash_dir / filename
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

        log.warning(f"Crash salvato: {path.name}")
        return path

    def load_unresolved(self) -> list[dict]:
        """Carica tutti i crash report non risolti."""
        reports = []
        for f in sorted(self.crash_dir.glob("crash_*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if not data.get("resolved", False):
                    data["_file"] = str(f)
                    reports.append(data)
            except Exception:
                pass
        return reports

    def mark_resolved(self, report: dict, fix_description: str):
        """Marca un crash come risolto."""
        f = Path(report["_file"])
        if f.exists():
            data = json.loads(f.read_text(encoding="utf-8"))
            data["resolved"] = True
            data["resolved_at"] = datetime.now().isoformat()
            data["fix_applied"] = fix_description
            f.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def mark_failed(self, report: dict, reason: str):
        """Aggiunge un tentativo fallito al report."""
        f = Path(report["_file"])
        if f.exists():
            data = json.loads(f.read_text(encoding="utf-8"))
            data["fix_attempts"].append({
                "timestamp": datetime.now().isoformat(),
                "reason": reason,
            })
            f.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def cleanup_old(self):
        """Mantieni solo gli ultimi MAX_REPORTS_KEPT report."""
        files = sorted(self.crash_dir.glob("crash_*.json"))
        for f in files[:-MAX_REPORTS_KEPT]:
            f.unlink(missing_ok=True)


# ─── CrashRecoveryEngine ─────────────────────────────────────────────────────

class CrashRecoveryEngine:
    """
    Si attiva ad ogni avvio: legge crash report pendenti,
    usa Gemini per generare fix, applica patch, riprova.
    """

    def __init__(self, workdir: Path, api_key: str = ""):
        self.workdir = workdir
        self.src_root = Path(__file__).parent
        self.reporter = CrashReport(workdir)
        self.api_key = api_key or os.environ.get("GOOGLE_API_KEY", "")

    def run(self) -> int:
        """
        Controlla crash pendenti e tenta di risolverli.
        Ritorna il numero di crash risolti.
        """
        reports = self.reporter.load_unresolved()
        if not reports:
            return 0

        print(f"\n🚨 Trovati {len(reports)} crash non risolti dal run precedente.")
        resolved = 0

        for report in reports:
            print(f"\n🔬 Analizzo crash: [{report['crash_type']}] {report['error'][:80]}")
            print(f"   Fase: {report['phase']} | {report['timestamp'][:19]}")

            success = self._resolve(report)
            if success:
                resolved += 1
                print(f"   ✅ Risolto automaticamente")
            else:
                print(f"   ⚠️  Non risolto automaticamente — continuo comunque")

        if resolved:
            print(f"\n✅ {resolved}/{len(reports)} crash risolti prima dell'avvio.\n")

        self.reporter.cleanup_old()
        return resolved

    def _resolve(self, report: dict) -> bool:
        """Tenta di risolvere un crash con tutti i metodi disponibili."""
        crash_type = report.get("crash_type", "unknown")
        attempts = len(report.get("fix_attempts", []))

        # Dopo 5 tentativi falliti → skip
        if attempts >= 5:
            print(f"   ⏭  Saltato (troppi tentativi falliti: {attempts})")
            return False

        # 1. Prova fix predefinito veloce
        quick = QUICK_FIXES.get(crash_type)
        if quick:
            print(f"   💡 Fix predefinito: {quick['description']}")
            success = self._apply_quick_fix(report, quick["fix"])
            if success:
                self.reporter.mark_resolved(report, f"quick_fix:{quick['fix']}")
                return True
            self.reporter.mark_failed(report, f"quick_fix {quick['fix']} fallito")

        # 2. Se Gemini disponibile → genera fix con LLM
        if self.api_key:
            print(f"   🤖 Chiedo a Gemini di analizzare e generare fix...")
            success = self._llm_fix(report)
            if success:
                self.reporter.mark_resolved(report, "llm_generated_patch")
                return True
            self.reporter.mark_failed(report, "llm fix fallito")

        # 3. Fix universale: reinstalla il pacchetto coinvolto
        if "ModuleNotFoundError" in report.get("error_class", ""):
            success = self._reinstall_from_traceback(report)
            if success:
                self.reporter.mark_resolved(report, "reinstall_package")
                return True

        return False

    # ─── Quick fixes predefiniti ─────────────────────────────────────────────

    def _apply_quick_fix(self, report: dict, fix_name: str) -> bool:
        if fix_name == "migrate_to_streaming_pull":
            return self._patch_file(
                "bootstrap.py",
                find="""result = subprocess.run(
                        ["ollama", "pull", model_name],
                        capture_output=True, text=True, timeout=600
                    )""",
                replace="""success = self._ollama_pull_streaming(model_name)
                    result = type('R', (), {'returncode': 0 if success else 1})()""",
                description="Migrato ollama pull da subprocess a streaming SDK"
            )

        elif fix_name == "use_getattr_fallback":
            return self._patch_file(
                "bootstrap.py",
                find="creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0,",
                replace='creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if IS_WINDOWS else 0,',
                description="Usato getattr per CREATE_NO_WINDOW con fallback numerico"
            )

        elif fix_name == "add_hasattr_fallback":
            return self._patch_file(
                "bootstrap.py",
                find="existing = {m.model for m in ol.list().models}",
                replace="""resp = ol.list()
            if hasattr(resp, 'models'):
                existing = {m.model for m in resp.models if hasattr(m, 'model')}
            elif isinstance(resp, dict):
                existing = {m.get('name', m.get('model', '')) for m in resp.get('models', [])}
            else:
                existing = set()""",
                description="Aggiunto controllo hasattr per compatibilità SDK Ollama v0.2+"
            )

        elif fix_name == "pip_install_missing":
            # Estrai nome modulo dalla traceback
            tb = report.get("traceback", "")
            import re
            m = re.search(r"No module named '([^']+)'", tb)
            if m:
                module = m.group(1).split(".")[0]
                print(f"   ⬇  Installo modulo mancante: {module}")
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "--quiet", module],
                    capture_output=True, text=True, timeout=120
                )
                return result.returncode == 0

        elif fix_name == "increase_wait_and_retry":
            return self._patch_file(
                "bootstrap.py",
                find="time.sleep(3)\n            ollama_running = self._is_ollama_running()",
                replace="""for _ in range(10):
                time.sleep(1)
                if self._is_ollama_running():
                    break
            ollama_running = self._is_ollama_running()""",
                description="Aumentato wait Ollama serve da 3s fisso a 10s con polling"
            )

        return False

    # ─── LLM Fix via Gemini ──────────────────────────────────────────────────

    def _llm_fix(self, report: dict) -> bool:
        """Usa Gemini per analizzare il crash e generare una patch."""
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel("gemini-2.5-flash")

            # Leggi il file sorgente coinvolto
            src_file, src_code = self._find_source_in_traceback(report.get("traceback", ""))

            prompt = f"""Sei un esperto Python. Analizza questo crash di DUST AI e genera una patch.

## Crash Report
- Tipo: {report['crash_type']}
- Errore: {report['error']}
- Classe: {report['error_class']}
- Fase: {report['phase']}

## Traceback
```
{report['traceback'][-2000:]}
```

## Contesto
{json.dumps(report.get('context', {}), indent=2)[:500]}

## Codice sorgente ({src_file or 'N/A'})
```python
{src_code[:3000] if src_code else 'N/A'}
```

## Istruzioni
Analizza la causa radice e genera una patch minimale.
Rispondi SOLO con JSON valido, nessun testo aggiuntivo:

{{
  "analysis": "causa radice in 1-2 frasi",
  "can_fix": true,
  "file": "nome_file.py",
  "find": "stringa esatta da trovare nel codice (copia dal sorgente)",
  "replace": "stringa sostitutiva corretta",
  "explanation": "cosa cambia e perché funziona"
}}

Se non puoi generare un fix sicuro, rispondi: {{"can_fix": false, "analysis": "motivo"}}
"""
            response = model.generate_content(prompt)
            raw = response.text.strip()
            # Pulisci markdown
            import re
            raw = re.sub(r"```json|```", "", raw).strip()
            data = json.loads(raw)

            if not data.get("can_fix", False):
                print(f"   ℹ️  Gemini: {data.get('analysis', 'fix non possibile')}")
                return False

            print(f"   📝 Analisi: {data.get('analysis', '')}")
            print(f"   ✏️  Fix: {data.get('explanation', '')}")

            return self._patch_file(
                data["file"],
                find=data["find"],
                replace=data["replace"],
                description=f"LLM patch: {data.get('analysis', '')}"
            )

        except Exception as e:
            log.warning(f"LLM fix fallito: {e}")
            return False

    # ─── Patch file ──────────────────────────────────────────────────────────

    def _patch_file(self, filename: str, find: str, replace: str, description: str) -> bool:
        """Applica una patch a un file sorgente con backup automatico."""
        # Cerca il file nella directory src
        candidates = [
            self.src_root / filename,
            self.src_root / filename.replace("bootstrap.py", "bootstrap.py"),
        ]
        for path in candidates:
            if path.exists():
                target = path
                break
        else:
            log.warning(f"File non trovato per patch: {filename}")
            return False

        try:
            original = target.read_text(encoding="utf-8")
            if find not in original:
                log.warning(f"Stringa 'find' non trovata in {filename}")
                return False

            # Backup con timestamp
            backup = target.with_suffix(f".py.bak_{int(time.time())}")
            backup.write_text(original, encoding="utf-8")

            # Applica patch
            patched = original.replace(find, replace, 1)
            target.write_text(patched, encoding="utf-8")

            # Mostra diff
            diff = list(difflib.unified_diff(
                original.splitlines(),
                patched.splitlines(),
                fromfile=f"{filename} (prima)",
                tofile=f"{filename} (dopo)",
                lineterm=""
            ))
            if diff:
                print(f"   📊 Patch applicata a {filename}:")
                for line in diff[:15]:
                    if line.startswith("+") and not line.startswith("+++"):
                        print(f"      \033[32m{line}\033[0m")
                    elif line.startswith("-") and not line.startswith("---"):
                        print(f"      \033[31m{line}\033[0m")

            log.info(f"Patch applicata: {filename} — {description}")
            return True

        except Exception as e:
            log.error(f"Patch fallita su {filename}: {e}")
            return False

    # ─── Helpers ─────────────────────────────────────────────────────────────

    def _find_source_in_traceback(self, tb: str) -> tuple[str, str]:
        """Trova il file sorgente DUST AI nella traceback e ne legge il codice."""
        import re
        for match in re.finditer(r'File "([^"]*dustai[^"]*\.py)"', tb):
            path = Path(match.group(1))
            if path.exists():
                try:
                    return path.name, path.read_text(encoding="utf-8")
                except Exception:
                    pass
        return "", ""

    def _reinstall_from_traceback(self, report: dict) -> bool:
        """Reinstalla il pacchetto menzionato nella traceback."""
        import re
        tb = report.get("traceback", "")
        m = re.search(r"No module named '([^']+)'", tb)
        if not m:
            return False
        module = m.group(1).split(".")[0]
        print(f"   ⬇  Reinstallo: {module}")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "--quiet", module],
            capture_output=True, text=True, timeout=120
        )
        return result.returncode == 0
