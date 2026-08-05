"""[Spec MAP_ALIGNMENT_SPEC 0.1/0.2] Layer 9 (the plan) reads layer 8 (the confirmation).

The chain ends at the plan. Until now its canonical frame -- the frame every other source
is aligned ONTO, which is the whole N-ary consolidation decision -- was picked by
`CANONICAL_FRAME_ROLES`, a config-ordered tuple with no record, no version and no source
list. These tests pin the three things that had to become true:

1. WHEN A CONFIRMATION EXISTS ITS FRAME WINS and the tuple is not consulted. Proved by
   making the two disagree and watching the alignment markers invert -- a test where they
   agree proves only that the code compiled.
2. THE FALLBACK SAYS SO. Identical numbers with a silent provenance is the exact state
   this chain exists to remove, so the absence of a confirmation is named, not implied.
3. THE MIDDLE RUNG EXISTS. `connected` and `connected(align_unavailable)` could not say
   "aligned, but weakly supported", so a confirmation whose WEAKEST contributor is
   unranked had to be rounded to one end. It is now spelled -- with a word the project
   already owns. No sixth token.

[격리] Table names use the `bdp_test_*` prefix shared with `test_bonding_plan.py` for the
same reason it does: a name that exists in the operator's real (gitignored) config makes
the import-time `init_dynamic_models` win the race and the fixture silently tests theirs.
"""
import json

import pytest

import bonding_plan
import config_resolve_report
import frame_confirmation as fc
from database import crud, models

from test_bonding_plan import _add_meta, _seed_core, bdp_env  # noqa: F401  (fixture)

# The unit is whatever the enrichment rule declares -- a column name written here would be
# a second spelling of the decision unit (same discipline as `test_frame_confirmation.py`).
RULE = {"name": "eqp_product_frame_attribution",
        "derived_table": "eqp_frame_attribution",
        "decision_key": ["dt_eqp", "product"],
        "target_fields": ["core_frame", "dt_frame"]}

CORE_TABLE = "bdp_test_core_defect_map"
EDS_TABLE = "bdp_test_eds_fail_map"
MAP_ID = "LOTX_01"

# Every key `get_core_summary` answered with BEFORE layer 8 was wired in. Anything outside
# this set is an addition and has to be a deliberate one.
PRE_EXISTING_KEYS = {"identity", "sources", "chips", "history", "warnings",
                     "region_chips", "inactive_subtractions"}


def _confirm(db, contributors, reference=None, unit=("EQP-A", "P1"), frames=None):
    return fc.record_confirmation(
        db, RULE, {"dt_eqp": unit[0], "product": unit[1]}, contributors,
        confirmed_by="tester", frames=frames or {"core_frame": "rot0_front"},
        reference=reference)


def _contrib(role, table, map_id, source_name, **kw):
    d = {"role": role, "source_table": table, "map_id": map_id,
         "source_name": source_name, "applied_frame": "rot0_front",
         "shift_dx": 0, "shift_dy": 0}
    d.update(kw)
    return d


def _summary(client, lot="LOTX", slot="01", **params):
    res = client.get("/api/bonding-plan/core-summary",
                     params=dict(lot=lot, slot=slot, **params))
    assert res.status_code == 200, res.text
    return res.json()


# ---------------------------------------------------------------------------
# 1. The fallback: same answer, no longer a silent one
# ---------------------------------------------------------------------------

def test_a_unit_with_no_confirmation_keeps_every_pre_existing_key_unchanged(bdp_env, client):
    """The additive rule. `frame_basis` is the ONLY new key and nothing else moved.

    The values pinned here are the ones `test_bonding_plan.test_core_summary_counts`
    already pins; repeating them is the point -- if wiring layer 8 in moves a single one of
    them for a unit that has no confirmation, this fails before anyone reaches production.
    """
    _seed_core(bdp_env)
    body = _summary(client)

    assert set(body) - PRE_EXISTING_KEYS == {"frame_basis"}
    assert body["chips"] == {"total": 36, "defect": 2, "eds_fail": 2, "used": 2,
                             "remaining": 30}
    assert body["sources"] == {"process_history": "connected", "defect": "connected",
                               "eds_fail": "connected(aligned:180)",
                               "used_chips": "connected", "total_chips": "connected"}


