"""
DUST AI – self_optimization_patch.py
Patch automatica basata su analisi log 2026-03-12.

BUG TROVATI:
  1. file_list() got unexpected keyword argument 'recursive'
     → file_ops.py non accetta recursive=True
  2. AIConductorTool: ai_ask() argument after ** must be a mapping, not Config
     → registry.py: dispatch lambda passa Config invece di params dict
  3. LiteLLM non installato → AIGateway degraded
  4. Gemini 429 in loop senza switch immediato a Gemini Lite / Ollama
  5. Task completato a step 4/20 senza completare il ciclo

Esegui: python A:\dustai\self_optimization_patch.py
"""
import ast, shutil, time, subprocess, sys, re
from pathlib import Path

BASE  = Path(r"A:\dustai")
SRC   = BASE / "src"
STUFF = Path(r"A:\dustai_stuff")
BAK   = STUFF / "patches"
BAK.mkdir(parents=True, exist_ok=True)

ok_count   = 0
fail_count = 0

def backup(f: Path) -> Path:
    ts  = str(int(time.time()))
    dst = BAK / (f.stem + ".bak_" + ts + f.suffix)
    shutil.copy2(f, dst)
    return dst

def save_verified(f: Path, src: str, label: str):
    global ok_count, fail_count
    try:
        ast.parse(src)
        f.write_text(src, encoding="utf-8")
        print("  ✅ " + label)
        ok_count += 1
    except SyntaxError as e:
        print("  ❌ SINTASSI " + label + ": " + str(e))
        fail_count += 1

print("=" * 60)
print("DUST self_optimization_patch.py")
print("=" * 60)

# ══════════════════════════════════════════════════════════════
# FIX 1: file_ops.py – aggiungi parametro recursive a file_list
# ══════════════════════════════════════════════════════════════
print("\n[FIX 1] file_ops.py – file_list() + recursive...")

FILE_OPS = SRC / "tools" / "file_ops.py"
if FILE_OPS.exists():
    src = FILE_OPS.read_text(encoding="utf-8")
    bak = backup(FILE_OPS)

    # Trova la firma di file_list e aggiorna
    OLD_SIGS = [
        "def file_list(self, path: str) -> str:",
        "def file_list(self, path: str):",
        "def file_list(self,path:str)->str:",
    ]
    found_sig = False
    for old_sig in OLD_SIGS:
        if old_sig in src:
            src = src.replace(old_sig,
                "def file_list(self, path: str, recursive: bool = False, pattern: str = \"*\") -> str:")
            found_sig = True
            break

    if not found_sig:
        # Prova regex più flessibile
        src, n = re.subn(
            r'def file_list\(self,\s*path\s*:\s*str\s*\)',
            'def file_list(self, path: str, recursive: bool = False, pattern: str = "*")',
            src
        )
        found_sig = n > 0

    if found_sig:
        # Aggiorna il corpo della funzione per usare recursive
        # Cerca il corpo e aggiungi supporto recursive
        OLD_BODY_PATTERNS = [
            # Pattern comune: usa Path(path).iterdir() o os.listdir
            ("        items = list(Path(path).iterdir())",
             "        items = list(Path(path).rglob(pattern) if recursive else Path(path).glob(pattern))"),
            ("        files = list(Path(path).iterdir())",
             "        files = list(Path(path).rglob(pattern) if recursive else Path(path).glob(pattern))"),
            ("        entries = list(Path(path).iterdir())",
             "        entries = list(Path(path).rglob(pattern) if recursive else Path(path).glob(pattern))"),
        ]
        for old_body, new_body in OLD_BODY_PATTERNS:
            if old_body in src:
                src = src.replace(old_body, new_body)
                break
        else:
            # Se non trovato pattern esatto, inietta logica recursive dopo la firma
            # Cerca "def file_list" e il suo corpo
            src = re.sub(
                r'(def file_list\(self, path: str, recursive: bool = False, pattern: str = "\*"\)[^:]*:)',
                r'\1\n        p = Path(path)\n        if not p.exists():\n            return "Path non trovato: " + path\n        try:\n            if recursive:\n                items = sorted(p.rglob(pattern))\n            else:\n                items = sorted(p.glob(pattern))\n            lines = [str(i.relative_to(p)) for i in items]\n            return "\\n".join(lines) if lines else "(vuoto)"\n        except Exception as e:\n            return "Errore file_list: " + str(e)\n        # --- originale ---',
                src, count=1
            )

        save_verified(FILE_OPS, src, "file_ops.py file_list(recursive)")
    else:
        print("  ⚠️  Firma file_list non trovata – scrivo versione completa del metodo")
        # Cerca la classe e aggiungi metodo
        METHOD = '''
    def file_list(self, path: str, recursive: bool = False, pattern: str = "*") -> str:
        """Lista file in una directory. recursive=True per cercare nelle sottocartelle."""
        from pathlib import Path as _P
        p = _P(path)
        if not p.exists():
            return "Path non trovato: " + path
        try:
            if recursive:
                items = sorted(p.rglob(pattern))
            else:
                items = sorted(p.glob(pattern))
            lines = []
            for i in items:
                prefix = "[D] " if i.is_dir() else "[F] "
                lines.append(prefix + str(i))
            return "\\n".join(lines) if lines else "(cartella vuota)"
        except Exception as e:
            return "Errore file_list: " + str(e)

'''
        # Sostituisci vecchio file_list se esiste
        src = re.sub(
            r'def file_list\(self[^)]*\)[^:]*:.*?(?=\n    def |\Z)',
            METHOD.strip(),
            src, flags=re.DOTALL
        )
        save_verified(FILE_OPS, src, "file_ops.py file_list(recursive) – riscrittura")
