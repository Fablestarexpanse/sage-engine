import { useCallback, useEffect, useRef } from "react";
import { joinPaths } from "../utils/paths.js";
import { parsePositionsDoc, serializePositionsDoc } from "../utils/positionsDoc.js";
import { deepClone } from "../utils/clone.js";
import * as fs from "../utils/fsBridge.js";

const DEFAULT_UNDO_LIMIT = 40;

function clonePositionsDoc(doc) {
  return deepClone(doc ?? parsePositionsDoc(null));
}

/**
 * ZoneEditor's undo stack: a capped LIFO of layout/room-creation snapshots
 * (see push sites in ZoneEditor for the entry shapes — "duplicate",
 * "stampPlace", "layout", "clearConnections"). Extracted verbatim from
 * ZoneEditor's undoStackRef + applyUndo so the entry shapes and restore
 * behavior are unchanged; the stack itself resets whenever `zoneId` changes,
 * matching the original per-zone-visit reset.
 *
 * Returns { push(entry), undo(), canUndo() }.
 */
export function useUndoStack({ zoneId, worldRoot, dispatch, positionsPath, setPositionsDoc, setStatusMsg, limit = DEFAULT_UNDO_LIMIT }) {
  const stackRef = useRef([]);

  useEffect(() => {
    stackRef.current = [];
  }, [zoneId]);

  const push = useCallback(
    (entry) => {
      stackRef.current.push(entry);
      if (stackRef.current.length > limit) stackRef.current.shift();
    },
    [limit]
  );

  const canUndo = useCallback(() => stackRef.current.length > 0, []);

  const undo = useCallback(async () => {
    const stack = stackRef.current;
    if (!stack.length) {
      setStatusMsg("Nothing to undo");
      return;
    }
    const entry = stack.pop();
    if (entry.type === "duplicate" || entry.type === "stampPlace") {
      for (const slug of entry.createdSlugs) {
        try {
          await fs.deleteFile(joinPaths(worldRoot, "zones", zoneId, "rooms", `${slug}.yaml`));
        } catch {
          /* missing file */
        }
        dispatch({ type: "DELETE_ZONE_ROOM", zoneId, slug });
      }
      const restored = clonePositionsDoc(entry.prevPositionsDoc);
      setPositionsDoc(restored);
      await fs.writeText(positionsPath, serializePositionsDoc(restored));
      setStatusMsg(
        entry.type === "stampPlace"
          ? `Undid stamp placement (${entry.createdSlugs.length} room(s))`
          : `Undid duplicate (${entry.createdSlugs.length} room(s))`
      );
    } else if (entry.type === "layout") {
      const restored = clonePositionsDoc(entry.prevPositionsDoc);
      setPositionsDoc(restored);
      await fs.writeText(positionsPath, serializePositionsDoc(restored));
      setStatusMsg("Undid layout / rotate / map border");
    } else if (entry.type === "clearConnections") {
      for (const [slug, data] of Object.entries(entry.prevRooms || {})) {
        dispatch({ type: "UPDATE_ZONE_ROOM", zoneId, slug, data });
        await fs.writeYaml(joinPaths(worldRoot, "zones", zoneId, "rooms", `${slug}.yaml`), data);
      }
      const restored = clonePositionsDoc(entry.prevPositionsDoc);
      setPositionsDoc(restored);
      await fs.writeText(positionsPath, serializePositionsDoc(restored));
      setStatusMsg("Undid clear all connections");
    }
  }, [zoneId, worldRoot, dispatch, positionsPath, setPositionsDoc, setStatusMsg]);

  return { push, undo, canUndo };
}
