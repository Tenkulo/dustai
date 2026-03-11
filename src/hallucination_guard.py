"""
DUST AI – HallucinationGuard v2.0
Sistema anti-allucinazione basato su ricerca scientifica 2025-2026.

Fonti:
  - Darwish et al. 2025: multi-agent framework -> 85.5% improvement in consistency
  - Lakera 2026: prompt-based mitigation 53%->23% hallucination rate
  - MDPI Taxonomy 2025: 6 categorie (Training, Architecture, Prompt Opt,
      Post-Gen QC, Interpretability, Agent-Based Orchestration)
  - THaMES 2024: Chain-of-Verification (CoV) + RAG + layered pipelines
  - Survey Li et al. Oct 2025: RAG + reasoning + agentic systems come paradigmi primari

Strategie implementate (TUTTE GRATUITE – solo Gemini Free + Ollama):
  1. PROMPT HARDENING     – system prompt anti-allucinazione + "say I don't know"
  2. CHAIN-OF-VERIFICATION– il modello verifica le proprie affermazioni
  3. CROSS-VALIDATION     – stessa domanda a 2 modelli, check accordo
  4. CONFIDENCE SCORING   – punteggio di confidenza da 0-100 per ogni risposta
  5. FACT ANCHORING       – grounding a fatti verificabili nel contesto
  6. SELF-REFLECTION LOOP – il modello si critica e migliora la risposta
  7. HALLUCINATION DETECTION – pattern matching + LLM-judge per rilevare allucinazioni
  8. UNCERTAINTY SIGNALING– segnala dubbi invece di inventare

Tutti i modelli usati: gemini-2.5-flash (free), gemini-2.5-flash-lite (free), ollama/qwen3:8b
"""

import re
import json
import logging
import time
from pathlib import Path
from datetime import datetime
from typing import Optional

log = logging.getLogger("HallucinationGuard")

# ─── Pattern che segnalano possibili allucinazioni ────────────────────────────
# Basato su MDPI Taxonomy 2025 + empirical patterns

HALLUCINATION_PATTERNS = [
    # Eccessiva certezza su dati non verificabili
    (r'\b(certamente|sicuramente|assolutamente|senza dubbio)\b', 0.3,
     "overconfidence"),
    # Citazioni/riferimenti inventati
    (r'(secondo|come dice|cita|riferisce)\s+[A-Z][a-z]+\s+\(\d{4}\)', 0.4,
     "suspicious_citation"),
    # Numeri molto precisi senza fonte
    (r'\b\d{1,3}[.,]\d{3}[.,]\d{3}\b', 0.2, "unverified_precise_number"),
    # URL inventati
    (r'https?://[^\s]+\.(com|org|it|ai)/[^\s]{10,}', 0.3, "unverified_url"),
    # Contraddizioni interne (stesso testo dice A poi non-A)
    (r'\b(tuttavia|al contrario|invece|però)\b.*\b(ho detto|afferma|sostiene)\b', 0.2,
     "potential_contradiction"),
    # Frasi vaghe che mascherano incertezza
    (r'\b(alcuni|molti|vari|certi)\s+(esperti|studi|ricerche)\b', 0.2,
     "vague_attribution"),
    # Claims su eventi futuri presentati come certi
    (r'\b(sarà|verrà|accadrà|avverrà)\b.{0,50}\b(sicuramente|certamente|di certo)\b', 0.3,
     "false_future_certainty"),
]

# ─── System prompt hardening (Lakera 2026 + THaMES best practices) ────────────
ANTI_HALLUCINATION_SYSTEM = """
Sei un assistente AI preciso e onesto. Segui SEMPRE queste regole anti-allucinazione:

1. SE NON SAI: dì esplicitamente "Non lo so" o "Non ho informazioni sufficienti su questo".
   Non inventare MAI fatti, citazioni, numeri, URL o nomi.

2. DISTINGUI chiaramente:
   - Fatto verificato: "X è confermato"
   - Inferenza: "Probabilmente X, basandomi su Y"
   - Incertezza: "Non sono sicuro, ma potrebbe essere X"

3. CITA LE FONTI: se fai un'affermazione specifica, indica da dove viene.
   Se non hai fonte, usa "stimo che..." o "mi sembra che...".

4. NUMERI E DATE: usa solo valori che conosci con certezza.
   Per valori incerti: "circa", "all'incirca", "stima approssimativa".

5. CONSISTENZA: controlla che la tua risposta non si contraddica internamente.

6. ASTIENITI piuttosto che allucinare: è meglio dire "non so" che dare informazioni false.
"""

