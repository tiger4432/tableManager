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

🔴 THE WRITE-JOIN HALF THAT SURVIVED IS STILL NOT IMPORTED HERE. `materialize: true`
declarations keep running in `chain.legacy_materialized_join` — the second write door, written
down as a debt in that module's own docstring — and this module borrows FUNCTIONS
(`notation_norm`'s folding, which is what makes a key expression match the unique index) and
never that engine, its caches or its declaration loader. What the two doors must NOT disagree
about is the KEY, and that is why the fold comes from the shared function rather than from a
second spelling here.

⚠️ AND THAT LEAVES ONE HONEST COST, WRITTEN DOWN. `legacy_materialized_join.join_onclause`
calls itself 「ON 절의 유일한 철자」, and this module builds an ON clause too. Two spellings that
must agree is the 「같은 기능에 두 경로」 shape — so the fold and the `coalesce` are taken from
the same place the index is built from. That cost lives exactly as long as the second door does.
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
JOIN_CELLS = ("right_table", "on", "take")


def unknown_cells(spec: dict) -> list:
    return sorted(str(key) for key in (spec or {}) if key not in JOIN_CELLS)


def right_key(rule: dict) -> tuple:
    """(the right table, its join columns, the folds) - what a unique index on it would need.

    🔴 [S-240] ASKED HERE BECAUSE THE FOLD IS DECIDED HERE. The index and the join must be
    built from the SAME expression or PostgreSQL silently stops using the index (S-181), and
    this module already computes the fold from the two tables' notation declarations. A
    second computation in the shell would be the second author 판정 397 removed.

    ⚠️ AND THIS MODULE STILL DOES NOT KNOW THE OTHER JOIN DOOR EXISTS. It hands back the three
    values; whoever builds an index is the shell's business.
    """
    spec = join_spec(rule)
    left_table = str((rule or {}).get("target_table") or "")
    pairs = _pairs(spec, left_table)
    return (str(spec.get("right_table") or ""),
            [right for _left, right, _fold in pairs],
            [fold for _left, _right, fold in pairs])


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
    return ""


def _answer(db, spec, left_model, right_model, where, left_table=""):
    """One SELECT: the left rows in scope, LEFT JOINed to their right row.

    🔴 LEFT JOIN, NOT A SECOND QUERY FOR THE UNMATCHED. `matched` is 「the right row exists」,
    and it has to be a fact the database states - deciding it from 「the value came back NULL」
    would make a matched row whose value is legitimately NULL indistinguishable from a row
    that matched nothing, and those two get OPPOSITE treatment below.
    """
    from sqlalchemy import and_, select

    onclause = and_(*[_folded(getattr(left_model, left_col), fold)
                      == _folded(getattr(right_model, right_col), fold)
                      for left_col, right_col, fold in _pairs(spec, left_table)])
    columns = [left_model.row_id.label("row_id"),
               (right_model.row_id.isnot(None)).label("matched"),
               # 🔴 [S-280 · 판정 434] THE ROW THAT ANSWERED. `matched` above is already
               # computed FROM this column, so the join reads it either way; naming it
               # keeps the note a retraction aims with instead of collapsing it to a bool.
               right_model.row_id.label("origin_row_id")]
    columns.extend(getattr(right_model, right_col).label("take_%d" % index)
                   for index, (right_col, _into) in enumerate(_takes(spec)))
    stmt = select(*columns).select_from(
        left_model.__table__.outerjoin(right_model.__table__, onclause)).where(where)
    return db.execute(stmt).fetchall()


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


def _apply(db, left_table: str, updates) -> int:
    """Apply what `propose` built. Returns rows written.

    🔴 [판정 567] THE WRITING IS ITS OWN STEP, because a mapper does not write - it
    PROPOSES, and the caller's batch writes inside the chain envelope. The items are built
    once, by `_update_items`, whichever door this join is reached through; only whether this
    function runs differs between them. Copying the item-building into the mapper would put
    the layer label, the origin row and the fan-out net in two places, and those are exactly
    the cells that go wrong silently.

    ⚰️ THIS GOES WITH `run`. Once nothing writes for itself, the caller's batch is the only
    writer and this function has no caller.
    """
    from database import crud, schemas

    if not updates:
        return 0
    crud.apply_batch_updates(db, left_table,
                             schemas.GeneralUpdateBatch(updates=updates, silent=True))
    return len(updates)


def propose(db, rule: dict, row_ids=None):
    """What this join would change, as update items — and why, when it is nothing.

    🔴 [판정 567] THE BODY THE DYNAMIC MAPPER RUNS. A mapper proposes and the caller
    writes, so the answer has to be separable from the act. Nothing here decides anything a
    different way; the last step is simply not taken.
    """

    # ⚠️ ONE KIND, TWO SIDES, AND THE RULE SAYS WHICH. A rule triggered on the LEFT table
    # recomputes the rows that moved; a rule triggered on the RIGHT table recomputes the left
    # rows whose key now resolves differently. The side is read from the declaration
    # (`trigger_table` against `right_table`) rather than from which argument the caller
    # passed, so a caller cannot put a rule on the wrong side by accident.
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
        where = _left_rows_for_reference(db, spec, left_model, right_model,
                                         rows_in, left_table)
    else:
        where = left_model.row_id.in_(rows_in)
    if where is None:
        return {"updates": [],
                "refusal": "기준 표의 이번 변경이 이 규칙의 왼쪽 행을 하나도 가리키지 않습니다"}

    rows = _answer(db, spec, left_model, right_model, where, left_table)
    updates = _update_items(db, left_table, rows, spec,
                            str((rule or {}).get("name") or ""))
    written = len(updates)
    # ⚠️ TWO DIFFERENT ZEROS, AND THE OPERATOR FIXES THEM DIFFERENTLY: no match means the
    #    join key or the right table's data; a match that wrote nothing means the value was
    #    already there. Collapsing them sends half the readers to the wrong repair.
    refusal = None
    if not written:
        refusal = ("오른쪽 표에서 짝을 찾은 행이 없습니다 (넘어온 %d 행)" % len(rows_in)
                   if not rows else
                   "짝은 찾았고 채울 값이 이미 같습니다 (%d 행)" % len(rows))
    return {"updates": updates, "rows_in": len(rows_in), "refusal": refusal, "side":
            "reference" if reference_side else "target"}


def run(db, rule: dict, row_ids=None, done=None, **_):
    """The self-writing entry: propose, then apply.

    ⚰️ THIS DOCSTRING SAID 「this whole function goes when the kind table does」. The kind
    table went on 2026-09-17 and this did NOT: it is the body `chain.dynamic_mappers._join`
    registers, because the registration it replaced named it. What retires it is the round
    that gives every door a batch writer, and until then the doors with none reach the write
    through here.
    """
    outcome = propose(db, rule, row_ids)
    updates = outcome.get("updates") or []
    written = _apply(db, str((rule or {}).get("target_table") or ""), updates)
    answer = {key: value for key, value in outcome.items() if key != "updates"}
    answer["written"] = written
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
    return tuple_(*left_key).in_([tuple(row) for row in keys])
