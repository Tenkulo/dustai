#!/usr/bin/env python3
"""
DUST AI – Entry point v1.3
Pre-boot recovery: intercetta QUALSIASI errore di import/syntax prima
che l'agent si carichi, lo patcha con Gemini e si riavvia da solo.
Funziona anche se agent.py, bootstrap.py o qualsiasi src/ è rotto.
"""
import os
import sys
import json
import time
import traceback
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.absolute()
sys.path.insert(0, str(ROOT))

MAX_BOOT_ATTEMPTS = 5
BOOT_STATE_FILE   = ROOT / "src" / ".boot_state.json"


# ─── Boot state: conta i tentativi e memorizza crash ─────────────────────────

def load_boot_state() -> dict:
    try:
        if BOOT_STATE_FILE.exists():
            return json.loads(BOOT_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"attempts": 0, "last_error": None, "last_file": None, "patches": []}


def save_boot_state(state: dict):
    try:
        BOOT_STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def clear_boot_state():
    try:
        BOOT_STATE_FILE.unlink(missing_ok=True)
    except Exception:
        pass


# ─── Estrae file sorgente dalla traceback ─────────────────────────────────────

def extract_broken_file(tb_str: str) -> tuple[str, str]:
    """Ritorna (path_assoluto, nome_file) del file DUST AI che ha causato il crash."""
    import re
    # Cerca tutti i file nella traceback che appartengono a src/
    matches = re.findall(r'File "([^"]*[/\\]src[/\\][^"]+\.py)", line (\d+)', tb_str)
    if matches:
        path, line = matches[-1]  # ultimo = più vicino all'errore
        return path, Path(path).name
    # Cerca anche file nella root del progetto
    matches = re.findall(r'File "([^"]*dustai[/\\][^"]+\.py)", line (\d+)', tb_str)
    if matches:
        path, line = matches[-1]
        return path, Path(path).name
    return "", ""


# ─── Pre-boot patch con Gemini (stdlib only + google-generativeai) ────────────

def preboot_patch(error_str: str, tb_str: str, broken_file: str) -> bool:
    """
    Usa Gemini per analizzare il crash e patchare il file sorgente.
    Viene chiamato PRIMA che qualsiasi modulo DUST AI sia importato.
    Richiede solo: google-generativeai (già installato dal bootstrap).
    """
    print(f"\n🔬 Pre-boot recovery: analizzo crash in {Path(broken_file).name}...")

    # Leggi il file rotto
    try:
        source = Path(broken_file).read_text(encoding="utf-8")
    except Exception:
        source = ""

    # Carica API key direttamente senza Config
    api_key = os.environ.get("GOOGLE_API_KEY", "")
    if not api_key:
        env_file = Path(os.environ.get("APPDATA", Path.home())) / "dustai" / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("GOOGLE_API_KEY=") and "inserisci_qui" not in line:
                    api_key = line.split("=", 1)[1].strip()
                    break

    if not api_key:
        print("   ⚠️  GOOGLE_API_KEY non trovata — patch manuale necessaria")
        return False

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")

        prompt = f"""Sei un esperto Python. DUST AI crasha all'avvio per un errore nel codice sorgente.
Analizza l'errore e genera una patch minimale per correggere il file.

## Errore
{error_str}

## Traceback
{tb_str[-2000:]}

## Versione Python
{sys.version}

## File sorgente ({Path(broken_file).name})
```python
{source[:4000]}
```

## Istruzioni CRITICHE
- Il fix deve essere compatibile con Python {sys.version_info.major}.{sys.version_info.minor}
- Errori comuni Python 3.11: backslash in f-string, walrus operator, match/case
- Per backslash in f-string: estrai il valore in una variabile PRIMA della f-string
- Rispondi SOLO con JSON valido, nessun testo aggiuntivo:

{{
  "can_fix": true,
  "analysis": "causa radice",
  "find": "stringa esatta da trovare (copia letterale dal sorgente, inclusi spazi)",
  "replace": "stringa corretta compatibile Python {sys.version_info.major}.{sys.version_info.minor}",
  "explanation": "cosa è stato cambiato"
}}

Se non puoi fixare: {{"can_fix": false, "analysis": "motivo"}}"""

        print("   🤖 Chiedo fix a Gemini...")
        response = model.generate_content(prompt)
        raw = response.text.strip()

        # Pulisci markdown
        import re
        raw = re.sub(r"```json\s*|```\s*", "", raw).strip()
        data = json.loads(raw)

        if not data.get("can_fix", False):
            print(f"   ℹ️  Gemini: {data.get('analysis', 'fix non possibile')}")
            return False

        find_str    = data.get("find", "")
        replace_str = data.get("replace", "")

        if not find_str or find_str not in source:
            print(f"   ⚠️  Stringa 'find' non trovata nel sorgente")
            # Prova a fare il fix noto per backslash in f-string automaticamente
            return _fix_backslash_fstrings(broken_file, source)

        # Backup
        backup = Path(broken_file).with_suffix(f".py.bak{int(time.time())}")
        backup.write_text(source, encoding="utf-8")

        # Applica patch
        patched = source.replace(find_str, replace_str, 1)
        Path(broken_file).write_text(patched, encoding="utf-8")

        # Verifica sintassi
        import ast
        try:
            ast.parse(patched)
            print(f"   ✅ Patch applicata e verificata: {data.get('explanation', '')}")
            return True
        except SyntaxError as e:
            # Ripristina backup
            Path(broken_file).write_text(source, encoding="utf-8")
            print(f"   ❌ Patch genera ancora syntax error ({e}) — ripristinato")
            return False

    except Exception as e:
        print(f"   ❌ Pre-boot patch fallita: {e}")
        # Prova fix automatico senza LLM
        return _fix_backslash_fstrings(broken_file, source)


