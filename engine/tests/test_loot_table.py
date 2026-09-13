"""Drop-table normalization on entity templates."""

from sage.world.models import EntityTemplate


class TestLootTable:
    def test_bare_strings_coerce_with_default_chance(self):
        e = EntityTemplate(id="e", name="e", loot=["lamp_oil"])
        assert e.loot[0].template == "lamp_oil"
        assert e.loot[0].chance == 0.6
        assert e.loot[0].count == 1

    def test_full_rows_pass_through(self):
        e = EntityTemplate(id="e", name="e", loot=[{"template": "wick", "chance": 1.0, "count": 4}])
        assert e.loot[0].chance == 1.0
        assert e.loot[0].count == 4
