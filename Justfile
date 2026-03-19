# kris — build automation

# Build everything
build:
    cd scanner && cargo build --release
    uv sync

# Run all tests
test:
    cd scanner && cargo test
    uv run pytest

# Full pre-commit check: format, lint, typecheck, test
check: fmt-check lint test

# Format code
fmt:
    cd scanner && cargo fmt
    uv run ruff format .

# Check formatting without modifying
fmt-check:
    cd scanner && cargo fmt --check
    uv run ruff format --check .

# Lint
lint:
    cd scanner && cargo clippy -- -D warnings
    uv run ruff check .
    uv run ty check

# Clean build artifacts
clean:
    cd scanner && cargo clean
    rm -rf dist/ .pytest_cache/ .ruff_cache/
    find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
