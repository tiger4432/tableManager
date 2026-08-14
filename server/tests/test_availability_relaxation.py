"""[relaxation 2026-08-04 — board request 2] Optional auxiliary declarations.

Real-fab feedback: sites do NOT keep `fail_sources` / `origin_log` /
`transfer_log` side tables — deductions are marked on the map object itself.
The old engine treated an absent declaration as a broken one (`missing` →
degradation → remaining nulled), which hid availability for every material.

The relaxed semantics, pinned here on BOTH sides of the boundary:

  ABSENT key   → status `not_declared` (NOT a degradation), availability is
                 computed and served as a real number WITHOUT that subtraction,
                 and the skipped kinds are NAMED in `inactive_subtractions`
                 (honest degradation — gross must never silently pose as net).
  PRESENT key  → every pre-existing judgement unchanged: broken bindings stay
                 `missing`/demoted, remaining stays nulled, warnings stay.
                 (`transfer_log: "none"` keeps its 7c upper-bound behavior —
                 see test_transfer_untracked.py.)
  total_chips  → still required (the denominator): absent stays `missing`.

Fixtures are the shared tp_test_* scenario (total 8, fail-union 4, used 3,
true remaining 2) — so a relaxed remaining of 8 proves the subtractions were
skipped, not silently applied.
"""
import pytest

import bonding_plan
import transfer_plan
from database import crud, models

from test_transfer_plan import (TP_TABLES, _tp_config, _bp_config, _write_cfg,
                                _seed_scenario, _seed_bins, _seed_second_slot,
                                _seed_plan, _paint, _validate)

AUX_ROLES = ("transfer_log", "origin_log", "process_history")


def _relaxed_tp_config():
    """bonding stage with every auxiliary source declaration removed."""
    cfg = _tp_config()
    src = cfg["stages"]["bonding"]["source"]
    for key in ("transfer_log", "origin_log", "process_history",
                "fail_sources", "origin_area_map"):
        del src[key]
    return cfg


def _broken_tp_config():
    """Same roles PRESENT but broken — the guard side of the boundary."""
    cfg = _tp_config()
    src = cfg["stages"]["bonding"]["source"]
    src["transfer_log"]["table"] = "tp_test_no_such"
    src["origin_log"]["table"] = "tp_test_no_such"
    src["fail_sources"]["defect"]["table"] = "tp_test_no_such"
    return cfg


@pytest.fixture()
def env(db_session, tmp_path, monkeypatch):
    models.init_dynamic_models(TP_TABLES)
    crud.TABLE_CONFIG.update(TP_TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())
    return db_session, tmp_path, monkeypatch


def _summary(client, **extra):
    params = {"stage": "bonding", "lot": "TAPE-X", "slot": "01"}
    params.update(extra)
    res = client.get("/api/transfer-plan/source-summary", params=params)
    assert res.status_code == 200, res.text
    return res.json()


# ---------------------------------------------------------------------------
# Inline (tape-kind) path
# ---------------------------------------------------------------------------


def test_absent_declarations_serve_availability(env, client):
    """The headline of the request: no auxiliary tables declared → the material
    still shows a computed availability, with the skipped kinds named."""
    db, tmp_path, monkeypatch = env
    _write_cfg(tmp_path, monkeypatch, tp_cfg=_relaxed_tp_config())
    _seed_scenario(db)
    body = _summary(client)

    for role in AUX_ROLES:
        assert body["sources"][role] == "not_declared", role
    chips = body["chips"]
    assert chips["total"] == 8
    assert chips["fail_breakdown"] == {}
    # remaining is a REAL number — total minus nothing (no subtraction sources).
    # 8 (not the fully-subtracted 2) proves the terms were skipped, not applied.
    assert chips["remaining"] == 8
    assert chips["remaining_reliable"] is True
    assert "remaining_upper_bound" not in chips
    # transferred is unknown (no log exists), never a fake 0
    assert chips["transferred"] is None

    # honest degradation: the payload SAYS which subtraction kinds were inactive
    assert body["inactive_subtractions"] == ["transfer_log", "origin_log",
                                             "fail_sources"]
    # ...and none of it is a degradation
    assert not any(w.get("type") == transfer_plan.WARN_SOURCE_DEGRADED
                   for w in body["warnings"])
    assert not any(w.get("type") == transfer_plan.WARN_TRANSFER_UNTRACKED
                   for w in body["warnings"])