def test_the_fallback_names_itself_rather_than_looking_identical(bdp_env, client):
    """"No confirmation" must be readable off the payload, not inferred from its absence."""
    _seed_core(bdp_env)
    basis = _summary(client)["frame_basis"]

    assert basis["kind"] == bonding_plan.BASIS_ROLE_ORDER
    assert basis["reason"] == config_resolve_report.REASON_NOT_DECLARED
    # and it names the degenerate rule it fell back to, so the reader knows WHAT decided.
    assert basis["roles"] == list(bonding_plan.CANONICAL_FRAME_ROLES)
    assert "confirmation_uid" not in basis


# ---------------------------------------------------------------------------
# 2. The confirmation wins -- proved by disagreement
# ---------------------------------------------------------------------------

def test_the_confirmation_picks_the_canonical_frame_and_the_role_tuple_is_not_consulted(
        bdp_env, client):
    """🔴 THE test. Role order says rot0 (core map); the confirmation says rot180 (EDS map).

    If the confirmation were merely *read* and the tuple still decided, every marker below
    would keep its pre-confirmation value and this would pass on broken code. So the two
    are made to disagree and the alignment markers must INVERT: the source that needed a
    180 correction now needs none, and the one that needed none now needs 180.
    """
    _seed_core(bdp_env)
    before = _summary(client)["sources"]
    assert before["defect"] == "connected" and before["eds_fail"] == "connected(aligned:180)"

    _confirm(bdp_env,
             [_contrib("total_chips", CORE_TABLE, MAP_ID, "user"),
              _contrib("defect", CORE_TABLE, MAP_ID, "chain_ingestion")],
             reference={"table": EDS_TABLE, "map_id": MAP_ID})
    bdp_env.commit()

    after = _summary(client)
    assert after["sources"]["defect"] == "connected(aligned:180)"
    assert after["sources"]["eds_fail"] == "connected"
    assert after["frame_basis"]["kind"] == bonding_plan.BASIS_CONFIRMATION
    assert after["frame_basis"]["reference"] == {"table": EDS_TABLE, "map_id": MAP_ID}


def test_a_superseded_confirmation_does_not_decide(bdp_env, client):
    """Sealed판 is not the answer. Two판 for one unit -- only the live one may be read."""
    _seed_core(bdp_env)
    contributors = [_contrib("total_chips", CORE_TABLE, MAP_ID, "user"),
                    _contrib("defect", CORE_TABLE, MAP_ID, "chain_ingestion")]
    _confirm(bdp_env, contributors, reference={"table": EDS_TABLE, "map_id": MAP_ID})
    # v2 for the SAME unit seals v1 and points at the core map instead.
    _confirm(bdp_env, contributors, reference={"table": CORE_TABLE, "map_id": MAP_ID})
    bdp_env.commit()

    body = _summary(client)
    assert body["frame_basis"]["version"] == 2
    assert body["frame_basis"]["reference"] == {"table": CORE_TABLE, "map_id": MAP_ID}
    # v1's rot180 floor must be gone: back to the pre-confirmation markers.
    assert body["sources"]["eds_fail"] == "connected(aligned:180)"


def test_an_excluded_contributor_cannot_claim_the_confirmation(bdp_env, client):
    """A source that was refused was never aligned onto anything.

    It stays in the record (otherwise "absent" and "rejected" become indistinguishable),
    but it may not answer "is this plan's coordinate system confirmed" with yes.
    """
    _seed_core(bdp_env)
    _confirm(bdp_env,
             [_contrib("total_chips", CORE_TABLE, MAP_ID, "user",
                       excluded_reason="meta_missing"),
              _contrib("defect", "some_other_table", "OTHER", "chain_ingestion")],
             reference={"table": EDS_TABLE, "map_id": MAP_ID})
    bdp_env.commit()

    body = _summary(client)
    assert body["frame_basis"]["kind"] == bonding_plan.BASIS_ROLE_ORDER
    assert body["sources"]["eds_fail"] == "connected(aligned:180)"


