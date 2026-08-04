"""The dt_log -> dt_map derivation: the gate, the identity, the frame, the retraction.

WHAT THIS IS
------------
The body of the `dt_log_to_dt_map` chain rule family. `mappers/dt_map_mapper.py` is a
thin adapter that turns a chain payload into a call on this module; everything that
decides anything lives here so the three trigger rules cannot drift apart.

THE IDENTITY - AND WHY `dt_job` IS NOT IN IT
--------------------------------------------
A derived cell's identity is the map key (declared `map_key_columns`) plus the
coordinates. `dt_job` travels with the cell as its SOURCE, not as key material.

That is what makes overwrite work. The same physical die is the same row, so the
layering invariant, the priority tiers and the human-correction rule all apply
unchanged - including the rule that a derivation must never overwrite a human
correction. Were `dt_job` in the key, two jobs on one die would be two rows that can
never merge, and the map view would need a "which job wins" rule that does not exist.

Because the source travels with the value, "what did this source used to own" is
answerable, which is what makes retraction possible at all (see `plan_retraction`).

NOTHING HERE HARDCODES A COLUMN NAME
------------------------------------
Every column this module touches is resolved from the live declarations at call time:

  * identity columns      <- target table's `map_key_columns`
  * coordinate columns    <- target's `composite_key_source` minus the identity columns
  * raw source coordinates<- the same coordinate columns, looked up on the SOURCE table
  * the confirmed lot/slot <- the `expose` list of the confirmed-attribution virtual join
  * the frame             <- the `expose` list of the frame-attribution virtual join
  * the join keys         <- both rules' `join_key`

This matters more than style. The dev database and production disagree about
`dt_map`'s shape, so a module that reads `dt_lot` because someone typed `dt_lot`
would be correct in exactly one of the two.

THE GATE: THREE THINGS, ALL REQUIRED
------------------------------------
A row is derived only when the confirmed lot, the confirmed slot and the frame all
resolve. Missing any one, NO ROW IS CREATED - the `dt_log` row is the record and
loses nothing. A row created with an empty map key would appear in no map, and a
population of those accumulates until nobody can tell a bug from normal.

Three refusals that must not be relaxed:

  * NEVER fall back to the stored lot/slot. `virtual_join_rules.json` says in its own
    words that `dt_log` carries lot/slot that are absent 40% of the time and WRONG 10%
    of the time, and that the confirmed columns were given non-colliding names
    precisely so the wrong value could not win an absent-only merge. In a map key that
    is not a quality problem, it is corruption: a wrong lot writes cells into another
    lot's map, and the cell count is identical either way. `_forbidden_fallback_columns`
    exists to make the refusal structural rather than a habit.
  * NEVER substitute `core_frame` for a missing `dt_frame`. They are different frames
    and only `dt_frame` applies here (user ruling). The frame-attribution join exposes
    both; this module reads one, and
    `test_core_frame_is_never_substituted_for_a_missing_dt_frame` proves it by seeding
    a readable `core_frame` and requiring the row to be held back anyway.
  * NEVER guess between disagreeing evidence. Two frame rows that disagree produce
    `frame_disagreement`, not a pick - the discipline `html_topology_parser` uses.

Held-back rows are reported as a NAMED AGGREGATE and are individually silent, and the
reasons are SPLIT: "attribution missing: N" and "frame missing: M" are different
repairs and a combined number tells the operator neither.

THE FRAME TRIGGER IS THE DANGEROUS ONE
--------------------------------------
`eqp_frame_attribution` is keyed by equipment and product, not by job, so ONE
corrected frame row re-transforms every job on that equipment for that product.
Measured on the dev fixture 2026-08-04: a single row covers up to 2,892 `dt_log` rows
across 40 jobs - 33% of the whole table. `frame_trigger_scope` sizes that before
anything expands, and `SCOPE_ROW_CAP` makes a large fan-out an explicit refusal rather
than a silent mass re-derivation.

COORDINATES
-----------
`dt_log` records coordinates in whichever of the 8 frames the equipment used; that
frame is `dt_frame`. The map's canonical frame is the one its `wafer_map_metadata` row
declares. Moving between them is `map_overlay.make_frame_transform`, which is THE
transform - a second copy once lived in `bonding_plan.py` and was deleted for that
reason. This module does not write a third spelling and does not modify the second.

The source meta is the target meta with rotation and side replaced by `dt_frame`'s.
That is forced rather than chosen: it is the same physical wafer, and
`make_frame_transform` refuses when the grid dimensions or the phys signature differ.

If the target map has no registered meta, the derivation HOLDS BACK
(`target_meta_missing`) instead of inventing a canonical frame. "The first write
defines canonical" would make the canonical frame a side effect of arrival order.
"""

