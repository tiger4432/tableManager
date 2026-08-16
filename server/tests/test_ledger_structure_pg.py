# -*- coding: utf-8 -*-
"""`GET /api/ledger/structure` — asserted on the FAILURE CONDITIONS, not on the happy path.

The product owner named two of them in the brief (§0-quater) and they are the two this
file exists for:

    「하드코딩된 노드/엣지 목록이 응답 어디에든 보이면 실패입니다.」
    「건수 0인 선언 엣지를 숨기지 마십시오.」

Both are properties nothing else can catch. A hand-written node list PASSES every
functional test on the box it was written on — it is only wrong on the day somebody adds
a predicate. So the whole vocabulary is SWAPPED here for one whose words are named
nothing like the real ones (`Widget`, `Crate`, `bolted_to`), and the graph is asserted to
follow it. A single literal `"Lot"` or `"has_wafer"` anywhere in `ledger_structure.py`
fails this file.

WHY PostgreSQL OR SKIP
-----------------------
The census is `GROUP BY` over a PARTITIONED table with a jsonb key extraction in the
group key, and the absent-relation branch is judged with `to_regclass`. SQLite has
neither. A suite that ran this on in-memory SQLite would be green about a query that
cannot execute in production — "SQLite accepts what PostgreSQL refuses", paid for three
times in this project already.

WHAT EACH TEST DEFENDS
-----------------------
1. `test_the_graph_follows_a_swapped_vocabulary` — the failure condition, directly.
2. `test_a_declared_edge_with_no_atoms_is_served_as_zero` — the honest empty axis.
3. `test_an_absent_ledger_gives_null_atoms_and_never_zero` — `null` != `0`, the
   distinction `absent-zero-is-not-inert-zero` cost this project a wrong diagnosis.
4. `test_an_undeclared_shape_is_shown_as_drift_and_never_dropped` — an atom whose shape
   the vocabulary does not declare must reach the screen, or an ontology fork is silent.
5. `test_the_class_breakdown_agrees_with_claim_class` — the census classifies through
   `claim_class`, and this drives EVERY arm of it (pin / confirmed-by-flag /
   inference-by-derivation / inference-by-flag / observation) so the payload-flag
   extraction in SQL cannot quietly stop matching what Python reads.
6. `test_a_window_narrows_counts_but_never_the_declared_structure` — the scale defence
   must not defeat the honest-empty-axis rule.
"""
import contextlib
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import ledger_structure                                             # noqa: E402
import ledger_trace                                                 # noqa: E402

PG_TEST_URL_ENV = "ASSY_PG_TEST_DATABASE_URL"
SCRATCH_SCHEMA = "assy_structure_pytest" + (
    "_" + os.environ["PYTEST_XDIST_WORKER"]
    if os.environ.get("PYTEST_XDIST_WORKER") else "")

#: 🔴 NOT the real vocabulary. Nothing here is named like anything in
#: `server/ledger/vocabulary.py`, so a literal from the real one cannot satisfy any
#: assertion below.
#:
#: The shape is chosen to cover every branch of `declared_edges`:
#:   `bolted_to`  entity_ref with TWO declared targets   -> two edges from one predicate
#:   `stamped`    a `value` object with required fields  -> object_fields on the wire
#:   `enrol`      object None (∅)                        -> the register-shaped edge
#:   `pinpoint`   event_ref                              -> the fourth object token
#:   `mothballed` status `reserved`                      -> declared, never emittable
FAKE_ENTITY_TYPES = {
    "Widget": {"class": "issued", "keys": ["widget"], "semi_ref": "X1",
               "label_ko": "위젯"},
    "Crate":  {"class": "issued", "keys": ["crate"], "semi_ref": None,
               "label_ko": "상자"},
    "Sliver": {"class": "composed", "keys": ["widget", "n"], "semi_ref": None,
               "label_ko": "조각"},
}

