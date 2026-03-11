"""
DUST AI – App Orchestrator v1.1
Esegue Bootstrap prima di avviare l'agent.
"""
import os
import sys
import logging
from pathlib import Path


class DustApp:
    VERSION = "1.1.0"
    NAME = "DUST AI"

    def __init__(self):
        from .config import Config
        self.config = Config()
        self.agent = None
        self.ui = None
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

    def run(self, skip_bootstrap: bool = False):
        self.log.info(f"=== {self.NAME} v{self.VERSION} avviato ===")
        print(f"\n🤖 {self.NAME} v{self.VERSION}")
        print("=" * 50)

        # ── Bootstrap: installa tutto il necessario ──────────────────────────
        if not skip_bootstrap:
            try:
                from .bootstrap import Bootstrap
                bs = Bootstrap(workdir=self.config.get_workdir(), silent=False)
                bs.run()
            except Exception as e:
                self.log.warning(f"Bootstrap parziale: {e}")
                print(f"⚠️  Bootstrap: {e}")

        # ── Inizializza agent ────────────────────────────────────────────────
        from .agent import Agent
        self.agent = Agent(self.config)

        # ── Scegli UI ────────────────────────────────────────────────────────
        ui_mode = os.environ.get("DUSTAI_UI", "auto")

        if ui_mode == "gui" or (ui_mode == "auto" and self._has_display()):
            try:
                from .ui.gui import DustAIWindow
                from PySide6.QtWidgets import QApplication
                app = QApplication(sys.argv)
                app.setStyle("Fusion")
                window = DustAIWindow(agent=self.agent, config=self.config)
                window.show()
                sys.exit(app.exec())
            except Exception as e:
                self.log.warning(f"GUI non disponibile ({e}), uso console")
                self._run_console()
        else:
            self._run_console()

    def _run_console(self):
        from .ui.console import ConsoleUI
        ui = ConsoleUI(self.agent)
        ui.run()

    def _has_display(self) -> bool:
        """Ritorna True se c'è un display disponibile (GUI possibile)."""
        import platform
        if platform.system() == "Windows":
            return True
        return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
