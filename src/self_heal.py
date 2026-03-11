"""
DUST AI - SelfHealEngine v1.1
Sistema di auto-guarigione: classifica errori tool, cerca soluzioni,
genera patch con Gemini e riprova automaticamente.
"""
import re
import os
import copy
import logging
import json
from typing import Optional, Callable

log = logging.getLogger("SelfHeal")

SEP = os.sep


# --- Classificazione errore --------------------------------------------------

def classify_error(error: str) -> str:
    """
    Ritorna una categoria di errore:
    - 'permission' : accesso negato
    - 'not_found'  : file/comando non trovato
    - 'syntax'     : errore di sintassi
    - 'network'    : errore di rete
    - 'timeout'    : timeout
    - 'unknown'    : altro
    """
    err = error.lower()
    if any(k in err for k in ["accesso negato", "access is denied", "permission denied", "(5)"]):
        return "permission"
    if any(k in err for k in ["impossibile trovare", "cannot find", "the system cannot find",
                               "no such file", "not found", "[exit code: 2]"]):
        return "not_found"
    if any(k in err for k in ["sintassi", "syntax error", "unexpected token"]):
        return "syntax"
    if "timeout" in err or "timed out" in err:
        return "timeout"
    if any(k in err for k in ["network", "connection", "unreachable"]):
        return "network"
    return "unknown"


# --- SelfHealEngine ----------------------------------------------------------

class SelfHealEngine:
    """
    Motore di auto-guarigione per i tool di DUST AI.

    Flusso:
    1. Classifica l'errore
    2. Tenta strategie built-in (es. path alternativo per not_found)
    3. Se necessario, chiede a Gemini una soluzione
    4. Restituisce: {message, give_up, retry_params, patch_applied}
    """

    def __init__(self, config, gemini_model=None, web_search_fn=None):
        self.config = config
        self.gemini = gemini_model
        self.web_search = web_search_fn
        self._heal_cache = {}  # error_key -> attempt_count

    # -- Metodo principale ----------------------------------------------------

    def heal(self, error: str, context: dict, max_attempts: int = 3) -> dict:
        """
        Tenta di risolvere l'errore.

        Returns dict con chiavi:
            message, give_up, retry_params, patch_applied
        """
        error_key = self._error_key(error)
        attempts = self._heal_cache.get(error_key, 0)

        if attempts >= max_attempts:
            msg = "SelfHeal: esauriti " + str(max_attempts) + " tentativi per questo errore."
            return {
                "message": msg,
                "give_up": True,
                "retry_params": None,
                "patch_applied": False,
            }

        self._heal_cache[error_key] = attempts + 1
        category = classify_error(error)
        log.info("SelfHeal: categoria=" + category + ", tentativo=" + str(attempts + 1))

        # 1. Strategie built-in
        builtin = self._builtin_strategy(category, error, context)
        if builtin:
            return builtin

        # 2. Strategia Gemini (se disponibile)
        if self.gemini:
            return self._gemini_strategy(error, context, category)

        return {
            "message": "SelfHeal: nessuna strategia disponibile per errore '" + category + "'.",
            "give_up": True,
            "retry_params": None,
            "patch_applied": False,
        }

    # -- Strategie built-in ---------------------------------------------------

    def _builtin_strategy(self, category: str, error: str, context: dict):
        params = context.get("params", {})

        if category == "permission":
            return {
                "message": "SelfHeal [permission]: prova percorso alternativo o esegui come amministratore.",
                "give_up": False,
                "retry_params": self._alt_path_params(params),
                "patch_applied": False,
            }

        if category == "not_found":
            alt = self._alt_path_params(params)
            if alt and alt != params:
                return {
                    "message": "SelfHeal [not_found]: riprovo con percorso alternativo.",
                    "give_up": False,
                    "retry_params": alt,
                    "patch_applied": False,
                }

        return None

    def _alt_path_params(self, params: dict):
        """Sostituisce il Desktop path con il percorso alternativo USERPROFILE\\Desktop."""
        desktop = str(self.config.get_desktop())
        userprofile = os.environ.get("USERPROFILE", "")
        desktop_folder = "Desktop"
        alt_desktop = os.path.join(userprofile, desktop_folder) if userprofile else ""

        if not alt_desktop or desktop == alt_desktop:
            return None

        new_params = copy.deepcopy(params)
        changed = False
        for key, val in new_params.items():
            if isinstance(val, str) and desktop in val:
                new_params[key] = val.replace(desktop, alt_desktop)
                changed = True
        return new_params if changed else None

    # -- Strategia Gemini -----------------------------------------------------

    def _gemini_strategy(self, error: str, context: dict, category: str) -> dict:
        operation = context.get("operation", "")
        task = context.get("task", "")
        params = context.get("params", {})

        # Cerca soluzioni web se disponibile
        web_ctx = ""
        if self.web_search:
            try:
                query = "python windows " + category + " error fix: " + error[:200]
                results = self.web_search({"query": query, "max_results": 3})
                if isinstance(results, list):
                    snippets = []
                    for r in results[:3]:
                        title = r.get("title", "")
                        snippet = r.get("snippet", "")[:300]
                        snippets.append("- " + title + ": " + snippet)
                    web_ctx = "\n".join(snippets)
                elif isinstance(results, str):
                    web_ctx = results[:800]
            except Exception as exc:
                log.debug("web_search fallita: " + str(exc))

        web_section = ""
        if web_ctx:
            web_section = "\n## Soluzioni web trovate\n" + web_ctx

        params_json = json.dumps(params, ensure_ascii=False)
        task_short = task[:500]

        prompt = (
            "Sei un esperto Python/Windows. Un tool di DUST AI ha restituito un errore.\n"
            "Analizza e suggerisci i parametri corretti per risolvere il problema.\n\n"
            "## Errore\n" + error + "\n\n"
            "## Categoria\n" + category + "\n\n"
            "## Operazione\n" + operation + "\n\n"
            "## Params attuali\n" + params_json + "\n\n"
            "## Task originale\n" + task_short
            + web_section + "\n\n"
            "## Risposta\n"
            'Rispondi SOLO con JSON valido:\n'
            '{"can_fix": true, "new_params": {...}, "explanation": "cosa cambiare"}\n'
            'Se non puoi risolvere: {"can_fix": false, "explanation": "motivo"}'
        )

        try:
            response = self.gemini.generate_content(prompt)
            raw = response.text.strip()
            raw = re.sub(r"```json\s*|```\s*", "", raw).strip()
            data = json.loads(raw)

            if not data.get("can_fix", False):
                explanation = data.get("explanation", "nessun fix")
                return {
                    "message": "SelfHeal [Gemini]: " + explanation,
                    "give_up": True,
                    "retry_params": None,
                    "patch_applied": False,
                }

            new_params = data.get("new_params") or params
            explanation = data.get("explanation", "")
            return {
                "message": "SelfHeal [Gemini]: " + explanation,
                "give_up": False,
                "retry_params": new_params,
                "patch_applied": False,
            }

        except Exception as exc:
            log.warning("SelfHeal Gemini fallito: " + str(exc))
            return {
                "message": "SelfHeal: errore Gemini (" + str(exc) + ")",
                "give_up": True,
                "retry_params": None,
                "patch_applied": False,
            }

    # -- Utility --------------------------------------------------------------

    def _error_key(self, error: str) -> str:
        """Chiave di deduplicazione per l'errore."""
        return error[:120].strip().lower()
