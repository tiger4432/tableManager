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

    Bounds the JSONB payload AND the failure path: a poison row can never take
    more than one chunk FAILED with it.
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


def test_a_collapsed_event_that_loads_no_rows_is_refused_not_succeeded(obx):
    """🔴 ALL of them missing is a READ THAT FAILED, not an empty answer (S-158).

    A collapsed event NAMES its rows. If none can be read back, the mapper is handed an
    empty payload, does nothing, and the group would end SUCCESS - stamping the event
    processed while those rows derive NOTHING, with no error, no retry, no quarantine.
    Measured 2026-09-11: four events of 1,000 rows each went exactly that way and 3,000
    rows silently failed to reach their derived table, so this is pinned rather than
    trusted to the warning that was already being logged beside it.

    ⚠️ THE PARTIAL CASE IS THE TEST ABOVE, AND STAYS A SUCCESS. Some rows deleted
    between write and consumption is a legitimate answer the warning names; the refusal
    is narrowed to the all-missing shape so it cannot swallow that one.
    """
    from chain import ingestion_worker as ciw
    db = obx

    _seed(db, "obxcol_src", [_row(i) for i in range(3)], "tx-blind", mode=COLLAPSED)
    ev = _events(db, "obxcol_src", "tx-blind")[0]
    named = list(get_payload_dict(ev)["row_ids"])
    assert len(named) == 3

    model = models.DYNAMIC_TABLES["obxcol_src"]
    with outbox_mode(COLLAPSED):
        for row in db.query(model).filter(model.row_id.in_(named)).all():
            db.delete(row)
        db.commit()

    rules = [{"name": "obxcol_blind", "trigger_table": "obxcol_src",
              "target_table": "obxcol_mirror", "enabled": True}]
    ok, reason, _msgs = ciw._process_chain_transaction_group_sync("tx-blind", [ev], db, rules)

    assert ok is False, "a group that could read NONE of its named rows must not succeed"
    assert "rows_not_visible" in (reason or ""), reason
    assert str(len(named)) in (reason or ""), "the refusal says how many rows were lost"
    assert ev.processed_chain is not True, "a refused group leaves the event to retry"


# ---------------------------------------------------------------------------
# 3) The failure path: a chunk fails whole (test_a_failed_chunk_goes_failed_whole)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_unreadable_rows_are_deferred_without_charging_a_retry(obx, monkeypatch):
    """🔴 A DEFERRAL IS NOT AN ATTEMPT (S-160, 판정 267).

    Measured: rows an event names become readable in under 100 ms - the same session that
    saw none sees all of them on the next look. So a group refused for `rows_not_visible`
    was never TRIED; charging `retry_count` for it would quarantine a good chunk at the
    default cap of 1 - leaving 1,000 rows FAILED to wait out a sub-second window.

    ⚠️ THE CAP IS THE OTHER HALF. "Defer forever" is the same silent loss one room over,
    just in the queue instead of the ledger, so this also pins that the patience ENDS.
    """
    from chain import ingestion_worker as ciw
    db = obx
    monkeypatch.setattr(ciw, "_RULES_DOCUMENT", {"max_rows_not_visible_defers": 3})
    ciw._ROWS_NOT_VISIBLE_DEFERS.clear()

    _seed(db, "obxcol_src", [_row(i) for i in range(3)], "tx-defer", mode=COLLAPSED)
    ev = _events(db, "obxcol_src", "tx-defer")[0]
    named = list(get_payload_dict(ev)["row_ids"])
    model = models.DYNAMIC_TABLES["obxcol_src"]
    with outbox_mode(COLLAPSED):
        for row in db.query(model).filter(model.row_id.in_(named)).all():
            db.delete(row)
        db.commit()

    rules = [{"name": "obxcol_blind", "trigger_table": "obxcol_src",
              "target_table": "obxcol_mirror", "enabled": True}]
    before = len(_events(db, "obxcol_src"))

    for expected in (1, 2):
        await ciw.process_pending_groups(db, ["tx-defer"], {"tx-defer": [ev]}, rules, None)
        assert ev.processed_chain is not True, "a deferred event stays in the queue"
        assert (ev.retry_count or 0) == 0, "a deferral must not be charged as an attempt"
        assert ciw._ROWS_NOT_VISIBLE_DEFERS.get("tx-defer") == expected

    assert len(_events(db, "obxcol_src")) == before, "a deferral writes no new event"

    # ⚠️ THE CAP: the third pass stops deferring and refuses for real.
    await ciw.process_pending_groups(db, ["tx-defer"], {"tx-defer": [ev]}, rules, None)
    assert "tx-defer" not in ciw._ROWS_NOT_VISIBLE_DEFERS, "the patience is released"
    assert (ev.retry_count or 0) >= 1, "at the cap it becomes a real, counted attempt"


