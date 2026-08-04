"""[D2] The orientation axis, and whether anyone declared it.

`map_overlay.orientation_declaration` is the ONE spelling of "is this map's orientation a
declaration". It is the twin of `geometry_declaration` on the phys axis and it shares that
function's vocabulary; the only addition is `indeterminate`, for the case the phys axis does
not have (a legal value that no writer had to look at a wafer to produce).

THE LOAD-BEARING TEST here is `test_no_evidence_values_are_the_readers_own_absent_defaults`.
Every other assertion in this file is downstream of one table of constants, and that table is
only true as long as it matches what the coordinate readers actually do with a meta that says
nothing. If a reader's absent-default ever changes and the table does not, this module keeps
passing while `indeterminate` starts pointing at the wrong value - the exact silent-divergence
class (I6) this declaration exists to close. So the table is not asserted against literals; it
is asserted against the readers themselves.

Nothing here touches the database or the transform path: layer (3) is pure by contract
(`docs/spec/MAP_ALIGNMENT_SPEC.md` section 0.2).
"""
import pytest

import map_overlay
from map_meta_registrar import synthesize_grid_meta


DECLARED = map_overlay.GEOMETRY_DECLARED
AUTO = map_overlay.GEOMETRY_AUTO_REGISTERED
ABSENT = map_overlay.GEOMETRY_ABSENT
UNPARSABLE = map_overlay.GEOMETRY_UNPARSABLE
INDET = map_overlay.ORIENTATION_INDETERMINATE

AXES = map_overlay.ORIENTATION_KEYS


def _meta(**kw):
    """A meta carrying ONLY what the test names. Absence is a case under test, so this
    helper must not helpfully fill the orientation keys in."""
    base = {"grid_cols": 6, "grid_rows": 6,
            "phys_wafer_dia": 300, "phys_chip_x": 2.5, "phys_chip_y": 2.5,
            "phys_offset_x": 0, "phys_offset_y": 0, "phys_edge_margin": 3}
    base.update(kw)
    return base


def _src(meta, axis):
    return map_overlay.orientation_declaration(meta)[axis]["source"]


def _val(meta, axis):
    return map_overlay.orientation_declaration(meta)[axis]["value"]


# ---------------------------------------------------------------------------
# The table of no-evidence values is the whole predicate. Score it against the readers.
# ---------------------------------------------------------------------------

def test_no_evidence_values_are_the_readers_own_absent_defaults():
    """The value a reader invents when the key is missing IS that axis's no-evidence value.

    That equality is the entire justification for `indeterminate`: a stored value equal to it
    is byte-identical downstream to a value nobody ever wrote, so no consumer can tell them
    apart. Asserting the table against literals would let the two drift; this asks the readers.
    """
    silent = {"grid_cols": 6, "grid_rows": 6}          # says nothing about orientation
    grid = map_overlay._grid_of(silent)
    from_readers = {
        "rotation": map_overlay._rotation_of(silent),
        "side": map_overlay._side_of(silent),
        "grid_y_invert": map_overlay._y_invert_of(silent),
        "grid_start_x": grid["start_x"],
        "grid_start_y": grid["start_y"],
    }
    table = {axis: d for axis, (_r, d, _s, _v) in map_overlay._ORIENTATION_READERS.items()}
    assert table == from_readers, (
        "the no-evidence table drifted from the readers - `indeterminate` now points at a "
        "value the readers do not actually produce from absence")


def test_every_axis_is_answered_and_only_the_five():
    d = map_overlay.orientation_declaration(_meta())
    assert set(d) == set(AXES) == {"rotation", "side", "grid_y_invert",
                                   "grid_start_x", "grid_start_y"}
    assert all(set(v) == {"value", "source"} for v in d.values()), (
        "the layer's contract is value AND provenance per axis, in the client's "
        "`physDeclaration` shape")


def test_axis_order_matches_frame_axes():
    """`frame_axes` already orders these five. A second order is a second spelling (I6)."""
    axes = map_overlay.frame_axes(_meta(rotation=90, side="back", grid_y_invert=True,
                                        grid_start_x=3, grid_start_y=4))
    decl = map_overlay.orientation_declaration(
        _meta(rotation=90, side="back", grid_y_invert=True, grid_start_x=3, grid_start_y=4))
    assert tuple(decl[a]["value"] for a in AXES) == axes[:5]


