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
)
# ⚰️ [판정 652 3걸음] THE SECOND ROW WAS 「virtual join」. 그 문법이 은퇴하면서 그 반쪽이
#    짓던 규칙이 «0» 이 됐다 — 실조인은 `chain_rules.json` 에 선언되어 로더가 그대로
#    실으므로 합성될 것이 없다. 표가 둘이었던 이유는 「반쪽이 가끔 다른 낱말로 보고되는 것」을
#    막기 위해서였고, 반쪽이 하나면 그 위험이 없다. 모양은 남긴다 — 둘째가 생기면
#    그때 다시 그 자리로 들어오면 된다.


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
        from chain import enrichment
        return enrichment.config.load_enrichment_chain_rules(known_tables=known_tables)

    rules = []
    for (half, stops, says), produce in zip(_SYNTHESIS_HALVES, (_enrichment,)):
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
    from chain import enrichment

    # ⚰️ [판정 652 3걸음] 이 질문은 반쪽이 «둘»일 때 갈렸다 — `JOIN_MAPPER` 를 달면
    #    `virtual_join_rules.json`, 아니면 인리치 파일. 그 문법이 은퇴해 합성되는 것이
    #    한 반쪽뿐이라 답도 하나다. 자리는 남긴다 — 이름 중복 거절이 「어느 파일을
    #    열어라」를 말하려면 여전히 이 답이 필요하고, 반쪽이 둘로 다시 늘면 여기에 심는다.
    return os.path.basename(enrichment.config.ENRICHMENT_RULES_PATH)


# ---------------------------------------------------------------------------
# the `builtin:` table
# ---------------------------------------------------------------------------

# ⚰️ [판정 562 · 563 · 580] THE KIND TABLE AND ITS ENTRIES STOOD HERE.
#
#   `BUILTIN_KINDS` · `ORIGIN_STAMPING_KINDS` · `SELF_WRITING_KINDS` · `BUILTIN_LABELS` ·
#   `HANDS_ROW_IDS` · `HANDS_PAYLOADS` · `BUILTIN_HANDS` · `register_builtin` · `_install` ·
#   `_run_join` · `_run_auto_confirm` · `UnknownBuiltinKind`.
#
#   All of it existed because a rule could name a kind THIS REPOSITORY implemented, and
#   that was the second door. The names those rules carry are registered mappers now,
#   built in process from the declaration (`chain.dynamic_mappers`), so a rule reaches its
#   code the same way an operator's own mapper does.
#
# 🔴 WHERE EACH FACT WENT, because 「없애였다」 and 「옮겼다」 are different claims:
#     _run_auto_confirm   -> `dynamic_mappers._auto_confirm` (the body, unchanged)
#     BUILTIN_LABELS      -> `TEMPLATE_FACTS[...]['label']`
#     ORIGIN_STAMPING     -> `TEMPLATE_FACTS[...]['stamps_origin']`
#     SELF_WRITING_KINDS  -> `TEMPLATE_FACTS[...]['writes_itself']`, and out again
#                            2026-09-23: nothing writes for itself, so nobody is asked in
#                            advance and the seat totals what each mapper reports

#        ⚰️ THIS LINE SAID 「read only by the deferred pass, which goes with it」
#        AND THAT WAS A PREDICTION WEARING A MEASUREMENT'S CLOTHES. Counted
#        2026-09-17, there are TWO product readers and they ask in different tenses:
#          `ingestion_worker.picked_up_by_the_follow_up_pass` - asked BEFORE the run,
#             to select. This one does go when the deferred step can write proposals.
#          `replay` -> `admin.retroactive` - asked when the rule is NOT run at all, to
#             pick the pre-count's UNIT (「다시 계산할 행」 vs 「덮어쓸 셀」, 판정 505).
#             A dry run has no answer to read a count off, so 567's move to reading it
#             off the result does not reach this seat and this reader STAYS.
#        So the fact is the same class as `stamps_origin`: about the WORK, not the
#        address, and it belongs beside the template rather than being on its way out.
#     BUILTIN_HANDS/HANDS -> nowhere. One calling convention has nothing to record.
#     _run_join           -> nowhere. 판정 580: its execution half was already unreachable,
#                            and the READING half it named (`rules_for_right`) went with
#                            its grammar in 652 step three. The write path's uniqueness
#                            guard now reads `right_keys_for`, which walks the unified
#                            declarations - one producer, because there is one grammar.


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
    for name, table, columns, folds, skip, _kind in declared_unique_targets(rules):
        if skip:
            # ⚠️ [판정 683 ㄱ] 부류로 «거르지 않는다» — 웜업은 이 목록을 그대로 찍고, 머리를
            #    중립으로 둔 덕에 줄 전체가 참이다. 거르면 「안 물었다」가 다시 조용해진다.
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


