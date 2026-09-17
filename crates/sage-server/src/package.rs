//! `.sagepkg`: a fragment as one file, a tar archive compressed with zstd.
//!
//! Packing is deterministic: the same files give the same bytes (sorted paths, fixed mode,
//! owner and time). Unpacking treats the archive as hostile: only regular files and
//! directories, every path component checked like a directory fragment's file names, no
//! duplicates, and the file-count and size limits enforced while decompressing, so a
//! compression bomb stops at the limit instead of filling memory.
//!
//! A package's content digest is the same as the directory it was packed from: the digest
//! covers the files, not the archive.

use std::io::Read;

use crate::library::{Files, MAX_FILES, MAX_FRAGMENT_BYTES};

/// The first bytes of every zstd frame.
pub const ZSTD_MAGIC: [u8; 4] = [0x28, 0xb5, 0x2f, 0xfd];

/// zstd level used when packing.
const LEVEL: i32 = 19;

/// Packs `files` (which must include `fragment.yaml`) into `.sagepkg` bytes.
pub fn pack(files: &Files) -> Result<Vec<u8>, String> {
    let mut sorted: Vec<&(String, Vec<u8>)> = files.0.iter().collect();
    sorted.sort_by(|a, b| a.0.as_bytes().cmp(b.0.as_bytes()));
    let mut archive = tar::Builder::new(Vec::new());
    archive.mode(tar::HeaderMode::Deterministic);
    for (path, bytes) in sorted {
        let mut header = tar::Header::new_ustar();
        header.set_entry_type(tar::EntryType::Regular);
        header.set_size(bytes.len() as u64);
        header.set_mode(0o644);
        header.set_uid(0);
        header.set_gid(0);
        header.set_mtime(0);
        archive
            .append_data(&mut header, path, bytes.as_slice())
            .map_err(|e| format!("{path}: {e}"))?;
    }
    let tar = archive.into_inner().map_err(|e| e.to_string())?;
    zstd::stream::encode_all(tar.as_slice(), LEVEL).map_err(|e| e.to_string())
}

/// Unpacks `.sagepkg` bytes into files, refusing anything a fragment directory could not hold.
pub fn unpack(bytes: &[u8]) -> Result<Files, String> {
    if !bytes.starts_with(&ZSTD_MAGIC) {
        return Err("not a .sagepkg (no zstd frame)".into());
    }
    let decoder = zstd::stream::read::Decoder::new(bytes).map_err(|e| e.to_string())?;
    // Tar adds a 512-byte header per file and padding; allow for that on top of the content.
    let archive_limit = MAX_FRAGMENT_BYTES + (MAX_FILES as u64 + 4) * 1024;
    let mut archive = tar::Archive::new(decoder.take(archive_limit));
    let mut files: Vec<(String, Vec<u8>)> = Vec::new();
    let mut total = 0u64;
    let entries = archive
        .entries()
        .map_err(|e| format!("not a .sagepkg: {e}"))?;
    for entry in entries {
        let mut entry = entry.map_err(|e| format!("the archive is damaged or too large: {e}"))?;
        let raw_path = entry.path_bytes().into_owned();
        let path = std::str::from_utf8(&raw_path)
            .map_err(|_| "an archive path is not UTF-8".to_owned())?
            .to_owned();
        let kind = entry.header().entry_type();
        if kind.is_dir() {
            check_path(path.trim_end_matches('/'))?;
            continue;
        }
        if !kind.is_file() {
            return Err(format!(
                "{path}: only files and directories are allowed in a package"
            ));
        }
        check_path(&path)?;
        if files.iter().any(|(p, _)| *p == path) {
            return Err(format!("{path} appears twice in the package"));
        }
        let size = entry.size();
        total += size;
        if files.len() == MAX_FILES || total > MAX_FRAGMENT_BYTES {
            return Err(format!(
                "a fragment has at most {MAX_FILES} files and {} MiB",
                MAX_FRAGMENT_BYTES / (1024 * 1024)
            ));
        }
        let mut data = Vec::with_capacity(size as usize);
        entry
            .read_to_end(&mut data)
            .map_err(|e| format!("{path}: the archive is damaged or too large: {e}"))?;
        if data.len() as u64 != size {
            return Err(format!("{path}: the archive is cut off"));
        }
        files.push((path, data));
    }
    if files.is_empty() {
        return Err("the package is empty".into());
    }
    files.sort();
    Ok(Files(files))
}

/// A relative `/`-separated path whose every component is a safe file name.
fn check_path(path: &str) -> Result<(), String> {
    let ok = !path.is_empty()
        && !path.starts_with('/')
        && path.split('/').all(crate::library::safe_name)
        && path.split('/').count() <= 16;
    if ok {
        Ok(())
    } else {
        Err(format!("`{path}` is not an allowed path in a package"))
    }
}

/// `sage pack <fragment-dir> <out.sagepkg>`: checks the fragment as `sage install` would
/// (except the engine range: a package may target another engine) and writes the package.
pub fn run(source: &std::path::Path, out: &std::path::Path) -> Result<(), String> {
    let verified =
        crate::library::verify(source, &Default::default(), false).map_err(|problems| {
            format!(
                "{} was not packed: {}",
                source.display(),
                problems.join("; ")
            )
        })?;
    let bytes = pack(&verified.files)?;
    std::fs::write(out, &bytes).map_err(|e| format!("{}: {e}", out.display()))?;
    let report = serde_json::json!({
        "ok": true,
        "fragment": verified.manifest.id.as_str(),
        "version": verified.manifest.version,
        "digest": verified.digest,
        "path": out.display().to_string(),
        "bytes": bytes.len(),
        "warnings": verified.warnings,
    });
    println!("{report}");
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn files() -> Files {
        Files(vec![
            ("fragment.yaml".into(), b"schema: x\n".to_vec()),
            ("assets/a.txt".into(), b"hello".to_vec()),
        ])
    }

    #[test]
    fn packing_is_deterministic_and_round_trips() {
        let one = pack(&files()).unwrap();
        let reversed = Files(files().0.into_iter().rev().collect());
        assert_eq!(one, pack(&reversed).unwrap());
        let back = unpack(&one).unwrap();
        let mut expected = files().0;
        expected.sort();
        assert_eq!(back.0, expected);
    }

    #[test]
    fn unsafe_paths_are_refused() {
        for bad in ["../x", "/etc/x", "a/../b", "a//b", "a\\b", "c:x", ""] {
            assert!(check_path(bad).is_err(), "{bad}");
        }
        assert!(check_path("assets/icons/main.png").is_ok());
    }
}
