"""Interaction score to completion — the CANONICAL instrument for SYSTEM_OVERVIEW
§1 core value #1 ("minimum-effort correction"), user-specified 2026-07-29.

The metric: how much human effort one completed correction cost.

    score(tx) = key*w_key + mouse*w_mouse + nav*w_nav      (lower is better)

Aggregated per SESSION first, then across sessions.

This value is NOT retroactively computable - there are no click logs for past
sessions. Whatever this measures before the UI overhaul is the only "before"
that will ever exist, so every decision that could silently make the number
wrong is pinned by a test here.
"""
import uuid
from datetime import datetime, timezone, timedelta

import pytest

from database import crud, models

# Session ids are namespaced so a test can never be confused with real traffic.
S1 = "effort_test_sess_1"
S2 = "effort_test_sess_2"


def _effort(db, *, session, key=0, mouse=0, nav=0, nav_preserved=0, tx=None, days_ago=1):
    db.add(models.InteractionEffortLog(
        transaction_id=tx or f"effort-tx-{uuid.uuid4()}",
        session_id=session,
        key_count=key, mouse_count=mouse, nav_count=nav,
        nav_preserved_count=nav_preserved,
        timestamp=datetime.now(timezone.utc) - timedelta(days=days_ago),
    ))


def _user_tx(db, tx, *, days_ago=1, source=None):
    """An audit row so the tx exists in the measured_ratio denominator."""
    db.add(models.AuditLog(
        table_name="effort_test_tbl", row_id="r1", column_name="a",
        old_value="before", new_value="after",
        source_name=source or crud.USER_SOURCE, updated_by="tester",
        transaction_id=tx,
        timestamp=datetime.now(timezone.utc) - timedelta(days=days_ago),
    ))


DEFAULT_W = {"key": 1, "mouse": 3, "nav": 5, "nav_preserved": 0}


def _stats(db, weights=None, window_days=7):
    db.commit()
    return crud.get_effort_stats(db, weights or DEFAULT_W, window_days=window_days)


# ── 1. Scoring ───────────────────────────────────────────────────────────────

def test_score_is_the_weighted_sum_of_raw_counts(db_session):
    """key=1, mouse=3, nav=5 - the user's scoring, applied at READ time."""
    _effort(db_session, session=S1, key=2, mouse=1, nav=1)   # 2 + 3 + 5 = 10
    s = _stats(db_session)
    assert s["avg_score"] == 10.0
    assert s["tx_count"] == 1
    assert s["session_count"] == 1


def test_weights_reinterpret_past_data_rather_than_freezing_it(db_session):
    """The stored row is RAW counts, so re-tuning weights re-reads history.

    If the score were computed at write time, every past transaction would stay
    frozen at the weights that happened to be configured that day and the
    before/after comparison this instrument exists for would be impossible.
    """
    _effort(db_session, session=S1, key=2, mouse=1, nav=1)

    assert _stats(db_session)["avg_score"] == 10.0                       # 2+3+5
    flat = _stats(db_session, weights={"key": 1, "mouse": 1, "nav": 1})
    assert flat["avg_score"] == 4.0, "same rows must re-score under new weights"
    assert flat["weights"] == {"key": 1.0, "mouse": 1.0, "nav": 1.0,
                               "nav_preserved": 0.0}, \
        "the weights used must be reported alongside the number"

    # And the stored row itself must still be raw - no score column, no rewrite.
    row = db_session.query(models.InteractionEffortLog).one()
    assert (row.key_count, row.mouse_count, row.nav_count) == (2, 1, 1)


# ── 1-bis. Context-preserving transitions are COUNTED, not discarded ─────────
#
# Lead addendum 2026-07-29. Classification must be a QUERY-time interpretation.
# Dropping exempted transitions at collection time bakes the exemption into the
# stored number - and because this metric cannot be recomputed retroactively, a
# classification error would make the only baseline we will ever have
# permanently wrong, with no second chance to collect it.

