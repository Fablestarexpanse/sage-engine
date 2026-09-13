"""Crafting recipes, deconstruction yields, and drop-table normalization."""

from sage.commands.crafting import missing_for, scrap_yield
from sage.world.models import EntityTemplate, ItemTemplate


def _inv(*templates):
    return [{"id": f"{t}_{i}", "template": t, "name": t} for i, t in enumerate(templates)]


class TestMissingFor:
    def test_ready_when_all_parts_present(self):
        recipe = {"power_cell": 2, "scrap_blade": 1}
        assert missing_for(recipe, _inv("power_cell", "power_cell", "scrap_blade")) == {}

    def test_reports_gaps(self):
        recipe = {"power_cell": 2, "scrap_blade": 1}
        assert missing_for(recipe, _inv("power_cell")) == {"power_cell": 1, "scrap_blade": 1}


class TestScrapYield:
    def test_explicit_scraps_win(self):
        t = ItemTemplate(id="x", name="x", recipe={"a": 4}, scraps={"b": 2})
        assert scrap_yield(t) == {"b": 2}

    def test_falls_back_to_half_recipe(self):
        t = ItemTemplate(id="x", name="x", recipe={"a": 4, "b": 1})
        assert scrap_yield(t) == {"a": 2}

    def test_never_scraps_to_nothing_with_recipe(self):
        t = ItemTemplate(id="x", name="x", recipe={"a": 1})
        assert scrap_yield(t) == {"a": 1}

    def test_plain_item_yields_nothing(self):
        assert scrap_yield(ItemTemplate(id="x", name="x")) == {}


class TestLootTable:
    def test_bare_strings_coerce_with_default_chance(self):
        e = EntityTemplate(id="e", name="e", loot=["power_cell"])
        assert e.loot[0].template == "power_cell"
        assert e.loot[0].chance == 0.6
        assert e.loot[0].count == 1

    def test_full_rows_pass_through(self):
        e = EntityTemplate(
            id="e", name="e", loot=[{"template": "charge_cell", "chance": 1.0, "count": 4}]
        )
        assert e.loot[0].chance == 1.0
        assert e.loot[0].count == 4

    def test_yields_batch_field(self):
        t = ItemTemplate(id="x", name="x", recipe={"power_cell": 1}, yields=3)
        assert t.yields == 3
