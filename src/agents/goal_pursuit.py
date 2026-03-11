"""
DUST AI – GoalPursuit v1.0
Mantiene gli obiettivi del progetto come North Star permanente.
Ogni task eseguito viene valutato rispetto ai goal.
Goal non raggiunti → generano sotto-task automatici nella TaskQueue.

I goal del progetto (immutabili):
  G1 - Tool calling 100% funzionante (Gemini + Ollama)
  G2 - Autonomia 98%+ (zero supervisione umana)
  G3 - Self-consciousness (reflective loop + self_profile aggiornato)
  G4 - Vision attiva (screenshot + analisi GUI)
  G5 - SkillForge attivo (apprende da ogni task)
  G6 - Multi-agente (Planner → Executor → Verifier)
  G7 - Task queue persistente sempre processata
  G8 - Budget token ottimizzato (Gemini free + Perplexity €5)
"""
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

log = logging.getLogger("GoalPursuit")

# ─── Definizione goal del progetto ────────────────────────────────────────────

PROJECT_GOALS = [
    {
        "id":          "G1",
        "name":        "Tool calling 100% funzionante",
        "description": "Gemini usa native function calling. Ollama usa two-phase + Pydantic schema. "
                       "Zero parse fail non gestiti. SelfHeal attivo su ogni failure.",
        "kpis": [
            "parse_fail_rate < 5%",
            "tool_success_rate > 95%",
            "ollama_fallback_ok = true",
        ],
        "check_files": ["src/agent.py", "src/ollama_caller.py", "src/self_heal.py"],
        "status":      "in_progress",
    },
    {
        "id":          "G2",
        "name":        "Autonomia 98%+",
        "description": "L'agente completa task reali senza intervento umano. "
                       "Nessun loop infinito. Nessuna simulazione.",
        "kpis": [
            "task_success_rate > 98%",
            "human_intervention_count = 0",
            "narrative_output_count = 0",
        ],
        "check_files": ["src/agent.py", "src/agents/orchestrator.py"],
        "status":      "in_progress",
    },
    {
        "id":          "G3",
        "name":        "Self-consciousness attiva",
        "description": "Reflective loop post ogni tool. self_profile.json aggiornato. "
                       "Post-task reflection salva fatti e skills.",
        "kpis": [
            "reflection_active = true",
            "self_profile_updated = true",
            "facts_count > 10",
        ],
        "check_files": ["src/memory.py", "src/agent.py"],
        "status":      "in_progress",
    },
    {
        "id":          "G4",
        "name":        "Vision tool attivo",
        "description": "VisionTool cattura screenshot con mss, analizza con Gemini Vision, "
                       "trova elementi UI, guida mouse_click.",
        "kpis": [
            "vision_tool_loaded = true",
            "screenshot_ok = true",
            "find_element_ok = true",
        ],
        "check_files": ["src/tools/vision.py"],
        "status":      "in_progress",
    },
    {
        "id":          "G5",
        "name":        "SkillForge attivo",
        "description": "Ogni task completato viene analizzato per skills riusabili. "
                       "Skills indicizzate per tag. Usate nei prompt successivi.",
        "kpis": [
            "skills_count > 0",
            "skill_context_injected = true",
            "skill_extraction_running = true",
        ],
        "check_files": ["src/memory.py"],
        "status":      "in_progress",
    },
    {
        "id":          "G6",
        "name":        "Multi-agente Planner→Executor→Verifier",
        "description": "Task complessi pianificati da Planner. Ogni step verificato da Verifier. "
                       "Retry automatico su fallimento verifica.",
        "kpis": [
            "orchestrator_active = true",
            "planner_produces_valid_json = true",
            "verifier_blocks_wrong_results = true",
        ],
        "check_files": ["src/agents/orchestrator.py"],
        "status":      "in_progress",
    },
    {
        "id":          "G7",
        "name":        "Task queue sempre processata",
        "description": "TaskQueue persistente. Task aggiunti da GUI/CLI/sistema. "
                       "Processati in ordine priorità all'avvio e periodicamente.",
        "kpis": [
            "queue_file_exists = true",
            "pending_tasks_processed = true",
            "queue_runner_active = true",
        ],
        "check_files": ["src/memory.py", "src/agents/orchestrator.py"],
        "status":      "in_progress",
    },
    {
        "id":          "G8",
        "name":        "Budget token ottimizzato",
        "description": "3 progetti AI Studio = 3000 Flash req/giorno. "
                       "Perplexity: max 10 sonar-pro/mese entro €5. "
                       "Rate limit rispettato automaticamente.",
        "kpis": [
            "multi_project_configured = true",
            "perplexity_budget_tracked = true",
            "monthly_cost_eur < 5.5",
        ],
        "check_files": ["src/config.py", "src/tools/web_search.py"],
        "status":      "in_progress",
    },
]


