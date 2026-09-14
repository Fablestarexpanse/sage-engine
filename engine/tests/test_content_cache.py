"""DirCache: plugin content reloads when its directory changes, and only then."""

from sage.world.content_cache import DirCache


def test_reloads_on_add_and_change_only(tmp_path):
    d = tmp_path / "things"
    d.mkdir()
    (d / "one.yaml").write_text("a: 1\n", encoding="utf-8")
    loads: list[list[str]] = []

    def loader(directory):
        names = sorted(f.stem for f in directory.glob("*.yaml"))
        loads.append(names)
        return names

    cache = DirCache(d, loader)
    assert cache.get() == ["one"]
    assert cache.get() == ["one"] and len(loads) == 1
    (d / "two.yaml").write_text("b: 2\n", encoding="utf-8")
    assert cache.get() == ["one", "two"] and len(loads) == 2


def test_missing_directory_loads_once(tmp_path):
    calls = []
    cache = DirCache(tmp_path / "absent", lambda d: calls.append(d) or "empty")
    assert cache.get() == "empty" and cache.get() == "empty"
    assert len(calls) == 1
