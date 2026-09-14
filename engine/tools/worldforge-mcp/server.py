"""
WorldForge MCP Server — exposes map-building tools so Claude can create and edit
zone layouts, rooms, exits, and floor assignments directly.

Usage:
  python worldforge-mcp/server.py

Environment:
  WORLDFORGE_ROOT  Path to content/world (the directory that contains zones/).
                   Defaults to ./content/world relative to the project root.
"""

from __future__ import annotations

import json
import os
import tempfile
import os
import re
from pathlib import Path
from typing import Any

import yaml
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "WorldForge",
    instructions="""
WorldForge map-building tools for SAGE worlds.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
THE FUNDAMENTAL MUD MAP RULE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Each room has EXACTLY ONE exit per direction.
A room cannot have two "north" exits. North goes to one room, period.

This single rule governs all MUD map design. Every layout decision flows
from it. Think of rooms as nodes in a directed graph — each direction is
a labelled edge and each edge connects exactly two nodes.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HOW TO BUILD REAL SPACES (THE HALLWAY PROBLEM)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Real buildings have many rooms off a single corridor. In a MUD you cannot
branch multiple rooms off ONE corridor room in the same direction. You need
one corridor/hallway room per branch point.

WRONG — apartment block with one hallway room:
  hallway: north→apt1, south→apt2
  (only 2 apartments total — hallway is used up)

RIGHT — apartment block with a corridor of hallway rooms:
  entrance → hallway_a → hallway_b → hallway_c → hallway_d
  hallway_a: north→apt_1,  south→apt_2,  east→hallway_b
  hallway_b: north→apt_3,  south→apt_4,  east→hallway_c, west→hallway_a
  hallway_c: north→apt_5,  south→apt_6,  east→hallway_d, west→hallway_b
  hallway_d: north→apt_7,  south→apt_8,  west→hallway_c

This gives 8 apartments. The corridor itself is 4 rooms running east-west,
each with one apartment branching north and one branching south.

RULE OF THUMB: count how many side-rooms you need, then divide by 2 to get
the number of corridor segments (one room north + one south per segment).

More examples of the same principle:
  • A space-station ring corridor: 6 corridor rooms in a loop, each with an
    inner room branching inward → 6 inner rooms from 6 corridor rooms.
  • A dungeon with cells: 1 guard room, 3 corridor rooms east-west, each
    corridor has a cell to the north → 3 cells total.
  • A city street: 5 street rooms running north-south; east side has shops
    (1 per street room), west side has houses (1 per street room) → 10 units.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COMMON MUD LAYOUT PATTERNS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Plan the right pattern for the space BEFORE placing rooms.

1. LINEAR (corridor / tunnel / street)
   A → B → C → D → E
   Use for: corridors, tunnels, streets, ship passageways.
   Branches hang off each node. Good for guided progression.

2. HUB-AND-SPOKE (plaza / command centre / crossroads)
   Spokes radiate from a central hub room (up to 8 directions + up/down).
   Use for: town squares, ship bridges, dungeon intersections.
   Max 8 direct connections from one hub. For more, use a hub-of-hubs.

3. RING / LOOP (station ring / castle wall / city block)
   Rooms connect in a circle — last room connects back to first.
   Use for: station corridors, castle battlements, orbital rings.
   Gives players two routes between any two points.

4. GRID (city district / dungeon level / office floor)
   Rooms arranged in rows and columns with N/S/E/W exits.
   Use for: cities, large dungeons, space station decks.
   Each room has up to 4 cardinal exits to its 4 neighbours.

5. TREE (cave system / office building / apartment block)
   Branches split but never rejoin. Players must backtrack.
   Use for: cave systems, dead-end corridors, simple buildings.

6. MIXED — most real locations combine patterns:
   A city uses GRID for streets, HUB for the main square, LINEAR for
   alleys, and TREE for building interiors.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SIZING AND GRANULARITY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Each room = one distinct, named, playable location.
  • A room is NOT a building — it is ONE space inside a building.
  • A "shop" is at least 2–3 rooms: entrance, main floor, back room/storage.
  • A "bar" might be: entrance, bar_area, seating_area, bathroom, back_office.
  • A small apartment: hallway, living_room, bedroom, bathroom. (4 rooms)
  • A large apartment: hallway, living_room, kitchen, bedroom_1, bedroom_2,
    bathroom, balcony. (7 rooms)
  • A space station docking bay: outer_airlock, inner_airlock, docking_floor,
    cargo_area, control_booth, maintenance_tunnel. (6 rooms)

Think about what a player would want to explore, hide in, or interact with
separately. Each of those is a room.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CANVAS COORDINATE SYSTEM
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Origin (0,0) is top-left. +X = east (right), +Y = south (down).

Exit direction → canvas offset from parent room:
  north      →  dx=0,    dy=-130
  south      →  dx=0,    dy=+130
  east       →  dx=+220, dy=0
  west       →  dx=-220, dy=0
  northeast  →  dx=+220, dy=-130
  northwest  →  dx=-220, dy=-130
  southeast  →  dx=+220, dy=+130
  southwest  →  dx=-220, dy=+130
  up/down    →  same x,y (different floor canvas)

Room size: 176×108 px. Apply offsets so rooms sit flush without overlapping.

PLANNING LAYOUT — compute ALL positions before calling create_room:
1. Anchor room at e.g. (400, 300).
2. Apply offsets recursively for every exit.
3. Check for collisions (two paths landing on same x,y) — if found, shift
   one branch by one step in any perpendicular direction.
4. Orient the whole map for readability: rotate so long corridors run
   east-west (wider than tall), buildings run north-south (taller than wide).

Example — 3-segment corridor with side rooms (the "hallway" pattern above):
  hallway_a (400,300) east→hallway_b, north→apt_1(400,170), south→apt_2(400,430)
  hallway_b (620,300) east→hallway_c, north→apt_3(620,170), south→apt_4(620,430)
  hallway_c (840,300) north→apt_5(840,170), south→apt_6(840,430)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FLOORS / Z-LEVELS — THE VERTICAL STACK
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Floors are an unbounded integer stack. Positive = above ground. Negative = below.
You can have as many levels as the space needs.

  ┌─────────────────────────────────────────────┐
  │  floor= 3   top floor / roof level          │
  │  floor= 2   second floor up                 │
  │  floor= 1   first floor up                  │
  │  floor= 0   GROUND (street / main deck)     │  ← default
  │  floor=-1   first basement / sub-level      │
  │  floor=-2   second basement                 │
  │  floor=-3   third basement / deep vault     │
  └─────────────────────────────────────────────┘

STAIRS CONNECT ADJACENT FLOORS — NOT ALL TO GROUND:
  floor=2 ←→ floor=1   (NOT floor=2 ←→ floor=0)
  floor=1 ←→ floor=0
  floor=0 ←→ floor=-1
  floor=-1 ←→ floor=-2  (NOT floor=-2 ←→ floor=0)

  To reach floor=-2 players must pass through floor=-1.
  To reach floor=3 players must pass through floor=1 then floor=2.
  A stairwell on floor=1 connects UP to floor=2 and DOWN to floor=0.

CRITICAL — FLOOR VALUES ARE NOT INFERRED FROM ROOM NAMES:
  "basement_storage"  →  floor=-1  (YOU must pass floor=-1)
  "sub_vault"         →  floor=-2  (YOU must pass floor=-2)
  "upper_office"      →  floor=1   (YOU must pass floor=1)
  "rooftop_terrace"   →  floor=3   (YOU must pass floor=3)
  The server NEVER guesses. If you omit floor= it defaults to 0.
  A basement room created with floor=0 appears on the ground canvas
  and collides with ground rooms. The server will warn you but won't stop it.

UP/DOWN EXITS ARE FLOOR-CHANGE ONLY:
  "up" and "down" exits ONLY connect rooms on DIFFERENT floor values.
  Using up/down between two rooms on the SAME floor is a hard error.
  For same-floor movement use cardinal directions (north/south/east/west).

  DO NOT use from_dir="up" or from_dir="down" in create_room.
  Those directions have no canvas offset — the room will be unpositioned.
  Build the stairwell room with explicit x,y, then connect floors separately
  with connect_rooms(direction="up" or "down").

THE STAIRWELL IS THE SPATIAL ANCHOR:
  The stairwell room on floor=N MUST share the same x,y as its counterpart
  on floor=N-1. Every other room on that floor is positioned RELATIVE to
  that stairwell using the same direction offsets as the floor below/above.

MULTI-LEVEL EXAMPLE — 3-storey building + 2-level basement:

  floor= 2  roof_access (400,300)  ↓down→ stair_f2
  floor= 2  server_room (620,300)  east of roof_access

  floor= 1  stair_f2    (400,300)  ↑up→roof_access  ↓down→stair_gnd
  floor= 1  office_a    (620,300)  east of stair_f2
  floor= 1  office_b    (180,300)  west of stair_f2

  floor= 0  lobby       (400,300)  ↑up→stair_f2  ↓down→stair_b1
  floor= 0  reception   (620,300)  east of lobby
  floor= 0  storage     (400,430)  south of lobby

  floor=-1  stair_b1    (400,300)  ↑up→lobby  ↓down→stair_b2
  floor=-1  utility     (620,300)  east of stair_b1
  floor=-1  archives    (180,300)  west of stair_b1

  floor=-2  stair_b2    (400,300)  ↑up→stair_b1
  floor=-2  vault       (620,300)  east of stair_b2

  CONNECTIONS (each adjacent pair only):
    connect_rooms lobby     → stair_f2,  direction="up"
    connect_rooms stair_f2  → roof_access, direction="up"
    connect_rooms lobby     → stair_b1,  direction="down"
    connect_rooms stair_b1  → stair_b2,  direction="down"

HOW TO BUILD A BASEMENT (step by step):
  1. Note the ground stairwell's x,y (e.g. lobby at 400,300).
  2. create_room(zone_id, "stair_b1", floor=-1, x=400, y=300)
     — SAME x,y as lobby, floor=-1.
  3. create_room all other floor=-1 rooms with floor=-1, from_room="stair_b1", from_dir=<cardinal>.
  4. connect_rooms(zone_id, "lobby", "stair_b1", direction="down")

HOW TO BUILD A SECOND BASEMENT (floor=-2):
  1. Note stair_b1's x,y on floor=-1 (e.g. 400,300).
  2. create_room(zone_id, "stair_b2", floor=-2, x=400, y=300)
     — SAME x,y as stair_b1, floor=-2.
  3. create_room all other floor=-2 rooms with floor=-2, from_room="stair_b2", from_dir=<cardinal>.
  4. connect_rooms(zone_id, "stair_b1", "stair_b2", direction="down")
     — stair_b1 (floor=-1) connects DOWN to stair_b2 (floor=-2), NOT lobby to stair_b2.

HOW TO BUILD UPPER FLOORS (floor=2, floor=3, etc.):
  Each floor connects to its immediate neighbour, chaining upward:
  lobby(0)→stair_f1(1)→stair_f2(2)→stair_f3(3)
  1. create_room stair_f1 at floor=1, x=lobby.x, y=lobby.y
  2. create_room stair_f2 at floor=2, x=stair_f1.x, y=stair_f1.y
  3. connect_rooms lobby → stair_f1, direction="up"
  4. connect_rooms stair_f1 → stair_f2, direction="up"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BUILD ONE FLOOR AT A TIME — MANDATORY RULE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NEVER interleave rooms from different floors.
Complete ALL rooms on one floor before moving to the next floor.

WRONG (interleaved):
  create_room lobby          floor=0
  create_room stair_bsmt     floor=-1   ← switches floor mid-build
  create_room reception      floor=0    ← back to ground?? WRONG

RIGHT (one floor at a time):
  PHASE 1 — Ground floor (floor=0):
    create_room lobby        floor=0, x=400, y=300
    create_room reception    floor=0, from_room=lobby, from_dir=east
    create_room storage      floor=0, from_room=lobby, from_dir=south
    connect_rooms lobby ↔ reception (east)
    connect_rooms lobby ↔ storage   (south)

  PHASE 2 — Basement (floor=-1):
    create_room stair_bsmt   floor=-1, x=400, y=300  ← SAME x,y as lobby
    create_room wstorage     floor=-1, from_room=stair_bsmt, from_dir=east
    connect_rooms stair_bsmt ↔ wstorage (east)

  PHASE 3 — Cross-floor connections last:
    connect_rooms lobby → stair_bsmt, direction="down"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DIRECTION-POSITION CONSISTENCY — SERVER ENFORCED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
When you call connect_rooms or set_exit with an explicit direction, the
server checks that the target room's canvas position is actually in that
direction. If the claimed direction contradicts the canvas layout the call
FAILS with an error showing the correct direction.

This means: ALWAYS place rooms with from_room+from_dir (or explicit x,y)
BEFORE connecting them. Create rooms first, connect after.

If you get a direction-mismatch error:
  • Re-check the room's canvas position with get_zone
  • Use the direction the error suggests, or
  • Call set_room_position to move the room to where it should be

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RECOMMENDED BUILD ORDER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. create_zone
2. DESIGN — list every floor needed, count rooms per floor, plan x,y positions
3. PHASE 0: create ALL floor=0 rooms, connect ALL floor=0 exits (cardinal only)
4. PHASE -1: create ALL floor=-1 rooms (stair at SAME x,y as floor=0 stair), connect exits
5. PHASE -2: create ALL floor=-2 rooms (stair at SAME x,y as floor=-1 stair), connect exits
   (continue for each additional basement level, each anchored to the floor above it)
6. PHASE +1: create ALL floor=1 rooms (stair at SAME x,y as floor=0 stair), connect exits
7. PHASE +2: create ALL floor=2 rooms (stair at SAME x,y as floor=1 stair), connect exits
   (continue for each additional upper level, each anchored to the floor below it)
8. FINAL cross-floor connections — each pair adjacent only:
     connect_rooms(floor=0_stair  → floor=-1_stair, direction="down")
     connect_rooms(floor=-1_stair → floor=-2_stair, direction="down")
     connect_rooms(floor=0_stair  → floor=1_stair,  direction="up")
     connect_rooms(floor=1_stair  → floor=2_stair,  direction="up")
9. auto_layout_zone only if any positions were skipped
""",
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SLUG_RE = re.compile(r"^[a-zA-Z0-9_-]+$")