def test_declared_but_broken_still_demotes(env, client):
    """Guard side: the SAME roles, declared but broken, keep every demotion —
    the relaxation applies only to absence."""
    db, tmp_path, monkeypatch = env
    _write_cfg(tmp_path, monkeypatch, tp_cfg=_broken_tp_config())
    _seed_scenario(db)
    body = _summary(client)

    assert body["sources"]["transfer_log"] == "missing"
    assert body["sources"]["origin_log"] == "missing"
    assert body["sources"]["defect"] == "missing"
    assert body["chips"]["remaining"] is None
    assert body["chips"]["remaining_reliable"] is False
    degraded = {w["role"] for w in body["warnings"]
                if w.get("type") == transfer_plan.WARN_SOURCE_DEGRADED}
    assert {"transfer_log", "origin_log", "defect"} <= degraded
    # broken is not absent — nothing is reported as an inactive subtraction
    assert "inactive_subtractions" not in body


# ---------------------------------------------------------------------------
# [QA B3, 2026-08-04] A PRESENT-but-malformed `fail_sources` is state 2, never
# state 1.
#
# The relaxation rests on THREE states: absent (relaxed + named), present-but-
# broken (pre-existing handling, unchanged), present-and-valid (unchanged).
# `_summarize_inline` decided declaredness for `fail_sources` with a hand-rolled
# truthiness-and-shape test instead of the shared `role_is_declared` predicate,
# which collapsed state 2 into state 1: a garbage value read as an absent key.
# The visible lie is `inactive_subtractions` naming a role the operator DID
# declare — the one field whose whole job is to be trustworthy about that.
#
# Every other role is left declared AND working here, so the malformed container
# is the only variable: an honest engine emits no marker at all.
MALFORMED_FAIL_SOURCES = {
    "json_null": None,          # `"fail_sources": null`
    "string_none": "None",      # the 7c "none" spelling, wrong role
    "wrong_type_list": ["defect"],
    "wrong_type_int": 7,
}


@pytest.mark.parametrize("shape", sorted(MALFORMED_FAIL_SOURCES))
def test_malformed_fail_sources_is_declared_not_absent(env, client, shape):
    """PRESENT + garbage → treated exactly as before the relaxation: no fail
    subtraction was ever applied for a malformed container, and — the fix — the
    payload does NOT claim the site failed to declare one."""
    db, tmp_path, monkeypatch = env
    cfg = _tp_config()
    src = cfg["stages"]["bonding"]["source"]
    src["fail_sources"] = MALFORMED_FAIL_SOURCES[shape]     # present, garbage
    _write_cfg(tmp_path, monkeypatch, tp_cfg=cfg)
    _seed_scenario(db)
    body = _summary(client)

    # 🔴 the defect: a declared role named as an inactive subtraction
    assert "fail_sources" not in (body.get("inactive_subtractions") or []), shape
    # nothing else is absent, so the marker field must not appear at all
    assert "inactive_subtractions" not in body, shape

    # ...and the rest of the verdict is byte-for-byte the pre-relaxation one for
    # this shape: a malformed container yields no fail source to iterate, so the
    # fail term is simply absent from the arithmetic (remaining = 8 − used 3).
    assert body["chips"]["total"] == 8
    assert body["chips"]["fail_breakdown"] == {}
    assert body["chips"]["remaining"] == 5
    assert body["chips"]["remaining_reliable"] is True
    assert body["chips"]["transferred"] == 3
    assert body["sources"]["transfer_log"] == "connected"
    assert body["sources"]["origin_log"] == "connected"


def test_validate_never_names_a_declared_role_as_inactive(env, client):
    """The verdict surface carries the same lie downstream: with a malformed but
    PRESENT `fail_sources`, `validate` used to hand the operator a list naming a
    source the site had declared."""
    db, tmp_path, monkeypatch = env
    cfg = _tp_config()
    src = cfg["stages"]["bonding"]["source"]
    src["fail_sources"] = None
    _write_cfg(tmp_path, monkeypatch, tp_cfg=cfg)
    _seed_scenario(db)
    _seed_one_doe_plan(db, "BASE-MALFORMED", 5)             # required 5 <= 5

    body = _validate(client, "BASE-MALFORMED")
    assert body["availability_checked"] is True
    assert "fail_sources" not in (body.get("inactive_subtractions") or [])
    assert "inactive_subtractions" not in body
    assert set(body) == VALIDATE_DECLARED_KEYS


