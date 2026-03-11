"""
DUST AI – Bootstrap v1.1
Esegue ad ogni avvio PRIMA di caricare l'agent.
Novità v1.1:
  - CrashRecovery integrato: ogni crash viene salvato su disco
  - Al prossimo avvio: legge crash pendenti, usa Gemini per analizzarli,
    genera e applica patch automaticamente, poi riprova
  - Ogni fase è wrappata in try/except: un crash non blocca le altre
"""
import os
import sys
import json
import time
import shutil
import subprocess
import platform
import logging
import traceback
from pathlib import Path
from typing import Optional

log = logging.getLogger("Bootstrap")

IS_WINDOWS = platform.system() == "Windows"

# ─── Pacchetti Python richiesti ───────────────────────────────────────────────
# (package_name, import_name, pip_install_args)
REQUIRED_PACKAGES = [
    ("google-generativeai",  "google.generativeai",  ["google-generativeai>=0.8.0"]),
    ("requests",             "requests",              ["requests>=2.31.0"]),
    ("pyautogui",            "pyautogui",             ["pyautogui>=0.9.54"]),
    ("pillow",               "PIL",                   ["pillow>=10.0.0"]),
    ("playwright",           "playwright",            ["playwright>=1.40.0"]),
    ("python-dotenv",        "dotenv",                ["python-dotenv>=1.0.0"]),
    ("colorama",             "colorama",              ["colorama>=0.4.6"]),
    ("PySide6",              "PySide6",               ["PySide6>=6.6.0"]),
    ("ollama",               "ollama",                ["ollama>=0.2.0"]),
    ("pywin32",              "win32api",              ["pywin32>=306"]),  # Windows only
    ("psutil",               "psutil",                ["psutil>=5.9.0"]),
]

# ─── Software di sistema richiesto ────────────────────────────────────────────
SYSTEM_SOFTWARE = {
    "ollama": {
        "check_cmd": ["ollama", "--version"],
        "install_url": "https://ollama.ai/download/OllamaSetup.exe",
        "install_cmd": None,  # scaricato e avviato da installer
        "winget_id":  "Ollama.Ollama",
        "description": "Modelli AI locali (fallback offline)",
    },
    "git": {
        "check_cmd": ["git", "--version"],
        "winget_id":  "Git.Git",
        "description": "Versioning codice",
    },
}

# ─── Modelli Ollama consigliati ───────────────────────────────────────────────
OLLAMA_MODELS = [
    ("qwen3:8b",            "Modello primario locale (5.5 GB)"),
    ("mistral-small3.1",    "Modello alternativo leggero (4 GB)"),
]


