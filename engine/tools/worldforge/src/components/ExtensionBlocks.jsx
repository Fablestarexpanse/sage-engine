import { useMemo } from "react";
import { useTheme } from "../ThemeContext.jsx";
import { roomPanelChrome } from "../panels/roomPanelChrome.js";
import { defaultFor, extensionsFor, parseNumber, resolveSchema } from "../utils/schemaForm.js";

/**
 * Forms for the plugin fields a content object may carry (room.shop, feature.search, item.slot ...),
 * generated from the world's content schema. `doc` is the object; `onChange` gets a new object.
 * `choices` offers value lists for specific fields, e.g. { slot: ["hand", "body"] }.
 */
export default function ExtensionBlocks({ worldSchema, kind, doc, onChange, choices = {}, emptyNote }) {
  const { colors: COLORS } = useTheme();
  const chrome = useMemo(() => roomPanelChrome(COLORS), [COLORS]);
  const blocks = useMemo(() => extensionsFor(worldSchema, kind), [worldSchema, kind]);
  if (!worldSchema) {
    return (
      <p style={{ fontSize: 11, color: COLORS.textMuted, lineHeight: 1.45 }}>
        This folder has no content.schema.json, so plugin fields can only be edited in the YAML tab.
      </p>
    );
  }
  if (!blocks.length) {
    return emptyNote ? <p style={{ fontSize: 11, color: COLORS.textMuted }}>{emptyNote}</p> : null;
  }
  const value = doc || {};
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {blocks.map(({ name, owner, schema }) => {
        const present = value[name] !== undefined;
        return (
          <div key={name} style={{ padding: 8, borderRadius: 8, background: COLORS.bgCard, border: `1px solid ${COLORS.border}` }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 8 }}>
              <strong style={{ fontSize: 12, color: COLORS.text }}>{name}</strong>
              <span style={{ fontSize: 10, color: COLORS.textDim }}>plugin: {owner}</span>
            </div>
            {schema.description ? (
              <p style={{ fontSize: 10, color: COLORS.textMuted, margin: "4px 0", lineHeight: 1.4 }}>{schema.description.replace(/`/g, "")}</p>
            ) : null}
            {present ? (
              <>
                <SchemaField
                  schema={schema}
                  root={schema}
                  value={value[name]}
                  choices={choices[name]}
                  onChange={(next) => onChange({ ...value, [name]: next })}
                  chrome={chrome}
                  COLORS={COLORS}
                />
                <button
                  type="button"
                  style={{ ...chrome.btnDanger, marginTop: 6 }}
                  onClick={() => {
                    const { [name]: _removed, ...rest } = value;
                    onChange(rest);
                  }}
                >
                  Remove {name}
                </button>
              </>
            ) : (
              <button
                type="button"
                style={{ ...chrome.btn, marginTop: 4 }}
                onClick={() => {
                  const start = choices[name]?.length ? choices[name][0] : defaultFor(schema, schema);
                  onChange({ ...value, [name]: start });
                }}
              >
                + Add {name}
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}

function SchemaField({ schema, root, value, onChange, choices, chrome, COLORS, label }) {
  const node = resolveSchema(schema, root);
  const { lbl, inp, btn, btnDanger } = chrome;
  const title = label ?? node.title;
  const heading = title ? <label style={lbl}>{title}</label> : null;

  if (choices?.length || Array.isArray(node.enum)) {
    const options = choices?.length ? choices : node.enum;
    const list = value !== undefined && value !== "" && !options.includes(value) ? [...options, value] : options;
    return (
      <>
        {heading}
        <select style={inp} value={value ?? ""} onChange={(e) => onChange(e.target.value)}>
          {list.map((o) => (
            <option key={String(o)} value={o}>
              {String(o)}
            </option>
          ))}
        </select>
      </>
    );
  }

  if (node.type === "object" && node.properties) {
    const obj = value && typeof value === "object" && !Array.isArray(value) ? value : {};
    return (
      <div style={{ paddingLeft: title && label !== undefined ? 8 : 0 }}>
        {label !== undefined ? heading : null}
        {Object.entries(node.properties).map(([key, prop]) => (
          <SchemaField
            key={key}
            schema={prop}
            root={root}
            label={`${resolveSchema(prop, root).title || key}${(node.required || []).includes(key) ? " *" : ""}`}
            value={obj[key]}
            onChange={(next) => {
              const out = { ...obj };
              if (next === undefined) delete out[key];
              else out[key] = next;
              onChange(out);
            }}
            chrome={chrome}
            COLORS={COLORS}
          />
        ))}
      </div>
    );
  }

  if (node.type === "object" && node.additionalProperties) {
    const obj = value && typeof value === "object" && !Array.isArray(value) ? value : {};
    const itemSchema = node.additionalProperties;
    const entries = Object.entries(obj);
    return (
      <>
        {heading}
        {entries.map(([key, v], i) => (
          <div key={i} style={{ display: "flex", gap: 6, alignItems: "center", marginTop: 4 }}>
            <input
              style={{ ...inp, flex: 2 }}
              value={key}
              placeholder="key"
              onChange={(e) => {
                const rebuilt = {};
                entries.forEach(([k, val], j) => {
                  rebuilt[j === i ? e.target.value : k] = val;
                });
                onChange(rebuilt);
              }}
            />
            <div style={{ flex: 1 }}>
              <SchemaField
                schema={itemSchema}
                root={root}
                label=""
                value={v}
                onChange={(next) => onChange({ ...obj, [key]: next })}
                chrome={chrome}
                COLORS={COLORS}
              />
            </div>
            <button
              type="button"
              style={btnDanger}
              onClick={() => {
                const { [key]: _gone, ...rest } = obj;
                onChange(rest);
              }}
            >
              ✕
            </button>
          </div>
        ))}
        <button type="button" style={{ ...btn, marginTop: 4 }} onClick={() => onChange({ ...obj, [`new_${entries.length + 1}`]: defaultFor(itemSchema, root) })}>
          + entry
        </button>
      </>
    );
  }

  if (node.type === "array") {
    const list = Array.isArray(value) ? value : [];
    const itemSchema = node.items || {};
    const itemNode = resolveSchema(itemSchema, root);
    return (
      <>
        {heading}
        {list.map((item, i) => (
          <div key={i} style={{ display: "flex", gap: 6, alignItems: "flex-start", marginTop: 4, padding: itemNode.type === "object" ? 6 : 0, border: itemNode.type === "object" ? `1px dashed ${COLORS.border}` : "none", borderRadius: 6 }}>
            <div style={{ flex: 1 }}>
              <SchemaField
                schema={itemSchema}
                root={root}
                value={item}
                onChange={(next) => {
                  const out = [...list];
                  out[i] = next;
                  onChange(out);
                }}
                chrome={chrome}
                COLORS={COLORS}
              />
            </div>
            <button type="button" style={btnDanger} onClick={() => onChange(list.filter((_, j) => j !== i))}>
              ✕
            </button>
          </div>
        ))}
        <button type="button" style={{ ...btn, marginTop: 4 }} onClick={() => onChange([...list, defaultFor(itemSchema, root)])}>
          + {itemNode.title || "item"}
        </button>
      </>
    );
  }

  if (node.type === "integer" || node.type === "number") {
    return (
      <>
        {heading}
        <input
          type="number"
          step={node.type === "integer" ? 1 : "any"}
          style={inp}
          value={value ?? ""}
          onChange={(e) => onChange(parseNumber(e.target.value, node.type))}
        />
      </>
    );
  }

  if (node.type === "boolean") {
    return (
      <label style={{ ...lbl, display: "flex", gap: 6, alignItems: "center" }}>
        <input type="checkbox" checked={Boolean(value)} onChange={(e) => onChange(e.target.checked)} />
        {title}
      </label>
    );
  }

  const long = /description|lines?$/i.test(String(title || ""));
  return (
    <>
      {heading}
      {long ? (
        <textarea style={{ ...inp, minHeight: 50 }} value={value ?? ""} onChange={(e) => onChange(e.target.value)} />
      ) : (
        <input style={inp} value={value ?? ""} onChange={(e) => onChange(e.target.value)} />
      )}
    </>
  );
}