DIR_OPPOSITE: dict[str, str] = {
    "north": "south",
    "south": "north",
    "east": "west",
    "west": "east",
    "northeast": "southwest",
    "southwest": "northeast",
    "northwest": "southeast",
    "southeast": "northwest",
    "up": "down",
    "down": "up",
}

# Pixel offsets used by auto_layout — matches WorldForge canvas spacing
DIR_OFFSET: dict[str, tuple[float, float]] = {
    "north": (0, -130),
    "south": (0, 130),
    "east": (220, 0),
    "west": (-220, 0),
    "northeast": (220, -130),
    "northwest": (-220, -130),
    "southeast": (220, 130),
    "southwest": (-220, 130),
}

DEFAULT_W = 176
DEFAULT_H = 108

VALID_ROOM_TYPES = {
    "chamber",
    "corridor",
    "junction",
    "alcove",
    "descent",
    "danger",
    "safe",
    "boss",
    "hub",
    "command",
    "engineering",
    "airlock",
}

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def _world_root() -> Path:
    raw = os.environ.get("WORLDFORGE_ROOT", "content/world")
    p = Path(raw)
    if p.is_absolute():
        return p
    # Relative roots resolve against the working directory when it has them (the usual
    # launch from the repository root), else against the nearest ancestor of this file that
    # contains them, so the tool keeps working wherever it sits in the repo.
    if (Path.cwd() / raw).exists():
        return (Path.cwd() / raw).resolve()
    for ancestor in Path(__file__).resolve().parents:
        if (ancestor / raw).exists():
            return (ancestor / raw).resolve()
    return (Path.cwd() / raw).resolve()


def _zones_dir() -> Path:
    return _world_root() / "zones"


def _zone_dir(zone_id: str) -> Path:
    return _zones_dir() / zone_id


def _rooms_dir(zone_id: str) -> Path:
    return _zone_dir(zone_id) / "rooms"


def _positions_path(zone_id: str) -> Path:
    return _zone_dir(zone_id) / ".positions.json"


# ---------------------------------------------------------------------------
# YAML / JSON I/O
# ---------------------------------------------------------------------------


