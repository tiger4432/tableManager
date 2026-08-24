"""The finding-kind registry: what a defect kind IS, as data rather than as a branch.

🔴 WHY THIS FILE EXISTS AT ALL (product owner, 2026-08-14, `SCENARIO_CONSOLE_BRIEF`
§0-bis 3 and the [일반화] block of §0)
------------------------------------------------------------------------------------
> "코드에 기본값 아닌 `finding_kind='void'` 하드코딩이 보이면 일반화가 소실된 것."

Void is ONE example. The case-control console has to give every observed defect kind the
same analysis, so the kind has to be a PARAMETER everywhere and a literal nowhere. The
only way that survives contact with a second author is for the kind's definition to be a
lookup rather than a condition: this module is that lookup, and `DEFAULT_KIND` is the one
place the word "void" is allowed to appear as a value (a default parameter, which is what
the ruling explicitly permits).

WHAT A KIND DECLARES, AND WHY EACH FIELD IS LOAD-BEARING
---------------------------------------------------------
``observed_by``
    The `inspection_run.method` values that LOOK FOR this kind. **This is the
    denominator's definition**, and it is the whole reason `inspection_run` exists
    (`table_config.json`: "'3 voids' means nothing without 'out of how many scans'").
    A kind with an EMPTY list has no denominator - an incidental observation nobody
    systematically scans for - and the honest answer for it is "분모 없음 - 대조 불가",
    not a rate computed against whatever rows happened to be nearby. `has_denominator`
    is how a caller asks, and it is a declaration rather than an accident: a kind
    somebody forgets to give methods to renders the refusal instead of a wrong number.

``observation_table``
    Where this kind's observations live. Two kinds may not share one table today, but
    nothing here depends on that - the console reads the name from here.

``extent_columns``
    The geometry columns that say HOW BIG. Named, never assumed, and never reduced to a
    stored grade: `void_obs`'s config comment is explicit that pass/fail is
    `area > threshold` with the threshold living in a recipe, so a stored verdict makes
    history un-re-judgeable. The console shows extent; it does not show a verdict.

🔴 THE THREE-WAY SPLIT IS SPELLED ONCE, HERE
---------------------------------------------
`population_ctes` is not a convenience. The brief's rule is that a package which was
NEVER SCANNED must not be able to drift into the clean side, and the way that rule gets
broken is always the same: somebody writes the control population as "no finding row",
which is true of **280,001** positions on this box that nobody has ever looked at
(MEASURED 2026-08-14 for kind `void`, against 46,899 found and 28,101 clean-scanned; an
earlier draft of this docstring said 277,500, which was arithmetic on the fixture size and
not a count -- it omitted the ~2,501 distinct positions contributed by the 5,296
non-synthetic `bonding_log` rows). So the control set is defined as ``scanned MINUS found``
and never as ``NOT EXISTS(finding)``.

⚠️ **AND THERE IS A SECOND SPELLING, LANDED, WHICH THIS FILE DOES NOT OWN.**
`server/ledger_siblings.py` assembles its own `runs` / `scanned` / `found` rather than
calling `population_ctes`, and it has a real reason: the console scopes runs to a time
window and must define `found` THROUGH those windowed runs to keep `found ⊆ scanned`.
So the honest statement is not "one spelling" - it is: **two spellings exist, they agree
today, and nothing detects the day they stop.** Do not merge them without deciding where
the window belongs; do not repeat "one spelling" from this docstring without grepping for
callers first.
"""
from __future__ import annotations

import json
import os
import threading

