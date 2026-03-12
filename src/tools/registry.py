"""
DUST AI – Tool Registry
Registra tutti i tool disponibili e gestisce l'esecuzione.
Aggiungere nuovi tool: crea file in tools/ e registralo qui.
"""
import logging
from typing import Any

from .sys_exec import SysExecTool
from .file_ops import FileOpsTool
from .browser import BrowserTool
from .input_control import InputControlTool
from .windows_apps import WindowsAppsTool
from .web_search import WebSearchTool
from .code_runner import CodeRunnerTool


class ToolRegistry:
    def __init__(self, config):
        self.config = config
        self.log = logging.getLogger("ToolRegistry")
        self._tools = {}
        self._register_all()

    def _register_all(self):
        """Registra tutti i tool disponibili."""
        tool_classes = {
            
            # Orchestra AI
            'ai_ask':     lambda p: (self._get_conductor_tool().ai_ask(**self._safe_params(p)) if self._get_conductor_tool() and self._safe_params(p).get('prompt') else ('N/D' if not self._get_conductor_tool() else 'Uso: ai_ask prompt="..." model=auto')),
            'ai_parallel':lambda p: (self._get_conductor_tool().ai_parallel(**self._safe_params(p)) if self._get_conductor_tool() and self._safe_params(p).get('prompt') else ('N/D' if not self._get_conductor_tool() else 'Uso: ai_parallel prompt="..." models="gemini,claude"')),
            'ai_status':  lambda p: (self._get_conductor_tool().ai_status() if self._get_conductor_tool() else 'N/D'),
            'ai_models':  lambda p: (self._get_conductor_tool().ai_models(**self._safe_params(p)) if self._get_conductor_tool() else 'N/D'),
            'git_sync':   lambda p: (self._get_git_sync_tool().git_sync(**self._safe_params(p)) if self._get_git_sync_tool() else 'N/D'),
            'git_commit': lambda p: (self._get_git_sync_tool().git_commit(**self._safe_params(p)) if self._get_git_sync_tool() and self._safe_params(p).get('message') else ('N/D' if not self._get_git_sync_tool() else 'Uso: git_commit message="..."')),
            'git_status': lambda p: (self._get_git_sync_tool().git_status() if self._get_git_sync_tool() else 'N/D'),
            'git_push':   lambda p: (self._get_git_sync_tool().git_push() if self._get_git_sync_tool() else 'N/D'),
            "sys_exec": SysExecTool,
            "file_read": FileOpsTool,
            "file_write": FileOpsTool,
            "file_list": FileOpsTool,
            "file_delete": FileOpsTool,
            "file_exists": FileOpsTool,
            "browser_open": BrowserTool,
            "browser_click": BrowserTool,
            "browser_type": BrowserTool,
            "browser_screenshot": BrowserTool,
            "browser_get_text": BrowserTool,
            "mouse_move": InputControlTool,
            "mouse_click": InputControlTool,
            "mouse_double_click": InputControlTool,
            "keyboard_type": InputControlTool,
            "keyboard_hotkey": InputControlTool,
            "screenshot": InputControlTool,
            "app_launch": WindowsAppsTool,
            "app_focus": WindowsAppsTool,
            "app_list": WindowsAppsTool,
            "web_search": WebSearchTool,
            "code_run": CodeRunnerTool,
        }

        # Istanze singleton per tool dello stesso modulo
        _instances = {}
        for name, cls in tool_classes.items():
            # Lambda: registra direttamente senza istanziare
            if callable(cls) and not isinstance(cls, type):
                self._tools[name] = cls
                self.log.info(f"Tool caricato: {name}")
                continue
            # Classe: istanzia con config (singleton per classe)
            cls_name = cls.__name__
            if cls_name not in _instances:
                try:
                    _instances[cls_name] = cls(self.config)
                    self.log.info(f"Tool caricato: {cls_name}")
                except Exception as e:
                    self.log.warning(f"Tool non disponibile {cls_name}: {e}")
                    _instances[cls_name] = None
            self._tools[name] = _instances[cls_name]


    # ── Orchestra AI / GitHub tools (v2.0) ──

    @staticmethod
    def _safe_params(p):
        """Converte p in dict sicuro per **kwargs, filtrando attributi privati."""
        if p is None:
            return {}
        if isinstance(p, dict):
            return {k: v for k, v in p.items()
                    if isinstance(k, str) and not k.startswith("_")}
        if hasattr(p, "__dict__"):
            return {k: v for k, v in vars(p).items()
                    if isinstance(k, str) and not k.startswith("_")
                    and isinstance(v, (str, int, float, bool, list, type(None)))}
        return {}


    def _normalize_params(self, params):
        """Normalizza params a dict sicuro."""
        if params is None:
            return {}
        if isinstance(params, dict):
            return params
        if hasattr(params, "__dict__"):
            return {k: v for k, v in vars(params).items() if not k.startswith("_")}
        return {}
    def _get_conductor_tool(self):
        if not hasattr(self, '_conductor_tool_inst'):
            try:
                from ..ai_conductor import AIConductorTool
                self._conductor_tool_inst = AIConductorTool(self.config)
            except Exception as e:
                self._conductor_tool_inst = None
                self._failed['conductor'] = str(e)
        return self._conductor_tool_inst

    def _get_git_sync_tool(self):
        if not hasattr(self, '_git_sync_tool_inst'):
            try:
                from ..github_sync import GitSyncTool
                self._git_sync_tool_inst = GitSyncTool(self.config)
            except Exception as e:
                self._git_sync_tool_inst = None
                self._failed['git_sync'] = str(e)
        return self._git_sync_tool_inst
    def execute(self, tool_name: str, params: dict) -> Any:
        """Esegue un tool per nome con i parametri dati."""
        tool = self._tools.get(tool_name)
        if not tool:
            return f"❌ Tool '{tool_name}' non trovato o non disponibile"

        try:
            method = getattr(tool, tool_name, None)
            if not method:
                # Fallback: chiama execute() con nome e params
                method = getattr(tool, "execute", None)
                if method:
                    return method(tool_name, params)
                return f"❌ Metodo '{tool_name}' non trovato in {type(tool).__name__}"
            return method(**params)
        except Exception as e:
            self.log.error(f"Errore tool {tool_name}: {e}")
            return f"❌ Errore esecuzione {tool_name}: {e}"

    def list_tools(self) -> list:
        """Lista tutti i tool disponibili."""
        return [name for name, tool in self._tools.items() if tool is not None]
