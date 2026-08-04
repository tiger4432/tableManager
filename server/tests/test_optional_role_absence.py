"""A DELETED optional role must not silently change a verdict (board N14).

WHY THIS FILE EXISTS. `8817dde` added derivation and `ba65c59` rewrote the guide
to teach operators that the repair for a wrong declaration is to DELETE the line.
That advice is correct for REQUIRED roles - derivation fills them back. It is a
trap one line further down: an OPTIONAL role is never derived, so deleting it
removes a capability, and until this round the removal was reported by nothing.

The measured shape (QA batch gate 2026-08-04, F5, on live `dt_log`): a
`fail_sources.*` block declares `fail_values` and a `val` column. Delete the
`val` line and every row in the pool matches the fail predicate - 0 fail chips
become 144 - while the response still says `remaining_reliable: true`.

WHICH SIDE WAS THE DEFECT. The JUDGEMENT, not the flag. `fail_values` says WHICH
values mean fail; `val` says WHERE to read them. With no `val` the question "is
this row a fail" is unanswerable, and "unanswerable" is not "yes". The identical
arithmetic was already ruled on for the declared-but-unresolvable spelling
(`bonding_plan.py`, `transfer_plan.py`: refuse, serve 0, demote) - the deletion
just walked around that ruling. Fixing the flag instead would keep serving 144
as a fail count with an honest caveat attached, which is a wrong number politely
labelled.

[Isolation] `optabs_test_` prefix - cannot exist in a user's live config
(conftest initialises dynamic models from the real config at import).
"""
import hashlib
import json
import uuid

import pytest

import bonding_plan
import map_overlay
import transfer_plan
from database import crud, models

OPTABS_TABLES = {
    # The tape: identity + coordinates, plus the origin (core) attribution that
    # makes the `frame: "origin"` projection reachable.
    "optabs_test_log": {
        "business_key": "cell_key",
        "column_types": {
            "cell_key": "string", "o_lot": "string", "o_slot": "string",
            "o_x": "number", "o_y": "number", "o_bn": "string",
            "c_lot": "string", "c_slot": "string",
            "c_x": "number", "c_y": "number",
        },
        "map_key_columns": ["o_lot", "o_slot"],
    },
    # The core wafer the tape chips came from - the pool a `frame: "origin"`
    # fail source counts and projects.
    "optabs_test_core": {
        "business_key": "cell_key",
        "column_types": {
            "cell_key": "string", "k_lot": "string", "k_slot": "string",
            "k_x": "number", "k_y": "number", "k_bn": "string",
        },
        "map_key_columns": ["k_lot", "k_slot"],
    },
}

ROWS = 8                       # scaled twin of the live 144
IDENT = {"lot": "o_lot", "slot": "o_slot"}
FAIL_FULL = {"lot": "o_lot", "slot": "o_slot", "val": "o_bn"}
FAIL_VAL_DELETED = {"lot": "o_lot", "slot": "o_slot"}


@pytest.fixture()
def optabs_env(db_session, tmp_path, monkeypatch):
    models.init_dynamic_models(OPTABS_TABLES)
    crud.TABLE_CONFIG.update(OPTABS_TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())
    # No overlay binding for this table: derivation must not reach in and fill
    # the deleted optional role from somewhere else - absence has to stay absent.
    path = tmp_path / f"overlay_{uuid.uuid4().hex[:6]}.json"
    path.write_text(json.dumps({"table_bindings": {}}), encoding="utf-8")
    monkeypatch.setattr(map_overlay, "CONFIG_PATH", str(path))
    bonding_plan._OVERLAY_MEMO["stamp"] = None
    _seed(db_session)
    return db_session


def _src(columns, table="optabs_test_log"):
    return {"table": table, "columns": dict(columns)}


def _cfg(fail_columns, fail_values=("F",)):
    """A stage whose only subtraction term is one self-frame fail source."""
    fs = _src(fail_columns)
    fs["frame"] = "self"
    fs["fail_values"] = list(fail_values)
    return {
        "stages": {
            "bonding": {
                "source_kind": "tape", "target_kind": "base",
                "source": {
                    "identity": {"compose": ["lot", "slot"]},
                    "total_chips": _src(IDENT),
                    "fail_sources": {"eds": fs},
                },
                "target_map": {"table": "optabs_test_log"},
            },
        },
    }


def _summary(db, cfg):
    return transfer_plan.get_stage_source_summary(db, cfg, "bonding", "L1", "01")


