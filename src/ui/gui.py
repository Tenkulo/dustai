"""DUST AI GUI v3.0 — Dark chat interface (Claude-style bubbles)."""
import json
import queue
import sys
import threading
import tkinter as tk
from tkinter import ttk
from pathlib import Path

# Ensure src is on path
_SRC = Path(__file__).resolve().parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# ─── Palette ─────────────────────────────────────────────────
C = {
    "bg":           "#1a1a2e",
    "sidebar":      "#16213e",
    "chat_bg":      "#0d1117",
    "user_bub":     "#1f6feb",
    "ai_bub":       "#161b22",
    "user_fg":      "#f0f6fc",
    "ai_fg":        "#c9d1d9",
    "input_bg":     "#161b22",
    "input_fg":     "#f0f6fc",
    "btn":          "#238636",
    "btn_hover":    "#2ea043",
    "accent":       "#58a6ff",
    "muted":        "#8b949e",
    "border":       "#30363d",
    "ok":           "#3fb950",
    "err":          "#f85149",
    "warn":         "#d29922",
}
FF = ("Segoe UI", 11)
FM = ("Consolas", 10)
FT = ("Segoe UI", 13, "bold")
FS = ("Segoe UI", 9)


# ─── AgentWorker ─────────────────────────────────────────────
class AgentWorker(threading.Thread):
    """Background thread: consumes tasks, calls agent, emits results."""

    def __init__(self, agent, out_q: queue.Queue):
        super().__init__(daemon=True, name="AgentWorker")
        self.agent   = agent
        self.out_q   = out_q
        self._in_q   = queue.Queue()
        self._alive  = True

    def submit(self, message: str, history: list, **kwargs):
        self._in_q.put((message, history, kwargs))

    def run(self):
        while self._alive:
            try:
                msg, hist, kw = self._in_q.get(timeout=0.5)
            except queue.Empty:
                continue
            self.out_q.put(("thinking", ""))
            try:
                text, _tools = self.agent.run_turn(msg, hist, **kw)
                self.out_q.put(("response", text))
            except Exception as exc:
                self.out_q.put(("error", str(exc)))

    def stop(self):
        self._alive = False