import logging
import time

import map_overlay

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Declared names this module resolves against (not column names - rule names).
# ---------------------------------------------------------------------------

CONFIRMED_JOIN_RULE = "dt_log_confirmed_attribution"
FRAME_JOIN_RULE = "dt_log_frame_attribution"

# The frame-attribution rule exposes BOTH frames. Only this one applies to dt_map's
# coordinates. `core_frame` is a different frame of a different wafer and filling an
# absent value from the neighbouring axis is the substitution that produced a
# perfectly-aligned screen with every value wrong.
FRAME_COLUMN = "dt_frame"
FORBIDDEN_FRAME_SUBSTITUTE = "core_frame"

# The confirmed columns are deliberately NOT named after the stored ones (see the
# virtual-join rule's own `_why_comment`). Resolution is by declaration first: an
# identity column C is fed by an exposed column named C, or failing that C+suffix.
# Nothing else is accepted - an unresolvable identity column is a refusal, not a guess.
CONFIRMED_SUFFIX = "_confirmed"

# ---------------------------------------------------------------------------
# Named outcomes. A refusal must be NAMED in the log; an empty result is not a
# refusal, and an operator cannot tell "nothing to do" from "everything refused".
# ---------------------------------------------------------------------------

HOLD_ATTRIBUTION_MISSING = "attribution_missing"
HOLD_FRAME_MISSING = "frame_missing"
HOLD_FRAME_DISAGREEMENT = "frame_disagreement"
HOLD_FRAME_UNREADABLE = "frame_unreadable"
HOLD_TARGET_META_MISSING = "target_meta_missing"
HOLD_TRANSFORM_UNAVAILABLE = "transform_unavailable"
HOLD_COORDINATES_MISSING = "coordinates_missing"

# The two the operator is asked to look at. They are split because they are different
# repairs: one is "confirm a job", the other is "confirm an equipment/product frame".
PRIMARY_HOLD_REASONS = (HOLD_ATTRIBUTION_MISSING, HOLD_FRAME_MISSING)

HOLD_REASONS = PRIMARY_HOLD_REASONS + (
    HOLD_FRAME_DISAGREEMENT, HOLD_FRAME_UNREADABLE, HOLD_TARGET_META_MISSING,
    HOLD_TRANSFORM_UNAVAILABLE, HOLD_COORDINATES_MISSING,
)

# Refusals that abort the whole call rather than holding rows back one at a time.
REFUSE_IDENTITY_UNDECLARED = "identity_columns_undeclared"
REFUSE_COORDINATES_UNDECLARED = "coordinate_columns_undeclared"
REFUSE_SOURCE_COLUMN_MISSING = "source_column_missing"
REFUSE_JOIN_RULE_MISSING = "join_rule_missing"
REFUSE_SCOPE_TOO_LARGE = "scope_too_large"

# One corrected `eqp_frame_attribution` row can reach a third of `dt_log`. Past this
# many rows the expansion refuses and names itself rather than re-deriving silently.
SCOPE_ROW_CAP = 50000

CHUNK = 1000

# Retraction budget. Losing more than this share of what a source owns looks exactly
# like a mapping typo, so the plan declines instead of acting (graph_stale_edges shape).
DEFAULT_MAX_RETRACT_FRACTION = 0.5
DEFAULT_MIN_RETRACT_POPULATION = 20


class DerivationRefused(Exception):
    """Raised with a NAMED code when the call cannot proceed at all."""

    def __init__(self, code: str, detail: str):
        self.code = code
        self.detail = detail
        super().__init__("%s: %s" % (code, detail))


# ---------------------------------------------------------------------------
# Declaration reading
# ---------------------------------------------------------------------------

def _table_config(table: str) -> dict:
    """Live declaration for `table`. Read through the module attribute every time -
    `crud.TABLE_CONFIG` is mutated in place on hot reload, so a snapshot goes stale."""
    from database import crud
    return crud.TABLE_CONFIG.get(table) or {}


