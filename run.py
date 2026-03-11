#!/usr/bin/env python3
"""
DUST AI – Entry point
Uso:
  python run.py          → GUI (default)
  python run.py --gui    → GUI forzata
  python run.py --console → terminale
"""
import sys
import os

# Root del progetto nel path
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from src.app import DustApp

if __name__ == "__main__":
    args = sys.argv[1:]
    if "--console" in args:
        os.environ["DUSTAI_UI"] = "console"
    else:
        os.environ["DUSTAI_UI"] = "gui"   # default: GUI

    app = DustApp()
    app.run()
