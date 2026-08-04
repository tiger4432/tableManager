"""MAP SEAM — the SERVER half, scored against the shared contract vectors.

The file being scored is `contracts/map_seam/vectors.json`, and it is the same file
`contracts/map_seam/client_harness.mjs` reads. Nothing here hardcodes an expectation:
every assertion comes out of the contract, so deleting a case removes coverage LOUDLY
(`test_every_vector_group_is_consumed_or_declared`).

WHY IT LIVES UNDER contracts/ AND NOT server/tests/
    Three agents held this tree open while the round landed, and a seam contract is worth
    nothing if landing it costs someone else a round to a merge conflict. The module is
    self-bootstrapping (it puts `server/` on sys.path itself), so it runs standalone:

        conda run -n assy_manager python -m pytest contracts/map_seam/ -q -rs

HOW IT REACHES THE DEFAULT SUITE  [wired 2026-07-29]
    `server/tests/test_map_seam_contract.py` re-exports every test in this module, so

        conda run -n assy_manager python -m pytest server/tests/ -q -rs

    covers this contract. That shim exists instead of a `testpaths` entry for a concrete
    reason: pytest IGNORES testpaths whenever paths are given on the command line, and the
    documented command everywhere in this repo passes `server/tests/` explicitly. A testpaths
    change would have looked like wiring and changed nothing.

    Do not move the assertions into the shim. This file stays the one definition; the shim
    only makes it reachable.

WHY `-rs` IS PART OF THE COMMAND AND NOT AN OPTION  [2026-07-29]
    The Lead PM's rule is that a `pending` axis does not block the SUITE but does block ROUND
    COMPLETION. That rule only functions while pending is visible BY NAME AND NUMBER: without
    it there is no basis on which to judge a round finished, and the rule dies quietly at the
    exact moment it is supposed to bite.

    Bare `-q` prints only a count — "42 passed, 10 skipped" — which says something is unscored
    but not what, not whose, and not what it blocks. `-rs` prints the reason line for every
    skip, and `_server_symbol` builds those reasons to carry the symbol, the owner, and the
    invariants left unscored. The flag is the difference between a number and an inventory.

    ⚠️ It is still a FLAG, and a flag can be dropped. Anyone running bare `-q` gets the count
    and no attribution. The robust form would be `addopts = "-rs"` under
    `[tool.pytest.ini_options]` in pyproject.toml, which cannot be forgotten — that is a
    repo-wide change and therefore the Lead PM's call, recorded here rather than assumed.

WHAT IS SCORED, AND WHAT IS DECLARED
    7b  canonical_value / compose / decompose / canonical_map_key      — fully scored
        compose_divergence / decompose_lossy                          — scored AS DIVERGENCE
    7c  chips_bound                                                   — fully scored (pure)
        transfer_log_declaration                                      — fully scored (the named
                                                                        predicate landed 2026-07-29)
    M4  mask_baseline / valid_die_ref_parse / valid_die_basis         — fully scored
        valid_die_ref_home_divergence                                 — scored AS DIVERGENCE
    M4② valid_die_authoring / valid_die_chain                         — fully scored, BOTH
                                                                        sides (both halves
                                                                        landed 2026-07-29)
        valid_die_push_decision                                       — CLIENT-ONLY; no server
                                                                        counterpart exists to
                                                                        score it against

    ⚠️ THIS BLOCK IS PROSE AND PROSE GOES STALE. It said "server half `pending` on two
    symbols" for part of 2026-07-29 while the run was already 52 passed / 0 skipped — a
    header claiming a pending axis in a file whose whole argument is that pending must be
    visible by name AND NUMBER. That is the failure mode this file warns about, committed by
    this file. The RUN is the authority; when the two disagree, this text is what is wrong.
    `test_pending_symbols_are_owned_and_never_stale` polices the machine-readable half —
    nothing polices this paragraph except whoever reads it next.

    A group whose implementation is MISSING is never quietly green. Which noise it makes is
    the `symbol_status` table's call, and only ONE state is quiet — `pending`, meaning the
    vectors were written contract-first and there is nothing to score YET. That state is
    reported by name with an owner, is scored the moment the symbol appears, and turns into a
    hard STALE PENDING failure if the declaration is not promoted afterwards. Everything else
    is red: `required` means overdue, `live` means it was here and left.

    Nothing here is ever skipped for convenience and nothing is xfailed. A contract the code
    is SUPPOSED to meet and does not is a red contract, and a comfortable green is how the
    previous round's two HIGH defects reached review.

    The ONE exception is a NAMED KNOWN DEFECT (`known_defects` in vectors.json), and it is an
    exception in form only: a pin is scored strictly against the recorded wrong value, so it
    still fails against the contract today and goes red the day the defect is fixed. See the
    `_all_pins` tests at the foot of this file for the guards that keep it honest.
"""
import json
import pathlib
import sys

import pytest

_HERE = pathlib.Path(__file__).resolve().parent
_ROOT = _HERE.parents[1]
if str(_ROOT / "server") not in sys.path:
    sys.path.insert(0, str(_ROOT / "server"))

import map_meta_registrar          # noqa: E402
import map_overlay                 # noqa: E402
import transfer_plan               # noqa: E402
from database import crud          # noqa: E402
from utils.physical_wafer_engine import PhysicalWaferEngine   # noqa: E402


def _vectors():
    p = _HERE / "vectors.json"
    assert p.exists(), f"shared contract vectors are missing: {p}"
    return json.loads(p.read_text(encoding="utf-8"))


def _cases(group, key="name"):
    """Real cases — `$comment` entries filtered out."""
    return [c for c in _vectors()[group] if key in c]


def _case(group, name):
    return next(c for c in _cases(group) if c["name"] == name)


# Groups this file consumes / that have no server counterpart. A new group in the vector
# file fails the completeness test below: dropping the registration would let the contract
# silently stop covering an axis, which is the failure this whole file exists to prevent.
_SERVER_CONSUMED = {
    "canonical_value_cases", "canonical_value_server_only_cases",
    "compose_cases", "compose_divergence_cases",
    "decompose_cases", "decompose_lossy_cases", "canonical_map_key_cases",
    "chips_bound_cases", "transfer_log_declaration_cases",
    "mask_baseline_cases",
    "valid_die_ref_parse_cases", "valid_die_ref_home_divergence_cases",
    "valid_die_basis_cases", "valid_die_ref_canonical_cases",
    "valid_die_refused_render_divergence_cases",
    "valid_die_authoring_cases", "valid_die_chain_cases",
}
_CLIENT_ONLY = {
    # The Push boundary: `validDieRefForPush` decides whether a stored declaration is
    # rewritten at all, by comparing a DOM control against the stored value. The server has
    # no counterpart to a control reflecting a stored value, so there is nothing here to
    # score it against — NOT an exemption from the invariant. The server's half of the same
    # invariant is `valid_die_authoring_cases`, which both sides run.
    "valid_die_push_decision_cases",
    # Rendering has no server counterpart — the server serves numbers and flags, never text.
    "remaining_display_cases",
    # Strictness of the `transfer_untracked` FLAG is a client-side read. The server writes
    # the flag; scoring the writer against its own literal would assert nothing.
    "untracked_flag_cases",
}


def test_every_vector_group_is_consumed_or_declared():
    present = {k for k in _vectors() if k.endswith("_cases")}
    assert present == (_SERVER_CONSUMED | _CLIENT_ONLY), (
        "vector group composition changed. Add a server test and register the group in "
        "_SERVER_CONSUMED, or register it in _CLIENT_ONLY WITH A REASON if the server has "
        f"no counterpart.\n  unregistered: {sorted(present - _SERVER_CONSUMED - _CLIENT_ONLY)}"
        f"\n  registered but gone: {sorted((_SERVER_CONSUMED | _CLIENT_ONLY) - present)}")


def test_every_declared_server_symbol_exists_or_is_declared_pending():
    """A `live` symbol that vanished was RENAMED, and the contract must say so loudly.

    Without this, a rename turns every group that used the symbol into an import error or,
    worse, a silently narrowed run.
    """
    import importlib
    missing = []
    for role, m in _vectors()["server_symbols"].items():
        if role == "$comment":
            continue
        mod = importlib.import_module(m["module"])
        if getattr(mod, m["fn"], None) is None and m["status"] == "live":
            missing.append(f"{m['module']}.{m['fn']} (role {role})")
    assert not missing, (
        "contract symbols declared `live` are gone — renamed or removed:\n  "
        + "\n  ".join(missing)
        + "\nUpdate vectors.json server_symbols deliberately; do not delete the check.")


_VALID_STATUSES = {"live", "pending", "required"}


def test_symbol_statuses_are_from_the_shared_vocabulary():
    """Both scorers branch on this string. A typo would fall through to whichever arm the
    implementation happens to end on, and the two scorers might not choose the same one."""
    assert "symbol_status" in _vectors(), (
        "the shared status vocabulary block is gone from vectors.json. Both scorers implement "
        "it; deleting the documentation is how the two implementations drift apart.")
    bad = []
    for kind in ("server_symbols", "client_symbols"):
        for role, m in _vectors()[kind].items():
            if role == "$comment":
                continue
            if m.get("status") not in _VALID_STATUSES:
                bad.append(f"{kind}.{role}: {m.get('status')!r}")
    assert not bad, (
        f"symbol statuses outside the shared vocabulary {sorted(_VALID_STATUSES)}:\n  "
        + "\n  ".join(bad))