#: The SIXTH cell of `declared_unique_targets`, so nobody has to read the fifth one's
#: SENTENCE to tell two different facts apart (판정 682·683·685).
#:
#: 🔴 683 QUEUED THIS AS TIDINESS AND 685 MADE IT NECESSARY. While the only consumer
#: was a warmup log line, a neutral word was enough. The approval panel has to place each
#: row in a CLOSED vocabulary, and the only other ways to tell 「asked nothing」 from
#: 「asked and cannot」 are proxies: 「is there a DDL」 (a refusal with no DDL then reads as
#: 「not asked」) or re-deriving `key.unique` outside this walker (a second author of the
#: one question this walker exists to answer once).
SKIP_NOT_ASKED = "not_asked"   #: 지금 승인을 «묻지 않는다» — key.unique 없음 · 꺼짐
SKIP_UNMET = "unmet"           #: 물었는데 «성립 못 한다» — 오른쪽 키 없음 · key.columns 불일치


def declared_unique_targets(rules):
    """(name, right table, columns, folds, skip reason, skip kind) per unified join.

    🔴 ONE WALKER, BECAUSE THEY ARE ONE QUESTION. 「which index do we build」 and
    「which index do we require」 must never be able to disagree - the day they do, the
    product builds an index at warmup and retracts it on the next read, forever.

    🔴 [판정 682·685] AND THE SKIP CELL CARRIED TWO MEANINGS. To the seat that BUILDS,
    「the declaration asked nothing」 is not a skip - there was nothing to skip; to the seat
    that REPORTS, it is the answer itself. The KIND rides beside the sentence and every
    consumer asks the KIND. ⛔ Never split on the sentence: that counts a place, not a
    property, and the spelling moves.
    """
    from chain import join_into

    for rule in rules or ():
        if not isinstance(rule, dict):
            continue
        if rule.get("mapper") != join_into.JOIN_INTO_MAPPER:
            continue
        name = rule.get("name")
        if not rule.get("enabled", True):
            # ⚠️ OFF IS NOT WRONG (판정 399). An operator who switched something off did
            #    not make a mistake, so this is 「asks nothing right now」 and NOT a refusal.
            yield (name, None, None, None, "enabled=false", SKIP_NOT_ASKED)
            continue
        if not (rule.get("key") or {}).get("unique"):
            # ⚠️ ABSENT IS NOT 「no」 TO A QUESTION NOBODY ASKED. A declaration that says
            # nothing about uniqueness gets no index and no complaint; `join_into`'s own
            # row-level net still refuses a left row with two right answers.
            #
            # 🔴 [판정 680] IT STILL HAS TO COME OUT SAYING SO. This cell used to `continue`,
            # and the cell above it yields a REASON for a disabled join - so on one axis one
            # non-answer spoke and the other was silent, and the silent one is
            # indistinguishable from 「the product never read my declaration」. Both seats that consume this
            # walker skip on a reason (`declared_unique_index_names`, `right_keys_for`), so
            # no index is built or required that was not before; what changes is that the
            # approval report can draw this declaration instead of dropping it.
            yield (name, None, None, None,
                   "key.unique 를 안 적었습니다 — 이 선언은 승인을 묻지 않습니다. "
                   "인덱스가 필요하면 `key: {unique: true}` 를 적으십시오.", SKIP_NOT_ASKED)
            continue
        table, columns, folds = join_into.right_key(rule)
        if not table or not columns:
            yield (name, None, None, None, "no right key to cover", SKIP_UNMET)
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
                   "the right key" % (declared, list(columns)), SKIP_UNMET)
            continue
        yield (name, table, columns, folds, None, None)


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
        for _name, table, columns, folds, skip, _kind in declared_unique_targets(stood):
            if skip:
                continue
            names.add(vjc.required_index_name(table, columns, folds))
    return names


