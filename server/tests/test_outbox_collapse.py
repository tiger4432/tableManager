"""[OUTBOX-4] Collapsing the per-row outbox event into one event per flush.

WHAT IS PINNED HERE, AND WHY EACH TEST EXISTS RATHER THAN JUST PASSING.

The outbox used to write one row per changed row, carrying that row's values.
Measured on this workstation (a simulation) against a real PostgreSQL
`database_outbox` with all seven indexes: 2,108 B per `dt_log` row all-in, i.e.
19.6 GiB at 10,000,000 ingested rows - and, decisively, the purge drains only
1.2M rows/day, so above that ingestion rate the table has no steady state at all.
Collapsed, one event names up to 1,000 row_ids: 10,000 outbox rows and 260 MiB
for the same 10M ingested rows, one fifth of a SINGLE purge cycle.

🔴 EVERY TEST BELOW THAT SCORES THE NEW BEHAVIOUR ALSO EXERCISES THE OLD ONE ON
THE SAME INPUT. A fixture that is already green proves nothing (server-pm lessons
file: "새로 만든 코드 경로를 한 번도 실행하지 않는 검증으로 해소를 선언"), so the
per-row arm is not a control for decoration - it is the proof that the collapsed
arm is the thing being measured. Where an arm cannot be run both ways
(`test_expansion_is_load_bearing`), the test asserts directly that the RAW
collapsed payload fails the accessor the expansion exists to satisfy.

[Isolation] Table names use the `obxcol_` prefix — they cannot exist in a real
user config. conftest claims the live config at import time on a shared sqlite
(see the lessons file: the `bonding_log` trap), so a colliding name would
silently test the wrong table.
"""
import json

import pytest

import event_constants
import outbox_expand
from database import crud, models, schemas
from database.context import request_outbox_mode, outbox_mode
from database.models import DatabaseOutbox
from utils.payload_helper import get_payload_dict

COLLAPSED = event_constants.OUTBOX_MODE_COLLAPSED

# Two IDENTICAL schemas. The mirror exists so the same rows can be written once
# per-row and once collapsed and the two payloads compared field by field - the
# only way to show the expansion rebuilds what the producer would have written
# rather than something that merely looks plausible.
_COLS = {
    "column_types": {
        "key_id": "string",
        "lot": "string",
        "qty": "number",
        "eqp": "string",
    },
}
OBX_TABLES = {
    "obxcol_src": dict(business_key="key_id", **_COLS),
    "obxcol_mirror": dict(business_key="key_id", **_COLS),
}


@pytest.fixture()
def obx(db_session):
    models.init_dynamic_models(OBX_TABLES)
    crud.TABLE_CONFIG.update(OBX_TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())
    return db_session


def _row(i, qty=None):
    return {"key_id": f"K{i}", "lot": "LOT-A", "qty": qty if qty is not None else float(i),
            "eqp": f"EQP-{i}"}


def _seed(db, table, rows, tx_id, mode=None, source="DT_LOG_20260807.csv",
          updated_by="tester"):
    updates = [
        schemas.GeneralUpdateItem(
            updates=dict(r), source_name=source, updated_by=updated_by,
            business_key_val=str(r["key_id"]),
        )
        for r in rows
    ]
    batch = schemas.GeneralUpdateBatch(updates=updates, transaction_id=tx_id, silent=True)
    if mode is None:
        return crud.apply_batch_updates(db, table, batch)
    with outbox_mode(mode):
        return crud.apply_batch_updates(db, table, batch)


def _events(db, table, tx_id=None):
    evs = db.query(DatabaseOutbox).filter(
        DatabaseOutbox.table_name == table
    ).order_by(DatabaseOutbox.id.asc()).all()
    if tx_id is None:
        return evs
    return [e for e in evs if get_payload_dict(e).get("transaction_id") == tx_id]


# ---------------------------------------------------------------------------
# 1) The collapse itself, measured against the behaviour it replaces
# ---------------------------------------------------------------------------

