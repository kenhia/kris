# kris — Clarifications Needed

Open questions and decisions that need input before finalizing architecture and beginning implementation. Grouped by topic area.

---

## Scanner & Collection

### Q1: Scanner Language
The architecture proposes Rust for the scanner/agent. Confirm this is the direction, or would you prefer to start with Python for faster iteration and port to Rust later?

**Trade-offs:**
- **Rust now**: Better performance on large directory trees, single binary for remote agents, lower memory. Higher initial investment.
- **Python now, Rust later**: Faster to prototype, but you'd be rewriting a core component. The scanner interface is clean enough that a rewrite wouldn't cascade.

#### A1: Rust
Rust as initial language for scanner; if POC/exploration is needed that *can* be in Python.

### Q2: Remote Source Strategy
For other Linux machines, which model do you prefer?

- **Agent mode**: A small daemon runs on each remote host, scans locally, pushes manifests to the hub. Requires installing software on each remote machine.
- **Pull mode**: The hub SSHs into remote hosts and runs a scan command. Nothing to install on remote machines, but requires SSH access and the scan binary present or transferable.
- **Hybrid**: Support both, choose per source.
- **Defer**: Skip remote sources entirely for now, design the interface, implement local-only MVP.

#### A2: Agent Mode
Should be able to use as daemon or via cron. If/when Windows clients are added, the agent will likely run via scheduled tasks.

### Q3: NAS Access Pattern
How is your NAS currently mounted? This affects the scanner approach:

- **NFS/SMB mount**: Appears as local filesystem — local scanner works directly
- **Not mounted**: Would need a protocol-specific scanner or an agent on the NAS
- **Synology/QNAP with SSH**: Could run an agent on the NAS itself

#### A3: NAS is mounted as a local filesystem
Mount point for NAS is `/gratch`

### Q4: Filesystem Watching
Do you want real-time file change detection (inotify/fanotify) in the MVP, or is periodic scanning sufficient?

- Real-time adds complexity (especially for large directory trees — inotify has watch limits)
- Periodic scanning is simpler and covers the "run indexing when I want" use case
- A background daemon with periodic scanning is a middle ground

#### A4: No real-time file change detection
Note: Scanning should be schedulable with different priorities for different configured paths (e.g. code more often than pictures)

---

## Processing & Models

### Q5: Embedding Model Selection
krag defaults to `BAAI/bge-base-en-v1.5` (768 dimensions). Are you happy with this for the initial model, or do you have a preferred embedding model?

Considerations:
- Dimension size (768 vs 1024 vs 1536) affects storage and search speed
- Some models are better for code (e.g., jina code embeddings)
- Once you embed with a model, changing requires re-embedding everything

#### A5: MVP can focus on single model, but...
...like in krag, we will want to (soon!) support multiple embedding models (likely more than the two krag uses). All model selections should be configurable, likely with model specific prompts/templates. We should make sure this is expressed in the architecture from the start even if the MVP does not fully implement this.


### Q6: LLM for Synthesis/Summarization
Which LLM(s) do you plan to use for synthesis and summarization tasks? Local GGUF models via llama-cpp, or remote APIs, or both?

This affects:
- VRAM budget planning
- Model manager complexity
- Whether tasks can run in parallel (remote API) vs. sequentially (local GPU)

#### A6: We should plan for both in the architecture
While I would *like* to keep the processing all local, we may find that particular tasks like summarization don't generate enough quality locally. I am not concerned with the processing time if we can stay local, but I do want to get quality.

Bottom line, remote is "if absolutely necessary" and I'm willing to spend time trying to find right model and configuration to achieve locally even at the expense of performance.

### Q7: Vision Model for Image Captioning
Do you want image captioning in the near term? If so, which approach:

- **Local vision model** (e.g., LLaVA, Qwen-VL) — requires significant VRAM
- **Deferred** — index images by filename/EXIF metadata only, add captioning later
- **Lightweight local** (e.g., BLIP-2) — smaller VRAM footprint, less capable

#### A7: Not for MVP, but soon.
This was the next logical step for `krag` and what I had planned on pursuing next until I pivoted to this project. This is an area where some POC/exploration will show viability.

### Q8: GPU/VRAM Budget
What GPU hardware are you working with? This drives decisions about:
- How many models can be loaded simultaneously
- Whether hot-swap or simultaneous mode is feasible
- Batch sizes for embedding

#### A7: NVIDIA 4090 Super with 16GB

---

## Storage & Data

### Q9: Duplicate File Handling
Files may exist on multiple sources (e.g., same repo on local machine and dev server). How should this be handled?

