import { invoke } from "@tauri-apps/api/core";
import yaml from "js-yaml";

/** @returns {Promise<string>} Absolute path to the running Tauri executable. */
export async function getExePath() {
  return invoke("get_exe_path");
}

/**
 * @param {string} name Environment variable name.
 * @returns {Promise<string|null>} The value, or null if unset.
 */
export async function getEnvVar(name) {
  return invoke("get_env_var", { name });
}

/**
 * Read a file and parse it as YAML.
 * @param {string} path Absolute file path.
 * @returns {Promise<any>} The parsed YAML document.
 */
export async function readYaml(path) {
  const text = await invoke("read_file", { path });
  return yaml.load(text);
}

/**
 * Serialize a value to YAML and write it to disk.
 * @param {string} path Absolute file path.
 * @param {any} data Value to serialize with js-yaml.
 * @returns {Promise<void>}
 */
export async function writeYaml(path, data) {
  const text = yaml.dump(data, { lineWidth: 120, quotingType: '"', noRefs: true });
  await invoke("write_file", { path, content: text });
}

/**
 * @param {string} path Absolute file path.
 * @returns {Promise<string>} Raw file contents.
 */
export async function readText(path) {
  return invoke("read_file", { path });
}

/**
 * @param {string} path Absolute file path.
 * @param {string} content Text to write.
 * @returns {Promise<void>}
 */
export async function writeText(path, content) {
  return invoke("write_file", { path, content });
}

/**
 * @param {string} path Absolute file path to remove.
 * @returns {Promise<void>}
 */
export async function deleteFile(path) {
  return invoke("delete_file", { path });
}

/**
 * @param {string} path Absolute directory path.
 * @returns {Promise<{name: string, path: string, is_dir: boolean}[]>} Directory entries.
 */
export async function listDir(path) {
  return invoke("list_dir", { path });
}

/**
 * @param {string} path Absolute path to check.
 * @returns {Promise<boolean>} Whether the path exists.
 */
export async function pathExists(path) {
  return invoke("path_exists", { path });
}

/**
 * Create a directory, including any missing parent directories.
 * @param {string} path Absolute directory path.
 * @returns {Promise<void>}
 */
export async function createDir(path) {
  return invoke("create_dir", { path });
}

/**
 * Recursively remove a directory and everything under it.
 * @param {string} path Absolute directory path.
 * @returns {Promise<void>}
 */
export async function removeDirAll(path) {
  return invoke("remove_dir_all", { path });
}

/**
 * @param {string} src Absolute source file path.
 * @param {string} dest Absolute destination file path.
 * @returns {Promise<void>}
 */
export async function copyFile(src, dest) {
  return invoke("copy_file", { src, dest });
}

/** @returns {Promise<string|null>} The picked folder path, or null if the user cancelled. */
export async function pickFolder() {
  return invoke("pick_folder");
}

/**
 * @param {string} defaultName Suggested file name for the save dialog.
 * @returns {Promise<string|null>} The chosen save path, or null if cancelled.
 */
export async function pickSavePath(defaultName) {
  return invoke("pick_save_path", { defaultName });
}

/** @returns {Promise<string|null>} The picked image file path, or null if cancelled. */
export async function pickImageFile() {
  return invoke("pick_image_file");
}

/**
 * @param {string} filtersName Label shown for the file-type filter.
 * @param {string[]} extensions Allowed extensions (without leading dots).
 * @returns {Promise<string|null>} The picked file path, or null if cancelled.
 */
export async function pickOpenFile(filtersName, extensions) {
  return invoke("pick_open_file", { filtersName, extensions });
}

/**
 * @param {string} path Absolute file path.
 * @returns {Promise<Uint8Array>} Raw file bytes.
 */
export async function readBinaryFile(path) {
  return invoke("read_binary_file", { path });
}

/**
 * @param {string} path Absolute file path.
 * @param {Uint8Array|number[]} data Bytes to write.
 * @returns {Promise<void>}
 */
export async function writeBinaryFile(path, data) {
  return invoke("write_binary_file", { path, data });
}

/**
 * Zip a flat list of files into a bundle, keyed by file name only.
 * @param {string[]} filePaths Absolute paths of files to include.
 * @param {string} destPath Absolute path for the output .zip.
 * @param {string} bundleName Logical bundle name (unused by the backend currently).
 * @returns {Promise<void>}
 */
export async function exportBundle(filePaths, destPath, bundleName) {
  return invoke("export_bundle", { filePaths, destPath, bundleName });
}

/**
 * Zip files preserving their paths relative to a root directory.
 * @param {string[]} filePaths Absolute paths of files to include.
 * @param {string} destPath Absolute path for the output .zip.
 * @param {string} rootPath Root directory paths are made relative to.
 * @returns {Promise<void>}
 */
export async function exportBundleWithRoot(filePaths, destPath, rootPath) {
  return invoke("export_bundle_with_root", { filePaths, destPath, rootPath });
}

/**
 * @param {string} zipPath Absolute path to a .zip file.
 * @returns {Promise<{name: string, size: number, is_dir: boolean}[]>} Entries in the archive.
 */
export async function listZipEntries(zipPath) {
  return invoke("list_zip_entries", { zipPath });
}

/**
 * Extract a WorldForge export bundle's `content/world/*` entries into a world root.
 * @param {string} zipPath Absolute path to the .zip file.
 * @param {string} contentWorldRoot Absolute destination world root directory.
 * @returns {Promise<string[]>} Absolute paths written.
 */
export async function importBundle(zipPath, contentWorldRoot) {
  return invoke("import_bundle", { zipPath, contentWorldRoot });
}
