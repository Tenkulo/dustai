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
