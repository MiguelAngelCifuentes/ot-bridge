import sys
from pathlib import Path

# Raiz del servicio en el path: los tests importan domain/, app/ y adapters/ como el propio main.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
