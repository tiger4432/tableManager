"""WF/lot/slot notation normalization - a DECLARATION about a column, applied at
QUERY TIME to BOTH SIDES of a comparison. It stores nothing.

[What the declaration means]
    "columns": {"dt_log": {"core_lot": true}}
reads as **"this column's notation is normalized"**. It does NOT read as "this
column derives into that column". The operator touches exactly one file and one
line; there is no second column to declare, no visibility question, and nothing
to backfill.

Consumers apply the SAME fold to BOTH sides of the comparison, in SQL, at query
time. Today the consumer is virtual-join key resolution
(`virtual_join_executor`); the fold expression itself is consumer-agnostic.

[Why the stored derived column was withdrawn - user ruling 2026-08-04]
The first shipped shape (92b8d6f) put the folded value in a physical `<col>_norm`
column. It was rejected for reasons that were measured, not aesthetic:
  - Arming it took THREE layers (`table_config` declares the physical column ->
    `notation_rules` declares the pair -> `display_columns` decides visibility).
    Three layers with a silent failure between them is a config an operator gets
    wrong.
  - The column was write-refused by design: visible and uneditable, riding along
    in CSV extracts, and the moment it entered `display_columns` an incoming file
    with a matching header reached `crud` and the refusal failed the whole batch.
  - To USE it in a virtual join the operator had to name `<col>_norm` in
    `join_key` on BOTH sides. Measured: `dt_log.core_lot` has 15 merge groups and
    `core_wafer_map.core_lot` has zero, so nobody would think to declare it on the
    clean side - and a join folded on ONE side only SILENTLY DROPS MATCHES.
A config that is syntactically fine and wrong in its results is the worst shape
available, so the physical column is gone and the comparison folds instead.

🔴 THE TWO REFUSALS THAT DIED WITH IT, AND WHY THEIR REASONING IS NOT LOST
`would_rewrite_raw` and `key_column` are not oversights of this round. They were
guarding a WRITE, and there is no longer a write:
  - `would_rewrite_raw` refused a declaration whose derived column was the raw
    column itself. Nothing is written now, so nothing can rewrite raw. The
    property it protected ("a wrong folding rule is repaired by editing the rule,
    because the original is still there") is now unconditional and free: the
    stored value is ALWAYS the original, and changing a rule changes only what the
    next query computes. There is nothing to re-derive.
  - `key_column` refused a derived column that was the business key or a member of
    `composite_key_source`, because a derived value must never move a row's
    identity. Nothing is written now, so no identity can move. `business_key_val`
    is computed by `crud._update_row_business_key` from the STORED values and this
    module never touches storage.
Both refusals are therefore vacuous, not relaxed. If a future round ever writes a
folded value anywhere, both must come back, and this paragraph is the record of
what they were for.

[THE RULES - independently switchable, on purpose]
    separator   a RUN of '.', '_', '-' or whitespace  ->  a single '-'  (LOW risk)
    case        ASCII a-z -> A-Z                                        (LOW risk)
    zero_pad    leading zeros stripped        NOT IMPLEMENTED - see below

🔴 `zero_pad` is DECLARED AND REFUSED, not silently ignored. It is the one rule
whose false-merge risk is real (`WF010` and `WF10` both become `WF10`). Setting it
`true` produces a NAMED refusal (`zero_pad_unimplemented`) that surfaces in
`GET /admin/config/resolve`, because a knob that reads as ON and does nothing is
the exact silence this repo keeps paying for.
Note the separate ruling "slot is always int" retires the question for slot - but
only once the column IS declared `number`, and a `number` column cannot be
declared normalized at all (see `_validate_column`): a number has no notation.

[🔴 THE LOAD-BEARING PROPERTY: ONE FOLD, TWO ENGINES, PROVEN EQUAL]
Two spellings of "normalize" is the exact defect class this repository keeps
paying for - it is why the fold was layered on `canonical_key_value` instead of
written beside it. One layer down, the same trap: the fold now has to exist in
Python (the reference, and any Python-side comparand) AND in SQL (what actually
runs). They are scored against each other by `contracts/notation_fold/`, which
runs a vector set through both against a live PostgreSQL and compares for BYTE
equality.

Everything below is shaped by what that comparison MEASURED (2026-08-04,
PostgreSQL 18.3, live, read-only). Do not "simplify" any of it back:

  1. `\\s` / `[[:space:]]` IS NOT PORTABLE AND THE TWO ENGINES DISAGREE.
     Python `\\s` matches 29 codepoints. This server's `[[:space:]]` matches 26 of
     them and adds one Python does not: it MISSES U+001C U+001D U+001E U+001F and
     ADDS U+180E. Worse, that answer is a property of the database's ctype
     (measured `Korean_Korea.949`, provider `c`) - a Linux deployment would answer
     differently again, so the shorthand is not even stable across installs of the
     same product.
     -> The class is therefore ENUMERATED, as `\\uXXXX` escapes, from ONE constant
        that builds both regexes. Neither engine's whitespace table participates.
        `\\uXXXX` inside a bracket expression is understood by PostgreSQL's ARE and
        by Python's `re`, measured identical on 27 vectors.

  2. `upper()` IS NOT `str.upper()`.
     Measured on this server: `upper('straße')` keeps the eszett where Python
     yields 'STRASSE' (a LENGTH change); `upper('ı')` is a no-op where Python
     yields 'I'; `upper('ﬁ')` is a no-op where Python yields 'FI'; `upper('é')` is
     a no-op HERE only because of the database ctype, and would fold on a UTF-8
     locale. Full Unicode case mapping cannot be made to agree.
     -> The case rule folds ASCII a-z ONLY, via `translate()` in SQL and
        `str.translate` in Python, from ONE alphabet pair. Every non-ASCII letter
        is left alone by both engines, identically. This NARROWS what the first
        shipped `fold_notation` did (it called `.upper()`); nothing was stored
        under the old behaviour, so nothing changes underfoot.

  3. `regexp_replace` WITHOUT THE 'g' FLAG REPLACES ONLY THE FIRST MATCH.
     Measured: `regexp_replace('WF.A_B 01', <class>+, '-')` returns 'WF-A_B 01'.
     The flag is not optional and `fold_sql_text` is the only place it is spelled.

  4. THE '-' IS THE LAST CHARACTER OF THE BRACKET EXPRESSION, ALWAYS.
     Anywhere else it is a range operator. It is appended literally, after the
     escaped codepoints, and `_check_pattern_shape` asserts that on import.

[THE TARGET IS '-' AND THAT IS THE POINT]
'_' is the composite map-key join character (`map_overlay.compose_map_id`), so a
value that keeps its '_' is a value that shreds the key it is part of. Folding TO
'_' would defeat the feature.

🔴 **MAP KEYS ARE NOT TOUCHED BY THIS MODULE.** Pointing `canonical_map_key` at a
folded value is a separate, unapproved decision AND a data migration, not a config
flip: `wafer_map_metadata` rows are registered under RAW identities, so existing
`map_id`s would stop matching their meta rows. Nothing here reaches that path.

[PERFORMANCE - stated, not buried]
A folded predicate cannot use a plain b-tree index on the column; it needs a
FUNCTIONAL index on the fold expression. That is why `virtual_join_config`'s
approval gate moves with the fold: a plain UNIQUE index does not even establish
the uniqueness the gate is asking about, because two rows that are distinct raw
('CL-1' and 'CL_1') fold to one value. See `virtual_join_config` for the DDL and
the measured cost.
"""
import json
import logging
import os
import re

