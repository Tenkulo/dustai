"""
DUST AI – App Orchestrator v1.2
app.py NON crea l'agent — lo fa DustAIWindow autonomamente.
app.py si occupa solo di: bootstrap → scegliere GUI o console.
"""
import os
import sys
import logging
from pathlib import Path


class DustApp:
    VERSION = "1.2.0"
    NAME    = "DUST AI"

    def __init__(self):
        from .config import Config
        self.config = Config()
        self._setup_logging()

    def _setup_logging(self):
        log_dir = self.config.get_log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            handlers=[
                logging.FileHandler(log_dir / "dustai.log", encoding="utf-8"),
                logging.StreamHandler(sys.stdout),
            ],
        )
        self.log = logging.getLogger("DustApp")

    def run(self, skip_bootstrap=False):
        self.log.info(f"=== {self.NAME} v{self.VERSION} avviato ===")

        # Bootstrap
        if not skip_bootstrap:
            try:
                from .bootstrap import Bootstrap
                Bootstrap(workdir=self.config.get_workdir()).run()
            except Exception as e:
                self.log.warning(f"Bootstrap parziale: {e}")

        # Scegli UI
        ui_mode = os.environ.get("DUSTAI_UI", "gui")
        if ui_mode == "console":
            self._run_console()
        else:
            self._run_gui()

    def _run_gui(self):
        try:
            from PySide6.QtWidgets import QApplication
            from .ui.gui import DustAIWindow
            qt_app = QApplication.instance() or QApplication(sys.argv)
            qt_app.setStyle("Fusion")
            # DustAIWindow si inizializza da sola (agent, config, tutto)
            win = DustAIWindow()
            win.show()
            sys.exit(qt_app.exec())
        except ImportError as e:
            self.log.warning(f"PySide6 non disponibile ({e}) — uso console")
            self._run_console()
        except Exception as e:
            self.log.error(f"GUI crash: {e} — fallback console")
            import traceback; traceback.print_exc()
            self._run_console()

    def _run_console(self):
        from .config import Config
        from .agent import Agent
        from .ui.console import ConsoleUI
        agent = Agent(self.config)
        ConsoleUI(agent).run()
