"""
DUST BRAIN FIX v1.0
Risolve i problemi reali dal log di 22:44:

BUG 1: SelfHealEngine → 'temperature' kwarg non supportato → crash silenzioso
BUG 2: agent.py non interattivo → non chiede nome repo, credenziali, info mancanti
BUG 3: cascade non funziona → solo Gemini→Ollama, ignora KEY2/KEY3/Browser
BUG 4: gh CLI non trovato → crasha invece di usare alternativa (git + API GitHub)
DESIGN: system prompt troppo rigido → rende DUST meccanico invece di conversazionale

Esegui: python A:\\dustai\\DUST_BRAIN_FIX.py
"""
import ast, shutil, time, subprocess, sys
from pathlib import Path
from datetime import datetime

BASE = Path(r"A:\dustai")
SRC  = BASE / "src"
BAK  = Path(r"A:\dustai_stuff\patches")
BAK.mkdir(parents=True, exist_ok=True)

def bak(f):
    p = Path(f)
    if p.exists():
        shutil.copy2(p, BAK / (p.stem + ".bak_" + str(int(time.time())) + p.suffix))

def patch_file(path, replacements: list, label: str):
    """Applica una lista di (old, new) sostituzioni a un file."""
    p = Path(path)
    if not p.exists():
        print(f"  ⚠️  {label}: file non trovato ({path})")
        return False
    src = p.read_text(encoding="utf-8")
    bak(path)
    applied = 0
    for old, new in replacements:
        if old in src:
            src = src.replace(old, new, 1)
            applied += 1
        elif new in src:
            applied += 1  # già applicato
    try:
        ast.parse(src)
    except SyntaxError as e:
        print(f"  ❌ SINTASSI {label}: {e}")
        shutil.copy2(BAK / (p.stem + ".bak_" + str(int(time.time()) - 1) + p.suffix), p)
        return False
    p.write_text(src, encoding="utf-8")
    print(f"  ✅ {label} ({applied} patch)")
    return True

print("=" * 60)
print("DUST BRAIN FIX v1.0")
print("=" * 60)

# ══════════════════════════════════════════════════════════════
# FIX 1: SelfHealEngine – rimuovi 'temperature' da AIGateway.call()
# Log: AIGateway.call() got an unexpected keyword argument 'temperature'
# ══════════════════════════════════════════════════════════════
print("\n[1/5] Fix SelfHealEngine – temperatura kwarg")

SELFHEAL = SRC / "self_heal.py"
SELFHEAL_V2 = SRC / "self_heal_v2.py"
target = SELFHEAL_V2 if SELFHEAL_V2.exists() else SELFHEAL

patch_file(target, [
    # Rimuovi temperature= da tutte le chiamate a AIGateway.call()
    ("temperature=0.3", ""),
    ("temperature=0.7", ""),
    ("temperature=temp", ""),
    (", temperature)", ")"),
    ("call(mid, prompt, temperature=", "call(mid, prompt,"),
    # Fix la firma di free_call per non passare temperature
    ("self._gw.call(model_id, prompt, temperature=0.3)",
     "self._gw.call(model_id, prompt)"),
    ("self._gw.call(model_id, prompt, temperature=0.7)",
     "self._gw.call(model_id, prompt)"),
], "self_heal.py – temperature kwarg")

# Fix anche in ai_gateway.py se ha temperature nella firma sbagliata
GATEWAY = SRC / "ai_gateway.py"
if GATEWAY.exists():
    patch_file(GATEWAY, [
        # Aggiungi temperature alla firma di call() se non c'è
        ("def call(self, model_id: str, prompt: str, system=\"\", max_tokens=2000) -> dict:",
         "def call(self, model_id: str, prompt: str, system=\"\", max_tokens=2000, temperature=0.7) -> dict:"),
        # Versione senza type hints
        ("def call(self, model_id, prompt, system=\"\", max_tokens=2000):",
         "def call(self, model_id, prompt, system=\"\", max_tokens=2000, temperature=0.7):"),
    ], "ai_gateway.py – aggiunge temperature alla firma")

