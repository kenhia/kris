use rusqlite::{Connection, params};
use std::time::SystemTime;

use crate::classify::FileKind;

/// Upsert a file record into the catalog.
/// Returns true if this is a new or changed file (content_hash differs).
#[allow(clippy::too_many_arguments)]
pub fn upsert_file(
    conn: &Connection,
    source_id: &str,
    path: &str,
    content_hash: &str,
    size: i64,
    mtime: i64,
    file_kind: &FileKind,
    mime_type: Option<&str>,
    permissions: Option<i32>,
) -> rusqlite::Result<bool> {
    // Check if file already exists with same content_hash
    let existing_hash: Option<String> = conn
        .query_row(
            "SELECT content_hash FROM file WHERE source_id = ? AND path = ?",
            params![source_id, path],
            |row| row.get(0),
        )
        .ok();

    let is_changed = existing_hash.as_deref() != Some(content_hash);
    let file_id = uuid_v4();
    let processing_status = if is_changed { "pending" } else { "completed" };

    conn.execute(
        "INSERT INTO file
         (id, source_id, content_hash, path, size, mtime, file_kind,
          mime_type, processing_status, visibility, last_seen, permissions)
         VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, 'active', datetime('now'), ?10)
         ON CONFLICT(source_id, path) DO UPDATE SET
             content_hash = excluded.content_hash,
             size = excluded.size,
             mtime = excluded.mtime,
             file_kind = excluded.file_kind,
             mime_type = excluded.mime_type,
             processing_status = CASE
                 WHEN file.content_hash != excluded.content_hash THEN 'pending'
                 ELSE file.processing_status
             END,
             visibility = 'active',
             last_seen = datetime('now'),
             permissions = excluded.permissions",
        params![
            file_id,
            source_id,
            content_hash,
            path,
            size,
            mtime,
            file_kind.as_str(),
            mime_type,
            processing_status,
            permissions,
        ],
    )?;

    Ok(is_changed)
}

/// Insert a content record if it doesn't exist.
pub fn insert_content_if_not_exists(conn: &Connection, content_hash: &str) -> rusqlite::Result<()> {
    conn.execute(
        "INSERT OR IGNORE INTO content (content_hash, processing_status) VALUES (?1, 'pending')",
        params![content_hash],
    )?;
    Ok(())
}

/// Mark files not seen in this scan as 'missing'.
pub fn mark_unseen_files_missing(
    conn: &Connection,
    source_id: &str,
    scan_start: &str,
) -> rusqlite::Result<usize> {
    let count = conn.execute(
        "UPDATE file SET visibility = 'missing', disappeared_at = datetime('now')
         WHERE source_id = ? AND visibility = 'active' AND last_seen < ?",
        params![source_id, scan_start],
    )?;
    Ok(count)
}

/// Update the source's last_scan timestamp.
pub fn update_source_last_scan(conn: &Connection, source_id: &str) -> rusqlite::Result<()> {
    conn.execute(
        "UPDATE source SET last_scan = datetime('now') WHERE id = ?",
        params![source_id],
    )?;
    Ok(())
}

