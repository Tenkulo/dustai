"""Fix chirurgico _safe_params riga 84 - esegui: python A:\dustai\fix_safe_params2.py"""
import ast, shutil, time
from pathlib import Path

f   = Path(r"A:\dustai\src\tools\registry.py")
bak = Path(r"A:\dustai_stuff\patches")
bak.mkdir(parents=True, exist_ok=True)

s = f.read_text(encoding="utf-8")
shutil.copy2(f, bak / ("registry.bak_" + str(int(time.time())) + ".py"))

OLD = (
    '    @staticmethod\n'
    '    def _safe_params(p):\n'
    '        """Assicura che p sia un dict prima di usarlo come **kwargs."""\n'
    '        if isinstance(p, dict):\n'
    '            return p\n'
    '        if hasattr(p, "__dict__"):\n'
    '            return vars(p)\n'
    '        return {}'
)

NEW = (
    '    @staticmethod\n'
    '    def _safe_params(p):\n'
    '        """Converte p in dict sicuro per **kwargs, filtrando attributi privati."""\n'
    '        if p is None:\n'
    '            return {}\n'
    '        if isinstance(p, dict):\n'
    '            return {k: v for k, v in p.items()\n'
    '                    if isinstance(k, str) and not k.startswith("_")}\n'
    '        if hasattr(p, "__dict__"):\n'
    '            return {k: v for k, v in vars(p).items()\n'
    '                    if isinstance(k, str) and not k.startswith("_")\n'
    '                    and isinstance(v, (str, int, float, bool, list, type(None)))}\n'
    '        return {}'
)

if OLD in s:
    s = s.replace(OLD, NEW)
    try:
        ast.parse(s)
        f.write_text(s, encoding="utf-8")
        print("Fix OK - registry.py salvato")
    except SyntaxError as e:
        print("ERRORE sintassi: " + str(e))
else:
    print("Pattern non trovato - mostro righe 78-86:")
    for i, l in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
        if 77 <= i <= 87:
            print(str(i).rjust(4), repr(l))
