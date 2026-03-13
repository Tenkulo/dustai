"""
DUST Self-Knowledge — DUST legge il suo codice, i suoi tool, il suo env.

Espone:
  get_system_context()   → stringa per il system prompt (usata da agent.py)
  self_inspect(path)     → contenuto di un file sorgente
  self_list_tools()      → dizionario tool disponibili
  self_env()             → info sull'ambiente (OS, Python, RAM, modelli)
  self_edit_file(path, new_content) → riscrive un file sorgente (self-mod)
"""
import os
import platform
import sys
from pathlib import Path
from typing import Union

try:
    from config import BASE_PATH, GEMINI_KEYS, GEMINI_MODEL, OLLAMA_MODELS
except ImportError:
    import pathlib
    BASE_PATH    = pathlib.Path(r"A:\dustai")
    GEMINI_KEYS  = []
    GEMINI_MODEL = "gemini-2.0-flash"
    OLLAMA_MODELS = []

SRC_DIR = BASE_PATH / "src"


# ── Lettura sorgenti ─────────────────────────────────────────────
def self_inspect(path: str = None) -> dict:
    """
    Leggi il contenuto di un file sorgente di DUST.
    path: relativo a A:\\dustai\\src   (es. 'agent.py' oppure 'tools/registry.py')
    Se omesso restituisce l'elenco di tutti i file.
    """
    if path is None:
        files = []
        for f in SRC_DIR.rglob("*.py"):
            rel = f.relative_to(BASE_PATH).as_posix()
            files.append({"path": rel, "size": f.stat().st_size})
        return {"status": "ok", "files": files}

    # Risolvi il percorso
    candidates = [
        SRC_DIR / path,
        BASE_PATH / path,
        SRC_DIR / "tools" / path,
    ]
    for c in candidates:
        if c.exists():
            try:
                content = c.read_text(encoding="utf-8")
                return {"status": "ok", "path": c.relative_to(BASE_PATH).as_posix(),
                        "content": content, "lines": len(content.splitlines())}
            except Exception as e:
                return {"status": "error", "error": str(e)}

    return {"status": "error", "error": f"File non trovato: {path}"}


def self_list_tools() -> dict:
    """Elenca tutti i tool registrati con descrizione."""
    try:
        # Import lazy del registry per non creare dipendenze circolari
        import importlib
        spec = importlib.util.spec_from_file_location(
            "registry", SRC_DIR / "tools" / "registry.py")
        mod  = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        reg  = mod.Registry()

        # Auto-registra i moduli principali
        for m_name in ["computer_use", "file_ops", "web_search",
                        "sys_exec", "github_tool"]:
            try:
                m_spec = importlib.util.spec_from_file_location(
                    m_name, SRC_DIR / "tools" / f"{m_name}.py")
                m_mod  = importlib.util.module_from_spec(m_spec)
                m_spec.loader.exec_module(m_mod)
                reg.register_module(m_mod)
            except Exception:
                pass

        return {"status": "ok", "tools": reg.list_tools()}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def self_env() -> dict:
    """Info sull'ambiente di esecuzione di DUST."""
    info: dict = {
        "os":          platform.system() + " " + platform.release(),
        "machine":     platform.machine(),
        "python":      sys.version.split()[0],
        "base_path":   str(BASE_PATH),
        "src_path":    str(SRC_DIR),
        "gemini_model": GEMINI_MODEL,
        "gemini_keys":  len(GEMINI_KEYS),
        "ollama_models": OLLAMA_MODELS,
        "cwd":         os.getcwd(),
        "pid":         os.getpid(),
    }
    try:
        import psutil
        m = psutil.virtual_memory()
        info["ram_total_gb"] = round(m.total / 1e9, 1)
        info["ram_used_pct"] = m.percent
        info["cpu_pct"]      = psutil.cpu_percent(interval=0.5)
    except ImportError:
        pass
    return {"status": "ok", "env": info}


def self_edit_file(path: str, content: str) -> dict:
    """
    Riscrivi un file sorgente di DUST con nuovo contenuto.
    ATTENZIONE: cambia il comportamento di DUST al prossimo import!
    """
    candidates = [SRC_DIR / path, BASE_PATH / path]
    for c in candidates:
        if c.exists():
            backup = c.with_suffix(c.suffix + ".bak")
            backup.write_text(c.read_text(encoding="utf-8"), encoding="utf-8")
            c.write_text(content, encoding="utf-8")
            return {"status": "ok", "path": str(c), "backup": str(backup)}
    return {"status": "error", "error": f"File non trovato: {path}"}


def self_reload_module(module_name: str) -> dict:
    """Ricarica un modulo Python a runtime (dopo self_edit_file)."""
    import importlib
    try:
        if module_name in sys.modules:
            importlib.reload(sys.modules[module_name])
            return {"status": "ok", "module": module_name, "action": "reloaded"}
        else:
            importlib.import_module(module_name)
            return {"status": "ok", "module": module_name, "action": "imported"}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


# ── Context per system prompt ────────────────────────────────────
def get_system_context() -> str:
    """
    Genera un blocco di testo con tutto il contesto di DUST
    da inserire nel system prompt.
    """
    lines = ["=== DUST AI — AUTOCONSAPEVOLEZZA ==="]

    # File sorgenti
    files_result = self_inspect()
    if files_result["status"] == "ok":
        lines.append("\nFILE SORGENTI (A:\\dustai\\src\\):")
        for f in files_result["files"]:
            lines.append(f"  • {f['path']}  ({f['size']} bytes)")

    # Tool disponibili
    tools_result = self_list_tools()
    if tools_result["status"] == "ok":
        lines.append("\nTOOL DISPONIBILI:")
        for name, desc in tools_result["tools"].items():
            lines.append(f"  • {name}: {desc or '(nessuna descrizione)'}")

    # Ambiente
    env_result = self_env()
    if env_result["status"] == "ok":
        e = env_result["env"]
        lines.append(f"\nAMBIENTE:")
        lines.append(f"  OS: {e.get('os')}")
        lines.append(f"  Python: {e.get('python')}")
        lines.append(f"  Gemini model: {e.get('gemini_model')}")
        lines.append(f"  Gemini keys attive: {e.get('gemini_keys')}")
        lines.append(f"  Ollama models: {e.get('ollama_models')}")
        lines.append(f"  Base path: {e.get('base_path')}")

    lines.append("\nPuoi usare self_inspect(path) per leggere qualsiasi tuo file sorgente.")
    lines.append("Puoi usare self_edit_file(path, content) per modificare il tuo codice.")
    lines.append("=== FINE CONTESTO DUST ===")

    return "\n".join(lines)
