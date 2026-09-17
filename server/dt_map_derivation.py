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
  * the confirmed lot/slot <- the `take` list of the confirmed-attribution join
  * the frame             <- the `take` list of the frame-attribution join
  * the join keys         <- both rules' `on`

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

  * NEVER fall back to the stored lot/slot. The join declaration says in its own
    words that `dt_log` carries lot/slot that are absent 40% of the time and WRONG 10%
    of the time, and that the confirmed columns were given non-colliding names
    precisely so the wrong value could not win an absent-only merge. In a map key that
    is not a quality problem, it is corruption: a wrong lot writes cells into another
    lot's map, and the cell count is identical either way. `_forbidden_fallback_columns`
    exists to make the refusal structural rather than a habit.
  * NEVER substitute `core_frame` for a missing `dt_frame`. They are different frames
    and only `dt_frame` applies here (user ruling). The frame-attribution join takes
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
import event_constants

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


def _join_from_unified(db, rule: dict) -> dict:
    """One unified `derive: {kind: "join"}` rule -> the dict this module has always read.

    THE KEYS DO NOT MOVE, DELIBERATELY. `join_pairs`, `resolve_identity_sources` and the
    two `load_attribution` calls read `join_key`, `expose` and `right_table`, and
    `mapper_sdk.MAPPER_SURFACE` puts `join_rule` and `join_pairs` in the operator's own
    mappers. So the SOURCE of these four cells changes and their spelling does not.

    🔴 `expose` IS `take`'s `from` SIDE, NOT ITS `into`. `expose` names columns to
    SELECT on the RIGHT table - the read-time loader refuses one absent from `right_cols`,
    and `load_attribution` reads them there - and `from` is the right column while `into`
    is the name the value lands under on the LEFT. Reading `into` here would SELECT a
    column that does not exist on the table being read.
    """
    from chain import join_into, join_key_index

    spec = join_into.join_spec(rule)
    name = rule.get("name")
    right_table, right_columns, right_folds = join_into.right_key(rule)

    # 🔴 THE SAME UNIQUENESS QUESTION, ASKED WITH THE SAME FUNCTION. The read-time
    # path's `verify_uniqueness` is a thin wrapper on this call, and a fan-out here is not a
    # slow query: `load_attribution` keys results by the join key, so a second attribution
    # row for one key silently overwrites the first and an arbitrary lot wins. Calling the
    # one definition rather than re-asking keeps the answer from being able to differ.
    #
    # `folds` travels ONLY when something actually folds - the call shape the read-time seat
    # uses, for the reason written there.
    kwargs = {"folds": right_folds} if any(right_folds or []) else {}
    unique_index = join_key_index.unique_index_covering(
        db, right_table, right_columns, **kwargs)
    if not unique_index:
        raise DerivationRefused(
            REFUSE_JOIN_RULE_MISSING,
            "join rule %r declares %s(%s) but no valid UNIQUE index covers that key, so "
            "the join may fan out and one attribution row would silently win. Build it: %s"
            % (name, right_table, ", ".join(right_columns),
               join_key_index.required_index_ddl(right_table, right_columns, right_folds)))

    left_table = str(rule.get("target_table") or "")
    pairs = join_into._pairs(spec, left_table)
    return {
        "name": name,
        "_name": name,
        # 🔴 `left_table` IS ON THE CONTRACT TOO, AND MY FIRST CENSUS MISSED IT.
        # I counted the cells THIS module reads; `mapper_sdk.MAPPER_SURFACE` hands the same
        # dict to the operator's mappers, and `_matching_join_rule` there picks a rule by
        # comparing BOTH `right_table` and `left_table`. Dropping it did not raise - the
        # comparison just never matched and the revisit derived nothing. Two tests caught it.
        "left_table": left_table,
        "left_columns": [left for left, _r, _f in pairs],
        "right_table": right_table,
        "join_key": [{"left": left, "right": right} for left, right, _f in pairs],
        "expose": [source for source, _into in join_into._takes(spec)],
        "right_columns": list(right_columns),
        "right_folds": list(right_folds or []),
        "required_index": join_key_index.required_index_name(
            right_table, right_columns, right_folds),
        "required_index_ddl": join_key_index.required_index_ddl(
            right_table, right_columns, right_folds),
        "unique_index": unique_index,
    }