def test_pending_symbols_are_owned_and_never_stale():
    """PENDING expires by itself — properties 2 and 3 of `symbol_status`.

    A `pending` axis is deliberately quiet, and that concession is only safe while two things
    hold. First it must be OWNED: an anonymous pending axis is a hole with better manners, and
    `$blocks` is what makes the cost of the wait legible instead of a shrug. Second, and this
    is the load-bearing half, it must be promoted once the symbol lands.

    Why promotion is not cosmetic: an ABSENT `pending` symbol is forgiven by design. So a
    symbol left at `pending` after landing could later be renamed or deleted and the contract
    would forgive THAT too — silently sliding back to 'quiet' with the axis unscored, which is
    exactly the failure `live` status exists to catch. `pending` is a promise to promote, and
    this test is what collects on it.
    """
    import importlib
    unowned, stale = [], []
    groups = {k for k in _vectors() if k.endswith("_cases")}
    for role, m in _vectors()["server_symbols"].items():
        if role == "$comment" or m.get("status") != "pending":
            continue
        if not m.get("$owner") or not m.get("$blocks"):
            unowned.append(f"{role} (owner={m.get('$owner')!r} blocks={m.get('$blocks')!r})")
        elif not any(g in m["$blocks"] for g in groups):
            unowned.append(
                f"{role}: $blocks names no vector group in this file — the blast radius of "
                f"the wait is not checkable, so nobody can see what the pending axis costs")
        if getattr(importlib.import_module(m["module"]), m["fn"], None) is not None:
            stale.append(f"{m['module']}.{m['fn']} (role {role})")
    assert not unowned, (
        "pending symbols must carry `$owner` AND a `$blocks` that names a real vector "
        "group:\n  " + "\n  ".join(unowned))
    assert not stale, (
        "STALE PENDING — these symbols HAVE LANDED but vectors.json still calls them "
        "`pending`:\n  " + "\n  ".join(stale)
        + "\n\nTheir vectors are already being scored (the scorers look the symbol up rather "
          "than trusting the field), so this is a one-word edit: set `\"status\": \"live\"`.\n"
          "It is not bookkeeping. While the entry reads `pending`, an ABSENT symbol is "
          "forgiven — so a later rename of this now-landed function would be silently "
          "forgiven too and the axis would go unscored with a green suite.")


# ---------------------------------------------------------------------------
# Declared-type plumbing. `declared_column_type` reads crud.TABLE_CONFIG through the module
# attribute at call time (hot reload mutates it in place), so a test declares its types by
# writing into that dict. Names are `seam_*`-prefixed: they cannot collide with a real user
# config, and the fixture removes them again.
# ---------------------------------------------------------------------------

@pytest.fixture
def declare():
    added = []

    def _declare(table, column_types):
        if column_types is None:          # deliberately undeclared — register nothing
            return
        assert table.startswith("seam_"), f"contract fixtures must be seam_*-prefixed: {table}"
        crud.TABLE_CONFIG[table] = {"column_types": dict(column_types)}
        added.append(table)
    yield _declare
    for t in added:
        crud.TABLE_CONFIG.pop(t, None)


class _FakeCol:
    """A column whose `==` records the bind instead of building SQL, so `build_key_filters`
    can be scored without a database or a mapped model."""

    def __init__(self, name):
        self.name = name

    def __eq__(self, other):
        return (self.name, other)


class _FakeModel:
    def __init__(self, table, columns):
        self.__tablename__ = table
        for c in columns:
            setattr(self, c, _FakeCol(c))


def _binding(c):
    return {"key_columns": list(c["key_columns"])}


# ---------------------------------------------------------------------------
# 7b — canonical key values
# ---------------------------------------------------------------------------

def test_canonical_value_matches_the_contract():
    seen = 0
    for c in _cases("canonical_value_cases") + _cases("canonical_value_server_only_cases"):
        seen += 1
        got = map_overlay.canonical_key_value(c["value"], c["declared_type"])
        assert got == c["expect"], (
            f"{c['name']}: canonical_key_value({c['value']!r}, {c['declared_type']!r}) "
            f"= {got!r}, contract says {c['expect']!r}")
    assert seen >= 16, "canonical value vectors disappeared"


def test_declared_types_actually_differ():
    """Structural guard, DERIVED from the vectors rather than restated.

    INV-7b-2 only means something if some input lands on different keys under `number` and
    `string`. An implementation that ignored the declaration entirely would pass every case
    above whose two halves happen to agree; this fails it.
    """
    by_value = {}
    for c in _cases("canonical_value_cases"):
        by_value.setdefault(c["value"], {})[c["declared_type"]] = c["expect"]
    differing = [v for v, m in by_value.items()
                 if "number" in m and "string" in m and m["number"] != m["string"]]
    assert differing, (
        "no vector distinguishes `number` from `string`. Without one, an implementation "
        "that never reads the declaration passes this contract — add a case (e.g. '01').")
    for v in differing:
        assert (map_overlay.canonical_key_value(v, "number")
                != map_overlay.canonical_key_value(v, "string")), (
            f"{v!r} canonicalizes identically under number and string — the declared type "
            f"is not being read")


# ---------------------------------------------------------------------------
# 7b — composition (INV-7b-1 / 7b-2 / 7b-3)
# ---------------------------------------------------------------------------

def test_compose_map_id_matches_the_contract(declare):
    for c in _cases("compose_cases"):
        declare(c["table"], c["column_types"])
        got = map_overlay.compose_map_id(
            c["key_columns"], c["values"], {"table": c["table"], "columns": {}})
        assert got == c["expect_map_id"], (
            f"{c['name']}: map_overlay composed {got!r}, contract says {c['expect_map_id']!r}")


def test_registrar_composes_the_same_identity(declare):
    """The REGISTRATION side must compose what the lookup side composes.

    This is the seam inside the server. `ab6ac02`'s own report records the registration path
    writing 'LOT_01' while every reader looked up 'LOT_1'; both were self-consistent.
    """
    for c in _cases("compose_cases"):
        declare(c["table"], c["column_types"])
        got = map_meta_registrar.compose_map_id(c["key_columns"], c["values"], c["table"])
        assert got == c["expect_map_id"], (
            f"{c['name']}: registrar composed {got!r}, contract says {c['expect_map_id']!r}")


def test_all_number_spellings_collapse_to_one_key(declare):
    """INV-7b-1 stated as a SET, not as a count.

    Four cases asserted individually would still pass if a fifth spelling were added and
    landed somewhere else. A set cannot.
    """
    block = [c for c in _cases("compose_cases") if c["name"].startswith("slot_number_")]
    assert len(block) >= 4, "INV-7b-1 needs at least the four declared spellings"
    keys = set()
    for c in block:
        declare(c["table"], c["column_types"])
        keys.add(map_overlay.compose_map_id(
            c["key_columns"], c["values"], {"table": c["table"], "columns": {}}))
    assert len(keys) == 1, f"number-declared spellings composed {sorted(keys)} — INV-7b-1 broken"


def test_string_declaration_keeps_padding(declare):
    """INV-7b-2 — and that it differs from INV-7b-1's answer for the same input."""
    pad_num = _case("compose_cases", "slot_number_padded")
    pad_str = _case("compose_cases", "slot_string_padded")
    assert pad_num["values"] == pad_str["values"], (
        "the two padding vectors must share an input, or they prove nothing about the type")
    assert pad_num["expect_map_id"] != pad_str["expect_map_id"], (
        "the contract itself stopped distinguishing the declared types")
    for c in (pad_num, pad_str):
        declare(c["table"], c["column_types"])
        got = map_overlay.compose_map_id(
            c["key_columns"], c["values"], {"table": c["table"], "columns": {}})
        assert got == c["expect_map_id"], f"{c['name']}: {got!r} != {c['expect_map_id']!r}"


def test_compose_divergences_are_exactly_as_declared(declare):
    """DECLARED DIVERGENCE, pinned per implementation.

    Three composers disagree on a missing key component on purpose. Pinning each to its own
    documented answer keeps the disagreement from drifting into a fourth shape unnoticed —
    which is different from, and weaker than, agreement.
    """
    for c in _cases("compose_divergence_cases"):
        declare(c["table"], c["column_types"])
        overlay = map_overlay.compose_map_id(
            c["key_columns"], c["values"], {"table": c["table"], "columns": {}})
        registrar = map_meta_registrar.compose_map_id(
            c["key_columns"], c["values"], c["table"])
        assert overlay == c["expect_overlay"], f"{c['name']} overlay: {overlay!r}"
        assert registrar == c["expect_registrar"], f"{c['name']} registrar: {registrar!r}"
        assert c["expect_client"] not in (overlay, registrar), (
            f"{c['name']}: a divergence case whose client answer now matches a server "
            f"answer is no longer a divergence — move it into compose_cases")


# ---------------------------------------------------------------------------
# 7b — decomposition (INV-7b-4)
# ---------------------------------------------------------------------------

