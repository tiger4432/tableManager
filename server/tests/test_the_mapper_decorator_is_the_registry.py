# -*- coding: utf-8 -*-
"""S-188 ⓒ. `@mapper` registers, so 「which mappers exist」 has an answer.

🔴 BEFORE THIS IT REGISTERED NOTHING. `mapper_sdk.mapper` wrapped an author's
`(df, db) -> df` into the `(db, payloads, rule)` the worker calls and returned it -- that was
all. So a rule named its mapper with TWO cells, `mapper_module` + `mapper_function`, and the
worker resolved them with `importlib`; nothing could list the mappers, which is what the
builder needs and what ⓓ needs before it can collapse those two cells into one.

⚠️ THIS FILE BRINGS ITS OWN MAPPERS. `server/mappers/**` is the OWNER's and gitignored, and
measured on this box it registers ZERO -- no file there uses the decorator yet. A test that
counted the real package would therefore assert nothing here, and would assert something
different on the owner's machine.

🔴 AND A RELOAD IS THE HARD CASE. `system_reload` drops `mappers.*` from `sys.modules` but
not `mapper_sdk`, so the registry outlives the modules it points into. It is cleared there,
and a re-import is NOT a collision -- sameness is decided by `module.qualname`, not by object
identity, or a reload would refuse every mapper it just refreshed.
"""
import os
import sys
import textwrap

import pytest

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

import mapper_sdk                                                    # noqa: E402


@pytest.fixture(autouse=True)
def _clean_registry():
    """⚠️ The registry is process-wide, like every other singleton here."""
    before = dict(mapper_sdk.MAPPER_REGISTRY), dict(mapper_sdk.MAPPER_PARAMS)
    looked = mapper_sdk._DISCOVERY_ATTEMPTED
    mapper_sdk.reset_registry()
    yield
    mapper_sdk.reset_registry()
    mapper_sdk.MAPPER_REGISTRY.update(before[0])
    mapper_sdk.MAPPER_PARAMS.update(before[1])
    mapper_sdk._DISCOVERY_ATTEMPTED = looked


def test_a_decorated_mapper_is_registered_under_its_own_name():
    @mapper_sdk.mapper(target_table="t", params=("x_col", "y_col"))
    def build_rows(df, db):
        return None

    assert mapper_sdk.MAPPER_REGISTRY["build_rows"] is build_rows
    assert mapper_sdk.MAPPER_PARAMS["build_rows"] == ("x_col", "y_col")


def test_the_decorator_still_returns_the_worker_s_calling_convention():
    """🔴 THE REGRESSION LINE. Registration may not change what a rule gets when it calls
    the mapper -- `(db, payloads, rule=None)` returning an envelope."""
    @mapper_sdk.mapper(target_table="t")
    def noop(df, db):
        return None

    assert noop(None, [], rule={"target_table": "t"}) == {"updates": []}


def test_a_declared_name_wins_over_the_function_name():
    @mapper_sdk.mapper(target_table="t", name="published_name")
    def internal(df, db):
        return None

    assert "published_name" in mapper_sdk.MAPPER_REGISTRY
    assert "internal" not in mapper_sdk.MAPPER_REGISTRY


def test_two_modules_claiming_one_name_are_refused_by_name():
    """⛔ NEVER RESOLVED. Which one a rule meant would depend on import order, and nothing
    would say so -- the posture `load_chain_rules` already takes toward a rule name claimed
    by both the file and a synthesized rule (S-179 ①, 판정 292)."""
    def first(db, payloads, rule=None): ...
    def second(db, payloads, rule=None): ...
    first.__module__, second.__module__ = "mappers.one", "mappers.two"

    mapper_sdk.register("shared", first)
    with pytest.raises(mapper_sdk.MapperNameClaimedTwice) as caught:
        mapper_sdk.register("shared", second)
    assert "mappers.one" in str(caught.value) and "mappers.two" in str(caught.value)


def test_re_importing_the_same_module_replaces_rather_than_collides():
    """🔴 THE RELOAD CASE. The decorator builds a NEW wrapper each import, so an
    identity-based rule would call a refresh a collision."""
    def v1(db, payloads, rule=None): ...
    def v2(db, payloads, rule=None): ...
    for fn in (v1, v2):
        fn.__module__, fn.__qualname__ = "mappers.same", "build_rows"

    mapper_sdk.register("build_rows", v1)
    mapper_sdk.register("build_rows", v2)          # must not raise
    assert mapper_sdk.MAPPER_REGISTRY["build_rows"] is v2


