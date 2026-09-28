# -*- coding: utf-8 -*-
"""`declared:join` — 통합 선언의 `join` 종류가 «쓰는» 조인 (S-237, 소유자 판정 셋).

🔴 WHY THE NAME IS `join_into` AND NOT `builtin:join`. That id was taken: the READ-TIME join's
loader registered it, and the registry refused a second claimant by name (measured — the gate
scores that collision). ⚠️ [판정 591] THAT SENTENCE NAMED `register_builtin` IN THE PRESENT
TENSE and the function was deleted on 2026-09-17; the PROPERTY moved rather than died, and
`mapper_sdk.register` raises `MapperNameClaimedTwice` today (판정 409, confirmed in 584). The
class of mistake is 「a ruling indexed by its mechanism dies with it」 - the mechanism was
renamed and the sentence went with it. The two were told apart by the cell the internal rule already
used: the read-time one answered at `into.read`, this one writes `into.table`. So `join_into`
names the axis rather than the round it arrived in — 「unified」 stops distinguishing anything
the day enrich and mapper move over too.

⚰️ THE COLLISION IS HISTORY AND THE NAME MOVED ANYWAY (판정 600, 2026-09-17). This paragraph
said 「the name stays」 because renaming would make an operator migrate a live declaration. The
owner was asked and the answer was 「없다」 — no production declaration writes the `mapper` cell
by hand, so the migration cost that argument rested on is ZERO and the lead retracted 562/567's
「이름은 안 옮긴다」. The value is `declared:join` now; `JOIN_INTO_MAPPER`, the CONSTANT, keeps
its name because it is the code's word and not the operator's.

⚰️ [판정 652 3걸음] THE SECOND WRITE DOOR IS GONE, AND WITH IT THE DEBT. These two paragraphs
said `materialize: true` declarations keep running in `chain.legacy_materialized_join` and
that its `join_onclause` was a second spelling of the ON clause this module also builds —
「같은 기능에 두 경로」, written down as a cost that 「lives exactly as long as the second door
does」. That door was deleted, so this is now the only door and the only spelling.

🔴 WHAT SURVIVED THE DELETION IS THE REASON THE COST WAS SURVIVABLE. The fold and the
`coalesce` are still taken from the place the index is built from (`notation_norm`'s folding,
`join_key_index`'s expression) rather than spelled here — not because a second door might
disagree, but because the INDEX is the other party and it always was. A key this module folds
one way and the index folds another does not fail; it stops matching the index.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("Chain.JoinInto")

#: The kind an operator's `derive: {kind: "join"}` becomes. One string, read by the translator
#: that writes it and by the table that runs it, so the two cannot drift.
JOIN_INTO_MAPPER = "declared:join"
#: The one layer every chain write carries; the worker's wake filter reads exactly this.
CHAIN_LAYER = "chain_ingestion"


def join_spec(rule: dict) -> dict:
    """The join this rule describes. `params` IS the spec - no second shape in between."""
    return dict((rule or {}).get("params") or {})


def _pairs(spec: dict, left_table: str = "") -> list:
    """`on` as (left column, right column, fold rules).

    🔴 THE FOLD IS COMPUTED, NEVER AUTHORED (판정 397). Today it is derived from the two
    TABLES' notation declarations by `notation_norm.join_pair_rules`, and the unique index is
    built from the same source - so letting a join declare its own fold would make a second
    author of one fact, free to disagree with the index expression. An author who wants a
    different fold changes the table's notation declaration, where the index can see it.

    ⚠️ 「EITHER SIDE DECLARED」 MEANS BOTH SIDES FOLDED, and that rule lives in the shared
    function rather than here: a join folded on one side does not merely fail to help, it
    silently drops matches the unfolded join was already making."""
    import notation_norm

    right_table = str(spec.get("right_table") or "")
    out = []
    for pair in spec.get("on") or ():
        if not isinstance(pair, dict):
            continue
        left, right = pair.get("left"), pair.get("right")
        if left and right:
            fold = (notation_norm.join_pair_rules(left_table, str(left),
                                                  right_table, str(right))
                    if left_table and right_table else None)
            out.append((str(left), str(right), fold))
    return out


#: The sub-cells of `derive.join` this product reads. Anything else is NAMED, never refused
#: (판정 397 자세) - a cell the product does not know may be a live argument it has not
#: learned yet, and refusing it would stop a rule that works.
#: ⚰️ [총괄 e91b96a28] `right_table` left this list: the declaration's `on.table` names the source
#:    and `rule_shape.as_chain_rule` fills the spec's `right_table` from it. The engine below still
#:    reads `spec["right_table"]` - that is the internal spec, not a cell anyone writes.
JOIN_CELLS = ("on", "take")

#: The skeleton node of each join cell that is NOT one value - read by `_pairs` (`on`: a list
#: of {left, right}) and `_takes` (`take`: a list of names). A cell missing here is a value.
#: ⚠️ `take` also reads a {from, into} item; the vocabulary has no union, so the item is drawn
#:    as a name and the record form stays in the raw editor - named, never refused.
JOIN_CELL_SHAPES = {
    "on": {"kind": "map", "keyed_by": "index", "member": "pair",
           "of": {"kind": "record", "fields": [
               {"key": "left", "required": False, "node": {"kind": "leaf", "hint": "free"}},
               {"key": "right", "required": False, "node": {"kind": "leaf", "hint": "free"}}]}},
    "take": {"kind": "map", "keyed_by": "index", "member": "column",
             "of": {"kind": "leaf", "hint": "free"}},
}


def unknown_cells(spec: dict) -> list:
    return sorted(str(key) for key in (spec or {}) if key not in JOIN_CELLS)


def pairs(rule: dict) -> list:
    """이 규칙의 `on` — `(왼쪽 컬럼, 오른쪽 컬럼, 폴드)` 들.

    🔴 [판정 678] THE SAME BODY `right_key` USES, GIVEN A NAME SO NOBODY COMPUTES IT TWICE.
    The approval report needs the LEFT column to say 「left = right」 and the fold to say why
    an index has that shape, and the walker that decides which index to build hands back the
    right side only. Reaching into `_pairs` from outside, or recomputing the fold there,
    would make a second author of a fact 판정 397 gave exactly one - and the fold is the
    cell where that bites silently (a mismatch does not fail, it stops using the index).
    """
    return _pairs(join_spec(rule), str((rule or {}).get("target_table") or ""))


def takes(rule: dict) -> list:
    """이 규칙의 `take` — `(오른쪽 컬럼, 왼쪽에 적히는 이름)` 들. `pairs` 와 같은 이유로 공개다."""
    return _takes(join_spec(rule))


def right_key(rule: dict) -> tuple:
    """(the right table, its join columns, the folds) - what a unique index on it would need.

    🔴 [S-240] ASKED HERE BECAUSE THE FOLD IS DECIDED HERE. The index and the join must be
    built from the SAME expression or PostgreSQL silently stops using the index (S-181), and
    this module already computes the fold from the two tables' notation declarations. A
    second computation in the shell would be the second author 판정 397 removed.

    ⚠️ AND THIS MODULE STILL DOES NOT KNOW THE OTHER JOIN DOOR EXISTS. It hands back the three
    values; whoever builds an index is the shell's business.
    """
    on = pairs(rule)
    return (str(join_spec(rule).get("right_table") or ""),
            [right for _left, right, _fold in on],
            [fold for _left, _right, fold in on])


def _takes(spec: dict) -> list:
    """`take` as (right column, left column). `into` defaults to the right column's name."""
    out = []
    for item in spec.get("take") or ():
        if isinstance(item, str):
            out.append((item, item))
        elif isinstance(item, dict) and item.get("from"):
            out.append((str(item["from"]), str(item.get("into") or item["from"])))
    return out


