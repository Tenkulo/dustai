"""
DUST AI – Memory System
Salva e recupera contesto tra sessioni.
Short-term: lista messaggi recenti
Long-term: sommario persistente su disco
"""
import json
import logging
from pathlib import Path
from datetime import datetime


class Memory:
    MAX_SHORT_TERM = 20    # Ultimi N scambi in memoria

    def __init__(self, config):
        self.config = config
        self.log = logging.getLogger("Memory")
        self._short_term = []       # [(task, response, timestamp)]
        self._long_term_file = config.get_workdir() / "memory.json"
        self._load_long_term()

    def _load_long_term(self):
        """Carica memoria long-term da disco."""
        if self._long_term_file.exists():
            try:
                with open(self._long_term_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._long_term = data.get("summaries", [])
                self._facts = data.get("facts", [])
                self.log.info(f"Memoria caricata: {len(self._long_term)} sommari, {len(self._facts)} fatti")
            except Exception as e:
                self.log.warning(f"Errore caricamento memoria: {e}")
                self._long_term = []
                self._facts = []
        else:
            self._long_term = []
            self._facts = []

    def _save_long_term(self):
        """Salva memoria long-term su disco."""
        try:
            data = {
                "updated_at": datetime.now().isoformat(),
                "summaries": self._long_term[-50:],   # Ultimi 50
                "facts": self._facts[-100:],           # Ultimi 100 fatti
            }
            with open(self._long_term_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.log.warning(f"Errore salvataggio memoria: {e}")

    def add(self, task: str, response: str):
        """Aggiunge uno scambio alla memoria."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "task": task[:500],
            "response": response[:500],
        }
        self._short_term.append(entry)

        # Mantieni solo gli ultimi N
        if len(self._short_term) > self.MAX_SHORT_TERM:
            self._short_term = self._short_term[-self.MAX_SHORT_TERM:]

        # Aggiungi al long-term come sommario
        self._long_term.append(f"[{entry['timestamp'][:10]}] Task: {task[:100]}")
        self._save_long_term()

    def add_fact(self, fact: str):
        """Aggiungi un fatto permanente (es: 'Desktop è in OneDrive')."""
        if fact not in self._facts:
            self._facts.append(fact)
            self._save_long_term()

    def get_context(self) -> str:
        """Restituisce il contesto rilevante per l'agente."""
        parts = []

        # Fatti permanenti
        if self._facts:
            parts.append("Fatti noti:\n" + "\n".join(f"• {f}" for f in self._facts[-10:]))

        # Ultimi 5 task
        if self._short_term:
            recent = self._short_term[-5:]
            history = "\n".join(
                f"[{e['timestamp'][:16]}] {e['task'][:80]}" for e in recent
            )
            parts.append(f"Task recenti:\n{history}")

        return "\n\n".join(parts) if parts else ""

    def clear(self):
        """Svuota la memoria short-term."""
        self._short_term = []
        self.log.info("Memoria short-term svuotata")