FAKE_PREDICATES = {
    "enrol": {
        "label_ko": "등재", "status": "active", "since": 1, "layer": "canonical",
        "subject": ["Widget", "Crate"], "object": None, "qualifiers": [],
        "unit": None, "semi_ref": "X", "superseded_by": None,
    },
    "pinpoint": {
        "label_ko": "지목", "status": "active", "since": 1, "layer": "canonical",
        "subject": ["Widget"], "object": {"kind": "event_ref"}, "qualifiers": [],
        "unit": None, "semi_ref": "X", "superseded_by": None,
    },
    "bolted_to": {
        "label_ko": "체결", "status": "active", "since": 1, "layer": "ontology",
        "subject": ["Widget"],
        "object": {"kind": "entity_ref", "types": ["Crate", "Widget"]},
        "qualifiers": [], "unit": None, "semi_ref": "X", "superseded_by": None,
    },
    "stamped": {
        "label_ko": "각인", "status": "active", "since": 2, "layer": "ontology",
        "subject": ["Widget"],
        "object": {"kind": "value", "required": ["mark", "depth"]},
        "qualifiers": [], "unit": None, "semi_ref": "X", "superseded_by": None,
    },
    "mothballed": {
        "label_ko": "봉인", "status": "reserved", "since": 2, "layer": "ontology",
        "subject": ["Crate"], "object": {"kind": "value", "required": ["why"]},
        "qualifiers": [], "unit": None, "semi_ref": "X", "superseded_by": None,
    },
}

#: The resolver config the fixture is built against. Declared here rather than defaulted
#: so the class assertions rest on something this file states, and so `pinpoint` (not
#: `pin`) is what class 0 means — another place a real-vocabulary literal would show.
FAKE_RESOLVER = dict(ledger_trace.DEFAULT_RESOLVER_CONFIG,
                     pin_predicates=["pinpoint"],
                     confirmed_predicates=[],
                     confirmed_sources=[],
                     inference_derivations=["assumed_pairing"],
                     inference_sources=[])

BASE = datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc)
OLD = BASE - timedelta(days=400)

LEDGER_DDL = """
CREATE TABLE ledger_events (
    id                    UUID        NOT NULL,
    subject_type          TEXT        NOT NULL,
    subject_keys          JSONB       NOT NULL,
    predicate             TEXT        NOT NULL,
    object_kind           TEXT,
    object_payload        JSONB,
    occurred_at           TIMESTAMPTZ NOT NULL,
    source_who            TEXT        NOT NULL,
    source_translator_ver TEXT        NOT NULL,
    source_raw_ref        TEXT        NOT NULL,
    supersedes            UUID,
    PRIMARY KEY (id, occurred_at)
);
CREATE TABLE ledger_translator_cursor (
    source TEXT PRIMARY KEY, translator_ver TEXT NOT NULL,
    cursor_value JSONB NOT NULL, molecules_done BIGINT DEFAULT 0,
    atoms_written BIGINT DEFAULT 0, atoms_deduped BIGINT DEFAULT 0,
    molecules_refused BIGINT DEFAULT 0, incomplete_molecules BIGINT DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT now()
);
"""