def identity_columns(target_table: str) -> list:
    """The target's map key - the columns that say WHICH MAP a cell belongs to.

    This is the declaration the whole design turns on. Under the settled design it
    resolves to the confirmed lot and slot; on the dev fixture it resolves to
    `['dt_job']`. Both are handled by the same code, which is the point of reading it.
    """
    cols = _table_config(target_table).get("map_key_columns") or []
    if isinstance(cols, str):
        cols = [cols]
    cols = [str(c) for c in cols if str(c).strip()]
    if not cols:
        raise DerivationRefused(
            REFUSE_IDENTITY_UNDECLARED,
            "'%s' declares no map_key_columns, so a derived cell would belong to no "
            "map. Rows that appear in no map accumulate and nobody can later tell "
            "whether that is a bug or normal." % target_table)
    return cols


def coordinate_columns(target_table: str) -> list:
    """The target's per-cell address: `composite_key_source` minus the identity.

    Derived, never typed. The row key is (which map) + (where in it); whatever the
    composite key holds beyond the map key IS the coordinate pair.
    """
    composite = _table_config(target_table).get("composite_key_source") or []
    if isinstance(composite, str):
        composite = [composite]
    ident = set(identity_columns(target_table))
    coords = [str(c) for c in composite if str(c) not in ident]
    if not coords:
        raise DerivationRefused(
            REFUSE_COORDINATES_UNDECLARED,
            "'%s' composite_key_source %r leaves no coordinate column once the map key "
            "%r is removed - every cell of a map would collapse onto one row."
            % (target_table, list(composite), sorted(ident)))
    return coords


def _declared_columns(table: str) -> dict:
    return _table_config(table).get("column_types") or {}


def join_rule(db, name: str) -> dict:
    """One VERIFIED virtual-join rule.

    `load_verified_rules` and not `load_virtual_join_rules`. The latter checks the
    SHAPE of a declaration only; the former also asks `pg_index` whether a UNIQUE index
    actually covers the join key, and `virtual_join_config` names itself "the only
    entry point for code that executes a join" for that reason - the difference it
    quotes is 130 million rows.

    This module executes those joins. A rule whose uniqueness was never checked can
    fan out, and a fan-out here is not a slow query: `load_attribution` keys results by
    the join key, so a second attribution row for the same key would silently overwrite
    the first and one arbitrary lot would win. Refusing an unverified rule is the only
    honest option.

    Returns the loader's normalized rule (it carries `name`, `right_columns`,
    `required_index` and the DDL that would create it).
    """
    import virtual_join_config
    from database import crud

    rejections = []
    rules = virtual_join_config.load_verified_rules(
        db, known_tables=crud.TABLE_CONFIG, rejections=rejections)
    for rule in rules or []:
        if rule.get("name") == name:
            return rule
    why = [r for r in rejections if r.get("subject") == name]
    raise DerivationRefused(
        REFUSE_JOIN_RULE_MISSING,
        "virtual join rule '%s' is absent or was not verified; the gate cannot be "
        "resolved without it.%s"
        % (name, (" Rejected: %r" % why) if why else ""))


def join_pairs(rule: dict) -> list:
    """[(left column on the source, right column on the attribution table)]."""
    out = []
    for pair in rule.get("join_key") or []:
        left, right = pair.get("left"), pair.get("right")
        if left and right:
            out.append((str(left), str(right)))
    return out


def resolve_identity_sources(target_table: str, confirmed_rule: dict) -> dict:
    """identity column -> the exposed CONFIRMED column that may fill it.

    Declaration first (an exposed column of the same name), then the declared
    non-colliding convention (`<column>_confirmed`). Anything else refuses. There is
    deliberately no third fallback to the stored column of the same name: that is the
    corruption this whole design exists to prevent.
    """
    exposed = [str(c) for c in (confirmed_rule.get("expose") or [])]
    exposed_set = set(exposed)
    mapping = {}
    unresolved = []
    for col in identity_columns(target_table):
        if col in exposed_set:
            mapping[col] = col
        elif col + CONFIRMED_SUFFIX in exposed_set:
            mapping[col] = col + CONFIRMED_SUFFIX
        else:
            unresolved.append(col)
    if unresolved:
        raise DerivationRefused(
            REFUSE_IDENTITY_UNDECLARED,
            "map key column(s) %r of '%s' have no confirmed source in rule '%s' "
            "(exposes %r). Falling back to the stored column of the same name is "
            "exactly the substitution that writes cells into another lot's map."
            % (unresolved, target_table, confirmed_rule.get("_name") or "confirmed",
               exposed))
    return mapping


