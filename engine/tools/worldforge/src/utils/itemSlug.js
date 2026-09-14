/** Slug for item id: [a-zA-Z0-9_-]+ */
const ID_RE = /^[a-zA-Z0-9_-]+$/;

/**
 * Turn a display string into a filesystem-safe item id base.
 * @param {string} name
 * @returns {string}
 */
export function slugifyItemId(name) {
  let s = String(name || "")
    .trim()
    .toLowerCase()
    .replace(/['"]/g, "")
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_|_$/g, "");
  if (!s) s = "item";
  if (!/^[a-z]/.test(s)) s = `i_${s}`;
  if (!ID_RE.test(s)) s = "item";
  return s.slice(0, 80);
}

/**
 * @param {Set<string>|string[]} existingIds
 * @param {string} base
 * @returns {string}
 */
export function nextAvailableItemId(existingIds, base) {
  const set = existingIds instanceof Set ? existingIds : new Set(existingIds || []);
  let b = slugifyItemId(base);
  if (!ID_RE.test(b)) b = "item";
  if (!set.has(b)) return b;
  for (let i = 2; i < 10000; i++) {
    const c = `${b}_${i}`;
    if (!set.has(c)) return c;
  }
  return `${b}_${Date.now().toString(36)}`;
}