def _folded(column, fold):
    """The key expression, folded and NULL-safe - the SAME shape the unique index has.

    🔴 `coalesce(..., '')` IS NOT A STYLE CHOICE (S-181, 판정 285·287). NULL equals NULL where
    keys are compared, and PostgreSQL uses an expression index only when the query's
    expression MATCHES it - a mismatch here does not fail, it turns a join into a sequential
    scan while every test stays green.
    """
    import notation_norm

    # 🔴 [S-245] ONE AUTHOR. This seat learned the type fold first (the owner met the
    # `number` key here), and the read-time ON clause and the index DDL did NOT - so one key
    # had two shapes depending on which door asked. The pair in `notation_norm` is now the
    # only place any of the three is spelled.
    #
    # ⚠️ AND THE ORDER CHANGED WITH THE MOVE: the cast is applied to the COLUMN, before
    # the fold, rather than to whatever the fold returned. The fold construct declares a
    # String type, so asking it afterwards could only ever answer 「already text」 - which is
    # right today only because the declaration validator refuses a fold on a non-string
    # column. Asking the column is the question we actually mean.
    return notation_norm.key_expression_sql(column, fold)


def _models(spec: dict, left_table: str):
    from database import models

    left = models.DYNAMIC_TABLES.get(left_table)
    right = models.DYNAMIC_TABLES.get(str(spec.get("right_table") or ""))
    return left, right


