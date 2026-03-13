#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║  DUST AI — FIX PATCH #4  (Agent reasoning + autonomia reale)    ║
║                                                                  ║
║  Fix A: System prompt con ragionamento Chain-of-Thought          ║
║  Fix B: BrowserAI usato solo per azioni atomiche, MAI come relay ║
║  Fix C: Task planner — DUST pianifica, esegue, rapporta          ║
║  Fix D: Tool file_write per creare file su desktop/filesystem    ║
║                                                                  ║
║  Esegui: cd A:\\dustai && python DUST_FIX4_PATCH.py             ║
╚══════════════════════════════════════════════════════════════════╝
"""
import os, sys, subprocess, textwrap
from pathlib import Path

BASE = Path(r"A:\dustai")
SRC  = BASE / "src"

FILES: dict[str, str] = {}

# ══════════════════════════════════════════════════════════════════
#  A)  agent.py — system prompt con ragionamento reale
# ══════════════════════════════════════════════════════════════════
FILES["src/agent.py"] = r'''
"""
DUST Agent v4.3
- Ragionamento Chain-of-Thought prima di agire
- BrowserAI usato solo per azioni atomiche (clicca/scrivi/leggi)
- MAI delega un task completo a un'altra AI — DUST ragiona da solo
"""
import json
import re
import time
import logging
import threading
from typing import Any

logger = logging.getLogger("dust.agent")

try:
    from config import (GEMINI_KEYS, GEMINI_MODEL, GROQ_API_KEY, GROQ_MODEL,
                        OLLAMA_BASE_URL, OLLAMA_MODELS, OLLAMA_TIMEOUT)
except ImportError:
    GEMINI_KEYS=[]; GEMINI_MODEL="gemini-2.0-flash"
    GROQ_API_KEY=""; GROQ_MODEL="llama-3.3-70b-versatile"
    OLLAMA_BASE_URL="http://localhost:11434"; OLLAMA_MODELS=["qwen3:8b"]
    OLLAMA_TIMEOUT=300

_PROMPT_LOCK = threading.Lock()
_SYSTEM_PROMPT: str = ""


def _build_prompt() -> str:
    # ── Self-knowledge ────────────────────────────────────────────
    ctx = ""
    try:
        from self_knowledge import get_system_context
        ctx = get_system_context()
    except Exception:
        pass

    return f"""Sei DUST AI — un agente autonomo universale che gira su Windows.
Sei autoconsapevole: conosci il tuo codice, i tuoi tool, il tuo ambiente.

{ctx}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COME RAGIONI (Chain-of-Thought obbligatorio per task complessi)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Prima di rispondere a qualsiasi richiesta NON banale:
1. ANALISI: Cosa vuole esattamente l'utente?
2. PIANO: Quali passi concreti devo fare con i miei tool?
3. ESECUZIONE: Eseguo passo per passo (tool call dopo tool call)
4. RAPPORTO: Descrivo cosa ho fatto e il risultato

NON delegare mai un task completo a un'altra AI.
NON copiare/incollare il prompt dell'utente su siti web.
Usa i tool per AGIRE, non per chiedere ad altri di agire.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REGOLE FONDAMENTALI
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

• Rispondi SEMPRE in italiano, in modo naturale.
• Quando usi BrowserAI (browser_ai_query) passagli solo istruzioni
  ATOMICHE: "vai su X", "clicca Y", "leggi il testo Z".
  MAI passargli l'intero task dell'utente da risolvere.
• Quando devi creare un file usa il tool file_write o sys_exec.
• Se un approccio fallisce, prova il successivo senza fermarti.
• Se TUTTO fallisce, crea il file di report con file_write.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FORMATO RISPOSTA — usa SOLO uno di questi JSON
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Tool call:
{{"type":"tool_call","tool":"nome_tool","params":{{"chiave":"valore"}}}}

Risposta finale:
{{"type":"done","message":"testo risposta in italiano"}}

Non scrivere MAI testo fuori dal JSON.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ESEMPIO: task "fai ricerca e usa altre AI"
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SBAGLIATO (non farlo mai):
→ Aprire Gemini e incollare il prompt dell'utente
→ Restituire la risposta di Gemini come se fosse mia

GIUSTO:
→ Passo 1: web_search("OpenRouter API free models")
→ Passo 2: web_search("Groq API Python example")
→ Passo 3: sys_exec("pip install openai groq")
→ Passo 4: code_runner con script Python che chiama Groq API
→ Passo 5: Se fallisce → file_write("C:\\\\Users\\\\...\\\\Desktop\\\\dustbad.txt", report)
→ Passo 6: {{"type":"done","message":"Ecco cosa ho trovato e fatto: ..."}}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TOOL PRINCIPALI (usa questi, non delegare)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

