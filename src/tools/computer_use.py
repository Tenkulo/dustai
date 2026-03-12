"""
DUST AI – ComputerUseTool v1.0
================================
Vede lo schermo, muove mouse, usa tastiera su qualsiasi app Windows.
Nessuna modifica alle app: lavora sull'interfaccia grafica come un umano.

LOOP PRINCIPALE (screen_do):
  1. Screenshot schermo intero
  2. Manda a Gemini Vision: "task=X, step=N, cosa faccio?"
  3. Gemini risponde JSON con l'azione
  4. Esegui azione con pyautogui (mouse umano: curva ease, piccoli jitter)
  5. Aspetta che lo schermo si aggiorni
  6. Torna a 1 finché done=true o max_steps raggiunto
"""
import io, json, time, base64, logging, random, math, os, re, subprocess, platform
from pathlib import Path
from datetime import datetime
import pyautogui
from PIL import Image, ImageGrab

log = logging.getLogger("ComputerUse")
SCREENSHOT_DIR = Path(r"A:\dustai_stuff\screenshots")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

# ── Sicurezza ────────────────────────────────────────────────
pyautogui.FAILSAFE  = True   # sposta mouse angolo top-left per fermare
pyautogui.PAUSE     = 0.08   # piccola pausa tra azioni (sembra umano)

# ── Prompt Vision ────────────────────────────────────────────
VISION_PROMPT = """Sei un agente AI che controlla un computer Windows per completare un task.
Guarda questo screenshot e decidi la prossima singola azione da eseguire.

TASK COMPLETO: {task}
STEP: {step}/{max_steps}
STORIA AZIONI: {history}

REGOLE:
- Fai UNA SOLA azione alla volta
- Se vedi un dialogo di conferma, gestiscilo
- Se l'app non è aperta, aprila prima
- Se manca info (es. nome repo), rispondi con action="ask_user"
- Usa le coordinate PRECISE in pixel basandoti sull'immagine
- Lo schermo è {w}x{h} pixel

Rispondi SOLO in JSON valido:
{{
  "thought": "cosa vedo e perché faccio questa azione",
  "done": false,
  "result": "",
  "action": "click|double_click|right_click|type|hotkey|scroll|open_app|open_url|wait|ask_user|done",
  "x": 0,
  "y": 0,
  "text": "",
  "keys": "",
  "direction": "up|down",
  "amount": 3,
  "app": "",
  "url": "",
  "question": ""
}}

CAMPI PER AZIONE:
- click/double_click/right_click: x, y (pixel precisi dall'immagine)
- type: text (testo da digitare)
- hotkey: keys (es. "ctrl+t", "win+r", "alt+f4")
- scroll: direction, amount (numero di scroll)
- open_app: app (nome app: "chrome","edge","notepad","explorer","github")
- open_url: url (URL completo)
- wait: (aspetta che la pagina carichi)
- ask_user: question (cosa chiedere all'utente)
- done: result (descrizione di cosa è stato fatto)
"""

READ_PROMPT = """Guarda questo screenshot Windows e descrivi:
1. Quale applicazione è aperta (o il desktop)
2. Cosa è visibile (testo, pulsanti, form, ecc.)
3. Eventuali errori o messaggi importanti

Sii conciso e pratico."""