def _missing(spec: dict, left_table: str, left_model, right_model) -> str:
    """Why this rule cannot run, by NAME, or `""`.

    ⛔ A JOIN THAT CANNOT RUN IS REFUSED WITH ITS REASON, never skipped quietly: a rule that
    sits enabled and writes nothing is indistinguishable from one that had nothing to write.
    """
    if not left_table:
        return "the rule names no table to write into"
    if left_model is None:
        return "left table %r is not among this process's declared tables" % left_table
    if right_model is None:
        return "right table %r is not among this process's declared tables" % (
            spec.get("right_table") or "")
    if not _pairs(spec, left_table):
        return "`on` names no usable left/right column pair"
    if not _takes(spec):
        return "`take` names no column to bring across"
    for left_col, right_col, _fold in _pairs(spec, left_table):
        if not hasattr(left_model, left_col):
            return "left column %r does not exist on %r" % (left_col, left_table)
        if not hasattr(right_model, right_col):
            return "right column %r does not exist on %r" % (
                right_col, spec.get("right_table"))
    for right_col, into_col in _takes(spec):
        if not hasattr(right_model, right_col):
            return "take column %r does not exist on %r" % (
                right_col, spec.get("right_table"))
        if not hasattr(left_model, into_col):
            return "target column %r does not exist on %r" % (into_col, left_table)
    for required in _required(spec):
        if not hasattr(right_model, required):
            return "require column %r does not exist on %r" % (
                required, spec.get("right_table"))
    return ""


def _required(spec: dict) -> list:
    """The value-table columns an answer row must have filled (`on.require`)."""
    import chain_bindings

    return [str(column) for column in spec.get(chain_bindings.REQUIRE_KEY) or ()]


class _Answer:
    """One row the LEFT JOIN used to return - a left row and its right row, or none."""

    __slots__ = ("_mapping", "matched")

    def __init__(self, row_id, origin_row_id, values):
        self._mapping = {"row_id": row_id, "origin_row_id": origin_row_id}
        self._mapping.update(("take_%d" % index, value) for index, value in enumerate(values))
        # 🔴 `matched` is 「the right row exists」, never 「the value came back NULL」: a matched
        #    row whose value is legitimately NULL and a row that matched nothing get OPPOSITE
        #    treatment in `_update_items`.
        self.matched = origin_row_id is not None


