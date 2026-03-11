"""
DUST AI – InputControlTool v2.0
Mouse, tastiera, hotkey tramite pyautogui.
"""
import logging
import time
from typing import Optional

log = logging.getLogger("InputControlTool")


class InputControlTool:
    def __init__(self, config):
        self.config = config
        self._pg    = None
        self._setup()

    def _setup(self):
        try:
            import pyautogui
            pyautogui.FAILSAFE  = True   # muovi mouse angolo top-left per stop di emergenza
            pyautogui.PAUSE     = 0.05
            self._pg = pyautogui
        except ImportError:
            log.warning("pyautogui non installato — InputControl non disponibile")

    def _check(self) -> Optional[str]:
        if not self._pg:
            return "❌ pyautogui non installato: pip install pyautogui"
        return None

    def mouse_move(self, x: int, y: int, duration: float = 0.2) -> str:
        err = self._check()
        if err:
            return err
        try:
            self._pg.moveTo(int(x), int(y), duration=duration)
            return "✅ Mouse mosso a (" + str(x) + ", " + str(y) + ")"
        except Exception as e:
            return "❌ mouse_move: " + str(e)

    def mouse_click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> str:
        err = self._check()
        if err:
            return err
        try:
            self._pg.click(int(x), int(y), button=button, clicks=clicks)
            return "✅ Click (" + str(x) + ", " + str(y) + ")"
        except Exception as e:
            return "❌ mouse_click: " + str(e)

    def mouse_double_click(self, x: int, y: int) -> str:
        return self.mouse_click(x, y, clicks=2)

    def keyboard_type(self, text: str, interval: float = 0.02) -> str:
        err = self._check()
        if err:
            return err
        try:
            self._pg.typewrite(text, interval=interval)
            return "✅ Digitato: " + text[:50]
        except Exception as e:
            # Fallback con pyperclip per testo con caratteri speciali
            try:
                import pyperclip
                pyperclip.copy(text)
                self._pg.hotkey("ctrl", "v")
                return "✅ Digitato (clipboard): " + text[:50]
            except Exception:
                return "❌ keyboard_type: " + str(e)

    def keyboard_hotkey(self, keys: str) -> str:
        """
        Premi combinazione tasti.
        keys: stringa separata da '+' es. "ctrl+s", "alt+f4", "win+d"
        """
        err = self._check()
        if err:
            return err
        try:
            parts = [k.strip().lower() for k in keys.split("+")]
            self._pg.hotkey(*parts)
            return "✅ Hotkey: " + keys
        except Exception as e:
            return "❌ keyboard_hotkey: " + str(e)

    def screenshot(self, region: str = "full") -> dict:
        """Cattura screenshot (delega a VisionTool se disponibile)."""
        try:
            from .vision import VisionTool
            vt = VisionTool(self.config)
            return vt.screenshot(region=region, save=True)
        except Exception as e:
            return {"error": "❌ screenshot: " + str(e)}
