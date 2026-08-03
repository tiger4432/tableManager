"""BLANK PREDICATE -- the SERVER half of the seam, scored against the shared vectors.

The file being scored is `contracts/blank_predicate/vectors.json`. Nothing here hardcodes an
expected answer: every verdict comes out of that file, so deleting a case removes coverage
LOUDLY (`test_every_contract_case_is_consumed`).

    conda run -n assy_manager python -m pytest contracts/blank_predicate/ -q -rs

`-rs` IS PART OF THE COMMAND. One axis (the Postgres dialect) is an opt-in skip and one is a
named pending symbol. Bare `-q` reports "N skipped", which says something is unscored but not
what, whose, or what it blocks. `-rs` prints the reasons, which carry all three.

HOW IT REACHES THE DEFAULT SUITE
    `server/tests/test_blank_predicate_contract.py` re-exports every test here -- same shim
    shape and same reason as map_seam and config_resolve_report: `testpaths` is ignored
    whenever paths are given on the command line, and every documented command in this repo
    passes `server/tests/` explicitly.

WHAT THIS FILE SCORES AND WHAT IT REFUSES TO RE-TYPE
    The two spellings are `crud.is_blank_value` and `crud.blank_sql_condition`. This file never
    re-writes either comparison: the SQL half is exercised by BUILDING A REAL FILTER through
    `main.get_column_filter_condition` and running it against a real row. A hand-typed copy of
    `col IS NULL OR col = ''` in a test scores nothing -- it would pass against an
    implementation that had drifted, because the copy drifts with the author, not with the code.

WHY THE ROUND TRIP IS THE POINT
    Each half is correct on its own. The 2026-07-29 instrumentation round lost 20 keystrokes to
    exactly that shape: server and client were each internally consistent and nobody had run the
    two together. `test_round_trip_through_the_write_funnel` is the assertion that cannot be
    satisfied by a coincidence in one half.

WHAT THIS FILE DOES NOT DO
    It does not decide. Where the two sides disagree the disagreement is RECORDED
    (`known_defects`, `declared_divergences`) with both answers and reported to the Lead PM.
    Nothing here edits an implementation and nothing here calls one of them wrong.
"""
import ast
import json
import os
import pathlib
import sys
import unicodedata

import pytest

_HERE = pathlib.Path(__file__).resolve().parent
_ROOT = _HERE.parents[1]
_SERVER = _ROOT / "server"

# [Isolation] Same pin, for the same reason, as server/tests/conftest.py: with DATABASE_URL
# unset, `database.py` resolves to DEFAULT_PG_URL -- the LIVE production database. Importing
# `crud` only builds a lazy engine, so nothing connects, but a contract that leaves a
# production URL configured in the process is one edit away from using it. Under the shim
# conftest has already set exactly this value, so the assignment is idempotent; standalone it
# is the only thing standing between this file and production.
os.environ["DATABASE_URL"] = os.environ.get("ASSY_TEST_DATABASE_URL", "sqlite:///:memory:")

if str(_SERVER) not in sys.path:
    sys.path.insert(0, str(_SERVER))

from database import crud, models, schemas          # noqa: E402
from database.database import Base                  # noqa: E402

VECTORS = json.loads((_HERE / "vectors.json").read_text(encoding="utf-8"))
CASES = VECTORS["corpus"]["cases"]
SYMBOLS = VECTORS["server_symbols"]
DEFECTS = VECTORS["known_defects"]
DIVERGENCES = VECTORS["declared_divergences"]

# Table name carries a prefix that cannot exist in the user's gitignored table_config. The
# `bonding_log` trap is on record: a collision lets import-time init pin a real schema, and
# then the contract is scored against production's column set instead of its own.
PROBE_TABLE = "bpx_blank_probe"
PROBE_TABLES = {
    PROBE_TABLE: {
        "business_key": "probe_key",
        "column_types": {"probe_key": "string", "txt": "string", "num": "number"},
    }
}

_CONSUMED = set()


def _unregister(table_names):
    """Take scratch tables back out of the PROCESS-WIDE registries.

    `models.init_dynamic_models` writes into `models.DYNAMIC_TABLES` and `Base.metadata`, both
    of which outlive the fixture and the test file. Restoring only `crud.TABLE_CONFIG` is not
    enough, and this is not theoretical: leaving `bpx_*` behind made
    `test_config_reload_integrity.py::test_h3_cross_directory_replace_applies_physical_alter`
    fail in the full-suite ORDER while both files passed alone -- measured 2026-07-31. A
    contract that costs an unrelated suite a red is a contract that gets deleted.
    """
    for name in table_names:
        models.DYNAMIC_TABLES.pop(name, None)
        tbl = Base.metadata.tables.get(name)
        if tbl is not None:
            Base.metadata.remove(tbl)


# ---------------------------------------------------------------------------
# Decoding the corpus. Inputs are codepoint arrays on purpose -- see vectors.json.
# ---------------------------------------------------------------------------

def _decode(spec):
    """A vectors.json value spec -> the Python object it denotes."""
    if spec is None:
        return None
    kind = spec["type"]
    if kind == "null":
        return None
    if kind == "text":
        return "".join(chr(cp) for cp in spec["cp"])
    if kind == "number":
        return float(spec["value"])
    raise AssertionError(f"unknown value spec type {kind!r} in vectors.json")


def _show(v):
    """A console-safe rendering of a corpus value.

    Every non-printing or non-ASCII character comes out as U+XXXX. Two reasons, both measured:
    a raw U+3000 in a failure message is indistinguishable from a space in a terminal, and the
    console on this machine is CP949 -- a character it cannot encode takes the WHOLE LINE with
    it, so the one assertion the reader needs is the one that vanishes.
    """
    if v is None:
        return "NULL"
    if isinstance(v, float):
        return f"float({v!r})"
    out = []
    for ch in v:
        if ch.isprintable() and ch.isascii():
            out.append(ch)
        else:
            try:
                name = unicodedata.name(ch)
            except ValueError:
                name = "?"
            out.append(f"<U+{ord(ch):04X} {name}>")
    return "'" + "".join(out) + "'"


