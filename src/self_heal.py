"""
DUST AI – SelfHealEngine v2.0
Potenziato: guarisce anche su parse failure e rate limit.
Auto-patcha il codice sorgente stesso se necessario.

Tipi di heal:
  - tool_error:    errore di esecuzione tool (permission, not_found, ecc.)
  - parse_fail:    modello Ollama non produce JSON valido
  - rate_limit:    429 Gemini → switch strategy
  - src_syntax:    syntax error nel codice sorgente → patch + reload
  - import_error:  modulo mancante → pip install automatico
"""
import os
import re
import sys
import ast
import json
import copy
import time
import logging
import importlib
import subprocess
from pathlib import Path
from typing import Optional, Any

log = logging.getLogger("SelfHeal")


# ─── Classificatori ──────────────────────────────────────────────────────────

def classify_tool_error(error: str) -> str:
    err = error.lower()
    if any(k in err for k in ["accesso negato", "access is denied", "permission denied", "(5)", "winerror 5"]):
        return "permission"
    if any(k in err for k in ["impossibile trovare", "cannot find", "no such file", "not found", "exit code: 2"]):
        return "not_found"
    if any(k in err for k in ["timeout", "timed out"]):
        return "timeout"
    if any(k in err for k in ["network", "connection", "unreachable", "refused"]):
        return "network"
    if any(k in err for k in ["syntax error", "unexpected token", "sintassi"]):
        return "syntax"
    return "unknown"


def classify_src_error(error: str, tb: str) -> str:
    combined = error + " " + tb
    if "f-string expression part cannot include a backslash" in combined:
        return "fstring_backslash"
    if re.search(r"No module named '([^']+)'", combined):
        return "missing_module"
    if "CREATE_NO_WINDOW" in combined and "AttributeError" in combined:
        return "create_no_window"
    if "SyntaxError" in combined:
        return "syntax_error"
    if re.search(r"has no attribute", combined):
        return "attr_error"
    return "unknown"


# ─── SelfHealEngine ──────────────────────────────────────────────────────────

