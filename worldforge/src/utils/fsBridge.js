import { invoke } from "@tauri-apps/api/core";
import yaml from "js-yaml";

export async function getExePath() {
  return invoke("get_exe_path");
}

export async function getEnvVar(name) {
  return invoke("get_env_var", { name });
}

export async function readYaml(path) {
  const text = await invoke("read_file", { path });
  return yaml.load(text);
}

export async function writeYaml(path, data) {
  const text = yaml.dump(data, { lineWidth: 120, quotingType: '"', noRefs: true });
  await invoke("write_file", { path, content: text });
}

export async function readText(path) {
  return invoke("read_file", { path });
}

export async function writeText(path, content) {
  return invoke("write_file", { path, content });
}

export async function deleteFile(path) {
  return invoke("delete_file", { path });
}

export async function listDir(path) {
  return invoke("list_dir", { path });
}

export async function pathExists(path) {
  return invoke("path_exists", { path });
}

export async function createDir(path) {
  return invoke("create_dir", { path });
}

export async function removeDirAll(path) {
  return invoke("remove_dir_all", { path });
}

export async function copyFile(src, dest) {
  return invoke("copy_file", { src, dest });
}

export async function pickFolder() {
  return invoke("pick_folder");
}

export async function pickSavePath(defaultName) {
  return invoke("pick_save_path", { defaultName });
}

export async function pickImageFile() {
  return invoke("pick_image_file");
}

export async function pickOpenFile(filtersName, extensions) {
  return invoke("pick_open_file", { filtersName, extensions });
}

export async function readBinaryFile(path) {
  return invoke("read_binary_file", { path });
}

export async function writeBinaryFile(path, data) {
  return invoke("write_binary_file", { path, data });
}

export async function exportBundle(filePaths, destPath, bundleName) {
  return invoke("export_bundle", { filePaths, destPath, bundleName });
}

export async function exportBundleWithRoot(filePaths, destPath, rootPath) {
  return invoke("export_bundle_with_root", { filePaths, destPath, rootPath });
}

export async function listZipEntries(zipPath) {
  return invoke("list_zip_entries", { zipPath });
}

export async function importBundle(zipPath, contentWorldRoot) {
  return invoke("import_bundle", { zipPath, contentWorldRoot });
}