logger = logging.getLogger("NotationNorm")

import paths  # single override point (ASSY_DATA_ROOT)

NOTATION_RULES_PATH = paths.config_path("notation_rules.json")

# --- The rule vocabulary -----------------------------------------------------

RULE_SEPARATOR = "separator"
RULE_CASE = "case"
RULE_ZERO_PAD = "zero_pad"

KNOWN_RULES = (RULE_SEPARATOR, RULE_CASE, RULE_ZERO_PAD)

# Rules this module can actually apply. `zero_pad` is deliberately absent - see
# the module docstring. Membership here is what `_normalize_rules` checks, so
# implementing it later is one tuple entry plus one branch in `fold_notation`,
# one branch in `fold_sql_text`, and the refusal disappears on its own.
IMPLEMENTED_RULES = (RULE_SEPARATOR, RULE_CASE)

DEFAULT_RULES = {RULE_SEPARATOR: True, RULE_CASE: True, RULE_ZERO_PAD: False}

# The one form every separator collapses to.
SEPARATOR_TARGET = "-"

# 🔴 THE separator character set. ENUMERATED, never a shorthand class - see item 1
# of the module docstring for the measurement that forces this.
#
# Contents: '.', '_', and every codepoint Python's `\s` matches (measured: exactly
# the 29 codepoints `str.isspace()` reports). '-' is NOT in this tuple; it is
# appended literally as the LAST character of the bracket expression, where it
# cannot be read as a range operator.
SEPARATOR_CODEPOINTS = (
    0x0009, 0x000A, 0x000B, 0x000C, 0x000D,          # tab LF VT FF CR
    0x001C, 0x001D, 0x001E, 0x001F,                  # file/group/record/unit sep
    0x0020,                                          # space
    0x002E,                                          # '.'
    0x005F,                                          # '_'
    0x0085,                                          # NEL
    0x00A0,                                          # NBSP
    0x1680,                                          # OGHAM SPACE MARK
    0x2000, 0x2001, 0x2002, 0x2003, 0x2004, 0x2005,
    0x2006, 0x2007, 0x2008, 0x2009, 0x200A,          # EN QUAD .. HAIR SPACE
    0x2028, 0x2029,                                  # LINE / PARAGRAPH SEPARATOR
    0x202F, 0x205F,                                  # NARROW NBSP, MEDIUM MATH
    0x3000,                                          # IDEOGRAPHIC SPACE
)