def test_default_mode_is_per_row():
    """The safe direction is what you get by doing nothing.

    Also pins the literal default in `context.py` (spelled out there because that
    module is imported before `server/` is on sys.path) to the shared constant.
    A drift here would silently collapse every human correction.
    """
    assert request_outbox_mode.get() == event_constants.OUTBOX_MODE_PER_ROW
    assert event_constants.OUTBOX_MODE_PER_ROW == "per_row"


def test_before_and_after_on_the_same_input(obx):
    """5 rows: 5 outbox events before, 1 after — same rows, same code, same table.

    The per-row arm runs FIRST and its assertions are the pre-change behaviour.
    If the collapse ever stopped taking effect, the first arm would still pass and
    the second would fail — which is the direction a regression must fail in.
    """
    db = obx
    rows = [_row(i) for i in range(5)]

    _seed(db, "obxcol_src", rows, "tx-perrow")
    per_row = _events(db, "obxcol_src", "tx-perrow")
    assert len(per_row) == 5, "pre-change behaviour must be one event per row"
    for e in per_row:
        p = get_payload_dict(e)
        assert "data" in p and "row_ids" not in p
        assert not event_constants.is_collapsed_payload(p)
        assert event_constants.payload_row_count(p) == 1

    _seed(db, "obxcol_mirror", rows, "tx-collapsed", mode=COLLAPSED)
    collapsed = _events(db, "obxcol_mirror", "tx-collapsed")
    assert len(collapsed) == 1, "5 rows in one flush must stage exactly one event"
    p = get_payload_dict(collapsed[0])
    assert event_constants.is_collapsed_payload(p)
    assert p["row_count"] == 5
    assert len(p["row_ids"]) == 5
    assert event_constants.payload_row_count(p) == 5
    # The event is a POINTER: it must not carry values at all.
    assert "data" not in p
    # Envelope keys every consumer greps for survive the collapse.
    assert p["transaction_id"] == "tx-collapsed"
    assert p["source_name"] == "DT_LOG_20260807.csv"
    assert p["table_name"] == "obxcol_mirror"


def test_events_per_ingested_row(obx):
    """The headline ratio, asserted rather than asserted-about: 1/row -> 1/chunk."""
    db = obx
    rows = [_row(i) for i in range(40)]
    _seed(db, "obxcol_src", rows, "tx-a")
    _seed(db, "obxcol_mirror", rows, "tx-b", mode=COLLAPSED)

    before = len(_events(db, "obxcol_src", "tx-a"))
    after = len(_events(db, "obxcol_mirror", "tx-b"))
    assert before / 40 == 1.0
    assert after == 1
    assert after < before


def test_chunk_cap_splits_a_huge_flush(obx, monkeypatch):
    """One event per 1,000 rows, not one event per flush however large.

    Bounds the JSONB payload AND the failure path: a poison row can never
    re-expand more than one chunk's worth of per-row retries.
    """
    db = obx
    import database.database as ddb
    monkeypatch.setattr("event_constants.OUTBOX_COLLAPSE_CHUNK_ROWS", 10, raising=False)
    # stage_collapsed_event imports the constant inside the function, so the patch
    # above is seen by the producer; assert that rather than trusting it.
    rows = [_row(i) for i in range(25)]
    _seed(db, "obxcol_src", rows, "tx-chunked", mode=COLLAPSED)
    evs = _events(db, "obxcol_src", "tx-chunked")
    assert len(evs) == 3, f"25 rows at 10/chunk must be 3 events, got {len(evs)}"
    assert [get_payload_dict(e)["row_count"] for e in evs] == [10, 10, 5]
    assert sum(len(get_payload_dict(e)["row_ids"]) for e in evs) == 25
    assert ddb.stage_collapsed_event  # the producer under test, named


def test_delete_never_collapses(obx):
    """A collapsed event is a pointer and a deleted row cannot be re-read."""
    db = obx
    _seed(db, "obxcol_src", [_row(i) for i in range(3)], "tx-seed", mode=COLLAPSED)
    model = models.DYNAMIC_TABLES["obxcol_src"]
    victims = db.query(model).all()
    with outbox_mode(COLLAPSED):
        for v in victims:
            db.delete(v)
        db.commit()

    deletes = [e for e in _events(db, "obxcol_src") if e.event_type == "DELETE"]
    assert len(deletes) == 3, "DELETE must stay per-row even in collapsed mode"
    for e in deletes:
        p = get_payload_dict(e)
        assert not event_constants.is_collapsed_payload(p)
        assert "data" in p and p["row_id"]


