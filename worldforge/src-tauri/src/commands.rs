use serde::Serialize;
use std::fs;
use std::io::{Read, Write};
use std::path::Path;
use zip::write::FileOptions;
use zip::{ZipArchive, ZipWriter};

#[derive(Debug, Serialize)]
pub struct FileEntry {
    pub name: String,
    pub path: String,
    pub is_dir: bool,
}

#[derive(Debug, Serialize)]
pub struct ZipEntryInfo {
    pub name: String,
    pub size: u64,
    pub is_dir: bool,
}

fn norm_err(e: impl std::fmt::Display) -> String {
    e.to_string()
}

/// Returns the running executable's path so the frontend can walk up to auto-detect
/// the project / content root without requiring the user to pick a folder.
#[tauri::command]
pub fn get_exe_path() -> Result<String, String> {
    std::env::current_exe()
        .map(|p| p.to_string_lossy().into_owned())
        .map_err(norm_err)
}

/// Return the value of an environment variable (used for WORLDFORGE_ROOT override).
#[tauri::command]
pub fn get_env_var(name: String) -> Option<String> {
    std::env::var(name).ok()
}

#[tauri::command]
pub fn read_file(path: String) -> Result<String, String> {
    fs::read_to_string(&path).map_err(norm_err)
}

#[tauri::command]
pub fn write_file(path: String, content: String) -> Result<(), String> {
    let p = Path::new(&path);
    if let Some(parent) = p.parent() {
        fs::create_dir_all(parent).map_err(norm_err)?;
    }
    fs::write(p, content.as_bytes()).map_err(norm_err)
}

#[tauri::command]
pub fn delete_file(path: String) -> Result<(), String> {
    fs::remove_file(&path).map_err(norm_err)
}

#[tauri::command]
pub fn list_dir(path: String) -> Result<Vec<FileEntry>, String> {
    let p = Path::new(&path);
    if !p.is_dir() {
        return Err("not_a_directory".into());
    }
    let mut out = Vec::new();
    for ent in fs::read_dir(p).map_err(norm_err)? {
        let ent = ent.map_err(norm_err)?;
        let meta = ent.metadata().map_err(norm_err)?;
        let name = ent.file_name().to_string_lossy().to_string();
        let path_str = ent.path().to_string_lossy().to_string();
        out.push(FileEntry {
            name,
            path: path_str,
            is_dir: meta.is_dir(),
        });
    }
    out.sort_by(|a, b| {
        match (a.is_dir, b.is_dir) {
            (true, false) => std::cmp::Ordering::Less,
            (false, true) => std::cmp::Ordering::Greater,
            _ => a.name.to_lowercase().cmp(&b.name.to_lowercase()),
        }
    });
    Ok(out)
}

#[tauri::command]
pub fn path_exists(path: String) -> Result<bool, String> {
    Ok(Path::new(&path).exists())
}

#[tauri::command]
pub fn create_dir(path: String) -> Result<(), String> {
    fs::create_dir_all(&path).map_err(norm_err)
}

#[tauri::command]
pub fn remove_dir_all(path: String) -> Result<(), String> {
    fs::remove_dir_all(&path).map_err(norm_err)
}

#[tauri::command]
pub fn copy_file(src: String, dest: String) -> Result<(), String> {
    let d = Path::new(&dest);
    if let Some(parent) = d.parent() {
        fs::create_dir_all(parent).map_err(norm_err)?;
    }
    fs::copy(&src, &dest).map_err(norm_err)?;
    Ok(())
}

#[tauri::command]
pub fn write_binary_file(path: String, data: Vec<u8>) -> Result<(), String> {
    let p = Path::new(&path);
    if let Some(parent) = p.parent() {
        fs::create_dir_all(parent).map_err(norm_err)?;
    }
    fs::write(p, data).map_err(norm_err)
}

#[tauri::command]
pub fn read_binary_file(path: String) -> Result<Vec<u8>, String> {
    fs::read(&path).map_err(norm_err)
}

#[tauri::command]
pub fn pick_folder() -> Result<Option<String>, String> {
    let picked = rfd::FileDialog::new().pick_folder();
    Ok(picked.map(|p| p.to_string_lossy().to_string()))
}

#[tauri::command]
pub fn pick_save_path(default_name: String) -> Result<Option<String>, String> {
    let picked = rfd::FileDialog::new()
        .set_file_name(&default_name)
        .save_file();
    Ok(picked.map(|p| p.to_string_lossy().to_string()))
}

#[tauri::command]
pub fn pick_image_file() -> Result<Option<String>, String> {
    let picked = rfd::FileDialog::new()
        .add_filter("Images", &["png", "jpg", "jpeg", "webp"])
        .pick_file();
    Ok(picked.map(|p| p.to_string_lossy().to_string()))
}