def test_two_decorated_functions_of_one_name_in_one_module_do_not_collide():
    """⛔ THE REGRESSION I SHIPPED FOR ONE RUN. The first spelling compared
    `module.qualname`, and a function defined INSIDE a test carries `…<locals>.emit` — so two
    tests of `test_mapper_sdk.py` that both name their mapper `emit` looked like two
    different mappers and the second was refused. Two existing tests went red.

    🔴 A module cannot hold two top-level functions of one name — Python decides that — so
    the module is the whole of what 「the same mapper」 means, and this asserts it with the
    decorator rather than with hand-set attributes, because the decorator is what broke.
    """
    # ⚠️ THE TWO `def`s MUST BE AT DIFFERENT SOURCE LOCATIONS. A first version of this test
    # built both from ONE nested `def`, so their qualnames were IDENTICAL and the test passed
    # under the very spelling it was written to refuse — a fixture both rules agree on
    # decides nothing. Two enclosing scopes is what makes the qualnames differ while the
    # module stays the same, which is exactly the shape `test_mapper_sdk` has.
    def scope_one():
        @mapper_sdk.mapper(target_table="t", name="emit")
        def emit(df, db):
            return None
        return emit

    def scope_two():
        @mapper_sdk.mapper(target_table="t", name="emit")
        def emit(df, db):
            return None
        return emit

    first, second = scope_one(), scope_two()
    assert first.__qualname__ != second.__qualname__, "the fixture is not a discriminator"
    assert first.__module__ == second.__module__
    assert mapper_sdk.MAPPER_REGISTRY["emit"] is second


def test_reset_registry_forgets_the_params_too():
    """⚠️ Two dicts, one lifetime. A stale `MAPPER_PARAMS` entry would make the loader warn
    about a name that IS declared, or accept one that is not."""
    mapper_sdk.register("x", lambda *a, **k: None, ("a",))
    mapper_sdk.reset_registry()
    assert not mapper_sdk.MAPPER_REGISTRY and not mapper_sdk.MAPPER_PARAMS


# ---------------------------------------------------------------------------
# 🔴 One broken mapper must not cost the others
# ---------------------------------------------------------------------------