fn uuid_v4() -> String {
    // Simple UUID v4 generation without extra dependency
    use std::collections::hash_map::DefaultHasher;
    use std::hash::{Hash, Hasher};

    let now = SystemTime::now()
        .duration_since(SystemTime::UNIX_EPOCH)
        .unwrap_or_default();

    let mut hasher = DefaultHasher::new();
    now.as_nanos().hash(&mut hasher);
    std::thread::current().id().hash(&mut hasher);
    let h1 = hasher.finish();

    // Second hash with different seed
    let mut hasher2 = DefaultHasher::new();
    h1.hash(&mut hasher2);
    now.as_secs()
        .wrapping_mul(6364136223846793005)
        .hash(&mut hasher2);
    let h2 = hasher2.finish();

    format!(
        "{:08x}-{:04x}-4{:03x}-{:04x}-{:012x}",
        (h1 >> 32) as u32,
        (h1 >> 16) as u16,
        h1 as u16 & 0x0FFF,
        (h2 >> 48) as u16 & 0x3FFF | 0x8000,
        h2 & 0xFFFFFFFFFFFF,
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::classify::FileKind;

    fn setup_db() -> Connection {
        let conn = Connection::open_in_memory().unwrap();
        conn.execute_batch(
            "PRAGMA journal_mode = WAL;
             PRAGMA foreign_keys = ON;

             CREATE TABLE source (
                 id TEXT PRIMARY KEY,
                 name TEXT NOT NULL,
                 source_type TEXT NOT NULL DEFAULT 'local',
                 base_path TEXT NOT NULL,
                 config TEXT,
                 last_scan TEXT,
                 created_at TEXT NOT NULL DEFAULT (datetime('now'))
             );

             CREATE TABLE file (
                 id TEXT PRIMARY KEY,
                 source_id TEXT NOT NULL REFERENCES source(id),
                 content_hash TEXT NOT NULL,
                 path TEXT NOT NULL,
                 size INTEGER NOT NULL,
                 mtime INTEGER NOT NULL,
                 file_kind TEXT NOT NULL,
                 mime_type TEXT,
                 processing_status TEXT NOT NULL DEFAULT 'pending',
                 visibility TEXT NOT NULL DEFAULT 'active',
                 first_seen TEXT NOT NULL DEFAULT (datetime('now')),
                 last_seen TEXT NOT NULL DEFAULT (datetime('now')),
                 disappeared_at TEXT,
                 permissions INTEGER,
                 UNIQUE(source_id, path)
             );

             CREATE TABLE content (
                 content_hash TEXT PRIMARY KEY,
                 parent_content_hash TEXT,
                 processing_status TEXT NOT NULL DEFAULT 'pending',
                 last_processed TEXT
             );

             INSERT INTO source (id, name, base_path) VALUES ('src1', 'Test', '/tmp/test');",
        )
        .unwrap();
        conn
    }

    #[test]
    fn test_upsert_new_file() {
        let conn = setup_db();
        let changed = upsert_file(
            &conn,
            "src1",
            "/tmp/test/a.txt",
            "hash_a",
            100,
            1700000000,
            &FileKind::Text,
            Some("text/plain"),
            None,
        )
        .unwrap();
        assert!(changed);

        let count: i64 = conn
            .query_row("SELECT COUNT(*) FROM file", [], |r| r.get(0))
            .unwrap();
        assert_eq!(count, 1);
    }

    #[test]
    fn test_upsert_same_hash_not_changed() {
        let conn = setup_db();
        upsert_file(
            &conn,
            "src1",
            "/tmp/test/a.txt",
            "hash_a",
            100,
            1700000000,
            &FileKind::Text,
            None,
            None,
        )
        .unwrap();
        let changed = upsert_file(
            &conn,
            "src1",
            "/tmp/test/a.txt",
            "hash_a",
            100,
            1700000000,
            &FileKind::Text,
            None,
            None,
        )
        .unwrap();
        assert!(!changed);
    }

    #[test]
    fn test_upsert_changed_hash() {
        let conn = setup_db();
        upsert_file(
            &conn,
            "src1",
            "/tmp/test/a.txt",
            "hash_a",
            100,
            1700000000,
            &FileKind::Text,
            None,
            None,
        )
        .unwrap();
        let changed = upsert_file(
            &conn,
            "src1",
            "/tmp/test/a.txt",
            "hash_b",
            200,
            1700000001,
            &FileKind::Text,
            None,
            None,
        )
        .unwrap();
        assert!(changed);

        let status: String = conn
            .query_row(
                "SELECT processing_status FROM file WHERE source_id = 'src1' AND path = '/tmp/test/a.txt'",
                [],
                |r| r.get(0),
            )
            .unwrap();
        assert_eq!(status, "pending");
    }

    #[test]
    fn test_insert_content_if_not_exists() {
        let conn = setup_db();
        insert_content_if_not_exists(&conn, "hash_a").unwrap();
        insert_content_if_not_exists(&conn, "hash_a").unwrap(); // no error on duplicate

        let count: i64 = conn
            .query_row("SELECT COUNT(*) FROM content", [], |r| r.get(0))
            .unwrap();
        assert_eq!(count, 1);
    }

    #[test]
    fn test_mark_unseen_files_missing() {
        let conn = setup_db();
        upsert_file(
            &conn,
            "src1",
            "/tmp/test/old.txt",
            "hash_old",
            50,
            1700000000,
            &FileKind::Text,
            None,
            None,
        )
        .unwrap();

        // Simulate a new scan that doesn't see old.txt
        let scan_start = "2099-01-01T00:00:00";
        let count = mark_unseen_files_missing(&conn, "src1", scan_start).unwrap();
        assert_eq!(count, 1);

        let vis: String = conn
            .query_row(
                "SELECT visibility FROM file WHERE path = '/tmp/test/old.txt'",
                [],
                |r| r.get(0),
            )
            .unwrap();
        assert_eq!(vis, "missing");
    }
}