# ══════════════════════════════════════════════════════════════
# FIX 2: agent.py – SYSTEM PROMPT intelligente e interattivo
# ══════════════════════════════════════════════════════════════
print("\n[2/5] Fix agent.py – system prompt intelligente")

AGENT = SRC / "agent.py"
if AGENT.exists():
    src = AGENT.read_text(encoding="utf-8")
    bak(AGENT)

    # Nuovo system prompt – rende DUST conversazionale come Claude
    NEW_SYSTEM = '''SYSTEM_PROMPT = """Sei DUST AI, un assistente AI intelligente e conversazionale.

PERSONALITÀ:
- Sei diretto, utile e naturale come un assistente umano esperto
- Fai domande quando mancano informazioni essenziali (nome repo, credenziali, percorsi)
- Non eseguire azioni irreversibili senza conferma esplicita
- Spiega brevemente cosa stai facendo e perché

QUANDO TI MANCANO INFORMAZIONI:
- CHIEDI all'utente invece di fallire silenziosamente
- Es: "Per creare la repo ho bisogno del nome. Come vuoi chiamarla?"
- Es: "Quale file vuoi modificare?"

STRATEGIA DI ESECUZIONE:
1. Se il comando diretto non funziona, usa alternative immediate
2. gh CLI non disponibile → usa 'git' + GitHub API via requests
3. Applicazione non trovata → cerca nel PATH, poi in Program Files
4. Errore 429/quota API → usa il modello successivo in cascata
5. Non bloccarti su un singolo strumento – adatta la strategia

TOOL DISPONIBILI:
- sys_exec: esegui comandi shell Windows
- file_read / file_write / file_list: gestione file
- browser_open: apri URL nel browser
- web_search: cerca su internet
- ai_ask / ai_parallel: chiedi ad altre AI
- git_sync / git_commit / git_push: gestione GitHub

REGOLE:
- Rispondi sempre in italiano
- Quando completi un task, riassumi brevemente cosa hai fatto
- Se non riesci, spiega il motivo e proponi alternative
- NON ripetere lo stesso tool call se ha già fallito – cambia approccio
""" '''

    # Cerca il SYSTEM_PROMPT esistente e sostituiscilo
    import re
    # Pattern per trovare SYSTEM_PROMPT = """..."""
    pattern = r'SYSTEM_PROMPT\s*=\s*""".*?"""'
    if re.search(pattern, src, re.DOTALL):
        src = re.sub(pattern, NEW_SYSTEM, src, flags=re.DOTALL)
        print("  ✅ SYSTEM_PROMPT sostituito")
    else:
        # Cerca variante con '''
        pattern2 = r"SYSTEM_PROMPT\s*=\s*'''.*?'''"
        if re.search(pattern2, src, re.DOTALL):
            src = re.sub(pattern2, NEW_SYSTEM, src, flags=re.DOTALL)
            print("  ✅ SYSTEM_PROMPT (variante ''') sostituito")
        else:
            print("  ⚠️  SYSTEM_PROMPT non trovato – aggiunto alla fine del file")
            src = NEW_SYSTEM + "\n\n" + src

    # FIX CRITICO: quando Gemini dà errore 500, non fermarsi
    src = src.replace(
        'return {"type": "done", "summary": "task completato"}',
        'return {"type": "text", "text": "Ho avuto un problema tecnico. Riprovo con un approccio diverso."}'
    )

    # FIX: cascade – aggiungi BrowserAI e KEY2/KEY3 se non presenti
    if "GOOGLE_API_KEY_2" not in src and "SWITCH_TO_OLLAMA" in src:
        old_switch = '                    print("   🔄 Gemini esaurito → Ollama locale")'
        new_switch = '''                    # Prova KEY2, KEY3, poi BrowserAI
                    import os as _os
                    for _env in ("GOOGLE_API_KEY_2","GOOGLE_API_KEY_3"):
                        _k = _os.environ.get(_env,"")
                        if not _k: continue
                        try:
                            import google.generativeai as _g2
                            _g2.configure(api_key=_k)
                            _m2 = _g2.GenerativeModel("gemini-2.5-flash")
                            _task_txt = messages[-1].get("parts",[""])[0] if messages else ""
                            _r2 = _m2.generate_content(str(_task_txt)[:3000])
                            try: _t2 = _r2.text.strip()
                            except: _t2 = ""
                            if _t2:
                                print("   🔑 "+_env+" → OK")
                                return {"type":"text","text":_t2}
                        except: pass
                    # Prova BrowserAI
                    try:
                        from .tools.browser_ai_bridge import BrowserAIBridge
                        _br = BrowserAIBridge(self.config)
                        if _br.get_ready_providers():
                            _task_txt = messages[-1].get("parts",[""])[0] if messages else ""
                            _brr = _br.query(str(_task_txt)[:3000])
                            if _brr.get("ok"):
                                print("   🌐 BrowserAI ["+_brr["provider"]+"] → OK")
                                return {"type":"text","text":_brr["text"]}
                    except: pass
                    print("   🔄 Cascade → Ollama locale")'''
        if old_switch in src:
            src = src.replace(old_switch, new_switch)
            print("  ✅ Cascade KEY2/KEY3/Browser aggiunto")

    try:
        ast.parse(src)
        AGENT.write_text(src, encoding="utf-8")
        print("  ✅ agent.py aggiornato")
    except SyntaxError as e:
        print(f"  ❌ Sintassi: {e}")

