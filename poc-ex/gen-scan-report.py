"""Generate markdown analysis report from scan database."""

from __future__ import annotations

import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

DB_PATH = "/krag/kris/scan.db"
OUTPUT = Path(__file__).parent.parent / "docs" / "scan-analysis.md"


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def fmt_size(n: int | float | None) -> str:
    if n is None or n == 0:
        return "0 B"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            if unit == "B":
                return f"{int(n):,} {unit}"
            return f"{n:,.1f} {unit}"
        n /= 1024
    return f"{n:,.1f} PB"


def fmt_num(n: int) -> str:
    return f"{n:,}"


def get_extensions(conn, source_id, file_kind=None):
    """Get extension breakdown for a source, optionally filtered by kind."""
    if file_kind:
        rows = conn.execute(
            "SELECT path, size FROM file WHERE source_id = ? AND file_kind = ?",
            (source_id, file_kind),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT path, size FROM file WHERE source_id = ?", (source_id,)
        ).fetchall()

    ext_count: Counter[str] = Counter()
    ext_size: defaultdict[str, int] = defaultdict(int)
    for r in rows:
        p = r["path"]
        dot = p.rfind(".")
        if dot > 0 and dot > p.rfind("/"):
            ext = p[dot:].lower()
        else:
            ext = "(none)"
        ext_count[ext] += 1
        ext_size[ext] += r["size"]
    return ext_count, ext_size


LANG_MAP = {
    ".py": "Python",
    ".rs": "Rust",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".jsx": "React JSX",
    ".tsx": "React TSX",
    ".java": "Java",
    ".c": "C",
    ".cpp": "C++",
    ".h": "C/C++ Header",
    ".hpp": "C++ Header",
    ".go": "Go",
    ".rb": "Ruby",
    ".php": "PHP",
    ".swift": "Swift",
    ".kt": "Kotlin",
    ".scala": "Scala",
    ".cs": "C#",
    ".sh": "Shell",
    ".bash": "Bash",
    ".zsh": "Zsh",
    ".fish": "Fish",
    ".sql": "SQL",
    ".lua": "Lua",
    ".r": "R",
    ".jl": "Julia",
    ".ex": "Elixir",
    ".exs": "Elixir Script",
    ".erl": "Erlang",
    ".hs": "Haskell",
    ".ml": "OCaml",
    ".clj": "Clojure",
    ".vue": "Vue",
    ".svelte": "Svelte",
    ".dart": "Dart",
    ".nim": "Nim",
    ".zig": "Zig",
    ".pl": "Perl",
    ".pm": "Perl Module",
    ".ps1": "PowerShell",
    ".bat": "Batch",
    ".cmd": "Cmd Script",
    ".f90": "Fortran 90",
    ".f95": "Fortran 95",
    ".d": "D",
    ".cu": "CUDA",
}