#[tauri::command]
pub fn pick_open_file(filters_name: String, extensions: Vec<String>) -> Result<Option<String>, String> {
    let ext_refs: Vec<&str> = extensions.iter().map(|s| s.as_str()).collect();
    let picked = rfd::FileDialog::new()
        .add_filter(&filters_name, &ext_refs)
        .pick_file();
    Ok(picked.map(|p| p.to_string_lossy().to_string()))
}

#[tauri::command]
pub fn export_bundle(file_paths: Vec<String>, dest_path: String, _bundle_name: String) -> Result<(), String> {
    let file = fs::File::create(&dest_path).map_err(norm_err)?;
    let mut zip = ZipWriter::new(file);
    let opts: FileOptions<'_, ()> = FileOptions::default().compression_method(zip::CompressionMethod::Deflated);

    for fp in file_paths {
        let p = Path::new(&fp);
        if !p.is_file() {
            continue;
        }
        let name = p
            .file_name()
            .map(|n| n.to_string_lossy().to_string())
            .unwrap_or_else(|| "file".into());
        zip.start_file(name.clone(), opts).map_err(norm_err)?;
        let mut f = fs::File::open(p).map_err(norm_err)?;
        let mut buf = Vec::new();
        f.read_to_end(&mut buf).map_err(norm_err)?;
        zip.write_all(&buf).map_err(norm_err)?;
    }
    zip.finish().map_err(norm_err)?;
    Ok(())
}

/// Export preserving relative paths under a root directory (e.g. repo root).
#[tauri::command]
pub fn export_bundle_with_root(file_paths: Vec<String>, dest_path: String, root_path: String) -> Result<(), String> {
    let root = Path::new(&root_path).canonicalize().map_err(norm_err)?;
    let file = fs::File::create(&dest_path).map_err(norm_err)?;
    let mut zip = ZipWriter::new(file);
    let opts: FileOptions<'_, ()> = FileOptions::default().compression_method(zip::CompressionMethod::Deflated);

    for fp in file_paths {
        let p = Path::new(&fp).canonicalize().map_err(|e| e.to_string())?;
        if !p.is_file() {
            continue;
        }
        let rel = p.strip_prefix(&root).unwrap_or(&p);
        let entry_name = rel.to_string_lossy().replace('\\', "/");
        zip.start_file(entry_name, opts).map_err(norm_err)?;
        let mut f = fs::File::open(&p).map_err(norm_err)?;
        let mut buf = Vec::new();
        f.read_to_end(&mut buf).map_err(norm_err)?;
        zip.write_all(&buf).map_err(norm_err)?;
    }
    zip.finish().map_err(norm_err)?;
    Ok(())
}

#[tauri::command]
pub fn list_zip_entries(zip_path: String) -> Result<Vec<ZipEntryInfo>, String> {
    let file = fs::File::open(&zip_path).map_err(norm_err)?;
    let mut archive = ZipArchive::new(file).map_err(norm_err)?;
    let mut out = Vec::new();
    for i in 0..archive.len() {
        let ent = archive.by_index(i).map_err(norm_err)?;
        out.push(ZipEntryInfo {
            name: ent.name().to_string(),
            size: ent.size(),
            is_dir: ent.is_dir(),
        });
    }
    Ok(out)
}

fn is_safe_worldforge_extract(name: &str) -> bool {
    if name.is_empty() || name.contains("..") {
        return false;
    }
    let n = name.replace('\\', "/");
    n.starts_with("content/world/") || n == "content/world"
}

#[tauri::command]
pub fn import_bundle(zip_path: String, content_world_root: String) -> Result<Vec<String>, String> {
    let root = Path::new(&content_world_root);
    if !root.is_dir() {
        return Err("content_world_root_not_dir".into());
    }
    let file = fs::File::open(&zip_path).map_err(norm_err)?;
    let mut archive = ZipArchive::new(file).map_err(norm_err)?;
    let mut written = Vec::new();
    for i in 0..archive.len() {
        let mut ent = archive.by_index(i).map_err(norm_err)?;
        let name = ent.name().to_string();
        let norm = name.replace('\\', "/");
        if ent.is_dir() {
            continue;
        }
        if !is_safe_worldforge_extract(&norm) {
            continue;
        }
        let Some(rel) = norm.strip_prefix("content/world/") else {
            continue;
        };
        let dest = root.join(rel);
        if let Some(parent) = dest.parent() {
            fs::create_dir_all(parent).map_err(norm_err)?;
        }
        let mut out = fs::File::create(&dest).map_err(norm_err)?;
        std::io::copy(&mut ent, &mut out).map_err(norm_err)?;
        written.push(dest.to_string_lossy().to_string());
    }
    Ok(written)
}
