"""Synthesizer — build LLM prompts from retrieved chunks, generate answers."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kris.models.manager import ModelManager
    from kris.models.registry import ModelInfo
    from kris.query.retriever import RetrievalResult

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a helpful assistant that answers questions based on the user's personal files. "
    "Use ONLY the provided context to answer. If the context doesn't contain enough information, "
    "say so. Always cite the source file paths when referencing information."
)


@dataclass
class SynthesisResult:
    answer: str
    sources: list[RetrievalResult] = field(default_factory=list)


def build_prompt(question: str, chunks: list[RetrievalResult]) -> str:
    """Build an LLM prompt with retrieved chunks as context."""
    if not chunks:
        return (
            f"Question: {question}\n\n"
            "No relevant context was found in the indexed files. "
            "Please answer based on general knowledge, and note that "
            "no file sources are available."
        )

    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        context_parts.append(f"[Source {i}: {chunk.file_path}]\n{chunk.chunk_text}")

    context = "\n\n".join(context_parts)
    return (
        f"Context from the user's files:\n\n{context}\n\n"
        f"Question: {question}\n\n"
        "Answer the question using the context above. "
        "Cite source files when referencing specific information."
    )


def format_sources(chunks: list[RetrievalResult]) -> str:
    """Format source citations for display."""
    if not chunks:
        return ""

    seen = {}
    lines = []
    for chunk in chunks:
        key = chunk.file_path
        if key not in seen:
            seen[key] = True
            lines.append(f"  {chunk.file_path} (score: {chunk.score:.2f})")

    return "Sources:\n" + "\n".join(lines)


def synthesize(
    question: str,
    chunks: list[RetrievalResult],
    model_manager: ModelManager,
    model_info: ModelInfo,
    max_tokens: int = 1024,
) -> SynthesisResult:
    """Generate an LLM answer from retrieved chunks.

    Returns a SynthesisResult with the answer and source references.
    """
    if not chunks:
        return SynthesisResult(
            answer="I could not find any relevant information in your indexed files.",
            sources=[],
        )

    llm = model_manager.load_llm(model_info)
    prompt = build_prompt(question, chunks)

    response = llm.create_chat_completion(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        max_tokens=max_tokens,
    )

    answer = response["choices"][0]["message"]["content"]

    return SynthesisResult(answer=answer, sources=chunks)