# ─── Bubble ──────────────────────────────────────────────────
class Bubble(tk.Frame):
    MAX_W = 65   # chars per line estimate

    def __init__(self, parent, text: str, role: str = "user"):
        super().__init__(parent, bg=C["chat_bg"])
        is_user = role == "user"

        outer = tk.Frame(self, bg=C["chat_bg"])
        outer.pack(fill=tk.X, padx=14, pady=5)

        bub_bg = C["user_bub"] if is_user else C["ai_bub"]
        txt_fg = C["user_fg"] if is_user else C["ai_fg"]

        # Label badge
        badge_txt = "Tu" if is_user else "⚡ DUST"
        badge = tk.Label(outer, text=badge_txt, font=FS,
                        bg=bub_bg, fg=C["user_fg"] if is_user else C["accent"],
                        padx=7, pady=2, bd=0)

        # Scrollable text widget
        w = min(self.MAX_W, max(20, max((len(ln) for ln in text.splitlines()), default=20)))
        h = self._height(text, w)
        txt_w = tk.Text(outer, wrap=tk.WORD, width=w, height=h,
                       bg=bub_bg, fg=txt_fg, font=FF,
                       bd=0, relief="flat", padx=10, pady=8,
                       cursor="arrow", state=tk.NORMAL, spacing3=2)
        txt_w.insert("1.0", text)
        txt_w.configure(state=tk.DISABLED)

        if is_user:
            badge.pack(side=tk.RIGHT, anchor="ne", padx=(6, 0))
            txt_w.pack(side=tk.RIGHT, anchor="ne", padx=4)
        else:
            badge.pack(side=tk.LEFT, anchor="nw", padx=(0, 6))
            txt_w.pack(side=tk.LEFT, anchor="nw", padx=4)

    @staticmethod
    def _height(text: str, width: int) -> int:
        lines = 0
        for ln in text.splitlines():
            lines += max(1, len(ln) // max(width, 1) + 1)
        return min(max(2, lines), 30)


# ─── Thinking dots ───────────────────────────────────────────
class Thinking(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=C["chat_bg"])
        outer = tk.Frame(self, bg=C["chat_bg"])
        outer.pack(fill=tk.X, padx=14, pady=5)
        tk.Label(outer, text="⚡ DUST", font=FS,
                bg=C["ai_bub"], fg=C["accent"], padx=7, pady=2).pack(side=tk.LEFT, padx=(0, 6))
        self._lbl = tk.Label(outer, text="Sto pensando…", font=FF,
                            bg=C["ai_bub"], fg=C["muted"], padx=10, pady=8)
        self._lbl.pack(side=tk.LEFT)
        self._n = 0; self._on = True; self._tick()

    def _tick(self):
        if self._on:
            self._lbl.config(text="Sto pensando" + "." * (self._n % 4))
            self._n += 1
            self.after(420, self._tick)

    def kill(self):
        self._on = False


# ─── Main GUI ────────────────────────────────────────────────
class DustGUI:
    def __init__(self, root: tk.Tk):
        self.root     = root
        self.history: list[dict] = []
        self.agent    = None
        self.worker: AgentWorker | None = None
        self._q       = queue.Queue()
        self._think: Thinking | None = None

        root.title("DUST AI — Assistente Universale v4.0")
        root.configure(bg=C["bg"])
        root.geometry("960x720")
        root.minsize(640, 480)

        self._build()
        self._set_status("Inizializzazione…", "warn")
        threading.Thread(target=self._init_agent, daemon=True).start()
        self._poll()

    # ── Layout ───────────────────────────────────────────────
    def _build(self):
        root = self.root
        root.columnconfigure(0, weight=0, minsize=190)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)

        # Sidebar
        sb = tk.Frame(root, bg=C["sidebar"], width=190)
        sb.grid(row=0, column=0, sticky="nsew")
        sb.grid_propagate(False)

        tk.Label(sb, text="⚡  DUST AI", font=FT, bg=C["sidebar"],
                fg=C["accent"], pady=22).pack()
        tk.Frame(sb, bg=C["border"], height=1).pack(fill=tk.X, padx=12)
        tk.Label(sb, text="Assistente Universale", font=FS,
                bg=C["sidebar"], fg=C["muted"]).pack(pady=(6, 0))
        tk.Label(sb, text="v4.0  •  Gemini + Ollama", font=FS,
                bg=C["sidebar"], fg=C["muted"]).pack(pady=(2, 10))

        btn = tk.Button(sb, text="＋  Nuova chat", font=FS,
                       bg=C["btn"], fg="white", relief="flat",
                       activebackground=C["btn_hover"], padx=10, pady=7,
                       cursor="hand2", command=self._new_chat)
        btn.pack(fill=tk.X, padx=12, pady=8)

        # Status bar (bottom of sidebar)
        sf = tk.Frame(sb, bg=C["sidebar"])
        sf.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=14)
        self._dot = tk.Label(sf, text="●", bg=C["sidebar"], fg=C["warn"], font=("Arial", 11))
        self._dot.pack(side=tk.LEFT)
        self._slbl = tk.Label(sf, text="…", font=FS, bg=C["sidebar"], fg=C["muted"])
        self._slbl.pack(side=tk.LEFT, padx=4)

        # Chat panel
        chat = tk.Frame(root, bg=C["chat_bg"])
        chat.grid(row=0, column=1, sticky="nsew")
        chat.rowconfigure(0, weight=1)
        chat.rowconfigure(1, weight=0)
        chat.columnconfigure(0, weight=1)

        # Scrollable message area
        cv_frame = tk.Frame(chat, bg=C["chat_bg"])
        cv_frame.grid(row=0, column=0, sticky="nsew")
        cv_frame.rowconfigure(0, weight=1)
        cv_frame.columnconfigure(0, weight=1)

        self._cv = tk.Canvas(cv_frame, bg=C["chat_bg"], highlightthickness=0)
        vsb = ttk.Scrollbar(cv_frame, orient="vertical", command=self._cv.yview)
        self._msgs = tk.Frame(self._cv, bg=C["chat_bg"])
        self._cw   = self._cv.create_window((0, 0), window=self._msgs, anchor="nw")
        self._cv.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._cv.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._msgs.bind("<Configure>", lambda e: self._cv.configure(
            scrollregion=self._cv.bbox("all")))
        self._cv.bind("<Configure>", lambda e: self._cv.itemconfig(self._cw, width=e.width))
        self._cv.bind_all("<MouseWheel>", lambda e: self._cv.yview_scroll(
            -1 * (e.delta // 120), "units"))

        # Welcome
        tk.Label(self._msgs, text="Ciao! Sono DUST AI.\nCome posso aiutarti oggi?",
                font=FT, bg=C["chat_bg"], fg=C["accent"], pady=40).pack()

        # Input area
        inp = tk.Frame(chat, bg=C["input_bg"], pady=12, padx=14)
        inp.grid(row=1, column=0, sticky="ew")
        inp.columnconfigure(0, weight=1)

        self._inp = tk.Text(inp, height=3, font=FF, bg=C["input_bg"], fg=C["input_fg"],
                           relief="flat", bd=0, wrap=tk.WORD,
                           insertbackground=C["accent"], padx=10, pady=8)
        self._inp.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self._inp.bind("<Return>",       self._on_enter)
        self._inp.bind("<Shift-Return>", lambda e: None)

        send = tk.Button(inp, text="Invia  ▶", font=FF, bg=C["accent"], fg=C["bg"],
                        relief="flat", padx=14, pady=8, cursor="hand2",
                        activebackground=C["btn"], command=self._send)
        send.grid(row=0, column=1)

        tk.Label(inp, text="Invio = invia  |  Shift+Invio = nuova riga",
                font=FS, bg=C["input_bg"], fg=C["muted"]).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))

    # ── Agent init ───────────────────────────────────────────
    def _init_agent(self):
        try:
            from agent import Agent
            from tools.registry import Registry
            import tools.computer_use as cu

            reg = Registry()
            reg.register_module(cu)

            for mod_name in ("tools.file_ops", "tools.web_search", "tools.sys_exec",
                             "tools.browser", "tools.input_control",
                             "tools.windows_apps", "tools.code_runner",
                             "tools.github_tool"):
                try:
                    import importlib
                    m = importlib.import_module(mod_name)
                    reg.register_module(m)
                except Exception:
                    pass

            try:
                from github_sync import sync_push, sync_pull, get_status
                reg.register_function("github_sync_push",  sync_push,  "Push al repo GitHub")
                reg.register_function("github_sync_pull",  sync_pull,  "Pull dal repo GitHub")
                reg.register_function("github_sync_status", get_status, "Status git")
            except Exception:
                pass

            bridge = None
            try:
                from tools.browser_ai_bridge import BrowserAIBridge
                bridge = BrowserAIBridge()
            except Exception:
                pass

            self.agent  = Agent(tools_registry=reg, browser_bridge=bridge)
            self.worker = AgentWorker(self.agent, self._q)
            self.worker.start()
            self._q.put(("status_ok", "Pronto"))
        except Exception as exc:
            self._q.put(("status_err", f"Errore init: {exc}"))

    # ── Send / receive ────────────────────────────────────────
    def _on_enter(self, event):
        if not (event.state & 0x1):   # Shift not held
            self._send()
            return "break"

    def _send(self):
        txt = self._inp.get("1.0", tk.END).strip()
        if not txt:
            return
        self._inp.delete("1.0", tk.END)
        self._add_bubble(txt, "user")
        self.history.append({"role": "user", "content": txt})
        self._inp.configure(state=tk.DISABLED)
        self._set_status("Elaborando…", "warn")
        if self.worker:
            self.worker.submit(txt, list(self.history[:-1]))
        else:
            self._q.put(("error", "Agent non ancora pronto, riprova."))

    def _poll(self):
        try:
            while True:
                kind, data = self._q.get_nowait()
                if kind == "thinking":
                    self._show_think()
                elif kind == "response":
                    self._hide_think()
                    self._add_bubble(data, "assistant")
                    self.history.append({"role": "assistant", "content": data})
                    self._inp.configure(state=tk.NORMAL)
                elif kind == "error":
                    self._hide_think()
                    self._add_bubble(f"❌ {data}", "assistant")
                    self._inp.configure(state=tk.NORMAL)
                elif kind == "status_ok":
                    self._set_status(data, "ok")
                elif kind == "status_err":
                    self._set_status(data, "err")
        except queue.Empty:
            pass
        self.root.after(80, self._poll)

    def _add_bubble(self, text: str, role: str):
        b = Bubble(self._msgs, text, role)
        b.pack(fill=tk.X)
        self.root.after(120, lambda: self._cv.yview_moveto(1.0))

    def _show_think(self):
        if self._think is None:
            self._think = Thinking(self._msgs)
            self._think.pack(fill=tk.X)
        self.root.after(120, lambda: self._cv.yview_moveto(1.0))

    def _hide_think(self):
        if self._think:
            self._think.kill()
            self._think.destroy()
            self._think = None

    def _new_chat(self):
        self.history.clear()
        for w in self._msgs.winfo_children():
            w.destroy()
        tk.Label(self._msgs, text="Nuova chat — come posso aiutarti?",
                font=FT, bg=C["chat_bg"], fg=C["accent"], pady=40).pack()

    def _set_status(self, text: str, level: str = "ok"):
        col = {"ok": C["ok"], "err": C["err"], "warn": C["warn"]}.get(level, C["muted"])
        self._dot.configure(fg=col)
        self._slbl.configure(text=text[:30])


def main():
    root = tk.Tk()
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except Exception:
        pass
    style.configure("Vertical.TScrollbar",
                   background=C["border"], troughcolor=C["chat_bg"],
                   borderwidth=0, arrowsize=12)
    DustGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
