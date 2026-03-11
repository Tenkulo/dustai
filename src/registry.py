"""
DUST AI – Tool Registry v2.0
Fix critico: ogni tool viene chiamato davvero.
Niente simulazioni, niente output narrativo.

Novità:
- Wrapper di sicurezza su ogni chiamata (timeout, catch, logging)
- Tool names normalizzati (file_ops → file_read, file_write, ecc.)
- Errori strutturati con dettaglio per SelfHeal
- Vision tool (screenshot + Gemini analysis)
"""
import logging
import time
from typing import Any

log = logging.getLogger("ToolRegistry")


class ToolRegistry:
    def __init__(self, config):
        self.config   = config
        self.log      = logging.getLogger("ToolRegistry")
        self._tools   = {}
        self._failed  = {}   # tool → error (per debug)
        self._register_all()

    def _register_all(self):
        """Registra tutti i tool. Ogni tool che non si carica viene segnato come non disponibile."""
        from pathlib import Path
        src_dir = Path(__file__).parent

        registrations = {
            # sys_exec
            "sys_exec": ("sys_exec", "SysExecTool"),
            # file ops — tutte puntano alla stessa istanza FileOpsTool
            "file_read":   ("file_ops", "FileOpsTool"),
            "file_write":  ("file_ops", "FileOpsTool"),
            "file_list":   ("file_ops", "FileOpsTool"),
            "file_delete": ("file_ops", "FileOpsTool"),
            "file_exists": ("file_ops", "FileOpsTool"),
            "file_copy":   ("file_ops", "FileOpsTool"),
            "file_move":   ("file_ops", "FileOpsTool"),
            # browser
            "browser_open":       ("browser", "BrowserTool"),
            "browser_click":      ("browser", "BrowserTool"),
            "browser_type":       ("browser", "BrowserTool"),
            "browser_screenshot": ("browser", "BrowserTool"),
            "browser_get_text":   ("browser", "BrowserTool"),
            # input
            "mouse_move":        ("input_control", "InputControlTool"),
            "mouse_click":       ("input_control", "InputControlTool"),
            "mouse_double_click":("input_control", "InputControlTool"),
            "keyboard_type":     ("input_control", "InputControlTool"),
            "keyboard_hotkey":   ("input_control", "InputControlTool"),
            "screenshot":        ("input_control", "InputControlTool"),
            # windows apps
            "app_launch": ("windows_apps", "WindowsAppsTool"),
            "app_focus":  ("windows_apps", "WindowsAppsTool"),
            "app_list":   ("windows_apps", "WindowsAppsTool"),
            # search + code
            "web_search": ("web_search",  "WebSearchTool"),
            "code_run":   ("code_runner", "CodeRunnerTool"),
            # vision
            "vision_analyze": ("vision", "VisionTool"),
        }

        instances = {}
        for tool_name, (module_name, class_name) in registrations.items():
            if class_name not in instances:
                instances[class_name] = self._load_tool(module_name, class_name)
            self._tools[tool_name] = instances[class_name]
            if instances[class_name] is None:
                self._failed[tool_name] = "Tool " + class_name + " non caricato"

        available = [k for k, v in self._tools.items() if v is not None]
        failed    = [k for k, v in self._tools.items() if v is None]
        self.log.info(str(len(available)) + " tool disponibili, " + str(len(failed)) + " non disponibili")
        if failed:
            self.log.warning("Tool non disponibili: " + str(failed))

    def _load_tool(self, module_name: str, class_name: str):
        """Carica un tool class. Ritorna None se non disponibile."""
        try:
            import importlib
            module = importlib.import_module("." + module_name, package="src.tools")
            cls    = getattr(module, class_name)
            return cls(self.config)
        except Exception as e:
            self.log.warning("Tool non disponibile: " + class_name + " — " + str(e))
            return None

    def execute(self, tool_name: str, params: dict) -> Any:
        """
        Esegui un tool per nome.
        Chiama SEMPRE il metodo reale — niente simulazioni.
        """
        # Normalizza nome tool (accetta varianti)
        normalized = self._normalize_name(tool_name)

        tool = self._tools.get(normalized)
        if not tool:
            err = "❌ Tool '" + tool_name + "' non trovato"
            if tool_name in self._failed:
                err += ": " + self._failed[tool_name]
            return err

        # Cerca il metodo sul tool
        method = getattr(tool, normalized, None)
        if method is None:
            # Fallback: prova il nome originale
            method = getattr(tool, tool_name, None)
        if method is None:
            # Fallback: chiama execute(name, params)
            method = getattr(tool, "execute", None)
            if method:
                try:
                    return method(normalized, params)
                except Exception as e:
                    return "❌ Errore " + tool_name + ": " + str(e)
            return "❌ Metodo '" + normalized + "' non trovato in " + type(tool).__name__

        # Esegui con timeout di sicurezza
        try:
            timeout = params.pop("timeout", None) or self._default_timeout(normalized)
            return self._call_with_timeout(method, params, timeout)
        except Exception as e:
            self.log.error("Errore tool " + tool_name + ": " + str(e))
            return "❌ Errore " + tool_name + ": " + str(e)

    def _call_with_timeout(self, method, params: dict, timeout: int) -> Any:
        """Chiama il metodo con timeout usando threading."""
        import threading
        result_container = [None]
        error_container  = [None]

        def target():
            try:
                result_container[0] = method(**params)
            except Exception as e:
                error_container[0] = e

        t = threading.Thread(target=target, daemon=True)
        t.start()
        t.join(timeout=timeout)

        if t.is_alive():
            return "❌ Timeout (" + str(timeout) + "s) su " + method.__name__

        if error_container[0]:
            raise error_container[0]

        return result_container[0]

    def _normalize_name(self, name: str) -> str:
        """Normalizza varianti di nomi tool."""
        aliases = {
            "exec":          "sys_exec",
            "shell":         "sys_exec",
            "run_cmd":       "sys_exec",
            "read_file":     "file_read",
            "write_file":    "file_write",
            "list_files":    "file_list",
            "type":          "keyboard_type",
            "click":         "mouse_click",
            "search":        "web_search",
            "open_browser":  "browser_open",
            "launch":        "app_launch",
            "run_code":      "code_run",
            "run_python":    "code_run",
            "capture":       "screenshot",
            "vision":        "vision_analyze",
        }
        return aliases.get(name, name)

    def _default_timeout(self, tool_name: str) -> int:
        timeouts = {
            "sys_exec":    30,
            "browser_open": 30,
            "web_search":  20,
            "code_run":    60,
            "screenshot":   5,
        }
        return timeouts.get(tool_name, 15)

    def list_tools(self) -> list:
        return [k for k, v in self._tools.items() if v is not None]

    def get_tool_status(self) -> dict:
        return {
            "available": self.list_tools(),
            "failed":    list(self._failed.keys()),
        }
