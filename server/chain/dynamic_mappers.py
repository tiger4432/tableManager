# -*- coding: utf-8 -*-
"""판정 562 · 563 · 567 — 선언이 이름을 대면 «맵퍼를 만들어» 꽂습니다. 코드 파일은 «안 씁니다».

> 소유자 2026-09-17: 「선언에서 조인 맵퍼, 오토컨펌 맵퍼, 파생행 맵퍼 «기본틀» 만들고
>  **동적으로 생성**해 **코드 저장하지 말고 프로세스상에만**」
> 「그냥 맵퍼 만들어서 꽂으면 **알아서 같은 문** 되잖아」

🔴 WHAT THIS DELETES, BY EXISTING. The chain had a KIND TABLE: a rule named a `builtin:`
kind, a registry said how that kind is CALLED (`hands`), whether it WRITES FOR ITSELF
(`writes_itself`), and what to LABEL it. Every one of those facts existed because the kinds
were a second door. There is one door now - the mapper registry - so the kind table has
nothing left to answer.

⚰️ THE NAME DID MOVE, ON THE DAY AFTER THIS WAS WRITTEN (판정 600). This paragraph said 「THE
NAME DOES NOT MOVE」 and gave the reason: a stored rule already says `mapper: "builtin:join_into"`,
so registering under that name meant no declaration changed and no operator migrated anything.
The lead then asked the owner whether any production declaration writes the `mapper` cell by
hand, and the answer was 「없다」 — the migration cost the argument rested on is ZERO. So the
value is `declared:join` now, and this module's three templates register under `declared:*`:
the prefix says 「a mapper the product built FROM THE DECLARATION」, and what follows is the
word the declaration itself uses (`DECLARED_KINDS` in `rule_shape`, and `virtual_join` for the
family `legacy_join_declaration` loads). `builtin:` named the KIND TABLE, which no longer
exists - a name that points at a retired mechanism tells an operator that mechanism is there.

⛔ NOT A FILE. `server/mappers/` is the owner's (gitignored, 판정 498), and writing product
code there is forbidden; writing a generated file anywhere else would make a build artifact
that can go stale against the declaration it came from. These live only in this process.

⚠️ ONE TEMPLATE PER KIND, NOT ONE FUNCTION PER RULE. The rule travels to the mapper at call
time (`rule=`), which is what makes a template enough - and a function per rule would need a
name per rule, which is a second naming scheme for something the declaration already names.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("Chain.DynamicMappers")


def _row_ids(payload) -> list:
    """The rows this call is about.

    🔴 THE PAYLOADS ALREADY CARRY `row_id` — measured, not assumed:
    `ingestion_worker` builds the caller's `row_ids` from exactly this
    (`[p.get("row_id") for p in payloads if p.get("row_id")]`). So a mapper handed the group
    can find the same rows without the seat passing a second list, which is what let the
    `row_ids` hand disappear.

    ⚠️ A BATCH RULE GETS A LIST, A PER-ROW RULE GETS ONE ROW. Both shapes are handled here
    rather than by asking which kind the rule is - asking would be the kind table again.
    """
    rows = payload if isinstance(payload, list) else [payload]
    return [row.get("row_id") for row in rows
            if isinstance(row, dict) and row.get("row_id")]


def _join(db, payload, rule=None):
    """`derive: {kind: "join"}` as an ordinary mapper. The body is `join_into.run`.

    🔴 [판정 567 「새 것이 먼저 서고, 서고 나서 예것이 나간다」] THE TEMPLATE DOES WHAT THE
    REGISTRATION IT REPLACES DID. That registration was
    `register_builtin(JOIN_INTO_MAPPER, join_into.run, ..., writes_itself=True)`, and my
    first version of this template called `propose` instead - the same computation with the
    WRITE taken out.

    ⚰️ MEASURED, 2026-09-17: that silently unwired the two doors that have no batch writer.
    `test_every_caller_and_door_leaves_the_same_envelope` was 17/17 at the round's base and
    red at HEAD; the log line says it all - `rows_in=4 rows_out=4 written=None`, four rows
    PROPOSED and four rows dropped, on the paced lap and on retroactive. The group step and
    replay's proposing branch were fine, which is why the join gates stayed green: a caller
    that applies proposals cannot tell the two bodies apart, and a caller that does not sees
    nothing at all.

    🔴 SO THE CONTRACT CHANGE IS NOT THIS ROUND'S. Making a join propose and every door
    apply is the SAME work as giving the deferred step the group step's batch write
    (판정 585's ③), and it lands there, whole. Splitting it - new body now, missing
    appliers later - is what 「나눠 착지시키면 그 사이가 거짓이다」 names.
    `join_into.propose` and `_apply` stay split, because that split is what the appliers
    will call.
    """
    from chain import join_into

    return join_into.run(db, rule, _row_ids(payload))


def _auto_confirm(db, payload, rule=None):
    """`derive: {kind: "decide"}` as an ordinary mapper.

    🔴 THE BODY MOVED HERE FROM THE KIND TABLE (판정 563: 「auto_confirm 의 «확정하는 로직»
    -> 동적 맵퍼의 «몸»이 됩니다」). What it does is unchanged: the collector's own gates
    decide (the global switch, the per-rule knob, and whether any reference view declares a
    candidate), and `confirm_keys` does the probing and the writing with its own caps.

    ⚠️ IT WRITES FOR ITSELF, AND SAYS SO. `written` is how a rule reports rows it applied
    rather than proposed; the seat reads that cell now, so nothing has to be REGISTERED in
    advance as self-writing (that was `writes_itself`, a fact about an address).

    ⚰️ WHAT IS NOT CARRIED: the `done["auto_confirmed"]` note. That existed because this kind
    was only ever reached from the deferred pass, which passed a dict for it to write into -
    and that pass is going. The counts travel back as the RETURN VALUE, which is where the
    caller reads everything else about a run.
    """
    import enrichment.candidates

    rows = _row_ids(payload)
    # 🔴 [판정 525 ②] EVERY ZERO EXIT SAYS WHY — and these are different repairs: nothing
    #   arrived / nothing is switched on / nothing was waiting. Two of the three are not
    #   even a problem, and 「0」 alone cannot tell them apart.
    table = str((rule or {}).get("target_table") or "")
    if not table or not rows:
        return {"written": 0, "confirmed": 0, "refused": 0,
                "refusal": "확정을 시도할 행이 넘어오지 않았습니다"}

    declared = (rule or {}).get("params") or None
    collector = enrichment.candidates.AutoConfirmCollector(
        table, rules=[declared] if isinstance(declared, dict) else None)
    if not collector.active:
        return {"written": 0, "confirmed": 0, "refused": 0,
                "refusal": "이 표에 켜진 자동확정 규칙이 없습니다"}

    collector.collect_rows(db, rows)
    stats = collector.flush(db) or {}
    confirmed = stats.get("confirmed") or 0
    refused = sum((stats.get("refused") or {}).values())
    refusal = None
    if not confirmed:
        refusal = ("%d 행이 확정 조건에 맞지 않았습니다" % refused if refused else
                   "확정을 기다리는 행이 없습니다")
    return {"written": confirmed, "confirmed": confirmed, "refused": refused,
            "refusal": refusal, "source_name": enrichment.candidates.SOURCE_NAME}


def _legacy_materialized_join(db, payload, rule=None):
    """`virtual_join_rules.json` 의 `materialize: true` — «지금 도는 구현을 그대로» 감쌉니다.

    🔴 [판정 581] AND IT IS NOT THE SAME JOB AS `_join`, WHICH IS WHY IT KEEPS ITS OWN
    implementation. Measured: a virtual join splits an `expose` column that ALSO exists on
    the left into `collide` and treats it absent-only - the operator's own edit wins.
    `join_into` has no such notion and writes the right side unconditionally. Folding the
    two would overwrite a hand-edited value silently, on every trigger.

    ⚠️ THREE IMPLEMENTATIONS IS NOT THREE DOORS. The door is `resolve`, and it is one; what
    the registry holds is what each name DOES. The debt the old table's note recorded is a
    debt of DECLARATION SURFACES (`virtual_join_rules.json` against `chain_rules.json`) and
    it closes when the last `materialize: true` moves to `into.table` - not here.

    ⚰️ THE REFERENCE ARM IS NOT CARRIED, and that is not a decision: `_run_join` also took
    `key_values` for 「a reference row moved」, and MEASURED - no chain caller ever passed it
    (`key_values` outside this module belongs to the alignment view). It was unreachable
    before this round and carrying it would be carrying a path nothing walks.

    ⛔ THE MODULE IT CALLS IS NOT DELETED (판정 580 · 581): its reading half is the write
    path's uniqueness guard, and a guard that cannot read its declaration refuses no row.
    """
    from chain import legacy_materialized_join as engine

    return engine.on_target_rows_changed(db, (rule or {}).get("params") or {},
                                         _row_ids(payload))


def _enrich(db, payload, rule=None):
    """`enrichment_rules.json` 의 «파생행» 반쪽 — the body is `map_enrichment_dedup`.

    🔴 [소유자 2026-09-17 「@mapper 를 굳이 할 필요는 없고 체인 프로세스에서 «똑같은 인자»로
    들어가서 돌면 됨」] THE ARGUMENTS WERE ALREADY THE SAME, AND THE CELL WAS NOT. This
    mapper's signature has been `(db, payloads, rule=None)` all along, so it entered the seat
    the way every mapper does; what it read once inside was `rule["enrichment"]`, a key no
    other template has. `enrichment.config` wrote that key AND `params` from the same dict,
    so this is one fact with two spellings - and the other two templates read `params`.

    🔴 [판정 581 · 600] THE TEMPLATE DOES WHAT THE REGISTRATION IT REPLACES DID, and here
    that registration was an IMPORT PATH (`mapper_module`/`mapper_function`), `resolve`'s
    third arm. Measured before the swap, all four of its answers:
        call          enrichment.mapper.map_enrichment_dedup   (unchanged - same body)
        accepts_rule  True                                     (unchanged - same signature)
        is_batch      True                                     (the DECLARATION's cell, untouched)
        writes_itself False -> the mapper returns `updates` and the seat writes them
    ⚠️ AND TWO ANSWERS DO CHANGE, deliberately, because they were answered by ADDRESS before:
        label          None -> 「decide」. `rule_shape` used to fall through to a NAME-PREFIX
                       branch (`name.startswith(DEDUP_PREFIX)`) to reach the same word. That
                       branch was this half's label declaration written somewhere else, which
                       is 「문 가르기」 with the label instead of the call.
        retraction     the hedge 「파일 맵퍼가 도장을 찍는지 제품이 모릅니다」 becomes the
                       definite 「이 종류는 안 찍습니다」. TRUE and countable: `origin_row_id`
                       appears 0 times in `enrichment/mapper.py`, which - unlike
                       `server/mappers/` - is this repository's own file.
    """
    from enrichment import mapper

    return mapper.map_enrichment_dedup(db, payload, rule)


#: 🔴 [판정 562] THE FACTS THAT ARE REAL, DECLARED WHERE THE TEMPLATE IS.
#:
#: The kind table held four facts about each kind. Two were about its ADDRESS and go away
#: with it - `hands` (「is it called with row ids or payloads」: there is one calling
#: convention now) and `writes_itself` (「will the caller have to write this」: a mapper
#: reports what it wrote, so nobody is asked in advance).
#:
#: ⚠️ THE OTHER TWO ARE ABOUT THE WORK, so they move rather than disappear - and saying that
#: plainly matters: a repair that moves a proxy down a level and calls it removed is how the
#: same defect comes back under a new name.
#:   label          what an operator's list calls this rule (`rule_census`, the form)
#:   stamps_origin  whether what it writes can be WITHDRAWN when its input row is deleted
#:                  (판정 434 ④: a retraction aims with `cell_sources.origin_row_id`)
TEMPLATE_FACTS = {}


def label_for(name):
    """What a rule naming this mapper is called in a list, or None when nothing built it."""
    return (TEMPLATE_FACTS.get(name) or {}).get("label")


def writes_itself(name) -> bool:
    """Does this mapper apply its own rows, instead of proposing them?

    ⚠️ THIS IS THE ONE FACT THAT IS STILL ASKED IN ADVANCE, and only by the deferred
    pass, which selects the rules it hands a batch to. Every other reader takes it off the
    RESULT (`written`), which is where it belongs - and this function goes with that pass.
    """
    return bool((TEMPLATE_FACTS.get(name) or {}).get("writes_itself"))


def stamps_origin(name) -> bool:
    """Does what this mapper writes carry the row it came from? Unknown names: False.

    ⚠️ False MEANS 「this product cannot say it does」, which for a mapper written by the
    owner is the honest answer - `GeneralUpdateItem.origin_row_id` is on the schema every
    mapper builds, so a file mapper CAN stamp, and whether the live ones do is not countable
    from here (`server/mappers/` is gitignored).
    """
    return bool((TEMPLATE_FACTS.get(name) or {}).get("stamps_origin"))


#: kind name -> the function built for it. The key is the `mapper` cell a translated rule
#: carries, so the declaration needs no new word.
TEMPLATES = {}


def _install_templates():
    """Bind the templates to the names stored rules already use."""
    import enrichment.config
    from chain import join_into, legacy_join_declaration

    TEMPLATES[join_into.JOIN_INTO_MAPPER] = _join
    TEMPLATES[enrichment.config.AUTO_CONFIRM_MAPPER] = _auto_confirm
    # ⚠️ THE JOIN STAMPS AND AUTO-CONFIRM DOES NOT — unchanged facts, moved here from
    #    the kind table. `join_into._update_items` fills `origin_row_id`;
    #    `confirm_keys` does not, so its cells cannot be withdrawn (판정 434 ④).
    # 🔴 [판정 562] `params` IS THE ARGUMENT LIST THE LOADER CHECKS A DECLARATION
    #   AGAINST, and it is NOT optional: registering a template without one told the
    #   loader 「this mapper declares no arguments」, so every real join was refused as
    #   `undeclared_param` on `on`, `right_table` and `take`. Measured - the whole
    #   declaration was dropped at load, which is why the rule list came back empty.
    # ⚠️ THE LIST IS NOT WRITTEN HERE. `join_into.JOIN_CELLS` already owns it and the
    #   refusal it feeds is the same one that names an unknown join cell.
    # ⚠️ None MEANS 「this product does not constrain the arguments」, which is a
    #   different statement from 「it takes none」 - auto-confirm is handed an enrichment
    #   rule whose cells that file owns. An empty tuple would refuse all of them.
    TEMPLATE_FACTS[join_into.JOIN_INTO_MAPPER] = {
        # ⚠️ `writes_itself` IS WHAT THE OLD REGISTRATION DECLARED, and it has to stay
        #   True while the body applies its own proposals - the two are one fact said
        #   twice, and the doors with no batch writer read THIS one to decide.
        "label": "join", "stamps_origin": True, "writes_itself": True,
        # ⚰️ `join_into.JOIN_CELLS` WAS PUT HERE AND TAKEN BACK OUT. Declaring the list
        #    makes the loader REFUSE a cell outside it - and 판정 397 settled the
        #    opposite: an unknown join cell is NAMED and the rule still runs,
        #    because a cell this product does not know may be a live argument it
        #    has not learned. `join_into.unknown_cells` is where that naming
        #    lives; declaring params here quietly converted it into a refusal.
        "params": None}
    TEMPLATE_FACTS[enrichment.config.AUTO_CONFIRM_MAPPER] = {
        "label": "decide", "stamps_origin": False, "writes_itself": True,
        "params": None}
    # ⚠️ ITS FACTS ARE THE ONES THE OLD REGISTRATION DECLARED, carried unchanged:
    #    `materialize_rows` puts the answering row in `origin_row_id`, and it writes
    #    for itself rather than proposing.
    TEMPLATES[enrichment.config.DEDUP_MAPPER] = _enrich
    # ⚠️ `writes_itself` IS False HERE AND THAT IS THE UNCHANGED FACT, not an omission: this
    #    mapper RETURNS `updates` for the seat to write, which is why it is the one template
    #    whose answer the caller cannot skip applying. ⚠️ `stamps_origin` False is measured
    #    (`origin_row_id` × 0 in `enrichment/mapper.py`), not assumed.
    # ⚠️ THE LABEL IS THE DECLARATION'S WORD, NOT THE HALF'S. One `decide` declaration makes
    #    two chain rules; an operator listing the rules for one table should see what they
    #    DECLARED, not which half they happened to get. The registry NAME is what tells the
    #    two halves apart.
    TEMPLATE_FACTS[enrichment.config.DEDUP_MAPPER] = {
        "label": "decide", "stamps_origin": False, "writes_itself": False,
        "params": None}
    TEMPLATES[legacy_join_declaration.JOIN_MAPPER] = _legacy_materialized_join
    TEMPLATE_FACTS[legacy_join_declaration.JOIN_MAPPER] = {
        "label": "join", "stamps_origin": True, "writes_itself": True,
        "params": None}


def install() -> tuple:
    """Build the mappers and put them in the registry. Returns the names installed.

    🔴 CALLED FROM `discover()` AND ONLY FROM THERE. `discover()` CLEARS the registry before
    re-importing the owner's files, and it has three live callers (the worker's warmup, the
    API's startup, and system reload). Installing anywhere else means a reload silently
    empties these: the rules stay, their mapper is gone, and every join is refused as
    「that name resolves to nothing」 - after a reload, which is the worst time to find out.
    """
    import mapper_sdk

    _install_templates()
    for name, fn in TEMPLATES.items():
        params = (TEMPLATE_FACTS.get(name) or {}).get("params")
        mapper_sdk.register(name, fn, params or ())
        if params is None:
            # ⚠️ ABSENT, NOT EMPTY. `chain_bindings` checks a declaration's arguments
            #    only when `MAPPER_PARAMS` HAS an entry; an empty tuple is a
            #    statement that none are legal. 판정 509 의 부류, one table over.
            mapper_sdk.MAPPER_PARAMS.pop(name, None)
    return tuple(sorted(TEMPLATES))

# 🔴 [판정 562] INSTALLED AT IMPORT TOO, AND THAT IS NOT BELT-AND-BRACES. The kind table
#   this replaces was a module constant filled by `builtins._install()` at IMPORT, so it
#   existed in any process that had imported the module - including one that never calls
#   `discover()`. Measured: with the install only in `discover`, a worker built without it
#   refused every join as 「'builtin:join_into' is not registered」. That is a robustness
#   REGRESSION dressed as a test failure, and production would meet it in any process that
#   loads rules before warming up.
# ⚠️ BOTH SEATS ARE NEEDED, not one: `discover()` CLEARS the registry, so an import-time
#   install alone is emptied by the first reload. This one covers 「never discovered」 and
#   the one in `discover` covers 「discovered again」.
# ⚠️ GUARDED, because an import that dies takes the importer with it and this module is
#   imported from the seat that runs every rule. A failure here must make JOINS refuse by
#   name, not make the chain unimportable.
try:
    install()
except Exception as _exc:                                          # noqa: BLE001
    logger.error("[DynamicMappers] 기본틀을 꽂지 못했습니다 — 조인·확정 규칙이 "
                 "「이름을 못 찾음」으로 거절됩니다: %s: %s",
                 type(_exc).__name__, _exc)