def _forbidden_fallback_columns(target_table: str, identity_sources: dict) -> set:
    """The stored columns a derivation must never read for key material.

    Structural, not a habit: `derive_cells` projects source rows through an allowlist
    and these names are excluded from it, so a fallback cannot be written by accident -
    it would have to be added here first.
    """
    return {col for col, src in identity_sources.items() if src != col}


# ---------------------------------------------------------------------------
# The frame
# ---------------------------------------------------------------------------

def parse_frame(text):
    """'rot90_back' -> (90, 'back'). Unreadable -> None (the caller holds the row back).

    Deliberately strict. A frame spelled in a way this does not recognise is not a
    frame to be guessed at; it is a declaration to be fixed.
    """
    if text is None:
        return None
    s = str(text).strip().lower()
    if not s.startswith("rot"):
        return None
    body = s[3:]
    if "_" not in body:
        return None
    rot_text, side = body.split("_", 1)
    try:
        rot = int(rot_text)
    except (TypeError, ValueError):
        return None
    if rot not in (0, 90, 180, 270):
        return None
    if side not in ("front", "back"):
        return None
    return rot, side


def source_meta_for_frame(target_meta: dict, frame_text: str):
    """The recorded frame, expressed as a map meta against the target's own wafer spec.

    Only rotation and side move. Grid dimensions and the phys signature are the same
    physical wafer and are copied unchanged - `make_frame_transform` refuses outright
    when they differ, so borrowing them is forced, not convenient.
    """
    parsed = parse_frame(frame_text)
    if parsed is None or not target_meta:
        return None
    rot, side = parsed
    meta = dict(target_meta)
    meta["rotation"] = rot
    meta["side"] = side
    return meta


# ---------------------------------------------------------------------------
# Fan-out sizing - run this BEFORE expanding a trigger, not after
# ---------------------------------------------------------------------------

def frame_trigger_scope(db, source_table: str, filters: dict) -> dict:
    """How many source rows and jobs one attribution correction would re-derive.

    Two aggregates, no row bodies. The frame trigger's whole hazard is that its key
    (equipment, product) is coarser than the thing it corrects, so the size of what it
    touches has to be a number the operator sees before it happens rather than a
    surprise in a log afterwards.
    """
    from database import models
    from sqlalchemy import func

    model = models.DYNAMIC_TABLES.get(source_table)
    if model is None:
        raise DerivationRefused(REFUSE_SOURCE_COLUMN_MISSING,
                                "source table '%s' has no model" % source_table)
    q = db.query(func.count()).select_from(model)
    for col, val in filters.items():
        attr = getattr(model, col, None)
        if attr is None:
            raise DerivationRefused(
                REFUSE_SOURCE_COLUMN_MISSING,
                "'%s' has no column '%s' to scope the trigger by" % (source_table, col))
        q = q.filter(attr == val)
    rows = q.scalar() or 0
    return {"filters": dict(filters), "rows": int(rows), "cap": SCOPE_ROW_CAP,
            "over_cap": int(rows) > SCOPE_ROW_CAP}


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------

def _blank(v):
    return v is None or str(v).strip() == ""


