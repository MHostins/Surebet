"""Convenience launcher for the read-only SureBet.com bookmaker discovery mode."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    return subprocess.call(
        [sys.executable, "main.py", "--mode", "bookmaker-discovery"],
        cwd=project_root,
    )


if __name__ == "__main__":
    raise SystemExit(main())