def _fix_backslash_fstrings(filepath: str, source: str) -> bool:
    """
    Fix automatico senza LLM: trova e corregge backslash in f-string
    (incompatibili con Python < 3.12).
    """
    import re, ast

    original = source
    py_version = sys.version_info[:2]
    if py_version >= (3, 12):
        return False  # non necessario

    # Pattern: f"...{expr_con_backslash}..."
    # Sostituisce \\ dentro {} di f-string con variabile temporanea
    changed = False
    lines = source.splitlines()
    new_lines = []

    for line in lines:
        # Cerca pattern: f"... {os.environ.get('X','C:\\Y')}\\Z ..."
        if 'f"' in line or "f'" in line:
            # Cerca backslash dentro le parentesi graffe dell'f-string
            if re.search(r'\{[^}]*\\[^}]*\}', line):
                # Estrai indentazione
                indent = len(line) - len(line.lstrip())
                ind = " " * indent
                # Prova a riscrivere estraendo il valore
                new_line = re.sub(
                    r"f\"([^\"]*)\{([^}]*\\[^}]*)\}([^\"]*)\"",
                    lambda m: f'_tmp = {m.group(2)}\n{ind}f"{m.group(1)}{{_tmp}}{m.group(3)}"',
                    line.strip()
                )
                if new_line != line.strip():
                    new_lines.append(ind + new_line)
                    changed = True
                    continue
        new_lines.append(line)

    if not changed:
        return False

    patched = "\n".join(new_lines)
    try:
        ast.parse(patched)
        backup = Path(filepath).with_suffix(f".py.bak{int(time.time())}")
        backup.write_text(original, encoding="utf-8")
        Path(filepath).write_text(patched, encoding="utf-8")
        print(f"   ✅ Fix automatico backslash f-string applicato")
        return True
    except SyntaxError:
        return False


# ─── Main boot loop ───────────────────────────────────────────────────────────

def boot():
    state = load_boot_state()

    if state["attempts"] >= MAX_BOOT_ATTEMPTS:
        print(f"\n❌ DUST AI ha fallito {MAX_BOOT_ATTEMPTS} avvii consecutivi.")
        print(f"   Ultimo errore: {state.get('last_error', 'N/A')}")
        print(f"   File rotto:    {state.get('last_file', 'N/A')}")
        print(f"\n   Ripristina manualmente oppure elimina:")
        print(f"   {BOOT_STATE_FILE}")
        input("\nPremi Enter per uscire...")
        sys.exit(1)

    state["attempts"] += 1
    save_boot_state(state)

    # ── Imposta UI mode ───────────────────────────────────────────────────────
    args = sys.argv[1:]
    os.environ["DUSTAI_UI"] = "console" if "--console" in args else "gui"

    # ── Tenta avvio normale ───────────────────────────────────────────────────
    try:
        from src.app import DustApp
        app = DustApp()
        app.run()
        clear_boot_state()  # avvio riuscito → reset contatore

    except (SyntaxError, ImportError, AttributeError, TypeError) as e:
        tb_str    = traceback.format_exc()
        error_str = str(e)

        print(f"\n💥 Boot error: {type(e).__name__}: {error_str}")
        print(f"   Tentativo {state['attempts']}/{MAX_BOOT_ATTEMPTS}")

        # Salva nel boot state
        broken_path, broken_name = extract_broken_file(tb_str)
        state["last_error"] = f"{type(e).__name__}: {error_str}"
        state["last_file"]  = broken_path
        save_boot_state(state)

        if not broken_path:
            print("   ⚠️  Impossibile identificare il file rotto dalla traceback")
            print(tb_str)
            sys.exit(1)

        print(f"   📄 File rotto: {broken_name}")

        # Prova a patchare
        patched = preboot_patch(error_str, tb_str, broken_path)

        if patched:
            print(f"\n🔄 Riavvio automatico dopo patch...\n")
            time.sleep(1)
            # Riavvia lo stesso processo
            os.execv(sys.executable, [sys.executable] + sys.argv)
        else:
            print(f"\n❌ Patch non applicata — riavvia manualmente dopo aver corretto {broken_name}")
            print(f"   Traceback completo:\n{tb_str}")
            sys.exit(1)

    except Exception as e:
        # Errore runtime (non di sintassi) — avvio comunque riuscito abbastanza
        clear_boot_state()
        raise


if __name__ == "__main__":
    boot()