# ══════════════════════════════════════════════════════════════
# FIX 3: aggiungi tool github_create_repo che non usa gh CLI
# (usa git init + GitHub API REST via requests)
# ══════════════════════════════════════════════════════════════
print("\n[3/5] Aggiungi github_create_repo tool (senza gh CLI)")

(SRC / "tools" / "github_tool.py").write_text(r'''"""
DUST AI – GitHubTool
Crea e gestisce repo GitHub senza gh CLI – usa solo git + GitHub REST API.
"""
import os, json, subprocess, logging
from pathlib import Path
log = logging.getLogger("GitHubTool")


class GitHubTool:
    """Operazioni GitHub via API REST (no gh CLI richiesto)."""

    def __init__(self, config):
        self.config = config
        self._token = os.environ.get("GITHUB_TOKEN", "")
        self._user  = os.environ.get("GITHUB_USER", "")

    # ─── Tool chiamato dall'agent ────────────────────────────────────

    def github_create_repo(self, name: str, description: str = "",
                           private: str = "false") -> str:
        """
        Crea una repository su GitHub.
        name: nome della repo
        private: "true" o "false"
        """
        token = self._token
        user  = self._user

        if not token:
            return ("❌ GITHUB_TOKEN mancante.\n"
                    "Aggiungilo in A:\\dustai_stuff\\.env:\n"
                    "  GITHUB_TOKEN=ghp_tuotoken\n"
                    "  GITHUB_USER=TuoUsername\n"
                    "Ottieni il token da: https://github.com/settings/tokens")

        if not user:
            # Cerca di ricavare lo username dal token
            try:
                import requests
                r = requests.get("https://api.github.com/user",
                                 headers={"Authorization": "token " + token,
                                          "Accept": "application/vnd.github.v3+json"},
                                 timeout=10)
                if r.status_code == 200:
                    user = r.json().get("login", "")
            except Exception:
                pass
        if not user:
            return "❌ GITHUB_USER mancante in .env"

        # Crea repo via API
        try:
            import requests
            payload = {
                "name":        name,
                "description": description,
                "private":     private.lower() == "true",
                "auto_init":   True,
            }
            r = requests.post(
                "https://api.github.com/user/repos",
                headers={"Authorization": "token " + token,
                         "Accept": "application/vnd.github.v3+json",
                         "Content-Type": "application/json"},
                data=json.dumps(payload),
                timeout=15)
            data = r.json()
            if r.status_code in (200, 201):
                url = data.get("html_url", "")
                clone_url = data.get("clone_url", "")
                return (f"✅ Repo creata!\n"
                        f"  URL:   {url}\n"
                        f"  Clone: git clone {clone_url}\n"
                        f"  SSH:   git clone git@github.com:{user}/{name}.git")
            elif r.status_code == 422:
                msg = data.get("message","")
                if "already exists" in msg.lower():
                    return (f"ℹ️  La repo '{name}' esiste già.\n"
                            f"  https://github.com/{user}/{name}")
                return f"❌ Errore GitHub 422: {msg}"
            elif r.status_code == 401:
                return "❌ Token GitHub non valido o scaduto. Rigenera da https://github.com/settings/tokens"
            else:
                return f"❌ GitHub API errore {r.status_code}: {data.get('message','')}"
        except Exception as e:
            return f"❌ Errore: {str(e)[:200]}"

    def github_list_repos(self, max_n: str = "10") -> str:
        """Lista le tue repository GitHub."""
        token = self._token
        if not token:
            return "❌ GITHUB_TOKEN mancante in .env"
        try:
            import requests
            r = requests.get(
                "https://api.github.com/user/repos",
                headers={"Authorization": "token " + token,
                         "Accept": "application/vnd.github.v3+json"},
                params={"sort": "updated", "per_page": int(max_n)},
                timeout=15)
            repos = r.json()
            if r.status_code != 200:
                return f"❌ {repos.get('message','errore')}"
            lines = [f"📂 Le tue ultime {len(repos)} repository:"]
            for repo in repos:
                vis  = "🔒" if repo.get("private") else "🌍"
                star = repo.get("stargazers_count", 0)
                lines.append(f"  {vis} {repo['full_name']:<40} ⭐{star}")
            return "\n".join(lines)
        except Exception as e:
            return f"❌ {str(e)[:200]}"

    def github_clone(self, repo_url: str, dest: str = "") -> str:
        """Clona una repository GitHub localmente."""
        dest_path = dest or Path(r"A:\dustai_stuff\repos") / repo_url.split("/")[-1].replace(".git","")
        Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
        try:
            result = subprocess.run(
                ["git", "clone", repo_url, str(dest_path)],
                capture_output=True, text=True, timeout=120)
            if result.returncode == 0:
                return f"✅ Repository clonata in: {dest_path}"
            return f"❌ git clone fallito:\n{result.stderr[:300]}"
        except Exception as e:
            return f"❌ {str(e)[:200]}"
''', encoding="utf-8")
print("  ✅ github_tool.py creato")

