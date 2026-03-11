"""
DUST AI – install_heal_v2.py
Installa HallucinationGuard v2 + SelfHealEngine v2 in DUST.
Tutto gratuito: Gemini Free + Ollama.

Esegui: python A:\dustai\install_heal_v2.py
"""
import ast, shutil, time, subprocess, sys
from pathlib import Path

BASE  = Path(r"A:\dustai")
SRC   = BASE / "src"
STUFF = Path(r"A:\dustai_stuff")
BAK   = STUFF / "patches"
BAK.mkdir(parents=True, exist_ok=True)
DL    = Path.home() / "Downloads"

print("=" * 60)
print("DUST AI – HallucinationGuard v2 + SelfHeal v2")
print("=" * 60)

# ── 1: Copia file dal download ─────────────────────────────────────────────────
print("\n[1/4] Copia file...")
for fname in ["hallucination_guard.py", "self_heal_v2.py"]:
    src_file = DL / fname
    dst_file = SRC / fname
    if src_file.exists():
        shutil.copy2(src_file, dst_file)
        print("  OK " + fname)
    else:
        print("  WARN: " + fname + " non in Downloads - copia manualmente in " + str(SRC))

# Rinomina self_heal_v2 -> sostituzione self_heal
old_heal = SRC / "self_heal.py"
new_heal = SRC / "self_heal_v2.py"
if new_heal.exists():
    if old_heal.exists():
        # Backup self_heal v1
        bak_heal = BAK / ("self_heal.bak_" + str(int(time.time())) + ".py")
        shutil.copy2(old_heal, bak_heal)
        print("  Backup self_heal v1: " + str(bak_heal))
    shutil.copy2(new_heal, old_heal)
    print("  OK self_heal.py sostituito con v2")

# ── 2: Patcha agent.py per usare HallucinationGuard ───────────────────────────
print("\n[2/4] Patch agent.py -> HallucinationGuard...")
AGENT = SRC / "agent.py"
if AGENT.exists():
    ag_src = AGENT.read_text(encoding="utf-8")
    bak_ag = BAK / ("agent.bak_hall_" + str(int(time.time())) + ".py")
    shutil.copy2(AGENT, bak_ag)

    HALL_GUARD_INIT = (
        "\n"
        "        # HallucinationGuard v2\n"
        "        self._hall_guard = None\n"
    )
    HALL_GUARD_METHOD = '''
    def _get_hall_guard(self):
        """Lazy init HallucinationGuard."""
        if self._hall_guard is None:
            try:
                from .hallucination_guard import HallucinationGuard
                self._hall_guard = HallucinationGuard(
                    self.config,
                    gateway=self._gateway if hasattr(self, "_gateway") else None
                )
                self.log.info("HallucinationGuard v2 pronto")
            except Exception as e:
                self.log.warning("HallucinationGuard N/D: " + str(e))
                self._hall_guard = False
        return self._hall_guard if self._hall_guard else None

'''
    HALL_CALL_PATCH = '''
                # HallucinationGuard: processa risposta prima di usarla
                guard = self._get_hall_guard()
                if guard and isinstance(result, dict) and result.get("type") == "text":
                    _text = result.get("text", "")
                    if _text and len(_text) > 30:
                        _prompt_ctx = messages[-1].get("parts", [""])[0] if messages else ""
                        _guarded = guard.process(str(_prompt_ctx), _text, level="standard")
                        if _guarded.get("corrected"):
                            self.log.info("HallucinationGuard: risposta corretta (conf=%d)", _guarded.get("confidence", 0))
                            result["text"] = _guarded["text"]
                            result["_hall_confidence"] = _guarded["confidence"]
'''

    changed = False

    # Aggiungi _hall_guard = None nell'__init__
    if "self._hall_guard = None" not in ag_src:
        target = "        self._setup_gemini()"
        ag_src = ag_src.replace(target, HALL_GUARD_INIT + target, 1)
        changed = True
        print("  OK _hall_guard init aggiunto")

    # Aggiungi metodo _get_hall_guard
    if "_get_hall_guard" not in ag_src:
        ag_src = ag_src.replace("    def _call_model(", HALL_GUARD_METHOD + "    def _call_model(", 1)
        changed = True
        print("  OK _get_hall_guard() aggiunto")

    # Aggiunge guardrail nel loop principale _call_model o run_task
    if "HallucinationGuard: processa" not in ag_src:
        # Trova il return result in _call_model dopo Ollama
        anchor = "            return result\n\n"
        if anchor in ag_src:
            ag_src = ag_src.replace(anchor, HALL_CALL_PATCH + anchor, 1)
            changed = True
            print("  OK HallucinationGuard hook nel loop aggiunto")

    if changed:
        try:
            ast.parse(ag_src)
            AGENT.write_text(ag_src, encoding="utf-8")
            print("  OK agent.py salvato (sintassi OK)")
        except SyntaxError as e:
            print("  ERRORE sintassi: " + str(e) + " - ripristino backup")
            shutil.copy2(bak_ag, AGENT)
    else:
        print("  SKIP (gia patchato)")

# ── 3: Patcha self_heal.py: usa SelfHealEngine v2 in agent.py ────────────────
print("\n[3/4] Aggiorno riferimento SelfHealEngine in agent.py...")
if AGENT.exists():
    ag_src = AGENT.read_text(encoding="utf-8")
    # Già importa da self_heal - la v2 ha stesso nome classe
    if "SelfHealEngine" in ag_src:
        print("  OK SelfHealEngine gia referenziato (v2 sostituisce v1 stesso nome)")

# ── 4: Commit e push ──────────────────────────────────────────────────────────
print("\n[4/4] Commit e push...")
from datetime import datetime
ts = datetime.now().strftime("%Y-%m-%d %H:%M")

for cmd in [
    ["git", "add", "-A"],
    ["git", "commit", "-m",
     "feat: HallucinationGuard v2 + SelfHeal v2 (free-only, multi-agent, CoV) " + ts],
    ["git", "push", "origin", "master"],
]:
    r = subprocess.run(cmd, cwd=str(BASE), capture_output=True, text=True, encoding="utf-8")
    label = " ".join(cmd[:2])
    out   = r.stderr or r.stdout or ""
    if r.returncode == 0 or "nothing to commit" in out or "up to date" in out:
        print("  OK " + label)
    else:
        print("  WARN " + label + ": " + out[:150])

print("""
==================================================
HallucinationGuard v2 + SelfHeal v2 installati!

FUNZIONA AUTOMATICAMENTE - nessuna configurazione:
  - Ogni risposta AI viene analizzata prima dell'uso
  - CoV (Chain-of-Verification) su Gemini Flash FREE
  - Cross-validation su Ollama locale (gratis)
  - Self-reflection se confidence < 60
  - Rate limit: switch immediato al prossimo modello
  - SyntaxError: patch automatica con backup

LOG:
  A:\\dustai_stuff\\logs\\hallucination_log.jsonl
  A:\\dustai_stuff\\memory\\selfheal_history.json

STATISTICHE nella GUI DUST:
  ai_status   <- mostra stats orchestra + healing
==================================================
""")