def _case(cid):
    for c in CASES:
        if c["id"] == cid:
            return c
    raise AssertionError(f"no corpus case named {cid!r}")


def _consume(cid):
    _CONSUMED.add(cid)


def _pin_for(cid):
    """The `known_defects` entry that stands in for the contract value on this case, if any."""
    for name, d in DEFECTS.items():
        if name == "$comment":
            continue
        if cid in (d.get("cases") or []):
            return dict(d, **{"$id": name})
    return None


def _text_cases():
    for c in CASES:
        if c["input"]["type"] in ("text", "null"):
            yield c


# ---------------------------------------------------------------------------
# A real table, a real write funnel, a real filter builder.
# ---------------------------------------------------------------------------

@pytest.fixture()
def probe_db():
    """A scratch table on an isolated in-memory SQLite, plus the production write funnel.

    Deliberately NOT reusing conftest's `db_session`: this module must score identically when
    run standalone (`pytest contracts/blank_predicate/`) and under the shim, and a fixture that
    only exists in one of those two modes is a contract that is quietly weaker in the other.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    saved = dict(crud.TABLE_CONFIG)
    models.init_dynamic_models(PROBE_TABLES)
    crud.TABLE_CONFIG.update(PROBE_TABLES)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
        crud.TABLE_CONFIG.clear()
        crud.TABLE_CONFIG.update(saved)
        _unregister(PROBE_TABLES)


def _model():
    m = models.DYNAMIC_TABLES.get(PROBE_TABLE)
    assert m is not None, f"{PROBE_TABLE} was not registered by models.init_dynamic_models"
    return m


def _write_through_funnel(db, key, column, value):
    """One row through `crud.apply_batch_updates` -- the funnel every write path converges on."""
    crud.apply_batch_updates(db, PROBE_TABLE, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates={"probe_key": key, column: value},
                                  source_name="contract", updated_by="contract-keeper")
    ], silent=True))
    db.commit()


def _write_bypassing_funnel(db, key, column, value):
    """A row written STRAIGHT to the column, skipping `cast_value_by_type`.

    This is not a hypothetical: it is what a legacy row, a snapshot restore
    (`server/scripts/dev_env/snapshot_db.py` copies values verbatim) or any future bulk loader
    looks like from the database's point of view. INV-BP-X1 is scored on these rows.
    """
    m = _model()
    row = m(row_id=f"bypass_{key}", probe_key=key, business_key_val=key)
    setattr(row, column, value)
    db.add(row)
    db.commit()
    return row


def _stored(db, key, column):
    m = _model()
    row = db.query(m).filter(m.probe_key == key).first()
    assert row is not None, f"the write for {key!r} did not produce a row"
    return getattr(row, column)


def _filter_finds(db, column, f_info, key):
    """Run a REAL AG-Grid filter through the production builder and say whether it found `key`.

    `main.get_column_filter_condition` is the function the operator's filter actually reaches.
    Building the condition here rather than re-typing `col IS NULL OR col = ''` is the whole
    difference between scoring the implementation and scoring a copy of it.
    """
    import main
    m = _model()
    cond = main.get_column_filter_condition(m, column, f_info)
    assert cond is not None, (
        f"the production filter builder returned NO condition for {f_info!r} on column "
        f"{column!r}. An unfiltered page would come back looking filtered.")
    hits = {r[0] for r in db.query(m.probe_key).filter(cond).all()}
    return key in hits


# ---------------------------------------------------------------------------
# The whitespace class, derived rather than transcribed
# ---------------------------------------------------------------------------

def test_the_whitespace_class_is_derived_and_still_29_codepoints():
    """INV foundation. `whitespace_class` in vectors.json is a DERIVED fact, re-derived here.

    If a Python upgrade changes `str.isspace()`, this fails BEFORE any spelling comparison does,
    and the failure names the delta -- which is the difference between "the contract moved" and
    "someone broke the predicate".
    """
    live = [cp for cp in range(0x110000) if chr(cp).strip() == ""]
    declared = VECTORS["whitespace_class"]["codepoints"]
    assert len(live) == VECTORS["whitespace_class"]["expected_size"], (
        f"str.strip() now removes {len(live)} codepoints, vectors.json declares "
        f"{VECTORS['whitespace_class']['expected_size']}")
    assert live == declared, (
        "the derived whitespace class no longer matches vectors.json.\n"
        f"  only in the interpreter: {['U+%04X' % c for c in sorted(set(live) - set(declared))]}\n"
        f"  only in vectors.json   : {['U+%04X' % c for c in sorted(set(declared) - set(live))]}")


def test_the_separators_python_strips_are_not_unicode_whitespace():
    """Why U+001C..U+001F are in the corpus, asserted rather than left in a comment.

    Anyone writing a SQL character class "covering Unicode whitespace" produces a set that is
    missing exactly these four, and every test seeded with spaces and tabs passes anyway.
    """
    for cp in (0x1C, 0x1D, 0x1E, 0x1F):
        ch = chr(cp)
        assert ch.strip() == "", f"U+{cp:04X} is no longer stripped by Python"
        assert not unicodedata.category(ch).startswith("Z"), (
            f"U+{cp:04X} is now a Unicode separator; the argument for this case has changed")


# ---------------------------------------------------------------------------
# The named symbols
# ---------------------------------------------------------------------------

def test_every_declared_server_symbol_exists_or_is_declared_pending():
    """The names are part of the contract. A rename must be loud, not quiet.

    `client2/tests/split_registry_harness.mjs` threw at its extraction step for weeks after five
    symbols were renamed, comparing nothing, and nobody noticed. That is what this prevents.
    """
    missing = []
    for role, meta in SYMBOLS.items():
        if role == "$comment":
            continue
        if meta.get("status") == "pending":
            continue
        mod_path = _ROOT / meta["file"]
        assert mod_path.exists(), f"{role}: {meta['file']} does not exist"
        tree = ast.parse(mod_path.read_text(encoding="utf-8"))
        names = {n.name for n in ast.walk(tree)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        if meta["fn"] not in names:
            missing.append(f"{role}: {meta['file']} defines no `{meta['fn']}`")
    assert not missing, (
        "declared `live` symbols are gone. Either they were renamed (re-point vectors.json) or "
        "the extraction was reverted (the seam is unscored either way):\n  " + "\n  ".join(missing))


def test_pending_symbols_are_owned():
    """A pending axis is deliberately quiet, and that is only safe while it is OWNED."""
    for role, meta in SYMBOLS.items():
        if role == "$comment" or meta.get("status") != "pending":
            continue
        assert meta.get("$owner") and meta.get("$blocks"), (
            f"`{role}` is pending without an owner and a blocked-invariant list. An anonymous "
            "pending axis is a hole with better manners.")


# ---------------------------------------------------------------------------
# Axis E -- the Python spelling
# ---------------------------------------------------------------------------

def test_python_predicate_scores_the_corpus():
    """INV-BP-E1/E2/E3, Python half. `crud.is_blank_value` against the contract verdict."""
    wrong = []
    for c in CASES:
        _consume(c["id"])
        v = _decode(c["input"])
        got = crud.is_blank_value(v)
        if got != c["blank"]:
            wrong.append(f"{c['id']:26} input={_show(v):46} contract={c['blank']} "
                         f"is_blank_value={got}")
    assert not wrong, (
        "the PYTHON spelling disagrees with the contract:\n  " + "\n  ".join(wrong)
        + "\n\nThe expected answers are sourced in vectors.json `$blank_source`. If the contract "
          "is what changed, take it to the Lead PM -- do not edit vectors to make this pass.")


def test_python_render_scores_the_corpus():
    """INV-BP-R1/R2, Python half. `crud.clean_str_value` against the contract's canonical text.

    Cases whose `render` is null are DECLARED DIVERGENCES and are scored separately -- see
    `test_declared_divergences_still_diverge_exactly_as_recorded`.
    """
    wrong = []
    for c in CASES:
        _consume(c["id"])
        if c["render"] is None:
            continue
        v = _decode(c["input"])
        want = _decode(c["render"])
        got = crud.clean_str_value(v)
        if got != want:
            wrong.append(f"{c['id']:26} input={_show(v):46} contract={_show(want):14} "
                         f"clean_str_value={_show(got)}")
    assert not wrong, (
        "the PYTHON render disagrees with the contract:\n  " + "\n  ".join(wrong))


def test_python_blank_and_render_are_coupled():
    """INV-BP-R1. `blank(v)` iff `render(v) == ''`, on the Python side, for every case.

    This is the invariant that needs no ruling about trailing whitespace, and it kills the
    natural half-fix: adding a trim to the emptiness test and leaving the value path untrimmed.
    A cell would then be counted as unresolved by the filter and painted as non-empty in the
    grid -- the same row giving two answers about itself.
    """
    broken = []
    for c in CASES:
        _consume(c["id"])
        v = _decode(c["input"])
        if crud.is_blank_value(v) != (crud.clean_str_value(v) == ""):
            broken.append(f"{c['id']} input={_show(v)}")
    assert not broken, (
        "blank() and render() have come uncoupled on the Python side for:\n  "
        + "\n  ".join(broken))


# ---------------------------------------------------------------------------
# Axis W -- the write boundary
# ---------------------------------------------------------------------------

def test_the_write_boundary_removes_every_divergent_input():
    """INV-BP-W1. The 2026-07-31 user ruling, scored as a POST-CONDITION.

    The ruling was "block a value like a bare tab from being stored", not "normalize it" and not
    "refuse it" -- so this asserts what must be TRUE OF STORAGE afterwards and leaves the
    mechanism alone. `stored_as` in vectors.json is that post-condition.
    """
    wrong = []
    for c in CASES:
        _consume(c["id"])
        v = _decode(c["input"])
        col_type = "number" if c["input"]["type"] == "number" else "string"
        try:
            got = crud.cast_value_by_type(v, col_type, "txt")
        except ValueError as e:
            got = f"REFUSED({e})"
        pin = _pin_for(c["id"])
        if pin is not None:
            # A NAMED known defect stands in for the contract value on this case, and the
            # substitution is checked in both directions by
            # `test_known_defects_are_named_owned_and_not_self_satisfying`.
            assert str(got).startswith(pin["actual_prefix"]), (
                f"known defect {pin['$id']} ({pin['title']}) no longer reproduces.\n"
                f"  case            : {c['id']}\n"
                f"  recorded actual : starts with {pin['actual_prefix']!r}\n"
                f"  measured actual : {got!r}\n"
                "If the defect was FIXED, delete the entry from vectors.json and let the "
                "contract value stand -- this pin has stopped asserting anything. If it "
                "changed shape, that is louder and needs the Lead PM.")
            continue
        want = _decode(c["stored_as"])
        if got != want:
            wrong.append(f"{c['id']:26} input={_show(v):46} contract_stores={_show(want):14} "
                         f"boundary_produced={_show(got) if not isinstance(got, str) or not got.startswith('REFUSED') else got}")
    assert not wrong, (
        "the write boundary does not leave storage in the state the contract requires:\n  "
        + "\n  ".join(wrong)
        + "\n\nEvery row here is an input that can still reach storage in a form the two "
          "spellings answer differently about. That is the seam re-opening.")


def test_no_storable_value_can_make_the_two_spellings_disagree():
    """INV-BP-W1, stated the way it actually protects the seam.

    Derived rather than enumerated: take every corpus input, push it through the real boundary,
    and assert the RESULT is in the set the two spellings agree on. This is the sentence
    `blank_sql_condition`'s docstring relies on ("only correct because normalize_stored_text
    makes storage canonical"), turned into a check instead of a claim.
    """
    bad = []
    for c in CASES:
        _consume(c["id"])
        if c["input"]["type"] == "number":
            continue                    # numbers are not text; the SQL blank arm is IS NULL
        stored = crud.cast_value_by_type(_decode(c["input"]), "string", "txt")
        # The agreeing set for `col IS NULL OR col = ''` is exactly {None, ""} plus anything
        # `clean_str_value` also calls non-blank. A stored value is safe iff it is None, "",
        # or non-blank to Python.
        safe = stored is None or stored == "" or not crud.is_blank_value(stored)
        if not safe:
            bad.append(f"{c['id']:26} input={_show(_decode(c['input'])):46} "
                       f"stored={_show(stored)} -- Python calls it blank, SQL will not")
    assert not bad, (
        "a value survives the write boundary in a form the two spellings answer differently "
        "about:\n  " + "\n  ".join(bad))


# ---------------------------------------------------------------------------
# Axis E+W -- the round trip, through the real funnel and the real filter builder
# ---------------------------------------------------------------------------

def test_round_trip_through_the_write_funnel(probe_db):
    """INV-BP-W2 + INV-BP-E1/E2. THE assertion this contract exists for.

    Write each corpus input through `crud.apply_batch_updates`, then ask the production AG-Grid
    filter builder for `blank` and compare its answer with `crud.is_blank_value` on the value
    that actually landed in the column. Neither half can satisfy this by itself.
    """
    db = probe_db
    disagreements = []
    for c in _text_cases():
        _consume(c["id"])
        key = f"rt_{c['id']}"
        _write_through_funnel(db, key, "txt", _decode(c["input"]))
        stored = _stored(db, key, "txt")

        py = crud.is_blank_value(stored)
        sql = _filter_finds(db, "txt", {"type": "blank"}, key)
        if py != sql:
            disagreements.append(
                f"{c['id']:26} input={_show(_decode(c['input'])):46} stored={_show(stored):14} "
                f"is_blank_value={py} blank_filter_found={sql}")
        # And the contract's own verdict for the input must survive the trip.
        if py != c["blank"]:
            disagreements.append(
                f"{c['id']:26} input={_show(_decode(c['input'])):46} stored={_show(stored):14} "
                f"contract_blank={c['blank']} after_round_trip={py}")

    assert not disagreements, (
        "the two spellings answered differently about a row written through the real funnel:\n  "
        + "\n  ".join(disagreements)
        + "\n\nA row the grid paints as the unresolved label is missing from a search for it, "
          "or the reverse. Report both answers to the Lead PM -- do not pick one here.")


def test_a_search_for_what_python_renders_finds_the_row(probe_db):
    """INV-BP-R2. The user-facing form of the render axis.

    `equals` is the axis that bites: `contains` would match 'A' inside 'A\\t' and hide the
    divergence entirely. The operator types what the grid shows; the row must come back.
    """
    db = probe_db
    misses = []
    for c in _text_cases():
        _consume(c["id"])
        if c["render"] is None or c["blank"]:
            continue                    # blank rows are the `blank` filter's axis, above
        key = f"rd_{c['id']}"
        _write_through_funnel(db, key, "txt", _decode(c["input"]))
        needle = _decode(c["render"])
        found = _filter_finds(db, "txt", {"type": "equals", "filter": needle}, key)
        if not found:
            misses.append(f"{c['id']:26} input={_show(_decode(c['input'])):46} "
                          f"searched_for={_show(needle):14} stored={_show(_stored(db, key, 'txt'))}")
    assert not misses, (
        "a search for the text the contract says the cell renders did NOT find the row:\n  "
        + "\n  ".join(misses)
        + "\n\nThis is the silent under-report in its user-facing form.")


def test_bypass_rows_diverge_exactly_as_recorded(probe_db):
    """INV-BP-X1. What the storage invariant is holding back, with a number on it.

    These rows skip `cast_value_by_type` -- which is what a legacy row, a `snapshot_db.py`
    restore, or any future bulk loader looks like to the database. The SQL spelling is short
    ONLY because storage is canonical; this measures the size of that dependency instead of
    trusting it.

    It is deliberately red IN THE OTHER DIRECTION if the disagreement ever narrows: a trim
    quietly added to the SQL side would mean the two halves are no longer the pair vectors.json
    describes, and that has to be a decision, not a drift.
    """
    db = probe_db
    expected_divergent, actually_divergent = [], []
    for c in _text_cases():
        _consume(c["id"])
        raw = _decode(c["input"])
        if raw is None:
            continue
        key = f"bp_{c['id']}"
        _write_bypassing_funnel(db, key, "txt", raw)
        py = crud.is_blank_value(raw)
        sql = _filter_finds(db, "txt", {"type": "blank"}, key)
        # The recorded expectation: the pair disagrees exactly on the inputs the boundary
        # exists to remove -- blank to Python, and not NULL/'' as far as SQL is concerned.
        should_diverge = py and raw != ""
        if should_diverge:
            expected_divergent.append(c["id"])
        if py != sql:
            actually_divergent.append(c["id"])

    assert actually_divergent == expected_divergent, (
        "the bypass exposure changed shape.\n"
        f"  recorded divergent: {expected_divergent}\n"
        f"  measured divergent: {actually_divergent}\n"
        "If the measured set SHRANK, one of the two spellings was changed unilaterally and this "
        "contract no longer describes the pair. If it GREW, a new input class reaches storage "
        "unnormalized. Both are Lead PM decisions.")

    print(f"\n  DECLARED DIVERGENCE INV-BP-X1 -- {len(expected_divergent)} of "
          f"{len(list(_text_cases()))} corpus inputs answer differently when they BYPASS the "
          f"write boundary: {expected_divergent}")


def test_null_is_blank_and_never_unknown(probe_db):
    """INV-BP-E2, on its own, because it is the largest possible under-report.

    `_resolve_one` case (1) arrives as NULL. In SQL three-valued logic `btrim(c) = ''` on NULL
    is UNKNOWN, which a WHERE clause treats as not-matched -- so a spelling that forgets the
    NULL arm loses EVERY unmatched row from a blank search while passing any test seeded with
    non-NULL rows.
    """
    db = probe_db
    _consume("null")
    key = "nul_probe"
    _write_through_funnel(db, key, "txt", None)
    assert _stored(db, key, "txt") is None
    assert crud.is_blank_value(None) is True
    assert _filter_finds(db, "txt", {"type": "blank"}, key), (
        "the production blank filter did not return a NULL row. Every row where the join found "
        "no match is NULL, so this is the whole unmatched population going missing from a "
        "search for the unresolved label.")
    assert not _filter_finds(db, "txt", {"type": "notBlank"}, key), (
        "a NULL row came back from `notBlank`. NULL leaked through the negation -- the exact "
        "reason `not_blank_sql_condition` is spelled out rather than written as `~blank(...)`.")


# ---------------------------------------------------------------------------
# The resolution seam -- `_resolve_one` (Python) against `resolved_expression` (SQL)
# ---------------------------------------------------------------------------

VJ_LEFT, VJ_RIGHT = "bpx_vj_left", "bpx_vj_right"
VJ_TABLES = {
    VJ_LEFT: {"business_key": "lk",
              "column_types": {"lk": "string", "jk": "string", "wafer_id": "string"}},
    VJ_RIGHT: {"business_key": "rk",
               # `slot_no` is the NUMERIC expose axis (board item N7, 2026-08-02). It did
               # not exist when the numeric read path shipped broken - "0 numeric expose
               # columns in this environment" - so nothing here went red. Now it exists.
               "column_types": {"rk": "string", "jk": "string", "wafer_id": "string",
                                "fab_site": "string", "slot_no": "number"}},
}
VJ_DECL = {"bpx_rule": {"left_table": VJ_LEFT, "right_table": VJ_RIGHT,
                        "join_key": [{"left": "jk", "right": "jk"}],
                        "expose": ["fab_site", "slot_no"]}}


@pytest.fixture()
def vj_db(tmp_path, monkeypatch):
    """A verified one-rule join on an isolated SQLite, so both halves can be run on one corpus.

    `unique_index_covering` is stood in for, exactly as `test_virtual_column_search.py` records:
    it answers through `pg_index` and returns None on any non-Postgres dialect, and "unknown
    means refuse" would leave zero verified rules and every assertion below passing vacuously.
    """
    import virtual_join_config as vjc
    import virtual_join_executor as vjx
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    engine = create_engine("sqlite:///:memory:",
                           connect_args={"check_same_thread": False}, poolclass=StaticPool)
    saved = dict(crud.TABLE_CONFIG)
    models.init_dynamic_models(VJ_TABLES)
    crud.TABLE_CONFIG.update(VJ_TABLES)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()

    p = tmp_path / "virtual_join_rules.json"
    p.write_text(json.dumps(VJ_DECL), encoding="utf-8")
    monkeypatch.setattr(vjc, "VIRTUAL_JOIN_RULES_PATH", str(p))
    monkeypatch.setattr(vjc, "unique_index_covering",
                        lambda db, table, columns: "uq_stub" if table == VJ_RIGHT else None)
    vjx.reset_cache()
    try:
        rules = vjx.rules_for(session, VJ_LEFT)
        assert rules, (
            "no verified rule -- every assertion in this fixture would pass vacuously. The "
            "approval stand-in stopped working; do not read a green run from this state.")
        yield session, rules[0]["unresolved_label"]
    finally:
        session.close()
        engine.dispose()
        vjx.reset_cache()
        crud.TABLE_CONFIG.clear()
        crud.TABLE_CONFIG.update(saved)
        _unregister(VJ_TABLES)


def _vj_seed(db, cid, right_value, through_funnel, column="fab_site"):
    """One left row and its matching right row, with `column` carrying a corpus value."""
    crud.apply_batch_updates(db, VJ_LEFT, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates={"lk": cid, "jk": cid},
                                  source_name="contract", updated_by="contract-keeper")
    ], silent=True))
    if through_funnel:
        crud.apply_batch_updates(db, VJ_RIGHT, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates={"rk": cid, "jk": cid, column: right_value},
                                      source_name="contract", updated_by="contract-keeper")
        ], silent=True))
    else:
        m = models.DYNAMIC_TABLES[VJ_RIGHT]
        row = m(row_id=f"raw_{cid}", rk=cid, jk=cid, business_key_val=cid)
        setattr(row, column, right_value)
        db.add(row)
    db.commit()


def _vj_python(db, cid, column="fab_site"):
    """What `virtual_join_executor.attach` puts in the payload cell -- the value the grid paints."""
    import virtual_join_executor as vjx
    m = models.DYNAMIC_TABLES[VJ_LEFT]
    row = db.query(m).filter(m.lk == cid).first()
    payload = [{"row_id": row.row_id, "data": {}}]
    vjx.attach(db, VJ_LEFT, payload)
    cell = payload[0]["data"].get(column)
    return cell["value"] if isinstance(cell, dict) else None


def _vj_sql(db, cid, column="fab_site"):
    """What `resolved_expression` evaluates to for the same row -- the value SEARCH compares."""
    import virtual_join_executor as vjx
    m = models.DYNAMIC_TABLES[VJ_LEFT]
    q = db.query(m.row_id)
    q, expr, _label = vjx.resolved_expression(db, m, VJ_LEFT, column, q)
    assert expr is not None, "resolved_expression produced no expression for an exposed column"
    return q.with_entities(expr).filter(m.lk == cid).scalar()


def test_the_two_resolutions_agree_on_every_value_the_boundary_can_store(vj_db):
    """INV-BP-E1 at the place the operator actually meets it.

    `_resolve_one` decides the cell in Python; `resolved_expression` decides the same cell in
    SQL so it can go in a WHERE clause. This runs the corpus through BOTH and compares the
    resolved value -- which is the round trip. Neither half can pass this alone.
    """
    db, label = vj_db
    disagreements = []
    for c in _text_cases():
        _consume(c["id"])
        cid = f"vj_{c['id']}"
        _vj_seed(db, cid, _decode(c["input"]), through_funnel=True)
        py, sql = _vj_python(db, cid), _vj_sql(db, cid)
        if py != sql:
            disagreements.append(
                f"{c['id']:26} right_value={_show(_decode(c['input'])):46} "
                f"python={_show(py):16} sql={_show(sql)}")
        # And blankness must fold into the label on BOTH sides, not just one.
        want_label = c["blank"]
        if (py == label) != want_label:
            disagreements.append(
                f"{c['id']:26} python resolved to {_show(py)}; contract says blank={want_label} "
                f"so it must {'' if want_label else 'NOT '}be the unresolved label {label!r}")
        if (sql == label) != want_label:
            disagreements.append(
                f"{c['id']:26} sql resolved to {_show(sql)}; contract says blank={want_label} "
                f"so it must {'' if want_label else 'NOT '}be the unresolved label {label!r}")
    assert not disagreements, (
        "the Python and SQL resolutions disagree about what a cell holds:\n  "
        + "\n  ".join(disagreements)
        + "\n\nThis is the silent under-report: the grid paints one value and the search "
          "compares another. Report both answers to the Lead PM.")


def test_the_two_resolutions_diverge_on_a_bypassed_row_exactly_as_recorded(vj_db):
    """INV-BP-X1 at the resolution seam.

    Same corpus, written STRAIGHT to the right table. This is what a legacy row looks like, and
    it measures what `resolved_expression`'s "no trim() appears here" comment is resting on.
    """
    db, label = vj_db
    expected, measured = [], []
    for c in _text_cases():
        _consume(c["id"])
        raw = _decode(c["input"])
        if raw is None:
            continue
        cid = f"vjraw_{c['id']}"
        _vj_seed(db, cid, raw, through_funnel=False)
        py, sql = _vj_python(db, cid), _vj_sql(db, cid)
        if crud.is_blank_value(raw) and raw != "":
            expected.append(c["id"])
        if py != sql:
            measured.append(c["id"])
    assert measured == expected, (
        "the bypass exposure at the RESOLUTION seam changed shape.\n"
        f"  recorded divergent: {expected}\n"
        f"  measured divergent: {measured}\n"
        "Shrank -> one spelling was changed unilaterally. Grew -> a new class of stored value "
        "resolves differently in the grid and in search. Both are Lead PM decisions.")
    print(f"\n  DECLARED DIVERGENCE INV-BP-X1 (resolution) -- {len(expected)} corpus inputs "
          f"resolve differently in Python and SQL when stored WITHOUT the write boundary: "
          f"{expected}")


def _number_cases():
    for c in CASES:
        if c["input"]["type"] == "number":
            yield c


def test_the_two_resolutions_agree_on_a_numeric_column(vj_db):
    """INV-BP-E1/R2 on a NUMBER expose column -- the axis N7 shipped without (2026-08-02).

    Pre-fix, the SQL half of this seam could not even RUN on the production dialect for a
    numeric column (`COALESCE(double precision, text)`; `double precision = ''`), and on
    this suite's dialect it resolved to the raw float -- '3.0' where the grid says '3'.
    The fix (`crud.numeric_text_sql` inside `resolved_expression`) renders the number to
    its canonical comparison text with the INT spelling for integral values, per the user
    ruling. This scores every number corpus case through BOTH spellings, plus the NULL
    that a number column folds into the label.

    The payload half carries the RAW number (like every other numeric cell in the
    system); its comparison text is `clean_str_value` -- the same render the whole
    Python side already answers with. So the agreement scored here is:
        clean_str_value(payload value)  ==  SQL resolved text
    and NEITHER side may ever produce the float spelling ('7.0') the ruling rejected.
    """
    db, label = vj_db
    disagreements = []
    for through_funnel in (True, False):
        for c in _number_cases():
            _consume(c["id"])
            v = _decode(c["input"])
            cid = f"vjnum_{'f' if through_funnel else 'b'}_{c['id']}"
            _vj_seed(db, cid, v, through_funnel=through_funnel, column="slot_no")
            py = _vj_python(db, cid, "slot_no")
            sql = _vj_sql(db, cid, "slot_no")
            py_text = py if py == label else crud.clean_str_value(py)
            if py_text != sql:
                disagreements.append(
                    f"{c['id']:26} stored={v!r:24} funnel={through_funnel} "
                    f"python_renders={_show(py_text):22} sql={_show(sql)}")
            # A number is blank only as NULL -- no corpus number is blank, so none may
            # fold into the label on EITHER side (INV-BP-E3's zero case included).
            for side, got in (("python", py_text), ("sql", sql)):
                if (got == label) != c["blank"]:
                    disagreements.append(
                        f"{c['id']:26} {side} resolved to {_show(got)}; contract says "
                        f"blank={c['blank']}")

    # The NULL a number column actually produces: right row exists, value NULL. Both
    # spellings must fold it into the label -- this is `_resolve_one` case (2) for
    # numbers, where 'IS NULL alone' must still be a complete blank rule.
    _vj_seed(db, "vjnum_null", None, through_funnel=False, column="slot_no")
    py, sql = _vj_python(db, "vjnum_null", "slot_no"), _vj_sql(db, "vjnum_null", "slot_no")
    if py != label or sql != label:
        disagreements.append(
            f"{'numeric NULL':26} python={_show(py)} sql={_show(sql)} -- both must be "
            f"the label {label!r}")

    assert not disagreements, (
        "the two resolutions disagree about a NUMERIC column:\n  "
        + "\n  ".join(disagreements)
        + "\n\nThis is the N7 seam: the grid paints one spelling and search compares "
          "another (or, on PostgreSQL, the read fails outright). Report both answers to "
          "the Lead PM -- do not force one side here.")


# ---------------------------------------------------------------------------
# Declared divergences and named defects
# ---------------------------------------------------------------------------

def test_declared_divergences_still_diverge_exactly_as_recorded():
    """A declared divergence is a RECORD of two answers, not a licence to stop checking.

    Three outcomes, and only the first is green:
      Python still gives its recorded answer  -> PINNED, reported by id.
      Python gives the OTHER side's answer    -> the divergence closed and nobody removed this
                                                 entry, so it has silently stopped asserting.
      Python gives neither                    -> it changed shape. Louder.
    """
    for name, d in DIVERGENCES.items():
        if name == "$comment":
            continue
        c = _case(d["case"])
        _consume(c["id"])
        got = crud.clean_str_value(_decode(c["input"]))
        assert d["python"] != d["postgres"], (
            f"declared divergence {name} records the SAME answer for both sides. A divergence "
            "that agrees with itself asserts nothing and would make any case permanently green.")
        assert got == d["python"], (
            f"declared divergence {name} ({d['title']}):\n"
            f"  recorded python : {d['python']!r}\n"
            f"  measured python : {got!r}\n"
            f"  recorded postgres: {d['postgres']!r}\n"
            + ("  -- the two sides now AGREE. Delete this entry and give the case a real "
               "`render`.\n" if got == d["postgres"] else
               "  -- the Python side changed to a third answer.\n")
            + f"  decision owner: {d['decision']}")
        print(f"\n  DECLARED DIVERGENCE {name} -- python={d['python']!r} "
              f"postgres={d['postgres']!r} (decision: {d['decision']})")


def test_exactly_one_sql_blank_spelling_exists_in_server():
    """INV-BP-D1, counted by AST.

    Counted, not grepped: a grep hits the spelling quoted inside `blank_sql_condition`'s own
    docstring, which is how a duplication guard gets disabled for being noisy. The pattern is
    `or_(<x>.is_(None), <x> == '')` and its `and_(<x>.isnot(None), <x> != '')` twin.

    Pinned by `known_defects.DUP1` while a second copy is live. The pin is SELF-CANCELLING: the
    moment the copy is removed this goes red in the other direction, because a pin that agrees
    with the contract asserts nothing.
    """
    def _is_none_call(n, attr):
        return (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == attr and len(n.args) == 1
                and isinstance(n.args[0], ast.Constant) and n.args[0].value is None)

    def _cmp_empty(n, op):
        return (isinstance(n, ast.Compare) and len(n.ops) == 1 and isinstance(n.ops[0], op)
                and isinstance(n.comparators[0], ast.Constant)
                and n.comparators[0].value == "")

    blank_sites, notblank_sites = [], []
    for p in sorted((_ROOT / "server").rglob("*.py")):
        if any(part in {"tests", "__pycache__", "scripts", "migrations"} for part in p.parts):
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for n in ast.walk(tree):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and len(n.args) == 2):
                continue
            where = f"{p.relative_to(_ROOT).as_posix()}:{n.lineno}"
            if (n.func.id == "or_" and _is_none_call(n.args[0], "is_")
                    and _cmp_empty(n.args[1], ast.Eq)):
                blank_sites.append(where)
            if (n.func.id == "and_" and _is_none_call(n.args[0], "isnot")
                    and _cmp_empty(n.args[1], ast.NotEq)):
                notblank_sites.append(where)

    pin = DEFECTS.get("DUP1")
    want_blank = pin["measured_blank_spellings"] if pin else 1
    want_notblank = pin["measured_notblank_spellings"] if pin else 1

    tail = ("\n\nIf a count went DOWN to 1, that half of DUP1 was fixed -- update or delete the "
            "entry in vectors.json and let INV-BP-D1 stand at 1. If it went UP, another copy "
            "landed; that is exactly the state the extraction existed to prevent, and it is the "
            "class nobody catches in review." if pin else "")

    assert len(blank_sites) == want_blank, (
        f"the number of SQL blank spellings in server/ changed: pinned {want_blank} "
        f"(known_defects.DUP1), found {len(blank_sites)}.\n  " + "\n  ".join(blank_sites) + tail)
    assert len(notblank_sites) == want_notblank, (
        f"the number of SQL notBlank spellings changed: pinned {want_notblank}, found "
        f"{len(notblank_sites)}.\n  " + "\n  ".join(notblank_sites) + tail)

    if pin:
        print(f"\n  KNOWN DEFECT DUP1 -- contract wants 1 of each; measured "
              f"blank={len(blank_sites)} {blank_sites}, notBlank={len(notblank_sites)} "
              f"{notblank_sites}. Owner: {pin['owner']}")


def test_known_defects_are_named_owned_and_not_self_satisfying():
    """Charter rule 5. A permanent red must be a NAMED, OWNED, self-cancelling pin."""
    for name, d in DEFECTS.items():
        if name == "$comment":
            continue
        for field in ("title", "statement", "owner", "clears_when", "site"):
            assert d.get(field), f"known defect {name} has no `{field}`. An unowned pin is a hole."
        for field in ("measured_blank_spellings", "measured_notblank_spellings"):
            if field in d:
                assert d[field] != 1, (
                    f"known defect {name}.{field} records the contract's own value (1). A pin "
                    "that agrees with the contract asserts nothing and is a way to make any "
                    "check permanently green.")
        for cid in (d.get("cases") or []):
            c = _case(cid)
            assert d.get("actual_prefix"), (
                f"known defect {name} stands in for case {cid} without recording what the "
                "implementation actually does. An unrecorded pin cannot go stale.")
            assert not str(_decode(c["stored_as"])).startswith(d["actual_prefix"]), (
                f"known defect {name} records the SAME answer the contract does for {cid}. "
                "A self-satisfying pin is how a contract becomes permanently green by writing "
                "its expectation twice.")


# ---------------------------------------------------------------------------
# Dialect
# ---------------------------------------------------------------------------

def test_the_suite_dialect_is_not_production_and_the_difference_is_recorded(probe_db):
    """The trap that would have made this contract lie.

    `pytest server/tests/` runs on SQLite; production is PostgreSQL. `cast(<number col> as
    varchar)` is '7.0' on SQLite and '7' on Postgres, so the render axis for NUMBER columns
    cannot be scored here at all. This asserts the SQLite half of `dialect_facts` so that the
    skip below is justified by a measurement rather than by an assumption.
    """
    db = probe_db
    from sqlalchemy import cast, String
    m = _model()
    _write_through_funnel(db, "dialect_probe", "num", 7.0)
    got = db.query(cast(m.num, String)).filter(m.probe_key == "dialect_probe").scalar()
    facts = VECTORS["dialect_facts"]["render_of_float_7_0"]
    assert db.get_bind().dialect.name == "sqlite", (
        "this contract's probe fixture is no longer on SQLite. Re-measure `dialect_facts` "
        "before trusting any number-column render result from this suite.")
    assert got == facts["sqlite"], (
        f"SQLite now renders float 7.0 as {got!r}; `dialect_facts` records {facts['sqlite']!r}. "
        "Re-measure both dialects -- the reason the number render axis is skipped here has "
        "changed.")
    assert facts["sqlite"] != facts["postgres"], (
        "`dialect_facts` says the suite dialect and production agree on number rendering. If "
        "that became true, this axis can move out of the opt-in Postgres run.")


def test_postgres_dialect_axis():
    """The number render axis, scored on the dialect production actually runs.

    Opt-in by design. It is a READ-ONLY, scalar-only run -- no table is named and no row is
    read -- but a contract that reaches for a database URL on its own is one edit away from
    reaching for the wrong one, so it takes an explicit variable and skips loudly without it.
    """
    url = os.environ.get("ASSY_CONTRACT_PG_URL")
    if not url:
        pytest.skip(
            "PENDING AXIS -- number-column RENDER on the production dialect is UNSCORED. "
            "Blocks: INV-BP-R2 for `float_7_0`/`float_0_0`/`float_1e16`. Owner: whoever runs "
            "the suite. Run with ASSY_CONTRACT_PG_URL=postgresql://... to score it. "
            "Recorded measurement (2026-07-31, PostgreSQL 18.3): float 7.0 renders as '7', "
            "matching clean_str_value, while SQLite renders '7.0' and does not.")
    import psycopg2
    conn = psycopg2.connect(url, connect_timeout=5)
    try:
        conn.set_session(readonly=True, autocommit=True)
        cur = conn.cursor()
        facts = VECTORS["dialect_facts"]
        for key, expr in (("render_of_float_7_0", "cast(7.0::float8 as varchar)"),
                          ("render_of_float_0_0", "cast(0.0::float8 as varchar)"),
                          ("render_of_float_7_5", "cast(7.5::float8 as varchar)")):
            cur.execute(f"select {expr}")
            got = cur.fetchone()[0]
            assert got == facts[key]["postgres"], (
                f"{key}: production dialect renders {got!r}, `dialect_facts` records "
                f"{facts[key]['postgres']!r}")
            assert got == facts[key]["python"], (
                f"{key}: the two spellings render differently on the production dialect -- "
                f"python={facts[key]['python']!r} postgres={got!r}. INV-BP-R2 violated.")
        d = DIVERGENCES["FLOAT_EXPONENT"]
        cur.execute("select cast(1e16::float8 as varchar)")
        assert cur.fetchone()[0] == d["postgres"], (
            "declared divergence FLOAT_EXPONENT: the Postgres side changed its answer")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Coverage of the contract itself
# ---------------------------------------------------------------------------

def test_every_contract_case_is_consumed():
    """A case nobody reads is a case that can be deleted without anything going red."""
    declared = {c["id"] for c in CASES}
    unused = sorted(declared - _CONSUMED)
    assert not unused, (
        "these corpus cases were never scored by any test in this file:\n  " + "\n  ".join(unused)
        + "\n\nEither wire them in or delete them -- an unread vector is a comment that looks "
          "like coverage.")


def test_the_corpus_covers_the_classes_the_charter_requires():
    """0 and the empty string are mandatory in every contract this repo writes.

    `v || dflt` turns a declared 0 into a default; an emptiness predicate is the single most
    likely place for that to come back. Asserted rather than trusted to review.
    """
    ids = {c["id"] for c in CASES}
    required = {"null", "empty_string", "space", "tab", "lf", "crlf", "nbsp",
                "ideographic_space", "mixed_whitespace", "zero_string",
                "zero_point_zero_string", "padded_zero", "float_7_0", "float_7_5",
                "plain_string", "content_trailing_tab", "content_trailing_space",
                "float_0_0"}
    assert required <= ids, f"the corpus lost required classes: {sorted(required - ids)}"