# The ONE pattern string. Handed verbatim to `re.compile` and to PostgreSQL's
# `regexp_replace`; there is no second spelling to drift.
SEPARATOR_PATTERN = "[" + "".join(
    "\\u%04x" % cp for cp in SEPARATOR_CODEPOINTS) + SEPARATOR_TARGET + "]+"

# 🔴 THE case mapping. ASCII only, from ONE pair - see item 2 of the docstring.
CASE_SOURCE_ALPHABET = "abcdefghijklmnopqrstuvwxyz"
CASE_TARGET_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _check_pattern_shape():
    """Import-time assertions on the pattern, so a bad edit cannot ship quietly.

    Every one of these corresponds to a way the two engines were measured to
    diverge or to a way a bracket expression silently changes meaning.
    """
    assert SEPARATOR_PATTERN.endswith(SEPARATOR_TARGET + "]+"), (
        "'-' must be the LAST character inside the bracket expression; anywhere "
        "else it is a range operator in both engines")
    assert "'" not in SEPARATOR_PATTERN, (
        "the pattern is interpolated into a single-quoted SQL literal in "
        "`fold_sql_text` and in the index DDL an operator pastes into psql")
    assert SEPARATOR_PATTERN.isascii(), (
        "the pattern must stay ASCII-printable: it appears in a DDL string the "
        "operator reads, and this project's console is cp949")
    assert len(CASE_SOURCE_ALPHABET) == len(CASE_TARGET_ALPHABET), (
        "translate() requires the two alphabets to be the same length")
    assert CASE_SOURCE_ALPHABET.isascii() and CASE_TARGET_ALPHABET.isascii(), (
        "the case fold is ASCII-only BY MEASUREMENT - see docstring item 2")


_check_pattern_shape()

_SEPARATOR_RUN_RE = re.compile(SEPARATOR_PATTERN)
_CASE_TABLE = str.maketrans(CASE_SOURCE_ALPHABET, CASE_TARGET_ALPHABET)

# --- Rejection codes (mirrors virtual_join_config's {scope,subject,detail,code})

CODE_SHAPE = "shape"
CODE_ZERO_PAD_UNIMPLEMENTED = "zero_pad_unimplemented"
CODE_UNKNOWN_RULE = "unknown_rule"
CODE_UNDECLARED = "undeclared"
CODE_NOT_TEXT = "not_text"

SCOPE_FILE = "file"
SCOPE_TABLE = "table"
SCOPE_COLUMN = "column"

# TTL cache, same discipline as `virtual_join_executor.RULES_CACHE_TTL`: the
# explicit invalidation (`reset_cache`) is wired into the web server's reload
# hook, and the TTL is what covers the worker processes that never reach it.
RULES_CACHE_TTL = 5.0
_RULES_CACHE = {"at": 0.0, "by_table": None}


def reset_cache():
    """Drop the declaration cache (web server config-reload hook)."""
    _RULES_CACHE["at"] = 0.0
    _RULES_CACHE["by_table"] = None


# ---------------------------------------------------------------------------
# The fold - Python half
# ---------------------------------------------------------------------------

def fold_notation(text, rules: dict):
    """Apply the ENABLED folding rules to a text value. The REFERENCE spelling.

    `contracts/notation_fold/` scores this against `fold_notation_sql` on a live
    PostgreSQL for byte equality. A change here that is not made there is a
    contract failure, by design.

    Each rule is its own independent branch. Passing `{}` (or all-false) returns
    the input unchanged, which is what makes "prove each rule toggles alone" a
    real test rather than a claim.

    Non-strings pass through untouched: this folds NOTATION, and a value that is
    not text has none. In SQL the same statement is made structurally - a column
    that is not declared `string` cannot be declared normalized at all.
    """
    if not isinstance(text, str):
        return text
    out = text
    if rules.get(RULE_SEPARATOR):
        out = _SEPARATOR_RUN_RE.sub(SEPARATOR_TARGET, out)
    if rules.get(RULE_CASE):
        out = out.translate(_CASE_TABLE)
    return out


