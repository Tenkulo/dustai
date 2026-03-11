"""
DUST AI – SelfImprovementLoop v1.0
Il cuore dell'autonomia a lungo termine.

Ciclo:
  1. EVALUATE  - analizza log + profilo + errori ricorrenti
  2. DIAGNOSE  - identifica i 3 punti deboli più impattanti
  3. PLAN      - genera piano di miglioramento (codice / prompt / config)
  4. PATCH     - applica le patch con verifica AST
  5. TEST      - esegue task di benchmark per misurare miglioramento
  6. COMMIT    - salva in self_profile.json + skill library
  7. REPEAT    - schedula prossimo ciclo

Triggering:
  - Automatico dopo ogni 10 task completati
  - Manuale da GUI: pulsante "Auto-Improve"
  - Da TaskQueue: task con source="self_improvement"
"""
import json
import logging
import ast
import re
import time
from pathlib import Path
from datetime import datetime
from typing import Optional

log = logging.getLogger("SelfImprovement")


class SelfImprovementLoop:

    IMPROVEMENT_INTERVAL_TASKS = 10   # ogni N task completati
    MAX_PATCH_FILES_PER_CYCLE  = 3    # max file modificati per ciclo
    BENCHMARK_TASKS = [
        "Crea un file test.txt sul Desktop con contenuto 'DUST_BENCHMARK_OK'",
        "Elenca i processi in esecuzione e salvali in A:\\dustai_stuff\\memory\\procs.txt",
        "Cerca su web 'python list files windows' e salva il primo risultato",
    ]

    def __init__(self, config, agent, memory, skill_forge, debug_system=None):
        self.config       = config
        self.agent        = agent
        self.memory       = memory
        self.skill_forge  = skill_forge
        self.debug        = debug_system
        self._gemini      = agent._gemini_model
        self._improvement_file = config.get_profiles_dir() / "improvement_history.json"
        self._history     = self._load_history()
        self._task_count  = 0

    # ─── Trigger ─────────────────────────────────────────────────────────────

    def on_task_complete(self, task: str, success: bool):
        """Chiamato dall'agent dopo ogni task. Triggera ciclo ogni N task."""
        self._task_count += 1
        if self._task_count >= self.IMPROVEMENT_INTERVAL_TASKS:
            self._task_count = 0
            log.info("SelfImprovement: trigger automatico dopo " +
                     str(self.IMPROVEMENT_INTERVAL_TASKS) + " task")
            return self.run_cycle()
        return None

    # ─── Ciclo principale ─────────────────────────────────────────────────────

    def run_cycle(self) -> dict:
        """Esegui un ciclo completo di auto-miglioramento."""
        cycle_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        log.info("SelfImprovement ciclo: " + cycle_id)
        print("\n🧠 Auto-miglioramento avviato [" + cycle_id + "]")

        result = {
            "cycle_id":    cycle_id,
            "started_at":  datetime.now().isoformat(),
            "phases":      {},
            "patches":     [],
            "benchmark":   {},
            "net_gain":    0.0,
        }

        try:
            # 1. Valutazione
            evaluation = self._phase_evaluate()
            result["phases"]["evaluate"] = evaluation
            print("  📊 Valutazione: " + str(len(evaluation.get("weaknesses", []))) + " punti deboli")

            if not evaluation.get("weaknesses"):
                print("  ✅ Nessun punto debole critico. Ciclo saltato.")
                return result

            # 2. Piano di miglioramento
            plan = self._phase_plan(evaluation)
            result["phases"]["plan"] = plan
            print("  📋 Piano: " + str(len(plan.get("improvements", []))) + " miglioramenti")

            # 3. Applica patch
            patches = self._phase_patch(plan)
            result["patches"] = patches
            ok_patches = [p for p in patches if p.get("applied")]
            print("  🔧 Patch: " + str(len(ok_patches)) + "/" + str(len(patches)) + " applicate")

            # 4. Benchmark
            benchmark = self._phase_benchmark()
            result["benchmark"] = benchmark
            print("  🏁 Benchmark: " + str(benchmark.get("success_rate", 0)) + "% successo")

            # 5. Salva risultati
            result["completed_at"] = datetime.now().isoformat()
            result["net_gain"]     = benchmark.get("success_rate", 0) - evaluation.get("baseline_score", 0)
            self._save_cycle(result)

            # 6. Aggiorna self_profile
            self.memory.update_profile(
                task="self_improvement_cycle",
                success=result["net_gain"] >= 0,
            )

            print("  ✅ Ciclo completato. Net gain: " + str(round(result["net_gain"], 1)) + "%")
            return result

        except Exception as e:
            log.error("SelfImprovement ciclo error: " + str(e))
            result["error"] = str(e)
            return result

    # ─── Fase 1: Valutazione ─────────────────────────────────────────────────

    def _phase_evaluate(self) -> dict:
        """Analizza log, profilo e errori per identificare debolezze."""
        if not self._gemini:
            return self._heuristic_evaluate()

        profile   = self.memory.get_profile()
        log_stats = self._read_log_stats()
        prompt    = self._build_eval_prompt(profile, log_stats)

        try:
            resp  = self._gemini.generate_content(prompt)
            clean = re.sub(r"```json\s*|```\s*", "", resp.text.strip()).strip()
            data  = json.loads(clean)
            data["baseline_score"] = log_stats.get("success_rate", 50.0)
            return data
        except Exception as e:
            log.warning("Evaluate LLM error: " + str(e))
            return self._heuristic_evaluate()

    def _heuristic_evaluate(self) -> dict:
        """Valutazione euristica senza LLM."""
        log_stats = self._read_log_stats()
        return {
            "baseline_score": log_stats.get("success_rate", 50.0),
            "weaknesses": [
                {"area": "tool_calling", "severity": "high",
                 "evidence": "parse_fails=" + str(log_stats.get("parse_fails", 0))}
            ] if log_stats.get("parse_fails", 0) > 2 else [],
            "strengths": ["sys_exec"],
        }

    def _build_eval_prompt(self, profile: dict, log_stats: dict) -> str:
        return (
            "Sei il modulo di auto-valutazione di DUST AI.\n"
            "Analizza questi dati e identifica i 3 punti deboli più impattanti.\n\n"
            "## Profilo agente\n" + json.dumps(profile, ensure_ascii=False)[:800] + "\n\n"
            "## Statistiche log (ultimi 7 giorni)\n" +
            json.dumps(log_stats, ensure_ascii=False)[:600] + "\n\n"
            "## Obiettivi DUST AI\n"
            "1. Tool calling sempre funzionante (Gemini + Ollama)\n"
            "2. Zero loop infiniti da parse fail\n"
            "3. Task di filesystem completati al 100%\n"
            "4. Ricerche web accurate con budget Perplexity rispettato\n"
            "5. Vision tool attivo per GUI automation\n\n"
            "Rispondi SOLO con JSON:\n"
            "{\n"
            '  "baseline_score": 72.5,\n'
            '  "weaknesses": [\n'
            '    {"area": "nome_area", "severity": "high|medium|low",\n'
            '     "evidence": "dati specifici", "fix_type": "prompt|code|config"}\n'
            "  ],\n"
            '  "strengths": ["area1", "area2"],\n'
            '  "priority_fix": "area più urgente da correggere"\n'
            "}"
        )

    # ─── Fase 2: Piano ────────────────────────────────────────────────────────

    def _phase_plan(self, evaluation: dict) -> dict:
        """Genera piano concreto di miglioramento."""
        if not self._gemini:
            return {"improvements": []}

        weaknesses = evaluation.get("weaknesses", [])[:3]
        src_root   = Path(__file__).parent.parent

        # Raccoglie snippet di codice rilevanti
        code_ctx = self._collect_code_context(weaknesses, src_root)

        prompt = (
            "Sei il modulo di pianificazione auto-miglioramento di DUST AI.\n"
            "Genera miglioramenti concreti per questi punti deboli.\n\n"
            "## Punti deboli\n" + json.dumps(weaknesses, ensure_ascii=False) + "\n\n"
            "## Codice rilevante\n" + code_ctx[:3000] + "\n\n"
            "## Regole\n"
            "- Python 3.11+: NO backslash dentro {} nelle f-string\n"
            "- Ogni patch deve essere atomica (find→replace su un file)\n"
            "- Max " + str(self.MAX_PATCH_FILES_PER_CYCLE) + " file modificati\n"
            "- Priorità: fix > ottimizzazione > nuova feature\n\n"
            "Rispondi SOLO con JSON:\n"
            "{\n"
            '  "improvements": [\n'
            '    {\n'
            '      "id": "fix_001",\n'
            '      "area": "nome_area",\n'
            '      "type": "code_patch|prompt_update|config_change",\n'
            '      "description": "cosa cambia e perché",\n'
            '      "file": "src/agent.py",\n'
            '      "find": "stringa ESATTA nel file",\n'
            '      "replace": "stringa sostitutiva",\n'
            '      "expected_gain": "descrizione del miglioramento atteso"\n'
            "    }\n"
            "  ]\n"
            "}"
        )

        try:
            resp  = self._gemini.generate_content(prompt)
            clean = re.sub(r"```json\s*|```\s*", "", resp.text.strip()).strip()
            return json.loads(clean)
        except Exception as e:
            log.warning("Plan LLM error: " + str(e))
            return {"improvements": []}

    def _collect_code_context(self, weaknesses: list, src_root: Path) -> str:
        """Raccoglie snippets di codice rilevanti per le aree deboli."""
        area_files = {
            "tool_calling":   ["src/agent.py", "src/ollama_caller.py"],
            "parse_fail":     ["src/agent.py", "src/ollama_caller.py"],
            "self_heal":      ["src/self_heal.py"],
            "memory":         ["src/memory.py"],
            "vision":         ["src/tools/vision.py"],
            "web_search":     ["src/tools/web_search.py"],
            "orchestration":  ["src/agents/orchestrator.py"],
        }

        snippets = []
        seen     = set()
        for w in weaknesses:
            area = w.get("area", "")
            for filename in area_files.get(area, []):
                if filename in seen:
                    continue
                seen.add(filename)
                fp = src_root.parent / filename
                if fp.exists():
                    text = fp.read_text(encoding="utf-8", errors="replace")
                    snippets.append("### " + filename + "\n" + text[:800])

        return "\n\n".join(snippets)

    # ─── Fase 3: Patch ────────────────────────────────────────────────────────

    def _phase_patch(self, plan: dict) -> list:
        """Applica le patch al codice sorgente con verifica AST."""
        src_root = Path(__file__).parent.parent
        results  = []

        for improvement in plan.get("improvements", [])[:self.MAX_PATCH_FILES_PER_CYCLE]:
            if improvement.get("type") != "code_patch":
                # prompt_update e config_change gestiti separatamente
                results.append(self._apply_non_code_improvement(improvement))
                continue

            file_rel = improvement.get("file", "")
            find_str = improvement.get("find", "")
            repl_str = improvement.get("replace", "")

            if not file_rel or not find_str:
                results.append({"id": improvement.get("id"), "applied": False,
                                 "reason": "find/file mancanti"})
                continue

            fp = src_root.parent / file_rel
            if not fp.exists():
                results.append({"id": improvement.get("id"), "applied": False,
                                 "reason": "file non trovato: " + file_rel})
                continue

            source = fp.read_text(encoding="utf-8")
            if find_str not in source:
                results.append({"id": improvement.get("id"), "applied": False,
                                 "reason": "stringa 'find' non trovata in " + file_rel})
                continue

            patched = source.replace(find_str, repl_str, 1)

            # Verifica AST prima di scrivere
            try:
                ast.parse(patched)
            except SyntaxError as e:
                results.append({"id": improvement.get("id"), "applied": False,
                                 "reason": "SyntaxError post-patch: " + str(e)})
                continue

            # Backup + write
            bak_dir = self.config.get_base_path() / "patches"
            bak_dir.mkdir(exist_ok=True)
            bak_path = bak_dir / (fp.stem + ".bak" + str(int(time.time())) + ".py")
            bak_path.write_text(source, encoding="utf-8")
            fp.write_text(patched, encoding="utf-8")

            log.info("SelfImprovement patch: " + file_rel + " — " +
                     improvement.get("description", "")[:60])
            results.append({
                "id":          improvement.get("id"),
                "applied":     True,
                "file":        file_rel,
                "description": improvement.get("description", ""),
                "backup":      str(bak_path),
            })

        return results

    def _apply_non_code_improvement(self, improvement: dict) -> dict:
        """Gestisce miglioramenti a prompt e config."""
        imp_type = improvement.get("type", "")

        if imp_type == "config_change":
            cfg_file = self.config.get_base_path() / "config.json"
            try:
                cfg = json.loads(cfg_file.read_text()) if cfg_file.exists() else {}
                # Applica la patch come merge
                patch = json.loads(improvement.get("replace", "{}"))
                cfg.update(patch)
                cfg_file.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))
                return {"id": improvement.get("id"), "applied": True,
                        "type": "config_change"}
            except Exception as e:
                return {"id": improvement.get("id"), "applied": False, "reason": str(e)}

        if imp_type == "prompt_update":
            agents_dir = Path(__file__).parent.parent.parent / "agents"
            agents_dir.mkdir(exist_ok=True)
            fname   = improvement.get("file", "updated_prompt.md")
            content = improvement.get("replace", "")
            if content:
                (agents_dir / fname).write_text(content, encoding="utf-8")
                return {"id": improvement.get("id"), "applied": True,
                        "type": "prompt_update", "file": fname}

        return {"id": improvement.get("id"), "applied": False,
                "reason": "tipo non gestito: " + imp_type}

    # ─── Fase 4: Benchmark ───────────────────────────────────────────────────

    def _phase_benchmark(self) -> dict:
        """Esegue task di benchmark per misurare performance dopo le patch."""
        successes = 0
        details   = []

        for task in self.BENCHMARK_TASKS:
            try:
                result  = self.agent.run_task(task, max_steps=6)
                success = "❌" not in result and len(result) > 5
                if success:
                    successes += 1
                details.append({"task": task[:60], "success": success,
                                 "result": result[:100]})
            except Exception as e:
                details.append({"task": task[:60], "success": False, "result": str(e)})

        rate = round(successes / len(self.BENCHMARK_TASKS) * 100, 1)
        return {
            "success_rate": rate,
            "passed":       successes,
            "total":        len(self.BENCHMARK_TASKS),
            "details":      details,
        }

    # ─── Utilities ───────────────────────────────────────────────────────────

    def _read_log_stats(self) -> dict:
        """Statistiche aggregate dai log degli ultimi 7 giorni."""
        from collections import defaultdict
        log_dir = self.config.get_log_dir()
        counts  = defaultdict(int)

        for log_file in sorted(log_dir.glob("debug_*.jsonl"))[-7:]:
            try:
                for line in log_file.read_text(encoding="utf-8", errors="replace").splitlines():
                    ev = json.loads(line)
                    counts[ev.get("type", "unknown")] += 1
                    if ev.get("severity") in ("error", "fatal"):
                        counts["errors"] += 1
            except Exception:
                pass

        total   = counts["tool_ok"] + counts["tool_error"]
        ok_rate = round(counts["tool_ok"] / total * 100, 1) if total > 0 else 0

        return {
            "tool_calls":    total,
            "tool_ok":       counts["tool_ok"],
            "tool_errors":   counts["tool_error"],
            "parse_fails":   counts["parse_fail"],
            "heals":         counts["heal"],
            "model_calls":   counts["model_call"],
            "errors":        counts["errors"],
            "success_rate":  ok_rate,
        }

    def _load_history(self) -> list:
        if self._improvement_file.exists():
            try:
                return json.loads(self._improvement_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return []

    def _save_cycle(self, result: dict):
        self._history.append(result)
        self._history = self._history[-50:]
        self._improvement_file.write_text(
            json.dumps(self._history, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def get_history(self) -> list:
        return list(self._history)