class Bootstrap:
    def __init__(self, workdir: Path, silent: bool = False):
        self.workdir = workdir
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.silent = silent
        self.results = {
            "packages":  {},
            "software":  {},
            "models":    {},
            "env":       False,
            "errors":    [],
        }
        # CrashRecovery: inizializzato dopo (ha bisogno dell'api_key dal .env)
        self._crash_reporter = None

    def _init_crash_recovery(self):
        """Inizializza CrashRecovery dopo che .env è stato caricato."""
        try:
            from .crash_recovery import CrashRecoveryEngine, CrashReport
            self._crash_reporter = CrashReport(self.workdir)
            api_key = self._load_api_key()
            self._recovery_engine = CrashRecoveryEngine(self.workdir, api_key=api_key)
        except Exception as e:
            log.warning(f"CrashRecovery non disponibile: {e}")
            self._crash_reporter = None
            self._recovery_engine = None

    def _load_api_key(self) -> str:
        env_file = self.workdir / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("GOOGLE_API_KEY=") and "inserisci_qui" not in line:
                    return line.split("=", 1)[1].strip()
        return os.environ.get("GOOGLE_API_KEY", "")

    def _save_crash(self, error: Exception, phase: str, context: dict = None):
        """Salva un crash report su disco."""
        if self._crash_reporter:
            try:
                path = self._crash_reporter.save(error, context or {}, phase)
                self._print(f"  💾 Crash salvato: {path.name}")
                self._print(f"     Al prossimo avvio verrà risolto automaticamente.")
            except Exception:
                pass

    def run(self) -> bool:
        """
        Esegue tutti i check e installa ciò che manca.
        Ogni fase è wrappata: un crash non blocca le fasi successive.
        Al prossimo avvio, i crash salvati vengono risolti automaticamente.
        """
        self._print("🚀 DUST AI Bootstrap v1.1 - Controllo dipendenze...")
        self._print("=" * 55)

        # ── Fase 0: risolvi crash del run precedente ──────────────────────
        self._run_phase("crash_recovery", self._resolve_previous_crashes)

        ok = True
        ok &= self._run_phase("python_version",   self._check_python_version,   critical=True)
        ok &= self._run_phase("pip_packages",      self._install_pip_packages,   critical=True)
        ok &= self._run_phase("playwright",        self._setup_playwright)
        ok &= self._run_phase("env_file",          self._setup_env_file)

        # Init crash recovery dopo che .env è disponibile
        self._init_crash_recovery()

        if IS_WINDOWS:
            self._run_phase("system_software", self._install_system_software)
            self._run_phase("ollama",          self._setup_ollama)
            self._run_phase("igpu",            self._configure_igpu)

        self._print_summary()
        return ok

    def _run_phase(self, phase_name: str, fn, critical: bool = False) -> bool:
        """
        Esegue una fase del bootstrap wrappata in try/except.
        Se crasha: salva il report e continua (a meno che critical=True).
        """
        try:
            result = fn()
            return result if result is not None else True
        except KeyboardInterrupt:
            self._print(f"
  ⏹  Bootstrap interrotto dall'utente durante: {phase_name}")
            raise
        except Exception as e:
            self._print(f"
  ❌ Crash in fase [{phase_name}]: {type(e).__name__}: {e}")
            self._save_crash(e, phase=phase_name, context={"phase": phase_name})
            if critical:
                self._print(f"  ⚠️  Fase critica fallita — DUST AI potrebbe non avviarsi correttamente")
            else:
                self._print(f"  ↩️  Continuo con le fasi successive...")
            return False

    def _resolve_previous_crashes(self):
        """Risolve crash del run precedente prima di fare qualsiasi altra cosa."""
        try:
            from .crash_recovery import CrashRecoveryEngine, CrashReport
            reporter = CrashReport(self.workdir)
            pending = reporter.load_unresolved()
            if not pending:
                return True
            api_key = self._load_api_key()
            engine = CrashRecoveryEngine(self.workdir, api_key=api_key)
            engine.run()
        except ImportError:
            pass  # crash_recovery.py non ancora disponibile
        except Exception as e:
            log.warning(f"Crash recovery fallita: {e}")
        return True

    # ─── Python version ──────────────────────────────────────────────────────

    def _check_python_version(self) -> bool:
        major, minor = sys.version_info[:2]
        if major < 3 or (major == 3 and minor < 10):
            self._error(f"Python {major}.{minor} non supportato. Richiesto: 3.10+")
            self._print(f"  Scarica Python 3.12: https://python.org/downloads/")
            return False
        self._ok(f"Python {major}.{minor}")
        return True

    # ─── Pacchetti pip ───────────────────────────────────────────────────────

    def _install_pip_packages(self) -> bool:
        self._print("\n📦 Controllo pacchetti Python...")
        all_ok = True

        for pkg_name, import_name, pip_args in REQUIRED_PACKAGES:
            # Skip pywin32 su non-Windows
            if pkg_name == "pywin32" and not IS_WINDOWS:
                continue

            if self._can_import(import_name):
                self._ok(f"  {pkg_name}")
                self.results["packages"][pkg_name] = "ok"
                continue

            self._print(f"  ⬇  Installo {pkg_name}...")
            success, out = self._pip_install(pip_args)
            if success:
                self._ok(f"  {pkg_name} installato")
                self.results["packages"][pkg_name] = "installed"
            else:
                self._warn(f"  {pkg_name} fallito: {out[:120]}")
                self.results["packages"][pkg_name] = "failed"
                if pkg_name not in ("pywin32", "PySide6", "ollama"):  # non critici
                    all_ok = False

        # pywin32 post-install (richiede script speciale su Windows)
        if IS_WINDOWS and self._can_import("win32api"):
            try:
                scripts_dir = Path(sys.prefix) / "Scripts"
                post_install = scripts_dir / "pywin32_postinstall.py"
                if post_install.exists():
                    subprocess.run(
                        [sys.executable, str(post_install), "-install"],
                        capture_output=True, timeout=30
                    )
            except Exception:
                pass

        return all_ok

    # ─── Playwright ──────────────────────────────────────────────────────────

    def _setup_playwright(self) -> bool:
        self._print("\n🌐 Controllo Playwright + Chromium...")
        if not self._can_import("playwright"):
            self._warn("  Playwright non installato, salto browser setup")
            return True  # non critico

        # Verifica se Chromium è già installato
        try:
            result = subprocess.run(
                [sys.executable, "-m", "playwright", "install", "--dry-run", "chromium"],
                capture_output=True, text=True, timeout=15
            )
            already = "chromium" in result.stdout.lower() and "download" not in result.stdout.lower()
        except Exception:
            already = False

        # Controlla cache browsers
        cache_dirs = [
            Path.home() / "AppData" / "Local" / "ms-playwright",
            Path.home() / ".cache" / "ms-playwright",
        ]
        browsers_exist = any(d.exists() and any(d.iterdir()) for d in cache_dirs if d.exists())

        if browsers_exist:
            self._ok("  Chromium già installato")
            return True

        self._print("  ⬇  Installo Chromium (prima volta, ~150 MB)...")
        try:
            result = subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                capture_output=True, text=True, timeout=300
            )
            if result.returncode == 0:
                self._ok("  Chromium installato")
                return True
            else:
                self._warn(f"  Chromium: {result.stderr[:100]}")
                return True  # non critico
        except subprocess.TimeoutExpired:
            self._warn("  Chromium: timeout (rete lenta). Riprova più tardi.")
            return True

    # ─── Software di sistema ─────────────────────────────────────────────────

    def _install_system_software(self):
        self._print("\n🖥  Controllo software di sistema...")
        for name, info in SYSTEM_SOFTWARE.items():
            if self._command_exists(info["check_cmd"]):
                self._ok(f"  {name}")
                self.results["software"][name] = "ok"
                continue

            self._print(f"  ⬇  {name} non trovato – tento installazione via winget...")
            success = self._winget_install(info.get("winget_id", ""))
            if success:
                self._ok(f"  {name} installato via winget")
                self.results["software"][name] = "installed"
            else:
                self._warn(f"  {name} non installabile automaticamente")
                self._warn(f"       Scarica manualmente: {info.get('install_url','')}")
                self.results["software"][name] = "manual_required"

    # ─── Ollama setup ────────────────────────────────────────────────────────

    def _setup_ollama(self):
        self._print("\n🦙 Controllo Ollama + modelli locali...")

        # Controlla se Ollama è in esecuzione
        ollama_running = self._is_ollama_running()

        if not ollama_running:
            if not self._command_exists(["ollama", "--version"]):
                self._warn("  Ollama non installato.")
                self._warn("  Scarica da: https://ollama.ai  oppure:")
                self._warn("  winget install Ollama.Ollama")
                return
            # Avvia servizio Ollama — NO capture_output per evitare blocchi
            self._print("  ▶  Avvio Ollama serve...")
            kwargs = {
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
            }
            if IS_WINDOWS:
                # CREATE_NO_WINDOW solo su Windows, accesso sicuro all'attributo
                kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            subprocess.Popen(["ollama", "serve"], **kwargs)
            # Aspetta fino a 10s che il server risponda
            for _ in range(10):
                time.sleep(1)
                if self._is_ollama_running():
                    break
            ollama_running = self._is_ollama_running()

        if not ollama_running:
            self._warn("  Ollama non raggiungibile (porta 11434)")
            return

        self._ok("  Ollama in esecuzione")

        # Controlla modelli disponibili via SDK (struttura compatibile v0.2+)
        existing = self._ollama_list_models()

        for model_name, description in OLLAMA_MODELS:
            short = model_name.split(":")[0]
            has_model = any(short in m for m in existing)
            if has_model:
                self._ok(f"  Modello {model_name}")
                self.results["models"][model_name] = "ok"
            else:
                self._print(f"  ⬇  Pull {model_name} ({description})...")
                success = self._ollama_pull_streaming(model_name)
                if success:
                    self._ok(f"  {model_name} scaricato")
                    self.results["models"][model_name] = "pulled"
                else:
                    self._warn(f"  {model_name}: pull fallito (vedi log)")
                    self._warn(f"  Puoi farlo manualmente: ollama pull {model_name}")
                    self.results["models"][model_name] = "failed"

    def _ollama_list_models(self) -> set:
        """
        Ritorna i nomi dei modelli installati.
        Compatibile con ollama SDK v0.2+ (struttura risposta cambiata).
        """
        try:
            import ollama as ol
            resp = ol.list()
            # SDK v0.2+: resp.models è lista di oggetti con .model
            if hasattr(resp, "models"):
                return {m.model for m in resp.models if hasattr(m, "model")}
            # Fallback: risposta dict raw
            if isinstance(resp, dict) and "models" in resp:
                return {m.get("name", m.get("model", "")) for m in resp["models"]}
            return set()
        except Exception as e:
            log.warning(f"ollama list fallito: {e}")
            # Fallback via HTTP diretto
            try:
                import requests
                r = requests.get("http://127.0.0.1:11434/api/tags", timeout=5)
                data = r.json()
                return {m.get("name", "") for m in data.get("models", [])}
            except Exception:
                return set()

    def _ollama_pull_streaming(self, model_name: str) -> bool:
        """
        Scarica un modello Ollama con streaming SDK.
        - Nessun timeout fisso
        - Progress in tempo reale (non bufferizza in RAM)
        - Resume automatico se interrotto (Ollama gestisce i layer già scaricati)
        - Non crasha su download grandi
        """
        try:
            import ollama as ol

            last_status = ""
            last_pct = -1

            # stream=True: riceve chunk progressivi, nessun buffer in RAM
            for progress in ol.pull(model_name, stream=True):
                # Compatibilità struttura risposta v0.2+
                if hasattr(progress, "status"):
                    status   = progress.status or ""
                    total    = getattr(progress, "total",     0) or 0
                    completed = getattr(progress, "completed", 0) or 0
                elif isinstance(progress, dict):
                    status    = progress.get("status", "")
                    total     = progress.get("total",     0) or 0
                    completed = progress.get("completed", 0) or 0
                else:
                    continue

                # Calcola percentuale
                if total > 0:
                    pct = int(completed / total * 100)
                else:
                    pct = 0

                # Stampa solo se cambia di 5% o status cambia (evita spam)
                if status != last_status or pct >= last_pct + 5:
                    bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
                    size_mb = f"{completed/1024/1024:.0f}/{total/1024/1024:.0f} MB" if total > 0 else ""
                    print(f"\r     [{bar}] {pct:3d}% {status[:30]:<30} {size_mb}", end="", flush=True)
                    last_status = status
                    last_pct    = pct

            print()  # newline dopo la progress bar
            return True

        except KeyboardInterrupt:
            print()
            self._warn(f"  Pull {model_name} interrotto dall'utente.")
            self._warn(f"  Riprendi con: ollama pull {model_name}  (riprende dal punto di interruzione)")
            return False
        except Exception as e:
            print()
            log.warning(f"ollama pull SDK fallito ({e}), tento via subprocess...")
            # Fallback subprocess SENZA capture_output — output va direttamente al terminale
            # Nessun timeout: il download può durare ore su rete lenta
            try:
                result = subprocess.run(
                    ["ollama", "pull", model_name],
                    stdout=None,   # eredita stdout del processo padre → nessun buffering
                    stderr=None,   # stessa cosa per stderr
                    timeout=None,  # nessun timeout
                )
                return result.returncode == 0
            except KeyboardInterrupt:
                self._warn(f"  Pull interrotto. Riprendi con: ollama pull {model_name}")
                return False
            except Exception as e2:
                self._warn(f"  Pull fallito definitivamente: {e2}")
                return False

    # ─── iGPU acceleration ───────────────────────────────────────────────────

    def _configure_igpu(self):
        """Configura variabili d'ambiente per iGPU AMD Radeon (Ryzen 5600G)."""
        env_vars = {
            "OLLAMA_GPU_LAYERS": "18",
            "OLLAMA_NUM_GPU":    "1",
            "OLLAMA_HOST":       "127.0.0.1:11434",
        }
        changed = False
        for key, value in env_vars.items():
            current = os.environ.get(key, "")
            if current != value:
                try:
                    subprocess.run(
                        ["powershell", "-Command",
                         f'[System.Environment]::SetEnvironmentVariable("{key}", "{value}", "User")'],
                        capture_output=True, timeout=10
                    )
                    os.environ[key] = value
                    changed = True
                except Exception:
                    pass
        if changed:
            self._ok("  Variabili iGPU configurate (OLLAMA_GPU_LAYERS=18)")

    # ─── File .env ───────────────────────────────────────────────────────────

    def _setup_env_file(self) -> bool:
        env_file = self.workdir / ".env"
        if env_file.exists():
            # Controlla che le keys siano valorizzate
            content = env_file.read_text(encoding="utf-8")
            has_google = "GOOGLE_API_KEY=" in content and "inserisci_qui" not in content
            if has_google:
                self._ok("  File .env con API keys configurato")
                self.results["env"] = True
                return True
            else:
                self._warn("  .env trovato ma GOOGLE_API_KEY non configurata")
                self._print(f"  Apri: {env_file}")
                self._print("  Inserisci la tua Gemini API key da: https://aistudio.google.com")
                self.results["env"] = False
                return False  # non critico ma segnaliamo

        # Crea .env di default
        template = (
            "# DUST AI – API Keys\n"
            "# Ottieni Gemini key da: https://aistudio.google.com\n"
            "# Ottieni Perplexity key da: https://perplexity.ai/settings/api\n\n"
            "GOOGLE_API_KEY=inserisci_qui_la_tua_gemini_key\n"
            "PERPLEXITY_API_KEY=inserisci_qui_la_tua_perplexity_key\n"
        )
        env_file.write_text(template, encoding="utf-8")
        self._warn(f"  File .env creato: {env_file}")
        self._warn("  ⚠  CONFIGURA GOOGLE_API_KEY prima di avviare DUST AI")

        # Apri il file automaticamente su Windows
        if IS_WINDOWS:
            try:
                os.startfile(str(env_file))
            except Exception:
                pass

        self.results["env"] = False
        return False

    # ─── Helpers ─────────────────────────────────────────────────────────────

    def _can_import(self, module: str) -> bool:
        try:
            __import__(module.split(".")[0])
            return True
        except ImportError:
            return False

    def _pip_install(self, args: list) -> tuple[bool, str]:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--quiet", "--upgrade"] + args,
                capture_output=True, text=True, timeout=120
            )
            return result.returncode == 0, result.stderr
        except Exception as e:
            return False, str(e)

    def _command_exists(self, cmd: list) -> bool:
        try:
            subprocess.run(cmd, capture_output=True, timeout=5)
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _winget_install(self, package_id: str) -> bool:
        if not package_id:
            return False
        try:
            result = subprocess.run(
                ["winget", "install", "--id", package_id, "--silent", "--accept-package-agreements", "--accept-source-agreements"],
                capture_output=True, text=True, timeout=180
            )
            return result.returncode == 0
        except Exception:
            return False

    def _is_ollama_running(self) -> bool:
        try:
            import requests
            r = requests.get("http://127.0.0.1:11434/api/tags", timeout=3)
            return r.status_code == 200
        except Exception:
            return False

    def _print(self, msg: str):
        if not self.silent:
            print(msg)
        log.info(msg)

    def _ok(self, msg: str):
        self._print(f"  ✅{msg}")

    def _warn(self, msg: str):
        self._print(f"  ⚠️ {msg}")
        self.results["errors"].append(msg)

    def _error(self, msg: str):
        self._print(f"  ❌ {msg}")
        self.results["errors"].append(f"ERROR: {msg}")

    def _print_summary(self):
        self._print("\n" + "=" * 55)
        errors = [e for e in self.results["errors"] if "ERROR:" in e]
        warnings = [e for e in self.results["errors"] if "ERROR:" not in e]
        if not errors and not warnings:
            self._print("✅ Bootstrap completato — tutto pronto!")
        elif not errors:
            self._print(f"✅ Bootstrap completato con {len(warnings)} avvisi")
        else:
            self._print(f"❌ Bootstrap: {len(errors)} errori critici")
        self._print("=" * 55 + "\n")