def join_rule(db, name: str) -> dict:
    """One VERIFIED join, read from the UNIFIED declaration (판정 440 ③ㅡ).

    🔴 WHY THIS MOVED. The read-time virtual join is being retired - the owner's
    ruling is that production writes join columns into the TABLE (`into.table`) - so the
    declaration this module used to resolve against will not exist. Nothing about what it
    resolves changes: the same two rule names, the same four cells, the same refusal when
    a name is absent. Only where the answer comes from.

    🔴 AND IT READS THE DECLARATION THROUGH THE JUDGE THE LOADER USES (S-244).
    `read_rules_document` + `expand_declaration` is the one reading of that file;
    `chain.synthesis.declared_unique_index_names` asks the same pair the same way. A second
    reading here would be a second answer to 「what does this declaration stand」.

    ⚰️ I WROTE THAT 「없다」 AND 「꺼져 있다」 COULD NOT BE TOLD APART HERE, AND THAT WAS
    WRONG (판정 450 ①). `expand_declaration` returns THREE things and this function was
    discarding the third: a disabled declaration stands no rule, raises no refusal, and says
    so in `notes` - its own docstring says 「OFF IS NOT A REFUSAL … and SAYS SO IN notes」.
    The loss was not the loader's to fix later; it was this call throwing the answer away.
    Both the loader's refusal and its notes are carried into the sentence now, so an
    operator who switched a declaration off is told that, not that it was never written.

    Returns a dict carrying `name`, `left_table`, `right_table`, `join_key`, `expose`,
    `right_columns`, `required_index` and the DDL that would create it - the cells the
    previous return carried, under the same names.
    """
    from chain import ingestion_worker, rule_run, rule_shape
    from database import crud

    withheld = None
    for raw in ingestion_worker.read_rules_document()["rules"] or ():
        stood, refusal, notes = rule_shape.expand_declaration(raw, crud.TABLE_CONFIG)
        # 🔴 THE NAME FIELD, NOT THE NAME INSIDE THE SENTENCE (판정 450 ②). A refusal
        # reads "<name>: <detail>", so a substring test let `dt_map` claim `dt_map_extra`'s
        # refusal and send the operator to somebody else's declaration. It is also the SAME
        # question the lookup below asks - 「is this the rule I was asked for」 - and the two
        # were spelled differently one line apart, inside a single commit.
        declared_name = str(raw.get("name") or "") if isinstance(raw, dict) else ""
        if declared_name == name and (refusal or notes):
            # ⚠️ WHATEVER THE LOADER SAID ABOUT THIS NAME IS THE ANSWER, not noise to skip
            # past: it is the difference between 「there is no such join」 and 「it is there
            # and not standing」, and the operator can only act on the second. `notes` is
            # where a switched-off declaration says so.
            withheld = str(refusal) if refusal else "; ".join(str(n) for n in notes)
        for rule in stood or ():
            if rule.get("name") != name:
                continue
            # 🪦 [판정 498 ④] THIS COMPARED `rule["mapper"]` TO AN IMPORTED CONSTANT.
            # The seat answers now. Measured equivalent rather than assumed: the rules walked
            # here come from `rule_shape.expand_declaration`, and the only join mapper it ever
            # stamps is `JOIN_INTO_MAPPER` (`rule_shape.py:139`) - it never emits the legacy
            # kind - so 「label is join」 and 「mapper is JOIN_INTO_MAPPER」 select the same rules
            # over this population, and the refusal below still means what it says.
            if rule_run.rule_label(rule) != "join":
                raise DerivationRefused(
                    REFUSE_JOIN_RULE_MISSING,
                    "rule %r exists but is not a join (`derive: {kind: \"join\"}`); the "
                    "gate cannot be resolved from it." % name)
            return _join_from_unified(db, rule)
    # 🔴 A REFUSAL CARRIES THE NEXT ACTION (판정 450 ③). The retirement refusal landed
    # the same night says 「→ 다음: …」 and this one stopped at 「absent」, which is two ways of
    # speaking in one house - and the half without an action leaves the operator to guess.
    #
    # ⚠️ THE LOADER'S SENTENCE IS QUOTED, NOT MERGED. It is written for the operator in
    # Korean and this one is the module's own English; running them together would build the
    # half-translated sentence `_record`'s own docstring warns about, so it rides in quotes
    # as what the loader said.
    if withheld:
        raise DerivationRefused(
            REFUSE_JOIN_RULE_MISSING,
            "join rule %r is declared but no rule stands for it, so the gate has no "
            "source. The loader said: %s" % (name, withheld))
    raise DerivationRefused(
        REFUSE_JOIN_RULE_MISSING,
        "join rule %r is absent from the chain declaration; the gate cannot be resolved "
        "without it. Next: declare it there as `derive: {kind: \"join\"}` with `on` for the "
        "join key and `take` for the columns to bring across." % name)


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

