"""
DUST AI – FileOpsTool v2.0
Operazioni file sicure: read, write, list, delete, copy, move, exists.
"""
import logging
import shutil
from pathlib import Path

log = logging.getLogger("FileOpsTool")


class FileOpsTool:
    MAX_READ_BYTES = 512 * 1024   # 512 KB max per file_read

    def __init__(self, config):
        self.config = config

    def file_read(self, path: str) -> str:
        p = self._resolve(path)
        if not p:
            return "❌ Path non valido: " + str(path)
        if not p.exists():
            return "❌ File non trovato: " + str(p)
        if not p.is_file():
            return "❌ Non è un file: " + str(p)
        try:
            size = p.stat().st_size
            if size > self.MAX_READ_BYTES:
                return "❌ File troppo grande (" + str(size // 1024) + " KB) — usa sys_exec con type/head"
            return p.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return "❌ Lettura fallita: " + str(e)

    def file_write(self, path: str, content: str, mode: str = "w") -> str:
        p = self._resolve(path)
        if not p:
            return "❌ Path non valido: " + str(path)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            if mode == "a":
                with open(p, "a", encoding="utf-8") as f:
                    f.write(content)
                return "✅ Testo aggiunto a: " + str(p)
            else:
                p.write_text(content, encoding="utf-8")
                return "✅ File scritto: " + str(p) + " (" + str(len(content)) + " chars)"
        except PermissionError:
            return "❌ Accesso negato: " + str(p)
        except Exception as e:
            return "❌ Scrittura fallita: " + str(e)

    def file_list(self, path: str) -> str:
        p = self._resolve(path)
        if not p:
            return "❌ Path non valido: " + str(path)
        if not p.exists():
            return "❌ Directory non trovata: " + str(p)
        try:
            items   = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
            lines   = []
            for item in items[:100]:
                prefix = "[DIR] " if item.is_dir() else "[FILE]"
                size   = ""
                if item.is_file():
                    try:
                        size = " (" + str(item.stat().st_size) + "b)"
                    except Exception:
                        pass
                lines.append(prefix + " " + item.name + size)
            if len(items) > 100:
                lines.append("... (" + str(len(items) - 100) + " altri)")
            return "\n".join(lines) if lines else "(directory vuota)"
        except PermissionError:
            return "❌ Accesso negato: " + str(p)
        except Exception as e:
            return "❌ List fallita: " + str(e)

    def file_delete(self, path: str) -> str:
        p = self._resolve(path)
        if not p:
            return "❌ Path non valido: " + str(path)
        if not p.exists():
            return "❌ Non trovato: " + str(p)
        try:
            if p.is_dir():
                shutil.rmtree(p)
                return "✅ Directory eliminata: " + str(p)
            p.unlink()
            return "✅ File eliminato: " + str(p)
        except PermissionError:
            return "❌ Accesso negato: " + str(p)
        except Exception as e:
            return "❌ Delete fallita: " + str(e)

    def file_exists(self, path: str) -> str:
        p = self._resolve(path)
        if not p:
            return "false"
        exists = p.exists()
        kind   = "directory" if p.is_dir() else "file" if p.is_file() else "unknown"
        return ("true (" + kind + ")") if exists else "false"

    def file_copy(self, path: str, destination: str) -> str:
        src  = self._resolve(path)
        dst  = self._resolve(destination)
        if not src or not dst:
            return "❌ Path non valido"
        if not src.exists():
            return "❌ Sorgente non trovata: " + str(src)
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)
            return "✅ Copiato: " + str(src) + " → " + str(dst)
        except Exception as e:
            return "❌ Copy fallita: " + str(e)

    def file_move(self, path: str, destination: str) -> str:
        src = self._resolve(path)
        dst = self._resolve(destination)
        if not src or not dst:
            return "❌ Path non valido"
        if not src.exists():
            return "❌ Sorgente non trovata: " + str(src)
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            return "✅ Spostato: " + str(src) + " → " + str(dst)
        except Exception as e:
            return "❌ Move fallita: " + str(e)

    def _resolve(self, path: str) -> Path:
        try:
            p = Path(path.strip())
            if not p.is_absolute():
                p = self.config.get_base_path() / p
            return p
        except Exception:
            return None
