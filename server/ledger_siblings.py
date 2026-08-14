# -*- coding: utf-8 -*-
"""`GET /api/ledger/siblings` — one question, two framings, over any declared kind.

WHAT THIS ANSWERS
-----------------
**공통점 (intersection)** — which factors does the found set SHARE?
**차이점 (contrast)**   — which factors are ENRICHED in found-versus-clean?

One endpoint, because it is one question asked twice, and because putting the two answers
side by side is the only way the difference between them is visible. `mode` changes
RANKING AND FILTERING ONLY; the row shape is identical. A decoy factor — one carried by
the found and the clean sides alike — sits at the TOP of `intersection` and is DROPPED by
`contrast`. If the two modes returned different rows that fact would be unobservable, and
killing decoys that a plain intersection reports as findings is the entire reason
contrast exists.

🔴 THE DENOMINATOR IS THE HARD PART AND THE WHOLE POINT
--------------------------------------------------------
A rate without its denominator is not a number. Every rate here carries `of` beside it,
both populations are on every row, and the split is **three-way, always**:

    found           observed at least one finding of this kind
    clean_scanned   scanned by a method that COULD have seen it, and saw none
    never_scanned   no run by any relevant method — ITS OWN COUNT

The third bucket is why this module is careful rather than clever. A never-scanned unit
that quietly joins the clean side inflates the clean denominator with things nobody
looked at; that drags every enrichment toward 1 and hides exactly the factor the console
was opened to find. On this box the difference is 280,000 positions against a clean set
of 28,101 — an order of magnitude, in the direction that makes every finding disappear.
So `clean_scanned` is built strictly from run rows (`scanned MINUS found`, the spelling
`finding_kinds.population_ctes` fixes), never as "the universe minus the found set", and
a unit with no run is structurally incapable of reaching it.

**Honest degradation.** A kind whose registry entry declares `observed_by: []` — an
ad-hoc human observation, somebody looked through a microscope and wrote it down — has NO
clean population, and there is no way to invent one that is not a lie. Intersection still
works. Contrast returns 「분모 없음 — 대조 불가」 with the reason in a structured field,
and `clean_scanned` / `never_scanned` come back as **`null`, not `0`** — a zero there
would be the claim "nothing was clean", and this project has already paid for reading an
absent zero as an inert one.

WHERE THE DECLARATIONS LIVE, AND WHY IN TWO PLACES
---------------------------------------------------
* **`server/finding_kinds.py`** — what a KIND is: its label, its `observed_by` methods,
  its observation table. That registry is another lane's and is the SSOT; this module
  reads it and deliberately keeps no second copy. `finding=<kind>` is a parameter from
  the first line here, and `void` appears exactly once, as `finding_kinds.DEFAULT_KIND`.
* **`server/config/siblings_axes.json`** — how a population is ATTRIBUTED to factors:
  which relations to join, on which columns, and which columns are axes. The kind
  registry models none of that, so this is an addition rather than a duplicate.

[SCALE]
-------
* populations  aggregates over `DISTINCT` unit tuples; 65-160 ms at 75,000 scanned
               positions / 91,756 findings (measured, `assy_manager`, 2026-08-14).
* universe     one `count(*)` over distinct join tuples. Never a per-row series.
* factors      ONE pass per attribution relation using `GROUPING SETS`, so five axes
               cost one scan and not five — 584 ms for three axes plus evidence refs.
* refs         a capped slice of an `array_agg`. The one construct here that is
               O(population) in memory rather than O(1); the cap is declared
               (`evidence_ref_sample`) and the O(1) fallback if it ever bites is
               `min`/`max` of the ref column, which is two refs instead of five.
Nothing loads a row into Python that is not returned to the caller.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from datetime import datetime, timedelta, timezone

import finding_kinds
from ledger_trace import _fetch, relation_exists     # ONE spelling of both, reused

logger = logging.getLogger("Ledger.Siblings")

MODE_INTERSECTION = "intersection"
MODE_CONTRAST = "contrast"
MODES = (MODE_INTERSECTION, MODE_CONTRAST)

#: `state` — which world the caller is in. Same vocabulary as `GET /api/ledger/coverage`
#: on purpose: one word means one thing across the ledger endpoints.
STATE_ABSENT = "absent"      # the observation relation is not deployed
STATE_EMPTY = "empty"        # deployed, zero findings of this kind in this window
STATE_READY = "ready"

#: Structured tokens. A client BRANCHES on these; the Korean beside them is prose for the
#: operator's eyes only (ruling R-2026-08-13-C).
REASON_NO_OBSERVED_BY = "no_observed_by_declared"
REASON_NO_RUNS = "no_runs_for_methods"
REASON_RUN_RELATION_ABSENT = "run_relation_absent"
REASON_FINDING_RELATION_ABSENT = "finding_relation_absent"
REASON_NO_UNIVERSE = "no_universe_declared"
REASON_UNIVERSE_RELATION_ABSENT = "universe_relation_absent"
REASON_UNKNOWN_KIND = "unknown_finding_kind"
REASON_BAD_WINDOW = "bad_window"
REASON_BAD_MODE = "bad_mode"
REASON_ABSENT_FROM_CLEAN = "absent_from_clean_population"

#: Enrichment verdicts. `undeterminable` is NOT `flat`: one is the absence of a
#: judgement and the other IS a judgement, and they must never render the same.
ENRICHED, FLAT, DEPLETED, UNDETERMINABLE = (
    "enriched", "flat", "depleted", "undeterminable")

AXES_CONFIG_FILENAME = "siblings_axes.json"
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_WINDOW_DAYS = re.compile(r"^(\d+)\s*d$", re.I)
_WINDOW_RANGE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.\.(\d{4}-\d{2}-\d{2})$")

_lock = threading.Lock()
_axes_cache = None


class SiblingsRequestError(ValueError):
    """A malformed request. Carries the structured body the route returns as 422."""

    def __init__(self, detail):
        super().__init__(detail.get("message") or detail.get("reason"))
        self.detail = detail


class SiblingsConfigError(RuntimeError):
    """The declared factor geometry is unusable. Refused at the door, loudly."""


# --------------------------------------------------------------- factor geometry config
def _identifier(value, where):
    """Every relation and column name below is interpolated into SQL, because PostgreSQL
    has no parameter form for an identifier. So each is checked here, at LOAD time — a
    config that could inject is refused before any request can reach it."""
    text = str(value or "").strip()
    if not _IDENTIFIER.match(text):
        raise SiblingsConfigError(
            f"{where} must be a bare SQL identifier: {value!r}")
    return text


def _column_map(raw, where):
    if not isinstance(raw, dict) or not raw:
        raise SiblingsConfigError(f"{where} must be a non-empty object")
    return {_identifier(k, f"{where} key"): _identifier(v, f"{where}[{k}]")
            for k, v in raw.items()}


DEFAULT_AXES_CONFIG = {
    "defaults": {"limit": 20, "min_support": 2, "evidence_ref_sample": 5,
                 "contrast": {"enriched_at": 1.5, "depleted_at": 0.6667}},
    "geometry": {
        "unit": "package",
        "unit_label": "패키지 (base 위치)",
        "unit_columns": ["base_wafer_id", "base_x", "base_y"],
        "run_key_column": "run_uid",
        "run_method_column": "method",
        "run_time_column": "observed_at",
        "observation_run_ref_column": "run_uid",
        "universe": {"relation": finding_kinds.PACKAGE_TABLE,
                     "join": dict(zip(("base_wafer_id", "base_x", "base_y"),
                                      finding_kinds.PACKAGE_COLUMNS))},
    },
    "attribution": [],
    "kinds": {},
}


class Axis:
    __slots__ = ("name", "label", "column", "about", "relation")

    def __init__(self, raw, source, where, i):
        self.name = raw.get("name")
        if not self.name:
            raise SiblingsConfigError(f"{where}.axes[{i}] has no name")
        self.column = _identifier(raw.get("column"), f"{where}.axes[{i}].column")
        self.label = raw.get("label") or self.name
        self.about = raw.get("about") or source.about
        self.relation = source.relation

    def as_dict(self):
        return {"name": self.name, "label": self.label, "about": self.about,
                "source": f"{self.relation}.{self.column}"}


class AttributionSource:
    """One relation the populations are attributed THROUGH, and its axes.

    `about` is a badge and never a filter: `process` means the axis describes what made
    the part, `inspection` means it describes the scan that looked at it. Both are real
    findings and they are DIFFERENT findings — a console that cannot tell them apart will
    report a scanner artefact as a process cause.
    """

    __slots__ = ("relation", "about", "label", "key_column", "join", "axes",
                 "filter_column", "filter_values_from", "filter_values")

    def __init__(self, raw, where):
        self.relation = _identifier(raw.get("relation"), f"{where}.relation")
        self.about = raw.get("about") or "process"
        self.label = raw.get("label") or self.relation
        self.key_column = (None if not raw.get("key_column")
                           else _identifier(raw["key_column"], f"{where}.key_column"))
        self.join = _column_map(raw.get("join"), f"{where}.join")
        # 🔴 MEASURED DEFECT, not a precaution. `inspection_run` holds every method's
        # runs, so attributing a void population through it WITHOUT this filter dragged
        # the delamination scanner's recipe in as a "factor of voids" - `SYN_DELAM_R1`
        # appeared on a `finding=void` answer (assy_manager, 2026-08-14) purely because
        # the same package had also been scanned by `scat`. A factor relation that holds
        # rows about other kinds has to be narrowed by the SAME declaration that defines
        # the denominator, or the generalisation leaks between kinds.
        flt = raw.get("filter") or {}
        self.filter_column = (None if not flt.get("column") else
                              _identifier(flt["column"], f"{where}.filter.column"))
        self.filter_values_from = flt.get("values_from")
        self.filter_values = flt.get("values")
        self.axes = [Axis(a, self, where, i)
                     for i, a in enumerate(raw.get("axes") or [])]
        if not self.axes:
            raise SiblingsConfigError(f"{where} declares no axes")

    def filter_clause(self, alias, methods, params):
        """`AND a.<col> = ANY(...)`, or nothing. `values_from: observed_by` binds the
        kind's OWN methods, so the narrowing follows the kind rather than the config."""
        if not self.filter_column:
            return ""
        values = (list(methods) if self.filter_values_from == "observed_by"
                  else list(self.filter_values or []))
        if not values:
            return ""
        params["attr_filter"] = values
        return f" AND {alias}.{self.filter_column} = ANY(%(attr_filter)s)"


