"""[7c] `"transfer_log": "none"` — declared-absent consumption.

The user site records NO bonding-consumption log at all. Declaring the exact
string "none" states that fact, and the engine must answer with a bounded
presentation instead of a degradation:

  * sources.transfer_log = "connected(untracked)"  (NOT missing / degraded)
  * chips.remaining stays null, chips.remaining_upper_bound = total − fail
  * chips.transferred = null (unknown — never a fake 0)
  * a DISTINCT warning `transfer_untracked` (effect remaining_upper_bound) so
    the client can render "≤N" instead of 미상
  * by_core used/remaining = null; bins entries flagged with per-bin bounds
  * ONLY the exact string "none" declares this — JSON null and an absent key
    stay exactly the accidental-missing behavior of before.

Fixtures are the shared tp_test_* scenario (total 8, fail-union 4, seeded
bonding_log rows that must be IGNORED once consumption is declared untracked —
if the declaration were quietly resolved as a binding, transferred would be 3
and remaining 2, which is exactly what these tests refuse).
"""
import json
import uuid

import pytest

import transfer_plan
from database import crud, models

from test_transfer_plan import (TP_TABLES, _tp_config, _write_cfg,
                                _seed_scenario, _seed_bins, _seed_region,
                                _region_params)


def _env(db_session, tmp_path, monkeypatch, transfer_log="none"):
    """tp_test_* env with the bonding stage's transfer_log swapped."""
    models.init_dynamic_models(TP_TABLES)
    crud.TABLE_CONFIG.update(TP_TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())
    cfg = _tp_config()
    src = cfg["stages"]["bonding"]["source"]
    if transfer_log is _ABSENT:
        del src["transfer_log"]
    else:
        src["transfer_log"] = transfer_log
    _write_cfg(tmp_path, monkeypatch, tp_cfg=cfg)
    return db_session


_ABSENT = object()


@pytest.fixture()
def untracked_env(db_session, tmp_path, monkeypatch):
    return _env(db_session, tmp_path, monkeypatch, transfer_log="none")


def _summary(client, **extra):
    params = {"stage": "bonding", "lot": "TAPE-X", "slot": "01"}
    params.update(extra)
    res = client.get("/api/transfer-plan/source-summary", params=params)
    assert res.status_code == 200
    return res.json()


# ---------------------------------------------------------------------------
# Declared state — status, upper bound, distinct warning
# ---------------------------------------------------------------------------


def test_stages_report_untracked_not_missing(untracked_env, client):
    body = client.get("/api/transfer-plan/stages").json()
    bonding = next(s for s in body["stages"] if s["name"] == "bonding")
    assert bonding["roles"]["transfer_log"] == "connected(untracked)"


def test_untracked_serves_upper_bound_not_a_number(untracked_env, client):
    _seed_scenario(untracked_env)
    body = _summary(client)

    chips = body["chips"]
    assert body["sources"]["transfer_log"] == "connected(untracked)"
    assert chips["total"] == 8
    # fixture activation: the fail axis must be live, or the bound is just total
    assert sum(chips["fail_breakdown"].values()) == 4
    assert chips["transferred"] is None          # unknown — NOT 0, NOT 3
    assert chips["remaining"] is None            # no exact number exists
    assert chips["remaining_reliable"] is False
    assert chips["remaining_upper_bound"] == 4   # total − |fail-union|

    warns = body["warnings"]
    untracked = [w for w in warns if w.get("type") == "transfer_untracked"]
    assert len(untracked) == 1
    assert untracked[0]["role"] == "transfer_log"
    assert untracked[0]["effect"] == "remaining_upper_bound"
    # declared state, not a degradation — no source_degraded for this role
    assert not any(w.get("type") == "source_degraded"
                   and w.get("role") == "transfer_log" for w in warns)


def test_untracked_by_core_used_and_remaining_are_null(untracked_env, client):
    _seed_scenario(untracked_env)
    body = _summary(client)
    assert body["by_core_origin"] == "log"
    for core in body["by_core"]:
        assert core["total"] is not None
        assert core["fail"] is not None          # fail projection is unaffected
        assert core["used"] is None              # unknowable, never fake 0
        assert core["remaining"] is None


