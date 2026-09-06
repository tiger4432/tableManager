"""프로세스 간 이벤트 공용 상수 — 내부 이벤트(POST /internal/events/*) + 아웃박스 제어 이벤트.

워처(parsers/directory_watcher.py)와 체인 워커(chain_ingestion_worker.py) 등
발신 측 데몬들이 공유한다. 값 변경 시 두 발신 경로와 수신부(main.py)의
구버전 호환 절단(500)을 함께 검토할 것.
"""

# ---------------------------------------------------------------------------
# Outbox CONTROL events - rows in `database_outbox` that are instructions to a
# daemon, not records of a data change.
#
# The chain worker drains the same table looking for data transactions, so every
# control type MUST be listed here: an unlisted one falls through into
# `process_chain_transaction_group`, which would read a trigger payload as a set
# of changed rows. `SCHEDULER_RUN_NOW` was already skipped by a hardcoded literal
# in one file; the set exists so the second control type could not be added
# without the skip.
# ---------------------------------------------------------------------------

#: Published by POST /admin/auto-update/run-now; consumed by run_auto_update.py.
EVENT_SCHEDULER_RUN_NOW = "SCHEDULER_RUN_NOW"

#: Published by POST /admin/retroactive/{op}/run; consumed by run_auto_update.py.
#: See server/retroactive.py (`RUN_EVENT_TYPE` is this constant).
EVENT_RETROACTIVE_RUN = "RETROACTIVE_RUN"

#: Durable marker left behind when an internal notification could NOT be
#: delivered (the hub was down, the POST timed out, a 5xx came back). It is not a
#: data change and no mapper may ever run for it: it is written already
#: `processed_chain=True, status='SUCCESS', broadcast_at=NULL`, which is exactly
#: the shape the chain worker's undelivered-broadcast sweep collects. The sweep
#: then fires `batch_refresh_required` for its `table_name` and stamps it.
#:
#: This deliberately reuses the marker the chain worker already had rather than
#: inventing a second recovery mechanism: one durable marker, one sweeper, one
#: place to be wrong. See internal_event_client.record_undelivered_notification.
EVENT_BROADCAST_RECOVERY = "BROADCAST_RECOVERY"

#: Every control type. The chain worker filters on membership, not on a literal.
CONTROL_EVENT_TYPES = frozenset({EVENT_SCHEDULER_RUN_NOW, EVENT_RETROACTIVE_RUN,
                                 EVENT_BROADCAST_RECOVERY})

#: `database_outbox.table_name` is not empty by convention, so a row that is about no
#: single table fills the column with an invented name. `retroactive` writes this one: a
#: run spans whatever its operation touches, which is not a table.
RETROACTIVE_RUN_TABLE = "__retroactive__"

#: 🔴 EVERY NAME IN THAT COLUMN THAT IS NOT A TABLE, and this declaration IS the
#: statement "these are not tables". A reader that shows the column to an operator asks
#: this set first, because a name nobody created sends them looking for it -- absence
#: spoken as a name, which costs a trip rather than a fact.
#:
#: ⛔ IT IS NOT "IS THIS A CONTROL EVENT". That class was tried on 2026-09-05 and is one
#: member too wide: `SCHEDULER_RUN_NOW` carries the REAL table its caller named
#: (`main.py`'s on-demand publisher), so filtering on the event type deleted a true name
#: and lost "which table is this run about" -- `event_types` does not carry that.
PLACEHOLDER_TABLE_NAMES = frozenset({RETROACTIVE_RUN_TABLE})

# ---------------------------------------------------------------------------
# WHO DRAINS A WAITING ROW
#
# 🔴 `processed_chain = false` DOES NOT MEAN "the chain worker is behind". Two daemons
# empty this table, and an instrument that adds their rows together reports the chain as
# backed up when the row it is counting belongs to the scheduler. That happened on
# 2026-09-04: one RETROACTIVE_RUN row aged in place while /health called the chain worker
# healthy, and the queue screen - which says "chain queue" - sent the reader to the chain.
#
# The sets live HERE because the judgement has to have one home. The scheduler's two
# watchers spelled one of them as a literal in its own filter, and a second copy in the
# instrument is how the two drift apart without either being wrong at the time.
# ---------------------------------------------------------------------------

#: Drained by `run_auto_update.py`. It watches exactly these two.
SCHEDULER_OWNED_EVENT_TYPES = frozenset({EVENT_SCHEDULER_RUN_NOW, EVENT_RETROACTIVE_RUN})