def _decompose(table, key_columns, map_id):
    """Through `build_key_filters` — the CELL-filter path, not just the split primitive.

    A map key that finds the cells but not the meta is the 7b defect's exact shape, so the
    consumer is what gets scored.
    """
    model = _FakeModel(table, key_columns)
    filters = map_overlay.build_key_filters(model, {"key_columns": list(key_columns)}, map_id)
    assert filters is not None, f"build_key_filters refused {map_id!r}"
    return dict(filters)


def test_decompose_matches_the_contract(declare):
    for c in _cases("decompose_cases"):
        declare(c["table"], c["column_types"])
        got = _decompose(c["table"], c["key_columns"], c["map_id"])
        assert got == c["expect"], f"{c['name']}: {got!r} != {c['expect']!r}"


def test_split_primitive_and_filter_path_agree(declare):
    """`map_key_parts` is documented as the single split point shared by the cell-filter path
    and the identity path. DERIVED check that the sharing is real: if `build_key_filters`
    ever grew its own split, the same declaration would find the cells and miss the meta.
    """
    for c in _cases("decompose_cases"):
        declare(c["table"], c["column_types"])
        parts = map_overlay.map_key_parts({"key_columns": c["key_columns"]}, c["map_id"])
        via_filters = _decompose(c["table"], c["key_columns"], c["map_id"])
        via_parts = {name: map_overlay.canonical_bind_value(c["table"], name, val)
                     for name, val in parts}
        assert via_parts == via_filters, (
            f"{c['name']}: map_key_parts gives {via_parts!r} but build_key_filters gives "
            f"{via_filters!r} — the split forked")


def test_decompose_inverts_compose(declare):
    """INV-7b-4, DERIVED from compose_cases so it cannot drift from what it inverts.

    A hand-written round-trip table is how an inverse quietly stops being one: someone edits
    composition, edits the table to match, and the property is gone while the tests stay
    green.
    """
    for c in _cases("compose_cases"):
        declare(c["table"], c["column_types"])
        composed = map_overlay.compose_map_id(
            c["key_columns"], c["values"], {"table": c["table"], "columns": {}})
        back = _decompose(c["table"], c["key_columns"], composed)
        expected = {k: map_overlay.canonical_bind_value(c["table"], k, c["values"].get(k))
                    for k in c["key_columns"]}
        assert back == expected, (
            f"{c['name']}: compose->decompose gave {back!r}, canonical components are "
            f"{expected!r} (map_id was {composed!r})")


def test_lossy_roundtrip_is_exactly_as_recorded(declare):
    """The boundary of INV-7b-4, pinned rather than papered over.

    A component that is not last and contains the separator does not survive the round trip.
    Both sides lose it the SAME way, which is the only property a harness can defend; whether
    the absorb-last rule should change is a contract decision for the Lead PM.
    """
    for c in _cases("decompose_lossy_cases"):
        declare(c["table"], c["column_types"])
        composed = map_overlay.compose_map_id(
            c["key_columns"], c["compose_values"], {"table": c["table"], "columns": {}})
        assert composed == c["composed"], f"{c['name']}: composed {composed!r}"
        back = _decompose(c["table"], c["key_columns"], composed)
        assert back == c["expect_decomposed"], f"{c['name']}: decomposed {back!r}"
        canonical = {k: map_overlay.canonical_bind_value(c["table"], k, c["compose_values"].get(k))
                     for k in c["key_columns"]}
        assert (back == canonical) is c["roundtrip_holds"], (
            f"{c['name']}: roundtrip_holds is recorded as {c['roundtrip_holds']} but the code "
            f"now says {back == canonical} — the recorded boundary moved")


def test_canonical_map_key_matches_the_contract(declare):
    for c in _cases("canonical_map_key_cases"):
        declare(c["table"], c["column_types"])
        got = map_overlay.canonical_map_key(c["table"], _binding(c), c["map_key"])
        assert got == c["expect"], f"{c['name']}: {got!r} != {c['expect']!r}"


def test_canonical_map_key_is_idempotent(declare):
    """DERIVED. The output IS the lookup key, so a second application must not move it —
    otherwise 'canonical' depends on how many times the value crossed a boundary."""
    for c in _cases("canonical_map_key_cases"):
        declare(c["table"], c["column_types"])
        once = map_overlay.canonical_map_key(c["table"], _binding(c), c["map_key"])
        twice = map_overlay.canonical_map_key(c["table"], _binding(c), once)
        assert once == twice, f"{c['name']}: {c['map_key']!r} -> {once!r} -> {twice!r}"


# ---------------------------------------------------------------------------
# 7c — the upper bound (INV-7c-3)
# ---------------------------------------------------------------------------

def test_chips_bound_matches_the_contract():
    for c in _cases("chips_bound_cases"):
        chips, extra = transfer_plan.build_chips_block(
            total=c["total"], fail_breakdown=c["fail_breakdown"],
            transferred=c["transferred"], remaining=c["remaining"],
            remaining_reliable=c["remaining_reliable"], total_reliable=c["total_reliable"])
        exp = c["expect"]
        assert chips["remaining"] == exp["remaining"], f"{c['name']} remaining"
        assert chips["remaining_reliable"] == exp["remaining_reliable"], \
            f"{c['name']} remaining_reliable"
        has = "remaining_upper_bound" in chips
        assert has == exp["has_upper_bound"], (
            f"{c['name']}: upper bound {'served' if has else 'withheld'}, contract says "
            f"{'served' if exp['has_upper_bound'] else 'withheld'}")
        if exp["has_upper_bound"]:
            assert chips["remaining_upper_bound"] == exp["upper_bound"], f"{c['name']} bound"
        assert [w["type"] for w in extra] == c["expect_warning_types"], \
            f"{c['name']} warnings: {[w['type'] for w in extra]}"


def test_upper_bound_is_never_served_alongside_an_exact_remaining():
    """DERIVED — two numbers for one quantity is how a reader picks the wrong one. Not
    restated per case: it must hold for every vector, including ones added later."""
    for c in _cases("chips_bound_cases"):
        chips, _ = transfer_plan.build_chips_block(
            total=c["total"], fail_breakdown=c["fail_breakdown"],
            transferred=c["transferred"], remaining=c["remaining"],
            remaining_reliable=c["remaining_reliable"], total_reliable=c["total_reliable"])
        if chips.get("remaining") is not None:
            assert "remaining_upper_bound" not in chips, (
                f"{c['name']}: served an exact remaining AND a bound")


def test_upper_bound_equals_total_minus_fail_when_untracked_is_the_only_cause():
    """INV-7c-3's arithmetic, against the vector's own inputs. The bound is the SAME
    computation with the consumption term dropped, and dropping a subtraction term can only
    raise the result — that is what makes it a bound rather than a guess."""
    c = _case("chips_bound_cases", "untracked_only")
    fail = sum(c["fail_breakdown"].values())
    chips, _ = transfer_plan.build_chips_block(
        total=c["total"], fail_breakdown=c["fail_breakdown"], transferred=None,
        remaining=c["remaining"], remaining_reliable=False, total_reliable=True)
    assert chips["remaining_upper_bound"] == c["total"] - fail, (
        f"bound {chips['remaining_upper_bound']} != total - fail ({c['total']} - {fail})")


# ---------------------------------------------------------------------------
# 7c — the declaration itself (INV-7c-2). PENDING.
# ---------------------------------------------------------------------------

def test_transfer_log_declaration_is_exact_string_only():
    fn = getattr(transfer_plan, "transfer_log_is_declared_none", None)
    if fn is None:
        pytest.fail(
            "NOT LANDED: transfer_plan.transfer_log_is_declared_none.\n"
            "INV-7c-2 ('exact string only') at the CONFIG boundary currently lives as an "
            "inline comparison inside a DB-bound function (transfer_plan.py:1256), so no "
            "scorer can reach it. Re-typing `src == TRANSFER_LOG_NONE` here would score "
            "nothing: it passes against `str(src).lower() == 'none'`, which is the very "
            "defect the invariant forbids. Extract the predicate and call it at 1256.")
    for c in _cases("transfer_log_declaration_cases"):
        got = bool(fn(c["value"]))
        assert got is c["expect_declared"], (
            f"{c['name']}: {c['value']!r} declared={got}, contract says {c['expect_declared']}")


def test_the_declaration_constants_are_exact():
    """Weaker than the test above, and worth having while it is pending: it cannot see the
    branch, but it does catch the constants themselves being loosened."""
    assert transfer_plan.TRANSFER_LOG_NONE == "none"
    assert transfer_plan.STATUS_TRANSFER_UNTRACKED == "connected(untracked)"


# ---------------------------------------------------------------------------
# M4 — circle-mask baseline (INV-M4-1)
# ---------------------------------------------------------------------------

def _meta_of(case):
    d = case["declared"]
    return {
        "rotation": case["rotation"], "side": case["side"],
        "grid_cols": case["cols"], "grid_rows": case["rows"],
        "phys_wafer_dia": d["wafer_dia"], "phys_chip_x": d["chip_x"],
        "phys_chip_y": d["chip_y"], "phys_offset_x": d["offset_x"],
        "phys_offset_y": d["offset_y"], "phys_edge_margin": d["edge_margin"],
    }