def _read_once(db, spec, left_model, right_model, wheres, left_table=""):
    """Everything the answer depends on, read ONCE: -> (sorted [(left row_id, key)],
    {key: [(right row_id, take values)]}).

    🔴 [총괄 529fc7ce8 ②] BEFORE ANY WRITE, BECAUSE THE PAGES ARE WRITTEN IN BETWEEN. The seat
    writes a page before it asks the next, and a rule before this one in the group may already
    have written the right value or the left key - measured, pages two on then read what that
    rule wrote while one write had read what was there before it. A page only slices this.
    The key is the folded expression on both sides (S-181), compared here instead of in an ON.
    """
    from sqlalchemy import select, tuple_

    from chain import keyset_scan
    from database import crud

    pairs = _pairs(spec, left_table)
    left_key = [_folded(getattr(left_model, left_col), fold) for left_col, _r, fold in pairs]
    left = {}
    for where in wheres:
        for row in db.execute(select(left_model.row_id, *left_key).where(where)):
            left[row[0]] = tuple(row[1:])
    right_key = [_folded(getattr(right_model, right_col), fold) for _l, right_col, fold in pairs]
    takes = [getattr(right_model, right_col) for right_col, _into in _takes(spec)]
    # 🔴 [총괄 2276e38cf] A value row with an empty `require` column is not an answer, from
    #   whichever side the join woke - the SQL twin of the seat's `crud.is_blank_value`.
    filled = [crud.not_blank_sql_condition(crud.column_text_sql(getattr(right_model, column)))
              for column in _required(spec)]
    answers = {}
    width = len(right_key)
    for chunk in crud._chunks(sorted(set(left.values())), keyset_scan.DEFAULT_CHUNK_SIZE):
        for row in db.execute(select(right_model.row_id, *right_key, *takes)
                              .where(tuple_(*right_key).in_(chunk), *filled)):
            answers.setdefault(tuple(row[1:1 + width]), []).append(
                (row[0], tuple(row[1 + width:])))
    return sorted(left.items()), answers


def _update_items(db, left_table: str, rows, spec, source_name: str):
    """What this join says should change - as update items, written by somebody else.

    🔴 [판정 567] THIS IS THE BODY THE DYNAMIC MAPPER CARRIES. It was inside `_write`,
    which meant 「compute the answer」 and 「apply it」 were one act and a mapper could not
    borrow the first without the second.

    🔴 A MATCHED NULL IS WRITTEN AS NULL, AN UNMATCHED ROW IS NOT WRITTEN (판정 f3c04dee).
    The first is an answer - the right row exists and says the value is empty - and skipping
    it would leave a stale value standing where the declaration says there is none. The second
    is 「no answer」, and writing NULL for it would erase a value this join never spoke about.
    """
    from database import crud, schemas

    takes = _takes(spec)
    # THE ROW-LEVEL NET (principle 2). If the SELECT returned two answers for one left
    # row, the right side fanned out for THAT key despite the gates. Neither answer is
    # THE answer, so neither is written; those rows are named once and the rest proceed.
    seen = {}
    for row in rows:
        rid = row._mapping["row_id"]
        seen[rid] = seen.get(rid, 0) + 1
    fanned = sorted(rid for rid, n in seen.items() if n > 1)
    if fanned:
        # 🔴 [S-247] THE LINE CARRIES ITS NEXT ACTION. 소유자 2026-09-15: 「난 이 에러를
        # 이해할 수가 없다, 조치를 뭘 해야 하는지 안 알려줌」 - and production logs cannot
        # be pasted out, so the line has to answer alone. This one is DATA: the right table
        # holds two rows under one join key, and widening the declaration would not change
        # that.
        import operator_line

        logger.warning("%s", operator_line.line(
            "join_into", source_name,
            "왼쪽 행 %d 개가 오른쪽에서 «둘 이상»과 맞아 건너뜁니다 — 어느 쪽이 답인지 "
            "제품이 고를 수 없습니다" % len(fanned),
            operator_line.fold_the_data(
                str(spec.get("right_table") or "오른쪽 표"),
                [right for _l, right, _f in _pairs(spec, left_table)]),
            fanned))
    updates = []
    for row in rows:
        if not row.matched or seen.get(row._mapping["row_id"], 0) > 1:
            continue
        mapping = row._mapping
        updates.append(schemas.GeneralUpdateItem(
            row_id=mapping["row_id"],
            updates={into_col: mapping["take_%d" % index]
                     for index, (_right, into_col) in enumerate(takes)},
            # 🔴 [S-280 · 판정 434] Only matched rows reach here (the `continue` above), so
            # this is never the id of a row that did not answer.
            origin_row_id=mapping["origin_row_id"],
            # 🔴 THE LAYER IS THE CHAIN'S, THE AUTHOR IS THE RULE'S (owner 2026-09-15, 「핑퐁은
            # 제대로 고쳐」). The first cut put the rule name in the LAYER so an operator could
            # see who wrote the cell - and that name was also what the worker's wake filter
            # reads: a write labelled anything but `chain_ingestion` wakes every rule on that
            # table, so this join's writes re-woke the enrich that feeds it. One label for
            # every chain write keeps the opt-in (`allow_chain_trigger`) the ONLY way a chain
            # write wakes a rule; `updated_by` still says which rule, and it is constant per
            # rule so an unchanged value stays a no-op write.
            source_name=CHAIN_LAYER,
            updated_by=source_name))
    return updates