def test_preserved_transitions_score_zero_today(db_session):
    """Default nav_preserved weight is 0, so the published score is unchanged."""
    _effort(db_session, session=S1, key=2, mouse=1, nav=1, nav_preserved=4)
    assert _stats(db_session)["avg_score"] == 10.0, \
        "preserved transitions must not affect today's score"


def test_a_preserved_transition_can_be_re_scored_from_stored_rows(db_session):
    """THE point of storing it: re-classify later without new collection.

    If `nav_preserved` had simply never incremented anything, these rows would
    be indistinguishable from transactions with no screen movement at all and
    this re-scoring would be impossible forever.
    """
    _effort(db_session, session=S1, key=2, mouse=1, nav=1, nav_preserved=4)

    assert _stats(db_session)["avg_score"] == 10.0
    # Someone later decides those transitions did cost context after all.
    rescored = _stats(db_session, weights={"key": 1, "mouse": 3, "nav": 5,
                                           "nav_preserved": 5})
    assert rescored["avg_score"] == 30.0, "10 + 4 preserved moves x 5"
    assert rescored["weights"]["nav_preserved"] == 5.0


def test_preserved_count_is_stored_separately_from_the_counted_one(client, db_session):
    assert _put(client, {"session_id": S1, "key": 1, "mouse": 2,
                         "nav": 3, "nav_preserved": 4}).status_code == 200
    row = db_session.query(models.InteractionEffortLog).one()
    assert (row.key_count, row.mouse_count, row.nav_count,
            row.nav_preserved_count) == (1, 2, 3, 4), \
        "the two navigation kinds must never be merged into one number"


def test_a_client_that_does_not_send_nav_preserved_is_not_an_error(client, db_session):
    """Additive field: an older client omitting it stays valid, defaulting to 0."""
    res = _put(client, {"session_id": S1, "key": 1, "mouse": 2, "nav": 3})
    assert res.status_code == 200
    row = db_session.query(models.InteractionEffortLog).one()
    assert row.nav_preserved_count == 0


# ── 2. Aggregation unit: per-session average, THEN across sessions ───────────

def test_aggregation_is_per_session_average_not_per_transaction(db_session):
    """The user specified "세션별 평균". The two are NOT the same number.

    Session 1: one expensive correction (score 10).
    Session 2: three cheap ones (score 2 each).

      per-session:      (10 + 2) / 2 = 6.0      <- required
      naive per-tx:  (10+2+2+2) / 4 = 4.0      <- what a flat AVG() gives

    Averaging transactions lets one heavy session dominate the whole metric, so
    a day of bulk editing would look like a UI improvement.
    """
    _effort(db_session, session=S1, key=2, mouse=1, nav=1)      # 10
    for _ in range(3):
        _effort(db_session, session=S2, key=2, mouse=0, nav=0)  # 2

    s = _stats(db_session)
    assert s["avg_score"] == 6.0, "must average sessions, not transactions"
    assert s["avg_score"] != 4.0
    assert s["session_count"] == 2
    assert s["tx_count"] == 4, "tx_count still reports every measured transaction"


def test_one_busy_session_cannot_drown_out_the_others(db_session):
    """Regression guard on the same decision, at a scale where it bites."""
    _effort(db_session, session=S1, key=100, mouse=0, nav=0)     # 100, once
    for _ in range(200):
        _effort(db_session, session=S2, key=2, mouse=0, nav=0)   # 2, two hundred times

    s = _stats(db_session)
    assert s["avg_score"] == 51.0            # (100 + 2) / 2
    assert s["session_count"] == 2
    assert s["tx_count"] == 201


# ── 3. Absent effort is NOT MEASURED, and NOT zero ───────────────────────────

