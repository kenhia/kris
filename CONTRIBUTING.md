# Contributing to kris

Thank you for your interest in contributing to **kris** - a local-first
personal data intelligence system for indexing, analyzing, and querying
data across local machines, remote hosts, and NAS storage. Contributions
of all kinds are welcome: bug fixes, new pipelines, documentation
improvements, architectural discussions, and performance enhancements.

This document describes the contribution process, coding expectations, and
licensing requirements.

---

## Guiding Principles

- **Local-first**: All processing runs on owned hardware. Remote LLM APIs
  are permitted only as an explicit quality fallback, never a default.
- **Modular architecture**: New functionality should fit cleanly into
  existing component boundaries (scanner, catalog, planner, workers,
  pipelines, query engine, model manager).
- **Spec-driven development**: All changes must be documented in `/specs/`
  before implementation. See the [constitution](.specify/memory/constitution.md)
  for the full workflow.
- **Interface-first**: Contracts between layers are stable; implementations
  evolve independently.
- **Strong typing**: Python code uses type hints throughout. Rust code
  follows standard idioms and passes `cargo clippy` cleanly.

If you are unsure where something belongs, open an issue - architectural
clarity is a core value of the project.

---

## Development Workflow

1. **Fork the repository**
   Create your own fork and work in a feature branch.

2. **Create an issue first (recommended)**
   For anything non-trivial, open an issue describing:
   - the problem
   - the proposed solution
   - any interface or contract changes

3. **Document the change**
   Add or update the relevant spec in `/specs/`. Ad-hoc changes that fall
   outside an active spec go in `/specs/supplemental-spec.md`.

4. **Follow TDD**
   Write failing tests first, then implement. See the constitution for
   the full Red-Green-Refactor expectations.

5. **Run pre-commit checks**
   All code must pass the checks below before submitting a PR.

6. **Submit a pull request**
   Include:
   - a clear description of the change
   - rationale and context
   - any architectural considerations
   - links to related issues

---

## Pre-Commit Checks

### Python

```bash
ruff format --check
ruff check
ty check
pytest -q
```

### Rust

```bash
cargo fmt --check
cargo clippy --all-targets --all-features -- -D warnings
cargo test
```

See the [constitution](.specify/memory/constitution.md) for additional
ecosystem checks (Svelte, PowerShell, C#) if those come into play.

---

## Testing

kris uses a layered testing strategy:

- **Unit tests** for module-level behavior
- **Integration tests** for cross-component boundaries
  (scanner/catalog, catalog/planner, retriever/Qdrant)
- **Contract tests** for interfaces and invariants

All new code must include appropriate tests.

---

## Code of Conduct

Be respectful, constructive, and collaborative. Architectural discussions
are welcome and encouraged - kris is designed to evolve.

---

## License and Contributor Agreement

By submitting a contribution, you agree that:

- Your contribution is licensed under the **Apache License 2.0**.
- You have the right to submit the work.
- You grant the project maintainers the right to redistribute and modify
  your contribution under the project license.

This ensures the project remains permissively licensed and safe for all
users.