# ---------------------------------------------------------------------------
# The transition itself
# ---------------------------------------------------------------------------

def test_declared_val_counts_only_the_failing_rows(optabs_env):
    """The BEFORE half of the pair - the fixture is not vacuous."""
    out = _summary(optabs_env, _cfg(FAIL_FULL))

    assert out["chips"]["total"] == ROWS
    assert out["chips"]["fail_breakdown"]["eds"] == 0     # no row carries 'F'
    assert out["chips"]["remaining"] == ROWS
    assert out["chips"]["remaining_reliable"] is True
    assert out["sources"]["eds"] == "connected"


def test_deleting_the_optional_val_does_not_fail_every_row(optabs_env):
    """RED BEFORE THE FIX: fail_breakdown 0 -> 8, remaining 8 -> 0, and
    `remaining_reliable` stayed True the whole way.

    The pool is unchanged and no row carries a fail value; only one line left
    the config file. A number that moves by the whole population on a deletion
    the operator was ADVISED to make must not be served as reliable.
    """
    out = _summary(optabs_env, _cfg(FAIL_VAL_DELETED))

    assert out["chips"]["fail_breakdown"]["eds"] == 0, (
        "a fail predicate with no column to read counted every row as FAIL: "
        + json.dumps(out["chips"], ensure_ascii=False, default=str))
    assert out["chips"]["remaining_reliable"] is False
    assert out["chips"]["remaining"] is None
    # the subtraction dropped out, so the computed value is a genuine upper bound
    assert out["chips"]["remaining_upper_bound"] == ROWS
    assert "fail_value_column_absent" in out["sources"]["eds"]
    degraded = [w for w in out["warnings"]
                if w.get("type") == transfer_plan.WARN_SOURCE_DEGRADED
                and w.get("role") == "eds"]
    assert degraded and degraded[0]["effect"] == transfer_plan.EFFECT_REMAINING_OVERSTATED


def test_a_typo_and_a_deletion_reach_the_same_verdict(optabs_env):
    """The asymmetry that made this reachable: the typo was refused by name and
    the deletion was not. Both are "no usable fail column" - one ruling."""
    typo = _summary(optabs_env, _cfg(dict(FAIL_FULL, val="no_such_column")))
    deleted = _summary(optabs_env, _cfg(FAIL_VAL_DELETED))

    for out in (typo, deleted):
        assert out["chips"]["fail_breakdown"]["eds"] == 0
        assert out["chips"]["remaining_reliable"] is False
        assert out["chips"]["remaining"] is None
    # ...and each still names its OWN cause, so the repair differs
    assert "column_unresolved" in typo["sources"]["eds"]
    assert "fail_value_column_absent" in deleted["sources"]["eds"]


def test_no_fail_values_declared_keeps_a_bare_count(optabs_env):
    """The refusal is scoped to `fail_values` WITHOUT a column. A fail source
    that declares no fail values at all counts its whole pool ON PURPOSE (the
    table itself is the fail list) - that path must not be swept up."""
    cfg = _cfg(FAIL_VAL_DELETED)
    cfg["stages"]["bonding"]["source"]["fail_sources"]["eds"].pop("fail_values")
    out = _summary(optabs_env, cfg)

    assert out["chips"]["fail_breakdown"]["eds"] == ROWS
    assert out["sources"]["eds"] == "connected"
    assert out["chips"]["remaining_reliable"] is True


# ---------------------------------------------------------------------------
# The sibling sweep - every reader of the same predicate, not just the measured one
# ---------------------------------------------------------------------------

ORIGIN_LOG = {"lot": "o_lot", "slot": "o_slot", "x": "o_x", "y": "o_y",
              "origin_lot": "c_lot", "origin_slot": "c_slot",
              "origin_x": "c_x", "origin_y": "c_y"}
CORE_FULL = {"lot": "k_lot", "slot": "k_slot", "x": "k_x", "y": "k_y", "val": "k_bn"}
CORE_VAL_DELETED = {"lot": "k_lot", "slot": "k_slot", "x": "k_x", "y": "k_y"}


def _origin_cfg(fail_columns):
    """A stage whose fail source lives on the CORE and projects onto the tape."""
    fs = _src(fail_columns, table="optabs_test_core")
    fs["frame"] = "origin"
    fs["fail_values"] = ["F"]
    cfg = _cfg(FAIL_FULL)
    src = cfg["stages"]["bonding"]["source"]
    src["origin_log"] = _src(ORIGIN_LOG)
    src["fail_sources"] = {"eds": fs}
    return cfg


