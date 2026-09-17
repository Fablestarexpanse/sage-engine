//! The content digest: the one hash that identifies what a fragment contains.
//!
//! It covers every file except `fragment.yaml`, so the manifest can carry the digest of the
//! content it describes without hashing itself. A directory and a package with the same files
//! have the same digest, and so does any copy on the Foundry, which computes it with this code.
//!
//! Files are hashed in byte order of their paths (`/`-separated, relative). Each contributes
//! its path length (u32, big-endian), its path, its size (u64, big-endian) and its bytes, so no
//! two different sets of files can produce the same input.

use sha2::{Digest, Sha256};

/// The manifest's file name; never part of the content digest.
pub const MANIFEST_FILE: &str = "fragment.yaml";

/// `sha256:` and 64 lowercase hex digits over `files`, ignoring [`MANIFEST_FILE`] and the
/// order given. Paths must be unique; a duplicate is an error.
pub fn content_digest(files: &[(&str, &[u8])]) -> Result<String, String> {
    let mut sorted: Vec<&(&str, &[u8])> = files
        .iter()
        .filter(|(path, _)| *path != MANIFEST_FILE)
        .collect();
    sorted.sort_by(|a, b| a.0.as_bytes().cmp(b.0.as_bytes()));
    if let Some(pair) = sorted.windows(2).find(|w| w[0].0 == w[1].0) {
        return Err(format!("`{}` is listed twice", pair[0].0));
    }
    let mut hasher = Sha256::new();
    for (path, bytes) in sorted {
        let length = u32::try_from(path.len()).map_err(|_| format!("path too long: {path}"))?;
        hasher.update(length.to_be_bytes());
        hasher.update(path.as_bytes());
        hasher.update((bytes.len() as u64).to_be_bytes());
        hasher.update(bytes);
    }
    let hash = hasher.finalize();
    let mut out = String::with_capacity(7 + 64);
    out.push_str("sha256:");
    for byte in hash {
        out.push_str(&format!("{byte:02x}"));
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_digest_is_fixed_by_the_format() {
        // Written down once so any change to the format fails here, not on the Foundry.
        assert_eq!(
            content_digest(&[]).unwrap(),
            "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        );
        let one = content_digest(&[("card.png", b"abc")]).unwrap();
        let mut input = Vec::new();
        input.extend_from_slice(&8u32.to_be_bytes());
        input.extend_from_slice(b"card.png");
        input.extend_from_slice(&3u64.to_be_bytes());
        input.extend_from_slice(b"abc");
        let expected: String = Sha256::digest(&input)
            .iter()
            .map(|b| format!("{b:02x}"))
            .collect();
        assert_eq!(one, format!("sha256:{expected}"));
    }

    #[test]
    fn order_and_the_manifest_do_not_matter_but_content_and_names_do() {
        let a = content_digest(&[("a", b"1"), ("b/c", b"2")]).unwrap();
        let b =
            content_digest(&[("b/c", b"2"), (MANIFEST_FILE, b"anything"), ("a", b"1")]).unwrap();
        assert_eq!(a, b);
        assert_ne!(a, content_digest(&[("a", b"1"), ("b/c", b"3")]).unwrap());
        assert_ne!(a, content_digest(&[("a", b"1"), ("b/d", b"2")]).unwrap());
        // Moving a byte between name and content changes the input.
        assert_ne!(
            content_digest(&[("ab", b"")]).unwrap(),
            content_digest(&[("a", b"b")]).unwrap()
        );
        assert!(content_digest(&[("a", b"1"), ("a", b"1")]).is_err());
    }
}