def enabled_rule_names(rules: dict) -> list:
    """The enabled, IMPLEMENTED rule names in declaration order."""
    return [n for n in IMPLEMENTED_RULES if (rules or {}).get(n)]


def folds_anything(rules: dict) -> bool:
    """True when at least one implemented rule is on (i.e. the fold is not a no-op)."""
    return bool(enabled_rule_names(rules))


# ---------------------------------------------------------------------------
# The fold - SQL half
# ---------------------------------------------------------------------------

# The name of the scalar function the NON-PostgreSQL fallback calls, and the name
# `install_sqlite_fold` registers. It is deliberately the same name in both
# places so a stack trace on either dialect names the same thing.
SQL_FOLD_FUNCTION = "assy_fold_notation"


def fold_sql_text(inner_sql: str, rules: dict) -> str:
    """PostgreSQL SQL text for the fold, wrapped around an already-text expression.

    🔴 **THE ONLY PLACE THE POSTGRES FOLD IS SPELLED.** The query-time expression
    (`fold_notation_sql`) and the functional-index DDL
    (`virtual_join_config.required_index_ddl`) both come out of here, and they
    HAVE to: PostgreSQL will only use a functional index when the query expression
    matches the index expression, so two spellings would not merely disagree in
    theory - they would silently produce a sequential scan on a 10-million-row
    table while every test still passed.

    `inner_sql` is interpolated, not bound: this text ends up inside a CREATE INDEX
    statement, where a bind parameter has no meaning. Callers pass either a
    compiled column reference or a quoted identifier, never user input.
    """
    out = inner_sql
    if rules.get(RULE_SEPARATOR):
        # 'g' IS LOAD-BEARING - without it only the FIRST run is replaced
        # (measured: 'WF.A_B 01' -> 'WF-A_B 01'). See docstring item 3.
        out = "regexp_replace(%s, '%s', '%s', 'g')" % (
            out, SEPARATOR_PATTERN, SEPARATOR_TARGET)
    if rules.get(RULE_CASE):
        # translate(), never upper() - see docstring item 2 for the measurement.
        out = "translate(%s, '%s', '%s')" % (
            out, CASE_SOURCE_ALPHABET, CASE_TARGET_ALPHABET)
    return out


def _install_notation_fold_construct():
    """The dialect-dispatched fold expression, built once at import.

    A `@compiles` variant rather than a runtime `if dialect == 'postgresql'`, for
    the same reason `crud._install_temporal_text_construct` gives: the expression
    is handed to callers that never see a connection, so letting the compiler
    choose keeps one expression object correct on every bind.
    """
    from sqlalchemy import String as _String
    from sqlalchemy.ext.compiler import compiles
    from sqlalchemy.sql.functions import FunctionElement

    class _NotationFold(FunctionElement):
        type = _String()
        name = SQL_FOLD_FUNCTION
        # 🔴 NOT cacheable-by-inheritance: the enabled rules change the COMPILED
        # SQL but are not clause elements, so a shared cache key would serve a
        # case-folded plan to a separator-only expression. Correctness over the
        # compile-cache hit; the expression is built per query, not per row.
        inherit_cache = False

        def __init__(self, clause, separator: bool, case: bool):
            self.separator = bool(separator)
            self.case = bool(case)
            super().__init__(clause)

        def _rules(self):
            return {RULE_SEPARATOR: self.separator, RULE_CASE: self.case}

    @compiles(_NotationFold, "postgresql")
    def _pg(element, compiler, **kw):
        inner = compiler.process(list(element.clauses)[0], **kw)
        return fold_sql_text(inner, element._rules())

    @compiles(_NotationFold)
    def _default(element, compiler, **kw):
        # 🔴 EVERY OTHER DIALECT, WHICH IN PRACTICE MEANS THE SQLITE TEST SUITE.
        # SQLite has neither `regexp_replace` nor `translate`, so there is no
        # honest way to write the fold in its SQL. It calls a registered scalar
        # function instead (`install_sqlite_fold`), whose body IS `fold_notation`.
        #
        # BE CLEAR ABOUT WHAT THAT DOES AND DOES NOT PROVE. On SQLite the SQL
        # fold and the Python fold are the same code, so a suite test can prove
        # the WIRING (that both sides of a comparison are folded, that an
        # asymmetric declaration still folds both) and CANNOT prove the SPELLING.
        # The spelling is proven by `contracts/notation_fold/` against a real
        # PostgreSQL, and only there.
        inner = compiler.process(list(element.clauses)[0], **kw)
        return "%s(%s, %d, %d)" % (SQL_FOLD_FUNCTION, inner,
                                   1 if element.separator else 0,
                                   1 if element.case else 0)

    return _NotationFold


