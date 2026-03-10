"""
DUST AI – GUI v1.2
PySide6 window completamente connessa all'Agent.
Features: output ragionamenti in tempo reale, threading, fallback Ollama, dark theme.
"""
import sys
import time
import logging
from pathlib import Path

# ─── Aggiungi root al sys.path ────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLineEdit, QPushButton, QLabel, QSizePolicy, QSplitter
)
from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtGui import QFont, QColor, QTextCursor, QPalette


# ─── Worker: esegue l'agent in un thread separato ────────────────────────────

class AgentWorker(QObject):
    """Esegue task/chat in background e manda segnali alla GUI."""

    # Segnali
    chunk = Signal(str, str)   # (testo, tipo) tipo: user|think|tool|result|agent|error|system
    done = Signal()

    def __init__(self, agent, task: str, mode: str):
        super().__init__()
        self.agent = agent
        self.task = task
        self.mode = mode
        self._cancelled = False

    def run(self):
        try:
            if self.mode == "chat":
                self.chunk.emit(f"💬 Chat: {self.task}", "user")
                result = self._run_chat()
                self.chunk.emit(result, "agent")

            else:  # agent mode
                self.chunk.emit(f"🎯 Task: {self.task}", "user")
                result = self._run_agent()
                self.chunk.emit(result, "agent")

        except Exception as e:
            self.chunk.emit(f"❌ Errore critico: {e}", "error")
        finally:
            self.done.emit()

    def _run_chat(self) -> str:
        return self.agent.chat(self.task)

    def _run_agent(self) -> str:
        """Loop agente con intercettazione tool calls per output in tempo reale."""
        max_steps = self.agent.config.get("agent", {}).get("max_steps", 20)
        import json, re

        # Patch del tools.execute per intercettare le chiamate
        original_execute = self.agent.tools.execute

        def hooked_execute(name, params):
            self.chunk.emit(f"🔧 Tool: [{name}]  {json.dumps(params, ensure_ascii=False)[:200]}", "tool")
            result = original_execute(name, params)
            result_str = str(result)[:500]
            self.chunk.emit(f"   ↳ {result_str}", "result")
            return result

        self.agent.tools.execute = hooked_execute

        # Patch _call_model per mostrare i ragionamenti grezzi
        original_call = self.agent._call_model

        def hooked_call(messages):
            self.chunk.emit("🧠 Sto ragionando...", "think")
            response = original_call(messages)
            # Mostra il ragionamento grezzo solo se NON è una tool call
            try:
                data = json.loads(response.strip().strip('```json').strip('```'))
                if "tool" not in data:
                    self.chunk.emit(f"💭 {response[:600]}", "think")
            except Exception:
                # Non è JSON → è testo libero (ragionamento o risposta finale)
                if len(response.strip()) > 10:
                    self.chunk.emit(f"💭 {response[:600]}", "think")
            return response

        self.agent._call_model = hooked_call

        try:
            result = self.agent.run_task(self.task, max_steps=max_steps)
        finally:
            # Ripristina i metodi originali
            self.agent.tools.execute = original_execute
            self.agent._call_model = original_call

        return result


# ─── Finestra principale ──────────────────────────────────────────────────────

DARK_STYLE = """
QWidget {
    background-color: #1a1a2e;
    color: #e0e0e0;
    font-family: 'Segoe UI', sans-serif;
    font-size: 13px;
}
QTextEdit {
    background-color: #16213e;
    border: 1px solid #0f3460;
    border-radius: 6px;
    padding: 8px;
    color: #e0e0e0;
}
QLineEdit {
    background-color: #16213e;
    border: 2px solid #0f3460;
    border-radius: 6px;
    padding: 8px 12px;
    color: #e0e0e0;
    font-size: 13px;
}
QLineEdit:focus {
    border-color: #e94560;
}
QPushButton {
    background-color: #0f3460;
    color: #e0e0e0;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-size: 13px;
}
QPushButton:hover {
    background-color: #e94560;
}
QPushButton:checked {
    background-color: #e94560;
}
QPushButton:disabled {
    background-color: #333;
    color: #666;
}
QLabel {
    color: #a0a0b0;
}
QSplitter::handle {
    background-color: #0f3460;
}
"""

# Colori per tipo di messaggio
MESSAGE_COLORS = {
    "user":   "#e94560",   # rosso accent
    "think":  "#7a8fcc",   # blu chiaro
    "tool":   "#e8a838",   # arancio
    "result": "#5a8a5a",   # verde scuro
    "agent":  "#50fa7b",   # verde brillante
    "error":  "#ff5555",   # rosso
    "system": "#666688",   # grigio
}


class DustAIWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🤖 DUST AI v1.2 – Desktop Autonomous Agent")
        self.setGeometry(100, 100, 960, 680)
        self.setMinimumSize(700, 500)

        self._agent = None
        self._worker = None
        self._thread = None
        self._mode = "agent"
        self._show_thinking = True

        self._build_ui()
        self.setStyleSheet(DARK_STYLE)
        self._init_agent()

    # ─── Build UI ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # ── Top bar ──
        top = QHBoxLayout()

        self._dot = QLabel("●")
        self._dot.setFixedWidth(18)
        self._dot.setStyleSheet("color: #ff5555; font-size: 16px;")
        top.addWidget(self._dot)

        self._status = QLabel("Inizializzazione...")
        top.addWidget(self._status)
        top.addStretch()

        self._mode_btn = QPushButton("🤖 Agent Mode")
        self._mode_btn.setCheckable(True)
        self._mode_btn.setChecked(True)
        self._mode_btn.setFixedWidth(150)
        self._mode_btn.clicked.connect(self._toggle_mode)
        top.addWidget(self._mode_btn)

        self._think_btn = QPushButton("🧠 Ragionamenti ON")
        self._think_btn.setCheckable(True)
        self._think_btn.setChecked(True)
        self._think_btn.setFixedWidth(180)
        self._think_btn.clicked.connect(self._toggle_thinking)
        top.addWidget(self._think_btn)

        self._clear_btn = QPushButton("🗑 Pulisci")
        self._clear_btn.setFixedWidth(90)
        self._clear_btn.clicked.connect(self._clear_output)
        top.addWidget(self._clear_btn)

        layout.addLayout(top)

        # ── Output area ──
        self._output = QTextEdit()
        self._output.setReadOnly(True)
        self._output.setFont(QFont("Consolas", 12))
        layout.addWidget(self._output, stretch=1)

        # ── Input row ──
        input_row = QHBoxLayout()

        self._input = QLineEdit()
        self._input.setPlaceholderText("Scrivi un task o un messaggio... (Enter per inviare)")
        self._input.returnPressed.connect(self._send)
        input_row.addWidget(self._input, stretch=1)

        self._send_btn = QPushButton("▶ Invia")
        self._send_btn.setFixedWidth(100)
        self._send_btn.clicked.connect(self._send)
        input_row.addWidget(self._send_btn)

        self._stop_btn = QPushButton("⏹ Stop")
        self._stop_btn.setFixedWidth(90)
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._stop)
        input_row.addWidget(self._stop_btn)

        layout.addLayout(input_row)

    # ─── Agent init ──────────────────────────────────────────────────────────

    def _init_agent(self):
        self._log("system", "⚙️  Caricamento DUST AI...")
        try:
            from src.config import Config
            from src.agent import Agent
            self._config = Config()
            self._agent = Agent(self._config)
            self._dot.setStyleSheet("color: #50fa7b; font-size: 16px;")
            model = self._config.get_model("primary").split("/")[-1]
            desktop = str(self._config.get_desktop())
            self._status.setText(f"Online · {model} · Desktop: {desktop}")
            self._log("system", f"✅ DUST AI pronto. Modello: {model}")
            self._log("system", f"📁 Desktop: {desktop}")
            self._log("system", f"📂 Workdir: {self._config.get_workdir()}")
            self._input.setEnabled(True)
            self._send_btn.setEnabled(True)
        except Exception as e:
            self._dot.setStyleSheet("color: #ff5555; font-size: 16px;")
            self._status.setText(f"Errore: {e}")
            self._log("error", f"❌ Init fallita: {e}")
            self._log("system", "💡 Controlla GOOGLE_API_KEY in %APPDATA%\\dustai\\.env")

    # ─── Actions ─────────────────────────────────────────────────────────────

    def _send(self):
        task = self._input.text().strip()
        if not task or not self._agent:
            return
        self._input.clear()
        self._set_busy(True)

        self._worker = AgentWorker(self._agent, task, self._mode)
        self._thread = QThread()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.chunk.connect(self._on_chunk)
        self._worker.done.connect(self._on_done)
        self._thread.start()

    def _stop(self):
        """Interrompe il thread (best-effort)."""
        if self._thread and self._thread.isRunning():
            self._thread.requestInterruption()
            self._thread.quit()
            self._log("system", "⏹ Task interrotto.")
        self._set_busy(False)

    def _toggle_mode(self):
        if self._mode_btn.isChecked():
            self._mode = "agent"
            self._mode_btn.setText("🤖 Agent Mode")
        else:
            self._mode = "chat"
            self._mode_btn.setText("💬 Chat Mode")
        self._log("system", f"Modalità: {self._mode.upper()}")

    def _toggle_thinking(self):
        self._show_thinking = self._think_btn.isChecked()
        label = "ON" if self._show_thinking else "OFF"
        self._think_btn.setText(f"🧠 Ragionamenti {label}")

    def _clear_output(self):
        self._output.clear()

    # ─── Slots ───────────────────────────────────────────────────────────────

    def _on_chunk(self, text: str, kind: str):
        """Riceve output dall'agent e lo stampa colorato."""
        # Filtra ragionamenti se disabilitati
        if kind in ("think",) and not self._show_thinking:
            return
        self._log(kind, text)

    def _on_done(self):
        self._set_busy(False)
        self._log("system", "─" * 60)
        if self._thread:
            self._thread.quit()
            self._thread.wait()

    # ─── Helpers ─────────────────────────────────────────────────────────────

    def _log(self, kind: str, text: str):
        color = MESSAGE_COLORS.get(kind, "#e0e0e0")
        # Escape HTML
        text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        # Newline → <br>
        text = text.replace("\n", "<br>")
        html = f'<span style="color:{color};">{text}</span><br>'
        self._output.moveCursor(QTextCursor.End)
        self._output.insertHtml(html)
        self._output.moveCursor(QTextCursor.End)

    def _set_busy(self, busy: bool):
        self._input.setEnabled(not busy)
        self._send_btn.setEnabled(not busy)
        self._stop_btn.setEnabled(busy)
        if busy:
            self._status.setText("⏳ Elaborazione in corso...")
            self._dot.setStyleSheet("color: #e8a838; font-size: 16px;")
        else:
            model = ""
            if self._agent:
                model = self._config.get_model("primary").split("/")[-1]
            self._status.setText(f"Online · {model}" if model else "Pronto")
            self._dot.setStyleSheet("color: #50fa7b; font-size: 16px;")


# ─── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = DustAIWindow()
    window.show()
    sys.exit(app.exec())
