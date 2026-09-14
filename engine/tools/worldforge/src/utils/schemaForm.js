/** Helpers for forms generated from the world's content schema (content.schema.json). */

/** Extension fields a kind carries in this world: [{ name, owner, schema }], sorted by name. */
export function extensionsFor(worldSchema, kind) {
  const all = worldSchema?.extensions || {};
  return Object.entries(all)
    .filter(([key]) => key.startsWith(`${kind}.`))
    .map(([key, value]) => ({ name: key.slice(kind.length + 1), owner: value.owner, schema: value.schema }))
    .sort((a, b) => a.name.localeCompare(b.name));
}

/** Follow a local `#/$defs/Name` reference against the extension's root schema. */
export function resolveSchema(schema, root) {
  let node = schema || {};
  const seen = new Set();
  while (node && typeof node.$ref === "string" && !seen.has(node.$ref)) {
    seen.add(node.$ref);
    const name = node.$ref.replace(/^#\/\$defs\//, "");
    node = root?.$defs?.[name] || {};
  }
  return node;
}

/** A starting value for a new block: declared defaults, minimums, empty containers. */
export function defaultFor(schema, root) {
  const node = resolveSchema(schema, root);
  if (node.default !== undefined) return structuredClone(node.default);
  switch (node.type) {
    case "object": {
      if (node.properties) {
        const out = {};
        for (const [key, prop] of Object.entries(node.properties)) {
          const required = (node.required || []).includes(key);
          const resolved = resolveSchema(prop, root);
          // Lists start empty even without a declared default (pydantic omits default_factory).
          if (required || resolved.default !== undefined || resolved.type === "array") out[key] = defaultFor(prop, root);
        }
        return out;
      }
      return {};
    }
    case "array":
      return [];
    case "integer":
    case "number":
      return typeof node.minimum === "number" ? node.minimum : typeof node.exclusiveMinimum === "number" ? node.exclusiveMinimum + 1 : 0;
    case "boolean":
      return false;
    case "string":
      return Array.isArray(node.enum) && node.enum.length ? node.enum[0] : "";
    default:
      return "";
  }
}

/** Parse a number input for a schema type; empty input means "not set". */
export function parseNumber(text, type) {
  if (text === "" || text == null) return undefined;
  const n = Number(text);
  if (!Number.isFinite(n)) return undefined;
  return type === "integer" ? Math.trunc(n) : n;
}