class ComputerUse:
    """
    Agente che usa il computer come un umano:
    screenshot → Gemini Vision → pyautogui
    """
    def __init__(self, config):
        self.config    = config
        self._gemini   = None
        self._w, self._h = pyautogui.size()
        log.info("ComputerUse pronto: schermo %dx%d", self._w, self._h)

    # ════════════════════════════════════════════════════════════
    # API PRINCIPALE
    # ════════════════════════════════════════════════════════════

    def do(self, task: str, max_steps: int = 20) -> str:
        """
        Esegui un task completo usando il computer.
        Es: do("crea una repo chiamata 'test' su github.com")
        """
        log.info("ComputerUse.do: %s", task[:80])
        print(f"\n🖥️  DUST prende il controllo del computer")
        print(f"📋 Task: {task}")
        print(f"{'─'*50}")

        history = []
        last_screenshot_path = None

        for step in range(1, max_steps + 1):
            print(f"\n[Step {step}/{max_steps}]", end=" ")

            # 1. Screenshot
            screenshot_path, img_bytes = self._screenshot(f"step_{step:02d}")
            last_screenshot_path = screenshot_path

            # 2. Chiedi a Gemini cosa fare
            prompt = VISION_PROMPT.format(
                task=task,
                step=step,
                max_steps=max_steps,
                history=json.dumps(history[-5:], ensure_ascii=False),  # ultime 5 azioni
                w=self._w, h=self._h
            )

            decision = self._ask_vision(prompt, img_bytes)
            if not decision:
                print("❌ Vision fallita")
                break

            thought = decision.get("thought", "")
            action  = decision.get("action", "wait")
            print(f"💭 {thought[:80]}")

            history.append({"step": step, "action": action,
                            "thought": thought[:50]})

            # 3. Esegui azione
            if decision.get("done") or action == "done":
                result = decision.get("result", "Task completato")
                print(f"\n✅ {result}")
                return result

            elif action == "ask_user":
                question = decision.get("question", "Hai bisogno di più info?")
                print(f"\n❓ {question}")
                return f"ASK_USER: {question}"

            else:
                ok = self._execute(decision)
                if not ok:
                    print("  ⚠️ Azione fallita, riprovo...")

            # Pausa umana tra step
            time.sleep(random.uniform(0.8, 1.5))

        return "⚠️ Task non completato entro i passi massimi"

    def read_screen(self) -> str:
        """Leggi e descrivi lo schermo corrente."""
        _, img_bytes = self._screenshot("read")
        return self._ask_vision(READ_PROMPT, img_bytes) or "Impossibile leggere lo schermo"

    def click(self, target_description: str) -> str:
        """Trova e clicca un elemento sulla schermata corrente."""
        _, img_bytes = self._screenshot("click")
        prompt = (
            f"Trova '{target_description}' in questo screenshot e dammi le coordinate x,y precise.\n"
            f"Rispondi SOLO in JSON: {{\"found\": true, \"x\": 0, \"y\": 0, \"description\": \"cosa hai trovato\"}}"
        )
        result = self._ask_vision(prompt, img_bytes)
        if isinstance(result, dict) and result.get("found"):
            x, y = result["x"], result["y"]
            self._human_click(x, y)
            return f"✅ Cliccato '{target_description}' a ({x},{y})"
        return f"❌ Elemento '{target_description}' non trovato"

    def type_text(self, text: str) -> str:
        """Digita testo con velocità umana."""
        self._human_type(text)
        return f"✅ Digitato: {text[:50]}"

    def hotkey(self, keys: str) -> str:
        """Premi combinazione tasti. Es: 'ctrl+c', 'win+r'"""
        parts = [k.strip() for k in keys.replace("+", " ").split()]
        pyautogui.hotkey(*parts)
        time.sleep(0.3)
        return f"✅ Hotkey: {keys}"

    def scroll(self, direction: str = "down", amount: int = 3) -> str:
        amt = amount if direction == "up" else -amount
        pyautogui.scroll(amt)
        return f"✅ Scroll {direction} x{amount}"

    def open_app(self, app_name: str) -> str:
        """Apre un'applicazione Windows."""
        app_lower = app_name.lower()

        # Mappa nomi → comandi Windows
        APP_MAP = {
            "chrome":    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            "edge":      r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            "firefox":   r"C:\Program Files\Mozilla Firefox\firefox.exe",
            "notepad":   "notepad.exe",
            "explorer":  "explorer.exe",
            "excel":     r"C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE",
            "word":      r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE",
            "vscode":    r"C:\Users\ugopl\AppData\Local\Programs\Microsoft VS Code\Code.exe",
            "github":    "https://github.com",
            "terminal":  "cmd.exe",
            "powershell":"powershell.exe",
        }

        # Cerca nell'APP_MAP
        for key, val in APP_MAP.items():
            if key in app_lower:
                if val.startswith("http"):
                    return self.open_url(val)
                try:
                    os.startfile(val)
                    time.sleep(2)
                    return f"✅ Aperto: {app_name}"
                except Exception:
                    pass  # prova via Win+R

        # Fallback: Win+R → digita il nome
        pyautogui.hotkey("win", "r")
        time.sleep(0.8)
        pyautogui.write(app_name, interval=0.05)
        pyautogui.press("enter")
        time.sleep(2)
        return f"✅ Aperto via Win+R: {app_name}"

    def open_url(self, url: str) -> str:
        """Apre URL nel browser di default."""
        import webbrowser
        webbrowser.open(url)
        time.sleep(2.5)
        return f"✅ Browser aperto: {url}"

    # ════════════════════════════════════════════════════════════
    # AZIONI UMANE (movimenti naturali, non robotici)
    # ════════════════════════════════════════════════════════════

    def _human_click(self, x: int, y: int, button="left", double=False):
        """Click umano: curva ease + piccolo jitter."""
        # Piccolo offset random intorno al target (±3px) – come un umano
        jx = x + random.randint(-3, 3)
        jy = y + random.randint(-3, 3)
        # Movimento con curva ease (non lineare)
        dur = random.uniform(0.15, 0.35)
        pyautogui.moveTo(jx, jy, duration=dur, tween=pyautogui.easeInOutQuad)
        time.sleep(random.uniform(0.05, 0.12))
        if double:
            pyautogui.doubleClick(button=button)
        else:
            pyautogui.click(button=button)

    def _human_type(self, text: str):
        """Typing umano: velocità variabile, piccole pause."""
        for char in text:
            pyautogui.write(char, interval=0)
            # Pausa variabile tra caratteri (simula velocità di scrittura umana)
            time.sleep(random.uniform(0.03, 0.12))
        time.sleep(0.1)

    def _human_scroll(self, direction: str, amount: int):
        amt = amount if direction == "up" else -amount
        for _ in range(abs(amount)):
            pyautogui.scroll(1 if amt > 0 else -1)
            time.sleep(random.uniform(0.05, 0.15))

    # ════════════════════════════════════════════════════════════
    # EXECUTOR  – traduce decision JSON → azione pyautogui
    # ════════════════════════════════════════════════════════════

    def _execute(self, decision: dict) -> bool:
        action = decision.get("action", "")
        try:
            if action == "click":
                x, y = int(decision.get("x", 0)), int(decision.get("y", 0))
                if x > 0 and y > 0:
                    self._human_click(x, y)
                    print(f"  🖱️  click({x},{y})")
                    return True

            elif action == "double_click":
                x, y = int(decision.get("x", 0)), int(decision.get("y", 0))
                self._human_click(x, y, double=True)
                print(f"  🖱️  double_click({x},{y})")
                return True

            elif action == "right_click":
                x, y = int(decision.get("x", 0)), int(decision.get("y", 0))
                self._human_click(x, y, button="right")
                print(f"  🖱️  right_click({x},{y})")
                return True

            elif action == "type":
                text = decision.get("text", "")
                if text:
                    self._human_type(text)
                    print(f"  ⌨️  type: {text[:40]}")
                    return True

            elif action == "hotkey":
                keys = decision.get("keys", "")
                if keys:
                    parts = [k.strip() for k in re.split(r"[+\s]+", keys) if k.strip()]
                    pyautogui.hotkey(*parts)
                    time.sleep(0.4)
                    print(f"  ⌨️  hotkey: {keys}")
                    return True

            elif action == "scroll":
                direction = decision.get("direction", "down")
                amount    = int(decision.get("amount", 3))
                self._human_scroll(direction, amount)
                print(f"  🖱️  scroll {direction} x{amount}")
                return True

            elif action == "open_app":
                app = decision.get("app", "")
                result = self.open_app(app)
                print(f"  🚀 {result}")
                return True

            elif action == "open_url":
                url = decision.get("url", "")
                result = self.open_url(url)
                print(f"  🌐 {result}")
                return True

            elif action == "wait":
                secs = float(decision.get("amount", 2))
                print(f"  ⏳ attendo {secs}s...")
                time.sleep(secs)
                return True

            else:
                print(f"  ❓ azione sconosciuta: {action}")
                return False

        except Exception as e:
            log.warning("Execute errore [%s]: %s", action, str(e)[:80])
            return False

    # ════════════════════════════════════════════════════════════
    # VISION  – Gemini vede lo screenshot
    # ════════════════════════════════════════════════════════════

    def _ask_vision(self, prompt: str, img_bytes: bytes):
        """Manda screenshot a Gemini Vision, ritorna dict o str."""
        # Prova KEY1, KEY2, KEY3
        for env in ("GOOGLE_API_KEY", "GOOGLE_API_KEY_2", "GOOGLE_API_KEY_3"):
            key = os.environ.get(env, "")
            if not key:
                continue
            try:
                import google.generativeai as genai
                genai.configure(api_key=key)
                model = genai.GenerativeModel("gemini-2.5-flash")
                img_part = {"mime_type": "image/png", "data": img_bytes}
                resp = model.generate_content([prompt, img_part])
                try:
                    text = resp.text.strip()
                except Exception:
                    continue
                if not text:
                    continue

                # Prova a parsare come JSON
                try:
                    # Estrai JSON dal testo (Gemini a volte aggiunge backtick)
                    m = re.search(r'\{.*\}', text, re.DOTALL)
                    if m:
                        return json.loads(m.group())
                except Exception:
                    pass
                return text  # Ritorna testo grezzo (per read_screen)

            except Exception as e:
                err = str(e)
                if "429" in err or "RESOURCE_EXHAUSTED" in err:
                    continue  # prova chiave successiva
                log.warning("Vision errore [%s]: %s", env, err[:80])

        # Fallback: Gemini via genai nuovo SDK
        try:
            from google import genai as genai_new
            key = os.environ.get("GOOGLE_API_KEY", "")
            client = genai_new.Client(api_key=key)
            img_obj = Image.open(io.BytesIO(img_bytes))
            resp = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[prompt, img_obj])
            text = resp.text.strip()
            m = re.search(r'\{.*\}', text, re.DOTALL)
            if m:
                return json.loads(m.group())
            return text
        except Exception:
            pass

        return None

    # ════════════════════════════════════════════════════════════
    # SCREENSHOT
    # ════════════════════════════════════════════════════════════

    def _screenshot(self, label: str = ""):
        """Prende screenshot e ritorna (path, bytes_png)."""
        ts   = datetime.now().strftime("%H%M%S")
        name = f"cu_{ts}_{label}.png"
        path = SCREENSHOT_DIR / name

        img = ImageGrab.grab()  # PIL ImageGrab – più affidabile di pyautogui su Windows
        img.save(str(path), format="PNG")

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return path, buf.getvalue()