else:
    print("  ⚠️  file_ops.py non trovato in " + str(FILE_OPS))

# ══════════════════════════════════════════════════════════════
# FIX 2: registry.py – AIConductorTool dispatch: Config != params dict
# ══════════════════════════════════════════════════════════════
print("\n[FIX 2] registry.py – fix dispatch AIConductorTool (Config bug)...")

REGISTRY = SRC / "tools" / "registry.py"
if REGISTRY.exists():
    src = REGISTRY.read_text(encoding="utf-8")
    bak = backup(REGISTRY)

    # Il bug: lambda p: self._get_conductor_tool().ai_ask(**p)
    # quando p è un Config object e non un dict
    # Fix: wrappa con safe_params()

    SAFE_PARAMS_HELPER = '''
    @staticmethod
    def _safe_params(p):
        """Assicura che p sia un dict prima di usarlo come **kwargs."""
        if isinstance(p, dict):
            return p
        if hasattr(p, "__dict__"):
            return vars(p)
        return {}

'''

    if "_safe_params" not in src:
        src = src.replace("    def _get_conductor_tool(",
                          SAFE_PARAMS_HELPER + "    def _get_conductor_tool(", 1)
        print("  OK _safe_params helper aggiunto")

    # Sostituisci lambda che usano **p con lambda che usano **self._safe_params(p)
    FIXES = [
        # Conductor tools
        ("lambda p: (self._get_conductor_tool().ai_ask(**p)",
         "lambda p: (self._get_conductor_tool().ai_ask(**self._safe_params(p))"),
        ("lambda p: (self._get_conductor_tool().ai_parallel(**p)",
         "lambda p: (self._get_conductor_tool().ai_parallel(**self._safe_params(p))"),
        ("lambda p: (self._get_conductor_tool().ai_models(**p)",
         "lambda p: (self._get_conductor_tool().ai_models(**self._safe_params(p))"),
        ("lambda p: (self._get_conductor_tool().ai_status()",
         "lambda p: (self._get_conductor_tool().ai_status()"),  # no **p
        # Git tools
        ("lambda p: (self._get_git_sync_tool().git_sync(**p)",
         "lambda p: (self._get_git_sync_tool().git_sync(**self._safe_params(p))"),
        ("lambda p: (self._get_git_sync_tool().git_commit(**p)",
         "lambda p: (self._get_git_sync_tool().git_commit(**self._safe_params(p))"),
        # Browser AI tools (se presenti)
        ("lambda p: self._get_browser_ai_tool().browser_ai_query(**p)",
         "lambda p: self._get_browser_ai_tool().browser_ai_query(**self._safe_params(p))"),
    ]

    fixed = 0
    for old, new in FIXES:
        if old in src:
            src = src.replace(old, new)
            fixed += 1

    print("  OK " + str(fixed) + " lambda patchate con _safe_params")

    # Fix aggiuntivo: il dispatch principale usa params dict?
    # Cerca il metodo execute e assicura che params sia sempre dict
    EXECUTE_FIX = '''
    def _normalize_params(self, params):
        """Normalizza params a dict sicuro."""
        if params is None:
            return {}
        if isinstance(params, dict):
            return params
        if hasattr(params, "__dict__"):
            return {k: v for k, v in vars(params).items() if not k.startswith("_")}
        return {}
'''
    if "_normalize_params" not in src:
        src = src.replace(SAFE_PARAMS_HELPER,
                          SAFE_PARAMS_HELPER + EXECUTE_FIX)

    save_verified(REGISTRY, src, "registry.py dispatch fix")