#: Drained by `chain_ingestion_worker.py`. These are the data events it groups by
#: transaction and marks processed on success (`CREATE`/`EDIT` are named at its
#: `valid_events`; every event in a successful group is marked, `DELETE` included).
CHAIN_OWNED_EVENT_TYPES = frozenset({"CREATE", "EDIT", "DELETE"})

OUTBOX_OWNER_SCHEDULER = "scheduler"
OUTBOX_OWNER_CHAIN = "chain"
OUTBOX_OWNER_UNKNOWN = "unknown"


def outbox_owner(event_type):
    """Which daemon empties a waiting row of this type - or that nobody has established it.

    🔴 `unknown` IS A REAL ANSWER AND MUST NOT BE FOLDED INTO `chain`. An unlisted type is
    one nobody has traced to a consumer, and "assume chain" reproduces exactly the
    misreading this split exists to end. `SYSTEM_RELOAD` is deliberately unlisted: the
    chain worker marks the LATEST one on a throttled branch of its own, so its fate
    depends on which row it is rather than on its type, and that is not a per-type answer.
    """
    if event_type in SCHEDULER_OWNED_EVENT_TYPES:
        return OUTBOX_OWNER_SCHEDULER
    if event_type in CHAIN_OWNED_EVENT_TYPES:
        return OUTBOX_OWNER_CHAIN
    return OUTBOX_OWNER_UNKNOWN

# [C-5] 인제션/체인 완료 통지에 동봉하는 감사 로그(created_logs) 상한.
# 웹서버(main.py /internal/events/*)와 audit_cache는 어차피 트랜잭션당 500건만 유지하므로,
# 발신 측이 전량(수만~수십만 dict, 직렬화 시 수십 MB JSON)을 메모리 누적·HTTP POST하는 것은
# 순수 낭비이자 웹서버 이벤트 루프 동결(대형 json.loads / pydantic 검증의 GIL 점유) 요인이다.
# 이벤트 필드 형태(created_logs: list)는 그대로 유지하고 항목 수만 제한하며(경계 계약 불변),
# 실제 총 로그 건수는 total_log_count 필드로 별도 전달한다(순수 추가 필드).
MAX_NOTIFY_CREATED_LOGS = 500


# ---------------------------------------------------------------------------
# [DEPTH] How far a chain has travelled, and how far it may.
# ---------------------------------------------------------------------------
#
# `source_name == "chain_ingestion"` says WHETHER the chain wrote a row. It cannot say HOW
# MANY hops produced it, so between "the chain may never wake the chain" (too tight - the
# owner's own words) and `allow_chain_trigger` (opt-in, then unbounded) there was nothing.
# This is the middle: the write carries a number, and a declared limit refuses beyond it.
#
#: The payload key. ⚠️ ABSENT means "not written by the chain" and is NOT 0 - an event from
#: outside the chain must never be refused for depth, and a 0 would be a chain write that
#: forgot to count. Folding the two loses the distinction exactly where it decides.
CHAIN_DEPTH_KEY = "chain_depth"

#: Used only when the declaration does not say. ⚠️ NOT the answer - the answer is the
#: declaration (`chain_rules.json`'s `max_chain_depth`), because an operator who knows their
#: own cascade is the one who can set this. This is what a config written before the key
#: existed gets, chosen to be generous enough that no cascade shipped today reaches it.
DEFAULT_MAX_CHAIN_DEPTH = 8


def chain_depth_of(payload):
    """How deep this event is, or `None` when it did not come from the chain.

    ⚠️ THREE STATES, NOT TWO. No key -> `None` (outside the chain). A key -> its number,
    including 0. A caller that wants arithmetic reads `None` as "start", but a caller
    deciding whether the limit applies must ask whether it is `None` FIRST.
    """
    if not isinstance(payload, dict):
        return None
    value = payload.get(CHAIN_DEPTH_KEY)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def max_chain_depth(rules):
    """The declared hop limit, or the default when nothing declares one.

    ⛔ ONE LIMIT, NOT ONE PER RULE. A per-rule limit was considered and not built: nothing
    today needs two, and the gate that would read them is a single loop over every rule an
    event matches, so a per-rule number would have to be reconciled at that point anyway.
    Gate ② of the standing checklist - do not build an axis nothing asks for yet.
    """
    if isinstance(rules, dict):
        declared = rules.get("max_chain_depth")
    else:
        declared = None
    if isinstance(declared, bool) or not isinstance(declared, int) or declared < 1:
        return DEFAULT_MAX_CHAIN_DEPTH
    return declared