#: The second token, and the PHYSICAL SIDE it names.
#:
#: 🔴 `tl`/`tr` are the CANDIDATE spellings (`map_alignment.candidate_text`): the corner the
#:    equipment numbered its walk from. Both name the FRONT, because a numbering corner is not
#:    a claim that the wafer was flipped - that was the confusion the walk axis replaced
#:    (2026-08-08). The corner itself is not a side and is read by `parse_candidate`, not here.
#: 🔴 `front`/`back` stay accepted and MUST: rows confirmed before the walk axis existed hold
#:    those spellings, and `confirmed_meta_for` reads them to write `rotation`/`side`.
_SIDE_OF_TOKEN = {"front": "front", "back": "back", "tl": "front", "tr": "front"}


def parse_frame(text):
    """'rot90_back' -> (90, 'back'), 'rot90_tr' -> (90, 'front'). Unreadable -> None
    (the caller holds the row back).

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
    if side not in _SIDE_OF_TOKEN:
        return None
    return rot, _SIDE_OF_TOKEN[side]


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
                 meta_loader=None, slow_warn_ms=None) -> dict:
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
        # Composed by the SHARED primitive, not by joining the parts here. Every writer
        # and reader of a map identity goes through it, and an identity composed two ways
        # is an identity that eventually differs - the meta exists and nothing can find
        # it. It also refuses a partial identity by returning None.
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
    # 🔴 [S-7] 「성공했는데 «느렸다»」 — 예산이 «선언»됐을 때만 잰다.
    #    인자가 None 이면 이 칸이 «없다». `None` 이 아니다: `None` 은 「재 봤는데 안 느리다」는
    #    주장이고, 부재는 「이 경로는 안 잰다」다. 규칙에 키를 «잘못 적으면» 그 경로가
    #    「안 잰다」로 보이지, 조용히 「안 느리다」로 «거짓말하지» 않는다.
    # ⚠️ 정의는 «시계»다. 상한에 닿은 사실은 `truncated` 가 이미 말한다.
    if slow_warn_ms is not None:
        result["slow_reason"] = (event_constants.slow_sentence(elapsed, slow_warn_ms)
                                 if elapsed > slow_warn_ms else None)
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
                    min_population=DEFAULT_MIN_RETRACT_POPULATION,
                    slow_warn_ms=None) -> dict:
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

    _elapsed = (time.monotonic() - t0) * 1000.0
    # 🔴 [S-7] 「성공했는데 «느렸다»」 — 예산이 «선언»됐을 때만 잰다.
    #    인자가 None 이면 이 칸이 «없다». `None` 이 아니다: `None` 은 「재 봤는데 안 느리다」는
    #    주장이고, 부재는 「이 경로는 안 잰다」다. 규칙에 키를 «잘못 적으면» 그 경로가
    #    「안 잰다」로 보이지, 조용히 「안 느리다」로 «거짓말하지» 않는다.
    # ⚠️ 정의는 «시계»다. 상한에 닿은 사실은 `truncated` 가 이미 말한다.
    _slow = ({} if slow_warn_ms is None else
             {"slow_reason": (event_constants.slow_sentence(_elapsed, slow_warn_ms)
                              if _elapsed > slow_warn_ms else None)})
    return {
        **_slow,
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

    THE LEDGERS GO WITH THE ROW. `cell_sources` and `cell_overwrites` are keyed by
    `(table_name, row_id)` and nothing else, so a row deleted without them leaves
    records that no longer describe anything and that no query will ever join back to.
    `crud._apply_batch_updates_once` deletes exactly these two tables before it deletes
    the row on BOTH of its removal paths (the up-front purge and the scope diff); this
    is the same three statements in the same order, because a second way to remove a map
    row is a second chance to disagree about what removing one means.

    The orphans are not hypothetical: `dt_map` on this workstation carried 16,150
    `cell_overwrites` rows whose `row_id` no longer existed (measured 2026-08-12), which
    is what a purge that skipped the ledger leaves behind.
    """
    from database import models
    table_name = plan.get("target_table")
    model = models.DYNAMIC_TABLES.get(table_name)
    ids = plan.get("delete_row_ids") or []
    if model is None or not ids:
        return 0
    deleted = 0
    for i in range(0, len(ids), CHUNK):
        chunk = ids[i:i + CHUNK]
        db.query(models.CellSource).filter(
            models.CellSource.table_name == table_name,
            models.CellSource.row_id.in_(chunk)).delete(synchronize_session=False)
        db.query(models.CellOverwrite).filter(
            models.CellOverwrite.table_name == table_name,
            models.CellOverwrite.row_id.in_(chunk)).delete(synchronize_session=False)
        deleted += (db.query(model)
                    .filter(model.row_id.in_(chunk))
                    .delete(synchronize_session=False))
    db.commit()
    return deleted


