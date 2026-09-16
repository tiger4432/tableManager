"""Stage 6 PostgreSQL E2E for the compiled Ledger v2 transaction.

This module never falls back to SQLite.  It runs only when the operator declares an
isolated PostgreSQL database, creates a disposable Ledger schema plus uniquely named
physical source tables, and proves descriptor issuance against PostgreSQL's real UNIQUE
catalog before compiling the snapshot.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import json
import os

import pandas as pd
import pytest
from sqlalchemy import Column, DateTime, String, create_engine, text

# Every test here drives `clean_pg_v2`, which skips without a declared PostgreSQL (S-256).
pytestmark = pytest.mark.pg
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool

from ledger import gate, schema
from ledger.runtime_v2 import execute_scoped_batch, preview_cursor_batch
from ledger.roleframe import DeclarativeRoleMapper, RoleMapperImplementationRegistry
from ledger.setup_bundle import validate_bundle
from ledger.setup_registry import compile_setup_snapshot
from ledger.source_preparation import (
    DirectJoinSourcePreparer,
    JoinRightRow,
    SQLAlchemyVerifiedJoinBatchReader,
    SourcePreparationError,
    SourcePreparerImplementationRegistry,
)
from ledger.setup_registry import cursor_translator_version
from ledger.store import LedgerStore
from ledger.trace import relation_exists
from test_ledger_setup_bundle import logical_bundle, logical_catalog
from test_ledger_setup_registry import trusted_implementations
from chain import legacy_join_declaration
from chain import join_key_index


# TOMBSTONE: THE GATE MOVED OUT (S-115). This file carried its own `_resolve_url` and its
# own `db_safety` context manager, and they were the copy WITHOUT the `dev_env` fallback -
# so every proof here reported "skipped" on a machine where the other suite ran, and stayed
# quiet through a `backfill.run` call in the retired v1 shape and a call to
# `ledger_trace.trace`, which does not exist. One gate now answers for both.
from tests.support.isolated_pg import (       # noqa: E402
    PG_TEST_URL_ENV,
    declared_as_test_database as _declared,
    install_trigram,
    resolve_url as _resolve_url,
    scratch_connect_args,
    scratch_schema,
)

#: Process-unique already before S-116 - this file put the pid in the name and was the one
#: of the three that never flapped. It now says it through the shared helper.
SCRATCH_SCHEMA = scratch_schema("assy_ledger_v2_s6")
RUN_TOKEN = SCRATCH_SCHEMA.split("assy_ledger_v2_s6_", 1)[1]


SOURCE_TABLE = f"v2s6_input_rows_{RUN_TOKEN}"
RIGHT_TABLE = f"v2s6_reference_rows_{RUN_TOKEN}"
UNIQUE_INDEX = f"uq_v2s6_reference_{RUN_TOKEN}"
NOW = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)


def _bundle():
    raw = logical_bundle()
    join = raw["virtual_joins"]["input_to_reference"]
    join["left_table"] = SOURCE_TABLE
    join["right_table"] = RIGHT_TABLE
    # ⚰️ `materialize` / `max_rewrite_rows` WERE SET HERE FOR ONE COMMIT. I declared them
    # locally because only this file needed them and eleven files share `logical_bundle`.
    # 판정 481 then made the BUNDLE VALIDATOR require the field of every bundle, so the
    # shared fixture had to carry it - and a local copy would have been a second author of
    # the same declaration. It is in `logical_bundle` now.
    raw["sources"]["input_rows"]["relation"] = SOURCE_TABLE
    return raw


def _catalog():
    """The scratch plant's physical schema, under this run's disposable table names.

    Built from `logical_catalog` -- the fixture's PHYSICAL half -- and never from the
    bundle `_bundle()` returns.  The ledger stopped carrying a `tables` section precisely
    so the two halves can disagree; deriving one from the other here would put the
    unfalsifiable check back.  See the docstring on `logical_catalog`.
    """
    catalog = copy.deepcopy(dict(logical_catalog()))
    catalog[SOURCE_TABLE] = catalog.pop("input_rows")
    catalog[RIGHT_TABLE] = catalog.pop("reference_rows")
    catalog[RIGHT_TABLE]["indexes"][0]["name"] = UNIQUE_INDEX
    return catalog


CATALOG = _catalog()


def _known_tables(catalog):
    return {
        table: {"column_types": dict(config["columns"])}
        for table, config in catalog.items()
    }


def _registries():
    preparer_registry = SourcePreparerImplementationRegistry()
    preparer_registry.register("prepare-input", 1, DirectJoinSourcePreparer)
    mapper_registry = RoleMapperImplementationRegistry()
    mapper_registry.register("map-transition-role", 1, DeclarativeRoleMapper)
    return preparer_registry.seal(), mapper_registry.seal()


@pytest.fixture(scope="module")
def pg_v2(tmp_path_factory):
    url, reason = _resolve_url()
    if url is None:
        pytest.skip(reason)
    try:
        import psycopg2  # noqa: F401
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"psycopg2 unavailable: {exc}")

    with _declared(url):
        admin = create_engine(url, poolclass=NullPool)
        runtime = create_engine(
            url, poolclass=NullPool,
            connect_args=scratch_connect_args(SCRATCH_SCHEMA),
        )
        with admin.begin() as connection:
            connection.execute(text(
                f'DROP TABLE IF EXISTS public."{SOURCE_TABLE}" CASCADE'))
            connection.execute(text(
                f'DROP TABLE IF EXISTS public."{RIGHT_TABLE}" CASCADE'))
            connection.execute(text(
                f'DROP SCHEMA IF EXISTS "{SCRATCH_SCHEMA}" CASCADE'))
            connection.execute(text(f'CREATE SCHEMA "{SCRATCH_SCHEMA}"'))
            # `pg_trgm` inside the scratch schema, so it goes with the DROP at teardown
            # instead of needing its own `extension_created` bookkeeping in `public`.
            install_trigram(connection, SCRATCH_SCHEMA)
            connection.execute(text(f'''
                CREATE TABLE public."{SOURCE_TABLE}" (
                    record_id TEXT PRIMARY KEY,
                    join_id TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    event_at TIMESTAMPTZ NOT NULL,
                    event_key TEXT NOT NULL
                )'''))
            connection.execute(text(f'''
                CREATE TABLE public."{RIGHT_TABLE}" (
                    row_id TEXT PRIMARY KEY,
                    updated_at TIMESTAMPTZ NOT NULL,
                    join_id TEXT NOT NULL,
                    target_id TEXT NOT NULL
                )'''))
            # 🔴 NULL-SAFE, AND THE EXPRESSION COMES FROM THE ONE PRODUCER
            # (S-181, 판정 287). A plain `UNIQUE (join_id)` calls two NULLs
            # DISTINCT, so it never enforced the uniqueness this join is approved
            # against, and the gate stopped accepting it. Spelling the `coalesce` by
            # hand here would put a SECOND spelling in the tree - the exact drift that
            # turns a matching index into a sequential scan nobody ordered - so it is
            # asked for rather than written.
            connection.execute(text(
                f'CREATE UNIQUE INDEX "{UNIQUE_INDEX}" '
                f'ON public."{RIGHT_TABLE}" '
                f'({join_key_index.index_key_expression("join_id")})'))

        raw = _bundle()
        config_path = tmp_path_factory.mktemp("ledger_v2_s6") / "virtual_joins.json"
        config_path.write_text(json.dumps(raw["virtual_joins"]), encoding="utf-8")
        Maker = sessionmaker(bind=admin, autoflush=False)
        verifier_session = Maker()
        try:
            # 🔴 `rejections` IS COLLECTED SO THE FAILURE CAN SAY WHY. Without it this
            # fixture failed as `assert 0 == 1  where 0 = len(())` - true, and silent about
            # which of the loader's several refusals fired. The loader already offers the
            # list; not passing it was the whole distance between a number and a sentence.
            rejections = []
            verified = tuple(legacy_join_declaration.load_verified_rules(
                verifier_session, path=str(config_path),
                known_tables=_known_tables(CATALOG), rejections=rejections))
        finally:
            verifier_session.close()
        assert len(verified) == 1, (
            "the join declaration did not verify, so nothing below measures anything. "
            "Refusals: %r" % (rejections,))
        assert verified[0].unique_index == UNIQUE_INDEX
        compiled = compile_setup_snapshot(
            validate_bundle(raw, catalog=CATALOG), trusted_implementations(),
            verified, catalog=CATALOG)

        RightBase = declarative_base()

        class RightModel(RightBase):
            __tablename__ = RIGHT_TABLE
            __table_args__ = {"schema": "public"}
            row_id = Column(String, primary_key=True)
            updated_at = Column(DateTime(timezone=True), nullable=False)
            join_id = Column(String, nullable=False)
            target_id = Column(String, nullable=False)

        from database import models
        previous_model = models.DYNAMIC_TABLES.get(RIGHT_TABLE)
        models.DYNAMIC_TABLES[RIGHT_TABLE] = RightModel
        store = LedgerStore(runtime, who="ledger-v2-stage6")
        store.ensure_schema()

        try:
            yield {
                "admin": admin, "runtime": runtime, "compiled": compiled,
                "store": store, "sessionmaker": sessionmaker(
                    bind=runtime, autoflush=False),
            }
        finally:
            if previous_model is None:
                models.DYNAMIC_TABLES.pop(RIGHT_TABLE, None)
            else:
                models.DYNAMIC_TABLES[RIGHT_TABLE] = previous_model
            runtime.dispose()
            with admin.begin() as connection:
                connection.execute(text(
                    f'DROP SCHEMA IF EXISTS "{SCRATCH_SCHEMA}" CASCADE'))
                connection.execute(text(
                    f'DROP TABLE IF EXISTS public."{SOURCE_TABLE}" CASCADE'))
                connection.execute(text(
                    f'DROP TABLE IF EXISTS public."{RIGHT_TABLE}" CASCADE'))
                left = connection.execute(text(
                    "SELECT count(*) FROM information_schema.schemata "
                    "WHERE schema_name=:schema"), {"schema": SCRATCH_SCHEMA}).scalar()
                assert left == 0
            admin.dispose()


@pytest.fixture
def clean_pg_v2(pg_v2):
    with pg_v2["runtime"].begin() as connection:
        connection.execute(text(f"TRUNCATE {schema.LEDGER_TABLE} CASCADE"))
        connection.execute(text(f"TRUNCATE {schema.CURSOR_TABLE}"))
    with pg_v2["admin"].begin() as connection:
        connection.execute(text(f'TRUNCATE public."{SOURCE_TABLE}"'))
        connection.execute(text(f'TRUNCATE public."{RIGHT_TABLE}"'))
    gate.reset_counters()
    yield pg_v2
    gate.reset_counters()


def _seed(case, *, with_right=True):
    with case["admin"].begin() as connection:
        connection.execute(text(f'''
            INSERT INTO public."{SOURCE_TABLE}"
                (record_id, join_id, source_id, event_at, event_key)
            VALUES ('R-0001', 'J-0001', 'IN-0001', :event_at, 'E-0001')
        '''), {"event_at": NOW})
        if with_right:
            connection.execute(text(f'''
                INSERT INTO public."{RIGHT_TABLE}"
                    (row_id, updated_at, join_id, target_id)
                VALUES ('RIGHT-1', :updated_at, 'J-0001', 'OUT-J-0001')
            '''), {"updated_at": NOW})


def _base_batch(case):
    columns = case["compiled"].source_plans["input_rows"]
    physical = tuple(sorted({
        *columns.driver.identity, *columns.driver.group_by,
        *columns.driver.order_by, *columns.driver.cursor_columns,
        columns.driver.occurred_at.column,
        *columns.driver.preparation.preparer.input_columns,
        *(column for column in columns.driver.mapper.input_columns
          if column not in columns.driver.preparation.preparer.output_columns),
    }))
    assert "target_id" not in physical
    selected = ", ".join(f'"{column}"' for column in physical)
    with case["admin"].connect() as connection:
        rows = connection.execute(text(
            f'SELECT {selected} FROM public."{SOURCE_TABLE}" '
            'ORDER BY event_at, record_id LIMIT 1000')).mappings().all()
    return pd.DataFrame([dict(row) for row in rows], columns=physical)


def _cursor(base):
    return {"event_at": base.iloc[-1]["event_at"],
            "record_id": base.iloc[-1]["record_id"]}


def _scope(base):
    """Every row of this batch, named. The live door refuses an unscoped whole-source write.

    These proofs used to drive `execute_cursor_batch`, which took a cursor here and wrote
    the position; it retired with S-113 ⓐ (ruling 221) for having no product caller after
    S-76. The storage properties below - one transaction, dedupe on replay, a refusal
    leaving nothing behind - belong to the door the live path uses, so that is the door
    they are asked of.
    """
    return ("join_id", sorted(base["join_id"].tolist()))


def _counts(case):
    with case["runtime"].connect() as connection:
        atoms = connection.execute(text(
            f"SELECT count(*) FROM {schema.LEDGER_TABLE}")).scalar()
        cursors = connection.execute(text(
            f"SELECT count(*) FROM {schema.CURSOR_TABLE}")).scalar()
    return atoms, cursors


def test_postgres_bundle_to_read_apis_is_one_compiler_and_one_transaction(clean_pg_v2):
    case = clean_pg_v2
    _seed(case)
    base = _base_batch(case)
    session = case["sessionmaker"]()
    try:
        dry = preview_cursor_batch(
            case["compiled"], "input_rows", base, _cursor(base),
            SQLAlchemyVerifiedJoinBatchReader(session), *_registries())
        result = execute_scoped_batch(
            case["compiled"], "input_rows", base, _scope(base),
            SQLAlchemyVerifiedJoinBatchReader(session), *_registries(), case["store"])
    finally:
        session.rollback()
        session.close()

    assert result.preview.candidate_semantics == dry.candidate_semantics
    assert result.store_result["inserted"] == dry.atom_count == 1
    # ⚰️ IT USED TO BE `(1, 1)` AND READ THE CURSOR ROW BACK. The second number was the
    # registry row, which only the retired forward-scan door ever created; the live door
    # writes atoms and no position at all (S-113 ⓐ). A source gets its row from the census
    # tick now (`backfill.measure_and_store`), which this fixture does not run - so 0 here
    # is the honest count rather than a loss of coverage, and the fingerprint the cursor
    # assertion used to pin is asserted directly on the preview below.
    assert _counts(case) == (1, 0)
    assert result.preview.translator_version == cursor_translator_version(
        case["compiled"], "input_rows")
    # ⚰️ [S-261] THIS ASKED `ledger_trace.coverage` FOR `state == "ready"`. That report
    # retired with its route; the question - 「the atom reached a REAL ledger, not a
    # fixture's idea of one」 - is asked directly of the relation, through the same
    # `relation_exists` `schema_drift` and the walk route use.
    raw = case["runtime"].raw_connection()
    try:
        assert relation_exists(raw, "ledger_events")
        cursor = raw.cursor()
        try:
            cursor.execute("SELECT count(*) FROM ledger_events")
            assert cursor.fetchone()[0] == 1
        finally:
            cursor.close()
    finally:
        raw.close()
    # ⚰️ THE WALK HALF CALLED A FUNCTION THAT DOES NOT EXIST. `ledger_trace.trace` is gone
    # (`resolve` and the subgraph walk replaced it) and the line raised `NameError` before
    # any assertion - unnoticed because this whole module skips unless
    # `ASSY_PG_TEST_DATABASE_URL` is set, which is `test_ledger_l1_pg.py`'s false green
    # (S-104) in its twin. Removed rather than renamed: what it asserted - that a walk from
    # a seeded subject returns hops - is not this module's subject, and guessing a
    # replacement would pin a walk nobody chose.
    with case["admin"].connect() as connection:
        assert connection.execute(text(
            f'SELECT count(*) FROM public."{SOURCE_TABLE}"')).scalar() == 1
        assert connection.execute(text(
            f'SELECT count(*) FROM public."{RIGHT_TABLE}"')).scalar() == 1


def test_postgres_missing_join_and_ambiguous_reader_leave_atom0(clean_pg_v2):
    case = clean_pg_v2
    _seed(case, with_right=False)
    base = _base_batch(case)
    session = case["sessionmaker"]()
    try:
        with pytest.raises(SourcePreparationError) as missing:
            execute_scoped_batch(
                case["compiled"], "input_rows", base, _scope(base),
                SQLAlchemyVerifiedJoinBatchReader(session), *_registries(),
                case["store"])
    finally:
        session.rollback()
        session.close()
    assert missing.value.code == "source_preparation_missing"
    assert _counts(case) == (0, 0)

    class AmbiguousReader(SQLAlchemyVerifiedJoinBatchReader):
        def read_chunk(self, descriptor, keys):
            key = keys[0]
            return {key: (
                JoinRightRow(key, {"row_id": "A"}, {"target_id": "A"}, NOW),
                JoinRightRow(key, {"row_id": "B"}, {"target_id": "B"}, NOW),
            )}

    session = case["sessionmaker"]()
    try:
        with pytest.raises(SourcePreparationError) as ambiguous:
            execute_scoped_batch(
                case["compiled"], "input_rows", base, _scope(base),
                AmbiguousReader(session), *_registries(), case["store"])
    finally:
        session.rollback()
        session.close()
    assert ambiguous.value.code == "source_preparation_ambiguous"
    assert _counts(case) == (0, 0)


# DELETED 2026-08-23 with the field it measured:
# `test_postgres_unapproved_binding_stops_before_atom_or_cursor` (two parameters). It set
# a subject key binding's `approval_status` to `pending`/`rejected` and asserted the
# compile refused with `binding_not_approved`. That field retired on 2026-08-22
# (`90383987`) for holding one reachable value on all 40 live bindings, and
# `bundle_readiness_errors` -- the pass that owned the rule -- now has none: measured
# off-PostgreSQL through the same three calls, `validate_bundle` accepts, readiness
# returns `()`, and the snapshot compiles. `binding_not_approved` appears in no
# production file in the tree. The bundle twins went the same way in the retirement
# commit (`test_readiness_blocks_nonapproved_bindings_without_rejecting_draft`,
# `test_readiness_walks_nested_entity_key_bindings`); that a retired name is swallowed
# rather than refused, and that a typo at the same path is still `unknown_field`, is
# asserted by `test_ledger_setup_bundle.py`.
#
# Its `_counts(case) == (0, 0)` added nothing: this unit never called `_seed` and never
# executed a batch, so both counts were the clean fixture's own baseline. That a refusal
# reaching PostgreSQL leaves atom 0 and cursor 0 is asserted above by
# `test_postgres_missing_join_and_ambiguous_reader_leave_atom0_cursor0`, which seeds
# first and refuses mid-execution.
#
# Second, independent reason it could not have passed: it wrote `["mappings"][0]`, and
# `mappings` is a dict keyed by mapping id, so the line raised `KeyError: 0` before the
# assertion was reached.


# ⚰️ `test_postgres_cursor_snapshot_conflict_rolls_back_insert_and_cursor` - died with
# `enforce_translator_version` (S-113 ⓐ, ruling 221). The guard it drove lives in
# `store._advance_cursor`'s WHERE clause and is reached only through
# `write_batch(advance_cursor=True)`, whose one product caller was the door that retired.
#
# 🔴 THE PROPERTY LOST ITS ONLY PRODUCT READER AND IS NAMED HERE: "a batch whose declaration
# fingerprint differs from the stored one is refused rather than written" is not asserted by
# anything on the live path any more, because the live path does not compare fingerprints at
# all - measured in the S-113 census: nothing raises `cursor_snapshot_reset_required` either.
# What protects a moved declaration today is S-87's boot re-stamp, which repairs rather than
# refuses. Whether that is enough is the open half of S-113 ⓔ, not something a retirement
# commit may decide.


def test_postgres_replay_dedupes_the_second_write_of_the_same_batch(clean_pg_v2):
    case = clean_pg_v2
    _seed(case)
    base = _base_batch(case)
    results = []
    for _ in range(2):
        session = case["sessionmaker"]()
        try:
            results.append(execute_scoped_batch(
                case["compiled"], "input_rows", base, _scope(base),
                SQLAlchemyVerifiedJoinBatchReader(session), *_registries(),
                case["store"]))
        finally:
            session.rollback()
            session.close()

    assert results[0].store_result["inserted"] == 1
    assert results[1].store_result["inserted"] == 0
    assert results[1].store_result["deduped"] == 1
    assert _counts(case) == (1, 0)


def test_postgres_gate_refusal_stops_before_store_transaction(clean_pg_v2, monkeypatch):
    case = clean_pg_v2
    _seed(case)
    base = _base_batch(case)

    def refuse(*args, **kwargs):
        raise gate.MoleculeRefused("input_rows", "test_refusal", "forced gate refusal")

    monkeypatch.setattr(gate, "screen_compiled_molecule", refuse)
    session = case["sessionmaker"]()
    try:
        with pytest.raises(gate.MoleculeRefused):
            execute_scoped_batch(
                case["compiled"], "input_rows", base, _scope(base),
                SQLAlchemyVerifiedJoinBatchReader(session), *_registries(),
                case["store"])
    finally:
        session.rollback()
        session.close()
    assert _counts(case) == (0, 0)


def test_postgres_right_unique_index_is_used_by_the_join_probe(clean_pg_v2):
    case = clean_pg_v2
    _seed(case)
    with case["admin"].begin() as connection:
        connection.execute(text("SET LOCAL enable_seqscan = off"))
        # ⚠️ THE PROBE ASKS WHAT THE JOIN ASKS. `join_onclause` compares
        # `coalesce(col, '')` on both sides (판정 285), so probing on the bare
        # column would prove the index unused - correctly - and prove nothing about the
        # join. This is what scores the two halves of S-181 against PostgreSQL itself:
        # the index is built on that expression and the query is written on it, and an
        # expression index is used ONLY when those match.
        probe = join_key_index.index_key_expression("join_id")
        plan = "\n".join(row[0] for row in connection.execute(text(
            f'EXPLAIN SELECT target_id FROM public."{RIGHT_TABLE}" '
            f"WHERE {probe} = 'J-0001'")))
    assert UNIQUE_INDEX in plan, plan
    assert "Index Scan" in plan, plan


# TOMBSTONE: `test_stage7_manifest_selected_lot_event_uses_existing_store_cursor_transaction`
# - died of four things at once (S-115), and each on its own would have been enough.
#
# 1. It called `backfill.run(engine, {}, source=...)`, the v1 shape with a config dict as
#    the second positional. `run` has taken no declaration argument since S-76, so this
#    raised `TypeError` before reaching an assertion - unseen, because this whole module
#    skipped unless a variable was exported. That false green is what S-115 closed.
# 2. It read `DEFAULT_ONTOLOGY_ROOT`, the deployment's OWN gitignored declaration. A proof
#    that drives the live root measures whether THIS machine has adopted something (판정
#    219 / 212); the shipped declaration is what a proof may lean on.
# 3. It asserted the cursor row's `cursor_value`. Nothing writes a position any more
#    (S-76), and the registry row exists for the fingerprint, the census and the refusal
#    breakdown (S-113).
# 4. Its fixture seeded a lot SPLIT, which the shipped declaration cannot translate today -
#    `descent` carries no `when`, so it is said for every row while a split's two rows each
#    hold only one of `child_lot`/`parent_lot` (S-112). The rows it needed could only come
#    from a declaration of this file's own invention.
#
# WHAT IT ACTUALLY PROVED, AND WHERE THAT LIVES NOW: that a real `backfill.run` over real
# PostgreSQL lands atoms and that running it again reads nothing and inserts nothing.
# `test_ledger_l1_pg.py::test_a_second_run_reads_nothing_and_duplicates_no_atom` asserts
# exactly that, on a SHIPPED row source, against the shipped catalogue - which is the same
# proof with none of the four faults above.