def _read_room(zone_id: str, slug: str) -> dict:
    p = _rooms_dir(zone_id) / f"{slug}.yaml"
    if not p.exists():
        raise FileNotFoundError(f"Room {zone_id}:{slug} not found")
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def _atomic_write_text(p: Path, text: str) -> None:
    """Crash-safe write: tempfile in the same dir, then os.replace (matches Nexus's seam)."""
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".wf_", suffix=p.suffix, dir=str(p.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, p)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _write_room(zone_id: str, slug: str, data: dict) -> None:
    p = _rooms_dir(zone_id) / f"{slug}.yaml"
    _atomic_write_text(
        p, yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False)
    )


def _link_exit(
    zone_id: str, from_slug: str, to_slug: str, direction: str, description: str
) -> None:
    """Read a room, write one exit entry, save — the shared half of every connect tool."""
    room = _read_room(zone_id, from_slug)
    room.setdefault("exits", {})[direction] = {
        "destination": f"{zone_id}:{to_slug}",
        "description": description,
    }
    _write_room(zone_id, from_slug, room)


def _read_positions(zone_id: str) -> dict:
    p = _positions_path(zone_id)
    if not p.exists():
        return {"version": 2, "positions": {}, "notes": [], "muted_edges": [], "floors": {}}
    raw = json.loads(p.read_text(encoding="utf-8"))
    if raw.get("version") == 2:
        doc = {
            "version": 2,
            "positions": dict(raw.get("positions") or {}),
            "notes": list(raw.get("notes") or []),
            "muted_edges": list(raw.get("muted_edges") or []),
            "floors": dict(raw.get("floors") or {}),
        }
        # Preserve app-only metadata so an MCP round-trip never strips it.
        if raw.get("reference_image") is not None:
            doc["reference_image"] = raw.get("reference_image")
        return doc
    # Legacy v1 — inline positions
    return {
        "version": 2,
        "positions": {k: v for k, v in raw.items() if isinstance(v, dict) and "x" in v},
        "notes": [],
        "muted_edges": [],
        "floors": {},
    }


def _write_positions(zone_id: str, doc: dict) -> None:
    p = _positions_path(zone_id)
    _atomic_write_text(p, json.dumps(doc, indent=2))


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _require_slug(slug: str) -> None:
    if not SLUG_RE.match(slug):
        raise ValueError(f"Invalid slug '{slug}': letters, numbers, _ and - only")


def _require_zone(zone_id: str) -> None:
    if not _zone_dir(zone_id).exists():
        raise ValueError(f"Zone '{zone_id}' does not exist. Use create_zone first.")


def _floor_label(n: int) -> str:
    if n == 0:
        return "Ground"
    return f"F{n}" if n > 0 else f"B{abs(n)}"


def _auto_position(zone_id: str, from_room: str, from_dir: str) -> tuple[float, float] | None:
    """
    Compute a canvas position by taking `from_room`'s position and applying
    the direction offset.  Returns (x, y) or None if from_room has no position.
    """
    doc = _read_positions(zone_id)
    parent_pos = doc["positions"].get(from_room)
    if not parent_pos:
        return None
    offset = DIR_OFFSET.get(from_dir.lower())
    if not offset:
        return None
    return float(parent_pos["x"]) + offset[0], float(parent_pos["y"]) + offset[1]


# Keywords that strongly imply a below-ground room (basement/sub-level)
_BASEMENT_KEYWORDS = (
    "basement",
    "bsmt",
    "cellar",
    "sub_deck",
    "subdeck",
    "underground",
    "vault",
    "sublevel",
    "sub_level",
    "lower_deck",
    "lowerdeck",
    "underdeck",
    "under_deck",
    "subfloor",
    "sub_floor",
)

# Keywords that strongly imply an above-ground (upper) room
_UPPER_FLOOR_KEYWORDS = (
    "upper",
    "upstairs",
    "mezzanine",
    "penthouse",
    "attic",
    "rooftop",
    "roof_top",
    "roofdeck",
    "roof_deck",
    "loft",
    "topfloor",
    "top_floor",
    "topdeck",
    "top_deck",
    "skydeck",
)


def _warn_basement_floor(slug: str, floor: int) -> str | None:
    """
    Soft warning when a room slug strongly implies a non-ground floor but floor=0
    was given. The room is still created (per the tool docstring's promise) — the
    caller is told to fix it with set_room_floor.
    """
    if floor != 0:
        return None  # any non-zero floor is fine; we trust the caller
    slug_lower = slug.lower()

    for kw in _BASEMENT_KEYWORDS:
        if kw in slug_lower:
            return (
                f"WARNING - FLOOR MISMATCH: slug '{slug}' contains '{kw}' which implies a "
                f"below-ground room, but floor=0 (ground) was used. Below-ground rooms "
                f"should use a negative floor (first basement -> -1, second -> -2). "
                f"Fix with set_room_floor. Remember: floor=-2 connects to floor=-1, not "
                f"directly to floor=0 - build basements one level at a time."
            )

    for kw in _UPPER_FLOOR_KEYWORDS:
        if kw in slug_lower:
            return (
                f"WARNING - FLOOR MISMATCH: slug '{slug}' contains '{kw}' which implies an "
                f"above-ground room, but floor=0 (ground) was used. Upper rooms should use "
                f"a positive floor (first floor up -> 1, second -> 2). Fix with "
                f"set_room_floor. Remember: floor=2 connects to floor=1, not directly to "
                f"floor=0 - build upper floors one level at a time."
            )
    return None


def _check_orphan_room(zone_id: str, slug: str) -> str:
    """
    After room creation, check whether the new room has any exits or any incoming
    exits from neighbours. Returns a reminder string if the room is fully isolated.
    """
    rd = _rooms_dir(zone_id)
    if not rd.exists():
        return ""
    full_id = f"{zone_id}:{slug}"
    own = _read_room(zone_id, slug)
    if own.get("exits") or {}:
        return ""
    # Look for any other room pointing TO this one
    for f in rd.glob("*.yaml"):
        if f.stem == slug:
            continue
        other = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        for ex in (other.get("exits") or {}).values():
            if str((ex or {}).get("destination", "")) in (full_id, slug):
                return ""
    return (
        f"⚠ ORPHAN ROOM: '{slug}' has no exits and no incoming exits — it is "
        f"unreachable. Add at least one connection with connect_rooms or set_exit, "
        f"or it will float disconnected on the canvas like the 'Apartment 1' problem."
    )


def _validate_exit_direction(zone_id: str, from_slug: str, to_slug: str, direction: str) -> None:
    """
    Enforce that the claimed exit direction matches the canvas positions of both rooms.
    Skips check if either room lacks a canvas position, or direction is up/down.

    Raises ValueError if the claimed direction contradicts the canvas layout, giving
    the inferred correct direction so the caller can fix it.
    """
    direction = direction.lower()
    if direction in ("up", "down"):
        return  # vertical exits are cross-floor; canvas position doesn't apply

    doc = _read_positions(zone_id)
    pos_a = doc["positions"].get(from_slug)
    pos_b = doc["positions"].get(to_slug)
    if not pos_a or not pos_b:
        return  # can't check without both positions

    inferred = _infer_direction(
        float(pos_a["x"]),
        float(pos_a["y"]),
        float(pos_b["x"]),
        float(pos_b["y"]),
    )
    if inferred != direction:
        raise ValueError(
            f"Direction mismatch: you said direction='{direction}' but on the canvas "
            f"'{to_slug}' is to the {inferred} of '{from_slug}' "
            f"(from={pos_a['x']:.0f},{pos_a['y']:.0f}  to={pos_b['x']:.0f},{pos_b['y']:.0f}). "
            f"Either use direction='{inferred}' to match the layout, "
            f"or call set_room_position to move '{to_slug}' to the correct canvas position "
            f"before connecting."
        )


def _validate_vertical_exit(zone_id: str, from_slug: str, to_slug: str, direction: str) -> None:
    """
    Enforce that up/down exits only connect rooms on DIFFERENT floors.
    Raises ValueError with a clear message if both rooms are on the same floor.
    """
    direction = direction.lower()
    if direction not in ("up", "down"):
        return  # horizontal exits are unconstrained
    doc = _read_positions(zone_id)
    floors = doc.get("floors", {})
    from_floor = int(floors.get(from_slug, 0))
    to_floor = int(floors.get(to_slug, 0))
    if from_floor == to_floor:
        raise ValueError(
            f"Cannot create a '{direction}' exit between '{from_slug}' and '{to_slug}': "
            f"both are on {_floor_label(from_floor)}. "
            f"Up/down exits must connect rooms on DIFFERENT floors. "
            f"Fix: call set_room_floor(zone_id, '{to_slug}', {from_floor + (1 if direction == 'up' else -1)}) "
            f"to move it to the correct floor, then retry. "
            f"For same-floor movement use a cardinal direction (north/south/east/west) instead."
        )


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def list_zones() -> list[str]:
    """List all zone IDs in the world."""
    zd = _zones_dir()
    if not zd.exists():
        return []
    return sorted(p.name for p in zd.iterdir() if p.is_dir() and not p.name.startswith("."))


