"""Unit tests for the synthesizer — LLM prompt construction and answer formatting."""

from __future__ import annotations

from unittest.mock import MagicMock


class TestBuildPrompt:
    def test_prompt_includes_question(self):
        from kris.query.synthesizer import build_prompt

        prompt = build_prompt("What is Python?", [])
        assert "What is Python?" in prompt

    def test_prompt_includes_chunk_context(self):
        from kris.query.retriever import RetrievalResult
        from kris.query.synthesizer import build_prompt

        chunks = [
            RetrievalResult(
                chunk_id="c1",
                chunk_text="Python is a programming language.",
                chunk_index=0,
                content_hash="h1",
                file_path="docs/intro.md",
                file_kind="markdown",
                source_id="s1",
                source_name="Test",
                score=0.95,
            ),
        ]
        prompt = build_prompt("What is Python?", chunks)
        assert "Python is a programming language." in prompt
        assert "docs/intro.md" in prompt

    def test_prompt_includes_multiple_sources(self):
        from kris.query.retriever import RetrievalResult
        from kris.query.synthesizer import build_prompt

        chunks = [
            RetrievalResult(
                chunk_id="c1",
                chunk_text="First chunk",
                chunk_index=0,
                content_hash="h1",
                file_path="file1.py",
                file_kind="code",
                source_id="s1",
                source_name="Test",
                score=0.9,
            ),
            RetrievalResult(
                chunk_id="c2",
                chunk_text="Second chunk",
                chunk_index=0,
                content_hash="h2",
                file_path="file2.md",
                file_kind="markdown",
                source_id="s1",
                source_name="Test",
                score=0.8,
            ),
        ]
        prompt = build_prompt("explain", chunks)
        assert "First chunk" in prompt
        assert "Second chunk" in prompt
        assert "file1.py" in prompt
        assert "file2.md" in prompt

    def test_prompt_no_chunks(self):
        from kris.query.synthesizer import build_prompt

        prompt = build_prompt("What is X?", [])
        assert "What is X?" in prompt
        # Should still produce a valid prompt even with no context


class TestFormatSources:
    def test_format_sources_includes_paths(self):
        from kris.query.retriever import RetrievalResult
        from kris.query.synthesizer import format_sources

        chunks = [
            RetrievalResult(
                chunk_id="c1",
                chunk_text="Some text from a file.",
                chunk_index=0,
                content_hash="h1",
                file_path="src/main.py",
                file_kind="code",
                source_id="s1",
                source_name="Test",
                score=0.9,
            ),
        ]
        formatted = format_sources(chunks)
        assert "src/main.py" in formatted

    def test_format_sources_empty(self):
        from kris.query.synthesizer import format_sources

        formatted = format_sources([])
        assert formatted == ""


class TestSynthesize:
    def test_synthesize_calls_llm(self):
        from kris.query.retriever import RetrievalResult
        from kris.query.synthesizer import synthesize

        chunks = [
            RetrievalResult(
                chunk_id="c1",
                chunk_text="Python is great.",
                chunk_index=0,
                content_hash="h1",
                file_path="notes.md",
                file_kind="markdown",
                source_id="s1",
                source_name="Test",
                score=0.95,
            ),
        ]

        mock_llm = MagicMock()
        mock_llm.create_chat_completion.return_value = {
            "choices": [{"message": {"content": "Python is a great language."}}],
        }

        mock_manager = MagicMock()
        mock_manager.load_llm.return_value = mock_llm

        mock_info = MagicMock()
        mock_info.name = "test-model"

        result = synthesize(
            question="What is Python?",
            chunks=chunks,
            model_manager=mock_manager,
            model_info=mock_info,
        )

        assert result.answer == "Python is a great language."
        assert len(result.sources) == 1
        mock_manager.load_llm.assert_called_once_with(mock_info)

    def test_synthesize_no_chunks_returns_no_results(self):
        from kris.query.synthesizer import synthesize

        mock_manager = MagicMock()
        mock_info = MagicMock()

        result = synthesize(
            question="What is X?",
            chunks=[],
            model_manager=mock_manager,
            model_info=mock_info,
        )

        assert "no relevant" in result.answer.lower() or "not find" in result.answer.lower()
        assert result.sources == []
        mock_manager.load_llm.assert_not_called()
