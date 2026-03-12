"""
DUST AI – GUI PATCH v2.0
=========================
Sostituisce la GUI attuale con una chat moderna, pulita e universale.
Ispirata a Claude / ChatGPT: nessuna interfaccia a "task", solo conversazione.

Esegui: python A:\\dustai\\DUST_GUI_PATCH.py
"""
import ast, shutil, time, subprocess, sys
from pathlib import Path
from datetime import datetime

BASE = Path(r"A:\dustai")
SRC  = BASE / "src"
UI   = SRC / "ui"
BAK  = Path(r"A:\dustai_stuff\patches")
BAK.mkdir(parents=True, exist_ok=True)
UI.mkdir(exist_ok=True)

def bak(f):
    p = Path(f)
    if p.exists():
        shutil.copy2(p, BAK / (p.stem + ".bak_" + str(int(time.time())) + p.suffix))

def write(path, content, label):
    try:
        ast.parse(content)
        Path(path).write_text(content, encoding="utf-8")
        print(f"  ✅ {label}")
        return True
    except SyntaxError as e:
        print(f"  ❌ SINTASSI {label}: {e}")
        return False

print("=" * 60)
print("DUST AI – GUI PATCH v2.0")
print("=" * 60)

# ══════════════════════════════════════════════════════════════
# GUI NUOVA – src/ui/gui.py
# ══════════════════════════════════════════════════════════════
print("\n[1/2] Nuova GUI (chat moderna)")
bak(UI / "gui.py")