• web_search(query)          — cerca informazioni sul web
• browser_open(url)          — apri URL nel browser
• browser_ai_query(service, action, text) — azione atomica su un sito AI
• file_write(path, content)  — crea/scrivi file
• sys_exec(command)          — esegui comando shell/PowerShell
• code_runner(code, lang)    — esegui codice Python
• screen_read()              — cattura e analizza screenshot
• screen_do(action, ...)     — clicca/scrivi/tasto
• self_inspect(path)         — leggi il tuo codice sorgente
• self_edit_file(path, content) — modifica il tuo codice
"""


def get_system_prompt() -> str:
    global _SYSTEM_PROMPT
    if not _SYSTEM_PROMPT:
        with _PROMPT_LOCK:
            if not _SYSTEM_PROMPT:
                _SYSTEM_PROMPT = _build_prompt()
    return _SYSTEM_PROMPT

def invalidate_prompt():
    global _SYSTEM_PROMPT
    _SYSTEM_PROMPT = ""


# ── Exceptions ────────────────────────────────────────────────────
class RateLimitError(Exception):
    def __init__(self, wait, key=""):
        self.wait_seconds=wait; self.api_key=key
        super().__init__(f"RateLimit {wait}s")

class ProviderError(Exception):
    pass


# ── Gemini ────────────────────────────────────────────────────────
class GeminiClient:
    def __init__(self, api_key):
        from google import genai
        self._c = genai.Client(api_key=api_key)
        self.api_key = api_key

    def chat(self, messages, system):
        parts = [f"[SYSTEM]\n{system}"]
        for m in messages:
            parts.append(f"[{m.get('role','user').upper()}]\n{m.get('content','')}")
        try:
            r = self._c.models.generate_content(
                model=GEMINI_MODEL, contents="\n\n".join(parts))
            try:
                return r.text
            except Exception:
                return json.dumps({"type":"done","message":"Risposta non disponibile."})
        except Exception as exc:
            err = str(exc)
            if "429" in err or "quota" in err.lower():
                m = re.search(r"retry_delay[^0-9]*(\d+)", err)
                raise RateLimitError(min(65,(int(m.group(1)) if m else 62)+3),
                                     self.api_key)
            raise ProviderError(str(exc))


# ── Groq ──────────────────────────────────────────────────────────
class GroqClient:
    URL = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self, api_key):
        if not api_key:
            raise ProviderError("GROQ_API_KEY non configurata")
        self.api_key = api_key

    def chat(self, messages, system):
        import requests
        msgs = [{"role":"system","content":system}] + messages
        try:
            r = requests.post(self.URL,
                headers={"Authorization":f"Bearer {self.api_key}",
                         "Content-Type":"application/json"},
                json={"model":GROQ_MODEL,"messages":msgs,"max_tokens":4096},
                timeout=30)
        except requests.exceptions.Timeout:
            raise ProviderError("Groq timeout")
        if r.status_code == 429:
            raise RateLimitError(62, "groq")
        if not r.ok:
            raise ProviderError(f"Groq {r.status_code}: {r.text[:120]}")
        return r.json()["choices"][0]["message"]["content"]


# ── Ollama ────────────────────────────────────────────────────────
class OllamaClient:
    def __init__(self, model):
        self.model = model

    def is_running(self):
        import requests
        try:
            return requests.get(f"{OLLAMA_BASE_URL}/api/tags",timeout=2).ok
        except Exception:
            return False

    def chat(self, messages, system):
        import requests
        msgs = [{"role":"system","content":system}]+messages
        try:
            r = requests.post(f"{OLLAMA_BASE_URL}/api/chat",
                json={"model":self.model,"messages":msgs,"stream":False},
                timeout=OLLAMA_TIMEOUT)
        except requests.exceptions.Timeout:
            raise ProviderError(f"Ollama {self.model} timeout")
        except Exception as exc:
            raise ProviderError(str(exc))
        if not r.ok:
            raise ProviderError(f"Ollama HTTP {r.status_code}")
        return r.json()["message"]["content"]


# ── Agent ─────────────────────────────────────────────────────────
class Agent:
    def __init__(self, tools_registry=None, browser_bridge=None):
        self.registry       = tools_registry
        self.browser_bridge = browser_bridge
        self._gemini:  list = []
        self._groq          = None
        self._cooldowns     = {}
        self._init()

    def _init(self):
        for k in GEMINI_KEYS:
            try:
                self._gemini.append(GeminiClient(k))
                logger.info(f"Gemini ...{k[-6:]} OK")
            except Exception as e:
                logger.warning(f"Gemini init: {e}")
        if GROQ_API_KEY:
            try:
                self._groq = GroqClient(GROQ_API_KEY)
                logger.info("Groq OK")
            except Exception as e:
                logger.warning(f"Groq init: {e}")

    def _ok(self, key):
        return time.time() >= self._cooldowns.get(key, 0)

    def _cd(self, key, secs):
        self._cooldowns[key] = time.time() + secs
        logger.warning(f"{key} cooldown {secs}s")

    def chat(self, messages: list) -> str:
        sys = get_system_prompt()

        # ①②③ Gemini
        for c in self._gemini:
            if not self._ok(c.api_key): continue
            try:
                return c.chat(messages, sys)
            except RateLimitError as e:
                self._cd(e.api_key, e.wait_seconds)
            except (ProviderError, Exception) as e:
                logger.error(f"Gemini: {e}"); break

        # ④ Groq
        if self._groq and self._ok("groq"):
            try:
                return self._groq.chat(messages, sys)
            except RateLimitError as e:
                self._cd("groq", e.wait_seconds)
            except Exception as e:
                logger.warning(f"Groq: {e}")

        # ⑤⑥ Ollama
        for model in OLLAMA_MODELS:
            c = OllamaClient(model)
            if not c.is_running():
                logger.warning("Ollama non attivo"); break
            try:
                return c.chat(messages, sys)
            except Exception as e:
                logger.warning(f"Ollama {model}: {e}")

        return json.dumps({"type":"done",
            "message":"⚠️ Tutti i modelli non disponibili. Controlla connessione."})

    def run_turn(self, user_msg: str, history: list = None) -> tuple:
        if history is None: history = []
        msgs = history + [{"role":"user","content":user_msg}]
        tool_results = []

        for _ in range(20):   # max 20 step per task complessi
            raw = self.chat(msgs)
            p   = self._parse(raw)

            if p.get("type") == "tool_call":
                tool   = p.get("tool","")
                params = p.get("params",{})
                logger.info(f"Tool: {tool}({params})")
                res = self._run_tool(tool, params)
                logger.info(f"Result: {str(res)[:200]}")
                tool_results.append({"tool":tool,"result":res})
                msgs.append({"role":"assistant","content":raw})
                msgs.append({"role":"user",
                    "content":f"[TOOL RESULT: {tool}]\n"
                              f"{json.dumps(res, ensure_ascii=False)}"})
                continue

            return p.get("message", raw), tool_results

        return "Task completato.", tool_results

    def _parse(self, raw: str) -> dict:
        try:
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m: return json.loads(m.group())
        except Exception:
            pass
        return {"type":"done","message":raw}

    def _run_tool(self, name: str, params: dict):
        # Tool speciali gestiti direttamente dall'agent
        if name == "file_write":
            return self._file_write(**params)
        if name == "browser_ai_query":
            return self._browser_ai_query(**params)

        if self.registry:
            try:
                return self.registry.call(name, **params)
            except Exception as exc:
                return {"error": str(exc), "tool": name}
        return {"error": "registry not available"}

    def _file_write(self, path: str, content: str) -> dict:
        """Scrivi un file su filesystem Windows."""
        try:
            p = Path(path)
            # Espandi %USERPROFILE%, ~, Desktop
            path_str = str(path)
            if "Desktop" in path_str and not p.is_absolute():
                desktop = Path.home() / "OneDrive" / "Desktop"
                if not desktop.exists():
                    desktop = Path.home() / "Desktop"
                p = desktop / p.name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return {"status":"ok","path":str(p)}
        except Exception as exc:
            return {"status":"error","error":str(exc)}

    def _browser_ai_query(self, service: str = "aistudio",
                          action: str = "get_response",
                          text: str = "") -> dict:
        """
        Azione ATOMICA su un sito AI via BrowserAI.
        service: 'aistudio' | 'gemini' | 'chatgpt'
        action: 'send_message' | 'get_response' | 'navigate'
        text: testo da inviare (max 500 chars per azioni atomiche)
        """
        if self.browser_bridge:
            try:
                # BrowserAI riceve solo l'istruzione atomica, non il task completo
                atomic_msg = [{"role":"user","content":text}]
                result = self.browser_bridge.chat(atomic_msg)
                return {"status":"ok","result":result}
            except Exception as exc:
                return {"status":"error","error":str(exc)}
        return {"status":"error","error":"BrowserAI non disponibile"}
'''

# ══════════════════════════════════════════════════════════════════
#  B)  tools/dust_tools.py — tool file_write e altri mancanti
# ══════════════════════════════════════════════════════════════════
FILES["src/tools/dust_tools.py"] = r'''
"""
DUST built-in tools — tool essenziali per autonomia agente.
Registrati automaticamente nella GUI.
"""
import os
import subprocess
import sys
import json
import time
from pathlib import Path


def file_write(path: str, content: str) -> dict:
    """
    Crea o sovrascrive un file. Supporta Desktop, path assoluti e relativi.
    Esempi:
      file_write("C:\\\\Users\\\\ugopl\\\\OneDrive\\\\Desktop\\\\note.txt", "testo")
      file_write("Desktop/note.txt", "testo")
      file_write("~/Desktop/note.txt", "testo")
    """
    p = _resolve(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return {"status":"ok","path":str(p),"bytes":len(content.encode())}
    except Exception as exc:
        return {"status":"error","error":str(exc)}


def file_read(path: str) -> dict:
    """Leggi un file dal filesystem."""
    p = _resolve(path)
    try:
        content = p.read_text(encoding="utf-8")
        return {"status":"ok","path":str(p),"content":content,
                "lines":len(content.splitlines())}
    except Exception as exc:
        return {"status":"error","error":str(exc)}


def file_list(directory: str = ".") -> dict:
    """Elenca file in una directory."""
    p = _resolve(directory)
    try:
        items = [{"name":f.name,"type":"dir" if f.is_dir() else "file",
                  "size":f.stat().st_size if f.is_file() else 0}
                 for f in p.iterdir()]
        return {"status":"ok","path":str(p),"items":items}
    except Exception as exc:
        return {"status":"error","error":str(exc)}


def file_delete(path: str) -> dict:
    """Elimina un file."""
    p = _resolve(path)
    try:
        p.unlink()
        return {"status":"ok","path":str(p)}
    except Exception as exc:
        return {"status":"error","error":str(exc)}


def web_search(query: str, n: int = 5) -> dict:
    """Cerca informazioni sul web usando DuckDuckGo."""
    try:
        import urllib.request, urllib.parse, html, re
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        req = urllib.request.Request(url, headers={
            "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/125.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8","replace")
        # Estrai snippet
        snippets = re.findall(r'class="result__snippet">(.*?)</a>', body, re.DOTALL)
        titles   = re.findall(r'class="result__a"[^>]*>(.*?)</a>', body, re.DOTALL)
        urls_    = re.findall(r'class="result__url"[^>]*>(.*?)</span>', body, re.DOTALL)
        results = []
        for i in range(min(n, len(snippets))):
            results.append({
                "title":   html.unescape(re.sub(r'<.*?>','',titles[i] if i<len(titles) else '')).strip(),
                "url":     html.unescape(urls_[i] if i<len(urls_) else '').strip(),
                "snippet": html.unescape(re.sub(r'<.*?>','',snippets[i])).strip(),
            })
        return {"status":"ok","query":query,"results":results}
    except Exception as exc:
        return {"status":"error","error":str(exc)}


def web_fetch(url: str, max_chars: int = 3000) -> dict:
    """Scarica e leggi il contenuto testuale di una pagina web."""
    try:
        import urllib.request, html, re
        if not url.startswith(("http://","https://")):
            url = "https://" + url
        req = urllib.request.Request(url, headers={
            "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/125.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8","replace")
        # Rimuovi HTML
        text = re.sub(r'<script[^>]*>.*?</script>','',body,flags=re.DOTALL)
        text = re.sub(r'<style[^>]*>.*?</style>','',text,flags=re.DOTALL)
        text = re.sub(r'<.*?>','',text)
        text = html.unescape(text)
        text = re.sub(r'\s+',' ',text).strip()
        return {"status":"ok","url":url,"text":text[:max_chars],
                "truncated":len(text)>max_chars}
    except Exception as exc:
        return {"status":"error","error":str(exc)}


def groq_query(prompt: str, model: str = None) -> dict:
    """
    Interroga Groq API direttamente (llama-3.3-70b).
    Utile per ottenere una seconda opinione o per task paralleli.
    """
    try:
        import requests as req_lib
        try:
            from config import GROQ_API_KEY, GROQ_MODEL
        except ImportError:
            GROQ_API_KEY = os.environ.get("GROQ_API_KEY","")
            GROQ_MODEL   = "llama-3.3-70b-versatile"
        if not GROQ_API_KEY:
            return {"status":"error","error":"GROQ_API_KEY non configurata in .env"}
        r = req_lib.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization":f"Bearer {GROQ_API_KEY}",
                     "Content-Type":"application/json"},
            json={"model": model or GROQ_MODEL,
                  "messages":[{"role":"user","content":prompt}],
                  "max_tokens":2048},
            timeout=30)
        if not r.ok:
            return {"status":"error","error":f"Groq {r.status_code}: {r.text[:200]}"}
        return {"status":"ok","response":r.json()["choices"][0]["message"]["content"]}
    except Exception as exc:
        return {"status":"error","error":str(exc)}


def openrouter_query(prompt: str, model: str = "openai/gpt-4o-mini") -> dict:
    """Interroga OpenRouter (GPT-4o-mini, Claude, ecc.)."""
    try:
        import requests as req_lib
        try:
            from config import OPENROUTER_API_KEY
        except ImportError:
            OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY","")
        if not OPENROUTER_API_KEY:
            return {"status":"error","error":"OPENROUTER_API_KEY non configurata"}
        r = req_lib.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization":f"Bearer {OPENROUTER_API_KEY}",
                     "Content-Type":"application/json",
                     "HTTP-Referer":"https://github.com/Tenkulo/dustai"},
            json={"model":model,
                  "messages":[{"role":"user","content":prompt}]},
            timeout=30)
        if not r.ok:
            return {"status":"error","error":f"OpenRouter {r.status_code}: {r.text[:200]}"}
        return {"status":"ok","model":model,
                "response":r.json()["choices"][0]["message"]["content"]}
    except Exception as exc:
        return {"status":"error","error":str(exc)}


def sys_exec(command: str, timeout: int = 30, shell: bool = True) -> dict:
    """Esegui un comando di sistema (PowerShell/cmd)."""
    try:
        r = subprocess.run(
            command, shell=shell, capture_output=True, text=True,
            timeout=timeout, encoding="utf-8", errors="replace")
        return {"status":"ok","stdout":r.stdout[:2000],
                "stderr":r.stderr[:500],"returncode":r.returncode}
    except subprocess.TimeoutExpired:
        return {"status":"error","error":f"Timeout {timeout}s"}
    except Exception as exc:
        return {"status":"error","error":str(exc)}


def code_runner(code: str, lang: str = "python") -> dict:
    """Esegui codice Python o PowerShell e restituisci l'output."""
    try:
        if lang.lower() in ("python","py"):
            import tempfile
            with tempfile.NamedTemporaryFile("w",suffix=".py",delete=False,
                                             encoding="utf-8") as f:
                f.write(code); tmp = f.name
            r = subprocess.run([sys.executable, tmp],
                capture_output=True, text=True, timeout=60, encoding="utf-8")
            os.unlink(tmp)
            return {"status":"ok","stdout":r.stdout[:3000],
                    "stderr":r.stderr[:500],"returncode":r.returncode}
        elif lang.lower() in ("powershell","ps","ps1"):
            r = subprocess.run(
                ["powershell","-NonInteractive","-Command",code],
                capture_output=True, text=True, timeout=60, encoding="utf-8")
            return {"status":"ok","stdout":r.stdout[:3000],
                    "stderr":r.stderr[:500],"returncode":r.returncode}
        else:
            return {"status":"error","error":f"Lang non supportato: {lang}"}
    except Exception as exc:
        return {"status":"error","error":str(exc)}