def test_discovery_isolates_a_module_that_cannot_be_imported(tmp_path, monkeypatch):
    """⛔ THE POINT OF ⓒ's ISOLATION (S-177's posture). These files are the owner's; an
    ImportError in one is a thing to be NAMED, not a reason for the chain to come up with no
    mappers at all."""
    pkg = tmp_path / "s188pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "good.py").write_text(textwrap.dedent("""
        import mapper_sdk
        @mapper_sdk.mapper(target_table="t", params=("lot_column",))
        def good_rows(df, db):
            return None
        """), encoding="utf-8")
    (pkg / "broken.py").write_text("raise TypeError('boom')\n", encoding="utf-8")

    monkeypatch.syspath_prepend(str(tmp_path))
    registered, refusals = mapper_sdk.discover("s188pkg")

    assert "good_rows" in registered, "the healthy module still registered"
    assert list(refusals) == ["s188pkg.broken"], refusals
    assert "TypeError" in refusals["s188pkg.broken"] and "boom" in refusals["s188pkg.broken"]
    assert mapper_sdk.MAPPER_PARAMS["good_rows"] == ("lot_column",)


def test_a_package_that_cannot_be_imported_at_all_is_reported_not_raised():
    registered, refusals = mapper_sdk.discover("s188_no_such_package")
    assert list(refusals) == ["s188_no_such_package"]
    assert registered == ()


# ---------------------------------------------------------------------------
# The reload seat
# ---------------------------------------------------------------------------

def _probe_package(tmp_path, monkeypatch, files, package="probe_mappers"):
    pkg = tmp_path / package
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    for name, text in files.items():
        (pkg / name).write_text(text, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    return pkg


def _forget_probe(monkeypatch, package):
    for module in [m for m in sys.modules if m.startswith(package)]:
        monkeypatch.delitem(sys.modules, module)
    for name in [n for n, fn in mapper_sdk.MAPPER_REGISTRY.items() if mapper_sdk._origin(fn).startswith(package)]:
        mapper_sdk.MAPPER_REGISTRY.pop(name, None)
    mapper_sdk.MAPPER_REFUSALS.pop(package + ".m", None)


MAPPER_TEXT = "from mapper_sdk import mapper\nVERSION = %r\n\n@mapper()\ndef probe_%s(df, db):\n    return df\n"


def test_a_changed_mapper_file_is_swapped_in_only_once_it_imports(tmp_path, monkeypatch):
    """e6a0bdbbd ③ (owner 10-21 ㄱ 「맵퍼 폴더도 감시해」): a changed file is imported again and swapped in when it
    imports; one that does not keeps the module and the names it had, and is said by module and why; a file gone takes
    its names with it."""
    pkg = _probe_package(tmp_path, monkeypatch, {"m.py": MAPPER_TEXT % ("v1", "one")}, "probe_swap")
    monkeypatch.setattr(mapper_sdk, "_DISCOVERY_ATTEMPTED", False)
    try:
        mapper_sdk.discover("probe_swap")
        monkeypatch.setattr(mapper_sdk, "_DISCOVERY_ATTEMPTED", True)
        old = mapper_sdk.MAPPER_REGISTRY["probe_one"]
        assert sys.modules["probe_swap.m"].VERSION == "v1"

        (pkg / "m.py").write_text("import nowhere_at_all\n" + MAPPER_TEXT % ("v2", "one"), encoding="utf-8")
        kept = mapper_sdk.reload_modules([str(pkg / "m.py")], package="probe_swap")
        assert "probe_swap.m" in kept and "nowhere_at_all" in kept["probe_swap.m"]
        assert mapper_sdk.MAPPER_REGISTRY["probe_one"] is old, "the old one is kept"
        assert sys.modules["probe_swap.m"].VERSION == "v1"
        assert "probe_swap.m" in mapper_sdk.MAPPER_REFUSALS, "and said"

        (pkg / "m.py").write_text(MAPPER_TEXT % ("v3", "one") + "\n# a longer file\n", encoding="utf-8")
        assert mapper_sdk.reload_modules([str(pkg / "m.py")], package="probe_swap") == {}
        assert mapper_sdk.MAPPER_REGISTRY["probe_one"] is not old and sys.modules["probe_swap.m"].VERSION == "v3"
        assert "probe_swap.m" not in mapper_sdk.MAPPER_REFUSALS

        (pkg / "m.py").unlink()
        assert mapper_sdk.reload_modules([str(pkg / "m.py")], package="probe_swap") == {}
        assert "probe_one" not in mapper_sdk.MAPPER_REGISTRY, "a file gone takes its names"
    finally:
        _forget_probe(monkeypatch, "probe_swap")


def test_a_module_that_keeps_failing_is_walked_once_and_found_when_its_file_changes(tmp_path, monkeypatch):
    """A refused walk is not walked again per miss (lead 10-20, app QA: per group in the chain); the fixed file is
    found when the watcher says it changed (`reload_modules`, e6a0bdbbd) - it compared the folder's stamps per miss
    before."""
    from chain import rule_run

    pkg = _probe_package(tmp_path, monkeypatch, {"broken.py": "raise ImportError('still broken')\n"})
    walks = []
    real_walk = mapper_sdk._walk
    monkeypatch.setattr(mapper_sdk, "_walk", lambda package: walks.append(package) or real_walk(package))
    monkeypatch.setattr(mapper_sdk, "ensure_discovered",
                        lambda package="mappers", ensure=mapper_sdk.ensure_discovered: ensure("probe_mappers"))
    monkeypatch.setattr(mapper_sdk, "_DISCOVERY_ATTEMPTED", False)
    try:
        for _ in range(5):
            assert rule_run.runnable("probe_fixed") is None
        assert walks == ["probe_mappers"], "a module that keeps failing walked again: %d walks" % len(walks)
        assert "probe_mappers.broken" in mapper_sdk.MAPPER_REFUSALS

        (pkg / "broken.py").write_text(MAPPER_TEXT % ("ok", "fixed"), encoding="utf-8")
        assert rule_run.runnable("probe_fixed") is None, "not before the watcher says"
        mapper_sdk.reload_modules([str(pkg / "broken.py")], package="probe_mappers")
        assert rule_run.runnable("probe_fixed") is not None, "the fixed file is found"
        assert walks == ["probe_mappers"] and "probe_mappers.broken" not in mapper_sdk.MAPPER_REFUSALS
    finally:
        mapper_sdk.MAPPER_REGISTRY.pop("probe_fixed", None)
        for module in [m for m in sys.modules if m.startswith("probe_mappers")]:
            monkeypatch.delitem(sys.modules, module)


def test_a_reload_does_not_empty_the_registry_under_a_walk(monkeypatch):
    """A reload's reset waits for a walk in flight (lead 10-20): reset in the middle of another thread's walk
    emptied what that walk had registered, and the name it was walking for read as unknown."""
    import threading

    inside, release = threading.Event(), threading.Event()

    def walk(package):
        mapper_sdk.register("walked", lambda db, payload: [])
        if not inside.is_set():
            inside.set()
            release.wait(10)
        return tuple(mapper_sdk.MAPPER_REGISTRY), {}

    monkeypatch.setattr(mapper_sdk, "_walk", walk)
    first = threading.Thread(target=mapper_sdk.discover)
    first.start()
    assert inside.wait(10)
    reload = threading.Thread(target=mapper_sdk.rediscover)
    reload.start()
    reload.join(0.3)
    held = "walked" in mapper_sdk.MAPPER_REGISTRY
    release.set()
    first.join(10)
    reload.join(10)
    assert held, "the reload emptied the registry while a walk was in flight"


# ---------------------------------------------------------------------------
# The boot seat - 「not registered」 must not be this process saying 「I have not looked」
# ---------------------------------------------------------------------------

def test_a_name_is_not_unknown_just_because_nobody_walked_the_package_yet(monkeypatch):
    """🔴 MEASURED 2026-09-23: `load_chain_rules()` runs BEFORE `warmup_worker`, which is
    what calls `discover()`. So a declaration whose only mapper cell named one of the
    owner's functions was refused as unresolvable on the FIRST boot and accepted after a
    reload. Two answers to one question, and the quieter one is wrong.

    ⚠️ BRINGS ITS OWN MAPPER, like the rest of this file: the real package is the owner's
    and gitignored, so a test that leaned on a name from it would assert nothing here.
    """
    from chain import rule_run

    walked = []

    def _fake_discover(package="mappers"):
        walked.append(package)
        mapper_sdk.register("late_arriving_mapper", lambda df, db: df)
        return tuple(sorted(mapper_sdk.MAPPER_REGISTRY)), {}

    monkeypatch.setattr(mapper_sdk, "discover", _fake_discover)
    mapper_sdk.reset_registry()          # nobody has looked in this process

    assert "late_arriving_mapper" not in mapper_sdk.MAPPER_REGISTRY, (
        "canary: the name is registered before the ask, so finding it proves nothing")

    found = rule_run.runnable("late_arriving_mapper")

    assert callable(found), (
        "the seat answered 「nothing」 about a name the package does register")
    assert walked == ["mappers"], "it answered without ever looking"


def test_the_package_is_walked_once_not_once_per_unknown_name(monkeypatch):
    """A file full of refusals must not re-import the package per rule. The loader asks
    this seat once per rule, so a fill on every miss would walk `mappers` N times on a
    boot whose rules name mappers that genuinely do not exist."""
    from chain import rule_run

    walked = []

    def _fake_discover(package="mappers"):
        walked.append(package)
        return (), {}

    monkeypatch.setattr(mapper_sdk, "discover", _fake_discover)
    mapper_sdk.reset_registry()

    for name in ("no_such_a", "no_such_b", "no_such_c"):
        assert rule_run.runnable(name) is None

    assert walked == ["mappers"], (
        "three unknown names walked the package %d times" % len(walked))


def test_a_reload_that_empties_the_registry_can_still_answer_about_a_name(monkeypatch):
    """The same defect from the other side. `system_reload` drops `mappers.*` and clears
    the registry, and it re-runs `discover()` itself - but 2026-09-05 it did NOT, and the
    rule editor's grammar judge refused every one-cell mapper rule from the first reload
    onward. This is what holds if that call is ever lost again: emptying the registry also
    forgets that anyone looked, so the next ask refills instead of answering 「unknown」.
    """
    from chain import rule_run

    def _fake_discover(package="mappers"):
        mapper_sdk.register("mapper_after_the_reload", lambda df, db: df)
        return tuple(sorted(mapper_sdk.MAPPER_REGISTRY)), {}

    monkeypatch.setattr(mapper_sdk, "discover", _fake_discover)

    mapper_sdk.ensure_discovered()                    # boot looked once
    assert "mapper_after_the_reload" in mapper_sdk.MAPPER_REGISTRY, (
        "canary: the fill did nothing, so the reload below proves nothing")

    mapper_sdk.reset_registry()                       # the reload empties it
    assert "mapper_after_the_reload" not in mapper_sdk.MAPPER_REGISTRY

    assert callable(rule_run.runnable("mapper_after_the_reload")), (
        "after a reload the seat calls a registered name unknown")
