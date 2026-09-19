# Implementation Plan: OpenSearch Transition

**Branch**: `003-opensearch-transition` | **Date**: 2026-03-29 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/003-opensearch-transition/spec.md`

## Summary

Replace Qdrant with OpenSearch as kris's unified vector and text search backend. The `qdrant-client` dependency is removed and replaced with `opensearch-py` (v3.x). OpenSearch stores both embedding vectors (k-NN with Lucene engine) and chunk text (BM25-searchable) in a single `kris_chunks` index. kris connects to an existing external OpenSearch deployment over HTTPS with username/password authentication. SQLite remains the catalog and task queue — only the embedding/retrieval layer changes. See [research.md](research.md) for all technical decisions.

## Technical Context

**Language/Version**: Python 3.12+, Rust (scanner — unchanged this sprint)  
**Primary Dependencies**: `opensearch-py>=3.0` (replaces `qdrant-client>=1.14`), `sentence-transformers`, `llama-cpp-python`, `rich`, `typer`  
**Storage**: SQLite (catalog, task queue, chunk store — unchanged), OpenSearch (vectors + text — new)  
**Testing**: pytest (unit + integration), mocked OpenSearch client for unit tests  
**Target Platform**: Linux (personal workstation)  
**Project Type**: CLI application  
**Performance Goals**: Index 20K+ chunks without timeout; query latency <2s including LLM synthesis  
**Constraints**: Single-node OpenSearch, localhost only, self-signed TLS certs  
**Scale/Scope**: ~20K–100K chunks, single user, 768-dim embeddings (BAAI/bge-base-en-v1.5)  

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | Principle | Status | Notes |
|---|-----------|--------|-------|
| I | Spec-Driven Development | ✅ PASS | Spec at `specs/003-opensearch-transition/spec.md` with 32 FRs, 9 SCs |
| II | Architecture First | ✅ PASS | `docs/architecture.md` and `docs/data-model.md` will be updated during implementation |
| III | Test-Driven Development | ✅ PASS | TDD planned: unit tests with mocked OpenSearch, integration tests with live instance |
| IV | Code Standards Gate | ✅ PASS | Pre-commit: `ruff format`, `ruff check`, `ty check`, `pytest` |
| V | User Documentation | ✅ PASS | `docs/setup.md` and `docs/usage.md` updates are in scope (FR-031, FR-032) |
| VI | Quality & Accessibility | ✅ PASS | Rich CLI output, actionable error messages (R9), stderr for errors |
| VII | Simplicity | ✅ PASS | Direct replacement — no new abstractions. Single index, single client factory |

**Post-Phase 1 re-check**: All gates remain ✅. Design adds no unnecessary complexity — data model changes are column renames, config is a direct replacement, client factory is a single function.

## Project Structure

### Documentation (this feature)

```text
specs/003-opensearch-transition/
├── plan.md              # This file
├── spec.md              # Feature specification (32 FRs, 9 SCs)
├── research.md          # Phase 0: 10 research decisions (R1–R10)
├── data-model.md        # Phase 1: entity changes, ER diagram
├── quickstart.md        # Phase 1: developer quickstart
├── contracts/
│   └── cli.md           # Phase 1: CLI interface changes
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks.md             # Phase 2 output (/speckit.tasks — NOT created by /speckit.plan)
```

### Source Code (files modified by this sprint)

```text
src/kris/
├── config/
│   ├── schema.py            # QdrantConfig → OpenSearchConfig, remove qdrant_path
│   └── defaults.py          # Default config TOML: [qdrant] → [opensearch]
├── processing/
│   ├── embed.py             # create_qdrant_client → create_opensearch_client,
│   │                        #   ensure_collection → ensure_index,
│   │                        #   embed_chunks → bulk index to OpenSearch
│   └── worker.py            # qdrant_path param → opensearch config passthrough
├── query/
│   ├── retriever.py         # Qdrant query_points → OpenSearch k-NN search
│   └── engine.py            # qdrant_path passthrough → opensearch config
├── cli/
│   ├── index.py             # Pass opensearch config instead of qdrant_path
│   ├── query.py             # Pass opensearch config instead of qdrant_path
│   ├── cleanup.py           # Delete from OpenSearch instead of Qdrant
│   ├── config_cmd.py        # Add OpenSearch connectivity check to validate
│   └── diagnose.py          # Add OpenSearch health section
├── catalog/
│   ├── models.py            # Embedding.qdrant_point_id → .opensearch_doc_id
│   └── db.py                # EMBEDDING table schema, migration logic
└── __init__.py              # (unchanged)

tests/
├── unit/
│   ├── test_config.py       # TestQdrantConfig → TestOpenSearchConfig
│   ├── test_retriever.py    # Mock OpenSearch search instead of Qdrant
│   ├── test_cleanup.py      # Mock OpenSearch delete
│   ├── test_status.py       # Update for new config shape
│   └── test_worker_logging.py  # Update for new config shape
├── integration/
│   ├── test_index_flow.py   # End-to-end with OpenSearch
│   └── test_query_flow.py   # End-to-end with OpenSearch
└── conftest.py              # OpenSearch fixtures (mock client, test index)

pyproject.toml               # qdrant-client → opensearch-py dependency swap
```

**Structure Decision**: Existing single-project layout. No new directories or modules — this is a backend swap within the existing `processing/`, `query/`, `config/`, `catalog/`, and `cli/` packages. The 19 files identified in the codebase inventory (11 source + 8 test) map directly to the tree above.

## Complexity Tracking

No constitution violations to justify. The sprint is a direct backend replacement with no new abstractions, no additional projects, and no speculative features.
