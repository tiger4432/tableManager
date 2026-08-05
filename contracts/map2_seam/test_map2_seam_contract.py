"""MAP EDITOR 2 SEAMS -- the SERVER half, scored against the shared contract vectors.

The file being scored is `contracts/map2_seam/vectors.json`, and it is the same file
`contracts/map2_seam/client_harness.mjs` reads. Nothing here hardcodes an expectation: every
assertion comes out of the contract, so deleting a case removes coverage LOUDLY
(`test_every_vector_group_is_consumed_or_declared`).

WHY IT LIVES UNDER contracts/ AND NOT server/tests/
    Six lanes held this tree open while the round landed, and a seam contract is worth nothing
    if landing it costs somebody else a round to a merge conflict. The module is
    self-bootstrapping (it puts `server/` on sys.path itself), so it runs standalone:

        conda run -n assy_manager python -m pytest contracts/map2_seam/ -q -rs

    It is ALSO the reason the contract is not in `client2/tests/`: the rename detector scopes
    `client2/src`, so a harness parked in `client2/tests/` can die at the extraction step and
    stay dead. `split_registry_harness.mjs` sat broken from U6 for exactly that reason.

REACHING THE DEFAULT SUITE -- NOT YET WIRED, AND THAT IS A REPORTED GAP
    A contract that `pytest server/tests/` does not run is dead within a week. The shim that
    fixes it -- `server/tests/test_map2_seam_contract.py`, mirroring the existing
    `test_map_seam_contract.py` -- is OUTSIDE `contracts/` and this agent owns `contracts/`
    and nothing else, so it was reported to the lead PM rather than written here. Until the
    shim lands, this contract runs only on the standalone command above.

`-rs` IS PART OF THE COMMAND, NOT AN OPTION
    Several axes here are PENDING -- vectors authored before the implementation exists. The
    rule is that pending does not block the SUITE but does block ROUND COMPLETION, and that
    rule only functions while pending is visible BY NAME AND NUMBER. Bare `-q` prints a count;
    `-rs` prints the reason line for every skip, and the reasons below carry the axis, the
    owner, and what stays unscored.

WHAT IS SCORED HERE, AND WHAT IS DECLARED
    S1 orientation_agreement_cases     -- fully scored (both sides)
       orientation_divergence_cases    -- scored AS DIVERGENCE: the SERVER's answer is pinned,
                                          the client's is pinned in the harness, and neither is
                                          asserted to be right. The lead PM decides.
       orientation_census              -- fully scored (both sides), 23 shapes / 668 rows
    S2 frame_basis_cases               -- SERVER fully scored. The client is a NAMED EXPECTED
                                          FAILURE, not an anonymous red.
    S3 scoring_invariants              -- structural invariants scored; the ORACLE COMPARISON is
                                          unscored and reported by name.
    S4 excel_form_cases                -- one duplicate guard scored; the round trip is PENDING.
    S5 align_origin_cases              -- server vocabulary scored; the two client consumers are
                                          UNSCORED and reported, because they live in the frozen
                                          legacy editor and the only way to reach them is to
                                          assert on source text.

A GREEN RUN OF THIS FILE MEANS THE SERVER MEETS THE CONTRACT. It is not a statement about the
client, and it is not a statement about production -- everything measured here was measured on
a DEVELOPMENT box.
"""
import json
import pathlib
import re
import sys

import pytest

_HERE = pathlib.Path(__file__).resolve().parent
_REPO = _HERE.parents[1]
_SERVER = _REPO / "server"

if str(_SERVER) not in sys.path:
    sys.path.insert(0, str(_SERVER))


def _load(name):
    return json.loads((_HERE / name).read_text(encoding="utf-8"))


VECTORS = _load("vectors.json")
SHAPES = _load("orientation_shapes.json")

AXIS_SPELLING = {k: v for k, v in VECTORS["$axis_spelling"].items() if not k.startswith("$")}
SERVER_AXES = tuple(AXIS_SPELLING.keys())