#: The kind a caller gets when it does not name one. 🔴 This is the ONE permitted
#: appearance of a kind name as a literal in code - the ruling calls out "기본값이지
#: 특례가 아니다" - and it is a default parameter value, not a condition.
#: 🔴 WHERE A PROJECTED FIELD LIVES, STATED ONCE. Measured 2026-08-24 on `observed`:
#:
#:      finding_kind   top level 11,588   ·  under `qualifiers` «103,841»
#:      run_uid        top level 11,588   ·  under `qualifiers` «103,841»
#:      method · class · map_id           ·  under `qualifiers` «0»  -- simply ABSENT on v5
#:                                           atoms, so a fallback cannot help them and this
#:                                           tuple deliberately does NOT list them
#:
#: The v5 declaration puts the value at the top and everything else beside it, so a reader
#: that looks only at the top level counts the v1 remnant and misses every new atom. That is
#: how the void trend read 0% while its map read 50%: 15 atoms answered and 103,841 did not.
#:
#: 🔴 ONE STATEMENT, TWO LANGUAGES. `payload_field` is for Python and `payload_field_sql` for
#: a query, and they are here together so the rule cannot drift between them. Eight copies of
#: 「finding_kind is at the top level」 is what produced this incident -- one was repaired in
#: the morning and the rest stayed.
QUALIFIED_FIELDS = ("finding_kind", "run_uid")


def payload_field(payload, name):
    """The field from the payload top level, else from `qualifiers`, else None."""
    if not isinstance(payload, dict):
        return None
    if name in payload:
        return payload.get(name)
    return (payload.get("qualifiers") or {}).get(name)


def payload_field_sql(payload_expr, name):
    """The same rule as a SQL expression over `payload_expr` (e.g. `e.object_payload`).

    Returns NULL when neither place carries it, so callers keep whatever COALESCE or NULLIF
    they already wrap it in -- this changes WHERE the value is read, not what absence means.
    """
    return (f"COALESCE(NULLIF({payload_expr}->>'{name}', ''), "
            f"NULLIF({payload_expr}->'qualifiers'->>'{name}', ''))")


DEFAULT_KIND = "void"

#: The universe of packages, for the "never scanned" third. A package is a bonded
#: position, addressed the way `void_obs` addresses it: (base wafer, base x, base y).
PACKAGE_TABLE = "bonding_log"
PACKAGE_COLUMNS = ("base_id", "bx", "by")

RUN_TABLE = "inspection_run"

#: Declared kinds. Data, and overridable by `config/finding_kinds.json` (config-over-
#: hardcode) so a site that names its kinds differently does not need a code change.
DEFAULT_FINDING_KINDS = {
    "void": {
        "label": "보이드",
        "observed_by": ["sat"],
        "observation_table": "void_obs",
        "extent_columns": ["radius_x", "radius_y"],
        "unit_column": "unit",
        # 🔴 EMPTY, DECLARED OUT LOUD - and that is this file's own `observed_by` rule
        # applied one field over. MEASURED 2026-08-14: `void_obs` has no class column at
        # all, so the SAT tool utters no classification and the console renders no class
        # axis for a void. Leaving the field absent would have said the same thing to
        # `classes()` (it reads with `.get`) and a DIFFERENT thing to a reader: "nobody
        # has decided yet" rather than "the source says nothing". §6-quater names
        # 계면/벌크/에지 as a void's eventual set, so this is a real open question and the
        # empty list is where the answer will land - beside the tool that starts uttering
        # one.
        "classes": [],
    },
    "delam": {
        # Interface delamination. A DIFFERENT method looks for it, which is what makes
        # the denominator swing when the console's kind parameter changes - if both kinds
        # shared one method the generalization would be untested, because every kind
        # would be counted against the same rows.
        "label": "박리",
        "observed_by": ["scat"],
        "observation_table": "delam_obs",
        "extent_columns": ["extent_x", "extent_y"],
        "unit_column": "unit",
        # 🔴 THE CLOSED CLASS SET, AND IT NOW HAS A SECOND ENFORCEMENT POINT.
        # §6-quater: a defect's class is a CLAIM the tool utters, and the values it may
        # use are per-kind, closed and add-only. These two are MEASURED from the source
        # (`SELECT interface, count(*) FROM delam_obs GROUP BY 1` on 2026-08-14:
        # die-to-substrate 5,332 / die-to-die 5,089), not invented here.
        #
        # Until ruling R-2026-08-14-D this list only made a console axis appear. It is now
        # also what the ledger's observation translator screens `delam_obs.interface`
        # against: a value outside it refuses the atom BY NAME rather than putting an
        # unreviewed word in the ledger. That is the check §6-quater asks for - "두 장비가
        # 같은 class 이름을 쓰면 프레임 검사 먼저" - and it only happens if a new spelling
        # cannot arrive quietly.
        "classes": ["die-to-die", "die-to-substrate"],
    },
}

