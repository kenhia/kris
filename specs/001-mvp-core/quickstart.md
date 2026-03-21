# kris MVP — Quick Start Guide

## Prerequisites

- Linux (x86_64)
- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Rust toolchain (for building the scanner)
- NVIDIA GPU with CUDA support (for embedding and LLM inference)

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/kenhia/kris.git
cd kris
```

### 2. Build the Rust scanner

```bash
cd scanner
cargo build --release
cd ..
```

The scanner binary is at `scanner/target/release/kris-scanner`.

### 3. Set up the Python environment

```bash
uv sync
```

This installs all Python dependencies from `uv.lock`.

### 4. Initialize kris

```bash
uv run kris init
```

This creates a default configuration file at
`$XDG_CONFIG_HOME/kris/config.toml` (typically
`~/.config/kris/config.toml`).

## Configuration

Edit the config file to add your data sources:

```toml
[sources.my-code]
name = "Source Code"
type = "local"
base_path = "~/src"
exclude_patterns = ["target", "node_modules", ".git", ".venv"]

[[sources.my-code.schedules]]
path_pattern = "**"
interval_minutes = 60
priority = 1
```

Validate the configuration:

```bash
uv run kris config validate
```

## First Index

Run the initial scan and indexing:

```bash
uv run kris index
```

This will:
1. Scan all configured source directories
2. Catalog every discovered file
3. Extract text from text, code, and markdown files
4. Chunk the extracted text
5. Generate embeddings and store them in Qdrant

The first run may take a while depending on how many files you have.
Monitor progress with:

```bash
uv run kris status
```

## Querying

Ask a question about your indexed files:

```bash
uv run kris query "how does the authentication module work?"
```

To see the source chunks used to generate the answer:

```bash
uv run kris query --show-sources "error handling patterns"
```

To retrieve chunks without LLM synthesis:

```bash
uv run kris retrieve "database connection"
```

## Other Commands

```bash
# Check index status
uv run kris status

# Find duplicate files
uv run kris duplicates

# Clean up missing files older than 30 days
uv run kris cleanup --older-than 30d

# Re-index (only processes changes)
uv run kris index
```

## Development

```bash
# Run all checks
just check

# Run tests
just test

# Format code
just fmt
```
