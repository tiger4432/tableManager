"""Detector for `docs/architecture/SCHEMA_CANON.md` - the eight rules, counted.

WHY THIS EXISTS
---------------
SCHEMA_CANON.md §2 is blunt about it: *"a rule with no detector is not a rule"*. The
eight rules there each came out of a real incident, and prose alone drifts back out of
true within a week with nobody noticing. This script is the counting half.

**READ-ONLY, STRUCTURALLY.** There is no `--apply`, no DDL, no INSERT/UPDATE anywhere in
this file, and the connection is pinned with `SET SESSION default_transaction_read_only`
before a single catalogue query runs - the same discipline (and the same
`conn.invalidate()` on the way out, so the flag cannot leak back into the pool) that
`server/migrations/add_business_key_unique_index.py` uses for its `--check` pass. An
operator pointing this at production should not have to read the body to believe that.

WHAT IT JUDGES - BOTH SOURCES, AND THEIR DISAGREEMENT
-----------------------------------------------------
1. `server/config/table_config.json.sample` - production INTENT.
2. the physical catalogue of whatever database `--url` names - production REALITY.
3. **the two disagreeing**, which is its own report section, because that disagreement is
   literally R1's incident: `dt_inventory.dt_lot` declared `number` while the value it
   must hold is `CL_2601_005_A5`.

METHOD - SWEEP AND BUCKET, INCLUDING THE EMPTY BUCKETS
------------------------------------------------------
Every rule reports its WHOLE population split into named buckets, and **prints buckets
that came out empty**. This is not tidiness. The most expensive recurring failure on this
project is a filter written from a hypothesis, which deletes exactly the evidence that
would have refuted it; an empty bucket printed as `0` is a claim you can check, and a
bucket that was never printed is a claim nobody can.

A bucket carries a VERDICT, and the verdict is not the count:
  * `VIOLATION`     - breaks the rule as written.
  * `LEGITIMATE`    - inside the rule's own stated exception (R1's "quantities are
                      legitimately numeric" is the big one: `dt_x` is a key column AND a
                      number, and that is correct).
  * `INFO`          - the population the rule protects, reported so the reader can see
                      the surface. NOT a pass.
  * `UNCLASSIFIED`  - the evidence does not decide it. Listed by name, never folded into
                      either of the other two. Guessing here is how a "4 of 19 tables"
                      verdict gets computed on the wrong predicate.

`--self-test` FAULT-INJECTS EVERY RULE
--------------------------------------
A zero you cannot prove your detector distinguishes from silence is not a zero. Each
detector is a pure function over a snapshot (plain dicts/sets), never over a live cursor,
which is exactly what makes the injection possible **without writing to any database**:
`--self-test` hands each rule a clean synthetic snapshot (expects 0) and then the same
snapshot with a violation planted in it (expects >0), and fails loudly if either half
disagrees. Both halves matter - a detector that always fires would pass a one-sided test.

USAGE
-----
    conda run -n assy_manager python server/scripts/audit_schema_canon.py
    ... --url postgresql://postgres:admin@localhost:5432/assy_qa
    ... --config server/config/table_config.json     # judge the LIVE config, not .sample
    ... --rule R1,R3                                 # a subset
    ... --self-test                                  # fault injection only, no database
    ... --json out.json                              # machine-readable buckets

Exit code: 0 when no bucket with verdict VIOLATION has members, 1 when one does, 2 when
the run could not complete. `--self-test` exits 1 if any detector failed to fire.
⚠️ On this box exit 1 is EXPECTED - see R2, which is violated by every table on both
development databases because the unique-index migration has never been applied here.
"""
import argparse
import ast
import io
import json
import os
import re
import sys

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         "..", ".."))
SERVER_ROOT = os.path.join(REPO_ROOT, "server")

# --- verdicts -----------------------------------------------------------------
VIOLATION = "VIOLATION"
LEGITIMATE = "LEGITIMATE"
INFO = "INFO"
UNCLASSIFIED = "UNCLASSIFIED"


class Bucket:
    """A named subset of a rule's population, with a verdict that is not its count.

    `members` are `"table.column"` / `"table"` / `"file:line"` strings - something a
    reader can go and look at. A count with no names is not actionable, and this project
    has already shipped one wrong verdict that was arithmetically correct on a list
    nobody printed.
    """

    def __init__(self, key, verdict, why, members=None):
        self.key = key
        self.verdict = verdict
        self.why = why
        self.members = list(members or [])

    def add(self, m, detail=None):
        self.members.append(m if detail is None else f"{m}  [{detail}]")

    def __len__(self):
        return len(self.members)

    def to_dict(self):
        return {"bucket": self.key, "verdict": self.verdict, "why": self.why,
                "count": len(self.members), "members": self.members}


class RuleResult:
    def __init__(self, rule, title, buckets, uncovered=""):
        self.rule = rule
        self.title = title
        self.buckets = buckets
        self.uncovered = uncovered

    def violations(self):
        return [b for b in self.buckets if b.verdict == VIOLATION and len(b)]

    def to_dict(self):
        return {"rule": self.rule, "title": self.title, "uncovered": self.uncovered,
                "buckets": [b.to_dict() for b in self.buckets]}


# =============================================================================
# SNAPSHOTS - plain data. Every rule below reads these and never a live cursor,
# which is what lets `--self-test` plant a fault without touching a database.
# =============================================================================

# Columns `models.init_dynamic_models` injects into EVERY dynamic table and
# deliberately SKIPS if `column_types` also declares them (`models.py`, the
# `if col_name in [...]: continue` guard in both the create and hot-swap arms).
# A declaration under one of these names is therefore DEAD - the engine's own
# column wins - and that is reported rather than silently honoured.
RESERVED_METADATA_COLUMNS = frozenset({
    "created_at", "updated_at", "is_graph_synced", "needs_graph_rollback",
    "graph_synced_at",
})

# `models.init_dynamic_models` maps `column_types` onto SQL types. Kept here as data so
# the declaration-vs-physical section compares against what the engine ACTUALLY builds
# rather than against what a reader assumes it builds.
DECLARED_TO_PHYSICAL = {
    "number": {"double precision"},
    "datetime": {"timestamp with time zone"},
    "string": {"character varying", "text"},
}


class Declarations:
    """`table_config` + the sibling configs that say what a column MEANS.

    Loaded from `.sample` by default because that file is production INTENT; the
    un-suffixed files are gitignored per-workstation state. `--config` switches it.
    """

    def __init__(self, tables, chain_rules=None, overlay_bindings=None, source="<mem>"):
        self.source = source
        self.tables = tables or {}
        self.chain_rules = chain_rules or []
        self.overlay_bindings = overlay_bindings or {}

    @classmethod
    def load(cls, table_config_path, chain_rules_path=None, overlay_path=None):
        tables = _read_json(table_config_path) or {}
        # `__comment` keys are documentation, not tables.
        tables = {k: v for k, v in tables.items()
                  if isinstance(v, dict) and not k.startswith("__")}
        chain = (_read_json(chain_rules_path) or {}).get("rules", []) if chain_rules_path else []
        overlay = {}
        if overlay_path:
            raw = (_read_json(overlay_path) or {}).get("table_bindings", {}) or {}
            overlay = {k: v for k, v in raw.items()
                       if isinstance(v, dict) and not k.startswith("__")}
        return cls(tables, chain, overlay, source=table_config_path)

    def column_type(self, table, column):
        return ((self.tables.get(table) or {}).get("column_types") or {}).get(column)

    def declared_columns(self):
        for t, cfg in sorted(self.tables.items()):
            for c, ty in sorted((cfg.get("column_types") or {}).items()):
                yield t, c, ty


class PhysicalSchema:
    """What the catalogue HAS. Built once, then read as data.

    `indexed_leading` is the set of columns that are the FIRST key column of some index -
    the only position that serves a single-column equality lookup on its own. `indexed_any`
    keeps the wider set so R6 can distinguish "no index at all" from "buried in a composite",
    which are different repairs.
    """

    def __init__(self, label="<mem>"):
        self.label = label
        self.tables = set()
        self.columns = {}           # (t, c) -> {"data_type", "column_default", "is_nullable"}
        self.indexed_leading = set()
        self.indexed_any = set()
        self.unique_bk = {}         # table -> (index_name, is_valid) | None
        self.bk_tables = set()      # tables carrying `business_key_val` at all

    def type_of(self, table, column):
        return (self.columns.get((table, column)) or {}).get("data_type")


def _read_json(path):
    if not path or not os.path.exists(path):
        return None
    with io.open(path, encoding="utf-8") as fh:
        return json.load(fh)


def readonly_connection(engine):
    """A connection PROVEN read-only, not one that has been asked nicely.

    🔴 THE OBVIOUS SPELLING OF THIS DOES NOT WORK, AND IT IS ALREADY IN THIS REPOSITORY.
    `conn.execute("SET SESSION default_transaction_read_only = on")` is what a read-only
    pre-flight looks like, and measured on both databases on this box it leaves the
    session **writable**:

        default_transaction_read_only = on     <- the SET took effect
        transaction_read_only        = off     <- and this is the one that decides
        CREATE TABLE ...             SUCCEEDED

    The reason is that the SET itself BEGINS the implicit transaction, so the transaction
    it runs in was opened under the old default and keeps it; every later statement on
    that connection is inside that same still-writable transaction. The variable an
    operator would think to check reads `on` the whole time. This is a guard that reports
    itself as armed and is not.

    `postgresql_readonly=True` is SQLAlchemy's own option and sets the per-transaction
    flag, which is the one PostgreSQL enforces (measured: `transaction_read_only = on`,
    DDL refused). **And it is still verified below rather than trusted** - a safety claim
    nobody exercised is the exact thing this file just found in the alternative.
    """
    from sqlalchemy import text
    conn = engine.connect().execution_options(postgresql_readonly=True)
    armed = conn.execute(text("SHOW transaction_read_only")).scalar()
    if str(armed).lower() != "on":
        conn.invalidate()
        conn.close()
        raise RuntimeError(
            "refusing to run: could not make this session read-only "
            f"(transaction_read_only={armed!r}). The audit will not touch a database it "
            f"cannot prove it is unable to write to.")
    return conn