def test_fully_declared_config_payload_unchanged(env, client):
    """Third side: a fully declared, working config keeps the exact numbers and
    gains NO new field."""
    db, tmp_path, monkeypatch = env
    _write_cfg(tmp_path, monkeypatch)
    _seed_scenario(db)
    body = _summary(client)
    assert body["chips"]["remaining"] == 2
    assert body["chips"]["remaining_reliable"] is True
    assert "inactive_subtractions" not in body


def test_declared_origin_frame_fail_source_without_origin_log_still_surfaces(env, client):
    """A DECLARED frame='origin' fail source with an undeclared origin_log is a
    contradiction between declarations — it must keep the explicit
    unavailable(origin_missing) demotion, not ride the relaxation."""
    db, tmp_path, monkeypatch = env
    cfg = _tp_config()
    src = cfg["stages"]["bonding"]["source"]
    del src["origin_log"]          # absent → relaxed on its own axis
    del src["transfer_log"]
    _write_cfg(tmp_path, monkeypatch, tp_cfg=cfg)
    _seed_scenario(db)
    body = _summary(client)
    assert body["sources"]["origin_log"] == "not_declared"
    assert body["sources"]["defect"] == "unavailable(origin_missing)"
    assert body["chips"]["remaining"] is None            # the declared source is down
    assert body["chips"]["remaining_reliable"] is False
    # origin_log absence is still named as inactive; fail_sources is declared so not
    assert body["inactive_subtractions"] == ["transfer_log", "origin_log"]


# ---------------------------------------------------------------------------
# /stages role view
# ---------------------------------------------------------------------------


def test_stages_distinguish_absent_from_broken(env, client):
    db, tmp_path, monkeypatch = env
    _write_cfg(tmp_path, monkeypatch, tp_cfg=_relaxed_tp_config())
    body = client.get("/api/transfer-plan/stages").json()
    bd = next(s for s in body["stages"] if s["name"] == "bonding")
    for role in AUX_ROLES:
        assert bd["roles"][role] == "not_declared", role
    assert bd["roles"]["total_chips"] == "connected"

    _write_cfg(tmp_path, monkeypatch, tp_cfg=_broken_tp_config())
    body = client.get("/api/transfer-plan/stages").json()
    bd = next(s for s in body["stages"] if s["name"] == "bonding")
    assert bd["roles"]["transfer_log"] == "missing"
    assert bd["roles"]["origin_log"] == "missing"


# ---------------------------------------------------------------------------
# BIN axis and lot scope compute without the missing subtractions
# ---------------------------------------------------------------------------


def test_bins_serve_numbers_without_undeclared_subtractions(env, client):
    db, tmp_path, monkeypatch = env
    _write_cfg(tmp_path, monkeypatch, tp_cfg=_relaxed_tp_config())
    _seed_scenario(db)
    _seed_bins(db)
    body = _summary(client, bins="")
    assert body["bins"]["axis"] == "connected"
    by_bin = {e["bin"]: e for e in body["bins"]["entries"]}
    for b in (1, 2):
        e = by_bin[b]
        assert e["status"] == "ok" and e["reliable"] is True
        assert e["total"] == 4
        assert e["remaining"] == 4          # no fail/consumption terms declared
        assert e["transferred"] is None     # unknown, never fake 0
        assert "remaining_upper_bound" not in e
    assert by_bin[1]["remaining"] + by_bin[2]["remaining"] == body["chips"]["remaining"]


def test_lot_scope_carries_the_inactive_kinds(env, client):
    db, tmp_path, monkeypatch = env
    _write_cfg(tmp_path, monkeypatch, tp_cfg=_relaxed_tp_config())
    _seed_scenario(db)
    _seed_bins(db)
    _seed_second_slot(db)
    body = client.get("/api/transfer-plan/source-summary",
                      params={"stage": "bonding", "lot": "TAPE-X",
                              "scope": "lot", "bins": ""}).json()
    assert body["slots"] == ["01", "02"]
    assert body["inactive_subtractions"] == ["transfer_log", "origin_log",
                                             "fail_sources"]
    b1 = next(e for e in body["bins"]["entries"] if e["bin"] == 1)
    assert b1["status"] == "ok"
    assert b1["remaining"] == 4 + 2         # slot sums, no subtraction terms
    assert b1["transferred"] is None        # pooled sum of unknowns is unknown


