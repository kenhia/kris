use std::path::{Path, PathBuf};

use globset::{Glob, GlobSet, GlobSetBuilder};
use walkdir::{DirEntry, WalkDir};

/// Build a compiled `GlobSet` from a list of exclude patterns.
///
/// Patterns without wildcards are treated as exact-name matches (wrapped in
/// `**/{pattern}` so they match at any depth). Patterns with wildcards are
/// compiled as-is.
fn build_glob_set(patterns: &[String]) -> GlobSet {
    let mut builder = GlobSetBuilder::new();
    for pattern in patterns {
        // If the pattern already contains a glob character, use it verbatim.
        // Otherwise wrap it so "node_modules" matches at any depth.
        let glob_pattern =
            if pattern.contains('*') || pattern.contains('?') || pattern.contains('[') {
                pattern.clone()
            } else {
                format!("**/{pattern}")
            };
        if let Ok(glob) = Glob::new(&glob_pattern) {
            builder.add(glob);
        }
    }
    builder.build().unwrap_or_else(|_| GlobSet::empty())
}

/// Walk a directory tree, respecting exclude patterns and symlink settings.
pub fn walk_directory(
    root: &Path,
    exclude_patterns: &[String],
    follow_symlinks: bool,
) -> Vec<PathBuf> {
    let glob_set = build_glob_set(exclude_patterns);

    let walker = WalkDir::new(root)
        .follow_links(follow_symlinks)
        .into_iter()
        .filter_entry(|e| !is_excluded(e, root, &glob_set));

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

fn is_excluded(entry: &DirEntry, root: &Path, glob_set: &GlobSet) -> bool {
    // Match against the entry name (e.g. ".git", "node_modules")
    let name = entry.file_name().to_string_lossy();
    if glob_set.is_match(&*name) {
        return true;
    }

    // Match against the relative path from root (e.g. "src/build/out")
    let rel = entry.path().strip_prefix(root).unwrap_or(entry.path());
    glob_set.is_match(rel)
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

    // T014: Glob pattern matching
    #[test]
    fn test_glob_pattern_wildcard() {
        let dir = TempDir::new().unwrap();
        let root = dir.path();
        fs::write(root.join("file.txt"), "hello").unwrap();
        fs::write(root.join("cache.pyc"), "bytecode").unwrap();
        fs::write(root.join("other.pyo"), "optimized").unwrap();
        fs::write(root.join("keep.py"), "source").unwrap();

        let excludes = vec!["*.pyc".to_string(), "*.pyo".to_string()];
        let files = walk_directory(root, &excludes, false);
        let names: Vec<String> = files
            .iter()
            .map(|f| f.file_name().unwrap().to_string_lossy().to_string())
            .collect();

        assert!(names.contains(&"file.txt".to_string()));
        assert!(names.contains(&"keep.py".to_string()));
        assert!(!names.contains(&"cache.pyc".to_string()));
        assert!(!names.contains(&"other.pyo".to_string()));
    }

    #[test]
    fn test_glob_exact_name_at_any_depth() {
        let dir = TempDir::new().unwrap();
        let root = dir.path();

        // Create build directories at different depths
        fs::create_dir_all(root.join("build")).unwrap();
        fs::write(root.join("build/output.o"), "obj").unwrap();
        fs::create_dir_all(root.join("project/build")).unwrap();
        fs::write(root.join("project/build/output.o"), "obj").unwrap();
        fs::create_dir_all(root.join("project")).unwrap();
        fs::write(root.join("project/main.py"), "code").unwrap();
        fs::write(root.join("readme.txt"), "hi").unwrap();

        let excludes = vec!["build".to_string()];
        let files = walk_directory(root, &excludes, false);
        let names: Vec<String> = files
            .iter()
            .map(|f| f.file_name().unwrap().to_string_lossy().to_string())
            .collect();

        assert!(names.contains(&"main.py".to_string()));
        assert!(names.contains(&"readme.txt".to_string()));
        assert!(!names.contains(&"output.o".to_string()));
    }

    // T015: Backward compatibility — existing .git/node_modules tests still pass with glob implementation
    #[test]
    fn test_backward_compat_dot_prefix_excludes() {
        let dir = setup_tree();
        let excludes = vec![
            ".git".to_string(),
            "node_modules".to_string(),
            "__pycache__".to_string(),
        ];
        let files = walk_directory(dir.path(), &excludes, false);
        assert_eq!(files.len(), 3);
        for f in &files {
            let s = f.to_string_lossy();
            assert!(!s.contains(".git"));
            assert!(!s.contains("node_modules"));
        }
    }
}
