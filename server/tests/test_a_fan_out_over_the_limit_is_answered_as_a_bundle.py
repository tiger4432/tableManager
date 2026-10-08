# -*- coding: utf-8 -*-
"""Walk control ㄴ (총괄 c9bf53033 · 11e5ea207): a step from one node along one predicate and direction
to more than `fanout_limit` nodes draws its first `fanout_limit` - the first read - and `bundles` says
the rest, with the count and what was drawn (소유자 「잘려도 일부는 나와야지」).

The count is taken over the steps the walk's guards pass (`_step`), so it is what expanding
that bundle draws. A bundle is not a node and not a truncation.
"""
import os
import sys
import uuid
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import explorer  # noqa: E402
from ledger_api import ledger_subgraph  # noqa: E402
from tests.test_ledger_trace_pg import ledger_engine  # noqa: E402,F401 - the shipped ledger schema

NOW = datetime(2026, 5, 1, tzinfo=timezone.utc)
DIES = 25
WAFER = explorer.entity_id("wafer", {"w": "W"})
SEED = explorer.entity_id("die", {"d": "D0"})


def _atom(number, subject_type, subject_keys, predicate, far_type, far_keys):
    return ledger_subgraph.EvidenceAtom(
        id=str(uuid.UUID(int=number)), subject_type=subject_type, subject_keys=subject_keys,
        predicate=predicate, object_kind="entity_ref",
        object_payload={"type": far_type, "keys": far_keys}, occurred_at=NOW,
        source_who="t", source_translator_ver="v1", source_raw_ref="row:%d" % number,
        supersedes=None, source_event_id=str(uuid.UUID(int=10_000 + number)),
        source_event_state="source_molecule")


def _wafer_of_dies(seed_in_container=True):
    """One wafer, its dies said twice - `in_container` (die -> wafer) and `inspected`
    (wafer -> die) - the shape the box measured (c9bf53033 ①)."""
    atoms = []
    for k in range(DIES):
        if k or seed_in_container:
            atoms.append(_atom(k + 1, "die", {"d": f"D{k}"}, "in_container", "wafer", {"w": "W"}))
        atoms.append(_atom(100 + k, "wafer", {"w": "W"}, "inspected", "die", {"d": f"D{k}"}))
    # one die inspected TWICE - two atoms, one far node (총괄 b1245bab9 검증): a count of
    # atoms would read DIES + 1 here, and the count is of distinct far nodes
    atoms.append(_atom(999, "wafer", {"w": "W"}, "inspected", "die", {"d": "D3"}))
    return atoms


def _walk(atoms, **kwargs):
    return ledger_subgraph.subgraph(SEED, ledger_subgraph.InMemoryEvidenceLookup(atoms),
                                    hops=2, **kwargs)


def _dies(body):
    return {n["id"] for n in body["nodes"] if n["type"] == "die"}


def _drawn(body, predicate):
    """The dies one predicate's edges reach from the wafer."""
    return {e["source"] if e["target"] == WAFER else e["target"] for e in body["edges"]
            if e["predicate"] == predicate and WAFER in (e["source"], e["target"])}


def test_a_fan_out_over_the_limit_draws_its_first_n_and_its_count_is_what_expanding_draws():
    body = _walk(_wafer_of_dies(), fanout_limit=20)
    assert body["bundles"] == [
        {"node": WAFER, "predicate": "in_container", "direction": "incoming",
         "far_type": "die", "count": DIES, "drawn": 20},
        {"node": WAFER, "predicate": "inspected", "direction": "outgoing",
         "far_type": "die", "count": DIES, "drawn": 20}]
    # the seed's own two edges are its depth-0 step, not the wafer's fan-out
    assert len(_drawn(body, "in_container") - {SEED}) == 20 == len(_drawn(body, "inspected") - {SEED}),         "a fan-out did not draw its first twenty"

    opened = _walk(_wafer_of_dies(), fanout_limit=20,
                   expand=[f"{WAFER}|in_container|incoming"])
    assert [b["predicate"] for b in opened["bundles"]] == ["inspected"]
    drawn = {e["source"] for e in opened["edges"]
             if e["predicate"] == "in_container" and e["target"] == WAFER}
    assert len(drawn) == DIES == len(_dies(opened)), "the count is not what expanding draws"


def test_the_limit_is_exceeded_not_reached():
    assert _walk(_wafer_of_dies(), fanout_limit=DIES)["bundles"] == []


def test_a_step_a_guard_refuses_is_not_counted():
    """Reached ONLY by climbing `inspected`, the wafer may not descend `inspected` - the
    guard refuses those steps, so they are no bundle; `in_container` still fans out."""
    body = _walk(_wafer_of_dies(seed_in_container=False), fanout_limit=20)
    assert body["bundles"] == [
        {"node": WAFER, "predicate": "in_container", "direction": "incoming",
         "far_type": "die", "count": DIES - 1, "drawn": 20}]