# ---------------------------------------------------------------------------
# validate — the surface that hands an operator a go/no-go verdict
#
# [QA B1, 2026-08-04] The relaxation makes `remaining_reliable` true for a number
# computed WITHOUT its subtractions, and `validate_plan` gates on exactly that
# flag. Nothing else about the verdict changes (the Lead PM ruled the site's
# declaration IS the site's best knowledge — see the module docstring), so the
# only thing that must change is that the response SAYS what it did not subtract.
# The gap this pins is that no test exercised validate on a relaxed config at all.
# ---------------------------------------------------------------------------

# Every key `validate_plan` returns for a fully declared config. Frozen here so a
# new field can never appear on the declared path without this test failing.
VALIDATE_DECLARED_KEYS = {"ref_table", "map_key", "stage", "map_status",
                          "doe_count", "painted_values", "status",
                          "availability_checked", "warnings"}


def _seed_one_doe_plan(db, map_key, cells):
    """One DOE ('A') drawing from TAPE-X/01, painted over `cells` chips.

    stack=1 → layers 1 → required == painted count, so the demand is the cell
    count and nothing else — the numbers below are read, not derived twice.
    """
    _seed_plan(db, map_key, "A", stack=1, mat_mid=["TAPE-X_01"])
    _paint(db, map_key, [(x, 1, "A") for x in range(1, cells + 1)])
    db.commit()


def test_validate_names_the_inactive_subtractions_behind_its_verdict(env, client):
    """Relaxed path: the verdict rests on a GROSS availability (8, not the
    fully-subtracted 2), so the response must name the subtractions it skipped —
    same field name and same shape as the slot / lot / M1 summaries."""
    db, tmp_path, monkeypatch = env
    _write_cfg(tmp_path, monkeypatch, tp_cfg=_relaxed_tp_config())
    _seed_scenario(db)
    _seed_one_doe_plan(db, "BASE-RELAXED", 5)      # required 5

    body = _validate(client, "BASE-RELAXED")
    # The verdict itself is unchanged by design: 5 <= gross 8, no warning, `ok`.
    assert body["availability_checked"] is True
    assert body["status"] == "ok"
    assert body["warnings"] == []
    # ...and the marker states what that `ok` was computed without.
    assert body["inactive_subtractions"] == ["transfer_log", "origin_log",
                                             "fail_sources"]


def test_validate_verdict_on_a_declared_config_is_byte_identical(env, client):
    """Declared path: the SAME plan against a fully declared config keeps every
    pre-existing judgement (5 > net 2 → shortage) and gains NO new field."""
    db, tmp_path, monkeypatch = env
    _write_cfg(tmp_path, monkeypatch)               # fully declared
    _seed_scenario(db)
    _seed_one_doe_plan(db, "BASE-DECLARED", 5)

    body = _validate(client, "BASE-DECLARED")
    assert "inactive_subtractions" not in body
    assert set(body) == VALIDATE_DECLARED_KEYS      # byte-identity of the shape
    shortage = [w for w in body["warnings"]
                if w["type"] == transfer_plan.WARN_QTY_SHORTAGE]
    assert len(shortage) == 1
    # 2 is the net number; the relaxed run above saw 8 for the identical plan.
    assert shortage[0]["required"] == 5 and shortage[0]["available"] == 2
    assert body["status"] == "warnings"


def test_validate_omits_the_marker_when_the_gross_number_never_judged(env, client):
    """A source that was skipped as 판정 불가 contributes no verdict, so its
    inactive kinds are not claimed as the basis of one. Here `fail_sources` is
    declared but broken (→ demotion → availability_unreliable) while the two log
    roles are merely absent: the whole source is unjudgeable, so the field is
    absent even though the summary itself carries inactive kinds."""
    db, tmp_path, monkeypatch = env
    cfg = _tp_config()
    src = cfg["stages"]["bonding"]["source"]
    del src["transfer_log"]
    del src["origin_log"]
    src["fail_sources"]["defect"]["table"] = "tp_test_no_such"
    _write_cfg(tmp_path, monkeypatch, tp_cfg=cfg)
    _seed_scenario(db)
    _seed_one_doe_plan(db, "BASE-MIXED", 5)

    body = _validate(client, "BASE-MIXED")
    assert body["status"] in ("unverified", "warnings")
    assert any(w["type"] == transfer_plan.WARN_AVAILABILITY_UNRELIABLE
               for w in body["warnings"])
    assert "inactive_subtractions" not in body


