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
