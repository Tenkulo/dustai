"""DUST AI – BrowserAIBridge v2.0
Interroga AI via browser Playwright – zero rate limit.
"""
import json, time, logging, hashlib
from pathlib import Path
log = logging.getLogger("BrowserAI")

PROFILES = Path(r"A:\dustai_stuff\browser_profiles")
CACHE    = Path(r"A:\dustai_stuff\cache\browser_ai")
TTL      = 3600   # 1 ora cache

PROVIDERS = {
    "gemini":     {"url":"https://gemini.google.com/app",  "pri":1,
                   "inp":"rich-textarea div[contenteditable]",
                   "send":"button[aria-label*='Send']",
                   "out":"message-content p","done":"button[aria-label*='Send']:not([disabled])"},
    "chatgpt":    {"url":"https://chatgpt.com/",           "pri":2,
                   "inp":"#prompt-textarea",
                   "send":"button[data-testid='send-button']",
                   "out":"[data-message-author-role='assistant'] p",
                   "done":"button[data-testid='send-button']:not([disabled])"},
    "claude":     {"url":"https://claude.ai/new",          "pri":3,
                   "inp":"div[contenteditable='true']",
                   "send":"button[aria-label='Send Message']",
                   "out":".prose p","done":"button[aria-label='Send Message']:not([disabled])"},
    "grok":       {"url":"https://grok.com/",              "pri":4,
                   "inp":"textarea","send":"button[type='submit']",
                   "out":".message-content p","done":"button[type='submit']:not([disabled])"},
    "perplexity": {"url":"https://www.perplexity.ai/",     "pri":5,
                   "inp":"textarea[placeholder]","send":"button[aria-label*='Submit']",
                   "out":".prose p","done":"button[aria-label*='Submit']:not([disabled])"},
}
ORDER = sorted(PROVIDERS, key=lambda p: PROVIDERS[p]["pri"])


class BrowserAIBridge:
    def __init__(self, config=None):
        self.config = config
        PROFILES.mkdir(parents=True, exist_ok=True)
        CACHE.mkdir(parents=True, exist_ok=True)
        self._st = self._load_status()

    def query(self, prompt: str, provider="auto", use_cache=True) -> dict:
        if use_cache:
            c = self._cache_get(prompt, provider)
            if c:
                return {"ok": True, "text": c, "provider": provider+"_cached"}
        provs = ORDER if provider == "auto" else [provider]
        for p in provs:
            if self._st.get(p) == "error":
                continue
            try:
                r = self._query_one(p, prompt)
                if r.get("ok"):
                    if use_cache:
                        self._cache_set(prompt, p, r["text"])
                    return r
            except Exception as e:
                log.warning("BrowserAI %s: %s", p, str(e)[:80])
                self._st[p] = "error"
                self._save_status()
        return {"ok": False, "error": "Tutti i browser provider falliti"}

    def get_ready_providers(self) -> list:
        return [p for p in ORDER
                if (PROFILES/p).exists() and self._st.get(p) != "error"]

    def login(self, provider="gemini") -> str:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return "playwright non installato: pip install playwright && python -m playwright install chromium"
        try:
            with sync_playwright() as pw:
                ctx = pw.chromium.launch_persistent_context(
                    user_data_dir=str(PROFILES/provider),
                    headless=False, viewport={"width":1280,"height":800})
                page = ctx.new_page()
                page.goto(PROVIDERS[provider]["url"], timeout=30000)
                print(f"\n{'='*50}\nLOGIN MANUALE: {provider}")
                print("Fai login nel browser aperto, poi premi INVIO qui.")
                input(">>> INVIO dopo login: ")
                self._st[provider] = "ready"
                self._save_status()
                ctx.close()
            return f"✅ Login {provider} salvato."
        except Exception as e:
            return f"❌ Errore: {str(e)[:100]}"

    def status(self) -> str:
        lines = ["=== BrowserAI Status ==="]
        for p in ORDER:
            ok = (PROFILES/p).exists() and self._st.get(p) != "error"
            lines.append(("✅" if ok else "❌")+" "+p.ljust(12)+" ["+self._st.get(p,"non configurato")+"]")
        lines.append("\nPer fare login: browser_ai_login provider=gemini")
        return "\n".join(lines)

    def _query_one(self, provider: str, prompt: str, timeout_ms=60000) -> dict:
        cfg = PROVIDERS[provider]
        try:
            from playwright.sync_api import sync_playwright, TimeoutError as PwTO
            with sync_playwright() as pw:
                ctx = pw.chromium.launch_persistent_context(
                    user_data_dir=str(PROFILES/provider), headless=True,
                    args=["--no-sandbox","--disable-blink-features=AutomationControlled"])
                page = ctx.new_page()
                page.goto(cfg["url"], timeout=30000, wait_until="domcontentloaded")
                try:
                    page.wait_for_selector(cfg["inp"], timeout=12000)
                except PwTO:
                    ctx.close()
                    self._st[provider] = "logged_out"
                    return {"ok":False,"error":provider+": login scaduto – esegui browser_ai_login provider="+provider}
                el = page.locator(cfg["inp"]).last
                el.click()
                el.fill("")
                for i in range(0, len(prompt), 500):
                    el.type(prompt[i:i+500], delay=8)
                    time.sleep(0.05)
                page.locator(cfg["send"]).click(timeout=5000)
                try:
                    page.wait_for_selector(cfg["done"], timeout=timeout_ms)
                except PwTO:
                    pass
                time.sleep(1.5)
                texts = []
                for el in page.locator(cfg["out"]).all()[-20:]:
                    try:
                        t = el.inner_text().strip()
                        if t and len(t) > 5:
                            texts.append(t)
                    except Exception:
                        pass
                ctx.close()
                if not texts:
                    return {"ok":False,"error":provider+": nessun testo estratto"}
                self._st[provider] = "ready"
                self._save_status()
                return {"ok":True,"text":"\n\n".join(texts),"provider":provider+"_web"}
        except ImportError:
            return {"ok":False,"error":"playwright non installato"}
        except Exception as e:
            return {"ok":False,"error":str(e)[:200]}

    def _cache_key(self, p, prov):
        return hashlib.md5((prov+p[:500]).encode()).hexdigest()

    def _cache_get(self, prompt, provider):
        f = CACHE/(self._cache_key(prompt,provider)+".json")
        if not f.exists(): return None
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            if time.time()-d.get("ts",0) < TTL:
                return d.get("text")
        except Exception: pass
        return None

    def _cache_set(self, prompt, provider, text):
        try:
            (CACHE/(self._cache_key(prompt,provider)+".json")).write_text(
                json.dumps({"ts":time.time(),"text":text},ensure_ascii=False),
                encoding="utf-8")
        except Exception: pass

    def _load_status(self):
        f = PROFILES/"status.json"
        if f.exists():
            try: return json.loads(f.read_text(encoding="utf-8"))
            except: pass
        return {}

    def _save_status(self):
        try: (PROFILES/"status.json").write_text(json.dumps(self._st,indent=2),encoding="utf-8")
        except: pass


class BrowserAITool:
    def __init__(self, config):
        self.config = config
        self._b     = None

    def _get(self):
        if not self._b:
            self._b = BrowserAIBridge(self.config)
        return self._b

    def browser_ai_query(self, prompt: str, provider: str = "auto") -> str:
        r = self._get().query(prompt, provider)
        return ("["+r["provider"]+"] "+r["text"]) if r.get("ok") else "❌ "+r.get("error","")

    def browser_ai_login(self, provider: str = "gemini") -> str:
        return self._get().login(provider)

    def browser_ai_status(self) -> str:
        return self._get().status()