def _approval_row(rule: dict, right_table, required_index, unique_index,
                  required_index_ddl, detail, state) -> dict:
    """선언 «하나»의 승인 행. 옛 라우트의 칸을 «전부» 들고, 상태 칸 하나가 더 있다.

    🔴 [판정 685] `approval_state` 가 «덧셈»인 이유. 옛 칸을 하나도 안 뺐으므로 오늘
    그리는 화면이 안 깨지고, 새 칸이 화면에게 「유도하지 말라」고 말한다 — 클라가
    「required_index_ddl 이 있나」로 「안 물음」과 «거절»을 가르고 있었고, 그건 대리다.
    """
    from chain import join_into

    rule = rule or {}
    on = join_into.pairs(rule)
    return {
        "name": rule.get("name"),
        "left_table": str(rule.get("target_table") or ""),
        "right_table": str(right_table
                           or join_into.join_spec(rule).get("right_table") or ""),
        "join_key": ["%s = %s" % (left, right) for left, right, _fold in on],
        # 접기는 «비교의 성질»이라 선언마다 다르고, 어느 쪽 컬럼이 선언됐는지와 상관없이
        # 양쪽에 걸린다. 그 사실을 말하지 않으면 운영자는 왜 이 조인만 «다른» 인덱스를
        # 요구하는지 알 방법이 없다.
        "folded_join_key": [
            {"left": left, "right": right,
             "rules": sorted(key for key, value in (fold or {}).items() if value)}
            for left, right, fold in on if fold],
        "expose": [source for source, _into in join_into.takes(rule)],
        # ⚠️ `accepted` 는 «남깁니다» — 옛 화면이 읽던 칸이고, 덧셈이라야 안 깨집니다.
        #    새 코드는 `approval_state` 를 읽습니다(그쪽이 셋을 가릅니다).
        "accepted": bool(unique_index) and detail is None,
        "approval_state": state,
        "unique_index": unique_index,
        "required_index": required_index,
        "required_index_ddl": None if unique_index else required_index_ddl,
        "detail": detail,
    }


