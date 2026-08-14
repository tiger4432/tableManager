# -*- coding: utf-8 -*-
"""`GET /api/ledger/siblings` — the answer key, asserted in BOTH directions.

WHY THIS RUNS AGAINST REAL PostgreSQL OR SKIPS
-----------------------------------------------
`GROUPING SETS`, `count(DISTINCT …) FILTER (…)`, `array_agg(…)[a:b]` and `= ANY(%s)` have
no SQLite spelling. A suite that ran here on in-memory SQLite would prove nothing about
what the endpoint does ("SQLite accepts what PostgreSQL refuses" — paid for three times
in this project), so these tests build a scratch schema in an ISOLATED database and drop
it at teardown, or they skip. They never quietly downgrade.

🔴 THE FIXTURE IS OURS, AND IT HAS AN ANSWER KEY
-------------------------------------------------
`assy_manager` holds a large synthetic fixture whose factors are, as of 2026-08-14,
UNBIASED — equipment and recipe are deterministic functions of lot and slot and are never
used to bias a defect (measured: every `bond_eqp` enrichment lands in 0.99-1.02). That
makes it an excellent DECOY corpus and a useless positive control, so the planted factor
is planted here, by this file, where its true value is known:

    bond_eqp = BAD-1     80% of its packages have a void   ← THE PLANTED FACTOR (void)
    bond_eqp = GOOD-1    10% of its packages have a void
    bond_lot = LOT-A     carried by 100% of EVERY package  ← DECOY
    b_bn     = 1         carried by ~50% of both sides     ← DECOY

🔴 AND BOTH DIRECTIONS ARE ASSERTED, WHICH IS THE POINT.
A test that only asserts "the planted factor is found" cannot tell a working contrast
from one that returns everything: an intersection returns the planted factor too. The
test that distinguishes them is `test_contrast_drops_the_decoy_that_intersection_tops`,
where `bond_lot = LOT-A` is the FIRST row of intersection (share 1.0) and must be ABSENT
from contrast. If contrast is broken in the direction of permissiveness, that assertion
is the only one here that fails.
"""
import contextlib
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import finding_kinds                                                  # noqa: E402
import ledger_siblings                                                # noqa: E402

PG_TEST_URL_ENV = "ASSY_PG_TEST_DATABASE_URL"
SCRATCH_SCHEMA = "assy_siblings_pytest" + (
    "_" + os.environ["PYTEST_XDIST_WORKER"]
    if os.environ.get("PYTEST_XDIST_WORKER") else "")


def _resolve_url():
    import db_safety
    from database.database import DEFAULT_PG_URL

    url = os.environ.get(PG_TEST_URL_ENV) or None
    if not url:
        candidate = os.environ.get(db_safety.TEST_DATABASE_URL_ENV) or ""
        url = candidate if candidate.startswith("postgres") else None
    if not url:
        return None, (f"no PostgreSQL test database declared. Set {PG_TEST_URL_ENV} to "
                      f"an ISOLATED database, e.g. postgresql://…@localhost:5432/assy_qa")
    violations = db_safety.check_test_database(url, production_url=DEFAULT_PG_URL,
                                               opt_in=url)
    if violations:
        return None, f"{PG_TEST_URL_ENV} is not usable: {violations[0]}"
    from sqlalchemy.engine import make_url
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql":
        return None, f"{PG_TEST_URL_ENV} is not a PostgreSQL URL"
    if (parsed.database or "") == "assy_manager":
        return None, "refusing to run schema DDL against 'assy_manager'"
    return url, None


@contextlib.contextmanager
def _declared_as_test_database(url):
    import db_safety
    key = db_safety.TEST_DATABASE_URL_ENV
    previous = os.environ.get(key)
    os.environ[key] = url
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = previous


DDL = """
CREATE TABLE bonding_log (
    bond_cell_key TEXT PRIMARY KEY,
    base_id       TEXT, bx INT, by INT,
    bond_lot      TEXT, bond_eqp TEXT, b_bn TEXT, stack_height INT
);
CREATE TABLE inspection_run (
    run_uid       TEXT PRIMARY KEY,
    method        TEXT,
    base_wafer_id TEXT, base_x INT, base_y INT, stack_gate INT,
    recipe_id     TEXT, eqp_id TEXT, observed_at TIMESTAMPTZ
);
CREATE TABLE void_obs (
    void_uid TEXT PRIMARY KEY, run_uid TEXT,
    base_wafer_id TEXT, base_x INT, base_y INT, stack_gate INT,
    radius_x DOUBLE PRECISION, radius_y DOUBLE PRECISION, unit TEXT
);
CREATE TABLE delam_obs (
    delam_uid TEXT PRIMARY KEY, run_uid TEXT,
    base_wafer_id TEXT, base_x INT, base_y INT, stack_gate INT,
    extent_x DOUBLE PRECISION, extent_y DOUBLE PRECISION, unit TEXT
);
"""