# ---------------------------------------------------------------------------
# absent
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("axis", AXES)
def test_missing_key_is_absent_and_still_reports_the_value_the_reader_will_use(axis):
    d = map_overlay.orientation_declaration(_meta())[axis]
    assert d["source"] == ABSENT
    assert d["value"] == map_overlay._ORIENTATION_READERS[axis][1], (
        "a refusing token still has to say what the coordinate path will do, or the caller "
        "has to re-derive it and we are back to two spellings")


@pytest.mark.parametrize("axis", AXES)
def test_explicit_null_and_blank_are_absent_not_unparsable(axis):
    assert _src(_meta(**{axis: None}), axis) == ABSENT
    assert _src(_meta(**{axis: "   "}), axis) == ABSENT


def test_none_meta_answers_absent_on_every_axis():
    d = map_overlay.orientation_declaration(None)
    assert {v["source"] for v in d.values()} == {ABSENT}


# ---------------------------------------------------------------------------
# indeterminate - the token the phys axis does not need
# ---------------------------------------------------------------------------

def test_the_canonical_row_is_indeterminate_on_three_axes_not_declared():
    """rotation 0 / front / no invert, unmarked. This is 516 of 668 production rows.

    Answering `declared` here is I4: a plausible default impersonating a declaration.
    Answering `absent` is false - the key exists and the transform uses its value.

    start is deliberately NOT in this set - see
    `test_start_provenance_comes_from_the_mark_alone`.
    """
    m = _meta(rotation=0, side="front", grid_y_invert=False,
              grid_start_x=1, grid_start_y=1)
    d = map_overlay.orientation_declaration(m)
    assert {a: d[a]["source"] for a in ("rotation", "side", "grid_y_invert")} == {
        "rotation": INDET, "side": INDET, "grid_y_invert": INDET}
    assert d["rotation"]["value"] == 0, "indeterminate still reports the value in force"


@pytest.mark.parametrize("value", [1, 0, 3, -8])
@pytest.mark.parametrize("axis", ["grid_start_x", "grid_start_y"])
def test_start_provenance_comes_from_the_mark_alone(axis, value):
    """[lead ruling 2026-08-05] On start, the VALUE never indicates provenance - only the mark.

    Rule N infers "nobody chose this" from equality with the reader's absent-default, and that
    inference is only available where the key CAN be absent. For start it never is (0 of 668
    production rows lack it), and the registrar writes the observed minimum rather than a
    constant, so no value is the registrar's signature even in principle. Marked ->
    `auto_registered`; unmarked -> `declared`, whatever the number.

    This is also what keeps the two implementations from inverting: a client whose absent-default
    is 0 and a server whose absent-default is 1 would disagree on 660 of 668 rows if either side
    ran a value test here.
    """
    assert _src(_meta(**{axis: value}), axis) == DECLARED
    marked = _meta(**{axis: value})
    marked["auto_registered"] = True
    assert _src(marked, axis) == AUTO


def test_indeterminate_never_applies_to_start():
    """The token is unreachable on those two axes. Stated as its own assertion because a
    future edit to the reader table could re-open it silently."""
    for m in (_meta(), _meta(grid_start_x=1, grid_start_y=1),
              _meta(grid_start_x=0, grid_start_y=0),
              synthesize_grid_meta(1, 1, 9, 9), synthesize_grid_meta(4, 7, 25, 19)):
        d = map_overlay.orientation_declaration(m)
        assert d["grid_start_x"]["source"] != INDET
        assert d["grid_start_y"]["source"] != INDET


def test_indeterminate_is_not_declared_and_not_absent():
    """The three-way distinction, stated as one assertion so folding it collapses this test."""
    stated = _meta(rotation=0)
    silent = _meta()
    real = _meta(rotation=90)
    assert _src(stated, "rotation") == INDET
    assert _src(silent, "rotation") == ABSENT
    assert _src(real, "rotation") == DECLARED
    assert len({_src(stated, "rotation"), _src(silent, "rotation"),
                _src(real, "rotation")}) == 3, (
        "before D2 these three were the same answer (0) - that collapse is the defect")


@pytest.mark.parametrize("axis,value", [
    ("rotation", 90), ("rotation", 180), ("rotation", 270),
    ("side", "back"), ("grid_y_invert", True),
    ("grid_start_x", 3), ("grid_start_y", 0),
])
def test_a_value_no_writer_produces_by_default_is_declared(axis, value):
    assert _src(_meta(**{axis: value}), axis) == DECLARED
    assert _val(_meta(**{axis: value}), axis) == value


