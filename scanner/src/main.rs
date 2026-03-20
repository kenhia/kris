use clap::Parser;
use std::path::PathBuf;

/// kris-scanner: filesystem scanner for the kris personal data system.
#[derive(Parser, Debug)]
#[command(name = "kris-scanner", version, about)]
struct Args {
    /// Path to the SQLite database
    #[arg(long)]
    db: PathBuf,

    /// Source ID for this scan
    #[arg(long)]
    source_id: String,

    /// Base directory path to scan
    #[arg(long)]
    base_path: PathBuf,

    /// Patterns to exclude (can be repeated)
    #[arg(long, default_value = ".git")]
    exclude: Vec<String>,

    /// Follow symbolic links
    #[arg(long, default_value_t = false)]
    follow_symlinks: bool,

    /// Skip SHA-256 hashing (faster exploration scans)
    #[arg(long, default_value_t = false)]
    skip_hash: bool,

    /// Output as JSON
    #[arg(long, default_value_t = false)]
    json: bool,
}

fn main() {
    let args = Args::parse();

    match kris_scanner::scan(
        &args.db,
        &args.source_id,
        &args.base_path,
        &args.exclude,
        args.follow_symlinks,
        args.skip_hash,
    ) {
        Ok(result) => {
            if args.json {
                println!("{}", serde_json::to_string(&result).unwrap());
            } else {
                println!("Scan complete:");
                println!("  Files found:     {}", result.files_found);
                println!("  New:             {}", result.files_new);
                println!("  Changed:         {}", result.files_changed);
                println!("  Unchanged:       {}", result.files_unchanged);
                println!("  Missing:         {}", result.files_missing);
                println!("  Errors:          {}", result.errors);
            }
        }
        Err(e) => {
            eprintln!("error: {}", e);
            std::process::exit(1);
        }
    }
}
