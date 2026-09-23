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

def test_the_reload_clears_the_registry_where_it_drops_the_modules():
    """⛔ SCORED ON THE SOURCE: running the real reload needs a database and a live app, and
    what matters here is that the two live in the SAME function -- a registry cleared
    somewhere else could drift away from the eviction it exists to follow."""
    import inspect

    from runtime import system_reload

    body = inspect.getsource(system_reload.reload_local_process_cache)
    assert "reset_registry()" in body
    head, _, tail = body.partition('startswith("mappers.")')
    assert tail, "the eviction this follows is gone"
    assert "reset_registry()" in tail, "the reset must come AFTER the eviction"


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