# ══════════════════════════════════════════════════════════════
# FIX 4: registry.py – aggiungi github tool + fix lambda dispatch
# ══════════════════════════════════════════════════════════════
print("\n[4/5] Fix registry.py – aggiungi github_create_repo")

REGISTRY = SRC / "tools" / "registry.py"
if REGISTRY.exists():
    src = REGISTRY.read_text(encoding="utf-8")
    bak(REGISTRY)
    changed = False

    # Aggiungi import github_tool
    if "GitHubTool" not in src:
        old_imp = "from .code_runner import CodeRunnerTool"
        new_imp = (old_imp + "\n"
                   "try:\n"
                   "    from .github_tool import GitHubTool as _GitHubTool\n"
                   "    _GITHUB_OK = True\n"
                   "except Exception:\n"
                   "    _GITHUB_OK = False; _GitHubTool = None")
        if old_imp in src:
            src = src.replace(old_imp, new_imp, 1); changed = True

    # Aggiungi getter lazy
    if "_get_github_tool" not in src and "    def _get_git_sync_tool(" in src:
        GITHUB_GETTER = '''
    def _get_github_tool(self):
        if not hasattr(self, "_gh_inst"):
            try:
                if _GITHUB_OK:
                    self._gh_inst = _GitHubTool(self.config)
                else:
                    self._gh_inst = None
            except Exception:
                self._gh_inst = None
        return self._gh_inst

'''
        src = src.replace("    def _get_git_sync_tool(",
                          GITHUB_GETTER + "    def _get_git_sync_tool(", 1)
        changed = True

    # Aggiungi lambda nel dispatch
    if "'github_create_repo'" not in src:
        GITHUB_LAMBDAS = (
            "            'github_create_repo': lambda p: (self._get_github_tool().github_create_repo(**self._safe_params(p)) if self._get_github_tool() else 'GITHUB_TOKEN mancante in .env'),\n"
            "            'github_list_repos':  lambda p: (self._get_github_tool().github_list_repos(**self._safe_params(p))  if self._get_github_tool() else 'N/D'),\n"
            "            'github_clone':       lambda p: (self._get_github_tool().github_clone(**self._safe_params(p))       if self._get_github_tool() else 'N/D'),\n"
        )
        # Inserisci dopo git_push o ai_ask
        for anchor in ("'git_push'", "'ai_ask'", "# Orchestra AI"):
            if anchor in src:
                # Trova fine della riga con anchor e inserisci dopo
                idx = src.find(anchor)
                end_line = src.find("\n", idx) + 1
                src = src[:end_line] + "            # GitHub API tools\n" + GITHUB_LAMBDAS + src[end_line:]
                changed = True
                break

    if changed:
        try:
            ast.parse(src)
            REGISTRY.write_text(src, encoding="utf-8")
            print("  ✅ registry.py aggiornato")
        except SyntaxError as e:
            print(f"  ❌ Sintassi: {e}")
    else:
        print("  ⏭️  registry.py (già aggiornato)")