# ---------------------------------------------------------------------------
# 3. The middle rung
# ---------------------------------------------------------------------------

def test_a_weak_confirmation_serves_the_middle_rung_not_either_end(bdp_env, client):
    """Aligned, and weakly supported. Four sources with one unconfirmed is not confirmed.

    The weakest contributor here is unranked, so the판 cannot warrant the frame it names --
    and yet the transform WAS computed, so `align_unavailable` would be a lie in the other
    direction. That is the rung that did not exist.
    """
    _seed_core(bdp_env)
    _confirm(bdp_env,
             [_contrib("total_chips", CORE_TABLE, MAP_ID, "user"),
              _contrib("defect", CORE_TABLE, MAP_ID, "trace_fixture_dt_log.csv")],
             reference={"table": CORE_TABLE, "map_id": MAP_ID})
    bdp_env.commit()

    body = _summary(client)
    assert body["frame_basis"]["warrant"] == fc.WARRANT_NOT_DECLARED
    assert body["frame_basis"]["weakest"]["priority"] == fc.UNRANKED
    # Neither end: not bare `connected`, not `align_unavailable`.
    assert body["sources"]["defect"] == "connected(not_declared)"
    assert body["sources"]["total_chips"] == "connected(not_declared)"
    assert body["sources"]["eds_fail"] == "connected(aligned:180,not_declared)"
    assert "align_unavailable" not in json.dumps(body["sources"])


def test_a_fully_ranked_confirmation_does_not_wear_the_middle_rung(bdp_env, client):
    """The rung must be earned. Every contributor ranked -> the plain status stands."""
    _seed_core(bdp_env)
    _confirm(bdp_env,
             [_contrib("total_chips", CORE_TABLE, MAP_ID, "user"),
              _contrib("defect", CORE_TABLE, MAP_ID, "chain_ingestion")],
             reference={"table": CORE_TABLE, "map_id": MAP_ID})
    bdp_env.commit()

    body = _summary(client)
    assert body["frame_basis"]["warrant"] == fc.WARRANT_CONFIRMED
    assert body["sources"]["defect"] == "connected"
    assert body["sources"]["eds_fail"] == "connected(aligned:180)"


def test_the_middle_rung_is_not_a_degradation_so_the_number_still_ships():
    """What a consumer DOES with the rung. It is a weaker warrant, not a loss.

    Nothing dropped out of the arithmetic, so `remaining` stays a number, no `source_degraded`
    is raised, and the `*` footnote (driven by `inactive_subtractions`, an EXACT match on
    `not_declared`) must not fire on it. If the rung ever starts reading as a degradation,
    every weakly-warranted plan collapses to 미상 -- which is the rounding this rung exists
    to stop, in the other direction.
    """
    import transfer_plan

    assert transfer_plan._status_is_degraded("connected(not_declared)") is False
    assert transfer_plan._status_is_degraded("connected(aligned:180,not_declared)") is False
    # ...while the bottom rung still is one.
    assert transfer_plan._status_is_degraded("connected(align_unavailable)") is True
    # and the role-status `not_declared` (absent table) is a different animal: exact match.
    assert "connected(not_declared)" != bonding_plan.STATUS_NOT_DECLARED


def test_the_middle_rung_does_not_fire_the_inactive_subtractions_footnote(bdp_env, client):
    """`inactive_subtractions` means "this subtraction never ran". A weakly-warranted
    defect count DID run. The two share a word and must not share a field."""
    _seed_core(bdp_env)
    _confirm(bdp_env,
             [_contrib("total_chips", CORE_TABLE, MAP_ID, "user"),
              _contrib("defect", CORE_TABLE, MAP_ID, "trace_fixture_dt_log.csv")],
             reference={"table": CORE_TABLE, "map_id": MAP_ID})
    bdp_env.commit()

    body = _summary(client)
    assert body["sources"]["defect"] == "connected(not_declared)"
    assert "inactive_subtractions" not in body
    assert body["chips"]["remaining"] == 30      # still a number, nothing dropped out


