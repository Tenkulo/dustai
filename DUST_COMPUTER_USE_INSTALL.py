"""
DUST AI – COMPUTER USE INSTALL v1.0
=====================================
Dopo questo install, DUST vede lo schermo e usa mouse+tastiera
come un umano, su qualsiasi applicazione Windows.

ARCHITETTURA:
  screenshot (PIL) → Gemini Vision (gratis) → azione pyautogui
  Loop: guarda → pensa → agisce → guarda ancora → ...

COME FUNZIONA:
  1. DUST prende screenshot dello schermo
  2. Manda l'immagine a Gemini Vision con "cosa devo fare per X?"
  3. Gemini risponde con JSON: { action, target, x, y, text }
  4. DUST esegue: click(x,y) / type(text) / hotkey / scroll
  5. Ricomincia dal punto 1 finché il task è completato

TOOL ESPOSTI:
  screen_do(task)           ← FA TUTTO: dai un task, lo esegue
  screen_read()             ← legge lo schermo corrente
  screen_click(target)      ← clicca su un elemento descritto
  screen_type(text)         ← digita testo
  screen_hotkey(keys)       ← es. "ctrl+c", "win+r"
  screen_scroll(direction)  ← up/down
  app_open(name)            ← apre un'app (browser, notepad, excel...)
  browser_go(url)           ← apre URL nel browser di default
  browser_do(task)          ← es. "crea repo su github.com"

Esegui: python A:\\dustai\\DUST_COMPUTER_USE_INSTALL.py
"""
import ast, shutil, time, subprocess, sys
from pathlib import Path
from datetime import datetime

BASE  = Path(r"A:\dustai")
SRC   = BASE / "src"
TOOLS = SRC / "tools"
BAK   = Path(r"A:\dustai_stuff\patches")
BAK.mkdir(parents=True, exist_ok=True)

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
print("DUST AI – COMPUTER USE INSTALL v1.0")
print("=" * 60)

# ══════════════════════════════════════════════════════════════
# 1. src/tools/computer_use.py  – IL CUORE
# ══════════════════════════════════════════════════════════════
print("\n[1/4] computer_use.py")

write(TOOLS / "computer_use.py", r'''"""
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
''', "computer_use.py")

# ══════════════════════════════════════════════════════════════
# 2. Patcha registry.py – aggiungi ComputerUseTool
# ══════════════════════════════════════════════════════════════
print("\n[2/4] Patching registry.py")

REGISTRY = TOOLS / "registry.py"
if REGISTRY.exists():
    src = REGISTRY.read_text(encoding="utf-8")
    bak(REGISTRY)
    changed = False

    # Import
    if "ComputerUseTool" not in src:
        OLD_IMP = "from .code_runner import CodeRunnerTool"
        NEW_IMP = (OLD_IMP + "\n"
                   "try:\n"
                   "    from .computer_use import ComputerUseTool as _CU\n"
                   "    _CU_OK = True\n"
                   "except Exception as _e:\n"
                   "    _CU_OK = False; _CU = None\n"
                   "    import logging; logging.getLogger('Registry').warning('ComputerUse N/D: %s', str(_e)[:60])")
        if OLD_IMP in src:
            src = src.replace(OLD_IMP, NEW_IMP, 1); changed = True

    # Getter lazy
    if "_get_computer_use" not in src:
        GETTER = '''
    def _get_computer_use(self):
        """Lazy init ComputerUseTool."""
        if not hasattr(self, "_cu_inst"):
            self._cu_inst = _CU(self.config) if _CU_OK else None
        return self._cu_inst

'''
        # Inserisci prima di execute()
        if "    def execute(" in src:
            src = src.replace("    def execute(", GETTER + "    def execute(", 1)
            changed = True

    # Lambda nel dispatch
    if "'screen_do'" not in src:
        CU_LAMBDAS = (
            "            # ─── Computer Use (mouse+tastiera su qualsiasi app) ─────────\n"
            "            'screen_do':     lambda p: (self._get_computer_use().screen_do(**self._safe_params(p))     if self._get_computer_use() else 'ComputerUse N/D'),\n"
            "            'screen_read':   lambda p: (self._get_computer_use().screen_read()                         if self._get_computer_use() else 'N/D'),\n"
            "            'screen_click':  lambda p: (self._get_computer_use().screen_click(**self._safe_params(p))  if self._get_computer_use() else 'N/D'),\n"
            "            'screen_type':   lambda p: (self._get_computer_use().screen_type(**self._safe_params(p))   if self._get_computer_use() else 'N/D'),\n"
            "            'screen_hotkey': lambda p: (self._get_computer_use().screen_hotkey(**self._safe_params(p)) if self._get_computer_use() else 'N/D'),\n"
            "            'screen_scroll': lambda p: (self._get_computer_use().screen_scroll(**self._safe_params(p)) if self._get_computer_use() else 'N/D'),\n"
            "            'app_open':      lambda p: (self._get_computer_use().app_open(**self._safe_params(p))       if self._get_computer_use() else 'N/D'),\n"
            "            'browser_go':    lambda p: (self._get_computer_use().browser_go(**self._safe_params(p))     if self._get_computer_use() else 'N/D'),\n"
            "            'browser_do':    lambda p: (self._get_computer_use().browser_do(**self._safe_params(p))     if self._get_computer_use() else 'N/D'),\n"
        )
        # Inserisci dopo sys_exec o all'inizio del dict
        for anchor in ("'sys_exec'", "'file_read'", "self._tools = {"):
            if anchor in src:
                idx      = src.find(anchor)
                end_line = src.find("\n", idx) + 1
                src      = src[:end_line] + CU_LAMBDAS + src[end_line:]
                changed  = True
                break

    if changed:
        try:
            ast.parse(src)
            REGISTRY.write_text(src, encoding="utf-8")
            print("  ✅ registry.py aggiornato")
        except SyntaxError as e:
            print(f"  ❌ Sintassi: {e}")
    else:
        print("  ⏭️  registry.py (già aggiornato)")

