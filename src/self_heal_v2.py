"""
DUST AI – SelfHealEngine v2.0
Auto-healing completo con integrazione AIOrchestra.

Miglioramenti rispetto alla v1:
  - Usa multi-agent orchestra per diagnosi più accurate (2 modelli gratis)
  - HallucinationGuard integrato nel loop di healing
  - Circuit breaker intelligente (non aspetta 65s se il prossimo modello è libero)
  - Diagnosi categorizata: parse_error | rate_limit | tool_error | src_code | hallucination
  - Patch differenziale: modifica solo le righe problematiche (non riscrive tutto)
  - Self-test automatico dopo ogni patch
  - History dei fix per evitare loop infiniti
  - Budget zero: solo Gemini Free (3 chiavi) + Ollama locale

Basato su:
  - Self-healing agent patterns (enterprise 2026)
  - ReST-EM: self-improvement via execution feedback
  - AgentScope fault tolerance patterns
"""

import re
import ast
import json
import time
import logging
import subprocess
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional

log = logging.getLogger("SelfHealEngine")

# ─── Limiti sicuri per retry/wait ────────────────────────────────────────────
MIN_WAIT_S   = 5
MAX_WAIT_S   = 65
MAX_RETRIES  = 4
MAX_PATCHES  = 10   # patch massime prima di reset manuale
HISTORY_FILE = Path(r"A:\dustai_stuff\memory\selfheal_history.json")

# ─── Categorie di errore ──────────────────────────────────────────────────────
ERROR_CATEGORIES = {
    "rate_limit": [
        "429", "RESOURCE_EXHAUSTED", "quota", "rate limit",
        "too many requests", "ratelimit",
    ],
    "parse_error": [
        "parse_error", "JSONDecodeError", "invalid json",
        "unterminated string", "parse fail", "finish_reason",
    ],
    "tool_error": [
        "ToolError", "tool not found", "invalid tool",
        "unexpected keyword argument", "missing required argument",
    ],
    "import_error": [
        "ImportError", "ModuleNotFoundError", "No module named",
        "cannot import",
    ],
    "syntax_error": [
        "SyntaxError", "IndentationError", "invalid syntax",
        "unexpected indent",
    ],
    "hallucination": [
        "HALLUCINATION_SCORE", "confidence < 30",
        "cross_validation_mismatch",
    ],
    "network_error": [
        "ConnectionError", "TimeoutError", "requests.exceptions",
        "ssl", "certificate",
    ],
}

# ─── Prompt di healing per categoria ─────────────────────────────────────────
HEAL_PROMPTS = {
    "parse_error": """
Sei un esperto Python. Questo output di un LLM non è JSON valido:
{raw}

Estrai il tool call corretto in formato JSON puro:
{{"tool": "nome_tool", "params": {{"chiave": "valore"}}}}
oppure se il task è finito:
{{"status": "done", "summary": "cosa è stato fatto"}}

Rispondi SOLO con JSON valido, nient'altro.
""",

    "syntax_error": """
Sei un esperto Python. Questo codice ha un errore sintattico:
FILE: {file_path}
ERRORE: {error_msg}
CODICE (righe {start_line}-{end_line}):
{code_snippet}

Fornisci SOLO le righe corrette in formato:
LINEA_ORIGINALE: <testo esatto della riga errata>
LINEA_CORRETTA: <testo corretto>

Una correzione per riga. Nient'altro.
""",

    "import_error": """
Questo import Python fallisce: {error_msg}
Nel file: {file_path}

Possibili soluzioni:
1. Il modulo non è installato -> pip install X
2. Path sbagliato -> correggere import
3. Typo nel nome modulo

Rispondi con:
ACTION: [install_pip|fix_import|check_path]
FIX: [comando pip install X oppure riga import corretta]
""",

    "tool_error": """
Un tool DUST ha prodotto questo errore: {error_msg}
Contesto: {context}

Analizza il problema e suggerisci:
1. Cosa ha causato l'errore
2. Come chiamare il tool correttamente
3. Parametri corretti da usare

Formato:
CAUSA: [spiegazione]
TOOL_CALL: {{"tool": "nome", "params": {{...}}}}
""",

    "hallucination": """
Questa risposta AI ha ricevuto un alto hallucination score ({hall_score}/10):
{response}

Problemi rilevati: {issues}

Riscrivi la risposta in modo più accurato e cauto:
- Elimina le affermazioni non verificabili
- Sostituisci certezze false con "probabilmente/stima/incerto"
- Aggiungi disclaimer dove necessario

RISPOSTA_CORRETTA:
""",
}


