//! Fetching a fragment for `sage install <world> <url>`.
//!
//! Only `https://` URLs are fetched, and redirects must stay on https. Plain `http://` is
//! allowed only for loopback hosts, for local registries and tests. The body is capped at the
//! fragment size limit while it downloads, and the whole request has a time limit. What comes
//! back is checked exactly like a local file; with `--digest`, its content digest must also
//! equal the one expected, which is how a registry pins what it listed.

use std::path::PathBuf;
use std::time::Duration;

use crate::library::MAX_FRAGMENT_BYTES;

/// Longest a download may take.
pub const DOWNLOAD_TIMEOUT: Duration = Duration::from_secs(120);

/// Whether `source` names a URL rather than a local path.
pub fn is_url(source: &str) -> bool {
    let lower = source.to_ascii_lowercase();
    lower.starts_with("https://") || lower.starts_with("http://")
}

/// Downloads `url`. Returns the file name its path ends with (to tell a package or card by
/// extension) and the bytes.
pub fn fetch(url: &str) -> Result<(PathBuf, Vec<u8>), String> {
    let parsed: ureq::http::Uri = url
        .parse()
        .map_err(|e| format!("`{url}` is not a URL: {e}"))?;
    let scheme = parsed.scheme_str().unwrap_or_default().to_ascii_lowercase();
    let host = parsed.host().unwrap_or_default().to_ascii_lowercase();
    let loopback = matches!(host.as_str(), "localhost" | "127.0.0.1" | "[::1]" | "::1");
    match scheme.as_str() {
        "https" => {}
        "http" if loopback => {}
        _ => {
            return Err(format!(
                "`{url}`: only https URLs are fetched (plain http only from this machine)"
            ));
        }
    }
    let agent: ureq::Agent = ureq::Agent::config_builder()
        .timeout_global(Some(DOWNLOAD_TIMEOUT))
        .https_only(!loopback)
        .max_redirects(5)
        .http_status_as_error(false)
        .build()
        .into();
    let mut response = agent
        .get(url)
        .header("User-Agent", concat!("sage/", env!("CARGO_PKG_VERSION")))
        .call()
        .map_err(|e| format!("downloading {url} failed: {e}"))?;
    let status = response.status();
    if !status.is_success() {
        return Err(format!(
            "downloading {url} failed: the server answered {status}"
        ));
    }
    let bytes = response
        .body_mut()
        .with_config()
        .limit(MAX_FRAGMENT_BYTES)
        .read_to_vec()
        .map_err(|e| {
            format!(
                "downloading {url} failed (a fragment is at most {} MiB): {e}",
                MAX_FRAGMENT_BYTES / (1024 * 1024)
            )
        })?;
    let name = parsed
        .path()
        .rsplit('/')
        .next()
        .filter(|n| !n.is_empty())
        .unwrap_or("download");
    Ok((PathBuf::from(name), bytes))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn only_https_or_loopback_http_is_fetched() {
        for refused in [
            "http://example.com/a.sagepkg",
            "ftp://example.com/a.sagepkg",
            "file:///etc/passwd",
            "http://10.0.0.1/a.png",
        ] {
            let err = fetch(refused).unwrap_err();
            assert!(
                err.contains("only https") || err.contains("not a URL"),
                "{refused}: {err}"
            );
        }
        assert!(is_url("HTTPS://x/y") && !is_url("./card.png"));
    }
}
