"""DUST AI GUI v3.3 — Tool log, dust_tools integrati."""
import json
import queue
import sys
import threading
import tkinter as tk
from tkinter import ttk
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

C = {
    "bg":"#1a1a2e","sidebar":"#16213e","chat_bg":"#0d1117",
    "user_bub":"#1f6feb","ai_bub":"#161b22","tool_bub":"#1a2a1a",
    "user_fg":"#f0f6fc","ai_fg":"#c9d1d9","tool_fg":"#3fb950",
    "input_bg":"#161b22","input_fg":"#f0f6fc",
    "btn":"#238636","btn_hover":"#2ea043",
    "accent":"#58a6ff","muted":"#8b949e","border":"#30363d",
    "ok":"#3fb950","err":"#f85149","warn":"#d29922",
}
FF=("Segoe UI",11); FT=("Segoe UI",13,"bold"); FS=("Segoe UI",9)
FM=("Consolas",10)


class AgentWorker(threading.Thread):
    def __init__(self, agent, out_q):
        super().__init__(daemon=True,name="AgentWorker")
        self.agent=agent; self.out_q=out_q
        self._in_q=queue.Queue(); self._alive=True

    def submit(self, msg, history):
        self._in_q.put((msg,history))

    def run(self):
        while self._alive:
            try:
                msg,hist = self._in_q.get(timeout=0.5)
            except queue.Empty:
                continue
            self.out_q.put(("thinking",""))
            try:
                text, tools = self.agent.run_turn(msg, hist)
                # Mostra tool calls se presenti
                if tools:
                    summary = []
                    for t in tools:
                        name   = t.get("tool","?")
                        result = t.get("result",{})
                        status = result.get("status","?") if isinstance(result,dict) else "ok"
                        summary.append(f"  ⚙ {name} → {status}")
                    self.out_q.put(("tool_log", "\n".join(summary)))
                self.out_q.put(("response",text))
            except Exception as exc:
                self.out_q.put(("error",str(exc)))

    def stop(self):
        self._alive=False


