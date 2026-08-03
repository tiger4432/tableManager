"""Coordinate/value columns are declared ONCE, and there is a place to ask what won.

WHY. `transfer_plan_config` asked the operator to retype a fact the system already
had. `map_overlay_config.json` says

    "dt_log": {"columns": {"x": "dt_x", "y": "dt_y", "val": "c_bn", ...}}

and the plan config asked for `x`/`y`/`bin` again - a third spelling of one fact.
The 2026-08-04 live incident landed exactly in that retyping (`"x": "x"` on a
table whose coordinate columns are `dt_x`/`dt_y`).

Two things are pinned here, and they belong together:
  * DERIVATION - an omitted required coordinate/value role is filled from the
    map binding, via `map_overlay.resolve_binding_info` (no second mechanism).
  * THE DRY-RUN - derivation can be quietly wrong, so `dry_run()` reports, per
    role, whether the column was declared or derived, WHICH column won, and
    where a derived one came from. Without that, we would have traded a silent
    wrong declaration for a silent wrong derivation.

[Isolation] `deriv_test_` prefix - cannot exist in a user's live config
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

DERIV_TABLES = {
    # Prefixed columns, like the live `dt_log`: nothing here matches the
    # x/y/val convention, so derivation MUST come from a declared map binding.
    "deriv_test_log": {
        "business_key": "cell_key",
        "column_types": {
            "cell_key": "string", "d_lot": "string", "d_slot": "string",
            "d_x": "number", "d_y": "number", "d_bn": "string",
        },
        "map_key_columns": ["d_lot", "d_slot"],
    },
    # Conventional columns: derivable from `table_config` alone, with no
    # map_overlay_config entry at all.
    "deriv_test_plain_map": {
        "business_key": "cell_key",
        "column_types": {
            "cell_key": "string", "lot": "string", "slot": "string",
            "x": "number", "y": "number", "val": "string",
        },
        "map_key_columns": ["lot", "slot"],
    },
    # No coordinates at all - derivation must FAIL BY NAME here, not silently.
    "deriv_test_no_coords": {
        "business_key": "row_key",
        "column_types": {"row_key": "string", "lot": "string", "slot": "string"},
    },
}

ROLES = transfer_plan.BIN_AXIS_ROLES

FULL = {"lot": "d_lot", "slot": "d_slot", "x": "d_x", "y": "d_y", "bin": "d_bn"}
SHORT = {"lot": "d_lot", "slot": "d_slot"}

OVERLAY = {
    "table_bindings": {
        "deriv_test_log": {
            "columns": {"x": "d_x", "y": "d_y", "val": "d_bn",
                        "key_columns": ["d_lot", "d_slot"]},
        },
    },
}


@pytest.fixture()
def deriv_env(db_session, tmp_path, monkeypatch):
    models.init_dynamic_models(DERIV_TABLES)
    crud.TABLE_CONFIG.update(DERIV_TABLES)
    from database.database import Base
    Base.metadata.create_all(bind=db_session.get_bind())
    path = tmp_path / f"overlay_{uuid.uuid4().hex[:6]}.json"
    path.write_text(json.dumps(OVERLAY), encoding="utf-8")
    monkeypatch.setattr(map_overlay, "CONFIG_PATH", str(path))
    bonding_plan._OVERLAY_MEMO["stamp"] = None      # do not inherit another test's read
    return db_session


def _src(columns, table="deriv_test_log"):
    return {"table": table, "columns": dict(columns)}


# ---------------------------------------------------------------------------
# Explicit always wins, and a fully-declared config is unchanged
# ---------------------------------------------------------------------------

def test_fully_declared_columns_are_returned_unchanged(deriv_env):
    """Same object back, not a rebuilt copy.

    Identity is the strongest available statement that nothing downstream can
    observe a difference - iteration order included, which `_resolve_model_columns`
    walks to build `unresolved`.
    """
    src = _src(FULL)
    effective, derivation = bonding_plan.resolve_effective_columns(src, ROLES)
    assert effective is src["columns"]
    assert derivation == {}


def test_fully_declared_response_is_byte_identical_with_and_without_derivation(deriv_env):
    """THE BYTE-IDENTITY PROOF the round was required to produce.

    Runs the whole stage-source-summary twice over identical seeded data: once
    normally, once with derivation replaced by a pass-through that cannot fill
    anything. If derivation could touch a fully-declared config at all, the two
    md5s would differ.
    """
    db = deriv_env
    _seed(db)
    cfg = _cfg(FULL)

    live = transfer_plan.get_stage_source_summary(
        db, cfg, "bonding", "L1", "01", bins="1,2")

    original = bonding_plan.resolve_effective_columns
    try:
        bonding_plan.resolve_effective_columns = (
            lambda source_cfg, required: (source_cfg.get("columns"), {}))
        without = transfer_plan.get_stage_source_summary(
            db, cfg, "bonding", "L1", "01", bins="1,2")
    finally:
        bonding_plan.resolve_effective_columns = original

    def md5(obj):
        return hashlib.md5(
            json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)
            .encode("utf-8")).hexdigest()

    assert md5(live) == md5(without), (live, without)
    # and the fixture is not vacuous - the response really carries numbers
    assert live["chips"]["total"] > 0
    assert live["bins"]["axis"] == "connected"


def test_a_wrong_explicit_declaration_still_loses_to_nothing(deriv_env):
    """Explicit wins even when it is wrong - that is the rule, and it is why the
    repair of the live file is DELETING the entries rather than correcting them.
    The refusal must say so, or the operator dead-ends at "there is a derivation,
    why is it not used".
    """
    reason, detail = bonding_plan.explain_binding_refusal(
        _src(dict(FULL, x="x", y="y")), ROLES, label="bin_map")

    assert reason == bonding_plan.BINDING_COLUMN_MISSING
    assert "지우면" in detail            # the instruction, not just the complaint
    assert "`d_x`" in detail and "`d_y`" in detail   # what deletion would derive


# ---------------------------------------------------------------------------
# Derivation, and what it refuses to derive
# ---------------------------------------------------------------------------

def test_omitted_roles_derive_from_the_declared_map_binding(deriv_env):
    effective, derivation = bonding_plan.resolve_effective_columns(_src(SHORT), ROLES)

    assert effective == FULL
    assert set(derivation) == {"x", "y", "bin"}
    assert derivation["x"]["column"] == "d_x"
    assert derivation["bin"]["column"] == "d_bn"
    # `bin` borrows the map binding's VALUE column - the report says which role
    assert derivation["bin"]["from_role"] == "val"
    for role in ("x", "y", "bin"):
        assert derivation[role]["source"] == bonding_plan.DERIVATION_DECLARED

    model, cols = bonding_plan._resolve_model_columns(_src(SHORT), ROLES)
    assert model is not None and set(ROLES) <= set(cols)


def test_conventional_table_derives_with_no_overlay_declaration(deriv_env):
    """`map_overlay_config` has no entry for this table; `table_config`'s x/y
    convention carries it. Same path, different source - and the report says so.
    """
    src = _src({"lot": "lot", "slot": "slot"}, table="deriv_test_plain_map")
    effective, derivation = bonding_plan.resolve_effective_columns(src, ROLES)

    assert effective["x"] == "x" and effective["y"] == "y" and effective["bin"] == "val"
    assert derivation["x"]["source"] == bonding_plan.DERIVATION_DERIVED


def test_keys_are_never_derived(deriv_env):
    """`lot`/`slot` differ by PURPOSE - the overlay keys this table one way and a
    plan may key it another. Deriving them would erase real information.
    """
    src = _src({"x": "d_x", "y": "d_y", "bin": "d_bn"})
    effective, derivation = bonding_plan.resolve_effective_columns(src, ROLES)

    assert "lot" not in effective and "slot" not in effective
    assert "lot" not in derivation and "slot" not in derivation
    reason, detail = bonding_plan.explain_binding_refusal(src, ROLES, label="bin_map")
    assert reason == bonding_plan.BINDING_NOT_DECLARED
    assert "lot" in detail and "slot" in detail


def test_optional_roles_are_never_filled(deriv_env):
    """THE LOAD-BEARING RESTRICTION.

    `transfer_plan._summarize_inline` reads a `transfer_log` that declares no
    x/y as `connected(count_only)` and subtracts a COUNT instead of a coordinate
    set. Filling an optional absent x/y would silently convert that site to set
    subtraction and change the numbers nobody asked to change.
    """
    src = _src(SHORT)
    effective, derivation = bonding_plan.resolve_effective_columns(
        src, transfer_plan.IDENTITY_ROLES)

    assert effective is src["columns"]
    assert derivation == {}
    _model, cols = bonding_plan._resolve_model_columns(
        src, transfer_plan.IDENTITY_ROLES)
    assert "x" not in cols and "y" not in cols


def test_derivation_failure_is_named_never_silent(deriv_env):
    """A silent derivation miss is strictly worse than the typo it replaces:
    there is no wrong string left to point at."""
    src = _src({"lot": "lot", "slot": "slot"}, table="deriv_test_no_coords")
    reason, detail = bonding_plan.explain_binding_refusal(src, ROLES, label="bin_map")

    assert reason == bonding_plan.BINDING_MAPPING_UNAVAILABLE
    assert "유도" in detail
    assert "deriv_test_no_coords" in detail
    for role in ("x", "y", "bin"):
        assert role in detail
    model, _cols = bonding_plan._resolve_model_columns(src, ROLES)
    assert model is None                      # refused, not half-resolved

    # and it does NOT read as a plain missing declaration
    absent_reason, absent_detail = bonding_plan.explain_binding_refusal(
        None, ROLES, label="bin_map")
    assert absent_reason == bonding_plan.BINDING_NOT_DECLARED
    assert absent_detail != detail


def test_a_guessed_value_column_is_refused_for_the_value_role(deriv_env, monkeypatch):
    """map_overlay keeps a `fallback_guess` value column out of its own data path.
    An availability count must not be the place it leaks back in. Coordinates of
    a guessed binding are still literal/declared, so they stay usable.
    """
    monkeypatch.setattr(map_overlay, "resolve_binding_info",
                        lambda cfg, table: {"x": "d_x", "y": "d_y", "val": "d_bn",
                                            "key_columns": ["d_lot"],
                                            "source": "fallback_guess"})
    effective, derivation = bonding_plan.resolve_effective_columns(_src(SHORT), ROLES)

    assert effective["x"] == "d_x" and effective["y"] == "d_y"
    assert "bin" not in effective
    assert derivation["bin"]["column"] is None
    assert derivation["bin"]["source"] == bonding_plan.DERIVATION_UNAVAILABLE


def test_sentences_survive_cp949(deriv_env):
    for src, roles in ((_src(dict(FULL, x="x")), ROLES),
                       (_src({"lot": "lot"}, table="deriv_test_no_coords"), ROLES),
                       (_src({"x": "d_x"}), ROLES),
                       (None, ROLES)):
        _reason, detail = bonding_plan.explain_binding_refusal(src, roles, label="bin_map")
        detail.encode("cp949")
        assert "—" not in detail


# ---------------------------------------------------------------------------
# The dry-run
# ---------------------------------------------------------------------------

def test_dry_run_shows_which_spelling_won(deriv_env):
    """"It worked" is not an answer. Every required role reports its resolved
    column AND whether that column was declared or derived."""
    report = transfer_plan.dry_run(_cfg(SHORT))
    bin_map = _role_of(report, "bonding", "bin_map")

    assert bin_map["accepted"] is True
    assert bin_map["reason"] is None
    assert bin_map["columns"]["lot"] == {
        "column": "d_lot", "origin": "declared", "required": True,
        "derivable": False, "derived_from": None,
        "derived_role": None, "exists_on_table": True}
    assert bin_map["columns"]["x"]["column"] == "d_x"
    assert bin_map["columns"]["x"]["origin"] == "derived"
    assert bin_map["columns"]["x"]["derived_from"] == bonding_plan.DERIVATION_DECLARED
    assert bin_map["columns"]["bin"]["derived_role"] == "val"
    assert report["counts"]["derived_columns"] == 3


def test_dry_run_rejects_with_the_named_reason_and_the_deletion_hint(deriv_env):
    report = transfer_plan.dry_run(_cfg(dict(FULL, x="x", y="y")))
    bin_map = _role_of(report, "bonding", "bin_map")

    assert bin_map["accepted"] is False
    assert bin_map["reason"] == bonding_plan.BINDING_COLUMN_MISSING
    assert bin_map["columns"]["x"]["origin"] == "declared"
    assert bin_map["columns"]["x"]["exists_on_table"] is False
    assert {"role": "x", "would_derive": "d_x"} in bin_map["removable_declarations"]
    assert report["counts"]["removable_declarations"] == 2
    assert report["counts"]["rejected"] >= 1


def test_dry_run_distinguishes_a_deletable_column_from_a_load_bearing_one(deriv_env):
    """The asymmetry an operator WILL trip on.

    `bin_map` requires x/y, so deleting them is safe - derivation fills them.
    `total_chips` treats x/y as OPTIONAL (their absence means "no coordinates for
    region counting"), so they are never derived and deleting them silently
    removes a capability. Both look like "an x column in the config file". The
    dry-run has to tell them apart or the shorter form becomes a new trap.
    """
    cfg = _cfg(SHORT)
    cfg["stages"]["bonding"]["source"]["total_chips"]["columns"].update(
        {"x": "d_x", "y": "d_y"})
    report = transfer_plan.dry_run(cfg)

    bin_x = _role_of(report, "bonding", "bin_map")["columns"]["x"]
    assert bin_x["required"] is True and bin_x["derivable"] is True

    total_x = _role_of(report, "bonding", "total_chips")["columns"]["x"]
    assert total_x["origin"] == "declared"      # shown even though not required
    assert total_x["required"] is False
    assert total_x["derivable"] is False        # deleting it would NOT be filled
    assert total_x["exists_on_table"] is True


def test_dry_run_marks_a_delegating_stage_not_reached(deriv_env):
    """A stage delegating via `source_config_ref` never reads its own `source.*`.
    Calling that `not_declared` invites an operator to fill in a block nothing
    consults - `not_reached` is the existing word for exactly this.
    """
    cfg = _cfg(SHORT)
    cfg["stages"]["dt"] = {"source_kind": "core", "target_kind": "tape",
                           "source_config_ref": "bonding_plan",
                           "target_map": {"table": "deriv_test_plain_map"}}
    report = transfer_plan.dry_run(cfg)

    total = _role_of(report, "dt", "total_chips")
    assert total["reason"] == bonding_plan.BINDING_NOT_REACHED
    assert "bonding_plan" in total["detail"]
    assert report["counts"]["not_reached"] == len(transfer_plan._STAGE_SOURCE_ROLES)


def test_dry_run_touches_no_data(deriv_env, monkeypatch):
    """Read-only means read-only. If any role reached the database this fails."""
    from database.database import SessionLocal

    def _boom(*_a, **_k):
        raise AssertionError("dry_run must not query data")

    monkeypatch.setattr(SessionLocal, "__call__", _boom, raising=False)
    report = transfer_plan.dry_run(_cfg(SHORT))
    assert report["counts"]["total"] > 0


def test_dry_run_route_is_admin_gated_and_read_only(deriv_env, client, monkeypatch):
    monkeypatch.setattr(transfer_plan, "CONFIG_PATH",
                        _write(deriv_env, monkeypatch, _cfg(SHORT)))
    resp = client.get("/admin/transfer-plan/dry-run")
    assert resp.status_code == 200
    body = resp.json()
    assert "counts" in body and "stages" in body

    import admin_auth
    monkeypatch.setenv("ASSY_ADMIN_TOKEN", "s3cret")
    monkeypatch.setattr(admin_auth, "_admin_token_cache", None, raising=False)
    assert client.get("/admin/transfer-plan/dry-run").status_code == 401


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _cfg(bin_columns):
    return {
        "stages": {
            "bonding": {
                "source_kind": "tape", "target_kind": "base",
                "bin_map": _src(bin_columns),
                "source": {
                    "identity": {"compose": ["lot", "slot"]},
                    "total_chips": _src({"lot": "d_lot", "slot": "d_slot"}),
                },
                "target_map": {"table": "deriv_test_plain_map"},
            },
        },
    }


def _write(_db, monkeypatch, cfg):
    import tempfile
    import os
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(cfg, f)
    return path


def _role_of(report, stage, role):
    for s in report["stages"]:
        if s["name"] == stage:
            for r in s["roles"]:
                if r["role"] == role:
                    return r
    raise AssertionError(f"role {role} not found on stage {stage}")


def _seed(db):
    model = models.DYNAMIC_TABLES["deriv_test_log"]
    for i, (x, y, b) in enumerate([(1, 1, "1"), (2, 1, "1"), (1, 2, "2"), (2, 2, "2")]):
        db.add(model(row_id=str(uuid.uuid4()), business_key_val=f"C{i}",
                     cell_key=f"C{i}", d_lot="L1", d_slot="01",
                     d_x=x, d_y=y, d_bn=b))
    db.commit()
