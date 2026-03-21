"""Text extraction — reads files and returns raw text content."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import charset_normalizer


@dataclass
class ExtractionResult:
    content_hash: str
    text: str
    encoding: str
    size: int


class ExtractionError(Exception):
    """Raised when text extraction fails."""


def extract_text(file_path: Path) -> tuple[str, str]:
    """Read a file and return (text, detected_encoding).

    Uses charset-normalizer for encoding detection on binary reads.
    """
    raw = file_path.read_bytes()
    if not raw:
        return "", "utf-8"

    # Try UTF-8 first (most common)
    try:
        text = raw.decode("utf-8")
        return text, "utf-8"
    except UnicodeDecodeError:
        pass

    # Fall back to charset-normalizer
    result = charset_normalizer.from_bytes(raw).best()
    if result is None:
        raise ExtractionError(f"Cannot detect encoding for {file_path}")

    return str(result), str(result.encoding)


def extract_for_content(
    conn: sqlite3.Connection,
    content_hash: str,
    data_dir: Path,
) -> ExtractionResult:
    """Extract text for a content record by finding a file with that hash.

    Looks up the file path from the catalog, reads and decodes it.
    """
    row = conn.execute(
        "SELECT f.path, s.base_path FROM file f JOIN source s ON f.source_id = s.id "
        "WHERE f.content_hash = ? AND f.visibility = 'active' LIMIT 1",
        (content_hash,),
    ).fetchone()

    if not row:
        raise ExtractionError(f"No active file found for content_hash={content_hash}")

    file_path = Path(row["base_path"]) / row["path"]
    if not file_path.exists():
        raise ExtractionError(f"File not found: {file_path}")

    text, encoding = extract_text(file_path)

    return ExtractionResult(
        content_hash=content_hash,
        text=text,
        encoding=encoding,
        size=len(text),
    )