def test_origin_frame_projection_refuses_the_same_deletion(optabs_env):
    """The SECOND reader. A fix applied to the self-frame branch only is how this
    class returns: the origin-frame branch projects the fail SET, so a missing
    predicate marks every origin chip as fail and the projection paints the whole
    tape.
    """
    ok = _summary(optabs_env, _origin_cfg(CORE_FULL))
    assert ok["chips"]["fail_breakdown"]["eds"] == 0
    assert ok["chips"]["remaining"] == ROWS          # the fixture is live
    assert ok["chips"]["remaining_reliable"] is True

    deleted = _summary(optabs_env, _origin_cfg(CORE_VAL_DELETED))
    assert deleted["chips"]["fail_breakdown"]["eds"] == 0, (
        "the origin-frame projection marked every core chip as FAIL: "
        + json.dumps(deleted["chips"], ensure_ascii=False, default=str))
    assert deleted["chips"]["remaining"] is None
    assert deleted["chips"]["remaining_reliable"] is False
    assert "fail_value_column_absent" in deleted["sources"]["eds"]


def test_m1_core_summary_refuses_the_same_deletion(optabs_env):
    """The THIRD reader - `bonding_plan.get_core_summary`'s defect/eds_fail
    roles, which the `dt`-style stages reach through `source_config_ref`."""
    def bp(columns):
        fail = _src(columns, table="optabs_test_core")
        fail["fail_values"] = ["F"]
        return {"sources": {
            "total_chips": _src({"lot": "k_lot", "slot": "k_slot",
                                 "x": "k_x", "y": "k_y"}, table="optabs_test_core"),
            "defect": fail,
        }}

    ok = bonding_plan.get_core_summary(optabs_env, "K1", "07", config=bp(CORE_FULL))
    assert ok["chips"]["total"] == ROWS
    assert ok["chips"]["defect"] == 0
    assert ok["sources"]["defect"] == "connected"

    deleted = bonding_plan.get_core_summary(
        optabs_env, "K1", "07", config=bp(CORE_VAL_DELETED))
    assert deleted["chips"]["defect"] == 0, (
        "M1 counted every core row as a defect: "
        + json.dumps(deleted["chips"], ensure_ascii=False, default=str))
    assert bonding_plan.FAIL_VALUE_COLUMN_ABSENT in deleted["sources"]["defect"]
    # ...and the M2 reshape turns that status into an honest remaining
    assert transfer_plan._status_is_degraded(deleted["sources"]["defect"]) is True


def test_absent_total_chips_coordinates_null_the_number_instead_of_moving_it(optabs_env):
    """SWEEP RESULT for the sibling the brief named: `total_chips` x/y.

    Not the same defect. Their absence cannot invert a verdict - every consumer
    already treats an unknown coordinate set as unknown: the BIN block says so by
    name and serves `total: null` with `reliable: false`. Nothing here claims a
    number it does not have, so nothing is changed. The dry-run now names the
    absence anyway, which is the whole point of the second half of this round.
    """
    cfg = _cfg(FAIL_FULL)                       # total_chips declares no x/y
    cfg["stages"]["bonding"]["bin_map"] = _src(
        {"lot": "o_lot", "slot": "o_slot", "x": "o_x", "y": "o_y", "bin": "o_bn"})
    out = transfer_plan.get_stage_source_summary(
        optabs_env, cfg, "bonding", "L1", "01", bins="1")

    entry = out["bins"]["entries"][0]
    assert entry["total"] is None
    assert entry["reliable"] is False
    assert entry["status"] == transfer_plan.BIN_UNKNOWN
    assert "총칩 좌표" in entry["reason"]

    report = transfer_plan.dry_run(cfg)
    assert _role_of(report, "bonding", "total_chips")["columns"]["x"]["origin"] == "absent"


def test_absent_transfer_log_coordinates_already_demote(optabs_env):
    """SWEEP RESULT: `transfer_log` x/y. Also not the same defect - absence lands
    on `connected(count_only)`, which the degradation engine already reads."""
    cfg = _cfg(FAIL_FULL)
    cfg["stages"]["bonding"]["source"]["transfer_log"] = _src(IDENT)
    out = _summary(optabs_env, cfg)

    assert out["sources"]["transfer_log"] == "connected(count_only)"
    assert out["chips"]["remaining_reliable"] is False
    assert out["chips"]["remaining"] is None


