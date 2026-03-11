"""
DUST AI – GUI v1.2
PySide6 window completamente connessa all'Agent.
Classe: DustAIWindow — gestisce autonomamente init agent, threading, output colorato.
"""
import sys
import logging
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLineEdit, QPushButton, QLabel, QSizePolicy
)
from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtGui import QFont, QTextCursor

DARK_STYLE = """
QWidget { background-color:#1a1a2e; color:#e0e0e0; font-family:'Segoe UI',sans-serif; font-size:13px; }
QTextEdit { background-color:#16213e; border:1px solid #0f3460; border-radius:6px; padding:8px; color:#e0e0e0; }
QLineEdit { background-color:#16213e; border:2px solid #0f3460; border-radius:6px; padding:8px 12px; color:#e0e0e0; }
QLineEdit:focus { border-color:#e94560; }
QPushButton { background-color:#0f3460; color:#e0e0e0; border:none; border-radius:6px; padding:8px 16px; }
QPushButton:hover { background-color:#e94560; }
QPushButton:checked { background-color:#e94560; }
QPushButton:disabled { background-color:#333; color:#666; }
QLabel { color:#a0a0b0; }
"""

COLORS = {
    "user":   "#e94560",
    "think":  "#7a8fcc",
    "tool":   "#e8a838",
    "result": "#5a8a5a",
    "agent":  "#50fa7b",
    "error":  "#ff5555",
    "system": "#666688",
}


class AgentWorker(QObject):
    chunk    = Signal(str, str)
    done     = Signal()

    def __init__(self, agent, task, mode):
        super().__init__()
        self.agent = agent
        self.task  = task
        self.mode  = mode

    def run(self):
        import json
        try:
            self.chunk.emit(f"{'🎯' if self.mode == 'agent' else '💬'} {self.task}", "user")

            original_execute = self.agent.tools.execute
            original_call    = self.agent._call_model

            def hooked_execute(name, params):
                self.chunk.emit(f"🔧 [{name}]  {json.dumps(params, ensure_ascii=False)[:200]}", "tool")
                result = original_execute(name, params)
                self.chunk.emit(f"   ↳ {str(result)[:500]}", "result")
                return result

            def hooked_call(messages):
                self.chunk.emit("🧠 Ragionamento...", "think")
                response = original_call(messages)
                try:
                    data = json.loads(response.strip().strip("```json").strip("```"))
                    if "tool" not in data and len(response.strip()) > 10:
                        self.chunk.emit(f"💭 {response[:600]}", "think")
                except Exception:
                    if len(response.strip()) > 10:
                        self.chunk.emit(f"💭 {response[:600]}", "think")
                return response

            self.agent.tools.execute = hooked_execute
            self.agent._call_model   = hooked_call

            if self.mode == "chat":
                result = self.agent.chat(self.task)
            else:
                result = self.agent.run_task(self.task)

            self.agent.tools.execute = original_execute
            self.agent._call_model   = original_call
            self.chunk.emit(result, "agent")

        except Exception as e:
            self.chunk.emit(f"❌ {e}", "error")
        finally:
            self.done.emit()


class DustAIWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("🤖 DUST AI — Desktop Agent")
        self.setGeometry(100, 100, 980, 680)
        self.setMinimumSize(700, 480)
        self._agent  = None
        self._config = None
        self._mode   = "agent"
        self._show_thinking = True
        self._thread = None
        self._worker = None
        self._build_ui()
        self.setStyleSheet(DARK_STYLE)
        self._init_agent()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        # Top bar
        top = QHBoxLayout()
        self._dot = QLabel("●")
        self._dot.setFixedWidth(18)
        self._dot.setStyleSheet("color:#ff5555; font-size:16px;")
        top.addWidget(self._dot)
        self._status = QLabel("Inizializzazione...")
        top.addWidget(self._status)
        top.addStretch()

        self._mode_btn = QPushButton("🤖 Agent")
        self._mode_btn.setCheckable(True)
        self._mode_btn.setChecked(True)
        self._mode_btn.setFixedWidth(120)
        self._mode_btn.clicked.connect(self._toggle_mode)
        top.addWidget(self._mode_btn)

        self._think_btn = QPushButton("🧠 ON")
        self._think_btn.setCheckable(True)
        self._think_btn.setChecked(True)
        self._think_btn.setFixedWidth(80)
        self._think_btn.clicked.connect(self._toggle_thinking)
        top.addWidget(self._think_btn)

        self._clear_btn = QPushButton("🗑")
        self._clear_btn.setFixedWidth(45)
        self._clear_btn.clicked.connect(lambda: self._output.clear())
        top.addWidget(self._clear_btn)

        layout.addLayout(top)

        # Output
        self._output = QTextEdit()
        self._output.setReadOnly(True)
        self._output.setFont(QFont("Consolas", 12))
        layout.addWidget(self._output, stretch=1)

        # Input row
        row = QHBoxLayout()
        self._input = QLineEdit()
        self._input.setPlaceholderText("Scrivi un task o un messaggio... (Enter per inviare)")
        self._input.returnPressed.connect(self._send)
        self._input.setEnabled(False)
        row.addWidget(self._input, stretch=1)

        self._send_btn = QPushButton("▶ Invia")
        self._send_btn.setFixedWidth(100)
        self._send_btn.setEnabled(False)
        self._send_btn.clicked.connect(self._send)
        row.addWidget(self._send_btn)

        self._stop_btn = QPushButton("⏹")
        self._stop_btn.setFixedWidth(45)
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._stop)
        row.addWidget(self._stop_btn)

        layout.addLayout(row)

    # ── Agent init ────────────────────────────────────────────────────────────

    def _init_agent(self):
        self._log("system", "⚙️  Caricamento DUST AI...")
        try:
            from src.config import Config
            from src.agent import Agent
            self._config = Config()
            self._agent  = Agent(self._config)
            model   = self._config.get_model("primary").split("/")[-1]
            desktop = str(self._config.get_desktop())
            self._dot.setStyleSheet("color:#50fa7b; font-size:16px;")
            self._status.setText(f"Online · {model} · {desktop}")
            self._log("system", f"✅ Pronto  |  Modello: {model}")
            self._log("system", f"📁 Desktop: {desktop}")
            self._input.setEnabled(True)
            self._send_btn.setEnabled(True)
        except Exception as e:
            self._dot.setStyleSheet("color:#ff5555; font-size:16px;")
            self._status.setText(f"Errore init: {e}")
            self._log("error", f"❌ Init fallita: {e}")
            self._log("system", "💡 Controlla GOOGLE_API_KEY in %APPDATA%\\dustai\\.env")

    # ── Actions ───────────────────────────────────────────────────────────────

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
        if self._thread and self._thread.isRunning():
            self._thread.requestInterruption()
            self._thread.quit()
            self._log("system", "⏹ Interrotto.")
        self._set_busy(False)

    def _toggle_mode(self):
        self._mode = "agent" if self._mode_btn.isChecked() else "chat"
        self._mode_btn.setText("🤖 Agent" if self._mode == "agent" else "💬 Chat")

    def _toggle_thinking(self):
        self._show_thinking = self._think_btn.isChecked()
        self._think_btn.setText("🧠 ON" if self._show_thinking else "🧠 OFF")

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_chunk(self, text, kind):
        if kind == "think" and not self._show_thinking:
            return
        self._log(kind, text)

    def _on_done(self):
        self._set_busy(False)
        self._log("system", "─" * 55)
        if self._thread:
            self._thread.quit()
            self._thread.wait()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _log(self, kind, text):
        color = COLORS.get(kind, "#e0e0e0")
        text  = text.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace("\n","<br>")
        self._output.moveCursor(QTextCursor.End)
        self._output.insertHtml(f'<span style="color:{color};">{text}</span><br>')
        self._output.moveCursor(QTextCursor.End)

    def _set_busy(self, busy):
        self._input.setEnabled(not busy)
        self._send_btn.setEnabled(not busy)
        self._stop_btn.setEnabled(busy)
        self._dot.setStyleSheet(f"color:{'#e8a838' if busy else '#50fa7b'}; font-size:16px;")
        if not busy and self._config:
            model = self._config.get_model("primary").split("/")[-1]
            self._status.setText(f"Online · {model}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = DustAIWindow()
    win.show()
    sys.exit(app.exec())