def approval_report(db, known_tables: dict = None) -> dict:
    """선언마다 「승인됐는가 · 아니면 무엇을 만들어야 하는가」. `GET /admin/chain/join/verify`.

    🔴 [판정 678 · 683] 이것은 «이름 옮기기가 아니라 수리다». 「승인」은 축이고
    「virtual-join」은 배관이라는 것까지는 672 가 맞았는데, 실측이 한 칸 더 말했다: 그 축이
    옛 좌석에서 «닿지 않고» 있었다. 옛 보고서는 읽기 시점 문법만 읽으므로, 실조인으로 선언된
    조인은 그 패널에 승인으로도 거절로도 «뜨지 않는다» — 그 문법으로 조인을 쓰지 않는 설치에서
    그 패널의 승인 목록은 비어 있게 된다.

    ⚠️ 그리고 그 «비어 있음»을 「지워도 잃을 것이 없다」로 읽으면 안 된다. 비는 것은 «승인
    목록»이고, 그 패널은 레거시 선언의 «거절 목록»을 들고 있다 — 그것이 왜 거절됐나는 아직
    거기서만 답해진다. 그래서 그 라우트는 «그 문법과 같은 커밋»에서 죽는다 (678 ③).

    🔴 저자가 «셋»이 되지 않는다. 「어느 인덱스를 «짓나»」와 「어느 것을 «요구하나»」가 갈릴 수
    없어야 해서 `declared_unique_targets` 가 한 워커인 것과 «같은 이유»로, 「어느 것을
    «보고하나»」도 그 워커에서 나온다. 접기·키 쌍은 `join_into` 가 이미 계산한 것을 받고,
    문장은 `/admin/config/resolve` 와 «같은 조립기»가 짓는다.

    ⚠️ 캐시를 «읽지도 채우지도» 않는다. `_RIGHT_KEYS` 는 쓰기 경로가 적재당 한 번 배우는
    답이고, 여기는 운영자가 인덱스를 «방금 만들고» 새로고침하는 자리라 그 답이 «지금»
    이어야 한다. 같은 워커와 같은 탐침을 쓰므로 **두 좌석은 「어느 것」에서 못 갈라지고
    「언제」에서만 갈라진다**.

    ⚠️ 행을 «안 센다» — 카탈로그만 읽는다. 그래서 비용이 표 크기와 무관하고 요청 경로에
    앉을 수 있다(옛 계약 그대로).
    """
    import event_constants
    from chain import ingestion_worker, join_key_index, join_refusal, rule_shape
    from database import crud

    catalogue = known_tables if known_tables is not None else crud.TABLE_CONFIG
    read = ingestion_worker.read_rules_document()
    stood_all, by_name, invalid, out = [], {}, [], []

    for raw in (read["rules"] or ()):
        if not isinstance(raw, dict):
            continue
        internal = rule_shape.from_declaration(raw)
        is_join = (internal.get("derive") or {}).get("kind") == "join"
        stood, refusal, notes = rule_shape.expand_declaration(raw, catalogue)
        if refusal:
            # ⚠️ 조인 갈래만. 거절된 `decide` 를 「조인 승인」 패널에 실으면 운영자가
            #    이 화면에서 «못 고치는» 것을 이 화면에서 읽는다.
            if is_join:
                invalid.append({"subject": raw.get("name"), "detail": refusal})
            continue
        if is_join and not stood:
            # 🔴 꺼 둔 조인은 서는 규칙이 «0» 이라 걷는 이에 닿지 않는다 (판정 399). 그런데
            #    그것도 「승인 안 됨」의 한 경우이고, 여기서 빠지면 운영자가 자기 선언을
            #    화면에서 «못 찾는다» — 판정 680 이 메운 구멍과 «같은 구멍»이다. 사유는
            #    로더의 것을 그대로 싣는다 (Q-194: 없는 사유가 틀린 사유보다 낫다).
            out.append(_approval_row(
                rule_shape.as_chain_rule(internal), None, None, None, None,
                notes[0] if notes else None,
                event_constants.APPROVAL_STATE_NOT_ASKED))
            continue
        for rule in stood:
            stood_all.append(rule)
            by_name.setdefault(rule.get("name"), rule)

    seen = set()
    for name, table, columns, folds, skip, kind in declared_unique_targets(stood_all):
        rule = by_name.get(name) or {}
        if skip or not table or not columns:
            # ⚠️ 동반 반쪽(`:reference`)은 같은 선언의 반쪽이라 한 행으로 접는다.
            base = (name or "").split(rule_shape.REFERENCE_SUFFIX)[0]
            if base in seen:
                continue
            seen.add(base)
            # 🔴 [판정 685] 상태는 걷는 이의 «칸»에서 옵니다. 사유 «문장»으로 가르면
            #    낱말이 바뀌는 날 조용히 틀리고, 여기서 `key.unique` 를 다시 보면 이 워커가
            #    한 번만 답하려고 존재하는 물음에 «둘째 저자»가 생깁니다.
            out.append(_approval_row(
                rule, table, None, None, None, skip,
                event_constants.APPROVAL_STATE_NOT_ASKED
                if kind == SKIP_NOT_ASKED
                else event_constants.APPROVAL_STATE_REFUSED))
            continue
        # ⚠️ 한 유일성, 한 행. 인덱스 «이름»으로 접으므로 패널의 수가 «인덱스의 수»와 같다 —
        #    `declared_unique_index_names` 가 요구 집합을 세는 바로 그 키다.
        required_index = join_key_index.required_index_name(table, columns, folds)
        if required_index in seen:
            continue
        seen.add(required_index)
        required_index_ddl = join_key_index.required_index_ddl(table, columns, folds)
        unique_index = join_key_index.unique_index_covering(
            db, table, columns, folds=folds)
        detail = None if unique_index else join_refusal.join_detail(
            join_refusal.CODE_NO_UNIQUE_INDEX,
            {"right_table": table, "join_key": list(columns),
             "required_index_ddl": required_index_ddl})
        out.append(_approval_row(
            rule, table, required_index, unique_index, required_index_ddl, detail,
            event_constants.APPROVAL_STATE_APPROVED if unique_index
            else event_constants.APPROVAL_STATE_REFUSED))

    return {
        "declarations": out,
        "accepted": sum(1 for row in out if row["accepted"]),
        "refused": sum(1 for row in out if not row["accepted"]),
        "invalid": invalid,
    }


