"""
DUST AI – ComputerUse v2.0
Vede lo schermo e usa mouse + tastiera su qualsiasi app Windows.
Loop: screenshot → Gemini Vision (gratis) → pyautogui → ripeti.
Nessuna modifica alle app target: agisce sull'UI come un umano.
"""
import io, json, time, logging, random, re, os
from pathlib import Path
from datetime import datetime

log = logging.getLogger("ComputerUse")

SCREEN_DIR = Path(r"A:\dustai_stuff\screenshots")
SCREEN_DIR.mkdir(parents=True, exist_ok=True)

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE    = 0.04
    _PYA = True
except ImportError:
    _PYA = False
    log.warning("pyautogui non installato: pip install pyautogui")

try:
    from PIL import ImageGrab
    _PIL = True
except ImportError:
    _PIL = False
    log.warning("Pillow non installato: pip install pillow")

_VISION_PROMPT = """Sei un agente AI che controlla un PC Windows tramite visione+azioni.
Guarda lo screenshot e decidi la PROSSIMA SINGOLA azione per completare il task.

TASK: {task}
STEP: {step}/{max_steps}
STORICO AZIONI: {history}
RISOLUZIONE: {w}x{h}

Rispondi ESCLUSIVAMENTE con JSON valido, nessun testo fuori dal JSON:
{{
  "thought": "cosa vedo e cosa farò (max 80 char)",
  "done": false,
  "result": "",
  "action": "click|double_click|right_click|type|hotkey|scroll|open_app|open_url|wait|ask_user|done",
  "x": 0,
  "y": 0,
  "text": "",
  "keys": "",
  "direction": "down",
  "amount": 3,
  "app": "",
  "url": "",
  "question": ""
}}

AZIONI:
- click/double_click/right_click: x,y coordinate pixel sullo schermo
- type: testo da digitare (text)
- hotkey: combinazione tasti (keys, es: "ctrl+c", "win+r", "alt+f4")
- scroll: direction=up/down, amount=righe
- open_app: nome app Windows (app)
- open_url: URL da aprire (url)
- wait: attendi N secondi (amount)
- ask_user: fai una domanda all'utente (question) — solo se INDISPENSABILE
- done: task completato, metti result=risultato
"""

_READ_PROMPT = """Descrivi questo screenshot Windows in modo preciso:
1. Che applicazione/finestra è aperta
2. Cosa c'è scritto (testo visibile importante)
3. Stato della schermata (form, menu, ecc.)
Rispondi in 3-5 righe in italiano."""