def load_physical(engine, label):
    """One read-only pass over the catalogue.

    `invalidate()` rather than `close()` on the way out: `close()` returns the connection
    to the pool, and a session-level setting left on a pooled connection becomes the next
    checkout's problem. Throwing it away cannot be skipped by an exception, which
    `finally` alone does not guarantee for a reset statement.
    """
    from sqlalchemy import text
    from migrations.add_business_key_unique_index import (  # noqa: E402
        existing_unique_index, tables_with_business_key)

    snap = PhysicalSchema(label)
    conn = readonly_connection(engine)
    try:
        snap.tables = {r[0] for r in conn.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"""))}

        for t, c, dt, dflt, nul in conn.execute(text("""
            SELECT table_name, column_name, data_type, column_default, is_nullable
            FROM information_schema.columns WHERE table_schema = 'public'""")):
            snap.columns[(t, c)] = {"data_type": dt, "column_default": dflt,
                                    "is_nullable": nul == "YES"}

        # `indkey` is an int2vector; position 0 is the leading key column. Expression
        # indexes carry attnum 0 there, which joins to no `pg_attribute` row and so drops
        # out on its own - correct, an expression index does not index the bare column.
        for t, c, pos in conn.execute(text("""
            SELECT cl.relname, a.attname, k.ord
            FROM pg_index x
            JOIN pg_class cl ON cl.oid = x.indrelid
            JOIN pg_namespace n ON n.oid = cl.relnamespace
            CROSS JOIN LATERAL unnest(x.indkey) WITH ORDINALITY AS k(attnum, ord)
            JOIN pg_attribute a ON a.attrelid = cl.oid AND a.attnum = k.attnum
            WHERE n.nspname = 'public' AND x.indisvalid""")):
            snap.indexed_any.add((t, c))
            if pos == 1:
                snap.indexed_leading.add((t, c))

        # R2's predicate is NOT re-spelled here. `existing_unique_index` already encodes
        # the three exclusions that make the difference between an index that enforces
        # identity and one that only looks like it does (partial, expression, or a
        # multi-column index whose second column is already unique). A second spelling
        # would be a second thing to keep in step.
        snap.bk_tables = set(tables_with_business_key(conn))
        for t in sorted(snap.bk_tables):
            snap.unique_bk[t] = existing_unique_index(conn, t)
    finally:
        conn.invalidate()
        conn.close()
    return snap


def load_default_surface(config_dict):
    """`(table, column) -> "py"|"server"|"onupdate"` for every defaulted column.

    Asked of SQLAlchemy's own metadata rather than grepped for `default=`, because the
    dynamic tables get their defaults from `init_dynamic_models` at runtime and a text
    scan of `models.py` sees one declaration where the catalogue has one per table.
    """
    import database.models as models
    models.init_dynamic_models(config_dict)
    out = {}
    for tname, tbl in models.Base.metadata.tables.items():
        for col in tbl.columns:
            kinds = []
            if col.default is not None:
                kinds.append("py")
            if col.server_default is not None:
                kinds.append("server")
            if col.onupdate is not None:
                kinds.append("onupdate")
            if kinds:
                out[(tname, col.name)] = "+".join(kinds)
    return out


# =============================================================================
# EVIDENCE - what a column IS, argued from declarations rather than from its name
# =============================================================================

def identifier_evidence(decl):
    """`(table, column) -> {reasons}` for every column the CONFIG treats as identity.

    🔴 The name is not the evidence and must not be. R1 cannot be decided by reading
    `dt_lot` and thinking "sounds like an id" - `dt_index` sounds like one too and is a
    count. What makes a column an identifier here is that something addresses a row BY it:
    it is the business key, part of the composite that composes the business key, a map
    key, a map overlay's lookup key, or the job column a chain rule joins on.
    """
    ev = {}

    def mark(t, c, why):
        if t and c:
            ev.setdefault((t, c), set()).add(why)

    for t, cfg in decl.tables.items():
        if cfg.get("business_key"):
            mark(t, cfg["business_key"], "business_key")
        for c in cfg.get("composite_key_source") or []:
            mark(t, c, "composite_key_source")
        for c in cfg.get("map_key_columns") or []:
            mark(t, c, "map_key_columns")

    for t, b in decl.overlay_bindings.items():
        for c in ((b.get("columns") or {}).get("key_columns") or []):
            mark(t, c, "overlay.key_columns")

    # A chain rule's job column is the handle the projection joins on. It is named once
    # in the rule and applies to whichever of the rule's tables actually carries it, so
    # every table the rule names is marked and the ones that do not declare the column
    # fall out later as `identifier_not_declared`.
    for r in decl.chain_rules:
        for key in ("job_column", "reference_job_column"):
            col = r.get(key)
            if not col:
                continue
            for tk in ("trigger_table", "target_table", "map_table",
                       "metadata_target_table"):
                mark(r.get(tk), col, f"chain.{key}")
    return ev


def quantity_evidence(decl):
    """`(table, column) -> {reasons}` for every column the CONFIG treats as a NUMBER.

    R1's dividing line is *"is arithmetic done on it"*, and there are two places the
    configuration says so out loud:

      a) `map_overlay_config.table_bindings[t].columns.x/.y` - a declared map axis. The
         whole coordinate transformer runs on these.
      b) a declared `<col>_base` / `<col>_sign` / `<col>_offset` triple anywhere in
         `table_config` - that triple IS an arithmetic declaration (`v * sign + offset`),
         and `dt_inventory` carries it for `dt_x`, `dt_y`, `core_x`, `core_y`.

    Anything else stays UNCLASSIFIED. There is deliberately no "it is called x so it is a
    coordinate" arm: the moment this file starts inferring meaning from spelling it can
    reach the wrong answer silently, which is the failure R1 itself is about.
    """
    ev = {}

    def mark(t, c, why):
        if t and c:
            ev.setdefault((t, c), set()).add(why)

    for t, b in decl.overlay_bindings.items():
        cols = b.get("columns") or {}
        for axis in ("x", "y"):
            mark(t, cols.get(axis), f"overlay.axis.{axis}")

    # The transform triple is declared in ONE table (`dt_inventory` holds the equation)
    # but describes an axis that appears in several, so the axis names are collected
    # globally and then applied wherever they are declared numeric.
    axis_names = set()
    for _t, cfg in decl.tables.items():
        types = cfg.get("column_types") or {}
        for c in types:
            for suffix in ("_base", "_sign", "_offset"):
                if c.endswith(suffix):
                    axis_names.add(c[: -len(suffix)])
    for t, cfg in decl.tables.items():
        for c in (cfg.get("column_types") or {}):
            if c in axis_names:
                mark(t, c, "declared transform triple (_base/_sign/_offset)")
    return ev


# =============================================================================
# THE EIGHT RULES
# =============================================================================

def probe_numeric_fill(engine, candidates, sample=20000):
    """`(table, col) -> {"sampled", "filled", "min", "max", "nonintegral"}`. READ-ONLY.

    🔴 WITHOUT THIS, R1 CANNOT TELL ITS OWN INCIDENT FROM A COORDINATE, and reporting
    both as one number is the "right arithmetic on the wrong predicate" failure. Config
    says `valid_die_ref.x` and `dt_inventory.dt_lot` are the same thing - a numeric column
    that composes a key. The DATA does not: `x` is 4,598/4,598 filled over the integers
    -20..40, and `dt_lot` was **251 rows, 0 filled** - a column typed to hold a number in
    a system whose lot ids look like `CL_2601_005_A5`, which is why it could never be
    written and why the canon calls it a decoy rather than an empty column.

    Bounded by `LIMIT` inside a subquery so the cost does not scale with a 10M-row table,
    and each probe gets its own transaction: a type error (asking `trunc()` of a varchar,
    which happens on any database where the column has already been migrated) otherwise
    poisons the session and every later probe fails with `InFailedSqlTransaction` -
    measured, and it silently turned 8 real answers into 1 answer and 7 error strings.
    """
    from sqlalchemy import text
    out = {}
    conn = readonly_connection(engine)
    try:
        for (t, c) in candidates:
            try:
                row = conn.execute(text(
                    f'SELECT count(*), count("{c}"), min("{c}"), max("{c}"), '
                    f'count(*) FILTER (WHERE "{c}" IS NOT NULL AND "{c}" <> trunc("{c}")) '
                    f'FROM (SELECT "{c}" FROM public."{t}" LIMIT {int(sample)}) s')).first()
                out[(t, c)] = {"sampled": int(row[0]), "filled": int(row[1]),
                               "min": row[2], "max": row[3], "nonintegral": int(row[4])}
            except Exception as e:
                conn.rollback()
                out[(t, c)] = {"error": str(e).strip().splitlines()[0][:80]}
    finally:
        conn.invalidate()
        conn.close()
    return out


def rule_r1(decl, phys=None, fill=None):
    """R1 - identifiers are never numeric."""
    ident = identifier_evidence(decl)
    quant = quantity_evidence(decl)
    fill = fill or {}

    b_violation = Bucket(
        "numeric_identifier_never_populated", VIOLATION,
        "THE INCIDENT'S OWN SIGNATURE. Config addresses rows by this column, declares it "
        "`number`, and the data probe finds it 100% EMPTY. A numeric column that no "
        "writer has ever filled in a system whose ids look like `CL_2601_005_A5` is not "
        "a column waiting for values - it is a decoy the design points at.")
    b_nonintegral = Bucket(
        "numeric_identifier_holding_fractional_values", VIOLATION,
        "declared/stored numeric, addressed as identity, and the sample contains "
        "non-integral values - `double precision` is already rounding something.")
    b_int_ordinal = Bucket(
        "numeric_identifier_holding_only_small_integers", UNCLASSIFIED,
        "identity evidence and `number`, but the data is dense integers in a narrow "
        "range - the shape of a coordinate or an ordinal, which R1 exempts. No config "
        "declares arithmetic on it, so the evidence stops short of deciding. Read the "
        "range and rule by hand.")
    b_no_data = Bucket(
        "numeric_identifier_no_data_to_judge", UNCLASSIFIED,
        "identity evidence and `number`, and the table is empty here, so the fill probe "
        "says nothing either way. NOT the same as the never-populated bucket above, "
        "which had rows and no values in them.")
    b_unprobed = Bucket(
        "numeric_identifier_unprobed", VIOLATION,
        "identity evidence and `number` with no data probe available (--no-db). Held as "
        "a violation rather than dismissed: this is the bucket the incident lived in.")
    b_quantity_key = Bucket(
        "key_part_but_declared_quantity", LEGITIMATE,
        "numeric AND part of a key, but config declares arithmetic on it (map axis or "
        "a `_base/_sign/_offset` triple). R1 exempts quantities by name.")
    b_string_ident = Bucket(
        "identifier_declared_string", INFO,
        "identifier evidence, declared `string`. What the rule wants.")
    b_undeclared = Bucket(
        "identifier_not_declared_in_table", UNCLASSIFIED,
        "something addresses this table by this column but the table declares no type "
        "for it - the rule cannot be applied and neither can the column be trusted.")
    b_datetime_ident = Bucket(
        "identifier_declared_datetime", UNCLASSIFIED,
        "identifier evidence on a `datetime` column - neither an identifier string nor "
        "a quantity. Decide by hand.")
    b_numeric_nonident = Bucket(
        "numeric_no_identifier_evidence", INFO,
        "declared `number` and nothing addresses rows by it - outside R1's scope, "
        "counted so the denominator is visible.")

    def place_numeric(t, c, tag):
        """Route a numeric identifier by what the DATA shows, not by what it is called."""
        f = fill.get((t, c))
        where = f"identity via {tag}"
        if not f or "error" in (f or {}):
            b_unprobed.add(f"{t}.{c}", where + (f" | probe: {f['error']}" if f else ""))
        elif f["sampled"] == 0:
            b_no_data.add(f"{t}.{c}", where + " | table empty here")
        elif f["filled"] == 0:
            b_violation.add(f"{t}.{c}",
                            f"{where} | {f['sampled']} rows sampled, 0 non-null")
        elif f["nonintegral"]:
            b_nonintegral.add(f"{t}.{c}",
                              f"{where} | {f['nonintegral']} fractional of {f['filled']}")
        else:
            b_int_ordinal.add(f"{t}.{c}",
                              f"{where} | {f['filled']}/{f['sampled']} filled, "
                              f"range {f['min']}..{f['max']}, all integral")

    for (t, c), why in sorted(ident.items()):
        ty = decl.column_type(t, c)
        q = quant.get((t, c))
        tag = ",".join(sorted(why))
        if ty is None:
            b_undeclared.add(f"{t}.{c}", tag)
        elif ty == "number" and q:
            b_quantity_key.add(f"{t}.{c}", f"{tag} | quantity: {','.join(sorted(q))}")
        elif ty == "number":
            place_numeric(t, c, tag)
        elif ty == "datetime":
            b_datetime_ident.add(f"{t}.{c}", tag)
        else:
            b_string_ident.add(f"{t}.{c}", tag)

    for t, c, ty in decl.declared_columns():
        if ty == "number" and (t, c) not in ident:
            b_numeric_nonident.add(f"{t}.{c}",
                                   "quantity" if (t, c) in quant else "no evidence either way")

    buckets = [b_violation, b_nonintegral, b_unprobed, b_int_ordinal, b_no_data,
               b_quantity_key, b_datetime_ident, b_undeclared, b_string_ident,
               b_numeric_nonident]

    # The physical half. A column may be declared `string` and still be `double
    # precision` in the catalogue - that is the incident's actual shape and it is a
    # violation of R1 no matter which side is wrong.
    if phys is not None:
        b_phys = Bucket(
            "physical_numeric_identifier_never_populated", VIOLATION,
            "the CATALOGUE stores an identifier numerically - whatever the config now "
            "says - and the data probe finds it empty. This is the arm that still fires "
            "after someone repairs the declaration and forgets the migration.")
        b_phys_other = Bucket(
            "physical_numeric_identifier_populated", UNCLASSIFIED,
            "catalogue stores an identifier numerically and the column DOES hold values. "
            "Not automatically wrong (a coordinate lives here too) and not automatically "
            "right - a lot id that happens to be all digits today fits in a float until "
            "the day a letter arrives.")
        b_phys_missing = Bucket(
            "identifier_absent_from_catalogue", UNCLASSIFIED,
            "identifier evidence but no such physical column in this database.")
        numeric_types = {"double precision", "real", "integer", "bigint", "smallint",
                         "numeric"}
        for (t, c) in sorted(ident):
            if t not in phys.tables:
                continue
            dt = phys.type_of(t, c)
            f = fill.get((t, c)) or {}
            if dt is None:
                b_phys_missing.add(f"{t}.{c}")
            elif dt in numeric_types and (t, c) not in quant:
                if f.get("sampled") and not f.get("filled"):
                    b_phys.add(f"{t}.{c}", f"{dt}; {f['sampled']} rows, 0 non-null")
                else:
                    b_phys_other.add(f"{t}.{c}", f"{dt}; "
                                                 f"{f.get('filled', '?')}/{f.get('sampled', '?')} filled")
        buckets += [b_phys, b_phys_other, b_phys_missing]

    return RuleResult(
        "R1", "identifiers are never numeric", buckets,
        uncovered="Identity and arithmetic are both argued from CONFIG. A column that is "
                  "used as a lookup handle only in Python, or has arithmetic done on it "
                  "only in Python, is invisible here - see the UNCLASSIFIED buckets, "
                  "which is where such a column lands rather than being guessed either "
                  "way.")


def rule_r2(decl, phys):
    """R2 - a declared `business_key` obliges a UNIQUE index."""
    b_missing = Bucket(
        "declared_bk_no_unique_index", VIOLATION,
        "the table declares a `business_key` and no VALID unique index enforces it. The "
        "duplicate-recovery guard in `apply_batch_updates` fires on `IntegrityError`, "
        "which only happens if the index exists; without it two processes writing one "
        "key produce two rows and no error.")
    b_invalid = Bucket(
        "unique_index_present_but_invalid", VIOLATION,
        "an index exists and `indisvalid` is false - a cancelled CONCURRENTLY build. It "
        "enforces nothing and `IF NOT EXISTS` walks past it forever.")
    b_ok = Bucket("enforced", LEGITIMATE, "valid unique index on exactly (business_key_val).")
    b_no_column = Bucket(
        "declared_bk_but_no_bk_column", UNCLASSIFIED,
        "config declares a business key but the physical table has no "
        "`business_key_val` column in this database.")
    b_undeclared_table = Bucket(
        "bk_column_without_declaration", INFO,
        "physical table carries `business_key_val` but this config declares no "
        "`business_key` for it - engine table or an undeclared one.")
    b_absent = Bucket(
        "declared_table_absent_here", INFO,
        "declared table does not exist in this database - R2 says nothing about it.")

    for t, cfg in sorted(decl.tables.items()):
        if not cfg.get("business_key"):
            continue
        if t not in phys.tables:
            b_absent.add(t)
            continue
        if t not in phys.bk_tables:
            b_no_column.add(t)
            continue
        got = phys.unique_bk.get(t)
        if got and got[1]:
            b_ok.add(t, got[0])
        elif got:
            b_invalid.add(t, got[0])
        else:
            b_missing.add(t, f"declares business_key={cfg['business_key']}")

    for t in sorted(phys.bk_tables):
        if not (decl.tables.get(t) or {}).get("business_key"):
            b_undeclared_table.add(t)

    return RuleResult(
        "R2", "a declared business key obliges a UNIQUE index",
        [b_missing, b_invalid, b_ok, b_no_column, b_undeclared_table, b_absent],
        uncovered="⚠️ READ THE PER-DATABASE HEADER BEFORE READING THIS COUNT. If a "
                  "database has never had `add_business_key_unique_index.py --apply` run "
                  "against it, EVERY table lands in `declared_bk_no_unique_index` and the "
                  "list carries no information beyond that single fact. The list is only "
                  "worth reading table-by-table on a database where some tables are "
                  "enforced and others are not.")


def rule_r3(decl):
    """R3 - `map_key_columns` must be a subset of `composite_key_source`."""
    b_violation = Bucket(
        "map_key_not_in_composite_source", VIOLATION,
        "a map key column absent from the composite key source. The map editor omits "
        "`scope`, so `derive_replace_map_scope` takes the DERIVED branch; a key column "
        "it cannot fill WIDENS the scope instead of refusing, and a widened purge "
        "deletes `CellOverwrite` rows - human corrections - across the whole lot.")
    b_ok = Bucket("subset_holds", LEGITIMATE, "every map key column is in the composite source.")
    b_extra = Bucket(
        "composite_source_not_a_map_key", INFO,
        "composite source columns that are not map keys. Expected and fine - these are "
        "the within-map coordinates. Printed so the direction of the rule is visible.")
    b_no_map = Bucket("no_map_key_columns", INFO, "table declares no `map_key_columns`.")
    b_no_composite = Bucket(
        "map_keys_but_no_composite_source", VIOLATION,
        "map keys declared with no composite key source at all - the subset obligation "
        "cannot be met by a table that has no superset.")

    for t, cfg in sorted(decl.tables.items()):
        mk = list(cfg.get("map_key_columns") or [])
        ck = list(cfg.get("composite_key_source") or [])
        if not mk:
            b_no_map.add(t)
            continue
        if not ck:
            b_no_composite.add(t, f"map_key_columns={mk}")
            continue
        missing = [c for c in mk if c not in ck]
        if missing:
            b_violation.add(t, f"missing from composite_key_source: {missing}; "
                               f"composite={ck}")
        else:
            b_ok.add(t, f"map_key_columns={mk}")
        extra = [c for c in ck if c not in mk]
        if extra:
            b_extra.add(t, f"{extra}")

    return RuleResult(
        "R3", "map_key_columns is a subset of composite_key_source",
        [b_violation, b_no_composite, b_ok, b_extra, b_no_map],
        uncovered="Pure config check - fully covered for the config it was pointed at. It "
                  "does NOT check the follow-on rule (a derived branch that resolves only "
                  "SOME keys must refuse rather than return a partial dict); that lives in "
                  "`derive_replace_map_scope` and is a code property, not a schema one.")


def rule_r4(default_surface, decl):
    """R4 - the surface a writer must not send explicit NULL into.

    🔴 THIS IS NOT A VIOLATION CHECK AND MUST NOT BE READ AS ONE. Whether a writer sends
    `None` for a defaulted column is a property of the writer's dict at run time; the
    catalogue cannot see it and neither can this file. What is reported here is the
    SURFACE - every column where sending `None` instead of omitting the key changes what
    gets stored. An empty section here would mean "nothing to protect", never "no bug".
    """
    b_surface = Bucket(
        "defaulted_columns", INFO,
        "columns where an explicit NULL and an omitted key store DIFFERENT values. "
        "SQLAlchemy drops a defaulted column from the statement when its value is None; "
        "a multi-row VALUES writer names the column and writes NULL. Damage is per ROW, "
        "so 1 row in 500 goes wrong and 499 look fine.")
    b_py = Bucket(
        "python_side_default", INFO,
        "Python-side default. The riskier half: raw SQL leaves these NULL where the ORM "
        "would have computed a value. `cell_overwrites.is_overwrite` is one.")
    b_onupdate = Bucket(
        "onupdate_columns", INFO,
        "carries `onupdate` - an UPDATE that names the column overrides the refresh. "
        "The incident's UPDATE arm: `ingested_at` seeded, upserted with None, stored NULL.")
    b_named = Bucket(
        "named_in_the_incident", INFO,
        "the three columns SCHEMA_CANON names for R4. Present here means the surface "
        "this detector reports really does cover the incident.")
    b_declared_reserved = Bucket(
        "config_declares_a_reserved_metadata_name", VIOLATION,
        "`column_types` declares one of the engine's own metadata columns. "
        "`init_dynamic_models` SKIPS these names, so the declaration is dead: it "
        "promises a type nobody applies, and a reader sizing a write against the config "
        "is reading a column that does not behave the way it is written down.")

    incident = {("cell_sources", "ingested_at"), ("cell_overwrites", "updated_at"),
                ("cell_overwrites", "is_overwrite")}
    for (t, c), kinds in sorted(default_surface.items()):
        b_surface.add(f"{t}.{c}", kinds)
        if "py" in kinds.split("+"):
            b_py.add(f"{t}.{c}", kinds)
        if "onupdate" in kinds:
            b_onupdate.add(f"{t}.{c}", kinds)
        if (t, c) in incident:
            b_named.add(f"{t}.{c}", kinds)

    for t, cfg in sorted(decl.tables.items()):
        for c in sorted((cfg.get("column_types") or {})):
            if c in RESERVED_METADATA_COLUMNS:
                b_declared_reserved.add(f"{t}.{c}",
                                        f"declared {cfg['column_types'][c]}, engine ignores it")

    return RuleResult(
        "R4", "no explicit NULL into a defaulted column",
        [b_declared_reserved, b_surface, b_py, b_onupdate, b_named],
        uncovered="THE RULE ITSELF IS UNCHECKABLE FROM SCHEMA. R4 constrains what a writer "
                  "puts in a dict, and the enforcement that exists is a runtime refusal in "
                  "`crud._pg_multirow_upsert` (`python_default_omitted` / "
                  "`defaulted_column_is_none`). This section reports the surface that "
                  "refusal protects and nothing else. Do not read a small number here as "
                  "safety.")


def rule_r5(decl, phys=None):
    """R5 - times are `timestamptz`, and world time is declared per source."""
    b_naive = Bucket(
        "physical_timestamp_without_time_zone", VIOLATION,
        "a naive timestamp. This system runs KST and stores UTC, so a value with no zone "
        "is a value nobody can say which one it is.")
    b_text_time = Bucket(
        "world_time_column_declared_string", VIOLATION,
        "a column whose NAME says it carries an event time, declared `string` - so it "
        "lands in the catalogue as varchar. A world time stored as text has no zone, no "
        "ordering the database understands, and no way to refuse a bad value. ⚠️ THE "
        "MEMBERSHIP OF THIS BUCKET IS ARGUED FROM THE COLUMN NAME (see `uncovered`).")
    b_declared_dt = Bucket(
        "declared_datetime", LEGITIMATE, "declared `datetime` -> `DateTime(timezone=True)`.")
    b_dt_mismatch = Bucket(
        "declared_datetime_but_physical_is_not_timestamptz", VIOLATION,
        "config says datetime, the catalogue says otherwise.")
    b_tz_ok = Bucket("physical_timestamptz", LEGITIMATE, "stored with a zone. Correct.")

    # 🔴 The membership of the text-time bucket is argued from the NAME, so the predicate
    # is written to be refutable rather than generous. `endswith` on a time token, not
    # `in`: a plain `in "date"` test claims `updated_by` is a timestamp (it contains
    # "date" inside "up-date-d") - measured, 2 false members out of 10 - and a bucket
    # that cries wolf twice gets read as noise the third time, when it is right.
    def looks_like_a_world_time(name):
        low = name.lower()
        if low.endswith(("_by", "_id", "_key", "_type", "_zone")):
            return False
        return low.endswith(("time", "_at", "date", "stamp", "_ts")) or low == "ts"

    for t, c, ty in decl.declared_columns():
        low = c.lower()
        if ty == "datetime":
            b_declared_dt.add(f"{t}.{c}")
            if phys is not None and t in phys.tables:
                dt = phys.type_of(t, c)
                if dt is not None and dt not in DECLARED_TO_PHYSICAL["datetime"]:
                    b_dt_mismatch.add(f"{t}.{c}", f"physical={dt}")
        elif ty == "string" and looks_like_a_world_time(low) \
                and c not in RESERVED_METADATA_COLUMNS:
            b_text_time.add(f"{t}.{c}", "declared string")

    if phys is not None:
        for (t, c), meta in sorted(phys.columns.items()):
            if meta["data_type"] == "timestamp without time zone":
                b_naive.add(f"{t}.{c}")
            elif meta["data_type"] == "timestamp with time zone":
                b_tz_ok.add(f"{t}.{c}")

    return RuleResult(
        "R5", "tz-aware timestamps, world time declared per source",
        [b_naive, b_text_time, b_dt_mismatch, b_declared_dt, b_tz_ok],
        uncovered="TWO GAPS, AND THE FIRST ONE MATTERS MORE THAN THE COUNT ABOVE. "
                  "(a) `timestamp without time zone` being ZERO is NOT an all-clear: the "
                  "way this schema actually stores world time is TEXT, which no timestamp "
                  "scan can see. That is what `world_time_column_declared_string` is for, "
                  "and its membership comes from the column NAME, so it can miss a "
                  "differently-named time column and can catch a non-time column that "
                  "happens to contain 'date'. Read the members, not the count. "
                  "(b) R5's second half - 'do not substitute arrival time for world time, "
                  "declare a per-source column' - has no config surface to check yet; "
                  "there is nowhere in `table_config` that says WHICH column is the "
                  "source's event time, so the absence of that declaration is itself the "
                  "finding and is not counted here.")


def rule_r6(decl, phys):
    """R6 - a marker is not a key; a column read as a lookup needs an index."""
    ident = identifier_evidence(decl)

    # 🔴 NOT EVERY "declared key" IS QUERIED BY ITS OWN NAME, AND COUNTING THEM TOGETHER
    # PRODUCES A NUMBER THAT IS ARITHMETICALLY CORRECT AND MEANS NOTHING. Three kinds of
    # evidence with three different obligations:
    #
    #   queried directly   `map_key_columns` / overlay `key_columns` / a chain's job
    #                      column. `map_overlay.build_key_filters` emits `col == value`
    #                      on exactly these, so an unindexed one IS a sequential scan on
    #                      every map open. This is the bucket R6 is about.
    #   composed only      a `composite_key_source` member. Nobody filters on it alone;
    #                      it is joined with a separator into `business_key_val`, and
    #                      THAT column carries the index. Demanding an index here would
    #                      be demanding indexes nothing would ever use.
    #   mirrored           the column named by `business_key`. Its value is copied into
    #                      `business_key_val`, which is indexed, so lookups already have
    #                      their index under a different name.
    QUERIED = {"map_key_columns", "overlay.key_columns"}
    b_unindexed = Bucket(
        "queried_key_with_no_index", VIOLATION,
        "a column that map/chain lookups filter on BY NAME, with no index leading on it. "
        "Every such lookup is a sequential scan, and at 10M rows that is a stalled "
        "screen rather than a slow one.")
    b_buried = Bucket(
        "queried_key_indexed_only_as_a_non_leading_column", VIOLATION,
        "present in an index but not in the leading position, which does not serve an "
        "equality lookup on the column alone.")
    b_composed = Bucket(
        "composite_source_member_unindexed", LEGITIMATE,
        "part of a composite that is joined into `business_key_val`; the mirror carries "
        "the index and nothing filters on this column by itself. Listed so the exemption "
        "is visible rather than assumed.")
    b_mirrored = Bucket(
        "business_key_column_unindexed_but_mirrored", LEGITIMATE,
        "the config-named business key column. Its value lives again in "
        "`business_key_val`, which IS indexed, so the lookup path is covered under "
        "another name. ⚠️ This exemption is exactly as strong as the mirror - see R2, "
        "which is about whether that mirror is UNIQUE.")
    b_ok = Bucket("indexed", LEGITIMATE, "leads an index.")
    b_absent = Bucket("not_in_this_database", INFO, "declared key with no physical column here.")
    b_marker = Bucket(
        "stored_marker_not_indexed_not_declared_a_key", INFO,
        "R6's named incident shape: a column that is stored, is nullable, has no index, "
        "and nothing declares as a key. Harmless TODAY. The rule exists because the day "
        "someone starts querying by it, promotion has to be a DECISION - index plus NULL "
        "contract plus uniqueness contract - and not a side effect.")

    for (t, c), why in sorted(ident.items()):
        tag = ",".join(sorted(why))
        queried = bool(QUERIED & why) or any(w.startswith("chain.") for w in why)
        if t not in phys.tables or (t, c) not in phys.columns:
            b_absent.add(f"{t}.{c}", tag)
        elif (t, c) in phys.indexed_leading:
            b_ok.add(f"{t}.{c}", tag)
        elif not queried:
            # Mirrored beats composed when the column is both: the business key column is
            # copied wholesale, which is the stronger of the two exemptions.
            (b_mirrored if "business_key" in why else b_composed).add(f"{t}.{c}", tag)
        elif (t, c) in phys.indexed_any:
            b_buried.add(f"{t}.{c}", tag)
        else:
            b_unindexed.add(f"{t}.{c}", tag)

    # The marker census is restricted to the incident's own shape so it stays readable:
    # nullable, unindexed, no identity evidence, and NOT one of the engine's bookkeeping
    # columns (which are markers on purpose).
    engine_ish = ("is_", "needs_", "has_", "_count", "note", "comment", "desc", "color")
    for (t, c), meta in sorted(phys.columns.items()):
        if (t, c) in ident or (t, c) in phys.indexed_any:
            continue
        if not meta["is_nullable"] or c in RESERVED_METADATA_COLUMNS:
            continue
        if any(c.startswith(p) or c.endswith(p) for p in engine_ish):
            continue
        b_marker.add(f"{t}.{c}", meta["data_type"])

    return RuleResult(
        "R6", "a marker is not a key",
        [b_unindexed, b_buried, b_ok, b_mirrored, b_composed, b_absent, b_marker],
        uncovered="🔴 THIS IS THE NARROWER CHECK, NOT THE RULE. R6 is about columns READ as "
                  "a filter; finding every lookup site would mean resolving a filter "
                  "expression back to a column through the query builders, which this file "
                  "does not attempt. What is covered: columns CONFIG declares as keys, "
                  "checked against the catalogue. What is NOT covered: a column filtered on "
                  "only in Python or in raw SQL and never declared - exactly "
                  "`FileIngestionCheckpoint.filepath`'s shape, which is why the marker "
                  "census is printed as INFO instead of being left out.")


class _LimitScan(ast.NodeVisitor):
    """Find capped reads and ask whether they carry a total order.

    An AST walk rather than a line grep, because a grep counts `LIMIT` inside comments and
    docstrings and cannot tell `.limit(` on a query from `.limit(` on anything else. Two
    tiers of evidence, kept apart on purpose:
      * SAME CHAIN  - `order_by` in the same attribute chain as the `.limit(`. Strong.
      * SAME SCOPE  - `order_by` somewhere in the enclosing function. Weak: it may be
                      applied to a different query object entirely.
    """

    def __init__(self, path, src):
        self.path, self.src = path, src
        self.func_stack = []
        self.findings = []

    def _visit_func(self, node):
        # `order_by` sites in this function, with their source text, so the tie-break
        # question can be asked of the actual expression rather than guessed.
        orders = []
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) \
                    and sub.func.attr in ("order_by", "order_desc"):
                orders.append(ast.get_source_segment(self.src, sub) or "order_by(?)")
        self.func_stack.append((node.name, orders))
        self.generic_visit(node)
        self.func_stack.pop()

    visit_FunctionDef = _visit_func
    visit_AsyncFunctionDef = _visit_func

    def visit_Call(self, node):
        if isinstance(node.func, ast.Attribute) and node.func.attr == "limit":
            self._record(node)
        self.generic_visit(node)

    def _record(self, node):
        chain, cur = [], node.func.value
        while isinstance(cur, (ast.Call, ast.Attribute)):
            if isinstance(cur, ast.Call):
                if isinstance(cur.func, ast.Attribute):
                    chain.append(cur.func.attr)
                cur = cur.func
            else:
                chain.append(cur.attr)
                cur = cur.value
        fname, orders = self.func_stack[-1] if self.func_stack else ("<module>", [])
        same_chain = any(a in ("order_by", "order_desc") for a in chain)
        seg = ast.get_source_segment(self.src, node) or ".limit(...)"
        ordering_text = " ".join(orders) if orders else ""
        if same_chain:
            ordering_text = seg
        self.findings.append({
            "file": self.path, "line": node.lineno, "func": fname,
            "text": seg.replace("\n", " ")[:150],
            "tier": "same_chain" if same_chain else ("same_scope" if orders else "none"),
            "tiebreak": any(k in ordering_text for k in ("row_id", ".id", "_id.asc",
                                                         "_id.desc", "id.asc", "id.desc")),
        })


def scan_capped_reads(roots=None, skip_dirs=("tests", "__pycache__", "archive", ".tmp")):
    """Every `.limit(` and every raw `LIMIT`, bucketed by the ordering evidence found."""
    roots = roots or [SERVER_ROOT]
    out = []
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in skip_dirs]
            for fn in filenames:
                if not fn.endswith(".py"):
                    continue
                path = os.path.join(dirpath, fn)
                try:
                    with io.open(path, encoding="utf-8") as fh:
                        src = fh.read()
                    tree = ast.parse(src)
                except (SyntaxError, UnicodeDecodeError, OSError):
                    continue
                rel = os.path.relpath(path, REPO_ROOT).replace("\\", "/")
                v = _LimitScan(rel, src)
                v.visit(tree)
                out.extend(v.findings)
                out.extend(_scan_sql_strings(tree, rel))
    return out


# A line that BEGINS a SQL statement, optionally after an opening paren. `UPDATE`/`DELETE`
# are kept in the set on purpose: a capped subquery inside a write is still a capped read
# choosing which rows to touch, and dropping it would be filtering out evidence.
_SQL_LINE_START = re.compile(r"^\s*\(?\s*(select|update|delete|insert|with)\b", re.I)


def _scan_sql_strings(tree, rel):
    """Raw `LIMIT` inside string literals, judged inside the string itself.

    🔴 The string must LOOK like SQL before its `LIMIT` is judged, and "contains the
    words select, from and limit" is NOT enough of a test. Two measured false positives,
    both of them a detector reading prose about SQL as SQL:
      * this file's own docstring, on the English "63-byte identifier limit";
      * `value_suggest.py`'s module docstring, where `select` is at offset 253, ` from `
        at 2130 and ` limit ` at 3921 - three unrelated English sentences.
    The gate that separates them is STRUCTURAL: a real query literal has a LINE that
    begins with a SQL verb. Prose about a query does not.
    """
    out = []
    for sub in ast.walk(tree):
        if not (isinstance(sub, ast.Constant) and isinstance(sub.value, str)):
            continue
        s = sub.value
        low = s.lower()
        if "select" not in low or " from " not in low:
            continue
        if " limit " not in f" {low} " and not low.rstrip().endswith("limit"):
            continue
        if not any(_SQL_LINE_START.match(ln) for ln in s.splitlines()):
            continue
        has_order = "order by" in low
        out.append({
            "file": rel, "line": getattr(sub, "lineno", 0), "func": "<sql string>",
            "text": " ".join(s.split())[:150],
            "tier": "same_chain" if has_order else "none",
            "tiebreak": has_order and any(k in low for k in ("row_id", ".id", " id")),
        })
    return out


# A capped read inside a one-shot diagnostic is not the incident R7 came from: nobody
# refreshes a script and gets different cells. Split rather than filtered - a bucket
# nobody printed is a claim nobody can check, and one of these directories may well hold
# a read that graduates into a request path later.
_TOOLING_PATH_MARKERS = ("/scripts/", "/migrations/", "/dev_env/", "/_qa", "/probe_",
                         "/diagnose_", "/seed_")


def _is_tooling(path):
    p = "/" + path.replace("\\", "/")
    return any(m in p for m in _TOOLING_PATH_MARKERS)


def rule_r7(findings):
    """R7 - a capped read needs a TOTAL order."""
    b_none = Bucket(
        "capped_read_with_no_ordering_found", VIOLATION,
        "a cap with no `order_by` in the same chain and none anywhere in the enclosing "
        "function. A capped map then returns DIFFERENT cells per refresh and raises no "
        "error - measured at `cell_cap=50`: 2 distinct payloads in 8 reads.")
    b_scope = Bucket(
        "ordering_only_elsewhere_in_the_function", UNCLASSIFIED,
        "an `order_by` exists in the enclosing function but not in this chain. It may "
        "order this query or a different one - the scan cannot tell.")
    b_no_tiebreak = Bucket(
        "ordered_but_no_id_tiebreak", VIOLATION,
        "ordered in the same chain, but the key set shows no `row_id`/`id` last key. A "
        "partial order leaves ties, and ties are the planner's choice - which is the "
        "same non-determinism with a smaller blast radius.")
    b_ok = Bucket("ordered_with_tiebreak", LEGITIMATE,
                  "same-chain ordering that includes an id-like final key.")
    b_tooling = Bucket(
        "unordered_cap_in_tooling_not_a_request_path", INFO,
        "the same shape, inside a script/migration/diagnostic. Nobody refreshes a "
        "one-shot and gets different cells, so it is not the incident - but it is "
        "printed, not filtered, because a scratch read that graduates into a request "
        "path brings the defect with it.")

    for f in findings:
        where = f"{f['file']}:{f['line']} ({f['func']})"
        if f["tier"] == "none":
            (b_tooling if _is_tooling(f["file"]) else b_none).add(where, f["text"])
        elif f["tier"] == "same_scope":
            b_scope.add(where, f["text"])
        elif f["tiebreak"]:
            b_ok.add(where)
        elif _is_tooling(f["file"]):
            b_tooling.add(where, f["text"])
        else:
            b_no_tiebreak.add(where, f["text"])

    return RuleResult(
        "R7", "a capped read needs a total order",
        [b_none, b_no_tiebreak, b_scope, b_ok, b_tooling],
        uncovered="🔴 THIS IS A SOURCE SCAN AND IT IS NOT A PROOF. It is structural (AST, "
                  "so comments and docstrings do not count) but it still cannot follow a "
                  "query object across function boundaries, through a helper that applies "
                  "the ordering, or into a `text()` fragment assembled from pieces. Expect "
                  "false positives in `capped_read_with_no_ordering_found` and assume false "
                  "NEGATIVES exist too. Every member is a site to open, not a defect.")


# Tables that are engine machinery rather than a production stage. Stated HERE, in one
# named list that the report prints in full, precisely so the exceptions are auditable
# instead of assumed - an exception nobody can see is indistinguishable from a bug.
ENGINE_TABLES = frozenset({
    "audit_logs", "cell_sources", "cell_overwrites", "database_outbox",
    "file_ingestion_checkpoints", "file_ingestion_logs", "graph_edges", "graph_nodes",
    "graph_sync_state", "interaction_effort_logs", "line_model_registry",
    "frame_confirmation", "frame_confirmation_source",
})
STAGE_PREFIXES = ("core_", "dt_", "bond_")
# The canon's table says `bond_*`; the codebase spells the TABLE `bonding_*` and the
# COLUMNS `bond_*`. Same stage, two spellings - reported as its own bucket rather than as
# a violation, because which spelling wins is the lead PM's call and not this file's.
STAGE_PREFIX_VARIANTS = {"bonding_": "bond_"}


def rule_r8(decl, phys=None):
    """R8 - stage prefixes follow fab -> dt -> bonding."""
    b_off = Bucket(
        "declared_table_off_canon_prefix", VIOLATION,
        "a table declared in config whose name starts with none of core_/dt_/bond_ and "
        "is not on the stated engine list. Either it belongs to a stage and is misnamed, "
        "or the exception list is missing an entry - both are decisions, not defaults.")
    b_variant = Bucket(
        "stage_prefix_spelling_variant", UNCLASSIFIED,
        f"matches a stage under a different spelling {dict(STAGE_PREFIX_VARIANTS)}. Same "
        f"layer, and the canon's table and the schema disagree on how to write it.")
    b_ok = Bucket("canonical_stage_prefix", LEGITIMATE, "core_/dt_/bond_.")
    b_engine = Bucket("engine_table_exception", INFO,
                      "on the stated engine list above - not a stage table at all.")
    b_undeclared = Bucket(
        "physical_table_not_declared_and_not_engine", UNCLASSIFIED,
        "exists in the database, is not in this config, and is not on the engine list. "
        "Fixture, leftover, or a stage table nobody declared - it cannot be judged from "
        "here, and that is the point of printing it.")
    b_col_naked = Bucket(
        "column_in_a_stage_table_with_no_stage_prefix", INFO,
        "a column inside a stage table carrying no stage prefix. Mostly correct - key "
        "and value columns like `c_bn`, `val`, `product` are not stage facts - so this "
        "is a census to read, not a defect list.")
    b_col_cross = Bucket(
        "cross_stage_column_reference", LEGITIMATE,
        "a column carrying ANOTHER stage's prefix inside this table, e.g. `dt_lot` in "
        "`bonding_log`. That is the join between layers and R8 explicitly wants the name "
        "to change when the fact crosses a layer.")

    def classify(t):
        if t in ENGINE_TABLES:
            return "engine"
        for v in STAGE_PREFIX_VARIANTS:
            if t.startswith(v):
                return "variant"
        return "ok" if any(t.startswith(p) for p in STAGE_PREFIXES) else "off"

    for t in sorted(decl.tables):
        k = classify(t)
        {"engine": b_engine, "variant": b_variant, "ok": b_ok, "off": b_off}[k].add(t)

    if phys is not None:
        for t in sorted(phys.tables):
            if t not in decl.tables and t not in ENGINE_TABLES:
                b_undeclared.add(t)

    for t, cfg in sorted(decl.tables.items()):
        own = None
        for p in STAGE_PREFIXES:
            if t.startswith(p):
                own = p
        for v, canonical in STAGE_PREFIX_VARIANTS.items():
            if t.startswith(v):
                own = canonical
        if not own:
            continue
        for c in sorted(cfg.get("column_types") or {}):
            if c.startswith(own):
                continue
            other = [p for p in STAGE_PREFIXES if c.startswith(p)]
            if other:
                b_col_cross.add(f"{t}.{c}", f"table stage {own}")
            else:
                b_col_naked.add(f"{t}.{c}", f"table stage {own}")

    return RuleResult(
        "R8", "stage prefixes follow fab -> dt -> bonding",
        [b_off, b_variant, b_ok, b_engine, b_undeclared, b_col_cross, b_col_naked],
        uncovered="The engine exception list is HAND-MAINTAINED (`ENGINE_TABLES` in this "
                  "file) and printed with the report so it can be argued with. R8's real "
                  "content - 'the same fact must not get two names inside one layer' - is "
                  "NOT checked: deciding that `core_lot` and some other column are the "
                  "same fact needs semantics no config carries.")


# PostgreSQL type families. Two spellings inside one family are a width or storage
# choice; two spellings ACROSS families mean the same fact is being kept as two different
# kinds of thing, which is the disagreement that matters.
TYPE_FAMILY = {}
for _fam, _types in {
    "text": ("character varying", "text", "character"),
    "numeric": ("smallint", "integer", "bigint", "real", "double precision", "numeric"),
    "temporal": ("timestamp with time zone", "timestamp without time zone", "date",
                 "time without time zone", "time with time zone", "interval"),
    "bool": ("boolean",),
    "json": ("json", "jsonb"),
}.items():
    for _t in _types:
        TYPE_FAMILY[_t] = _fam


def cross_table_type_conflicts(phys, decl):
    """One column NAME, two different type FAMILIES, across tables.

    🔴 THIS IS THE ARM THAT ACTUALLY CATCHES R1's OWN INCIDENT, and the key-evidence arm
    above does not. `dt_inventory.dt_lot` is not declared a business key, is not in any
    composite source, and is not a map key - nothing in the config says it is identity, so
    a detector built only from key declarations walks straight past the exact column the
    rule was written for. What DOES give it away needs no list of names and no semantics:
    `dt_lot` is `character varying` in `bonding_log`, `dt_job_attribution` and `dt_log`,
    and `double precision` in `dt_inventory`. The schema is holding one fact as two kinds
    of thing, and one of the two must be wrong.

    It is also the general form of R8's closing sentence - the same fact must not acquire
    two spellings inside a layer - applied to types instead of names, and it independently
    re-finds R5's text timestamps (`event_time` is `timestamptz` in `graph_edges` and
    varchar in five domain tables).
    """
    by_name = {}
    for (t, c), meta in phys.columns.items():
        by_name.setdefault(c, {})[t] = meta["data_type"]
    hard, soft = [], []
    for c, m in sorted(by_name.items()):
        fams = {TYPE_FAMILY.get(dt, dt) for dt in m.values()}
        if len(fams) > 1:
            hard.append((c, m, sorted(fams)))
        elif len(set(m.values())) > 1:
            soft.append((c, m))
    return hard, soft


def rule_mismatch(decl, phys):
    """Declaration vs physical. R1's incident is exactly this shape."""
    b_type = Bucket(
        "declared_type_disagrees_with_catalogue", VIOLATION,
        "config declares one type and the database stores another. One of the two is "
        "lying to whoever reads it, and the incident that produced R1 was a column "
        "declared `number`, built `double precision`, and asked to hold "
        "`CL_2601_005_A5`.")
    b_missing = Bucket(
        "declared_column_absent_from_catalogue", VIOLATION,
        "declared and not built. Reads of it fail or return nothing depending on the path.")
    b_table_missing = Bucket("declared_table_absent_from_catalogue", INFO,
                             "declared table that does not exist in this database.")
    b_extra = Bucket(
        "physical_column_not_declared", INFO,
        "in the database and not in this config - engine metadata columns, or drift.")
    b_ok = Bucket("agrees", LEGITIMATE, "declared type and physical type agree.")
    b_unknown = Bucket("unknown_declared_type", UNCLASSIFIED,
                       "a `column_types` value this file has no mapping for.")
    b_cross = Bucket(
        "same_column_name_stored_as_conflicting_type_families", VIOLATION,
        "one column NAME held as two different kinds of thing across tables - text here, "
        "a number or a timestamp there. One of the two is wrong, and this arm finds "
        "R1's own incident column, which the key-evidence arm cannot see because nothing "
        "declares it a key.")
    b_cross_soft = Bucket(
        "same_column_name_differing_within_one_type_family", INFO,
        "varchar vs text, integer vs bigint - a width or storage choice, not a "
        "disagreement about what the column IS. Printed so the hard bucket above can be "
        "read as the narrower claim it is.")
    b_cross_decl = Bucket(
        "same_column_name_declared_with_conflicting_types", VIOLATION,
        "the CONFIG itself gives one column name two different `column_types` across "
        "tables. Cheaper to catch than the physical version and it survives a database "
        "that has not been migrated yet.")

    engine_cols = RESERVED_METADATA_COLUMNS | {"row_id", "business_key_val"}
    for t, cfg in sorted(decl.tables.items()):
        if t not in phys.tables:
            b_table_missing.add(t)
            continue
        types = cfg.get("column_types") or {}
        for c, ty in sorted(types.items()):
            got = phys.type_of(t, c)
            expect = DECLARED_TO_PHYSICAL.get(ty)
            if expect is None:
                b_unknown.add(f"{t}.{c}", ty)
            elif got is None:
                b_missing.add(f"{t}.{c}", f"declared {ty}")
            elif got in expect:
                b_ok.add(f"{t}.{c}", f"{ty} -> {got}")
            else:
                b_type.add(f"{t}.{c}", f"declared {ty} (expects {sorted(expect)}), "
                                       f"catalogue has {got}")
        for (pt, pc) in phys.columns:
            if pt == t and pc not in types and pc not in engine_cols:
                b_extra.add(f"{t}.{pc}", phys.type_of(t, pc))

    hard, soft = cross_table_type_conflicts(phys, decl)
    for c, m, fams in hard:
        b_cross.add(c, f"families {fams}: " + ", ".join(f"{t}={dt}" for t, dt in sorted(m.items())))
    for c, m in soft:
        b_cross_soft.add(c, ", ".join(f"{t}={dt}" for t, dt in sorted(m.items())))

    declared_by_name = {}
    for t, c, ty in decl.declared_columns():
        declared_by_name.setdefault(c, {})[t] = ty
    for c, m in sorted(declared_by_name.items()):
        if len(set(m.values())) > 1:
            b_cross_decl.add(c, ", ".join(f"{t}={ty}" for t, ty in sorted(m.items())))

    return RuleResult(
        "MISMATCH", "declaration vs physical, and the schema vs itself",
        [b_type, b_missing, b_cross, b_cross_decl, b_unknown, b_table_missing,
         b_cross_soft, b_extra, b_ok],
        uncovered="Compares only columns SOME side declares, plus the cross-table name "
                  "sweep which needs no declaration at all. A physical table absent from "
                  "the config is reported by R8, not here. 🔴 It also cannot compare TWO "
                  "DATABASES: run it against each and diff the bucket counts - on this "
                  "box that diff is the finding, because the two development databases "
                  "are NOT in the same state.")


