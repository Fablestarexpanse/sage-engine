//! Serves the embedded browser client beside `/ws`, so one port is all a player needs.
//!
//! Only files that were in `client/dist` at build time are served; nothing is read from disk.
//! Every response carries a Content-Security-Policy that allows scripts, styles and
//! connections only from this server.

use axum::http::{HeaderValue, StatusCode, Uri, header};
use axum::response::{IntoResponse, Response};

mod embedded {
    include!(concat!(env!("OUT_DIR"), "/client.rs"));
}

/// The policy on every page and asset.
pub const CONTENT_SECURITY_POLICY: &str = "default-src 'none'; script-src 'self'; \
     style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; \
     base-uri 'none'; form-action 'none'; frame-ancestors 'none'";

/// Shown when the binary was built before the client was.
const NOT_BUILT: &str = "<!doctype html><html lang=\"en\"><meta charset=\"utf-8\">\
     <title>SAGE</title><h1>SAGE</h1><p>This engine was built without the browser client. \
     Build it with <code>pnpm --dir client install</code> and \
     <code>pnpm --dir client build</code>, then rebuild <code>sage</code>.</p>\
     <p>Any WebSocket client can still play: <code>sage.protocol/1</code> is at \
     <code>/ws</code>.</p></html>";

/// Whether the client was embedded.
pub fn client_built() -> bool {
    find("/index.html").is_some()
}

fn find(path: &str) -> Option<(&'static str, &'static [u8])> {
    embedded::ASSETS
        .binary_search_by(|(p, _, _)| (*p).cmp(path))
        .ok()
        .map(|i| (embedded::ASSETS[i].1, embedded::ASSETS[i].2))
}

/// The handler for everything that is not `/ws`.
pub async fn serve(uri: Uri) -> Response {
    let path = match uri.path() {
        "/" => "/index.html",
        path => path,
    };
    let (status, content_type, body, cache): (_, _, &'static [u8], _) = match find(path) {
        // Vite names these by content hash, so they never change under the same name.
        Some((content_type, body)) if path.starts_with("/assets/") => (
            StatusCode::OK,
            content_type,
            body,
            "public, max-age=31536000, immutable",
        ),
        Some((content_type, body)) => (StatusCode::OK, content_type, body, "no-cache"),
        None if path == "/index.html" => (
            StatusCode::OK,
            "text/html; charset=utf-8",
            NOT_BUILT.as_bytes(),
            "no-cache",
        ),
        None => (
            StatusCode::NOT_FOUND,
            "text/plain; charset=utf-8",
            b"Not found.",
            "no-cache",
        ),
    };
    let mut response = (status, body).into_response();
    let headers = response.headers_mut();
    headers.insert(header::CONTENT_TYPE, HeaderValue::from_static(content_type));
    headers.insert(header::CACHE_CONTROL, HeaderValue::from_static(cache));
    headers.insert(
        header::CONTENT_SECURITY_POLICY,
        HeaderValue::from_static(CONTENT_SECURITY_POLICY),
    );
    headers.insert(
        header::X_CONTENT_TYPE_OPTIONS,
        HeaderValue::from_static("nosniff"),
    );
    headers.insert(
        header::REFERRER_POLICY,
        HeaderValue::from_static("no-referrer"),
    );
    response
}
