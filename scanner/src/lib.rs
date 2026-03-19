pub mod catalog;
pub mod classify;
pub mod hash;
pub mod walk;

use rusqlite::Connection;
use std::fs;
use std::path::Path;

/// Scan result stats returned after a scan completes.
#[derive(Debug, serde::Serialize)]
pub struct ScanResult {
    pub files_found: usize,
    pub files_new: usize,
    pub files_changed: usize,
    pub files_unchanged: usize,
    pub files_missing: usize,
    pub errors: usize,
}

/// Run the scanner: walk → classify → hash → catalog.
pub fn scan(
    db_path: &Path,
    source_id: &str,
    base_path: &Path,
    exclude_patterns: &[String],
    follow_symlinks: bool,
) -> Result<ScanResult, Box<dyn std::error::Error>> {
    let conn = Connection::open(db_path)?;
    conn.execute_batch(
        "PRAGMA journal_mode = WAL; PRAGMA busy_timeout = 5000; PRAGMA foreign_keys = ON;",
    )?;

    let scan_start = chrono_now();

    let paths = walk::walk_directory(base_path, exclude_patterns, follow_symlinks);

    let mut files_new = 0usize;
    let mut files_unchanged = 0usize;
    let mut errors = 0usize;

    for path in &paths {
        let rel_path = path
            .strip_prefix(base_path)
            .unwrap_or(path)
            .to_string_lossy()
            .to_string();

        let metadata = match fs::metadata(path) {
            Ok(m) => m,
            Err(e) => {
                eprintln!("metadata error for {}: {}", path.display(), e);
                errors += 1;
                continue;
            }
        };

        let content_hash = match hash::sha256_file(path) {
            Ok(h) => h,
            Err(e) => {
                eprintln!("hash error for {}: {}", path.display(), e);
                errors += 1;
                continue;
            }
        };

        let file_kind = classify::classify(path);
        let mime_type = classify::guess_mime(path);
        let size = metadata.len() as i64;
        let mtime = metadata
            .modified()
            .ok()
            .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
            .map(|d| d.as_secs() as i64)
            .unwrap_or(0);

        #[cfg(unix)]
        let permissions = {
            use std::os::unix::fs::PermissionsExt;
            Some(metadata.permissions().mode() as i32)
        };
        #[cfg(not(unix))]
        let permissions: Option<i32> = None;

        match catalog::upsert_file(
            &conn,
            source_id,
            &rel_path,
            &content_hash,
            size,
            mtime,
            &file_kind,
            mime_type.as_deref(),
            permissions,
        ) {
            Ok(is_changed) => {
                // Also ensure content record exists
                if let Err(e) = catalog::insert_content_if_not_exists(&conn, &content_hash) {
                    eprintln!("content insert error: {}", e);
                    errors += 1;
                    continue;
                }
                if is_changed {
                    // Check if this was an update or insert by looking at file count
                    // For simplicity: first upsert always returns changed=true for new files
                    files_new += 1;
                } else {
                    files_unchanged += 1;
                }
            }
            Err(e) => {
                eprintln!("catalog error for {}: {}", rel_path, e);
                errors += 1;
            }
        }
    }

    let files_changed = 0usize; // TODO: separate new vs changed tracking in upsert_file

    let files_missing =
        catalog::mark_unseen_files_missing(&conn, source_id, &scan_start).unwrap_or(0);

    catalog::update_source_last_scan(&conn, source_id).ok();

    Ok(ScanResult {
        files_found: paths.len(),
        files_new,
        files_changed,
        files_unchanged,
        files_missing,
        errors,
    })
}

fn chrono_now() -> String {
    // UTC datetime string matching SQLite's datetime('now') format
    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default();
    let secs = now.as_secs();
    // Convert to rough UTC datetime (not using chrono crate to avoid extra dep)
    let days = secs / 86400;
    let time_of_day = secs % 86400;
    let hours = time_of_day / 3600;
    let minutes = (time_of_day % 3600) / 60;
    let seconds = time_of_day % 60;

    // Approximate date calculation from Unix epoch (1970-01-01)
    let mut y = 1970i64;
    let mut remaining_days = days as i64;

    loop {
        let days_in_year = if is_leap(y) { 366 } else { 365 };
        if remaining_days < days_in_year {
            break;
        }
        remaining_days -= days_in_year;
        y += 1;
    }

    let month_days = if is_leap(y) {
        [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    } else {
        [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    };

    let mut m = 0u32;
    for (i, &md) in month_days.iter().enumerate() {
        if remaining_days < md {
            m = i as u32 + 1;
            break;
        }
        remaining_days -= md;
    }
    if m == 0 {
        m = 12;
    }
    let d = remaining_days + 1;

    format!(
        "{:04}-{:02}-{:02} {:02}:{:02}:{:02}",
        y, m, d, hours, minutes, seconds
    )
}

fn is_leap(y: i64) -> bool {
    (y % 4 == 0 && y % 100 != 0) || y % 400 == 0
}
