import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VIOLATION_FILE = ROOT / "src" / "quality" / "_tmp_violation.py"


def test_import_linter_ловит_нарушение_границы() -> None:
    VIOLATION_FILE.write_text("from src.production import models\n", encoding="utf-8")
    try:
        result = subprocess.run(
            ["uv", "run", "lint-imports", "--no-cache"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        assert result.returncode != 0
    finally:
        VIOLATION_FILE.unlink()
