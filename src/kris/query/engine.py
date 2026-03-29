"""Query engine — orchestrates retrieval and LLM synthesis."""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from kris.query.retriever import RetrievalResult, retrieve
from kris.query.synthesizer import synthesize

if TYPE_CHECKING:
    from kris.config.schema import KrisConfig
    from kris.models.manager import ModelManager
    from kris.models.registry import ModelRegistry

logger = logging.getLogger(__name__)


@dataclass
class QueryResult:
    question: str
    answer: str | None
    results: list[RetrievalResult] = field(default_factory=list)
    retrieval_only: bool = False


def query(
    question: str,
    conn: sqlite3.Connection,
    model_manager: ModelManager,
    registry: ModelRegistry,
    config: KrisConfig,
    top_k: int = 10,
    source_filter: str | None = None,
    kind_filter: str | None = None,
    retrieval_only: bool = False,
) -> QueryResult:
    """Run a query: retrieve relevant chunks and optionally synthesize an answer.

    If retrieval_only is True, returns chunks without LLM synthesis.
    """
    embedding_info = registry.get("embedding")
    if embedding_info is None:
        raise RuntimeError("Embedding model not configured in registry")

    chunks = retrieve(
        query=question,
        conn=conn,
        model_manager=model_manager,
        model_info=embedding_info,
        config=config,
        top_k=top_k,
        source_filter=source_filter,
        kind_filter=kind_filter,
    )

    if retrieval_only:
        return QueryResult(
            question=question,
            answer=None,
            results=chunks,
            retrieval_only=True,
        )

    # Synthesize with LLM
    llm_info = registry.get("llm")
    if llm_info is None:
        raise RuntimeError(
            "LLM model not configured. Use 'kris retrieve' for retrieval-only mode, "
            "or configure [models.llm] in your config."
        )

    synthesis = synthesize(
        question=question,
        chunks=chunks,
        model_manager=model_manager,
        model_info=llm_info,
    )

    return QueryResult(
        question=question,
        answer=synthesis.answer,
        results=synthesis.sources,
    )
