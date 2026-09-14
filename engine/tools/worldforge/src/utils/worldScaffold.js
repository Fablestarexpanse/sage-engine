import yaml from "js-yaml";
import { joinPaths } from "./paths.js";
import * as fs from "./fsBridge.js";

async function yamlFilesInDir(dirPath) {
  if (!(await fs.pathExists(dirPath))) return 0;
  const entries = await fs.listDir(dirPath);
  return entries.filter((e) => !e.is_dir && e.name.toLowerCase().endsWith(".yaml")).length;
}

/** True if there is any game-facing YAML under content/world (zones, entities, items). */
export async function hasAnyWorldContent(worldRoot) {
  if (await fs.pathExists(worldRoot)) {
    const entries = await fs.listDir(worldRoot);
    for (const e of entries) {
      if (!e.is_dir && e.name.toLowerCase().endsWith(".yaml")) return true;
    }
  }
  if ((await yamlFilesInDir(joinPaths(worldRoot, "entities"))) > 0) return true;
  if ((await yamlFilesInDir(joinPaths(worldRoot, "items"))) > 0) return true;

  const zonesRoot = joinPaths(worldRoot, "zones");
  if (!(await fs.pathExists(zonesRoot))) return false;
  const zdirs = await fs.listDir(zonesRoot);
  for (const d of zdirs) {
    if (!d.is_dir) continue;
    const roomsDir = joinPaths(d.path, "rooms");
    if ((await yamlFilesInDir(roomsDir)) > 0) return true;
  }
  return false;
}

const STARTER_ZONE = "starter_zone";

/** Resolve the world root from whatever root the caller has, without double-appending.
 * Historical bug: blindly appending "content/world" to a picked folder that already
 * WAS content/world produced a nested content/world/content/world tree. */
function resolveScaffoldWorldRoot(root) {
  const norm = String(root || "").replace(/\\/g, "/").replace(/\/+$/, "");
  if (norm.endsWith("/content/world")) return root;
  if (norm.endsWith("/content")) return joinPaths(root, "world");
  return joinPaths(root, "content", "world");
}

/** Create content/world layout + starter zone (skips files that already exist). */
export async function createWorldScaffold(contentRoot) {
  const worldRoot = resolveScaffoldWorldRoot(contentRoot);

  await fs.createDir(worldRoot);
  await fs.createDir(joinPaths(worldRoot, "zones"));
  await fs.createDir(joinPaths(worldRoot, "stamps"));
  await fs.createDir(joinPaths(worldRoot, "entities"));
  await fs.createDir(joinPaths(worldRoot, "items"));

  const zoneRoot = joinPaths(worldRoot, "zones", STARTER_ZONE);
  const roomsDir = joinPaths(zoneRoot, "rooms");
  const entrancePath = joinPaths(roomsDir, "entrance.yaml");

  if (!(await fs.pathExists(entrancePath))) {
    await fs.createDir(roomsDir);
    // Matches the server's ZoneModel shape (id/name/description required).
    const zoneMeta = {
      id: STARTER_ZONE,
      name: "Starter Zone",
      description: "The first zone of a new world.",
      depth_range: [1, 3],
      type: "exploration",
      status: "active",
    };
    await fs.writeText(joinPaths(zoneRoot, "zone.yaml"), yaml.dump(zoneMeta, { lineWidth: 120, quotingType: '"', noRefs: true }));

    const entrance = {
      id: `${STARTER_ZONE}:entrance`,
      zone: STARTER_ZONE,
      type: "hub",
      depth: 1,
      description: { base: "The starting point of your new world." },
      exits: {},
      features: [],
      entity_spawns: [],
      hazards: [],
      tags: [],
    };
    await fs.writeYaml(entrancePath, entrance);
  }
}