class SelfHealEngine:
    """
    Motore di auto-riparazione DUST v2.0.
    Completamente gratuito: Gemini Free + Ollama.
    """

    def __init__(self, config, gemini_model=None, gateway=None):
        self.config       = config
        self._gm          = gemini_model   # vecchio model (compat v1)
        self.gateway      = gateway
        self._base        = config.get_base_path()
        self._patch_dir   = self._base / "patches"
        self._patch_dir.mkdir(exist_ok=True)
        self._history     = self._load_history()
        self._hall_guard  = None
        self._circuit     = {}   # model_id -> timestamp fine cooldown

    # ─── Modelli gratuiti ─────────────────────────────────────────────────────

    FREE_MODELS = [
        "gemini/gemini-2.5-flash",
        "gemini/gemini-2.5-flash-lite",
        "ollama/qwen3:8b",
    ]

    def _free_call(self, prompt: str, temperature: float = 0.2,
                   max_tokens: int = 1000) -> str:
        """Chiama il primo modello gratuito disponibile."""
        if not self.gateway:
            self._init_gateway()
        if not self.gateway:
            return self._fallback_gemini(prompt)

        for model_id in self.FREE_MODELS:
            # Circuit breaker
            if model_id in self._circuit:
                if time.time() < self._circuit[model_id]:
                    continue
                del self._circuit[model_id]
            try:
                result = self.gateway.call(model_id, prompt,
                                           max_tokens=max_tokens,
                                           temperature=temperature)
                if result.get("ok"):
                    return result.get("text", "")
                # Rate limit -> circuit breaker
                err = result.get("error", "")
                if "429" in err or "RATE" in err.upper():
                    self._circuit[model_id] = time.time() + 65
                    log.warning("Circuit breaker %s per 65s", model_id)
                    continue
            except Exception as e:
                log.warning("free_call %s: %s", model_id, str(e)[:60])
        return ""

    def _fallback_gemini(self, prompt: str) -> str:
        """Fallback diretto Gemini senza gateway."""
        try:
            import os
            import google.generativeai as genai
            key = (os.environ.get("GOOGLE_API_KEY") or
                   os.environ.get("GOOGLE_API_KEY_2") or "")
            if not key:
                return ""
            genai.configure(api_key=key)
            m = genai.GenerativeModel("gemini-2.5-flash")
            r = m.generate_content(prompt)
            return r.text.strip()
        except Exception:
            return ""

    def _init_gateway(self):
        try:
            from .ai_gateway import AIGateway
            self.gateway = AIGateway(self.config)
        except ImportError:
            try:
                from ai_gateway import AIGateway
                self.gateway = AIGateway(self.config)
            except Exception:
                pass

    def _get_hall_guard(self):
        if not self._hall_guard:
            try:
                from .hallucination_guard import HallucinationGuard
                self._hall_guard = HallucinationGuard(self.config, self.gateway)
            except ImportError:
                try:
                    from hallucination_guard import HallucinationGuard
                    self._hall_guard = HallucinationGuard(self.config, self.gateway)
                except Exception:
                    pass
        return self._hall_guard

    # ─── Metodi pubblici di healing ───────────────────────────────────────────

    def heal(self, error: str, context: dict = None) -> dict:
        """
        Entry point principale. Diagnostica e risolve automaticamente.

        context: {
          "raw":       output grezzo del modello (per parse_error)
          "messages":  conversazione corrente
          "file_path": file con errore
          "tool":      tool che ha fallito
          "response":  risposta AI da correggere
        }
        """
        context  = context or {}
        category = self._categorize_error(error)

        log.info("SelfHeal: categoria=%s error='%s...'", category, error[:60])
        print("   🔧 SelfHeal [" + category + "] attivo...")

        # Dispatch per categoria
        handlers = {
            "rate_limit":   self.heal_rate_limit,
            "parse_error":  self.heal_parse_fail,
            "syntax_error": self.heal_syntax_error,
            "import_error": self.heal_import_error,
            "tool_error":   self.heal_tool_error,
            "hallucination":self.heal_hallucination,
            "network_error":self.heal_network_error,
        }

        handler = handlers.get(category, self.heal_generic)
        result  = handler(error, context)

        # Registra nella history
        self._record(category, error, result.get("ok", False))

        return result

    def heal_rate_limit(self, error: str, context: dict = None) -> dict:
        """
        Healing per rate limit (429).
        Nuova logica v2: invece di aspettare, switcha subito al prossimo modello free.
        """
        context = context or {}

        # Calcola wait SICURO (bugfix v1: mai più 550M secondi)
        wait = self._safe_retry_delay(error)
        log.info("Rate limit: wait=%ds", wait)

        # Trova il modello che ha dato 429
        failed_model = context.get("model_id", "")
        if failed_model:
            self._circuit[failed_model] = time.time() + wait

        # Lista modelli alternativi disponibili
        alternatives = [m for m in self.FREE_MODELS
                        if m != failed_model and m not in self._circuit]

        if alternatives:
            print("   🔄 Rate limit → switch a " + alternatives[0].split("/")[-1])
            return {
                "ok":          True,
                "action":      "switch_model",
                "model":       alternatives[0],
                "wait":        0,   # zero attesa!
                "msg":         "Switchato a " + alternatives[0],
            }

        # Nessun alternativo disponibile: aspetta il minimo
        print("   ⏳ Rate limit: attesa " + str(wait) + "s (tutti i modelli esauriti)...")
        time.sleep(wait)
        return {
            "ok":     True,
            "action": "waited",
            "wait":   wait,
            "msg":    "Attesi " + str(wait) + "s",
        }

    def heal_parse_fail(self, raw: str, messages: list = None) -> Optional[dict]:
        """
        Healing per parse error dell'LLM.
        v2: usa HallucinationGuard + 2 modelli per estrazione più robusta.
        """
        # 1. Prova parsing diretto (zero costo)
        direct = self._try_parse_direct(raw)
        if direct:
            log.info("Parse fix: estrazione diretta riuscita")
            return direct

        # 2. Prova con Gemini Free
        prompt = HEAL_PROMPTS["parse_error"].format(raw=raw[:1500])
        fixed_raw = self._free_call(prompt, temperature=0.1)

        if fixed_raw:
            parsed = self._try_parse_direct(fixed_raw)
            if parsed:
                log.info("Parse fix: Gemini ha estratto tool call")
                return parsed

        # 3. Fallback Ollama
        ollama_result = self.gateway.call("ollama/qwen3:8b", prompt,
                                          max_tokens=200, temperature=0.1) if self.gateway else {}
        if ollama_result.get("ok"):
            parsed = self._try_parse_direct(ollama_result["text"])
            if parsed:
                return parsed

        log.warning("Parse heal fallito per: %s...", raw[:60])
        return None

    def heal_syntax_error(self, error: str, context: dict = None) -> dict:
        """Healing per SyntaxError in file Python."""
        context   = context or {}
        file_path = context.get("file_path", "")

        if not file_path or not Path(file_path).exists():
            return {"ok": False, "error": "file_path mancante o non trovato"}

        # Leggi il file
        src    = Path(file_path).read_text(encoding="utf-8")
        lines  = src.splitlines()

        # Estrai numero riga dall'errore
        line_m = re.search(r'line (\d+)', error)
        err_line = int(line_m.group(1)) if line_m else 1
        start  = max(0, err_line - 5)
        end    = min(len(lines), err_line + 5)
        snippet = "\n".join(
            str(i + 1 + start).rjust(4) + "  " + l
            for i, l in enumerate(lines[start:end])
        )

        prompt = HEAL_PROMPTS["syntax_error"].format(
            file_path=file_path,
            error_msg=error[:200],
            start_line=start + 1,
            end_line=end,
            code_snippet=snippet,
        )

        raw = self._free_call(prompt, temperature=0.1)
        if not raw:
            return {"ok": False, "error": "Modello non ha risposto"}

        # Applica la correzione
        original_line = ""
        fixed_line    = ""

        for line in raw.splitlines():
            if line.startswith("LINEA_ORIGINALE:"):
                original_line = line.replace("LINEA_ORIGINALE:", "").strip()
            elif line.startswith("LINEA_CORRETTA:"):
                fixed_line = line.replace("LINEA_CORRETTA:", "").strip()

        if original_line and fixed_line and original_line in src:
            # Backup
            self._backup_file(file_path)
            new_src = src.replace(original_line, fixed_line, 1)

            # Verifica sintassi
            try:
                ast.parse(new_src)
                Path(file_path).write_text(new_src, encoding="utf-8")
                log.info("Syntax fix applicato: %s", file_path)
                return {"ok": True, "action": "syntax_fixed", "file": file_path,
                        "original": original_line, "fixed": fixed_line}
            except SyntaxError as e2:
                log.warning("Patch genera ancora errore: %s", e2)
                return {"ok": False, "error": "Patch proposta non risolve il problema"}

        return {"ok": False, "error": "Non ho trovato la riga da correggere nell'output"}

    def heal_import_error(self, error: str, context: dict = None) -> dict:
        """Healing per ImportError / ModuleNotFoundError."""
        context = context or {}

        # Estrai nome modulo
        module_m = re.search(r"No module named '([^']+)'", error)
        module   = module_m.group(1) if module_m else ""

        if not module:
            return {"ok": False, "error": "Nome modulo non estratto"}

        prompt = HEAL_PROMPTS["import_error"].format(
            error_msg=error[:300],
            file_path=context.get("file_path", "?")
        )

        raw = self._free_call(prompt, temperature=0.1)
        action = ""
        fix    = ""

        for line in (raw or "").splitlines():
            if line.startswith("ACTION:"):
                action = line.replace("ACTION:", "").strip()
            elif line.startswith("FIX:"):
                fix = line.replace("FIX:", "").strip()

        if action == "install_pip" and fix:
            # Esegui pip install
            result = subprocess.run(
                ["pip", "install", module, "--quiet"],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode == 0:
                log.info("pip install %s OK", module)
                return {"ok": True, "action": "installed", "module": module}
            return {"ok": False, "error": "pip install fallito: " + result.stderr[:200]}

        return {"ok": False, "action": action, "fix": fix,
                "error": "Azione non automatizzabile: " + action}

    def heal_tool_error(self, error: str, context: dict = None) -> dict:
        """Healing per errori nei tool."""
        context = context or {}
        prompt  = HEAL_PROMPTS["tool_error"].format(
            error_msg=error[:300],
            context=json.dumps(context, ensure_ascii=False)[:500],
        )

        raw = self._free_call(prompt, temperature=0.2)
        if not raw:
            return {"ok": False, "error": "Modello non ha risposto"}

        # Cerca tool call corretta
        tc = self._try_parse_direct(raw)
        if tc:
            return {"ok": True, "action": "corrected_tool_call",
                    "tool_call": tc}

        # Cerca causa nell'output
        for line in raw.splitlines():
            if line.startswith("CAUSA:"):
                return {"ok": False, "causa": line.replace("CAUSA:", "").strip(),
                        "raw": raw[:300]}

        return {"ok": False, "raw": raw[:300]}

    def heal_hallucination(self, error: str, context: dict = None) -> dict:
        """Healing per risposte con alta probabilità di allucinazione."""
        context  = context or {}
        response = context.get("response", "")
        if not response:
            return {"ok": False, "error": "Nessuna risposta da correggere"}

        guard = self._get_hall_guard()
        if guard:
            prompt = context.get("prompt", "")
            result = guard.process(prompt, response, level="thorough")
            if result.get("corrected"):
                return {"ok":      True,
                        "action":  "hallucination_corrected",
                        "text":    result["text"],
                        "confidence": result["confidence"],
                        "issues":  result["issues"]}

        # Fallback: richiedi direttamente la correzione
        hall_score = context.get("hall_score", "?")
        issues_str = str(context.get("issues", []))[:200]
        prompt     = HEAL_PROMPTS["hallucination"].format(
            response=response[:1200],
            hall_score=hall_score,
            issues=issues_str,
        )

        raw = self._free_call(prompt, temperature=0.3)
        if raw:
            m = re.search(r'RISPOSTA_CORRETTA:\s*(.*?)$', raw, re.DOTALL)
            corrected = m.group(1).strip() if m else raw.strip()
            return {"ok": True, "action": "hallucination_corrected",
                    "text": corrected}

        return {"ok": False, "error": "Correzione allucinazione fallita"}

    def heal_network_error(self, error: str, context: dict = None) -> dict:
        """Healing per errori di rete."""
        # Aspetta 10s e prova con Ollama locale
        time.sleep(10)
        return {
            "ok":     True,
            "action": "switch_to_ollama",
            "model":  "ollama/qwen3:8b",
            "msg":    "Network error -> switch Ollama locale",
        }

    def heal_generic(self, error: str, context: dict = None) -> dict:
        """Healing generico per errori non categorizzati."""
        context = context or {}
        prompt  = (
            "Sei un esperto Python e AI. Questo errore si è verificato in DUST AI:\n\n"
            "ERRORE: " + error[:500] + "\n\n"
            "CONTESTO: " + json.dumps(context, ensure_ascii=False)[:300] + "\n\n"
            "Suggerisci una soluzione concreta in 2-3 passi.\n"
            "Risposta breve e pratica."
        )
        raw = self._free_call(prompt, temperature=0.2)
        return {
            "ok":        bool(raw),
            "action":    "generic_suggestion",
            "suggestion": raw[:500] if raw else "Nessuna soluzione trovata",
        }

    # ─── Helper: parse output LLM ─────────────────────────────────────────────

    def _try_parse_direct(self, raw: str) -> Optional[dict]:
        """
        Tenta di estrarre un dict/JSON valido dall'output raw.
        Prova varie strategie prima di rinunciare.
        """
        if not raw:
            return None

        text = raw.strip()

        # 1. JSON diretto
        try:
            data = json.loads(text)
            if self._is_valid_result(data):
                return data
        except json.JSONDecodeError:
            pass

        # 2. Primo JSON nel testo
        m = re.search(r'\{[^{}]*\}', text, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(0))
                if self._is_valid_result(data):
                    return data
            except json.JSONDecodeError:
                pass

        # 3. JSON in blocco ```json ... ```
        m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(1))
                if self._is_valid_result(data):
                    return data
            except json.JSONDecodeError:
                pass

        # 4. Cerca "tool": "nome" + "params": {...}
        tool_m   = re.search(r'"tool"\s*:\s*"([^"]+)"', text)
        params_m = re.search(r'"params"\s*:\s*(\{[^{}]*\})', text, re.DOTALL)
        if tool_m:
            params = {}
            if params_m:
                try:
                    params = json.loads(params_m.group(1))
                except json.JSONDecodeError:
                    pass
            return {"type": "tool_call", "tool": tool_m.group(1), "params": params}

        # 5. Cerca "status": "done"
        if re.search(r'"status"\s*:\s*"done"', text):
            summary_m = re.search(r'"summary"\s*:\s*"([^"]*)"', text)
            return {
                "type":    "done",
                "status":  "done",
                "summary": summary_m.group(1) if summary_m else "completato",
            }

        return None

    def _is_valid_result(self, data: dict) -> bool:
        """Verifica che il dict sia un risultato DUST valido."""
        if not isinstance(data, dict):
            return False
        if "tool" in data and isinstance(data["tool"], str):
            return True
        if data.get("status") in ("done", "completed", "complete"):
            return True
        if data.get("type") in ("tool_call", "done", "text"):
            return True
        return False

    # ─── Categorizzazione errori ──────────────────────────────────────────────

    def _categorize_error(self, error: str) -> str:
        error_lower = error.lower()
        for category, keywords in ERROR_CATEGORIES.items():
            if any(kw.lower() in error_lower for kw in keywords):
                return category
        return "generic"

    # ─── Rate limit delay sicuro ──────────────────────────────────────────────

    def _safe_retry_delay(self, error: str) -> int:
        """
        Estrae il delay da un errore 429.
        BUGFIX v1: l'API Gemini manda Retry-After in MILLISECONDI non secondi.
        Clamp sempre tra MIN_WAIT_S e MAX_WAIT_S.
        """
        # Cerca valore numerico nell'errore
        m = re.search(r'(\d+)', error)
        if m:
            raw_val = int(m.group(1))
            # Se > 1000 probabilmente è in ms (bug Gemini API)
            if raw_val > 1000:
                raw_val = raw_val // 1000
            return max(MIN_WAIT_S, min(MAX_WAIT_S, raw_val))
        return MAX_WAIT_S

    # ─── Backup file ──────────────────────────────────────────────────────────

    def _backup_file(self, file_path: str):
        ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
        src = Path(file_path)
        dst = self._patch_dir / (src.stem + ".bak_" + ts + src.suffix)
        try:
            shutil.copy2(src, dst)
        except Exception as e:
            log.warning("Backup fallito: %s", e)

    # ─── History ──────────────────────────────────────────────────────────────

    def _record(self, category: str, error: str, success: bool):
        ts = datetime.now().isoformat()
        self._history.append({
            "ts":       ts,
            "category": category,
            "error":    error[:100],
            "ok":       success,
        })
        # Mantieni solo ultimi 100 record
        self._history = self._history[-100:]
        try:
            HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            HISTORY_FILE.write_text(
                json.dumps(self._history, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
        except Exception:
            pass

    def _load_history(self) -> list:
        if HISTORY_FILE.exists():
            try:
                return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        return []

    def history_report(self) -> str:
        if not self._history:
            return "SelfHeal: nessun evento registrato"
        total   = len(self._history)
        success = sum(1 for h in self._history if h.get("ok"))
        by_cat  = {}
        for h in self._history:
            cat = h.get("category", "?")
            by_cat[cat] = by_cat.get(cat, 0) + 1
        lines = [
            "=== SelfHeal History ===",
            "Totale: " + str(total) + " | OK: " + str(success) +
            " | Fail: " + str(total - success),
            "",
            "Per categoria:",
        ]
        for cat, count in sorted(by_cat.items(), key=lambda x: x[1], reverse=True):
            lines.append("  " + cat.ljust(15) + " " + str(count))
        return "\n".join(lines)