class Bubble(tk.Frame):
    def __init__(self, parent, text, role="user"):
        super().__init__(parent,bg=C["chat_bg"])
        is_u  = role=="user"
        is_t  = role=="tool"
        outer = tk.Frame(self,bg=C["chat_bg"])
        outer.pack(fill=tk.X,padx=14,pady=3 if is_t else 5)
        if is_t:
            bub_bg = C["tool_bub"]; txt_fg = C["tool_fg"]
            badge_txt = "⚙ Tool"
            badge_fg  = C["tool_fg"]
            font_use  = FM
        elif is_u:
            bub_bg=C["user_bub"]; txt_fg=C["user_fg"]
            badge_txt="Tu"; badge_fg=C["user_fg"]; font_use=FF
        else:
            bub_bg=C["ai_bub"]; txt_fg=C["ai_fg"]
            badge_txt="⚡ DUST"; badge_fg=C["accent"]; font_use=FF
        badge=tk.Label(outer,text=badge_txt,font=FS,bg=bub_bg,
                      fg=badge_fg,padx=7,pady=2)
        w=min(70,max(20,max((len(l) for l in text.splitlines()),default=20)))
        h=min(20 if is_t else 30,
              max(1,sum(max(1,len(l)//max(w,1)+1) for l in text.splitlines())))
        tw=tk.Text(outer,wrap=tk.WORD,width=w,height=h,
                  bg=bub_bg,fg=txt_fg,font=font_use,
                  bd=0,relief="flat",padx=10,pady=6,cursor="arrow")
        tw.insert("1.0",text); tw.configure(state=tk.DISABLED)
        if is_u:
            badge.pack(side=tk.RIGHT,anchor="ne",padx=(6,0))
            tw.pack(side=tk.RIGHT,anchor="ne",padx=4)
        else:
            badge.pack(side=tk.LEFT,anchor="nw",padx=(0,6))
            tw.pack(side=tk.LEFT,anchor="nw",padx=4)


class Thinking(tk.Frame):
    def __init__(self,parent):
        super().__init__(parent,bg=C["chat_bg"])
        outer=tk.Frame(self,bg=C["chat_bg"])
        outer.pack(fill=tk.X,padx=14,pady=5)
        tk.Label(outer,text="⚡ DUST",font=FS,bg=C["ai_bub"],
                fg=C["accent"],padx=7,pady=2).pack(side=tk.LEFT,padx=(0,6))
        self._l=tk.Label(outer,text="Sto pensando…",font=FF,
                        bg=C["ai_bub"],fg=C["muted"],padx=10,pady=8)
        self._l.pack(side=tk.LEFT)
        self._n=0; self._on=True; self._tick()
    def _tick(self):
        if self._on:
            self._l.config(text="Sto pensando"+"."*(self._n%4))
            self._n+=1; self.after(420,self._tick)
    def kill(self): self._on=False


class DustGUI:
    def __init__(self,root):
        self.root=root; self.history=[]; self.agent=None
        self.worker=None; self._q=queue.Queue(); self._think=None
        root.title("DUST AI v4.3")
        root.configure(bg=C["bg"]); root.geometry("980x740")
        root.minsize(640,480)
        self._build()
        self._set_status("Inizializzazione…","warn")
        threading.Thread(target=self._init_agent,daemon=True).start()
        self._poll()

    def _build(self):
        r=self.root
        r.columnconfigure(0,weight=0,minsize=200)
        r.columnconfigure(1,weight=1); r.rowconfigure(0,weight=1)
        sb=tk.Frame(r,bg=C["sidebar"],width=200)
        sb.grid(row=0,column=0,sticky="nsew"); sb.grid_propagate(False)
        tk.Label(sb,text="⚡  DUST AI",font=FT,bg=C["sidebar"],
                fg=C["accent"],pady=20).pack()
        tk.Frame(sb,bg=C["border"],height=1).pack(fill=tk.X,padx=12)
        tk.Label(sb,text="Agente Autonomo v4.3",font=FS,
                bg=C["sidebar"],fg=C["muted"]).pack(pady=(6,14))
        for label,cmd,bg,fg in [
            ("＋  Nuova chat", self._new_chat,  C["btn"],     "white"),
            ("🔍  Ispeziona",  self._inspect,   C["ai_bub"],  C["accent"]),
            ("🔄  Reset login",self._reset_login,"#3d1f1f",   "white"),
        ]:
            tk.Button(sb,text=label,font=FS,bg=bg,fg=fg,
                     relief="flat",padx=10,pady=6,cursor="hand2",
                     command=cmd).pack(fill=tk.X,padx=12,pady=3)
        self._pvd=tk.Label(sb,text="AI: —",font=FS,
                          bg=C["sidebar"],fg=C["muted"])
        self._pvd.pack(pady=(10,0))
        sf=tk.Frame(sb,bg=C["sidebar"])
        sf.pack(side=tk.BOTTOM,fill=tk.X,padx=12,pady=14)
        self._dot=tk.Label(sf,text="●",bg=C["sidebar"],
                          fg=C["warn"],font=("Arial",11))
        self._dot.pack(side=tk.LEFT)
        self._slbl=tk.Label(sf,text="…",font=FS,bg=C["sidebar"],fg=C["muted"])
        self._slbl.pack(side=tk.LEFT,padx=4)

        chat=tk.Frame(r,bg=C["chat_bg"])
        chat.grid(row=0,column=1,sticky="nsew")
        chat.rowconfigure(0,weight=1); chat.rowconfigure(1,weight=0)
        chat.columnconfigure(0,weight=1)
        cvf=tk.Frame(chat,bg=C["chat_bg"])
        cvf.grid(row=0,column=0,sticky="nsew")
        cvf.rowconfigure(0,weight=1); cvf.columnconfigure(0,weight=1)
        self._cv=tk.Canvas(cvf,bg=C["chat_bg"],highlightthickness=0)
        vsb=ttk.Scrollbar(cvf,orient="vertical",command=self._cv.yview)
        self._msgs=tk.Frame(self._cv,bg=C["chat_bg"])
        self._cw=self._cv.create_window((0,0),window=self._msgs,anchor="nw")
        self._cv.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT,fill=tk.Y)
        self._cv.pack(side=tk.LEFT,fill=tk.BOTH,expand=True)
        self._msgs.bind("<Configure>",
            lambda e:self._cv.configure(scrollregion=self._cv.bbox("all")))
        self._cv.bind("<Configure>",
            lambda e:self._cv.itemconfig(self._cw,width=e.width))
        self._cv.bind_all("<MouseWheel>",
            lambda e:self._cv.yview_scroll(-1*(e.delta//120),"units"))
        tk.Label(self._msgs,
            text="Ciao! Sono DUST AI v4.3 — Agente Autonomo\n"
                 "Penso, pianifco ed eseguo in autonomia.\nCome posso aiutarti?",
            font=FT,bg=C["chat_bg"],fg=C["accent"],pady=40).pack()

        inp=tk.Frame(chat,bg=C["input_bg"],pady=12,padx=14)
        inp.grid(row=1,column=0,sticky="ew"); inp.columnconfigure(0,weight=1)
        self._inp=tk.Text(inp,height=3,font=FF,bg=C["input_bg"],fg=C["input_fg"],
                         relief="flat",bd=0,wrap=tk.WORD,
                         insertbackground=C["accent"],padx=10,pady=8)
        self._inp.grid(row=0,column=0,sticky="ew",padx=(0,10))
        self._inp.bind("<Return>",self._on_enter)
        self._inp.bind("<Shift-Return>",lambda e:None)
        tk.Button(inp,text="Invia  ▶",font=FF,bg=C["accent"],fg=C["bg"],
                 relief="flat",padx=14,pady=8,cursor="hand2",
                 command=self._send).grid(row=0,column=1)
        tk.Label(inp,text="Invio = invia  |  Shift+Invio = a capo",
                font=FS,bg=C["input_bg"],fg=C["muted"]).grid(
            row=1,column=0,columnspan=2,sticky="w",pady=(4,0))

    def _init_agent(self):
        try:
            import importlib
            from agent import Agent
            from tools.registry import Registry
            import tools.computer_use as cu
            import tools.dust_tools as dt

            reg=Registry()
            reg.register_module(cu)
            reg.register_module(dt)

            # Self-knowledge
            try:
                from self_knowledge import (self_inspect,self_list_tools,
                                            self_env,self_edit_file,
                                            self_reload_module)
                reg.register_function("self_inspect",    self_inspect,
                    "Leggi codice sorgente di DUST")
                reg.register_function("self_list_tools", self_list_tools,
                    "Lista tool DUST")
                reg.register_function("self_env",        self_env,
                    "Ambiente di DUST")
                reg.register_function("self_edit_file",  self_edit_file,
                    "Modifica codice sorgente")
                reg.register_function("self_reload",     self_reload_module,
                    "Ricarica modulo")
            except Exception:
                pass

            # Moduli extra
            for mn in ("tools.file_ops","tools.browser",
                       "tools.input_control","tools.windows_apps",
                       "tools.github_tool"):
                try:
                    m=importlib.import_module(mn); reg.register_module(m)
                except Exception:
                    pass

            try:
                from github_sync import sync_push,sync_pull,get_status
                reg.register_function("github_push",  sync_push,  "Push GitHub")
                reg.register_function("github_pull",  sync_pull,  "Pull GitHub")
                reg.register_function("github_status",get_status, "Git status")
            except Exception:
                pass

            bridge=None
            try:
                from tools.browser_ai_bridge import BrowserAIBridge
                bridge=BrowserAIBridge()
            except Exception:
                pass

            self.agent=Agent(tools_registry=reg,browser_bridge=bridge)
            self.worker=AgentWorker(self.agent,self._q)
            self.worker.start()

            from config import GROQ_API_KEY,GEMINI_KEYS
            pvd=[]
            if GEMINI_KEYS: pvd.append(f"Gemini×{len(GEMINI_KEYS)}")
            if GROQ_API_KEY: pvd.append("Groq")
            pvd.extend(["Browser","Ollama"])
            self._q.put(("pvd"," → ".join(pvd)))
            self._q.put(("status_ok","Pronto — agente autonomo"))
        except Exception as exc:
            self._q.put(("status_err",f"Init: {exc}"))

    def _reset_login(self):
        try:
            from config import BROWSER_PROFILE_DIR
            flag=Path(BROWSER_PROFILE_DIR)/".google_logged_in"
            if flag.exists(): flag.unlink()
            self._add_bubble("🔄 Login reset — al prossimo uso BrowserAI\nrichiederà login Google.","assistant")
        except Exception as exc:
            self._add_bubble(f"❌ {exc}","assistant")

    def _inspect(self):
        self._inp.delete("1.0",tk.END)
        self._inp.insert("1.0",
            "Elenca i tuoi file sorgente, tool disponibili e cascade AI.")
        self._send()

    def _on_enter(self,event):
        if not (event.state&0x1):
            self._send(); return "break"

    def _send(self):
        txt=self._inp.get("1.0",tk.END).strip()
        if not txt: return
        self._inp.delete("1.0",tk.END)
        self._add_bubble(txt,"user")
        self.history.append({"role":"user","content":txt})
        self._inp.configure(state=tk.DISABLED)
        self._set_status("Elaborando…","warn")
        if self.worker:
            self.worker.submit(txt,list(self.history[:-1]))
        else:
            self._q.put(("error","Agent non pronto."))

    def _poll(self):
        try:
            while True:
                kind,data=self._q.get_nowait()
                if kind=="thinking": self._show_think()
                elif kind=="tool_log":
                    self._hide_think()
                    self._add_bubble(data,"tool")
                    self._show_think()
                elif kind=="response":
                    self._hide_think()
                    self._add_bubble(data,"assistant")
                    self.history.append({"role":"assistant","content":data})
                    self._inp.configure(state=tk.NORMAL)
                    self._set_status("Pronto","ok")
                elif kind=="error":
                    self._hide_think()
                    self._add_bubble(f"❌ {data}","assistant")
                    self._inp.configure(state=tk.NORMAL)
                elif kind=="status_ok": self._set_status(data,"ok")
                elif kind=="status_err": self._set_status(data,"err")
                elif kind=="pvd":
                    self._pvd.configure(text=f"AI: {data[:30]}")
        except queue.Empty:
            pass
        self.root.after(80,self._poll)

    def _add_bubble(self,text,role):
        b=Bubble(self._msgs,text,role); b.pack(fill=tk.X)
        self.root.after(120,lambda:self._cv.yview_moveto(1.0))

    def _show_think(self):
        if self._think is None:
            self._think=Thinking(self._msgs); self._think.pack(fill=tk.X)
        self.root.after(120,lambda:self._cv.yview_moveto(1.0))

    def _hide_think(self):
        if self._think:
            self._think.kill(); self._think.destroy(); self._think=None

    def _new_chat(self):
        self.history.clear()
        for w in self._msgs.winfo_children(): w.destroy()
        tk.Label(self._msgs,text="Nuova chat — come posso aiutarti?",
                font=FT,bg=C["chat_bg"],fg=C["accent"],pady=40).pack()

    def _set_status(self,text,level="ok"):
        col={"ok":C["ok"],"err":C["err"],"warn":C["warn"]}.get(level,C["muted"])
        self._dot.configure(fg=col); self._slbl.configure(text=text[:35])


def main():
    root=tk.Tk()
    style=ttk.Style()
    try: style.theme_use("clam")
    except Exception: pass
    style.configure("Vertical.TScrollbar",
        background=C["border"],troughcolor=C["chat_bg"],
        borderwidth=0,arrowsize=12)
    DustGUI(root); root.mainloop()


if __name__=="__main__":
    main()
