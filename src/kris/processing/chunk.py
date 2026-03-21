"""Chunking strategies — split text into chunks for embedding."""

from __future__ import annotations

import hashlib
import re
import sqlite3
import uuid
from dataclasses import dataclass

from kris.catalog.models import Chunk


@dataclass
class ChunkResult:
    chunks: list[Chunk]
    strategy: str


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Text / markdown semantic chunking
# ---------------------------------------------------------------------------

_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")
_HEADING_SPLIT = re.compile(r"(?=^#{1,6}\s)", re.MULTILINE)

DEFAULT_CHUNK_SIZE = 1000  # target characters per chunk
DEFAULT_CHUNK_OVERLAP = 100


def chunk_text(
    text: str,
    content_hash: str,
    strategy: str = "text",
    max_chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[Chunk]:
    """Split text into chunks using paragraph boundaries.

    Tries to split on paragraph boundaries (double newlines). If a paragraph
    is still too large, splits on sentence boundaries.
    """
    if not text.strip():
        return []

    paragraphs = _PARAGRAPH_SPLIT.split(text)
    chunks: list[Chunk] = []
    current = ""
    current_start = 0
    offset = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            offset += 2  # account for split \n\n
            continue

        if current and len(current) + len(para) + 2 > max_chunk_size:
            # Flush current chunk
            chunks.append(
                _make_chunk(
                    content_hash,
                    len(chunks),
                    current,
                    current_start,
                    current_start + len(current),
                    strategy,
                )
            )
            # Overlap: keep tail of current
            if overlap > 0 and len(current) > overlap:
                current = current[-overlap:]
                current_start = offset - overlap
            else:
                current = ""
                current_start = offset

        if current:
            current += "\n\n" + para
        else:
            current = para
            current_start = offset

        offset += len(para) + 2  # +2 for the \n\n separator

    if current.strip():
        chunks.append(
            _make_chunk(
                content_hash,
                len(chunks),
                current,
                current_start,
                current_start + len(current),
                strategy,
            )
        )

    return chunks


def chunk_markdown(
    text: str,
    content_hash: str,
    max_chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[Chunk]:
    """Split markdown by heading boundaries, then paragraph-split large sections."""
    if not text.strip():
        return []

    sections = _HEADING_SPLIT.split(text)
    chunks: list[Chunk] = []
    offset = 0

    for section in sections:
        if not section.strip():
            offset += len(section)
            continue

        if len(section) <= max_chunk_size:
            chunks.append(
                _make_chunk(
                    content_hash,
                    len(chunks),
                    section.strip(),
                    offset,
                    offset + len(section),
                    "markdown",
                )
            )
        else:
            # Sub-split large sections by paragraph
            sub_chunks = chunk_text(
                section,
                content_hash,
                strategy="markdown",
                max_chunk_size=max_chunk_size,
                overlap=overlap,
            )
            for sc in sub_chunks:
                sc.chunk_index = len(chunks)
                sc.start_offset += offset
                sc.end_offset += offset
                chunks.append(sc)

        offset += len(section)

    return chunks


# ---------------------------------------------------------------------------
# Code chunking with tree-sitter
# ---------------------------------------------------------------------------


def chunk_code(
    text: str,
    content_hash: str,
    language: str = "python",
    max_chunk_size: int = DEFAULT_CHUNK_SIZE * 2,
) -> list[Chunk]:
    """Split code into chunks using tree-sitter AST nodes.

    Falls back to line-based splitting if tree-sitter parsing fails.
    """
    try:
        return _chunk_code_treesitter(text, content_hash, language, max_chunk_size)
    except Exception:
        # Fallback to line-based splitting
        return _chunk_code_lines(text, content_hash, max_chunk_size)


def _chunk_code_treesitter(
    text: str,
    content_hash: str,
    language: str,
    max_chunk_size: int,
) -> list[Chunk]:
    """Use tree-sitter to split code by top-level definitions."""
    import tree_sitter

    parser = tree_sitter.Parser()

    # Map language names to tree-sitter language modules
    lang_module = _get_treesitter_language(language)
    if lang_module is None:
        return _chunk_code_lines(text, content_hash, max_chunk_size)

    ts_lang = tree_sitter.Language(lang_module)
    parser.language = ts_lang
    tree = parser.parse(text.encode("utf-8"))

    chunks: list[Chunk] = []
    root = tree.root_node

    # Collect top-level named nodes (functions, classes, etc.)
    for child in root.children:
        node_text = text[child.start_byte : child.end_byte].strip()
        if not node_text:
            continue

        if len(node_text) <= max_chunk_size:
            chunks.append(
                _make_chunk(
                    content_hash,
                    len(chunks),
                    node_text,
                    child.start_byte,
                    child.end_byte,
                    "code_ast",
                )
            )
        else:
            # Large node — split by sub-children or lines
            sub = _chunk_code_lines(node_text, content_hash, max_chunk_size)
            for sc in sub:
                sc.chunk_index = len(chunks)
                sc.start_offset += child.start_byte
                sc.end_offset += child.start_byte
                chunks.append(sc)

    if not chunks and text.strip():
        # No top-level nodes found, fall back to line splitting
        return _chunk_code_lines(text, content_hash, max_chunk_size)

    return chunks


def _get_treesitter_language(language: str):
    """Try to import a tree-sitter language grammar."""
    module_map = {
        "python": "tree_sitter_python",
        "javascript": "tree_sitter_javascript",
        "typescript": "tree_sitter_typescript",
        "rust": "tree_sitter_rust",
        "go": "tree_sitter_go",
        "ruby": "tree_sitter_ruby",
        "java": "tree_sitter_java",
        "c": "tree_sitter_c",
        "cpp": "tree_sitter_cpp",
    }

    module_name = module_map.get(language)
    if module_name is None:
        return None

    try:
        import importlib

        mod = importlib.import_module(module_name)
        return mod.language()
    except ImportError:
        return None


def _chunk_code_lines(
    text: str,
    content_hash: str,
    max_chunk_size: int,
) -> list[Chunk]:
    """Fall-back line-based code splitting."""
    lines = text.split("\n")
    chunks: list[Chunk] = []
    current_lines: list[str] = []
    current_start = 0
    offset = 0

    for line in lines:
        current_lines.append(line)
        chunk_text_so_far = "\n".join(current_lines)

        if len(chunk_text_so_far) >= max_chunk_size:
            chunks.append(
                _make_chunk(
                    content_hash,
                    len(chunks),
                    chunk_text_so_far,
                    current_start,
                    offset + len(line),
                    "code_lines",
                )
            )
            current_lines = []
            current_start = offset + len(line) + 1

        offset += len(line) + 1  # +1 for \n

    if current_lines:
        remaining = "\n".join(current_lines)
        if remaining.strip():
            chunks.append(
                _make_chunk(
                    content_hash,
                    len(chunks),
                    remaining,
                    current_start,
                    offset,
                    "code_lines",
                )
            )

    return chunks


def _make_chunk(
    content_hash: str,
    index: int,
    text: str,
    start: int,
    end: int,
    strategy: str,
) -> Chunk:
    return Chunk(
        id=str(uuid.uuid4()),
        content_hash=content_hash,
        chunk_index=index,
        chunk_content_hash=_sha256_text(text),
        content=text,
        start_offset=start,
        end_offset=end,
        chunking_strategy=strategy,
    )


def save_chunks(conn: sqlite3.Connection, chunks: list[Chunk]) -> int:
    """Write chunks to the catalog. Returns count written."""
    for chunk in chunks:
        conn.execute(
            """INSERT OR REPLACE INTO chunk
               (id, content_hash, chunk_index, chunk_content_hash, content,
                start_offset, end_offset, chunking_strategy, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                chunk.id,
                chunk.content_hash,
                chunk.chunk_index,
                chunk.chunk_content_hash,
                chunk.content,
                chunk.start_offset,
                chunk.end_offset,
                chunk.chunking_strategy,
                chunk.metadata,
            ),
        )
    conn.commit()
    return len(chunks)
