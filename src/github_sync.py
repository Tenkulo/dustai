"""GitHub auto-sync — git add -A && commit && push via subprocess."""
import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger("dust.github_sync")

try:
    from config import BASE_PATH, GITHUB_TOKEN, GITHUB_USER, GITHUB_REPO
except ImportError:
    import pathlib
    BASE_PATH = pathlib.Path(r"A:\dustai")
    GITHUB_TOKEN = ""; GITHUB_USER = "Tenkulo"; GITHUB_REPO = "dustai"

REPO_DIR = BASE_PATH


def _git(args: list, cwd: Path = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    # Inject credentials silently
    if GITHUB_TOKEN and GITHUB_USER:
        env["GIT_TERMINAL_PROMPT"] = "0"
    return subprocess.run(
        ["git"] + args,
        cwd=str(cwd or REPO_DIR),
        capture_output=True, text=True, env=env
    )


def _set_remote_url():
    url = f"https://{GITHUB_USER}:{GITHUB_TOKEN}@github.com/{GITHUB_USER}/{GITHUB_REPO}.git"
    _git(["remote", "set-url", "origin", url])


def sync_push(message: str = "Auto-sync DUST AI", add_all: bool = True) -> dict:
    """git add -A && commit && push."""
    if add_all:
        r = _git(["add", "-A"])
        if r.returncode:
            return {"status": "error", "step": "add", "error": r.stderr[:300]}

    status = _git(["status", "--porcelain"])
    if not status.stdout.strip():
        return {"status": "ok", "message": "Nothing to commit."}

    r = _git(["commit", "-m", message])
    if r.returncode:
        return {"status": "error", "step": "commit", "error": r.stderr[:300]}

    _set_remote_url()
    r = _git(["push", "origin", "master"])
    if r.returncode:
        return {"status": "error", "step": "push", "error": r.stderr[:300]}

    return {"status": "ok", "message": f"Pushed: {message}"}


def sync_pull() -> dict:
    """git pull origin master."""
    _set_remote_url()
    r = _git(["pull", "origin", "master"])
    if r.returncode:
        return {"status": "error", "error": r.stderr[:300]}
    return {"status": "ok", "output": r.stdout[:500]}


def get_status() -> dict:
    """git status --short."""
    r = _git(["status", "--short"])
    return {"status": "ok", "changes": r.stdout}
