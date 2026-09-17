//! Embeds the built browser client (`client/dist`) into the `sage` binary.
//!
//! Building the client needs Node; building the engine must not. When `client/dist` is empty
//! the binary serves a short page saying how to build the client, and `/ws` works either way.
//! `SAGE_CLIENT_DIST` points at a different build output.

use std::fmt::Write as _;
use std::path::{Path, PathBuf};

fn main() {
    println!("cargo:rerun-if-env-changed=SAGE_CLIENT_DIST");
    let manifest = PathBuf::from(std::env::var("CARGO_MANIFEST_DIR").expect("manifest dir"));
    let dist = std::env::var_os("SAGE_CLIENT_DIST")
        .map(PathBuf::from)
        .unwrap_or_else(|| manifest.join("../../client/dist"));
    // Watch the directory even before the client is first built: a missing path would make
    // cargo rerun this script, and rebuild the crate, on every build.
    let _ = std::fs::create_dir_all(&dist);
    println!("cargo:rerun-if-changed={}", dist.display());

    let mut files = Vec::new();
    collect(&dist, &dist, &mut files);
    files.sort();

    let mut out = String::from(
        "/// The built client: (URL path, content type, bytes), sorted by path.\n\
         pub static ASSETS: &[(&str, &str, &[u8])] = &[\n",
    );
    for (url, path) in &files {
        let absolute = path.canonicalize().expect("client file");
        writeln!(
            out,
            "    ({url:?}, {:?}, include_bytes!({:?})),",
            content_type(path),
            absolute.display().to_string()
        )
        .expect("write to string");
    }
    out.push_str("];\n");
    let target = PathBuf::from(std::env::var("OUT_DIR").expect("out dir")).join("client.rs");
    std::fs::write(target, out).expect("write client.rs");
}

fn collect(root: &Path, dir: &Path, files: &mut Vec<(String, PathBuf)>) {
    let Ok(entries) = std::fs::read_dir(dir) else {
        return;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_dir() {
            collect(root, &path, files);
        } else if let Ok(relative) = path.strip_prefix(root) {
            let url = relative
                .components()
                .map(|c| c.as_os_str().to_string_lossy().into_owned())
                .collect::<Vec<_>>()
                .join("/");
            if !url.starts_with('.') {
                files.push((format!("/{url}"), path));
            }
        }
    }
}

fn content_type(path: &Path) -> &'static str {
    match path.extension().and_then(|e| e.to_str()).unwrap_or("") {
        "html" => "text/html; charset=utf-8",
        "js" | "mjs" => "text/javascript; charset=utf-8",
        "css" => "text/css; charset=utf-8",
        "json" | "map" => "application/json",
        "svg" => "image/svg+xml",
        "png" => "image/png",
        "ico" => "image/x-icon",
        "woff2" => "font/woff2",
        "txt" => "text/plain; charset=utf-8",
        _ => "application/octet-stream",
    }
}
