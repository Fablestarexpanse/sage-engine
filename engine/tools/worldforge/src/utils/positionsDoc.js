const DOC_KEYS = new Set(["version", "positions", "notes", "reference_image", "muted_edges", "floors"]);

export function parsePositionsDoc(raw) {
  if (!raw || typeof raw !== "object") {
    return {
      version: 2,
      positions: {},
      notes: [],
      muted_edges: [],
      floors: {},
      reference_image: null,
    };
  }
  if (raw.version === 2 && raw.positions && typeof raw.positions === "object") {
    return {
      version: 2,
      positions: { ...raw.positions },
      notes: Array.isArray(raw.notes) ? [...raw.notes] : [],
      muted_edges: Array.isArray(raw.muted_edges) ? [...raw.muted_edges] : [],
      floors: raw.floors && typeof raw.floors === "object" ? { ...raw.floors } : {},
      reference_image: raw.reference_image && typeof raw.reference_image === "object" ? { ...raw.reference_image } : null,
    };
  }
  const positions = {};
  for (const [k, v] of Object.entries(raw)) {
    if (DOC_KEYS.has(k)) continue;
    if (v && typeof v === "object" && "x" in v && "y" in v) {
      positions[k] = { ...v };
    }
  }
  return {
    version: 2,
    positions,
    notes: [],
    muted_edges: [],
    floors: {},
    reference_image: null,
  };
}

export function serializePositionsDoc(doc) {
  const out = {
    version: 2,
    positions: doc.positions || {},
    notes: doc.notes || [],
    muted_edges: doc.muted_edges || [],
    floors: doc.floors || {},
  };
  if (doc.reference_image && typeof doc.reference_image === "object") {
    out.reference_image = doc.reference_image;
  }
  return JSON.stringify(out, null, 2);
}