# ── symbol availability ─────────────────────────────────────────────────────────
# An UNLISTED CALLEE makes its CALLER unevaluable, and silently. Every symbol this file
# touches is resolved here first, so a rename surfaces as a named skip carrying the symbol
# rather than as a green run that scored nothing.
def _server_symbol(dotted_module, name):
    try:
        mod = __import__(dotted_module, fromlist=["*"])
    except Exception as exc:                                    # noqa: BLE001
        return None, f"{dotted_module} did not import: {type(exc).__name__}: {exc}"
    obj = getattr(mod, name, None)
    if obj is None:
        return None, (
            f"{dotted_module}.{name} does not exist. It is listed in vectors.json "
            "`server_symbols`, so either it was renamed (update the contract WITH the rename) "
            "or the lane has not landed it yet.")
    return obj, None


def _require(name):
    module = VECTORS["server_symbols"].get(name)
    if module is None:
        pytest.skip(f"UNSCORED: '{name}' is not declared in vectors.json server_symbols")
    obj, why = _server_symbol(module, name)
    if obj is None:
        pytest.skip(f"UNSCORED: {why}")
    return obj


# ═══════════════════════════════════════════════════════════════════════════════
# S1  THE DECLARATION VOCABULARY
# ═══════════════════════════════════════════════════════════════════════════════

def _decl(meta):
    return _require("orientation_declaration")(meta)


@pytest.mark.parametrize(
    "case", VECTORS["orientation_agreement_cases"]["cases"],
    ids=[c["id"] for c in VECTORS["orientation_agreement_cases"]["cases"]])
def test_orientation_agreement(case):
    """Both sides must give THIS answer. The expectation came from Rule N plus the lead PM's
    2026-08-05 start ruling -- not from either implementation."""
    got = _decl(case["meta"])

    for axis, want in case.get("expect", {}).items():
        assert axis in got, (
            f"[{case['id']}] axis '{axis}' missing from orientation_declaration's answer. "
            "All five axes must always be present -- a caller cannot refuse what it cannot "
            "observe.")
        assert got[axis]["source"] == want["source"], (
            f"[{case['id']}] {axis} source: expected '{want['source']}', got "
            f"'{got[axis]['source']}'.\n  why: {case['$why']}\n  kills: {case['$kills']}")
        assert got[axis]["value"] == want["value"] and \
               type(got[axis]["value"]) is type(want["value"]), (
            f"[{case['id']}] {axis} value: expected {want['value']!r}, got "
            f"{got[axis]['value']!r}. The VALUE is what the reader will actually use, so a "
            "matching token with a different value is still a divergence.")

    for axis, want_source in case.get("expect_source_only", {}).items():
        assert got[axis]["source"] == want_source, (
            f"[{case['id']}] {axis} source: expected '{want_source}', got "
            f"'{got[axis]['source']}'")


@pytest.mark.parametrize(
    "case", VECTORS["geometry_declaration_cases"]["cases"],
    ids=[c["id"] for c in VECTORS["geometry_declaration_cases"]["cases"]])
def test_geometry_declaration_agreement(case):
    """The WHOLE-META physical verdict, one word. A different question from the per-axis
    orientation cases, and measured to be one they cannot answer: deleting the borrow branch
    from the client port left every orientation case green.

    Both sides must give THIS answer. The expectation comes from the spec, not from either
    implementation.
    """
    got = _require("geometry_declaration")(case["meta"])
    assert got == case["expect"], (
        f"[{case['id']}] expected '{case['expect']}', got '{got}'.\n"
        f"  why: {case['$why']}\n  kills: {case['$kills']}")


@pytest.mark.parametrize(
    "case", VECTORS["orientation_divergence_cases"]["cases"],
    ids=[c["id"] for c in VECTORS["orientation_divergence_cases"]["cases"]])
def test_orientation_divergence_server_half(case):
    """A DECLARED DIVERGENCE. This asserts only that the SERVER still answers what it answered
    when the divergence was measured -- it does NOT assert the server is right.

    Green here means "the two sides diverge today exactly as recorded". The lead PM decides
    which side becomes the contract; when that happens this case must move into
    `orientation_agreement_cases`, and the harness fails if a divergence quietly disappears.
    """
    got = _decl(case["meta"])
    axis = case["axis"]
    want = case["server"]
    assert got[axis]["source"] == want["source"] and got[axis]["value"] == want["value"], (
        f"[{case['id']}] the SERVER's half of a recorded divergence changed.\n"
        f"  recorded: {want}\n  now:      {{'value': {got[axis]['value']!r}, "
        f"'source': {got[axis]['source']!r}}}\n"
        f"  client side of this divergence: {case['client']}\n"
        "  If this was a deliberate fix, move the case to orientation_agreement_cases; "
        "leaving it here makes the contract lie about the seam.")
    # start_absent_substitute names a second axis explicitly.
    if case.get("$also"):
        assert got["grid_start_y"]["value"] == want["value"], case["$also"]