# =============================================================================
# FAULT INJECTION - a zero is worthless until the detector is shown to fire
# =============================================================================

def _clean_decl():
    """A synthetic, canon-clean config. Every rule must report zero violations on it."""
    return Declarations(
        tables={
            "dt_probe": {
                "business_key": "dt_job",
                "composite_key_source": ["dt_job", "dt_x", "dt_y"],
                "map_key_columns": ["dt_job"],
                "column_types": {"dt_job": "string", "dt_x": "number",
                                 "dt_y": "number", "dt_bn": "string"},
            },
        },
        chain_rules=[],
        overlay_bindings={"dt_probe": {"columns": {"x": "dt_x", "y": "dt_y",
                                                   "key_columns": ["dt_job"]}}},
        source="<synthetic>")


def _clean_phys():
    p = PhysicalSchema("<synthetic>")
    p.tables = {"dt_probe"}
    for c, dt in (("dt_job", "character varying"), ("dt_x", "double precision"),
                  ("dt_y", "double precision"), ("dt_bn", "character varying"),
                  ("business_key_val", "character varying")):
        p.columns[("dt_probe", c)] = {"data_type": dt, "column_default": None,
                                      "is_nullable": True}
    p.indexed_leading = {("dt_probe", "dt_job"), ("dt_probe", "dt_x"),
                         ("dt_probe", "dt_y"), ("dt_probe", "business_key_val")}
    p.indexed_any = set(p.indexed_leading)
    p.bk_tables = {"dt_probe"}
    p.unique_bk = {"dt_probe": ("uq_bk_dt_probe", True)}
    return p