def test_the_middle_rung_is_not_a_sixth_token(bdp_env, client):
    """`config_resolve_report.py:404` -- adding a word to a closed vocabulary is a contract
    change. Pin the rung to the canonical spelling so a rename upstream cannot leave a
    second one behind (same discipline as `test_binding_refusal.py`)."""
    assert fc.WARRANT_NOT_DECLARED == config_resolve_report.REASON_NOT_DECLARED
    assert bonding_plan.STATUS_NOT_DECLARED == config_resolve_report.REASON_NOT_DECLARED
    assert bonding_plan.BINDING_MAPPING_UNAVAILABLE == \
        config_resolve_report.REASON_MAPPING_UNAVAILABLE


# ---------------------------------------------------------------------------
# 4. A confirmation that cannot supply a floor
# ---------------------------------------------------------------------------

def test_a_confirmation_with_no_reference_falls_back_but_still_names_itself(bdp_env, client):
    """`map_alignment.REFERENCE_ABSENT` is common. A판 scored without a common floor cannot
    hand the plan one -- but the plan must still say WHICH판 could not."""
    _seed_core(bdp_env)
    h = _confirm(bdp_env, [_contrib("total_chips", CORE_TABLE, MAP_ID, "user")],
                 reference=None)
    bdp_env.commit()

    basis = _summary(client)["frame_basis"]
    assert basis["kind"] == bonding_plan.BASIS_ROLE_ORDER
    assert basis["reason"] == config_resolve_report.REASON_NOT_DECLARED
    assert basis["confirmation_uid"] == h.confirmation_uid


def test_an_unreadable_reference_is_mapping_unavailable_not_not_declared(bdp_env, client):
    """Two different repairs, so two different words. "You never declared a floor" sends the
    operator to declare one; "your declared floor did not load" sends them to the map that
    is missing its meta. Folding them invites the wrong fix."""
    _seed_core(bdp_env)
    _confirm(bdp_env, [_contrib("total_chips", CORE_TABLE, MAP_ID, "user")],
             reference={"table": CORE_TABLE, "map_id": "NO_SUCH_MAP"})
    bdp_env.commit()

    basis = _summary(client)["frame_basis"]
    assert basis["kind"] == bonding_plan.BASIS_ROLE_ORDER
    assert basis["reason"] == config_resolve_report.REASON_MAPPING_UNAVAILABLE
    assert basis["reference"] == {"table": CORE_TABLE, "map_id": "NO_SUCH_MAP"}


# ---------------------------------------------------------------------------
# 5. One spelling, two consumers
# ---------------------------------------------------------------------------

def test_transfer_plan_asks_the_same_function_for_the_canonical_frame(bdp_env, monkeypatch):
    """M1 and M2 must not pick different floors for the same wafer.

    `transfer_plan._core_region_counts` already orders its adapter by
    `bonding_plan.CANONICAL_FRAME_ROLES` precisely so the two agree; the moment M1 starts
    reading a confirmation and M2 does not, that agreement is gone and the same wafer
    reports two numbers. So M2's canonical resolver must reach the same function.
    """
    import transfer_plan

    seen = []
    real = bonding_plan.canonical_basis

    def spy(db, config, map_pairs, meta_cache=None):
        seen.append(list(map_pairs))
        return real(db, config, map_pairs, meta_cache)

    monkeypatch.setattr(bonding_plan, "canonical_basis", spy)

    cfg = bonding_plan.load_bonding_plan_config()
    adapter = {"identity": cfg.get("core_identity"),
               "map_metadata": cfg.get("map_metadata"),
               "fail_sources": {k: dict(v, frame="origin")
                                for k, v in (cfg.get("sources") or {}).items()
                                if v.get("mode") == "map"}}
    transfer_plan._canonical_origin_meta(bdp_env, adapter, "LOTX", "01")

    assert seen, "transfer_plan resolved a canonical frame without consulting layer 8"
    assert (CORE_TABLE, MAP_ID) in seen[0]
