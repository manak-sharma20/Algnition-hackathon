"""Puts src/ on sys.path so tests can `import generate_features` etc. the
same way the CLI scripts do (python src/train.py relies on the same
implicit path-insertion when run directly).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