CONFIDENCE_PROMPT_SUFFIX = """

---
ISTRUZIONE AGGIUNTIVA:
Alla fine della tua risposta aggiungi OBBLIGATORIAMENTE una riga:
CONFIDENCE: [0-100] | UNCERTAIN_PARTS: [elenco parti incerte, o "nessuna"]

Esempio: CONFIDENCE: 85 | UNCERTAIN_PARTS: anno esatto dell'evento
"""

COV_PROMPT = """
Hai appena generato questa risposta:
{response}

Ora esegui una CHAIN-OF-VERIFICATION (CoV):
1. Elenca le 3-5 affermazioni principali della risposta
2. Per ognuna: è verificabile? da cosa la sai?
3. Indica quali parti potrebbero essere imprecise o inventate
4. Scrivi una versione corretta e più cauta della risposta originale

Formato output:
CLAIMS:
- [affermazione] -> [verificabile: sì/no/incerto] -> [fonte o "stima"]

REVISED_RESPONSE:
[versione corretta]

CONFIDENCE: [0-100]
"""

REFLECTION_PROMPT = """
Revisiona criticamente questa risposta AI:
{response}

La risposta contiene:
- Fatti inventati o non verificabili?
- Citazioni o numeri sospetti?
- Contraddizioni interne?
- Linguaggio troppo sicuro su cose incerte?

Rispondi con:
HALLUCINATION_SCORE: [0-10] (0=nessuna, 10=grave)
ISSUES: [lista problemi trovati, o "nessuno"]
IMPROVED: [risposta migliorata, più cauta e accurata]
"""