def test_no_fanout_limit_answers_as_today():
    atoms = _wafer_of_dies()
    plain = _walk(atoms)
    roomy = _walk(atoms, fanout_limit=1000)
    assert "bundles" not in plain, "the key is absent when the question was not put"
    assert roomy.pop("bundles") == []
    for body in (plain, roomy):
        body.pop("generated_at")
    assert plain == roomy
    assert len(_dies(plain)) == DIES


def test_a_bundle_is_not_a_truncation():
    cut = _walk(_wafer_of_dies(), node_limit=10)
    assert cut["truncated"]["nodes"] is True and "bundles" not in cut
    bundled = _walk(_wafer_of_dies(), node_limit=60, fanout_limit=20)    # room for what it draws
    assert (bundled["truncated"]["nodes"], bundled["truncated"]["edges"],
            len(bundled["bundles"])) == (False, False, 2)


@pytest.mark.parametrize("item", ["W|in_container", "W|in_container|sideways", "|x|incoming"])
def test_an_expand_that_is_not_a_bundle_key_is_refused(item):
    with pytest.raises(ValueError, match="expand"):
        _walk(_wafer_of_dies(), fanout_limit=20, expand=[item])


def test_the_route_passes_both_cells_through(monkeypatch):
    from ledger import trace_router as router

    seen = []
    monkeypatch.setattr(router, "_evidence_graph", lambda *a, **kw: seen.append(kw) or {})
    monkeypatch.setattr(router, "_signed_start", lambda *a, **kw: "seed")

    class _Db:
        def connection(self):
            return None

    common = dict(node_id="seed", response_format="json", db=_Db(), hops=1,
                  direction="both", since=None, until=None, node_limit=400, edge_limit=1200,
                  positive=None, negative=None, follow=None, backbone_hops=0, collect=None,
                  include_superseded=False)
    router.evidence_subgraph(fanout_limit=20, expand=["n|processed_with|outgoing"], **common)
    router.evidence_subgraph(**common)
    assert (seen[0]["fanout_limit"], seen[0]["expand"]) == (20, ["n|processed_with|outgoing"])
    assert (seen[1]["fanout_limit"], seen[1]["expand"]) == (None, None)


