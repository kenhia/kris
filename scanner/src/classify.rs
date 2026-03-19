use std::path::Path;

/// File kind classification for kris catalog.
#[derive(Debug, Clone, PartialEq, serde::Serialize)]
pub enum FileKind {
    Text,
    Code,
    Markdown,
    Config,
    Data,
    Unknown,
}

impl FileKind {
    pub fn as_str(&self) -> &'static str {
        match self {
            FileKind::Text => "text",
            FileKind::Code => "code",
            FileKind::Markdown => "markdown",
            FileKind::Config => "config",
            FileKind::Data => "data",
            FileKind::Unknown => "unknown",
        }
    }
}

/// Classify a file by its extension.
pub fn classify(path: &Path) -> FileKind {
    let ext = path
        .extension()
        .and_then(|e| e.to_str())
        .unwrap_or("")
        .to_lowercase();

    let name = path
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or("")
        .to_lowercase();

    match ext.as_str() {
        // Markdown
        "md" | "markdown" | "rst" => FileKind::Markdown,

        // Code
        "py" | "rs" | "js" | "ts" | "jsx" | "tsx" | "java" | "c" | "cpp" | "h" | "hpp" | "go"
        | "rb" | "php" | "swift" | "kt" | "scala" | "cs" | "fs" | "hs" | "ml" | "ex" | "exs"
        | "erl" | "clj" | "lisp" | "lua" | "r" | "jl" | "sh" | "bash" | "zsh" | "fish" | "ps1"
        | "bat" | "cmd" | "pl" | "pm" | "sql" | "vue" | "svelte" | "dart" | "nim" | "zig" | "v"
        | "cr" | "d" | "ada" | "pas" | "f90" | "f95" => FileKind::Code,

        // Config
        "toml" | "yaml" | "yml" | "ini" | "cfg" | "conf" | "env" | "properties" => FileKind::Config,

        // Data
        "json" | "xml" | "csv" | "tsv" | "jsonl" | "ndjson" => FileKind::Data,

        // Text
        "txt" | "text" | "log" | "rtf" => FileKind::Text,

        // Check filename-based patterns for extensionless files
        "" => classify_by_name(&name),

        _ => FileKind::Unknown,
    }
}

fn classify_by_name(name: &str) -> FileKind {
    match name {
        "makefile" | "justfile" | "dockerfile" | "vagrantfile" | "rakefile" | "gemfile"
        | "procfile" | ".env" | ".editorconfig" | ".gitignore" | ".dockerignore" => {
            FileKind::Config
        }
        "readme" | "license" | "changelog" | "contributing" | "authors" | "todo" | "notes" => {
            FileKind::Text
        }
        _ => FileKind::Unknown,
    }
}

/// Guess a MIME type from the file extension.
pub fn guess_mime(path: &Path) -> Option<String> {
    let ext = path.extension().and_then(|e| e.to_str())?.to_lowercase();
    let mime = match ext.as_str() {
        "txt" | "text" | "log" => "text/plain",
        "md" | "markdown" => "text/markdown",
        "py" => "text/x-python",
        "rs" => "text/x-rust",
        "js" => "text/javascript",
        "ts" => "text/typescript",
        "json" => "application/json",
        "toml" => "application/toml",
        "yaml" | "yml" => "text/x-yaml",
        "xml" => "application/xml",
        "csv" => "text/csv",
        "html" | "htm" => "text/html",
        "css" => "text/css",
        "sh" | "bash" => "text/x-shellscript",
        _ => return None,
    };
    Some(mime.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;

    #[test]
    fn test_classify_code() {
        assert_eq!(classify(&PathBuf::from("main.py")), FileKind::Code);
        assert_eq!(classify(&PathBuf::from("lib.rs")), FileKind::Code);
        assert_eq!(classify(&PathBuf::from("app.tsx")), FileKind::Code);
        assert_eq!(classify(&PathBuf::from("query.sql")), FileKind::Code);
    }

    #[test]
    fn test_classify_markdown() {
        assert_eq!(classify(&PathBuf::from("README.md")), FileKind::Markdown);
        assert_eq!(classify(&PathBuf::from("docs.rst")), FileKind::Markdown);
    }

    #[test]
    fn test_classify_config() {
        assert_eq!(classify(&PathBuf::from("config.toml")), FileKind::Config);
        assert_eq!(classify(&PathBuf::from("settings.yaml")), FileKind::Config);
        assert_eq!(classify(&PathBuf::from(".env")), FileKind::Config);
    }

    #[test]
    fn test_classify_text() {
        assert_eq!(classify(&PathBuf::from("notes.txt")), FileKind::Text);
        assert_eq!(classify(&PathBuf::from("output.log")), FileKind::Text);
    }

    #[test]
    fn test_classify_data() {
        assert_eq!(classify(&PathBuf::from("data.json")), FileKind::Data);
        assert_eq!(classify(&PathBuf::from("records.csv")), FileKind::Data);
    }

    #[test]
    fn test_classify_unknown() {
        assert_eq!(classify(&PathBuf::from("image.png")), FileKind::Unknown);
        assert_eq!(classify(&PathBuf::from("binary.exe")), FileKind::Unknown);
    }

    #[test]
    fn test_classify_by_filename() {
        assert_eq!(classify(&PathBuf::from("Makefile")), FileKind::Config);
        assert_eq!(classify(&PathBuf::from("Dockerfile")), FileKind::Config);
        assert_eq!(classify(&PathBuf::from("README")), FileKind::Text);
    }

    #[test]
    fn test_guess_mime() {
        assert_eq!(
            guess_mime(&PathBuf::from("a.py")),
            Some("text/x-python".into())
        );
        assert_eq!(
            guess_mime(&PathBuf::from("a.md")),
            Some("text/markdown".into())
        );
        assert_eq!(guess_mime(&PathBuf::from("a.png")), None);
    }
}