# ══════════════════════════════════════════════════════════════
# 3. Patcha agent.py – system prompt aggiornato con computer use
# ══════════════════════════════════════════════════════════════
print("\n[3/4] Patching agent.py – system prompt")

AGENT = SRC / "agent.py"
if AGENT.exists():
    src = AGENT.read_text(encoding="utf-8")
    bak(AGENT)

    NEW_SYSTEM = r'''SYSTEM_PROMPT = """Sei DUST AI – un assistente AI che controlla un computer Windows.

## CAPACITÀ PRINCIPALI

### 🖥️ COMPUTER USE – Usi mouse e tastiera come un umano
Puoi vedere lo schermo e interagire con QUALSIASI applicazione:
- Browser (Chrome, Edge, Firefox) → GitHub, Google, YouTube, Gmail, ecc.
- Applicazioni Windows → Notepad, Explorer, Office, VS Code, ecc.
- Qualsiasi interfaccia grafica

**Quando usare il computer use:**
- Operazioni su siti web (GitHub, Google Drive, LinkedIn, ecc.)
- Aprire e usare applicazioni
- Qualsiasi cosa che un umano farebbe cliccando sullo schermo

### 🔧 TOOL PRINCIPALI

**Computer & Browser:**
- `screen_do(task)` ← **USA QUESTO** per tutto ciò che richiede un browser o GUI
- `screen_read()` ← vedi cosa c'è sullo schermo ora
- `screen_click(target)` ← clicca un elemento
- `screen_type(text)` ← digita testo
- `app_open(name)` ← apre un'app
- `browser_go(url)` ← apre URL nel browser

**File e sistema:**
- `sys_exec(cmd)` ← comandi shell (per operazioni locali veloci)
- `file_read/write/list` ← gestione file locali

**AI e ricerca:**
- `ai_ask(prompt)` ← chiedi a un'AI
- `web_search(query)` ← cerca sul web

## REGOLE DI COMPORTAMENTO

1. **Chiedi sempre le info mancanti** prima di agire
   - "Crea una repo" → chiedi: nome, pubblica/privata, descrizione?

2. **Preferisci il computer use** per operazioni su browser e GUI
   - Non usare API o CLI se puoi fare la stessa cosa via browser

3. **Sii conversazionale** – rispondi come farebbe un assistente umano

4. **Conferma azioni importanti** prima di eseguirle
   - Cancellazioni, pubblicazioni, invii email, ecc.

5. **Rispondi in italiano**

6. **Adatta la strategia** se qualcosa non funziona:
   - GUI non risponde → prova keyboard shortcut
   - Elemento non trovato → scrolla, cerca altrove
   - App non aperta → aprila prima

## ESEMPIO DI INTERAZIONE CORRETTA

Utente: "crea una repo su github"
DUST: "Come vuoi chiamare la repo? Vuoi che sia pubblica o privata?"
Utente: "test-progetto, pubblica"
DUST: [screen_do("vai su github.com, crea nuova repo chiamata 'test-progetto' pubblica")]
      "✅ Repo creata! Ecco il link: https://github.com/..."
"""'''

    import re
    pattern = r'SYSTEM_PROMPT\s*=\s*""".*?"""'
    if re.search(pattern, src, re.DOTALL):
        src = re.sub(pattern, NEW_SYSTEM, src, flags=re.DOTALL)
        print("  ✅ SYSTEM_PROMPT aggiornato")
    else:
        pattern2 = r"SYSTEM_PROMPT\s*=\s*'''.*?'''"
        if re.search(pattern2, src, re.DOTALL):
            src = re.sub(pattern2, NEW_SYSTEM, src, flags=re.DOTALL)
            print("  ✅ SYSTEM_PROMPT (variante ''') aggiornato")
        else:
            src = NEW_SYSTEM + "\n\n" + src
            print("  ⚠️ SYSTEM_PROMPT aggiunto (pattern non trovato)")

    try:
        ast.parse(src)
        AGENT.write_text(src, encoding="utf-8")
        print("  ✅ agent.py salvato")
    except SyntaxError as e:
        print(f"  ❌ Sintassi: {e}")