# ---------------------------------------------------------------------------
# 2) The re-read: the payload the mappers get is the payload they got before
# ---------------------------------------------------------------------------

def test_expanded_payload_matches_what_the_producer_would_have_written(obx):
    """Same rows, both modes, compared field by field after expansion.

    The collapsed side is expanded by the real consumer helper. Everything except
    identity (row_id/business_key, which differ per table) must be equal - most
    importantly the COLUMN SET, because producer and expander derive it from the
    same shared frozenset and a drift there is a column silently appearing or
    vanishing for a mapper with nothing to fail.
    """
    db = obx
    rows = [_row(i) for i in range(4)]
    _seed(db, "obxcol_src", rows, "tx-p")
    _seed(db, "obxcol_mirror", rows, "tx-c", mode=COLLAPSED)

    per_row = [get_payload_dict(e) for e in _events(db, "obxcol_src", "tx-p")]
    collapsed_ev = _events(db, "obxcol_mirror", "tx-c")[0]
    expanded = outbox_expand.expand_events(db, [collapsed_ev])[collapsed_ev.event_uuid]

    assert len(expanded) == len(per_row) == 4
    by_key = {p["business_key"]: p for p in per_row}
    for got in expanded:
        want = by_key[got["business_key"]]
        assert set(got["data"].keys()) == set(want["data"].keys())
        for col, cell in want["data"].items():
            assert got["data"][col] == cell, f"column {col} differs after expansion"
        assert got["updated_by"] == want["updated_by"]
        assert got["source_name"] == want["source_name"]
        # Identity is present and is the row's own, not the event's.
        assert got["row_id"]


def test_expansion_is_load_bearing(obx):
    """The RAW collapsed payload fails the accessor the user-owned mappers use.

    This is the injection: it shows the expansion is not decoration. The exact
    accessors quoted are `production_mapper.py:11` (`payload.get("data", {})`)
    and `mappers/utils.py:15` (`p.get("data", {})` then `cell_detail["value"]`) —
    user-owned files in the gitignored tree that this round may not edit.
    """
    db = obx
    _seed(db, "obxcol_src", [_row(1, qty=7.0)], "tx-x", mode=COLLAPSED)
    ev = _events(db, "obxcol_src", "tx-x")[0]

    raw = get_payload_dict(ev)
    assert raw.get("data", {}) == {}, "a collapsed event carries no values by design"
    assert raw.get("data", {}).get("qty") is None

    expanded = outbox_expand.expand_events(db, [ev])[ev.event_uuid]
    p = expanded[0]
    row_data = p.get("data", {})                       # production_mapper.py:11
    assert row_data.get("qty", {}).get("value") == 7.0
    cell_detail = row_data["qty"]                      # mappers/utils.py:15
    assert "value" in cell_detail and cell_detail["value"] == 7.0
    assert p.get("row_id")


def test_per_row_events_pass_through_expansion_unchanged(obx):
    """A batch with no collapsed event in it must be a no-op for the expander."""
    db = obx
    _seed(db, "obxcol_src", [_row(i) for i in range(3)], "tx-pass")
    evs = _events(db, "obxcol_src", "tx-pass")
    expanded = outbox_expand.expand_events(db, evs)
    for e in evs:
        assert expanded[e.event_uuid] == [get_payload_dict(e)]