def generate():
    conn = connect()
    lines: list[str] = []
    w = lines.append

    # ── Header ──
    w("# Scan Analysis Report")
    w("")
    sources = conn.execute("SELECT * FROM source").fetchall()
    scan_dates = [s["last_scan"] for s in sources]
    w(f"**Generated from**: `/krag/kris/scan.db`")
    w(f"**Scan dates**: {', '.join(d or 'n/a' for d in scan_dates)}")
    w(f"**Mode**: `--skip-hash` (metadata-only exploration scan)")
    w("")

    # ── Overview ──
    w("## Overview")
    w("")
    w("| Source | Path | Files | Total Size |")
    w("|--------|------|------:|------------|")
    grand_files = 0
    grand_size = 0
    for s in sources:
        cnt = conn.execute(
            "SELECT COUNT(*) as c, COALESCE(SUM(size),0) as sz FROM file WHERE source_id = ?",
            (s["id"],),
        ).fetchone()
        w(
            f"| {s['name']} (`{s['id']}`) | `{s['base_path']}` | {fmt_num(cnt['c'])} | {fmt_size(cnt['sz'])} |"
        )
        grand_files += cnt["c"]
        grand_size += cnt["sz"]
    w(f"| **Total** | | **{fmt_num(grand_files)}** | **{fmt_size(grand_size)}** |")
    w("")

    # ── Files by Kind ──
    w("## Files by Kind")
    w("")
    for s in sources:
        w(f"### {s['name']} (`{s['base_path']}`)")
        w("")
        total = conn.execute(
            "SELECT COUNT(*) as c, COALESCE(SUM(size),0) as sz FROM file WHERE source_id = ?",
            (s["id"],),
        ).fetchone()
        total_cnt, total_sz = total["c"], total["sz"]

        w("| Kind | Count | % Count | Size | % Size | Avg Size |")
        w("|------|------:|--------:|-----:|-------:|---------:|")
        rows = conn.execute(
            """SELECT file_kind, COUNT(*) as cnt, SUM(size) as sz, AVG(size) as avg
               FROM file WHERE source_id = ? GROUP BY file_kind ORDER BY cnt DESC""",
            (s["id"],),
        ).fetchall()
        for r in rows:
            pc = r["cnt"] / total_cnt * 100 if total_cnt else 0
            ps = r["sz"] / total_sz * 100 if total_sz else 0
            w(
                f"| {r['file_kind']} | {fmt_num(r['cnt'])} | {pc:.1f}% | {fmt_size(r['sz'])} | {ps:.1f}% | {fmt_size(int(r['avg']))} |"
            )
        w("")

    # ── Size Distribution ──
    w("## File Size Distribution")
    w("")
    buckets = [
        ("0 B (empty)", "size = 0"),
        ("1 B – 1 KB", "size >= 1 AND size < 1024"),
        ("1 KB – 10 KB", "size >= 1024 AND size < 10240"),
        ("10 KB – 100 KB", "size >= 10240 AND size < 102400"),
        ("100 KB – 1 MB", "size >= 102400 AND size < 1048576"),
        ("1 MB – 10 MB", "size >= 1048576 AND size < 10485760"),
        ("10 MB – 100 MB", "size >= 10485760 AND size < 104857600"),
        ("100 MB – 1 GB", "size >= 104857600 AND size < 1073741824"),
        ("> 1 GB", "size >= 1073741824"),
    ]
    for s in sources:
        w(f"### {s['name']}")
        w("")
        total_cnt = conn.execute(
            "SELECT COUNT(*) FROM file WHERE source_id = ?", (s["id"],)
        ).fetchone()[0]
        w("| Bucket | Count | % Files |")
        w("|--------|------:|--------:|")
        for label, cond in buckets:
            cnt = conn.execute(
                f"SELECT COUNT(*) FROM file WHERE source_id = ? AND {cond}",
                (s["id"],),
            ).fetchone()[0]
            pc = cnt / total_cnt * 100 if total_cnt else 0
            w(f"| {label} | {fmt_num(cnt)} | {pc:.1f}% |")
        w("")

    # ── All Extensions ──
    w("## All Extensions")
    w("")
    for s in sources:
        w(f"### {s['name']} — All Extensions")
        w("")
        ext_count, ext_size = get_extensions(conn, s["id"])
        w(f"**{len(ext_count)} distinct extensions**, {fmt_num(sum(ext_count.values()))} files")
        w("")
        w("| Extension | Count | Size | Avg Size |")
        w("|-----------|------:|-----:|---------:|")
        for ext, cnt in ext_count.most_common():
            avg = ext_size[ext] // cnt if cnt else 0
            w(f"| `{ext}` | {fmt_num(cnt)} | {fmt_size(ext_size[ext])} | {fmt_size(avg)} |")
        w("")

    # ── Code Language Breakdown ──
    w("## Code Files by Language")
    w("")
    for s in sources:
        w(f"### {s['name']}")
        w("")
        rows = conn.execute(
            "SELECT path, size FROM file WHERE source_id = ? AND file_kind = 'code'",
            (s["id"],),
        ).fetchall()
        lang_count: Counter[str] = Counter()
        lang_size: defaultdict[str, int] = defaultdict(int)
        for r in rows:
            p = r["path"]
            dot = p.rfind(".")
            if dot > 0:
                ext = p[dot:].lower()
                lang = LANG_MAP.get(ext, f"Other (`{ext}`)")
            else:
                lang = "Other (no ext)"
            lang_count[lang] += 1
            lang_size[lang] += r["size"]

        total_code = sum(lang_count.values())
        total_code_sz = sum(lang_size.values())
        w(f"**{fmt_num(total_code)} code files**, {fmt_size(total_code_sz)} total")
        w("")
        w("| Language | Count | % Code | Size | Avg Size |")
        w("|----------|------:|-------:|-----:|---------:|")
        for lang, cnt in lang_count.most_common():
            pc = cnt / total_code * 100 if total_code else 0
            avg = lang_size[lang] // cnt if cnt else 0
            w(
                f"| {lang} | {fmt_num(cnt)} | {pc:.1f}% | {fmt_size(lang_size[lang])} | {fmt_size(avg)} |"
            )
        w("")

    # ── Unknown Kind Breakdown ──
    w("## Unknown Kind — Extension Breakdown")
    w("")
    w("Files classified as `unknown` by the scanner. Many of these are candidates")
    w("for future classifier expansion (e.g., `.html`, `.css`, `.pyi`, `.svg`) or")
    w("represent binary/media formats that will be handled in later phases.")
    w("")
    for s in sources:
        w(f"### {s['name']}")
        w("")
        ext_count, ext_size = get_extensions(conn, s["id"], "unknown")
        w(
            f"**{fmt_num(sum(ext_count.values()))} unknown files** across {len(ext_count)} extensions"
        )
        w("")
        w("| Extension | Count | Size | Avg Size | Notes |")
        w("|-----------|------:|-----:|---------:|-------|")
        # Annotate known types
        notes_map = {
            ".html": "Web content — add to classifier",
            ".htm": "Web content",
            ".css": "Stylesheets — add to classifier",
            ".svg": "Vector graphics",
            ".png": "Image (raster)",
            ".jpg": "Image (raster)",
            ".jpeg": "Image (raster)",
            ".gif": "Image (animated/raster)",
            ".webp": "Image (modern raster)",
            ".ico": "Icon",
            ".bmp": "Image (bitmap)",
            ".tga": "Image (Targa)",
            ".blp": "Image (Blizzard)",
            ".pdf": "Document — future extraction",
            ".doc": "Document — future extraction",
            ".docx": "Document — future extraction",
            ".pyi": "Python type stubs — add to code",
            ".pyx": "Cython — add to code",
            ".pxd": "Cython header",
            ".cmake": "Build config — add to config",
            ".make": "Build config — add to config",
            ".cu": "CUDA — add to code",
            ".cuh": "CUDA header — add to code",
            ".o": "Object file (binary)",
            ".so": "Shared library (binary)",
            ".a": "Static library (binary)",
            ".lib": "Library (binary)",
            ".dll": "Dynamic library (binary)",
            ".exe": "Executable (binary)",
            ".pyc": "Python bytecode",
            ".woff": "Web font",
            ".woff2": "Web font",
            ".ttf": "Font",
            ".otf": "Font",
            ".stl": "3D model — future phase",
            ".step": "3D CAD — future phase",
            ".obj": "3D model — future phase",
            ".fbx": "3D model — future phase",
            ".blend": "Blender — future phase",
            ".ogg": "Audio",
            ".mp3": "Audio",
            ".wav": "Audio",
            ".mp4": "Video",
            ".avi": "Video",
            ".mkv": "Video",
            ".zip": "Archive",
            ".gz": "Archive",
            ".tar": "Archive",
            ".7z": "Archive",
            ".rar": "Archive",
            ".lock": "Lock file",
            ".map": "Source map",
            ".crate": "Cargo package",
            ".whl": "Python wheel",
            ".cel": "Celestia data",
            ".cfa": "Raw image data",
            ".bak": "Backup file",
            ".old": "Backup file",
            ".log": "Log file — add to text",
        }
        for ext, cnt in ext_count.most_common():
            avg = ext_size[ext] // cnt if cnt else 0
            note = notes_map.get(ext, "")
            w(
                f"| `{ext}` | {fmt_num(cnt)} | {fmt_size(ext_size[ext])} | {fmt_size(avg)} | {note} |"
            )
        w("")

    # ── Summary / Takeaways ──
    w("## Key Takeaways")
    w("")

    # Calculate processable corpus
    processable = conn.execute(
        "SELECT COUNT(*) as c, COALESCE(SUM(size),0) as sz FROM file WHERE file_kind IN ('code','markdown','text','config','data')"
    ).fetchone()
    w(
        f"1. **Processable corpus** (code + markdown + text + config + data): "
        f"**{fmt_num(processable['c'])} files / {fmt_size(processable['sz'])}** — very manageable for embedding"
    )
    w("")

    big_files = conn.execute("SELECT COUNT(*) FROM file WHERE size >= 1073741824").fetchone()[0]
    w(
        f"2. **{big_files} files over 1 GB** — all binary/media, would be filtered before processing"
    )
    w("")

    under_100k = conn.execute("SELECT COUNT(*) FROM file WHERE size < 102400").fetchone()[0]
    under_100k_pct = under_100k / grand_files * 100
    w(
        f"3. **{under_100k_pct:.0f}% of files are under 100 KB** — default chunk sizes should work well"
    )
    w("")

    w(
        "4. **Classifier expansion candidates**: `.html`, `.css`, `.pyi`, `.cu`, `.cuh`, `.cmake`, `.make`, `.log`"
    )
    w("   would move ~200K+ files from `unknown` to proper categories")
    w("")

    w("5. **Future media support**: Images (`.png`, `.jpg`, `.tga`, `.blp`) = ~118K files,")
    w("   3D models (`.stl`, `.step`, `.obj`) = ~12K files,")
    w("   documents (`.pdf`) = ~1.4K files — all valuable for later phases")
    w("")

    conn.close()
    return "\n".join(lines)


if __name__ == "__main__":
    md = generate()
    OUTPUT.write_text(md, encoding="utf-8")
    print(f"Wrote {len(md):,} bytes to {OUTPUT}")
