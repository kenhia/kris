"""Integration test for the Rust scanner binary."""

from __future__ import annotations

import json
import sqlite3
import subprocess

import pytest

from kris.catalog.db import get_connection
from kris.scanner import find_scanner_binary


@pytest.fixture
def scanner_binary():
    """Locate the built scanner binary, skip if not found."""
    try:
        return find_scanner_binary()
    except Exception:
        pytest.skip("kris-scanner binary not built — run 'cd scanner && cargo build --release'")


@pytest.fixture
def scan_env(tmp_path):
    """Set up a scan environment with a temp directory and database."""
    db_path = tmp_path / "test.db"
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    # Create test files
    (data_dir / "hello.txt").write_text("Hello, world!", encoding="utf-8")
    (data_dir / "main.py").write_text('print("hello")\n', encoding="utf-8")
    (data_dir / "readme.md").write_text("# Test\n\nContent.\n", encoding="utf-8")
    sub = data_dir / "sub"
    sub.mkdir()
    (sub / "nested.txt").write_text("nested content", encoding="utf-8")

    # Initialize database with schema
    conn = get_connection(db_path)
    conn.execute(
        "INSERT INTO source (id, name, source_type, base_path) VALUES (?, ?, ?, ?)",
        ("test-src", "Test", "local", str(data_dir)),
    )
    conn.commit()
    conn.close()

    return {"db_path": db_path, "data_dir": data_dir}


class TestScannerBinary:
    def test_scan_produces_json_output(self, scanner_binary, scan_env):
        result = subprocess.run(
            [
                str(scanner_binary),
                "--db",
                str(scan_env["db_path"]),
                "--source-id",
                "test-src",
                "--base-path",
                str(scan_env["data_dir"]),
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["files_found"] == 4

    def test_scan_populates_database(self, scanner_binary, scan_env):
        subprocess.run(
            [
                str(scanner_binary),
                "--db",
                str(scan_env["db_path"]),
                "--source-id",
                "test-src",
                "--base-path",
                str(scan_env["data_dir"]),
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        conn = sqlite3.connect(str(scan_env["db_path"]))
        conn.row_factory = sqlite3.Row
        files = conn.execute("SELECT * FROM file WHERE source_id = 'test-src'").fetchall()
        conn.close()

        assert len(files) == 4
        paths = {f["path"] for f in files}
        assert "hello.txt" in paths
        assert "main.py" in paths
        assert "readme.md" in paths

    def test_scan_creates_content_records(self, scanner_binary, scan_env):
        subprocess.run(
            [
                str(scanner_binary),
                "--db",
                str(scan_env["db_path"]),
                "--source-id",
                "test-src",
                "--base-path",
                str(scan_env["data_dir"]),
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        conn = sqlite3.connect(str(scan_env["db_path"]))
        count = conn.execute("SELECT COUNT(*) FROM content").fetchone()[0]
        conn.close()

        assert count >= 4  # one content per unique hash

    def test_scan_with_excludes(self, scanner_binary, scan_env):
        # Create a directory to exclude
        excluded = scan_env["data_dir"] / ".git"
        excluded.mkdir()
        (excluded / "config").write_text("gitconfig", encoding="utf-8")

        result = subprocess.run(
            [
                str(scanner_binary),
                "--db",
                str(scan_env["db_path"]),
                "--source-id",
                "test-src",
                "--base-path",
                str(scan_env["data_dir"]),
                "--exclude",
                ".git",
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        data = json.loads(result.stdout)
        assert data["files_found"] == 4  # .git/config excluded

    def test_rescan_detects_unchanged(self, scanner_binary, scan_env):
        cmd = [
            str(scanner_binary),
            "--db",
            str(scan_env["db_path"]),
            "--source-id",
            "test-src",
            "--base-path",
            str(scan_env["data_dir"]),
            "--json",
        ]

        # First scan
        subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        # Second scan — same files
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        data = json.loads(result.stdout)
        assert data["files_unchanged"] == 4
        assert data["files_new"] == 0