@pytest.mark.anyio
async def test_cheap_retries_come_first(obx, monkeypatch):
    """Quarantine happens at the declared cap, not at the first failure.

    A transient failure (a dead connection, a lock) must recover at chunk cost,
    not take 1,000 rows FAILED for a blip.
    """
    from chain import ingestion_worker as ciw
    db = obx

    async def always_fails(tx_id, events, db_, rules):
        return False, "transient", []

    monkeypatch.setattr(ciw, "process_chain_transaction_group", always_fails)
    # ⚠️ THESE MEASURE RETRY/HOL MECHANICS, NOT THE DEFAULT (S-139). The cap moved
    # to 1, so the declaration keeps this test's SUBJECT intact - and doubles as
    # the ruling's gate that 「3 을 적으면 옛 동작」 is literally true.
    from chain import ingestion_worker as _ciw
    monkeypatch.setattr(_ciw, "_RULES_DOCUMENT", {"max_group_attempts": 3})
    _seed(db, "obxcol_src", [_row(i) for i in range(3)], "tx-blip", mode=COLLAPSED)
    ev = _events(db, "obxcol_src", "tx-blip")[0]
    before = len(_events(db, "obxcol_src"))

    await ciw.process_pending_groups(db, ["tx-blip"], {"tx-blip": [ev]}, [], None)

    assert ev.retry_count == 1 and ev.status == "RETRYING"
    assert len(_events(db, "obxcol_src")) == before, "a retry writes no new event"


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


def test_retry_failed_skips_an_already_reexpanded_chunk(obx, client):
    """A chunk split BEFORE the split retired (총괄 c9ee06b34) is not requeued as a chunk -
    and the route SAYS it skipped, it does not lie. A queue may still hold one."""
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


# ---------------------------------------------------------------------------
# 사건이 «들고 다니는» 키 — 확장을 넘어서 사나
# ---------------------------------------------------------------------------

def test_an_expanded_child_keeps_the_hop_count_it_was_born_with():
    """🔴 실측된 구멍이다(2026-09-22). `synthesize_payload` 는 키 일곱으로 «닫혀» 있었고
    `chain_depth` 가 그 안에 없어서, 재확장된 행이 깊이를 «잃었다».

    잃으면 `chain_depth_of` 가 `None` 을 돌려주고, 그 독스트링이 `None` 을 「체인 밖」이라
    정의한다 — 즉 **재확장된 행에 홉 상한이 안 걸린다.** 도달 가능한 이유는
    `database.py` 가 묶음 이벤트에 깊이를 «일부러 찍기» 때문이다: 체인이 낳은 묶음이
    있다는 뜻이고, 확장이 그것을 도로 지우고 있었다.

    ⚠️ 「루프가 실제로 났다」는 «안 쟀다». 이 줄이 고정하는 것은 「상한이 걸린다」까지다.
    """
    from outbox_expand import synthesize_payload
    import event_constants as ec

    env = {"transaction_id": "tx", "updated_by": "u", "source_name": "s",
           "timestamp": "t", ec.CHAIN_DEPTH_KEY: 3}
    out = synthesize_payload("r1", "bk1", {"c": "v"}, env)

    assert ec.chain_depth_of(out) == 3, (
        "확장된 자식이 깊이를 잃었다 — 이 행에는 홉 상한이 «안 걸린다»")


def test_an_expanded_child_keeps_the_one_rule_it_was_restricted_to():
    """확장은 «같은 사건이 모양만 바뀌는» 것이라 제한이 따라가야 한다.

    잃으면 그 표의 «모든» 규칙이 깨어난다 — 리플레이가 막으려던 것의 정반대이고
    역시 아무 오류도 안 난다.
    """
    from outbox_expand import synthesize_payload
    import event_constants as ec

    env = {"transaction_id": "tx", ec.ONLY_RULE_KEY: "rule_x"}
    out = synthesize_payload("r1", "bk1", {"c": "v"}, env)

    assert ec.only_rule_of(out) == "rule_x"


def test_a_key_that_was_not_there_does_not_appear_as_none():
    """⛔ 「키 없음」과 「값이 None」은 «다른 상태»다. 둘을 접으면 부재가 «선언»이 된다.

    `chain_depth_of` 의 독스트링이 그 이유를 든다 — 「No key -> None (outside the chain)」.
    `None` 을 «써 넣으면» 읽는 쪽 답은 같아 보여도, 그 행은 이제 「체인이 깊이를 안 셌다」가
    아니라 「깊이가 없다고 «적힌»」 행이 된다.
    """
    from outbox_expand import synthesize_payload
    import event_constants as ec

    out = synthesize_payload("r1", "bk1", {"c": "v"}, {"transaction_id": "tx"})

    assert ec.CHAIN_DEPTH_KEY not in out
    assert ec.ONLY_RULE_KEY not in out
    assert ec.chain_depth_of(out) is None
    assert ec.only_rule_of(out) is None


def test_the_chain_does_not_hand_its_restriction_to_the_rows_it_writes():
    """🔴 자식이 «둘»이고 답이 반대다.

    확장 자식(위 둘)은 «가져가고», 체인이 낳은 자식은 «버려야» 한다 — 규칙 X 가 표 B 에
    써서 난 행에까지 「X 만」이 붙으면, X 는 B 를 안 보므로 리플레이가 한 홉만 돌고
    «조용히» 끝난다.

    구조로 그렇게 된다: 체인의 쓰기는 `stage_event` 를 지나고 그 봉투(`_outbox_envelope`)는
    ContextVar 넷만 읽는다 — 제한은 거기 «없다». 이 줄은 그 부재를 «고정»한다.
    ⚠️ 그래서 제한을 ContextVar 로 만들면 이 줄이 빨개진다. 그것이 이 시험의 일이다.
    """
    import inspect

    from database import database as db_mod
    import event_constants as ec

    envelope_src = inspect.getsource(db_mod._outbox_envelope)
    assert ec.ONLY_RULE_KEY not in envelope_src, (
        "봉투가 제한을 나르기 시작했다 — 체인이 낳은 행이 그것을 «물려받으면» "
        "리플레이가 한 홉만 돌고 멈춘다")