@mcp.tool()
def get_zone(zone_id: str) -> dict[str, Any]:
    """
    Get the full layout of a zone: every room with its exits and properties, plus the
    canvas layout (positions and floor assignments).

    Returns: { rooms: {slug: roomData}, layout: {positions, floors, ...} }
    """
    _require_zone(zone_id)
    rd = _rooms_dir(zone_id)
    rooms: dict[str, Any] = {}
    if rd.exists():
        for f in sorted(rd.glob("*.yaml")):
            rooms[f.stem] = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    return {"rooms": rooms, "layout": _read_positions(zone_id)}


@mcp.tool()
def create_zone(zone_id: str, *, display_name: str = "", description: str = "") -> str:
    """
    Create a new zone (map area). Zone ID is the folder name used in all room IDs.
    After creating, use create_room to populate it.

    Args:
        zone_id:      Slug, e.g. "space_station_alpha". Letters, numbers, _ and - only.
        display_name: Human-readable name written to zone.yaml (defaults to the slug titled).
        description:  One-line zone description written to zone.yaml.
    """
    _require_slug(zone_id)
    zd = _zone_dir(zone_id)
    if zd.exists():
        return f"Zone '{zone_id}' already exists"
    zd.mkdir(parents=True)
    (zd / "rooms").mkdir()
    # Always write zone.yaml in the server's ZoneModel shape (id/name/description).
    meta = {
        "id": zone_id,
        "name": display_name or zone_id.replace("_", " ").replace("-", " ").title(),
        "description": description or f"The {display_name or zone_id.replace('_', ' ')} area.",
        "depth_range": [1, 3],
    }
    with open(zd / "zone.yaml", "w", encoding="utf-8") as f:
        yaml.dump(meta, f, allow_unicode=True, sort_keys=False)
    return f"Created zone '{zone_id}'" + (f" ({display_name})" if display_name else "")


@mcp.tool()
def create_room(
    zone_id: str,
    slug: str,
    *,
    name: str = "",
    room_type: str = "chamber",
    depth: int = 1,
    description: str = "",
    floor: int = 0,
    from_room: str = "",
    from_dir: str = "",
    x: float | None = None,
    y: float | None = None,
) -> str:
    """
    Create a new room and place it on the canvas.

    PREFERRED USAGE — use from_room + from_dir and let the server compute position:
      create_room(zone_id, "office_a", from_room="hallway_1", from_dir="north")
      → office_a is placed directly north of hallway_1 on the canvas automatically.

    The server looks up hallway_1's position and adds the direction offset:
      north  → y - 130    south  → y + 130
      east   → x + 220    west   → x - 220
      northeast/northwest/southeast/southwest → diagonal combination

    This guarantees the canvas layout matches the exit graph — if the exit goes
    north, the room appears north on the map.

    For the FIRST room in a zone (no parent yet), pass x=400, y=300 explicitly.
    Every subsequent room should use from_room + from_dir.

    Args:
        zone_id:     Zone ID the room belongs to.
        slug:        Unique room identifier within the zone, e.g. "bridge_upper".
        name:        Display name on the map. Defaults to slug if empty.
        room_type:   One of: chamber, corridor, junction, alcove, descent, danger,
                     safe, boss, hub, command, engineering, airlock.
        depth:       Difficulty/depth level 1–10.
        description: Base description text players see on entering.
        floor:       Physical vertical floor level. REQUIRED for non-ground rooms.
                     0=ground (default), 1=one floor up, -1=basement, -2=sub-basement.
                     The server NEVER infers floor from the room name — you must pass
                     the correct value. A basement room created without floor=-1 will
                     be placed on the ground canvas and collide with other floor=0 rooms.
                     For stairwell rooms linking two floors, both rooms get the SAME
                     x,y coordinates but DIFFERENT floor values.
        from_room:   Slug of the existing room this new room connects FROM.
                     Position is computed automatically as parent_pos + direction_offset.
        from_dir:    The exit direction FROM from_room TO this new room.
                     Use cardinal/diagonal directions only (north/south/east/west/
                     northeast/northwest/southeast/southwest).
                     NEVER pass "up" or "down" — those have no canvas offset and will
                     leave the room unpositioned. Cross-floor links are added separately
                     with connect_rooms(direction="up"/"down") after room creation.
        x:           Override canvas X (only needed for the first room or special cases).
        y:           Override canvas Y (only needed for the first room or special cases).
    """
    _require_slug(zone_id)
    _require_slug(slug)
    _require_zone(zone_id)

    data: dict[str, Any] = {
        "id": f"{zone_id}:{slug}",
        "zone": zone_id,
        "type": room_type,
        "depth": depth,
        "description": {"base": description},
        "exits": {},
        "features": [],
        "entity_spawns": [],
        "hazards": [],
        "tags": [],
    }
    if name:
        data["name"] = name

    _write_room(zone_id, slug, data)

    doc = _read_positions(zone_id)
    doc["floors"][slug] = floor

    # Resolve position: from_room+from_dir takes priority, then explicit x/y,
    # then leave unset (auto_layout_zone can place it later).
    final_x, final_y = x, y
    auto_note = ""

    if from_room and from_dir:
        from_dir_lower = from_dir.lower()
        if from_dir_lower in ("up", "down"):
            auto_note = (
                f" (WARNING: from_dir='{from_dir}' has no canvas offset — room is unpositioned. "
                f"Use a cardinal direction for from_dir, then connect floors separately with "
                f"connect_rooms(direction='{from_dir_lower}'))"
            )
        else:
            computed = _auto_position(zone_id, from_room, from_dir)
            if computed:
                final_x, final_y = computed
                auto_note = f" (auto-placed {from_dir} of {from_room})"
            else:
                auto_note = (
                    f" (WARNING: {from_room} has no position yet — run auto_layout_zone to fix)"
                )

    if final_x is not None and final_y is not None:
        doc["positions"][slug] = {
            "x": final_x,
            "y": final_y,
            "width": DEFAULT_W,
            "height": DEFAULT_H,
        }

    _write_positions(zone_id, doc)

    pos_str = (
        f" at ({final_x:.0f}, {final_y:.0f})" if final_x is not None else " (position: pending)"
    )
    floor_warning = _warn_basement_floor(slug, floor)
    result = f"Created {zone_id}:{slug} on {_floor_label(floor)}{pos_str}{auto_note}"
    if floor_warning:
        result += f"\n{floor_warning}"
    return result


@mcp.tool()
def update_room(
    zone_id: str,
    slug: str,
    *,
    name: str | None = None,
    room_type: str | None = None,
    depth: int | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
) -> str:
    """
    Update properties of an existing room. Pass only the fields you want to change.

    Args:
        zone_id:     Zone ID
        slug:        Room slug
        name:        New display name (pass empty string "" to clear the name)
        room_type:   New room type
        depth:       New depth level
        description: New base description text
        tags:        New tags list (replaces existing)
    """
    _require_zone(zone_id)
    data = _read_room(zone_id, slug)

    if name is not None:
        if name:
            data["name"] = name
        else:
            data.pop("name", None)
    if room_type is not None:
        data["type"] = room_type
    if depth is not None:
        data["depth"] = depth
    if description is not None:
        desc = data.get("description") or {}
        data["description"] = {**(desc if isinstance(desc, dict) else {}), "base": description}
    if tags is not None:
        data["tags"] = tags

    _write_room(zone_id, slug, data)
    return f"Updated {zone_id}:{slug}"


