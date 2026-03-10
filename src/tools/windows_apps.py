"""
DUST AI – Tool: windows_apps
Lancia e controlla applicazioni Windows: Roblox Studio, browser, editor, ecc.
Usa subprocess + pywin32 per window focus.
"""
import subprocess
import platform
import logging
import time
import os


# Mappa app comuni → percorsi/comandi
APP_MAP = {
    "roblox_studio": [
        r"%LOCALAPPDATA%\Roblox\Versions\RobloxStudio.exe",
        "RobloxStudioBeta.exe",
    ],
    "notepad": ["notepad.exe"],
    "explorer": ["explorer.exe"],
    "chrome": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ],
    "edge": ["msedge.exe"],
    "firefox": [r"C:\Program Files\Mozilla Firefox\firefox.exe"],
    "vscode": [
        r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe",
        "code.exe",
    ],
    "powershell": ["powershell.exe"],
    "cmd": ["cmd.exe"],
    "taskmgr": ["taskmgr.exe"],
    "calc": ["calc.exe"],
    "paint": ["mspaint.exe"],
}


class WindowsAppsTool:
    def __init__(self, config):
        self.config = config
        self.log = logging.getLogger("WindowsAppsTool")
        self.is_windows = platform.system() == "Windows"
        self._win32_available = self._check_win32()

    def _check_win32(self) -> bool:
        try:
            import win32gui
            import win32con
            return True
        except ImportError:
            self.log.warning("pywin32 non installato. app_focus non disponibile. pip install pywin32")
            return False

    def app_launch(self, app: str, args: str = "", wait: bool = False) -> str:
        """
        Lancia un'applicazione Windows.
        
        Parametri:
        - app: nome dall'APP_MAP ('roblox_studio', 'chrome', ecc.) 
               oppure percorso assoluto al .exe
               oppure nome eseguibile
        - args: argomenti da passare all'app
        - wait: attendi che l'app si chiuda
        """
        if not self.is_windows:
            return "⚠️ app_launch è disponibile solo su Windows"

        # Risolvi l'app
        exe_path = self._resolve_app(app)
        if not exe_path:
            return f"❌ App non trovata: {app}"

        try:
            cmd = [exe_path]
            if args:
                cmd.extend(args.split())

            if wait:
                result = subprocess.run(cmd, capture_output=True, text=True)
                return f"✅ App terminata: {app} (exit: {result.returncode})"
            else:
                subprocess.Popen(cmd)
                time.sleep(1)  # Dai tempo all'app di avviarsi
                return f"✅ App lanciata: {app} ({exe_path})"
        except Exception as e:
            return f"❌ Errore lancio {app}: {e}"

    def app_focus(self, title_contains: str) -> str:
        """
        Porta in primo piano una finestra Windows che contiene il testo nel titolo.
        Esempio: app_focus("Roblox Studio") porta in focus Roblox Studio.
        """
        if not self.is_windows:
            return "⚠️ Disponibile solo su Windows"

        if not self._win32_available:
            return "❌ pywin32 non installato. pip install pywin32"

        try:
            import win32gui
            import win32con

            found_windows = []

            def enum_callback(hwnd, results):
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    if title_contains.lower() in title.lower():
                        results.append((hwnd, title))

            win32gui.EnumWindows(enum_callback, found_windows)

            if not found_windows:
                return f"❌ Nessuna finestra trovata con titolo contenente: '{title_contains}'"

            hwnd, title = found_windows[0]
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(0.3)
            return f"✅ Focus su: '{title}'"
        except Exception as e:
            return f"❌ Errore app_focus: {e}"

    def app_list(self) -> str:
        """Lista le finestre aperte su Windows."""
        if not self.is_windows:
            return "⚠️ Disponibile solo su Windows"

        try:
            result = subprocess.run(
                ["tasklist", "/fo", "csv", "/nh"],
                capture_output=True, text=True, timeout=10
            )
            lines = result.stdout.strip().split("\n")
            apps = []
            for line in lines[:30]:  # Prime 30 app
                parts = line.strip('"').split('","')
                if parts:
                    apps.append(parts[0])

            return "App in esecuzione:\n" + "\n".join(f"• {a}" for a in apps)
        except Exception as e:
            return f"❌ Errore app_list: {e}"

    def _resolve_app(self, app: str) -> str:
        """Risolve il nome app nel percorso eseguibile."""
        # Percorso assoluto diretto
        if os.path.isabs(app) or app.endswith(".exe"):
            expanded = os.path.expandvars(app)
            if os.path.exists(expanded):
                return expanded
            return app  # Prova comunque (potrebbe essere nel PATH)

        # Cerca nella mappa
        app_lower = app.lower().replace(" ", "_")
        candidates = APP_MAP.get(app_lower, [app])

        for candidate in candidates:
            expanded = os.path.expandvars(candidate)
            if os.path.exists(expanded):
                return expanded
            # Prova come comando nel PATH
            try:
                result = subprocess.run(
                    ["where", candidate],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    return result.stdout.strip().split("\n")[0]
            except Exception:
                pass

        return candidates[0] if candidates else None