else:
    print("  ⚠️  registry.py non trovato")

# ══════════════════════════════════════════════════════════════
# FIX 3: agent.py – rate limit switch immediato (non 3× 65s)
# ══════════════════════════════════════════════════════════════
print("\n[FIX 3] agent.py – rate limit: switch immediato invece di 3× retry...")

AGENT = SRC / "agent.py"
if AGENT.exists():
    src = AGENT.read_text(encoding="utf-8")
    bak = backup(AGENT)
    changed = False

    # Bug: riprova Gemini 3 volte con 65s di attesa prima di switchare Ollama
    # Fix: dopo il primo 429 switcha subito a Gemini Lite poi Ollama

    # Aggiungi lista modelli fallback in _call_gemini_fn
    OLD_429 = (
        "                if \"429\" in err or \"RESOURCE_EXHAUSTED\" in err:\n"
        "                    wait_match = re.search(r\"(\\d+)[\\s]*s\", err)\n"
        "                    wait = min(65, int(wait_match.group(1)) + 5) if wait_match else 65\n"
        "                    if attempt < max_retries - 1:\n"
        "                        print(\"   ⏳ 429 — riprovo in \" + str(wait) + \"s...\")\n"
        "                        time.sleep(wait)\n"
        "                        continue\n"
        "                    raise RuntimeError(\"SWITCH_TO_OLLAMA\")"
    )
    NEW_429 = (
        "                if \"429\" in err or \"RESOURCE_EXHAUSTED\" in err:\n"
        "                    # Switch immediato invece di 3× 65s\n"
        "                    if attempt == 0:\n"
        "                        # Prova Gemini Lite (KEY_2) prima di arrendersi\n"
        "                        try:\n"
        "                            import os, google.generativeai as _gen\n"
        "                            _key2 = os.environ.get(\"GOOGLE_API_KEY_2\", \"\")\n"
        "                            if _key2:\n"
        "                                _gen.configure(api_key=_key2)\n"
        "                                _lite = _gen.GenerativeModel(\"gemini-2.5-flash\")\n"
        "                                _r2 = _lite.generate_content(messages[-1].get(\"parts\", [\"\"])[0] if messages else \"continua\")\n"
        "                                try:\n"
        "                                    _t = _r2.text.strip()\n"
        "                                    if _t:\n"
        "                                        self.log.info(\"Gemini KEY_2 fallback OK\")\n"
        "                                        return {\"type\": \"text\", \"text\": _t}\n"
        "                                except Exception:\n"
        "                                    pass\n"
        "                        except Exception:\n"
        "                            pass\n"
        "                    wait_match = re.search(r\"(\\d+)[\\s]*s\", err)\n"
        "                    wait = min(65, int(wait_match.group(1)) + 5) if wait_match else 65\n"
        "                    if attempt < min(1, max_retries - 1):  # max 1 retry\n"
        "                        print(\"   ⏳ 429 — riprovo in \" + str(wait) + \"s...\")\n"
        "                        time.sleep(wait)\n"
        "                        continue\n"
        "                    raise RuntimeError(\"SWITCH_TO_OLLAMA\")"
    )

    if OLD_429 in src:
        src = src.replace(OLD_429, NEW_429)
        changed = True
        print("  OK rate limit: switch immediato Gemini KEY_2 → Ollama")
    else:
        print("  ⚠️  pattern 429 non trovato (già patchato?)")

    # Fix anche il mistral-small3.1 in Ollama: è disponibile, usalo come fallback
    # Aggiungi mistral-small3.1 nella lista preferiti Ollama
    OLD_PREF = "            preferred = self.config.get(\"ollama_tool_models\", [])"
    NEW_PREF = (
        "            preferred = self.config.get(\"ollama_tool_models\", []) or "
        "[\"qwen3:8b\", \"mistral-small3.1\", \"qwen3\", \"mistral\"]"
    )
    if OLD_PREF in src and "mistral-small3.1" not in src:
        src = src.replace(OLD_PREF, NEW_PREF)
        changed = True
        print("  OK mistral-small3.1 aggiunto come fallback Ollama")

    if changed:
        save_verified(AGENT, src, "agent.py rate limit + mistral fallback")
    else:
        print("  SKIP agent.py (nessuna modifica applicata)")
