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

🔴 THE NAME DOES NOT MOVE. A stored rule already says `mapper: "builtin:join_into"`, written
by `rule_shape.as_chain_rule` from `derive: {kind: "join"}`. Registering the built function
under THAT name means no declaration changes and no operator migrates anything: the same
rule resolves through the ordinary mapper path tomorrow.

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
    """`derive: {kind: "join"}` as an ordinary mapper: propose, never write.

    The body is `join_into.propose` — the same computation the retiring builtin runs, with
    the writing left to the caller's batch. That batch is what carries the chain envelope
    (판정 423), so the join's writes are dressed exactly like every other mapper's.
    """
    from chain import join_into

    return join_into.propose(db, rule, _row_ids(payload))


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


#: kind name -> the function built for it. The key is the `mapper` cell a translated rule
#: carries, so the declaration needs no new word.
TEMPLATES = {}


def _install_templates():
    """Bind the templates to the names stored rules already use."""
    import enrichment.config
    from chain import join_into

    TEMPLATES[join_into.JOIN_INTO_MAPPER] = _join
    TEMPLATES[enrichment.config.AUTO_CONFIRM_MAPPER] = _auto_confirm


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
        mapper_sdk.register(name, fn)
    return tuple(sorted(TEMPLATES))