def test_unmeasured_transactions_do_not_enter_the_average(db_session):
    """Worker/ingestion/chain traffic has no human at the keyboard.

    Recording those as 0 would publish "effort 0" corrections that no person
    performed, pulling the average toward zero exactly as the surface got worse.
    They must be absent from the table, and visible only as coverage.
    """
    _effort(db_session, session=S1, key=2, mouse=1, nav=1)       # 10, measured
    _user_tx(db_session, "tx-measured")
    for i in range(9):                                           # 9 unmeasured user tx
        _user_tx(db_session, f"tx-unmeasured-{i}")

    s = _stats(db_session)
    assert s["avg_score"] == 10.0, "absent effort must not dilute the average"
    assert s["tx_count"] == 1
    assert s["measured_ratio"] == 0.1, "10% coverage must be reported, not hidden"


def test_empty_window_reports_no_score_rather_than_zero(db_session):
    """No sample must not render as a perfect score of 0."""
    s = _stats(db_session)
    assert s["avg_score"] is None
    assert s["tx_count"] == 0
    assert s["session_count"] == 0
    assert s["measured_ratio"] is None, "no denominator means no ratio, not 0.0"


# ── 4. measured_ratio - the mandatory coverage figure ────────────────────────

def test_measured_ratio_is_measured_over_total_human_transactions(db_session):
    _effort(db_session, session=S1, key=1, tx="tx-a")
    _effort(db_session, session=S1, key=1, tx="tx-b")
    _user_tx(db_session, "tx-a")
    _user_tx(db_session, "tx-b")
    _user_tx(db_session, "tx-c")
    _user_tx(db_session, "tx-d")

    assert _stats(db_session)["measured_ratio"] == 0.5


def test_automatic_transactions_are_not_in_the_coverage_denominator(db_session):
    """A parser flood must not make coverage look catastrophic.

    The denominator is human transactions only - the same positive USER_SOURCE
    match the re-correction rate uses, and for the same reason: parsers write
    under the ingested FILENAME, so the automatic source set is open-ended and
    can never be blacklisted.
    """
    _effort(db_session, session=S1, key=1, tx="tx-a")
    _user_tx(db_session, "tx-a")
    for i in range(50):
        _user_tx(db_session, f"tx-parser-{i}", source="some_ingested_file.csv")

    assert _stats(db_session)["measured_ratio"] == 1.0


def test_writes_outside_the_window_are_excluded(db_session):
    _effort(db_session, session=S1, key=2, mouse=1, nav=1, days_ago=30)
    _user_tx(db_session, "tx-old", days_ago=30)

    assert _stats(db_session, window_days=7)["tx_count"] == 0
    wide = _stats(db_session, window_days=60)
    assert wide["tx_count"] == 1
    assert wide["avg_score"] == 10.0


# ── 5. One row per transaction ───────────────────────────────────────────────

def test_a_retried_transaction_records_effort_once(db_session):
    """A client retry re-sends the same effort; it is not new human work.

    Counting it twice would inflate that session's transaction count with a
    duplicate score. First write wins.
    """
    ok1 = crud.record_interaction_effort(db_session, "tx-retry", S1, 2, 1, 1)
    ok2 = crud.record_interaction_effort(db_session, "tx-retry", S1, 99, 99, 99)

    assert ok1 is True
    assert ok2 is False, "the duplicate must be refused, not overwrite the first"
    rows = db_session.query(models.InteractionEffortLog).all()
    assert len(rows) == 1
    assert (rows[0].key_count, rows[0].mouse_count, rows[0].nav_count) == (2, 1, 1)


def test_recording_never_raises_into_the_correction_path(db_session, monkeypatch):
    """Instrumentation must not be able to fail the thing it instruments."""
    def boom(*a, **kw):
        raise RuntimeError("effort table is on fire")

    monkeypatch.setattr(db_session, "add", boom)
    assert crud.record_interaction_effort(db_session, "tx-x", S1, 1, 1, 1) is False


# ── 6. Config: weights and the transition allowlist ─────────────────────────

def test_defaults_apply_when_no_config_file_exists(tmp_path):
    import effort_metric
    missing = str(tmp_path / "nope.json")
    assert effort_metric.load_config(missing) == {}
    assert effort_metric.resolve_weights({}) == DEFAULT_W