_NotationFold = _install_notation_fold_construct()


def fold_notation_sql(text_expr, rules: dict):
    """SQLAlchemy expression: `text_expr` folded by the ENABLED rules.

    `text_expr` must already be text. Callers fold a `string`-declared column
    directly - the declaration validator refuses any other declared type, so the
    render-to-text funnel (`crud.column_text_sql`) does not belong here and is
    deliberately NOT applied: wrapping the column in `blank_to_null`'s CASE would
    make the index expression a monster no operator would paste, for a column that
    is already text.

    Returns `text_expr` unchanged when no implemented rule is enabled, so a
    declaration with everything off costs nothing and reads as "not folded"
    everywhere downstream.
    """
    if not folds_anything(rules):
        return text_expr
    return _NotationFold(text_expr, bool(rules.get(RULE_SEPARATOR)),
                         bool(rules.get(RULE_CASE)))


_SQLITE_FOLD_INSTALLED = {"done": False}


def install_sqlite_fold():
    """Register `assy_fold_notation` on every SQLite connection in this process.

    Registered on the Engine CLASS, not on one engine, for exactly the reason
    `db_safety.install_global_test_database_guard` gives: the suite builds its own
    engine in `conftest.py` and contracts build theirs, and a listener attached to
    `database.engine` alone would miss both.

    A no-op for PostgreSQL connections, which is every production connection.
    """
    if _SQLITE_FOLD_INSTALLED["done"]:
        return
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    @event.listens_for(Engine, "connect")
    def _register(dbapi_connection, connection_record):
        create_function = getattr(dbapi_connection, "create_function", None)
        if create_function is None:
            return          # not a sqlite3 connection - nothing to register
        def _fold(value, separator, case):
            return fold_notation(value, {RULE_SEPARATOR: bool(separator),
                                         RULE_CASE: bool(case)})
        try:
            create_function(SQL_FOLD_FUNCTION, 3, _fold)
        except Exception as e:      # pragma: no cover - defensive
            logger.warning("[NotationNorm] could not register %s on this "
                           "connection: %s", SQL_FOLD_FUNCTION, e)

    _SQLITE_FOLD_INSTALLED["done"] = True


# ---------------------------------------------------------------------------
# Declaration loading
# ---------------------------------------------------------------------------

def _record(rejections, scope: str, subject, detail: str, code: str = CODE_SHAPE):
    """One invalid declaration, collected for `GET /admin/config/resolve`.

    Same posture as `enrichment_config._record` and for the same reason - a skip
    that lives only in a daemon log is a skip nobody sees.
    """
    if rejections is None:
        return
    rejections.append({"scope": scope, "subject": subject, "detail": detail,
                       "code": code})


def _normalize_rules(raw, subject, rejections=None) -> dict:
    """A rule-toggle object -> the effective {rule: bool}, refusing by name.

    Unknown names and the unimplemented `zero_pad: true` are REJECTED, not
    dropped quietly. `zero_pad: false` is not a rejection - declaring a rule off
    is a decision on the record, and this repo distinguishes "declared false"
    from "undeclared" deliberately (`enrichment_config.auto_confirm_declared`).
    """
    effective = dict(DEFAULT_RULES)
    if raw is None:
        return effective
    if not isinstance(raw, dict):
        _record(rejections, SCOPE_TABLE, subject,
                "'rules' must be an object {rule_name: true|false}; the default "
                "rule set is used instead", CODE_SHAPE)
        return effective
    for name, on in raw.items():
        if not isinstance(name, str) or name.startswith("_"):
            continue  # '_'-prefixed names are comments, per the repo convention
        if name not in KNOWN_RULES:
            _record(rejections, SCOPE_TABLE, subject,
                    f"unknown rule '{name}'; known rules are "
                    f"{', '.join(KNOWN_RULES)}", CODE_UNKNOWN_RULE)
            continue
        if not isinstance(on, bool):
            _record(rejections, SCOPE_TABLE, subject,
                    f"rule '{name}' must be true or false (got {on!r}); the "
                    f"default is kept", CODE_SHAPE)
            continue
        if on and name not in IMPLEMENTED_RULES:
            _record(rejections, SCOPE_TABLE, subject,
                    f"rule '{name}' is declared but NOT IMPLEMENTED, so it is "
                    f"refused rather than silently ignored. It is the one rule "
                    f"that can merge two different entities ('WF010' and 'WF10' "
                    f"both become 'WF10'), and no census has said whether such a "
                    f"collapse exists here. Run the fold preview first.",
                    CODE_ZERO_PAD_UNIMPLEMENTED)
            effective[name] = False
            continue
        effective[name] = on
    return effective


