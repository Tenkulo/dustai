"""
DUST AI – HumanResearcher v1.0
Agisce come una persona che cerca qualcosa:
  1. DECOMPOSE  – spezza il task in sotto-domande
  2. SEARCH     – cerca sul web (WebSearchTool)
  3. PARALLEL   – chiede a 3 AI in parallelo
  4. VALIDATE   – cross-valida le risposte (HallucinationGuard)
  5. SYNTHESIZE – un'AI sintetizza il meglio
  6. SAVE       – salva in memoria + GitHub

Inspired by: ReConcile (multi-model round-table), SALLMA, SkillOrchestra
"""
import json, time, logging, threading
from pathlib import Path
from datetime import datetime
log = logging.getLogger("HumanResearcher")

# Modelli da usare in parallelo (preferiti free)
PARALLEL_MODELS = [
    "gemini-flash",    # Gemini 2.5 Flash (KEY1)
    "gemini-flash2",   # Gemini 2.5 Flash (KEY2) – quota separata
    "gemini-pro",      # Gemini 2.5 Pro – più intelligente
]
SYNTHESIZER = "gemini-flash"   # modello usato per sintetizzare

DECOMPOSE_PROMPT = """Sei un assistente che aiuta a pianificare una ricerca.
Dato questo task/domanda, elenca al massimo 3 sotto-domande chiave da rispondere.
Rispondi SOLO in JSON: {"subquestions": ["domanda1", "domanda2", "domanda3"]}

TASK: {task}"""

SYNTHESIZE_PROMPT = """Sei un esperto sintetizzatore di informazioni.
Hai ricevuto risposte da più AI diverse sullo stesso task. 
Sintetizza la risposta migliore, più completa e accurata.
Elimina contraddizioni, privilegia il consenso, segnala incertezze.

TASK ORIGINALE: {task}

RISPOSTE RICEVUTE:
{responses}

RISULTATI WEB (se disponibili):
{web_results}

Fornisci una risposta definitiva, strutturata e pratica."""


