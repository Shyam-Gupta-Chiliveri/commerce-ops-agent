from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = PROJECT_ROOT / "fixtures"
SCHEMA_PATH = Path(__file__).resolve().parent / "warehouse" / "schema.sql"
VAR_DIR = PROJECT_ROOT / "var"