def _frame_dims(case):
    return ((case["rows"], case["cols"]) if case["rotation"] in (90, 270)
            else (case["cols"], case["rows"]))


def test_mask_baseline_matches_the_recorded_2a9f6c4_measurement():
    for c in _cases("mask_baseline_cases"):
        dia, cx, cy, ox, oy, margin = map_overlay._frame_phys_params(_meta_of(c))
        eng = PhysicalWaferEngine(wafer_diameter_mm=dia, chip_size_x_mm=cx, chip_size_y_mm=cy,
                                  edge_exclusion_mm=margin, offset_x_mm=ox, offset_y_mm=oy)
        assert eng.effective_radius_mm == pytest.approx(c["effective_radius_mm"]), (
            f"{c['name']}: effective radius {eng.effective_radius_mm} != "
            f"{c['effective_radius_mm']} — the declared edge margin is not being read")
        C, R = _frame_dims(c)
        mask = ["".join("#" if eng.is_cell_inside_wafer(col, row, C, R) else "."
                        for col in range(C)) for row in range(R)]
        assert mask == c["mask"], (
            f"{c['name']}: mask drifted from the 2a9f6c4 measurement\n"
            f"  recorded: {c['mask']}\n  now     : {mask}")


def test_circle_die_mask_agrees_with_the_engine_baseline():
    """M4 introduced `circle_die_mask` as the enumerated form of the same judgement. Two
    enumerations of one geometry is exactly the shape that drifts, so they are pinned to each
    other — and both to the recorded 2a9f6c4 measurement."""
    fn = getattr(map_overlay, "circle_die_mask", None)
    if fn is None:
        pytest.fail("NOT LANDED: map_overlay.circle_die_mask (declared by the M4 branch)")
    for c in _cases("mask_baseline_cases"):
        got = fn(_meta_of(c))
        if got is None:
            pytest.fail(f"{c['name']}: circle_die_mask returned None for a fully declared "
                        f"spec — the baseline branch cannot enumerate its own answer")
        C, R = _frame_dims(c)
        from_mask = ["".join("#" if (col, row) in got else "." for col in range(C))
                     for row in range(R)]
        assert from_mask == c["mask"], (
            f"{c['name']}: circle_die_mask disagrees with the recorded baseline\n"
            f"  recorded: {c['mask']}\n  mask fn : {from_mask}")


def test_mask_baseline_covers_every_rotation_and_both_sides():
    """Fixture-inactivity guard.

    The rotation/side tables are two independent 4-row tables, one per side of the seam. A
    baseline containing only rot-0 front would pass against an implementation that ignores
    rotation entirely, and the group would still look like coverage.
    """
    cases = _cases("mask_baseline_cases")
    assert {c["rotation"] for c in cases} == {0, 90, 180, 270}, "rotation coverage lost"
    assert {c["side"] for c in cases} == {"front", "back"}, "side coverage lost"
    assert [c for c in cases if c["declared"]["offset_x"] or c["declared"]["offset_y"]], (
        "every baseline case has zero offsets — the offset permutation table is then "
        "unobservable and any of its 8 entries could be wrong")
    assert any(c["declared"]["edge_margin"] == 0 for c in cases), (
        "no case declares a ZERO edge margin — that is the axis on which the two sides were "
        "measured to disagree, and it must not be dropped from the baseline")
    live_aniso = [c for c in cases
                  if c["rotation"] in (90, 270)
                  and c["declared"]["chip_x"] != c["declared"]["chip_y"]
                  and _PIN_KEY not in c]
    assert live_aniso, (
        "no LIVE (unpinned) quarter-turn case declares unequal chip pitches. Rotation permutes "
        "chip_x/chip_y into the frame axes, so with only square chips a pitch-blind "
        "implementation moves zero cells and the whole rotation axis is nominal coverage. A "
        "PINNED case cannot carry this: its mask is empty on both sides of the swap.")


def test_quarter_turn_pitch_swap_is_observable():
    """The anisotropy axis, asserted by RUNNING the swap rather than by trusting two literals.

    Measured 2026-07-29: swapping the declared pitches in every mask vector that existed
    before that date moved ZERO cells — nine declare a square chip, and the one anisotropic
    case is pinned to an empty mask by D1. Four cases carried rotation 90/270 and all four
    were nominal. This test is what stops that from being true again quietly: if a future
    vector set loses its anisotropy, the guard above fails, and if the rotation table stops
    permuting the pitches, this one does.
    """
    for c in _cases("mask_baseline_cases"):
        if c["rotation"] not in (90, 270):
            continue
        if c["declared"]["chip_x"] == c["declared"]["chip_y"] or _PIN_KEY in c:
            continue
        swapped = dict(c, declared=dict(c["declared"],
                                        chip_x=c["declared"]["chip_y"],
                                        chip_y=c["declared"]["chip_x"]))
        C, R = _frame_dims(c)
        masks = []
        for case in (c, swapped):
            dia, cx, cy, ox, oy, margin = map_overlay._frame_phys_params(_meta_of(case))
            eng = PhysicalWaferEngine(wafer_diameter_mm=dia, chip_size_x_mm=cx,
                                      chip_size_y_mm=cy, edge_exclusion_mm=margin,
                                      offset_x_mm=ox, offset_y_mm=oy)
            masks.append(["".join("#" if eng.is_cell_inside_wafer(col, row, C, R) else "."
                                  for col in range(C)) for row in range(R)])
        assert masks[0] != masks[1], (
            f"{c['name']}: swapping the declared chip pitches moves NO cells, so this vector "
            f"cannot tell a rotation-aware implementation from a pitch-blind one. The case is "
            f"not carrying the anisotropy axis it was added for.")


# ---------------------------------------------------------------------------
# M4 — the declaration reader (INV-M4-3)
# ---------------------------------------------------------------------------

def _parse_outcome(meta, home):
    ref, err = map_overlay.parse_valid_die_ref(meta, default_table=home)
    if err is not None:
        return "error", None
    if ref is None:
        return "none", None
    return "ref", ref


def test_valid_die_ref_parse_matches_the_contract():
    for c in _cases("valid_die_ref_parse_cases"):
        kind, ref = _parse_outcome(c["meta"], c["home_table"])
        assert kind == c["expect"], (
            f"{c['name']}: parse gave {kind!r}, contract says {c['expect']!r}")
        if kind == "ref":
            assert ref.get("table") == c["expect_table"], f"{c['name']} table: {ref!r}"
            assert ref.get("map_id") == c["expect_key"], f"{c['name']} map_id: {ref!r}"


def test_every_resolved_ref_reads_the_FIXED_table():
    """[1-a] THE PIN, DERIVED and scored against the CONSTANT rather than the literals.

    Mirror of the client harness's `QA_NO_GO_pin` block. Reading each vector's
    `expect_table` one at a time is not enough: every literal in the group could be edited
    to `seam_map` and the group would stay green against an unpinned implementation. So the
    resolved table is compared to `map_overlay.VALID_DIE_TABLE` — the same constant the read
    path itself uses — which no edit to this file can satisfy.
    """
    fixed = getattr(map_overlay, "VALID_DIE_TABLE", None)
    assert isinstance(fixed, str) and fixed, (
        "map_overlay.VALID_DIE_TABLE is missing — the server read path is not pinned, so "
        "a legacy declaration resolves against a table the client never looks in")
    refs = [c for c in _cases("valid_die_ref_parse_cases") if c["expect"] == "ref"]
    assert refs, "the parse group lost every resolved vector"
    for c in refs:
        _kind, ref = _parse_outcome(c["meta"], c["home_table"])
        assert ref["table"] == fixed, (
            f"{c['name']}: resolved to {ref['table']!r}, the pin is {fixed!r}")

    # Fixture-inactivity guard, same wording as the client's. If every vector's declaration
    # already named the fixed table, an UNPINNED reader would pass by inheritance.
    def _declared(c):
        raw = c["meta"]["valid_die_ref"]
        if isinstance(raw, str):
            return c["home_table"]
        t = raw.get("table", raw.get("target_table"))
        return t if (t is not None and str(t).strip()) else c["home_table"]

    assert [c for c in refs if _declared(c) and _declared(c) != fixed], (
        "no ref vector's declaration names a table OTHER than the pinned one — an unpinned "
        "reader passes this group unchanged")


def test_the_two_sides_now_name_the_SAME_table():
    """🟢 THE CLOSED DIVERGENCE, asserted rather than narrated.

    `expect_table` (server) and `expect_client_table` (client) held different values on every
    `ref` vector between `c97b319` and the server pin: the client refused a legacy declaration
    while the server resolved it against `bonding_map`/`dt_map`, so one row named two maps.
    The two fields are deliberately NOT merged — a single field would be satisfied by any two
    implementations that both read it — so this is what says they agree, and it is what goes
    red if either side unpins.
    """
    disagree = [(c["name"], c["expect_table"], c["expect_client_table"])
                for c in _cases("valid_die_ref_parse_cases") if c["expect"] == "ref"
                and c["expect_table"] != c.get("expect_client_table")]
    assert not disagree, (
        "the map seam names two different tables for one declaration again:\n  "
        + "\n  ".join(f"{n}: server={s!r} client={cl!r}" for n, s, cl in disagree))


