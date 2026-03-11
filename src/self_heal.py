"""
DUST AI – SelfHealEngine v1.0
Sistema di auto-guarigione: classifica errori tool, cerca soluzioni,
genera patch con Gemini e riprova automaticamente.
"""
import re
import logging
import json
from typing import Optional, Callable

log = logging.getLogger("SelfHeal")


# ─── Classificazione errore ───────────────────────────────────────────────────

def classify_error(error: str) -> str:
    """
    Ritorna una categoria di errore stringa:
    - 'permission'   : accesso negato
    - 'not_found'    : file/comando non trovato
    - 'syntax'       : errore di sintassi
    - 'network'      : errore di rete
    - 'timeout'      : timeout
    - 'unknown'      : altro
    """
    err = error.lower()
    if any(k in err for k in ["accesso negato", "access is denied", "permission denied", "(5)"]):
        return "permission"
    if any(k in err for k in ["impossibile trovare", "cannot find", "the system cannot find",
                               "no such file", "not found", "[exit code: 2]"]):
        return "not_found"
    if any(k in err for k in ["sintassi", "syntax error", "unexpected token"]):
        return "syntax"
    if any(k in err for k in ["network", "connection", "unreachable", "timeout", "timed out"]):
        return "network" if "timeout" not in err else "timeout"
    if "timeout" in err or "timed out" in err:
        return "timeout"
    return "unknown"


# ─── SelfHealEngine ───────────────────────────────────────────────────────────

class SelfHealEngine:
    """
    Motore di auto-guarigione per i tool di DUST AI.

    Flusso:
    1. Classifica l'errore
    2. Tenta strategie built-in (es. path alternativo per not_found)
    3. Se necessario, chiede a Gemini una soluzione
    4. Restituisce: {message, give_up, retry_params, patch_applied}
    """

    def __init__(
        self,
        config,
        gemini_model=None,
        web_search_fn: Optional[Callable] = None,
    ):
        self.config = config
        self.gemini = gemini_model
        self.web_search = web_search_fn
        self._heal_cache: dict[str, int] = {}  # error_hash -> attempt_count

    # ── Metodo principale ────────────────────────────────────────────────────

    def heal(
        self,
        error: str,
        context: dict,
        max_attempts: int = 3,
    ) -> dict:
        """
        Tenta di risolvere l'errore.

        Args:
            error:        stringa di errore del tool
            context:      dizionario con chiavi: operation, params, task, file
            max_attempts: numero massimo di tentativi per questo errore

        Returns:
            {
                'message':       str  - messaggio leggibile
                'give_up':       bool - True se non si sa come risolvere
                'retry_params':  dict|None - nuovi params da usare
                'patch_applied': bool - True se un file sorgente è stato patchato
            }
        """
        error_key = self._error_key(error)
        attempts = self._heal_cache.get(error_key, 0)

        if attempts >= max_attempts:
            return {
                "message": f"SelfHeal: esauriti {max_attempts} tentativi per questo errore.",
                "give_up": True,
                "retry_params": None,
                "patch_applied": False,
            }

        self._heal_cache[error_key] = attempts + 1
        category = classify_error(error)
        log.info(f"SelfHeal: categoria={category}, tentativo={attempts+1}")

        # 1. Strategie built-in
        builtin = self._builtin_strategy(category, error, context)
        if builtin:
            return builtin

        # 2. Strategia Gemini (se disponibile)
        if self.gemini:
            return self._gemini_strategy(error, context, category)

        return {
            "message": f"SelfHeal: nessuna strategia disponibile per errore '{category}'.",
            "give_up": True,
            "retry_params": None,
            "patch_applied": False,
        }

    # ── Strategie built-in ───────────────────────────────────────────────────

    def _builtin_strategy(self, category: str, error: str, context: dict) -> Optional[dict]:
        params = context.get("params", {})

        if category == "permission":
            # Prova a rieseguire con runas (solo info, non possiamo davvero elevare)
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

    def _alt_path_params(self, params: dict) -> Optional[dict]:
        """Sostituisce il Desktop path con l'alternativo %USERPROFILE%\\Desktop."""
        import os
        import copy
        desktop = str(self.config.get_desktop())
        userprofile = os.environ.get("USERPROFILE", "")
        alt_desktop = userprofile + "\\Desktop" if userprofile else ""

        if not alt_desktop or desktop == alt_desktop:
            return None

        new_params = copy.deepcopy(params)
        changed = False
        for key, val in new_params.items():
            if isinstance(val, str) and desktop in val:
                new_params[key] = val.replace(desktop, alt_desktop)
                changed = True
        return new_params if changed else None

    # ── Strategia Gemini ─────────────────────────────────────────────────────

    def _gemini_strategy(self, error: str, context: dict, category: str) -> dict:
        operation = context.get("operation", "")
        task = context.get("task", "")
        params = context.get("params", {})

        # Cerca soluzioni web se disponibile
        web_ctx = ""
        if self.web_search:
            try:
                query = f"python windows {category} error fix: {error[:200]}"
                results = self.web_search({"query": query, "max_results": 3})
                if isinstance(results, list):
                    web_ctx = "\n".join(
                        f"- {r.get('title','')}: {r.get('snippet','')[:300]}"
                        for r in results[:3]
                    )
                elif isinstance(results, str):
                    web_ctx = results[:800]
            except Exception as e:
                log.debug(f"web_search fallita: {e}")

        prompt = f"""Sei un esperto Python/Windows. Un tool di DUST AI ha restituito un errore.
Analizza e suggerisci i parametri corretti per risolvere il problema.

## Errore
{error}

## Categoria
{category}

## Operazione
{operation}

## Params attuali
{json.dumps(params, ensure_ascii=False)}

## Task originale
{task[:500]}

{('## Soluzioni web trovate\n' + web_ctx) if web_ctx else ''}

## Risposta
Rispondi SOLO con JSON valido:
{{"can_fix": true, "new_params": {{...}}, "explanation": "cosa cambiare"}}
Se non puoi risolvere: {{"can_fix": false, "explanation": "motivo"}}"""

        try:
            response = self.gemini.generate_content(prompt)
            raw = response.text.strip()
            raw = re.sub(r"```json\s*|```\s*", "", raw).strip()
            data = json.loads(raw)

            if not data.get("can_fix", False):
                return {
                    "message": f"SelfHeal [Gemini]: {data.get('explanation', 'nessun fix')}",
                    "give_up": True,
                    "retry_params": None,
                    "patch_applied": False,
                }

            new_params = data.get("new_params") or params
            explanation = data.get("explanation", "")
            return {
                "message": f"SelfHeal [Gemini]: {explanation}",
                "give_up": False,
                "retry_params": new_params,
                "patch_applied": False,
            }

        except Exception as e:
            log.warning(f"SelfHeal Gemini fallito: {e}")
            return {
                "message": f"SelfHeal: errore Gemini ({e})",
                "give_up": True,
                "retry_params": None,
                "patch_applied": False,
            }

    # ── Utility ──────────────────────────────────────────────────────────────

    def _error_key(self, error: str) -> str:
        """Chiave di deduplicazione per l'errore."""
        return error[:120].strip().lower()