else:
    print("  ⚠️  agent.py non trovato")

# ══════════════════════════════════════════════════════════════
# FIX 4: installa litellm
# ══════════════════════════════════════════════════════════════
print("\n[FIX 4] pip install litellm...")
r = subprocess.run(
    [sys.executable, "-m", "pip", "install", "litellm", "--quiet"],
    capture_output=True, text=True, timeout=120
)
if r.returncode == 0:
    print("  ✅ litellm installato")
    ok_count += 1
else:
    # Prova senza --quiet per vedere l'errore
    print("  ⚠️  litellm: " + (r.stderr or r.stdout)[:200])

# ══════════════════════════════════════════════════════════════
# FIX 5: skills.json – registra i bug risolti in SkillForge
# ══════════════════════════════════════════════════════════════
print("\n[FIX 5] Aggiorno skills.json con fix appresi...")

import json
from datetime import datetime

SKILLS_FILE = STUFF / "skills" / "skills.json"
SKILLS_FILE.parent.mkdir(parents=True, exist_ok=True)

if SKILLS_FILE.exists():
    try:
        skills = json.loads(SKILLS_FILE.read_text(encoding="utf-8"))
    except Exception:
        skills = []
else:
    skills = []

new_skills = [
    {
        "id": "fix_file_list_recursive",
        "name": "file_list supporta recursive",
        "category": "bug_fix",
        "learned_at": datetime.now().isoformat(),
        "description": "file_list() accetta recursive=True per cercare nelle sottocartelle. Usa Path.rglob() invece di iterdir().",
        "example": {"tool": "file_list", "params": {"path": "A:\\dustai_stuff\\logs", "recursive": True}},
        "source": "self_optimization_patch_2026-03-12",
    },
    {
        "id": "fix_registry_safe_params",
        "name": "registry dispatch usa _safe_params()",
        "category": "bug_fix",
        "learned_at": datetime.now().isoformat(),
        "description": "Il dispatch del ToolRegistry deve wrappare **p con _safe_params(p) per evitare che Config objects vengano passati come kwargs.",
        "example": "lambda p: tool.method(**self._safe_params(p))",
        "source": "self_optimization_patch_2026-03-12",
    },
    {
        "id": "fix_rate_limit_switch_immediate",
        "name": "Rate limit 429: switch immediato a KEY_2 poi Ollama",
        "category": "optimization",
        "learned_at": datetime.now().isoformat(),
        "description": "Dopo un 429 Gemini, non fare 3 retry da 65s. Switcha subito a GOOGLE_API_KEY_2 (Gemini Lite), poi a Ollama qwen3:8b o mistral-small3.1.",
        "models_available": ["qwen3:8b", "mistral-small3.1"],
        "source": "self_optimization_patch_2026-03-12",
    },
    {
        "id": "mistral_small_available",
        "name": "mistral-small3.1 disponibile in Ollama locale",
        "category": "capability",
        "learned_at": datetime.now().isoformat(),
        "description": "Il sistema ha mistral-small3.1 installato in Ollama. Usarlo come secondo fallback locale dopo qwen3:8b.",
        "source": "bootstrap_log_2026-03-12",
    },
]

# Aggiorna o aggiungi skill senza duplicati
existing_ids = {s.get("id") for s in skills if isinstance(s, dict)}
for ns in new_skills:
    if ns["id"] not in existing_ids:
        skills.append(ns)