def test_the_declared_table_survives_the_pin():
    """The pin IGNORES the declared table on read; it must not DESTROY it.

    A refusal has to tell 'the key is wrong' from 'the key is right and that map lives
    somewhere else', and those are different repairs. Once the parse has dropped the declared
    table the information is nowhere else on this path — the raw bytes are behind the caller.
    """
    for c in _cases("valid_die_ref_parse_cases"):
        if c["expect"] != "ref":
            continue
        _kind, ref = _parse_outcome(c["meta"], c["home_table"])
        assert "declared_table" in ref, (
            f"{c['name']}: the parse dropped what the declaration pointed at ({ref!r}); "
            f"every refusal downstream is then generic")
        raw = c["meta"]["valid_die_ref"]
        declared = (c["home_table"] if isinstance(raw, str)
                    else (raw.get("table", raw.get("target_table")) or c["home_table"]))
        assert ref["declared_table"] == declared, (
            f"{c['name']}: declared_table is {ref['declared_table']!r}, the declaration said "
            f"{declared!r}")


def test_only_null_means_no_declaration():
    """INV-M4-3's structural core, DERIVED from the group rather than restated.

    Every vector whose declaration is present but unreadable must land on `error`. If any of
    them collapsed into `none`, one typo would silently restore circle geometry — a wrong
    answer indistinguishable from a right one.
    """
    for c in _cases("valid_die_ref_parse_cases"):
        kind, _ = _parse_outcome(c["meta"], c["home_table"])
        declared = "valid_die_ref" in c["meta"] and c["meta"]["valid_die_ref"] is not None
        assert (kind == "none") is (not declared), (
            f"{c['name']}: declaration present={declared} but parse said {kind!r} — only "
            f"null/absent may mean 'no declaration'")


def test_valid_die_ref_home_divergence_is_exactly_as_recorded():
    """DECLARED DIVERGENCE found on the round trip and reported to the Lead PM rather than
    decided here. Pinned so it cannot drift into a third shape while nobody is looking."""
    for c in _cases("valid_die_ref_home_divergence_cases"):
        kind, _ = _parse_outcome(c["meta"], c["home_table"])
        assert kind == c["expect_server"], (
            f"{c['name']}: server parse gave {kind!r}, recorded {c['expect_server']!r}")


def test_refused_render_divergence_is_exactly_as_recorded():
    """DECLARED DIVERGENCE — the server half of 'what happens on `refused`'.

    The asymmetry is structural, not a disagreement: the server CAN answer 'no mask' because
    it is drawing nothing, and a canvas cannot, so the client renders the pre-M4 circle and
    surfaces the refusal instead. What this side owns is the half that makes the divergence
    safe — that the server refuses with NO basis at all. If it ever started serving a
    fallback basis alongside `refused`, the client would have a mask to draw and the refusal
    would stop being visible anywhere.

    The client half (verdict passthrough + the two surfacing properties) is scored by
    contracts/map_seam/client_harness.mjs against these same vectors.
    """
    for c in _cases("valid_die_refused_render_divergence_cases"):
        out = map_overlay.resolve_valid_die_basis(
            c["meta"], _resolver_for(c), table="seam_map")
        assert out["source"] == c["expect_server_source"], (
            f"{c['name']}: server source {out['source']!r}, recorded "
            f"{c['expect_server_source']!r}")
        assert out.get("basis") == c["expect_server_basis"], (
            f"{c['name']}: the server served basis {out.get('basis')!r} alongside a refusal. "
            f"A refusal that carries a fallback basis gives the client something to draw, and "
            f"the refusal stops being visible to the operator — the exact silent fallback "
            f"INV-M4-3 forbids.")


def test_refused_divergence_covers_every_route_to_refusal():
    """Fixture-inactivity guard. `refused` is reached three different ways and they run
    through different code — an unreadable declaration never touches the resolver, and a
    zero-cell result never touches the parser. Covering one route and calling the axis pinned
    is how the other two drift."""
    routes = {c["resolver"] for c in _cases("valid_die_refused_render_divergence_cases")}
    metas = [c["meta"].get("valid_die_ref") for c
             in _cases("valid_die_refused_render_divergence_cases")]
    assert "null" in routes or "raise" in routes, "no UNRESOLVABLE-reference route"
    assert any(not isinstance(m, (str, dict)) for m in metas), (
        "no UNREADABLE-declaration route — that one reaches `refused` through the parser, "
        "not the resolver")
    assert any(c["resolver"] == "cells" and not c["resolver_cells"]
               for c in _cases("valid_die_refused_render_divergence_cases")), (
        "no ZERO-CELL route — that one is DERIVED from state on the client rather than "
        "declared, and it is the route where the surfacing is thinnest")


# ---------------------------------------------------------------------------
# M4 — the branch point (INV-M4-1 / M4-2 / M4-3)
# ---------------------------------------------------------------------------

def _resolver_for(case):
    kind = case["resolver"]
    if kind == "none":
        return None
    if kind == "unused":
        def _never(_ref):
            raise AssertionError("resolver was called for a case that must not resolve")
        return _never
    if kind == "null":
        return lambda _ref: None
    if kind == "raise":
        def _boom(_ref):
            raise RuntimeError("reference lookup exploded")
        return _boom
    cells = [tuple(p) for p in case["resolver_cells"]]
    return lambda _ref: cells


def test_valid_die_basis_matches_the_contract():
    for c in _cases("valid_die_basis_cases"):
        out = map_overlay.resolve_valid_die_basis(
            c["meta"], _resolver_for(c), table="seam_map")
        assert out["source"] == c["expect_source"], (
            f"{c['name']}: source {out['source']!r}, contract says {c['expect_source']!r} "
            f"(reason: {out.get('reason')!r})")
        if c.get("expect_reason_nonempty"):
            assert (out.get("reason") or "").strip(), (
                f"{c['name']}: refused with NO reason — INV-M4-3 requires a stated reason, "
                f"because a refusal nobody can read is a silent failure with extra steps")
        if c.get("expect_reason_empty"):
            assert not (out.get("reason") or "").strip(), f"{c['name']}: unexpected reason"
        if "expect_basis" in c:
            exp = c["expect_basis"]
            got = out.get("basis")
            if exp is None:
                assert got is None, f"{c['name']}: refused but shipped a basis {got!r}"
            else:
                assert got is not None and sorted(map(list, got)) == sorted(exp), (
                    f"{c['name']}: basis {got!r} != {exp!r}")


def test_a_refusal_never_carries_a_fallback_basis():
    """INV-M4-3 structurally, DERIVED over the whole group. A consumer that reads `basis`
    without checking `source` must find nothing to read — that is what makes 'never a silent
    fallback' a property of the data rather than of the caller's discipline."""
    for c in _cases("valid_die_basis_cases"):
        out = map_overlay.resolve_valid_die_basis(
            c["meta"], _resolver_for(c), table="seam_map")
        if out["source"] == "refused":
            assert out.get("basis") is None, (
                f"{c['name']}: source=refused but basis={out.get('basis')!r} — a consumer "
                f"reading basis alone would silently use circle geometry")


def test_ref_basis_is_not_intersected_with_circle_geometry():
    """INV-M4-2 with teeth, DERIVED from the vector's own cells.

    The `ref_is_the_sole_basis` case deliberately includes a coordinate no circle described by
    this metadata could admit. Intersecting looks conservative and silently drops dies the
    template declares valid — the defect class M4 exists to remove.
    """
    c = _case("valid_die_basis_cases", "ref_is_the_sole_basis")
    out = map_overlay.resolve_valid_die_basis(c["meta"], _resolver_for(c), table="seam_map")
    assert out["source"] == "ref"
    got = sorted(map(list, out["basis"]))
    assert got == sorted(c["resolver_cells"]), (
        f"basis {got!r} != the resolver's cells {c['resolver_cells']!r} — something filtered "
        f"the template's declaration")


def test_m4_no_ref_case_points_at_a_real_measured_baseline():
    """'identical to 2a9f6c4' is only checkable against something measured from 2a9f6c4. A
    case carrying its own inline mask would be someone's opinion of that commit."""
    names = {c["name"] for c in _cases("mask_baseline_cases")}
    for c in _cases("valid_die_basis_cases"):
        if c.get("baseline_case"):
            assert c["baseline_case"] in names, (
                f"{c['name']} references baseline {c['baseline_case']!r}, which is not in "
                f"mask_baseline_cases")


def test_m4_ref_key_reuses_the_7b_canonicalisation(declare):
    """INV-M4-4. The expected value is not trusted as a literal: it is asserted to be the
    answer `canonical_map_key` already gives for the mirrored 7b case. If M4 ever resolved
    refs with its own normalisation, this is where it surfaces."""
    for c in _cases("valid_die_ref_canonical_cases"):
        declare(c["table"], c["column_types"])
        got = map_overlay.canonical_map_key(c["table"], _binding(c), c["declared_ref_key"])
        assert got == c["expect_resolved"], (
            f"{c['name']}: 7b canonicalisation gives {got!r} but the M4 vector expects "
            f"{c['expect_resolved']!r} — one of the two is a second normalisation")
        mirror = _case("canonical_map_key_cases", c["mirrors_case"])
        assert mirror["column_types"] == c["column_types"], (
            f"{c['name']} claims to mirror {c['mirrors_case']!r} but declares different "
            f"column types — the mirror is decorative")