#: The `batch_refresh_required` event name, and the ONE place its payload is built.
EVENT_BATCH_REFRESH_REQUIRED = "batch_refresh_required"


def batch_refresh_message(table_name, change_count, *, transaction_id=None,
                          created_logs=None, total_log_count=None,
                          deleted_row_ids_omitted=None):
    """The `batch_refresh_required` payload, built in one place.

    🔴 NINE SENDERS WERE EACH WRITING THIS DICT BY HAND, and a payload written nine times
    is a payload that will differ nine ways -- silently, because the client reads
    `msg.table_name` as a guard and then this event's body not at all, so a sender that
    dropped or misspelled a key would produce no error, no warning and no visible change.
    That is the owner's fourth cleanliness rule: one capability must not have two paths.
    Now they all pass through here, so drifting apart takes editing this function.

    ⛔ THE PAYLOAD IS UNCHANGED - NOT ONE KEY ADDED OR REMOVED. The optional four are
    omitted when they are not given, so every sender still produces exactly the object it
    produced before: seven send `{event, table_name, change_count}`, one adds
    `deleted_row_ids_omitted`, one adds the audit trio. Unifying the SHAPES is a different
    change and would be a boundary-contract decision, not this one.

    ⚠️ `change_count` IS ALWAYS PRESENT, INCLUDING WHEN IT IS 0. The client does not use it
    to decide whether to refresh, but `{change_count: 0}` and a missing key are different
    objects and the sweep's recovery message deliberately sends the zero.
    """
    message = {
        "event": EVENT_BATCH_REFRESH_REQUIRED,
        "table_name": table_name,
        "change_count": change_count,
    }
    # `is not None` rather than truthiness: an empty list and a zero are things a sender
    # meant to say, and dropping them would make "nothing was omitted" indistinguishable
    # from "this sender does not report omissions".
    if transaction_id is not None:
        message["transaction_id"] = transaction_id
    if created_logs is not None:
        message["created_logs"] = created_logs
    if total_log_count is not None:
        message["total_log_count"] = total_log_count
    if deleted_row_ids_omitted is not None:
        message["deleted_row_ids_omitted"] = deleted_row_ids_omitted
    return message

# [P1b] Row count above which a write's broadcast degrades from per-row `batch_row_upsert`
# items to a single `batch_refresh_required` carrying only a count (the client refetches).
#
# The VALUE is unchanged - it was the literal 100 written independently at four decision
# sites (main.py's batch-update, priority-batch and source-delete-batch endpoints, and the
# chain worker). It lives here for the same reason MAX_NOTIFY_CREATED_LOGS does: this is a
# per-SENDER decision that four senders make about the SAME client contract, and the
# documented failure mode of this codebase is one sender being corrected while the others
# keep the old literal. Above the threshold `items` has no consumer, so each site must also
# decide it BEFORE building them - see the comments at each call site.
BROADCAST_ITEM_LIMIT = 100

# [P2-C9] 단일 감사 로그 값(old_value/new_value)의 문자 길이 상한.
# 근거: created_logs를 500건으로 절단해도 값 하나가 무제한이면 페이로드가 다시 수십 MB가 될 수
# 있다(맵 문자열류 대형 텍스트 셀이 체인/워처 대상이 되는 경우 — 2026-07-25 인시던트의 잔여 경로).
# 500건 × 2값 × 4KB = 최악 4MB로 상한이 고정된다.
# 상한 초과 시 **조용히 자르지 않고** MAX_AUDIT_VALUE_TRUNCATION_SUFFIX 마커를 덧붙여
# 절단 사실과 원래 길이를 값 자체에 남긴다(DB 감사 레코드·WS 페이로드 양쪽 동일).
MAX_AUDIT_VALUE_CHARS = 4096