class ComputerUse:
    def __init__(self, config):
        self.config = config
        self._w = self._h = 1920
        if _PYA:
            self._w, self._h = pyautogui.size()

    # ── API principale ────────────────────────────────────────────────────────

    def do(self, task: str, max_steps: int = 25) -> str:
        if not _PYA or not _PIL:
            return "pyautogui o Pillow non installati (pip install pyautogui pillow)"
        print(f"\n🖥  screen_do: {task[:70]}")
        history = []

        for step in range(1, max_steps + 1):
            print(f"  [{step:02d}] ", end="", flush=True)
            _, img = self._screenshot(f"do_{step:02d}")
            prompt  = _VISION_PROMPT.format(
                task=task, step=step, max_steps=max_steps,
                history=json.dumps(history[-5:], ensure_ascii=False),
                w=self._w, h=self._h
            )
            dec = self._vision(prompt, img)
            if dec is None:
                print("vision N/D"); break
            if isinstance(dec, str):
                # Stringa invece di dict = risposta finale
                print(dec[:60])
                return dec

            thought = dec.get("thought", "…")
            action  = dec.get("action",  "wait")
            print(thought[:70])
            history.append({"s": step, "a": action, "t": thought[:30]})

            if dec.get("done") or action == "done":
                result = dec.get("result", "completato")
                print(f"\n  ✅ {result}")
                return result

            if action == "ask_user":
                return f"ASK_USER:{dec.get('question','')}"

            self._exec_action(dec)
            time.sleep(random.uniform(0.5, 1.1))

        return "⚠️ Massimo step raggiunto senza completamento"

    def read(self) -> str:
        if not _PIL:
            return "Pillow non installato"
        _, img = self._screenshot("read")
        r = self._vision(_READ_PROMPT, img)
        if isinstance(r, dict):
            return r.get("thought", str(r))
        return r or "Impossibile leggere lo schermo"

    def click_target(self, description: str) -> str:
        if not _PYA or not _PIL:
            return "pyautogui/Pillow non installati"
        _, img = self._screenshot("click")
        p = (f'Trova "{description}" sullo schermo. '
             f'Rispondi SOLO JSON: {{"found":true,"x":100,"y":200}}')
        r = self._vision(p, img)
        if isinstance(r, dict) and r.get("found") and r.get("x"):
            self._click(int(r["x"]), int(r["y"]))
            return f"✅ Cliccato '{description}'"
        return f"❌ Non trovato: {description}"

    # ── Esecuzione azioni ─────────────────────────────────────────────────────

    def _exec_action(self, d: dict):
        a = d.get("action", "")
        try:
            if a in ("click", "double_click", "right_click"):
                x, y = int(d.get("x", 0)), int(d.get("y", 0))
                if x > 0 and y > 0:
                    btn = "right" if a == "right_click" else "left"
                    self._click(x, y, button=btn, double=(a == "double_click"))
                    print(f" 🖱 {a}({x},{y})", end="")

            elif a == "type":
                text = d.get("text", "")
                for ch in text:
                    pyautogui.write(ch, interval=0)
                    time.sleep(random.uniform(0.02, 0.07))
                print(f" ⌨ {text[:30]!r}", end="")

            elif a == "hotkey":
                keys  = d.get("keys", "")
                parts = [k.strip() for k in re.split(r"[+\s]+", keys) if k.strip()]
                if parts:
                    pyautogui.hotkey(*parts)
                    time.sleep(0.3)
                    print(f" ⌨ {keys}", end="")

            elif a == "scroll":
                n = int(d.get("amount", 3))
                pyautogui.scroll(n if d.get("direction") == "up" else -n)
                print(f" 🖱 scroll {d.get('direction','down')}×{n}", end="")

            elif a == "open_app":
                self._open_app(d.get("app", ""))

            elif a == "open_url":
                import webbrowser
                webbrowser.open(d.get("url", ""))
                time.sleep(2.5)
                print(f" 🌐 {d.get('url','')}", end="")

            elif a == "wait":
                t = min(30, float(d.get("amount", 2)))
                print(f" ⏳ {t}s", end="")
                time.sleep(t)

        except Exception as e:
            log.warning("exec [%s]: %s", a, str(e)[:60])
        print()

    def _click(self, x, y, button="left", double=False):
        jx = x + random.randint(-2, 2)
        jy = y + random.randint(-2, 2)
        pyautogui.moveTo(jx, jy, duration=random.uniform(0.10, 0.25),
                         tween=pyautogui.easeInOutQuad)
        time.sleep(random.uniform(0.03, 0.08))
        if double:
            pyautogui.doubleClick(button=button)
        else:
            pyautogui.click(button=button)

    def _open_app(self, name: str):
        APPS = {
            "chrome":   r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            "edge":     r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            "notepad":  "notepad.exe",
            "explorer": "explorer.exe",
            "vscode":   r"C:\Users\ugopl\AppData\Local\Programs\Microsoft VS Code\Code.exe",
            "cmd":      "cmd.exe",
            "powershell": "powershell.exe",
        }
        n = name.lower()
        for k, v in APPS.items():
            if k in n:
                try:
                    os.startfile(v)
                    time.sleep(2)
                    return
                except Exception:
                    pass
        # Fallback: Win+R
        pyautogui.hotkey("win", "r")
        time.sleep(0.6)
        pyautogui.write(name, interval=0.04)
        pyautogui.press("enter")
        time.sleep(2)
        print(f" 🚀 {name}", end="")

    # ── Vision ────────────────────────────────────────────────────────────────

    def _vision(self, prompt: str, img_bytes: bytes):
        import google.generativeai as genai
        keys = self.config.get_all_google_keys() if hasattr(self.config, "get_all_google_keys") else []
        if not keys:
            # fallback: singola key
            k = os.environ.get("GOOGLE_API_KEY", "")
            if k:
                keys = [("GOOGLE_API_KEY", k)]

        for env, key in keys:
            try:
                genai.configure(api_key=key)
                model = genai.GenerativeModel("gemini-2.5-flash")
                resp  = model.generate_content([
                    prompt,
                    {"mime_type": "image/png", "data": img_bytes}
                ])
                try:
                    text = resp.text.strip()
                except Exception:
                    continue
                if not text:
                    continue
                m = re.search(r"\{[^{}]*\}", text, re.DOTALL)
                if m:
                    try:
                        return json.loads(m.group())
                    except Exception:
                        pass
                # Prova a parsare tutto il testo come JSON
                try:
                    return json.loads(text)
                except Exception:
                    pass
                return text
            except Exception as e:
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    continue
                log.warning("Vision [%s]: %s", env, str(e)[:60])
        return None

    # ── Screenshot ────────────────────────────────────────────────────────────

    def _screenshot(self, label=""):
        ts   = datetime.now().strftime("%H%M%S_%f")[:10]
        path = SCREEN_DIR / f"cu_{ts}_{label}.png"
        img  = ImageGrab.grab()
        img.save(str(path), format="PNG")
        buf  = io.BytesIO()
        img.save(buf, format="PNG")
        return path, buf.getvalue()


# ── Tool wrapper (esposto a ToolRegistry) ─────────────────────────────────────

class ComputerUseTool:
    def __init__(self, config):
        self._cu = ComputerUse(config)

    def screen_do(self, task: str) -> str:
        return self._cu.do(task)

    def screen_read(self) -> str:
        return self._cu.read()

    def screen_click(self, target: str) -> str:
        return self._cu.click_target(target)

    def screen_type(self, text: str) -> str:
        if _PYA:
            for ch in text:
                pyautogui.write(ch, interval=0)
                time.sleep(random.uniform(0.02, 0.07))
            return f"✅ Digitato: {text[:40]}"
        return "pyautogui non installato"

    def screen_hotkey(self, keys: str) -> str:
        if not _PYA:
            return "pyautogui non installato"
        parts = [k.strip() for k in re.split(r"[+\s]+", keys) if k.strip()]
        pyautogui.hotkey(*parts)
        time.sleep(0.3)
        return f"✅ Hotkey: {keys}"

    def screen_scroll(self, direction: str = "down", amount: str = "3") -> str:
        if not _PYA:
            return "pyautogui non installato"
        n = int(str(amount))
        pyautogui.scroll(n if direction == "up" else -n)
        return f"✅ Scroll {direction} ×{amount}"

    def app_open(self, name: str) -> str:
        self._cu._open_app(name)
        return f"✅ Aperto: {name}"

    def browser_go(self, url: str) -> str:
        import webbrowser
        webbrowser.open(url)
        time.sleep(2.5)
        return f"✅ Browser: {url}"

    def browser_do(self, task: str) -> str:
        return self._cu.do(f"Nel browser: {task}")
