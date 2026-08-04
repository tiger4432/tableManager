-- =====================================================================
-- WF / lot / slot spelling census -- READ ONLY
--
-- Purpose: decide, with numbers, which notation-folding rules are safe to
-- turn on before we derive normalized columns (board request 7, 2026-08-04:
-- "WF.01, WF-01 etc. are mixed, filters and JOINs suffer everywhere").
--
-- SAFETY
--   * Every statement below is a single SELECT. No DDL, no DML, no temp
--     tables, no transaction state carried between steps.
--   * Each STEP is independently runnable. If one fails, the others still
--     work -- paste them one at a time.
--   * Nothing here writes to the database. Safe to run on production.
--
-- WHY IT IS BUILT THIS WAY
--   A previous cleanup script used a temp table and the client halted at the
--   first error, leaving the rest unrun. These statements share no state.
--
-- THE THREE CANDIDATE RULES (kept separate on purpose -- do not bundle)
--   R1 separator    '.' '_' whitespace  ->  '-'      (low risk)
--   R2 case         lower  ->  upper                 (low risk)
--   R3 zero-pad     leading zeros in each number run stripped   (HIGH RISK)
--
--   R3 is the one that can merge two genuinely different entities:
--   'WF010' and 'WF10' both become 'WF10'. STEP 2 exists to show you every
--   such collapse so a human who knows the fab can judge it.
--
-- HOW TO READ THE RESULT
--   A rule is worth turning on when it REDUCES the distinct spelling count
--   (STEP 1) and every collapse group it creates (STEP 2) is obviously the
--   same physical thing. A rule that merges two different things is worse
--   than no rule at all.
-- =====================================================================


-- ---------------------------------------------------------------------
-- STEP 0 -- which columns will be measured
--
-- Run this first and eyeball the list. If it misses a column that matters,
-- or includes noise, edit the two regexes at the bottom of this query and
-- apply the same edit to STEP 1 and STEP 2.
-- ---------------------------------------------------------------------
SELECT c.table_schema AS sch,
       c.table_name   AS tbl,
       c.column_name  AS col,
       c.data_type
FROM information_schema.columns c
JOIN information_schema.tables t
  ON  t.table_schema = c.table_schema
  AND t.table_name   = c.table_name
  AND t.table_type   = 'BASE TABLE'
WHERE c.table_schema NOT IN ('pg_catalog', 'information_schema')
  AND c.data_type IN ('character varying', 'text', 'character')
  AND c.column_name ~* '(lot|slot|wafer|wf|job)'
  AND c.column_name !~* '(time|date|_at$|comment|desc|note|reason|status|owner|user|source|path|file)'
ORDER BY 1, 2, 3;


-- ---------------------------------------------------------------------
-- STEP 1 -- spelling census: how much does each rule fold?
--
-- One row per column. Compare n_raw against n_r1 / n_r2 / n_r3:
--   n_raw  = distinct spellings today
--   n_r1   = distinct after separator unification
--   n_r2   = distinct after case fold
--   n_r3   = distinct after zero-pad strip
--   n_r12  = R1 + R2 together   (the "safe pair")
--   n_r123 = all three          (only if STEP 2 clears R3)
--
-- A big gap between n_raw and n_r12 is the friction you are feeling.
--
-- RUNTIME: this scans every listed column in full. On large tables
-- (bonding_map is ~1.76M rows) expect minutes. It is read-only -- let it run.
-- To measure one schema at a time, add a table_schema filter in the CTE.
-- ---------------------------------------------------------------------
WITH cand AS (
    SELECT c.table_schema AS sch, c.table_name AS tbl, c.column_name AS col
    FROM information_schema.columns c
    JOIN information_schema.tables t
      ON  t.table_schema = c.table_schema
      AND t.table_name   = c.table_name
      AND t.table_type   = 'BASE TABLE'
    WHERE c.table_schema NOT IN ('pg_catalog', 'information_schema')
      AND c.data_type IN ('character varying', 'text', 'character')
      AND c.column_name ~* '(lot|slot|wafer|wf|job)'
      AND c.column_name !~* '(time|date|_at$|comment|desc|note|reason|status|owner|user|source|path|file)'
)
SELECT cand.sch, cand.tbl, cand.col,
       x.n_rows, x.n_raw,
       x.n_r1, x.n_r2, x.n_r3, x.n_r12, x.n_r123,
       (x.n_raw - x.n_r12) AS gain_safe_pair,
       (x.n_r12 - x.n_r123) AS extra_from_zero_pad