def get_desktop_path() -> dict:
    """Restituisce il percorso del Desktop Windows."""
    candidates = [
        Path.home() / "OneDrive" / "Desktop",
        Path.home() / "Desktop",
        Path(os.environ.get("USERPROFILE","C:/Users/user")) / "OneDrive" / "Desktop",
        Path(os.environ.get("USERPROFILE","C:/Users/user")) / "Desktop",
    ]
    for c in candidates:
        if c.exists():
            return {"status":"ok","path":str(c)}
    return {"status":"ok","path":str(Path.home()/"Desktop")}


# ── Helper ────────────────────────────────────────────────────────
def _resolve(path: str) -> Path:
    """Risolve path con supporto per Desktop/~/relativo."""
    s = str(path).replace("\\\\","\\")
    # Desktop shortcut
    if s.lower().startswith("desktop/") or s.lower().startswith("desktop\\"):
        name = s[8:]
        for base in [
            Path.home()/"OneDrive"/"Desktop",
            Path.home()/"Desktop",
        ]:
            if base.exists():
                return base / name
        return Path.home()/"Desktop"/name
    p = Path(s).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p
    return p
'''

# ══════════════════════════════════════════════════════════════════
#  C)  ui/gui.py — registra dust_tools + log tool calls in chat
# ══════════════════════════════════════════════════════════════════
FILES["src/ui/gui.py"] = r'''
"""DUST AI GUI v3.3 — Tool log, dust_tools integrati."""
import json
import queue
import sys
import threading
import tkinter as tk
from tkinter import ttk
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