# ---------------------------------------------------------------------------
# M4② — authoring the declaration (INV-M4-1 write path / INV-M4-5) and the
#       one-hop limit (INV-M4-6)
#
# Both rest on symbols the contract declares `required`. A missing one is a CONTRACT
# failure, not a harness failure: the invariant is unscored and the run must say so by
# name, with an owner. `_server_symbol` is that failure — never a skip, never an xfail.
# A comfortable green here is precisely how the previous round's two HIGH defects reached
# review.
# ---------------------------------------------------------------------------

def _server_symbol(role):
    """Resolve a contract symbol, honouring the SHARED status vocabulary.

    The table lives in `vectors.json` -> `symbol_status`, and the client harness implements
    the same three states. Note that the lookup happens FIRST and the declared status is only
    consulted when the symbol is absent: that is what makes a landed symbol scored
    automatically, with nobody having to remember to promote it.
    """
    import importlib
    m = _vectors()["server_symbols"][role]
    fn = getattr(importlib.import_module(m["module"]), m["fn"], None)
    if fn is not None:
        return fn

    status = m.get("status")
    if status == "pending":
        # QUIET BY DESIGN, and only this one state is. These vectors were written
        # contract-first, so having nothing to score yet is the intended condition, not a
        # regression — rendering it red teaches people to ignore a red suite, and a suite
        # nobody reads is how `split_registry_harness.mjs` stayed dead from U6.
        # It stops being quiet the moment the symbol appears: see
        # `test_pending_symbols_are_owned_and_never_stale`.
        pytest.skip(
            f"PENDING: {m['module']}.{m['fn']} (contract role {role!r})\n"
            f"  owner  : {m.get('$owner', 'unassigned')}\n"
            f"  blocks : {m.get('$blocks', '')}\n"
            f"  shape  : {m.get('$shape', '')}\n"
            "Written contract-first; scored automatically the moment the symbol lands.")
    if status == "live":
        pytest.fail(
            f"RENAMED or REMOVED: {m['module']}.{m['fn']} (contract role {role!r})\n"
            "This symbol was declared `live`, meaning it existed. Its disappearance is a "
            "regression, NOT a pending axis — do not demote it to `pending` to silence this. "
            "Update vectors.json server_symbols deliberately if it was renamed.")
    pytest.fail(
        f"NOT LANDED: {m['module']}.{m['fn']} (contract role {role!r})\n"
        f"  owner  : {m.get('$owner', 'unassigned')}\n"
        f"  blocks : {m.get('$blocks', '')}\n"
        f"  shape  : {m.get('$shape', '')}\n"
        "The invariant above is UNSCORED until this lands. `required` means overdue rather "
        "than unscheduled; if it is merely unscheduled, the Lead PM demotes it to `pending`. "
        "Do not delete the check and do not xfail it.")


def _apply_ops(fn, base_meta, ops, case=None):
    """Run a case's authoring sequence. `set` may be a bare key string or an object.

    A RAISE is not an error in the test — it is one of the two answers this seam can give,
    and the case may carry the other side's measured answer in `$client_measured`. Reporting
    it as a bare traceback would hide a divergence inside a stack trace; reporting BOTH
    answers is what makes it a contract finding the Lead PM can rule on.
    """
    meta = base_meta
    for op in ops:
        try:
            meta = fn(meta, None) if op.get("clear") else fn(meta, op["set"])
        except Exception as e:                       # noqa: BLE001 — the raise IS the answer
            measured = (case or {}).get("$client_measured") or {}
            pytest.fail(
                f"{(case or {}).get('name', '?')}: the server writer RAISED on {op!r}\n"
                f"  server : [{type(e).__name__}] {e}\n"
                f"  client : reads back as {measured.get('reads_back_as', '(not recorded)')!r}"
                f" — {measured.get('fn', 'the landed client writer')}"
                f" (measured {measured.get('on', '?')})\n"
                f"  contract says: {(case or {}).get('expect_read', '?')!r}\n"
                "TWO WRITERS, TWO ANSWERS, ONE INPUT. This is a seam divergence, not a test "
                "error: take both answers to the Lead PM rather than editing either side to "
                "match the other. See the vector's $why for the grounds behind the contract "
                "value and for the alternative it deliberately did not choose.")
    return meta


def _stored_ref(meta):
    return meta.get("valid_die_ref") if isinstance(meta, dict) else None


def test_authoring_round_trip_matches_the_contract():
    """INV-M4-5. Scored THROUGH THE READER: the writer's output is handed to the contract's
    own `parse_valid_die_ref` / `resolve_valid_die_basis` and asked what it means.

    Nothing here asserts the stored shape. The contract does not get to pick between the
    string form and the object form — only to insist that whichever is written reads back as
    the thing that was asked for, and that an unset reads back as `circle`.
    """
    fn = _server_symbol("apply_valid_die_ref")
    for c in _cases("valid_die_authoring_cases"):
        home = c["home_table"]
        out = _apply_ops(fn, json.loads(json.dumps(c["base_meta"])), c["ops"], c)
        kind, _ref = _parse_outcome(out, home)
        assert kind == c["expect_read"], (
            f"{c['name']}: after {c['ops']!r} the declaration reads {kind!r}, contract says "
            f"{c['expect_read']!r} (stored: {_stored_ref(out)!r})")
        if kind == "ref":
            # [1-a] Same split the client harness makes, and for the same reason: this group
            # scores what the WRITER PUT IN THE METADATA, so the table comes from the
            # storage-bytes reader (`valid_die_ref_display`), never from the pinned parser.
            # Since the load pin the parser answers `valid_die_ref` for every declaration
            # whatever the bytes say, so reading the written table back through it would make
            # "the writer preserved the declared table" UNFALSIFIABLE here. The KIND above
            # still goes through the parser, because the kind did not move.
            shown = _server_symbol("valid_die_ref_display")(_stored_ref(out))
            saved_table = shown["table"] if shown["table"] != "" else home
            assert saved_table == c["expect_table"], (
                f"{c['name']} table: stored {_stored_ref(out)!r} -> {saved_table!r}, "
                f"contract says {c['expect_table']!r}")
            assert shown["map_id"] == c["expect_key"], (
                f"{c['name']} map_id: stored {_stored_ref(out)!r} -> {shown['map_id']!r}")
        if "expect_source" in c:
            got = map_overlay.resolve_valid_die_basis(out, None, table=home)
            assert got["source"] == c["expect_source"], (
                f"{c['name']}: the branch point says {got['source']!r}, contract says "
                f"{c['expect_source']!r}. An unset that does not reach `circle` is a map "
                f"nobody can return to circle geometry — `valid_die_ref` has no other editor.")


def test_authoring_never_writes_an_unreadable_declaration():
    """DERIVED over the whole group, and it is the vector-free half of INV-M4-5.

    `""`, `"   "` and `{map_id: ""}` are all things a cleared form field produces, and the
    reader calls every one of them an ERROR — which by the phase-1 rule is a DECLARATION, so
    the map is refused permanently and the metadata has no other editor. No authoring
    sequence in this contract may produce one.
    """
    fn = _server_symbol("apply_valid_die_ref")
    for c in _cases("valid_die_authoring_cases"):
        out = _apply_ops(fn, json.loads(json.dumps(c["base_meta"])), c["ops"], c)
        kind, _ = _parse_outcome(out, c["home_table"])
        assert kind != "error", (
            f"{c['name']}: the writer produced a declaration the reader cannot read "
            f"({_stored_ref(out)!r}). That map is now `refused` on both sides with no UI path "
            f"back to circle geometry.")


def test_authoring_never_writes_a_tableless_object():
    """WAS `test_authoring_never_writes_the_shape_the_two_sides_read_differently`, and the
    RE-ANCHORING is recorded rather than performed quietly.

    The original grounds were a seam divergence: `{map_id: k}` with no table was the one shape
    the server resolved and the client refused. The 1-a pin CLOSED that — both sides now read
    it as `ref` — so the assertion lost its anchor, and the honest options were to delete it or
    to name a live harm. It has one, checked below rather than asserted in prose: with no table
    in the bytes, `declared_table` falls back to the DECLARING map's table, so the refusal text
    goes on to name a table the operator never wrote. A refusal that names the wrong table is
    worse than a generic one, because it sends the repair to the wrong place.

    (Reported to the Lead PM as an assertion whose original anchor closed — the new anchor is
    weaker than the old one and is a judgement, not a measurement.)
    """
    fn = _server_symbol("apply_valid_die_ref")
    diverging = _case("valid_die_ref_home_divergence_cases", "object_no_table_no_home")
    assert diverging["expect_server"] == diverging["expect_client"], (
        "the recorded divergence on the table-less object has REOPENED — the two sides read "
        "it differently again, which is a bigger problem than this test's own subject")
    # The live harm, RUN rather than described: with no table in the bytes the parse invents
    # one from the home table. That invented name is what a refusal would go on to print.
    _kind, invented = _parse_outcome({"valid_die_ref": {"map_id": "TPL_1"}}, "seam_map")
    assert invented["declared_table"] == "seam_map", (
        "a table-less object no longer inherits the home table into `declared_table`, so the "
        "harm this test guards against has changed shape — re-derive it before editing")
    for c in _cases("valid_die_authoring_cases"):
        out = _apply_ops(fn, json.loads(json.dumps(c["base_meta"])), c["ops"], c)
        stored = _stored_ref(out)
        if isinstance(stored, dict):
            table = stored.get("table", stored.get("target_table"))
            assert table is not None and str(table).strip(), (
                f"{c['name']}: wrote {stored!r} — an object declaration with no table. The "
                f"server resolves that shape and the client refuses it, so the same map "
                f"would have a mask on one side and a refusal on the other.")


