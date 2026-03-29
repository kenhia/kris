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
| Cache | `~/.cache/kris/` | Model caches, temporary files |

## Default Exclude Patterns

kris ships with a built-in list of exclude patterns that filter common
non-content directories and files during scanning. These include `.git`,
`node_modules`, `__pycache__`, `target/`, `*.pyc`, `.DS_Store`, and many
more (33 patterns total covering VCS, Python, Node.js, Rust, IDE, and
build artifacts).

To **opt out** of default excludes for a specific source:

```toml
[sources.my-code]
include_default_exclude_patterns = false
exclude_patterns = [".git"]
```

To see the effective exclude list for each source:

```bash
uv run kris config validate
```

## OpenSearch Setup

kris uses OpenSearch for vector search (k-NN). You need a running
OpenSearch instance (2.x with k-NN plugin).

### Start OpenSearch via Docker Compose

```bash
# See https://opensearch.org/docs/latest/install-and-configure/install-opensearch/docker/
docker compose -f ~/opensearch/docker-compose.yml up -d
```

### Configure kris to connect

```toml
[opensearch]
url = "https://localhost:9200"
username = "admin"
password = "your-password"
verify_certs = false   # set true if using proper TLS certificates
index_prefix = "kris"  # creates kris_chunks index
```

The password can also be set via the `KRIS_OPENSEARCH_PASSWORD`
environment variable (useful for CI or secrets management).

### Verify the connection

```bash
uv run kris config validate
```

This checks configuration syntax and tests OpenSearch connectivity,
reporting cluster health, index status, and document count.

---

## Migrating from Qdrant to OpenSearch

If you have an existing kris installation using Qdrant, follow these
steps to migrate to OpenSearch:

### Prerequisites

- OpenSearch 2.x running and accessible
- Existing kris installation with indexed content

### Migration Steps

1. **Update your config.toml** — Replace the `[qdrant]` section with
   `[opensearch]`:

   ```toml
   # Remove this:
   # [qdrant]
   # mode = "embedded"

   # Add this:
   [opensearch]
   url = "https://localhost:9200"
   username = "admin"
   password = "your-password"
   verify_certs = false
   index_prefix = "kris"
   ```

2. **Validate configuration**:

   ```bash
   uv run kris config validate
   ```

3. **Re-index all content** — This re-embeds all content into OpenSearch:

   ```bash
   uv run kris index
   ```

   Existing SQLite catalog data (files, chunks) is preserved. Only
   the vector embeddings are regenerated in OpenSearch.

4. **Verify the migration**:

   ```bash
   uv run kris status
   uv run kris diagnose
   uv run kris retrieve "test query"
   ```

5. **Clean up** — Once verified, you can safely remove the old Qdrant
   data directory (`~/.cache/kris/qdrant/`) and the `[qdrant]` config
   section if still present.

## VRAM Calibration

Measure actual GPU VRAM usage for your models and update the config:

```bash
uv run kris config update-model-sizes
```

This loads each model onto the GPU, measures VRAM consumption, and
writes the results back to `config.toml` (preserving comments).

Preview without modifying config:

```bash
uv run kris config update-model-sizes --dry-run
```

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

## GPU Setup

### Embedding model

The embedding model (sentence-transformers) uses CUDA automatically
when PyTorch is installed with CUDA support. No extra steps needed
if `torch.cuda.is_available()` returns `True`.

### LLM inference

`llama-cpp-python` must be built with CUDA support for GPU-accelerated
LLM inference. The default pip/uv install is CPU-only. Rebuild with:

```bash
CMAKE_ARGS="-DGGML_CUDA=on" uv pip install llama-cpp-python --force-reinstall --no-cache-dir
```

Verify GPU offloading by checking the log output during `kris query` —
you should see all model layers offloaded to CUDA and a `CUDA0` model
buffer allocation.

---

## Troubleshooting

**"Configuration file not found"** — Run `uv run kris init` first.

**"Source ... base_path does not exist"** — Verify the paths in your
config are correct and accessible.

**Scanner binary not found** — Run `just build` to compile the
Rust scanner.

**VRAM errors** — Ensure your GPU has enough VRAM for the configured
models. Reduce `vram_gb` or use a smaller embedding model.

**LLM running on CPU** — If `kris query` is slow and logs show
`n_gpu_layers=0`, `llama-cpp-python` was installed without CUDA.
See the GPU Setup section above.

**Log files** — Check `~/.local/share/kris/kris.log` for detailed
diagnostic output. Use `-v` or `-vv` for more console output.