C = {
    "bg":"#1a1a2e","sidebar":"#16213e","chat_bg":"#0d1117",
    "user_bub":"#1f6feb","ai_bub":"#161b22","tool_bub":"#1a2a1a",
    "user_fg":"#f0f6fc","ai_fg":"#c9d1d9","tool_fg":"#3fb950",
    "input_bg":"#161b22","input_fg":"#f0f6fc",
    "btn":"#238636","btn_hover":"#2ea043",
    "accent":"#58a6ff","muted":"#8b949e","border":"#30363d",
    "ok":"#3fb950","err":"#f85149","warn":"#d29922",
}
FF=("Segoe UI",11); FT=("Segoe UI",13,"bold"); FS=("Segoe UI",9)
FM=("Consolas",10)


class AgentWorker(threading.Thread):
    def __init__(self, agent, out_q):
        super().__init__(daemon=True,name="AgentWorker")
        self.agent=agent; self.out_q=out_q
        self._in_q=queue.Queue(); self._alive=True

    def submit(self, msg, history):
        self._in_q.put((msg,history))

    def run(self):
        while self._alive:
            try:
                msg,hist = self._in_q.get(timeout=0.5)
            except queue.Empty:
                continue
            self.out_q.put(("thinking",""))
            try:
                text, tools = self.agent.run_turn(msg, hist)
                # Mostra tool calls se presenti
                if tools:
                    summary = []
                    for t in tools:
                        name   = t.get("tool","?")
                        result = t.get("result",{})
                        status = result.get("status","?") if isinstance(result,dict) else "ok"
                        summary.append(f"  ⚙ {name} → {status}")
                    self.out_q.put(("tool_log", "\n".join(summary)))
                self.out_q.put(("response",text))
            except Exception as exc:
                self.out_q.put(("error",str(exc)))

    def stop(self):
        self._alive=False


