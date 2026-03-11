"""
DUST AI – WindowsAppsTool v2.0
Avvio, focus e lista applicazioni Windows.
"""
import logging
import platform
import subprocess
from pathlib import Path

log = logging.getLogger("WindowsAppsTool")
_IS_WINDOWS = platform.system() == "Windows"
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


class WindowsAppsTool:
    def __init__(self, config):
        self.config = config

    def app_launch(self, app: str) -> str:
        if not app:
            return "❌ Nome app vuoto"
        try:
            if _IS_WINDOWS:
                subprocess.Popen(
                    ["start", app], shell=True,
                    creationflags=_CREATE_NO_WINDOW,
                )
            else:
                subprocess.Popen([app])
            return "✅ Avviato: " + app
        except Exception as e:
            return "❌ app_launch: " + str(e)

    def app_focus(self, app: str) -> str:
        if not _IS_WINDOWS:
            return "❌ app_focus solo su Windows"
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd   = user32.FindWindowW(None, app)
            if hwnd:
                user32.SetForegroundWindow(hwnd)
                return "✅ Focus su: " + app
            return "❌ Finestra non trovata: " + app
        except Exception as e:
            return "❌ app_focus: " + str(e)

    def app_list(self) -> str:
        if _IS_WINDOWS:
            result = subprocess.run(
                "tasklist /FO CSV /NH", shell=True, capture_output=True, text=True,
                creationflags=_CREATE_NO_WINDOW,
            )
            lines = result.stdout.strip().splitlines()[:30]
            return "\n".join(l.split(",")[0].strip('"') for l in lines)
        else:
            result = subprocess.run(["ps", "-e", "-o", "comm="],
                                    capture_output=True, text=True)
            return result.stdout[:1000]