def load_attribution(db, table: str, key_columns: list, keys: set, wanted: list) -> dict:
    """(key tuple) -> {column: value} for the attribution rows covering `keys`.

    Chunked `IN` rather than a row-at-a-time lookup: both attribution tables carry the
    UNIQUE index the virtual-join loader demanded (`uq_vjoin_*`), so this is an index
    scan per chunk and stays flat as the population grows.
    """
    from database import models

    model = models.DYNAMIC_TABLES.get(table)
    if model is None:
        return {}
    key_attrs = [getattr(model, c, None) for c in key_columns]
    if any(a is None for a in key_attrs):
        return {}
    want_attrs = [(c, getattr(model, c, None)) for c in wanted]
    want_attrs = [(c, a) for c, a in want_attrs if a is not None]

    out = {}
    key_list = [k for k in keys if k is not None]
    if len(key_columns) == 1:
        singles = [k[0] for k in key_list]
        for i in range(0, len(singles), CHUNK):
            batch = singles[i:i + CHUNK]
            rows = (db.query(*(key_attrs + [a for _c, a in want_attrs]))
                    .filter(key_attrs[0].in_(batch)).all())
            for row in rows:
                out.setdefault((row[0],), {}).update(
                    {c: row[len(key_columns) + j] for j, (c, _a) in enumerate(want_attrs)})
        return out

    # Composite key: one OR-of-ANDs per chunk. Still one statement per chunk.
    from sqlalchemy import and_, or_
    for i in range(0, len(key_list), CHUNK):
        batch = key_list[i:i + CHUNK]
        clauses = [and_(*[key_attrs[j] == part for j, part in enumerate(k)]) for k in batch]
        rows = (db.query(*(key_attrs + [a for _c, a in want_attrs]))
                .filter(or_(*clauses)).all())
        for row in rows:
            k = tuple(row[:len(key_columns)])
            out.setdefault(k, {}).update(
                {c: row[len(key_columns) + j] for j, (c, _a) in enumerate(want_attrs)})
    return out


def resolve_frame(attribution_row: dict):
    """(frame text, None) or (None, named hold reason).

    Reads exactly one column. `core_frame` is present in the same row and is never
    consulted - the missing-value repair is to confirm `dt_frame`, not to borrow the
    neighbouring axis.
    """
    if not attribution_row:
        return None, HOLD_FRAME_MISSING
    value = attribution_row.get(FRAME_COLUMN)
    if _blank(value):
        return None, HOLD_FRAME_MISSING
    if parse_frame(value) is None:
        return None, HOLD_FRAME_UNREADABLE
    return str(value).strip(), None


def resolve_frame_candidates(values):
    """Several pieces of frame evidence -> one answer, or a refusal to choose.

    Disagreement is not a tie to be broken. Two sources that disagree mean one of them
    is wrong, and picking either writes a whole wafer's worth of correct-looking cells
    at wrong coordinates.
    """
    distinct = {str(v).strip() for v in values if not _blank(v)}
    if not distinct:
        return None, HOLD_FRAME_MISSING
    if len(distinct) > 1:
        return None, HOLD_FRAME_DISAGREEMENT
    only = distinct.pop()
    if parse_frame(only) is None:
        return None, HOLD_FRAME_UNREADABLE
    return only, None


# ---------------------------------------------------------------------------
# Derivation
# ---------------------------------------------------------------------------

class HoldBack:
    """Named aggregate of what did not get derived. Individually silent by design.

    Per-row logging of a 40%-absent population is how a log becomes unreadable and the
    number stops being watched. What matters is that the total trends toward zero and
    that the reasons stay SPLIT, because "confirm these jobs" and "confirm these
    equipment/product frames" are different work for different people.
    """

    def __init__(self):
        self.counts = {r: 0 for r in HOLD_REASONS}
        self.samples = {}

    def add(self, reason: str, key=None):
        self.counts[reason] = self.counts.get(reason, 0) + 1
        if key is not None:
            bucket = self.samples.setdefault(reason, [])
            if len(bucket) < 5:
                bucket.append(key)

    @property
    def total(self):
        return sum(self.counts.values())

    def as_dict(self):
        return {"total": self.total,
                "by_reason": {k: v for k, v in self.counts.items() if v},
                "samples": self.samples}


def format_holdback_summary(held: dict, derived: int, elapsed_ms=None) -> str:
    """One line naming both split counts even when they are zero.

    The two primary reasons are printed unconditionally. A summary that omits a zero
    makes "nothing was held back for this reason" indistinguishable from "this reason
    was never checked", and the operator needs to see the number go down.
    """
    by = (held or {}).get("by_reason") or {}
    parts = ["derived=%d" % derived]
    for reason in PRIMARY_HOLD_REASONS:
        parts.append("%s=%d" % (reason, by.get(reason, 0)))
    other = {k: v for k, v in by.items() if k not in PRIMARY_HOLD_REASONS and v}
    if other:
        parts.append("other(" + ",".join("%s=%d" % kv for kv in sorted(other.items())) + ")")
    if elapsed_ms is not None:
        parts.append("%.0fms" % elapsed_ms)
    return "[DtMapDerivation] " + " ".join(parts)


