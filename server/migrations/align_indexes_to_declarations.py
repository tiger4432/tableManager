"""Make an EXISTING database's dynamic-table indexes match what `table_config.json`
declares - the migration half of the F6 rule that `models.init_dynamic_models` now
implements for freshly created tables.

WHAT THE RULE IS
----------------
Every index the framework creates must be explainable from a declaration. One
declared-key index per dynamic table, derived by `models.declared_key_columns`:

    map_key_columns  ->  else composite_key_source  ->  else a single-column
    business_key (only when the table declares no composite key)

and two framework indexes retired because measurement says nothing reads them:

    ix_<table>_created_at   zero scans on 35 of the 36 (table, database) pairs
                            across both dev copies; the one exception is
                            `ix_production_plan_created_at` on `assy_qa` at 1 scan,
                            and this script REFUSES it by itself - see section 3
    idx_<table>_bk          zero scans on every registered table, BOTH dev copies

WHY THIS IS A MIGRATION AND NOT JUST A BUILDER CHANGE
-----------------------------------------------------
`Base.metadata.create_all` does not add indexes to tables that already exist and
does not drop indexes ever. So the builder change reaches new tables only, and
every database that already has the 18 tables would keep paying for two indexes
nobody reads while never getting the one everybody wants. That asymmetry is
exactly how the two dev copies drifted into DISJOINT hand-added index sets in the
first place (F5 survey, `a256eca`).

WHY EACH ACTION RE-PROVES ITSELF AGAINST THE LIVE CATALOGUE
------------------------------------------------------------
Measurements taken on one database are not facts about another. The precedent is
`drop_redundant_layering_indexes.py`, and this file REUSES its catalogue readers
(`index_facts`, `covering_index`, `stats_are_trustworthy`, `_drop`, `quote_ident`,
`rollback_ddl`) rather than growing a second spelling of them. Every action is
gated on a proof evaluated at run time on the target database, and an action whose
proof fails is REFUSED BY NAME and the run continues.

The two drops are gated differently ON PURPOSE:

  * `idx_<t>_bk` is gated STRUCTURALLY - it is dropped only when another valid,
    non-partial btree index on the same table leads with `business_key_val`. That
    proof lives in `pg_index` and does not depend on a statistics counter that a
    restore or a `pg_stat_reset()` can zero.
  * `ix_<t>_created_at` has no structural substitute, so its gate is the counter,
    and the counter is used the way `drop_redundant_layering_indexes` uses it: a
    zero is a REFUSAL gate, never a reason, and it is refused outright when every
    index on the table reads zero (a fresh restore, where the zero is absence of
    evidence rather than evidence of absence).

WHAT THIS DOES NOT TOUCH
------------------------
`ix_<table>_row_id`, the exact copy of each table's primary key that 12 of the 18
tables still carry. Its DECLARATION was already retired ([D3] in `models.py`), and
the physical leftovers have a canonical owner:

    conda run -n assy_manager python server/migrations/add_business_key_unique_index.py --drop-redundant

That script rediscovers the whole class from `pg_index` rather than from a list of
names. Duplicating it here would be a second mechanism for one class of defect.

USAGE
-----
    conda run -n assy_manager python server/migrations/align_indexes_to_declarations.py
    conda run -n assy_manager python server/migrations/align_indexes_to_declarations.py --apply
    conda run -n assy_manager python server/migrations/align_indexes_to_declarations.py --reverse --apply

Default is read-only and PostgreSQL enforces it (`db_safety.open_readonly_engine`),
so a check run has no writable connection anywhere in the process. `--reverse`
recomputes the undo from the SAME config and catalogue rather than from a stored
list, so it cannot drift from the forward run.

Exit code is 0 only when nothing was refused.
"""
import argparse
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text  # noqa: E402

from db_safety import (  # noqa: E402
    assert_writable, close_readonly_connection, open_readonly_connection)
import db_safety  # noqa: E402

# 🔴 Reused, not re-implemented. These are the catalogue readers and the
# drop-then-ask-the-catalogue helper that `drop_redundant_layering_indexes`
# already carries the measurements for.
from drop_redundant_layering_indexes import (  # noqa: E402
    _drop, index_facts, quote_ident, rollback_ddl, stats_are_trustworthy)