def test_authoring_preserves_every_other_key_including_declared_falsies():
    """INV-M4-1 at the WRITE path. The declaration is one key in a payload the write path
    does not own; touching it may not disturb the rest.

    The falsy declarations in the base metas are the point: a writer that rebuilds from the
    fields it knows drops the ones it does not, and one that copies with `v or default`
    turns `phys_edge_margin: 0` into 3.0 — moving the wafer mask of a map whose valid-die
    reference was merely being cleared. That is known defect D1's shape one layer up, and it
    is silent.
    """
    fn = _server_symbol("apply_valid_die_ref")
    for c in _cases("valid_die_authoring_cases"):
        base = json.loads(json.dumps(c["base_meta"]))
        out = _apply_ops(fn, json.loads(json.dumps(c["base_meta"])), c["ops"], c)
        before = {k: v for k, v in base.items() if k != "valid_die_ref"}
        after = {k: v for k, v in out.items() if k != "valid_die_ref"}
        assert after == before, (
            f"{c['name']}: authoring changed metadata it does not own\n"
            f"  lost/changed: { {k: before[k] for k in before if after.get(k, '~') != before[k]} }\n"
            f"  invented    : { {k: after[k] for k in after if k not in before} }")


def test_authoring_does_not_mutate_its_argument():
    """A mutating writer breaks Cancel: the in-memory metadata already carries the edit the
    user just abandoned, and nothing on screen says so."""
    fn = _server_symbol("apply_valid_die_ref")
    for c in _cases("valid_die_authoring_cases"):
        arg = json.loads(json.dumps(c["base_meta"]))
        snapshot = json.loads(json.dumps(c["base_meta"]))
        _apply_ops(fn, arg, c["ops"], c)
        assert arg == snapshot, (
            f"{c['name']}: apply_valid_die_ref MUTATED the metadata it was given\n"
            f"  before: {snapshot!r}\n  after : {arg!r}")


def test_authoring_is_idempotent_in_the_last_operation():
    """Repeating the last op must change nothing. A clear that appends debris, or a set that
    accumulates, only shows up on the second application — and in an editor the second
    application is one extra click."""
    fn = _server_symbol("apply_valid_die_ref")
    for c in _cases("valid_die_authoring_cases"):
        once = _apply_ops(fn, json.loads(json.dumps(c["base_meta"])), c["ops"], c)
        twice = _apply_ops(fn, json.loads(json.dumps(c["base_meta"])),
                           list(c["ops"]) + [c["ops"][-1]], c)
        assert twice == once, (
            f"{c['name']}: repeating {c['ops'][-1]!r} changed the result\n"
            f"  once : {once!r}\n  twice: {twice!r}")


def test_authoring_group_covers_both_directions():
    """Fixture-inactivity guard. A group that only SETS passes against a writer with no clear
    path at all, and the round would ship the unrecoverable state INV-M4-5 exists to prevent.
    """
    cs = _cases("valid_die_authoring_cases")
    assert any(any("clear" in op for op in c["ops"]) for c in cs), "no UNSET case"
    assert any(c["expect_read"] == "none" for c in cs), "no case ends with NO declaration"
    assert any(c["expect_read"] == "ref" for c in cs), "no case ends with a declaration"
    assert any(len(c["ops"]) >= 3 for c in cs), (
        "no set -> clear -> set case. Two operations cannot see a clear that leaves debris "
        "the next set appends to")
    assert any(c["base_meta"].get("valid_die_ref") is not None
               and not isinstance(c["base_meta"]["valid_die_ref"], (str, dict))
               for c in cs), (
        "no case clears an UNREADABLE declaration — that is the recovery path, and a writer "
        "that parses before it writes cannot walk it")
    assert any(0 in c["base_meta"].values() or False in c["base_meta"].values()
               or "" in c["base_meta"].values() for c in cs), (
        "no base metadata declares a falsy value. `0`/`false`/`\"\"` are legitimate "
        "declarations and they are the ones a rebuild-style writer destroys first")


# ---------------------------------------------------------------------------
# M4② — the one-hop limit (INV-M4-6)
# ---------------------------------------------------------------------------

def _chain_ref(case, declare):
    """The case's reference, canonicalised through the ALREADY-SCORED 7b primitive.

    Not through a literal in the vector: `canonical_map_key` is what the resolver uses, so
    running it here is what makes 'the guard compares canonical identities' an assertion
    rather than a claim.
    """
    key = case["declared_ref_key"]
    if case.get("key_columns"):
        declare(case["table"], case["column_types"])
        key = map_overlay.canonical_map_key(case["table"], _binding(case), key)
    return {"table": case["ref_table"], "map_id": key}


def _chain_home(case):
    return {"table": case["home"]["table"], "map_id": case["home"]["map_id"]}


def test_chain_limit_matches_the_contract(declare):
    """INV-M4-6. A valid-die map is a map, so it can declare one of its own; the reference
    is legal for exactly one hop.

    Today NEITHER refusal exists: `resolve_valid_die_set` loads the referenced map's meta and
    never asks what that map declares, so a two-level chain resolves to the MIDDLE map's
    stored cells — a set nobody declared, wearing a resolved reference's chip.
    """
    fn = _server_symbol("valid_die_chain_error")
    for c in _cases("valid_die_chain_cases"):
        err = fn(_chain_ref(c, declare), c["ref_meta"], _chain_home(c))
        if c["expect"] == "ok":
            assert err is None, (
                f"{c['name']}: a LEGAL reference was refused ({err!r}). A guard that refuses "
                f"too much disables the feature this round ships, and it passes every "
                f"refusal vector in this group.")
        else:
            assert isinstance(err, str) and err.strip(), (
                f"{c['name']}: expected a refusal ({c['expect_kind']}) and got {err!r}. A "
                f"refusal with no reason is a silent failure with extra steps — INV-M4-3's "
                f"rule, one layer down.")


def test_chain_and_self_reference_do_not_share_one_reason(declare):
    """The two refusals are different problems with different fixes — re-point the reference
    vs. flatten the template. The wording is NOT pinned (that would freeze a user-facing
    string into a contract); what is pinned is that an operator can tell them apart."""
    fn = _server_symbol("valid_die_chain_error")
    reasons = {}
    for c in _cases("valid_die_chain_cases"):
        if c["expect"] != "refused":
            continue
        reasons.setdefault(c["expect_kind"], set()).add(
            fn(_chain_ref(c, declare), c["ref_meta"], _chain_home(c)))
    self_r = reasons.get("self_reference", set())
    chain_r = reasons.get("chain", set())
    assert self_r and chain_r, "the group lost one of the two refusal kinds"
    assert not (self_r & chain_r), (
        "self-reference and a two-level chain produce the SAME reason, so the operator "
        f"cannot tell which one they have: {sorted(self_r & chain_r)!r}")


def test_chain_self_reference_is_compared_after_7b_canonicalisation(declare):
    """INV-M4-7 reuse, asserted by RUNNING the pair rather than trusting two literals.

    The same declared text against the same home key must be a self-reference under
    `slot: number` and a legal reference under `slot: string`. The second polarity is the
    load-bearing one: it is what a guard carrying its own normalisation fails, and a second
    normalisation is exactly what INV-M4-4 forbids.

    NOT SCORED HERE, deliberately: that the CALLER canonicalises before consulting the guard.
    That step is DB-bound and no scorer reaches it — `valid_die_ref_canonical_cases` covers
    it at the resolver. The canonicalisation performed below is the SCORER'S, and asserting
    it against itself would be the copy-harness failure this file has been bitten by before.
    """
    fn = _server_symbol("valid_die_chain_error")
    pair = [c for c in _cases("valid_die_chain_cases") if c.get("mirrors_case")]
    assert len(pair) >= 2, (
        "the canonicalisation pair is gone. Without it a guard comparing raw declared text "
        "passes this whole group, and 'LOT_01 vs LOT_1' is the exact defect 7b exists for")
    keys = {c["declared_ref_key"] for c in pair}
    homes = {c["home"]["map_id"] for c in pair}
    assert len(keys) == 1 and len(homes) == 1, (
        f"the mirrored cases no longer share their declared key/home key ({keys!r} / "
        f"{homes!r}) — then the differing answer is explained by the input, not by the "
        f"declared type, and the pair proves nothing")
    assert {c["expect"] for c in pair} == {"ok", "refused"}, (
        "the mirrored cases agree; the pair only has teeth when the declared TYPE flips the "
        "answer")
    for c in pair:
        mirror = _case("canonical_map_key_cases", c["mirrors_case"])
        assert mirror["column_types"] == c["column_types"], (
            f"{c['name']} claims to mirror {c['mirrors_case']!r} but declares different "
            f"column types — the mirror is decorative")
        err = fn(_chain_ref(c, declare), c["ref_meta"], _chain_home(c))
        assert (err is None) is (c["expect"] == "ok"), (
            f"{c['name']}: canonicalised key resolves the wrong way (err={err!r})")


