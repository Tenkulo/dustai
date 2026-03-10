"""
DUST AI – Tool: file_ops
Operazioni file affidabili: read, write, list, delete, exists.
Usa percorsi assoluti. OneDrive-aware su Windows.
"""
import os
import shutil
import logging
from pathlib import Path


class FileOpsTool:
    def __init__(self, config):
        self.config = config
        self.log = logging.getLogger("FileOpsTool")

    def get_desktop(self) -> str:
        """Restituisce il percorso Desktop reale (OneDrive-aware)."""
        return str(self.config.get_desktop())

    def file_read(self, path: str, encoding: str = "utf-8") -> str:
        """Legge il contenuto di un file."""
        try:
            p = Path(path)
            if not p.exists():
                return f"❌ File non trovato: {path}"
            content = p.read_text(encoding=encoding, errors="replace")
            return content if content else "[file vuoto]"
        except Exception as e:
            return f"❌ Errore lettura {path}: {e}"

    def file_write(self, path: str, content: str, encoding: str = "utf-8", append: bool = False) -> str:
        """Scrive contenuto in un file. Crea directory se non esiste."""
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            mode = "a" if append else "w"
            with open(p, mode, encoding=encoding) as f:
                f.write(content)
            return f"✅ File scritto: {path} ({p.stat().st_size} bytes)"
        except Exception as e:
            return f"❌ Errore scrittura {path}: {e}"

    def file_list(self, path: str, pattern: str = "*", recursive: bool = False) -> str:
        """Lista file in una directory."""
        try:
            p = Path(path)
            if not p.exists():
                return f"❌ Directory non trovata: {path}"
            if not p.is_dir():
                return f"❌ Non è una directory: {path}"

            if recursive:
                files = list(p.rglob(pattern))
            else:
                files = list(p.glob(pattern))

            if not files:
                return f"[directory vuota o nessun file con pattern '{pattern}']"

            result = []
            for f in sorted(files):
                if f.is_dir():
                    result.append(f"📁 {f.name}/")
                else:
                    size = f.stat().st_size
                    result.append(f"📄 {f.name} ({size} bytes)")

            return "\n".join(result)
        except Exception as e:
            return f"❌ Errore listing {path}: {e}"

    def file_delete(self, path: str) -> str:
        """Elimina file o directory."""
        try:
            p = Path(path)
            if not p.exists():
                return f"❌ Non trovato: {path}"
            if p.is_dir():
                shutil.rmtree(p)
                return f"✅ Directory eliminata: {path}"
            else:
                p.unlink()
                return f"✅ File eliminato: {path}"
        except Exception as e:
            return f"❌ Errore eliminazione {path}: {e}"

    def file_exists(self, path: str) -> str:
        """Verifica se un file o directory esiste."""
        p = Path(path)
        if p.exists():
            kind = "directory" if p.is_dir() else "file"
            size = p.stat().st_size if p.is_file() else "-"
            return f"✅ Esiste ({kind}, {size} bytes): {path}"
        return f"❌ Non esiste: {path}"