def test_untracked_region_transferred_is_null(untracked_env, client):
    _seed_scenario(untracked_env)
    _seed_region(untracked_env, "BASE-R", ("TAPE-X", "01"),
                 [(1, 1), (2, 1), (3, 1), (4, 1)])
    untracked_env.commit()
    body = _summary(client, **_region_params("BASE-R"))
    rc = body["region_chips"]
    assert rc["transferred"] is None
    assert rc["reliable"] is False


# ---------------------------------------------------------------------------
# BIN axis — per-bin upper bounds with the flag
# ---------------------------------------------------------------------------


def test_untracked_bins_serve_per_bin_upper_bounds(untracked_env, client):
    """BIN 1 = row y=1 {4 cells}, fail∩ = {(1,1),(2,1)} → bound 2 (same for
    BIN 2). The seeded bonding_log rows would have blocked (3,1)/(4,2)/(2,1);
    an implementation that still consumed them would emit 1, not 2 — the bound
    must come from total − fail ONLY."""
    _seed_scenario(untracked_env)
    _seed_bins(untracked_env)
    body = _summary(client, bins="")
    bins = body["bins"]
    assert bins["axis"] == "connected"
    by_bin = {e["bin"]: e for e in bins["entries"]}
    for b in (1, 2):
        e = by_bin[b]
        assert e["transfer_untracked"] is True
        assert e["transferred"] is None
        assert e["remaining"] is None
        assert e["remaining_upper_bound"] == 2
        assert e["reliable"] is False
        assert e["total"] == 4


def test_untracked_bin_absent_is_still_absent(untracked_env, client):
    _seed_scenario(untracked_env)
    _seed_bins(untracked_env)
    body = _summary(client, bins="7")
    (entry,) = body["bins"]["entries"]
    assert entry["status"] == "bin_absent"
    assert "transfer_untracked" not in entry
    assert "remaining_upper_bound" not in entry


# ---------------------------------------------------------------------------
# Accidental missing stays EXACTLY as before — "none" is the only declaration
# ---------------------------------------------------------------------------


def _assert_accidental_missing(client):
    body = _summary(client)
    assert body["sources"]["transfer_log"] == "missing"
    warns = body["warnings"]
    assert any(w.get("type") == "source_degraded"
               and w.get("role") == "transfer_log" for w in warns)
    assert not any(w.get("type") == "transfer_untracked" for w in warns)
    # missing also nulls remaining and serves a bound — but as a DEGRADATION
    assert body["chips"]["remaining"] is None
    assert body["chips"]["transferred"] == 0     # count of an unbound role: 0 rows seen


def test_absent_key_stays_missing(db_session, tmp_path, monkeypatch, client):
    _env(db_session, tmp_path, monkeypatch, transfer_log=_ABSENT)
    _seed_scenario(db_session)
    _assert_accidental_missing(client)


def test_json_null_stays_missing_not_untracked(db_session, tmp_path, monkeypatch,
                                               client):
    """null is indistinguishable from an accidental absent-key edit — the spec
    accepts ONLY the exact string "none"."""
    _env(db_session, tmp_path, monkeypatch, transfer_log=None)
    _seed_scenario(db_session)
    _assert_accidental_missing(client)


def test_case_variant_is_not_a_declaration(db_session, tmp_path, monkeypatch,
                                           client):
    _env(db_session, tmp_path, monkeypatch, transfer_log="None")
    _seed_scenario(db_session)
    _assert_accidental_missing(client)


def test_mutation_untracked_branch_is_load_bearing(untracked_env, client,
                                                   monkeypatch):
    """MUTATION TWIN: repoint the declaration constant and the "none" config
    must fall back to plain missing — proving the declared-state branch (and
    not some other machinery) produces the untracked shape asserted above."""
    monkeypatch.setattr(transfer_plan, "TRANSFER_LOG_NONE", "__never__")
    _seed_scenario(untracked_env)
    body = _summary(client)
    assert body["sources"]["transfer_log"] == "missing"
    assert not any(w.get("type") == "transfer_untracked"
                   for w in body["warnings"])
