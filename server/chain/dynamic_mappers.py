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
value is `declared:join` now, and this module's templates register under `declared:*`: the
prefix says 「a mapper the product built FROM THE DECLARATION」, and what follows is the word
the declaration itself uses (`DECLARED_KINDS` in `rule_shape`). `builtin:` named the KIND
TABLE, which no longer exists - a name that points at a retired mechanism tells an operator
that mechanism is there. ⚰️ 652 3걸음: `declared:virtual_join` went the same way, and for
the same reason - the family that name spoke for has no declaration file any more.

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
    """`derive: {kind: "join"}` as an ordinary mapper. The body is `join_into.propose`.

    ⚰️ [판정 567 · 총괄 2026-09-23] THIS CALLED `join_into.run`, which proposed AND wrote.
       The write is the seat's now. `join_into` carries the tombstone that says what comes
       back if only half of this is put back - it is a measured log line, not a worry.
    """
    from chain import join_into

    return join_into.propose(db, rule, _row_ids(payload))



def _auto_confirm(db, payload, rule=None):
    """`derive: {kind: "decide"}` as an ordinary mapper.

    🔴 THE BODY MOVED HERE FROM THE KIND TABLE (판정 563: 「auto_confirm 의 «확정하는 로직»
    -> 동적 맵퍼의 «몸»이 됩니다」). The collector's own gates still decide: the global
    switch, the per-rule knob, and whether any reference view declares a candidate.

    ⚠️ IT PROPOSES. `confirm_keys` builds the items - stamp, partial-key rank and all - and
    this hands them back in `updates` for the seat to write inside the chain envelope. It
    applied its own rows until 2026-09-23; `confirm_keys` carries why the sweep still does.

    ⚰️ WHAT IS NOT CARRIED: the `done["auto_confirmed"]` note. That existed because this kind
    was only ever reached from the deferred pass, which passed a dict for it to write into -
    and that pass is gone. The counts travel back as the RETURN VALUE.
    """
    from chain import enrichment

    rows = _row_ids(payload)
    # 🔴 [판정 525 ②] EVERY ZERO EXIT SAYS WHY — and these are different repairs: nothing
    #   arrived / nothing is switched on / nothing was waiting. Two of the three are not
    #   even a problem, and 「0」 alone cannot tell them apart.
    table = str((rule or {}).get("target_table") or "")
    if not table or not rows:
        return {"updates": [], "confirmed": 0, "refused": 0,
                "refusal": "확정을 시도할 행이 넘어오지 않았습니다"}

    declared = (rule or {}).get("params") or None
    collector = enrichment.candidates.AutoConfirmCollector(
        table, rules=[declared] if isinstance(declared, dict) else None)
    if not collector.active:
        return {"updates": [], "confirmed": 0, "refused": 0,
                "refusal": "이 표에 켜진 자동확정 규칙이 없습니다"}

    collector.collect_rows(db, rows)
    # ⚠️ NOT `written`. The seat adds that cell to its own count, so reporting it here while
    #   the seat ALSO writes these items would count every confirmed row twice.
    proposed = []
    stats = collector.flush(db, propose_into=proposed) or {}
    confirmed = stats.get("confirmed") or 0
    refused = sum((stats.get("refused") or {}).values())
    refusal = None
    if not confirmed:
        refusal = ("%d 행이 확정 조건에 맞지 않았습니다" % refused if refused else
                   "확정을 기다리는 행이 없습니다")
    return {"updates": proposed, "confirmed": confirmed, "refused": refused,
            "refusal": refusal, "source_name": enrichment.candidates.SOURCE_NAME}



# ⚰️ [판정 652 3걸음] `_legacy_materialized_join` STOOD HERE, and with it the registry name
#    `declared:virtual_join`. It wrapped `virtual_join_rules.json`'s `materialize: true`
#    half, and 판정 581 kept it separate from `_join` for a REAL reason: a virtual join
#    split an `expose` column that also existed on the left into `collide` and wrote it
#    absent-only, so the operator's own edit won. 🔴 THAT FACT DID NOT DIE WITH THE CODE —
#    it is the behaviour difference an operator migrating a declaration meets, and
#    `join_into` writes the right side unconditionally. It is stated here because the
#    grammar that carried it is gone and nobody can read it off the source any more.


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
    from chain.enrichment import mapper

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
    from chain import enrichment
    from chain import join_into

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
        "label": "join", "stamps_origin": True,
        # ⚰️ `join_into.JOIN_CELLS` WAS PUT HERE AND TAKEN BACK OUT. Declaring the list
        #    makes the loader REFUSE a cell outside it - and 판정 397 settled the
        #    opposite: an unknown join cell is NAMED and the rule still runs,
        #    because a cell this product does not know may be a live argument it
        #    has not learned. `join_into.unknown_cells` is where that naming
        #    lives; declaring params here quietly converted it into a refusal.
        "params": None}
    TEMPLATE_FACTS[enrichment.config.AUTO_CONFIRM_MAPPER] = {
        "label": "decide", "stamps_origin": False,
        "params": None}
    TEMPLATES[enrichment.config.DEDUP_MAPPER] = _enrich
    # ⚠️ `stamps_origin` False is measured (`origin_row_id` × 0 in `enrichment/mapper.py`),
    #    not assumed.

    # ⚠️ THE LABEL IS THE DECLARATION'S WORD, NOT THE HALF'S. One `decide` declaration makes
    #    two chain rules; an operator listing the rules for one table should see what they
    #    DECLARED, not which half they happened to get. The registry NAME is what tells the
    #    two halves apart.
    TEMPLATE_FACTS[enrichment.config.DEDUP_MAPPER] = {
        "label": "decide", "stamps_origin": False,
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
#   this replaces was a module constant filled by `synthesis._install()` at IMPORT, so it
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
