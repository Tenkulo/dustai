"""DUST AI – GitHubSync v2.0"""
import subprocess, logging, json, shutil, time
from pathlib import Path
from datetime import datetime
log = logging.getLogger("GitHubSync")

REPO_PATH  = Path(r"A:\dustai")
BACKUP_DIR = Path(r"A:\dustai_stuff\backups")
REMOTE     = "origin"
BRANCH     = "master"


class GitHubSync:
    def __init__(self, config):
        self.config = config
        self.repo_dir = REPO_PATH
        self._last_push = 0.0
        self._push_interval = 30 * 60

    def auto_sync(self, commit_msg=""):
        results = {}
        results["pull"] = self.pull()
        if self.has_uncommitted_changes():
            msg = commit_msg or self._auto_commit_message()
            results["commit"] = self.commit(msg)
        else:
            results["commit"] = {"ok": True, "msg": "Niente da committare"}
        if time.time() - self._last_push > self._push_interval or commit_msg:
            results["push"] = self.push()
            if results["push"].get("ok"):
                self._last_push = time.time()
        else:
            wait = int((self._push_interval - (time.time() - self._last_push)) / 60)
            results["push"] = {"ok": True, "msg": "Prossimo push tra " + str(wait) + " min"}
        return results

    def commit(self, message, files=None):
        try:
            self._run(["git", "add", "-A"] if not files else ["git", "add"] + [str(f) for f in files])
            status = self._run(["git", "status", "--porcelain"])
            if not status.get("stdout", "").strip():
                return {"ok": True, "msg": "Niente da committare"}
            ts = datetime.now().strftime("%Y-%m-%d %H:%M")
            full_msg = "[DUST " + ts + "] " + message[:60]
            result = self._run(["git", "commit", "-m", full_msg])
            if result.get("ok"):
                return {"ok": True, "msg": full_msg, "hash": self._last_commit_hash()}
            return {"ok": False, "error": result.get("stderr", "errore commit")}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def push(self):
        try:
            self._backup()
            result = self._run(["git", "push", REMOTE, BRANCH])
            if result.get("ok"):
                return {"ok": True, "msg": "Push OK -> github.com/Tenkulo/dustai"}
            if "non-fast-forward" in result.get("stderr", ""):
                result2 = self._run(["git", "push", "--force-with-lease", REMOTE, BRANCH])
                if result2.get("ok"):
                    return {"ok": True, "msg": "Force push OK"}
                return {"ok": False, "error": result2.get("stderr", "")}
            return {"ok": False, "error": result.get("stderr", "errore push")}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def pull(self):
        try:
            result = self._run(["git", "pull", REMOTE, BRANCH, "--rebase"])
            stdout = result.get("stdout", "")
            if result.get("ok"):
                if "Already up to date" in stdout or "Aggiornato" in stdout:
                    return {"ok": True, "msg": "Gia aggiornato"}
                return {"ok": True, "msg": "Pull OK:\n" + stdout[:200]}
            return {"ok": False, "error": result.get("stderr", "")}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def status(self):
        lines = ["=== GitHub Sync ===", "Repo: " + str(self.repo_dir), ""]
        branch = self._run(["git", "branch", "--show-current"])
        lines.append("Branch: " + branch.get("stdout", "?").strip())
        last = self._run(["git", "log", "--oneline", "-3"])
        lines.append("Ultimi commit:\n" + last.get("stdout", "?").strip())
        dirty = self._run(["git", "status", "--short"])
        dirty_out = dirty.get("stdout", "").strip()
        if dirty_out:
            lines.append("\nModifiche non committate:\n" + dirty_out[:300])
        else:
            lines.append("\nWorking tree pulito")
        return "\n".join(lines)

    def has_uncommitted_changes(self):
        return bool(self._run(["git", "status", "--porcelain"]).get("stdout", "").strip())

    def _auto_commit_message(self):
        result = self._run(["git", "status", "--short"])
        changes = result.get("stdout", "").strip().splitlines()
        if not changes:
            return "auto: sync"
        modified = [l[3:] for l in changes if l.startswith(" M ") or l.startswith("M ")]
        new_files = [l[3:] for l in changes if l.startswith("?? ")]
        parts = []
        if modified:
            parts.append("edit: " + ", ".join(modified[:3]))
        if new_files:
            parts.append("add: " + ", ".join(new_files[:3]))
        return (" | ".join(parts) or "auto: modifiche")[:72]

    def _last_commit_hash(self):
        return self._run(["git", "rev-parse", "--short", "HEAD"]).get("stdout", "").strip()

    def _backup(self):
        try:
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            dst = BACKUP_DIR / ("dustai_" + ts)
            shutil.copytree(self.repo_dir, dst,
                            ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
            backups = sorted(BACKUP_DIR.glob("dustai_*"))
            for old in backups[:-5]:
                shutil.rmtree(old, ignore_errors=True)
        except Exception as e:
            log.warning("Backup fallito: %s", e)

    def _run(self, cmd):
        try:
            result = subprocess.run(cmd, cwd=str(self.repo_dir), capture_output=True,
                                    text=True, encoding="utf-8", errors="replace", timeout=60)
            return {"ok": result.returncode == 0, "stdout": result.stdout,
                    "stderr": result.stderr, "code": result.returncode}
        except Exception as e:
            return {"ok": False, "error": str(e), "stdout": "", "stderr": ""}


class GitSyncTool:
    """Tool wrapper per ToolRegistry."""

    def __init__(self, config):
        self.config = config
        self._sync = None

    def _get(self):
        if not self._sync:
            self._sync = GitHubSync(self.config)
        return self._sync

    def git_sync(self, message=""):
        results = self._get().auto_sync(message)
        return "\n".join(
            ("OK" if r.get("ok") else "FAIL") + " " + step + ": " + r.get("msg", r.get("error", ""))
            for step, r in results.items()
        )

    def git_commit(self, message):
        r = self._get().commit(message)
        return ("OK: " if r.get("ok") else "FAIL: ") + r.get("msg", r.get("error", ""))

    def git_push(self):
        r = self._get().push()
        return ("OK: " if r.get("ok") else "FAIL: ") + r.get("msg", r.get("error", ""))

    def git_pull(self):
        r = self._get().pull()
        return ("OK: " if r.get("ok") else "FAIL: ") + r.get("msg", r.get("error", ""))

    def git_status(self):
        return self._get().status()
