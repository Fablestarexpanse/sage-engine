//! Builds SAGE's WebAssembly components from source: first-party plugins, test plugins, and
//! the schema validator. Development tool and test support; never shipped, and nothing it
//! builds is committed.
//!
//! - [`first_party_plugin`] / [`first_party_plugins`]: fragments in `plugins/`, assembled into
//!   ready-to-run fragment directories under `target/plugins/<id>/` (`fragment.yaml` and
//!   `plugin.wasm`).
//! - [`test_plugin`]: test plugins in `crates/sage-build/test-plugins` (`mover`, `spinner`,
//!   `hog`, `forger`).
//! - [`schema_validator`]: `crates/sage-schema/wasm`, the WASM build of manifest validation.

use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::OnceLock;

/// Repository root.
pub fn repo_root() -> &'static Path {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(Path::parent)
        .expect("crate lives at crates/sage-build")
}

fn cargo() -> String {
    std::env::var("CARGO").unwrap_or_else(|_| "cargo".to_owned())
}

/// Builds the cargo workspace at `manifest` for wasm32-unknown-unknown into
/// `target/<target_name>` and returns the directory of release artifacts.
fn build(manifest: &Path, target_name: &str) -> Result<PathBuf, String> {
    let target = repo_root().join("target").join(target_name);
    let status = Command::new(cargo())
        .args(["build", "--release", "--target", "wasm32-unknown-unknown"])
        .arg("--manifest-path")
        .arg(manifest)
        .arg("--target-dir")
        .arg(&target)
        .status()
        .map_err(|e| format!("cannot run cargo: {e}"))?;
    if !status.success() {
        return Err(format!("building {} failed", manifest.display()));
    }
    Ok(target.join("wasm32-unknown-unknown/release"))
}

/// Wraps a core wasm module (with its embedded WIT) into a component.
pub fn componentize(module_path: &Path) -> Result<Vec<u8>, String> {
    let module =
        std::fs::read(module_path).map_err(|e| format!("{}: {e}", module_path.display()))?;
    wit_component::ComponentEncoder::default()
        .module(&module)
        .and_then(|encoder| encoder.validate(true).encode())
        .map_err(|e| format!("{}: {e:#}", module_path.display()))
}

/// A test plugin as a component: `mover`, `spinner`, `hog` or `forger`. Panics on failure.
pub fn test_plugin(name: &str) -> Vec<u8> {
    static DIR: OnceLock<PathBuf> = OnceLock::new();
    let dir = DIR.get_or_init(|| {
        build(
            &repo_root().join("crates/sage-build/test-plugins/Cargo.toml"),
            "sage-build-test-plugins",
        )
        .unwrap()
    });
    componentize(&dir.join(format!("{name}.wasm"))).unwrap()
}

/// The manifest validator (`sage:schema/validator`) as a component. Panics on failure.
pub fn schema_validator() -> Vec<u8> {
    static DIR: OnceLock<PathBuf> = OnceLock::new();
    let dir = DIR.get_or_init(|| {
        build(
            &repo_root().join("crates/sage-schema/wasm/Cargo.toml"),
            "sage-schema-wasm",
        )
        .unwrap()
    });
    componentize(&dir.join("sage_schema_wasm.wasm")).unwrap()
}

/// Ids of the first-party plugins: directories in `plugins/` that hold a `fragment.yaml`.
pub fn first_party_plugin_ids() -> Vec<String> {
    let mut ids: Vec<String> = std::fs::read_dir(repo_root().join("plugins"))
        .map(|entries| {
            entries
                .filter_map(Result::ok)
                .filter(|e| e.path().join("fragment.yaml").is_file())
                .map(|e| e.file_name().to_string_lossy().into_owned())
                .collect()
        })
        .unwrap_or_default();
    ids.sort();
    ids
}

/// Builds every first-party plugin and returns their fragment directories.
pub fn first_party_plugins() -> Result<Vec<PathBuf>, String> {
    let release = build(
        &repo_root().join("plugins/Cargo.toml"),
        "sage-build-plugins",
    )?;
    first_party_plugin_ids()
        .into_iter()
        .map(|id| assemble(&release, &id))
        .collect()
}

/// Builds the first-party plugin `id` (e.g. `sage.wander`) and returns its fragment directory.
/// Panics on failure; for tests.
pub fn first_party_plugin(id: &str) -> PathBuf {
    static RELEASE: OnceLock<PathBuf> = OnceLock::new();
    let release = RELEASE.get_or_init(|| {
        build(
            &repo_root().join("plugins/Cargo.toml"),
            "sage-build-plugins",
        )
        .unwrap()
    });
    assemble(release, id).unwrap()
}

/// Copies `plugins/<id>/fragment.yaml` and the componentized module into `target/plugins/<id>/`.
/// The crate for plugin `creator.slug` is named `creator-slug`.
fn assemble(release: &Path, id: &str) -> Result<PathBuf, String> {
    let module = release.join(format!("{}.wasm", id.replace(['.', '-'], "_")));
    let component = componentize(&module)?;
    let out = repo_root().join("target/plugins").join(id);
    std::fs::create_dir_all(&out).map_err(|e| format!("{}: {e}", out.display()))?;
    std::fs::copy(
        repo_root().join("plugins").join(id).join("fragment.yaml"),
        out.join("fragment.yaml"),
    )
    .map_err(|e| format!("{id}/fragment.yaml: {e}"))?;
    std::fs::write(out.join("plugin.wasm"), component)
        .map_err(|e| format!("{}: {e}", out.display()))?;
    Ok(out)
}
