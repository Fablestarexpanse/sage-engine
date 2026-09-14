"""Room positions from exits, for zones without editor layout (`.positions.json`).

Maps and editors place rooms by stored canvas positions. A zone written by hand or by a tool
that never saved a layout has none, and every room would sit on the same spot. `layout_from_exits`
walks the exit graph from the first room and puts each neighbour one grid step away in the exit's
direction (the same spacing WorldForge and its MCP tools use), stepping further out when that
spot is taken. Stored positions always win; only rooms without one are placed.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping

STEP_X = 220.0
STEP_Y = 130.0
OFFSETS = {
    "north": (0, -1),
    "south": (0, 1),
    "east": (1, 0),
    "west": (-1, 0),
    "northeast": (1, -1),
    "northwest": (-1, -1),
    "southeast": (1, 1),
    "southwest": (-1, 1),
}
ORIGIN = (400.0, 300.0)


def layout_from_exits(
    exits: Mapping[str, Mapping[str, str]],
    known: Mapping[str, tuple[float, float]] | None = None,
) -> dict[str, tuple[float, float]]:
    """{room: (x, y)} for every room in `exits` ({room: {direction: neighbour}})."""
    placed: dict[str, tuple[float, float]] = dict(known or {})
    taken = {(round(x), round(y)) for x, y in placed.values()}

    def free_spot(x: float, y: float, dx: int, dy: int) -> tuple[float, float]:
        step = 1
        while (round(x), round(y)) in taken:
            step += 1
            x += (dx or 1) * STEP_X
            y += dy * STEP_Y
            if step > 50:
                break
        return x, y

    for start in sorted(exits):
        if start in placed and not any(n not in placed for n in exits[start].values()):
            continue
        if start not in placed:
            x, y = free_spot(*ORIGIN, 1, 0) if taken else ORIGIN
            placed[start] = (x, y)
            taken.add((round(x), round(y)))
        queue = deque([start])
        while queue:
            room = queue.popleft()
            rx, ry = placed[room]
            for direction, neighbour in sorted(exits.get(room, {}).items()):
                if neighbour not in exits or neighbour in placed:
                    continue
                dx, dy = OFFSETS.get(direction, (1, 0))
                x, y = free_spot(rx + dx * STEP_X, ry + dy * STEP_Y, dx, dy)
                placed[neighbour] = (x, y)
                taken.add((round(x), round(y)))
                queue.append(neighbour)
    return placed