READONLY_APPLICATION_NAME = "assy_align_indexes_check"


def open_readonly_engine(url=None):
    return db_safety.open_readonly_engine(url, application_name=READONLY_APPLICATION_NAME)


def declared_plan():
    """`{table: (columns, source_declaration)}` straight out of the live config.

    The config is the input to BOTH halves of this rule, so it is read once here
    and the builder's own function decides what the key is. If this file grew its
    own copy of that decision, the migration and the builder would answer
    differently the first time either changed - which is the defect this whole
    round exists to remove.
    """
    from database import crud, models
    cfg = crud.load_table_config() or {}
    out = {}
    for table_name, table_cfg in cfg.items():
        if table_name.startswith("__") or not isinstance(table_cfg, dict):
            continue
        out[table_name] = models.declared_key_columns(table_cfg)
    return out


def already_covering(facts, cols):
    """The existing index whose LEADING key columns are exactly `cols`, or None.

    Leading, in order, and by key column only - `indnkeyatts` means an INCLUDE
    payload is not counted, so `(base_id, bx, by, row_id) INCLUDE (stack_height)`
    is compared on its four key columns. A wider index that starts with `cols`
    serves every equality lookup on `cols`, so creating a second one beside it
    would buy nothing and cost WAL on every insert.

    ⚠️ This is why the three hand-added predicate indexes that already exist
    (`idx_core_wafer_map_map_key`, `idx_wafer_map_metadata_target_map`,
    `idx_map_split_registry_ref_map`) are NOT duplicated by this migration: they
    ARE the declared-key index, under the name a human gave them before the rule
    existed. See the name-convergence note in `docs/architecture/INDEX_POLICY.md`
    for why this migration does not rename them.
    """
    n = len(cols)
    for name, f in sorted(facts.items()):
        if not f["valid"] or f["am"] != "btree" or f["partial"] or f["expr"]:
            continue
        if f["cols"][:n] == cols:
            return name
    return None


def _create(conn, name, table, cols):
    """Create once, then ask the CATALOGUE whether it is there. `IF NOT EXISTS`
    makes a name that already exists a silent success, so the return code is not
    evidence - the same standard `_drop` holds itself to."""
    ddl = (f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {quote_ident(name)} "
           f"ON public.{quote_ident(table)} "
           f"({', '.join(quote_ident(c) for c in cols)})")
    try:
        conn.execute(text(ddl))
    except Exception as e:
        print(f"      !! FAILED: {str(e).strip().splitlines()[0]}")
        return None
    row = conn.execute(text(
        "SELECT x.indisvalid FROM pg_class i "
        "JOIN pg_namespace n ON n.oid = i.relnamespace "
        "JOIN pg_index x ON x.indexrelid = i.oid "
        "WHERE n.nspname='public' AND i.relname = :n"), {"n": name}).first()
    if row is None:
        print("      !! FAILED: CREATE reported success but the index is not "
              "in the catalogue")
        return None
    if not row[0]:
        # CONCURRENTLY leaves an INVALID index behind when it loses a race; an
        # invalid index is maintained on every insert and used by nothing, which
        # is the worst of both halves of this migration.
        print(f"      !! FAILED: index exists but is INVALID - drop it and retry: "
              f"DROP INDEX CONCURRENTLY {quote_ident(name)};")
        return None
    print("      created")
    return name