def test_rotation_360_normalises_to_zero_and_is_therefore_indeterminate():
    """`_rotation_of` folds mod 360. A declaration function that skipped the fold would call
    360 `declared` while the transform runs it as 0 - a claim of evidence for a value that
    is not the value used."""
    assert map_overlay._rotation_of({"rotation": 360}) == 0
    d = map_overlay.orientation_declaration(_meta(rotation=360))["rotation"]
    assert (d["value"], d["source"]) == (0, INDET)


# ---------------------------------------------------------------------------
# unparsable - values the readers mis-read rather than reject
# ---------------------------------------------------------------------------

def test_rotation_off_the_quarter_turn_is_unparsable_because_the_engine_treats_it_as_zero():
    assert map_overlay._frame_phys_params(_meta(rotation=45)) == \
        map_overlay._frame_phys_params(_meta(rotation=0)), (
        "premise of this test: 45 is silently rot-0 in the phys params table")
    assert _src(_meta(rotation=45), "rotation") == UNPARSABLE


def test_side_with_wrong_case_is_unparsable_because_the_transform_only_matches_back():
    assert map_overlay._side_of(_meta(side="Back")) == "Back"
    assert map_overlay._frame_phys_params(_meta(side="Back")) == \
        map_overlay._frame_phys_params(_meta(side="front")), (
        "premise: 'Back' is silently front downstream")
    assert _src(_meta(side="Back"), "side") == UNPARSABLE


def test_y_invert_as_the_string_false_is_unparsable_not_false():
    """`_y_invert_of` is `bool(raw)`, so the string "false" reads as TRUE. A declaration
    function that echoed the reader would report `declared: False` for a row the transform
    mirrors."""
    assert map_overlay._y_invert_of({"grid_y_invert": "false"}) is True
    assert _src(_meta(grid_y_invert="false"), "grid_y_invert") == UNPARSABLE


def test_non_integral_start_is_unparsable():
    assert map_overlay._grid_of(_meta(grid_start_x="3.5")) is None
    assert _src(_meta(grid_start_x="3.5"), "grid_start_x") == UNPARSABLE


@pytest.mark.parametrize("raw,expect", [(0, False), (1, True), (True, True), (False, False)])
def test_y_invert_accepts_real_truth_values_only(raw, expect):
    d = map_overlay.orientation_declaration(_meta(grid_y_invert=raw))["grid_y_invert"]
    assert d["value"] is expect


# ---------------------------------------------------------------------------
# the mark - and the exact width of its authority
# ---------------------------------------------------------------------------

def test_the_registrars_own_output_declares_nothing_on_rotation_side_invert():
    """Score the real function, not a hand-copied shape. `synthesize_grid_meta` is what put
    320 of the 668 production rows on this axis."""
    m = synthesize_grid_meta(1, 1, 25, 19)
    d = map_overlay.orientation_declaration(m)
    assert {d[a]["source"] for a in ("rotation", "side", "grid_y_invert")} == {AUTO}


def test_the_mark_does_not_launder_a_start_the_registrar_measured():
    """The registrar writes start from the observed minimum, so a non-1 start on a marked row
    is its bbox scan, not somebody's declaration. Reading it as `declared` would promote a
    machine's observation of the data into a claim about the frame."""
    m = synthesize_grid_meta(4, 7, 25, 19)
    assert (m["grid_start_x"], m["grid_start_y"]) == (4, 7)
    d = map_overlay.orientation_declaration(m)
    assert d["grid_start_x"]["source"] == AUTO
    assert d["grid_start_y"]["source"] == AUTO
    assert d["grid_start_x"]["value"] == 4, "still reports what the transform will use"


def test_the_mark_cannot_explain_a_rotation_the_registrar_never_writes():
    """The editor carries the mark forward while letting the operator change rotation
    (`map_editor.js:6292`). `synthesize_grid_meta` only ever writes rotation 0, so a marked
    row saying 90 was written by something else - calling that `auto_registered` is false."""
    assert synthesize_grid_meta(1, 1, 9, 9)["rotation"] == 0
    m = synthesize_grid_meta(1, 1, 9, 9)
    m["rotation"] = 90
    m["side"] = "back"
    d = map_overlay.orientation_declaration(m)
    assert d["rotation"]["source"] == DECLARED
    assert d["side"]["source"] == DECLARED
    assert d["grid_y_invert"]["source"] == AUTO, "untouched axes keep the mark's explanation"