def test_preserved_navigation_weight_defaults_to_zero():
    """Shipping it at 0 keeps today's score identical while the count accrues."""
    import effort_metric
    assert effort_metric.resolve_weights({})["nav_preserved"] == 0


def test_declared_weights_override_defaults(tmp_path):
    import effort_metric
    assert effort_metric.resolve_weights({"weights": {"mouse": 4}}) == \
        {"key": 1, "mouse": 4, "nav": 5, "nav_preserved": 0}


@pytest.mark.parametrize("bad", [-1, "3", None, True, float("nan"), float("inf")])
def test_an_unusable_weight_falls_back_instead_of_inverting_the_metric(bad):
    """A negative weight would mean "more clicking scores better"; a string or a
    NaN would take the aggregate down. Either way the key reverts to its default
    rather than publishing a meaningless average."""
    import effort_metric
    assert effort_metric.resolve_weights({"weights": {"mouse": bad}})["mouse"] == 3


def test_transitions_default_to_empty_so_every_move_is_counted(tmp_path):
    """DEFAULT IS COUNTED. The allowlist is a positive declaration only.

    Seeding it with guesses would bias the instrument optimistic in exactly the
    direction its owner would prefer.
    """
    import effort_metric
    assert effort_metric.resolve_context_preserving_transitions({}) == []
    assert effort_metric.resolve_context_preserving_transitions(
        {"context_preserving_transitions": None}) == []
    assert effort_metric.resolve_context_preserving_transitions(
        {"context_preserving_transitions": "doe->map"}) == [], "non-list must not be trusted"


def test_declared_transitions_are_served_verbatim():
    import effort_metric
    declared = {"context_preserving_transitions": [
        {"from": "doe", "to": "dt_map"},
        {"from": "grid"},                      # malformed - dropped
        "doe->dt_map",                         # malformed - dropped
    ]}
    assert effort_metric.resolve_context_preserving_transitions(declared) == [
        {"from": "doe", "to": "dt_map"}]


@pytest.mark.parametrize("wildcard", [
    {"from": "*", "to": "*"},
    {"from": "*", "to": "trace"},
    {"from": "grid", "to": "*"},
    {"from": "map_editor:*", "to": "grid"},
])
def test_wildcard_transitions_are_rejected_not_kept_as_inert_literals(wildcard):
    """Route matching is EXACT, so a wildcard matches nothing.

    Keeping it would be the worst of both worlds: a config author reads the
    file and believes a whole class of moves is exempt, while every one of them
    is still being charged the nav weight. The declaration and the behaviour
    would disagree with nothing to say so. Refusing it puts the disagreement in
    the log and leaves the entry out of GET /api/effort/config.
    """
    import effort_metric
    assert effort_metric.resolve_context_preserving_transitions(
        {"context_preserving_transitions": [wildcard]}) == []


def test_a_wildcard_does_not_take_valid_neighbours_down_with_it():
    import effort_metric
    declared = {"context_preserving_transitions": [
        {"from": "map_editor", "to": "map_editor:material"},
        {"from": "*", "to": "*"},
        {"from": "grid", "to": "trace"},
    ]}
    assert effort_metric.resolve_context_preserving_transitions(declared) == [
        {"from": "map_editor", "to": "map_editor:material"},
        {"from": "grid", "to": "trace"}]


def test_shipped_sample_config_matches_the_documented_defaults():
    """The .sample is what an operator copies - it must not disagree with code."""
    import json, os
    import effort_metric
    sample = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(
        effort_metric.__file__))), "server", "config", "sample",
        "effort_metric.json.sample")
    if not os.path.exists(sample):     # layout differs when run from server/
        sample = os.path.join(os.path.dirname(os.path.abspath(effort_metric.__file__)),
                              "config", "sample", "effort_metric.json.sample")
    with open(sample, encoding="utf-8") as f:
        raw = json.load(f)
    assert effort_metric.resolve_weights(raw) == DEFAULT_W
    assert effort_metric.resolve_context_preserving_transitions(raw) == [], \
        "the allowlist ships EMPTY - entries are proposed and approved, not invented"


