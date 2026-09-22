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
        from chain import enrichment
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
    from chain import enrichment
    from chain import legacy_join_declaration

    if (rule or {}).get("mapper") == legacy_join_declaration.JOIN_MAPPER:
        return os.path.basename(legacy_join_declaration.VIRTUAL_JOIN_RULES_PATH)
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
#     SELF_WRITING_KINDS  -> `TEMPLATE_FACTS[...]['writes_itself']`
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
#     _run_join           -> nowhere. 판정 580: its execution half was already unreachable;
#                            the READING half (`legacy_materialized_join.rules_for_right`)
#                            is alive in the write path's uniqueness guard and is NOT
#                            touched - a guard that cannot read its declaration refuses no
#                            row, silently.


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


#: 이 프로세스가 «규칙을 다시 실을 때까지» 유효한 오른쪽 키 답. 시간 기준이 아니다.
_RIGHT_KEYS = {"loaded": False, "by_table": {}}


def reset_right_key_cache():
    """이 프로세스가 규칙을 다시 싣는다 — 다음 물음에서 새로 계산한다.

    🔴 [판정 667] 만료가 «시간»이 아니라 «적재»다. The seat this replaced carried a 5-second
    TTL, and the comment on it said why: the reload hook is the WEB server's, and worker
    processes never reach it, so the TTL was standing in for an invalidation those processes
    do not get. Keyed to loading instead, every process gets the same rule - the answer is
    good until that process reads the declarations again - and no process pays a clock.

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

    🔴 [판정 652] 입력이 «실조인 선언»이다. 읽기 시점 조인 문법이 은퇴하면서, 이 답을 주던
    `legacy_materialized_join.rules_for_right` 도 같이 간다. 값은 같은 세 개이고, 나오는 곳이
    `join_into` 가 이미 계산하는 폴드로 바뀐다 — 인덱스와 조인이 «같은 식»에서 나와야 하고,
    두 번째 계산은 판정 397 이 없앤 두 번째 저자다.

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
            for name, table, columns, folds, skip in declared_unique_targets(
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
    answer = list(_RIGHT_KEYS["by_table"].get(table_name) or [])
    # 🔴 [Q-192 의 교훈] 아직 살아 있는 읽기 시점 조인의 유일성도 «같이» 듭니다. 그 좌석은
    #    자기 캐시와 자기 세션을 들고 있어 여기서 재지 않습니다 - 그리고 그 문법이 죽는
    #    커밋에서 이 두 줄이 같이 죽습니다.
    from database.database import SessionLocal

    legacy_probe = SessionLocal()
    try:
        answer.extend(_legacy_right_keys(
            legacy_probe, table_name,
            {(table_name, tuple(cols), tuple(folds)) for _n, cols, folds in answer}))
    finally:
        legacy_probe.close()
    return answer


def _legacy_right_keys(probe, table_name: str, seen: set) -> list:
    """아직 살아 있는 «읽기 시점» 조인이 지고 있는 유일성도 같이 든다.

    🔴 [Q-192 의 교훈을 같은 라운드에 두 번 쓰지 않기 위해] BOTH PRODUCERS OR NEITHER. The
    duplicate net protects a uniqueness a table CARRIES, and until 판정 652 finishes there
    are two grammars that can make a table carry one. Moving the net to the real join alone
    would leave a live read-time join's uniqueness unprotected - which is the same half-set
    mistake the retraction made earlier today, pointed at writes instead of indexes.

    ⚰️ AND IT DIES WITH ITS GRAMMAR, IN THAT COMMIT. 652 step one deletes the read-time
    loader; this goes with it. Removing it sooner is the half state, removing it later
    leaves a second author of the same answer.

    ⚠️ 이 박스에서는 그 문법의 선언 다섯이 전부 거절돼 «0» 을 냅니다. 그 0 은 설치 하나를
    돌리는 곳에 대해 아무 말도 하지 않습니다 - 그래서 수가 아니라 구조로 답합니다.
    """
    from chain import legacy_materialized_join

    out = []
    for rule in legacy_materialized_join.rules_for_right(probe, table_name) or ():
        columns = list((rule or {}).get("right_columns") or ())
        folds = list((rule or {}).get("right_folds") or ())
        if not columns:
            continue
        shape = (table_name, tuple(columns), tuple(folds))
        if shape in seen:
            continue
        seen.add(shape)
        out.append((rule.get("name") or "<unnamed>", columns, folds))
    return out


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

    return unique_key.retract_unrequired_once(
        db, declared_unique_index_names(known_tables=known_tables)
        | _legacy_required_index_names(known_tables=known_tables))


def _legacy_required_index_names(known_tables: dict = None) -> set:
    """아직 살아 있는 «읽기 시점» 조인 선언이 요구하는 `uq_vjoin_*` 이름.

    🔴 [Q-192] BOTH PRODUCERS OR NEITHER, AND THIS HALF IS NOT GONE YET. Two grammars write
    declarations that require an index and BOTH indexes wear the `uq_vjoin_` prefix, so the
    retraction sweeps them together. A required set holding only one half does not retract a
    little less - it retracts the OTHER half's live indexes, which is S-248's outage (23505
    on every insert, the group failing permanently) pointed at the grammar that still runs.
    Measured by adversarial QA on the commit that moved the seat: the move carried the
    retraction across and left this half behind.

    ⚰️ AND IT DIES WITH ITS GRAMMAR, NOT BEFORE. 판정 652 retires the read-time join; when
    that declaration file and its loader go, this function goes IN THE SAME COMMIT. Removing
    it earlier is precisely the half-set this docstring is about.

    ⚠️ NAMES ONLY, NO DATABASE. `load_virtual_join_rules` validates SHAPE and approves
    nothing, so this costs a file read and no session - the retraction's caller already holds
    the only session in play.
    """
    from chain import join_key_index, legacy_join_declaration

    names = set()
    for rule in legacy_join_declaration.load_virtual_join_rules(
            known_tables=known_tables) or ():
        table = (rule or {}).get("right_table")
        columns = (rule or {}).get("right_columns")
        if table and columns:
            names.add(join_key_index.required_index_name(
                table, columns, rule.get("right_folds")))
    return names