def _copy_decl(d):
    return Declarations(json.loads(json.dumps(d.tables)),
                        json.loads(json.dumps(d.chain_rules)),
                        json.loads(json.dumps(d.overlay_bindings)), d.source)


def _copy_phys(p):
    q = PhysicalSchema(p.label)
    q.tables = set(p.tables)
    q.columns = {k: dict(v) for k, v in p.columns.items()}
    q.indexed_leading = set(p.indexed_leading)
    q.indexed_any = set(p.indexed_any)
    q.unique_bk = dict(p.unique_bk)
    q.bk_tables = set(p.bk_tables)
    return q


def _violating_members(res):
    out = []
    for b in res.buckets:
        if b.verdict == VIOLATION:
            out += [f"{b.key}:{m}" for m in b.members]
    return out


_CLEAN_R7 = "def f(db):\n    return db.query(X).order_by(X.row_id.asc()).limit(10).all()\n"
_FAULT_R7 = "def f(db):\n    return db.query(X).filter(X.a == 1).limit(10).all()\n"


def _scan_source_text(src, name="<injected>"):
    """Both arms of the R7 scanner over one source string - what a file walk does per file."""
    tree = ast.parse(src)
    v = _LimitScan(name, src)
    v.visit(tree)
    return v.findings + _scan_sql_strings(tree, name)