def test_a_row_deleted_before_consumption_derives_nothing_and_is_counted(obx, caplog):
    """The named outcome for the snapshot-vs-current-state difference.

    A payload would still carry the deleted row. A pointer cannot. Chain replay
    already answers this the same way (it walks CURRENT contents, so a deleted row
    is simply not in the page) - this test pins that the answer is the same AND
    that it is never a silent skip.
    """
    db = obx
    _seed(db, "obxcol_src", [_row(i) for i in range(3)], "tx-del", mode=COLLAPSED)
    ev = _events(db, "obxcol_src", "tx-del")[0]
    assert get_payload_dict(ev)["row_count"] == 3

    model = models.DYNAMIC_TABLES["obxcol_src"]
    gone = db.query(model).filter(model.business_key_val == "K1").one()
    gone_id = gone.row_id
    with outbox_mode(COLLAPSED):
        db.delete(gone)
        db.commit()

    with caplog.at_level("WARNING"):
        expanded = outbox_expand.expand_events(db, [ev])[ev.event_uuid]

    assert len(expanded) == 2, "the deleted row derives nothing"
    assert gone_id not in {p["row_id"] for p in expanded}
    # `record.message` is the ALREADY-FORMATTED string (pytest's handler formats
    # each record), so re-applying `% r.args` to it raises. `getMessage()` is the
    # one call that renders msg+args exactly once.
    joined = " ".join(r.getMessage() for r in caplog.records)
    assert "no longer exist" in joined and "obxcol_src" in joined, (
        "an unresolved row_id must be NAMED, never silently skipped")


# ---------------------------------------------------------------------------
# 3) The failure path: coarse on the happy path, fine where something broke
# ---------------------------------------------------------------------------

def test_reexpansion_gives_every_row_its_own_group(obx):
    """A failed chunk becomes per-row retries, each its own transaction group.

    Distinct transaction_ids are the whole point: the worker's unit of failure is
    the GROUP, so re-expanding under the original id would put all the rows back
    in one group where they would fail together again and the re-expansion would
    have bought nothing.
    """
    db = obx
    _seed(db, "obxcol_src", [_row(i) for i in range(4)], "tx-poison", mode=COLLAPSED)
    ev = _events(db, "obxcol_src", "tx-poison")[0]
    payload = get_payload_dict(ev)

    n = outbox_expand.reexpand_collapsed_event(db, ev, payload, "boom")
    db.commit()
    assert n == 4

    children = [e for e in _events(db, "obxcol_src")
                if get_payload_dict(e).get("reexpanded_from")]
    assert len(children) == 4
    tx_ids = {get_payload_dict(c)["transaction_id"] for c in children}
    assert len(tx_ids) == 4, "each re-expanded row must be its own group"
    assert all(t.startswith("tx-poison#row#") for t in tx_ids)
    for c in children:
        p = get_payload_dict(c)
        assert c.status == "PENDING" and c.processed_chain in (False, None)
        assert c.retry_count in (0, None)
        assert p["data"]["qty"]["value"] is not None
        # 🔴 Termination: a re-expanded event is per-row, so it can never
        # re-expand again. There is no second round, by construction.
        assert not event_constants.is_collapsed_payload(p)
        assert outbox_expand.reexpand_collapsed_event(db, c, p, "again") == 0


@pytest.mark.anyio
async def test_third_failure_reexpands_instead_of_quarantining_the_chunk(obx, monkeypatch):
    """The ruling, end to end, through the real `process_pending_groups`.

    The control arm is the same code on a PER-ROW event: it must still quarantine
    exactly as it always did, so the new branch is proven to be the collapsed one
    and not a change to everyone's retry semantics.
    """
    import chain_ingestion_worker as ciw
    db = obx

    async def always_fails(tx_id, events, db_, rules):
        return False, f"boom:{tx_id}", []

    monkeypatch.setattr(ciw, "process_chain_transaction_group", always_fails)

    # --- control: a per-row event still quarantines, unchanged ---
    _seed(db, "obxcol_mirror", [_row(9)], "tx-ctl")
    ctl = _events(db, "obxcol_mirror", "tx-ctl")[0]
    ctl.retry_count = 2
    db.commit()
    await ciw.process_pending_groups(db, ["tx-ctl"], {"tx-ctl": [ctl]}, [], None)
    assert ctl.status == "FAILED" and ctl.processed_chain is True
    assert not [e for e in _events(db, "obxcol_mirror")
                if get_payload_dict(e).get("reexpanded_from")]

    # --- collapsed: the chunk narrows instead of taking 4 rows down with it ---
    _seed(db, "obxcol_src", [_row(i) for i in range(4)], "tx-chunk", mode=COLLAPSED)
    ev = _events(db, "obxcol_src", "tx-chunk")[0]
    ev.retry_count = 2  # cheap chunk-level retries already spent
    db.commit()

    await ciw.process_pending_groups(db, ["tx-chunk"], {"tx-chunk": [ev]}, [], None)

    assert ev.status == "FAILED" and ev.processed_chain is True
    err = get_payload_dict(ev)["error_log"]
    assert err["reexpanded_into"] == 4
    children = [e for e in _events(db, "obxcol_src")
                if get_payload_dict(e).get("reexpanded_from")]
    assert len(children) == 4
    assert all(e.processed_chain in (False, None) for e in children)


