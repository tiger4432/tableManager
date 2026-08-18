# -*- coding: utf-8 -*-
"""`GET /api/ledger/lots` — the SURPRISE TABLE: rows = one declared axis, columns = metrics.

🔴 WHY THIS ENDPOINT EXISTS (product owner, 2026-08-14, `SCENARIO_CONSOLE_BRIEF` §0-ter
「놀라움 장치 확정」)
--------------------------------------------------------------------------------------
> 「선택기 없음 — 종합 트렌드표(행=랏 생산 순서, 열=지표 나란히, 항목축 조건부서식).」

The first screen of the investigation console is not a lot list, it is an EXPECTATION
VIOLATION list. A count is not a surprise; a count against a denominator against a
baseline is. So every number this endpoint serves travels with the denominator it was
divided by and the baseline it was compared to, and the client never divides.

🔴 THREE OWNER CONSTRAINTS, AND WHERE EACH ONE LIVES IN THE RESPONSE
---------------------------------------------------------------------
1. 「열 구성 = {항목 × 집계}는 사용자 커스텀이고 URL에 실린다. 다만 지표 «자체»는 config
   선언이다.」 — `columns=<kind>:<aggregate>,...` is the request; WHICH kinds and WHICH
   aggregates may be named is answered by declaration and never by a literal here. The
   kinds come from `finding_kinds` (already the registry, already served by
   `GET /api/ledger/kinds`) and the aggregates from `AGGREGATES` below, overridable by
   `config/lot_grid.json`. There is NO list of metrics in this file — a metric is the
   CROSS PRODUCT of a declared kind and a declared aggregate, so declaring a kind adds a
   whole column family with no edit here.

2. 「조건부서식은 현행 유지 — 열마다 자기 기저 대비 배수. 특수평가는 뱃지만, 미검사는 —.」
   `cells[].level` is SERVED, not computed by the client, because the baseline it is
   measured against excludes rows the client cannot know are excluded (see
   `bucket.counts_toward_baseline`). And 미검사 versus 0 is `cells[].state`, which is the
   whole reason this module refuses to let a rate default to zero — see the next block.

3. 「3축 맵은 실제 valid die 레퍼런스를 참조해 표준 frame으로 그린다.」 — that is
   `GET /api/ledger/lot_map`, below, which serves the registered frame and the valid-die
   pointer rather than a grid it invented. Coordinates are CELL COUNTS FROM ORIGIN; this
   module never multiplies by a pitch and never emits a millimetre.

🔴 「미검사」 IS NOT 「0」 AND THIS FILE IS WHERE THAT IS ENFORCED
------------------------------------------------------------------
MEASURED on `assy_manager` 2026-08-14: a lot holds 3,525 bonded chips and only 725 of
them are ever scanned by `sat` — 20.6%. A client that divided a void count by the lot
size would be wrong by a factor of five, and a lot with NO scan at all would render as a
flawless 0.0%. So:

    state: "measured"    n and of are both integers; of > 0. A 0 here means LOOKED AT
                         AND NOTHING FOUND, and renders as 「0」.
    state: "unscanned"   of == 0. value/n/level are null and it renders as 「—」.
                         NOT zero, NOT clean, NOT in any baseline.
    state: "no_denominator"
                         the kind declares no `observed_by`, so no rate exists at all
                         (`finding_kinds.has_denominator`). Renders 「분모 없음」.
    state: "unmeasurable"
                         the relation this column needs is not deployed. A deployment
                         fact, answered as one.

This is this project's own `absent-zero-is-not-inert-zero` lesson, which it has already
paid for once, spelled as a FIELD the client branches on rather than as arithmetic the
client is trusted to get right (ruling R-2026-08-13-C).

🔴 THE ROW AXIS IS DECLARED, AND IT SAYS WHAT IT IS
-----------------------------------------------------
The brief asked for 「행 = 코어 랏」. The RULING below stands, but the evidence sentence has
now been wrong twice and the second time was worse than the first.

  * Originally: "`core_lot`/`core_slot`/`cx`/`cy` are NULL in all 357,796 rows". A one-off
    measurement written as a present-tense invariant. Row counts are not properties of the
    code, so a docstring asserting one goes stale in silence.
  * 🔴 Then, on 2026-08-18, that was "corrected" to say those columns do not exist here at
    all — **and that correction was measured against the wrong database.** `server/config/
    database.json` was pointing at an empty `postgres` instance rather than `assy_manager`.
    An empty database answers every question with "nothing there", which reads exactly like
    "the thing you are asking about does not exist". It does exist.

Measured on `assy_manager` (2026-08-18, after the connection was fixed): `bonding_log` has
**376,043 rows**; `core_lot`, `core_slot`, `cx` and `cy` all exist and each carries **88,888
non-NULL values** (~24%). `dt_map` does have `core_lot`. So the axis is not absent — it is
SPARSE, which is a third thing again, and neither of the two earlier sentences.

Re-measure before citing any of this; the numbers belong to a dataset, not to this file:
`SELECT count(*) FILTER (WHERE core_lot IS NOT NULL), count(*) FROM bonding_log`.
And check what `database.json` resolves to first — a number measured against the wrong
database is not a weaker fact, it is a different fact wearing this one's clothes.

The lead PM's ruling (2026-08-14) is therefore `bond_lot`, WITH the screen saying so —
hence `row_axis.label`
carries 「본딩 랏」 and the client is expected to render it, so nobody reads a bonding lot
as a core lot.

The axis is not hardcoded: it is one of the axes `siblings_axes.json` already declares
(`attribution[].axes[].name`), reached by `?by=`, and `axes_available` lists what `by`
accepts. A site that declares another axis gets another row axis for free.

🔴 NO NEW SIDE-JOIN (ruling R-2026-08-14-D)
---------------------------------------------
The chip→lot bridge is the join `siblings_axes.json` ALREADY declares and `/siblings`
ALREADY runs — `{base_wafer_id: base_id, base_x: bx, base_y: by}` into `bonding_log`.
Nothing new is joined. The three-axis map reads `bond_x/bond_y` and `dt_x/dt_y` off THE
SAME bonding row that bridge already lands on, so two of the three projections cost zero
additional relations. The CORE projection would need `dt_log`, which WOULD be a new side
join, so it is not built: it is served as `state: "unreachable"`,
`reason: "no_live_bridge"`, and the screen says so. 「없으면 없다고.」

⚠️ ONE POPULATION SPELLING, GUARDED — READ THIS BEFORE ADDING A SECOND
-----------------------------------------------------------------------
`finding_kinds.population_ctes` and `ledger_siblings._Plan` are already TWO spellings of
the three-way split, and `finding_kinds`'s own docstring says so plainly: "two spellings
exist, they agree today, and nothing detects the day they stop." This module needs N
kinds at once, which neither of them does, so it does not call either.

What it does instead of quietly becoming a third: it follows `_Plan`'s rules exactly
(found is defined THROUGH the windowed runs, so `found ⊆ scanned` holds and a package
scanned twice — clean inside the window, found outside it — does not count as found),
and `test_ledger_lots_pg.py::test_the_grid_totals_agree_with_siblings_populations` drives
BOTH endpoints over the same rows and asserts the totals match. That is the detector
`finding_kinds`'s docstring says does not exist. Do not add a fourth spelling; extend
this one and let that test fail if it disagrees.

[SCALE — measured first, and the ceiling is stated rather than discovered later]
---------------------------------------------------------------------------------
MEASURED on `assy_manager`, 2026-08-14, 352,500 bridged chips / 91,756 voids /
10,421 delams / 107,500 runs, best of three:

    chip→lot bridge ALONE (DISTINCT over bonding_log)          398 ms
    naive: one query per column, 2 columns                   1,303 ms
    ONE PASS, 7 columns (this module's shape)                1,186 ms
    one lot's three-axis map (GET /lot_map)                     189 ms

So the one-pass shape is ~6.4x cheaper PER COLUMN and adding a column is nearly free,
which is the whole reason the grid is one statement instead of one per cell.

🔴 AND IT IS STILL OVER BUDGET, WHICH THE RESPONSE SAYS OUT LOUD. 1,186 ms is at ~3.5% of
this project's ten-million-row target; the bottleneck moved from the bridge to the
per-chip aggregate (352,500 groups, 21 batches, 20 MB spilled to disk) and it is linear,
so the target is tens of seconds. The defence is a DECLARED SIZE GATE, the same shape
`ledger_structure` uses: under `FULL_GRID_MAX_BYTES` the grid covers all time; above it a
declared window is FORCED and `window.forced` + `window.forced_reason` say so, so a screen
can never quietly show a month's counts labelled as all time.

**No materialisation, deliberately** (lead PM, 2026-08-14): the `observed` translation lane
is about to move where these numbers come from, and a rollup built on the source tables
today is one that gets thrown away. `provenance` is the seam instead — see below.

🔴 `provenance` IS THE SWAP SEAM, AND IT IS PINNED BY A TEST
--------------------------------------------------------------
Today the numbers come from the source tables, because THIS MODULE STILL READS THEM:
`_GridPlan` scans `void_obs` / `delam_obs` / `bonding_log` / `inspection_run` and no
statement here touches `ledger_events`. So `provenance` says exactly that —
`source: "source_tables"`, `ledger_backed: false`, and the relations it actually read.

⚠️ That is a fact about THIS QUERY, not about the ledger's contents, and the two came
apart on 2026-08-14: the `observed` translation landed and `Wafer|observed|value` now
carries 102,177 atoms (`GET /api/ledger/kinds`: both kinds `in_ledger: true`, `flowing`).
`ledger_backed` stays `false` until the READ path moves, which has not happened.

When the translation lands, the same response says `ledger_backed: true` and THE CLIENT
DOES NOT CHANGE A LINE. That property is the point, so it is asserted rather than hoped
about: `test_the_provenance_seam_is_the_only_thing_that_moves` builds both answers and
asserts every field except `provenance` is identical. A change that makes the client care
where the numbers came from fails that test.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import finding_kinds
import ledger_siblings
import map_overlay
from ledger_trace import _fetch, relation_exists

logger = logging.getLogger("Ledger.Lots")

#: `state`, in `GET /api/ledger/coverage`'s three words. One word means one thing across
#: every ledger endpoint, so the console reuses its reading.
STATE_ABSENT = "absent"
STATE_EMPTY = "empty"
STATE_READY = "ready"

#: Per-cell state. 🔴 THE CLIENT BRANCHES ON THIS — see the module docstring. It exists so
#: that 「검사했는데 0건」 and 「검사한 적 없음」 are never the same pixel.
CELL_MEASURED = "measured"
CELL_UNSCANNED = "unscanned"
CELL_NO_DENOMINATOR = "no_denominator"
CELL_UNMEASURABLE = "unmeasurable"

#: Column-level state, for a column that cannot be computed at all on this box.
COLUMN_READY = "ready"
COLUMN_UNMEASURABLE = "unmeasurable"

REASON_UNKNOWN_KIND = "unknown_finding_kind"
REASON_UNKNOWN_AGGREGATE = "unknown_aggregate"
REASON_UNKNOWN_AXIS = "unknown_row_axis"
REASON_BAD_COLUMNS = "bad_columns_spec"
REASON_NO_DENOMINATOR = "no_observed_by_declared"
REASON_RELATION_ABSENT = "relation_absent"
REASON_GRID_TOO_LARGE = "grid_too_large_for_full_window"
#: 🔴 A DECLARED WINDOW THAT CANNOT BE APPLIED IS A REFUSAL, NEVER AN ECHO. The geometry
#: has to name a run time column for a window to mean anything here; without one the only
#: honest answers are 「이 축은 기간으로 좁힐 수 없다」 or silence, and emitting a
#: `window.applied` block that no clause implements is the worse of the two failures —
#: silently ignoring a parameter is a bug, claiming it ran is a false statement, and it
#: also removes the one cheap way a caller could have noticed.
REASON_WINDOW_NOT_APPLICABLE = "window_not_applicable_to_axis"

#: Above this — summed on-disk size of every relation the grid must scan — the all-time
#: grid is refused and `LARGE_GRID_WINDOW` is FORCED. 512 MB is ~1.5 M bridged chips at
#: the density measured on this box, i.e. ~5 s of grid, which is already past what a page
#: load may spend; it is a ceiling on the damage, not a promise of speed. Same rule and
#: same vocabulary as `ledger_structure.FULL_CENSUS_MAX_BYTES`, one screen over.
FULL_GRID_MAX_BYTES = 512 * 1024 * 1024

#: What a too-large grid is windowed to instead. Applied to the RUN time column, so it
#: narrows the scanned population rather than the declared structure.
LARGE_GRID_WINDOW = "30d"

#: 🔴 NOT A LIST OF METRICS. A metric is `<kind>:<aggregate>`, so this declares the second
#: half only and the first half stays in `finding_kinds`. Adding a kind adds a whole
#: column family with no edit here; adding an aggregate adds one column to EVERY kind.
#:
#: `needs_denominator` is what makes a cell render 「—」 instead of a number when nothing
#: was scanned, and `over` names WHICH population the value is divided by so the response
#: can ship the denominator beside the value rather than leaving the client to guess.
AGGREGATES = {
    "found_rate": {
        "label": "발생 칩비", "value_kind": "ratio", "needs_denominator": True,
        "over": "scanned",
        "doc": "발견된 칩 / 검사된 칩. 분모는 kind의 observed_by가 정의한다.",
    },
    "found_count": {
        "label": "발생 칩수", "value_kind": "count", "needs_denominator": False,
        "over": None,
        "doc": "발견된 칩 수. 분모 없는 원시 계수 — 랏 크기가 다르면 비교 불가.",
    },
    "per_chip": {
        "label": "칩당 건수", "value_kind": "mean", "needs_denominator": True,
        "over": "scanned",
        "doc": "관측 건수 / 검사된 칩. 한 칩에 여러 건이 나는 종류를 가른다.",
    },
    "event_count": {
        "label": "관측 건수", "value_kind": "count", "needs_denominator": False,
        "over": None,
        "doc": "관측 행 수. 칩 수가 아니라 사건 수다.",
    },
    "extent_mean": {
        "label": "평균 크기", "value_kind": "mean", "needs_denominator": True,
        "over": "found",
        "doc": ("kind의 extent_columns 곱의 평균. 🔴 분모가 «발견된 칩»이지 검사된 "
                "칩이 아니다 — 안 난 칩의 크기는 0이 아니라 없는 값이다."),
    },
    "scanned": {
        "label": "검사 칩", "value_kind": "count", "needs_denominator": False,
        "over": None,
        "doc": "이 kind의 분모 그 자체. 표에 분모를 열로 세울 수 있게 한다.",
    },
}

#: The conditional-format ladder, in the mock-up's steps (owner: 「현행 유지」). A cell is
#: coloured by `value / baseline`, so the ladder is unit-free and one spelling serves every
#: column. Overridable per deployment in `config/lot_grid.json`.
DEFAULT_THRESHOLDS = [
    {"level": 1, "at": 2.0, "label": "주의"},
    {"level": 2, "at": 3.0, "label": "높음"},
    {"level": 3, "at": 4.5, "label": "심각"},
    {"level": 4, "at": 6.0, "label": "극단"},
]

#: How a column's baseline is chosen. The median of the rows that COUNT TOWARD IT — which
#: is not every row: a special-evaluation lot is on the screen with a badge and out of the
#: baseline, per the owner's constraint 2. Mean would let one extreme lot raise the bar it
#: is being judged against.
BASELINE_MEDIAN_OF_ROWS = "median_of_rows"

#: Buckets. 🔴 Until the owner names the real special-evaluation discriminator (brief
#: §0-ter 설계 결정 2: 「실데이터의 특수 평가 구분자는 소유자 입력 대기」), every row is
#: `unknown` and every row counts toward the baseline. That is deliberately the SAFE
#: direction: excluding rows on a guess would quietly reshape every colour on the screen.
BUCKET_UNKNOWN = {"id": "unknown", "label": "미상", "counts_toward_baseline": True}

CONFIG_FILENAME = "lot_grid.json"

_lock = ledger_siblings._lock if hasattr(ledger_siblings, "_lock") else None


class LotGridRequestError(ValueError):
    """A malformed request, refused with a STRUCTURED body the client branches on."""

    def __init__(self, detail):
        super().__init__(detail.get("message") or detail.get("reason"))
        self.detail = detail


# --------------------------------------------------------------------------- declaration
def aggregates():
    """Every declared aggregate name, sorted. What the column picker is built from."""
    return sorted(AGGREGATES)


def aggregate_spec(name):
    """One aggregate's declaration. An undeclared one is refused BY NAME, never defaulted.

    Defaulting here would render some other aggregate's numbers under the requested
    heading, and every figure in the column would be true of something else.
    """
    found = AGGREGATES.get(name)
    if found is None:
        raise LotGridRequestError({
            "reason": REASON_UNKNOWN_AGGREGATE, "aggregate": name,
            "declared": aggregates(),
            "message": (f"집계 {name!r} 미선언 (선언된 것: {', '.join(aggregates())})")})
    return found


class Column:
    """One requested `<kind>:<aggregate>` pair, resolved against both declarations."""

    __slots__ = ("kind", "aggregate", "spec", "kind_spec", "id", "state", "reason")

    def __init__(self, kind, aggregate):
        self.kind, self.aggregate = kind, aggregate
        self.id = f"{kind}:{aggregate}"
        try:
            self.kind_spec = finding_kinds.spec(kind)
        except finding_kinds.FindingKindError as exc:
            raise LotGridRequestError({
                "reason": REASON_UNKNOWN_KIND, "kind": kind,
                "declared": finding_kinds.kinds(), "message": str(exc)})
        self.spec = aggregate_spec(aggregate)
        self.state, self.reason = COLUMN_READY, None

    @property
    def needs_denominator(self):
        return bool(self.spec["needs_denominator"])

    @property
    def methods(self):
        return finding_kinds.methods(self.kind)

    def as_dict(self, baseline, thresholds):
        """The column header, with everything the client needs to render it and NOTHING
        it would have to compute. `has_denominator` is served rather than derived from
        `len(methods)` for the reason `ledger_kinds` already gives: the day the rule
        becomes conditional, a client computing it keeps answering the old rule."""
        has_denom = finding_kinds.has_denominator(self.kind)
        denominator = None
        if self.spec["over"] == "scanned" and has_denom:
            denominator = {"population": "scanned_chips", "label": "검사 칩",
                           "methods": self.methods}
        elif self.spec["over"] == "found":
            denominator = {"population": "found_chips", "label": "발견 칩",
                           "methods": self.methods}
        return {
            "id": self.id,
            "kind": self.kind, "kind_label": self.kind_spec.get("label") or self.kind,
            "aggregate": self.aggregate, "aggregate_label": self.spec["label"],
            "value_kind": self.spec["value_kind"],
            "doc": self.spec["doc"],
            "has_denominator": has_denom,
            "denominator": denominator,
            "baseline": baseline,
            "thresholds": thresholds,
            "state": self.state, "reason": self.reason,
        }


def parse_columns(text, default=None):
    """`void:found_rate,delam:found_rate` -> `[Column, ...]`.

    🔴 THIS IS THE URL-CARRIED QUESTION (owner: 「열 구성이 곧 공유 가능한 질문」), so a
    malformed member is refused by name rather than skipped — a column silently dropped
    would make two people looking at the same link see different tables.
    """
    raw = (text or "").strip()
    if not raw:
        return list(default or ())
    columns, seen = [], set()
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        if token.count(":") != 1:
            raise LotGridRequestError({
                "reason": REASON_BAD_COLUMNS, "token": token,
                "message": (f"열 명세 {token!r} 형식 오류 — <종류>:<집계> 형태여야 한다 "
                            f"(예: void:found_rate)")})
        kind, aggregate = (part.strip() for part in token.split(":"))
        column = Column(kind, aggregate)
        if column.id in seen:
            continue
        seen.add(column.id)
        columns.append(column)
    if not columns:
        raise LotGridRequestError({
            "reason": REASON_BAD_COLUMNS, "token": raw,
            "message": "columns가 비었다 — 최소 한 열이 필요하다"})
    return columns


def default_columns():
    """Every declared kind x the two aggregates that answer 「이 랏 왜 이래?」 first.

    🔴 GENERATED FROM THE REGISTRY, never a literal list: a site that declares a third
    kind sees three column families here with no code change, which is the owner's
    「지표 목록을 하드코딩하지 마십시오」 applied to the DEFAULT as well as to the picker.
    """
    columns = []
    for kind in finding_kinds.kinds():
        for aggregate in ("found_rate", "per_chip"):
            columns.append(Column(kind, aggregate))
    return columns


# --------------------------------------------------------------------------- the row axis
def resolve_row_axis(config, kind, name=None):
    """The declared axis rows are grouped by, and the attribution source it lives on.

    🔴 Not a lot column chosen here — one of the axes `siblings_axes.json` declares. The
    default is the first `about: process` axis whose name ends in `_lot`, which on the
    declared geometry is `bond_lot`; naming it explicitly here would put a lot column back
    into code, which is the thing the owner asked twice to avoid.
    """
    _geometry, attribution = config.for_kind(kind)
    available = [(source, axis) for source in attribution for axis in source.axes]
    if not available:
        raise LotGridRequestError({
            "reason": REASON_UNKNOWN_AXIS, "axis": name, "declared": [],
            "message": "요인 축이 하나도 선언돼 있지 않다 — siblings_axes.json 확인"})
    if name:
        for source, axis in available:
            if axis.name == name:
                return source, axis
        raise LotGridRequestError({
            "reason": REASON_UNKNOWN_AXIS, "axis": name,
            "declared": [a.name for _s, a in available],
            "message": (f"행 축 {name!r} 미선언 "
                        f"(선언된 것: {', '.join(a.name for _s, a in available)})")})
    for source, axis in available:
        if axis.about == "process" and axis.name.endswith("_lot"):
            return source, axis
    for source, axis in available:
        if axis.about == "process":
            return source, axis
    return available[0]


def axes_available(config, kind):
    """What `?by=` accepts, with the badge that says what each axis DESCRIBES.

    `about: inspection` is a badge and never a filter — grouping rows by the scanner's
    recipe is a legitimate question and a DIFFERENT one from grouping by what made the
    part, and a console that cannot tell them apart reports a scanner artefact as a
    process cause (`ledger_siblings.AttributionSource`'s words, kept true here).
    """
    _geometry, attribution = config.for_kind(kind)
    return [{"name": axis.name, "label": axis.label, "about": axis.about,
             "source": f"{source.relation}.{axis.column}"}
            for source in attribution for axis in source.axes]


# --------------------------------------------------------------------------- the size gate
def _relation_size(connection, relation):
    """On-disk bytes, or None when the relation is not deployed. Catalogue only.

    Asked BEFORE any query touches the relation, for the reason `relation_exists` states:
    one `UndefinedTable` poisons the transaction and every later statement in the request
    fails for an unrelated-looking reason.
    """
    if not relation_exists(connection, relation):
        return None
    rows = _fetch(connection,
                  "SELECT pg_relation_size(c.oid) FROM pg_class c "
                  "WHERE c.oid = to_regclass(%(rel)s)", {"rel": relation})
    if not rows or rows[0][0] is None:
        return None
    return int(rows[0][0])


def apply_size_gate(connection, relations, window, now=None, may_force=True):
    """`(window, gate)` — forces `LARGE_GRID_WINDOW` when the scan is too big to buy.

    🔴 THE FORCING IS ANNOUNCED. `ledger_structure` established the shape and this reuses
    it verbatim: a screen may never quietly show a month's counts under an all-time
    heading. When the gate fires the caller's requested window is preserved in
    `window.requested` beside the one that was actually applied.

    `may_force=False` when the caller knows the window could not be applied even if it were
    forced (no declared run time column). Reporting `forced: true` there would announce a
    narrowing that no clause performs — the same false claim as an unapplied `applied`.
    """
    sizes, missing = {}, []
    for relation in relations:
        size = _relation_size(connection, relation)
        if size is None:
            missing.append(relation)
        else:
            sizes[relation] = size
    total = sum(sizes.values())
    gate = {"relations": sizes, "absent_relations": missing,
            "total_bytes": total, "max_bytes": FULL_GRID_MAX_BYTES,
            "forced": False, "reason": None}
    if window.declared or total <= FULL_GRID_MAX_BYTES or not may_force:
        return window, gate
    gate["forced"] = True
    gate["reason"] = REASON_GRID_TOO_LARGE
    return ledger_siblings.parse_window(LARGE_GRID_WINDOW, now=now), gate


# --------------------------------------------------------------------------- the one pass
class _GridPlan:
    """Every requested column as FILTERed aggregates over ONE scan.

    🔴 ONE STATEMENT, NOT ONE PER COLUMN. Measured: the naive shape costs 776 ms for the
    first column and 527 ms for the second, because each one re-derives the chip→lot
    bridge; this shape pays for the bridge once and every further column is a `FILTER`
    over the same rows (1,186 ms for seven columns). The bridge is the expensive half, so
    the number of columns is very nearly free and the number of ROWS is what costs.

    The population rules are `ledger_siblings._Plan`'s, deliberately: `found` is defined
    THROUGH the windowed runs, so `found` stays a SUBSET of `scanned` and a package
    scanned twice — clean inside the window and found outside it — is not counted as
    found. See the module docstring on why this is not permitted to become a third
    spelling.
    """

    def __init__(self, geometry, source, axis, columns, window):
        self.geo = geometry
        self.source = source
        self.axis = axis
        self.columns = columns
        self.params = {}
        self.kinds = []
        seen = set()
        for column in columns:
            if column.kind not in seen:
                seen.add(column.kind)
                self.kinds.append(column.kind)
        self.sql = self._build(window)

    # -- the pieces ---------------------------------------------------------------
    def _unit_cte(self):
        """The chip→row bridge — THE DECLARED JOIN, not a new one.

        `SELECT DISTINCT` rather than a bare select: the bridge is 1:1 on this box today
        (measured: 352,500 rows over 352,500 distinct chips) but nothing DECLARES it to
        be, and a chip that was ever bonded twice would otherwise be counted twice in
        every denominator on the screen. One dedup pass is paid for; a wrong denominator
        is not recoverable.
        """
        units = self.geo.unit_columns
        cols = ", ".join(f"{theirs} AS {ours}"
                         for ours, theirs in self.source.join.items())
        keys = list(self.source.join.keys())
        not_null = " AND ".join(f"{theirs} IS NOT NULL"
                                for theirs in self.source.join.values())
        filter_sql = self.source.filter_clause(
            self.source.relation, self._all_methods(), self.params)
        # `filter_clause` qualifies with an alias; inside this CTE the relation is bare.
        filter_sql = filter_sql.replace(f"{self.source.relation}.", "")
        return (f"unit AS (SELECT DISTINCT {cols}, {self.axis.column} AS row_value "
                f"FROM {self.source.relation} "
                f"WHERE {not_null} AND {self.axis.column} IS NOT NULL{filter_sql})",
                keys, units)

    def _all_methods(self):
        methods = []
        for kind in self.kinds:
            for method in finding_kinds.methods(kind):
                if method not in methods:
                    methods.append(method)
        return methods

    def _runs_cte(self, window):
        geo = self.geo
        self.params["all_methods"] = self._all_methods()
        time_clause = ""
        if window.declared and geo.run_time_column:
            if window.start is not None:
                self.params["win_from"] = window.start
                time_clause += f" AND {geo.run_time_column} >= %(win_from)s"
            if window.end is not None:
                self.params["win_to"] = window.end
                time_clause += f" AND {geo.run_time_column} < %(win_to)s"
        units = ", ".join(geo.unit_columns)
        return (f"runs AS (SELECT {geo.run_key_column} AS run_key, {units}, "
                f"{geo.run_method_column} AS method, {geo.run_time_column} AS run_at "
                f"FROM {finding_kinds.RUN_TABLE} "
                f"WHERE {geo.run_method_column} = ANY(%(all_methods)s){time_clause})")

    def _kind_ctes(self, kind, i):
        """`scanned_i` / `agg_i` for one kind. Both keyed by the geometry's unit columns,
        both at most one row per chip, so the outer LEFT JOINs cannot fan out and the
        denominators stay exact."""
        geo = self.geo
        units = ", ".join(geo.unit_columns)
        qualified = ", ".join(f"r.{c}" for c in geo.unit_columns)
        table = finding_kinds.observation_table(kind)
        spec = finding_kinds.spec(kind)
        self.params[f"m{i}"] = finding_kinds.methods(kind)
        extent = spec.get("extent_columns") or []
        # The extent MEASURE is the product of the declared geometry columns. Named from
        # the registry and never assumed: `void_obs` is radius x radius, `delam_obs` is
        # extent x extent, and a kind declaring three columns multiplies three.
        extent_expr = "NULL::double precision"
        if extent:
            for column in extent:
                finding_kinds.observation_table(kind)  # identifier validation reuse
            extent_expr = " * ".join(f"o.{c}" for c in extent)
        return [
            (f"scanned_{i} AS (SELECT DISTINCT {units} FROM runs "
             f"WHERE method = ANY(%(m{i})s))"),
            (f"agg_{i} AS (SELECT {qualified}, count(*) AS n, "
             f"avg({extent_expr}) AS extent "
             f"FROM {table} o "
             f"JOIN runs r ON r.run_key = o.{geo.observation_run_ref_column} "
             f"AND r.method = ANY(%(m{i})s) "
             f"GROUP BY {qualified})"),
        ]

    def _build(self, window):
        unit_cte, unit_keys, units = self._unit_cte()
        unit_list = ", ".join(units)
        parts = [self._runs_cte(window), unit_cte]
        # one time axis for the whole row, from the runs — NOT from the bridge relation.
        # MEASURED: `bonding_log.event_time` is one identical string across all 352,500
        # synthetic rows, so it cannot order production; `inspection_run.observed_at`
        # spans months and can.
        parts.append(
            f"chip_time AS (SELECT {unit_list}, min(run_at) AS first_at, "
            f"max(run_at) AS last_at FROM runs GROUP BY {unit_list})")
        for i, kind in enumerate(self.kinds):
            parts.extend(self._kind_ctes(kind, i))

        selects = ["u.row_value", "count(*) AS universe",
                   "min(t.first_at) AS first_at", "max(t.last_at) AS last_at"]
        joins = [f"LEFT JOIN chip_time t ON "
                 + " AND ".join(f"t.{c} = u.{k}" for c, k in zip(units, unit_keys))]
        for i, kind in enumerate(self.kinds):
            on_scanned = " AND ".join(f"s{i}.{c} = u.{k}"
                                      for c, k in zip(units, unit_keys))
            on_agg = " AND ".join(f"a{i}.{c} = u.{k}" for c, k in zip(units, unit_keys))
            joins.append(f"LEFT JOIN scanned_{i} s{i} ON {on_scanned}")
            joins.append(f"LEFT JOIN agg_{i} a{i} ON {on_agg}")
            scanned_flag = f"s{i}.{units[0]} IS NOT NULL"
            selects.extend([
                f"count(*) FILTER (WHERE {scanned_flag}) AS scanned_{i}",
                f"count(*) FILTER (WHERE {scanned_flag} AND a{i}.n > 0) AS found_{i}",
                f"sum(a{i}.n) FILTER (WHERE {scanned_flag}) AS events_{i}",
                f"avg(a{i}.extent) FILTER (WHERE {scanned_flag}) AS extent_{i}",
            ])
        # 🔴 THE WINDOW HAS TO REACH THE ROW SET, NOT ONLY THE CELLS.
        #
        # The driving table is `unit` — the chip→row bridge, which is a fact about what was
        # BONDED and knows nothing about time. `runs` is the only windowed relation, and it
        # arrives through LEFT JOINs, so before this clause a window narrowed the
        # measurements and left every row standing: measured on the restarted server,
        # `window=1990-01-01..1990-01-02` returned all 2,600 wafers with every cell
        # 「미검사」, under a `window.applied` block claiming the filter had run. `/siblings`
        # answered `state: "empty"` for the same window, because its population is defined
        # THROUGH the windowed runs — so the two endpoints disagreed about what a window
        # means, and the console is about to draw them side by side.
        #
        # `HAVING` rather than an inner join, deliberately: an inner join would also shrink
        # `universe` (`count(*)`), which is the third bucket's denominator — how many chips
        # this row HAS, a structural fact that no window may edit. So the row must have at
        # least one chip with a run inside the window to appear, and the row's own size is
        # still reported in full. Undeclared window keeps every row, never-scanned rows
        # included, which is what `geometry.universe` exists to make expressible.
        # Counted on a unit column rather than on `first_at`: a run with a NULL timestamp
        # would make `min(run_at)` null and drop a row that genuinely has runs. Under a
        # declared window such a run is already excluded by the time clause, so the two
        # spellings agree today — but only one of them stays right without that argument.
        having = (f"\nHAVING count(t.{units[0]}) > 0" if window.declared else "")
        return ("WITH " + ",\n".join(parts) + "\nSELECT " + ",\n       ".join(selects)
                + "\nFROM unit u\n" + "\n".join(joins)
                + "\nGROUP BY u.row_value" + having
                + "\nORDER BY min(t.first_at) NULLS LAST, u.row_value")


# --------------------------------------------------------------------------- cells
def _cell(column, kind_index, row, has_denominator):
    """One cell, with `state` decided BEFORE any arithmetic.

    🔴 The order of these branches is the contract. `unscanned` is decided from the
    DENOMINATOR being zero and never from the numerator being zero, because those are the
    two facts an operator most needs told apart and the numerator cannot tell them apart.
    """
    scanned = row.get(f"scanned_{kind_index}") or 0
    found = row.get(f"found_{kind_index}") or 0
    events = row.get(f"events_{kind_index}")
    extent = row.get(f"extent_{kind_index}")
    aggregate, spec = column.aggregate, column.spec

    if column.state == COLUMN_UNMEASURABLE:
        return {"column": column.id, "state": CELL_UNMEASURABLE,
                "value": None, "n": None, "of": None}
    if spec["needs_denominator"] and not has_denominator:
        return {"column": column.id, "state": CELL_NO_DENOMINATOR,
                "value": None, "n": None, "of": None}

    if aggregate == "found_rate":
        if scanned == 0:
            return _unscanned(column, found, scanned)
        return _measured(column, found / scanned, found, scanned)
    if aggregate == "found_count":
        return _measured(column, found, found, None)
    if aggregate == "scanned":
        return _measured(column, scanned, scanned, None)
    if aggregate == "event_count":
        return _measured(column, int(events or 0), int(events or 0), None)
    if aggregate == "per_chip":
        if scanned == 0:
            return _unscanned(column, events, scanned)
        return _measured(column, float(events or 0) / scanned, int(events or 0), scanned)
    if aggregate == "extent_mean":
        # 🔴 The denominator here is FOUND, not scanned: a chip with no void has no void
        # size, and averaging a zero in for it would drag every lot's mean toward zero in
        # proportion to how well it did. `of` therefore reports `found`.
        if found == 0:
            return _unscanned(column, None, found)
        return _measured(column, float(extent) if extent is not None else None,
                         found, found)
    raise LotGridRequestError({
        "reason": REASON_UNKNOWN_AGGREGATE, "aggregate": aggregate,
        "message": f"집계 {aggregate!r}에 계산 규칙이 없다"})


def _measured(column, value, n, of):
    return {"column": column.id, "state": CELL_MEASURED,
            "value": _round(value), "n": n, "of": of}


def _unscanned(column, n, of):
    """🔴 `value` is null and it renders 「—」. It is NOT zero and NOT clean."""
    return {"column": column.id, "state": CELL_UNSCANNED,
            "value": None, "n": None, "of": of}


def _round(value, places=6):
    if value is None:
        return None
    if isinstance(value, int):
        return value
    try:
        return round(float(value), places)
    except (TypeError, ValueError):
        return None


def _baseline(cells, thresholds):
    """The median of the cells that COUNT TOWARD the baseline, plus what was excluded.

    Median rather than mean for a stated reason: one extreme lot is exactly what this
    screen exists to surface, and with a mean that lot raises the bar it is judged
    against and partly hides itself.
    """
    values = [c["value"] for c in cells
              if c["state"] == CELL_MEASURED and c["value"] is not None
              and c.get("_counts")]
    excluded = sum(1 for c in cells if c["state"] == CELL_MEASURED and not c.get("_counts"))
    if not values:
        return {"value": None, "basis": BASELINE_MEDIAN_OF_ROWS, "n_rows": 0,
                "excluded_rows": excluded, "excluded_reason": None}
    values.sort()
    mid = len(values) // 2
    median = (values[mid] if len(values) % 2
              else (values[mid - 1] + values[mid]) / 2.0)
    return {"value": _round(median), "basis": BASELINE_MEDIAN_OF_ROWS,
            "n_rows": len(values), "excluded_rows": excluded,
            "excluded_reason": "bucket_not_production" if excluded else None}


def _level(value, baseline, thresholds):
    """`(ratio_to_baseline, level)` — SERVED, because the client cannot know the baseline's
    exclusions. A zero baseline yields `None` rather than an infinity: 「기저가 0이라
    배수가 없다」 is a real answer and `inf` is not a number a screen can paint."""
    if value is None or not baseline or not baseline.get("value"):
        return None, None
    ratio = float(value) / float(baseline["value"])
    level = 0
    for step in thresholds:
        if ratio >= step["at"]:
            level = step["level"]
    return _round(ratio, 3), level


# --------------------------------------------------------------------------- the answer
def lots(connection, columns=None, by=None, window=None, kind=None, limit=None,
         offset=None, now=None):
    """The whole grid, in the pinned envelope. Read-only: never writes, never DDLs."""
    now = now or datetime.now(timezone.utc)
    config = ledger_siblings.load_axes_config()
    requested_window = ledger_siblings.parse_window(window, now=now)

    resolved = parse_columns(columns, default=default_columns())
    axis_kind = kind or resolved[0].kind
    source, axis = resolve_row_axis(config, axis_kind, by)
    geometry, _attribution = config.for_kind(axis_kind)

    # 🔴 REFUSE BEFORE ANY WORK, RATHER THAN ECHO AFTERWARDS. `_runs_cte` can only apply a
    # window through `geometry.run_time_column`; without one it silently emits no time
    # clause. That branch used to run all the way to a `window.applied` block, which is the
    # false statement this route was reported for. An honest refusal is fine here — the
    # caller asked for something this axis cannot do, and now it is told which.
    if requested_window.declared and not geometry.run_time_column:
        raise LotGridRequestError({
            "reason": REASON_WINDOW_NOT_APPLICABLE,
            "window": window, "kind": axis_kind, "axis": axis.name,
            "message": (f"{axis.label or axis.name} 축은 기간으로 좁힐 수 없다 — "
                        f"{axis_kind} 기하가 run_time_column을 선언하지 않았다. "
                        f"window 없이 요청할 것")})

    plan = _GridPlan(geometry, source, axis, resolved, requested_window)

    # -- the gate, BEFORE the scan ------------------------------------------------
    relations = [source.relation, finding_kinds.RUN_TABLE]
    for column in resolved:
        table = finding_kinds.observation_table(column.kind)
        if table not in relations:
            relations.append(table)
    # 🔴 The gate may FORCE a window, so it inherits the same rule: forcing one onto an
    # axis that cannot apply it would manufacture the very `applied` lie the refusal above
    # exists to prevent — this time on a request that declared nothing and did nothing
    # wrong. A geometry with no run time column keeps the all-time grid and the gate says
    # `forced: false`, which is true.
    applied_window, gate = (
        apply_size_gate(connection, relations, requested_window, now=now)
        if geometry.run_time_column
        else apply_size_gate(connection, relations, requested_window, now=now,
                             may_force=False))
    if gate["forced"]:
        logger.warning("lot grid windowed to %s: %s bytes over %s",
                       LARGE_GRID_WINDOW, gate["total_bytes"], FULL_GRID_MAX_BYTES)
        plan = _GridPlan(geometry, source, axis, resolved, applied_window)

    # -- a column whose relation is not deployed is UNMEASURABLE, not zero ---------
    absent = set(gate["absent_relations"])
    for column in resolved:
        if finding_kinds.observation_table(column.kind) in absent:
            column.state, column.reason = COLUMN_UNMEASURABLE, REASON_RELATION_ABSENT

    if source.relation in absent or finding_kinds.RUN_TABLE in absent:
        return _envelope(STATE_ABSENT, resolved, axis, source, config, axis_kind,
                         [], requested_window, applied_window, gate, relations, now,
                         note="행 축 또는 검사 릴레이션 미배포 — 마이그레이션 미실행")

    rows = _run(connection, plan)
    state = STATE_READY if rows else STATE_EMPTY
    body = _envelope(state, resolved, axis, source, config, axis_kind, rows,
                     requested_window, applied_window, gate, relations, now,
                     limit=limit, offset=offset)
    return body


def _run(connection, plan):
    """Execute the one pass and return dict rows keyed by the SELECT aliases.

    The alias list is rebuilt from `plan.kinds` in the same order `_GridPlan` emitted
    them, so the mapping is positional by construction rather than by a name the database
    round-trips — `_fetch` returns bare tuples on both connection shapes it supports.
    """
    raw = _fetch(connection, plan.sql, plan.params)
    names = ["row_value", "universe", "first_at", "last_at"]
    for i, _kind in enumerate(plan.kinds):
        names.extend([f"scanned_{i}", f"found_{i}", f"events_{i}", f"extent_{i}"])
    return [dict(zip(names, row)) for row in raw]


def _envelope(state, columns, axis, source, config, axis_kind, raw_rows,
              requested_window, applied_window, gate, relations, now,
              limit=None, offset=None, note=None):
    """The pinned response. Every field the client branches on is a FIELD."""
    kind_index = {}
    for column in columns:
        if column.kind not in kind_index:
            kind_index[column.kind] = len(kind_index)

    thresholds = DEFAULT_THRESHOLDS
    rows, per_column = [], {c.id: [] for c in columns}
    for order, raw in enumerate(raw_rows):
        bucket = dict(BUCKET_UNKNOWN)
        cells = []
        for column in columns:
            cell = _cell(column, kind_index[column.kind], raw,
                         finding_kinds.has_denominator(column.kind))
            cell["_counts"] = bucket["counts_toward_baseline"]
            per_column[column.id].append(cell)
            cells.append(cell)
        rows.append({
            "row": raw["row_value"],
            "label": raw["row_value"],
            "order_index": order,
            "occurred_at": {
                "first": raw["first_at"].isoformat() if raw.get("first_at") else None,
                "last": raw["last_at"].isoformat() if raw.get("last_at") else None},
            "bucket": bucket,
            "universe": int(raw["universe"] or 0),
            "cells": cells,
        })

    baselines = {c.id: _baseline(per_column[c.id], thresholds) for c in columns}
    for row in rows:
        for cell in row["cells"]:
            ratio, level = _level(cell["value"], baselines[cell["column"]], thresholds)
            cell["ratio_to_baseline"], cell["level"] = ratio, level
            cell.pop("_counts", None)

    total = len(rows)
    start = int(offset or 0)
    end = total if limit is None else start + int(limit)
    page = rows[start:end]

    notes = []
    if note:
        notes.append({"code": "relation_absent", "message": note})
    if gate["forced"]:
        notes.append({
            "code": REASON_GRID_TOO_LARGE,
            "message": (f"스캔 대상 {gate['total_bytes']:,}B가 상한 "
                        f"{gate['max_bytes']:,}B를 넘어 window를 "
                        f"{LARGE_GRID_WINDOW}로 강제했다 — 전 기간 아님")})

    return {
        "state": state,
        "generated_at": now.isoformat(),
        "row_axis": {"name": axis.name, "label": axis.label, "about": axis.about,
                     "relation": source.relation, "column": axis.column,
                     "source": f"{source.relation}.{axis.column}"},
        "axes_available": axes_available(config, axis_kind),
        "columns": [c.as_dict(baselines[c.id], thresholds) for c in columns],
        "aggregates_available": [
            dict(name=name, **{k: v for k, v in spec.items()})
            for name, spec in sorted(AGGREGATES.items())],
        "rows": page,
        "populations": {"rows_total": total, "rows_returned": len(page),
                        "rows_truncated": len(page) < total},
        "window": {
            "requested": requested_window.as_dict(),
            "applied": applied_window.as_dict(),
            "forced": gate["forced"], "forced_reason": gate["reason"]},
        "gate": {"total_bytes": gate["total_bytes"], "max_bytes": gate["max_bytes"],
                 "relations": gate["relations"],
                 "absent_relations": gate["absent_relations"]},
        "notes": notes,
        "provenance": _provenance(relations, gate),
    }


# ------------------------------------------------------------------- the three-axis map
#: The projections `GET /api/ledger/lot_map` serves, DECLARED rather than branched on.
#:
#: 🔴 THE BONDING AND DT AXES COST NO EXTRA JOIN. Both `bond_x/bond_y` and `dt_x/dt_y` sit
#: on THE SAME `bonding_log` row the declared chip→lot bridge already lands on, so two of
#: the three projections are free. This is the finding that replaced the brief's original
#: plan (「투영은 transferred 걷기」), which is not implementable: MEASURED 2026-08-14, no
#: `transferred` atom carries a chip coordinate (`position` is None at every emit site) and
#: `ledger_trace.LINEAGE_PREDICATES` does not contain `transferred` at all.
#:
#: 🔴 THE CORE AXIS IS DECLARED AND UNREACHABLE FROM HERE, AND SAYS SO. See the module
#: docstring for the measurement history — including a 2026-08-18 "correction" that claimed
#: these columns do not exist, which was taken against an empty database and is wrong. On
#: `assy_manager` they exist and are ~24% populated. The axis is unreachable not because the
#: coordinate is absent but because reaching it needs a
#: NEW side join into `dt_log`, which ruling R-2026-08-14-D forbids. It is therefore listed
#: — not hidden — at `state: "unreachable"`, because an axis missing from the screen and an
#: axis with no data are different answers and the operator would read the second from the
#: first. Same rule as `ledger_structure`'s honest-empty-axis.
MAP_AXES = [
    {"axis": "bond", "label": "본딩축", "sublabel": "스테이지 좌표",
     "x_column": "bond_x", "y_column": "bond_y",
     "frame_key_columns": ["bond_lot", "bond_slot"]},
    {"axis": "dt", "label": "DT축", "sublabel": "테이프 좌표",
     "x_column": "dt_x", "y_column": "dt_y",
     "frame_key_columns": ["dt_lot", "dt_slot"]},
    {"axis": "core", "label": "코어축", "sublabel": "웨이퍼 좌표",
     "x_column": "cx", "y_column": "cy",
     "frame_key_columns": ["core_lot", "core_slot"]},
]

#: 🔴 THREE VERDICTS, BECAUSE THERE ARE THREE SITUATIONS AND THEY LOOK THE SAME IF MERGED.
#:
#:   ready         coordinates AND a registered frame — draw it.
#:   no_frame      coordinates exist, NO registered frame to draw them on. The cells are
#:                 still served (hiding measured data is not honesty), but the client MUST
#:                 NOT invent a grid for them — owner constraint 3, 「목업의 원형 격자는
#:                 시늉이다」. A plausible wrong grid is worse than no grid: every
#:                 coordinate on it is off by the difference and nothing on screen says so.
#:   unreachable   no coordinates at all for this axis on these rows.
MAP_STATE_READY = "ready"
MAP_STATE_NO_FRAME = "no_frame"
MAP_STATE_UNREACHABLE = "unreachable"

#: 🔴 THE MIDDLE LAYER. `cells[]` used to be the FOUND SET ALONE — `counts[key]` was built
#: inside `if not r.get("is_found"): continue` — so every map was a numerator with no
#: denominator under it and 「보이드 26개」 had nothing to be 26 OF. The scanned positions
#: were computed in the same loop, counted into `scanned`, and then thrown away.
#:
#: THREE values, not the two the brief asked for, and the third is the reason: measured on
#: `SYN-BW-101-07`, 141 bonded positions carry 29 scanned and 26 found. Tagging the other
#: 112 as `scanned` would be a false claim about 112 of 141 positions — the exact 「미검사와
#: 0은 다른 답」 rule this file already enforces in its grid cells (`CELL_UNSCANNED`). So the
#: same three-way split the populations use, spelled the same way:
#:   found      inspected, and something was found here
#:   scanned    inspected, nothing found — the denominator the finding is a fraction of
#:   unscanned  present in the process record, never inspected. NOT a zero.
#:
#: ⚠️ `cells[]` IS THEREFORE NO LONGER THE FOUND SET. A consumer that drew every cell as a
#: finding now draws 141 where it drew 26 and must filter on `state`. `n` keeps its exact
#: meaning (findings at this position, so 0 on the other two states) so nothing that reads
#: it shifts.
MAP_CELL_FOUND = "found"
MAP_CELL_SCANNED = "scanned"
MAP_CELL_UNSCANNED = "unscanned"
MAP_REASON_NO_BRIDGE = "no_live_bridge"
MAP_REASON_NO_FRAME = "no_registered_frame"
#: 🔴 CAUGHT BY ITS OWN SMOKE TEST, 2026-08-14, and named so it cannot come back. With no
#: `slot` the first draft picked the FIRST slot it saw and drew all 25 slots' chips onto
#: that one slot's grid — 125 cells on a frame that holds one slot's worth. Every
#: coordinate was real and the picture was fiction. A row spanning more than one frame is
#: now REFUSED with the slot list, never flattened.
MAP_REASON_FRAME_AMBIGUOUS = "frame_ambiguous_across_slots"

#: Where a registered frame's geometry lives. The map is drawn on THIS, never on a circle
#: this module invented — owner constraint 3 (「목업의 원형 격자는 시늉이다」).
FRAME_RELATION = "wafer_map_metadata"
#: 🔴 NOT TYPED HERE. `map_overlay.VALID_DIE_TABLE` is the PINNED storage table of valid-die
#: maps (user ruling 2026-08-04), and the name itself is declared by
#: `product_tables.PRODUCT_TABLES` — a deployment that spells its floor differently changes
#: the declaration and this module follows. It used to be a literal in this file, which made
#: it a SECOND spelling of a name that already had an owner.
VALID_DIE_RELATION = map_overlay.VALID_DIE_TABLE

#: 🔴 WHO THE FRAME IS. The owner asked for the map strip to be listed by the BONDED BASE
#: WAFER and labelled with its id (`SCENARIO_CONSOLE_BRIEF` P0 item 5, 「본딩 base wf 축으로
#: 리스트」). `map_id` is `{lot}_{slot}`, which is the frame's key and not the wafer's name,
#: so the client had nothing to put under a wafer heading that was not an invention.
#:
#: `IDENTITY_FIELD` is FIXED because it is a landed client contract —
#: `surprise_map_core.waferLabelOf` reads `frame.wafer` and upgrades the label the moment it
#: arrives. Only the VALUE is declared, and the declaration is `siblings_axes.json`'s
#: `geometry.ledger_subject.column` (the unit column the config already declares to BE the
#: wafer subject's key) mapped through the attribution source's own `join` into that
#: relation's spelling. NO TABLE OR COLUMN NAME IS TYPED HERE: a deployment that declares
#: another subject column, or another relation that spells it differently, gets its identity
#: on the wire by swapping declarations alone.
IDENTITY_FIELD = "wafer"
#: The alias it is fetched under — the row tuples are zipped positionally against `names`,
#: so the identity must not be able to collide with a frame key column's own name.
IDENTITY_ALIAS = "frame_identity"


def lot_map(connection, row, kind=None, by=None, slot=None, window=None, now=None):
    """One marked row's defective chips, projected onto every declared axis.

    🔴 COORDINATES ARE CELL COUNTS FROM ORIGIN. Nothing here multiplies by a pitch and
    nothing emits a millimetre — this project has a standing lesson that converting cell
    counts to physical distance manufactures defects that do not exist.

    ⚠️ A ROW IS NOT ONE FRAME. MEASURED: a bond lot spans 25 slots and each slot is a
    SEPARATELY REGISTERED frame with its own grid (11x11, 12x12, 12x13, 13x13 ... on this
    box), so there is no single grid a whole lot can be drawn on. `slot` selects one; with
    no `slot` the response lists the frames available and draws none, rather than
    flattening incompatible grids on top of each other and calling the result a wafer.

    ⚠️ AND `slot` BELONGS TO EXACTLY ONE FAMILY — the row axis's (see `_slot_column_for`),
    named back in `slot_column`. It narrows ROWS; it never picks a frame. Each projection
    derives its frame key from ITS OWN lot/slot pair on the surviving rows, so a request
    for bonding slot 3 cannot make the core axis look up a core frame numbered 3.
    """
    now = now or datetime.now(timezone.utc)
    config = ledger_siblings.load_axes_config()
    the_kind = kind or finding_kinds.DEFAULT_KIND
    requested_window = ledger_siblings.parse_window(window, now=now)
    source, axis = resolve_row_axis(config, the_kind, by)
    geometry, _attribution = config.for_kind(the_kind)

    if not relation_exists(connection, source.relation):
        return {"row": row, "state": STATE_ABSENT, "projections": [],
                "message": f"{source.relation} 미배포"}

    methods = finding_kinds.methods(the_kind)
    table = finding_kinds.observation_table(the_kind)
    units = geometry.unit_columns
    join_pairs = list(source.join.items())

    params = {"row": row, "methods": methods}
    time_clause = ""
    if requested_window.declared and geometry.run_time_column:
        if requested_window.start is not None:
            params["win_from"] = requested_window.start
            time_clause += f" AND {geometry.run_time_column} >= %(win_from)s"
        if requested_window.end is not None:
            params["win_to"] = requested_window.end
            time_clause += f" AND {geometry.run_time_column} < %(win_to)s"
    slot_clause = ""
    # 🔴 THE SLOT NARROWS ROWS IN THE ROW AXIS'S OWN FAMILY, AND NOWHERE ELSE. See
    # `_slot_column_for`. A row axis with no frame family (`bond_eqp`, `b_bn`, ...) has no
    # slot to be narrowed by, so nothing is narrowed and `slot_column` below says so — the
    # response never implies a filter it did not run.
    slot_column = _slot_column_for(axis)
    if slot_column and not _column_present(connection, source.relation, slot_column):
        slot_column = None
    if slot and slot_column:
        params["slot"] = slot
        slot_clause = f" AND b.{slot_column} = %(slot)s"
    else:
        slot_column = None

    projected = ", ".join(
        f"b.{a['x_column']} AS {a['axis']}_x, b.{a['y_column']} AS {a['axis']}_y"
        for a in MAP_AXES if _column_present(connection, source.relation, a["x_column"]))
    if not projected:
        return {"row": row, "state": STATE_EMPTY, "projections": [],
                "message": f"{source.relation}에 투영 가능한 좌표 컬럼이 없다"}

    key_cols = ", ".join(f"b.{c}" for c in _frame_key_columns(connection,
                                                             source.relation))
    # The bonded base wafer's declared identity, on the SAME row the bridge already lands
    # on — no new relation, so ruling R-2026-08-14-D is untouched and the column is free.
    identity_column = _identity_column(connection, geometry, source)
    identity_select = (f", b.{identity_column} AS {IDENTITY_ALIAS}"
                       if identity_column else "")
    sql = f"""
WITH runs AS (
    SELECT {geometry.run_key_column} AS run_key, {', '.join(units)}
    FROM {finding_kinds.RUN_TABLE}
    WHERE {geometry.run_method_column} = ANY(%(methods)s){time_clause}
), found AS (
    SELECT DISTINCT {', '.join('r.' + c for c in units)}
    FROM {table} o JOIN runs r ON r.run_key = o.{geometry.observation_run_ref_column}
), scanned AS (
    SELECT DISTINCT {', '.join(units)} FROM runs
)
SELECT {projected}{',' if key_cols else ''} {key_cols}{identity_select},
       (f.{units[0]} IS NOT NULL) AS is_found,
       (s.{units[0]} IS NOT NULL) AS is_scanned
FROM {source.relation} b
LEFT JOIN found f ON """ + " AND ".join(
        f"f.{ours} = b.{theirs}" for ours, theirs in join_pairs) + """
LEFT JOIN scanned s ON """ + " AND ".join(
        f"s.{ours} = b.{theirs}" for ours, theirs in join_pairs) + f"""
WHERE b.{axis.column} = %(row)s{slot_clause}
"""
    raw = _fetch(connection, sql, params)
    return _map_envelope(connection, row, axis, source, slot, slot_column, the_kind, raw,
                         projected, requested_window, now, identity_column)


def _identity_column(connection, geometry, source):
    """The column on `source.relation` that NAMES the bonded base wafer, or `None`.

    🔴 REACHED THROUGH THE DECLARATION, TWO HOPS, AND NEITHER HOP IS A LITERAL:

        geometry.ledger_subject.column   the UNIT column the config declares to be the
                                         wafer subject's key (`base_wafer_id`). Declared
                                         rather than `unit_columns[0]` — see `Geometry`,
                                         which pays for that distinction already.
        source.join[<that>]              that unit column in THIS relation's own spelling
                                         (`bonding_log.base_id`; `inspection_run` spells
                                         it `base_wafer_id`, and the join says so).

    `None` when the geometry declares no ledger subject, when this relation's join does not
    carry it, or when the column is not deployed — three ways of having no declared
    identity, and all three answer the same way: the field is simply not on the wire. That
    is the honest answer rather than a fallback to the frame key, which would put a
    `{lot}_{slot}` on screen under a wafer heading.
    """
    subject = getattr(geometry, "ledger_subject", None) if geometry else None
    if not subject:
        return None
    column = (source.join or {}).get(subject.get("column"))
    if not column or not _column_present(connection, source.relation, column):
        return None
    return column


def _column_present(connection, relation, column):
    rows = _fetch(connection,
                  "SELECT 1 FROM information_schema.columns "
                  "WHERE table_name = %(rel)s AND column_name = %(col)s",
                  {"rel": relation, "col": column})
    return bool(rows)


def _frame_key_columns(connection, relation):
    present = []
    for spec in MAP_AXES:
        for column in spec["frame_key_columns"]:
            if column not in present and _column_present(connection, relation, column):
                present.append(column)
    return present


def _slot_column_for(axis):
    """The slot column of the ROW AXIS's own frame family, or None if it has none.

    🔴 THE DOCSTRING WAS RIGHT AND THE CODE WAS WRONG (2026-08-14), and the tell was in
    the signature: this took a `source` it never read, and `return`ed inside the loop on
    the FIRST declared family, so it answered `bond_slot` for every row axis there is.
    That is a loop written to look like a lookup. Judged in favour of the docstring, for a
    reason that is not taste:

    `slot` narrows the rows of `row`, and `row` is a value of `axis.column`. A bond lot is
    subdivided by `bond_slot`, a DT lot by `dt_slot` — THREE DIFFERENT SLOT SPACES, in
    which the token "3" names three different physical objects. Filtering a `by=dt_lot`
    row on `bond_slot` keeps an arbitrary cross-section of that DT lot and hands it to the
    frame logic as if it were one frame's worth, which is the same fiction
    `MAP_REASON_FRAME_AMBIGUOUS` is named after, one layer earlier.

    ⚠️ AND `None` IS AN ANSWER, NOT A GAP. A row axis that is not a lot at all
    (`bond_eqp`, `b_bn`, `stack_height`) has no frame family, so there is no column a
    `slot` could mean. Borrowing the first family's would narrow on a slot space the
    caller never named — 「다른 축의 슬롯을 빌려다 쓰면 안 된다」 (lead PM, 2026-08-14).
    The caller reports the `None` as `slot_column: null` so the screen can see that its
    `slot` bought nothing, rather than reading an unnarrowed row as one slot's picture.
    """
    for spec in MAP_AXES:
        lot_col, slot_col = spec["frame_key_columns"]
        if lot_col and slot_col and lot_col == axis.column:
            return slot_col
    return None


def _map_envelope(connection, row, axis, source, slot, slot_column, kind, raw, projected,
                  window, now, identity_column=None):
    """Every declared axis, each carrying its own verdict. An axis with no data is
    PRESENT and says why — it is never dropped."""
    names = []
    for spec in MAP_AXES:
        if f"{spec['axis']}_x" in projected:
            names.extend([f"{spec['axis']}_x", f"{spec['axis']}_y"])
    key_columns = _frame_key_columns(connection, source.relation)
    names.extend(key_columns)
    if identity_column:
        names.append(IDENTITY_ALIAS)
    names.extend(["is_found", "is_scanned"])
    rows = [dict(zip(names, r)) for r in raw]

    projections = []
    for spec in MAP_AXES:
        ax = spec["axis"]
        xk, yk = f"{ax}_x", f"{ax}_y"
        if xk not in names:
            projections.append({
                "axis": ax, "label": spec["label"], "sublabel": spec["sublabel"],
                "state": MAP_STATE_UNREACHABLE, "reason": MAP_REASON_NO_BRIDGE,
                "message": (f"{source.relation}에 {spec['x_column']} 컬럼이 없다 — "
                            f"이 축으로 가는 선언된 경로 없음"),
                "frame": None, "cells": [], "found": 0, "scanned": 0})
            continue
        present = [r for r in rows if r.get(xk) is not None and r.get(yk) is not None]
        if not present:
            projections.append({
                "axis": ax, "label": spec["label"], "sublabel": spec["sublabel"],
                "state": MAP_STATE_UNREACHABLE, "reason": MAP_REASON_NO_BRIDGE,
                "message": (f"{source.relation}.{spec['x_column']}가 이 행에서 전부 "
                            f"NULL — 좌표가 기록되지 않았다 (새 옆조인 금지: "
                            f"R-2026-08-14-D)"),
                "frame": None, "cells": [], "found": 0, "scanned": 0})
            continue
        # 🔴 EVERY PRESENT POSITION, not the found ones. See `MAP_CELL_*`.
        counts = {}
        found = scanned = 0
        for r in present:
            key = (int(r[xk]), int(r[yk]))
            cell = counts.setdefault(key, {"n": 0, "scanned": 0})
            if r.get("is_scanned"):
                scanned += 1
                cell["scanned"] += 1
            if r.get("is_found"):
                found += 1
                cell["n"] += 1
        lot_col, slot_col = spec["frame_key_columns"]
        # 🔴 THE FRAME KEYS ARE COUNTED, NOT SAMPLED. Picking the first value seen is what
        # produced the fiction this constant is named for (`MAP_REASON_FRAME_AMBIGUOUS`).
        #
        # 🔴 AND EVERY AXIS READS ITS OWN PAIR — `bond_lot`/`bond_slot`, `dt_lot`/`dt_slot`,
        # `core_lot`/`core_slot`. This line used to override the slot with the REQUEST's
        # `slot` for every axis at once (`str(slot) if slot else ...`), which is a bonding
        # slot: the filter that produced it is `b.bond_slot = %(slot)s`. So the core axis
        # looked its frame up at `wafer_map_metadata` under `{core_lot}_{bond_slot}` — a
        # key made of two unrelated families. It was invisible only because the core axis
        # is `unreachable` on this box today; the day core coordinates arrive it becomes A
        # PLAUSIBLE WRONG GRID, which is the one outcome `_frame`'s docstring says is worse
        # than no grid at all (「지어낸 격자는 없는 결함을 만든다」).
        #
        # The override was not merely wrong, it was REDUNDANT where it was right: the
        # WHERE clause has already narrowed `present` to the requested slot, so for the
        # filtered axis `slots_seen` IS `[slot]`, spelled the way the column stores it —
        # which is the spelling `map_id` needs. Deriving it costs nothing and cannot cross
        # a family. (Fixed 2026-08-14, ahead of the fixture lane's `core_slot != bond_slot`
        # corpus, so the repair is not shaped by the sample that exposes it.)
        lots_seen = {r.get(lot_col) for r in present if r.get(lot_col)}
        slots_seen = sorted({str(r.get(slot_col)) for r in present if r.get(slot_col)})
        frame_lot = next(iter(lots_seen)) if len(lots_seen) == 1 else None
        frame_slot = slots_seen[0] if len(slots_seen) == 1 else None
        # 🔴 THE WAFER IS COUNTED, NOT SAMPLED — the same rule as the frame keys above, for
        # the same reason. MEASURED on `assy_manager` 2026-08-14: `base_id` and the BONDING
        # frame key are a bijection (2,575 ↔ 2,575), so this resolves on the bonding axis
        # and the strip gets its label. It does NOT resolve on the DT axis, where one frame
        # carries dies from many base wafers — and there the field is absent rather than
        # naming whichever wafer the first row happened to be, which is how a strip would
        # come to label 25 wafers' dies with one wafer's id.
        wafers_seen = {r.get(IDENTITY_ALIAS) for r in present if r.get(IDENTITY_ALIAS)}
        frame_wafer = next(iter(wafers_seen)) if len(wafers_seen) == 1 else None
        cells = [{"x": x, "y": y, "n": c["n"],
                  "state": (MAP_CELL_FOUND if c["n"]
                            else MAP_CELL_SCANNED if c["scanned"]
                            else MAP_CELL_UNSCANNED)}
                 for (x, y), c in sorted(counts.items())]
        # 🔴 THE PAIRS, NOT THE CROSS PRODUCT of `lots_seen` x `slots_seen`. A wafer's dies
        # come off 25 DT tapes; pairing every lot with every slot would ask the frame table
        # about combinations that were never used and then report them as unregistered.
        pairs_seen = sorted({(r.get(lot_col), r.get(slot_col)) for r in present
                             if r.get(lot_col) and r.get(slot_col)})

        if frame_slot is None or frame_lot is None:
            # 🔴 TWO SITUATIONS, TWO SENTENCES. 「슬롯을 고르십시오」 is actionable advice
            # when the row spans several frames and an INSTRUCTION TO DO THE IMPOSSIBLE
            # when this axis records no frame key at all — the core axis's case the moment
            # it has coordinates but `core_lot`/`core_slot` are unrecorded or absent from
            # the relation. The token stays (the client's refusal vocabulary is a landed
            # contract); the sentence tells the truth about which one happened.
            unkeyed = not lots_seen or not slots_seen
            projections.append({
                "axis": ax, "label": spec["label"], "sublabel": spec["sublabel"],
                "state": MAP_STATE_NO_FRAME, "reason": MAP_REASON_FRAME_AMBIGUOUS,
                "message": (
                    (f"이 축의 프레임 키({lot_col}·{slot_col})가 이 행에 기록돼 있지 "
                     f"않다 — 좌표는 있으나 어느 프레임의 좌표인지 알 수 없다. 슬롯을 "
                     f"골라도 해결되지 않는다.")
                    if unkeyed else
                    ("이 행이 프레임 여러 개에 걸쳐 있다 — 슬롯마다 격자 치수가 "
                     "다르므로 한 장에 겹쳐 그리면 좌표가 전부 어긋난다. "
                     "slot을 지정할 것.")),
                # 🔴 A REFUSAL STILL CARRIES WHAT THE FRAMES AGREE ON. Refusing to pick ONE
                # frame is not a reason to withhold what all of them say: measured on
                # `SYN-BW-101-07`, the 25 DT frames it touches are all registered and all
                # describe the SAME 15x10 lattice, and the DT sheet could not be drawn only
                # because that agreement was never carried at wafer granularity.
                "frame": _with_identity(
                    dict({"state": MAP_STATE_NO_FRAME,
                          "reason": MAP_REASON_FRAME_AMBIGUOUS,
                          "available_slots": slots_seen,
                          "available_lots": sorted(str(x) for x in lots_seen)},
                         **_agreed_frame(connection, source.relation, pairs_seen)),
                    frame_wafer),
                "coordinate_unit": "cells_from_origin",
                "cells": cells, "found": found, "scanned": scanned})
            continue

        frame = _with_identity(
            _frame(connection, source.relation, frame_lot, frame_slot, spec), frame_wafer)
        projections.append({
            "axis": ax, "label": spec["label"], "sublabel": spec["sublabel"],
            # 🔴 The projection is only `ready` when there is a REGISTERED frame under it.
            # Cells without a frame are served but must not be drawn as a wafer.
            "state": (MAP_STATE_READY if frame.get("state") == MAP_STATE_READY
                      else MAP_STATE_NO_FRAME),
            "reason": (None if frame.get("state") == MAP_STATE_READY
                       else frame.get("reason")),
            "message": (None if frame.get("state") == MAP_STATE_READY
                        else frame.get("message")),
            "frame": frame,
            "coordinate_unit": "cells_from_origin",
            "cells": cells, "found": found, "scanned": scanned})

    return {
        "row": row, "state": STATE_READY if rows else STATE_EMPTY,
        "generated_at": now.isoformat(), "kind": kind,
        "row_axis": {"name": axis.name, "label": axis.label,
                     "source": f"{source.relation}.{axis.column}"},
        "slot": slot,
        # 🔴 WHICH COLUMN THE `slot` WAS ACTUALLY APPLIED TO, OR `null` FOR 「applied to
        # nothing」. Echoing `slot` alone lets a screen show an UNNARROWED row under a slot
        # heading: if the row happens to span one slot the projection resolves, and the
        # operator reads a whole equipment's chips as one slot's picture. The request and
        # what the query did are two facts, so the response carries both.
        "slot_column": slot_column,
        "window": window.as_dict(),
        "projections": projections,
        "provenance": {"source": PROVENANCE_SOURCE_TABLES, "ledger_backed": False,
                       "relations": [source.relation, finding_kinds.RUN_TABLE]},
    }


def _with_identity(frame, wafer):
    """Name the frame's bonded base wafer — or leave the field OFF, which is an answer.

    🔴 ABSENT IS A FACT HERE, AND IT HAS A MEASURED POPULATION. `assy_manager`, 2026-08-14:
    5 of 108 bond lots (`BS-2601-001`..`005`, 5,296 rows) carry NO `base_id` at all, and
    their frames are registered and still open. Those maps must keep opening and must not
    acquire a name — so nothing is invented, nothing falls back to `map_id`, and the frame
    is never dropped from the response. The client renders the frame key instead and marks
    it as such (`data-wafer-source="frame_key"`), so nothing on screen claims to be a wafer
    id that isn't one.
    """
    if wafer:
        frame[IDENTITY_FIELD] = str(wafer)
    return frame


def _frame(connection, relation, lot, slot, spec):
    """The REGISTERED frame for this (lot, slot), or a refusal that names what is missing.

    🔴 The grid is READ, never invented. `wafer_map_metadata.grid_metadata` carries
    `grid_cols`/`grid_rows`/`grid_start_x`/`grid_start_y`/`grid_y_invert`/`rotation`, and
    the client draws on exactly that. When no frame is registered the response says
    `no_registered_frame` rather than falling back to a circle, because a plausible wrong
    grid is worse than no grid: every coordinate on it would be off by the difference.
    """
    if not relation_exists(connection, FRAME_RELATION):
        return {"state": MAP_STATE_UNREACHABLE, "reason": MAP_REASON_NO_FRAME,
                "message": f"{FRAME_RELATION} 미배포"}
    if not lot or not slot:
        return {"state": MAP_STATE_NO_FRAME, "reason": MAP_REASON_FRAME_AMBIGUOUS,
                "message": "프레임 키(랏·슬롯)가 이 행에서 하나로 정해지지 않는다"}
    map_id = f"{lot}_{slot}"
    rows = _fetch(connection,
                  f"SELECT map_id, grid_metadata FROM {FRAME_RELATION} "
                  f"WHERE target_table = %(t)s AND map_id = %(m)s",
                  {"t": relation, "m": map_id})
    if not rows:
        return {"state": MAP_STATE_NO_FRAME, "reason": MAP_REASON_NO_FRAME,
                "message": (f"{relation}/{map_id} 프레임 미등록 — 등록된 격자 없이는 "
                            f"그리지 않는다 (지어낸 격자는 없는 결함을 만든다)"),
                "map_id": map_id}
    return {"state": MAP_STATE_READY, "table": relation, "map_id": rows[0][0],
            "grid": rows[0][1],
            "valid_die_ref": _valid_die_pointer(connection, rows[0][1])}


def _agreed_frame(connection, relation, pairs):
    """What the frames a row SPANS agree on — the lattice, and the valid-die floor.

    🔴 THE REFUSAL IS ABOUT SUPERPOSITION, NOT ABOUT THE LATTICE, and the two were being
    treated as one. The `frame_ambiguous` sentence says 「슬롯마다 격자 치수가 다르므로」 —
    measured on this box that is simply false for the DT axis: all 25 frames
    `SYN-BW-101-07` touches are registered and every one is 15x10 from (0,0). What is
    genuinely unsafe is drawing 25 tapes' dies on ONE sheet, because position (3,4) then
    shows a sum over 25 tapes. So the lattice is served — the client needs it and it is
    read, never invented — and `superposed` says out loud what the cells actually are.

    `frames_considered` vs `frames_matched` is the basis, on the wire: a grid agreed by 24
    of 25 registered frames is not the same claim as one agreed by all 25, and a client
    that cannot see the difference cannot decide whether to draw.

    One query, bounded by the frames the row actually touches.
    """
    out = {"frames_considered": len(pairs), "frames_matched": 0, "superposed": len(pairs) > 1}
    if not pairs or not relation_exists(connection, FRAME_RELATION):
        return out
    map_ids = [f"{lot}_{slot}" for lot, slot in pairs]
    rows = _fetch(connection,
                  f"SELECT map_id, grid_metadata FROM {FRAME_RELATION} "
                  f"WHERE target_table = %(t)s AND map_id = ANY(%(ids)s)",
                  {"t": relation, "ids": map_ids})
    out["frames_matched"] = len(rows)
    if not rows:
        return out

    lattices, pointers = [], []
    for _map_id, raw in rows:
        try:
            meta = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:                                    # noqa: BLE001 - text is data
            return out                                       # unreadable -> agree on nothing
        if not isinstance(meta, dict):
            return out
        # Compared with the floor pointer REMOVED rather than against a typed list of grid
        # keys: two frames may legitimately point at different floors while describing the
        # same lattice, and a hardcoded key list would silently stop covering a lattice key
        # added tomorrow. Everything else must match exactly — a conservative comparison
        # fails to `no grid`, which is the behaviour that was already there.
        lattice = {k: v for k, v in meta.items() if k != "valid_die_ref"}
        lattices.append(json.dumps(lattice, sort_keys=True, default=str))
        pointers.append(_valid_die_pointer(connection, meta))

    if len(set(lattices)) == 1:
        out["grid"] = json.loads(lattices[0])
        out["grid_basis"] = "agreed_across_matched_frames"
        if out["frames_matched"] < out["frames_considered"]:
            out["grid_partial"] = True
            out["grid_message"] = (
                f"격자는 등록된 {out['frames_matched']}개 프레임이 «전부 같다»는 근거 —"
                f" 나머지 {out['frames_considered'] - out['frames_matched']}개는 미등록이라"
                f" 확인 못 했다")
    # The floor is served only when every matched frame points at the SAME one. Two tapes
    # drawn on different valid-die maps have no common mask, and picking one would put the
    # wrong wafer's mask under the other's dies.
    keys = {(p.get("relation"), p.get("map_id")) for p in pointers}
    if len(keys) == 1 and pointers[0].get("map_id"):
        out["valid_die_ref"] = pointers[0]
    return out


def _valid_die_pointer(connection, grid_metadata):
    """WHICH valid-die map this frame is drawn on — read off the frame's own declaration.

    🔴 THIS FIELD USED TO ANNOUNCE PRESENCE ONLY (`{relation, present}`), AND THAT MADE THE
    MASK UNREACHABLE. The client resolves a floor by `table|map_id`
    (`surprise_map_core.referenceKey`) and REFUSES to build a key from the relation alone,
    because a key without the map id matches whichever mask happened to be cached and draws
    the wrong wafer. So with no `map_id` on the wire every panel took the `mask_absent`
    branch — the mask path had no way to fire at all, on any data.

    🔴 THE POINTER IS DECLARED, NOT DERIVED. `grid_metadata.valid_die_ref` is the declared
    consumer of the floor table (`product_tables.PRODUCT_TABLES['valid_die_ref']`), and it is
    read here through the SAME parser the map editor and the overlay use
    (`map_overlay.parse_valid_die_ref`), so the three cannot disagree about what a
    declaration means. No table name and no key convention is typed in this module: a
    deployment that names its floor differently changes the declaration and this follows.

    Three answers, matching the parser's three:
      declared and readable  -> `map_id` is on the wire and the mask resolves.
      not declared           -> no `map_id`. The panel draws the registered grid and says
                                「유효 다이 마스크 미적용」, which is true.
      declared but unreadable-> no `map_id` PLUS `reason`. A typo must not read as 「선언
                                없음」 — that is how a broken declaration silently becomes a
                                wafer nobody registered.
    """
    ref, error = (None, None)
    try:
        meta = (json.loads(grid_metadata) if isinstance(grid_metadata, str)
                else grid_metadata)
    except Exception:                                        # noqa: BLE001 - text is data
        meta = None
        error = "grid_metadata를 JSON으로 읽을 수 없다"
    if isinstance(meta, dict):
        ref, error = map_overlay.parse_valid_die_ref(meta)
    out = {"relation": VALID_DIE_RELATION,
           "present": relation_exists(connection, VALID_DIE_RELATION)}
    if ref:
        # `parse_valid_die_ref` PINS the read table (2026-08-04 ruling); `relation` carries
        # that pinned answer rather than whatever the declaration happened to name, so the
        # client reads the floor from the one place floors live.
        out["relation"] = ref["table"]
        out["map_id"] = ref["map_id"]
    elif error:
        out["reason"] = error
    return out


#: 🔴 THE SWAP SEAM. See the module docstring — this is the ONLY field that moves when the
#: `observed` translation lands, and a test asserts that.
PROVENANCE_SOURCE_TABLES = "source_tables"
PROVENANCE_LEDGER = "ledger"


def _provenance(relations, gate):
    """Where these numbers came from, said out loud.

    Today: the source tables — because THIS CODE PATH still reads them. `_GridPlan` scans
    `void_obs` / `delam_obs` / `inspection_row`, and no statement in this module touches
    `ledger_events`. Saying `ledger` here would be a claim about where these particular
    numbers came from, and it would be false whatever the ledger holds.

    ⚠️ THE REASON MOVED, THE VALUE DID NOT (2026-08-14). This block used to justify itself
    with 「관측이 원장에 없다」, and that premise expired the day the `observed` translation
    landed: MEASURED, `Wafer|observed|value` carries 102,177 atoms from `void_obs` and
    `delam_obs`, and `GET /api/ledger/kinds` answers `in_ledger: true`, `flowing` for both
    kinds. `ledger_backed: False` is STILL TRUE and must not be flipped — the observations
    being in the ledger and this endpoint reading them are two different facts, and only
    the second one is what this field reports. Flipping the value would make the response
    lie about its own query; leaving the old reason would send the next reader looking for
    a bug in a field that is answering correctly.
    """
    return {
        "source": PROVENANCE_SOURCE_TABLES,
        "ledger_backed": False,
        "relations": [r for r in relations if r not in gate["absent_relations"]],
        "absent_relations": gate["absent_relations"],
        "note": ("이 경로가 아직 원장을 읽지 않는다 — 숫자는 소스 테이블에서 나온다. "
                 "관측 자체는 원장에 있다(observed 원자 존재). 읽기 측이 옮겨 오면 "
                 "이 블록만 바뀐다."),
    }