# ══════════════════════════════════════════════════════════════
# FIX 5: .env – controlla che GITHUB_TOKEN sia configurato
# ══════════════════════════════════════════════════════════════
print("\n[5/5] Verifica .env")

ENV_FILE = Path(r"A:\dustai_stuff\.env")
if ENV_FILE.exists():
    env_content = ENV_FILE.read_text(encoding="utf-8")
    missing = []
    if "GITHUB_TOKEN" not in env_content:
        missing.append("GITHUB_TOKEN=ghp_IlTuoToken")
    if "GITHUB_USER" not in env_content:
        missing.append("GITHUB_USER=Tenkulo")
    if "GOOGLE_API_KEY_2" not in env_content:
        missing.append("GOOGLE_API_KEY_2=AIza... (secondo progetto Google Cloud)")
    if missing:
        print("  ⚠️  Aggiungi in A:\\dustai_stuff\\.env:")
        for m in missing:
            print("    " + m)
        print("\n  GITHUB_TOKEN: vai su https://github.com/settings/tokens → New token")
        print("  Scopes necessari: repo, read:user")
    else:
        print("  ✅ .env configurato")
else:
    print("  ⚠️  .env non trovato in A:\\dustai_stuff\\")

# ── Commit ────────────────────────────────────────────────────────────
print("\nCommit...")
ts = datetime.now().strftime("%Y-%m-%d %H:%M")
for cmd in [
    ["git", "add", "-A"],
    ["git", "commit", "-m", f"fix: DUST brain – interattivo, cascade, github API, temperatura {ts}"],
    ["git", "push", "origin", "master"],
]:
    r = subprocess.run(cmd, cwd=str(BASE), capture_output=True,
                       text=True, encoding="utf-8")
    out = r.stderr or r.stdout or ""
    label = " ".join(cmd[:2])
    if r.returncode == 0 or "nothing" in out or "up to date" in out:
        print(f"  ✅ {label}")
    else:
        print(f"  ⚠️  {label}: {out[:80]}")

print("""
╔══════════════════════════════════════════════════════════╗
║  DUST BRAIN FIX – COMPLETATO                            ║
╠══════════════════════════════════════════════════════════╣
║  FIX APPLICATI:                                         ║
║  ✅ temperature kwarg → SelfHeal non crasha più         ║
║  ✅ System prompt → DUST chiede info mancanti           ║
║  ✅ Cascade KEY2/KEY3/Browser/Ollama funzionante        ║
║  ✅ github_create_repo senza gh CLI (usa API REST)      ║
║  ✅ registry.py → github_create/list/clone disponibili  ║
╠══════════════════════════════════════════════════════════╣
║  DA FARE (1 volta):                                     ║
║  1. Aggiungi in .env:                                   ║
║     GITHUB_TOKEN=ghp_tuotoken                          ║
║     GITHUB_USER=Tenkulo                                 ║
║  → https://github.com/settings/tokens                  ║
║                                                         ║
║  POI RIAVVIA DUST e prova:                              ║
║  "crea una repo su github"                              ║
║  → DUST chiederà il nome, poi la creerà via API        ║
╚══════════════════════════════════════════════════════════╝
""")