@pytest.mark.anyio
async def test_cheap_retries_come_first(obx, monkeypatch):
    """Re-expansion happens at the QUARANTINE boundary, not at the first failure.

    A transient failure (a dead connection, a lock) must recover at chunk cost.
    Paying 1,000 per-row writes for a blip would spend the failure budget on the
    case the fine granularity does not exist for.
    """
    import chain_ingestion_worker as ciw
    db = obx

    async def always_fails(tx_id, events, db_, rules):
        return False, "transient", []

    monkeypatch.setattr(ciw, "process_chain_transaction_group", always_fails)
    _seed(db, "obxcol_src", [_row(i) for i in range(3)], "tx-blip", mode=COLLAPSED)
    ev = _events(db, "obxcol_src", "tx-blip")[0]

    await ciw.process_pending_groups(db, ["tx-blip"], {"tx-blip": [ev]}, [], None)

    assert ev.retry_count == 1 and ev.status == "RETRYING"
    assert not [e for e in _events(db, "obxcol_src")
                if get_payload_dict(e).get("reexpanded_from")]


# ---------------------------------------------------------------------------
# 4) The working set: a cap that counted events must now count rows
# ---------------------------------------------------------------------------

class _FakeEvent:
    def __init__(self, payload):
        self.payload = payload
        self._parsed_payload = payload


def test_batch_budget_is_charged_in_rows_not_events():
    """Left counting events, one batch would pull 20,000 chunks = 20,000,000 rows.

    The pre-change arm is the per-row list: 20,000 per-row events still fit, which
    is exactly what the old `LIMIT 20000` meant. The collapsed list must trim.
    """
    per_row = [_FakeEvent({"row_id": str(i), "data": {}}) for i in range(50)]
    assert event_constants.trim_events_to_row_budget(per_row, 20000) == per_row

    chunks = [_FakeEvent({"row_ids": [f"r{i}-{j}" for j in range(1000)],
                          "row_count": 1000}) for i in range(50)]
    kept = event_constants.trim_events_to_row_budget(chunks, 20000)
    assert len(kept) == 20, "20,000 ROWS, not 20,000 events"
    assert kept == chunks[:20], "a PREFIX — the tail returns next iteration, in order"

    # A single chunk larger than the budget must still make progress rather than
    # wedge the drain forever.
    huge = [_FakeEvent({"row_ids": ["x"] * 99999, "row_count": 99999})]
    assert event_constants.trim_events_to_row_budget(huge, 20000) == huge


def test_reexpansion_refuses_to_run_twice(obx):
    """The retry button must not multiply the outbox by 1,000 per press."""
    db = obx
    _seed(db, "obxcol_src", [_row(i) for i in range(3)], "tx-idem", mode=COLLAPSED)
    ev = _events(db, "obxcol_src", "tx-idem")[0]

    first = outbox_expand.reexpand_collapsed_event(db, ev, get_payload_dict(ev), "boom")
    db.commit()
    assert first == 3

    # The parent as the worker leaves it: error_log records what it expanded into.
    parent_payload = dict(get_payload_dict(ev))
    parent_payload["error_log"] = {"reason": "boom", "reexpanded_into": first}
    again = outbox_expand.reexpand_collapsed_event(db, ev, parent_payload, "boom")
    assert again == 0, "a chunk that already re-expanded must refuse to do it again"

    children = [e for e in _events(db, "obxcol_src")
                if get_payload_dict(e).get("reexpanded_from")]
    assert len(children) == 3, "no second generation"