# ⚰️ [판정 567 · 총괄 2026-09-23] `_apply` AND `run` RETIRED TOGETHER. `_apply`'s own
#    tombstone predicted this: 「Once nothing writes for itself, the caller's batch is the only
#    writer and this function has no caller」. `_join` calls `propose` now and the seat writes.
# 🔴 THE SYMPTOM THEY LEFT, kept as the control group: the FIRST attempt at this, on
#    2026-09-17, changed the body to `propose` WITHOUT giving every door a batch writer, and
#    the doors that had none dropped the rows silently - `rows_in=4 rows_out=4 written=None`.
#    What made it safe this time is that the last door without one (replay's row-ids arm) is
#    collapsed in this same commit. Reinstate either half alone and that log line comes back.

def propose(db, rule: dict, row_ids=None):
    """What this join would change, as update items — and why, when it is nothing.

    🔴 [판정 567] THE BODY THE DYNAMIC MAPPER RUNS. A mapper proposes and the caller
    writes, so the answer has to be separable from the act. Nothing here decides anything a
    different way; the last step is simply not taken.
    """

    # ⚠️ ONE KIND, TWO SIDES, AND THE RULE SAYS WHICH. The declaration's own rule is triggered
    # on the RIGHT (source) table and recomputes the left rows whose key now resolves
    # differently; its `:target` companion is triggered on the LEFT table and recomputes the
    # rows that moved. The side is read from the rule (`trigger_table` against the spec's
    # `right_table`) rather than from which argument the caller passed.
    spec = join_spec(rule)
    left_table = str((rule or {}).get("target_table") or "")
    rows_in = list(row_ids or ())
    # 🔴 [판정 525 ②] EVERY ZERO EXIT SAYS WHY. This kind is product code, so 「왜 0 인가」 is
    #   a question it can answer - and until it did, the operator's queue cell said only
    #   that no rows came out, which they could already see.
    if not rows_in:
        return {"updates": [], "refusal": "이 규칙이 볼 행이 넘어오지 않았습니다"}

    left_model, right_model = _models(spec, left_table)
    refusal = _missing(spec, left_table, left_model, right_model)
    if refusal:
        return {"updates": [], "refusal": refusal}

    reference_side = str((rule or {}).get("trigger_table") or "") == str(
        spec.get("right_table") or "")
    if reference_side:
        wheres = _left_rows_for_reference(db, spec, left_model, right_model,
                                          rows_in, left_table)
    else:
        wheres = [left_model.row_id.in_(rows_in)]
    if wheres is None:
        return {"updates": [],
                "refusal": "기준 표의 이번 변경이 이 규칙의 왼쪽 행을 하나도 가리키지 않습니다"}

    # 🔴 [총괄 e10c58e5e] PAGES OF LEFT ROWS. One source row can match hundreds of thousands of
    #    left rows, and one SELECT and one write of all of them held the chain for minutes with
    #    no beat. The left rows are read ONCE - asking the key filter again per page re-walks
    #    the table from the cursor (measured: a page past the last match read 9,999 rows for 0)
    #    - and each page answers only its own rows. The seat writes a page, then asks the next.
    left_rows, answers = _read_once(db, spec, left_model, right_model, wheres, left_table)
    return _page(db, rule, spec, left_table, left_rows, answers, 0, len(rows_in),
                 "reference" if reference_side else "target")


