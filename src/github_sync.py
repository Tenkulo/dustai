"""DUST AI – GitHubSync v2.0"""
import subprocess, logging, shutil, time
from pathlib import Path
from datetime import datetime
log = logging.getLogger("GitHubSync")
REPO   = Path(r"A:\dustai")
BACKUP = Path(r"A:\dustai_stuff\backups")

class GitHubSync:
    def __init__(self, config):
        self.config = config
        self._last_push = 0.0

    def auto_sync(self, msg="") -> dict:
        r = {}
        r["pull"]   = self.pull()
        r["commit"] = self.commit(msg or self._auto_msg())
        if time.time() - self._last_push > 1800 or msg:
            r["push"]       = self.push()
            self._last_push = time.time()
        else:
            r["push"] = {"ok": True, "msg": "push posticipato (< 30 min)"}
        return r

    def commit(self, msg="auto") -> dict:
        self._run(["git","add","-A"])
        s = self._run(["git","status","--porcelain"])
        if not s.get("stdout","").strip():
            return {"ok": True, "msg": "Niente da committare"}
        ts   = datetime.now().strftime("%Y-%m-%d %H:%M")
        full = f"[DUST {ts}] {msg[:60]}"
        r    = self._run(["git","commit","-m",full])
        return {"ok": r["ok"], "msg": full} if r["ok"] else {"ok": False, "error": r.get("stderr","")}

    def push(self) -> dict:
        BACKUP.mkdir(parents=True, exist_ok=True)
        ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
        dst = BACKUP / ("dustai_" + ts)
        try:
            shutil.copytree(REPO, dst, ignore=shutil.ignore_patterns(".git","__pycache__","*.pyc"))
            [shutil.rmtree(b, True) for b in sorted(BACKUP.glob("dustai_*"))[:-5]]
        except Exception: pass
        r = self._run(["git","push","origin","master"])
        return {"ok": True, "msg": "Push OK"} if r["ok"] else {"ok": False, "error": r.get("stderr","")}

    def pull(self) -> dict:
        r = self._run(["git","pull","origin","master","--rebase"])
        return {"ok": r["ok"], "msg": r.get("stdout","")[:80]}

    def status(self) -> str:
        log_ = self._run(["git","log","--oneline","-5"])
        dirty = self._run(["git","status","--short"])
        return ("Branch: master\nUltimi 5 commit:\n" + log_.get("stdout","") +
                "\nModifiche locali:\n" + (dirty.get("stdout","").strip() or "(nessuna)"))

    def _auto_msg(self) -> str:
        r = self._run(["git","status","--short"])
        files = [l[3:] for l in r.get("stdout","").strip().splitlines()[:3]]
        return "auto: " + ", ".join(files) if files else "auto: sync"

    def _run(self, cmd) -> dict:
        try:
            r = subprocess.run(cmd, cwd=str(REPO), capture_output=True,
                               text=True, encoding="utf-8", errors="replace", timeout=60)
            return {"ok": r.returncode==0, "stdout": r.stdout, "stderr": r.stderr}
        except Exception as e:
            return {"ok": False, "error": str(e), "stdout": "", "stderr": ""}


class GitSyncTool:
    def __init__(self, config):
        self.config = config
        self._s     = None

    def _get(self):
        if not self._s:
            self._s = GitHubSync(self.config)
        return self._s

    def git_sync(self, message: str = "") -> str:
        r = self._get().auto_sync(message)
        return "\n".join(("✅" if v.get("ok") else "❌")+" "+k+": "+v.get("msg",v.get("error",""))
                         for k, v in r.items())

    def git_commit(self, message: str) -> str:
        r = self._get().commit(message)
        return ("✅ " if r["ok"] else "❌ ") + r.get("msg", r.get("error",""))

    def git_push(self) -> str:
        r = self._get().push()
        return ("✅ " if r["ok"] else "❌ ") + r.get("msg", r.get("error",""))

    def git_status(self) -> str:
        return self._get().status()