#: The universe: 300 bonded packages. Only 200 are ever scanned, so 100 are NEVER
#: SCANNED — and the assertion that they stay out of `clean_scanned` is the one this
#: whole three-way split exists for.
N_UNIVERSE, N_SCANNED = 300, 200
VOID_EQP, CLEAN_EQP = "BAD-1", "GOOD-1"          # void's factor lives on `bond_eqp`
DELAM_BN, CLEAN_BN = "DEL-1", "DEL-0"            # delam's factor lives on `b_bn`
DECOY_LOT = "LOT-A"        # carried by every SCANNED package, found and clean alike
GHOST_LOT = "LOT-GHOST"    # carried ONLY by the 100 packages nobody ever scanned


def _plant(connection):
    """The answer key. Deterministic, not sampled — so the assertions can be equalities.

    THE TWO KINDS' FACTORS ARE ON DIFFERENT AXES AND ARE INDEPENDENT (`i % 2` against
    `i % 3`). That is deliberate: if they shared an axis, "delam's answer does not
    contain void's factor" would be true by construction rather than by the query being
    right, and the generalisation would be untested.
    """
    with connection.cursor() as cur:
        for i in range(N_UNIVERSE):
            cur.execute(
                "INSERT INTO bonding_log VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (f"PKG-{i:03d}", f"W-{i:03d}", i, 0,
                 DECOY_LOT if i < N_SCANNED else GHOST_LOT,    # decoy / never-scanned
                 VOID_EQP if i % 2 == 0 else CLEAN_EQP,        # void's planted factor
                 DELAM_BN if i % 3 == 0 else CLEAN_BN,         # delam's planted factor
                 12))                                          # decoy: everybody
        for i in range(N_SCANNED):
            for method in ("sat", "scat"):
                cur.execute(
                    "INSERT INTO inspection_run VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (f"{method}|W-{i:03d}", method, f"W-{i:03d}", i, 0, 3,
                     f"RCP-{method}", f"SCAN-{method}", "2026-08-10T00:00:00+00:00"))
            # 🔴 A RE-SCAN, and it is not decoration. Every fifth package is scanned
            # TWICE by the same method with the same recipe. Without this the fixture
            # cannot tell `count(*)` from `count(DISTINCT unit)` - the fan-out defect
            # would be injectable and nothing would go red, which is what a green
            # suite over an inactive defect axis looks like from the outside.
            if i % 5 == 0:
                cur.execute(
                    "INSERT INTO inspection_run VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (f"sat|W-{i:03d}|rescan", "sat", f"W-{i:03d}", i, 0, 3,
                     "RCP-sat", "SCAN-sat", "2026-08-11T00:00:00+00:00"))
            if (i // 2) % 10 < (8 if i % 2 == 0 else 1):
                cur.execute(
                    "INSERT INTO void_obs (void_uid, run_uid, base_wafer_id, base_x, "
                    "base_y, stack_gate) VALUES (%s,%s,%s,%s,%s,%s)",
                    (f"sat|W-{i:03d}|1", f"sat|W-{i:03d}", f"W-{i:03d}", i, 0, 3))
            if (i // 3) % 10 < (8 if i % 3 == 0 else 1):
                cur.execute(
                    "INSERT INTO delam_obs (delam_uid, run_uid, base_wafer_id, base_x, "
                    "base_y, stack_gate) VALUES (%s,%s,%s,%s,%s,%s)",
                    (f"scat|W-{i:03d}|1", f"scat|W-{i:03d}", f"W-{i:03d}", i, 0, 3))
    connection.commit()


REGISTRY = {
    "void": {"label": "보이드", "observed_by": ["sat"], "observation_table": "void_obs",
             "extent_columns": ["radius_x", "radius_y"], "unit_column": "unit"},
    "delam": {"label": "박리", "observed_by": ["scat"], "observation_table": "delam_obs",
              "extent_columns": ["extent_x", "extent_y"], "unit_column": "unit"},
    # 🔴 The honest-degradation kind: an ad-hoc human observation with NO systematic
    # scan behind it, hence NO denominator. `observed_by: []` is a DECLARATION.
    "om_scratch": {"label": "스크래치", "observed_by": [],
                   "observation_table": "void_obs",
                   "extent_columns": ["radius_x", "radius_y"], "unit_column": "unit"},
}

AXES = {
    "version": 1,
    "defaults": {"limit": 50, "min_support": 2, "evidence_ref_sample": 3,
                 "contrast": {"enriched_at": 1.5, "depleted_at": 0.6667}},
    "geometry": {
        "unit": "package", "unit_label": "패키지",
        "unit_columns": ["base_wafer_id", "base_x", "base_y"],
        "run_key_column": "run_uid", "run_method_column": "method",
        "run_time_column": "observed_at", "observation_run_ref_column": "run_uid",
        "universe": {"relation": "bonding_log",
                     "join": {"base_wafer_id": "base_id", "base_x": "bx",
                              "base_y": "by"}},
    },
    "attribution": [{
        "relation": "bonding_log", "about": "process", "label": "본딩",
        "key_column": "bond_cell_key",
        "join": {"base_wafer_id": "base_id", "base_x": "bx", "base_y": "by"},
        "axes": [{"name": "bond_eqp", "label": "본딩 장비", "column": "bond_eqp"},
                 {"name": "bond_lot", "label": "본딩 랏", "column": "bond_lot"},
                 {"name": "b_bn", "label": "판정", "column": "b_bn"}],
    }, {
        # The relation that FANS OUT (a package may have several runs) and that holds
        # OTHER kinds' rows. Both hazards live here, so both are exercised.
        "relation": "inspection_run", "about": "inspection", "label": "검사",
        "key_column": "run_uid",
        "join": {"base_wafer_id": "base_wafer_id", "base_x": "base_x",
                 "base_y": "base_y"},
        "filter": {"column": "method", "values_from": "observed_by"},
        "axes": [{"name": "scan_recipe", "label": "검사 레시피", "column": "recipe_id"},
                 {"name": "scan_eqp", "label": "검사 장비", "column": "eqp_id"}],
    }],
    "kinds": {},
}


@pytest.fixture(scope="module")
def pg():
    url, reason = _resolve_url()
    if url is None:
        pytest.skip(reason)
    try:
        import psycopg2                                              # noqa: F401
    except Exception as exc:                                         # pragma: no cover
        pytest.skip(f"psycopg2 is not importable: {exc}")
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.pool import NullPool

    with _declared_as_test_database(url):
        admin = create_engine(url, poolclass=NullPool)
        try:
            with admin.begin() as conn:
                conn.execute(text("SELECT 1"))
        except OperationalError as exc:
            admin.dispose()
            pytest.skip(f"PostgreSQL is not reachable: "
                        f"{str(exc).strip().splitlines()[0]}")
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{SCRATCH_SCHEMA}" CASCADE'))
            conn.execute(text(f'CREATE SCHEMA "{SCRATCH_SCHEMA}"'))
        engine = create_engine(
            url, poolclass=NullPool,
            connect_args={"options": f"-csearch_path={SCRATCH_SCHEMA}"})
        raw = engine.raw_connection()
        with raw.cursor() as cur:
            cur.execute(DDL)
        raw.commit()
        _plant(raw)
        try:
            yield raw
        finally:
            raw.close()
            engine.dispose()
            with admin.begin() as conn:
                conn.execute(text(f'DROP SCHEMA IF EXISTS "{SCRATCH_SCHEMA}" CASCADE'))
                # ASK THE CATALOGUE. "I issued a DROP" is not the same fact as "it is
                # gone" - a reviewer left 92 objects behind on 2026-08-12 believing it was.
                left = conn.execute(text(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema = :s"), {"s": SCRATCH_SCHEMA}).scalar()
                assert left == 0, f"{left} object(s) left behind in {SCRATCH_SCHEMA}"
            admin.dispose()


@pytest.fixture(autouse=True)
def declarations():
    finding_kinds.set_registry(REGISTRY)
    ledger_siblings.set_axes_config(AXES)
    yield
    finding_kinds.set_registry(None)
    ledger_siblings.set_axes_config(None)


def _row(answer, axis, value):
    for f in answer["factors"]:
        if f["axis"] == axis and f["value"] == value:
            return f
    return None


# ------------------------------------------------------------------ the three-way split
def test_never_scanned_is_its_own_count_and_never_joins_the_clean_side(pg):
    """The defect this whole split exists to prevent, asserted as arithmetic.

    100 of the 300 bonded packages were never scanned, and they are the only carriers of
    `bond_lot = LOT-GHOST`. So the leak is not merely counted, it is OBSERVABLE: if a
    never-scanned package could reach the clean side, `LOT-GHOST` would appear as a
    factor row with 100 clean units behind it and would read as "a lot that is unusually
    clean". It must appear NOWHERE, in either mode.
    """
    answer = ledger_siblings.siblings(pg, kind="void", limit=200)
    pops = answer["populations"]
    assert pops["scanned"]["count"] == N_SCANNED
    assert pops["universe"]["count"] == N_UNIVERSE
    assert pops["never_scanned"]["count"] == N_UNIVERSE - N_SCANNED == 100
    assert pops["found"]["count"] + pops["clean_scanned"]["count"] == \
        pops["scanned"]["count"], "the two scanned buckets must exhaust the scanned set"

    assert _row(answer, "bond_lot", GHOST_LOT) is None, \
        "a NEVER-SCANNED package reached a population it was never looked at for"
    contrast = ledger_siblings.siblings(pg, kind="void", mode="contrast", limit=200)
    assert _row(contrast, "bond_lot", GHOST_LOT) is None

    assert answer["denominator"]["state"] == "ready"
    assert answer["denominator"]["basis"] == "inspection_run"
    assert answer["denominator"]["methods"] == ["sat"]


def test_a_rescanned_package_is_one_package_and_not_two(pg):
    """Every fifth package carries two `sat` runs with the same recipe.

    Counting attribution ROWS would report that recipe as covering 20% more packages
    than exist — a numerator above its own denominator, on the one screen whose rule is
    that every rate carries one.
    """
    answer = ledger_siblings.siblings(pg, kind="void", limit=200)
    recipe = _row(answer, "scan_recipe", "RCP-sat")
    assert recipe is not None
    assert recipe["found"]["n"] == answer["populations"]["found"]["count"], \
        "every found package was scanned by this recipe, so the two must be equal"
    assert recipe["clean_scanned"]["n"] == \
        answer["populations"]["clean_scanned"]["count"]


def test_the_other_kinds_scans_do_not_become_this_kinds_factors(pg):
    """`inspection_run` holds every method's rows; a void answer may not carry `scat`'s.

    Measured on the real fixture before the narrowing existed: `SYN_DELAM_R1`, the
    delamination scanner's recipe, appeared as a factor of VOIDS purely because the same
    packages had also been scanned for delamination.
    """
    answer = ledger_siblings.siblings(pg, kind="void", limit=200)
    assert _row(answer, "scan_recipe", "RCP-sat") is not None
    assert _row(answer, "scan_recipe", "RCP-scat") is None, \
        "another method's recipe leaked into this kind's factors"


def test_every_rate_carries_its_denominator(pg):
    answer = ledger_siblings.siblings(pg, kind="void", limit=200)
    for factor in answer["factors"]:
        assert factor["found"]["of"] == answer["populations"]["found"]["count"]
        assert factor["clean_scanned"]["of"] == \
            answer["populations"]["clean_scanned"]["count"]
        assert factor["found"]["n"] <= factor["found"]["of"], \
            "a numerator larger than its denominator means units were double counted"
        assert factor["evidence_refs"], "every row carries its evidence refs"
        assert factor["evidence_ref_count"] == factor["found"]["n"]


# ------------------------------------------------------- the answer key, both directions
def test_contrast_finds_the_planted_factor(pg):
    answer = ledger_siblings.siblings(pg, kind="void", mode="contrast")
    planted = _row(answer, "bond_eqp", VOID_EQP)
    assert planted is not None, "the planted factor is missing from contrast"
    assert planted["enrichment"] > 1.5
    assert planted["enrichment_state"] == "enriched"
    assert planted["enrichment_ci"][0] > 1.5, "ranked on the interval's lower bound"


def test_contrast_drops_the_decoy_that_intersection_tops(pg):
    """🔴 THE ASSERTION THAT DISTINGUISHES A WORKING CONTRAST FROM A BROKEN ONE.

    `bond_lot = LOT-A` is carried by EVERY package, found and clean alike. A plain
    intersection reports it first and it is worthless; contrast must drop it. Without
    this, a contrast that simply returned everything would pass the test above.
    """
    intersection = ledger_siblings.siblings(pg, kind="void", mode="intersection")
    decoy = _row(intersection, "bond_lot", DECOY_LOT)
    assert decoy is not None and decoy["found"]["rate"] == 1.0
    assert intersection["factors"][0]["value"] == DECOY_LOT, \
        "the decoy must TOP intersection, or this test is not testing what it claims"

    contrast = ledger_siblings.siblings(pg, kind="void", mode="contrast")
    assert _row(contrast, "bond_lot", DECOY_LOT) is None, \
        "the decoy survived contrast - base-rate comparison is not being applied"


def test_switching_the_kind_switches_the_answer_and_not_only_the_heading(pg):
    """Each kind must find ITS OWN planted factor and not the other kind's.

    This is what a `finding_kind='void'` literal anywhere below the default would break,
    and it would break it silently: the heading would say `delam` and the numbers would
    be void's.
    """
    void = ledger_siblings.siblings(pg, kind="void", mode="contrast")
    delam = ledger_siblings.siblings(pg, kind="delam", mode="contrast")

    assert void["denominator"]["methods"] == ["sat"]
    assert delam["denominator"]["methods"] == ["scat"]
    assert void["populations"]["found"]["count"] != delam["populations"]["found"]["count"]

    assert _row(void, "bond_eqp", VOID_EQP) is not None
    assert _row(void, "b_bn", DELAM_BN) is None, \
        "void's answer carries the OTHER kind's planted factor"
    assert _row(delam, "b_bn", DELAM_BN) is not None
    assert _row(delam, "bond_eqp", VOID_EQP) is None, \
        "delam's answer carries the OTHER kind's planted factor"


# --------------------------------------------------------------- honest degradation
def test_a_kind_with_no_denominator_degrades_instead_of_inventing_one(pg):
    """Intersection still works; contrast says 「분모 없음 — 대조 불가」 WITH the reason.

    And the clean buckets come back `null`, never `0`: a zero there is the CLAIM that
    nothing was clean, and a screen cannot tell an invented zero from a measured one.
    """
    answer = ledger_siblings.siblings(pg, kind="om_scratch", mode="contrast")
    assert answer["state"] == "ready"
    assert answer["populations"]["found"]["count"] > 0, "intersection still answers"
    assert answer["factors"], "the shared-factor list is still computed"

    assert answer["populations"]["clean_scanned"]["count"] is None
    assert answer["populations"]["never_scanned"]["count"] is None
    assert answer["denominator"]["state"] == "absent"
    assert answer["denominator"]["reason"] == \
        ledger_siblings.REASON_NO_OBSERVED_BY
    assert "분모 없음" in answer["denominator"]["message"]
    assert any(n["note"] == "contrast_unavailable" for n in answer["notes"])

    for factor in answer["factors"]:
        assert factor["clean_scanned"] is None
        assert factor["enrichment"] is None
        assert factor["enrichment_state"] == "undeterminable", \
            "'undeterminable' is not 'flat' - one is a missing judgement, not a verdict"
        assert factor["reason"] == ledger_siblings.REASON_NO_OBSERVED_BY


def test_an_undeclared_kind_is_refused_by_name_and_never_defaulted(pg):
    with pytest.raises(ledger_siblings.SiblingsRequestError) as caught:
        ledger_siblings.siblings(pg, kind="no_such_kind")
    detail = caught.value.detail
    assert detail["reason"] == ledger_siblings.REASON_UNKNOWN_KIND
    assert "void" in detail["declared_kinds"]


@pytest.mark.parametrize("spec", ["7 days", "0d", "2026-08-10..2026-08-01", "last week"])
def test_a_malformed_window_is_a_structured_refusal(pg, spec):
    with pytest.raises(ledger_siblings.SiblingsRequestError) as caught:
        ledger_siblings.siblings(pg, kind="void", window=spec)
    assert caught.value.detail["reason"] == ledger_siblings.REASON_BAD_WINDOW


def test_an_absent_observation_relation_is_an_answer_and_not_an_error(pg):
    registry = dict(REGISTRY)
    registry["ghost"] = dict(REGISTRY["void"], observation_table="no_such_obs")
    finding_kinds.set_registry(registry)
    answer = ledger_siblings.siblings(pg, kind="ghost")
    assert answer["state"] == "absent"
    assert answer["denominator"]["reason"] == \
        ledger_siblings.REASON_FINDING_RELATION_ABSENT
    assert answer["populations"]["found"]["count"] is None, "absent is not zero"