def test_a_mark_that_is_not_literally_true_is_not_a_mark():
    """Mirrors `geometry_declaration`: `is True`, not truthiness."""
    m = _meta(rotation=0)
    m["auto_registered"] = "yes"
    assert _src(m, "rotation") == INDET


# ---------------------------------------------------------------------------
# refusal - naming, not judging
# ---------------------------------------------------------------------------

def test_refusal_is_none_only_when_all_five_axes_are_declared():
    full = _meta(rotation=90, side="back", grid_y_invert=True,
                 grid_start_x=3, grid_start_y=4)
    assert map_overlay.orientation_refusal(full) is None
    for axis in AXES:
        weakened = dict(full)
        weakened.pop(axis)
        assert map_overlay.orientation_refusal(weakened) is not None, (
            "dropping %s must be visible in the refusal" % axis)


def test_refusal_names_the_axis_so_the_operator_knows_what_to_fix():
    why = map_overlay.orientation_refusal(
        _meta(rotation=0, side="back", grid_y_invert=True, grid_start_x=3, grid_start_y=4))
    assert why is not None
    assert "회전" in why
    assert "면" not in why, "a declared axis must not appear in the refusal"


def test_refusal_covers_every_token_it_can_receive():
    """A missing entry in the text table would be a KeyError at the moment of refusal - the
    worst possible time for it, since refusal is the failure path."""
    for token in (AUTO, ABSENT, UNPARSABLE, INDET):
        assert token in map_overlay._ORIENTATION_REFUSAL_TEXT


def test_refusal_does_not_judge_it_only_names():
    """Every axis the declaration calls non-declared, and only those, appear in the text."""
    m = _meta(rotation=45, side="back", grid_start_x=3, grid_start_y=4)   # y_invert absent
    d = map_overlay.orientation_declaration(m)
    why = map_overlay.orientation_refusal(m)
    for axis, info in d.items():
        label = map_overlay._ORIENTATION_AXIS_LABEL[axis]
        assert (label in why) == (info["source"] != DECLARED), axis


# ---------------------------------------------------------------------------
# the vocabulary is ONE vocabulary (I6)
# ---------------------------------------------------------------------------

def test_orientation_reuses_the_phys_token_strings_verbatim():
    """Not equal-looking constants - the same objects. A second spelling of "declared" is the
    defect class this whole round is about."""
    assert map_overlay.GEOMETRY_DECLARED == "declared"
    assert map_overlay.GEOMETRY_AUTO_REGISTERED == "auto_registered"
    assert map_overlay.GEOMETRY_ABSENT == "absent"
    assert map_overlay.GEOMETRY_UNPARSABLE == "unparsable"
    assert map_overlay.ORIENTATION_INDETERMINATE == "indeterminate"
    produced = set()
    for m in (_meta(), _meta(rotation=0), _meta(rotation=90), _meta(rotation=45),
              synthesize_grid_meta(1, 1, 9, 9)):
        produced |= {v["source"] for v in map_overlay.orientation_declaration(m).values()}
    assert produced <= {DECLARED, AUTO, ABSENT, UNPARSABLE, INDET}, (
        "a sixth token appeared - the vocabulary is closed")


def test_declaration_is_pure_and_does_not_mutate_its_input():
    m = _meta(rotation=90)
    before = dict(m)
    map_overlay.orientation_declaration(m)
    map_overlay.orientation_refusal(m)
    assert m == before


def test_nothing_on_the_coordinate_path_calls_the_refusal_yet():
    """Stage A builds the predicate and measures; it does NOT move behaviour. If this fails,
    someone wired the refusal in without the blast-radius number that gates it."""
    import inspect
    for fn in (map_overlay.make_frame_transform, map_overlay.resolve_align,
               map_overlay.resolve_map_transform, map_overlay.frame_axes):
        src = inspect.getsource(fn)
        assert "orientation_refusal" not in src and "orientation_declaration" not in src, (
            "%s now consults the orientation declaration - that is a stage B change and it "
            "needs its blast radius measured first" % fn.__name__)