def _validate_column(table: str, column: str, spec, table_rules: dict,
                     table_cfg: dict, rejections=None):
    """One "this column is normalized" declaration. Returns the spec, or None.

    Accepted forms:
        "core_lot": true                      - normalized, inherited rules
        "core_lot": false                     - explicitly NOT normalized (a
                                                decision on the record; the loader
                                                simply omits it, no rejection)
        "core_lot": {"rules": {...}}          - normalized, per-column rules

    Note what is NOT here any more: there is no `derived` key, because there is no
    derived column. The two refusals that used to live in this function
    (`would_rewrite_raw`, `key_column`) both guarded a WRITE; the module docstring
    records what they were for and why they are vacuous rather than relaxed.
    """
    subject = f"{table}.{column}"
    if spec is False:
        return None                 # declared OFF - a decision, not an error
    if spec is True:
        rules_raw = None
    elif isinstance(spec, dict):
        rules_raw = spec.get("rules")
        if "derived" in spec:
            _record(rejections, SCOPE_COLUMN, subject,
                    "'derived' is no longer a thing: normalization does not "
                    "produce a column any more, it folds BOTH SIDES of a "
                    "comparison at query time. Replace the declaration with "
                    "`true` (or `{\"rules\": {...}}`) and delete the "
                    "'<col>_norm' column from table_config.json if nothing else "
                    "uses it", CODE_SHAPE)
            return None
    else:
        _record(rejections, SCOPE_COLUMN, subject,
                "declaration must be true, false, or an object {rules}",
                CODE_SHAPE)
        return None

    col_types = (table_cfg or {}).get("column_types") or {}
    if table_cfg is not None and column not in col_types:
        _record(rejections, SCOPE_COLUMN, subject,
                f"column '{column}' is not declared in table_config.json for "
                f"'{table}'", CODE_UNDECLARED)
        return None

    # 🔴 A NUMBER HAS NO NOTATION, and this refusal is what keeps the SQL fold
    # short enough to be an index expression. If a non-text column could be
    # declared, the fold would have to sit on top of `crud.column_text_sql`, whose
    # CASE-expression output would make the functional-index DDL unreadable and
    # unmatchable. It is also the right answer on its own terms: separators and
    # case do not occur in a number, and the one rule that WOULD apply to a
    # numeric spelling (`zero_pad`) is refused outright - for a `number` column
    # `canonical_key_value`'s integer parse already made '01' and '1' one value.
    declared = col_types.get(column) if table_cfg is not None else "string"
    if table_cfg is not None and declared != "string":
        _record(rejections, SCOPE_COLUMN, subject,
                f"column '{column}' is declared '{declared}'; only a \"string\" "
                f"column can be normalized. A number has no notation - and for a "
                f"'number' column the integer parse already folds '01' and '1' "
                f"into one value", CODE_NOT_TEXT)
        return None

    rules = _normalize_rules(rules_raw, subject, rejections) if rules_raw is not None \
        else dict(table_rules)
    return {"table": table, "column": column, "rules": rules}


def validate_notation_rules(raw_config: dict, known_tables: dict = None,
                            rejections: list = None) -> dict:
    """Config dict -> `{table: {column: {table, column, rules}}}`.

    `known_tables` is `crud.TABLE_CONFIG`. Passing None skips the table/column
    existence and declared-type checks (pure shape validation), matching
    `enrichment_config._validate_rule`.
    """
    by_table = {}
    if not isinstance(raw_config, dict):
        _record(rejections, SCOPE_FILE, None,
                "notation_rules.json must be an object; the whole file was "
                "ignored and NO column is normalized", CODE_SHAPE)
        return by_table

    file_rules = _normalize_rules(raw_config.get("rules"), None, rejections)

    columns = raw_config.get("columns")
    if columns is None:
        return by_table
    if not isinstance(columns, dict):
        _record(rejections, SCOPE_FILE, None,
                "'columns' must be an object {table: {column: true}}", CODE_SHAPE)
        return by_table

    for table, decls in columns.items():
        if not isinstance(table, str) or table.startswith("_"):
            continue  # '_'-prefixed names are comments, per the repo convention
        if not isinstance(decls, dict):
            _record(rejections, SCOPE_TABLE, table,
                    "declaration must be an object {column: true}", CODE_SHAPE)
            continue
        table_rules = dict(file_rules)
        if "rules" in decls:
            table_rules = _normalize_rules(decls.get("rules"), table, rejections)
        table_cfg = None
        if known_tables is not None:
            table_cfg = known_tables.get(table)
            if table_cfg is None:
                _record(rejections, SCOPE_TABLE, table,
                        f"table '{table}' is not registered in table_config.json",
                        CODE_UNDECLARED)
                continue
        for column, spec in decls.items():
            if column == "rules" or column.startswith("_"):
                continue
            normalized = _validate_column(table, column, spec, table_rules,
                                          table_cfg, rejections)
            if normalized is not None:
                by_table.setdefault(table, {})[column] = normalized
    return by_table


