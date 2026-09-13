"""Resolved proficiency tree: leaves plus inferred internal prefix nodes."""

from __future__ import annotations

from sage.proficiencies.models import ProficiencyLeafDefinition, ProficiencyNode
from sage.proficiencies.validation import _effective_depth, prefix_closure


def _display_name(leaf_id: str, explicit: str) -> str:
    if (explicit or "").strip():
        return explicit.strip()
    tail = leaf_id.split(".")[-1].replace("_", " ")
    return tail[:1].upper() + tail[1:] if tail else leaf_id


class ProficiencyRegistry:
    def __init__(self, leaves: list[ProficiencyLeafDefinition]):
        self.leaves: dict[str, ProficiencyLeafDefinition] = {x.id: x for x in leaves}
        self.nodes: dict[str, ProficiencyNode] = {}
        self._build_nodes(leaves)

    def _build_nodes(self, leaves: list[ProficiencyLeafDefinition]) -> None:
        leaf_ids = [x.id for x in leaves]
        all_ids = sorted(prefix_closure(leaf_ids))
        leaf_set = set(leaf_ids)

        for nid in all_ids:
            parts = nid.split(".")
            domain = parts[0]
            is_leaf = nid in leaf_set
            parent_id: str | None = ".".join(parts[:-1]) if len(parts) > 1 else None
            if is_leaf:
                src = self.leaves[nid]
                depth = _effective_depth(src)
                name = _display_name(nid, src.name)
                desc = src.description
                weights = dict(src.stat_weights)
                tags = list(src.tags)
            else:
                depth = max(1, min(4, len(parts)))
                name = parts[-1].replace("_", " ").title()
                desc = ""
                weights = {}
                tags = []
            children = [
                c for c in all_ids if c.startswith(nid + ".") and c.count(".") == nid.count(".") + 1
            ]
            self.nodes[nid] = ProficiencyNode(
                id=nid,
                is_leaf=is_leaf,
                domain=domain,
                name=name,
                description=desc,
                tree_depth=depth,
                stat_weights=weights,
                children=sorted(children),
                parent_id=parent_id,
                tags=tags,
            )

    def get_leaf(self, leaf_id: str) -> ProficiencyLeafDefinition | None:
        return self.leaves.get(leaf_id)

    def get_node(self, node_id: str) -> ProficiencyNode | None:
        return self.nodes.get(node_id)

    @property
    def leaf_ids(self) -> list[str]:
        return sorted(self.leaves.keys())

    def total_level_cap(self) -> int:
        return 5000

    def leaf_level_cap(self) -> int:
        return 200