def run(apply=False, reverse=False, engine=None, readonly_engine=None):
    mode = "APPLY" if apply else "CHECK (read-only)"
    print(f"=== Align dynamic-table indexes to declarations - "
          f"{'REVERSE ' if reverse else ''}{mode} ===")

    own_ro_engine = readonly_engine is None
    if own_ro_engine:
        readonly_engine = open_readonly_engine()
    try:
        conn = open_readonly_connection(readonly_engine)
    except BaseException:
        if own_ro_engine:
            readonly_engine.dispose()
        raise

    wconn = None
    created, dropped, refused, skipped = [], [], [], []
    before, after = {}, {}
    try:
        if apply:
            from database.database import engine as default_engine
            wconn = (engine or default_engine).connect().execution_options(
                isolation_level="AUTOCOMMIT")
            assert_writable(wconn)

        db = conn.execute(text("SELECT current_database()")).scalar()
        print(f"database: {db}\n")

        plan = declared_plan()
        present = {r[0] for r in conn.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname='public'")).fetchall()}
        tables = [t for t in sorted(plan) if t in present]
        missing = [t for t in sorted(plan) if t not in present]
        if missing:
            print(f"declared but not physically present here (skipped): {missing}\n")

        facts = {t: index_facts(conn, t) for t in tables}
        for t in tables:
            before[t] = len(facts[t])

        # --- section 1: the declared-key index ------------------------------
        print("=== Section 1: declared-key index (create) ===")
        for t in tables:
            cols, source = plan[t]
            name = f"idx_{t}_declared_key"
            if not cols:
                print(f"  -- {t}: no declared-key index - {source}")
                skipped.append((t, source))
                continue
            covering = already_covering(facts[t], cols)
            print(f"  {t}.{name}  ({', '.join(cols)})  <- {source}")
            if reverse:
                if name not in facts[t]:
                    print("      -- not present in this database - nothing to undo")
                    continue
                me = facts[t][name]
                print(f"      ROLLBACK: {rollback_ddl(me['def'])}")
                if apply:
                    if _drop(wconn, name):
                        dropped.append(name)
                else:
                    print(f"      would run: DROP INDEX CONCURRENTLY IF EXISTS "
                          f"{quote_ident(name)};")
                continue
            if covering:
                cov = facts[t][covering]
                print(f"      already covered by {covering} "
                      f"({', '.join(cov['cols'])}) - nothing to create")
                skipped.append((t, f"covered by {covering}"))
                continue
            if apply:
                if _create(wconn, name, t, cols):
                    created.append(name)
            else:
                print(f"      would run: CREATE INDEX CONCURRENTLY IF NOT EXISTS "
                      f"{quote_ident(name)} ON public.{quote_ident(t)} "
                      f"({', '.join(quote_ident(c) for c in cols)});")

        # --- section 2: idx_<t>_bk, structurally gated ----------------------
        print("\n=== Section 2: idx_<table>_bk (business_key_val, row_id) - retire ===")
        print("  gate: another valid non-partial btree index on the table must lead "
              "with business_key_val")
        for t in tables:
            name = f"idx_{t}_bk"
            if reverse:
                if name in facts[t]:
                    print(f"  -- {t}: {name} already present - nothing to undo")
                    continue
                print(f"  {t}.{name}")
                if apply:
                    if _create(wconn, name, t, ["business_key_val", "row_id"]):
                        created.append(name)
                else:
                    print(f"      would run: CREATE INDEX CONCURRENTLY IF NOT EXISTS "
                          f"{quote_ident(name)} ON public.{quote_ident(t)} "
                          f"(business_key_val, row_id);")
                continue
            if name not in facts[t]:
                print(f"  -- {t}: {name} not present - nothing to do")
                continue
            me = facts[t][name]
            substitute = None
            for other, f in sorted(facts[t].items()):
                if other == name or not f["valid"] or f["am"] != "btree":
                    continue
                if f["partial"] or f["expr"]:
                    continue
                if f["cols"][:1] == ["business_key_val"]:
                    substitute = other
                    break
            scans = conn.execute(text(
                "SELECT idx_scan FROM pg_stat_user_indexes WHERE indexrelname = :n"),
                {"n": name}).scalar()
            print(f"  {t}.{name}  ({me['bytes'] / 1024 / 1024:.1f} MB)  "
                  f"idx_scan={scans}")
            if me["unique"]:
                why = "it is UNIQUE - that is a constraint, not an index"
                print(f"      !! REFUSED: {why}")
                refused.append((name, why))
                continue
            if not substitute:
                why = ("no other valid non-partial btree index on this table leads "
                       "with business_key_val, so dropping this would leave identity "
                       "lookups (crud.get_row_by_business_key) with no index at all")
                print(f"      !! REFUSED: {why}")
                refused.append((name, why))
                continue
            print(f"      substitute: {substitute} ({', '.join(facts[t][substitute]['cols'])})"
                  f"{'  UNIQUE' if facts[t][substitute]['unique'] else ''}")
            print(f"      ROLLBACK: {rollback_ddl(me['def'])}")
            if apply:
                if _drop(wconn, name):
                    dropped.append(name)
            else:
                print(f"      would run: DROP INDEX CONCURRENTLY IF EXISTS "
                      f"{quote_ident(name)};")

        # --- section 3: ix_<t>_created_at, counter-gated --------------------
        print("\n=== Section 3: ix_<table>_created_at - retire ===")
        print("  gate: idx_scan must be 0 AND the table's other indexes must have "
              "seen traffic")
        for t in tables:
            name = f"ix_{t}_created_at"
            if reverse:
                if name in facts[t]:
                    print(f"  -- {t}: {name} already present - nothing to undo")
                    continue
                print(f"  {t}.{name}")
                if apply:
                    if _create(wconn, name, t, ["created_at"]):
                        created.append(name)
                else:
                    print(f"      would run: CREATE INDEX CONCURRENTLY IF NOT EXISTS "
                          f"{quote_ident(name)} ON public.{quote_ident(t)} "
                          f"(created_at);")
                continue
            if name not in facts[t]:
                print(f"  -- {t}: {name} not present - nothing to do")
                continue
            me = facts[t][name]
            reset_at, age, peers = stats_are_trustworthy(conn, t)
            scans = conn.execute(text(
                "SELECT idx_scan FROM pg_stat_user_indexes WHERE indexrelname = :n"),
                {"n": name}).scalar()
            print(f"  {t}.{name}  ({me['bytes'] / 1024 / 1024:.1f} MB)  "
                  f"idx_scan={scans}  peers={peers}  "
                  f"stats_reset={reset_at or 'never'}")
            if peers == 0:
                why = ("every index on this table reads zero, so the counters have "
                       "observed no traffic at all - a fresh restore or a reset "
                       "statistics file. This zero is absence of evidence, not "
                       "evidence of absence")
                print(f"      !! REFUSED: {why}")
                refused.append((name, why))
                continue
            if scans:
                why = (f"idx_scan = {scans}, not 0 - something on THIS database reads "
                       f"created_at. The census that justified this retirement does "
                       f"not describe this installation")
                print(f"      !! REFUSED: {why}")
                refused.append((name, why))
                continue
            print(f"      ROLLBACK: {rollback_ddl(me['def'])}")
            if apply:
                if _drop(wconn, name):
                    dropped.append(name)
            else:
                print(f"      would run: DROP INDEX CONCURRENTLY IF EXISTS "
                      f"{quote_ident(name)};")

        # --- before/after -----------------------------------------------------
        after_facts = {t: index_facts(conn, t) for t in tables}
        for t in tables:
            after[t] = len(after_facts[t])
        print(f"\n=== Index count per table ({'after' if apply else 'projected'}) ===")
        print(f"  {'table':<22}{'before':>8}{'after':>8}")
        for t in tables:
            print(f"  {t:<22}{before[t]:>8}{after[t]:>8}")
        print(f"  {'TOTAL':<22}{sum(before.values()):>8}{sum(after.values()):>8}")

    finally:
        close_readonly_connection(conn)
        if own_ro_engine:
            readonly_engine.dispose()
        if wconn is not None:
            wconn.close()

    print(f"\nSummary: {len(created)} created, {len(dropped)} dropped, "
          f"{len(refused)} refused, {len(skipped)} skipped.")
    for name, why in refused:
        print(f"  !! {name}: {why}")
    if not apply:
        print("Nothing was written.")
    return {"created": created, "dropped": dropped, "refused": refused,
            "skipped": skipped, "before": before, "after": after}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--apply", action="store_true",
                   help="actually write. Without it the run is read-only.")
    p.add_argument("--reverse", action="store_true",
                   help="undo: drop the declared-key indexes and rebuild the two "
                        "retired framework families, recomputed from the same config.")
    args = p.parse_args(argv)
    out = run(apply=args.apply, reverse=args.reverse)
    return 1 if out["refused"] else 0


if __name__ == "__main__":
    sys.exit(main())