class HallucinationGuard:
    """
    Sistema completo di mitigazione allucinazioni.
    Usa SOLO modelli gratuiti: Gemini Flash Free + Ollama.
    """

    def __init__(self, config, gateway=None):
        self.config  = config
        self.gateway = gateway  # AIGateway (lazy init se None)
        self._log_dir = config.get_base_path() / "logs"
        self._log_dir.mkdir(exist_ok=True)
        self._hall_log = self._log_dir / "hallucination_log.jsonl"
        self._stats    = {"total": 0, "flagged": 0, "corrected": 0}

    # ─── Modelli gratuiti disponibili ─────────────────────────────────────────

    FREE_MODELS = [
        "gemini/gemini-2.5-flash",        # primario (free, 1500/day)
        "gemini/gemini-2.5-flash-lite",   # secondario (free, 3000/day)
        "ollama/qwen3:8b",                # locale, sempre disponibile
    ]

    def _free_call(self, prompt: str, system: str = "",
                   model_idx: int = 0) -> str:
        """Chiama un modello gratuito. Fallback automatico."""
        if not self.gateway:
            self._init_gateway()

        models = self.FREE_MODELS[model_idx:]
        for model_id in models:
            try:
                result = self.gateway.call(model_id, prompt, system=system,
                                           max_tokens=1500, temperature=0.3)
                if result.get("ok") and result.get("text"):
                    return result["text"]
            except Exception as e:
                log.warning("free_call %s: %s", model_id, str(e)[:80])
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

    # ─── API pubblica ──────────────────────────────────────────────────────────

    def process(self, prompt: str, response: str,
                level: str = "standard") -> dict:
        """
        Pipeline principale di mitigazione.

        level:
          "fast"     – solo pattern detection + confidence score (0 chiamate extra)
          "standard" – pattern + CoV su Gemini Free (1 chiamata extra)
          "thorough" – pattern + CoV + cross-validation + reflection (3 chiamate extra)

        Ritorna:
          {"ok": True, "text": str, "confidence": int, "flagged": bool,
           "issues": list, "corrected": bool, "original": str}
        """
        self._stats["total"] += 1
        result = {
            "original":  response,
            "text":      response,
            "confidence": 80,
            "flagged":   False,
            "issues":    [],
            "corrected": False,
            "level":     level,
        }

        # 1. Pattern detection (zero costo)
        pattern_issues = self._pattern_detection(response)
        if pattern_issues:
            result["flagged"] = True
            result["issues"]  = pattern_issues
            # Abbassa confidence in base ai pattern trovati
            penalty = sum(p["penalty"] for p in pattern_issues)
            result["confidence"] = max(10, 80 - int(penalty * 100))
            log.info("Pattern issues: %d (penalty %.2f)", len(pattern_issues), penalty)

        if level == "fast":
            if result["flagged"]:
                self._stats["flagged"] += 1
                self._log(prompt, response, result)
            return result

        # 2. Chain-of-Verification su Gemini Free
        cov_result = self._chain_of_verification(response)
        if cov_result:
            result["confidence"]  = min(result["confidence"],
                                        cov_result.get("confidence", 80))
            if cov_result.get("revised"):
                result["text"]      = cov_result["revised"]
                result["corrected"] = True
            result["issues"] += cov_result.get("issues", [])
            result["cov"]     = cov_result

        if level == "standard":
            if result["flagged"] or result["corrected"]:
                self._stats["flagged" if result["flagged"] else "corrected"] += 1
            self._log(prompt, response, result)
            return result

        # 3. Cross-validation (thorough only): stessa domanda a modello diverso
        if level == "thorough":
            cross = self._cross_validate(prompt, result["text"])
            if cross:
                result["cross_validation"] = cross
                if cross.get("agreement") < 0.5:
                    result["flagged"]    = True
                    result["confidence"] = min(result["confidence"],
                                               int(cross["agreement"] * 100))
                    result["issues"].append({
                        "type":    "cross_validation_mismatch",
                        "penalty": 0.4,
                        "detail":  "Le due AI hanno dato risposte significativamente diverse",
                    })
                    # Usa sintesi come testo finale
                    if cross.get("synthesis"):
                        result["text"]      = cross["synthesis"]
                        result["corrected"] = True

            # 4. Self-reflection finale
            reflection = self._self_reflect(result["text"])
            if reflection:
                result["reflection"] = reflection
                hall_score = reflection.get("hallucination_score", 0)
                if hall_score >= 4:
                    result["flagged"] = True
                    result["confidence"] = min(result["confidence"],
                                               max(10, 100 - hall_score * 10))
                    if reflection.get("improved"):
                        result["text"]      = reflection["improved"]
                        result["corrected"] = True

        if result["flagged"]:
            self._stats["flagged"] += 1
        if result["corrected"]:
            self._stats["corrected"] += 1

        self._log(prompt, response, result)
        return result

    def harden_prompt(self, prompt: str,
                      add_confidence: bool = False) -> str:
        """
        Aggiunge istruzioni anti-allucinazione al prompt.
        Strategia: Prompt Hardening (Lakera 2026 + MDPI Taxonomy 2025).
        """
        hardened = ANTI_HALLUCINATION_SYSTEM + "\n\n" + prompt
        if add_confidence:
            hardened += CONFIDENCE_PROMPT_SUFFIX
        return hardened

    def score_response(self, response: str) -> dict:
        """
        Assegna un punteggio di affidabilità alla risposta (0-100).
        Zero costo (solo analisi locale).
        """
        score     = 80  # baseline
        issues    = []
        penalties = 0.0

        # Pattern detection
        for pattern_issues in [self._pattern_detection(response)]:
            for issue in pattern_issues:
                penalties += issue["penalty"]
                issues.append(issue)

        # Lunghezza: risposte molto corte o molto lunghe sono sospette
        words = len(response.split())
        if words < 10:
            penalties += 0.3
            issues.append({"type": "too_short", "penalty": 0.3,
                            "detail": "Risposta troppo breve"})
        elif words > 2000:
            penalties += 0.1
            issues.append({"type": "very_long", "penalty": 0.1,
                            "detail": "Risposta molto lunga - verifica accuratezza"})

        # Frasi fatte dell'AI
        ai_cliches = ["come AI", "come modello linguistico", "non posso avere opinioni",
                      "come assistente virtuale", "sono progettato per"]
        for cliche in ai_cliches:
            if cliche.lower() in response.lower():
                penalties += 0.1
                issues.append({"type": "ai_cliche", "penalty": 0.1,
                                "detail": "Frase standard AI non informativa"})

        score = max(5, int(score - penalties * 80))
        return {
            "score":   score,
            "grade":   "A" if score >= 85 else "B" if score >= 70 else "C" if score >= 50 else "D",
            "issues":  issues,
            "flagged": len(issues) > 0,
        }

    # ─── Strategie interne ────────────────────────────────────────────────────

    def _pattern_detection(self, text: str) -> list:
        """Rileva pattern di allucinazione nel testo (zero costo)."""
        issues = []
        for pattern, penalty, issue_type in HALLUCINATION_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                issues.append({
                    "type":    issue_type,
                    "penalty": penalty,
                    "matches": matches[:3],
                    "detail":  "Pattern sospetto rilevato: " + issue_type,
                })
        return issues

    def _chain_of_verification(self, response: str) -> Optional[dict]:
        """
        Chain-of-Verification (CoV) – THaMES 2024 / ACL.
        Chiama Gemini Free per verificare le affermazioni principali.
        """
        prompt = COV_PROMPT.format(response=response[:1500])
        try:
            raw = self._free_call(prompt, model_idx=0)
            if not raw:
                return None
            return self._parse_cov_output(raw)
        except Exception as e:
            log.warning("CoV fallita: %s", str(e)[:80])
            return None

    def _parse_cov_output(self, raw: str) -> dict:
        result = {"confidence": 80, "issues": [], "revised": ""}

        # Estrai confidence
        m = re.search(r'CONFIDENCE:\s*(\d+)', raw, re.IGNORECASE)
        if m:
            result["confidence"] = min(100, max(0, int(m.group(1))))

        # Estrai risposta rivista
        m = re.search(r'REVISED_RESPONSE:\s*(.*?)(?=CONFIDENCE:|$)',
                      raw, re.DOTALL | re.IGNORECASE)
        if m:
            revised = m.group(1).strip()
            if len(revised) > 50:
                result["revised"] = revised

        # Cerca claims non verificabili
        claims_block = re.search(r'CLAIMS:(.*?)(?=REVISED_RESPONSE:|CONFIDENCE:|$)',
                                 raw, re.DOTALL | re.IGNORECASE)
        if claims_block:
            for line in claims_block.group(1).splitlines():
                if "no" in line.lower() or "incerto" in line.lower():
                    result["issues"].append({
                        "type":    "unverified_claim_cov",
                        "penalty": 0.2,
                        "detail":  line.strip()[:100],
                    })

        return result

    def _cross_validate(self, prompt: str, response: str) -> Optional[dict]:
        """
        Cross-validation: chiede a un secondo modello gratuito (Ollama)
        di rispondere allo stesso prompt e confronta.
        Ispirato a Darwish et al. 2025 multi-agent framework (85.5% consistency).
        """
        try:
            # Usa Ollama come secondo modello (sempre free, locale)
            result2 = self.gateway.call("ollama/qwen3:8b", prompt,
                                        max_tokens=800, temperature=0.3)
            if not result2.get("ok") or not result2.get("text"):
                return None

            response2 = result2["text"]

            # Misura accordo semantico
            agreement = self._semantic_overlap(response, response2)

            out = {"agreement": agreement, "response2": response2}

            if agreement < 0.4:
                # Divergenza significativa: sintetizza con Gemini
                synth_prompt = (
                    "Due AI hanno risposto diversamente alla stessa domanda.\n\n"
                    "DOMANDA: " + prompt[:400] + "\n\n"
                    "RISPOSTA A:\n" + response[:600] + "\n\n"
                    "RISPOSTA B:\n" + response2[:600] + "\n\n"
                    "Analizza le differenze e scrivi una risposta UNIFICATA e ACCURATA. "
                    "Dove le risposte divergono su fatti, scegli quella più cauta e verificabile. "
                    "Segna le parti incerte con [INCERTO]."
                )
                synth_raw = self._free_call(synth_prompt, model_idx=0)
                if synth_raw:
                    out["synthesis"] = synth_raw

            return out

        except Exception as e:
            log.warning("Cross-validate: %s", str(e)[:80])
            return None

    def _self_reflect(self, response: str) -> Optional[dict]:
        """
        Self-reflection loop – Lakera 2026 / MDPI survey.
        Il modello si auto-critica e produce una versione migliorata.
        """
        prompt = REFLECTION_PROMPT.format(response=response[:1200])
        try:
            raw = self._free_call(prompt, model_idx=0)
            if not raw:
                return None
            return self._parse_reflection(raw)
        except Exception as e:
            log.warning("Self-reflect: %s", str(e)[:80])
            return None

    def _parse_reflection(self, raw: str) -> dict:
        result = {"hallucination_score": 0, "issues": [], "improved": ""}

        m = re.search(r'HALLUCINATION_SCORE:\s*(\d+)', raw, re.IGNORECASE)
        if m:
            result["hallucination_score"] = min(10, int(m.group(1)))

        m = re.search(r'ISSUES:\s*(.*?)(?=IMPROVED:|$)', raw, re.DOTALL | re.IGNORECASE)
        if m:
            issues_text = m.group(1).strip()
            if issues_text.lower() not in ("nessuno", "none", "nessuna"):
                for line in issues_text.splitlines():
                    line = line.strip().lstrip("-•*").strip()
                    if line:
                        result["issues"].append({"type": "reflection", "detail": line[:100]})

        m = re.search(r'IMPROVED:\s*(.*?)$', raw, re.DOTALL | re.IGNORECASE)
        if m:
            improved = m.group(1).strip()
            if len(improved) > 50:
                result["improved"] = improved

        return result

    def _semantic_overlap(self, text1: str, text2: str) -> float:
        """Misura sovrapposizione semantica tra due testi (zero costo)."""
        stopwords = {"il","lo","la","i","gli","le","un","uno","una","di","a",
                     "da","in","con","su","per","tra","fra","e","o","che","non",
                     "the","a","an","is","are","and","or","but","in","on","at","to"}
        def kw(text):
            return {w.lower() for w in re.findall(r'\b\w{4,}\b', text)
                    if w.lower() not in stopwords}
        k1, k2 = kw(text1), kw(text2)
        if not k1 or not k2:
            return 0.5
        intersection = k1 & k2
        union        = k1 | k2
        return len(intersection) / len(union)

    # ─── Logging ──────────────────────────────────────────────────────────────

    def _log(self, prompt: str, original: str, result: dict):
        entry = {
            "ts":         datetime.now().isoformat(),
            "prompt":     prompt[:200],
            "confidence": result.get("confidence"),
            "flagged":    result.get("flagged"),
            "corrected":  result.get("corrected"),
            "n_issues":   len(result.get("issues", [])),
            "issues":     [i.get("type") for i in result.get("issues", [])],
        }
        try:
            with open(self._hall_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def stats(self) -> str:
        total    = self._stats["total"]
        flagged  = self._stats["flagged"]
        corrected = self._stats["corrected"]
        if total == 0:
            return "HallucinationGuard: nessuna risposta processata"
        return (
            "=== HallucinationGuard Stats ===\n"
            "Risposte processate: " + str(total) + "\n"
            "Flaggate (sospette): " + str(flagged) +
            " (" + str(round(flagged / total * 100)) + "%)\n"
            "Corrette automaticamente: " + str(corrected) +
            " (" + str(round(corrected / total * 100)) + "%)\n"
            "Tasso affidabilità: " + str(round((1 - flagged / total) * 100)) + "%"
        )
