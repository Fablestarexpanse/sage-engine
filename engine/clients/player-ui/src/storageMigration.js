// One-time rename of browser storage keys from the pre-SAGE "fablestar_" prefix, so a
// signed-in admin stays signed in and saved preferences survive the engine rename.
// Safe to delete one release after the rename (docs/sage/PHASE1_CONTRACTS.md F.1).
export const RENAMED_KEYS = [
  ["fablestar_admin_token", "sage_admin_token"],
  ["fablestar_admin_ui_theme", "sage_admin_ui_theme"],
  ["fablestar_player_ui_theme", "sage_player_ui_theme"],
  ["fablestar_narrative_portrait_backdrop_on", "sage_narrative_portrait_backdrop_on"],
  ["fablestar_narrative_portrait_backdrop_opacity", "sage_narrative_portrait_backdrop_opacity"],
  ["fablestar_narrative_portrait_backdrop_scale", "sage_narrative_portrait_backdrop_scale"],
  ["fablestar_narrative_portrait_backdrop_x_offset", "sage_narrative_portrait_backdrop_x_offset"],
];

export function migrateStorageKeys(storage, pairs = RENAMED_KEYS) {
  for (const [oldKey, newKey] of pairs) {
    try {
      const value = storage.getItem(oldKey);
      if (value === null) continue;
      if (storage.getItem(newKey) === null) storage.setItem(newKey, value);
      storage.removeItem(oldKey);
    } catch {
      /* storage unavailable (private mode, blocked site data) — nothing to migrate */
    }
  }
}

try {
  migrateStorageKeys(window.localStorage);
} catch {
  /* no localStorage */
}