def self_test(verbose=True):
    """Plant one violation per rule; require silence before and noise after.

    Both halves are asserted. A detector that fires on everything would sail through a
    test that only checks the faulted case, and this project has already shipped one
    alarm that had never been rung.
    """
    cases = []

    # R1: retype an identifier that has no arithmetic declaration, and give the probe the
    # incident's own reading - rows present, none of them filled.
    d = _copy_decl(_clean_decl())
    d.tables["dt_probe"]["column_types"]["dt_lot"] = "string"
    d.tables["dt_probe"]["composite_key_source"].append("dt_lot")
    clean = _copy_decl(d)
    d.tables["dt_probe"]["column_types"]["dt_lot"] = "number"
    empty_probe = {("dt_probe", "dt_lot"): {"sampled": 251, "filled": 0, "min": None,
                                            "max": None, "nonintegral": 0}}
    cases.append(("R1", "identifier `dt_lot` retyped number AND the column is 0/251 filled",
                  lambda x=clean: rule_r1(x, _clean_phys(), empty_probe),
                  lambda x=d: rule_r1(x, _clean_phys(), empty_probe)))

    # 🔴 The counter-case: the SAME retype, but with data that says coordinate. It must
    # NOT come out as a violation. Without this half the detector could be a rubber stamp
    # that calls every numeric key column a defect and still pass a fault injection.
    coord_probe = {("dt_probe", "dt_lot"): {"sampled": 4598, "filled": 4598, "min": -20.0,
                                            "max": 40.0, "nonintegral": 0}}
    r_coord = rule_r1(d, _clean_phys(), coord_probe)
    coord_ok = (not _violating_members(r_coord)) and any(
        b.key == "numeric_identifier_holding_only_small_integers" and len(b)
        for b in r_coord.buckets)

    # R1 probe-blind arm: no probe data at all must be held as a violation, not dismissed.
    cases.append(("R1-unprobed", "numeric identifier with NO probe data available",
                  lambda x=clean: rule_r1(x, _clean_phys(), {}),
                  lambda x=d: rule_r1(x, _clean_phys(), {})))

    # R1 physical arm: catalogue turns an identifier numeric while config stays string.
    pf = _copy_phys(_clean_phys())
    pf.columns[("dt_probe", "dt_job")]["data_type"] = "double precision"
    job_empty = {("dt_probe", "dt_job"): {"sampled": 251, "filled": 0, "min": None,
                                          "max": None, "nonintegral": 0}}
    cases.append(("R1-phys", "catalogue stores identifier `dt_job` as double precision, empty",
                  lambda: rule_r1(_clean_decl(), _clean_phys(), job_empty),
                  lambda p=pf: rule_r1(_clean_decl(), p, job_empty)))

    # R2: take the unique index away.
    p2 = _copy_phys(_clean_phys())
    p2.unique_bk["dt_probe"] = None
    p3 = _copy_phys(_clean_phys())
    p3.unique_bk["dt_probe"] = ("uq_bk_dt_probe", False)
    cases.append(("R2", "unique index removed",
                  lambda: rule_r2(_clean_decl(), _clean_phys()),
                  lambda p=p2: rule_r2(_clean_decl(), p)))
    cases.append(("R2-invalid", "unique index present but indisvalid=false",
                  lambda: rule_r2(_clean_decl(), _clean_phys()),
                  lambda p=p3: rule_r2(_clean_decl(), p)))

    # R3: drop a map key out of the composite source.
    d3 = _copy_decl(_clean_decl())
    d3.tables["dt_probe"]["map_key_columns"] = ["dt_job", "dt_slot"]
    cases.append(("R3", "map key `dt_slot` absent from composite_key_source",
                  lambda: rule_r3(_clean_decl()),
                  lambda x=d3: rule_r3(x)))

    # R4: declare a reserved metadata name, which the engine silently ignores.
    d4 = _copy_decl(_clean_decl())
    d4.tables["dt_probe"]["column_types"]["updated_at"] = "string"
    surface = {("dt_probe", "dt_bn"): "py"}
    cases.append(("R4", "config declares reserved metadata name `updated_at`",
                  lambda: rule_r4(surface, _clean_decl()),
                  lambda x=d4: rule_r4(surface, x)))

    # R4 surface arm: the INFO bucket must actually populate, or the section is silence
    # dressed as safety. Checked separately from the violation halves above.
    empty_surface_ok = len(rule_r4({}, _clean_decl()).buckets[1]) == 0
    filled_surface_ok = len(rule_r4(surface, _clean_decl()).buckets[1]) == 1

    # R5: both arms - a naive physical timestamp, and a text-typed world time.
    p5 = _copy_phys(_clean_phys())
    p5.columns[("dt_probe", "seen_at")] = {"data_type": "timestamp without time zone",
                                           "column_default": None, "is_nullable": True}
    cases.append(("R5-naive", "physical column typed `timestamp without time zone`",
                  lambda: rule_r5(_clean_decl(), _clean_phys()),
                  lambda p=p5: rule_r5(_clean_decl(), p)))
    d5 = _copy_decl(_clean_decl())
    d5.tables["dt_probe"]["column_types"]["event_time"] = "string"
    cases.append(("R5-text", "world time `event_time` declared string",
                  lambda: rule_r5(_clean_decl(), _clean_phys()),
                  lambda x=d5: rule_r5(x, _clean_phys())))

    # R6: strip the index off a QUERIED key (`dt_job` is a map key column here).
    p6 = _copy_phys(_clean_phys())
    p6.indexed_leading.discard(("dt_probe", "dt_job"))
    p6.indexed_any.discard(("dt_probe", "dt_job"))
    p7 = _copy_phys(_clean_phys())
    p7.indexed_leading.discard(("dt_probe", "dt_job"))
    cases.append(("R6", "queried key `dt_job` loses its index",
                  lambda: rule_r6(_clean_decl(), _clean_phys()),
                  lambda p=p6: rule_r6(_clean_decl(), p)))
    cases.append(("R6-buried", "queried key indexed only as a non-leading column",
                  lambda: rule_r6(_clean_decl(), _clean_phys()),
                  lambda p=p7: rule_r6(_clean_decl(), p)))

    # 🔴 R6 counter-case: a COMPOSITE-SOURCE-ONLY column losing its index must stay
    # LEGITIMATE. This is the half that stops R6 from re-becoming the 63-member list that
    # was arithmetically right on the wrong predicate.
    p6b = _copy_phys(_clean_phys())
    p6b.indexed_leading.discard(("dt_probe", "dt_x"))
    p6b.indexed_any.discard(("dt_probe", "dt_x"))
    r6b = rule_r6(_clean_decl(), p6b)
    composed_ok = (not _violating_members(r6b)) and any(
        b.key == "composite_source_member_unindexed" and len(b) for b in r6b.buckets)

    # R7: a cap with the ordering removed.
    cases.append(("R7", "`.limit()` with the `order_by` removed",
                  lambda: rule_r7(_scan_source_text(_CLEAN_R7)),
                  lambda: rule_r7(_scan_source_text(_FAULT_R7))))
    cases.append(("R7-tiebreak", "ordering present but with no id tie-break",
                  lambda: rule_r7(_scan_source_text(_CLEAN_R7)),
                  lambda: rule_r7(_scan_source_text(
                      "def f(db):\n    return db.query(X).order_by(X.name).limit(5).all()\n"))))

    # R8: rename the table off the stage prefixes.
    d8 = _copy_decl(_clean_decl())
    d8.tables["legacy_probe"] = d8.tables.pop("dt_probe")
    cases.append(("R8", "declared table renamed off every stage prefix",
                  lambda: rule_r8(_clean_decl(), _clean_phys()),
                  lambda x=d8: rule_r8(x, _clean_phys())))

    # MISMATCH: make the catalogue disagree with the declaration.
    pm = _copy_phys(_clean_phys())
    pm.columns[("dt_probe", "dt_job")]["data_type"] = "double precision"
    cases.append(("MISMATCH", "catalogue type diverges from the declared type",
                  lambda: rule_mismatch(_clean_decl(), _clean_phys()),
                  lambda p=pm: rule_mismatch(_clean_decl(), p)))

    # MISMATCH cross-table: the INCIDENT's own shape, reproduced. One name, two families.
    dx = _copy_decl(_clean_decl())
    dx.tables["bond_probe"] = {"business_key": "bond_key",
                               "column_types": {"bond_key": "string", "dt_lot": "string"}}
    dx.tables["dt_probe"]["column_types"]["dt_lot"] = "string"
    px = _copy_phys(_clean_phys())
    px.tables.add("bond_probe")
    for (t, c, dt) in (("bond_probe", "bond_key", "character varying"),
                       ("bond_probe", "dt_lot", "character varying"),
                       ("dt_probe", "dt_lot", "character varying")):
        px.columns[(t, c)] = {"data_type": dt, "column_default": None, "is_nullable": True}
    px.bk_tables.add("bond_probe")
    px.unique_bk["bond_probe"] = ("uq_bk_bond_probe", True)
    px.indexed_leading.add(("bond_probe", "bond_key"))
    px.indexed_any.add(("bond_probe", "bond_key"))
    pxf = _copy_phys(px)
    pxf.columns[("dt_probe", "dt_lot")]["data_type"] = "double precision"
    cases.append(("MISMATCH-x", "`dt_lot` is varchar in one table and double precision "
                                "in another - the R1 incident, found with no name list",
                  lambda d=dx, p=px: rule_mismatch(d, p),
                  lambda d=dx, p=pxf: rule_mismatch(d, p)))

    # And the counter-case: varchar vs text is NOT a conflict.
    pxs = _copy_phys(px)
    pxs.columns[("dt_probe", "dt_lot")]["data_type"] = "text"
    r_soft = rule_mismatch(dx, pxs)
    soft_ok = (not _violating_members(r_soft)) and any(
        b.key == "same_column_name_differing_within_one_type_family" and len(b)
        for b in r_soft.buckets)

    # MISMATCH declaration arm: the config alone giving one name two types.
    dxf = _copy_decl(dx)
    dxf.tables["dt_probe"]["column_types"]["dt_lot"] = "number"
    dxf.tables["dt_probe"]["composite_key_source"] = ["dt_job"]  # keep R1 out of it
    cases.append(("MISMATCH-decl", "config declares one column name as two types",
                  lambda d=dx, p=px: rule_mismatch(d, p),
                  lambda d=dxf, p=px: rule_mismatch(d, p)))

    print("=== FAULT INJECTION - each detector must be silent on a clean input and "
          "fire on a planted violation ===")
    failures = []
    for rule, what, clean_fn, fault_fn in cases:
        before = _violating_members(clean_fn())
        after = _violating_members(fault_fn())
        gained = [m for m in after if m not in before]
        ok = not before and bool(gained)
        if not ok:
            failures.append(rule)
        if verbose:
            print(f"  [{'PASS' if ok else 'FAIL'}] {rule:12s} {what}")
            print(f"           clean={len(before)} violations, faulted={len(after)} "
                  f"-> gained {gained[:2] or '(NOTHING - the detector is blind)'}")
    # The counter-cases. These do not check that a detector FIRES - they check that it
    # STAYS SILENT on the rule's own stated exception, which is the other way a detector
    # is useless. A rule that flags every candidate passes fault injection perfectly.
    extra = [
        ("R4-surface", empty_surface_ok and filled_surface_ok,
         "the INFO surface census populates from its input (empty->0, one->1)"),
        ("R1-counter", coord_ok,
         "a numeric identifier holding dense small integers is NOT called a violation"),
        ("R6-counter", composed_ok,
         "an unindexed composite-source-only column is NOT called a violation"),
        ("R5-counter", not any(
            "updated_by" in m for m in _violating_members(rule_r5(
                Declarations({"dt_probe": {"column_types": {"updated_by": "string"}}}),
                _clean_phys()))),
         "`updated_by` is not mistaken for a timestamp by the name heuristic"),
        ("R7-counter", not any(
            "audit_schema_canon" in m for m in _violating_members(
                rule_r7(scan_capped_reads([os.path.dirname(os.path.abspath(__file__))])))),
         "this file's own prose about a 'limit' is not reported as an unordered read"),
        ("MISMATCH-cnt", soft_ok,
         "varchar vs text for one name is NOT called a conflicting-family violation"),
    ]
    for name, ok, what in extra:
        if not ok:
            failures.append(name)
        if verbose:
            print(f"  [{'PASS' if ok else 'FAIL'}] {name:12s} {what}")
    total = len(cases) + len(extra)
    if verbose:
        print(f"\n{total - len(failures)}/{total} detectors proved they fire on a planted "
              f"fault AND stay silent on the rule's own exception. "
              + (f"BLIND: {failures}" if failures else "None are blind."))
    return failures