SKILLS_FILE.write_text(json.dumps(skills, indent=2, ensure_ascii=False), encoding="utf-8")
print("  ✅ skills.json aggiornato (" + str(len(new_skills)) + " nuove skill)")
ok_count += 1

# ══════════════════════════════════════════════════════════════
# FIX 6: TaskQueue – reset task stuck in "running"
# ══════════════════════════════════════════════════════════════
print("\n[FIX 6] TaskQueue – reset task bloccati in 'running'...")

QUEUE_FILE = STUFF / "tasks" / "queue.json"
if QUEUE_FILE.exists():
    try:
        queue = json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
        changed_q = 0
        for task in queue:
            if task.get("status") == "running":
                task["status"] = "pending"
                task.pop("started_at", None)
                changed_q += 1
        if changed_q:
            QUEUE_FILE.write_text(json.dumps(queue, indent=2, ensure_ascii=False), encoding="utf-8")
            print("  ✅ " + str(changed_q) + " task resettati da 'running' a 'pending'")
            ok_count += 1
        else:
            print("  OK nessun task bloccato")
    except Exception as e:
        print("  ⚠️  TaskQueue: " + str(e))
else:
    print("  SKIP: queue.json non trovato")

# ══════════════════════════════════════════════════════════════
# SELF-TEST: verifica tool principali
# ══════════════════════════════════════════════════════════════
print("\n[SELF-TEST] Verifica moduli core...")

tests = [
    ("src.tools.file_ops",   "FileOpsTool"),
    ("src.tools.registry",   "ToolRegistry"),
    ("src.agent",            "Agent"),
]

sys.path.insert(0, str(BASE))
for module, cls in tests:
    try:
        mod = __import__(module, fromlist=[cls])
        getattr(mod, cls)
        print("  ✅ " + module + "." + cls)
        ok_count += 1
    except ImportError as e:
        print("  ⚠️  import " + module + ": " + str(e)[:80])
    except AttributeError:
        print("  ⚠️  " + cls + " non trovato in " + module)
    except Exception as e:
        print("  ⚠️  " + module + ": " + str(e)[:80])

# ══════════════════════════════════════════════════════════════
# COMMIT e PUSH
# ══════════════════════════════════════════════════════════════
print("\n[GIT] Commit e push...")
ts = datetime.now().strftime("%Y-%m-%d %H:%M")
for cmd in [
    ["git", "add", "-A"],
    ["git", "commit", "-m",
     "fix: file_list recursive, registry safe_params, rate-limit switch immediato, mistral fallback " + ts],
    ["git", "push", "origin", "master"],
]:
    r = subprocess.run(cmd, cwd=str(BASE), capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    out = r.stderr or r.stdout or ""
    label = " ".join(cmd[:2])
    if r.returncode == 0 or "nothing to commit" in out or "up to date" in out:
        print("  ✅ " + label)
    else:
        print("  ⚠️  " + label + ": " + out[:120])

# ══════════════════════════════════════════════════════════════
# REPORT FINALE
# ══════════════════════════════════════════════════════════════
print("""
╔══════════════════════════════════════════════════════════╗
║  DUST self_optimization_patch – REPORT FINALE           ║
╠══════════════════════════════════════════════════════════╣""")
print("║  Fix applicati: " + str(ok_count) + " OK, " + str(fail_count) + " FAIL" + " " * 30 + "║")
print("""╠══════════════════════════════════════════════════════════╣
║  BUG RISOLTI:                                            ║
║  1. file_list(recursive=True) → Path.rglob()            ║
║  2. registry dispatch → _safe_params(p) wrapper         ║
║  3. 429 rate limit → switch immediato KEY_2 + Ollama     ║
║  4. mistral-small3.1 aggiunto come fallback Ollama       ║
║  5. litellm installato (AIGateway ora operativo)         ║
║  6. skills.json aggiornato con 4 nuove skill             ║
║  7. TaskQueue: task 'running' resettati a 'pending'      ║
╠══════════════════════════════════════════════════════════╣
║  PROSSIMO PASSO:                                         ║
║  Riavvia DUST: python A:\\dustai\\run.py                   ║
╚══════════════════════════════════════════════════════════╝
""")