def load_notation_rules(path: str = None, known_tables: dict = None,
                        rejections: list = None) -> dict:
    """Read + validate notation_rules.json. A missing file is NOT a rejection."""
    rules_path = path or NOTATION_RULES_PATH
    if not os.path.exists(rules_path):
        return {}
    try:
        with open(rules_path, "r", encoding="utf-8") as f:
            raw_config = json.load(f)
    except Exception as e:
        logger.error("Failed to load %s: %s", rules_path, e)
        _record(rejections, SCOPE_FILE, None,
                f"notation_rules.json could not be read "
                f"({e.__class__.__name__}) - NO column is normalized", CODE_SHAPE)
        return {}
    return validate_notation_rules(raw_config, known_tables=known_tables,
                                   rejections=rejections)


def normalized_by_table() -> dict:
    """`{table: {column: spec}}`, TTL-cached. Every consumer's only entry."""
    import time

    now = time.monotonic()
    cached = _RULES_CACHE["by_table"]
    if cached is not None and (now - _RULES_CACHE["at"]) < RULES_CACHE_TTL:
        return cached
    try:
        from database import crud
        loaded = load_notation_rules(known_tables=crud.TABLE_CONFIG)
    except Exception as e:
        # An unreadable declaration means NO column is normalized. Failing the
        # read here would turn a config problem into an outage, and the safe
        # direction is the one that compares raw values - the behaviour every
        # join had before this feature existed.
        logger.error("[NotationNorm] declarations unreadable, no column is "
                     "normalized: %s", e)
        loaded = {}
    _RULES_CACHE["by_table"] = loaded
    _RULES_CACHE["at"] = now
    return loaded


def rules_for_column(table: str, column: str):
    """The effective rule set for `table.column`, or None when not declared."""
    spec = (normalized_by_table().get(table) or {}).get(column)
    return dict(spec["rules"]) if spec else None


def is_normalized(table: str, column: str) -> bool:
    """True when `table.column` is declared normalized AND something folds."""
    return folds_anything(rules_for_column(table, column) or {})


def join_pair_rules(left_table: str, left_column: str,
                    right_table: str, right_column: str):
    """The rule set BOTH sides of one join-key comparison must be folded with.

    Returns None when neither side is declared (compare raw, as before).

    🔴 **"EITHER SIDE DECLARED" MEANS BOTH SIDES FOLDED.** This is the whole
    reason the feature was redesigned. Measured 2026-08-04: `dt_log.core_lot` has
    15 merge groups and `core_wafer_map.core_lot` has zero, so an operator looking
    at the clean side has no reason to declare anything there - and a join folded
    on one side only does not merely fail to help, it SILENTLY DROPS matches that
    the unfolded join was already making ('CL-1' folded to 'CL-1' compared against
    an unfolded 'CL_1'). There is deliberately no argument, no flag and no call
    shape by which a caller could fold one side.

    When BOTH sides are declared with DIFFERENT rules, the effective set is the
    UNION. The fold is a property of the COMPARISON, not of a column: "this
    column's notation is normalized with rules R" is a statement that at least R
    must be folded when this column is compared, and the union is the smallest
    set satisfying both declarations. Union is also the only monotone choice -
    it can only merge more, never drop a match - and the effective set is
    reported per declaration by `/admin/config/virtual-join/verify`, so it is
    visible rather than inferred.
    """
    left = rules_for_column(left_table, left_column)
    right = rules_for_column(right_table, right_column)
    if left is None and right is None:
        return None
    merged = {}
    for name in KNOWN_RULES:
        merged[name] = bool((left or {}).get(name)) or bool((right or {}).get(name))
    return merged if folds_anything(merged) else None


# ---------------------------------------------------------------------------
# The fold preview - the false-merge check, which is the question that matters
# ---------------------------------------------------------------------------