# ── 7. Endpoint contract: GET /api/effort/config ────────────────────────────

def test_config_endpoint_is_the_single_client_facing_source(client):
    res = client.get("/api/effort/config")
    assert res.status_code == 200
    body = res.json()
    assert set(body) == {"weights", "context_preserving_transitions"}
    assert set(body["weights"]) == {"key", "mouse", "nav", "nav_preserved"}
    assert isinstance(body["context_preserving_transitions"], list)


# ── 8. Endpoint contract: PUT .../data/updates effort field ─────────────────

def _put(client, effort=None, value="EFF_1", effort_field="effort"):
    payload = {
        "updates": [{
            "business_key_val": value,
            "updates": {"EQP_ID": value},
            "source_name": "user",
            "updated_by": "tester",
        }],
        "silent": True,
    }
    if effort is not None:
        payload[effort_field] = effort
    return client.put("/tables/raw_table_1/data/updates", json=payload)


def _stored(db, business_key):
    """The value the correction was supposed to write, read back from the table."""
    M = models.DYNAMIC_TABLES["raw_table_1"]
    row = db.query(M).filter(M.business_key_val == business_key).first()
    return None if row is None else row.EQP_ID


def test_effort_is_optional_and_its_absence_writes_no_row(client, db_session):
    """The worker/ingestion path uses this same endpoint with no human present."""
    assert _put(client).status_code == 200
    assert db_session.query(models.InteractionEffortLog).count() == 0, \
        "absent effort must be NOT MEASURED - never a zero-effort row"


def test_a_measured_correction_stores_its_raw_counts_against_the_audit_tx(client, db_session):
    res = _put(client, {"session_id": S1, "key": 7, "mouse": 2, "nav": 1})
    assert res.status_code == 200
    assert res.json()["effort_recorded"] is True, \
        "the client clears its counters on this flag - it must mean a row was written"
    assert res.json()["effort_error"] is None

    row = db_session.query(models.InteractionEffortLog).one()
    assert (row.key_count, row.mouse_count, row.nav_count) == (7, 2, 1)
    assert row.session_id == S1
    # The key is the SAME tx id the audit trail already uses - no new correlation concept.
    audit_txs = {a.transaction_id for a in db_session.query(models.AuditLog)
                 .filter(models.AuditLog.source_name == crud.USER_SOURCE).all()}
    assert row.transaction_id in audit_txs


@pytest.mark.parametrize("bad_effort, why", [
    ({"session_id": S1, "key": -1, "mouse": 0, "nav": 0}, "negative"),
    ({"session_id": S1, "key": 0, "mouse": -5, "nav": 0}, "negative"),
    ({"session_id": S1, "key": 0, "mouse": 0, "nav": -1}, "negative"),
    ({"session_id": S1, "key": 0, "mouse": 0, "nav": 0, "nav_preserved": -2},
     "negative nav_preserved"),
    ({"session_id": S1, "key": 0, "mouse": 0, "nav": 0, "nav_preserved": "2"},
     "string nav_preserved"),
    ({"session_id": S1, "key": 1.5, "mouse": 0, "nav": 0}, "fractional"),
    ({"session_id": S1, "key": 3.0, "mouse": 0, "nav": 0}, "float-that-looks-whole"),
    ({"session_id": S1, "key": "4", "mouse": 0, "nav": 0}, "string"),
    ({"session_id": S1, "key": True, "mouse": 0, "nav": 0}, "bool-is-an-int-in-python"),
    ({"session_id": "", "key": 1, "mouse": 0, "nav": 0}, "empty session"),
    ({"session_id": "   ", "key": 1, "mouse": 0, "nav": 0}, "blank session"),
    ({"key": 1, "mouse": 0, "nav": 0}, "missing session_id"),
    ({"session_id": 12345, "key": 1, "mouse": 0, "nav": 0}, "non-string session_id"),
    ("nine", "effort is not even an object"),
    ([{"session_id": S1}], "effort is a list"),
])
def test_bad_counts_are_discarded_and_reported_but_never_clamped(client, db_session,
                                                                 bad_effort, why):
    """The count is refused. The CORRECTION is not (fix round F4, 2026-07-29).

    These used to be 400s raised before any write, so a client counter bug became a
    total data-entry outage: the operator's edit was rejected because the instrument
    measuring it was broken. A dropped counter costs one row in a metric; a rejected
    write costs a human their correction and violates core value #1 directly. Note
    "missing session_id" here - it returned 422 (not even the contracted 400) because
    the field was non-optional on the pydantic model, so it never reached the validator.
    """
    res = _put(client, bad_effort, value="EFF_KEEP")
    assert res.status_code == 200, f"{why} must not take the user's correction down"
    body = res.json()
    assert body["effort_recorded"] is False
    assert body["effort_error"], f"{why} must be reported, never silently swallowed"
    assert db_session.query(models.InteractionEffortLog).count() == 0, \
        f"{why} must not be stored in any coerced form"
    assert _stored(db_session, "EFF_KEEP") == "EFF_KEEP", \
        f"{why} must still have written the correction"