def derive_cells(db, rows, source_table: str, target_table: str,
                 source_column: str, value_columns=None, origin_columns=None,
                 meta_loader=None) -> dict:
    """`dt_log` rows -> derived `dt_map` cell payloads, plus what was held back.

    Returns {"updates": [...], "held": {...}, "derived": n, "identity_columns": [...],
    "coordinate_columns": [...]}. Writes nothing; the caller (the chain worker, via the
    mapper) performs the upsert so this stays testable without a write path.

    No `business_key_val` is set on any item. `crud.apply_batch_updates` composes the
    composite key itself when the caller omits it and supplies every
    `composite_key_source` column, and letting it do so guarantees this module cannot
    disagree with the recomposition crud performs after the write.
    """
    t0 = time.monotonic()
    held = HoldBack()

    ident_cols = identity_columns(target_table)
    coord_cols = coordinate_columns(target_table)

    confirmed_rule = join_rule(db, CONFIRMED_JOIN_RULE)
    frame_rule = join_rule(db, FRAME_JOIN_RULE)
    ident_sources = resolve_identity_sources(target_table, confirmed_rule)
    forbidden = _forbidden_fallback_columns(target_table, ident_sources)

    src_declared = _declared_columns(source_table)
    for col in coord_cols:
        if col not in src_declared:
            raise DerivationRefused(
                REFUSE_COORDINATES_UNDECLARED,
                "coordinate column '%s' is declared on target '%s' but not on source "
                "'%s'; the raw coordinate to transform cannot be located."
                % (col, target_table, source_table))

    conf_pairs = join_pairs(confirmed_rule)
    frame_pairs = join_pairs(frame_rule)

    # ---- allowlist projection. `forbidden` is excluded here, which is what makes the
    # "never fall back to the stored lot/slot" rule structural instead of a promise.
    carried = [source_column] + list(coord_cols)
    carried += [left for left, _r in conf_pairs] + [left for left, _r in frame_pairs]
    carried += list(value_columns or [])
    carried += list(origin_columns or [])
    allow = [c for c in dict.fromkeys(carried) if c in src_declared and c not in forbidden]

    rows = list(rows or [])
    if not rows:
        return {"updates": [], "held": held.as_dict(), "derived": 0,
                "identity_columns": ident_cols, "coordinate_columns": coord_cols}

    def pick(row, col):
        return row.get(col) if isinstance(row, dict) else getattr(row, col, None)

    conf_keys = {tuple(pick(r, left) for left, _x in conf_pairs) for r in rows}
    frame_keys = {tuple(pick(r, left) for left, _x in frame_pairs) for r in rows}

    conf_map = load_attribution(
        db, confirmed_rule.get("right_table"), [right for _l, right in conf_pairs],
        conf_keys, sorted(set(ident_sources.values())))
    frame_map = load_attribution(
        db, frame_rule.get("right_table"), [right for _l, right in frame_pairs],
        frame_keys, [FRAME_COLUMN])

    loader = meta_loader or (lambda mid: map_overlay.load_map_meta(db, target_table, mid))
    meta_cache = {}
    transform_cache = {}

    updates = []
    for row in rows:
        row_key = pick(row, source_column)

        # ---- gate 1 and 2: the confirmed lot and slot
        conf = conf_map.get(tuple(pick(row, left) for left, _x in conf_pairs)) or {}
        ident_values = {}
        missing_attribution = False
        for col in ident_cols:
            raw = conf.get(ident_sources[col])
            if _blank(raw):
                missing_attribution = True
                break
            ident_values[col] = map_overlay.canonical_bind_value(target_table, col, raw)
        if missing_attribution:
            held.add(HOLD_ATTRIBUTION_MISSING, row_key)
            continue

        # ---- gate 3: the frame
        frame_row = frame_map.get(tuple(pick(row, left) for left, _x in frame_pairs))
        frame_text, reason = resolve_frame(frame_row)
        if reason:
            held.add(reason, row_key)
            continue

        # ---- the map this cell belongs to, and the frame that map is drawn in.
        # Composed by the SHARED primitive, not by joining the parts here. Registration
        # (`MapMetaCollector`) composes identities with it too, and an identity composed
        # two ways is an identity that eventually differs - the meta exists and nothing
        # can find it. It also refuses a partial identity by returning None.
        import map_meta_registrar
        map_id = map_meta_registrar.compose_map_id(ident_cols, ident_values, target_table)
        if map_id is None:
            held.add(HOLD_ATTRIBUTION_MISSING, row_key)
            continue
        if map_id not in meta_cache:
            meta_cache[map_id] = loader(map_id)
        target_meta = meta_cache[map_id]
        if not target_meta:
            held.add(HOLD_TARGET_META_MISSING, map_id)
            continue

        tf_key = (map_id, frame_text)
        if tf_key not in transform_cache:
            src_meta = source_meta_for_frame(target_meta, frame_text)
            try:
                transform_cache[tf_key] = map_overlay.resolve_map_transform(
                    src_meta, target_meta)[0]
            except ValueError as e:
                logger.warning("[DtMapDerivation] transform unavailable for map '%s' "
                               "frame '%s': %s", map_id, frame_text, e)
                transform_cache[tf_key] = e
        transform = transform_cache[tf_key]
        if isinstance(transform, Exception):
            held.add(HOLD_TRANSFORM_UNAVAILABLE, map_id)
            continue

        raw_coords = [pick(row, c) for c in coord_cols]
        if any(v is None for v in raw_coords):
            held.add(HOLD_COORDINATES_MISSING, row_key)
            continue
        try:
            nums = [int(float(v)) for v in raw_coords]
        except (TypeError, ValueError):
            held.add(HOLD_COORDINATES_MISSING, row_key)
            continue

        if transform is None:
            placed = nums                       # identity frame - nothing to move
        elif len(nums) == 2:
            placed = list(transform(nums[0], nums[1]))
        else:
            held.add(HOLD_TRANSFORM_UNAVAILABLE, map_id)
            continue

        cell = dict(ident_values)
        for i, col in enumerate(coord_cols):
            cell[col] = placed[i]
        # The source travels with the value. This is what makes the cell traceable and
        # what makes retraction possible - without it "what did this source own" has
        # no answer and stale cells could only be found by set difference.
        cell[source_column] = pick(row, source_column)
        for col in allow:
            if col in cell or col in ident_cols or col in coord_cols:
                continue
            cell[col] = pick(row, col)

        updates.append({
            # No business_key_val on purpose - see the docstring.
            "updates": cell,
            "source_name": "chain_ingestion",
            "updated_by": "chain_worker",
        })

    elapsed = (time.monotonic() - t0) * 1000.0
    result = {"updates": updates, "held": held.as_dict(), "derived": len(updates),
              "identity_columns": ident_cols, "coordinate_columns": coord_cols,
              "elapsed_ms": elapsed}
    logger.info("%s", format_holdback_summary(result["held"], len(updates), elapsed))
    return result


