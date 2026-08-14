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
which is true of 277,500 positions on this box that nobody has ever looked at. So the
control set is defined as ``scanned MINUS found`` and never as ``NOT EXISTS(finding)``,
and it is defined in ONE place so that a second consumer cannot spell it the other way.
"""
from __future__ import annotations

import json
import os
import threading

#: The kind a caller gets when it does not name one. 🔴 This is the ONE permitted
#: appearance of a kind name as a literal in code - the ruling calls out "기본값이지
#: 특례가 아니다" - and it is a default parameter value, not a condition.
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
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "config",
                            CONFIG_FILENAME)


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
    difference is 277,500 positions: every bonded position nobody has ever scanned would
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