#: `(predicate, subject, object_kind, payload, source_who, ver, when, expected class)`.
#: 🔴 EVERY CLASS IS REPRESENTED, including the two arms that are easy to break:
#: `assumed_pairing` reaches class 3 through the `#<derivation>` SUFFIX, and the setpoint
#: row reaches class 3 through the PAYLOAD FLAG. A census that stopped extracting the
#: flag would still be green on the first and wrong on the second.
ATOMS = [
    ("enrol", "Widget", None, None, "hopper", "hopper/1/r:aa#first_sight",
     BASE, "observation"),
    ("enrol", "Widget", None, None, "hopper", "hopper/1/r:aa#first_sight",
     BASE + timedelta(minutes=1), "observation"),
    ("enrol", "Crate", None, None, "hopper", "hopper/1/r:aa#first_sight",
     BASE, "observation"),
    ("pinpoint", "Widget", "event_ref", {"event": "E1"}, "human",
     "human/1/r:aa#by_hand", BASE, "pin"),
    ("bolted_to", "Widget", "entity_ref", {"type": "Crate", "keys": {"crate": "C1"}},
     "hopper", "hopper/1/r:aa#pair_field", BASE, "observation"),
    ("bolted_to", "Widget", "entity_ref", {"type": "Crate", "keys": {"crate": "C2"}},
     "hopper", "hopper/1/r:aa#assumed_pairing", BASE, "inference"),
    ("stamped", "Widget", "value", {"mark": "M", "depth": 2, "confirmed": True},
     "gauge", "gauge/1/r:bb#read", BASE, "confirmed"),
    ("stamped", "Widget", "value", {"mark": "M", "depth": 9, "inferred": True},
     "book", "book/1/r:bb#setpoint", BASE, "inference"),
    # OUTSIDE the window used by the window test, and the ONLY atom of its edge, so a
    # windowed census must report that edge as `declared_only` and not drop it.
    ("stamped", "Widget", "value", {"mark": "OLD", "depth": 1},
     "gauge", "gauge/1/r:bb#read", OLD, "observation"),
]

#: 🔴 A shape the FAKE vocabulary does not declare: `Sliver` may not be `bolted_to`
#: anything. Written straight into the table (no gate in this fixture, which is the point
#: — the gate is what should stop this, and the screen is what has to show it if the gate
#: ever does not).
UNDECLARED_ATOM = ("bolted_to", "Sliver", "entity_ref",
                   {"type": "Crate", "keys": {"crate": "C9"}},
                   "rogue", "rogue/1/r:zz#unknown", BASE)


def _resolve_url():
    import db_safety
    from database.database import DEFAULT_PG_URL

    url = os.environ.get(PG_TEST_URL_ENV) or None
    if not url:
        candidate = os.environ.get(db_safety.TEST_DATABASE_URL_ENV) or ""
        url = candidate if candidate.startswith("postgres") else None
    if not url:
        return None, (f"no PostgreSQL test database declared. Set {PG_TEST_URL_ENV} to "
                      f"an ISOLATED database, e.g. postgresql://…@localhost:5432/assy_qa")
    violations = db_safety.check_test_database(url, production_url=DEFAULT_PG_URL,
                                               opt_in=url)
    if violations:
        return None, f"{PG_TEST_URL_ENV} is not usable: {violations[0]}"
    from sqlalchemy.engine import make_url
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql":
        return None, f"{PG_TEST_URL_ENV} is not a PostgreSQL URL"
    if (parsed.database or "") == "assy_manager":
        # 🔴 This file runs DDL. The owner's dev database is not its playground.
        return None, "refusing to run schema DDL against 'assy_manager'"
    return url, None


@contextlib.contextmanager
def _declared_as_test_database(url):
    import db_safety
    key = db_safety.TEST_DATABASE_URL_ENV
    previous = os.environ.get(key)
    os.environ[key] = url
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = previous


def _insert(cur, predicate, subject, object_kind, payload, who, ver, when):
    import json
    cur.execute(
        "INSERT INTO ledger_events (id, subject_type, subject_keys, predicate, "
        "object_kind, object_payload, occurred_at, source_who, source_translator_ver, "
        "source_raw_ref, source_event_id, source_event_state) VALUES "
        "(gen_random_uuid(), %s, %s::jsonb, %s, %s, %s::jsonb, "
        "%s, %s, %s, 'ref', gen_random_uuid(), 'source_record')",
        (subject, json.dumps({"k": "1"}), predicate, object_kind,
         json.dumps(payload) if payload is not None else None, when, who, ver))


