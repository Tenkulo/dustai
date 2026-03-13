"""DUST AI entry point."""
import sys
from pathlib import Path

BASE = Path(__file__).parent
SRC  = BASE / "src"
sys.path.insert(0, str(SRC))

def main():
    try:
        import tkinter as tk
        from tkinter import ttk
        from ui.gui import DustGUI, C
        root = tk.Tk()
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        DustGUI(root)
        root.mainloop()
    except ImportError as exc:
        print(f"GUI non disponibile ({exc}), uso console.")
        try:
            from ui.console import ConsoleUI
            ConsoleUI().run()
        except ImportError:
            print("Nessuna UI disponibile.")

if __name__ == "__main__":
    main()
