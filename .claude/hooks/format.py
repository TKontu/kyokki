"""PostToolUse hook: format the file Claude just wrote or edited.

Claude Code passes the tool event as JSON on stdin. Runs ruff on Python files and
ESLint on frontend TypeScript. Always exits 0 so a formatter problem never blocks an edit.
"""

import contextlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run(cmd: list[str], cwd: Path) -> None:
    with contextlib.suppress(OSError, subprocess.TimeoutExpired):
        subprocess.run(cmd, cwd=cwd, check=False, timeout=60)


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except (ValueError, OSError):
        return
    raw = event.get("tool_input", {}).get("file_path", "")
    if not raw:
        return
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        return

    if path.suffix == ".py":
        run(
            [sys.executable, "-m", "ruff", "check", "--fix", "--quiet", str(path)], ROOT
        )
        run([sys.executable, "-m", "ruff", "format", "--quiet", str(path)], ROOT)
        return

    frontend = ROOT / "frontend"
    is_frontend_source = (
        path.suffix in {".ts", ".tsx", ".js", ".jsx"} and frontend in path.parents
    )
    if is_frontend_source and (frontend / "node_modules" / ".bin").exists():
        run(["npx", "--no-install", "eslint", "--fix", "--quiet", str(path)], frontend)


if __name__ == "__main__":
    main()
