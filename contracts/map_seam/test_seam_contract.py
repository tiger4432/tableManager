"""MAP SEAM — the SERVER half, scored against the shared contract vectors.

The file being scored is `contracts/map_seam/vectors.json`, and it is the same file
`contracts/map_seam/client_harness.mjs` reads. Nothing here hardcodes an expectation:
every assertion comes out of the contract, so deleting a case removes coverage LOUDLY
(`test_every_vector_group_is_consumed_or_declared`).

WHY IT LIVES UNDER contracts/ AND NOT server/tests/
    Three agents held this tree open while the round landed, and a seam contract is worth
    nothing if landing it costs someone else a round to a merge conflict. The module is
    self-bootstrapping (it puts `server/` on sys.path itself), so it runs standalone:

        conda run -n assy_manager python -m pytest contracts/map_seam/ -q

HOW IT REACHES THE DEFAULT SUITE  [wired 2026-07-29]
    `server/tests/test_map_seam_contract.py` re-exports every test in this module, so

        conda run -n assy_manager python -m pytest server/tests/ -q

    covers this contract. That shim exists instead of a `testpaths` entry for a concrete
    reason: pytest IGNORES testpaths whenever paths are given on the command line, and the
    documented command everywhere in this repo passes `server/tests/` explicitly. A testpaths
    change would have looked like wiring and changed nothing.

    Do not move the assertions into the shim. This file stays the one definition; the shim
    only makes it reachable.

WHAT IS SCORED, AND WHAT IS DECLARED
    7b  canonical_value / compose / decompose / canonical_map_key      — fully scored
        compose_divergence / decompose_lossy                          — scored AS DIVERGENCE
    7c  chips_bound                                                   — fully scored (pure)
        transfer_log_declaration                                      — fully scored (the named
                                                                        predicate landed 2026-07-29)
    M4  mask_baseline / valid_die_ref_parse / valid_die_basis         — fully scored
        valid_die_ref_home_divergence                                 — scored AS DIVERGENCE

    A pending group FAILS. It is not skipped and not marked xfail: a contract the code does
    not meet yet is a red contract, and a comfortable green is how the previous round's two
    HIGH defects reached review.

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
}
_CLIENT_ONLY = {
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