# ---------------------------------------------------------------------------
# [OUTBOX-4] Collapsed outbox events - the SHARED symbols of the shape contract.
#
# WHY THIS LIVES HERE AND NOT AT EACH SITE. The producer (`database.stage_event`)
# and four consumer families (chain worker, graph materializer, admin view,
# undelivered sweep) have to agree on what a payload MEANS. The documented
# failure mode of this table is a contract held by convention alone: the
# undelivered marker is written by `internal_event_client` as
# `processed_chain=True / status='SUCCESS' / broadcast_at=NULL` and collected by
# `chain_ingestion_worker.sweep_undelivered_broadcasts` filtering on exactly
# that, with NO shared symbol binding the two - change either side and nothing
# fails a test while markers stop being recovered forever. This block exists so
# the collapse contract does not repeat that.
#
# WHAT THE COLLAPSE IS. In `collapsed` mode one outbox row names the row_ids
# written by one flush instead of one outbox row carrying one row's values.
#
# WHY. Measured on this workstation (a simulation) against a real PostgreSQL
# `database_outbox` with all seven indexes: a per-row `dt_log` event costs
# 2,108 B/row all-in, i.e. 19.6 GiB at 10,000,000 ingested rows. Collapsed at
# 1,000 row_ids per event the same 10M rows cost 27.2 B/row - 10,000 outbox rows,
# 260 MiB. 1,000x fewer rows, 45x fewer bytes.
#
# 🔴 THE FRAMING THAT MATTERS IS NOT THE SIZE, IT IS THE DRAIN CEILING. The purge
# removes OUTBOX_PURGE_CHUNK(1000) x OUTBOX_PURGE_MAX_CHUNKS(50) = 50,000 rows per
# hourly cycle = 1,200,000 rows/day. That is the drain's SUSTAINED CEILING: at any
# ingestion rate above 1.2M rows/day the per-row outbox has no steady state and
# grows without bound. Collapsed, 10M ingested rows produce 10,000 outbox rows -
# one FIFTH of a single purge cycle. The purge knobs are untouched by this change
# precisely because at this event rate they no longer need to change.
#
# WHAT IT COSTS. The event stops being a SNAPSHOT and becomes a POINTER: a
# consumer that drains late re-reads the row's CURRENT value, not its value at
# event time. DELETE therefore cannot collapse (a deleted row cannot be re-read)
# and stays per-row - see `database.auto_stage_database_outbox`.
# ---------------------------------------------------------------------------

#: Per-row outbox events - one row per changed row, payload carries its values.
#: THE DEFAULT, so every caller that does not opt in keeps today's behaviour and
#: the safe direction needs no edit. The human/correction path must stay here:
#: a correction that reaches the DB but not the screen stops the correction loop.
OUTBOX_MODE_PER_ROW = "per_row"

#: Collapsed events - one row per (table, event_type) per flush, naming row_ids.
#: Bulk ingestion only, opted into explicitly. NOT inferred from `request_source`
#: (that is a FILENAME on the ingestion path, not a channel) and NOT inferred
#: from row count (a human map push is thousands of rows and must stay per-row).
OUTBOX_MODE_COLLAPSED = "collapsed"

#: Max row_ids carried by ONE collapsed event. Also the project-wide 1,000-row
#: chunking discipline. Keeps the payload ~40 KB, and bounds the blast radius of
#: the failure path: a poison row re-expands at most this many per-row retries.
OUTBOX_COLLAPSE_CHUNK_ROWS = 1000

#: Max INGESTED ROWS a chain/graph worker pulls into one processing batch.
#:
#: 🔴 THIS IS THE OLD `LIMIT 20000` KEEPING ITS MEANING, NOT A NEW KNOB. That cap
#: bounded the chain worker's completion-guard fetch at 20,000 EVENTS, which
#: while events were per-row meant 20,000 ROWS. Counting events after the
#: collapse would let one batch pull 20,000 chunks = 20,000,000 rows into a
#: single mapper call - a 1,000x amplification of the working set, in the one
#: place the codebase is most careful about (`bulk_*`, 1,000-row chunking). The
#: budget below is charged in ROWS (a per-row event costs 1, a collapsed event
#: costs its `row_count`), so the working set after the collapse is the same size
#: it was before it.
OUTBOX_GROUP_MAX_ROWS = 20000

#: Columns `stage_event` never puts in a payload (identity + housekeeping).
#: Shared so the expander rebuilds EXACTLY the columns the producer would have
#: written - a divergence here is a mapper silently seeing a column appear or
#: vanish, with nothing to fail.
OUTBOX_PAYLOAD_EXCLUDED_COLUMNS = frozenset({
    "row_id", "business_key_val", "created_at", "updated_at",
    "is_graph_synced", "needs_graph_rollback", "graph_synced_at",
})


