"""Scan database analysis — magnitude estimation for kris.

Reads /krag/kris/scan.db and produces a breakdown of scanned files
by source, kind, extension, and size distribution.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = "/krag/kris/scan.db"


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def fmt_size(n: int | None) -> str:
    """Human-readable size."""
    if n is None or n == 0:
        return "0 B"

    size: int = n  # type narrowing for mypy/ty

    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024:
            return f"{size:,.1f} {unit}"
        size /= 1024
    return f"{size:,.1f} PB"


def fmt_num(n: int) -> str:
    return f"{n:,}"


def section(title: str):
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


def overview(conn: sqlite3.Connection):
    section("SCAN OVERVIEW")
    for r in conn.execute("SELECT id, name, base_path, last_scan FROM source").fetchall():
        print(f"  Source: {r['name']} ({r['id']})")
        print(f"    Path:      {r['base_path']}")
        print(f"    Scanned:   {r['last_scan']}")
        cnt = conn.execute(
            "SELECT COUNT(*) as c, SUM(size) as s FROM file WHERE source_id = ?",
            (r["id"],),
        ).fetchone()
        print(f"    Files:     {fmt_num(cnt['c'])}")
        print(f"    Total:     {fmt_size(cnt['s'])}")
        print()

    total = conn.execute("SELECT COUNT(*) as c, SUM(size) as s FROM file").fetchone()
    print(f"  TOTAL: {fmt_num(total['c'])} files, {fmt_size(total['s'])}")


def by_kind(conn: sqlite3.Connection):
    section("FILES BY KIND")
    for source in ("home", "gratch"):
        src = conn.execute("SELECT name FROM source WHERE id = ?", (source,)).fetchone()
        print(f"\n  --- {src['name']} ({source}) ---")
        print(
            f"  {'Kind':<12} {'Count':>10} {'Size':>12} {'Avg Size':>10} {'% Count':>8} {'% Size':>8}"
        )
        print(f"  {'-' * 12} {'-' * 10} {'-' * 12} {'-' * 10} {'-' * 8} {'-' * 8}")

        total = conn.execute(
            "SELECT COUNT(*) as c, SUM(size) as s FROM file WHERE source_id = ?",
            (source,),
        ).fetchone()
        total_cnt, total_size = total["c"], total["s"]

        rows = conn.execute(
            """SELECT file_kind, COUNT(*) as cnt, SUM(size) as total_size,
                      AVG(size) as avg_size
               FROM file WHERE source_id = ?
               GROUP BY file_kind ORDER BY cnt DESC""",
            (source,),
        ).fetchall()
        for r in rows:
            pct_cnt = r["cnt"] / total_cnt * 100 if total_cnt else 0
            pct_size = r["total_size"] / total_size * 100 if total_size else 0
            print(
                f"  {r['file_kind']:<12} {fmt_num(r['cnt']):>10} "
                f"{fmt_size(r['total_size']):>12} {fmt_size(int(r['avg_size'])):>10} "
                f"{pct_cnt:>7.1f}% {pct_size:>7.1f}%"
            )


def top_extensions(conn: sqlite3.Connection, top_n: int = 25):
    section(f"TOP {top_n} EXTENSIONS BY COUNT")
    for source in ("home", "gratch"):
        src = conn.execute("SELECT name FROM source WHERE id = ?", (source,)).fetchone()
        print(f"\n  --- {src['name']} ({source}) ---")
        print(f"  {'Extension':<16} {'Count':>10} {'Size':>12} {'Avg Size':>10}")
        print(f"  {'-' * 16} {'-' * 10} {'-' * 12} {'-' * 10}")

        rows = conn.execute(
            """SELECT
                 CASE
                   WHEN path LIKE '%.%'
                   THEN '.' || LOWER(SUBSTR(path, LENGTH(path) - INSTR(SUBSTR(path, 1), '.') + 2))
                   ELSE '(none)'
                 END as ext,
                 COUNT(*) as cnt, SUM(size) as total_size, AVG(size) as avg_size
               FROM file WHERE source_id = ?
               GROUP BY ext ORDER BY cnt DESC LIMIT ?""",
            (source, top_n),
        ).fetchall()

        # The SQL for extension extraction without REVERSE is tricky.
        # Let's use a simpler Python approach.
        rows = conn.execute(
            "SELECT path, size FROM file WHERE source_id = ?", (source,)
        ).fetchall()

        from collections import Counter, defaultdict

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

        for ext, cnt in ext_count.most_common(top_n):
            avg = ext_size[ext] // cnt if cnt else 0
            print(
                f"  {ext:<16} {fmt_num(cnt):>10} {fmt_size(ext_size[ext]):>12} {fmt_size(avg):>10}"
            )


def size_distribution(conn: sqlite3.Connection):
    section("FILE SIZE DISTRIBUTION")
    buckets = [
        ("0 B (empty)", 0, 0),
        ("1 B - 1 KB", 1, 1024),
        ("1 KB - 10 KB", 1024, 10 * 1024),
        ("10 KB - 100 KB", 10 * 1024, 100 * 1024),
        ("100 KB - 1 MB", 100 * 1024, 1024 * 1024),
        ("1 MB - 10 MB", 1024 * 1024, 10 * 1024 * 1024),
        ("10 MB - 100 MB", 10 * 1024 * 1024, 100 * 1024 * 1024),
        ("100 MB - 1 GB", 100 * 1024 * 1024, 1024 * 1024 * 1024),
        ("> 1 GB", 1024 * 1024 * 1024, None),
    ]

    for source in ("home", "gratch"):
        src = conn.execute("SELECT name FROM source WHERE id = ?", (source,)).fetchone()
        total = conn.execute(
            "SELECT COUNT(*) as c FROM file WHERE source_id = ?", (source,)
        ).fetchone()["c"]

        print(f"\n  --- {src['name']} ({source}) ---")
        print(f"  {'Bucket':<18} {'Count':>10} {'% Files':>8}  {'Bar'}")
        print(f"  {'-' * 18} {'-' * 10} {'-' * 8}  {'-' * 30}")

        for label, lo, hi in buckets:
            if hi is None:
                row = conn.execute(
                    "SELECT COUNT(*) as c FROM file WHERE source_id = ? AND size >= ?",
                    (source, lo),
                ).fetchone()
            elif lo == 0 and hi == 0:
                row = conn.execute(
                    "SELECT COUNT(*) as c FROM file WHERE source_id = ? AND size = 0",
                    (source,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) as c FROM file WHERE source_id = ? AND size >= ? AND size < ?",
                    (source, lo, hi),
                ).fetchone()
            cnt = row["c"]
            pct = cnt / total * 100 if total else 0
            bar = "#" * int(pct / 2)
            print(f"  {label:<18} {fmt_num(cnt):>10} {pct:>7.1f}%  {bar}")


def code_language_breakdown(conn: sqlite3.Connection):
    section("CODE FILES BY LANGUAGE")

    lang_map = {
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
    }

    for source in ("home", "gratch"):
        src = conn.execute("SELECT name FROM source WHERE id = ?", (source,)).fetchone()
        print(f"\n  --- {src['name']} ({source}) ---")
        print(f"  {'Language':<16} {'Count':>10} {'Size':>12} {'Avg Size':>10}")
        print(f"  {'-' * 16} {'-' * 10} {'-' * 12} {'-' * 10}")

        rows = conn.execute(
            "SELECT path, size FROM file WHERE source_id = ? AND file_kind = 'code'",
            (source,),
        ).fetchall()

        from collections import Counter, defaultdict

        lang_count: Counter[str] = Counter()
        lang_size: defaultdict[str, int] = defaultdict(int)
        for r in rows:
            p = r["path"]
            dot = p.rfind(".")
            if dot > 0:
                ext = p[dot:].lower()
                lang = lang_map.get(ext, f"Other ({ext})")
            else:
                lang = "Other (no ext)"
            lang_count[lang] += 1
            lang_size[lang] += r["size"]

        for lang, cnt in lang_count.most_common(30):
            avg = lang_size[lang] // cnt if cnt else 0
            print(
                f"  {lang:<16} {fmt_num(cnt):>10} "
                f"{fmt_size(lang_size[lang]):>12} {fmt_size(avg):>10}"
            )


def unknown_extensions(conn: sqlite3.Connection, top_n: int = 25):
    section(f"TOP {top_n} 'UNKNOWN' FILE EXTENSIONS (not text/code/md/config/data)")
    for source in ("home", "gratch"):
        src = conn.execute("SELECT name FROM source WHERE id = ?", (source,)).fetchone()
        print(f"\n  --- {src['name']} ({source}) ---")
        print(f"  {'Extension':<16} {'Count':>10} {'Size':>12}")
        print(f"  {'-' * 16} {'-' * 10} {'-' * 12}")

        rows = conn.execute(
            "SELECT path, size FROM file WHERE source_id = ? AND file_kind = 'unknown'",
            (source,),
        ).fetchall()

        from collections import Counter, defaultdict

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

        for ext, cnt in ext_count.most_common(top_n):
            print(f"  {ext:<16} {fmt_num(cnt):>10} {fmt_size(ext_size[ext]):>12}")


def main():
    conn = connect()
    overview(conn)
    by_kind(conn)
    size_distribution(conn)
    top_extensions(conn)
    code_language_breakdown(conn)
    unknown_extensions(conn)
    conn.close()


if __name__ == "__main__":
    main()
