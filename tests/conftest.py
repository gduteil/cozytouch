"""Put the repository root on the path so custom_components is importable."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