def test_an_unknown_effort_key_is_reported_by_name_not_silently_dropped(client, db_session):
    """A silently dropped value is indistinguishable from one never sent.

    Measured live: the client sent `nav_preserved` before the server declared
    it, pydantic discarded it, and nothing errored - `nav` was still right, so
    nothing LOOKED broken. This metric cannot be recomputed retroactively, so
    by the time such a gap is noticed the baseline for that period is gone.
    Client and server ship from this one repo, so a mismatch is a mistake and
    it should be loud.

    Loud in the RESPONSE and the LOG, though - not in the status code. Refusing the
    write would make the instrument able to destroy the operation it measures.
    """
    res = _put(client, {"session_id": S1, "key": 1, "mouse": 0, "nav": 0,
                        "scroll": 9, "drag_px": 120}, value="EFF_UNKNOWN_KEY")
    assert res.status_code == 200
    err = res.json()["effort_error"]
    assert "scroll" in err and "drag_px" in err, \
        "the offending key must be named - 'invalid payload' does not help anyone"
    assert res.json()["effort_recorded"] is False
    assert db_session.query(models.InteractionEffortLog).count() == 0
    assert _stored(db_session, "EFF_UNKNOWN_KEY") == "EFF_UNKNOWN_KEY"


def test_an_unknown_top_level_key_is_reported_rather_than_measuring_nothing(client, db_session):
    """`{"efort": {...}}` used to return a clean 200 with no measurement at all.

    Same class as the unknown key inside the blob, at the opposite end: one letter and
    the instrument is silently off for every save that page makes. The batch model
    accepted anything at the top level, so nothing could say so.
    """
    res = _put(client, {"session_id": S1, "key": 5, "mouse": 2, "nav": 0},
               value="EFF_TYPO", effort_field="efort")
    assert res.status_code == 200
    err = res.json()["effort_error"]
    assert "efort" in err, "the misspelled key must be named"
    assert "effort" in err, "and the reader must be told what it probably meant"
    assert res.json()["effort_recorded"] is False
    assert db_session.query(models.InteractionEffortLog).count() == 0, \
        "a misspelled field name means unmeasured - never a guessed measurement"
    assert _stored(db_session, "EFF_TYPO") == "EFF_TYPO"


def test_rejecting_unknown_keys_does_not_reject_missing_ones(client, db_session):
    """Absence stays legal - that is the whole 'unmeasured is not zero' contract."""
    assert _put(client, {"session_id": S1}).status_code == 200
    row = db_session.query(models.InteractionEffortLog).one()
    assert (row.key_count, row.mouse_count, row.nav_count,
            row.nav_preserved_count) == (0, 0, 0, 0)


