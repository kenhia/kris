use std::path::{Path, PathBuf};

use walkdir::{DirEntry, WalkDir};

/// Walk a directory tree, respecting exclude patterns and symlink settings.
pub fn walk_directory(
    root: &Path,
    exclude_patterns: &[String],
    follow_symlinks: bool,
) -> Vec<PathBuf> {
    let walker = WalkDir::new(root)
        .follow_links(follow_symlinks)
        .into_iter()
        .filter_entry(|e| !is_excluded(e, exclude_patterns));

    let mut paths = Vec::new();
    for entry in walker {
        match entry {
            Ok(e) if e.file_type().is_file() => {
                paths.push(e.into_path());
            }
            Ok(_) => {} // skip directories
            Err(err) => {
                // Log and skip errors (permission denied, symlink cycles, etc.)
                eprintln!("walk error: {}", err);
            }
        }
    }
    paths
}

fn is_excluded(entry: &DirEntry, patterns: &[String]) -> bool {
    let name = entry.file_name().to_string_lossy();
    for pattern in patterns {
        if name == pattern.as_str() {
            return true;
        }
        // Also match if pattern starts with a dot and name starts with that dot pattern
        if pattern.starts_with('.') && name == pattern.as_str() {
            return true;
        }
    }
    false
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::TempDir;

    fn setup_tree() -> TempDir {
        let dir = TempDir::new().unwrap();
        let root = dir.path();

        fs::write(root.join("file1.txt"), "hello").unwrap();
        fs::write(root.join("file2.py"), "x = 1").unwrap();
        fs::create_dir_all(root.join("sub")).unwrap();
        fs::write(root.join("sub/nested.md"), "# hi").unwrap();
        fs::create_dir_all(root.join(".git")).unwrap();
        fs::write(root.join(".git/config"), "gitconfig").unwrap();
        fs::create_dir_all(root.join("node_modules")).unwrap();
        fs::write(root.join("node_modules/pkg.js"), "pkg").unwrap();

        dir
    }

    #[test]
    fn test_walks_all_files() {
        let dir = setup_tree();
        let files = walk_directory(dir.path(), &[], false);
        assert!(files.len() >= 5); // file1.txt, file2.py, sub/nested.md, .git/config, node_modules/pkg.js
    }

    #[test]
    fn test_excludes_directories() {
        let dir = setup_tree();
        let excludes = vec![".git".to_string(), "node_modules".to_string()];
        let files = walk_directory(dir.path(), &excludes, false);
        assert_eq!(files.len(), 3); // file1.txt, file2.py, sub/nested.md
        for f in &files {
            let s = f.to_string_lossy();
            assert!(!s.contains(".git"));
            assert!(!s.contains("node_modules"));
        }
    }

    #[test]
    fn test_handles_empty_directory() {
        let dir = TempDir::new().unwrap();
        let files = walk_directory(dir.path(), &[], false);
        assert!(files.is_empty());
    }

    #[test]
    fn test_symlink_cycle_detection() {
        let dir = TempDir::new().unwrap();
        let root = dir.path();
        fs::write(root.join("real.txt"), "data").unwrap();
        // Create a symlink cycle: root/link -> root
        #[cfg(unix)]
        {
            std::os::unix::fs::symlink(root, root.join("link")).unwrap();
            // Should not panic or hang — walkdir handles cycles
            let files = walk_directory(root, &[], true);
            // Should find at least real.txt
            assert!(files.iter().any(|f| f.file_name().unwrap() == "real.txt"));
        }
    }
}
