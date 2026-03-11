"""
DUST AI – GUI v1.3
Fix critico: hooked_call() ora accetta **kwargs → risolve
  "got an unexpected keyword argument 'task_hint'"

Altre fix:
  - Chat mode usa agent.chat() diretto
  - Stop button funzionante
  - Encoding output robusto
"""
import sys
import logging
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QTextEdit, QLineEdit, QLabel,
    )
    from PySide6.QtCore import QThread, Signal
    from PySide6.QtGui  import QFont, QColor, QTextCursor
except ImportError:
    print("pip install PySide6")
    sys.exit(1)

log = logging.getLogger("GUI")

COLOR_MAP = {
    "user":   "#FF6B6B",
    "think":  "#4FC3F7",
    "tool":   "#FFB74D",
    "result": "#81C784",
    "agent":  "#81C784",
    "error":  "#EF5350",
    "system": "#B0BEC5",
}


class AgentWorker(QThread):
    output_signal   = Signal(str, str)
    finished_signal = Signal()

    def __init__(self, agent, task: str, mode: str = "agent"):
        super().__init__()
        self.agent      = agent
        self.task       = task
        self.mode       = mode
        self._stop_flag = False
        self._orig_call = None
        self._orig_exec = None

    def run(self):
        try:
            if self.mode == "chat":
                self.output_signal.emit("💬 " + self.task, "user")
                result = self.agent.chat(self.task)
                self.output_signal.emit(result, "agent")
            else:
                self.output_signal.emit("🎯 " + self.task, "user")
                self._hook()
                result = self.agent.run_task(self.task)
                self._unhook()
                self.output_signal.emit("\n✅ " + result, "agent")
        except Exception as e:
            self._unhook()
            self.output_signal.emit("❌ " + str(e), "error")
        finally:
            self.finished_signal.emit()

    def stop(self):
        self._stop_flag = True

    def _hook(self):
        worker = self

        # ── FIX: **kwargs cattura task_hint e qualsiasi argomento futuro ──
        orig_call = self.agent._call_model
        self._orig_call = orig_call

        def hooked_call(messages, **kwargs):
            if worker._stop_flag:
                raise RuntimeError("Fermato dall'utente")
            return orig_call(messages, **kwargs)

        self.agent._call_model = hooked_call

        orig_exec = self.agent.tools.execute
        self._orig_exec = orig_exec

        def hooked_exec(tool_name, params):
            if worker._stop_flag:
                raise RuntimeError("Fermato dall'utente")
            import json
            worker.output_signal.emit(
                "🔧 [" + tool_name + "] " + json.dumps(params, ensure_ascii=False)[:160],
                "tool"
            )
            result = orig_exec(tool_name, params)
            worker.output_signal.emit("   → " + str(result)[:300], "result")
            return result

        self.agent.tools.execute = hooked_exec

    def _unhook(self):
        if self._orig_call:
            self.agent._call_model = self._orig_call
            self._orig_call = None
        if self._orig_exec:
            self.agent.tools.execute = self._orig_exec
            self._orig_exec = None


class DustAIWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DUST AI v2.0")
        self.resize(1000, 680)
        self._worker   = None
        self._agent    = None
        self._config   = None
        self._mode     = "agent"
        self._thinking = True
        self._build_ui()
        self._init_agent()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        lay = QVBoxLayout(central)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(6)

        self.status_label = QLabel("⚙️ Caricamento DUST AI...")
        self.status_label.setStyleSheet("color:#B0BEC5;font-size:12px;")
        lay.addWidget(self.status_label)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setFont(QFont("Consolas", 10))
        self.output.setStyleSheet(
            "QTextEdit{background:#1E1E1E;color:#E0E0E0;"
            "border:1px solid #333;border-radius:4px;}"
        )
        lay.addWidget(self.output, stretch=1)

        row = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Scrivi un task o domanda...")
        self.input_field.setFont(QFont("Consolas", 10))
        self.input_field.setStyleSheet(
            "QLineEdit{background:#2D2D2D;color:#E0E0E0;"
            "border:1px solid #444;border-radius:4px;padding:6px;}"
        )
        self.input_field.returnPressed.connect(self._send)
        row.addWidget(self.input_field, stretch=1)

        self.send_btn = QPushButton("▶ Invia")
        self.send_btn.clicked.connect(self._send)
        self.send_btn.setStyleSheet(self._bs("#1565C0"))
        row.addWidget(self.send_btn)

        self.stop_btn = QPushButton("⏹ Stop")
        self.stop_btn.clicked.connect(self._stop)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet(self._bs("#B71C1C"))
        row.addWidget(self.stop_btn)

        lay.addLayout(row)

        ctrl = QHBoxLayout()
        self.mode_btn = QPushButton("🤖 Agent")
        self.mode_btn.clicked.connect(self._toggle_mode)
        self.mode_btn.setStyleSheet(self._bs("#1B5E20", True))
        ctrl.addWidget(self.mode_btn)

        self.think_btn = QPushButton("💭 Thinking: ON")
        self.think_btn.clicked.connect(self._toggle_think)
        self.think_btn.setStyleSheet(self._bs("#4A148C", True))
        ctrl.addWidget(self.think_btn)

        cb = QPushButton("🗑 Clear")
        cb.clicked.connect(self.output.clear)
        cb.setStyleSheet(self._bs("#37474F", True))
        ctrl.addWidget(cb)
        ctrl.addStretch()
        lay.addLayout(ctrl)

        self.setStyleSheet("QMainWindow,QWidget{background:#121212;}")

    def _bs(self, c, small=False):
        p = "4px 10px" if small else "6px 16px"
        return (
            "QPushButton{background:" + c + ";color:white;border:none;"
            "border-radius:4px;padding:" + p + ";font-size:11px;}"
            "QPushButton:hover{background:" + c + "CC;}"
            "QPushButton:disabled{background:#333;color:#666;}"
        )

    def _init_agent(self):
        try:
            from src.config import Config
            from src.agent  import Agent
            self._config = Config()
            self._agent  = Agent(self._config)
            model = self._config.get_model("primary").replace("gemini/", "")
            self._append("✅ Pronto | Modello: " + model, "system")
            self._append("📁 Desktop: " + str(self._config.get_desktop()), "system")
            self.status_label.setText("✅ DUST AI — " + model)
        except Exception as e:
            self._append("❌ Init: " + str(e), "error")
            self.status_label.setText("❌ Errore")

    def _send(self):
        text = self.input_field.text().strip()
        if not text or not self._agent:
            return
        if self._worker and self._worker.isRunning():
            self._append("⚠️ Task in corso", "error")
            return
        self.input_field.clear()
        self._append("\n" + "─" * 60, "system")
        self._worker = AgentWorker(self._agent, text, self._mode)
        self._worker.output_signal.connect(self._on_out)
        self._worker.finished_signal.connect(self._on_done)
        self._worker.start()
        self.send_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.input_field.setEnabled(False)

    def _stop(self):
        if self._worker:
            self._worker.stop()
            self._append("⏹ Fermato", "system")

    def _on_out(self, text, key):
        if not self._thinking and key == "think":
            return
        safe = text.encode("utf-8", errors="replace").decode("utf-8")
        self._append(safe, key)

    def _on_done(self):
        self.send_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.input_field.setEnabled(True)
        self.input_field.setFocus()
        self._append("─" * 60, "system")

    def _toggle_mode(self):
        self._mode = "chat" if self._mode == "agent" else "agent"
        self.mode_btn.setText("💬 Chat" if self._mode == "chat" else "🤖 Agent")

    def _toggle_think(self):
        self._thinking = not self._thinking
        self.think_btn.setText("💭 Thinking: " + ("ON" if self._thinking else "OFF"))

    def _append(self, text, key="agent"):
        c = COLOR_MAP.get(key, "#E0E0E0")
        cur = self.output.textCursor()
        cur.movePosition(QTextCursor.End)
        self.output.setTextCursor(cur)
        self.output.setTextColor(QColor(c))
        self.output.append(text)
        self.output.ensureCursorVisible()


def launch():
    app = QApplication.instance() or QApplication(sys.argv)
    w   = DustAIWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    launch()