GUI_CODE = r'''"""
DUST AI – GUI v2.0
Chat moderna e universale. Nessun task fisso: parla e basta.
"""
import sys, time, logging, json, re
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLineEdit, QPushButton, QLabel, QScrollArea,
    QSizePolicy, QFrame, QSpacerItem
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QSize, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import (
    QColor, QPalette, QFont, QTextCursor, QKeyEvent,
    QIcon, QPainter, QBrush, QPixmap
)

log = logging.getLogger("DustApp")

# ── Palette colori ───────────────────────────────────────────────────────────
C = {
    "bg":         "#0f1117",   # sfondo app
    "bg_sidebar": "#16181f",   # sidebar
    "bg_bubble_u":"#1e2030",   # bolla utente
    "bg_bubble_a":"#141720",   # bolla agent
    "bg_input":   "#1a1d28",   # campo input
    "bg_tool":    "#0d1a2e",   # bolla tool call
    "accent":     "#5b8af5",   # blu principale
    "accent2":    "#7c6af5",   # viola
    "text":       "#e8eaf0",   # testo principale
    "text_dim":   "#6b7280",   # testo secondario
    "text_tool":  "#64b5f6",   # testo tool call
    "text_ok":    "#4ade80",   # verde ok
    "text_err":   "#f87171",   # rosso errore
    "text_warn":  "#fbbf24",   # giallo warn
    "border":     "#2a2d3e",   # bordi
    "border_focus":"#5b8af5",  # bordo input focus
    "dot_ok":     "#4ade80",
    "dot_think":  "#fbbf24",
    "dot_err":    "#f87171",
}

STYLE_APP = f"""
QMainWindow, QWidget {{ background: {C['bg']}; color: {C['text']}; }}
QScrollArea {{ background: {C['bg']}; border: none; }}
QScrollBar:vertical {{
    background: {C['bg']}; width: 6px; border-radius: 3px;
}}
QScrollBar::handle:vertical {{
    background: {C['border']}; border-radius: 3px; min-height: 30px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
"""

STYLE_INPUT = f"""
QTextEdit {{
    background: {C['bg_input']};
    color: {C['text']};
    border: 1px solid {C['border']};
    border-radius: 12px;
    padding: 12px 16px;
    font-size: 14px;
    font-family: 'Segoe UI', Arial, sans-serif;
    selection-background-color: {C['accent']};
}}
QTextEdit:focus {{
    border: 1px solid {C['border_focus']};
}}
"""

STYLE_SEND = f"""
QPushButton {{
    background: {C['accent']};
    color: white;
    border: none;
    border-radius: 10px;
    padding: 10px 20px;
    font-size: 14px;
    font-weight: 600;
}}
QPushButton:hover {{
    background: #7aa3ff;
}}
QPushButton:pressed {{
    background: #4070e0;
}}
QPushButton:disabled {{
    background: {C['border']};
    color: {C['text_dim']};
}}
"""

STYLE_STOP = f"""
QPushButton {{
    background: #3a1a1a;
    color: {C['text_err']};
    border: 1px solid #5a2a2a;
    border-radius: 10px;
    padding: 10px 20px;
    font-size: 14px;
    font-weight: 600;
}}
QPushButton:hover {{
    background: #4a2020;
}}
"""


# ── Worker Thread ────────────────────────────────────────────────────────────
class AgentWorker(QThread):
    """Esegue il task in background, emette segnali per ogni evento."""
    sig_token    = Signal(str)   # token di testo in streaming
    sig_tool     = Signal(str, str)  # (tool_name, params_json)
    sig_tool_res = Signal(str, str)  # (tool_name, result)
    sig_done     = Signal(str)   # risultato finale
    sig_error    = Signal(str)   # errore
    sig_status   = Signal(str)   # stato (thinking / waiting / ecc.)

    def __init__(self, agent, user_input: str):
        super().__init__()
        self.agent      = agent
        self.user_input = user_input
        self._stop      = False

    def run(self):
        try:
            # Hook: intercetta tool calls e testo
            orig_call = self.agent._call_model

            def hooked_call(messages, **kwargs):
                if self._stop:
                    raise InterruptedError("Fermato dall'utente")
                self.sig_status.emit("thinking")
                result = orig_call(messages, **kwargs)
                return result

            self.agent._call_model = hooked_call

            # Hook tool execution
            orig_exec = self.agent.tools.execute

            def hooked_exec(name, params):
                if self._stop:
                    raise InterruptedError("Fermato dall'utente")
                p_str = json.dumps(params, ensure_ascii=False)[:200]
                self.sig_tool.emit(name, p_str)
                self.sig_status.emit(f"tool:{name}")
                result = orig_exec(name, params)
                res_str = str(result)[:500] if result else ""
                self.sig_tool_res.emit(name, res_str)
                return result

            self.agent.tools.execute = hooked_exec

            result = self.agent.run_task(self.user_input)
            self.sig_done.emit(result or "")

        except InterruptedError:
            self.sig_done.emit("")
        except Exception as e:
            self.sig_error.emit(str(e)[:300])
        finally:
            self.sig_status.emit("idle")

    def stop(self):
        self._stop = True


# ── Bubble widget ────────────────────────────────────────────────────────────
class Bubble(QFrame):
    """Singola bolla di messaggio nella chat."""

    def __init__(self, role: str, parent=None):
        super().__init__(parent)
        self.role = role  # "user" | "assistant" | "tool" | "tool_result"
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)

        # Header piccolo (ruolo)
        if self.role != "user":
            hdr = QLabel(self._role_label())
            hdr.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            hdr.setStyleSheet(f"color: {self._header_color()}; padding: 0 4px;")
            lay.addWidget(hdr)

        # Corpo testo
        self.body = QTextEdit()
        self.body.setReadOnly(True)
        self.body.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.body.setMinimumWidth(200)
        self.body.document().setDocumentMargin(0)
        self.body.setStyleSheet(f"""
            QTextEdit {{
                background: {self._bg()};
                color: {self._fg()};
                border: 1px solid {self._border()};
                border-radius: 12px;
                padding: 10px 14px;
                font-size: 13.5px;
                font-family: 'Segoe UI', Arial, sans-serif;
                selection-background-color: {C['accent']};
            }}
        """)
        lay.addWidget(self.body)
        self.setStyleSheet("background: transparent; border: none;")

    def set_text(self, text: str):
        self.body.setPlainText(text)
        self._resize()

    def append_text(self, chunk: str):
        self.body.moveCursor(QTextCursor.MoveOperation.End)
        self.body.insertPlainText(chunk)
        self._resize()

    def _resize(self):
        doc = self.body.document()
        doc.setTextWidth(self.body.viewport().width() or 600)
        h = int(doc.size().height()) + 24
        self.body.setFixedHeight(min(h, 600))

    def _role_label(self):
        return {"assistant": "✦ DUST", "tool": "⚙", "tool_result": "→"}.get(self.role, "")

    def _header_color(self):
        return {"assistant": C["accent"], "tool": C["text_tool"],
                "tool_result": C["text_dim"]}.get(self.role, C["text"])

    def _bg(self):
        return {"user": C["bg_bubble_u"], "assistant": C["bg_bubble_a"],
                "tool": C["bg_tool"], "tool_result": C["bg_tool"]}.get(self.role, C["bg_bubble_a"])

    def _fg(self):
        return {"tool": C["text_tool"], "tool_result": C["text_dim"]}.get(self.role, C["text"])

    def _border(self):
        return {"user": "#2d3250", "tool": "#1a2a40",
                "tool_result": "#1a2030"}.get(self.role, C["border"])


# ── Chat area ────────────────────────────────────────────────────────────────
class ChatArea(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._container = QWidget()
        self._lay       = QVBoxLayout(self._container)
        self._lay.setSpacing(10)
        self._lay.setContentsMargins(20, 20, 20, 20)
        self._lay.addStretch()

        self.setWidget(self._container)
        self.setStyleSheet(f"background: {C['bg']}; border: none;")
        self._current_bubble = None

    def add_bubble(self, role: str, text: str = "") -> Bubble:
        b = Bubble(role)
        if text:
            b.set_text(text)
        self._lay.addWidget(b)
        self._current_bubble = b if not text else None
        QTimer.singleShot(50, self._scroll_bottom)
        return b

    def stream_token(self, token: str):
        """Aggiunge token alla bolla corrente (streaming)."""
        if self._current_bubble and self._current_bubble.role == "assistant":
            self._current_bubble.append_text(token)
            QTimer.singleShot(10, self._scroll_bottom)

    def start_assistant_bubble(self) -> Bubble:
        b = self.add_bubble("assistant")
        self._current_bubble = b
        return b

    def finalize_bubble(self, text: str = ""):
        if self._current_bubble:
            if text:
                self._current_bubble.set_text(text)
            self._current_bubble = None

    def add_tool(self, name: str, params: str):
        short = f"  {name}({params[:80]}{'…' if len(params)>80 else ''})"
        self.add_bubble("tool", short)

    def add_tool_result(self, name: str, result: str):
        lines = result.strip().splitlines()
        preview = lines[0][:120] if lines else ""
        if len(lines) > 1:
            preview += f"  (+{len(lines)-1} righe)"
        self.add_bubble("tool_result", f"  → {preview}")

    def clear_chat(self):
        while self._lay.count() > 1:
            item = self._lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._current_bubble = None

    def _scroll_bottom(self):
        sb = self.verticalScrollBar()
        sb.setValue(sb.maximum())


# ── Status bar ───────────────────────────────────────────────────────────────
class StatusBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 4, 16, 4)
        lay.setSpacing(8)

        self._dot = QLabel("●")
        self._dot.setFont(QFont("Segoe UI", 10))
        self._dot.setStyleSheet(f"color: {C['dot_ok']};")

        self._lbl = QLabel("Pronto")
        self._lbl.setFont(QFont("Segoe UI", 9))
        self._lbl.setStyleSheet(f"color: {C['text_dim']};")

        self._model = QLabel("")
        self._model.setFont(QFont("Segoe UI", 9))
        self._model.setStyleSheet(f"color: {C['text_dim']};")

        lay.addWidget(self._dot)
        lay.addWidget(self._lbl)
        lay.addStretch()
        lay.addWidget(self._model)

        self.setStyleSheet(f"background: {C['bg_sidebar']}; border-top: 1px solid {C['border']};")

    def set_state(self, state: str, model: str = ""):
        states = {
            "idle":     ("Pronto",        C["dot_ok"],   ""),
            "thinking": ("DUST sta pensando…", C["dot_think"], model),
            "waiting":  ("In attesa…",    C["dot_warn"] if "warn" in C else C["dot_think"], model),
            "tool":     ("Eseguo azione…",C["dot_think"], model),
            "error":    ("Errore",        C["dot_err"],  ""),
        }
        label, color, mdl = states.get(state, ("…", C["dot_think"], ""))
        self._dot.setStyleSheet(f"color: {color};")
        self._lbl.setText(label)
        if mdl:
            self._model.setText(mdl)

    def set_model(self, name: str):
        self._model.setText(name)


# ── Input box con Shift+Enter ─────────────────────────────────────────────────
class InputBox(QTextEdit):
    sig_submit = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("Scrivi un messaggio…  (Invio per inviare, Shift+Invio per andare a capo)")
        self.setMinimumHeight(48)
        self.setMaximumHeight(160)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setStyleSheet(STYLE_INPUT)
        self.document().contentsChanged.connect(self._auto_resize)

    def keyPressEvent(self, e: QKeyEvent):
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if e.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(e)
            else:
                self.sig_submit.emit()
            return
        super().keyPressEvent(e)

    def _auto_resize(self):
        doc_h = int(self.document().size().height()) + 24
        self.setFixedHeight(max(48, min(doc_h, 160)))


# ── Finestra principale ───────────────────────────────────────────────────────
class DustApp(QMainWindow):
    def __init__(self, agent):
        super().__init__()
        self.agent   = agent
        self._worker = None
        self._current_assistant_bubble = None

        self.setWindowTitle("DUST AI")
        self.resize(900, 700)
        self.setMinimumSize(600, 400)
        self._build_ui()
        self._apply_style()

        # Mostra messaggio di benvenuto
        QTimer.singleShot(300, self._welcome)

    # ── Build ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        header = self._make_header()
        root.addWidget(header)

        # Chat
        self.chat = ChatArea()
        root.addWidget(self.chat, 1)

        # Input area
        input_area = self._make_input()
        root.addWidget(input_area)

        # Status bar
        self.status_bar = StatusBar()
        root.addWidget(self.status_bar)

        # Imposta modello corrente
        try:
            m = self.agent.config.get_model("primary").replace("gemini/", "")
            self.status_bar.set_model(m)
        except Exception:
            pass

    def _make_header(self):
        w = QWidget()
        w.setFixedHeight(52)
        w.setStyleSheet(f"background: {C['bg_sidebar']}; border-bottom: 1px solid {C['border']};")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(20, 0, 16, 0)

        title = QLabel("✦ DUST AI")
        title.setFont(QFont("Segoe UI Semibold", 15, QFont.Weight.DemiBold))
        title.setStyleSheet(f"color: {C['accent']}; background: transparent;")
        lay.addWidget(title)
        lay.addStretch()

        # Pulsante "Nuova chat"
        btn_new = QPushButton("+ Nuova chat")
        btn_new.setFixedHeight(30)
        btn_new.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {C['text_dim']};
                border: 1px solid {C['border']};
                border-radius: 6px;
                padding: 0 12px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                color: {C['text']};
                border-color: {C['accent']};
            }}
        """)
        btn_new.clicked.connect(self._new_chat)
        lay.addWidget(btn_new)
        return w

    def _make_input(self):
        w = QWidget()
        w.setStyleSheet(f"background: {C['bg']}; border-top: 1px solid {C['border']};")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(10)

        self.input = InputBox()
        self.input.sig_submit.connect(self._send)
        lay.addWidget(self.input, 1)

        btn_col = QVBoxLayout()
        btn_col.setSpacing(6)

        self.btn_send = QPushButton("Invia")
        self.btn_send.setFixedSize(80, 40)
        self.btn_send.setStyleSheet(STYLE_SEND)
        self.btn_send.clicked.connect(self._send)
        btn_col.addWidget(self.btn_send)

        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setFixedSize(80, 40)
        self.btn_stop.setStyleSheet(STYLE_STOP)
        self.btn_stop.clicked.connect(self._stop)
        self.btn_stop.setVisible(False)
        btn_col.addWidget(self.btn_stop)

        lay.addLayout(btn_col)
        return w

    # ── Stile ─────────────────────────────────────────────────────────────

    def _apply_style(self):
        self.setStyleSheet(STYLE_APP)
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window,      QColor(C["bg"]))
        palette.setColor(QPalette.ColorRole.WindowText,  QColor(C["text"]))
        palette.setColor(QPalette.ColorRole.Base,        QColor(C["bg_input"]))
        palette.setColor(QPalette.ColorRole.Text,        QColor(C["text"]))
        self.setPalette(palette)

    # ── Logica chat ────────────────────────────────────────────────────────

    def _welcome(self):
        msg = ("Ciao! Sono DUST AI, il tuo assistente personale su Windows.\n\n"
               "Posso aiutarti con qualsiasi cosa:\n"
               "  • Cercare informazioni online\n"
               "  • Creare e modificare file\n"
               "  • Usare il browser e le applicazioni\n"
               "  • Scrivere, analizzare, programmare\n"
               "  • E molto altro\n\n"
               "Cosa vuoi fare?")
        self.chat.add_bubble("assistant", msg)

    def _new_chat(self):
        if self._worker and self._worker.isRunning():
            self._stop()
        self.chat.clear_chat()
        QTimer.singleShot(100, self._welcome)

    def _send(self):
        text = self.input.toPlainText().strip()
        if not text:
            return
        if self._worker and self._worker.isRunning():
            return

        self.input.clear()
        self.chat.add_bubble("user", text)

        # Avvia worker
        self._current_assistant_bubble = self.chat.start_assistant_bubble()
        self._worker = AgentWorker(self.agent, text)
        self._worker.sig_token.connect(self._on_token)
        self._worker.sig_tool.connect(self._on_tool)
        self._worker.sig_tool_res.connect(self._on_tool_res)
        self._worker.sig_done.connect(self._on_done)
        self._worker.sig_error.connect(self._on_error)
        self._worker.sig_status.connect(self._on_status)
        self._worker.start()

        self.btn_send.setEnabled(False)
        self.btn_stop.setVisible(True)

    def _stop(self):
        if self._worker:
            self._worker.stop()
        self._set_idle()

    def _set_idle(self):
        self.btn_send.setEnabled(True)
        self.btn_stop.setVisible(False)
        self.status_bar.set_state("idle")
        self.input.setFocus()

    # ── Segnali dal worker ────────────────────────────────────────────────

    def _on_token(self, token: str):
        if self._current_assistant_bubble:
            self._current_assistant_bubble.append_text(token)

    def _on_tool(self, name: str, params: str):
        # Chiudi la bolla "pensiero" se aperta
        if self._current_assistant_bubble:
            current_text = self._current_assistant_bubble.body.toPlainText()
            if not current_text.strip():
                self._current_assistant_bubble.body.deleteLater()
                self._current_assistant_bubble = None
        self.chat.add_tool(name, params)

    def _on_tool_res(self, name: str, result: str):
        self.chat.add_tool_result(name, result)
        # Prepara nuova bolla per la risposta successiva
        self._current_assistant_bubble = self.chat.start_assistant_bubble()

    def _on_done(self, result: str):
        if result and self._current_assistant_bubble:
            cur = self._current_assistant_bubble.body.toPlainText()
            if not cur.strip():
                self._current_assistant_bubble.set_text(result)
        elif result:
            self.chat.add_bubble("assistant", result)
        elif self._current_assistant_bubble:
            cur = self._current_assistant_bubble.body.toPlainText()
            if not cur.strip():
                self._current_assistant_bubble.set_text("✓ Completato")
        self.chat.finalize_bubble()
        self._current_assistant_bubble = None
        self._set_idle()

    def _on_error(self, err: str):
        self.chat.finalize_bubble()
        self.chat.add_bubble("assistant", f"⚠️ {err}")
        self._current_assistant_bubble = None
        self._set_idle()
        self.status_bar.set_state("error")

    def _on_status(self, state: str):
        if state.startswith("tool:"):
            self.status_bar.set_state("tool")
        elif state == "thinking":
            self.status_bar.set_state("thinking")
        elif state == "idle":
            pass  # gestito da _set_idle
        else:
            self.status_bar.set_state("waiting")


# ── Entry point ───────────────────────────────────────────────────────────────
def launch(agent):
    """Avvia la GUI. Chiamato da app.py o run.py."""
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("DUST AI")
    app.setStyle("Fusion")

    # Font globale
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    window = DustApp(agent)
    window.show()
    return app.exec()
'''