class GoalPursuit:
    """
    Tracker degli obiettivi del progetto.
    Valuta stato attuale, genera task per goal non raggiunti,
    misura progresso nel tempo.
    """

    def __init__(self, config, agent, task_queue=None):
        self.config     = config
        self.agent      = agent
        self.task_queue = task_queue
        self._gemini    = agent._gemini_model
        self._goals_f   = config.get_profiles_dir() / "goals_status.json"
        self._status    = self._load_status()

    # ─── Valutazione goal ─────────────────────────────────────────────────────

    def evaluate_all(self) -> dict:
        """Valuta tutti i goal e aggiorna status."""
        results = {}
        for goal in PROJECT_GOALS:
            gid    = goal["id"]
            status = self._evaluate_goal(goal)
            results[gid]           = status
            self._status[gid]      = status
            self._status[gid]["ts"] = datetime.now().isoformat()

        self._save_status()
        return results

    def _evaluate_goal(self, goal: dict) -> dict:
        """Valuta un singolo goal controllando file, log e config."""
        gid   = goal["id"]
        kpis  = goal["kpis"]
        score = 0.0
        notes = []

        # Check file esistenza
        src_root = Path(__file__).parent.parent
        for f in goal.get("check_files", []):
            fp = src_root.parent / f
            if fp.exists():
                score += 0.2
                notes.append(f + " ✓")
            else:
                notes.append(f + " ✗ MANCANTE")

        # Normalizza score
        if goal.get("check_files"):
            score = score / len(goal["check_files"]) * 100
        else:
            score = 50.0

        # KPI heuristic check
        achieved_kpis = []
        for kpi in kpis:
            achieved = self._check_kpi_heuristic(kpi, gid)
            if achieved:
                achieved_kpis.append(kpi)

        kpi_score = len(achieved_kpis) / len(kpis) * 100 if kpis else 100

        final_score = (score * 0.4 + kpi_score * 0.6)

        return {
            "goal_id":       gid,
            "name":          goal["name"],
            "score":         round(final_score, 1),
            "achieved_kpis": achieved_kpis,
            "missing_kpis":  [k for k in kpis if k not in achieved_kpis],
            "notes":         notes,
            "status":        "achieved" if final_score >= 85 else
                             "in_progress" if final_score >= 40 else "blocked",
        }

    def _check_kpi_heuristic(self, kpi: str, goal_id: str) -> bool:
        """Controllo euristico dei KPI basato su file e log."""
        base = self.config.get_base_path()
        src  = Path(__file__).parent.parent

        # File-based checks
        if "tool_loaded" in kpi:
            module = kpi.split("_tool")[0]
            return (src / "tools" / (module + ".py")).exists()

        if "queue_file_exists" in kpi:
            return self.config.get_tasks_file().exists()

        if "skills_count" in kpi:
            sf = self.config.get_skills_dir() / "skills.json"
            if sf.exists():
                try:
                    data = json.loads(sf.read_text(encoding="utf-8"))
                    return len(data) > 0
                except Exception:
                    pass
            return False

        if "self_profile_updated" in kpi:
            pf = self.config.get_profiles_dir() / "self_profile.json"
            return pf.exists()

        if "perplexity_budget_tracked" in kpi:
            uf = self.config.get_memory_dir() / "perplexity_usage.json"
            return uf.exists()

        if "multi_project_configured" in kpi:
            from pathlib import Path as P
            env_files = [
                base / ".env",
                P(str(self.config.get("paths", {}).get("workdir", ""))) / ".env",
            ]
            for ef in env_files:
                if ef.exists():
                    content = ef.read_text(encoding="utf-8", errors="replace")
                    return "GOOGLE_API_KEY_2" in content
            return False

        # Log-based checks
        log_stats = self._quick_log_stats()
        if "parse_fail_rate < 5%" in kpi:
            calls      = log_stats.get("model_calls", 1)
            parse_fail = log_stats.get("parse_fails", 0)
            return (parse_fail / calls * 100) < 5 if calls > 0 else True

        if "tool_success_rate > 95%" in kpi:
            return log_stats.get("success_rate", 0) > 95

        # Default: non verificabile → parzialmente
        return False

    def _quick_log_stats(self) -> dict:
        from collections import defaultdict
        counts = defaultdict(int)
        log_dir = self.config.get_log_dir()
        for f in sorted(log_dir.glob("debug_*.jsonl"))[-3:]:
            try:
                for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                    ev = json.loads(line)
                    counts[ev.get("type", "")] += 1
            except Exception:
                pass
        total = counts["tool_ok"] + counts["tool_error"]
        return {
            "tool_calls":   total,
            "parse_fails":  counts["parse_fail"],
            "model_calls":  max(counts["model_call"], 1),
            "success_rate": round(counts["tool_ok"] / total * 100, 1) if total else 0,
        }

    # ─── Generazione task autonomi ────────────────────────────────────────────

    def generate_tasks_for_gaps(self) -> list:
        """
        Per ogni goal non raggiunto, genera task autonomi e li aggiunge alla queue.
        Ritorna lista di task_id aggiunti.
        """
        if not self.task_queue:
            log.warning("GoalPursuit: task_queue non configurata")
            return []

        evaluation = self.evaluate_all()
        added_ids  = []

        for gid, status in evaluation.items():
            if status["status"] == "achieved":
                continue

            missing = status.get("missing_kpis", [])
            if not missing:
                continue

            goal = next((g for g in PROJECT_GOALS if g["id"] == gid), None)
            if not goal:
                continue

            # Genera task per i KPI mancanti
            task_text = self._build_goal_task(goal, missing)
            if task_text:
                task_id = self.task_queue.enqueue(
                    task=task_text,
                    priority=self._goal_priority(gid),
                    source="goal_pursuit_" + gid,
                )
                added_ids.append(task_id)
                log.info("GoalPursuit: task aggiunto per " + gid + " [" + task_id + "]")

        return added_ids

    def _build_goal_task(self, goal: dict, missing_kpis: list) -> str:
        """Costruisce un task testuale per raggiungere un goal."""
        kpi_str = "\n".join("  - " + k for k in missing_kpis[:3])
        return (
            "GOAL AUTONOMO [" + goal["id"] + "]: " + goal["name"] + "\n\n"
            "Obiettivo: " + goal["description"] + "\n\n"
            "KPI da soddisfare:\n" + kpi_str + "\n\n"
            "Esegui le azioni necessarie per soddisfare questi KPI. "
            "Verifica ogni azione con un tool call di conferma. "
            "Dichiara completato solo dopo verifica reale."
        )

    def _goal_priority(self, gid: str) -> int:
        priorities = {"G1": 1, "G2": 1, "G3": 3, "G4": 4,
                      "G5": 4, "G6": 3, "G7": 2, "G8": 5}
        return priorities.get(gid, 5)

    # ─── Report ───────────────────────────────────────────────────────────────

    def get_progress_report(self) -> str:
        """Report testuale dello stato dei goal."""
        evaluation = self.evaluate_all()
        lines      = ["DUST AI – Stato Goal Progetto",
                      "=" * 40,
                      "Generato: " + datetime.now().strftime("%Y-%m-%d %H:%M")]

        total_score = 0.0
        for gid in sorted(evaluation.keys()):
            s    = evaluation[gid]
            icon = "✅" if s["status"] == "achieved" else \
                   "🔄" if s["status"] == "in_progress" else "❌"
            lines.append(
                icon + " " + gid + " " + s["name"] +
                " (" + str(s["score"]) + "%)"
            )
            if s.get("missing_kpis"):
                lines.append("     Mancano: " + ", ".join(s["missing_kpis"][:2]))
            total_score += s["score"]

        avg = round(total_score / len(evaluation), 1) if evaluation else 0
        lines.append("")
        lines.append("Progresso medio: " + str(avg) + "%")
        autonomy_est = min(98, round(avg * 0.98, 1))
        lines.append("Autonomia stimata: " + str(autonomy_est) + "%")

        report = "\n".join(lines)

        # Salva su file
        try:
            out = self.config.get_base_path() / "goal_progress.txt"
            out.write_text(report, encoding="utf-8")
        except Exception:
            pass

        return report

    # ─── Persistenza ─────────────────────────────────────────────────────────

    def _load_status(self) -> dict:
        if self._goals_f.exists():
            try:
                return json.loads(self._goals_f.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save_status(self):
        try:
            self._goals_f.write_text(
                json.dumps(self._status, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except Exception as e:
            log.warning("GoalPursuit save: " + str(e))
