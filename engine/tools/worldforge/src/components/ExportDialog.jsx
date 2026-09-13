import { useEffect, useMemo, useState } from "react";
import { joinPaths } from "../utils/paths.js";
import { useTheme } from "../ThemeContext.jsx";
import * as fs from "../utils/fsBridge.js";
import { listStampSlugs } from "../utils/stampBundle.js";
import { useContent } from "../hooks/useContentStore.js";

const row = { display: "flex", alignItems: "center", gap: 8, fontSize: 12, marginTop: 4 };

export default function ExportDialog({ worldRoot, contentRoot, zoneIds, systemIds, entityIds, itemIds, glyphIds, onClose }) {
  const { colors: COLORS } = useTheme();
  const btn = useMemo(
    () => ({
      padding: "8px 14px",
      borderRadius: 6,
      border: `1px solid ${COLORS.border}`,
      background: COLORS.bgCard,
      color: COLORS.text,
      cursor: "pointer",
      fontSize: 12,
    }),
    [COLORS]
  );
  const [z, setZ] = useState(() => Object.fromEntries(zoneIds.map((id) => [id, true])));
  const [s, setS] = useState(() => Object.fromEntries(systemIds.map((id) => [id, true])));
  const [e, setE] = useState(() => Object.fromEntries(entityIds.map((id) => [id, true])));
  const [i, setI] = useState(() => Object.fromEntries(itemIds.map((id) => [id, true])));
  const [g, setG] = useState(() => Object.fromEntries(glyphIds.map((id) => [id, true])));
  const [gal, setGal] = useState(true);
  const [stampIds, setStampIds] = useState([]);
  const [st, setSt] = useState({});
  const { loadAll } = useContent();

  useEffect(() => {
    let alive = true;
    listStampSlugs(worldRoot)
      .then((slugs) => {
        if (!alive) return;
        setStampIds(slugs);
        setSt(Object.fromEntries(slugs.map((id) => [id, true])));
      })
      .catch((e) => setMsg(`Stamp list failed: ${e}`));
    return () => {
      alive = false;
    };
  }, [worldRoot]);
  const [msg, setMsg] = useState("");
  const [importPreview, setImportPreview] = useState(null);

  const paths = useMemo(() => {
    const out = [];
    if (gal) out.push(joinPaths(worldRoot, "galaxy.yaml"));
    for (const id of zoneIds) {
      if (!z[id]) continue;
      out.push(joinPaths(worldRoot, "zones", id));
    }
    for (const id of systemIds) {
      if (!s[id]) continue;
      out.push(joinPaths(worldRoot, "systems", `${id}.yaml`));
    }
    for (const id of entityIds) {
      if (!e[id]) continue;
      out.push(joinPaths(worldRoot, "entities", `${id}.yaml`));
    }
    for (const id of itemIds) {
      if (!i[id]) continue;
      out.push(joinPaths(worldRoot, "items", `${id}.yaml`));
    }
    for (const id of glyphIds) {
      if (!g[id]) continue;
      out.push(joinPaths(worldRoot, "glyphs", `${id}.yaml`));
    }
    for (const id of stampIds) {
      if (!st[id]) continue;
      out.push(joinPaths(worldRoot, "stamps", id));
    }
    return out;
  }, [worldRoot, zoneIds, systemIds, entityIds, itemIds, glyphIds, stampIds, z, s, e, i, g, st, gal]);

  const collectFiles = async () => {
    const files = [];
    for (const p of paths) {
      if (await fs.pathExists(p)) {
        const st = await fs.listDir(p).catch(() => null);
        if (st) {
          const stack = [...st];
          while (stack.length) {
            const ent = stack.pop();
            if (ent.is_dir) {
              const kids = await fs.listDir(ent.path);
              stack.push(...kids);
            } else if (ent.name.endsWith(".yaml") || ent.name.endsWith(".json")) {
              files.push(ent.path);
            }
          }
        } else {
          files.push(p);
        }
      }
    }
    return files;
  };

  const doExport = async () => {
    const files = await collectFiles();
    const dest = await fs.pickSavePath("world_bundle.zip");
    if (!dest) return;
    await fs.exportBundleWithRoot(files, dest, contentRoot);
    setMsg(`Exported ${files.length} files`);
  };

  const doImportPick = async () => {
    const zip = await fs.pickOpenFile("Zip", ["zip"]);
    if (!zip) return;
    const entries = await fs.listZipEntries(zip);
    setImportPreview({ zip, entries });
  };

  const doImportConfirm = async () => {
    if (!importPreview?.zip) return;
    const written = await fs.importBundle(importPreview.zip, contentRoot);
    setMsg(`Imported ${written.length} files`);
    setImportPreview(null);
    onClose();
    await loadAll(contentRoot);
  };

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        background: `${COLORS.bg}ee`,
        zIndex: 100,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 24,
      }}
      onMouseDown={onClose}
    >
      <div
        style={{
          width: "min(720px, 100%)",
          minHeight: 500,
          background: COLORS.bgPanel,
          border: `1px solid ${COLORS.border}`,
          borderRadius: 12,
          padding: 20,
          color: COLORS.text,
        }}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <h2 style={{ marginTop: 0, fontSize: 18 }}>Export bundle</h2>
        <div style={{ fontSize: 12, color: COLORS.textMuted, marginBottom: 12 }}>Select content to include (paths under content/world).</div>
        <label style={row}><input type="checkbox" checked={gal} onChange={(ev) => setGal(ev.target.checked)} /> galaxy.yaml</label>
        <div style={{ marginTop: 8, fontWeight: 600, fontSize: 12 }}>Zones (folders)</div>
        {zoneIds.map((id) => (
          <label key={id} style={row}><input type="checkbox" checked={!!z[id]} onChange={(ev) => setZ({ ...z, [id]: ev.target.checked })} /> {id}</label>
        ))}
        <div style={{ marginTop: 8, fontWeight: 600, fontSize: 12 }}>Systems</div>
        {systemIds.map((id) => (
          <label key={id} style={row}><input type="checkbox" checked={!!s[id]} onChange={(ev) => setS({ ...s, [id]: ev.target.checked })} /> {id}</label>
        ))}
        <div style={{ marginTop: 8, fontWeight: 600, fontSize: 12 }}>Entities</div>
        <div style={{ maxHeight: 100, overflow: "auto" }}>
          {entityIds.map((id) => (
            <label key={id} style={row}><input type="checkbox" checked={!!e[id]} onChange={(ev) => setE({ ...e, [id]: ev.target.checked })} /> {id}</label>
          ))}
        </div>
        <div style={{ marginTop: 8, fontWeight: 600, fontSize: 12 }}>Items</div>
        <div style={{ maxHeight: 100, overflow: "auto" }}>
          {itemIds.map((id) => (
            <label key={id} style={row}><input type="checkbox" checked={!!i[id]} onChange={(ev) => setI({ ...i, [id]: ev.target.checked })} /> {id}</label>
          ))}
        </div>
        <div style={{ marginTop: 8, fontWeight: 600, fontSize: 12 }}>Glyphs</div>
        <div style={{ maxHeight: 100, overflow: "auto" }}>
          {glyphIds.map((id) => (
            <label key={id} style={row}><input type="checkbox" checked={!!g[id]} onChange={(ev) => setG({ ...g, [id]: ev.target.checked })} /> {id}</label>
          ))}
        </div>
        <div style={{ marginTop: 8, fontWeight: 600, fontSize: 12 }}>Stamps</div>
        <div style={{ maxHeight: 100, overflow: "auto" }}>
          {stampIds.map((id) => (
            <label key={id} style={row}><input type="checkbox" checked={!!st[id]} onChange={(ev) => setSt({ ...st, [id]: ev.target.checked })} /> {id}</label>
          ))}
        </div>
        <div style={{ marginTop: 16, display: "flex", gap: 8 }}>
          <button type="button" style={btn} onClick={doExport}>Export ZIP</button>
          <button type="button" style={btn} onClick={onClose}>Close</button>
        </div>
        {msg ? <div style={{ marginTop: 12, fontSize: 12, color: COLORS.success }}>{msg}</div> : null}

        <h3 style={{ marginTop: 24, fontSize: 14 }}>Import bundle</h3>
        <button type="button" style={btn} onClick={doImportPick}>Choose .zip</button>
        {importPreview ? (
          <div style={{ marginTop: 12, fontSize: 11, color: COLORS.textMuted, maxHeight: 120, overflow: "auto" }}>
            {importPreview.entries.map((en, idx) => (
              <div key={idx}>{en.name}</div>
            ))}
            <button type="button" style={{ ...btn, marginTop: 8 }} onClick={doImportConfirm}>Confirm import</button>
          </div>
        ) : null}
      </div>
    </div>
  );
}