# ---------------------------------------------------------------------------
# M1 route (`GET /api/bonding-plan/core-summary`) + core-kind stage
#
# 🔴 [2026-08-14] These used to be ONE assertion each, because the `dt` stage
# delegated to `bonding_plan_config.json` and both surfaces read the same file.
# The delegation was retired (`server/M1_SOURCE_CONFIG_REF.RETIRED.md`) and the
# two surfaces are now independent, so each test drives BOTH configs and checks
# both — that independence is exactly what could rot unnoticed.
# M1 itself is NOT retired: the route and `bonding_plan_config.json` are live and
# these tests are now their only regression net inside this file.
# ---------------------------------------------------------------------------


def test_absent_used_chips_serves_availability(env, client):
    db, tmp_path, monkeypatch = env
    bp = _bp_config()
    del bp["sources"]["used_chips"]
    cfg = _tp_config()
    del cfg["stages"]["dt"]["source"]["transfer_log"]
    _write_cfg(tmp_path, monkeypatch, tp_cfg=cfg, bp_cfg=bp)
    _seed_scenario(db)

    # M1's own endpoint: counts unchanged (absent role contributes 0), status
    # and the inactive list are the only additions.
    m1 = client.get("/api/bonding-plan/core-summary",
                    params={"lot": "CORE-A", "slot": "01"}).json()
    assert m1["sources"]["used_chips"] == "not_declared"
    assert m1["chips"] == {"total": 36, "defect": 2, "eds_fail": 1,
                           "used": 0, "remaining": 33}
    assert m1["inactive_subtractions"] == ["used_chips"]

    # dt stage (inline): remaining stays a number, kind named in M2 vocabulary.
    body = _summary(client, stage="dt", lot="CORE-A", slot="01")
    assert body["sources"]["transfer_log"] == "not_declared"
    assert body["chips"]["remaining"] == 33
    assert body["chips"]["remaining_reliable"] is True
    assert body["chips"]["transferred"] is None
    # `origin_log` is not declared on this stage either, so it joins the list.
    assert body["inactive_subtractions"] == ["transfer_log", "origin_log"]
    assert not any(w.get("type") == transfer_plan.WARN_SOURCE_DEGRADED
                   for w in body["warnings"])


def test_broken_used_chips_still_demotes(env, client):
    db, tmp_path, monkeypatch = env
    cfg = _tp_config()
    cfg["stages"]["dt"]["source"]["transfer_log"]["table"] = "tp_test_no_such"
    _write_cfg(tmp_path, monkeypatch, tp_cfg=cfg)
    _seed_scenario(db)
    body = _summary(client, stage="dt", lot="CORE-A", slot="01")
    assert body["sources"]["transfer_log"] == "missing"
    assert body["chips"]["remaining"] is None
    assert body["chips"]["remaining_reliable"] is False
    # A BROKEN binding is not an absent one — it never enters `inactive_subtractions`.
    assert "transfer_log" not in (body.get("inactive_subtractions") or [])


def test_total_chips_stays_required(env, client):
    """The denominator is exempt from the relaxation — absent total_chips is
    still `missing` and availability refuses a number. Both surfaces."""
    db, tmp_path, monkeypatch = env
    bp = _bp_config()
    del bp["sources"]["total_chips"]
    cfg = _tp_config()
    del cfg["stages"]["dt"]["source"]["total_chips"]
    _write_cfg(tmp_path, monkeypatch, tp_cfg=cfg, bp_cfg=bp)
    _seed_scenario(db)
    m1 = client.get("/api/bonding-plan/core-summary",
                    params={"lot": "CORE-A", "slot": "01"}).json()
    assert m1["sources"]["total_chips"] == "missing"
    body = _summary(client, stage="dt", lot="CORE-A", slot="01")
    assert body["sources"]["total_chips"] == "missing"
    assert body["chips"]["remaining"] is None
    assert body["chips"]["remaining_reliable"] is False
