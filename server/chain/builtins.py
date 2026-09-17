# -*- coding: utf-8 -*-
"""What the PRODUCT contributes to the chain: synthesised rules, and the kinds that run them.

🔴 ONE SYNTHESIS SEAT (판정 304). `load_chain_rules` calls `synthesize_chain_rules` and
nothing else, and that function calls each half. 판정 292 forbids two synthesisers; putting
the join half inside `load_enrichment_chain_rules` would have satisfied the letter of that
while making a function named `enrichment_…` read the virtual-join file — a name that lies is
a cost paid by whoever next looks for where a declaration becomes a chain rule. Each half
keeps an honest name and reads its own file; the SEAT is what is singular.

🔴 ONE TABLE OF `builtin:` KINDS (판정 305). Measured before building: `builtin:auto_confirm`
appeared exactly twice, both in `enrichment_config`, and NOTHING read it — S-179 declared the
kind for the loader and graph layers and left execution in the auto-confirm sweep. So this is
the FIRST dispatcher the `builtin:` vocabulary has ever had.

🔵 AND THE TEMPORARY IS OVER (S-195). It carried one kind while auto-confirm still ran from
its own sweep, so a follow-up kind had two ways to run; both are in the table now and there is
one route. What made that survivable in between was that it was WRITTEN DOWN and queued — a
temporary nobody records is just a drift with a date on it.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("Chain.Builtins")


#: (half, what stops running - for the LOG, and for the SCREEN). 🔴 IT IS A TABLE AND NOT
#: TWO `except` BLOCKS because the two halves must be reported the same way: a half that
#: fails quietly in a different voice is how 「what is not running」 becomes 「nothing is
#: declared」.
#:
#: 🔴 AND BOTH RENDERINGS LIVE HERE, WHICH IS THE POINT (판정 454 ③). This repository writes
#: logs in English and screens in Korean, so a screen that composed its own sentence would
#: make one fact have two authors, free to disagree about WHICH half and WHAT stopped - the
#: door-splitting this round removes. The seat that knows the halves holds both spellings
#: and each surface takes its own out of here.
_SYNTHESIS_HALVES = (
    ("enrichment", "dedup and auto-confirm rules are NOT running",
     "중복 제거·자동 확정 규칙이 돌지 않습니다"),
    ("virtual join", "materialised join rules are NOT running",
     "표에 쓰는 조인 규칙이 돌지 않습니다"),
)


def synthesis_half_says(half: str) -> str:
    """The Korean sentence for what a failed half takes down. One author, two surfaces."""
    for name, _log, screen in _SYNTHESIS_HALVES:
        if name == half:
            return screen
    return ""


def synthesize_chain_rules(known_tables: dict = None, failures: list = None) -> list:
    """Every chain rule the product derives from a declaration the operator wrote.

    🔴 THE TWO HALVES FAIL SEPARATELY (판정 452 ②). They used to be one expression, so
    ANYTHING raising in the virtual-join half took the enrichment half down with it - and
    the caller's `except` logged one line and carried on with NO synthesised rules at all,
    dedup and auto-confirm included. That mattered when step 4 removed the `virtual_join`
    package: the import raised, and a single `except` would have made the failure read as
    「this box declares no enrichment」 rather than 「the join half is gone」.

    ⚠️ A FAILING HALF IS REPORTED, NEVER GUESSED AT. `failures` collects
    `(half, what stops running, the error)` the way `rejections` does elsewhere in this
    codebase; a caller that passes nothing still gets whichever half stood, because the
    alternative - raising - is what made one half able to kill the other.

    ⚠️ THE ENRICHMENT HALF IS UNCHANGED, BYTE FOR BYTE, and it still runs FIRST. This seat
    only moved its CALL; a test compares the list before against after, because a move that
    quietly reorders or drops a rule would be invisible until a chain stopped firing.
    """
    def _enrichment():
        import enrichment.config
        return enrichment.config.load_enrichment_chain_rules(known_tables=known_tables)

    def _joins():
        from chain import legacy_join_declaration
        return legacy_join_declaration.synthesized_join_chain_rules(known_tables=known_tables)

    rules = []
    for (half, stops, says), produce in zip(_SYNTHESIS_HALVES, (_enrichment, _joins)):
        try:
            rules.extend(produce() or ())
        except Exception as exc:                                   # noqa: BLE001
            logger.error("[ChainRules] the %s half of synthesis failed, so %s: %s",
                         half, stops, exc)
            if failures is not None:
                failures.append({"half": half, "stops": stops, "says": says,
                                 "error": str(exc)})
    return rules


def written_in(rule) -> str:
    """The file a rule THIS SEAT produced was written in, by basename (S-234 ①).

    🔴 FOR THE LOADER'S ONE-NAMESPACE REFUSAL: a name claimed twice is named with the files
    to look in. The join half emits `JOIN_MAPPER` and nothing else out of this seat does, so
    that one cell separates the two files.

    ⚠️ ONLY FOR RULES THAT CAME OUT OF `synthesize_chain_rules`. The loader tags what it read
    from `chain_rules.json` by position, never through here — a unified `decide` written in
    that file also carries `origin: synthesized:` and would otherwise be misfiled.

    🪦 `synthesized_kind_counts` sat here for the 「Synthesized N (a dedup · b auto-confirm ·
    c join)」 boot line. That line folded into the loader's set line, which names every rule
    with its origin and kind, so a count of kinds had no reader left.
    """
    import enrichment.config
    from chain import legacy_join_declaration

    if (rule or {}).get("mapper") == legacy_join_declaration.JOIN_MAPPER:
        return os.path.basename(legacy_join_declaration.VIRTUAL_JOIN_RULES_PATH)
    return os.path.basename(enrichment.config.ENRICHMENT_RULES_PATH)


# ---------------------------------------------------------------------------
# the `builtin:` table
# ---------------------------------------------------------------------------

class UnknownBuiltinKind(ValueError):
    """⛔ REFUSED BY NAME, NEVER IGNORED. A rule naming a kind nothing implements would
    otherwise sit enabled, look live, and never run — the same silence
    `_report_unwatchable_trigger_columns` exists to break for a mistyped trigger column."""


def _run_join(db, rule, row_ids=None, key_values=None, done=None, **_):
    """`builtin:join` — materialise one join rule's answer onto its target rows.

    ⚠️ TWO TRIGGERS, ONE KIND. Target rows moved (cheap, no ceiling) or a reference row moved
    (counts first, refuses over the rule's declared ceiling). The caller says which by which
    argument it passes; both land in the same declaration.
    """
    from chain import legacy_materialized_join as vje

    joined = (rule or {}).get("params") or {}
    if key_values is not None:
        return vje.on_reference_rows_changed(db, joined, list(key_values))
    return vje.on_target_rows_changed(db, joined, list(row_ids or ()))


def _run_auto_confirm(db, rule, row_ids=None, done=None, **_):
    """`builtin:auto_confirm` — the enrichment sweep, now reached through the table (S-195).

    🔴 THE WORK IS UNCHANGED; WHAT MOVED IS HOW IT IS FOUND. It ran from
    `_auto_confirm_followed_rows`, called directly on the drain beside this dispatcher — so a
    `follow_up` kind had TWO ways to run and the prohibition on that was carrying a named
    temporary. This closes it: one table, one route.

    🔴 AND THE RULE COMES FROM THE DECLARATION, NOT FROM A SECOND LOOKUP.
    `AutoConfirmCollector` already accepted `rules`; left to itself it called
    `load_enrichment_rules` and re-found what the synthesised rule is already carrying in
    `params`. Two readers of one fact is how they come to disagree — and here the second one
    also re-read a file on a paced path.

    ⚠️ `.active` STILL DECIDES. The global switch, the per-rule knob and 「does any reference
    view declare `candidate_for`」 are the collector's gates and stay there; this seat only
    hands it the rule it was already going to use.

    ⚠️ CONTAINED. A failure here must not cost the ledger follow-up that already succeeded.
    """
    import enrichment.candidates

    table = (done or {}).get("table")
    rows = list(row_ids or ())
    if not table or not rows:
        return {"confirmed": 0, "refused": 0}

    declared = (rule or {}).get("params") or None
    collector = enrichment.candidates.AutoConfirmCollector(
        table, rules=[declared] if isinstance(declared, dict) else None)
    if not collector.active:
        return {"confirmed": 0, "refused": 0}

    collector.collect_rows(db, rows)
    stats = collector.flush(db) or {}
    confirmed = stats.get("confirmed") or 0
    refused = sum((stats.get("refused") or {}).values())
    if done is not None:
        # Values, not a verdict: 「큰 깊이는 값으로 보임」 — a follow-up that confirms nothing
        # and one that never ran are different facts, and the note carries both. The drain
        # loop reads these two keys, so they keep their names.
        done["auto_confirmed"] = confirmed
        done["auto_refused"] = refused
    # 🔴 [S-246] `written` IS WHAT A `builtin:` KIND CALLS ITS ROW COUNT.
    # `join_into.run` and `materialize_rows` already answer under that name, and this one
    # did not - so the follow-up line S-249 added printed `written=None` for auto-confirm,
    # and the registration below would have had nothing to read. `confirmed` and `refused`
    # keep their names for the readers that have them; this adds the count, it does not
    # rename the fact.
    return {"written": confirmed, "confirmed": confirmed, "refused": refused,
            "source_name": enrichment.candidates.SOURCE_NAME}


def ensure_declared_unique_keys(db, rules) -> dict:
    """[S-240] Make the unique key a unified join DECLARED, at load time. Returns a report.

    🔴 THE CELL WAS WRITTEN AND READ BY NOBODY. `key.unique: true` never survived the
    translation (`rule_shape` dropped it), and the only place that builds a `uq_vjoin_*` is
    the RETIRED read-time loader - so the plan's 「선언이 key.unique 라고 말하면 제품이
    성립시킨다」 and RUN.md's 「제품이 인덱스를 세웁니다」 were both false for a unified join.

    ⚠️ THIS SEAT CALLS IT, NOT `join_into`. That module must not import the join ENGINE -
    a boundary its own test asserts - so it hands back the right table, its columns and the
    folds, and this seat, which already knows both halves, does the building.

    ⛔ LOAD TIME, NEVER THE READ PATH (§0-ter ①), and `enabled: false` means ZERO calls
    (판정 399 ③′): a switch that still probes is the defect that took the read path down
    on 2026-09-14.
    """
    from chain import join_key_index as vjc
    from chain import unique_key

    report = {"ensured": [], "skipped": []}
    seen = set()
    for name, table, columns, folds, skip in declared_unique_targets(rules):
        if skip:
            report["skipped"].append((name, skip))
            continue
        # ⚠️ ONE DECLARATION STANDS TWO RULES AND NEEDS ONE INDEX. The target half and
        # its `:reference` companion join the same two tables on the same key, so they ask
        # for the SAME index name - asking twice would probe `pg_index` twice at every
        # reload and report one index as two.
        index_name = vjc.required_index_name(table, columns, folds)
        if index_name in seen:
            continue
        seen.add(index_name)
        report["ensured"].append(
            (name, unique_key.ensure_once(db, name, table, columns, folds)))
    return report


def declared_unique_targets(rules):
    """(name, right table, columns, folds, skip reason) per unified join that DECLARED one.

    🔴 ONE WALKER, BECAUSE THEY ARE ONE QUESTION. 「which index do we build」 and
    「which index do we require」 must never be able to disagree - the day they do, the
    product builds an index at warmup and retracts it on the next read, forever.
    """
    from chain import join_into

    for rule in rules or ():
        if not isinstance(rule, dict):
            continue
        if rule.get("mapper") != join_into.JOIN_INTO_MAPPER:
            continue
        name = rule.get("name")
        if not rule.get("enabled", True):
            yield (name, None, None, None, "enabled=false")
            continue
        if not (rule.get("key") or {}).get("unique"):
            # ⚠️ ABSENT IS NOT 「no」 TO A QUESTION NOBODY ASKED. A declaration that says
            # nothing about uniqueness gets no index and no complaint; `join_into`'s own
            # row-level net still refuses a left row with two right answers.
            continue
        table, columns, folds = join_into.right_key(rule)
        if not table or not columns:
            yield (name, None, None, None, "no right key to cover")
            continue
        # ⚠️ `key.columns` IS A CHECK, NOT A CHOICE. The index has to be built over the
        # join's OWN right key or PostgreSQL will not use it (S-181) - so a list that names
        # other columns cannot be honoured, and honouring it silently would build an index
        # that covers nothing this join compares. It is read so that a typo is a sentence
        # rather than a cell nobody looks at, which is the whole defect of this round.
        declared = [str(column) for column in
                    ((rule.get("key") or {}).get("columns") or ()) if column]
        if declared and declared != list(columns):
            yield (name, table, columns, folds,
                   "key.columns %s is not this join's right key %s — the index covers "
                   "the right key" % (declared, list(columns)))
            continue
        yield (name, table, columns, folds, None)


def declared_unique_index_names(known_tables: dict = None) -> set:
    """Every `uq_vjoin_*` name the LIVE unified declarations require (S-240 · S-248).

    🔴 AN INDEX LIVES EXACTLY AS LONG AS THE JOIN THAT REQUIRES IT - and after S-240
    there are TWO kinds of join that require one. The retraction that enforces that lifetime
    computes 「required」 from the read-time declarations alone, so without this the index
    THIS module builds at warmup is dropped by the next read-path load, rebuilt at the next
    restart, and dropped again: a switch flapping on its own.

    ⚠️ THE DECLARATION IS EXPANDED BY THE SAME JUDGE THE LOADER USES (S-244). A second
    reading of the file would be a second answer to 「what does this declaration stand」,
    and this one has to agree with the seat that built the index.
    """
    from chain import ingestion_worker, rule_shape
    from database import crud
    from chain import join_key_index as vjc

    catalogue = known_tables if known_tables is not None else crud.TABLE_CONFIG
    names = set()
    for raw in ingestion_worker.read_rules_document()["rules"] or ():
        stood, refusal, _notes = rule_shape.expand_declaration(raw, catalogue)
        if refusal:
            # ⚠️ The loader already says this out loud; saying it again here would put a
            # refusal on the read path every few seconds - the flood 2026-09-14 was.
            continue
        for _name, table, columns, folds, skip in declared_unique_targets(stood):
            if skip:
                continue
            names.add(vjc.required_index_name(table, columns, folds))
    return names


#: kind -> callable. One table, the registry's posture: a name, a callable, nothing implicit.
BUILTIN_KINDS = {}

#: The kinds whose writer stamps `cell_sources.origin_row_id` — 「이 칸은 어느 행에서 왔나」
#: (판정 434). A kind that is NOT in here writes cells nothing can aim a retraction at, and
#: 판정 434 ④ says that must be answered BY NAME rather than by a quiet nothing.
#:
#: 🔴 REGISTERED BY THE SAME CALL AS THE IMPLEMENTATION, deliberately. A second table filled
#: from a second place is how 「이 종류가 무엇을 하나」 comes to have two answers; `_install`
#: below states both facts about a kind on one line, so they cannot drift apart.
ORIGIN_STAMPING_KINDS = set()

#: 🔴 [판정 497] KINDS THAT WRITE FOR THEMSELVES, SAID AT REGISTRATION.
#: The seat needs two facts before it runs anything: how to hand a rule its input, and
#: whether the result can be SEEN without being applied. Both used to be inferred from
#: 「is it a builtin」, which is a fact about where the code lives rather than about what it
#: does - and that inference is what let a dry run and a live lap grow separate branches.
#: A kind that PROPOSES its rows would go in as `writes_itself=False` and every seat would
#: follow without being edited.
SELF_WRITING_KINDS = set()

#: 🔴 [판정 498 ④] WHAT A KIND IS CALLED ON A SCREEN, SAID AT REGISTRATION.
#: `rule_shape` labelled rules join/decide/mapper by comparing against imported constants,
#: which is a hand-kept list wearing an import: register a fourth kind and it is silently
#: labelled 「mapper」 with nothing red. The label belongs to whoever adds the kind.
BUILTIN_LABELS = {}


def register_builtin(kind: str, fn, stamps_origin: bool = False,
                     writes_itself: bool = True, label: str = "mapper"):
    existing = BUILTIN_KINDS.get(kind)
    if existing is not None and existing is not fn:
        raise UnknownBuiltinKind(
            "two implementations claim %r; a rule naming it could not say which it meant"
            % kind)
    BUILTIN_KINDS[kind] = fn
    if stamps_origin:
        ORIGIN_STAMPING_KINDS.add(kind)
    if writes_itself:
        SELF_WRITING_KINDS.add(kind)
    BUILTIN_LABELS[kind] = label
    return fn


# 🪦 [판정 497] `run_builtin` AND `_rows_handed` LIVED HERE AND THE SEAT HAS THEM NOW.
# This function looked a name up in `BUILTIN_KINDS` and opened an `activity.running` entry -
# and `mapper_call.execute_custom_mapper` did the same two things for the other door. Two
# resolvers and two registrations for one question is what 소유자 called 「문 가르기」, and
# S-246 had made the second registration rather than removing the first.
#
# ⚠️ WHAT THE DELETED REFUSAL ACTUALLY COVERED, said accurately rather than carried over.
# `run_builtin` raised `UnknownBuiltinKind` when a kind was missing from the table, and that
# arm was ALREADY unreachable from the seat: `rule_run.builtin_kind` answers by membership in
# this same table, so a kind that reaches the call is a kind that is in it. The class stays
# live at its other raiser above - two implementations claiming one id.
#
# 🔴 WHERE THAT REFUSAL WENT, AND WHAT IS STILL MISSING FROM IT. A rule naming
# `builtin:<something not registered>` falls through to the seat's mapper arm, which refuses it
# by name AND lists the registered kinds - so the operator sentence survived the move. What did
# NOT survive is the seat knowing the operator MEANT a builtin: the refusal reads as 「names no
# implementation」 rather than 「that is not one of the kinds」. Telling those apart needs a
# spelling of the `builtin:` prefix, and there is no constant for one - only the two literals in
# `join_into` and `legacy_join_declaration` - so writing a third here would be the third author
# of that spelling. Reported, not built.


def _install():
    import enrichment.config
    from chain import legacy_join_declaration
    from chain import join_into

    # `stamps_origin`: `materialize_rows` carries the right row that answered into
    # `GeneralUpdateItem.origin_row_id` (S-280), so what it wrote can be withdrawn when
    # that row is deleted.
    register_builtin(legacy_join_declaration.JOIN_MAPPER, _run_join, stamps_origin=True,
                     writes_itself=True, label="join")
    # 🔴 [S-237 · 판정 461 ③] TWO ENTRIES, AND BOTH OF THEM WRITE. THAT IS THE DEBT.
    # ⚰️ This paragraph used to read 「`builtin:join` is the READ-TIME join and production
    # runs on it」. Both halves were false: ruling 461 deleted the read-time executor, and
    # production writes into the table. `_run_join` above reaches
    # `legacy_materialized_join.on_*_rows_changed`, which writes exactly as `join_into.run`
    # does. So the axis these two entries split on is NOT read-vs-write - it is WHICH
    # DECLARATION FILE BIRTHED THE RULE:
    #     builtin:join       virtual_join_rules.json with `materialize: true`. Alive only
    #                        while such a declaration is; `materialize: false` declared a
    #                        read-time join and is now refused by name.
    #     builtin:join_into  chain_rules.json, `derive: {kind: "join"}` with `into.table`.
    # 🔴 Two write doors for one job is a debt, not a design, and it is written down here
    # because this registry is where the two are visible at once. They are kept from
    # disagreeing about the KEY by both folding it through `notation_norm.key_expression_sql`
    # rather than by either trusting the other. The debt closes when the last
    # `materialize: true` declaration moves to `into.table`. `register_builtin` refuses two
    # claimants of one id by name, so the separation is enforced here rather than trusted.
    register_builtin(join_into.JOIN_INTO_MAPPER, join_into.run, stamps_origin=True,
                     writes_itself=True, label="join")
    # S-195: the kind S-179 declared finally has an implementation, so the table carries the
    # whole `builtin:` vocabulary and the named temporary two-path condition is over.
    # ⛔ NOT `stamps_origin`. The sweep's answer comes from a candidate PROBE over a
    # reference view, not from one reference row, so there is no single row to write down —
    # and 판정 434 forbids answering that with a NULL that already means 「기존 행」. The
    # seat names this kind instead (`rule_run.retraction_refusal`).
    register_builtin(enrichment.config.AUTO_CONFIRM_MAPPER, _run_auto_confirm,
                     writes_itself=True, label="decide")


_install()
