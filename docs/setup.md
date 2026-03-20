# kris — Installation and Setup Guide

## Prerequisites

| Requirement | Version | Purpose |
|-------------|---------|---------|
| Linux | x86_64 | Target platform |
| Python | 3.12+ | Core processing and CLI |
| [uv](https://docs.astral.sh/uv/) | latest | Python package manager |
| Rust toolchain | stable | Scanner binary |
| [Just](https://just.systems/) | latest | Build automation |
| NVIDIA GPU + CUDA | 16 GB VRAM recommended | Embedding and LLM inference |

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/kenhia/kris.git
cd kris
```

### 2. Build everything

```bash
just build
```

This runs `cargo build --release` for the Rust scanner and `uv sync`
for the Python environment. The scanner binary is at
`scanner/target/release/kris-scanner`.

### 3. Verify the build

```bash
just check
```

This runs formatting checks, linters, type checkers, and the full
test suite for both Rust and Python.

## Initial Configuration

### Create a default config

```bash
uv run kris init
```

This creates `~/.config/kris/config.toml` (or `$XDG_CONFIG_HOME/kris/config.toml`)
with sensible defaults and inline comments.

### Configure your sources

Edit the config file to add directories you want indexed:

```toml
[sources.my-code]
name = "Source Code"
type = "local"
base_path = "~/src"
exclude_patterns = ["target", "node_modules", ".git", ".venv", "__pycache__"]

[[sources.my-code.schedules]]
path_pattern = "**"
interval_minutes = 60
priority = 1

[sources.documents]
name = "Documents"
type = "local"
base_path = "~/Documents"
exclude_patterns = [".git"]
```

### Configure models

```toml
[models.embedding]
name = "BAAI/bge-base-en-v1.5"
dimensions = 768
vram_gb = 0.5

[models.llm]
name = "my-local-llm"
model_path = "/path/to/model.gguf"
vram_gb = 8.0
```

### Validate the configuration

```bash
uv run kris config validate
```

## Data Storage

kris stores data in XDG-compliant locations:

| Location | Default Path | Contents |
|----------|-------------|----------|
| Config | `~/.config/kris/` | `config.toml` |
| Data | `~/.local/share/kris/` | `catalog.db` (SQLite), `kris.log` |
| Cache | `~/.cache/kris/` | `qdrant/` (vector store) |

## First Index

```bash
uv run kris index
```

This scans all configured sources, extracts text, chunks content,
and generates embeddings. The first run may take a while depending
on the number of files. Monitor progress with:

```bash
uv run kris status
```

## Troubleshooting

**"Configuration file not found"** — Run `uv run kris init` first.

**"Source ... base_path does not exist"** — Verify the paths in your
config are correct and accessible.

**Scanner binary not found** — Run `just build` to compile the
Rust scanner.

**VRAM errors** — Ensure your GPU has enough VRAM for the configured
models. Reduce `vram_gb` or use a smaller embedding model.

**Log files** — Check `~/.local/share/kris/kris.log` for detailed
diagnostic output. Use `-v` or `-vv` for more console output.