def test_orientation_census():
    """668 production rows in 23 shapes, classified. One case at a time and a whole population
    are different claims: a rule can be right on every hand-written case and put the population
    in the wrong buckets, which is precisely the 660-of-668 inversion the start ruling closes.
    """
    decl = _require("orientation_declaration")
    census = {axis: {} for axis in SERVER_AXES}
    for shape in SHAPES["shapes"]:
        d = decl(shape["meta"])
        for axis in SERVER_AXES:
            tok = d[axis]["source"]
            census[axis][tok] = census[axis].get(tok, 0) + shape["count"]

    expect = VECTORS["orientation_census"]["expect"]
    for axis in SERVER_AXES:
        assert census[axis] == expect[axis], (
            f"census for '{axis}' diverged from the ruling.\n"
            f"  expected: {expect[axis]}\n  measured: {census[axis]}\n"
            f"  {VECTORS['orientation_census']['$expect_notes'][0]}")
    total = sum(s["count"] for s in SHAPES["shapes"])
    assert total == SHAPES["$row_total"], (
        f"the shapes file no longer covers {SHAPES['$row_total']} rows ({total}). A census over "
        "a different population is a different claim.")


def test_start_axes_carry_no_indeterminate_bucket():
    """The 2026-08-05 ruling, made checkable on its own.

    `indeterminate` NEVER applies to start. An implementation that runs the value test on start
    puts rows in that bucket, and -- this is the point -- the two sides put DIFFERENT rows there,
    because the server reader invents 1 and the client reader invents 0.
    """
    decl = _require("orientation_declaration")
    indeterminate = _require("ORIENTATION_INDETERMINATE")
    offenders = []
    for shape in SHAPES["shapes"]:
        d = decl(shape["meta"])
        for axis in ("grid_start_x", "grid_start_y"):
            if d[axis]["source"] == indeterminate:
                offenders.append((axis, shape["meta"], shape["count"]))
    assert not offenders, (
        "start axes landed in `indeterminate`, which the ruling says cannot happen:\n"
        + "\n".join(f"  {a} <- {m} x{n}" for a, m, n in offenders)
        + "\nProvenance for start comes from the MARKER ONLY, never from the value.")


def test_no_evidence_defaults_are_read_out_of_the_readers():
    """The no-evidence table must not be a SECOND transcription of the readers' defaults.

    If it is hand-written, the day somebody changes `_grid_of`'s substitute the table keeps the
    old number and nothing says so -- and the provenance verdict silently inverts on every row
    holding the old value.
    """
    decl = _require("orientation_declaration")
    empty = decl({})
    for reader_name, axis, in (("_rotation_of", "rotation"), ("_side_of", "side"),
                               ("_y_invert_of", "grid_y_invert")):
        reader = _require(reader_name)
        assert empty[axis]["value"] == reader({}), (
            f"the no-evidence value for '{axis}' ({empty[axis]['value']!r}) is not what the "
            f"reader {reader_name} produces for an absent key ({reader({})!r}). Rule N compares "
            "against the reader's invention; if the two drift, the rule is comparing against "
            "a number nobody uses.")
    grid_of = _require("_grid_of")
    grid = grid_of({"grid_cols": 5, "grid_rows": 5})
    if grid:
        assert empty["grid_start_x"]["value"] == grid["start_x"], (
            "the no-evidence value for grid_start_x does not match `_grid_of`'s substitute")


