"""Conduit panels through the host: attribute sheet and a skill tree of touched leaves with actions."""

from __future__ import annotations

import asyncio

from sage_plugin_conduit.catalog_loader import load_proficiency_catalog_from_disk
from tests.fakes import repo_world


def _sections(host, stats):
    return asyncio.run(host.server.snapshot_contributors.build("hero", stats))


def test_panels_are_declared_with_titles(plugin_host):
    host = plugin_host(repo_world(), ["conduit"])
    assert [(p["id"], p["kind"], p["section"], p["title"]) for p in host.server.panels.specs()] == [
        ("conduit.attributes", "stat_sheet", "conduit", "Conduit"),
        ("conduit.skills", "tree", "conduit_skills", "Skills"),
    ]


def test_attribute_sheet_and_skill_tree(plugin_host):
    host = plugin_host(repo_world(), ["conduit"])
    stats = {
        "conduit": {
            "conduit_attributes": {"FRT": 14, "RFX": 11, "ACU": 10, "RSV": 9, "PRS": 12},
            "proficiencies": {},
        }
    }
    sections = _sections(host, stats)
    sheet = sections["conduit"]["stats"]
    assert [row["label"] for row in sheet] == [
        "Fortitude",
        "Reflex",
        "Acuity",
        "Resolve",
        "Presence",
        "Resonance",
    ]
    assert sheet[0]["value"] == 14 and sheet[-1] == {"label": "Resonance", "value": 0, "max": 5000}

    tree = sections["conduit_skills"]["nodes"]
    assert tree and all(domain["children"] == [] and "." not in domain["id"] for domain in tree)

    # Touch two real leaves: one levelled, one locked at level 0.
    leaves = load_proficiency_catalog_from_disk(host.world.content_dir).leaves
    levelled, locked = leaves[0].id, leaves[1].id
    stats["conduit"]["proficiencies"] = {
        levelled: {"level": 7, "peak": 9, "state": "raise"},
        locked: {"level": 0, "peak": 0, "state": "lock"},
    }
    tree = _sections(host, stats)["conduit_skills"]["nodes"]
    children = {leaf["id"]: leaf for domain in tree for leaf in domain["children"]}
    assert set(children) == {levelled, locked}
    assert children[levelled]["value"] == 7 and children[levelled]["max"] == 200
    assert children[levelled]["tone"] == "good"
    assert [a["command"] for a in children[levelled]["actions"]] == [
        f"lower {levelled}",
        f"lock {levelled}",
    ]
    assert "tone" not in children[locked]
    assert [a["command"] for a in children[locked]["actions"]] == [
        f"raise {locked}",
        f"lower {locked}",
    ]
    domain = next(d for d in tree if d["id"] == levelled.split(".")[0])
    assert domain["value"] >= 7
