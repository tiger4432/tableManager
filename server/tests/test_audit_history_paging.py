"""Row/cell audit history is CAPPED, and the cap SAYS SO.

These endpoints used to end in `.order_by(timestamp.desc()).all()` - no LIMIT -
so one row click loaded that row's entire audit history. Measured on the
isolated `assy_qa` copy 2026-08-11 against a 300,019-entry row: 3,462 ms and
~54 MB of column text per click, before pydantic saw a row.

What is pinned here, and why each one is a way the fix could be green and wrong:

  * The page is capped at the CONFIGURED size, not a source literal.
  * A capped page SAYS `truncated: true` and carries `next_cursor`. A cap that
    looks identical to a complete answer is a wrong answer, not a slow one.
  * A complete page says `truncated: false` and carries NO cursor - otherwise
    the client's 더 보기 never turns off.
  * Paging with the cursor visits every row EXACTLY ONCE, including across a
    timestamp TIE. Ties are the normal case (one transaction stamps every audit
    row from the same `now()`), and they are precisely what a timestamp-only
    cursor gets wrong - so the tie fixture here is not decoration, it is the
    defect axis. Written with an EXPLICIT identical timestamp rather than by
    hoping a fast loop produces one.
  * A garbage cursor is a 400, not a silent restart from page 1.
  * Only ONE route is registered per history path (a second, unreachable
    `get_cell_history` used to sit further down main.py).
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

import audit_history
from database import models

TABLE = "raw_table_1"


def _seed(db, n, row_id=None, column="EQP_ID", tie_size=1, base=None):
    """`n` audit rows on one row_id, newest last. `tie_size` rows share a timestamp."""
    row_id = row_id or str(uuid.uuid4())
    base = base or datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(n):
        db.add(models.AuditLog(
            table_name=TABLE, row_id=row_id, column_name=column,
            old_value=f"old{i}", new_value=f"new{i}",
            source_name="probe", updated_by="probe",
            transaction_id=f"tx{i // max(tie_size, 1)}",
            timestamp=base + timedelta(seconds=i // max(tie_size, 1)),
        ))
    db.commit()
    return row_id


def _page(client, url, **params):
    r = client.get(url, params=params)
    assert r.status_code == 200, r.text
    return r.json()


# --------------------------------------------------------------------------
# The cap itself
# --------------------------------------------------------------------------

def test_row_history_is_capped_and_says_so(client, db_session, monkeypatch):
    monkeypatch.setattr(audit_history, "load_config",
                        lambda path=None: {"default_limit": 10, "max_limit": 50})
    row_id = _seed(db_session, 25)

    page = _page(client, f"/tables/{TABLE}/rows/{row_id}/history")
    assert page["limit"] == 10
    assert page["returned"] == 10 == len(page["logs"])
    assert page["truncated"] is True
    assert page["next_cursor"]


def test_complete_history_is_not_marked_truncated(client, db_session, monkeypatch):
    """The other half of the invariant. Without this, `truncated: True` always
    would pass the test above while making 더 보기 an infinite button."""
    monkeypatch.setattr(audit_history, "load_config",
                        lambda path=None: {"default_limit": 10, "max_limit": 50})
    row_id = _seed(db_session, 10)  # exactly the page size - the off-by-one case

    page = _page(client, f"/tables/{TABLE}/rows/{row_id}/history")
    assert page["returned"] == 10
    assert page["truncated"] is False
    assert page["next_cursor"] is None


def test_the_cap_comes_from_config_not_from_source(client, db_session, monkeypatch):
    """Two different declarations produce two different pages over one fixture."""
    row_id = _seed(db_session, 30)
    for declared in (3, 7):
        monkeypatch.setattr(audit_history, "load_config",
                            lambda path=None, d=declared: {"default_limit": d, "max_limit": 50})
        page = _page(client, f"/tables/{TABLE}/rows/{row_id}/history")
        assert page["limit"] == declared
        assert page["returned"] == declared


def test_requested_limit_is_clamped_to_max_not_refused(client, db_session, monkeypatch):
    """`?limit=100000` must not restore the unbounded fetch - and must not 400
    either, or one stale client breaks the sidebar."""
    monkeypatch.setattr(audit_history, "load_config",
                        lambda path=None: {"default_limit": 10, "max_limit": 20})
    row_id = _seed(db_session, 40)

    page = _page(client, f"/tables/{TABLE}/rows/{row_id}/history", limit=100000)
    assert page["limit"] == 20
    assert page["returned"] == 20
    assert page["truncated"] is True


# --------------------------------------------------------------------------
# The cursor
# --------------------------------------------------------------------------

@pytest.mark.parametrize("tie_size", [1, 7])
def test_paging_visits_every_row_exactly_once(client, db_session, monkeypatch, tie_size):
    """tie_size=7 puts seven rows on the SAME timestamp - the case a
    timestamp-only cursor duplicates or drops."""
    monkeypatch.setattr(audit_history, "load_config",
                        lambda path=None: {"default_limit": 5, "max_limit": 50})
    total = 23
    row_id = _seed(db_session, total, tie_size=tie_size)

    seen, cursor, pages = [], None, 0
    while True:
        params = {"cursor": cursor} if cursor else {}
        page = _page(client, f"/tables/{TABLE}/rows/{row_id}/history", **params)
        seen.extend(log["id"] for log in page["logs"])
        pages += 1
        assert pages < 20, "paging did not terminate"
        if not page["truncated"]:
            assert page["next_cursor"] is None
            break
        cursor = page["next_cursor"]

    expected = [r.id for r in db_session.query(models.AuditLog)
                .filter(models.AuditLog.row_id == row_id)
                .order_by(models.AuditLog.timestamp.desc(), models.AuditLog.id.desc()).all()]
    assert len(seen) == total
    assert len(set(seen)) == total, "a row was returned on two pages"
    assert seen == expected, "paging order diverged from the endpoint's own sort"


def test_tie_fixture_actually_produces_ties(db_session):
    """The guard on the test above. A tie fixture that produced no ties would
    make `tie_size=7` a silent duplicate of `tie_size=1` - green, and testing
    nothing. (server-pm memory: an alarm that was never made to ring.)"""
    row_id = _seed(db_session, 14, tie_size=7)
    stamps = [r.timestamp for r in db_session.query(models.AuditLog)
              .filter(models.AuditLog.row_id == row_id).all()]
    assert len(stamps) == 14
    assert len(set(stamps)) == 2, f"expected 2 distinct timestamps, got {len(set(stamps))}"


def test_a_bad_cursor_is_refused_not_ignored(client, db_session, monkeypatch):
    """Silently ignoring it would answer page 1 while the client believes it got
    page 2 - a 더 보기 loop that appends the same rows forever."""
    monkeypatch.setattr(audit_history, "load_config",
                        lambda path=None: {"default_limit": 5, "max_limit": 50})
    row_id = _seed(db_session, 12)
    for bad in ("not-base64!!",     # not base64url at all
                "Zm9vYmFy",         # valid base64url, payload is not "timestamp|id"
                "MjAyNi0wMS0wMXxi"  # right shape, id is not an integer
                ):
        r = client.get(f"/tables/{TABLE}/rows/{row_id}/history", params={"cursor": bad})
        assert r.status_code in (400, 422), f"{bad!r} -> {r.status_code} {r.text}"

    # `?cursor=` is NOT a lost position - it is what a client with no cursor yet
    # produces by interpolating an empty variable, and `next_cursor` is never "".
    # First page, deliberately. See audit_history.apply_cursor.
    r = client.get(f"/tables/{TABLE}/rows/{row_id}/history", params={"cursor": ""})
    assert r.status_code == 200
    assert r.json()["returned"] == 5


def test_cursor_round_trips_naive_and_aware_timestamps():
    """PostgreSQL hands back aware datetimes for this column and SQLite naive
    ones, and the decoded value is bound straight back against that column.
    Normalising here would compare two different things on one of the two."""
    for ts in (datetime(2026, 1, 2, 3, 4, 5, 678901),
               datetime(2026, 1, 2, 3, 4, 5, 678901, tzinfo=timezone.utc)):
        token = audit_history.encode_cursor(ts, 42)
        got_ts, got_id = audit_history.decode_cursor(token)
        assert (got_ts, got_id) == (ts, 42)
        assert "+" not in token and "/" not in token, "cursor must survive a query string"


# --------------------------------------------------------------------------
# The cell endpoint, and the duplicate route that used to shadow it
# --------------------------------------------------------------------------

def test_cell_history_is_capped_and_scoped_to_the_column(client, db_session, monkeypatch):
    monkeypatch.setattr(audit_history, "load_config",
                        lambda path=None: {"default_limit": 4, "max_limit": 50})
    row_id = str(uuid.uuid4())
    _seed(db_session, 12, row_id=row_id, column="EQP_ID")
    _seed(db_session, 12, row_id=row_id, column="other_col")

    page = _page(client, f"/tables/{TABLE}/rows/{row_id}/cells/EQP_ID/history")
    assert page["returned"] == 4
    assert page["truncated"] is True
    assert {log["column_name"] for log in page["logs"]} == {"EQP_ID"}


def test_only_one_route_serves_each_history_path():
    """A second `get_cell_history` was registered on this path and had never run.
    A duplicate route's reliable product is a fix applied to the dead copy."""
    from main import app
    for path in ("/tables/{table_name}/rows/{row_id}/history",
                 "/tables/{table_name}/rows/{row_id}/cells/{col_name}/history"):
        registered = [r for r in app.routes if getattr(r, "path", None) == path]
        assert len(registered) == 1, f"{path} has {len(registered)} registrations"
        assert registered[0].response_field is not None, f"{path} lost its response_model"


# --------------------------------------------------------------------------
# Config handling
# --------------------------------------------------------------------------

def test_malformed_knobs_fall_back_to_the_shipped_value():
    for bad in ({"default_limit": "200"}, {"default_limit": 0},
                {"default_limit": -5}, {"default_limit": True}):
        assert audit_history.resolve_settings(bad)["default_limit"] == \
            audit_history.DEFAULTS["default_limit"]


def test_default_limit_is_clamped_to_max_limit():
    s = audit_history.resolve_settings({"default_limit": 900, "max_limit": 100})
    assert s["default_limit"] == 100


def test_missing_config_file_is_normal_operation(tmp_path):
    assert audit_history.load_config(str(tmp_path / "nope.json")) == {}
    assert audit_history.resolve_settings(audit_history.load_config(
        str(tmp_path / "nope.json"))) == audit_history.DEFAULTS