def test_a_broken_counter_never_costs_the_user_their_correction(client, db_session):
    """The instrument must not be able to destroy the operation it measures.

    This test is the inverse of the one it replaces. The old contract validated before
    any write and returned 400, which read as "a bad metric cannot corrupt data" - but
    the real consequence was that a client-side counter bug refused every save the
    operator attempted. The correction is the product; the measurement is not.
    """
    before = db_session.query(models.AuditLog).count()
    res = _put(client, {"session_id": S1, "key": -3, "mouse": 0, "nav": 0},
               value="EFF_ALWAYS_LANDS")
    assert res.status_code == 200
    assert res.json()["change_count"] == 1
    assert db_session.query(models.AuditLog).count() > before, \
        "the correction must be applied even when the effort payload is refused"
    assert db_session.query(models.InteractionEffortLog).count() == 0, \
        "...and the refused counts must still not be stored"


# ── 8-bis. A no-op save must not report the effort as banked (F1) ────────────

def test_a_no_op_save_reports_that_the_effort_was_not_recorded(client, db_session):
    """The highest-friction event in the product used to score the LOWEST.

    Repeat the same value: crud's has_changed guard writes no audit log, so there is no
    completed correction to attribute the effort to and no row is written. The client
    saw `res.ok` and cleared its counters anyway, so the 20 keys and 5 clicks the
    operator spent on the failed attempt were ERASED - and the successful retry (3 keys,
    1 click) was recorded as the entire cost of a two-attempt correction. The metric was
    anti-correlated with exactly what core value #1 exists to detect.

    The recording condition itself stays as it was (a no-op is not a completed
    correction, and recording one would break measured_ratio's population match). What
    changes is that the response now tells the truth, so the client can keep counting.
    """
    first = _put(client, {"session_id": S1, "key": 3, "mouse": 1, "nav": 0},
                 value="EFF_NOOP")
    assert first.status_code == 200
    assert first.json()["effort_recorded"] is True

    # Byte-identical repeat: nothing changes, so nothing is logged, so nothing is banked.
    again = _put(client, {"session_id": S1, "key": 20, "mouse": 5, "nav": 0},
                 value="EFF_NOOP")
    assert again.status_code == 200
    body = again.json()
    assert body["change_count"] == 0 and body["created_logs"] == [], \
        "precondition: this repeat really is the no-op the bug rode on"
    assert body["effort_recorded"] is False, \
        "a save that recorded nothing must not tell the client its effort is banked"
    assert body["effort_error"] is None, \
        "a no-op is not a malformed payload - the blob was fine, there was nothing to bill"

    rows = db_session.query(models.InteractionEffortLog).all()
    assert len(rows) == 1 and (rows[0].key_count, rows[0].mouse_count) == (3, 1), \
        "the no-op must not have been recorded as a completed correction either"


def test_zero_effort_is_accepted_when_explicitly_declared(client, db_session):
    """Zero is a legitimate MEASURED value (a correction completed with no input
    of that kind). It is only the ABSENCE of the field that means not measured."""
    assert _put(client, {"session_id": S1, "key": 0, "mouse": 1, "nav": 0}).status_code == 200
    row = db_session.query(models.InteractionEffortLog).one()
    assert (row.key_count, row.mouse_count, row.nav_count) == (0, 1, 0)


# ── 9. Endpoint contract: /dashboard/summary ────────────────────────────────

def test_dashboard_summary_carries_score_weights_and_coverage(client, db_session):
    # Deliberately lopsided (1 tx vs 3) so the endpoint itself proves the
    # per-session unit: a flat per-tx average over these rows would read 4.0.
    _effort(db_session, session=S1, key=2, mouse=1, nav=1)       # 10
    for _ in range(3):
        _effort(db_session, session=S2, key=2, mouse=0, nav=0)   # 2 each
    for i in range(8):
        _user_tx(db_session, f"tx-{i}")
    db_session.commit()

    import main
    main.EFFORT_CACHE["value"] = None      # TTL cache must not serve a stale run

    res = client.get("/dashboard/summary")
    assert res.status_code == 200
    body = res.json()["effort"]
    assert body["avg_score"] == 6.0                    # (10 + 2) / 2, not 4.0
    assert body["tx_count"] == 4
    assert body["session_count"] == 2
    assert body["measured_ratio"] == 0.5
    assert body["weights"] == {"key": 1.0, "mouse": 3.0, "nav": 5.0,
                               "nav_preserved": 0.0}
    assert body["unavailable_reason"] is None
    main.EFFORT_CACHE["value"] = None