CONFIG_FILENAME = "finding_kinds.json"

_lock = threading.Lock()
_cache = None


class FindingKindError(ValueError):
    """The registry, or a kind asked for, is unusable. Refused by name."""


def _config_path():
    try:
        import paths
        return os.path.join(paths.CONFIG_DIR, CONFIG_FILENAME)
    except Exception:
        # Two levels up: this module lives in `server/ledger_api/`, the config tree
        # is `server/config/`. One `dirname` would name a directory that never exists.
        server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(server_dir, "config", CONFIG_FILENAME)


def load(force_reload: bool = False) -> dict:
    """The registry. Read once, cached, overridable by config file."""
    global _cache
    with _lock:
        if _cache is not None and not force_reload:
            return _cache
        merged = {name: dict(spec) for name, spec in DEFAULT_FINDING_KINDS.items()}
        path = _config_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    declared = json.load(handle)
            except Exception as exc:
                raise FindingKindError(f"{CONFIG_FILENAME} is not readable JSON: {exc}")
            if not isinstance(declared, dict):
                raise FindingKindError(f"{CONFIG_FILENAME} must be a JSON object")
            for name, spec in declared.items():
                if not isinstance(spec, dict):
                    raise FindingKindError(f"{CONFIG_FILENAME}.{name} must be an object")
                merged.setdefault(name, {}).update(spec)
        for name, spec in merged.items():
            if "active" in spec and not isinstance(spec["active"], bool):
                raise FindingKindError(
                    f"finding kind {name!r} declares `active` that is not boolean")
            for field in ("label", "observation_table", "extent_columns"):
                if not spec.get(field):
                    raise FindingKindError(
                        f"finding kind {name!r} declares no {field!r}. A kind whose "
                        f"observations have no home cannot be counted, and a silent "
                        f"default would count somebody else's rows.")
            if "observed_by" not in spec:
                raise FindingKindError(
                    f"finding kind {name!r} does not declare `observed_by`. An ABSENT "
                    f"list and an EMPTY one mean different things - empty declares 'no "
                    f"systematic scan looks for this, so there is no denominator', which "
                    f"is a decision somebody has to make explicitly.")
            declared_classes = spec.get("classes")
            if declared_classes is not None and (
                    not isinstance(declared_classes, (list, tuple))
                    or any(not isinstance(c, str) or not c.strip()
                           for c in declared_classes)):
                raise FindingKindError(
                    f"finding kind {name!r} declares `classes` that is not a list of "
                    f"non-empty names. The class set is CLOSED and add-only, so a "
                    f"malformed declaration has to be refused rather than half-read - "
                    f"a screen that offers a blank class as a slice axis asks a "
                    f"question nobody can answer.")
        _cache = merged
        return merged


def set_registry(registry):
    """Install a registry for this process. Tests use it; nothing else should."""
    global _cache
    with _lock:
        _cache = ({name: dict(spec) for name, spec in DEFAULT_FINDING_KINDS.items()}
                  if registry is None else
                  {name: dict(spec) for name, spec in registry.items()})
        return _cache


def kinds():
    """Every declared kind name, sorted. What the console's selector is built from."""
    return sorted(load())


def spec(kind: str = DEFAULT_KIND) -> dict:
    """One kind's declaration. An undeclared kind is refused BY NAME, never defaulted.

    Falling back to `DEFAULT_KIND` here would be the worst possible kindness: a
    misspelled kind in a URL would silently render void's numbers under the misspelled
    kind's heading, and every figure on the screen would be true of something else.
    """
    registry = load()
    found = registry.get(kind)
    if found is None:
        raise FindingKindError(
            f"finding kind {kind!r} is not declared (declared: {', '.join(kinds())}). "
            f"Adding a kind is a registry decision - declare it in "
            f"{CONFIG_FILENAME} or in `DEFAULT_FINDING_KINDS`.")
    return found