class SelfHealEngine:
    """
    Motore di auto-guarigione centralizzato.

    Metodi pubblici:
      heal(error, context)           → per errori tool runtime
      heal_parse_fail(raw, messages) → per output Ollama non-JSON
      heal_src_error(error, tb)      → per errori nel codice sorgente
      heal_rate_limit()              → strategia su 429 Gemini
    """

    def __init__(self, config, gemini_model=None, web_search_fn=None):
        self.config      = config
        self.gemini      = gemini_model
        self.web_search  = web_search_fn
        self._cache: dict = {}   # error_key → attempt_count
        self._src_root   = Path(__file__).parent

    # ─── Heal tool error ─────────────────────────────────────────────────────

    def heal(self, error: str, context: dict, max_attempts: int = None) -> dict:
        """
        Tenta di risolvere un errore di esecuzione tool.
        Ritorna: {message, give_up, retry_params, patch_applied}
        """
        max_attempts = max_attempts or self.config.get_self_heal_cfg("max_attempts") or 5
        error_key    = error[:120].lower().strip()
        attempts     = self._cache.get(error_key, 0)

        if attempts >= max_attempts:
            return self._give_up("Esauriti " + str(max_attempts) + " tentativi")

        self._cache[error_key] = attempts + 1
        category = classify_tool_error(error)
        log.info("SelfHeal tool: cat=" + category + " attempt=" + str(attempts + 1))

        # 1. Strategie built-in
        result = self._builtin_strategy(category, error, context)
        if result:
            return result

        # 2. Strategia Gemini
        if self.gemini:
            return self._gemini_strategy(error, context, category)

        return self._give_up("Nessuna strategia per: " + category)

    def _builtin_strategy(self, category: str, error: str, context: dict) -> Optional[dict]:
        params = context.get("params", {})

        if category == "permission":
            alt = self._alt_path(params)
            msg = "SelfHeal [permission]: uso percorso alternativo" if alt else "SelfHeal [permission]: nessun path alternativo"
            return {"message": msg, "give_up": alt is None, "retry_params": alt, "patch_applied": False}

        if category == "not_found":
            alt = self._alt_path(params)
            if alt and alt != params:
                return {"message": "SelfHeal [not_found]: path alternativo", "give_up": False, "retry_params": alt, "patch_applied": False}

        if category == "timeout":
            new_params = copy.deepcopy(params)
            new_params["timeout"] = (params.get("timeout") or 30) * 2
            return {"message": "SelfHeal [timeout]: raddoppio timeout", "give_up": False, "retry_params": new_params, "patch_applied": False}

        return None

    def _alt_path(self, params: dict) -> Optional[dict]:
        """Sostituisce Desktop path con percorso USERPROFILE\\Desktop come fallback."""
        desktop     = str(self.config.get_desktop())
        userprofile = os.environ.get("USERPROFILE", "")
        if not userprofile:
            return None
        alt_desktop = os.path.join(userprofile, "Desktop")
        if desktop == alt_desktop:
            return None

        new_params = copy.deepcopy(params)
        changed = False
        for key, val in new_params.items():
            if isinstance(val, str) and desktop in val:
                new_params[key] = val.replace(desktop, alt_desktop)
                changed = True
        return new_params if changed else None

    def _gemini_strategy(self, error: str, context: dict, category: str) -> dict:
        """Chiede a Gemini i parametri corretti per ritentare."""
        try:
            web_ctx = self._search_solution(error, category)
            web_section = ("\n## Soluzioni trovate\n" + web_ctx) if web_ctx else ""

            params_str = json.dumps(context.get("params", {}), ensure_ascii=False)
            prompt = (
                "Sei un esperto Python/Windows. Un tool DUST AI ha fallito.\n"
                "## Errore\n" + error + "\n"
                "## Categoria\n" + category + "\n"
                "## Operazione\n" + context.get("operation", "") + "\n"
                "## Params\n" + params_str
                + web_section + "\n\n"
                "Rispondi SOLO con JSON:\n"
                '{"can_fix":true,"new_params":{...},"explanation":"cosa cambiare"}\n'
                'Se impossibile: {"can_fix":false,"explanation":"motivo"}'
            )

            resp = self.gemini.generate_content(prompt)
            data = self._parse_json_safe(resp.text)

            if not data.get("can_fix"):
                return self._give_up("Gemini: " + data.get("explanation", ""))

            return {
                "message":      "SelfHeal [Gemini]: " + data.get("explanation", ""),
                "give_up":      False,
                "retry_params": data.get("new_params") or context.get("params"),
                "patch_applied": False,
            }
        except Exception as e:
            return self._give_up("Gemini strategy errore: " + str(e))

    def _search_solution(self, error: str, category: str) -> str:
        """Cerca soluzioni web se disponibile."""
        if not self.web_search:
            return ""
        try:
            query   = "python windows " + category + " fix: " + error[:150]
            results = self.web_search({"query": query, "max_results": 3})
            if isinstance(results, list):
                return "\n".join(
                    "- " + r.get("title", "") + ": " + r.get("snippet", "")[:200]
                    for r in results[:3]
                )
            return str(results)[:600]
        except Exception:
            return ""

    # ─── Heal parse failure ──────────────────────────────────────────────────

    def heal_parse_fail(self, raw_output: str, messages: list) -> Optional[dict]:
        """
        Chiamato quando Ollama produce output non-JSON.
        Tenta di:
        1. Estrarre JSON da testo narrativo
        2. Chiedere a Gemini di riformattare l'output
        Ritorna un tool_call dict o None.
        """
        if not self.config.get_self_heal_cfg("heal_parse_fail", True):
            return None

        log.info("SelfHeal parse_fail: provo estrazione da testo")

        # Estrazione aggressiva: cerca qualsiasi JSON-like nel testo
        for m in re.finditer(r'\{[^{}]{5,500}\}', raw_output, re.DOTALL):
            try:
                data = json.loads(m.group(0))
                if "tool" in data or "status" in data:
                    return data
            except json.JSONDecodeError:
                pass

        # Riformattazione via Gemini
        if self.gemini:
            try:
                prompt = (
                    "Il seguente output di un agente AI non è JSON valido.\n"
                    "Estrai l'intenzione e riformattala come JSON puro.\n\n"
                    "Output originale:\n" + raw_output[:1000] + "\n\n"
                    "Tool disponibili: sys_exec, file_read, file_write, file_list, "
                    "web_search, browser_open, screenshot, code_run, app_launch, "
                    "mouse_click, keyboard_type\n\n"
                    "Rispondi SOLO con JSON:\n"
                    '{"tool":"nome","params":{"param":"valore"}}\n'
                    'o se completato: {"status":"done","summary":"..."}'
                )
                resp = self.gemini.generate_content(prompt)
                data = self._parse_json_safe(resp.text)
                if data and ("tool" in data or "status" in data):
                    log.info("SelfHeal parse_fail: Gemini ha riformattato l'output")
                    return data
            except Exception as e:
                log.warning("SelfHeal parse_fail Gemini: " + str(e))

        return None

    # ─── Heal source code errors ─────────────────────────────────────────────

    def heal_src_error(self, error: str, tb: str, broken_file: str = "") -> bool:
        """
        Patcha il codice sorgente DUST AI quando c'è un errore prima del boot.
        Usato dal pre-boot recovery in run.py.
        """
        if not self.config.get_self_heal_cfg("auto_patch_src", True):
            return False

        src_type = classify_src_error(error, tb)
        target   = broken_file or self._find_file_in_tb(tb)

        if not target:
            log.warning("SelfHeal src: file non trovato nella traceback")
            return False

        log.info("SelfHeal src: tipo=" + src_type + " file=" + Path(target).name)

        # Fix predefiniti
        if src_type == "fstring_backslash":
            return self._fix_fstring_backslash(target)

        if src_type == "missing_module":
            m = re.search(r"No module named '([^']+)'", error + " " + tb)
            if m:
                return self._pip_install(m.group(1).split(".")[0])

        if src_type == "create_no_window":
            return self._patch_literal(
                target,
                "subprocess.CREATE_NO_WINDOW",
                'getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)'
            )

        # LLM patch per tutto il resto
        if self.gemini:
            return self._llm_patch_file(error, tb, target)

        return False

    def _fix_fstring_backslash(self, filepath: str) -> bool:
        """Fix backslash in f-string per Python < 3.12."""
        try:
            source   = Path(filepath).read_text(encoding="utf-8")
            original = source
            lines    = source.splitlines()
            new_lines = []
            changed  = False

            for line in lines:
                stripped = line.lstrip()
                indent   = line[:len(line) - len(stripped)]
                if re.search(r'f["\'].*\{[^}]*\\[^}]*\}.*["\']', line):
                    # Sostituisce backslash nell'espressione con path join sicuro
                    fixed = re.sub(
                        r'\{([^}]*\\[^}]*)\}',
                        lambda m: "{" + m.group(1).replace("\\\\", "/").replace("\\", "/") + "}",
                        stripped
                    )
                    new_lines.append(indent + fixed)
                    changed = True
                else:
                    new_lines.append(line)

            if not changed:
                return False

            patched = "\n".join(new_lines)
            ast.parse(patched)
            self._backup_and_write(filepath, patched, original)
            log.info("SelfHeal: fstring_backslash fix applicato a " + Path(filepath).name)
            return True
        except Exception as e:
            log.warning("fstring fix fallito: " + str(e))
            return False

    def _patch_literal(self, filepath: str, find: str, replace: str) -> bool:
        """Sostituisce una stringa letterale nel sorgente."""
        try:
            source = Path(filepath).read_text(encoding="utf-8")
            if find not in source:
                return False
            patched = source.replace(find, replace, 1)
            ast.parse(patched)
            self._backup_and_write(filepath, patched, source)
            log.info("SelfHeal: literal patch su " + Path(filepath).name)
            return True
        except Exception as e:
            log.warning("literal patch fallita: " + str(e))
            return False

    def _llm_patch_file(self, error: str, tb: str, filepath: str) -> bool:
        """Genera patch con Gemini e applica al file sorgente."""
        try:
            source = Path(filepath).read_text(encoding="utf-8") if Path(filepath).exists() else ""
            fname  = Path(filepath).name
            py_ver = str(sys.version_info.major) + "." + str(sys.version_info.minor)

            prompt = (
                "Sei un esperto Python. DUST AI crasha per un errore nel sorgente.\n"
                "Genera una patch minimale compatibile con Python " + py_ver + ".\n\n"
                "## Errore\n" + error + "\n\n"
                "## Traceback\n" + tb[-2000:] + "\n\n"
                "## File: " + fname + "\n```python\n" + source[:4000] + "\n```\n\n"
                "## Regole Python " + py_ver + "\n"
                "- NON mettere backslash dentro {..} nelle f-string\n"
                "- Usa variabili intermedie per valori con backslash\n\n"
                "Risposta SOLO JSON:\n"
                '{"can_fix":true,"find":"stringa ESATTA dal sorgente","replace":"stringa corretta","explanation":"perche"}\n'
                'Se impossibile: {"can_fix":false,"explanation":"motivo"}'
            )

            resp = self.gemini.generate_content(prompt)
            data = self._parse_json_safe(resp.text)

            if not data.get("can_fix"):
                log.info("LLM patch: can_fix=false — " + data.get("explanation", ""))
                return False

            find_str    = data.get("find", "")
            replace_str = data.get("replace", "")

            if not find_str or find_str not in source:
                log.warning("LLM patch: stringa 'find' non trovata nel sorgente")
                return False

            patched = source.replace(find_str, replace_str, 1)
            ast.parse(patched)
            self._backup_and_write(filepath, patched, source)
            log.info("SelfHeal: LLM patch applicata a " + fname + " — " + data.get("explanation", ""))
            return True

        except Exception as e:
            log.warning("LLM patch fallita: " + str(e))
            return False

    def _pip_install(self, package: str) -> bool:
        """Installa un pacchetto Python mancante."""
        if not package:
            return False
        log.info("SelfHeal: pip install " + package)
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--quiet", package],
                capture_output=True, text=True, timeout=120
            )
            return result.returncode == 0
        except Exception as e:
            log.warning("pip install fallito: " + str(e))
            return False

    # ─── Heal rate limit ─────────────────────────────────────────────────────

    def heal_rate_limit(self, error: str) -> dict:
        """
        Chiamato su errore 429 Gemini.
        Ritorna: {strategy: "wait"|"ollama"|"give_up", wait_seconds: int}
        """
        if not self.config.get_self_heal_cfg("heal_rate_limit", True):
            return {"strategy": "give_up", "wait_seconds": 0}

        # Estrai retry delay dall'errore se presente
        m = re.search(r"retry.*?(\d+)[\s]*s", error, re.IGNORECASE)
        wait = int(m.group(1)) + 5 if m else 65

        return {
            "strategy":     "ollama",   # preferisci switch a Ollama
            "wait_seconds": wait,
            "message":      "Rate limit: attendi " + str(wait) + "s o usa Ollama",
        }

    # ─── Utilities ───────────────────────────────────────────────────────────

    def _find_file_in_tb(self, tb: str) -> str:
        for match in re.finditer(r'File "([^"]*(?:src|dustai)[^"]*\.py)"', tb):
            path = match.group(1)
            if Path(path).exists():
                return path
        return ""

    def _backup_and_write(self, filepath: str, patched: str, original: str):
        patches_dir = self.config.get_base_path() / "patches"
        patches_dir.mkdir(exist_ok=True)
        bak_name = Path(filepath).stem + ".bak" + str(int(time.time())) + ".py"
        (patches_dir / bak_name).write_text(original, encoding="utf-8")
        Path(filepath).write_text(patched, encoding="utf-8")

    def _parse_json_safe(self, text: str) -> dict:
        clean = re.sub(r"```json\s*|```\s*", "", text.strip()).strip()
        try:
            return json.loads(clean)
        except json.JSONDecodeError:
            for m in re.finditer(r'\{[^{}]{5,2000}\}', clean, re.DOTALL):
                try:
                    return json.loads(m.group(0))
                except json.JSONDecodeError:
                    pass
        return {}

    def _give_up(self, reason: str) -> dict:
        return {"message": reason, "give_up": True, "retry_params": None, "patch_applied": False}