FROM cand
CROSS JOIN LATERAL (
    SELECT query_to_xml(
        format($q$
            SELECT count(*)::bigint                                            AS n_rows,
                   count(DISTINCT v)::bigint                                   AS n_raw,
                   count(DISTINCT regexp_replace(v,'[._[:space:]]+','-','g'))::bigint AS n_r1,
                   count(DISTINCT upper(v))::bigint                            AS n_r2,
                   count(DISTINCT regexp_replace(v,'(^|[^0-9])0+([0-9])','\1\2','g'))::bigint AS n_r3,
                   count(DISTINCT upper(regexp_replace(v,'[._[:space:]]+','-','g')))::bigint  AS n_r12,
                   count(DISTINCT regexp_replace(upper(regexp_replace(v,'[._[:space:]]+','-','g')),'(^|[^0-9])0+([0-9])','\1\2','g'))::bigint AS n_r123
            FROM (SELECT btrim(%I::text) AS v FROM %I.%I) s
            WHERE v IS NOT NULL AND v <> ''
        $q$, cand.col, cand.sch, cand.tbl),
        false, true, '') AS xd
) q
CROSS JOIN LATERAL
    XMLTABLE('/table/row' PASSING q.xd
        COLUMNS n_rows  bigint PATH 'n_rows',
                n_raw   bigint PATH 'n_raw',
                n_r1    bigint PATH 'n_r1',
                n_r2    bigint PATH 'n_r2',
                n_r3    bigint PATH 'n_r3',
                n_r12   bigint PATH 'n_r12',
                n_r123  bigint PATH 'n_r123') AS x
WHERE x.n_raw > 0
ORDER BY (x.n_raw - x.n_r123) DESC, cand.sch, cand.tbl, cand.col;


-- ---------------------------------------------------------------------
-- STEP 2 -- THE DECIDING ARTIFACT: every collapse group, per rule
--
-- This is the false-merge check. Each row is a set of raw spellings that a
-- rule folds into ONE value. Read the `variants` column and ask:
--
--     "Are these the same physical wafer / lot / slot?"
--
--   YES for every group under a rule  ->  that rule is safe to turn on
--   NO for even one group             ->  that rule stays off, or gets
--                                         narrowed (e.g. zero-pad only when
--                                         the numeric run has a fixed width)
--
-- Look hardest at rule = 'R3_pad'. Expect groups like {S1, S01, S001}
-- (probably fine) but also {WF10, WF010} (probably NOT fine).
--
-- Filter while reading, e.g.:   ... WHERE rule = 'R3_pad'
-- ---------------------------------------------------------------------
WITH cand AS (
    SELECT c.table_schema AS sch, c.table_name AS tbl, c.column_name AS col
    FROM information_schema.columns c
    JOIN information_schema.tables t
      ON  t.table_schema = c.table_schema
      AND t.table_name   = c.table_name
      AND t.table_type   = 'BASE TABLE'
    WHERE c.table_schema NOT IN ('pg_catalog', 'information_schema')
      AND c.data_type IN ('character varying', 'text', 'character')
      AND c.column_name ~* '(lot|slot|wafer|wf|job)'
      AND c.column_name !~* '(time|date|_at$|comment|desc|note|reason|status|owner|user|source|path|file)'
)
SELECT cand.sch, cand.tbl, cand.col,
       x.rule, x.folded, x.n_variants, x.n_rows, x.variants
