"""
DUST AI – Tool: input_control
Controllo tastiera e mouse via PyAutoGUI.
Funziona con qualsiasi app Windows: Roblox Studio, browser, editor, ecc.
Installa: pip install pyautogui pillow
"""
import logging
import time


class InputControlTool:
    def __init__(self, config):
        self.config = config
        self.log = logging.getLogger("InputControlTool")
        self._available = self._check_availability()

    def _check_availability(self) -> bool:
        try:
            import pyautogui
            pyautogui.FAILSAFE = True   # Muovi mouse angolo top-left per stop emergenza
            pyautogui.PAUSE = 0.1       # Pausa tra azioni (sicurezza)
            return True
        except ImportError:
            self.log.warning("PyAutoGUI non installato. Esegui: pip install pyautogui pillow")
            return False

    def _pyautogui(self):
        import pyautogui
        return pyautogui

    def screenshot(self, save_path: str = None) -> str:
        """Scatta screenshot dello schermo intero."""
        if not self._available:
            return "❌ PyAutoGUI non disponibile."
        try:
            pag = self._pyautogui()
            img = pag.screenshot()

            if not save_path:
                screenshots_dir = self.config.get_workdir() / "screenshots"
                screenshots_dir.mkdir(exist_ok=True)
                save_path = str(screenshots_dir / f"screen_{int(time.time())}.png")

            img.save(save_path)
            return f"✅ Screenshot: {save_path} ({img.size[0]}x{img.size[1]})"
        except Exception as e:
            return f"❌ Errore screenshot: {e}"

    def mouse_move(self, x: int, y: int, duration: float = 0.3) -> str:
        """Sposta il mouse alle coordinate (x, y)."""
        if not self._available:
            return "❌ PyAutoGUI non disponibile."
        try:
            pag = self._pyautogui()
            pag.moveTo(x, y, duration=duration)
            return f"✅ Mouse spostato a ({x}, {y})"
        except Exception as e:
            return f"❌ Errore mouse_move: {e}"

    def mouse_click(self, x: int = None, y: int = None, button: str = "left", clicks: int = 1) -> str:
        """Clicca con il mouse. Se x,y non specificati, clicca sulla posizione corrente."""
        if not self._available:
            return "❌ PyAutoGUI non disponibile."
        try:
            pag = self._pyautogui()
            if x is not None and y is not None:
                pag.click(x, y, button=button, clicks=clicks)
                return f"✅ Click {button} su ({x}, {y})"
            else:
                pag.click(button=button, clicks=clicks)
                return f"✅ Click {button} sulla posizione corrente"
        except Exception as e:
            return f"❌ Errore mouse_click: {e}"

    def mouse_double_click(self, x: int, y: int) -> str:
        """Doppio click su coordinate."""
        return self.mouse_click(x, y, clicks=2)

    def keyboard_type(self, text: str, interval: float = 0.02) -> str:
        """Digita testo tramite tastiera (simula keypresses)."""
        if not self._available:
            return "❌ PyAutoGUI non disponibile."
        try:
            pag = self._pyautogui()
            pag.write(text, interval=interval)
            return f"✅ Digitato: {text[:50]}{'...' if len(text) > 50 else ''}"
        except Exception as e:
            # Fallback per caratteri speciali
            try:
                pag = self._pyautogui()
                pag.typewrite(text, interval=interval)
                return f"✅ Digitato (fallback): {text[:50]}"
            except Exception as e2:
                return f"❌ Errore keyboard_type: {e2}"

    def keyboard_hotkey(self, *keys: str) -> str:
        """
        Premi una combinazione di tasti.
        Esempi: keyboard_hotkey("ctrl", "c") → Copia
                keyboard_hotkey("win", "d") → Mostra desktop
                keyboard_hotkey("alt", "f4") → Chiudi finestra
        """
        if not self._available:
            return "❌ PyAutoGUI non disponibile."
        try:
            pag = self._pyautogui()
            pag.hotkey(*keys)
            return f"✅ Hotkey: {' + '.join(keys)}"
        except Exception as e:
            return f"❌ Errore keyboard_hotkey: {e}"

    def keyboard_press(self, key: str) -> str:
        """Premi un singolo tasto. Es: 'enter', 'esc', 'tab', 'f5'"""
        if not self._available:
            return "❌ PyAutoGUI non disponibile."
        try:
            pag = self._pyautogui()
            pag.press(key)
            return f"✅ Tasto premuto: {key}"
        except Exception as e:
            return f"❌ Errore keyboard_press: {e}"