class Geometry:
    __slots__ = ("unit", "unit_label", "unit_columns", "run_key_column",
                 "run_method_column", "run_time_column", "observation_run_ref_column",
                 "universe_relation", "universe_join")

    def __init__(self, raw, where="geometry"):
        self.unit = raw.get("unit") or "unit"
        self.unit_label = raw.get("unit_label") or self.unit
        self.unit_columns = [_identifier(c, f"{where}.unit_columns")
                             for c in (raw.get("unit_columns") or [])]
        if not self.unit_columns:
            raise SiblingsConfigError(f"{where}.unit_columns is empty")
        self.run_key_column = _identifier(raw.get("run_key_column"),
                                          f"{where}.run_key_column")
        self.run_method_column = _identifier(raw.get("run_method_column"),
                                             f"{where}.run_method_column")
        self.run_time_column = (None if not raw.get("run_time_column") else
                                _identifier(raw["run_time_column"],
                                            f"{where}.run_time_column"))
        self.observation_run_ref_column = _identifier(
            raw.get("observation_run_ref_column"),
            f"{where}.observation_run_ref_column")
        universe = raw.get("universe") or {}
        if universe:
            self.universe_relation = _identifier(universe.get("relation"),
                                                 f"{where}.universe.relation")
            self.universe_join = _column_map(universe.get("join"),
                                             f"{where}.universe.join")
        else:
            self.universe_relation, self.universe_join = None, None