#: 이 프로세스가 «규칙을 다시 실을 때까지» 유효한 오른쪽 키 답. 시간 기준이 아니다.
_RIGHT_KEYS = {"loaded": False, "by_table": {}}


def reset_right_key_cache():
    """이 프로세스가 규칙을 다시 싣는다 — 다음 물음에서 새로 계산한다.

    🔴 [판정 667] 만료가 «시간»이 아니라 «적재»다. The seat this replaced carried a 5-second
    TTL, and the comment on it said why: the reload hook is the WEB server's, and worker
    processes never reach it, so the TTL was standing in for an invalidation those processes
    do not get. Keyed to loading instead, every process gets the same rule - the answer is
    good until that process reads the declarations again.

    ⚰️ [판정 677 ② · 652 3걸음] 「no process pays a clock」 stood here, was false when
    written, was corrected to name the OTHER half's 5-second TTL, and is now simply true:
    that half went with its grammar. 예고한 대로 «같은 커밋»에서 갔습니다.

    ⚠️ 창이 «길어집니다», 모양은 안 바뀝니다. 인덱스가 걷혔는데 맵이 「있다」로 낡으면 그물이
    파이썬에서 거절하고 그 거절은 `operator_line` 으로 표·컬럼·키·다음 행동을 «이름 대어»
    말합니다. 반대로 낡으면 그물을 건너뛰고 DB 제약이 23505 로 웁니다. 둘 다 시끄럽습니다 —
    바뀌는 것은 그 시끄러움이 5초 안에 끝나느냐, 이 프로세스가 다시 실을 때까지 가느냐입니다.
    """
    _RIGHT_KEYS["loaded"] = False
    _RIGHT_KEYS["by_table"] = {}


