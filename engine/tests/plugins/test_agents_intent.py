"""M4 intent: JSON parse, path compile, memory ring."""

from sage_plugin_agents.body import route_path
from sage_plugin_agents.brain import compile_goal, parse_intent
from sage_plugin_agents.feelings import MEMORY_CAP, recall, remember

EXITS = {
    "z:a": {"east": "z:b"},
    "z:b": {"west": "z:a", "east": "z:c", "north": "z:d"},
    "z:c": {"west": "z:b"},
    "z:d": {"south": "z:b"},
}


def _find_none(_target):
    return None


class TestParseIntent:
    def test_clean_json(self):
        raw = '{"goal": "wander_to", "target": "market_row", "why": "bored", "say": ""}'
        intent = parse_intent(raw)
        assert intent == {"goal": "wander_to", "target": "market_row", "why": "bored", "say": ""}

    def test_json_wrapped_in_prose(self):
        raw = 'Sure! Here is my choice:\n{"goal": "rest", "target": "", "why": "tired"}\nDone.'
        assert parse_intent(raw)["goal"] == "rest"

    def test_unknown_goal_rejected(self):
        assert parse_intent('{"goal": "fly_away", "target": "moon"}') is None

    def test_garbage_rejected(self):
        assert parse_intent("no json here") is None
        assert parse_intent('{"goal": broken') is None

    def test_why_capped(self):
        raw = '{"goal": "idle", "why": "' + "x" * 500 + '"}'
        assert len(parse_intent(raw)["why"]) <= 120


class TestRoutePath:
    def test_multi_step(self):
        assert route_path("z:a", "z:c", EXITS) == ["east", "east"]

    def test_already_there(self):
        assert route_path("z:a", "z:a", EXITS) == []

    def test_unreachable(self):
        assert route_path("z:a", "z:nowhere", EXITS) is None


class TestCompileGoal:
    def _i(self, goal, target="", say=""):
        return {"goal": goal, "target": target, "why": "", "say": say}

    def test_wander_to_paths(self):
        label, cmds = compile_goal(self._i("wander_to", "d"), "z:a", "z", EXITS, _find_none)
        assert label == "wander_to d"
        assert cmds == ["east", "north"]

    def test_wander_to_resolves_slug_in_another_zone(self):
        exits = {
            **EXITS,
            "z:d": {"south": "z:b", "up": "pub:apartment_1"},
            "pub:apartment_1": {"down": "z:d"},
        }
        label, cmds = compile_goal(
            self._i("wander_to", "apartment_1"), "z:a", "z", exits, _find_none
        )
        assert cmds == ["east", "north", "up"]

    def test_wander_to_unreachable_none(self):
        assert compile_goal(self._i("wander_to", "mars"), "z:a", "z", EXITS, _find_none) is None

    def test_rest_scavenge_idle(self):
        assert compile_goal(self._i("rest"), "z:a", "z", EXITS, _find_none) == ("rest", ["rest"])
        assert compile_goal(self._i("scavenge"), "z:a", "z", EXITS, _find_none) == (
            "scavenge",
            ["search"],
        )
        assert compile_goal(self._i("idle"), "z:a", "z", EXITS, _find_none) is None

    def test_talk_sanitized(self):
        label, cmds = compile_goal(
            self._i("talk", say='say "hi\nthere"'), "z:a", "z", EXITS, _find_none
        )
        assert cmds[0].startswith("say ")
        assert "\n" not in cmds[0]

    def test_hunt_routes_to_spawn_room(self):
        label, cmds = compile_goal(
            self._i("hunt", "drone"), "z:a", "z", EXITS, lambda t: "z:c" if t == "drone" else None
        )
        assert label == "hunt drone"
        assert cmds == ["east", "east"]

    def test_hunt_unknown_entity_none(self):
        assert compile_goal(self._i("hunt", "dragon"), "z:a", "z", EXITS, _find_none) is None

    def test_sell_routes_to_buyer_and_sells_all(self):
        label, cmds = compile_goal(
            self._i("sell"), "z:a", "z", EXITS, _find_none, buyer_room_finder=lambda: "z:c"
        )
        assert label == "sell salvage"
        assert cmds == ["east", "east", "sell all"]

    def test_sell_no_buyer_none(self):
        assert (
            compile_goal(
                self._i("sell"), "z:a", "z", EXITS, _find_none, buyer_room_finder=lambda: None
            )
            is None
        )

    def test_buy_routes_to_seller_and_buys(self):
        label, cmds = compile_goal(
            self._i("buy", "ration"),
            "z:a",
            "z",
            EXITS,
            _find_none,
            seller_room_finder=lambda item: "z:d" if item == "ration" else None,
        )
        assert label == "buy ration"
        assert cmds == ["east", "north", "buy ration"]


class TestMemoryRing:
    def test_remember_recall_capped(self):
        stats = {}
        for i in range(MEMORY_CAP + 10):
            remember(stats, f"event {i}")
        ring = recall(stats, MEMORY_CAP + 10)
        assert len(ring) == MEMORY_CAP
        assert ring[-1] == f"event {MEMORY_CAP + 9}"

    def test_recall_empty(self):
        assert recall({}) == []