def test_a_chain_refusal_reaches_the_branch_point_as_refused(declare):
    """INV-M4-5's other half at the new refusal route: a chain error must arrive at
    `resolve_valid_die_basis` as `refused` with the reason intact, never as `circle`.

    The resolver return shape used here is the one `resolve_valid_die_basis` documents
    (`{status, cells, detail}`), so this is the real wiring and not a second answer.
    """
    fn = _server_symbol("valid_die_chain_error")
    c = next(x for x in _cases("valid_die_chain_cases")
             if x["expect"] == "refused" and x.get("expect_kind") == "chain")
    reason = fn(_chain_ref(c, declare), c["ref_meta"], _chain_home(c))
    out = map_overlay.resolve_valid_die_basis(
        {"valid_die_ref": c["declared_ref_key"]},
        lambda _ref: {"status": map_overlay.STATUS_REF_UNAVAILABLE, "detail": reason},
        table=c["home"]["table"])
    assert out["source"] == "refused", (
        f"a chain refusal landed on {out['source']!r}. Falling back to circle geometry here "
        f"is the silent fallback INV-M4-3 forbids, reached through a new door.")
    assert out.get("basis") is None, "a refusal shipped a fallback basis"
    assert reason in (out.get("reason") or ""), (
        f"the chain reason was replaced by a generic one:\n  chain says: {reason!r}\n"
        f"  branch says: {out.get('reason')!r}\nThe operator is then told the reference "
        f"failed without being told it is a chain, which is the one fact that says what to "
        f"fix.")


def test_chain_group_covers_every_shape_it_claims(declare):
    """Fixture-inactivity guard. Each of these is a DIFFERENT wrong guard; losing any one of
    them leaves that guard passing."""
    cs = _cases("valid_die_chain_cases")
    kinds = {c.get("expect_kind") for c in cs if c["expect"] == "refused"}
    assert kinds == {"self_reference", "chain"}, (
        f"refusal kinds are {sorted(k for k in kinds if k)!r}; the contract names exactly "
        f"self_reference and chain, and two vocabularies on one seam is how a mapping table "
        f"gets written")
    assert any(c["expect"] == "ok" for c in cs), (
        "no LEGAL reference — a guard that refuses everything passes")
    declared = [c["ref_meta"].get("valid_die_ref") for c in cs
                if c["ref_meta"] and "valid_die_ref" in c["ref_meta"]]
    assert any(d == 0 or d is False or d == "" for d in declared), (
        "no case where the MIDDLE map's declaration is falsy. `if ref_meta['valid_die_ref']:` "
        "is the shortest way to write this guard and it is wrong for exactly those values")
    assert any(d == "" for d in declared), (
        "no case where the middle map's declaration is BROKEN. A guard written as "
        "`parse(ref_meta)[0] is not None` folds an unreadable declaration into absence — the "
        "phase-1 silent fallback, one layer down")
    assert any(c["ref_meta"] is not None and "valid_die_ref" in c["ref_meta"]
               and c["ref_meta"]["valid_die_ref"] is None for c in cs), (
        "no case where the middle map declares an explicit null — a guard testing key "
        "PRESENCE rather than value refuses that legal reference")
    assert any(c["ref_meta"] is None for c in cs), (
        "no case with unknown referenced metadata; that state is already refused upstream by "
        "`align_unavailable` and this predicate must not give it a second vocabulary")
    homes = {(c["home"]["table"], c["home"]["map_id"]) for c in cs}
    assert any(c["ref_table"] != c["home"]["table"] for c in cs), (
        "no cross-table case — a guard comparing keys alone refuses the commonest authoring "
        "shape")
    assert any(c["ref_table"] == c["home"]["table"]
               and c["declared_ref_key"] != c["home"]["map_id"] for c in cs), (
        "no same-table/different-key case — a guard comparing tables alone refuses every "
        "inherited-table reference")
    assert homes, "empty group"


# ---------------------------------------------------------------------------
# Known-defect pins — the SERVER half of the mechanism
#
# The pins themselves are scored by the client harness (they record CLIENT behaviour). What
# this side owns is the thing a client-side scorer structurally cannot check: that a pin
# stays client-scoped, stays attributable, and never quietly weakens the server's own
# assertion on the same vector. A pin is a licence to be red; it must not become a licence
# to stop being scored.
# ---------------------------------------------------------------------------

_PIN_KEY = "$client_known_defect"
_REQUIRED_DEFECT_FIELDS = (
    "title", "site", "statement", "predates", "predates_evidence",
    "server_is_correct", "impact", "why_not_fixed_in_this_round", "owner", "clears_when",
)


def _all_pins():
    """(group, case, pin) for every pinned vector in the file."""
    out = []
    for group, entries in _vectors().items():
        if not (group.endswith("_cases") and isinstance(entries, list)):
            continue
        for c in entries:
            if isinstance(c, dict) and _PIN_KEY in c:
                out.append((group, c, c[_PIN_KEY]))
    return out


def test_every_pin_names_a_registered_defect():
    """An anonymous red wearing an id is still an anonymous red.

    The whole value of a pin is that a reader can go from a failing vector to WHO owns it,
    WHY it was deferred and WHAT clears it, without asking anyone. That only holds while every
    pin resolves to a registry entry that actually carries those fields.
    """
    registry = _vectors().get("known_defects", {})
    for group, case, pin in _all_pins():
        ident = pin.get("defect")
        assert ident in registry, (
            f"{group}.{case['name']} pins defect {ident!r}, which is not in `known_defects`. "
            f"Register it with its owner and clearing condition, or remove the pin and let "
            f"the vector be red.")
        missing = [f for f in _REQUIRED_DEFECT_FIELDS if not registry[ident].get(f)]
        assert not missing, (
            f"known_defects.{ident} is missing {missing} — a pin without an owner and a "
            f"clearing condition is a permanent red with better manners.")


def test_a_pin_is_never_vacuous():
    """A pin whose recorded value equals the contract value cancels its own vector.

    Scored on BOTH sides on purpose: this is the one way to turn a red vector permanently
    green by writing the same number twice, so it may not depend on one scorer being run.
    """
    for group, case, pin in _all_pins():
        for field, recorded in (pin.get("client_actual") or {}).items():
            contract = case.get(field if field != "mask" else "mask")
            assert recorded != contract, (
                f"{group}.{case['name']}.{field}: the pinned client_actual is identical to "
                f"the contract value ({contract!r}). The pin asserts nothing and hides the "
                f"vector — a pin must record a real disagreement.")


def test_pins_never_claim_the_server_side():
    """Pins are client-scoped BY CONSTRUCTION, and this is the assertion that keeps it true.

    The server is scored against the CONTRACT value on the very same vectors — that asymmetry
    is what makes a recorded client value evidence of a seam disagreement rather than a label
    pasted over a red. The day someone adds `$server_known_defect`, both sides would be
    excused at once and the vector would stop being a contract at all.
    """
    banned = {"$server_known_defect", "$known_defect", "$xfail", "$expected_failure"}
    found = []
    for group, entries in _vectors().items():
        if not (group.endswith("_cases") and isinstance(entries, list)):
            continue
        for c in entries:
            if isinstance(c, dict):
                found += [f"{group}.{c.get('name', '?')}.{k}" for k in c if k in banned]
    assert not found, (
        "these keys would excuse the SERVER from a contract vector: " + ", ".join(found)
        + "\nA seam contract that lets both sides off the same vector asserts nothing. If the "
        "server genuinely cannot meet a vector, that is a NOT LANDED failure, not a pin.")


def test_pinned_vectors_are_still_scored_against_the_contract_here():
    """The server assertion on a pinned vector must be the CONTRACT value, unchanged.

    `test_mask_baseline_matches_the_recorded_2a9f6c4_measurement` above reads `c["mask"]`
    directly, so this is already true — but it is true by accident of how that test is
    written. Stated here so that a future edit which starts consulting the pin has to delete
    an assertion that says, in words, why it must not.
    """
    pinned = [(g, c) for g, c, _ in _all_pins()]
    assert pinned, (
        "no pinned vectors found. If D1 was fixed and the pins removed, delete this test's "
        "expectation too — otherwise it is the stale pin.")
    for group, case in pinned:
        if group != "mask_baseline_cases":
            continue
        dia, cx, cy, ox, oy, margin = map_overlay._frame_phys_params(_meta_of(case))
        eng = PhysicalWaferEngine(wafer_diameter_mm=dia, chip_size_x_mm=cx, chip_size_y_mm=cy,
                                  edge_exclusion_mm=margin, offset_x_mm=ox, offset_y_mm=oy)
        assert eng.effective_radius_mm == pytest.approx(case["effective_radius_mm"]), (
            f"{case['name']}: the server no longer meets the contract value on a vector that "
            f"is PINNED on the client. The pin records a one-sided defect; if the server has "
            f"drifted too, the vector has stopped describing a seam at all.")
