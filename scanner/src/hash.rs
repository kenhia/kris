use sha2::{Digest, Sha256};
use std::fs::File;
use std::io::{self, BufReader, Read};
use std::path::Path;

const BUF_SIZE: usize = 64 * 1024; // 64 KB streaming buffer

/// Compute SHA-256 hash of a file using streaming reads.
pub fn sha256_file(path: &Path) -> io::Result<String> {
    let file = File::open(path)?;
    let mut reader = BufReader::with_capacity(BUF_SIZE, file);
    let mut hasher = Sha256::new();
    let mut buf = vec![0u8; BUF_SIZE];

    loop {
        let n = reader.read(&mut buf)?;
        if n == 0 {
            break;
        }
        hasher.update(&buf[..n]);
    }

    Ok(format!("{:x}", hasher.finalize()))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::TempDir;

    #[test]
    fn test_hash_known_content() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("test.txt");
        fs::write(&path, "hello world").unwrap();
        let hash = sha256_file(&path).unwrap();
        // SHA-256 of "hello world"
        assert_eq!(
            hash,
            "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
        );
    }

    #[test]
    fn test_hash_empty_file() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("empty.txt");
        fs::write(&path, "").unwrap();
        let hash = sha256_file(&path).unwrap();
        // SHA-256 of empty string
        assert_eq!(
            hash,
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        );
    }

    #[test]
    fn test_hash_large_file() {
        let dir = TempDir::new().unwrap();
        let path = dir.path().join("large.bin");
        // Write >64KB to test streaming
        let data = vec![0xABu8; 256 * 1024];
        fs::write(&path, &data).unwrap();
        let hash = sha256_file(&path).unwrap();
        assert_eq!(hash.len(), 64); // 256-bit hex = 64 chars
    }

    #[test]
    fn test_hash_nonexistent_file() {
        let result = sha256_file(Path::new("/nonexistent/file.txt"));
        assert!(result.is_err());
    }
}