write(UI / "gui.py", GUI_CODE, "gui.py")

# ══════════════════════════════════════════════════════════════
# FIX app.py – usa il nuovo launch()
# ══════════════════════════════════════════════════════════════
print("\n[2/2] Patching app.py")
APP = SRC / "app.py"
if not APP.exists():
    APP = BASE / "app.py"

if APP.exists():
    src = APP.read_text(encoding="utf-8")
    bak(APP)
    changed = False

    # Assicurati che importi il nuovo gui.py
    old_imports = [
        "from src.ui.gui import DustAIWindow",
        "from src.ui.gui import DUSTAIGUI",
        "from .ui.gui import DustAIWindow",
        "from ui.gui import DustAIWindow",
    ]
    for old in old_imports:
        if old in src:
            src = src.replace(old, "from src.ui.gui import DustApp, launch")
            changed = True

    # Sostituisci la creazione della finestra
    import re as _re
    # Pattern: window = DustAIWindow(agent) / window.show() / sys.exit(app.exec())
    patterns_to_fix = [
        # Vecchio pattern window = DustAIWindow(...)
        (r'window\s*=\s*DustAIWindow\([^)]*\)\s*\n\s*window\.show\(\)\s*\n\s*(?:sys\.exit\()?app\.exec\(\)',
         'sys.exit(launch(agent))'),
        (r'window\s*=\s*DUSTAIGUI\([^)]*\)\s*\n\s*window\.show\(\)',
         'sys.exit(launch(agent))'),
        # Pattern con app.exec()
        (r'DustAIWindow\(agent\)',
         'DustApp(agent)'),
    ]
    for pat, repl in patterns_to_fix:
        new_src = _re.sub(pat, repl, src, flags=_re.DOTALL)
        if new_src != src:
            src = new_src
            changed = True

    # Assicurati che launch() venga chiamato
    if "launch(" not in src and "DustApp" not in src:
        # Aggiungi avvio manuale alla fine
        src += "\n\n# Auto-avvio GUI\nif __name__ == '__main__':\n    from src.ui.gui import launch\n    import sys\n    sys.exit(launch(agent))\n"
        changed = True

    if changed:
        try:
            import ast as _ast
            _ast.parse(src)
            APP.write_text(src, encoding="utf-8")
            print("  ✅ app.py aggiornato")
        except SyntaxError as e:
            print(f"  ❌ Sintassi app.py: {e}")
            print("  ⚠️  Patch app.py manuale richiesta")
    else:
        print("  ⏭️  app.py (nessun pattern trovato – verifica manualmente)")
        print(f"  ℹ️  Assicurati che app.py chiami: from src.ui.gui import launch")