# A malformed envelope raises plain `ValueError` (see `normalize_retraction_request`),
# so it deliberately has no code here - an unraised constant is the dead-reserved-value
# ambiguity `chain_bindings.ORIGIN_INHERITED` already left behind once.
REFUSE_RETRACTION_UNKEYED = "retraction_derived_keys_incomplete"


def require_scoped_batches_allowed(rule):
    """어느 «한 쪽» 권한이 봉투를 연다 — 전략별 검사는 배치마다 따로 한다.

    retract 만 쓰는 규칙이 자기에게 `allow_replace_map` 을 줄 필요가 «없어야» 한다.
    주면 «purge 권한»이 한 번도 purge 하지 않는 규칙에 서 있게 된다.
    """
    if not rule.get("allow_replace_map", False) and not rule.get("allow_retraction", False):
        raise ValueError(
            "rule '%s' returned scoped batches without allow_replace_map or allow_retraction"
            % (rule.get("name"),))


def normalize_scoped_batch(raw, rule, target_table) -> tuple:
    """범위 배치 «봉투» 하나 -> `(target_table, updates, scope, retract)`.

    🔴 «두 손으로 맞추던» 자리다. `chain_ingestion_worker` 와 `chain_replay` 가 같은 여섯
       규칙을 각자 적어 두고 「손으로 맞춘다」고 주석에 써 두었다 — 그리고 그 옆의 retract
       봉투는 이미 «한 독자»(§`normalize_retraction_request`)를 갖고 있었다. 같은 모양이다.
    ⚠️ 거절은 `ValueError` 다. 호출자가 «자기 거절 타입»으로 감싼다 — 형제가 이미 그 모양이고,
       그래야 이 독자가 어느 한 쪽의 예외 계층을 안 끌고 온다.

    ═══ 제거 전략은 «둘»이고 «동시에는 없다» ═══════════════════════════════════════════
    `replace_map` 은 «맵 단위»로 지운다 — 범위 안에서 페이로드가 다시 주장하지 않은 전부.
    한 맵에 생산자가 «하나»일 때 정확하다.
    `retract` 는 «소스 단위»로 지운다 — 이 소스가 갖고 있고 더는 유도하지 않는 것. 여러
    소스가 한 맵을 먹일 때의 전략이고, 그때 맵 범위 purge 는 이 소스를 고치려다 «형제의
    셀»을 지운다(맵 키는 「내 몫만」을 표현할 수 없다 — `derive_replace_map_scope` 가 모든
    범위 키를 맵 키 계약 «안»으로 검증하기 때문).
    한 배치에 둘 다 받으면 purge 가 «먼저» 돌고 그다음 생존자에 retract 가 걸린다 — 형제
    행은 좁은 전략이 보기도 전에 이미 사라진다. 그래서 «순서를 정하지 않고 거절»한다.
    """
    if not isinstance(raw, dict):
        raise ValueError("chain scoped batch must be an object")
    requested_target = raw.get("target_table") or target_table
    if requested_target != target_table:
        raise ValueError("rule '%s' cannot redirect scoped batch to '%s'"
                         % (rule.get("name"), requested_target))
    retract = raw.get("retract")
    if retract is not None and raw.get("replace_map"):
        raise ValueError(
            "rule '%s' set both replace_map and retract on one batch for '%s'. "
            "replace_map removes by MAP and retract removes by SOURCE; running both would "
            "purge the sibling sources' cells before the retraction could spare them."
            % (rule.get("name"), requested_target))
    updates = raw.get("updates") or ()
    if retract is not None:
        if not rule.get("allow_retraction", False):
            raise ValueError("rule '%s' returned a retract envelope without allow_retraction"
                             % (rule.get("name"),))
        return requested_target, updates, None, normalize_retraction_request(
            retract, rule.get("name"))
    if not raw.get("replace_map"):
        raise ValueError(
            "chain scoped batch must explicitly set replace_map=true or carry a retract envelope")
    scope = raw.get("scope")
    if not isinstance(scope, dict) or not scope:
        raise ValueError("chain scoped batch requires a non-empty scope")
    return requested_target, updates, scope, None


