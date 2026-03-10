"""
DUST AI – App Orchestrator
Gestisce il loop principale, carica config, inizializza tutti i moduli.
"""
import os
import sys
import json
import logging
from pathlib import Path

from .config import Config
from .agent import Agent
from .ui.console import ConsoleUI


class DustApp:
    VERSION = "1.0.0"
    NAME = "DUST AI"

    def __init__(self):
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

    def run(self):
        self.log.info(f"=== {self.NAME} v{self.VERSION} avviato ===")
        print(f"\n🤖 {self.NAME} v{self.VERSION}")
        print("=" * 50)

        # Inizializza agent
        self.agent = Agent(self.config)

        # Inizializza UI (console per ora, GUI in futuro)
        self.ui = ConsoleUI(self.agent)

        # Avvia loop
        self.ui.run()
