"""GitHub REST API tool — no gh CLI required."""
import base64
import logging
import requests

logger = logging.getLogger("dust.github_tool")

try:
    from config import GITHUB_TOKEN, GITHUB_USER, GITHUB_REPO
except ImportError:
    GITHUB_TOKEN = ""; GITHUB_USER = "Tenkulo"; GITHUB_REPO = "dustai"

_BASE = "https://api.github.com"


def _h() -> dict:
    h = {"Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN:
        h["Authorization"] = f"token {GITHUB_TOKEN}"
    return h


def github_list_repos(user: str = None) -> dict:
    """List GitHub repositories for a user."""
    u = user or GITHUB_USER
    r = requests.get(f"{_BASE}/users/{u}/repos", headers=_h(), timeout=10)
    if r.ok:
        return {"status": "ok", "repos": [
            {"name": x["name"], "url": x["html_url"], "desc": x["description"]}
            for x in r.json()
        ]}
    return {"status": "error", "error": r.text[:300]}


def github_get_file(path: str, repo: str = None, branch: str = "master") -> dict:
    """Get a file's content from GitHub."""
    rp = repo or GITHUB_REPO
    r  = requests.get(f"{_BASE}/repos/{GITHUB_USER}/{rp}/contents/{path}",
                      headers=_h(), params={"ref": branch}, timeout=10)
    if r.ok:
        data    = r.json()
        content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        return {"status": "ok", "content": content, "sha": data["sha"]}
    return {"status": "error", "error": r.text[:300]}


def github_put_file(path: str, content: str, message: str = "Update via DUST AI",
                    repo: str = None, branch: str = "master") -> dict:
    """Create or update a file on GitHub."""
    rp  = repo or GITHUB_REPO
    sha = None
    ex  = github_get_file(path, repo=rp, branch=branch)
    if ex["status"] == "ok":
        sha = ex["sha"]

    payload: dict = {
        "message": message,
        "content": base64.b64encode(content.encode()).decode(),
        "branch":  branch,
    }
    if sha:
        payload["sha"] = sha

    r = requests.put(f"{_BASE}/repos/{GITHUB_USER}/{rp}/contents/{path}",
                     headers=_h(), json=payload, timeout=15)
    if r.ok:
        return {"status": "ok", "path": path}
    return {"status": "error", "error": r.text[:300]}


def github_create_issue(title: str, body: str = "", labels: list = None,
                        repo: str = None) -> dict:
    """Create a GitHub issue."""
    rp      = repo or GITHUB_REPO
    payload = {"title": title, "body": body}
    if labels:
        payload["labels"] = labels
    r = requests.post(f"{_BASE}/repos/{GITHUB_USER}/{rp}/issues",
                      headers=_h(), json=payload, timeout=10)
    if r.ok:
        return {"status": "ok", "url": r.json()["html_url"]}
    return {"status": "error", "error": r.text[:300]}


def github_get_commits(repo: str = None, n: int = 10) -> dict:
    """Get recent commits from a repo."""
    rp = repo or GITHUB_REPO
    r  = requests.get(f"{_BASE}/repos/{GITHUB_USER}/{rp}/commits",
                      headers=_h(), params={"per_page": n}, timeout=10)
    if r.ok:
        return {"status": "ok", "commits": [
            {"sha": c["sha"][:7], "msg": c["commit"]["message"].split("\n")[0]}
            for c in r.json()
        ]}
    return {"status": "error", "error": r.text[:300]}