- **Index independently**: Each source's copy is indexed separately. Simple, but wastes storage.
- **Content-addressed dedup**: Files with the same content_hash share chunks/embeddings. More complex, saves storage.
- **Source-primary**: Designate one source as primary, others are "awareness only" (catalog entry, no processing).

#### A9: Content-addressed dedup
One of the things I want as a user for this project is to be able to identify duplicates so I can decide if they should be cleanted up.

### Q10: What Data to Index
Which types of content matter most to you? This helps prioritize pipeline development:

- [1] Source code repositories
- [2] Personal notes / documents (Obsidian, markdown)
- [4] Configuration files
- [3] Images / photos
- [5] PDFs
- [5] Email archives
- [5] Chat/message exports
- [6] Media files (audio/video metadata)
- [5] Any text file not already covered
- [5] Metadata for all other files, binaries, etc. (allow locate by name, get size, etc.)

#### A10: Added priority to above (1-highest priority)

### Q11: File Size Limits
krag skips files over a configurable limit. What's a reasonable max file size for your data?
- Text/code: 10 MB? 50 MB?
- Images: Process all? Cap at certain resolution?
- Default suggestion: 100 MB text, all images regardless of size

#### A12: Agree with your recommendation
Metadata should always be recorded. Should be able to query database to find "skipped for size" and force by processing pipeline (i.e. queue for "Summarization")

### Q12: Data Retention on Deletion
When a file is no longer seen by the scanner (deleted or moved):

- **Immediate removal**: Delete all artifacts (chunks, embeddings, summaries) immediately
- **Grace period**: Mark as "missing," remove artifacts after N days (handles temporary unmounts)
- **Archive**: Keep artifacts permanently, mark as "deleted source" (searchable but flagged)

#### A12: Archive
Keep "permanently" but allow for tooling that can clean up using selectors (path, path as regex, "all")

---

## Architecture & Design

### Q13: Monorepo vs. Multi-Repo
Should kris be a single repository, or should the scanner (Rust) and processing engine (Python) live in separate repos?

- **Monorepo**: Easier to keep schemas in sync, single CI, simpler development
- **Multi-repo**: Cleaner separation, independent release cycles, language-specific tooling

#### A13: Monorepo with clear directory separation
May pivot to multiple repos in the future, but I find it easier to get moving in a monorepo.

### Q14: Communication Between Scanner and Core
If the scanner is in Rust and the core is in Python, how should they communicate?

- **File-based**: Scanner writes JSON/MessagePack manifests to a known location, Python reads them
- **Unix socket / named pipe**: Direct IPC, lower latency
- **SQLite**: Scanner writes directly to the catalog database (both Rust and Python have excellent SQLite support)
- **gRPC / HTTP**: More formal API, overkill for single-machine?

Recommendation: **SQLite** — the scanner writes FileRecords directly to the catalog. Simple, atomic, no serialization format to maintain, both languages have battle-tested SQLite libraries.

#### A14: Agree with recommendation; SQLite

### Q15: Background Processing Model
How should processing run?

- **On-demand CLI**: `kris index` runs, processes, exits (like krag today)
- **Background daemon**: Always running, processes new files as they appear
- **Hybrid**: Daemon for scanning/detection, CLI triggers for heavy processing
- **Systemd service**: Managed by systemd with timer units for periodic scanning

#### A15: On-demand CLI
Note: we *will* want to shift to **Hybrid** at some point in the future.

### Q16: Query Interface Priority
Which query interfaces matter most for the MVP?

- [1] CLI (interactive terminal)
- [2] HTTP API (for integration with other tools)
- [5] TUI (terminal UI with browsing)
- [4] Editor integration (VS Code, Neovim)
- [3] Web UI

#### A17: Marked with priority (1-highest)
Note: once we have 2, we have a relatively easy path to modifying `krager` from `krag` repo to suit this project (probably a fresh re-write, but many of the issues have already been solved). As I do development on `kubs0` (this development machine) via ssh, having a `krager` like tool relatively early is a big win for me.

---

## Scope & Priorities

### Q17: What Does "Personal Data Intelligence" Mean to You?
This helps calibrate the ambition level:

- **Search**: "I need to find that file/snippet/note I wrote about X"
- **Analysis**: "Summarize what I worked on this week across all my projects"
- **Knowledge base**: "Answer questions using my accumulated notes and code as context"
- **Curation**: "Help me organize, tag, and deduplicate my data"
- **All of the above**, prioritized in order: ___

#### A17: All of the above
I already have a working "Knowledge base" with `krag`, so while this will replace `krag`, the highest priority would be "Search", but I can solve that need for now with an Open Source solution. I think from an implementation standpoint, the priority should be:

