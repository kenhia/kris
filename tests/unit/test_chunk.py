"""Tests for chunking strategies."""

from __future__ import annotations

from kris.processing.chunk import chunk_code, chunk_markdown, chunk_text


class TestChunkText:
    def test_short_text_single_chunk(self):
        chunks = chunk_text("Hello world.", "hash1")
        assert len(chunks) == 1
        assert chunks[0].content == "Hello world."
        assert chunks[0].chunking_strategy == "text"

    def test_empty_text(self):
        chunks = chunk_text("", "hash1")
        assert len(chunks) == 0

    def test_whitespace_only(self):
        chunks = chunk_text("   \n\n  ", "hash1")
        assert len(chunks) == 0

    def test_multiple_paragraphs(self):
        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        chunks = chunk_text(text, "hash1", max_chunk_size=30)
        assert len(chunks) >= 2
        # All content should be represented
        all_text = " ".join(c.content for c in chunks)
        assert "First paragraph" in all_text
        assert "Third paragraph" in all_text

    def test_chunk_indices_sequential(self):
        text = "A" * 500 + "\n\n" + "B" * 500 + "\n\n" + "C" * 500
        chunks = chunk_text(text, "hash1", max_chunk_size=600)
        indices = [c.chunk_index for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_chunk_content_hash_set(self):
        chunks = chunk_text("Some text content.", "hash1")
        assert len(chunks) == 1
        assert chunks[0].chunk_content_hash  # not empty
        assert len(chunks[0].chunk_content_hash) == 64  # SHA-256 hex


class TestChunkMarkdown:
    def test_markdown_sections(self):
        text = "# Title\n\nIntro text.\n\n## Section 1\n\nContent 1.\n\n## Section 2\n\nContent 2."
        chunks = chunk_markdown(text, "hash1")
        assert len(chunks) >= 1
        strategies = {c.chunking_strategy for c in chunks}
        assert "markdown" in strategies

    def test_empty_markdown(self):
        chunks = chunk_markdown("", "hash1")
        assert len(chunks) == 0


class TestChunkCode:
    def test_code_fallback_lines(self):
        code = "\n".join(f"line_{i} = {i}" for i in range(100))
        chunks = chunk_code(code, "hash1", language="unknown_lang", max_chunk_size=200)
        assert len(chunks) >= 1
        # All chunks should have code_lines strategy (fallback)
        for c in chunks:
            assert c.chunking_strategy in ("code_ast", "code_lines")

    def test_short_code_single_chunk(self):
        code = 'def hello():\n    print("hi")\n'
        chunks = chunk_code(code, "hash1", max_chunk_size=5000)
        assert len(chunks) >= 1

    def test_empty_code(self):
        # chunk_code with empty string should use fallback which returns empty
        chunks = chunk_code("", "hash1")
        assert len(chunks) == 0
