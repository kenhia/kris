"""Tests for text extraction."""

from __future__ import annotations

from pathlib import Path

from kris.processing.extract import extract_text


class TestExtractText:
    def test_extract_utf8(self, tmp_path: Path):
        f = tmp_path / "hello.txt"
        f.write_text("Hello, world!", encoding="utf-8")
        text, enc = extract_text(f)
        assert text == "Hello, world!"
        assert enc == "utf-8"

    def test_extract_empty_file(self, tmp_path: Path):
        f = tmp_path / "empty.txt"
        f.write_bytes(b"")
        text, enc = extract_text(f)
        assert text == ""
        assert enc == "utf-8"

    def test_extract_utf8_bom(self, tmp_path: Path):
        f = tmp_path / "bom.txt"
        f.write_bytes(b"\xef\xbb\xbfHello BOM")
        text, _enc = extract_text(f)
        assert "Hello BOM" in text

    def test_extract_latin1(self, tmp_path: Path):
        f = tmp_path / "latin.txt"
        # Latin-1 text with accented characters
        f.write_bytes("café résumé".encode("latin-1"))
        text, _enc = extract_text(f)
        assert "caf" in text  # charset-normalizer should decode this

    def test_extract_markdown(self, tmp_path: Path):
        f = tmp_path / "readme.md"
        f.write_text("# Title\n\nSome content.\n", encoding="utf-8")
        text, _enc = extract_text(f)
        assert text.startswith("# Title")

    def test_extract_python(self, tmp_path: Path):
        f = tmp_path / "main.py"
        f.write_text('print("hello")\n', encoding="utf-8")
        text, _enc = extract_text(f)
        assert 'print("hello")' in text