class AxesConfig:
    __slots__ = ("defaults", "geometry", "attribution", "per_kind", "path")

    def __init__(self, raw, path):
        self.path = path
        merged = dict(DEFAULT_AXES_CONFIG["defaults"])
        declared = raw.get("defaults") or {}
        contrast = dict(DEFAULT_AXES_CONFIG["defaults"]["contrast"])
        contrast.update(declared.get("contrast") or {})
        merged.update({k: v for k, v in declared.items()
                       if k != "contrast" and not k.startswith("__")})
        merged["contrast"] = contrast
        self.defaults = merged

        geo = dict(DEFAULT_AXES_CONFIG["geometry"])
        geo.update({k: v for k, v in (raw.get("geometry") or {}).items()
                    if not k.startswith("__")})
        self.geometry = Geometry(geo)
        self.attribution = [AttributionSource(s, f"attribution[{i}]")
                            for i, s in enumerate(raw.get("attribution") or [])]
        self.per_kind = {k: v for k, v in (raw.get("kinds") or {}).items()
                         if not k.startswith("__")}

    def for_kind(self, kind):
        """`(geometry, attribution)` for one kind — overrides on top of the shared pair."""
        override = self.per_kind.get(kind) or {}
        geometry = self.geometry
        if override.get("geometry"):
            geo = dict(DEFAULT_AXES_CONFIG["geometry"])
            geo.update({k: v for k, v in override["geometry"].items()
                        if not k.startswith("__")})
            geometry = Geometry(geo, f"kinds.{kind}.geometry")
        attribution = self.attribution
        if override.get("attribution"):
            attribution = [AttributionSource(s, f"kinds.{kind}.attribution[{i}]")
                           for i, s in enumerate(override["attribution"])]
        return geometry, attribution