def right_keys_for(db, table_name: str) -> list:
    """이 표가 «지고 있는 유일성» — `(규칙 이름, 컬럼, 폴드)` 들. 승인된 것만.

    🔴 승인된 것만이고, 그것이 이 방향의 핵심이다 (S-174 에서 옮겨 옴). 승인은 「조인 키를
    덮는 UNIQUE 인덱스가 «실제로» 있다」는 뜻이고, 인덱스가 없으면 깨질 제약도 없다. 모양만
    통과한 선언으로 행을 거절하면 데이터베이스가 받아 줬을 행을 «가드가» 버린다.

    🔴 [판정 652] 입력이 «실조인 선언»뿐이다. 이 답을 주던 둘째 생산자(`rules_for_right`)가
    자기 문법과 같이 갔고, 폴드는 `join_into` 가 이미 계산한 것에서 온다 — 인덱스와 조인이
    «같은 식»에서 나와야 하고, 두 번째 계산은 판정 397 이 없앤 두 번째 저자다.

    ⚠️ 한 프로세스당 «첫 배치» 한 번만 판다: 파일 1 + pg_index N. 선언이 0 이면 N 도 0 이라
    호출이 «아예» 없다. 그 뒤 모든 배치는 I/O 0 이다.
    """
    if not _RIGHT_KEYS["loaded"]:
        from chain import ingestion_worker, join_key_index
        from database.database import SessionLocal

        # ⛔ [판정 667 ⓒ, 2026-09-15 장애 다섯째] ITS OWN SESSION, AND THE `db` ARGUMENT IS
        # NOT USED FOR THIS. The probe used to run in whoever's session missed the cache,
        # so a declaration that blew up while checking table B killed the transaction that
        # was reading table A. 「호출자의 db 를 쓰면 세션이 안 는다」 is the simplification
        # that caused it - the caller's transaction is not this question's to spend.
        probe = SessionLocal()
        try:
            by_table, seen = {}, set()
            for name, table, columns, folds, skip, _kind in declared_unique_targets(
                    ingestion_worker.load_chain_rules()):
                if skip or not table or not columns:
                    continue
                # ⚠️ ONE UNIQUENESS, ONE ENTRY. A join and its `:reference` companion declare
                #    the SAME key on the same table, so both arrive here. Kept as two, the
                #    write gate checks one key twice and an operator sees the SAME duplicate
                #    reported under two rule names - 「한 사실, 두 문장」. The index seat
                #    already folds this way for the same reason (asking twice probes
                #    `pg_index` twice and reports one index as two).
                shape = (table, tuple(columns), tuple(folds or ()))
                if shape in seen:
                    continue
                if not join_key_index.unique_index_covering(
                        probe, table, columns, folds=folds):
                    continue
                seen.add(shape)
                by_table.setdefault(table, []).append(
                    (name, list(columns), list(folds or [])))
        finally:
            probe.close()
        _RIGHT_KEYS["by_table"] = by_table
        _RIGHT_KEYS["loaded"] = True
    # ⚰️ [Q-192 · 판정 652 3걸음] 여기서 «둘째 생산자»(읽기 시점 조인이 지고 있던 유일성)를
    #    같이 들었다. 그 문법이 은퇴해 한 표가 유일성을 지는 길이 하나뿐이라, 그 줄과
    #    `_legacy_right_keys` 가 예고한 대로 «같은 커밋»에서 갔다.
    return list(_RIGHT_KEYS["by_table"].get(table_name) or [])




def retract_unrequired_indexes_once(db, known_tables: dict = None) -> dict:
    """제품이 만든 `uq_vjoin_*` 중 «지금 아무 선언도 요구하지 않는» 것을 걷는다.

    🔴 [S-248, 판정 652 로 이사] AN INDEX LIVES EXACTLY AS LONG AS THE JOIN THAT REQUIRES IT.
    When the join that asked for one is refused, migrated or switched off, nothing took the
    index back - and the write gate cannot see it, because that gate knows the keys of
    declared rules only. So it bit from OUTSIDE the gate: 23505 on every insert of a
    colliding row, and the group failed permanently on every retry.

    🔴 IT MOVED HERE BECAUSE ITS OLD SEAT IS BEING RETIRED, AND THE MOVE IS THE POINT. The
    only production caller sat inside the read-time join loader, and the set it retracted
    from was 「read-time declarations PLUS the unified ones」. Retiring that loader without
    moving this would leave the REAL join's index with nobody to take it back - S-248
    reproduced, on the half that stays.

    ⛔ 「부분 목록으로 회수하지 않는다」 IS NOW STRUCTURAL, NOT A FLAG. The old seat had to
    refuse when a caller handed it a partial list; this one takes no list at all -
    `declared_unique_index_names` reads the live declarations through the loader's own judge,
    so a complete set is the only thing it can compute. Half a required set does not retract
    a little less, it retracts the wrong thing.

    ⚠️ AND IT CAN NEVER BREAK THE CALLER. Warmup continues whatever happens in here.
    """
    from chain import unique_key

    # ⚰️ [판정 652 3걸음] 여기에 `| _legacy_required_index_names(...)` 가 있었다. 문법이
    #    «둘»일 때 한쪽만 든 요구 집합은 「조금 덜 회수」가 아니라 «다른 쪽의 살아 있는
    #    인덱스»를 걷는다(S-248 의 장애). 이제 `uq_vjoin_` 을 요구하는 문법이 하나라
    #    이 한 줄이 전수다.
    return unique_key.retract_unrequired_once(
        db, declared_unique_index_names(known_tables=known_tables))