@pytest.fixture(scope="module")
def pg():
    url, reason = _resolve_url()
    if url is None:
        pytest.skip(reason)
    try:
        import psycopg2                                              # noqa: F401
    except Exception as exc:                                         # pragma: no cover
        pytest.skip(f"psycopg2 is not importable: {exc}")
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.pool import NullPool

    with _declared_as_test_database(url):
        admin = create_engine(url, poolclass=NullPool)
        try:
            with admin.begin() as conn:
                conn.execute(text("SELECT 1"))
        except OperationalError as exc:
            admin.dispose()
            pytest.skip(f"PostgreSQL is not reachable: "
                        f"{str(exc).strip().splitlines()[0]}")
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{SCRATCH_SCHEMA}" CASCADE'))
            conn.execute(text(f'CREATE SCHEMA "{SCRATCH_SCHEMA}"'))
        engine = create_engine(
            url, poolclass=NullPool,
            connect_args={"options": f"-csearch_path={SCRATCH_SCHEMA}"})
        raw = engine.raw_connection()
        with raw.cursor() as cur:
            cur.execute(LEDGER_DDL)
            for row in ATOMS:
                _insert(cur, *row[:7])
            cur.execute("INSERT INTO ledger_translator_cursor "
                        "(source, translator_ver, cursor_value) "
                        "VALUES ('hopper', 'hopper/1/r:aa', '{}'::jsonb)")
        raw.commit()
        try:
            yield raw
        finally:
            raw.close()
            engine.dispose()
            with admin.begin() as conn:
                conn.execute(text(f'DROP SCHEMA IF EXISTS "{SCRATCH_SCHEMA}" CASCADE'))
                left = conn.execute(text(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema = :s"), {"s": SCRATCH_SCHEMA}).scalar()
                assert left == 0, f"{left} object(s) left behind in {SCRATCH_SCHEMA}"
            admin.dispose()


@pytest.fixture(autouse=True)
def swapped_vocabulary(monkeypatch):
    """🔴 THE WHOLE VOCABULARY, REPLACED. Every assertion below is about words this file
    invented, so nothing in `ledger_structure.py` can satisfy them by knowing the real
    ones."""
    from ledger import vocabulary
    monkeypatch.setattr(vocabulary, "ENTITY_TYPES", FAKE_ENTITY_TYPES)
    monkeypatch.setattr(vocabulary, "PREDICATES", FAKE_PREDICATES)
    monkeypatch.setattr(vocabulary, "ISSUED_TYPES",
                        frozenset(k for k, v in FAKE_ENTITY_TYPES.items()
                                  if v["class"] == "issued"))
    yield


def _body(pg, **kwargs):
    kwargs.setdefault("config", FAKE_RESOLVER)
    return ledger_structure.structure(pg, **kwargs)


def _edge(body, edge_id):
    for edge in body["graph"]["edges"]:
        if edge["id"] == edge_id:
            return edge
    raise AssertionError(f"no edge {edge_id!r} in {[e['id'] for e in body['graph']['edges']]}")


def _node(body, node_id):
    for node in body["graph"]["nodes"]:
        if node["id"] == node_id:
            return node
    raise AssertionError(f"no node {node_id!r}")


# --------------------------------------------------------------------------- 1
def test_the_graph_follows_a_swapped_vocabulary(pg):
    """THE failure condition: the picture is generated, so a different declaration makes
    a different picture with no code change."""
    body = _body(pg)

    assert {n["id"] for n in body["graph"]["nodes"]} == set(FAKE_ENTITY_TYPES)
    assert _node(body, "Widget")["label"] == "위젯"
    assert _node(body, "Sliver")["requires_register"] is False, (
        "a COMPOSED type must not be reported as needing a register atom")

    # One predicate with TWO declared targets is TWO edges. A renderer cannot draw the
    # second one if the API collapsed them.
    assert _edge(body, "Widget|bolted_to|entity:Crate")["target"] == "Crate"
    assert _edge(body, "Widget|bolted_to|entity:Widget")["target"] == "Widget"

    # The `value` object's required fields reach the wire — this is how the screen can
    # say that a predicate names things INSIDE a payload rather than as entity refs.
    assert _edge(body, "Widget|stamped|value")["object_fields"] == ["mark", "depth"]
    assert _edge(body, "Widget|pinpoint|event")["object_kind"] == "event_ref"
    assert _edge(body, "Widget|enrol|none")["object_kind"] is None

    predicates = {p["predicate"] for p in body["vocabulary"]["predicates"]}
    assert predicates == set(FAKE_PREDICATES)
    reserved = [p for p in body["vocabulary"]["predicates"]
                if p["predicate"] == "mothballed"][0]
    assert reserved["emittable"] is False and reserved["status"] == "reserved"

    # And the linkage the client draws with: every predicate names its own edges.
    bolted = [p for p in body["vocabulary"]["predicates"]
              if p["predicate"] == "bolted_to"][0]
    assert bolted["edge_ids"] == ["Widget|bolted_to|entity:Crate",
                                  "Widget|bolted_to|entity:Widget"]


# --------------------------------------------------------------------------- 2
def test_a_declared_edge_with_no_atoms_is_served_as_zero(pg):
    """「선언은 있는데 데이터가 없다」 — half the reason this screen exists."""
    body = _body(pg)

    empty = _edge(body, "Crate|mothballed|value")
    assert empty["atoms"] == 0, "a counted-and-empty edge is 0, never null and never gone"
    assert empty["edge_state"] == ledger_structure.EDGE_DECLARED_ONLY
    assert empty["declared"] is True

    # The node with no atoms at all survives too, for the same reason.
    assert _node(body, "Sliver")["node_state"] == ledger_structure.EDGE_DECLARED_ONLY

    flowing = _edge(body, "Widget|enrol|none")
    assert flowing["atoms"] == 2 and flowing["edge_state"] == ledger_structure.EDGE_FLOWING
    assert _node(body, "Widget")["registered"] == 2


# --------------------------------------------------------------------------- 3
def test_an_absent_ledger_gives_null_atoms_and_never_zero(pg):
    """`null` means nobody counted; `0` means somebody counted nothing. Rendering them
    the same is the `absent-zero-is-not-inert-zero` defect."""
    body = _body(pg, relation="ledger_events_that_do_not_exist")

    assert body["state"] == ledger_structure.STATE_ABSENT
    assert body["cost"]["atoms_counted"] is None
    # The DECLARED structure is still served — a box with no ledger still has an ontology,
    # and somebody staring at a blank screen is exactly who needs to see it.
    assert len(body["graph"]["edges"]) > 0 and len(body["graph"]["nodes"]) == 3
    for edge in body["graph"]["edges"]:
        assert edge["atoms"] is None, f"{edge['id']} reported a count nobody measured"
        assert edge["edge_state"] == ledger_structure.EDGE_UNMEASURED
    for node in body["graph"]["nodes"]:
        assert node["atoms_as_subject"] is None
        assert node["node_state"] == ledger_structure.EDGE_UNMEASURED


# --------------------------------------------------------------------------- 4
def test_an_undeclared_shape_is_shown_as_drift_and_never_dropped(pg):
    """A shape nobody declared must REACH the screen. Dropping it makes an ontology fork
    silent, and silent is how it lasts."""
    before = _body(pg)
    assert before["drift"]["undeclared_edge_ids"] == []

    with pg.cursor() as cur:
        _insert(cur, *UNDECLARED_ATOM)
    pg.commit()
    try:
        body = _body(pg)
        rogue = _edge(body, "Sliver|bolted_to|entity:Crate")
        assert rogue["declared"] is False
        assert rogue["edge_state"] == ledger_structure.EDGE_UNDECLARED
        assert rogue["atoms"] == 1
        assert "Sliver|bolted_to|entity:Crate" in body["drift"]["undeclared_edge_ids"]
        assert "rogue" in body["drift"]["undeclared_sources"]
    finally:
        with pg.cursor() as cur:
            cur.execute("DELETE FROM ledger_events WHERE source_who = 'rogue'")
        pg.commit()


# --------------------------------------------------------------------------- 5
def test_the_class_breakdown_agrees_with_claim_class(pg):
    """The census classifies THROUGH `ledger_trace.claim_class`, so this drives every arm
    of it and pins the SQL-side payload-flag extraction that feeds it.

    The fixture's `expected` column is written by hand from the design's rules, so this is
    an ORACLE comparison and not the implementation checking itself."""
    body = _body(pg)

    expected = {}
    for predicate, subject, object_kind, _payload, _who, _ver, when, klass in ATOMS:
        token = ledger_structure._object_token(
            object_kind, "Crate" if object_kind == "entity_ref" else None)
        key = f"{subject}|{predicate}|{token}"
        expected.setdefault(key, {})
        expected[key][klass] = expected[key].get(klass, 0) + 1

    for edge_id, wanted in expected.items():
        got = {name: n for name, n in _edge(body, edge_id)["classes"].items() if n}
        assert got == wanted, f"{edge_id}: class breakdown {got} != {wanted}"

    # 🔴 The two class-3 routes are DIFFERENT mechanisms and both must be live, or this
    # test would pass with half the resolver working.
    assert _edge(body, "Widget|bolted_to|entity:Crate")["classes"]["inference"] == 1, (
        "the `#<derivation>` suffix route to class 3 is not firing")
    stamped = _edge(body, "Widget|stamped|value")["classes"]
    assert stamped["inference"] == 1, "the payload-flag route to class 3 is not firing"
    assert stamped["confirmed"] == 1, "the payload-flag route to class 1 is not firing"
    assert _edge(body, "Widget|pinpoint|event")["classes"]["pin"] == 1

    # The derivation is reported per source, verbatim, and it is what the resolver panel
    # links its class-3 declaration to.
    bolted = _edge(body, "Widget|bolted_to|entity:Crate")
    assert {s["derivation"] for s in bolted["sources"]} == {"pair_field",
                                                            "assumed_pairing"}
    rule = [d for d in body["declarations"]
            if d["id"] == "ledger_resolver:inference_derivations"][0]
    assert rule["edge_ids"] == ["Widget|bolted_to|entity:Crate"], (
        "the class-3 declaration must name the edge it actually moved")


# --------------------------------------------------------------------------- 6
def test_a_window_narrows_counts_but_never_the_declared_structure(pg):
    """The scale defence may not defeat the honest-empty-axis rule."""
    full = _body(pg)
    windowed = _body(pg, window="2026-03-01..2026-04-01")

    assert windowed["window"]["declared"] is True
    assert ({e["id"] for e in windowed["graph"]["edges"]}
            == {e["id"] for e in full["graph"]["edges"]}), (
        "a window may narrow counts; it may not remove a declared axis from the picture")
    assert (_edge(windowed, "Widget|stamped|value")["atoms"]
            == _edge(full, "Widget|stamped|value")["atoms"] - 1), (
        "the atom outside the window must be excluded from the count")
    assert _edge(windowed, "Crate|mothballed|value")["atoms"] == 0


# --------------------------------------------------------------------------- 7
def test_the_mechanism_layer_reports_absence_rather_than_inventing_a_graph(pg,
                                                                          monkeypatch,
                                                                          tmp_path):
    """🔴 The lead PM's instruction was explicit: 「없으면 없다고 응답이 말하게 하십시오
    (지어내지 말 것)」.

    Measured 2026-08-14: the M4 mechanism graph exists only as a fenced example inside
    `PHYSICS_ONTOLOGY_SETUP.md` §4 — no config, no loader, no consumer. So the layer must
    come back EMPTY with a reason, and must NOT be quietly filled from the doc.
    """
    import paths
    monkeypatch.setattr(paths, "CONFIG_DIR", str(tmp_path))          # no declaration here

    body = _body(pg)
    mech = body["graph"]["mechanism"]
    assert mech["state"] == ledger_structure.MECH_STATE_ABSENT
    assert mech["declared"] is False
    assert mech["nodes"] == [] and mech["edges"] == [] and mech["models"] == []
    assert mech["reason"] == ledger_structure.MECH_REASON_NO_FILE
    assert mech["spec_ref"], "an absent layer must say where its shape is proposed"
    # The linkage is DERIVED: no `Model` entity type is declared, so there is nowhere for
    # a mechanism node to attach to the ledger. It stops being true by itself the day one
    # is declared.
    assert mech["ledger_link"]["entity_type"] is None
    assert (mech["ledger_link"]["reason"]
            == ledger_structure.MECH_REASON_NO_MODEL_ENTITY)

    layers = {layer["id"]: layer for layer in body["graph"]["layers"]}
    assert set(layers) == {"ledger", "mechanism"}
    assert layers["mechanism"]["state"] == ledger_structure.MECH_STATE_ABSENT
    assert layers["ledger"]["state"] == ledger_structure.STATE_READY

    row = [d for d in body["declarations"] if d["group"] == "mechanism"]
    assert len(row) == 1 and row[0]["declared"] is False, (
        "the declaration map must carry a row saying the declaration is missing — a row "
        "that vanishes when absent can never report absence")


# --------------------------------------------------------------------------- 8
def test_a_landed_mechanism_declaration_renders_as_the_second_layer(pg, monkeypatch,
                                                                    tmp_path):
    """The seam is real: dropping the file in makes the layer render, with no code change.

    🔴 The fixture is deliberately NOT `void_formation_v0`. If this file used the model
    from the design doc, a hardcoded transcription of that doc would pass — which is the
    same failure condition the swapped vocabulary defends against, one layer over.
    """
    import json
    import paths
    monkeypatch.setattr(paths, "CONFIG_DIR", str(tmp_path))
    (tmp_path / ledger_structure.MECHANISM_CONFIG_FILENAME).write_text(json.dumps({
        "__doc": "ignored",
        "rattle_onset_v0": {
            "version": "0.1-qualitative",
            "nodes": ["torque", "clearance", "rattle", "orphan_quantity"],
            "edges": [
                {"from": "torque", "to": "clearance", "dir": "-", "form": None},
                {"from": "clearance", "to": "rattle", "dir": "+", "form": None},
                {"from": "torque", "to": "rattle", "dir": "u", "form": None},
            ],
            "validity": {"step": "assembly"},
        },
    }), encoding="utf-8")

    mech = _body(pg)["graph"]["mechanism"]
    assert mech["state"] == ledger_structure.MECH_STATE_DECLARED
    assert [m["model"] for m in mech["models"]] == ["rattle_onset_v0"]
    assert mech["models"][0]["validity"] == {"step": "assembly"}

    ids = {e["id"] for e in mech["edges"]}
    assert ids == {"rattle_onset_v0|torque->clearance",
                   "rattle_onset_v0|clearance->rattle",
                   "rattle_onset_v0|torque->rattle"}

    by_id = {e["id"]: e for e in mech["edges"]}
    # 🔴 `u` is NON-MONOTONE, an assertion the modeller made. A screen that rendered it
    # as "unknown" would throw away the only thing that edge says.
    assert by_id["rattle_onset_v0|torque->rattle"]["dir_label"] == "비단조"
    assert by_id["rattle_onset_v0|torque->clearance"]["dir_label"] == "감소"
    assert all(e["has_form"] is False for e in mech["edges"])

    # Declared and read by NOBODY — the fifth state word, and the reason this layer exists.
    assert all(e["edge_state"] == ledger_structure.EDGE_DECLARED_UNCONSUMED
               for e in mech["edges"])
    assert all(e["atoms"] is None for e in mech["edges"]), (
        "a mechanism edge has no count to take; a 0 would claim somebody looked")

    # A node declared and touched by no edge is a fact about the model, not clutter.
    assert "orphan_quantity" in {n["id"] for n in mech["nodes"]}

    row = [d for d in _body(pg)["declarations"] if d["group"] == "mechanism"][0]
    assert row["declared"] is True and row["edge_ids"] == mech["models"][0]["edge_ids"]