FROM cand
CROSS JOIN LATERAL (
    SELECT query_to_xml(
        format($q$
            SELECT r.rule::text                                   AS rule,
                   r.folded::text                                 AS folded,
                   count(*)::bigint                               AS n_variants,
                   sum(d.n)::bigint                               AS n_rows,
                   string_agg(d.v, ' | ' ORDER BY d.v)::text      AS variants
            FROM (
                SELECT v, count(*) AS n
                FROM (SELECT btrim(%I::text) AS v FROM %I.%I) s
                WHERE v IS NOT NULL AND v <> ''
                GROUP BY v
            ) d
            CROSS JOIN LATERAL (VALUES
                ('R1_sep',   regexp_replace(d.v,'[._[:space:]]+','-','g')),
                ('R2_case',  upper(d.v)),
                ('R3_pad',   regexp_replace(d.v,'(^|[^0-9])0+([0-9])','\1\2','g')),
                ('R12_safe', upper(regexp_replace(d.v,'[._[:space:]]+','-','g'))),
                ('R123_all', regexp_replace(upper(regexp_replace(d.v,'[._[:space:]]+','-','g')),'(^|[^0-9])0+([0-9])','\1\2','g'))
            ) AS r(rule, folded)
            GROUP BY r.rule, r.folded
            HAVING count(*) > 1
        $q$, cand.col, cand.sch, cand.tbl),
        false, true, '') AS xd
) q
CROSS JOIN LATERAL
    XMLTABLE('/table/row' PASSING q.xd
        COLUMNS rule       text   PATH 'rule',
                folded     text   PATH 'folded',
                n_variants bigint PATH 'n_variants',
                n_rows     bigint PATH 'n_rows',
                variants   text   PATH 'variants') AS x
ORDER BY x.rule, x.n_variants DESC, x.n_rows DESC;


-- ---------------------------------------------------------------------
-- STEP 3 -- join delta: how many more rows would actually match?
--
-- STEP 1 counts spellings; this counts MATCHES, which is what a filter or a
-- virtual join actually delivers. Fill in one pair of columns that are
-- supposed to join and run it. Repeat per pair you care about.
--
-- >>> EDIT THE FOUR PLACEHOLDERS ON THE NEXT TWO LINES <<<
-- ---------------------------------------------------------------------
WITH
lhs AS (SELECT DISTINCT btrim(core_lot::text)  AS v FROM assy_qa.dt_log),          -- <<< left  table.column
rhs AS (SELECT DISTINCT btrim(core_lot::text)  AS v FROM assy_qa.core_wafer_map),  -- <<< right table.column
l AS (SELECT v FROM lhs WHERE v IS NOT NULL AND v <> ''),
r AS (SELECT v FROM rhs WHERE v IS NOT NULL AND v <> '')
SELECT 'raw'      AS rule, count(*) AS matched_keys FROM (SELECT v FROM l INTERSECT SELECT v FROM r) z
UNION ALL
SELECT 'R12_safe', count(*) FROM (
    SELECT upper(regexp_replace(v,'[._[:space:]]+','-','g')) FROM l
    INTERSECT
    SELECT upper(regexp_replace(v,'[._[:space:]]+','-','g')) FROM r) z
UNION ALL
SELECT 'R123_all', count(*) FROM (
    SELECT regexp_replace(upper(regexp_replace(v,'[._[:space:]]+','-','g')),'(^|[^0-9])0+([0-9])','\1\2','g') FROM l
    INTERSECT
    SELECT regexp_replace(upper(regexp_replace(v,'[._[:space:]]+','-','g')),'(^|[^0-9])0+([0-9])','\1\2','g') FROM r) z;


-- =====================================================================
-- WHAT HAPPENS WITH THE ANSWER
--
--   * The rules that clear STEP 2 get applied as a DERIVED column
--     (`<col>_norm`) produced by a chain rule. The raw column is never
--     rewritten -- it stays the record of what the source actually said,
--     and re-deriving is how a rule change is corrected.
--   * Joins, filters, map keys and graph keys read the derived column.
--     Screens keep showing the raw value.
--   * The folding itself reuses the existing `canonical_key_value` (7b)
--     convention. We are not writing a second spelling of "normalize" --
--     that convention exists precisely because of the LOT_01 vs 1 incident.
-- =====================================================================
