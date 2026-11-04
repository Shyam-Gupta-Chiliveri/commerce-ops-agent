from __future__ import annotations

import json
from pathlib import Path

from opsagent.paths import FIXTURES


def load_json(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def quellberg_csv() -> Path:
    return FIXTURES / "quellberg" / "results.csv"
