"""
DUST AI – App Orchestrator v1.1
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

        # ── Bootstrap ────────────────────────────────────────────────────────
        if not skip_bootstrap:
            try:
                from .bootstrap import Bootstrap
                Bootstrap(workdir=self.config.get_workdir()).run()
            except Exception as e:
                self.log.warning(f"Bootstrap parziale: {e}")

        # ── Agent ────────────────────────────────────────────────────────────
        from .agent import Agent
        agent = Agent(self.config)

        # ── UI: legge DUSTAI_UI env var impostata da run.py ──────────────────
        ui_mode = os.environ.get("DUSTAI_UI", "gui")

        if ui_mode == "console":
            self._run_console(agent)
        else:
            self._run_gui(agent)

    def _run_gui(self, agent):
        try:
            from PySide6.QtWidgets import QApplication
            from .ui.gui import DustAIWindow
            qt_app = QApplication.instance() or QApplication(sys.argv)
            qt_app.setStyle("Fusion")
            window = DustAIWindow()
            # Inietta agent già inizializzato nella GUI
            window._agent = agent
            window._config = self.config
            # Aggiorna status nella GUI
            model = self.config.get_model("primary").split("/")[-1]
            desktop = str(self.config.get_desktop())
            window._status.setText(f"Online · {model} · Desktop: {desktop}")
            window._dot.setStyleSheet("color: #50fa7b; font-size: 16px;")
            window._input.setEnabled(True)
            window._send_btn.setEnabled(True)
            window._log("system", f"✅ DUST AI {DustApp.VERSION} pronto")
            window._log("system", f"🤖 Modello: {model}")
            window._log("system", f"📁 Desktop: {desktop}")
            window.show()
            sys.exit(qt_app.exec())
        except ImportError as e:
            self.log.warning(f"PySide6 non disponibile ({e}), uso console")
            self._run_console(agent)
        except Exception as e:
            self.log.error(f"GUI crash: {e} — fallback console")
            self._run_console(agent)

    def _run_console(self, agent):
        from .ui.console import ConsoleUI
        ConsoleUI(agent).run()
