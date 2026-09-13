/** Join path segments using the same separator as `root` (Windows vs POSIX). */
export function joinPaths(root, ...segments) {
  if (!root) return segments.filter(Boolean).join("/");
  const sep = root.includes("\\") ? "\\" : "/";
  let out = root.replace(/[/\\]+$/, "");
  for (const s of segments) {
    if (s == null || s === "") continue;
    const t = String(s).replace(/^[/\\]+/, "").replace(/\//g, sep);
    out = `${out}${sep}${t}`;
  }
  return out;
}
