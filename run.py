#!/usr/bin/env python3
"""
DUST AI – Desktop Unified Smart Tool
Entry point
"""
import sys
import os

# Aggiungi src al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from src.app import DustApp

if __name__ == "__main__":
    app = DustApp()
    app.run()