class ComputerUseTool:
    """Wrapper per ToolRegistry – espone i tool all'agent."""

    def __init__(self, config):
        self.config = config
        self._cu    = None

    def _get(self) -> ComputerUse:
        if not self._cu:
            self._cu = ComputerUse(self.config)
        return self._cu

    # ── Tool principali ──────────────────────────────────────────

    def screen_do(self, task: str) -> str:
        """
        Esegui qualsiasi task usando il computer come un umano.
        DUST vede lo schermo, muove il mouse, clicca, digita.
        Usa questo per tutto ciò che richiede un'interfaccia grafica.

        Esempi:
          screen_do("crea una repo chiamata 'test' su github.com")
          screen_do("apri chrome e vai su google.com")
          screen_do("cerca 'python tutorial' su youtube")
          screen_do("apri notepad e scrivi 'ciao mondo'")
        """
        return self._get().do(task)

    def screen_read(self) -> str:
        """Descrivi cosa è visibile sullo schermo in questo momento."""
        result = self._get().read_screen()
        if isinstance(result, str):
            return result
        return json.dumps(result, ensure_ascii=False, indent=2)

    def screen_click(self, target: str) -> str:
        """Clicca un elemento sullo schermo descritto a parole.
        Es: screen_click("pulsante New repository") """
        return self._get().click(target)

    def screen_type(self, text: str) -> str:
        """Digita del testo sulla tastiera (va sull'elemento attivo)."""
        return self._get().type_text(text)

    def screen_hotkey(self, keys: str) -> str:
        """Premi una combinazione di tasti. Es: 'ctrl+c', 'win+r', 'alt+tab'"""
        return self._get().hotkey(keys)

    def screen_scroll(self, direction: str = "down", amount: str = "3") -> str:
        """Scrolla la pagina. direction: up/down, amount: righe."""
        return self._get().scroll(direction, int(amount))

    def app_open(self, name: str) -> str:
        """Apri un'applicazione Windows. Es: 'chrome', 'notepad', 'explorer'"""
        return self._get().open_app(name)

    def browser_go(self, url: str) -> str:
        """Apri un URL nel browser di default."""
        return self._get().open_url(url)

    def browser_do(self, task: str) -> str:
        """
        Esegui un'operazione nel browser corrente.
        DUST vede la pagina e interagisce come un umano.
        Es: browser_do("crea repo 'test' pubblica su github.com")
        """
        # Apri il browser prima, poi esegui il task
        cu = self._get()
        result = cu.do(f"Nel browser: {task}")
        return result