def is_collapsed_payload(payload) -> bool:
    """True if this outbox payload NAMES rows instead of CARRYING one row's values.

    Membership test on the discriminating key, not on `event_type`: the collapse
    deliberately keeps `event_type` as CREATE/EDIT so that every consumer which
    only asks "is this a data change on table T" (`_group_target_tables`, the
    circular-loop filter, `materialize_events`, the admin view, health) keeps
    working untouched. Only the consumers that actually READ `payload['data']`
    need to branch, and they branch here.
    """
    return isinstance(payload, dict) and isinstance(payload.get("row_ids"), list)


def payload_row_count(payload) -> int:
    """How many ingested rows one outbox event stands for (per-row events: 1)."""
    if is_collapsed_payload(payload):
        rc = payload.get("row_count")
        if isinstance(rc, int) and rc >= 0:
            return rc
        return len(payload.get("row_ids") or ())
    return 1


def trim_events_to_row_budget(events, budget: int = OUTBOX_GROUP_MAX_ROWS,
                              payload_of=None):
    """Keep the id-ordered PREFIX of `events` whose ingested-row total fits `budget`.

    A prefix, never a filter: the tail is left `processed_chain=False` and is
    picked up by the next iteration in the same order, so nothing is skipped and
    no ordering is inverted. At least one event is always returned - a single
    chunk larger than the budget must still make progress rather than wedge the
    drain forever.
    """
    if not events:
        return events
    if payload_of is None:
        from utils.payload_helper import get_payload_dict as payload_of
    kept = []
    total = 0
    for ev in events:
        cost = payload_row_count(payload_of(ev))
        if kept and total + cost > budget:
            break
        kept.append(ev)
        total += cost
    return kept


def truncate_audit_value(value, max_chars: int = MAX_AUDIT_VALUE_CHARS):
    """감사 로그 값 1건을 상한 길이로 절단한다(절단 시 명시 마커 부착).

    - str: 상한 초과 시 앞부분을 남기고 `…[truncated: 총 N자]` 마커를 덧붙인다.
    - dict/list: repr 길이가 상한을 넘으면 타입·길이만 남긴 명시 플레이스홀더 문자열로 대체한다
      (부분 절단은 구조를 깨뜨려 더 해석 불가능한 값이 되므로 채택하지 않음).
    - 그 외(int/float/bool/None): 원본 그대로 (길이 위험 없음).

    반환: (절단된 값, 절단 여부)
    """
    if isinstance(value, str):
        if len(value) <= max_chars:
            return value, False
        return f"{value[:max_chars]}…[truncated: 총 {len(value)}자]", True
    if isinstance(value, (dict, list, tuple)):
        try:
            raw_len = len(repr(value))
        except Exception:
            return value, False
        if raw_len <= max_chars:
            return value, False
        return (
            f"[truncated: {type(value).__name__} 값 {raw_len}자 — "
            f"감사 로그 값 상한 {max_chars}자 초과로 본문 생략]",
            True,
        )
    return value, False


#: The shape an UNDELIVERED-NOTIFICATION marker has, in ONE place.
#
# 🔴 IT WAS TWO PLACES AND NOTHING JOINED THEM. `internal_event_client
# .record_undelivered_notification` builds the row and
# `chain_ingestion_worker.sweep_undelivered_broadcasts` filters for it, and both spelled
# the same three values by hand. Change one side and the marker is written in a shape the
# sweeper does not collect: no error, no exception, and the row sits in the database
# forever while the screen never learns - which is precisely the incident this mechanism
# exists to prevent.
#
# 🔴 AND THE TESTS COULD NOT SEE IT. The five covering the sweep hand-build their own
# rows, so they stay green whatever the writer does. A shared spelling is what makes the
# two sides fail together instead of drifting apart quietly.
#
# ⚠️ `broadcast_at` IS NOT HERE, deliberately: NULL is not a value the writer sets, it is
# the absence the sweeper looks for. Naming it would invite somebody to write it.
UNDELIVERED_MARKER_STATUS = "SUCCESS"          # the DATA succeeded; only the notice failed
UNDELIVERED_MARKER_PROCESSED_CHAIN = True      # never re-run as a data transaction
UNDELIVERED_MARKER_TAG = "undelivered_notification"   # payload["marker"], for attribution


