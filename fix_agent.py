"""Fix agent.py - esegui con: python A:\dustai\fix_agent.py"""
from pathlib import Path

f = Path(r"A:\dustai\src\agent.py")
s = f.read_text(encoding="utf-8")

# Fix 1: response.text sicuro (finish_reason=10 non ha testo)
OLD1 = (
    "                # Nessuna function call \u2192 testo\n"
    "                return {\"type\": \"text\", \"text\": response.text.strip()}"
)
NEW1 = (
    "                # Nessuna function call \u2192 testo\n"
    "                try:\n"
    "                    txt = response.text.strip()\n"
    "                except Exception:\n"
    "                    txt = \"\"\n"
    "                if not txt:\n"
    "                    return {\"type\": \"done\", \"summary\": \"task completato\"}\n"
    "                return {\"type\": \"text\", \"text\": txt}"
)

if OLD1 in s:
    s = s.replace(OLD1, NEW1)
    print("Fix 1 OK: response.text sicuro")
else:
    print("Fix 1 SKIP: stringa non trovata (gia' patchato?)")

# Fix 2: clamp wait a max 65s
OLD2 = "                    wait = int(wait_match.group(1)) + 5 if wait_match else 65"
NEW2 = "                    wait = min(65, int(wait_match.group(1)) + 5) if wait_match else 65"

if OLD2 in s:
    s = s.replace(OLD2, NEW2)
    print("Fix 2 OK: rate limit clamp 65s")
else:
    print("Fix 2 SKIP: stringa non trovata (gia' patchato?)")

# Verifica sintassi
import ast
try:
    ast.parse(s)
    print("Sintassi OK")
except SyntaxError as e:
    print("ERRORE sintassi:", e)
    exit(1)

f.write_text(s, encoding="utf-8")
print("agent.py salvato.")