def load_axes_config(force_reload=False):
    """Read once, cached. Falls back to `<name>.sample`, this project's convention for
    gitignored operator config — it is what lets a fresh checkout answer instead of 500."""
    global _axes_cache
    with _lock:
        if _axes_cache is not None and not force_reload:
            return _axes_cache
        try:
            import paths
            path = os.path.join(paths.CONFIG_DIR, AXES_CONFIG_FILENAME)
        except Exception:                                          # pragma: no cover
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "config", AXES_CONFIG_FILENAME)
        if not os.path.exists(path):
            path += ".sample"
        if not os.path.exists(path):
            raise SiblingsConfigError(
                f"no factor geometry at {AXES_CONFIG_FILENAME} (and no .sample beside it)")
        try:
            with open(path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except SiblingsConfigError:
            raise
        except Exception as exc:
            raise SiblingsConfigError(f"{path} is not readable JSON: {exc}")
        if not isinstance(raw, dict):
            raise SiblingsConfigError(f"{path} must be a JSON object")
        _axes_cache = AxesConfig(raw, path)
        return _axes_cache


def set_axes_config(config):
    """Install a geometry for this process. Tests use it; nothing else should."""
    global _axes_cache
    with _lock:
        _axes_cache = (None if config is None else
                       config if isinstance(config, AxesConfig) else
                       AxesConfig(config, "<memory>"))
        return _axes_cache


# --------------------------------------------------------------------------- window
class Window:
    __slots__ = ("spec", "start", "end")

    def __init__(self, spec=None, start=None, end=None):
        self.spec, self.start, self.end = spec, start, end

    @property
    def declared(self):
        return self.start is not None or self.end is not None

    def as_dict(self):
        return {"declared": self.declared, "spec": self.spec,
                "from": self.start.isoformat() if self.start else None,
                "to": self.end.isoformat() if self.end else None}


def parse_window(spec, now=None):
    """`7d` or `YYYY-MM-DD..YYYY-MM-DD`. Absent means all time, which is a real answer."""
    text = (spec or "").strip()
    if not text:
        return Window()
    now = now or datetime.now(timezone.utc)
    days = _WINDOW_DAYS.match(text)
    if days:
        n = int(days.group(1))
        if n <= 0:
            raise SiblingsRequestError({"reason": REASON_BAD_WINDOW, "spec": spec,
                                        "message": "window 일수는 1 이상"})
        return Window(text, now - timedelta(days=n), now)
    span = _WINDOW_RANGE.match(text)
    if span:
        start = datetime.fromisoformat(span.group(1)).replace(tzinfo=timezone.utc)
        end = datetime.fromisoformat(span.group(2)).replace(tzinfo=timezone.utc)
        if end <= start:
            raise SiblingsRequestError({"reason": REASON_BAD_WINDOW, "spec": spec,
                                        "message": "window 끝이 시작보다 앞"})
        return Window(text, start, end)
    raise SiblingsRequestError({
        "reason": REASON_BAD_WINDOW, "spec": spec,
        "message": "window 형식: 7d 또는 YYYY-MM-DD..YYYY-MM-DD"})


# --------------------------------------------------------------------------- SQL plan
class _Plan:
    """The CTE prelude every query of one request shares, built once.

    `runs`/`scanned` exist only when the kind HAS a denominator. When it does not, `pop`
    is the found set alone and every clean-side number is `None` rather than `0` — the
    distinction the console renders as 「분모 없음」.
    """

    def __init__(self, geometry, observation_relation, methods, window, has_runs):
        self.geo = geometry
        self.units = geometry.unit_columns
        self.has_runs = has_runs
        self.params = {}
        self.prelude = self._build(observation_relation, methods, window)

    def _build(self, observation, methods, window):
        geo, units = self.geo, self.units
        parts = []
        if self.has_runs:
            self.params["methods"] = list(methods)
            time_clause = ""
            if window.declared and geo.run_time_column:
                if window.start is not None:
                    self.params["win_from"] = window.start
                    time_clause += f" AND {geo.run_time_column} >= %(win_from)s"
                if window.end is not None:
                    self.params["win_to"] = window.end
                    time_clause += f" AND {geo.run_time_column} < %(win_to)s"
            parts.append(
                f"runs AS (SELECT {geo.run_key_column} AS run_key, {', '.join(units)} "
                f"FROM {finding_kinds.RUN_TABLE} "
                f"WHERE {geo.run_method_column} = ANY(%(methods)s){time_clause})")
            parts.append(f"scanned AS (SELECT DISTINCT {', '.join(units)} FROM runs)")
            # 🔴 The found set is defined THROUGH the windowed runs, not beside them. A
            # package scanned twice - clean inside the window, with a finding outside it -
            # must not count as found here, and joining on the run key is what makes that
            # exact rather than approximately right. It is also what keeps `found` a
            # SUBSET of `scanned`, without which `clean = scanned - found` would be wrong.
            parts.append(
                f"found AS (SELECT DISTINCT {', '.join('r.' + c for c in units)} "
                f"FROM {observation} o "
                f"JOIN runs r ON r.run_key = o.{geo.observation_run_ref_column})")
            # `unit_id` is a dense integer name for one member of the population. It is
            # here for one measured reason: the factor aggregate has to count UNITS and
            # not attribution rows, and `count(DISTINCT (a, b, c))` on a row constructor
            # made the delamination answer take 37 s against 30,000 scanned packages.
            # Counting distinct integers instead is the same number, and it is the
            # difference between a screen and a timeout.
            parts.append(
                f"pop AS (SELECT row_number() OVER () AS unit_id, "
                f"{', '.join('s.' + c for c in units)}, "
                f"(f.{units[0]} IS NOT NULL) AS is_found FROM scanned s "
                f"LEFT JOIN found f USING ({', '.join(units)}))")
        else:
            parts.append(
                f"found AS (SELECT DISTINCT {', '.join(units)} FROM {observation})")
            parts.append(
                f"pop AS (SELECT row_number() OVER () AS unit_id, {', '.join(units)}, "
                f"TRUE AS is_found FROM found)")
        return "WITH " + ",\n".join(parts)


def _join_on(left, right, mapping):
    return " AND ".join(f"{right}.{theirs} = {left}.{ours}"
                        for ours, theirs in mapping.items())


# --------------------------------------------------------------------------- the answer
def siblings(connection, kind=None, mode=MODE_INTERSECTION, window=None, limit=None,
             min_support=None, axes=None, now=None):
    """The whole answer, in the pinned envelope. Read-only: never writes, never DDLs."""
    config = load_axes_config()
    defaults = config.defaults
    kind = (kind or finding_kinds.DEFAULT_KIND).strip()
    mode = (mode or MODE_INTERSECTION).strip()
    if mode not in MODES:
        raise SiblingsRequestError({"reason": REASON_BAD_MODE, "mode": mode,
                                    "modes": list(MODES),
                                    "message": f"mode는 {' 또는 '.join(MODES)}"})
    try:
        spec = finding_kinds.spec(kind)
    except finding_kinds.FindingKindError as exc:
        raise SiblingsRequestError({
            "reason": REASON_UNKNOWN_KIND, "kind": kind,
            "declared_kinds": finding_kinds.kinds(),
            "message": f"선언되지 않은 관측 종류: {kind}", "detail": str(exc)})

    observation = finding_kinds.observation_table(kind)
    methods = finding_kinds.methods(kind)
    geometry, attribution = config.for_kind(kind)
    win = parse_window(window, now=now)
    limit = _bounded(limit, defaults["limit"], 1, 200)
    min_support = _bounded(min_support, defaults["min_support"], 0, 10 ** 9)
    sample_n = int(defaults["evidence_ref_sample"])
    wanted = {p.strip() for p in (axes or "").split(",") if p.strip()}

    envelope = {
        "generated_at": (now or datetime.now(timezone.utc)).isoformat(),
        "mode": mode,
        "finding": {
            "kind": kind, "label": spec.get("label") or kind, "declared": True,
            "observed_by": list(methods),
            "population_unit": geometry.unit,
            "population_unit_label": geometry.unit_label,
            "unit_columns": list(geometry.unit_columns),
            "source": {"relation": observation},
        },
        "window": win.as_dict(),
        "notes": [],
    }

    # -- 1. is the observation relation even deployed? ASK THE CATALOGUE, never an
    #       exception: one UndefinedTable poisons the request's transaction and every
    #       later statement fails for an unrelated-looking reason.
    if not relation_exists(connection, observation):
        envelope.update({
            "state": STATE_ABSENT,
            "populations": _null_populations(),
            "denominator": {"state": STATE_ABSENT, "basis": None,
                            "methods": list(methods),
                            "reason": REASON_FINDING_RELATION_ABSENT,
                            "message": f"관측 테이블 {observation} 없음 — 수집/"
                                       f"마이그레이션 미실행"},
            "axes": [], "factors": [], "factors_truncated": False,
            "factors_considered": 0,
        })
        return envelope

    # -- 2. is there a denominator at all? Three ways there is not, each named apart,
    #       because the operator's fix is different for each one.
    reason = None
    if not methods:
        reason = REASON_NO_OBSERVED_BY
    elif not relation_exists(connection, finding_kinds.RUN_TABLE):
        reason = REASON_RUN_RELATION_ABSENT
    has_runs = reason is None

    plan = _Plan(geometry, observation, methods, win, has_runs)
    counts = _populations(connection, plan)
    if has_runs and counts["scanned"] == 0:
        reason, has_runs = REASON_NO_RUNS, False
        plan = _Plan(geometry, observation, methods, win, False)
        counts = _populations(connection, plan)

    populations, denominator = _assemble(
        connection, geometry, counts, has_runs, reason, methods, plan, envelope["notes"])
    envelope["state"] = STATE_READY if counts["found"] else STATE_EMPTY
    envelope["populations"] = populations
    envelope["denominator"] = denominator

    # -- 3. the factors. One pass per attribution relation; GROUPING SETS inside it.
    rows, axis_meta, considered = [], [], 0
    for source in attribution:
        picked = [a for a in source.axes if not wanted or a.name in wanted]
        if not picked:
            continue
        if not relation_exists(connection, source.relation):
            envelope["notes"].append({"note": "attribution_relation_absent",
                                      "relation": source.relation})
            continue
        source_rows, covered = _factors(connection, plan, source, picked,
                                        sample_n, has_runs, methods)
        considered += len(source_rows)
        rows.extend(source_rows)
        for ax in picked:
            meta = ax.as_dict()
            meta["covered"] = covered
            axis_meta.append(meta)

    factors = [_score(r, populations, has_runs, reason, defaults["contrast"])
               for r in rows if r["n_found"] >= min_support]
    factors = _rank(factors, mode, has_runs)
    envelope.update({
        "axes": axis_meta,
        "factors_considered": considered,
        "factors_truncated": len(factors) > limit,
        "factors": factors[:limit],
    })
    if mode == MODE_CONTRAST and not has_runs:
        envelope["notes"].append({"note": "contrast_unavailable", "reason": reason,
                                  "message": "분모 없음 — 대조 불가"})
    return envelope


# --------------------------------------------------------------------------- pieces
def _bounded(value, default, low, high):
    try:
        n = int(value) if value is not None else int(default)
    except (TypeError, ValueError):
        n = int(default)
    return max(low, min(high, n))


def _null_populations():
    """Every bucket `null` — the shape that says "no claim", not "zero"."""
    return {name: {"count": None} for name in
            ("found", "clean_scanned", "never_scanned", "scanned", "universe")}


def _populations(connection, plan):
    if plan.has_runs:
        sql = (f"{plan.prelude}\n"
               f"SELECT (SELECT count(*) FROM scanned), (SELECT count(*) FROM found)")
        row = _fetch(connection, sql, plan.params)[0]
        return {"scanned": int(row[0]), "found": int(row[1])}
    sql = f"{plan.prelude}\nSELECT (SELECT count(*) FROM found)"
    return {"scanned": None, "found": int(_fetch(connection, sql, plan.params)[0][0])}


def _assemble(connection, geometry, counts, has_runs, reason, methods, plan, notes):
    unit = geometry.unit
    found = counts["found"]
    populations = _null_populations()
    populations["found"] = {"count": found, "unit": unit}

    if has_runs:
        scanned = counts["scanned"]
        populations["scanned"] = {"count": scanned, "unit": unit}
        populations["clean_scanned"] = {"count": scanned - found, "unit": unit}
        denominator = {"state": STATE_READY, "basis": finding_kinds.RUN_TABLE,
                       "methods": list(methods), "reason": None, "message": None}
    else:
        # 🔴 null, NOT zero. A zero here would be the claim "nothing was clean".
        denominator = {"state": STATE_ABSENT, "basis": None, "methods": list(methods),
                       "reason": reason,
                       "message": f"분모 없음 — 대조 불가 ({_why(reason, methods)})"}

    if geometry.universe_relation is None:
        notes.append({"note": REASON_NO_UNIVERSE,
                      "message": "미스캔 모집단 선언 없음 — never_scanned 산출 불가"})
        return populations, denominator
    if not relation_exists(connection, geometry.universe_relation):
        notes.append({"note": REASON_UNIVERSE_RELATION_ABSENT,
                      "relation": geometry.universe_relation})
        return populations, denominator

    cols = list(geometry.universe_join.values())
    universe = int(_fetch(connection,
                          f"SELECT count(*) FROM (SELECT DISTINCT {', '.join(cols)} "
                          f"FROM {geometry.universe_relation} "
                          f"WHERE {cols[0]} IS NOT NULL) t", None)[0][0])
    populations["universe"] = {"count": universe, "unit": unit}
    if has_runs:
        inside = _scanned_in_universe(connection, plan, geometry)
        populations["never_scanned"] = {"count": max(universe - inside, 0), "unit": unit}
        # 🔴 Not decoration. This fixture deliberately scans 2,500 positions that do not
        # exist (a negative control), and `universe - scanned` would under-report
        # never_scanned by exactly that many. Naming the discrepancy turns one wrong
        # number into two right ones.
        populations["scanned_outside_universe"] = {
            "count": counts["scanned"] - inside,
            "message": "선언된 모집단에 없는 대상을 스캔한 run"}
    return populations, denominator


def _scanned_in_universe(connection, plan, geometry):
    cols = list(geometry.universe_join.values())
    sql = (f"{plan.prelude},\n"
           f"uni AS (SELECT DISTINCT {', '.join(cols)} "
           f"FROM {geometry.universe_relation} WHERE {cols[0]} IS NOT NULL)\n"
           f"SELECT count(*) FROM scanned s JOIN uni u "
           f"ON {_join_on('s', 'u', geometry.universe_join)}")
    return int(_fetch(connection, sql, plan.params)[0][0])


def _why(reason, methods):
    if reason == REASON_NO_OBSERVED_BY:
        return "observed_by 선언 없음 (체계적 스캔 없는 임의 관측)"
    if reason == REASON_RUN_RELATION_ABSENT:
        return f"{finding_kinds.RUN_TABLE} 테이블 없음"
    if reason == REASON_NO_RUNS:
        return f"{'/'.join(methods)} 방법의 run 0건"
    return reason or ""


def _factors(connection, plan, source, axes, sample_n, has_runs, methods):
    """One pass over the joined population; `GROUPING SETS` does every axis at once.

    Five axes therefore cost ONE scan of the join and not five, and the extra `()`
    grouping set carries the attribution COVERAGE in the same pass — how many of the
    found and clean units this relation could say anything about at all. A screen that
    shows a factor rate without knowing the attribution was 95% complete is showing a
    rate over a denominator it has not checked.

    🔴 `count(DISTINCT <unit tuple>)`, NEVER `count(*)`. A package scanned five times has
    five attribution rows, and counting rows would report it as five packages — a
    numerator larger than its own denominator, on the very screen whose rule is that
    every rate carries one. The unit is what is counted because the unit is what the
    populations are made of.
    """
    alias = {ax.name: f"ax{i}" for i, ax in enumerate(axes)}
    select_axes = ", ".join(f"a.{ax.column} AS {alias[ax.name]}" for ax in axes)
    ref = f"a.{source.key_column}" if source.key_column else "NULL::text"
    sets = ", ".join(f"({alias[ax.name]})" for ax in axes) + ", ()"
    axis_case = " ".join(f"WHEN GROUPING({alias[ax.name]}) = 0 THEN '{ax.name}'"
                         for ax in axes)
    value_case = " ".join(
        f"WHEN GROUPING({alias[ax.name]}) = 0 THEN {alias[ax.name]}::text"
        for ax in axes)
    params = dict(plan.params)
    params["sample_n"] = int(sample_n)
    narrow = source.filter_clause("a", methods, params)
    sql = (
        f"{plan.prelude},\n"
        f"attr AS (SELECT p.unit_id, p.is_found, {select_axes}, {ref} AS ref\n"
        f"         FROM pop p JOIN {source.relation} a "
        f"ON {_join_on('p', 'a', source.join)}{narrow})\n"
        f"SELECT CASE {axis_case} ELSE '__total__' END AS axis,\n"
        f"       CASE {value_case} ELSE NULL END AS value,\n"
        f"       count(DISTINCT unit_id) FILTER (WHERE is_found) AS n_found,\n"
        f"       count(DISTINCT unit_id) FILTER (WHERE NOT is_found) AS n_clean,\n"
        f"       (array_agg(ref) FILTER (WHERE is_found))[1:%(sample_n)s] AS refs\n"
        f"FROM attr GROUP BY GROUPING SETS ({sets})")

    rows = []
    covered = {"found": 0, "clean_scanned": 0 if has_runs else None}
    by_name = {ax.name: ax for ax in axes}
    for axis, value, n_found, n_clean, refs in _fetch(connection, sql, params):
        if axis == "__total__":
            covered = {"found": int(n_found),
                       "clean_scanned": int(n_clean) if has_runs else None}
            continue
        ax = by_name[axis]
        rows.append({
            "axis": axis, "value": value, "label": f"{ax.label} = {value}",
            "about": ax.about, "relation": ax.relation, "column": ax.column,
            "key_column": source.key_column,
            "n_found": int(n_found), "n_clean": int(n_clean),
            "refs": [r for r in (refs or []) if r is not None],
        })
    return rows, covered


def _score(row, populations, has_runs, reason, contrast_cfg):
    """Raw counts into the pinned `FactorRow`. Both denominators, on every row."""
    of_found = (populations["found"] or {}).get("count") or 0
    of_clean = (populations["clean_scanned"] or {}).get("count")
    rate_found = (row["n_found"] / of_found) if of_found else None

    out = {
        "axis": row["axis"], "value": row["value"], "label": row["label"],
        "about": row["about"],
        "found": {"n": row["n_found"], "of": of_found, "rate": _round(rate_found)},
        "clean_scanned": None,
        "enrichment": None, "enrichment_ci": None, "rate_delta": None,
        "enrichment_state": UNDETERMINABLE, "reason": reason,
        "evidence_refs": [{"relation": row["relation"], "key_column": row["key_column"],
                           "key": r, "column": row["column"], "population": "found"}
                          for r in row["refs"]],
        "evidence_ref_count": row["n_found"],
    }
    if not has_runs or not of_clean:
        return out

    rate_clean = row["n_clean"] / of_clean
    out["clean_scanned"] = {"n": row["n_clean"], "of": of_clean,
                            "rate": _round(rate_clean)}
    out["reason"] = None
    out["rate_delta"] = _round(rate_found - rate_clean)
    if rate_clean == 0:
        # Present in the found set and in NO clean unit. NOT "infinitely enriched": an
        # unbounded point estimate would sort above every real one. The interval below
        # still has a finite lower bound (Haldane's correction), and THAT is what ranks.
        out["reason"] = REASON_ABSENT_FROM_CLEAN
    else:
        out["enrichment"] = _round(rate_found / rate_clean)

    low, high = _ratio_interval(row["n_found"], of_found, row["n_clean"], of_clean)
    out["enrichment_ci"] = [_round(low), _round(high)]
    if low >= contrast_cfg["enriched_at"]:
        out["enrichment_state"] = ENRICHED
    elif high <= contrast_cfg["depleted_at"]:
        out["enrichment_state"] = DEPLETED
    else:
        out["enrichment_state"] = FLAT
    return out


#: z for a 95% two-sided interval. Named rather than inlined so the confidence level is
#: a fact somebody can find and argue with.
_Z95 = 1.959963985


def _ratio_interval(a, n1, b, n2):
    """95% interval for the rate ratio (Katz log method, Haldane-corrected).

    🔴 WHY AN INTERVAL AND NOT THE BARE RATIO. Ranking by the point estimate puts the
    NOISIEST rows on top, which is the opposite of what a surprise ranking is for.
    Measured on this box: `finding=delam` returned a hundred per-lot rows at 1.7-1.9x,
    every one of them carried by ~108 packages, and they buried everything else. Their
    lower bounds land under 1.5 and they correctly become `flat`; a factor with the same
    ratio and real support keeps its verdict. This is the "기저율 대비 놀라움" rule
    doing the second half of its job — a ratio without its sample size is as unreadable
    as a rate without its denominator.

    The 0.5 correction is Haldane-Anscombe: it makes a zero cell finite instead of
    special-cased, so "present in the found set and in no clean unit" gets a real (large)
    lower bound rather than an infinity that would sort above every measured factor.
    """
    import math
    a, b = a + 0.5, b + 0.5
    n1, n2 = n1 + 0.5, n2 + 0.5
    ratio = (a / n1) / (b / n2)
    se = math.sqrt(1.0 / a - 1.0 / n1 + 1.0 / b - 1.0 / n2)
    log_ratio = math.log(ratio)
    return math.exp(log_ratio - _Z95 * se), math.exp(log_ratio + _Z95 * se)


def _rank(factors, mode, has_runs):
    if mode == MODE_CONTRAST and has_runs:
        # 🔴 THE DECOY FILTER, and the single behaviour that distinguishes contrast from
        # a plain intersection. A factor carried by the found and clean sides alike is
        # `flat` and is dropped here. `undeterminable` is KEPT - it is a missing
        # judgement, not a judgement of "no difference", and hiding it would make an
        # unmeasurable factor look like a measured non-finding.
        kept = [f for f in factors if f["enrichment_state"] != FLAT]
        # Ranked by the interval's LOWER bound, not by the point estimate: the top of
        # this list is "what am I most sure is enriched", which is the question, rather
        # than "what has the largest ratio", which small samples always win.
        return sorted(kept, key=lambda f: (-((f.get("enrichment_ci") or [0])[0] or 0),
                                           -f["found"]["n"]))
    return sorted(factors, key=lambda f: (-(f["found"]["rate"] or 0), -f["found"]["n"]))


def _round(value, places=4):
    return None if value is None else round(float(value), places)