# ---------------------------------------------------------------------------
# A fully-declared config is byte-identical
# ---------------------------------------------------------------------------

def _md5(obj):
    return hashlib.md5(
        json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)
        .encode("utf-8")).hexdigest()


def test_fully_declared_summary_is_byte_identical_to_the_prefix_behaviour(optabs_env):
    """THE MUTATION GATE.

    Runs the whole stage summary twice over identical seeded data: once live,
    once with the new predicate replaced by the pre-fix rule (refuse only the
    declared-but-unresolvable spelling). A fix that also refused a config which
    DOES declare a usable `val` would move the live md5 and turn this red.
    """
    db = optabs_env
    cfg = _cfg(FAIL_FULL)
    live = _summary(db, cfg)

    original = bonding_plan.fail_filter_status
    try:
        def _prefix_rule(src_cfg, cols, status):
            unusable = (isinstance(src_cfg, dict) and src_cfg.get("fail_values")
                        and "val" in bonding_plan._unresolved_roles(cols))
            return bool(unusable), status
        bonding_plan.fail_filter_status = _prefix_rule
        without = _summary(db, cfg)
    finally:
        bonding_plan.fail_filter_status = original

    assert _md5(live) == _md5(without), (live, without)
    assert live["chips"]["total"] == ROWS            # not vacuous


# ---------------------------------------------------------------------------
# The absence is observable BEFORE it is acted on
# ---------------------------------------------------------------------------

def test_dry_run_names_the_absent_optional_role(optabs_env):
    """The cheapest honest fix: an optional-but-absent role is an EXPLICIT row
    naming the capability that is currently off, instead of no row at all.
    Without this the operator's own report shows 3 columns where it used to show
    4 and nothing says which one left."""
    report = transfer_plan.dry_run(_cfg(FAIL_VAL_DELETED))
    role = _role_of(report, "bonding", "fail_sources.eds")

    val = role["columns"]["val"]
    assert val["origin"] == "absent"
    assert val["required"] is False
    assert val["column"] is None
    assert val["derivable"] is False              # never filled - absence is data
    assert val["effect"]                          # names the capability that is off
    assert report["counts"]["absent_optional_columns"] >= 1


def test_dry_run_absent_row_disappears_once_the_role_is_declared(optabs_env):
    """A declared role is reported as declared, not as absent - the row is a
    statement about THIS config, not a static catalogue."""
    report = transfer_plan.dry_run(_cfg(FAIL_FULL))
    val = _role_of(report, "bonding", "fail_sources.eds")["columns"]["val"]

    assert val["origin"] == "declared"
    assert val["column"] == "o_bn"
    assert val["effect"] is None


def test_dry_run_still_touches_no_data(optabs_env, monkeypatch):
    from database.database import SessionLocal

    def _boom(*_a, **_k):
        raise AssertionError("dry_run must not query data")

    monkeypatch.setattr(SessionLocal, "__call__", _boom, raising=False)
    report = transfer_plan.dry_run(_cfg(FAIL_VAL_DELETED))
    assert report["counts"]["total"] > 0


def test_absent_optional_sentences_survive_cp949(optabs_env):
    report = transfer_plan.dry_run(_cfg(FAIL_VAL_DELETED))
    for stage in report["stages"]:
        for role in stage["roles"]:
            for entry in role["columns"].values():
                if entry.get("effect"):
                    entry["effect"].encode("cp949")
                    assert "—" not in entry["effect"]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _role_of(report, stage, role):
    for s in report["stages"]:
        if s["name"] == stage:
            for r in s["roles"]:
                if r["role"] == role:
                    return r
    raise AssertionError(f"role {role} not found on stage {stage}")


def _seed(db):
    tape = models.DYNAMIC_TABLES["optabs_test_log"]
    core = models.DYNAMIC_TABLES["optabs_test_core"]
    for i in range(ROWS):
        db.add(tape(row_id=str(uuid.uuid4()), business_key_val=f"C{i}",
                    cell_key=f"C{i}", o_lot="L1", o_slot="01",
                    o_x=i % 4, o_y=i // 4, o_bn="1",
                    c_lot="K1", c_slot="07", c_x=i % 4, c_y=i // 4))
        db.add(core(row_id=str(uuid.uuid4()), business_key_val=f"K{i}",
                    cell_key=f"K{i}", k_lot="K1", k_slot="07",
                    k_x=i % 4, k_y=i // 4, k_bn="1"))
    db.commit()
