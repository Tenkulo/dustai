"""
Fix registry.py dispatch AIConductorTool.
Errore: ai_ask() missing 1 required positional argument: 'prompt'
Causa: il registry valida i tool all'avvio chiamando la lambda con {} vuoto.
Fix:   le lambda orchestra controllano che 'prompt' sia presente prima di chiamare.
Esegui: python A:\dustai\fix_registry_dispatch.py
"""
import ast, shutil, time
from pathlib import Path

f   = Path(r"A:\dustai\src\tools\registry.py")
bak = Path(r"A:\dustai_stuff\patches")
bak.mkdir(parents=True, exist_ok=True)
shutil.copy2(f, bak / ("registry.bak_dispatch_" + str(int(time.time())) + ".py"))

s = f.read_text(encoding="utf-8")

# Fix: le lambda orchestra devono restituire stringa di help se prompt mancante
# invece di crashare con missing argument

FIXES = [
    # ai_ask: richiede prompt
    (
        "'ai_ask':     lambda p: (self._get_conductor_tool().ai_ask(**self._safe_params(p)) if self._get_conductor_tool() else 'N/D'),",
        "'ai_ask':     lambda p: (self._get_conductor_tool().ai_ask(**self._safe_params(p)) if self._get_conductor_tool() and self._safe_params(p).get('prompt') else ('N/D' if not self._get_conductor_tool() else 'Uso: ai_ask prompt=\"...\" model=auto')),",
    ),
    # ai_parallel: richiede prompt
    (
        "'ai_parallel':lambda p: (self._get_conductor_tool().ai_parallel(**self._safe_params(p)) if self._get_conductor_tool() else 'N/D'),",
        "'ai_parallel':lambda p: (self._get_conductor_tool().ai_parallel(**self._safe_params(p)) if self._get_conductor_tool() and self._safe_params(p).get('prompt') else ('N/D' if not self._get_conductor_tool() else 'Uso: ai_parallel prompt=\"...\" models=\"gemini,claude\"')),",
    ),
    # ai_models: non richiede args obbligatori - ok
    # ai_status: non richiede args - ok
    # git_sync: non richiede args obbligatori
    (
        "'git_sync':   lambda p: (self._get_git_sync_tool().git_sync(**self._safe_params(p)) if self._get_git_sync_tool() else 'N/D'),",
        "'git_sync':   lambda p: (self._get_git_sync_tool().git_sync(**self._safe_params(p)) if self._get_git_sync_tool() else 'N/D'),",
    ),
    # git_commit: richiede message
    (
        "'git_commit': lambda p: (self._get_git_sync_tool().git_commit(**self._safe_params(p)) if self._get_git_sync_tool() else 'N/D'),",
        "'git_commit': lambda p: (self._get_git_sync_tool().git_commit(**self._safe_params(p)) if self._get_git_sync_tool() and self._safe_params(p).get('message') else ('N/D' if not self._get_git_sync_tool() else 'Uso: git_commit message=\"...\"')),",
    ),
]

applied = 0
for old, new in FIXES:
    if old in s and old != new:
        s = s.replace(old, new)
        applied += 1

print("Patch lambda applicate: " + str(applied))

# Verifica sintassi
try:
    ast.parse(s)
    f.write_text(s, encoding="utf-8")
    print("OK registry.py salvato")
except SyntaxError as e:
    print("ERRORE sintassi: " + str(e))
    exit(1)

# Commit
import subprocess
from datetime import datetime
ts = datetime.now().strftime("%Y-%m-%d %H:%M")
for cmd in [
    ["git", "add", "src/tools/registry.py"],
    ["git", "commit", "-m", "fix: registry lambda guard prompt required args " + ts],
    ["git", "push", "origin", "master"],
]:
    r = subprocess.run(cmd, cwd=str(Path(r"A:\dustai")),
                       capture_output=True, text=True, encoding="utf-8")
    out = r.stderr or r.stdout or ""
    label = " ".join(cmd[:2])
    if r.returncode == 0 or "nothing to commit" in out or "up to date" in out:
        print("OK " + label)
    else:
        print("WARN " + label + ": " + out[:100])

print("\nFix completato. Riavvia DUST.")
print("Il warning dovrebbe sparire e ai_ask dovrebbe essere disponibile.")
