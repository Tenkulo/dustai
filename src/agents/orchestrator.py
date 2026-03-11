"""
DUST AI – Orchestrator v2.0
Multi-agente: Planner → Executor → Verifier

Flusso:
  1. Planner: scompone task in step atomici (JSON strutturato)
  2. Executor: esegue ogni step tramite Agent.run_task()
  3. Verifier: valida ogni risultato prima del prossimo step
  4. Se verifica fallisce → retry step (max 2) → abort con reason

TaskQueue: preleva task dalla coda persistente e li esegue in ordine di priorità.
"""
import json
import logging
import time
from typing import Optional

log = logging.getLogger("Orchestrator")


class Orchestrator:
    def __init__(self, config, agent, memory=None, skill_forge=None):
        self.config      = config
        self.agent       = agent
        self.memory      = memory
        self.skill_forge = skill_forge
        self._gemini     = agent._gemini_model   # modello base per planner/verifier
        self._pm         = None                  # PromptManager (lazy)

    def _get_pm(self):
        if not self._pm:
            try:
                from ..prompt_manager import PromptManager
                self._pm = PromptManager(self.config)
            except Exception:
                self._pm = None
        return self._pm

    # ─── Entry point ─────────────────────────────────────────────────────────

    def run(self, task: str, use_planner: bool = True) -> str:
        """
        Esegui un task con pipeline Planner → Executor → Verifier.
        Se use_planner=False → esegui direttamente con Agent.run_task().
        """
        log.info("Orchestrator: " + task[:80])

        if not use_planner:
            return self.agent.run_task(task)

        # 1. Pianifica
        plan = self._plan(task)
        if not plan:
            log.warning("Planner fallito → esecuzione diretta")
            return self.agent.run_task(task)

        complexity = plan.get("complexity", "medium")
        steps      = plan.get("plan", [])
        criteria   = plan.get("success_criteria", "")

        print("\n📋 Piano (" + complexity + ", " + str(len(steps)) + " step):")
        for s in steps:
            print("  " + str(s.get("step", "?")) + ". " + s.get("description", ""))
        print("  Criterio: " + criteria)
        print()

        # 2. Esegui step per step con verifica
        results    = []
        all_ok     = True
        steps_done = []

        for step_data in steps:
            step_num  = step_data.get("step", "?")
            step_desc = step_data.get("description", "")
            tool_hint = step_data.get("tool", "")
            verify    = step_data.get("verify_after", False)

            print("▶ Step " + str(step_num) + ": " + step_desc)

            # Costruisce sotto-task per il singolo step
            subtask = step_desc
            if tool_hint:
                params_hint = step_data.get("params_hint", {})
                subtask = (
                    step_desc + "\n"
                    "Usa il tool '" + tool_hint + "' con questi parametri indicativi: " +
                    json.dumps(params_hint, ensure_ascii=False)
                )

            # Esegui (max 2 retry su fallimento verifica)
            step_result = None
            for attempt in range(2):
                step_result = self.agent.run_task(subtask, max_steps=8)

                if not verify:
                    break

                # Verifica il risultato
                verdict = self._verify(
                    tool=tool_hint,
                    params=step_data.get("params_hint", {}),
                    result=step_result,
                    expected=criteria,
                    task=task,
                )

                if verdict.get("success"):
                    print("  ✅ Verificato (confidence=" + str(verdict.get("confidence", "?")) + ")")
                    break
                else:
                    next_action = verdict.get("next_action", "retry")
                    print("  ⚠️ Verifica fallita: " + verdict.get("evidence", "?"))
                    if next_action == "abort":
                        print("  ❌ Step abortito: " + verdict.get("evidence", ""))
                        all_ok = False
                        break
                    if attempt == 0 and next_action in ("retry", "alternative"):
                        hint = verdict.get("retry_hint") or verdict.get("alternative_hint", "")
                        if hint:
                            subtask = step_desc + "\nATTENZIONE: tentativo precedente fallito. " + hint
                        print("  🔄 Retry step " + str(step_num) + "...")
                        continue
                    all_ok = False
                    break

            results.append({
                "step":   step_num,
                "desc":   step_desc,
                "result": (step_result or "")[:200],
                "ok":     all_ok,
            })
            steps_done.append({"tool": tool_hint, "params": step_data.get("params_hint", {}),
                                "result": step_result})

        # 3. Post-task: SkillForge learning
        if self.skill_forge and steps_done:
            try:
                self.skill_forge.learn_from_task(task, steps_done, all_ok)
            except Exception as e:
                log.warning("SkillForge: " + str(e))

        # 4. Riepilogo finale
        ok_count   = sum(1 for r in results if r["ok"])
        total      = len(results)
        status     = "✅ Completato" if all_ok else "⚠️ Parziale"
        summary    = (
            status + " (" + str(ok_count) + "/" + str(total) + " step)\n" +
            "\n".join("  " + str(r["step"]) + ". " + r["desc"] + " → " + r["result"][:80]
                      for r in results)
        )

        if self.memory:
            self.memory.add(task, summary, success=all_ok)

        return summary

    # ─── Planner ─────────────────────────────────────────────────────────────

    def _plan(self, task: str) -> Optional[dict]:
        """Chiama Gemini per pianificare il task in step atomici."""
        if not self._gemini:
            return None

        pm = self._get_pm()
        if pm:
            skills_ctx = ""
            if self.skill_forge:
                skills_ctx = self.skill_forge.get_skill_context(task)
            prompt = pm.get_planner_prompt(
                task=task,
                context=self.memory.get_context() if self.memory else "",
                skills=skills_ctx,
                available_tools="sys_exec, file_read, file_write, file_list, "
                                "web_search, browser_open, screenshot, vision_analyze, "
                                "mouse_click, keyboard_type, app_launch, code_run",
            )
        else:
            prompt = self._fallback_planner_prompt(task)

        try:
            resp = self._gemini.generate_content(prompt)
            text = resp.text.strip()

            import re
            clean = re.sub(r"```json\s*|```\s*", "", text).strip()
            data  = json.loads(clean)

            # Valida struttura minima
            if not isinstance(data.get("plan"), list) or not data["plan"]:
                return None

            return data

        except Exception as e:
            log.warning("Planner error: " + str(e))
            return None

    def _fallback_planner_prompt(self, task: str) -> str:
        desktop   = str(self.config.get_desktop())
        base_path = str(self.config.get_base_path())
        return (
            "Scomponi questo task in step atomici eseguibili su Windows 11.\n"
            "Task: " + task + "\n"
            "Desktop: " + desktop + " | Base: " + base_path + "\n\n"
            "Tool disponibili: sys_exec, file_read, file_write, file_list, "
            "web_search, browser_open, screenshot, vision_analyze, "
            "mouse_click, keyboard_type, app_launch, code_run\n\n"
            "Rispondi SOLO con JSON:\n"
            '{"complexity":"simple|medium|complex","plan":[{"step":1,'
            '"description":"...","tool":"...","params_hint":{},"verify_after":true}],'
            '"success_criteria":"come verificare il completamento"}'
        )

    # ─── Verifier ────────────────────────────────────────────────────────────

    def _verify(self, tool: str, params: dict, result: str,
                expected: str, task: str) -> dict:
        """Valida il risultato di un step."""
        if not self._gemini:
            # Verifica semplice senza LLM
            is_ok = not result.startswith("❌")
            return {"success": is_ok, "confidence": 0.6,
                    "evidence": result[:100], "next_action": "continue" if is_ok else "retry"}

        pm = self._get_pm()
        if pm:
            prompt = pm.get_verifier_prompt(tool, params, result, expected, task)
        else:
            prompt = self._fallback_verifier_prompt(tool, result, expected)

        try:
            resp = self._gemini.generate_content(prompt)
            import re
            clean = re.sub(r"```json\s*|```\s*", "", resp.text.strip()).strip()
            data  = json.loads(clean)
            return data
        except Exception:
            # Fallback: verifica lessicale
            is_ok = not result.startswith("❌") and "❌" not in result
            return {
                "success":     is_ok,
                "confidence":  0.5,
                "evidence":    result[:100],
                "next_action": "continue" if is_ok else "retry",
            }

    def _fallback_verifier_prompt(self, tool: str, result: str, expected: str) -> str:
        return (
            "Verifica se il risultato del tool '" + tool + "' è corretto.\n"
            "Risultato: " + result[:500] + "\n"
            "Atteso: " + expected + "\n\n"
            "Rispondi SOLO con JSON:\n"
            '{"success":true,"confidence":0.9,"evidence":"...","next_action":"continue|retry|abort"}'
        )

    # ─── TaskQueue runner ────────────────────────────────────────────────────

    def run_queue(self, max_tasks: int = 10) -> list:
        """
        Preleva e processa task dalla TaskQueue persistente.
        Ritorna lista di risultati.
        """
        try:
            from ..memory import TaskQueue
            queue   = TaskQueue(self.config)
            results = []

            for _ in range(max_tasks):
                task_entry = queue.next()
                if not task_entry:
                    break

                task_id   = task_entry["id"]
                task_text = task_entry["task"]

                log.info("Queue task [" + task_id + "]: " + task_text[:60])
                print("\n🔄 Task queue [" + task_id + "]: " + task_text[:80])

                try:
                    result  = self.run(task_text)
                    success = "❌" not in result
                    queue.complete(task_id, result, success=success)
                    results.append({"id": task_id, "success": success, "result": result[:200]})
                except Exception as e:
                    queue.complete(task_id, "❌ " + str(e), success=False)
                    results.append({"id": task_id, "success": False, "result": str(e)})

            return results

        except Exception as e:
            log.error("Queue error: " + str(e))
            return []