# ══════════════════════════════════════════════════════════════
# 4. pip install + commit
# ══════════════════════════════════════════════════════════════
print("\n[4/4] pip + commit")

for pkg in ["pillow", "pyautogui", "pygetwindow"]:
    r = subprocess.run([sys.executable, "-m", "pip", "install", pkg, "--quiet"],
                       capture_output=True, text=True, timeout=60)
    print(f"  {'✅' if r.returncode==0 else '⚠️ '} pip {pkg}")

ts = datetime.now().strftime("%Y-%m-%d %H:%M")
for cmd in [
    ["git", "add", "-A"],
    ["git", "commit", "-m", f"feat: DUST ComputerUse – screenshot+vision+mouse+keyboard {ts}"],
    ["git", "push", "origin", "master"],
]:
    r = subprocess.run(cmd, cwd=str(BASE), capture_output=True,
                       text=True, encoding="utf-8")
    out = r.stderr or r.stdout or ""
    label = " ".join(cmd[:2])
    ok = r.returncode == 0 or "nothing" in out or "up to date" in out
    print(f"  {'✅' if ok else '⚠️ '} {label}")

print("""
╔══════════════════════════════════════════════════════════════════╗
║  DUST AI – COMPUTER USE INSTALLATO                             ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  COME FUNZIONA:                                                  ║
║                                                                  ║
║   Tu: "crea una repo su github"                                 ║
║   DUST: "Come si chiama? Pubblica o privata?"                   ║
║   Tu: "test-repo, pubblica"                                     ║
║   DUST: 👁️ guarda lo schermo                                    ║
║          🖱️ apre il browser                                      ║
║          🖱️ va su github.com                                     ║
║          🖱️ clicca "New repository"                             ║
║          ⌨️ scrive "test-repo"                                   ║
║          🖱️ seleziona "Public"                                  ║
║          🖱️ clicca "Create repository"                          ║
║          ✅ "Repo creata! https://github.com/..."               ║
║                                                                  ║
║  LOOP INTERNO:                                                   ║
║  screenshot → Gemini Vision (gratis) → pyautogui → screenshot   ║
║  (ciclo fino a task completato, max 20 step)                    ║
║                                                                  ║
║  TOOL NELLA GUI DUST:                                           ║
║  screen_do task="crea repo 'test' su github"                   ║
║  screen_read                                                    ║
║  app_open name="chrome"                                         ║
║  browser_go url="https://github.com"                           ║
║  screen_click target="pulsante New repository"                 ║
║  screen_type text="test-repo"                                  ║
║  screen_hotkey keys="ctrl+t"                                   ║
╚══════════════════════════════════════════════════════════════════╝
""")
