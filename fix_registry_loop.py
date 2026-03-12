"""
Fix _register_all in registry.py.
Bug: il loop tratta lambda e classi allo stesso modo.
     Su lambda: cls.__name__ = '<lambda>', poi cls(self.config) passa Config come 'p'.
Fix: separa lambda (registrate direttamente) da classi (istanziate con config).
Esegui: python A:\dustai\fix_registry_loop.py
"""
import ast, shutil, time
from pathlib import Path

f   = Path(r"A:\dustai\src\tools\registry.py")
bak = Path(r"A:\dustai_stuff\patches")
bak.mkdir(parents=True, exist_ok=True)
shutil.copy2(f, bak / ("registry.bak_loop_" + str(int(time.time())) + ".py"))

s = f.read_text(encoding="utf-8")

OLD_LOOP = (
    '        # Istanze singleton per tool dello stesso modulo\n'
    '        _instances = {}\n'
    '        for name, cls in tool_classes.items():\n'
    '            cls_name = cls.__name__\n'
    '            if cls_name not in _instances:\n'
    '                try:\n'
    '                    _instances[cls_name] = cls(self.config)\n'
    '                    self.log.info(f"Tool caricato: {cls_name}")\n'
    '                except Exception as e:\n'
    '                    self.log.warning(f"Tool non disponibile {cls_name}: {e}")\n'
    '                    _instances[cls_name] = None\n'
    '            self._tools[name] = _instances[cls_name]'
)

NEW_LOOP = (
    '        # Istanze singleton per tool dello stesso modulo\n'
    '        _instances = {}\n'
    '        for name, cls in tool_classes.items():\n'
    '            # Lambda: registra direttamente senza istanziare\n'
    '            if callable(cls) and not isinstance(cls, type):\n'
    '                self._tools[name] = cls\n'
    '                self.log.info(f"Tool caricato: {name}")\n'
    '                continue\n'
    '            # Classe: istanzia con config (singleton per classe)\n'
    '            cls_name = cls.__name__\n'
    '            if cls_name not in _instances:\n'
    '                try:\n'
    '                    _instances[cls_name] = cls(self.config)\n'
    '                    self.log.info(f"Tool caricato: {cls_name}")\n'
    '                except Exception as e:\n'
    '                    self.log.warning(f"Tool non disponibile {cls_name}: {e}")\n'
    '                    _instances[cls_name] = None\n'
    '            self._tools[name] = _instances[cls_name]'
)

if OLD_LOOP in s:
    s = s.replace(OLD_LOOP, NEW_LOOP)
    try:
        ast.parse(s)
        f.write_text(s, encoding="utf-8")
        print("Fix OK - registry.py salvato")
    except SyntaxError as e:
        print("ERRORE sintassi: " + str(e))
        exit(1)
else:
    print("Pattern non trovato - mostro righe 62-74:")
    for i, l in enumerate(Path(r"A:\dustai\src\tools\registry.py").read_text(encoding="utf-8").splitlines(), 1):
        if 61 <= i <= 75:
            print(str(i).rjust(4), repr(l))
    exit(1)

# Anche execute() deve gestire lambda vs istanza
# Vediamo come chiama i tool
EXEC_FILE = Path(r"A:\dustai\src\tools\registry.py")
s2 = EXEC_FILE.read_text(encoding="utf-8")

# Cerca metodo execute
lines = s2.splitlines()
for i, l in enumerate(lines, 1):
    if "def execute" in l:
        print("\nMetodo execute trovato a riga " + str(i) + ":")
        for j in range(i-1, min(i+20, len(lines))):
            print(str(j+1).rjust(4), lines[j])
        break

import subprocess
from datetime import datetime
ts = datetime.now().strftime("%Y-%m-%d %H:%M")
for cmd in [
    ["git", "add", "src/tools/registry.py"],
    ["git", "commit", "-m", "fix: registry _register_all gestisce lambda e classi separatamente " + ts],
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

print("\nRiavvia DUST - il warning Tool non disponibile dovrebbe sparire.")
