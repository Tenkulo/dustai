"""
Fix immediato applicato da questo script:
  1. self_heal.py  — heal_rate_limit() parsava retry_after in ms → ora clamp 5-65s
  2. agent.py      — migra da google.generativeai a google.genai
  3. config.py     — aggiorna import se necessario

Esegui UNA VOLTA da terminale:
  python A:\dustai\fix_rate_limit.py
"""
import re
import sys
import ast
import shutil
from pathlib import Path
from datetime import datetime

SRC = Path(r"A:\dustai")
BAK = Path(r"A:\dustai_stuff\patches")
BAK.mkdir(parents=True, exist_ok=True)


def backup(path: Path):
    ts  = datetime.now().strftime("%H%M%S")
    dst = BAK / (path.stem + ".bak_" + ts + path.suffix)
    shutil.copy2(path, dst)
    print("  BAK → " + str(dst))


def patch_file(path: Path, patches: list) -> bool:
    """Applica lista di (find, replace) con verifica AST."""
    if not path.exists():
        print("  SKIP (non trovato): " + str(path))
        return False

    source = path.read_text(encoding="utf-8")
    patched = source

    for find, replace, label in patches:
        if find in patched:
            patched = patched.replace(find, replace, 1)
            print("  ✅ " + label)
        else:
            print("  ⚠️  non trovato (già patchato?): " + label)

    if patched == source:
        print("  (nessuna modifica)")
        return False

    # Verifica AST
    try:
        ast.parse(patched)
    except SyntaxError as e:
        print("  ❌ SyntaxError post-patch: " + str(e) + " — ANNULLATO")
        return False

    backup(path)
    path.write_text(patched, encoding="utf-8")
    return True


# ─── FIX 1: self_heal.py — rate limit retry timer ────────────────────────────
print("\n[1/3] Fix self_heal.py — rate limit timer")

SELF_HEAL = SRC / "src" / "self_heal.py"

# Cerca qualsiasi variante del parse retry_after che possa produrre valori enormi
SH_PATCHES = [
    # Pattern comune: retry_after = int(e.retry_after) oppure float(...)
    # Lo sostituiamo con un clamp sicuro 5-65 secondi
    (
        "retry_after = int(e.retry_after)",
        "retry_after = max(5, min(65, int(e.retry_after)))",
        "clamp retry_after int"
    ),
    (
        "retry_after = float(e.retry_after)",
        "retry_after = max(5, min(65, float(e.retry_after)))",
        "clamp retry_after float"
    ),
    # Se usa il messaggio di errore con regex
    (
        'wait_time = int(m.group(1))',
        'wait_time = max(5, min(65, int(m.group(1))))',
        "clamp wait_time regex"
    ),
    (
        'wait_time = float(m.group(1))',
        'wait_time = max(5, min(65, float(m.group(1))))',
        "clamp wait_time float regex"
    ),
]

# Patch più aggressiva: trova qualsiasi numero gigante nel retry
if SELF_HEAL.exists():
    source = SELF_HEAL.read_text(encoding="utf-8")

    # Cerca pattern come: riprovo in {N}s  dove N potrebbe essere enorme
    # Aggiunge una funzione helper _safe_retry_delay se non esiste
    HELPER = '''

def _safe_retry_delay(raw) -> int:
    """Clamp retry delay tra 5 e 65 secondi. Evita valori in ms o ns."""
    try:
        val = float(str(raw).strip())
        # Se il valore è in millisecondi (>1000) converti in secondi
        if val > 1000:
            val = val / 1000
        return max(5, min(65, int(val)))
    except Exception:
        return 30
'''

    if "_safe_retry_delay" not in source:
        # Inserisci dopo gli import
        insert_after = "log = logging.getLogger"
        if insert_after in source:
            source = source.replace(
                insert_after,
                HELPER + "\n" + insert_after,
                1
            )
            print("  ✅ aggiunto _safe_retry_delay helper")

    # Sostituisci tutti i pattern di sleep con rate limit
    # Cerca: time.sleep( ... retry ... ) con valori potenzialmente enormi
    # Pattern: time.sleep(retry_after) → time.sleep(_safe_retry_delay(retry_after))
    for old, new in [
        ("time.sleep(retry_after)", "time.sleep(_safe_retry_delay(retry_after))"),
        ("time.sleep(wait_time)",   "time.sleep(_safe_retry_delay(wait_time))"),
        ("time.sleep(delay)",       "time.sleep(_safe_retry_delay(delay))"),
    ]:
        if old in source and "_safe_retry_delay(" + old[11:] not in source:
            source = source.replace(old, new)
            print("  ✅ wrapped " + old)

    try:
        ast.parse(source)
        backup(SELF_HEAL)
        SELF_HEAL.write_text(source, encoding="utf-8")
        print("  ✅ self_heal.py salvato")
    except SyntaxError as e:
        print("  ❌ SyntaxError: " + str(e))

# ─── FIX 2: agent.py — deprecation google.generativeai → google.genai ────────
print("\n[2/3] Fix agent.py — migra a google.genai")

AGENT = SRC / "src" / "agent.py"
AG_PATCHES = [
    (
        "import google.generativeai as genai",
        "import google.genai as genai",
        "import google.genai"
    ),
    (
        "from google.generativeai",
        "from google.genai",
        "from google.genai"
    ),
]
patch_file(AGENT, AG_PATCHES)

# ─── FIX 3: config.py e altri file con lo stesso import ─────────────────────
print("\n[3/3] Fix altri file — migra a google.genai")

for rel in ["src/config.py", "src/self_heal.py", "src/tools/vision.py"]:
    fp = SRC / rel
    if fp.exists() and "google.generativeai" in fp.read_text(encoding="utf-8"):
        patch_file(fp, [
            (
                "import google.generativeai as genai",
                "import google.genai as genai",
                rel + " → google.genai"
            ),
            (
                "from google.generativeai",
                "from google.genai",
                rel + " → from google.genai"
            ),
        ])

# ─── FIX 4: installa google-genai se mancante ───────────────────────────────
print("\n[4/4] Verifica installazione google-genai")
import subprocess
r = subprocess.run(
    [sys.executable, "-c", "import google.genai; print('OK', google.genai.__version__)"],
    capture_output=True, text=True
)
if "OK" in r.stdout:
    print("  ✅ google.genai già installato: " + r.stdout.strip())
else:
    print("  Installo google-genai...")
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "google-genai"], check=True)
    print("  ✅ installato")

print("\n=== FIX COMPLETATI ===")
print("Ora riavvia con:  A:\\dustai\\run.bat")