# ---------------------------------------------------------------------------
# Retraction - the question that has kept this rule disabled
# ---------------------------------------------------------------------------
#
# A chain can upsert map cells and can never purge them: `replace_map` lives on the
# batch and `chain_ingestion_worker` builds that batch itself and never sets it. So
# correcting an attribution would leave the cells written under the old identity
# sitting there forever beside the new ones.
#
# `replace_map` is not the missing piece even if the worker did set it.
# `crud.derive_replace_map_scope` validates every scope key to be INSIDE the map-key
# contract, so a purge can only be scoped to a whole map. Under the settled identity
# one lot/slot map can be fed by more than one job, and purging by map would delete a
# second job's cells to correct the first. Verified at source 2026-08-04.
#
# What works is the shape `graph_stale_edges` already uses: POSITIVE SELECTION of what
# a source owns. `dt_job` travels on every derived cell, so "which cells did this job
# mint" is a plain indexed predicate, and stale is (owned now) minus (derived now).
# Dry run by default, a budget guard, and human-touched cells protected from deletion -
# the never-overwrite-a-human-correction rule extended to the delete.


def _human_touched_row_ids(db, table_name: str, row_ids: list) -> set:
    """Row ids carrying a human overwrite. These are never retracted.

    A derivation may not delete a human correction for the same reason it may not
    overwrite one. `cell_overwrites` is where that fact is recorded, so it is where
    this asks - not a heuristic on the value.
    """
    from database.models import CellOverwrite
    out = set()
    ids = list(row_ids)
    for i in range(0, len(ids), CHUNK):
        rows = (db.query(CellOverwrite.row_id)
                .filter(CellOverwrite.table_name == table_name,
                        CellOverwrite.row_id.in_(ids[i:i + CHUNK]))
                .distinct().all())
        out.update(r[0] for r in rows)
    return out


