"""Data models for the kris catalog."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Source:
    id: str
    name: str
    base_path: str
    source_type: str = "local"
    config: str | None = None
    last_scan: datetime | None = None
    created_at: datetime | None = None


@dataclass
class ScanSchedule:
    id: str
    source_id: str
    path_pattern: str = "**"
    interval_minutes: int = 60
    priority: int = 100
    last_run: datetime | None = None
    next_run: datetime | None = None


@dataclass
class File:
    id: str
    source_id: str
    content_hash: str
    path: str
    size: int
    mtime: int
    file_kind: str
    mime_type: str | None = None
    processing_status: str = "pending"
    visibility: str = "active"
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    disappeared_at: datetime | None = None
    permissions: int | None = None


@dataclass
class Content:
    content_hash: str
    processing_status: str = "pending"
    last_processed: datetime | None = None
    parent_content_hash: str | None = None


@dataclass
class Task:
    id: str
    content_hash: str
    task_type: str
    status: str = "queued"
    model_hint: str | None = None
    priority: int = 100
    depends_on: list[str] = field(default_factory=list)
    attempts: int = 0
    max_attempts: int = 3
    error: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


@dataclass
class Chunk:
    id: str
    content_hash: str
    chunk_index: int
    chunk_content_hash: str
    content: str
    start_offset: int
    end_offset: int
    chunking_strategy: str
    metadata: str | None = None


@dataclass
class Embedding:
    id: str
    chunk_id: str
    model_id: str
    collection_name: str
    qdrant_point_id: str


@dataclass
class ModelRegistryEntry:
    id: str
    name: str
    model_type: str
    model_path_or_repo: str
    vram_gb: float
    dimensions: int | None = None
    config: str | None = None
