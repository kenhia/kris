"""Scanner runner — invokes the Rust scanner binary for a source."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ScanResult:
    files_found: int = 0
    files_new: int = 0
    files_changed: int = 0
    files_unchanged: int = 0
    files_missing: int = 0
    errors: int = 0


class ScannerError(Exception):
    """Raised when the scanner binary fails."""


def find_scanner_binary() -> Path:
    """Locate the kris-scanner binary."""
    # Check common locations
    pkg_root = Path(__file__).parent.parent.parent.parent
    candidates = [
        pkg_root / "scanner" / "target" / "release" / "kris-scanner",
        pkg_root / "scanner" / "target" / "debug" / "kris-scanner",
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate

    # Try PATH
    found = shutil.which("kris-scanner")
    if found:
        return Path(found)

    raise ScannerError("kris-scanner binary not found. Run 'cd scanner && cargo build --release'")


def run_scanner(
    db_path: Path,
    source_id: str,
    base_path: Path,
    exclude_patterns: list[str] | None = None,
    follow_symlinks: bool = False,
) -> ScanResult:
    """Run the Rust scanner binary for a single source."""
    binary = find_scanner_binary()

    cmd = [
        str(binary),
        "--db",
        str(db_path),
        "--source-id",
        source_id,
        "--base-path",
        str(base_path),
        "--json",
    ]

    for pattern in exclude_patterns or []:
        cmd.extend(["--exclude", pattern])

    if follow_symlinks:
        cmd.append("--follow-symlinks")

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=300,
    )

    if result.returncode != 0:
        raise ScannerError(f"Scanner failed: {result.stderr.strip()}")

    data = json.loads(result.stdout)
    return ScanResult(
        files_found=data.get("files_found", 0),
        files_new=data.get("files_new", 0),
        files_changed=data.get("files_changed", 0),
        files_unchanged=data.get("files_unchanged", 0),
        files_missing=data.get("files_missing", 0),
        errors=data.get("errors", 0),
    )
