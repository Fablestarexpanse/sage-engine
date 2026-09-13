/** Deep clone for plain JSON data (room docs, drafts, positions).
 * One shared helper instead of inline JSON.parse(JSON.stringify(...)) at every
 * call site; structuredClone is faster and handles more, but our data is pure
 * JSON from YAML so the JSON round-trip stays the single, predictable contract.
 */
export function deepClone(value) {
  if (value == null) return value;
  return JSON.parse(JSON.stringify(value));
}