def test_token_vocabulary_is_five_and_shared():
    """One vocabulary at one seam. A mapping table between two token sets would be a second
    implementation of the answer."""
    tokens = {
        _require("GEOMETRY_DECLARED"), _require("GEOMETRY_AUTO_REGISTERED"),
        _require("GEOMETRY_ABSENT"), _require("GEOMETRY_UNPARSABLE"),
        _require("ORIENTATION_INDETERMINATE"),
    }
    assert tokens == {"declared", "auto_registered", "absent", "unparsable", "indeterminate"}, (
        f"the server's orientation token set changed: {sorted(tokens)}. The client's "
        "`DECLARATION_TOKENS` must change in the same commit or the two sides need a mapping "
        "table, and a mapping table is the second spelling this contract exists to prevent.")


def test_orientation_keys_match_the_contract_spelling():
    keys = tuple(_require("ORIENTATION_KEYS"))
    assert keys == SERVER_AXES, (
        f"server ORIENTATION_KEYS {keys} no longer matches vectors.json $axis_spelling "
        f"{SERVER_AXES}. That table is the only place the two sides' spellings are related.")


# ═══════════════════════════════════════════════════════════════════════════════
# S2  THE COORDINATE ROUND TRIP AND THE BOUNDING-BOX BASIS
# ═══════════════════════════════════════════════════════════════════════════════

def _transformer(meta):
    """Build the transformer THE WAY PRODUCTION DOES -- through `_frame_phys_params`.

    Never from raw meta pitch. The spec measures that one bounding box with 8 transforms on top
    misplaces production row `CORE_YINV` by (2,-1), and the cause is precisely this function:
    it swaps the pitch under a quarter turn and flips the offset sign under `back` / 180, and
    the engine is odd in those arguments, so the whole box mirrors.
    """
    tf_cls = _require("WaferMapCoordinateTransformer")
    engine_cls = _require("PhysicalWaferEngine")
    phys = _require("_frame_phys_params")
    rot_of, side_of, yinv_of = _require("_rotation_of"), _require("_side_of"), _require("_y_invert_of")

    dia, chip_x, chip_y, off_x, off_y, margin = phys(meta)
    engine = engine_cls(wafer_diameter_mm=dia, chip_size_x_mm=chip_x, chip_size_y_mm=chip_y,
                        edge_exclusion_mm=margin, offset_x_mm=off_x, offset_y_mm=off_y)
    return tf_cls(cols=meta["grid_cols"], rows=meta["grid_rows"],
                  start_x=meta["grid_start_x"], start_y=meta["grid_start_y"],
                  rotation=rot_of(meta), side=side_of(meta), invert_y=yinv_of(meta),
                  physical_engine=engine)


@pytest.mark.parametrize(
    "case", VECTORS["frame_basis_cases"]["cases"],
    ids=[c["id"] for c in VECTORS["frame_basis_cases"]["cases"]])
def test_frame_bounding_box(case):
    """The BOX ITSELF. The predecessor contract pinned only the box's INPUTS -- the box and the
    mirror were both unpinned, which is why a green run said nothing about this axis.
    """
    tf = _transformer(case["meta"])
    min_c, max_c, min_r, max_r = tf.get_wafer_bounding_box()
    got = {"minC": min_c, "maxC": max_c, "minR": min_r, "maxR": max_r}
    assert got == case["expect_bbox"], (
        f"[{case['id']}] bounding box: expected {case['expect_bbox']}, got {got}.\n"
        f"  why this fixture: {case['$why']}\n  kills: {case['$kills']}")
    assert (tf.visual_cols, tf.visual_rows) == \
           (case["expect_visual"]["cols"], case["expect_visual"]["rows"]), (
        f"[{case['id']}] visual dimensions: expected {case['expect_visual']}, got "
        f"{{'cols': {tf.visual_cols}, 'rows': {tf.visual_rows}}}. A quarter turn swaps them.")


@pytest.mark.parametrize(
    "case", VECTORS["frame_basis_cases"]["cases"],
    ids=[c["id"] for c in VECTORS["frame_basis_cases"]["cases"]])