# =============================================================================
# REPORT
# =============================================================================

_ORDER = {VIOLATION: 0, UNCLASSIFIED: 1, LEGITIMATE: 2, INFO: 3}


def print_rule(res, max_members):
    print(f"\n{'=' * 78}\n{res.rule}  {res.title}\n{'=' * 78}")
    for b in sorted(res.buckets, key=lambda x: (_ORDER[x.verdict], x.key)):
        mark = "!!" if (b.verdict == VIOLATION and len(b)) else "  "
        print(f"{mark} [{b.verdict:13s}] {b.key:48s} {len(b):5d}")
        print(f"        why: {b.why}")
        for m in b.members[:max_members]:
            print(f"          - {m}")
        if len(b) > max_members:
            print(f"          ... {len(b) - max_members} more (use --max-members)")
    if res.uncovered:
        print(f"\n  NOT COVERED BY THIS SECTION:\n    {res.uncovered}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", help="SQLAlchemy URL. Default: the app's configured database.")
    ap.add_argument("--config", help="table_config to judge. Default: table_config.json.sample")
    ap.add_argument("--rule", help="comma separated subset, e.g. R1,R3,MISMATCH")
    ap.add_argument("--self-test", action="store_true", dest="self_test",
                    help="fault injection only. Touches no database.")
    ap.add_argument("--no-db", action="store_true",
                    help="config-only rules; skip every catalogue read.")
    ap.add_argument("--max-members", type=int, default=40)
    ap.add_argument("--json", help="write the full bucket structure here")
    args = ap.parse_args(argv)

    if args.self_test:
        return 1 if self_test() else 0

    import paths
    cfg_path = args.config or paths.config_path("table_config.json.sample")
    if not os.path.exists(cfg_path):
        print(f"[canon] no such config: {cfg_path}")
        return 2
    decl = Declarations.load(
        cfg_path,
        chain_rules_path=paths.config_path("chain_rules.json.sample"),
        overlay_path=paths.config_path("map_overlay_config.json.sample"))

    phys, label = None, "(none)"
    if not args.no_db:
        from sqlalchemy import create_engine, text
        if args.url:
            engine, label = create_engine(args.url), paths.mask_db_password(args.url)
        else:
            from database.database import engine, SQLALCHEMY_DATABASE_URL, DB_URL_SOURCE
            label = f"{paths.mask_db_password(SQLALCHEMY_DATABASE_URL)} ({DB_URL_SOURCE})"
        try:
            with engine.connect() as c:
                c.execute(text("SELECT 1"))
        except Exception as e:
            print(f"[canon] cannot reach the database: {e}")
            return 2
        phys = load_physical(engine, label)

    print("=" * 78)
    print("SCHEMA CANON AUDIT - read-only. No statement in this script writes anything.")
    print(f"  declarations : {cfg_path}  ({len(decl.tables)} tables)")
    print(f"  catalogue    : {label}"
          + (f"  ({len(phys.tables)} tables, {len(phys.columns)} columns)" if phys else ""))
    print(f"  engine-table exception list ({len(ENGINE_TABLES)}), stated in this file "
          f"and printed so it can be argued with:")
    print(f"    {', '.join(sorted(ENGINE_TABLES))}")
    print("  verdicts: VIOLATION breaks the rule / LEGITIMATE is the rule's own stated "
          "exception /")
    print("            INFO is the protected surface, NOT a pass / UNCLASSIFIED means the "
          "evidence does not decide.")
    print("=" * 78)

    default_surface = {}
    if not args.no_db:
        try:
            default_surface = load_default_surface(_read_json(cfg_path) or {})
        except Exception as e:  # a model import failure must not hide the other seven rules
            print(f"[canon] R4 surface unavailable ({type(e).__name__}: {e}) - "
                  f"R4 reports the config half only.")

    # The fill probe runs over R1's candidate set ONLY - identifier columns that are
    # numeric on either side and carry no arithmetic declaration. A dozen bounded
    # aggregates, not a sweep: this must stay cheap enough that nobody is tempted to skip
    # it, because skipping it is what turns R1 back into a name-guessing exercise.
    fill = {}
    if phys is not None:
        ident, quant = identifier_evidence(decl), quantity_evidence(decl)
        numeric_types = {"double precision", "real", "integer", "bigint", "smallint",
                         "numeric"}
        cands = sorted({(t, c) for (t, c) in ident
                        if (t, c) not in quant and t in phys.tables
                        and (t, c) in phys.columns
                        and (decl.column_type(t, c) == "number"
                             or phys.type_of(t, c) in numeric_types)})
        if cands:
            print(f"\n[canon] R1 data probe over {len(cands)} numeric identifier "
                  f"candidate(s) - bounded SELECTs, nothing written.")
            fill = probe_numeric_fill(engine, cands)

    results = [rule_r1(decl, phys, fill), rule_r3(decl), rule_r4(default_surface, decl),
               rule_r5(decl, phys), rule_r7(scan_capped_reads()), rule_r8(decl, phys)]
    if phys is not None:
        results += [rule_r2(decl, phys), rule_r6(decl, phys), rule_mismatch(decl, phys)]
    results.sort(key=lambda r: (r.rule != "MISMATCH", r.rule))

    wanted = {s.strip().upper() for s in args.rule.split(",")} if args.rule else None
    shown = [r for r in results if not wanted or r.rule in wanted]
    for r in shown:
        print_rule(r, args.max_members)

    print(f"\n{'=' * 78}\nSUMMARY - buckets whose verdict is VIOLATION and which have "
          f"members\n{'=' * 78}")
    total = 0
    for r in shown:
        for b in r.violations():
            total += len(b)
            print(f"  {r.rule:9s} {b.key:52s} {len(b):6d}")
    if not total:
        print("  none. ⚠️ Read the UNCLASSIFIED buckets and each section's NOT COVERED "
              "note before calling this clean - several rules are only partly checkable "
              "from a schema.")
    print(f"\n  Re-run with --self-test to see each detector fire on a planted violation. "
          f"An unproven zero is not a zero.")

    if args.json:
        with io.open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"config": cfg_path, "database": label,
                       "engine_tables": sorted(ENGINE_TABLES),
                       "rules": [r.to_dict() for r in shown]}, fh,
                      ensure_ascii=False, indent=1)
        print(f"  json -> {args.json}")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