def plan_retraction(db, target_table: str, source_column: str, source_value,
                    derived_keys, max_fraction=DEFAULT_MAX_RETRACT_FRACTION,
                    min_population=DEFAULT_MIN_RETRACT_POPULATION) -> dict:
    """Decide, WITHOUT WRITING ANYTHING, which cells this source no longer owns.

    `derived_keys` is the set of `business_key_val` the current derivation produced for
    this source. Anything the source owns that is not in that set is stale: the
    attribution moved the map key, or the frame moved the coordinates, and the old row
    is now an orphan under an identity that is no longer true.

    Returns the plan; `apply_retraction` executes exactly it and re-derives nothing.
    A dry run that could differ from what runs is a decoration.
    """
    from database import models

    t0 = time.monotonic()
    model = models.DYNAMIC_TABLES.get(target_table)
    if model is None:
        raise DerivationRefused(REFUSE_SOURCE_COLUMN_MISSING,
                                "target table '%s' has no model" % target_table)
    src_attr = getattr(model, source_column, None)
    if src_attr is None:
        raise DerivationRefused(
            REFUSE_SOURCE_COLUMN_MISSING,
            "'%s' does not carry '%s', so what this source owns cannot be selected "
            "positively and stale cells could only be guessed at by set difference."
            % (target_table, source_column))

    owned = (db.query(model.row_id, model.business_key_val)
             .filter(src_attr == source_value).all())
    population = len(owned)
    keep = set(derived_keys or ())
    stale = [(rid, bk) for rid, bk in owned if bk not in keep]

    protected = _human_touched_row_ids(db, target_table, [rid for rid, _b in stale])
    retractable = [(rid, bk) for rid, bk in stale if rid not in protected]

    fraction = (len(retractable) / population) if population else 0.0
    declined = None
    if population >= min_population and fraction > max_fraction:
        declined = {
            "stale": len(retractable), "population": population, "fraction": fraction,
            "reason": ("would retract %.0f%% of what '%s'='%s' owns (> max_fraction "
                       "%.0f%%); a wrong frame or a wrong attribution looks exactly "
                       "like this" % (fraction * 100, source_column, source_value,
                                      max_fraction * 100)),
        }

    return {
        "target_table": target_table,
        "source_column": source_column,
        "source_value": source_value,
        "population": population,
        "stale": len(stale),
        "protected": len(protected),
        "protected_samples": sorted(protected)[:10],
        "retractable": len(retractable),
        "fraction": fraction,
        "declined": declined,
        "delete_row_ids": [] if declined else [rid for rid, _b in retractable],
        "samples": [bk for _r, bk in retractable[:10]],
        "elapsed_ms": (time.monotonic() - t0) * 1000.0,
    }


def apply_retraction(db, plan) -> int:
    """Delete exactly `plan["delete_row_ids"]`, in chunks. Returns the count deleted.

    Takes the ids the plan decided on and re-derives nothing: recomputing here could
    delete something the dry run never showed.
    """
    from database import models
    model = models.DYNAMIC_TABLES.get(plan.get("target_table"))
    ids = plan.get("delete_row_ids") or []
    if model is None or not ids:
        return 0
    deleted = 0
    for i in range(0, len(ids), CHUNK):
        deleted += (db.query(model)
                    .filter(model.row_id.in_(ids[i:i + CHUNK]))
                    .delete(synchronize_session=False))
    db.commit()
    return deleted


def format_retraction_summary(plan) -> str:
    """One line that names a refusal rather than reporting zero deletions.

    A retraction that reports only what it removed makes "the budget guard declined
    everything" read exactly like "there was nothing stale".
    """
    head = "[DtMapRetraction] %s %s='%s'" % (plan.get("target_table"),
                                             plan.get("source_column"),
                                             plan.get("source_value"))
    if plan.get("declined"):
        return "%s DECLINED: %s" % (head, plan["declined"]["reason"])
    return ("%s owns=%d stale=%d protected=%d would_delete=%d"
            % (head, plan.get("population", 0), plan.get("stale", 0),
               plan.get("protected", 0), len(plan.get("delete_row_ids") or [])))