def test_dashboard_survives_a_failing_effort_query(client, db_session, monkeypatch):
    """Missing index / statement timeout must blank ONE cell, never 500 the page.

    Same discipline as the re-correction rate: a metric going dark is better
    than the dashboard going slow, and far better than a confident wrong number.
    """
    import main

    def boom(*a, **kw):
        raise RuntimeError("canceling statement due to statement timeout")

    monkeypatch.setattr(crud, "get_effort_stats", boom)
    main.EFFORT_CACHE["value"] = None
    main.RECORRECTION_CACHE["value"] = None

    res = client.get("/dashboard/summary")
    assert res.status_code == 200
    body = res.json()
    assert body["total_tables"] >= 1, "the rest of the dashboard still renders"
    assert body["effort"]["avg_score"] is None
    assert body["effort"]["measured_ratio"] is None, \
        "coverage must go dark too - a ratio without a score is unreadable"
    assert body["effort"]["unavailable_reason"]
    assert body["effort"]["weights"], "the configured weights are still reported"
    main.EFFORT_CACHE["value"] = None
    main.RECORRECTION_CACHE["value"] = None


def test_the_unavailable_reason_names_the_actual_cause_not_a_canned_timeout(
        client, db_session, monkeypatch):
    """It used to say "집계 시간 초과 또는 실패" for every failure mode.

    A missing column or a broken query therefore read as "the index is slow", sending
    whoever was on call to tune an index that was never the problem. A diagnostic that
    names the wrong cause is worse than an empty cell.
    """
    import main

    def boom(*a, **kw):
        raise RuntimeError("column interaction_effort_logs.nav_preserved_count does not exist")

    monkeypatch.setattr(crud, "get_effort_stats", boom)
    main.EFFORT_CACHE["value"] = None

    reason = client.get("/dashboard/summary").json()["effort"]["unavailable_reason"]
    assert "nav_preserved_count does not exist" in reason, "name the real failure"
    assert "RuntimeError" in reason
    assert "시간 초과" not in reason, "must not claim a timeout that did not happen"
    main.EFFORT_CACHE["value"] = None


def test_a_real_timeout_is_still_identified_as_one(client, db_session, monkeypatch):
    import main

    def boom(*a, **kw):
        raise RuntimeError("canceling statement due to statement timeout")

    monkeypatch.setattr(crud, "get_effort_stats", boom)
    main.EFFORT_CACHE["value"] = None

    reason = client.get("/dashboard/summary").json()["effort"]["unavailable_reason"]
    assert "시간 초과" in reason and "idx_effort_window" in reason, \
        "the timeout case must still point at the index that fixes it"
    main.EFFORT_CACHE["value"] = None


def test_a_failing_effort_query_does_not_take_the_recorrection_rate_with_it(
        client, db_session, monkeypatch):
    """The two instruments share one request; neither may poison the other's
    transaction (a timeout rollback is exactly how that happens)."""
    import main

    def boom(*a, **kw):
        raise RuntimeError("canceling statement due to statement timeout")

    _user_tx(db_session, "tx-1")
    _user_tx(db_session, "tx-2")
    db_session.commit()

    monkeypatch.setattr(crud, "get_effort_stats", boom)
    main.EFFORT_CACHE["value"] = None
    main.RECORRECTION_CACHE["value"] = None

    body = client.get("/dashboard/summary").json()
    assert body["effort"]["avg_score"] is None
    assert body["recorrection"]["measured_cells"] == 1, \
        "the re-correction rate must still be computed"
    assert body["recorrection"]["unavailable_reason"] is None
    main.EFFORT_CACHE["value"] = None
    main.RECORRECTION_CACHE["value"] = None