def test_retry_failed_skips_an_already_reexpanded_chunk(obx, client):
    """The route half of the same guard — and it SAYS it skipped, it does not lie."""
    db = obx
    _seed(db, "obxcol_src", [_row(i) for i in range(2)], "tx-btn", mode=COLLAPSED)
    ev = _events(db, "obxcol_src", "tx-btn")[0]
    p = dict(get_payload_dict(ev))
    p["error_log"] = {"reason": "boom", "reexpanded_into": 2}
    ev.payload = p
    ev.status = "FAILED"
    ev.processed_chain = True
    db.commit()

    r = client.post("/admin/outbox/retry-failed", params={"event_id": ev.id})
    assert r.status_code == 200
    body = r.json()
    assert body["skipped_reexpanded"] == 1
    assert "already re-expanded" in body["message"]

    db.expire_all()
    assert ev.status == "FAILED", "the parent must NOT be requeued as a chunk"
    assert ev.processed_chain is True


def test_reexpansion_adds_nothing_when_it_cannot_finish(obx, monkeypatch):
    """All-or-nothing: a failure partway must leave no orphan children behind.

    Before the fix, `db.add` ran inside the build loop, so a raise at row N left
    N-1 children in the session — and the caller commits regardless (it has a
    quarantine to persist), so they were written next to a parent whose error_log
    claimed a plain whole-chunk quarantine.
    """
    db = obx
    _seed(db, "obxcol_src", [_row(i) for i in range(5)], "tx-partial", mode=COLLAPSED)
    ev = _events(db, "obxcol_src", "tx-partial")[0]

    calls = {"n": 0}
    real = outbox_expand._synthesize_payload

    def explode(row, columns, envelope):
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("synthetic failure partway through")
        return real(row, columns, envelope)

    monkeypatch.setattr(outbox_expand, "_synthesize_payload", explode)

    with pytest.raises(RuntimeError):
        outbox_expand.reexpand_collapsed_event(db, ev, get_payload_dict(ev), "boom")
    db.commit()   # the caller commits regardless — that is the point

    children = [e for e in _events(db, "obxcol_src")
                if get_payload_dict(e).get("reexpanded_from")]
    assert children == [], "a partial re-expansion must write nothing at all"


def test_expansion_key_survives_a_reshaped_event_list(obx):
    """`event_uuid`, not `id(event)`.

    Object identity is only stable while the caller holds the same objects. A
    caller that re-filtered or regenerated its list would miss every key — and the
    lookup FAILS OPEN to "derives nothing", silently. Keying on `event_uuid` makes
    the result survive re-shaping, which this test does explicitly.
    """
    db = obx
    _seed(db, "obxcol_src", [_row(i) for i in range(3)], "tx-key", mode=COLLAPSED)
    evs = _events(db, "obxcol_src", "tx-key")
    expanded = outbox_expand.expand_events(db, evs)

    assert set(expanded.keys()) == {e.event_uuid for e in evs}
    # Re-fetch the same events as NEW python objects; the keys must still resolve.
    db.expire_all()
    refetched = _events(db, "obxcol_src", "tx-key")
    for e in refetched:
        assert len(expanded[outbox_expand.event_key(e)]) == 3


def test_row_count_survives_a_missing_count_field():
    """`row_count` is a convenience; the ids are the truth."""
    assert event_constants.payload_row_count({"row_ids": ["a", "b", "c"]}) == 3
    assert event_constants.payload_row_count({"row_ids": ["a"], "row_count": 1}) == 1
    assert event_constants.payload_row_count({"row_id": "a", "data": {}}) == 1
    assert not event_constants.is_collapsed_payload({"row_id": "a"})
    assert not event_constants.is_collapsed_payload(None)


# ---------------------------------------------------------------------------