@mcp.tool()
def delete_room(zone_id: str, slug: str) -> str:
    """
    Delete a room YAML file, remove it from the layout, and clean up any exits
    in other rooms that pointed to it.
    """
    _require_zone(zone_id)
    p = _rooms_dir(zone_id) / f"{slug}.yaml"
    if p.exists():
        p.unlink()

    # Clean up exits in other rooms
    full_id = f"{zone_id}:{slug}"
    rd = _rooms_dir(zone_id)
    if rd.exists():
        for f in rd.glob("*.yaml"):
            room = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            exits = room.get("exits") or {}
            dirty = False
            for d, ex in list(exits.items()):
                dest = str((ex or {}).get("destination", ""))
                if dest in (full_id, slug):
                    del exits[d]
                    dirty = True
            if dirty:
                room["exits"] = exits
                with open(f, "w", encoding="utf-8") as wf:
                    yaml.dump(
                        room, wf, allow_unicode=True, default_flow_style=False, sort_keys=False
                    )

    doc = _read_positions(zone_id)
    doc["positions"].pop(slug, None)
    doc["floors"].pop(slug, None)
    _write_positions(zone_id, doc)
    return f"Deleted {zone_id}:{slug} and cleaned up {full_id} references"


@mcp.tool()
def set_exit(
    zone_id: str,
    from_slug: str,
    direction: str,
    to_slug: str,
    *,
    bidirectional: bool = True,
    description: str = "",
) -> str:
    """
    Connect two rooms with an exit. By default creates the return exit too.

    Args:
        zone_id:       Zone containing both rooms
        from_slug:     Room the exit leaves from
        direction:     north, south, east, west, northeast, northwest, southeast,
                       southwest, up, down
        to_slug:       Room the exit leads to
        bidirectional: Also add the matching return exit (default True)
        description:   Optional flavour text for the exit
    """
    _require_zone(zone_id)
    direction = direction.lower()
    _validate_vertical_exit(zone_id, from_slug, to_slug, direction)
    _validate_exit_direction(zone_id, from_slug, to_slug, direction)

    _link_exit(zone_id, from_slug, to_slug, direction, description)

    if bidirectional:
        ret = DIR_OPPOSITE.get(direction, "south")
        _link_exit(zone_id, to_slug, from_slug, ret, description)

    arrow = f"{from_slug} →[{direction}]→ {to_slug}"
    return arrow + (" + return" if bidirectional else "")


@mcp.tool()
def remove_exit(
    zone_id: str,
    from_slug: str,
    direction: str,
    *,
    bidirectional: bool = True,
) -> str:
    """
    Remove an exit from a room, and optionally the matching return exit.

    Args:
        zone_id:       Zone ID
        from_slug:     Room to remove the exit from
        direction:     Direction to remove
        bidirectional: Also remove the return exit from the target room (default True)
    """
    _require_zone(zone_id)
    direction = direction.lower()

    from_room = _read_room(zone_id, from_slug)
    exits = from_room.get("exits") or {}
    dest = str((exits.pop(direction, None) or {}).get("destination", ""))
    from_room["exits"] = exits
    _write_room(zone_id, from_slug, from_room)

    if bidirectional and dest:
        to_slug = dest.split(":")[-1] if ":" in dest else dest
        ret = DIR_OPPOSITE.get(direction, "south")
        try:
            to_room = _read_room(zone_id, to_slug)
            to_exits = to_room.get("exits") or {}
            to_exits.pop(ret, None)
            to_room["exits"] = to_exits
            _write_room(zone_id, to_slug, to_room)
        except FileNotFoundError:
            pass

    return f"Removed [{direction}] exit from {from_slug}"


@mcp.tool()
def set_room_floor(zone_id: str, slug: str, floor: int) -> str:
    """
    Move a room to a different physical floor level.
    Use this to correct a room that was created on the wrong floor, or to
    reorganise a building after the fact.

    Z-axis: positive = above ground (+Z up), negative = below ground (-Z down).

    floor=3  → third floor up
    floor=2  → second floor up
    floor=1  → first floor up
    floor=0  → ground / street / main deck (default)
    floor=-1 → first basement / sub-level
    floor=-2 → second basement
    floor=-3 → third basement / deep vault

    Stairs connect ADJACENT floors only: floor N ↔ floor N±1.
    After changing a room's floor, the up/down exits connecting it to adjacent
    floors should still be correct — only the visual canvas placement changes.
    """
    _require_zone(zone_id)
    doc = _read_positions(zone_id)
    doc["floors"][slug] = floor
    _write_positions(zone_id, doc)
    return f"{slug} → {_floor_label(floor)}"


@mcp.tool()
def set_room_position(zone_id: str, slug: str, x: float, y: float) -> str:
    """
    Set the canvas position of a room in WorldForge (pixels from origin).
    Typical spacing: 220px horizontal, 130px vertical between adjacent rooms.
    Rooms on the same floor share a canvas, so align positions within each floor.
    """
    _require_zone(zone_id)
    doc = _read_positions(zone_id)
    prev = doc["positions"].get(slug) or {}
    doc["positions"][slug] = {**prev, "x": x, "y": y, "width": DEFAULT_W, "height": DEFAULT_H}
    _write_positions(zone_id, doc)
    return f"{slug} → ({x}, {y})"