#: 실패 사유가 «카드»까지 가는 길에서 잘리던 상한. 토스트 문장은 100자로 접지만, 카드는
#: 사유 «자체»를 받아 자기 폭에 맞춰 자릅니다 — 서버가 미리 접으면 카드는 접힌 것을 또 접습니다.
MAX_INGESTION_ERROR_CHARS = 500

EVENT_FILE_INGESTION_COMPLETED = "file_ingestion_completed"


def file_ingestion_completed_message(table_name, filename, status, error_msg=None):
    """`file_ingestion_completed` 페이로드 — 한 자리에서 만든다.

    🔴 THE REASON WAS FOLDED INTO THE SENTENCE AND THE FIELD WAS NEVER SENT. Three senders
    each built this dict by hand, each appended `error_msg` to `message`, and none of them
    put `error_msg` in the payload. The client reads BOTH: the toast shows `message` (so the
    reason was visible there) and the floating progress card reads `msg.error_msg` -- which
    was always `undefined`, so the card fell back to its placeholder and EVERY failure looked
    like the same failure. 실측 2026-09-07: 보내는 자리 «셋» · 그 칸을 싣는 자리 «0» ·
    읽는 쪽은 «살아 있고 출하돼» 있었다(`utils.js` `finishIngestionProgress`).

    🔴 그래서 이것은 「만들기」가 아니라 «나르기»다. 읽는 쪽도, 사유도, 내부 POST 의 칸도
    (`run_watcher.trigger_ws_file_processed` 가 `payload["error_msg"]` 를 이미 싣는다) 전부
    있었고, «브로드캐스트를 짓는 세 자리»에서만 떨어졌다.

    ⛔ 그리고 셋에 한 줄씩 더하지 «않는다». `batch_refresh_message` 가 아홉 발신자에게
    같은 이유로 만들어진 그 자리이고, 손으로 세 번 쓴 페이로드는 «세 갈래로» 갈린다 —
    다음 사람이 둘만 고치는 것이 이 결함의 재발 경로다 (기준 ④).

    ⚠️ `error_msg` 는 SUCCESS 에도 실린다. 그 슬롯은 성공에서 «detail»(예: 「키 결측으로 N행
    스킵」)을 나르고, 그것을 여기서 «버리면» 화면이 그 사실에 닿을 길이 없어진다. 오늘 카드가
    그 값을 성공 갈래에서 «안 읽는» 것은 별개의 줄(F-6)이고, 여기서 미리 접지 않는다.
    """
    if status == "SUCCESS":
        message = f"{filename} 파일이 처리되었습니다."
    else:
        message = f"{filename} 파일 처리에 실패했습니다."
    reason = str(error_msg) if error_msg else None
    if reason:
        # 문장은 짧게 — 토스트 한 줄이다. 칸은 길게 — 카드가 자기 폭으로 자른다.
        message += f" ({reason[:100]})"
    msg = {
        "event": EVENT_FILE_INGESTION_COMPLETED,
        "table_name": table_name,
        "filename": filename,
        "status": status,
        "message": message,
    }
    if reason:
        msg["error_msg"] = reason[:MAX_INGESTION_ERROR_CHARS]
    return msg


#: 「이 묶음의 소급 정보를 «읽었나»」. `blocked_by` 와 `queue` 는 «한 번의 읽기»에서 나오므로
#: 상태도 하나다 — 둘 중 하나만 실패하는 경우가 없다.
#:
#: 🔴 낱말을 «새로 짓지 않았다**. `ready` 는 `ledger_trace.COVERAGE_STATES` 가,
#: `unknown` 은 `config_backup`(ok/stale/missing/unknown)과 `enrichment_candidates.EXPECT_UNKNOWN`
#: 이 이미 쓰는 것이다. 같은 뜻에 네 번째 철자를 만들면 화면이 그중 하나만 알게 된다.
#:
#: ⚠️ 그리고 이것은 `blocked_by` 의 null 을 «대체하지 않는다**. 그 null 은 이미 뜻이 있다 —
#: 「도는 것이 없다」이고, 화면이 그것을 「막힌 것 없음」으로 그리지 «않도록» 패널이 일부러
#: 아무것도 안 그린다. 여기서 가르는 것은 그 null 과 「못 읽어서 null」이다.
RETROACTIVE_READ_READY = "ready"
RETROACTIVE_READ_UNKNOWN = "unknown"
