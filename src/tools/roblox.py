"""
DUST AI – Tool: roblox
Controllo Roblox Studio: lancia, apre place, esegue script, screenshot.
"""
import subprocess
import logging
import time
import os
from pathlib import Path


class RobloxTool:
    STUDIO_PATHS = [
        r"%LOCALAPPDATA%\Roblox\Versions",
        r"%PROGRAMFILES%\Roblox\Versions",
    ]

    def __init__(self, config):
        self.config = config
        self.log = logging.getLogger("RobloxTool")
        self._studio_exe = self._find_studio()

    def _find_studio(self) -> str:
        """Trova il percorso di RobloxStudio.exe."""
        for base in self.STUDIO_PATHS:
            base_expanded = Path(os.path.expandvars(base))
            if base_expanded.exists():
                for item in base_expanded.iterdir():
                    if item.is_dir():
                        exe = item / "RobloxStudioBeta.exe"
                        if exe.exists():
                            return str(exe)
        return "RobloxStudioBeta.exe"  # Fallback PATH

    def roblox_launch(self, place_path: str = None) -> str:
        """Lancia Roblox Studio, opzionalmente aprendo un place."""
        try:
            cmd = [self._studio_exe]
            if place_path:
                cmd.append(place_path)
            subprocess.Popen(cmd)
            time.sleep(3)
            return f"✅ Roblox Studio avviato{f' con: {place_path}' if place_path else ''}"
        except Exception as e:
            return f"❌ Errore avvio Roblox Studio: {e}\nPercorso cercato: {self._studio_exe}"

    def roblox_open_place(self, path: str) -> str:
        """Apre un file .rbxl o .rbxlx in Roblox Studio."""
        p = Path(os.path.expandvars(path))
        if not p.exists():
            return f"❌ File non trovato: {path}"
        return self.roblox_launch(str(p))

    def roblox_screenshot(self, save_path: str = None) -> str:
        """Scatta uno screenshot di Roblox Studio."""
        try:
            import pyautogui
            if not save_path:
                screenshots_dir = self.config.get_workdir() / "screenshots"
                screenshots_dir.mkdir(exist_ok=True)
                save_path = str(screenshots_dir / f"roblox_{int(time.time())}.png")
            img = pyautogui.screenshot()
            img.save(save_path)
            return f"✅ Screenshot Roblox: {save_path}"
        except Exception as e:
            return f"❌ Errore screenshot: {e}"

    def roblox_run_script(self, script: str) -> str:
        """
        Esegue uno script Luau in Roblox Studio tramite tastiera.
        Richiede che Studio sia aperto e in primo piano.
        """
        try:
            import pyautogui
            # Apri Command Bar in Studio (Alt+F2 o View > Command Bar)
            pyautogui.hotkey("alt", "f2")
            time.sleep(0.5)
            pyautogui.write(script, interval=0.02)
            pyautogui.press("enter")
            time.sleep(0.5)
            return f"✅ Script eseguito in Roblox Studio"
        except Exception as e:
            return f"❌ Errore esecuzione script: {e}"
