"""
DUST AI – ToolRegistry v4.0
Dispatcher centralizzato.
Fix: _safe_params filtra attributi privati, callable vs class, lazy singleton.
"""
import logging
log = logging.getLogger("ToolRegistry")

from .sys_exec       import SysExecTool
from .file_ops       import FileOpsTool
from .browser        import BrowserTool
from .input_control  import InputControlTool
from .windows_apps   import WindowsAppsTool
from .web_search     import WebSearchTool
from .code_runner    import CodeRunnerTool

# ── Optional imports ──────────────────────────────────────────────────────────
try:
    from .computer_use import ComputerUseTool as _CUTool
    _CU = True
except Exception as _e:
    _CU = False
    log.debug("ComputerUse N/D: %s", str(_e)[:60])

try:
    from ..ai_conductor import AIConductorTool as _Conductor
    _COND = True
except Exception:
    try:
        from ..ai_gateway import AIGatewayTool as _Conductor
        _COND = True
    except Exception:
        _COND = False

try:
    from ..github_sync import GitSyncTool as _GitSync
    _GIT = True
except Exception:
    _GIT = False


class ToolRegistry:
    def __init__(self, config):
        self.config = config
        self._tools = {}   # name → callable/instance
        self._descs = {}   # name → description
        self._inst  = {}   # ClassName → instance (singleton)
        self._register_all()

    # ── Registrazione ─────────────────────────────────────────────────────────

    def _register_all(self):
        BASE = [
            # (tool_name, Classe, method_name, descrizione)
            ("sys_exec",           SysExecTool,       "sys_exec",      "Esegui comando shell Windows. params: cmd"),
            ("file_read",          FileOpsTool,       "file_read",     "Leggi file. params: path"),
            ("file_write",         FileOpsTool,       "file_write",    "Scrivi file. params: path, content"),
            ("file_list",          FileOpsTool,       "file_list",     "Lista directory. params: path"),
            ("file_delete",        FileOpsTool,       "file_delete",   "Elimina file. params: path"),
            ("file_exists",        FileOpsTool,       "file_exists",   "Verifica se file esiste. params: path"),
            ("browser_open",       BrowserTool,       "browser_open",  "Apri URL (Playwright). params: url"),
            ("browser_click",      BrowserTool,       "browser_click", "Clicca elemento CSS. params: selector"),
            ("browser_type",       BrowserTool,       "browser_type",  "Digita in elemento. params: selector, text"),
            ("browser_get_text",   BrowserTool,       "browser_get_text", "Estrai testo. params: selector"),
            ("browser_screenshot", BrowserTool,       "browser_screenshot", "Screenshot pagina. params: (nessuno)"),
            ("mouse_move",         InputControlTool,  "mouse_move",    "Muovi mouse. params: x, y"),
            ("mouse_click",        InputControlTool,  "mouse_click",   "Click. params: x, y"),
            ("mouse_double_click", InputControlTool,  "mouse_double_click", "Double click. params: x, y"),
            ("keyboard_type",      InputControlTool,  "keyboard_type", "Digita testo. params: text"),
            ("keyboard_hotkey",    InputControlTool,  "keyboard_hotkey", "Premi tasti. params: keys"),
            ("screenshot",         InputControlTool,  "screenshot",    "Screenshot schermo. params: (nessuno)"),
            ("app_launch",         WindowsAppsTool,   "app_launch",    "Lancia app. params: name"),
            ("app_focus",          WindowsAppsTool,   "app_focus",     "Porta in primo piano. params: name"),
            ("app_list",           WindowsAppsTool,   "app_list",      "Lista finestre. params: (nessuno)"),
            ("web_search",         WebSearchTool,     "web_search",    "Cerca su internet. params: query"),
            ("code_run",           CodeRunnerTool,    "code_run",      "Esegui Python. params: code"),
        ]

        for tname, cls, method, desc in BASE:
            self._descs[tname] = desc
            inst = self._get_or_create(cls)
            if inst and hasattr(inst, method):
                self._tools[tname] = getattr(inst, method)
                log.info("Tool: %s", tname)
            elif inst:
                # fallback: usa execute() sull'istanza
                self._tools[tname] = inst

        # ComputerUse
        if _CU:
            try:
                cu = self._get_or_create(_CUTool)
                if cu:
                    for tname, method, desc in [
                        ("screen_do",     "screen_do",    "Esegui task guardando schermo. params: task"),
                        ("screen_read",   "screen_read",  "Descrivi schermo. params: (nessuno)"),
                        ("screen_click",  "screen_click", "Clicca elemento sullo schermo. params: target"),
                        ("screen_type",   "screen_type",  "Digita testo. params: text"),
                        ("screen_hotkey", "screen_hotkey","Premi tasti. params: keys"),
                        ("screen_scroll", "screen_scroll","Scrolla. params: direction, amount"),
                        ("app_open",      "app_open",     "Apri applicazione Windows. params: name"),
                        ("browser_go",    "browser_go",   "Apri URL nel browser. params: url"),
                        ("browser_do",    "browser_do",   "Opera nel browser. params: task"),
                    ]:
                        if hasattr(cu, method):
                            self._tools[tname] = getattr(cu, method)
                            self._descs[tname] = desc
                            log.info("Tool: %s (ComputerUse)", tname)
            except Exception as e:
                log.warning("ComputerUse init: %s", str(e)[:60])

        # AIConductor
        if _COND:
            try:
                cond = self._get_or_create(_Conductor)
                if cond:
                    for tname, method, desc in [
                        ("ai_ask",      "ai_ask",    "Chiedi a un modello AI. params: prompt, model"),
                        ("ai_parallel", "ai_parallel","Chiedi a più AI. params: prompt"),
                        ("ai_models",   "ai_models", "Lista modelli. params: (nessuno)"),
                        ("ai_status",   "ai_status", "Stato AI. params: (nessuno)"),
                    ]:
                        if hasattr(cond, method):
                            self._tools[tname] = getattr(cond, method)
                            self._descs[tname] = desc
                            log.info("Tool: %s (AIConductor)", tname)
            except Exception as e:
                log.warning("AIConductor init: %s", str(e)[:60])

        # GitSync
        if _GIT:
            try:
                git = self._get_or_create(_GitSync)
                if git:
                    for tname, method, desc in [
                        ("git_sync",   "git_sync",   "Sincronizza GitHub. params: message"),
                        ("git_commit", "git_commit", "Commit locale. params: message"),
                        ("git_push",   "git_push",   "Push su GitHub. params: (nessuno)"),
                        ("git_status", "git_status", "Stato git. params: (nessuno)"),
                    ]:
                        if hasattr(git, method):
                            self._tools[tname] = getattr(git, method)
                            self._descs[tname] = desc
                            log.info("Tool: %s (GitSync)", tname)
            except Exception as e:
                log.warning("GitSync init: %s", str(e)[:60])

        log.info("Tool totali caricati: %d", len(self._tools))

    def _get_or_create(self, cls):
        cname = cls.__name__
        if cname not in self._inst:
            try:
                self._inst[cname] = cls(self.config)
            except Exception as e:
                log.warning("Init [%s]: %s", cname, str(e)[:60])
                self._inst[cname] = None
        return self._inst.get(cname)

    # ── Esecuzione ────────────────────────────────────────────────────────────

    def execute(self, tool_name: str, params):
        handler = self._tools.get(tool_name)
        if handler is None:
            return f"Tool '{tool_name}' non trovato"

        safe = self._safe_params(params)

        try:
            return handler(**safe)
        except TypeError as e:
            # Parametri incompatibili: prova con singolo arg
            log.warning("TypeError [%s]: %s – provo con input=", tool_name, str(e)[:80])
            try:
                return handler(input=str(params))
            except Exception as e2:
                return f"Errore {tool_name}: {str(e2)[:150]}"
        except Exception as e:
            log.error("Tool [%s]: %s", tool_name, str(e)[:150])
            return f"Errore {tool_name}: {str(e)[:150]}"

    # ── Utility ───────────────────────────────────────────────────────────────

    @staticmethod
    def _safe_params(p) -> dict:
        """
        Converte p in dict sicuro per **kwargs.
        Filtra chiavi private (_xxx) e valori non scalari.
        Fix per il bug: Config._cfg passato come kwarg.
        """
        if p is None:
            return {}
        if isinstance(p, dict):
            return {
                k: v for k, v in p.items()
                if isinstance(k, str)
                and not k.startswith("_")
                and isinstance(v, (str, int, float, bool, list, type(None)))
            }
        if hasattr(p, "__dict__"):
            return {
                k: v for k, v in vars(p).items()
                if isinstance(k, str)
                and not k.startswith("_")
                and isinstance(v, (str, int, float, bool, list, type(None)))
            }
        # Tenta conversione da stringa JSON
        if isinstance(p, str):
            try:
                import json
                d = json.loads(p)
                if isinstance(d, dict):
                    return ToolRegistry._safe_params(d)
            except Exception:
                pass
            return {"input": p}
        return {}

    def list_tools(self) -> list:
        return sorted(self._tools.keys())

    def get_description(self, name: str) -> str:
        return self._descs.get(name, f"Tool: {name}")