else:
    print("  ⚠️  app.py non trovato")

# ── Commit ─────────────────────────────────────────────────────────────
print("\nCommit...")
ts = datetime.now().strftime("%Y-%m-%d %H:%M")
for cmd in [
    ["git", "add", "-A"],
    ["git", "commit", "-m", f"feat: GUI v2.0 – chat moderna, dark, universale {ts}"],
    ["git", "push", "origin", "master"],
]:
    r = subprocess.run(cmd, cwd=str(BASE), capture_output=True,
                       text=True, encoding="utf-8")
    out = r.stderr or r.stdout or ""
    ok  = r.returncode == 0 or "nothing" in out or "up to date" in out
    print(f"  {'✅' if ok else '⚠️ '} {' '.join(cmd[:2])}")

print("""
╔══════════════════════════════════════════════════════════════╗
║  DUST GUI v2.0 – INSTALLATA                                 ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  Riavvia DUST:  A:\\dustai\\run.bat                          ║
║                                                              ║
║  COSA È CAMBIATO:                                            ║
║  ✅ Interfaccia chat pura (nessun "task queue")             ║
║  ✅ Dark theme professionale                                 ║
║  ✅ Bolle per utente / DUST / tool call / risultati         ║
║  ✅ Input multi-riga (Shift+Invio = a capo)                 ║
║  ✅ Pulsante Stop per interrompere                          ║
║  ✅ Status bar minima (pensando / pronto / errore)          ║
║  ✅ Pulsante "Nuova chat" per resettare                     ║
║  ✅ Tool call visibili inline (⚙ nome → risultato)         ║
║  ✅ Scroll automatico                                        ║
║  ✅ Universale: qualsiasi messaggio, qualsiasi task         ║
╚══════════════════════════════════════════════════════════════╝
""")