def normalize_retraction_request(request, rule_name=None) -> tuple:
    """`{"source_column": c, "source_value": v}` -> `(c, v)`, or a ValueError that NAMES it.

    One reader for the two consumers of the envelope (`chain_ingestion_worker` and
    `chain_replay`). They already have two spellings of the `replace_map` envelope's
    validation and those two have to be kept in step by hand; this one does not get a
    second copy.

    `ValueError` on purpose - it is what the worker's other envelope validations raise
    and what the API layer already maps to 400.
    """
    who = "chain rule '%s'" % (rule_name or "<unnamed rule>")
    if not isinstance(request, dict) or not request:
        raise ValueError("%s: a retract envelope must be a non-empty object naming "
                         "source_column and source_value" % who)
    column = request.get("source_column")
    value = request.get("source_value")
    if not isinstance(column, str) or not column.strip():
        raise ValueError("%s: retract envelope declares no 'source_column', so what this "
                         "source owns could not be selected and the fallback would be a "
                         "set difference over the whole table" % who)
    if _blank(value):
        raise ValueError("%s: retract envelope carries a blank 'source_value' for column "
                         "'%s'. A blank value would select every row whose source is "
                         "blank - the widening this envelope exists to avoid."
                         % (who, column))
    return column.strip(), value


def derived_keys_of(written_items, target_table: str, source_column: str) -> set:
    """The `business_key_val`s the write actually composed, for `plan_retraction`.

    Read back from the items the write mutated rather than recomposed here.
    `crud.assemble_composite_business_key` writes the key it built into
    `item.business_key_val`, and asking it for the answer is what guarantees this cannot
    disagree with the key the row was actually stored under. Recomposing the join from
    `composite_key_source` would be a second implementation of the same rule, and the
    two would diverge exactly when the separator or the blank handling changed.

    🔴 REFUSES on an item that came back without a key. `plan_retraction` treats "owned
    and not in derived_keys" as stale, so a key missing from this set is a row this
    source owns being marked for deletion. An incomplete set does not under-delete, it
    OVER-deletes, so it must not be allowed to look like a small one.
    """
    keys = set()
    unkeyed = 0
    for item in written_items or ():
        key = getattr(item, "business_key_val", None)
        if key is None or str(key).strip() == "":
            unkeyed += 1
            continue
        keys.add(key)
    if unkeyed:
        raise DerivationRefused(
            REFUSE_RETRACTION_UNKEYED,
            "%d of %d row(s) written to '%s' came back with no business_key_val, so the "
            "set of keys this derivation produced is incomplete. Retracting against it "
            "would treat every one of those rows as stale and DELETE what was just "
            "written. Refusing the retraction; the upsert itself already committed."
            % (unkeyed, len(list(written_items or ())), target_table))
    logger.debug("[DtMapRetraction] %s: %d derived key(s) for '%s'",
                 target_table, len(keys), source_column)
    return keys


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