# How many distinct RAW spellings the preview will look at. The grouping query is
# a full scan by construction (a folded expression has no plain index), so the
# cap is what keeps an operator-triggered admin call from being a 10-million-row
# surprise. It caps the GROUPS, not the rows - the counts stay exact for the
# groups returned, and `truncated` says when the cap bit.
PREVIEW_GROUP_LIMIT = 500
PREVIEW_VARIANT_LIMIT = 20


def fold_preview(db, table: str, column: str, rules: dict = None,
                 limit: int = PREVIEW_GROUP_LIMIT) -> dict:
    """What this column's declared fold ACTUALLY does to the values in the table.

    [Why this exists - it is the payment for a column that used to be inspectable]
    The withdrawn design put the folded value in the grid, where an operator could
    eyeball it. That is a real loss and it is paid for here rather than absorbed.
    The answer this returns is the one that actually matters:

        MERGE GROUPS - one folded value reached by MORE THAN ONE raw spelling,
        with the raw variants listed.

    That is the false-merge check: "did my rule merge two things that are not the
    same?" A list of raw->folded pairs cannot answer it, because the pairs that
    matter are the ones that COLLIDE, and a per-row listing buries them.

    🔴 **COMPUTED ENTIRELY IN SQL, THROUGH `fold_notation_sql`.** Not in Python
    over fetched rows. If the preview folded in Python it would be showing the
    operator an answer that the JOIN does not use, which is the same
    two-spellings defect one screen further out - and it would be the screen the
    operator TRUSTS.

    Read-only: one grouping query, no write, no DDL.
    """
    from sqlalchemy import func
    from database import models

    model = models.DYNAMIC_TABLES.get(table)
    if model is None:
        raise ValueError(f"table '{table}' has no initialized model")
    col = getattr(model, column, None)
    if col is None:
        raise ValueError(f"'{table}' has no column '{column}'")
    if rules is None:
        rules = rules_for_column(table, column)
    if rules is None:
        return {"table": table, "column": column, "declared": False, "rules": None,
                "folds": False, "groups": [], "merge_groups": [],
                "distinct_raw": 0, "distinct_folded": 0, "truncated": False}

    folded = fold_notation_sql(col, rules)
    rows = (db.query(col.label("raw"), folded.label("folded"),
                     func.count().label("n"))
            .filter(col.isnot(None))
            .group_by(col, folded)
            .order_by(func.count().desc())
            .limit(limit + 1).all())
    truncated = len(rows) > limit
    rows = rows[:limit]

    by_folded = {}
    for raw, fold_val, n in rows:
        entry = by_folded.setdefault(fold_val, {"folded": fold_val, "variants": [],
                                                "rows": 0})
        entry["variants"].append({"raw": raw, "rows": int(n)})
        entry["rows"] += int(n)

    groups = sorted(by_folded.values(), key=lambda g: (-len(g["variants"]), -g["rows"]))
    merge_groups = [
        {"folded": g["folded"], "raw_count": len(g["variants"]), "rows": g["rows"],
         "variants": g["variants"][:PREVIEW_VARIANT_LIMIT],
         "variants_truncated": len(g["variants"]) > PREVIEW_VARIANT_LIMIT}
        for g in groups if len(g["variants"]) > 1
    ]
    return {
        "table": table, "column": column, "declared": True,
        "rules": dict(rules), "folds": folds_anything(rules),
        "distinct_raw": sum(len(g["variants"]) for g in groups),
        "distinct_folded": len(groups),
        "merge_groups": merge_groups,
        # The plain raw->folded listing stays available, capped, for the operator
        # who wants to eyeball spellings that did NOT merge.
        "groups": [{"folded": g["folded"], "rows": g["rows"],
                    "variants": g["variants"][:PREVIEW_VARIANT_LIMIT]}
                   for g in groups],
        "truncated": truncated,
        "group_limit": limit,
    }


def declared_previews(db, limit: int = PREVIEW_GROUP_LIMIT) -> list:
    """`fold_preview` for every declared column. One entry per declaration.

    A table whose model is not initialized yields an `error` entry rather than
    taking the whole report down - the same posture `config_resolve_report` takes
    per domain.
    """
    out = []
    for table, specs in sorted(normalized_by_table().items()):
        for column, spec in sorted(specs.items()):
            try:
                out.append(fold_preview(db, table, column, spec["rules"], limit))
            except Exception as e:
                logger.error("[NotationNorm] preview failed for %s.%s: %s",
                             table, column, e)
                out.append({"table": table, "column": column, "declared": True,
                            "rules": dict(spec["rules"]),
                            "error": f"{e.__class__.__name__}: {e}"})
    return out
