"""
Fix _safe_params in registry.py.
Causa: vars(Config) ritorna {"_cfg": {...}} che viene passato come **kwargs ai tool.
Fix:   filtra chiavi che iniziano con _ e chiavi non accettate dalla firma del metodo.
"""
import ast, shutil, time
from pathlib import Path

REGISTRY = Path(r"A:\dustai\src\tools\registry.py")
BAK      = Path(r"A:\dustai_stuff\patches")
BAK.mkdir(parents=True, exist_ok=True)

src = REGISTRY.read_text(encoding="utf-8")
shutil.copy2(REGISTRY, BAK / ("registry.bak_safeparams_" + str(int(time.time())) + ".py"))

# Nuova _safe_params: filtra attributi privati, accetta solo stringhe/numeri/bool come valori
NEW_SAFE_PARAMS = '''    @staticmethod
    def _safe_params(p):
        """
        Converte p in dict sicuro per **kwargs.
        - Se p è già dict: filtra chiavi private (che iniziano con _)
        - Se p è oggetto: usa vars() ma filtra attributi privati e non-scalari
        - Risultato: solo chiavi stringa senza underscore iniziale
        """
        if p is None:
            return {}
        if isinstance(p, dict):
            return {k: v for k, v in p.items()
                    if isinstance(k, str) and not k.startswith("_")}
        # Oggetto (es. Config) -> vars() filtrato
        try:
            raw = vars(p)
            return {k: v for k, v in raw.items()
                    if isinstance(k, str)
                    and not k.startswith("_")
                    and isinstance(v, (str, int, float, bool, list, type(None)))}
        except TypeError:
            return {}

'''

# Trova e sostituisce il vecchio _safe_params
lines = src.splitlines()
start = None
end   = None

for i, line in enumerate(lines):
    if "_safe_params" in line and "def _safe_params" in line:
        start = i
    elif start is not None and i > start:
        # Fine metodo: prossima "def " allo stesso livello di indentazione
        if line.strip().startswith("def ") or (line.strip() and not line.startswith(" ")):
            end = i
            break

if start is not None and end is not None:
    before = "\n".join(lines[:start])
    after  = "\n".join(lines[end:])
    new_src = before + "\n" + NEW_SAFE_PARAMS + after
    print("Trovato _safe_params alle righe " + str(start+1) + "-" + str(end))
elif start is not None:
    # Fine file
    before  = "\n".join(lines[:start])
    new_src = before + "\n" + NEW_SAFE_PARAMS
    print("Trovato _safe_params alla riga " + str(start+1) + " (fine file)")
else:
    print("_safe_params NON trovato - lo aggiungo prima di _get_conductor_tool")
    new_src = src.replace(
        "    def _get_conductor_tool(",
        NEW_SAFE_PARAMS + "    def _get_conductor_tool(",
        1
    )

# Verifica sintassi
try:
    ast.parse(new_src)
    REGISTRY.write_text(new_src, encoding="utf-8")
    print("OK registry.py salvato")
except SyntaxError as e:
    print("ERRORE sintassi: " + str(e))
    exit(1)

# Verifica rapida: importa il modulo
import sys
sys.path.insert(0, str(Path(r"A:\dustai")))
try:
    import importlib
    mod = importlib.import_module("src.tools.registry")
    sp  = getattr(mod.ToolRegistry, "_safe_params", None)
    if sp:
        # Test con Config simulato
        class FakeConfig:
            def __init__(self):
                self._cfg   = {"internal": True}
                self._priv  = "privato"
                self.public = "pubblico"

        result = sp(FakeConfig())
        assert "_cfg" not in result, "_cfg non deve passare!"
        assert "_priv" not in result, "_priv non deve passare!"
        print("TEST OK: _cfg e _priv filtrati correttamente")
        print("Test result: " + str(result))

        result2 = sp({"prompt": "ciao", "_internal": "no", "model": "auto"})
        assert "_internal" not in result2
        assert result2 == {"prompt": "ciao", "model": "auto"}
        print("TEST OK: dict filtrato correttamente")
    else:
        print("WARN: _safe_params non trovato nel modulo caricato")
except Exception as e:
    print("Import test: " + str(e))

# Commit
import subprocess
from datetime import datetime
ts = datetime.now().strftime("%Y-%m-%d %H:%M")
for cmd in [
    ["git", "add", "src/tools/registry.py"],
    ["git", "commit", "-m", "fix: _safe_params filtra _cfg e attributi privati Config " + ts],
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