def test_stored_coordinate_is_box_relative(case):
    """A stored coordinate reversed to a seat. The expectation is the spec's convention:

        c = xv - start_x + box.minC
        r = invert ? box.maxR - (yv - start_y) : yv - start_y + box.minR

    followed by the frame map. It is NOT copied from the transformer -- the transformer merely
    corroborates it, and the same expectation is what the client harness scores `computeSeating`
    against.
    """
    tf = _transformer(case["meta"])
    for pin in case["expect_seats"]:
        xv, yv = pin["stored"]
        got = list(tf.visual_to_physical(xv, yv))
        assert got == pin["seat"], (
            f"[{case['id']}] stored ({xv},{yv}) should seat at {pin['seat']}, got {got}.\n"
            f"  kills: {case['$kills']}")


def test_bbox_is_not_centred_in_any_fixture():
    """A GUARD ON THE FIXTURES THEMSELVES, not on the code.

    A centred bounding box makes the box term zero, and a vector whose term is zero cannot see
    the omission it exists to catch. The predecessor contract's nine y-invert vectors were all
    the identity frame, which is the same failure. If somebody later 'simplifies' a fixture into
    a centred one, this fails and says why.
    """
    for case in VECTORS["frame_basis_cases"]["cases"]:
        box = case["expect_bbox"]
        vis = case["expect_visual"]
        centred = (box["minC"] == (vis["cols"] - 1 - box["maxC"])
                   and box["minR"] == (vis["rows"] - 1 - box["maxR"]))
        assert not (centred and box["minC"] == 0 and box["minR"] == 0), (
            f"[{case['id']}] the bounding box is centred AND flush, so the box term is zero on "
            "both axes and this fixture cannot observe a missing box term. Replace it with a "
            "geometry whose offset pushes the circle off centre -- the offset is the only "
            "lever that works; padding the grid with spare rows does not, because the engine "
            "forces the circle onto (rows-1)/2.")


# ═══════════════════════════════════════════════════════════════════════════════
# S3  SCORING -- server versus oracle
# ═══════════════════════════════════════════════════════════════════════════════

_PCT_RE = re.compile(r"pct|percent|ratio|coverage", re.IGNORECASE)