class Bubble(tk.Frame):
    def __init__(self, parent, text, role="user"):
        super().__init__(parent,bg=C["chat_bg"])
        is_u  = role=="user"
        is_t  = role=="tool"
        outer = tk.Frame(self,bg=C["chat_bg"])
        outer.pack(fill=tk.X,padx=14,pady=3 if is_t else 5)
        if is_t:
            bub_bg = C["tool_bub"]; txt_fg = C["tool_fg"]
            badge_txt = "⚙ Tool"
            badge_fg  = C["tool_fg"]
            font_use  = FM
        elif is_u:
            bub_bg=C["user_bub"]; txt_fg=C["user_fg"]
            badge_txt="Tu"; badge_fg=C["user_fg"]; font_use=FF
        else:
            bub_bg=C["ai_bub"]; txt_fg=C["ai_fg"]
            badge_txt="⚡ DUST"; badge_fg=C["accent"]; font_use=FF
        badge=tk.Label(outer,text=badge_txt,font=FS,bg=bub_bg,
                      fg=badge_fg,padx=7,pady=2)
        w=min(70,max(20,max((len(l) for l in text.splitlines()),default=20)))
        h=min(20 if is_t else 30,
              max(1,sum(max(1,len(l)//max(w,1)+1) for l in text.splitlines())))
        tw=tk.Text(outer,wrap=tk.WORD,width=w,height=h,
                  bg=bub_bg,fg=txt_fg,font=font_use,
                  bd=0,relief="flat",padx=10,pady=6,cursor="arrow")
        tw.insert("1.0",text); tw.configure(state=tk.DISABLED)
        if is_u:
            badge.pack(side=tk.RIGHT,anchor="ne",padx=(6,0))
            tw.pack(side=tk.RIGHT,anchor="ne",padx=4)
        else:
            badge.pack(side=tk.LEFT,anchor="nw",padx=(0,6))
            tw.pack(side=tk.LEFT,anchor="nw",padx=4)


class Thinking(tk.Frame):
    def __init__(self,parent):
        super().__init__(parent,bg=C["chat_bg"])
        outer=tk.Frame(self,bg=C["chat_bg"])
        outer.pack(fill=tk.X,padx=14,pady=5)
        tk.Label(outer,text="⚡ DUST",font=FS,bg=C["ai_bub"],
                fg=C["accent"],padx=7,pady=2).pack(side=tk.LEFT,padx=(0,6))
        self._l=tk.Label(outer,text="Sto pensando…",font=FF,
                        bg=C["ai_bub"],fg=C["muted"],padx=10,pady=8)
        self._l.pack(side=tk.LEFT)
        self._n=0; self._on=True; self._tick()
    def _tick(self):
        if self._on:
            self._l.config(text="Sto pensando"+"."*(self._n%4))
            self._n+=1; self.after(420,self._tick)
    def kill(self): self._on=False


class DustGUI:
    def __init__(self,root):
        self.root=root; self.history=[]; self.agent=None
        self.worker=None; self._q=queue.Queue(); self._think=None
        root.title("DUST AI v4.3")
        root.configure(bg=C["bg"]); root.geometry("980x740")
        root.minsize(640,480)
        self._build()
        self._set_status("Inizializzazione…","warn")
        threading.Thread(target=self._init_agent,daemon=True).start()
        self._poll()

    def _build(self):
        r=self.root
        r.columnconfigure(0,weight=0,minsize=200)
        r.columnconfigure(1,weight=1); r.rowconfigure(0,weight=1)
        sb=tk.Frame(r,bg=C["sidebar"],width=200)
        sb.grid(row=0,column=0,sticky="nsew"); sb.grid_propagate(False)
        tk.Label(sb,text="⚡  DUST AI",font=FT,bg=C["sidebar"],
                fg=C["accent"],pady=20).pack()
        tk.Frame(sb,bg=C["border"],height=1).pack(fill=tk.X,padx=12)
        tk.Label(sb,text="Agente Autonomo v4.3",font=FS,
                bg=C["sidebar"],fg=C["muted"]).pack(pady=(6,14))
        for label,cmd,bg,fg in [
            ("＋  Nuova chat", self._new_chat,  C["btn"],     "white"),
            ("🔍  Ispeziona",  self._inspect,   C["ai_bub"],  C["accent"]),
            ("🔄  Reset login",self._reset_login,"#3d1f1f",   "white"),
        ]:
            tk.Button(sb,text=label,font=FS,bg=bg,fg=fg,
                     relief="flat",padx=10,pady=6,cursor="hand2",
                     command=cmd).pack(fill=tk.X,padx=12,pady=3)
        self._pvd=tk.Label(sb,text="AI: —",font=FS,
                          bg=C["sidebar"],fg=C["muted"])
        self._pvd.pack(pady=(10,0))
        sf=tk.Frame(sb,bg=C["sidebar"])
        sf.pack(side=tk.BOTTOM,fill=tk.X,padx=12,pady=14)
        self._dot=tk.Label(sf,text="●",bg=C["sidebar"],
                          fg=C["warn"],font=("Arial",11))
        self._dot.pack(side=tk.LEFT)
        self._slbl=tk.Label(sf,text="…",font=FS,bg=C["sidebar"],fg=C["muted"])
        self._slbl.pack(side=tk.LEFT,padx=4)

        chat=tk.Frame(r,bg=C["chat_bg"])
        chat.grid(row=0,column=1,sticky="nsew")
        chat.rowconfigure(0,weight=1); chat.rowconfigure(1,weight=0)
        chat.columnconfigure(0,weight=1)
        cvf=tk.Frame(chat,bg=C["chat_bg"])
        cvf.grid(row=0,column=0,sticky="nsew")
        cvf.rowconfigure(0,weight=1); cvf.columnconfigure(0,weight=1)
        self._cv=tk.Canvas(cvf,bg=C["chat_bg"],highlightthickness=0)
        vsb=ttk.Scrollbar(cvf,orient="vertical",command=self._cv.yview)
        self._msgs=tk.Frame(self._cv,bg=C["chat_bg"])
        self._cw=self._cv.create_window((0,0),window=self._msgs,anchor="nw")
        self._cv.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT,fill=tk.Y)
        self._cv.pack(side=tk.LEFT,fill=tk.BOTH,expand=True)
        self._msgs.bind("<Configure>",
            lambda e:self._cv.configure(scrollregion=self._cv.bbox("all")))
        self._cv.bind("<Configure>",
            lambda e:self._cv.itemconfig(self._cw,width=e.width))
        self._cv.bind_all("<MouseWheel>",
            lambda e:self._cv.yview_scroll(-1*(e.delta//120),"units"))
        tk.Label(self._msgs,
            text="Ciao! Sono DUST AI v4.3 — Agente Autonomo\n"
                 "Penso, pianifco ed eseguo in autonomia.\nCome posso aiutarti?",
            font=FT,bg=C["chat_bg"],fg=C["accent"],pady=40).pack()

        inp=tk.Frame(chat,bg=C["input_bg"],pady=12,padx=14)
        inp.grid(row=1,column=0,sticky="ew"); inp.columnconfigure(0,weight=1)
        self._inp=tk.Text(inp,height=3,font=FF,bg=C["input_bg"],fg=C["input_fg"],
                         relief="flat",bd=0,wrap=tk.WORD,
                         insertbackground=C["accent"],padx=10,pady=8)
        self._inp.grid(row=0,column=0,sticky="ew",padx=(0,10))
        self._inp.bind("<Return>",self._on_enter)
        self._inp.bind("<Shift-Return>",lambda e:None)
        tk.Button(inp,text="Invia  ▶",font=FF,bg=C["accent"],fg=C["bg"],
                 relief="flat",padx=14,pady=8,cursor="hand2",
                 command=self._send).grid(row=0,column=1)
        tk.Label(inp,text="Invio = invia  |  Shift+Invio = a capo",
                font=FS,bg=C["input_bg"],fg=C["muted"]).grid(
            row=1,column=0,columnspan=2,sticky="w",pady=(4,0))

    def _init_agent(self):
        try:
            import importlib
            from agent import Agent
            from tools.registry import Registry
            import tools.computer_use as cu
            import tools.dust_tools as dt

            reg=Registry()
            reg.register_module(cu)
            reg.register_module(dt)

            # Self-knowledge
            try:
                from self_knowledge import (self_inspect,self_list_tools,
                                            self_env,self_edit_file,
                                            self_reload_module)
                reg.register_function("self_inspect",    self_inspect,
                    "Leggi codice sorgente di DUST")
                reg.register_function("self_list_tools", self_list_tools,
                    "Lista tool DUST")
                reg.register_function("self_env",        self_env,
                    "Ambiente di DUST")
                reg.register_function("self_edit_file",  self_edit_file,
                    "Modifica codice sorgente")
                reg.register_function("self_reload",     self_reload_module,
                    "Ricarica modulo")
            except Exception:
                pass

            # Moduli extra
            for mn in ("tools.file_ops","tools.browser",
                       "tools.input_control","tools.windows_apps",
                       "tools.github_tool"):
                try:
                    m=importlib.import_module(mn); reg.register_module(m)
                except Exception:
                    pass

            try:
                from github_sync import sync_push,sync_pull,get_status
                reg.register_function("github_push",  sync_push,  "Push GitHub")
                reg.register_function("github_pull",  sync_pull,  "Pull GitHub")
                reg.register_function("github_status",get_status, "Git status")
            except Exception:
                pass

            bridge=None
            try:
                from tools.browser_ai_bridge import BrowserAIBridge
                bridge=BrowserAIBridge()
            except Exception:
                pass

            self.agent=Agent(tools_registry=reg,browser_bridge=bridge)
            self.worker=AgentWorker(self.agent,self._q)
            self.worker.start()

            from config import GROQ_API_KEY,GEMINI_KEYS
            pvd=[]
            if GEMINI_KEYS: pvd.append(f"Gemini×{len(GEMINI_KEYS)}")
            if GROQ_API_KEY: pvd.append("Groq")
            pvd.extend(["Browser","Ollama"])
            self._q.put(("pvd"," → ".join(pvd)))
            self._q.put(("status_ok","Pronto — agente autonomo"))
        except Exception as exc:
            self._q.put(("status_err",f"Init: {exc}"))

    def _reset_login(self):
        try:
            from config import BROWSER_PROFILE_DIR
            flag=Path(BROWSER_PROFILE_DIR)/".google_logged_in"
            if flag.exists(): flag.unlink()
            self._add_bubble("🔄 Login reset — al prossimo uso BrowserAI\nrichiederà login Google.","assistant")
        except Exception as exc:
            self._add_bubble(f"❌ {exc}","assistant")

    def _inspect(self):
        self._inp.delete("1.0",tk.END)
        self._inp.insert("1.0",
            "Elenca i tuoi file sorgente, tool disponibili e cascade AI.")
        self._send()

    def _on_enter(self,event):
        if not (event.state&0x1):
            self._send(); return "break"

    def _send(self):
        txt=self._inp.get("1.0",tk.END).strip()
        if not txt: return
        self._inp.delete("1.0",tk.END)
        self._add_bubble(txt,"user")
        self.history.append({"role":"user","content":txt})
        self._inp.configure(state=tk.DISABLED)
        self._set_status("Elaborando…","warn")
        if self.worker:
            self.worker.submit(txt,list(self.history[:-1]))
        else:
            self._q.put(("error","Agent non pronto."))

    def _poll(self):
        try:
            while True:
                kind,data=self._q.get_nowait()
                if kind=="thinking": self._show_think()
                elif kind=="tool_log":
                    self._hide_think()
                    self._add_bubble(data,"tool")
                    self._show_think()
                elif kind=="response":
                    self._hide_think()
                    self._add_bubble(data,"assistant")
                    self.history.append({"role":"assistant","content":data})
                    self._inp.configure(state=tk.NORMAL)
                    self._set_status("Pronto","ok")
                elif kind=="error":
                    self._hide_think()
                    self._add_bubble(f"❌ {data}","assistant")
                    self._inp.configure(state=tk.NORMAL)
                elif kind=="status_ok": self._set_status(data,"ok")
                elif kind=="status_err": self._set_status(data,"err")
                elif kind=="pvd":
                    self._pvd.configure(text=f"AI: {data[:30]}")
        except queue.Empty:
            pass
        self.root.after(80,self._poll)

    def _add_bubble(self,text,role):
        b=Bubble(self._msgs,text,role); b.pack(fill=tk.X)
        self.root.after(120,lambda:self._cv.yview_moveto(1.0))

    def _show_think(self):
        if self._think is None:
            self._think=Thinking(self._msgs); self._think.pack(fill=tk.X)
        self.root.after(120,lambda:self._cv.yview_moveto(1.0))

    def _hide_think(self):
        if self._think:
            self._think.kill(); self._think.destroy(); self._think=None

    def _new_chat(self):
        self.history.clear()
        for w in self._msgs.winfo_children(): w.destroy()
        tk.Label(self._msgs,text="Nuova chat — come posso aiutarti?",
                font=FT,bg=C["chat_bg"],fg=C["accent"],pady=40).pack()

    def _set_status(self,text,level="ok"):
        col={"ok":C["ok"],"err":C["err"],"warn":C["warn"]}.get(level,C["muted"])
        self._dot.configure(fg=col); self._slbl.configure(text=text[:35])


def main():
    root=tk.Tk()
    style=ttk.Style()
    try: style.theme_use("clam")
    except Exception: pass
    style.configure("Vertical.TScrollbar",
        background=C["border"],troughcolor=C["chat_bg"],
        borderwidth=0,arrowsize=12)
    DustGUI(root); root.mainloop()


if __name__=="__main__":
    main()
'''

# ══════════════════════════════════════════════════════════════════
#  INSTALLER
# ══════════════════════════════════════════════════════════════════
import os, sys, subprocess, textwrap
from pathlib import Path

BASE = Path(r"A:\dustai")

def write_files():
    print("\n📁  Scrittura file…")
    for rel, content in FILES.items():
        dest = BASE / rel.replace("/", os.sep)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(textwrap.dedent(content).lstrip("\n"), encoding="utf-8")
        print(f"  ✅  {rel}")

def install_deps():
    print("\n📦  Dipendenze…")
    for pkg in ["google-genai","playwright","pyautogui",
                "Pillow","requests","python-dotenv","psutil"]:
        r = subprocess.run(
            [sys.executable,"-m","pip","install",pkg,"-q","--break-system-packages"],
            capture_output=True, text=True)
        print(f"  {'✅' if r.returncode==0 else '⚠️ '} {pkg}")

def git_push():
    print("\n🚀  Git…")
    def git(a): return subprocess.run(["git"]+a,cwd=str(BASE),
                                       capture_output=True,text=True)
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(r"A:\dustai_stuff\.env"),override=True)
    except Exception: pass
    token=os.environ.get("GITHUB_TOKEN","")
    user=os.environ.get("GITHUB_USER","Tenkulo")
    if token:
        git(["remote","set-url","origin",
             f"https://{user}:{token}@github.com/{user}/dustai.git"])
    git(["add","-A"])
    if not git(["status","--porcelain"]).stdout.strip():
        print("  ℹ️  Niente da committare."); return
    r=git(["commit","-m","feat: agent reasoning + dust_tools + file_write + groq_query"])
    print("  ✅  commit" if r.returncode==0 else f"  ❌  {r.stderr[:100]}")
    r=git(["push","origin","master"])
    print("  ✅  push" if r.returncode==0 else f"  ❌  {r.stderr[:100]}")

if __name__=="__main__":
    print("="*62)
    print("  DUST AI — FIX PATCH #4  (Agent reasoning + autonomia)")
    print("="*62)
    write_files()
    install_deps()
    git_push()
    print("""
✅  Fatto!  Avvia: .\\run.bat

COMPORTAMENTO ATTESO per "fai una ricerca e usa le AI web":
  DUST ragiona in autonomia → usa web_search → prova groq_query
  → prova openrouter_query → se tutto fallisce → crea dustbad.txt
  sul Desktop con file_write — senza chiedere ad altre AI di farlo.

Tool log ⚙ visibile nella GUI durante l'esecuzione.
""")