@mcp.tool()
def auto_layout_zone(
    zone_id: str,
    *,
    root_slug: str | None = None,
    floor: int | None = None,
) -> str:
    """
    Automatically arrange room canvas positions using a BFS graph walk.

    Rooms are placed based on their exit directions (north → up, east → right, etc.).
    Up/down exits are skipped for horizontal placement but ARE used to anchor floors:
    each floor's stairwell room inherits its x,y from the matching stairwell on the
    floor below, so all floors stack spatially — rooms directly above/below each other
    share the same canvas coordinates on their respective floors.

    Floors are processed in order (0, then 1, then 2, etc. / 0, then -1, then -2).
    For each floor above/below ground, the stairwell room (the one with a down/up exit
    to the previous floor) is anchored at the same x,y as its counterpart below, then
    all other rooms on that floor are laid out relative to it via BFS.

    Args:
        zone_id:    Zone to layout
        root_slug:  Room to start layout from on floor=0. Defaults to first alphabetically.
        floor:      If set, only layout rooms on this floor. If None, layout all floors.
    """
    _require_zone(zone_id)
    rd = _rooms_dir(zone_id)
    if not rd.exists():
        return "No rooms found"

    all_rooms = {
        f.stem: yaml.safe_load(f.read_text(encoding="utf-8")) or {} for f in rd.glob("*.yaml")
    }
    doc = _read_positions(zone_id)
    floors_map = doc["floors"]

    # Group rooms by floor
    floor_groups: dict[int, list[str]] = {}
    for slug in all_rooms:
        fl = int(floors_map.get(slug, 0))
        if floor is not None and fl != floor:
            continue
        floor_groups.setdefault(fl, []).append(slug)

    def _bfs_floor(
        slugs: list[str], start: str, start_x: float, start_y: float
    ) -> dict[str, tuple[float, float]]:
        """BFS layout for one floor, anchored at (start_x, start_y) for start room."""
        positions: dict[str, tuple[float, float]] = {}
        queue: list[tuple[str, float, float]] = [(start, start_x, start_y)]
        visited: set[str] = set()
        while queue:
            cur, cx, cy = queue.pop(0)
            if cur in visited:
                continue
            visited.add(cur)
            positions[cur] = (cx, cy)
            exits = (all_rooms.get(cur) or {}).get("exits") or {}
            for direction, ex in exits.items():
                dlow = direction.lower()
                if dlow in ("up", "down"):
                    continue
                offset = DIR_OFFSET.get(dlow)
                if not offset:
                    continue
                dest = str((ex or {}).get("destination", ""))
                tgt = dest.split(":")[-1] if ":" in dest else dest
                if tgt and tgt in slugs and tgt not in visited:
                    queue.append((tgt, cx + offset[0], cy + offset[1]))
        return positions

    def _find_stairwell(slugs: list[str], exit_dir: str) -> str | None:
        """Find the room on this floor that has an exit in exit_dir (up or down)."""
        for slug in slugs:
            exits = (all_rooms.get(slug) or {}).get("exits") or {}
            if any(d.lower() == exit_dir for d in exits):
                return slug
        return None

    total = 0
    # Process floors from 0 outward so each floor can inherit stairwell positions
    # Sort: 0 first, then positives ascending, then negatives descending
    sorted_floors = sorted(floor_groups.keys(), key=lambda f: (f != 0, f < 0, abs(f)))

    for fl in sorted_floors:
        slugs = floor_groups[fl]
        anchor_slug: str
        anchor_x: float
        anchor_y: float

        if fl == 0 or floor is not None:
            # Ground floor (or single-floor layout): use root_slug or first alphabetically
            anchor_slug = root_slug if root_slug and root_slug in slugs else sorted(slugs)[0]
            anchor_x, anchor_y = 400.0, 300.0
        else:
            # Upper/lower floor: find the stairwell and inherit its position from the
            # adjacent floor that was already laid out.
            connect_dir = "down" if fl > 0 else "up"  # how THIS floor connects back
            stair = _find_stairwell(slugs, connect_dir)
            if stair:
                # Look up what position the matching room on the adjacent floor got
                adj_fl = fl - 1 if fl > 0 else fl + 1
                adj_slugs = floor_groups.get(adj_fl, [])
                adj_connect_dir = "up" if fl > 0 else "down"
                adj_stair = _find_stairwell(adj_slugs, adj_connect_dir)
                if adj_stair and adj_stair in doc["positions"]:
                    saved = doc["positions"][adj_stair]
                    anchor_slug = stair
                    anchor_x = float(saved["x"])
                    anchor_y = float(saved["y"])
                else:
                    # Adjacent stairwell not positioned yet — use default
                    anchor_slug = stair
                    anchor_x, anchor_y = 400.0, 300.0
            else:
                anchor_slug = sorted(slugs)[0]
                anchor_x, anchor_y = 400.0, 300.0

        positions = _bfs_floor(slugs, anchor_slug, anchor_x, anchor_y)

        # Grid fallback for rooms not reachable from the anchor
        grid_i = 0
        for slug in sorted(slugs):
            if slug not in positions:
                positions[slug] = ((grid_i % 6) * 220.0, (grid_i // 6) * 130.0 + 900.0)
                grid_i += 1

        for slug, (x, y) in positions.items():
            prev = doc["positions"].get(slug) or {}
            doc["positions"][slug] = {
                **prev,
                "x": x,
                "y": y,
                "width": DEFAULT_W,
                "height": DEFAULT_H,
            }

        total += len(positions)

    _write_positions(zone_id, doc)
    floors_done = len(floor_groups)
    return f"Laid out {total} room(s) across {floors_done} floor(s) in '{zone_id}' (floors spatially aligned via stairwells)"


def _infer_direction(ax: float, ay: float, bx: float, by: float) -> str:
    """Pick the cardinal/diagonal/vertical direction from room A to room B by canvas delta."""
    dx = bx - ax
    dy = by - ay  # positive Y = down on canvas = south
    adx, ady = abs(dx), abs(dy)

    # Treat as purely vertical if one axis dominates strongly
    if adx < 30 and ady < 30:
        return "north"  # same position — default
    if adx == 0 or (ady > 0 and ady / max(adx, 1) > 3):
        return "south" if dy > 0 else "north"
    if ady == 0 or (adx > 0 and adx / max(ady, 1) > 3):
        return "east" if dx > 0 else "west"
    # Diagonal
    if dx > 0:
        return "southeast" if dy > 0 else "northeast"
    return "southwest" if dy > 0 else "northwest"


@mcp.tool()
def connect_rooms(
    zone_id: str,
    room_a: str,
    room_b: str,
    *,
    direction: str | None = None,
    bidirectional: bool = True,
    description: str = "",
) -> str:
    """
    Connect two rooms with an exit. This is the primary tool for linking rooms.

    ## Horizontal exits (same floor)
    If 'direction' is omitted the server infers it from the rooms' canvas positions
    (e.g. room_b to the right of room_a → east exit). If neither room has a saved
    position yet, 'east' is used as a safe default.

    ## Vertical exits (stairs / lifts between floors)
    When connecting rooms on DIFFERENT floors you MUST pass direction="up" or
    direction="down" explicitly — canvas position cannot infer cross-floor direction.

    direction="up"   = moving to a HIGHER floor number (+Z): floor=N → floor=N+1
    direction="down" = moving to a LOWER floor number  (-Z): floor=N → floor=N-1

    Examples:
      floor=0  → floor=1  : direction="up"
      floor=1  → floor=2  : direction="up"   (NOT floor=0 → floor=2 directly)
      floor=0  → floor=-1 : direction="down"
      floor=-1 → floor=-2 : direction="down" (NOT floor=0 → floor=-2 directly)

    Stairs CHAIN through adjacent floors — each connect_rooms call links ONE pair.
    With bidirectional=True (default) both exits are created in one call.

    Args:
        zone_id:       Zone both rooms live in
        room_a:        Source room slug (the room the "up"/"down" exit leaves FROM)
        room_b:        Destination room slug (the room it arrives AT)
        direction:     north/south/east/west/northeast/northwest/southeast/southwest/up/down
                       MUST be "up" or "down" for cross-floor connections.
        bidirectional: Also add the return exit on room_b (default True).
                       For stairs this means room_b also gets the opposite exit.
        description:   Optional exit flavour text applied to both exits
    """
    _require_zone(zone_id)

    if direction:
        direction = direction.lower()
    direction_was_explicit = bool(direction)
    if not direction_was_explicit:
        # Infer from canvas positions
        doc = _read_positions(zone_id)
        pos_a = doc["positions"].get(room_a)
        pos_b = doc["positions"].get(room_b)
        if pos_a and pos_b:
            direction = _infer_direction(
                float(pos_a["x"]),
                float(pos_a["y"]),
                float(pos_b["x"]),
                float(pos_b["y"]),
            )
        else:
            direction = "east"  # safe default when positions unknown

    # Block up/down exits between same-floor rooms
    _validate_vertical_exit(zone_id, room_a, room_b, direction)
    # Block direction claims that contradict canvas positions
    # (only check when direction was explicitly passed — inferred direction is always correct)
    if direction_was_explicit:
        _validate_exit_direction(zone_id, room_a, room_b, direction)

    _link_exit(zone_id, room_a, room_b, direction, description)

    if bidirectional:
        ret = DIR_OPPOSITE.get(direction, "west")
        _link_exit(zone_id, room_b, room_a, ret, description)

    how = "inferred from positions" if not direction_was_explicit else "explicit"
    return (
        f"{room_a} →[{direction}]→ {room_b}" + (" + return" if bidirectional else "") + f" ({how})"
    )


@mcp.tool()
def connect_chain(
    zone_id: str,
    slugs: list[str],
    *,
    direction: str = "east",
    loop: bool = False,
    description: str = "",
) -> str:
    """
    Connect a list of rooms in sequence: slugs[0]→slugs[1]→slugs[2]→...
    Useful for building corridors, linear decks, or ring layouts quickly.

    Args:
        zone_id:    Zone ID
        slugs:      Ordered list of room slugs to chain together
        direction:  Exit direction from each room to the next (default east).
                    The return exit uses the opposite direction automatically.
        loop:       If True, also connect the last room back to the first.
        description: Optional exit flavour text
    """
    _require_zone(zone_id)
    if len(slugs) < 2:
        return "Need at least 2 rooms to chain"

    direction = direction.lower()
    ret = DIR_OPPOSITE.get(direction, "west")
    pairs: list[str] = []

    pairs_to_link = list(zip(slugs, slugs[1:]))
    if loop:
        pairs_to_link.append((slugs[-1], slugs[0]))

    for a, b in pairs_to_link:
        _link_exit(zone_id, a, b, direction, description)
        _link_exit(zone_id, b, a, ret, description)
        pairs.append(f"{a}↔{b}")

    return f"Chained [{direction}]: " + ", ".join(pairs)


@mcp.tool()
def get_layout_guide() -> dict:
    """
    Returns the full MUD map design rulebook plus canvas spacing maths.
    CALL THIS at the start of any non-trivial build to plan correctly.

    Covers:
      - The one-exit-per-direction rule and what it means for layout
      - How to build corridors with multiple side-rooms (the hallway problem)
      - Common patterns: linear, hub, ring, grid, tree
      - Room granularity (what counts as one room)
      - Canvas offsets for computing x,y positions
      - Floor / Z-level rules
    """
    return {
        "fundamental_rule": (
            "Each room has EXACTLY ONE exit per direction. "
            "You cannot have two 'north' exits from the same room. "
            "All layout design flows from this constraint."
        ),
        "hallway_problem": {
            "explanation": (
                "To put multiple rooms off a corridor you need multiple corridor rooms — "
                "one per branch point. A single hallway room can only branch north AND south "
                "once each. For N side-rooms on each side you need N corridor rooms."
            ),
            "example_4_apartments": {
                "hallway_a": "north→apt_1, south→apt_2, east→hallway_b",
                "hallway_b": "north→apt_3, south→apt_4, east→hallway_c, west→hallway_a",
                "hallway_c": "north→apt_5, south→apt_6, west→hallway_b",
                "note": "3 corridor rooms → 6 apartments (2 per corridor section)",
            },
        },
        "patterns": {
            "linear": "A→B→C→D. Branches hang off each node. Good for corridors, tunnels, streets.",
            "hub_spoke": "Up to 8 spokes radiate from one central hub. Good for plazas, bridges, crossroads.",
            "ring_loop": "Rooms connect in a circle; last connects back to first. Two routes between any points.",
            "grid": "Rows/columns of rooms with N/S/E/W exits. Good for cities, dungeon levels.",
            "tree": "Branches split but never rejoin — players must backtrack. Good for caves, dead-ends.",
        },
        "sizing_guide": {
            "shop": "2-3 rooms: entrance, shop_floor, back_room",
            "bar_or_cafe": "3-4 rooms: entrance, bar_area, seating, back_office",
            "small_apartment": "4 rooms: hallway, living_room, bedroom, bathroom",
            "large_apartment": "6-7 rooms: hallway, living_room, kitchen, bedroom×2, bathroom, balcony",
            "docking_bay": "5-6 rooms: outer_airlock, inner_airlock, docking_floor, cargo_area, control_booth",
            "office_floor": "corridor×N + offices on each side (2 offices per corridor section)",
        },
        "offsets": {
            "north": {"dx": 0, "dy": -130},
            "south": {"dx": 0, "dy": 130},
            "east": {"dx": 220, "dy": 0},
            "west": {"dx": -220, "dy": 0},
            "northeast": {"dx": 220, "dy": -130},
            "northwest": {"dx": -220, "dy": -130},
            "southeast": {"dx": 220, "dy": 130},
            "southwest": {"dx": -220, "dy": 130},
            "up": {"dx": 0, "dy": 0, "note": "same x,y — different floor number"},
            "down": {"dx": 0, "dy": 0, "note": "same x,y — different floor number"},
        },
        "room_size": {"width": 176, "height": 108},
        "canvas": {
            "origin": "top-left (0,0)",
            "x_axis": "east = +X (right)",
            "y_axis": "south = +Y (down)",
            "suggested_anchor": "x=400, y=300 for the entrance/first room",
        },
        "position_planning_steps": [
            "1. Choose pattern (linear / hub / ring / grid / tree).",
            "2. Count rooms needed per floor — remember 1 corridor section per 2 side-rooms.",
            "3. Anchor first room at (400, 300).",
            "4. Apply offsets recursively for every exit to get each room's x,y.",
            "5. Check for collisions (two rooms at same x,y on the same floor) — shift by one offset step.",
            "6. Orient for readability: long corridors east-west, tall buildings north-south.",
            "7. THEN create all rooms — one complete floor at a time.",
        ],
        "BUILD_ONE_FLOOR_AT_A_TIME": {
            "rule": (
                "NEVER interleave rooms from different floors. "
                "Finish ALL rooms on floor=0, then ALL rooms on floor=-1, then ALL rooms on floor=1. "
                "Mixing floors mid-build causes wrong positions and disconnected layouts."
            ),
            "correct_order": [
                "PHASE 1: create ALL floor=0 rooms",
                "PHASE 2: connect ALL floor=0 exits (cardinal only)",
                "PHASE 3: create ALL floor=-1 rooms (basement stairwell at SAME x,y as ground stairwell)",
                "PHASE 4: connect ALL floor=-1 exits (cardinal only)",
                "PHASE 5: create ALL floor=1 rooms (upper stairwell at SAME x,y as ground stairwell)",
                "PHASE 6: connect ALL floor=1 exits (cardinal only)",
                "PHASE 7: connect_rooms(direction='down') for each ground→basement pair",
                "PHASE 8: connect_rooms(direction='up') for each ground→upper pair",
            ],
            "wrong_example": (
                "create lobby floor=0, create stair_bsmt floor=-1, create reception floor=0 "
                "← WRONG: never switch floor mid-creation"
            ),
        },
        "direction_position_consistency": {
            "rule": (
                "The server validates that the claimed exit direction matches canvas positions. "
                "If you call connect_rooms(room_a, room_b, direction='north') but room_b is to the "
                "east of room_a on canvas, the call FAILS with a direction-mismatch error. "
                "Always place rooms with from_room+from_dir BEFORE connecting them."
            ),
            "if_error": [
                "1. Call get_zone to inspect current positions.",
                "2. Use the direction the error message suggests, OR",
                "3. Call set_room_position to move the room to the correct canvas location.",
            ],
        },
        "floor_rules": {
            "z_axis_model": {
                "description": (
                    "Floors are an unbounded integer Z-axis. "
                    "Positive Z = above ground (up). Negative Z = below ground (down). "
                    "floor=0 is always ground/street/main-deck."
                ),
                "stack": {
                    "floor=3": "+Z  top/roof level",
                    "floor=2": "+Z  second floor up",
                    "floor=1": "+Z  first floor up",
                    "floor=0": " 0  GROUND (default)",
                    "floor=-1": "-Z  first basement / sub-level",
                    "floor=-2": "-Z  second basement",
                    "floor=-3": "-Z  third basement / deep vault",
                },
                "rule": (
                    "You can have as many levels as the space needs. "
                    "Stairs only connect ADJACENT floors: floor N ↔ floor N+1 or N-1. "
                    "floor=-2 connects to floor=-1, NOT to floor=0. "
                    "floor=3 connects to floor=2, NOT to floor=0. "
                    "Players chain through intermediate floors to reach deep levels."
                ),
            },
            "stairwell_chain_examples": {
                "3_storey_building": "lobby(0)→stair_f1(1)→stair_f2(2)→stair_f3(3)",
                "2_level_basement": "lobby(0)→stair_b1(-1)→stair_b2(-2)",
                "mixed_building": "vault(-2)→stair_b1(-1)→lobby(0)→stair_f1(1)→roof(2)",
                "connection_rule": "Each connect_rooms call links ONE adjacent floor pair only.",
            },
            "CRITICAL_floor_is_never_inferred": (
                "The server NEVER guesses floor from a room name. "
                "'basement_storage' created without floor=-1 lands on floor=0 (WRONG). "
                "'vault_deep' for a second basement needs floor=-2. "
                "'penthouse' needs floor=3 or whatever level it is. "
                "The server warns if a slug contains basement/bsmt/cellar/vault/sublevel/lower_deck "
                "keywords and floor=0 — but it will still create the room. Fix with set_room_floor."
            ),
            "up_down_exits_rule": (
                "up/down exits ONLY connect rooms on DIFFERENT floor values — hard error otherwise. "
                "direction='up' = moving to a higher floor number (+Z). "
                "direction='down' = moving to a lower floor number (-Z). "
                "Never use from_dir='up'/'down' in create_room — no canvas offset, room stays unpositioned."
            ),
            "stairwell_anchor": (
                "The stairwell on floor=N MUST share the same x,y as its counterpart on floor=N-1. "
                "All other rooms on floor=N are positioned relative to that stairwell "
                "using the same direction offsets as the floor below."
            ),
            "how_to_build_first_basement": [
                "1. Note ground stairwell x,y (e.g. lobby at 400,300).",
                "2. create_room 'stair_b1' floor=-1, x=400, y=300  (SAME x,y as lobby).",
                "3. create_room all floor=-1 rooms with floor=-1, from_room='stair_b1', from_dir=<cardinal>.",
                "4. connect_rooms(lobby → stair_b1, direction='down').",
            ],
            "how_to_build_second_basement": [
                "1. Note stair_b1 x,y on floor=-1 (e.g. 400,300).",
                "2. create_room 'stair_b2' floor=-2, x=400, y=300  (SAME x,y as stair_b1).",
                "3. create_room all floor=-2 rooms with floor=-2, from_room='stair_b2', from_dir=<cardinal>.",
                "4. connect_rooms(stair_b1 → stair_b2, direction='down')  ← NOT lobby→stair_b2.",
            ],
            "how_to_build_upper_floors": [
                "1. Note lobby x,y (e.g. 400,300).",
                "2. create_room 'stair_f1' floor=1, x=400, y=300.",
                "3. create_room all floor=1 rooms with floor=1, from_room='stair_f1', from_dir=<cardinal>.",
                "4. connect_rooms(lobby → stair_f1, direction='up').",
                "5. For floor=2: create_room 'stair_f2' floor=2, x=400, y=300.",
                "6. create_room all floor=2 rooms with floor=2, from_room='stair_f2', from_dir=<cardinal>.",
                "7. connect_rooms(stair_f1 → stair_f2, direction='up')  ← NOT lobby→stair_f2.",
            ],
            "spatial_coherence": (
                "A room at floor=2 (620,300) is directly above floor=1 (620,300) which is "
                "directly above floor=0 (620,300). Negative floors stack downward the same way. "
                "Switching floors in the editor shows ghost nodes from adjacent floors."
            ),
            "critical": "basement/upper rooms on floor=0 collide on the ground canvas — always set the correct floor value.",
        },
    }


@mcp.tool()
def validate_zone(zone_id: str) -> dict[str, Any]:
    """
    Validate a zone's rooms the way the WorldForge app's Validate panel does.
    Run after drafting or editing a zone to catch broken references before play.

    Checks: missing room/feature descriptions, unknown exit destinations,
    self-referencing and asymmetric exits (one_way honoured), orphaned and
    disconnected rooms, depth jumps, unknown entity templates in spawns,
    entity loot referencing unknown items, glyph prerequisite cycles to
    unknown glyphs, and the feature-density metric (aim >= 0.5 draws/room).

    Returns {"errors": [...], "warnings": [...], "info": [...], "counts": {...}}.
    """
    _require_zone(zone_id)
    errors: list[str] = []
    warnings: list[str] = []
    info: list[str] = []

    def _load_ids(subdir: str) -> set[str]:
        d = _world_root() / subdir
        ids: set[str] = set()
        if d.exists():
            for f in d.glob("*.yaml"):
                try:
                    doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
                except Exception:
                    errors.append(f"{subdir}/{f.name}: unparseable YAML")
                    continue
                ids.add(str(doc.get("id", f.stem)))
        return ids

    entity_ids = _load_ids("entities")
    item_ids = _load_ids("items")

    # All room ids across every zone (cross-zone exit targets).
    all_room_ids: set[str] = set()
    for zdir in _zones_dir().iterdir() if _zones_dir().exists() else []:
        rd = zdir / "rooms"
        if rd.is_dir():
            for f in rd.glob("*.yaml"):
                all_room_ids.add(f"{zdir.name}:{f.stem}")

    rooms: dict[str, dict] = {}
    for f in sorted(_rooms_dir(zone_id).glob("*.yaml")):
        try:
            rooms[f.stem] = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        except Exception:
            errors.append(f"{f.stem}: unparseable YAML")
    if not rooms:
        return {
            "errors": ["zone has no rooms"],
            "warnings": [],
            "info": [],
            "counts": {"err": 1, "warn": 0},
        }

    def _dest_id(dest: str) -> str:
        dest = str(dest or "")
        return dest if ":" in dest else f"{zone_id}:{dest}"

    def _exits(doc: dict) -> dict[str, str]:
        raw = doc.get("exits")
        out = {}
        if isinstance(raw, dict):
            for direction, ex in raw.items():
                if isinstance(ex, dict):
                    out[str(direction)] = _dest_id(ex.get("destination", ""))
                elif isinstance(ex, str):
                    out[str(direction)] = _dest_id(ex)
        return out

    multi = len(rooms) > 1
    neighbors: dict[str, set[str]] = {slug: set() for slug in rooms}

    for slug, doc in rooms.items():
        rid = f"{zone_id}:{slug}"
        desc = doc.get("description")
        base = desc.get("base") if isinstance(desc, dict) else desc
        if not str(base or "").strip():
            warnings.append(f"Missing description: {slug}")

        exits = _exits(doc)
        if not exits and multi:
            warnings.append(f"Orphaned room (no exits): {slug}")

        for direction, dest in exits.items():
            if dest == rid:
                errors.append(f"Self-referencing exit: {slug} ({direction})")
                continue
            dzone, _, dslug = dest.partition(":")
            if dest not in all_room_ids:
                errors.append(f"Broken exit target: {slug} {direction} -> {dest}")
                continue
            if dzone != zone_id:
                info.append(f"External exit {slug} {direction} -> {dest}")
                continue
            neighbors[slug].add(dslug)
            neighbors.setdefault(dslug, set()).add(slug)
            # Return-exit check (one_way honoured when present on the exit).
            raw_exit = doc["exits"][direction] if isinstance(doc.get("exits"), dict) else {}
            one_way = bool(raw_exit.get("one_way")) if isinstance(raw_exit, dict) else False
            back = any(d == rid for d in _exits(rooms.get(dslug, {})).values())
            if not back and one_way:
                info.append(f"One-way: {slug} -> {dslug} ({direction})")
            elif not back:
                warnings.append(
                    f"Asymmetric exit (no return, not marked one_way): "
                    f"{slug} -> {dslug} ({direction})"
                )

        feats = doc.get("features")
        if isinstance(feats, list):
            for feat in feats:
                if isinstance(feat, dict) and feat.get("name"):
                    if not str(feat.get("description", "") or "").strip():
                        warnings.append(f'Feature "{feat["name"]}" missing description ({slug})')

        spawns = doc.get("entity_spawns")
        if isinstance(spawns, list):
            for s in spawns:
                tid = s.get("template") if isinstance(s, dict) else None
                if tid and tid not in entity_ids:
                    errors.append(f'Unknown entity template "{tid}" in {slug}')

    # Connectivity: everything reachable (undirected) from the first room.
    if multi:
        start = next(iter(rooms))
        seen = {start}
        stack = [start]
        while stack:
            for nxt in neighbors.get(stack.pop(), ()):
                if nxt in rooms and nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        for slug in rooms:
            if slug not in seen:
                warnings.append(f"Disconnected room: {slug}")
            if len(neighbors.get(slug, ())) <= 1:
                info.append(f"Dead-end (<=1 connected neighbor): {slug}")

    # Depth discontinuity across internal exits.
    depth_of = {slug: int(doc.get("depth", 0) or 0) for slug, doc in rooms.items()}
    for slug, doc in rooms.items():
        for direction, dest in _exits(doc).items():
            dzone, _, dslug = dest.partition(":")
            if dzone == zone_id and dslug in depth_of:
                da, db = depth_of[slug], depth_of[dslug]
                if abs(da - db) >= 2:
                    info.append(f"Depth jump {da} -> {db}: {slug} to {dslug}")

    # Entity loot -> known items (only entities actually spawned in this zone).
    spawned = {
        s.get("template")
        for doc in rooms.values()
        for s in (doc.get("entity_spawns") or [])
        if isinstance(s, dict)
    }
    ent_dir = _world_root() / "entities"
    if ent_dir.exists():
        for f in ent_dir.glob("*.yaml"):
            try:
                doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            except Exception:
                continue
            eid = str(doc.get("id", f.stem))
            if eid not in spawned:
                continue
            for entry in doc.get("loot") or []:
                iid = entry.get("item") if isinstance(entry, dict) else entry
                if iid and iid not in item_ids:
                    errors.append(f'Entity {eid} loot references unknown item "{iid}"')

    # Glyph prerequisites (global check, cheap).
    glyph_dir = _world_root() / "glyphs"
    if glyph_dir.exists():
        glyph_docs = {}
        for f in glyph_dir.glob("*.yaml"):
            try:
                doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            except Exception:
                continue
            glyph_docs[str(doc.get("id", f.stem))] = doc
        for gid, doc in glyph_docs.items():
            for p in doc.get("prerequisites") or []:
                if p and p not in glyph_docs:
                    errors.append(f"Glyph {gid} prerequisite unknown: {p}")

    # Feature density (Epitaph metric): gameplay draws per room, aim >= 0.5.
    if multi:
        draws = 0
        for doc in rooms.values():
            draws += len(doc.get("features") or [])
            draws += len(doc.get("entity_spawns") or [])
            draws += len(doc.get("hazards") or [])
            ambient = doc.get("ambient")
            if isinstance(ambient, dict) and ambient.get("lines"):
                draws += 1
        density = draws / len(rooms)
        line = f"Feature density {density:.2f} ({draws} draws / {len(rooms)} rooms)"
        if density < 0.5:
            warnings.append(
                f"Low feature density: {density:.2f} ({draws} draws / {len(rooms)} rooms; "
                "aim >= 0.5 — add features, spawns, hazards or ambient)"
            )
        else:
            info.append(line)

    return {
        "errors": errors,
        "warnings": warnings,
        "info": info,
        "counts": {"err": len(errors), "warn": len(warnings)},
    }


if __name__ == "__main__":
    mcp.run()
