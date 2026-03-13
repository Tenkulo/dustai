"""Computer-use tools — screen_read usa google.genai (nuovo SDK)."""
import io
import json
import logging
import subprocess
import time
import webbrowser

logger = logging.getLogger("dust.computer_use")


def screen_read(region: list = None) -> dict:
    """Cattura screenshot e descrivilo con Gemini Vision."""
    try:
        import pyautogui
        from PIL import Image
        screenshot = pyautogui.screenshot(region=region)

        buf = io.BytesIO()
        screenshot.save(buf, format="PNG")
        image_bytes = buf.getvalue()

        from config import GEMINI_KEYS, GEMINI_MODEL
        from google import genai
        from google.genai import types

        for key in GEMINI_KEYS:
            try:
                client = genai.Client(api_key=key)
                resp   = client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=[
                        types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                        "Descrivi dettagliatamente questo screenshot: finestre aperte, "
                        "testo visibile, bottoni, icone, stato del sistema.",
                    ],
                )
                try:
                    return {"status": "ok", "description": resp.text}
                except Exception:
                    return {"status": "ok", "description": "Screenshot acquisito."}
            except Exception as exc:
                if "429" not in str(exc):
                    break
        return {"status": "ok", "description": "Screenshot acquisito (analisi non disponibile)."}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def screen_do(action: str, x: int = None, y: int = None, text: str = None,
              key: str = None, button: str = "left", clicks: int = 1,
              duration: float = 0.3, target: str = None) -> dict:
    """Esegui un'azione GUI: click|type|key|scroll|move|drag|screenshot."""
    try:
        import pyautogui
        pyautogui.FAILSAFE = True
        action = action.lower()

        if action == "click":
            if x is not None and y is not None:
                pyautogui.click(x, y, button=button, clicks=clicks)
            elif target:
                loc = pyautogui.locateCenterOnScreen(target, confidence=0.8)
                if loc:
                    pyautogui.click(loc)
                else:
                    return {"status": "error", "error": f"Target not found: {target}"}
            return {"status": "ok", "action": "click", "pos": [x, y]}

        elif action == "double_click":
            pyautogui.doubleClick(x or 0, y or 0)
            return {"status": "ok", "action": "double_click"}

        elif action in ("type", "write"):
            pyautogui.write(text or "", interval=0.04)
            return {"status": "ok", "action": "type"}

        elif action in ("key", "hotkey", "press"):
            if key:
                if "+" in key:
                    pyautogui.hotkey(*key.split("+"))
                else:
                    pyautogui.press(key)
            return {"status": "ok", "action": "key", "key": key}

        elif action == "scroll":
            pyautogui.scroll(clicks or 3, x=x, y=y)
            return {"status": "ok", "action": "scroll"}

        elif action == "move":
            pyautogui.moveTo(x or 0, y or 0, duration=duration)
            return {"status": "ok", "action": "move"}

        elif action == "drag":
            pyautogui.dragTo(x or 0, y or 0, duration=duration)
            return {"status": "ok", "action": "drag"}

        elif action == "screenshot":
            return screen_read()

        else:
            return {"status": "error", "error": f"Azione sconosciuta: {action}"}

    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def app_open(app_name: str, args: list = None) -> dict:
    """Apri un'applicazione Windows per nome o percorso .exe."""
    KNOWN = {
        "notepad": "notepad.exe", "explorer": "explorer.exe",
        "calc": "calc.exe", "calculator": "calc.exe",
        "chrome": "chrome.exe", "edge": "msedge.exe",
        "firefox": "firefox.exe", "cmd": "cmd.exe",
        "powershell": "powershell.exe", "vscode": "code.exe",
        "code": "code.exe", "paint": "mspaint.exe",
        "word": "winword.exe", "excel": "excel.exe",
    }
    try:
        exe = KNOWN.get(app_name.lower(), app_name)
        subprocess.Popen([exe] + (args or []), shell=True)
        time.sleep(0.8)
        return {"status": "ok", "app": app_name}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def browser_go(url: str) -> dict:
    """Apri un URL nel browser predefinito."""
    try:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        webbrowser.open(url)
        time.sleep(0.5)
        return {"status": "ok", "url": url}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}