1. Knowledge Base
2. Analysis
3. Search
4. Curation

I am particularly interested, as we move further towards the complete project, in using the various items together, for example, using both semantic and full-text search (OpenSearch k-NN and BM25) together to enhance the quality of responses.

### Q18: Scale Expectations
Rough order of magnitude for your data:

- Number of files across all sources: thousands? tens of thousands? hundreds of thousands?
- Total data size: GBs? TBs?
- Rate of change: files per day that are new/modified?

This affects decisions about batching, incremental strategies, and storage sizing.

#### A18: rough numbers below

- Number of files across all sources: hundreds of thousands, possibly 1-2 million.
    - Note: As noted elsewhere, I will want to do selective scanning (e.g. source code often, images once a week)
- Total data size: some percentage of ~8GB; of that I would be surprised if more than about 30-40% were files that we would process beyond storing metadata.
- Rate of change: low, likely below a couple hundred most days

I am not concerned about "day zero scan". I expect that to take several days or even a couple weeks. Once that scan is complete, I would expect the number of files changed for incremental scans to be such that a nightly scan and processing time of a couple hours would be sufficient.

### Q19: krag Coexistence
Should kris replace krag, coexist alongside it, or absorb krag's functionality over time?

- **Replace**: krag is deprecated once kris reaches feature parity
- **Coexist**: They serve different purposes (krag for quick project-scoped RAG, kris for cross-source intelligence)
- **Absorb**: kris eventually incorporates krag as a "mode" or subsystem

#### A19: `kris` will eventually replace `krag`
I learned a lot building `krag`, `kris` is the "lessons learned and expand" next generation.

---

## Decision Log

Track decisions as they're made. This becomes a living record.

| ID | Decision | Date | Rationale |
|----|----------|------|-----------|
| D1 | Rust for scanner/agent | 2026-03-19 | Performance, single binary for remote deployment (A1) |
| D2 | Agent mode for remote sources (daemon or cron) | 2026-03-19 | Runs on remote host, pushes manifests; future Windows support via scheduled tasks (A2) |
| D3 | NAS via local mount at `/gratch` | 2026-03-19 | Already mounted, no special scanner needed (A3) |
| D4 | No real-time file watching; scheduled periodic scans | 2026-03-19 | Simpler, sufficient for change rate; per-path scan priority/schedule (A4) |
| D5 | Single embedding model MVP, multi-model architecture | 2026-03-19 | Design for N models from start; model-specific prompts/templates configurable (A5) |
| D6 | Local-first LLMs, remote API as quality fallback | 2026-03-19 | Willing to trade performance for local operation; remote only if quality insufficient (A6) |
| D7 | Image captioning deferred past MVP | 2026-03-19 | Needs POC/exploration; was next step for krag (A7) |
| D8 | NVIDIA 4090 Super, 16 GB VRAM | 2026-03-19 | Drives model loading strategy and VRAM budgeting (A8) |
| D9 | Content-addressed dedup | 2026-03-19 | Identical files share artifacts; enables duplicate detection as user feature (A9) |
| D10 | Content priority: code > notes > images > config > everything else | 2026-03-19 | Drives pipeline development order (A10) |
| D11 | 100 MB size limit; metadata always recorded; force-queue for skipped | 2026-03-19 | Skipped files still cataloged; users can force specific pipelines (A11) |
| D12 | Archive on deletion, never auto-delete | 2026-03-19 | User-initiated cleanup via selectors (path, regex, all) (A12) |
| D13 | Monorepo with clear directory separation | 2026-03-19 | Easier to keep schemas in sync; may split later (A13) |
| D14 | SQLite for scanner↔core IPC | 2026-03-19 | Scanner writes directly to catalog DB; both languages have excellent SQLite libraries (A14) |
| D15 | On-demand CLI initially, hybrid daemon later | 2026-03-19 | Start simple; design for future daemon mode (A15) |
| D16 | Query priority: CLI → HTTP API → Web UI → Editor → TUI | 2026-03-19 | HTTP API enables krager-like tool relatively early (A16) |
| D17 | Intelligence priority: KB → Analysis → Search → Curation | 2026-03-19 | Working KB in krag; search solvable with OSS short-term (A17) |
| D18 | Scale: ~1-2M files, ~8 TB, low daily churn | 2026-03-19 | Day-zero scan expected to take days/weeks; nightly incremental sufficient after (A18) |
| D19 | kris replaces krag long-term | 2026-03-19 | Lessons learned + expanded scope = next generation (A19) |