def methods(kind: str = DEFAULT_KIND):
    """The `inspection_run.method` values that define this kind's denominator."""
    return list(spec(kind).get("observed_by") or ())


def has_denominator(kind: str = DEFAULT_KIND) -> bool:
    """Can a RATE be computed for this kind at all?

    False means the console must render "분모 없음 - 대조 불가" as CONTENT (the brief's
    words), not an empty panel and certainly not a rate over an invented denominator.
    """
    return bool(methods(kind))


def classes(kind: str = DEFAULT_KIND):
    """This kind's CLOSED class set, or `[]` when it declares none.

    `MI_LEDGER_SCHEMA_PROPOSAL` §6-quater: a defect's class (계면/벌크/에지 for a void)
    is a CLAIM rather than a stored attribute, and the set of names a claim may use is
    per-kind, closed and add-only - void's set is not delamination's. It is declared
    here, beside the kind, for the same reason `observed_by` is: the console builds its
    class slice axis from the declaration, so registering a kind's classes is what makes
    the axis appear, with no client change.

    🔴 EMPTY IS AN ANSWER. A kind whose source utters no class renders no class axis at
    all - not an axis with nothing in it, and certainly not a borrowed set from the kind
    next door.
    """
    return [str(c) for c in (spec(kind).get("classes") or ())]


def observation_table(kind: str = DEFAULT_KIND) -> str:
    """The table holding this kind's observations, validated against the registry.

    Validated because the name is interpolated into SQL: it can only ever be a value the
    registry declared, so an operator's config file cannot turn into a statement.
    """
    table = str(spec(kind)["observation_table"])
    if not table.replace("_", "").isalnum():
        raise FindingKindError(
            f"finding kind {kind!r} declares observation_table {table!r}, which is not a "
            f"plain identifier. This name is interpolated into SQL and will not be.")
    return table


def population_ctes(kind: str = DEFAULT_KIND) -> str:
    """The THREE-WAY SPLIT as SQL CTEs. One spelling, for every consumer.

    Produces `kind_run`, `kind_found`, `kind_scanned`, `kind_clean`, `kind_unscanned`,
    each keyed by `(base_wafer_id, base_x, base_y)`. The caller binds `:methods` (a list
    of method names) and may bind `:package_filter` conditions of its own.

    🔴 `kind_clean` is `scanned MINUS found`, NOT `NOT EXISTS(finding)`. On this box the
    difference is 280,001 positions (measured): every bonded position nobody has scanned would
    otherwise be reported as clean, and the console's central claim - "these packages were
    LOOKED AT and were fine" - would be false for the overwhelming majority of the rows
    supporting it. The brief names this exact drift as non-negotiable, and the way to
    keep a rule like that is to leave only one place where it could be broken.
    """
    table = observation_table(kind)
    package = ", ".join(PACKAGE_COLUMNS)
    return f"""
kind_run AS (
    SELECT r.run_uid, r.base_wafer_id, r.base_x, r.base_y, r.eqp_id, r.recipe_id,
           r.observed_at
    FROM {RUN_TABLE} r
    WHERE r.method = ANY(:methods)
),
kind_finding AS (
    SELECT o.*, k.base_wafer_id AS pkg_wafer, k.base_x AS pkg_x, k.base_y AS pkg_y
    FROM {table} o
    JOIN kind_run k ON k.run_uid = o.run_uid
),
kind_found AS (
    SELECT DISTINCT pkg_wafer AS base_wafer_id, pkg_x AS base_x, pkg_y AS base_y
    FROM kind_finding
),
kind_scanned AS (
    SELECT DISTINCT base_wafer_id, base_x, base_y FROM kind_run
),
kind_clean AS (
    SELECT base_wafer_id, base_x, base_y FROM kind_scanned
    EXCEPT
    SELECT base_wafer_id, base_x, base_y FROM kind_found
),
kind_unscanned AS (
    SELECT DISTINCT {package} FROM {PACKAGE_TABLE}
    EXCEPT
    SELECT base_wafer_id, base_x, base_y FROM kind_scanned
)"""
