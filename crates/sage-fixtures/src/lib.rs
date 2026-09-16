//! Test support only. Builds WebAssembly components from source the first time a test asks
//! for one, so no binaries live in the repository.
//!
//! - [`plugin`]: test plugins in `crates/sage-fixtures/plugins` (`mover`, `spinner`, `hog`,
//!   `forger`).
//! - [`schema_validator`]: `crates/sage-schema/wasm`, the WASM build of manifest validation.

use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::OnceLock;

fn repo_root() -> &'static Path {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(Path::parent)
        .expect("crate lives at crates/sage-fixtures")
}

/// Builds the cargo workspace at `manifest` for wasm32-unknown-unknown and returns the
/// directory of release artifacts.
fn build(manifest: &Path, target_name: &str) -> PathBuf {
    let target = repo_root().join("target").join(target_name);
    let status = Command::new(env!("CARGO"))
        .args(["build", "--release", "--target", "wasm32-unknown-unknown"])
        .arg("--manifest-path")
        .arg(manifest)
        .arg("--target-dir")
        .arg(&target)
        .status()
        .expect("cargo runs");
    assert!(status.success(), "building {} failed", manifest.display());
    target.join("wasm32-unknown-unknown/release")
}

fn componentize(module_path: &Path) -> Vec<u8> {
    let module =
        std::fs::read(module_path).unwrap_or_else(|e| panic!("{}: {e}", module_path.display()));
    wit_component::ComponentEncoder::default()
        .module(&module)
        .and_then(|encoder| encoder.validate(true).encode())
        .unwrap_or_else(|e| panic!("{}: {e:#}", module_path.display()))
}

/// A test plugin as a component: `mover`, `spinner`, `hog` or `forger`.
pub fn plugin(name: &str) -> Vec<u8> {
    static DIR: OnceLock<PathBuf> = OnceLock::new();
    let dir = DIR.get_or_init(|| {
        build(
            &repo_root().join("crates/sage-fixtures/plugins/Cargo.toml"),
            "sage-fixtures-plugins",
        )
    });
    componentize(&dir.join(format!("{name}.wasm")))
}

/// The manifest validator (`sage:schema/validator`) as a component.
pub fn schema_validator() -> Vec<u8> {
    static DIR: OnceLock<PathBuf> = OnceLock::new();
    let dir = DIR.get_or_init(|| {
        build(
            &repo_root().join("crates/sage-schema/wasm/Cargo.toml"),
            "sage-schema-wasm",
        )
    });
    componentize(&dir.join("sage_schema_wasm.wasm"))
}
