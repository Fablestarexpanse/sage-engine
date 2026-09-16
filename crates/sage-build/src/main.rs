//! `sage-build plugins`: builds every first-party plugin in `plugins/` into a runnable fragment
//! directory under `target/plugins/<id>/`, then prints each path.

use std::process::ExitCode;

fn main() -> ExitCode {
    match std::env::args().nth(1).as_deref() {
        Some("plugins") => match sage_build::first_party_plugins() {
            Ok(dirs) => {
                for dir in dirs {
                    println!("{}", dir.display());
                }
                ExitCode::SUCCESS
            }
            Err(message) => {
                eprintln!("sage-build: {message}");
                ExitCode::FAILURE
            }
        },
        _ => {
            eprintln!("usage: sage-build plugins");
            ExitCode::from(2)
        }
    }
}