# ─── Dependency Manager (usato dall'agent a runtime) ─────────────────────────

class DependencyManager:
    """
    Gestisce dipendenze a runtime: se un import fallisce durante l'esecuzione,
    installa il pacchetto al volo e riprova.
    """

    IMPORT_TO_PIP = {
        "playwright":        ["playwright>=1.40.0"],
        "pyautogui":         ["pyautogui>=0.9.54"],
        "PIL":               ["pillow>=10.0.0"],
        "win32api":          ["pywin32>=306"],
        "PySide6":           ["PySide6>=6.6.0"],
        "ollama":            ["ollama>=0.2.0"],
        "psutil":            ["psutil>=5.9.0"],
        "dotenv":            ["python-dotenv>=1.0.0"],
        "colorama":          ["colorama>=0.4.6"],
        "requests":          ["requests>=2.31.0"],
        "google.generativeai": ["google-generativeai>=0.8.0"],
    }

    @classmethod
    def ensure(cls, module: str) -> bool:
        """Assicura che un modulo sia importabile, installandolo se necessario."""
        try:
            __import__(module.split(".")[0])
            return True
        except ImportError:
            pip_args = cls.IMPORT_TO_PIP.get(module, [module])
            print(f"📦 Auto-install: {pip_args[0]}...")
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "--quiet"] + pip_args,
                    capture_output=True, text=True, timeout=120
                )
                if result.returncode == 0:
                    print(f"  ✅ {pip_args[0]} installato")
                    return True
                else:
                    print(f"  ❌ Installazione fallita: {result.stderr[:100]}")
                    return False
            except Exception as e:
                print(f"  ❌ Errore: {e}")
                return False

    @classmethod
    def safe_import(cls, module: str):
        """Import sicuro: installa se necessario, ritorna il modulo o None."""
        cls.ensure(module)
        try:
            return __import__(module)
        except ImportError:
            return None


# ─── Entry point standalone ──────────────────────────────────────────────────

if __name__ == "__main__":
    workdir = Path(os.environ.get("APPDATA", Path.home())) / "dustai"
    bootstrap = Bootstrap(workdir=workdir, silent=False)
    success = bootstrap.run()
    sys.exit(0 if success else 1)