def _walk_keys(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield f"{path}.{k}", k, v
            yield from _walk_keys(v, f"{path}.{k}")
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            yield from _walk_keys(v, f"{path}[{i}]")


def _score_a_toy_unit():
    """One real invocation of `score_candidates` on a tiny synthetic unit.

    Synthetic on purpose: these are STRUCTURAL invariants (no percentage, margin is a count,
    per-candidate meta rebuild), and they must hold for every input. The ORACLE COMPARISON --
    is the server's winner the right winner -- needs the map-pm lane's independent derivation
    and is reported as unscored, not faked with a fixture this file invented.
    """
    score = _require("score_candidates")
    meta = {"grid_cols": 9, "grid_rows": 9, "grid_start_x": 0, "grid_start_y": 0,
            "rotation": 0, "side": "front", "grid_y_invert": False,
            "phys_wafer_dia": 300, "phys_chip_x": 25, "phys_chip_y": 25,
            "phys_offset_x": 0, "phys_offset_y": 0, "phys_edge_margin": 3}
    # Deliberately ASYMMETRIC: the spec's theorem says the circle is invariant under all eight
    # frames, so only the occupied subset can break a tie. A symmetric footprint scores flat.
    cells = [(0, 0), (1, 0), (2, 0), (0, 1), (0, 2), (3, 0)]
    ref = list(cells)
    return score([{"map_id": "TOY", "meta": dict(meta), "cells": cells}], ref, dict(meta))


def test_scoring_emits_no_percentage_anywhere():
    """Measured, not stylistic: on an asymmetric 376-die mask a correctly-oriented candidate one
    cell off scored 94% and ranked BELOW three wrongly-oriented candidates at 98/97/95%. A
    coverage percentage provably inverts the ranking, so it must not exist to be rendered."""
    candidates, excluded, ruling, stats = _score_a_toy_unit()
    for blob, label in ((candidates, "candidates"), (ruling, "ruling"), (stats, "stats")):
        for path, key, _ in _walk_keys(blob):
            assert not _PCT_RE.search(str(key)), (
                f"a percentage-shaped key reached the scoring payload: {label}{path}. "
                "A number nobody ranks on today is a number somebody ranks on next quarter.")


def test_scoring_margin_is_a_die_count():
    candidates, _, _, _ = _score_a_toy_unit()
    agrees = [c["agreement"] for c in candidates]
    for i, c in enumerate(candidates):
        if c["margin"] is None:
            continue
        assert isinstance(c["margin"], int) and not isinstance(c["margin"], bool), (
            f"candidate {c['frame']} margin is {c['margin']!r}, not an integer die count")
        runner = max([a for j, a in enumerate(agrees) if j != i] or [0])
        assert c["margin"] == c["agreement"] - runner, (
            f"candidate {c['frame']} margin {c['margin']} != agreement {c['agreement']} minus "
            f"the best other agreement {runner}")


def test_scoring_rebuilds_a_full_meta_per_candidate():
    """THE PREMISE of section 2. One box with 8 transforms on top does not reproduce the
    cancellation between the y mirror and the offset sign flip, and production row `CORE_YINV`
    is measured to land (2,-1) off when that happens.

    Instrumented rather than reviewed, because the wrong implementation looks correct on every
    centred-box fixture.
    """
    import dt_map_derivation
    real = _require("source_meta_for_frame")
    calls = []

    def spy(target_meta, frame_text):
        calls.append(frame_text)
        return real(target_meta, frame_text)

    dt_map_derivation.source_meta_for_frame = spy
    # `map_alignment` bound the name at import; rebind there too or the spy never runs.
    import map_alignment
    saved = map_alignment.source_meta_for_frame
    map_alignment.source_meta_for_frame = spy
    try:
        _score_a_toy_unit()
    finally:
        map_alignment.source_meta_for_frame = saved
        dt_map_derivation.source_meta_for_frame = real

    frames = list(_require("CANDIDATE_FRAMES"))
    assert len(frames) == 8, f"the candidate set is no longer 8: {frames}"
    assert sorted(calls) == sorted(frames), (
        "the scorer did not rebuild a whole meta once per candidate.\n"
        f"  candidates: {frames}\n  rebuilds:   {calls}\n"
        "Deriving one bounding box and stacking transforms on it silently misplaces "
        "`CORE_YINV` by (2,-1), and looks correct on every centred-box fixture.")


def test_scoring_names_no_winner_when_nothing_discriminates():
    """The spec's theorem, as a refusal: the circle is invariant under all eight frames, so when
    no cell's membership varies between candidates, any winner is arbitrary. A forced first
    place is telling the operator the wrong thing is right."""
    score = _require("score_candidates")
    meta = {"grid_cols": 9, "grid_rows": 9, "grid_start_x": 0, "grid_start_y": 0,
            "rotation": 0, "side": "front", "grid_y_invert": False,
            "phys_wafer_dia": 300, "phys_chip_x": 25, "phys_chip_y": 25,
            "phys_offset_x": 0, "phys_offset_y": 0, "phys_edge_margin": 3}
    # A single cell at the centre of symmetry: every candidate places it identically, so the
    # membership vector is constant and NOTHING discriminates.
    centre = [(4, 4)]
    candidates, _, ruling, _ = score(
        [{"map_id": "SYM", "meta": dict(meta), "cells": centre}], centre, dict(meta))
    if all(c["discriminating"] == 0 for c in candidates):
        assert ruling.get("state") != "scored", (
            f"every candidate has discriminating == 0 and the ruling still named a winner: "
            f"{ruling}. When the occupied subset does not distinguish the frames, the correct "
            "answer is 'cannot tell', not a first place.")


def test_scoring_oracle_comparison_is_unscored():
    pytest.skip(
        "UNSCORED AXIS: scoring oracle comparison. Owner: the map-pm lane. The independently "
        "derived candidate enumeration and shift-solving fixture had not landed when this "
        "contract was written, so whether `score_candidates` picks the RIGHT winner and the "
        "RIGHT integer shift is not scored -- only that its output is structurally sound "
        "(no percentage, margin in dies, per-candidate meta rebuild, no forced winner). "
        "Drop the fixture in as contracts/map2_seam/scoring_oracle.json to close this.")


# ═══════════════════════════════════════════════════════════════════════════════
# S4  THE EXCEL FORM
# ═══════════════════════════════════════════════════════════════════════════════

_PARSER = (_REPO / "dev_env" / "ingestion_workspace" / "bonding_map" / "scripts"
           / "bonding_map_parser.py")


def test_ingestion_rename_has_one_spelling():
    """A DUPLICATE GUARD, not a round trip. The rename lives in a READ-ONLY ingestion script and
    is transcribed into `excel_io.js`; the day the two drift, the screen stays healthy and the
    values are wrong. `ingestion_workspace/` is read only -- this reads it and writes nothing.
    """
    if not _PARSER.exists():
        pytest.skip(f"UNSCORED: the ingestion parser is not at {_PARSER}")
    src = _PARSER.read_text(encoding="utf-8")
    expect = VECTORS["excel_form_cases"]["$invariants_pinned_now"][0]["expect"]
    for old, new in expect.items():
        assert re.search(rf"['\"]{re.escape(old)}['\"]\s*:\s*['\"]{re.escape(new)}['\"]", src), (
            f"the ingestion parser no longer renames '{old}' to '{new}'. "
            "`client2/src/map2/excel_io.js INGESTION_RENAME` transcribes this pair and must "
            "change with it -- the client harness scores the client half.")


def test_the_briefs_named_encoding_authority_is_wrong():
    """A FINDING, pinned so it is not re-discovered.

    The round brief names `bonding_map_parser.py` as the authoritative form encoding. It is not:
    it is a ~34-line pipeline shim that matches `.csv`/`.html`, delegates all matrix parsing to
    `server/parsers/html_topology_parser.py HTMLMatrixTableParser`, and renames two columns. The
    encoding is in the parser it delegates to. This asserts the delegation so that if the shim
    ever DOES grow an encoding, this fails and the contract gets re-pointed deliberately.
    """
    if not _PARSER.exists():
        pytest.skip(f"UNSCORED: the ingestion parser is not at {_PARSER}")
    src = _PARSER.read_text(encoding="utf-8")
    assert "HTMLMatrixTableParser" in src, (
        "bonding_map_parser.py no longer delegates to HTMLMatrixTableParser. If it grew its "
        "own encoding, the excel contract must be re-pointed at whichever file is now "
        "authoritative -- and the brief's claim would finally be true.")


def test_excel_round_trip_is_unscored():
    pytest.skip(
        "UNSCORED AXIS: excel form round trip against a real operator artefact. Owner: the "
        "excel_io lane. `dev_env/ingestion_workspace/bonding_map/archives/` is EMPTY on this "
        "box, so nothing here was round-tripped against a file an operator actually produced. "
        "A synthetic round trip proves the code is self-consistent -- which a re-implementation "
        "that copied the legacy defects would also be. Client-side structural assertions are "
        "in client_harness.mjs and are also PENDING.")


# ═══════════════════════════════════════════════════════════════════════════════
# S5  align_applied.origin
# ═══════════════════════════════════════════════════════════════════════════════

def test_align_origin_vocabulary_is_the_current_three():
    """Pins the CURRENT single-token behaviour so the approved three-way split has something to
    diff against -- and fires the moment the split lands, pointing at the client work it
    presupposes. That is the intended direction: a NAMED expected failure, never an anonymous
    permanent red.
    """
    got = sorted({_require("ALIGN_ORIGIN_IDENTITY"), _require("ALIGN_ORIGIN_DERIVED"),
                  _require("ALIGN_ORIGIN_UNRESOLVABLE")})
    want = sorted(VECTORS["align_origin_cases"]["current_vocabulary"]["expect"])
    consumers = VECTORS["align_origin_cases"]["client_consumers_fail_open"]
    assert got == want, (
        f"the server's align origin vocabulary changed: {got} (was {want}).\n"
        "🔴 THE CLIENT MUST CHANGE FIRST. Both client consumers are NEGATIVE LITERAL tests:\n"
        + "\n".join(f"    {s}" for s in consumers["$sites"])
        + "\nso a new token FAILS OPEN IN THE WRONG DIRECTION -- it is read as 'aligned' and "
        "the chip renders as corrected. " + consumers["$failure_scenario"])


def test_align_applied_payload_defaults_to_identity():
    """`align_applied_payload(None, None)` must still say `identity`. A None origin reaching the
    payload as None would make both client consumers take the 'aligned' branch, which is the
    same wrong-direction failure the split is being sequenced to avoid."""
    payload = _require("align_applied_payload")
    out = payload(None, None)
    assert out["origin"] == _require("ALIGN_ORIGIN_IDENTITY"), (
        f"align_applied_payload(None, None) produced origin={out['origin']!r}. Anything that is "
        "not the literal 'identity' is read by both client consumers as 'this overlay was "
        "aligned'.")


def test_align_origin_client_consumers_are_unscored():
    pytest.skip(
        "UNSCORED AXIS: align_applied.origin -- client consumers. Owner: the map-pm / client "
        "lane. Both consumers live in `client2/src/map_editor.js`, which is FROZEN by product "
        "owner ruling and which this contract may not edit. Reaching them needs either a module "
        "with heavy DOM state (impossible) or an assertion on source TEXT -- the technique that "
        "killed three harnesses this round. Re-typing the comparison inside the contract would "
        "score nothing: the copy would also pass `str(origin).lower() == 'none'`, which is what "
        "the invariant forbids. THE EXTRACTION IS WHAT MAKES THE AXIS TESTABLE, NOT THE TEST -- "
        "one exported pure predicate (e.g. `alignWasApplied(origin)`) closes it.")


# ═══════════════════════════════════════════════════════════════════════════════
# CONTRACT HYGIENE
# ═══════════════════════════════════════════════════════════════════════════════

_CONSUMED_GROUPS = {
    "orientation_agreement_cases", "orientation_divergence_cases", "orientation_census",
    "frame_basis_cases", "scoring_invariants", "excel_form_cases", "align_origin_cases",
    "geometry_declaration_cases",
}
_DECLARED_UNCONSUMED = {"unscored_axes"}


def test_every_vector_group_is_consumed_or_declared():
    """A vector nobody reads is worse than no vector: it looks like coverage. This is a SET
    comparison, not a count -- a group appearing while another disappears keeps the count."""
    groups = {k for k in VECTORS if not k.startswith("$")
              and k not in ("server_symbols", "client_symbols")}
    unknown = groups - _CONSUMED_GROUPS - _DECLARED_UNCONSUMED
    assert not unknown, (
        f"vector groups nobody scores: {sorted(unknown)}. Either wire them into this file and "
        "the client harness, or move them under `unscored_axes` with a reason.")
    missing = _CONSUMED_GROUPS - groups
    assert not missing, (
        f"this file scores groups that vectors.json no longer defines: {sorted(missing)}")


def test_every_case_answers_what_it_kills():
    """A vector both sides pass because they share the same wrong assumption is worth nothing.
    Every case must name the wrong implementation it rejects -- nine identity-frame vectors
    could not, and proved nothing for months."""
    naked = []
    for case in VECTORS["orientation_agreement_cases"]["cases"]:
        if not case.get("$kills"):
            naked.append(f"orientation_agreement_cases/{case['id']}")
    for case in VECTORS["frame_basis_cases"]["cases"]:
        if not case.get("$kills"):
            naked.append(f"frame_basis_cases/{case['id']}")
    for case in VECTORS["geometry_declaration_cases"]["cases"]:
        if not case.get("$kills"):
            naked.append(f"geometry_declaration_cases/{case['id']}")
    for case in VECTORS["orientation_divergence_cases"]["cases"]:
        if not (case.get("$failure_scenario") or case.get("$kills")):
            naked.append(f"orientation_divergence_cases/{case['id']}")
    assert not naked, (
        "cases with no `$kills` / `$failure_scenario`: " + ", ".join(naked)
        + "\nIf you cannot say which wrong implementation a case rejects, it is agreement, "
        "not discrimination.")


def test_no_case_carries_a_line_number_anchor():
    """Anchors slide. One extraction on 2026-07-29 moved 274 lines by +26 and staled the
    contract, CODE_MAP and three test messages at once. Point at function names."""
    bad = []
    for group in ("orientation_agreement_cases", "orientation_divergence_cases"):
        for case in VECTORS[group]["cases"]:
            why = case.get("$why", "")
            if re.search(r"\.(py|js|mjs):\d+", why):
                bad.append(f"{group}/{case['id']}")
    assert not bad, (
        f"`$why` fields carrying file:line anchors: {bad}. Name the function instead.")