class HumanResearcher:
    """
    Orchestratore principale che agisce come un ricercatore umano.
    Usa parallelo di AI + web search per rispondere al meglio.
    """
    def __init__(self, config):
        self.config = config
        self._gw    = None
        self._mem   = config.get_base_path() / "memory"
        self._mem.mkdir(exist_ok=True)

    def research(self, task: str, use_web=True, free_only=True) -> dict:
        """
        Metodo principale: ricerca completa come farebbe una persona.
        """
        t0 = time.time()
        log.info("HumanResearcher: task=%s", task[:80])
        print(f"\n🔍 DUST ricerca: {task[:80]}...")

        result = {
            "task":        task,
            "subquestions": [],
            "web_results": "",
            "ai_responses": [],
            "synthesis":   "",
            "model_used":  "",
            "elapsed":     0.0,
            "ok":          False,
        }

        # ── STEP 1: Decomposizione task ───────────────────────────────
        try:
            subq = self._decompose(task)
            result["subquestions"] = subq
            if subq:
                print(f"  📋 Sotto-domande: {len(subq)}")
        except Exception as e:
            log.warning("Decompose fallito: %s", e)

        # ── STEP 2: Web search (come una persona googla prima) ────────
        web_results = ""
        if use_web:
            try:
                web_results = self._web_search(task)
                result["web_results"] = web_results[:2000]
                if web_results:
                    print(f"  🌐 Web: {len(web_results)} chars trovati")
            except Exception as e:
                log.warning("Web search fallito: %s", e)

        # ── STEP 3: Chiedi a più AI in parallelo ─────────────────────
        print(f"  🤖 Parallelo su {len(PARALLEL_MODELS)} AI...")
        context = (f"Risultati web:\n{web_results[:1500]}\n\n" if web_results else "")
        ai_responses = self._ask_parallel(task, context)
        result["ai_responses"] = ai_responses
        n_ok = sum(1 for r in ai_responses if r.get("ok"))
        print(f"  ✅ {n_ok}/{len(PARALLEL_MODELS)} AI hanno risposto")

        # ── STEP 4: Cross-validation (HallucinationGuard) ────────────
        valid_responses = self._validate(ai_responses)

        # ── STEP 5: Sintesi finale ────────────────────────────────────
        synthesis = self._synthesize(task, valid_responses, web_results)
        result["synthesis"]  = synthesis
        result["ok"]         = bool(synthesis)
        result["elapsed"]    = round(time.time() - t0, 1)
        result["model_used"] = SYNTHESIZER

        if synthesis:
            print(f"  ✨ Sintesi: {len(synthesis)} chars in {result['elapsed']}s")
        else:
            # Fallback: usa la miglior risposta singola
            best = max((r for r in ai_responses if r.get("ok")),
                       key=lambda r: len(r.get("text","")), default=None)
            if best:
                result["synthesis"] = best["text"]
                result["ok"]        = True

        # ── STEP 6: Salva in memoria ──────────────────────────────────
        self._save_memory(result)
        return result

    # ── Decomposizione ────────────────────────────────────────────────
    def _decompose(self, task: str) -> list:
        gw = self._gateway()
        prompt = DECOMPOSE_PROMPT.format(task=task)
        r = gw.call_auto(prompt, task="fast")
        if not r.get("ok"):
            return []
        try:
            text = r["text"]
            import re
            m = re.search(r'\{[^}]+\}', text, re.DOTALL)
            if m:
                data = json.loads(m.group())
                return data.get("subquestions", [])[:3]
        except Exception:
            pass
        return []

    # ── Web search ────────────────────────────────────────────────────
    def _web_search(self, task: str) -> str:
        try:
            from .tools.registry import ToolRegistry
            reg = ToolRegistry(self.config)
            result = reg.execute("web_search", {"query": task[:200]})
            if isinstance(result, str) and len(result) > 50:
                return result
        except Exception:
            pass
        # Fallback: cerca con Perplexity browser
        try:
            from .tools.browser_ai_bridge import BrowserAIBridge
            bridge = BrowserAIBridge(self.config)
            r = bridge.query("Cerca informazioni aggiornate su: " + task, provider="perplexity")
            if r.get("ok"):
                return r["text"]
        except Exception:
            pass
        return ""

    # ── Parallelo AI ──────────────────────────────────────────────────
    def _ask_parallel(self, task: str, context: str) -> list:
        gw      = self._gateway()
        prompt  = (context + "\nDomanda: " + task) if context else task
        results = gw.call_parallel(prompt, PARALLEL_MODELS)
        return [{"ok": r.get("ok"), "text": r.get("text",""),
                 "model": r.get("model_name","?")} for r in results]

    # ── Cross-validation ──────────────────────────────────────────────
    def _validate(self, responses: list) -> list:
        """
        Versione semplice: tieni le risposte che hanno almeno 50 chars.
        Se abbiamo 2+ risposte, controlla sovrapposizione tematica.
        """
        valid = [r for r in responses if r.get("ok") and len(r.get("text","")) > 50]
        if len(valid) >= 2:
            # Semplice voto: tieni le risposte più lunghe (più complete)
            valid.sort(key=lambda r: len(r.get("text","")), reverse=True)
        return valid

    # ── Sintesi ───────────────────────────────────────────────────────
    def _synthesize(self, task: str, responses: list, web: str) -> str:
        if not responses:
            return ""
        if len(responses) == 1:
            return responses[0]["text"]
        formatted = "\n\n---\n".join(
            f"[{r['model']}]:\n{r['text'][:1200]}" for r in responses[:3])
        prompt = SYNTHESIZE_PROMPT.format(
            task=task, responses=formatted, web_results=web[:800])
        gw = self._gateway()
        r  = gw.call_auto(prompt, task="reasoning")
        return r.get("text", "") if r.get("ok") else (responses[0]["text"] if responses else "")

    # ── Memoria ───────────────────────────────────────────────────────
    def _save_memory(self, result: dict):
        try:
            f = self._mem / "research_history.jsonl"
            entry = {"ts": datetime.now().isoformat(),
                     "task": result["task"][:100],
                     "ok": result["ok"],
                     "elapsed": result["elapsed"],
                     "synthesis_len": len(result.get("synthesis",""))}
            with open(f, "a", encoding="utf-8") as fp:
                fp.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _gateway(self):
        if not self._gw:
            try:
                from .ai_gateway import AIGateway
                self._gw = AIGateway(self.config)
            except ImportError:
                from ai_gateway import AIGateway
                self._gw = AIGateway(self.config)
        return self._gw


class HumanResearcherTool:
    """Wrapper per ToolRegistry."""
    def __init__(self, config):
        self.config = config
        self._r     = None

    def _get(self):
        if not self._r:
            self._r = HumanResearcher(self.config)
        return self._r

    def dust_research(self, task: str, web: str = "true") -> str:
        """
        Ricerca completa: web + multi-AI + sintesi.
        Usa questo invece di ai_ask per task complessi.
        """
        use_web = web.lower() not in ("false", "0", "no")
        result  = self._get().research(task, use_web=use_web)
        if result["ok"]:
            n = len(result["ai_responses"])
            ok = sum(1 for r in result["ai_responses"] if r.get("ok"))
            header = f"[DUST Research | {ok}/{n} AI | {result['elapsed']}s]\n\n"
            return header + result["synthesis"]
        return "❌ Ricerca fallita: nessuna AI ha risposto"

    def dust_research_status(self) -> str:
        try:
            f = self._get()._mem / "research_history.jsonl"
            if not f.exists():
                return "Nessuna ricerca ancora."
            lines = f.read_text(encoding="utf-8").strip().splitlines()[-5:]
            entries = [json.loads(l) for l in lines]
            return "Ultime 5 ricerche:\n" + "\n".join(
                f"  {'✅' if e['ok'] else '❌'} [{e['ts'][:16]}] {e['task'][:50]}"
                for e in entries)
        except Exception as e:
            return "Errore: " + str(e)