def test_a_request_that_names_no_budget_walks_on_the_walks_own_defaults(monkeypatch):
    """총괄 de9455c17: the route said 1200 edges while the walk measured 6000, and the screen sends
    none - so the screen was cut at 1200 edges and 2400 claims. Through the mounted route, so
    FastAPI fills the defaults."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from admin.auth import require_admin_token
    from database.database import get_db
    from ledger import trace_router as router

    seen = []
    monkeypatch.setattr(router, "_evidence_graph", lambda *a, **kw: seen.append(kw) or {})
    monkeypatch.setattr(router, "_signed_start", lambda *a, **kw: "seed")
    app = FastAPI()
    app.dependency_overrides[require_admin_token] = lambda: None
    app.dependency_overrides[get_db] = lambda: type("_Db", (), {"connection": lambda self: None})()
    app.include_router(router.router)

    answer = TestClient(app).get("/api/ledger/subgraph", params={"id": "seed"})

    assert answer.status_code == 200, answer.text
    assert (seen[0]["hops"], seen[0]["node_limit"], seen[0]["edge_limit"]) == (
        ledger_subgraph.DEFAULT_HOPS, ledger_subgraph.DEFAULT_NODE_LIMIT,
        ledger_subgraph.DEFAULT_EDGE_LIMIT)


def _wafer_of_defects_and_newer_measures(defects=300, measures=300):
    """One wafer: `defects` older defects on it, and `measures` newer measures it carries - the
    newer branch alone fills a small claims budget (the lookup reads newest first)."""
    atoms = [_atom(1 + k, "defect", {"d": f"F{k}"}, "on_wafer", "wafer", {"w": "W"})
             for k in range(defects)]
    atoms += [_atom(100_000 + k, "wafer", {"w": "W"}, "measured", "measure", {"m": f"M{k}"})
              for k in range(measures)]
    return atoms


def test_an_opened_bundle_reads_first_within_its_depth():
    """총괄 11e5ea207 · c06b45ea5: the newer branch spends the budget, so the older one is not even
    read; opened, it is read first and drawn - and what the budget still cut comes back as a bundle."""
    atoms = _wafer_of_defects_and_newer_measures()
    seed = explorer.entity_id("wafer", {"w": "W"})

    def walk(**kw):
        return ledger_subgraph.subgraph(seed, ledger_subgraph.InMemoryEvidenceLookup(atoms), hops=1,
                                        edge_limit=100, fanout_limit=20, **kw)   # claims: 200

    def defects(body):
        return {n["id"] for n in body["nodes"] if n["type"] == "defect"}

    shut = walk()
    assert (defects(shut), [b["predicate"] for b in shut["bundles"]]) == (set(), ["measured"])
    opened = walk(expand=[f"{seed}|on_wafer|incoming"])
    (bundle,) = [b for b in opened["bundles"] if b["predicate"] == "on_wafer"]
    assert defects(opened) and 0 < bundle["drawn"] < bundle["count"] == 200, bundle
    assert opened["truncated"]["claims"] is True


# ------------------------------------------------- on PostgreSQL, the operating shape (총괄 11e5ea207 · e963e6eac)

PG_DEFECTS, PG_REGISTRATIONS = 3000, 3


def _pg_shape(measures=0):
    """One wafer; `PG_DEFECTS` defects `on_wafer` it, each registered `PG_REGISTRATIONS` times
    (a day later); and `measures` newer `measured` steps out of the wafer (two days later)."""
    import json
    from datetime import timedelta

    def row(subject_type, keys, predicate, kind, payload, when, raw):
        return {"id": str(uuid.uuid4()), "st": subject_type, "sk": json.dumps(keys), "p": predicate,
                "ok": kind, "op": json.dumps(payload), "oa": NOW + when, "who": "fanout",
                "ver": "fanout/1", "raw": raw, "sup": None}
    rows = []
    for k in range(PG_DEFECTS):
        keys = {"defect": "F%05d" % k}
        rows.append(row("defect", keys, "on_wafer", "entity_ref", {"type": "wafer", "keys": {"wafer": "W1"}},
                        timedelta(seconds=k), "d:%d" % k))
        rows.extend(row("defect", keys, "register", None, {"qualifiers": {"a%d" % j: "v%d" % k}},
                        timedelta(days=1, seconds=k * PG_REGISTRATIONS + j), "r:%d:%d" % (k, j))
                    for j in range(PG_REGISTRATIONS))
    rows.extend(row("wafer", {"wafer": "W1"}, "measured", "entity_ref", {"type": "measure", "keys": {"m": "M%05d" % k}},
                    timedelta(days=2, seconds=k), "m:%d" % k) for k in range(measures))
    return rows


@pytest.fixture(name="pg_walk")
def fixture_pg_walk(request):
    from sqlalchemy import text
    from tests.test_ledger_trace_pg import insert

    engine = request.getfixturevalue("ledger_engine")

    def seeded(measures=0):
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE ledger_events"))
            rows = _pg_shape(measures)
            for start in range(0, len(rows), 5000):
                insert(conn, rows[start:start + 5000])

    def walk(**kw):
        with engine.connect() as conn:
            return ledger_subgraph.subgraph(
                explorer.entity_id("wafer", {"wafer": "W1"}), ledger_subgraph.SqlEvidenceLookup(conn),
                hops=ledger_subgraph.DEFAULT_HOPS, registration_follow={"register"}, **kw)
    try:
        yield seeded, walk
    finally:
        with engine.begin() as conn:
            conn.execute(text("TRUNCATE ledger_events"))


def _pg_defects(body):
    return {n["id"] for n in body["nodes"] if n["type"] == "defect"}


def _pg_bundle(body, predicate):
    found = [b for b in body.get("bundles") or () if b["predicate"] == predicate]
    return found[0] if found else None


@pytest.mark.pg
def test_thousands_of_defects_on_a_wafer_draw_their_first_twenty_and_open_past_them(pg_walk):
    seeded, walk = pg_walk
    seeded()
    wafer = explorer.entity_id("wafer", {"wafer": "W1"})

    shut = walk(fanout_limit=20)
    assert len(_pg_defects(shut)) == 20
    assert {k: _pg_bundle(shut, "on_wafer")[k] for k in ("count", "drawn")} == {"count": PG_DEFECTS, "drawn": 20}

    opened = walk(fanout_limit=20, expand=[f"{wafer}|on_wafer|incoming"])
    left = _pg_bundle(opened, "on_wafer")
    assert 20 < left["drawn"] < left["count"] == PG_DEFECTS, left       # the node budget cut it
    assert opened["truncated"]["nodes"] is True
    # read once: the wafer's defects, then each drawn defect's own atoms - its step back and its registrations
    assert opened["walk"]["claims_scanned"] == PG_DEFECTS + (1 + PG_REGISTRATIONS) * left["drawn"]

    plain = walk()                                                    # no fan-out: as before
    assert "bundles" not in plain and len(_pg_defects(plain)) == len(_pg_defects(opened))


@pytest.mark.pg
def test_an_opened_bundle_is_read_before_a_newer_branch_that_fills_the_budget(pg_walk):
    seeded, walk = pg_walk
    seeded(measures=ledger_subgraph.MAX_CLAIM_SCAN + 1000)
    wafer = explorer.entity_id("wafer", {"wafer": "W1"})

    shut = walk(fanout_limit=20)
    assert (_pg_defects(shut), _pg_bundle(shut, "on_wafer")) == (set(), None)   # never read
    assert shut["truncated"]["claims"] is True
    opened = walk(fanout_limit=20, expand=[f"{wafer}|on_wafer|incoming"])
    assert len(_pg_defects(opened)) > 20 and _pg_bundle(opened, "on_wafer")["drawn"] > 20