def _page(db, rule, spec, left_table, left_rows, answers, start, handed, side):
    """One page of left rows answered from what was read once - and the call for the next."""
    from chain import keyset_scan

    size = keyset_scan.DEFAULT_CHUNK_SIZE
    blank = (None,) * len(_takes(spec))
    rows = [_Answer(row_id, origin, values)
            for row_id, key in left_rows[start:start + size]
            for origin, values in (answers.get(key) or [(None, blank)])]
    updates = _update_items(db, left_table, rows, spec, str((rule or {}).get("name") or ""))
    more = start + size < len(left_rows)
    # ⚠️ TWO DIFFERENT ZEROS, AND THE OPERATOR FIXES THEM DIFFERENTLY: no match means the
    #    join key or the right table's data; a match that wrote nothing means the value was
    #    already there. Collapsing them sends half the readers to the wrong repair.
    #    Said only by an answer that is ONE page: an empty first page says nothing of the rest.
    refusal = None
    if not updates and not more and not start:
        refusal = ("오른쪽 표에서 짝을 찾은 행이 없습니다 (넘어온 %d 행)" % handed
                   if not rows else
                   "짝은 찾았고 채울 값이 이미 같습니다 (%d 행)" % len(rows))
    answer = {"updates": updates, "rows_in": handed, "refusal": refusal, "side": side,
              "next_page": (lambda: _page(db, rule, spec, left_table, left_rows, answers,
                                          start + size, handed, side))
              if more else None}
    if not start:
        # 🔴 [총괄 529fc7ce8 ①] THE COUNT IS ALL THE PAGES', read off what was read once: a row
        #    with exactly one right answer is one proposed row, on whichever page it lands.
        answer["rows_total"] = sum(1 for _id, key in left_rows if len(answers.get(key) or ()) == 1)
    return answer


def _left_rows_for_reference(db, spec, left_model, right_model, right_row_ids,
                            left_table=""):
    """The left rows whose key matches the right rows that just moved.

    🔴 ONLY THE WHERE CLAUSE DIFFERS between the two sides, which is the whole reason this is
    one kind and not two. The key expression comes from the same `_folded`, so a fold declared
    once cannot apply on one side and not the other.
    """
    from sqlalchemy import select, tuple_

    pairs = _pairs(spec, left_table)
    keys = db.execute(
        select(*[_folded(getattr(right_model, right_col), fold).label("k%d" % index)
                 for index, (_left, right_col, fold) in enumerate(pairs)])
        .where(right_model.row_id.in_(list(right_row_ids)))).fetchall()
    if not keys:
        return None
    left_key = [_folded(getattr(left_model, left_col), fold)
                for left_col, _right, fold in pairs]
    # ⚠️ A TUPLE `IN`, NOT A COLUMN-WISE `IN` PER PART. Matching each part independently
    # would pull in every left row that shares ONE part of the key with ONE changed right
    # row - a cross product wearing the shape of a filter. One spelling for one key and
    # several, because a second branch for the single-column case is a second answer to the
    # same question (verified on this SQLite/SQLAlchemy pair by S-229's paging).
    # 🔴 ONE FILTER PER PAGE OF KEYS (총괄 a4bc9af48). A two-column tuple IN of 10,000 keys is
    #    a statement PostgreSQL refuses to plan (StatementTooComplex, measured) - and a group
    #    carries up to 20,000 rows.
    from chain import keyset_scan
    from database import crud

    distinct = list(dict.fromkeys(tuple(row) for row in keys))
    return [tuple_(*left_key).in_(chunk)
            for chunk in crud._chunks(distinct, keyset_scan.DEFAULT_CHUNK_SIZE)]
