import logging

logger = logging.getLogger(__name__)
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

#: `RETROACTIVE_RUN` «한 타입»이 주인 다른 일 셋을 덮는다 — 이 op 만 체인 워커가 비우고,
#: 나머지(`withdraw` · `ledger_backfill`)는 스케줄러 그대로다. 그래서 주인이 타입만으로
#: 안 나오는 «유일한» 타입이고, 이 집합이 그 예외의 정본이다.
CHAIN_OWNED_RETROACTIVE_OPS = frozenset({"chain_replay"})

#: 한 규칙이 한 트랜잭션 그룹에 «무엇을 했나» — 닫힌 어휘.
#: 🔴 운영자가 가르는 것은 다섯이다: 꺼짐 · 안 걸림 · 돌았는데 0 · 바뀜 · 실패.
#:    원인은 «여섯»이지만 값으로 만들지 않는다 — 원인은 «사유 문자열»이 옆에서 말하고,
#:    값이 원인마다 하나면 화면이 그 여섯을 다시 다섯으로 접어야 한다(판정 이 두 번이다).
#: ⚠️ 「꺼짐」이 「안 걸림」을 이긴다. 둘 다 참일 때 운영자가 «고칠 수 있는» 쪽이 그것이고,
#:    「안 걸림」은 데이터의 사실이라 고칠 대상이 아니다.
RULE_OUTCOME_SKIPPED_DISABLED = "skipped:disabled"
RULE_OUTCOME_SKIPPED_NOT_TRIGGERED = "skipped:not_triggered"
RULE_OUTCOME_RAN_UNCHANGED = "ran:unchanged"
RULE_OUTCOME_RAN_CHANGED = "ran:changed"
RULE_OUTCOME_FAILED = "failed"
#: 🔴 「아직 평가 안 됨」은 «부재가 아니라 값»이다. 이 프로세스가 그 규칙을 한 번도 안 본
#:    상태이고, 그것과 「옛 서버라 이 칸이 없다」는 다른 사실이다 — 부재는 뒤엣것 «하나»만
#:    뜻해야 한다(판정 45 게이트 ②와 같은 규율).
RULE_OUTCOME_NEVER_EVALUATED = "never_evaluated"

RULE_OUTCOMES = frozenset({
    RULE_OUTCOME_SKIPPED_DISABLED, RULE_OUTCOME_SKIPPED_NOT_TRIGGERED,
    RULE_OUTCOME_RAN_UNCHANGED, RULE_OUTCOME_RAN_CHANGED,
    RULE_OUTCOME_FAILED, RULE_OUTCOME_NEVER_EVALUATED,
})

#: 규칙 «목록»의 두 상태 — 위의 OUTCOME 과 다른 물음이다. 저쪽은 「한 그룹에 무엇을 했나」,
#: 이쪽은 「이 선언이 아예 서 있기는 한가」.
#: 🔴 [판정 656] 「없다」와 「꺼짐」이 같은 픽셀이면 안 된다. 운영자가 끈 선언은 목록에
#:    «남아야» 다시 켤 수 있고, 미완성 선언은 「사라진 것」이 아니라 「안 선 것」이다.
#: ⛔ 「안 섬」의 사유는 값으로 만들지 않는다 — `state_detail` 이 옆에서 말한다. 꺼짐과
#:    미완성을 값으로 가르면 화면이 둘을 다시 하나로 접어야 한다 (위 OUTCOME 과 같은 이유).
RULE_STATE_RUNNING = "running"
RULE_STATE_DECLARED_ONLY = "declared_only"

RULE_STATES = frozenset({RULE_STATE_RUNNING, RULE_STATE_DECLARED_ONLY})

#: 조인 «승인»의 세 상태 — 위의 RULE_STATE 와 다른 물음이다. 저쪽은 「이 선언이 서 있나」,
#: 이쪽은 「이 조인이 «성립»하나」(= 조인 키를 덮는 UNIQUE 인덱스가 실제로 있나).
#: 🔴 [판정 685] 화면이 이 셋을 «유도»하면 안 된다. 클라가 「DDL 이 있나」로 가르고
#:    있었고 그건 대리다 — DDL 없는 거절이 하나 생기는 날 조용히 틀린다.
#: ⛔ 위 RULE_STATE 와 «같은 규율»로 사유는 값이 아니다 — `detail` 이 옆에서 말한다.
#:    그래서 「꺼짐」은 넷째 값이 아니라 NOT_ASKED 다(판정 399: 끈 것은 «틀린 것이 아니다»).
APPROVAL_STATE_APPROVED = "approved"
APPROVAL_STATE_REFUSED = "refused"
APPROVAL_STATE_NOT_ASKED = "not_asked"

APPROVAL_STATES = frozenset({APPROVAL_STATE_APPROVED, APPROVAL_STATE_REFUSED,
                             APPROVAL_STATE_NOT_ASKED})

#: 아웃박스 «행 하나»가 체인에 대해 서 있는 자리 — 위 둘과 «같은 규율»로 사유는 값이
#: 아니다. `state_detail` 이 옆에서 말한다(RETRYING · 모순 조합 · 어휘 밖 원값).
#: 🔴 값을 넷째로 늘리고 싶어지면 그것은 대개 «사유»다. `status` 리터럴을 그대로 상태로
#:    쓰면 화면이 어휘 밖 값 하나에 「모름」을 그린다 — 실제로 RETRYING 이 그 자리였다.
#: ⚠️ 이 셋은 `status` 와 `processed_chain` «둘»에서 나온다. 한 칸만 읽으면
#:    「돌았다」와 「돌다 실패했다」가 같은 값이 된다.
CHAIN_STATE_WAITING = "waiting"
CHAIN_STATE_DONE = "done"
CHAIN_STATE_FAILED = "failed"

CHAIN_STATES = frozenset({CHAIN_STATE_WAITING, CHAIN_STATE_DONE, CHAIN_STATE_FAILED})

#: 통지가 «확정»됐나 — 체인 상태와 «다른 축»이다. 둘을 한 값으로 접으면
#: 「돌았는데 아직 안 알려졌다」가 「돌았다」에 묻힌다. 그 행은 스윕이 다시 쏜다.
BROADCAST_STATE_DELIVERED = "delivered"
BROADCAST_STATE_UNDELIVERED = "undelivered"
BROADCAST_STATE_NOT_APPLICABLE = "not_applicable"

BROADCAST_STATES = frozenset({BROADCAST_STATE_DELIVERED, BROADCAST_STATE_UNDELIVERED,
                              BROADCAST_STATE_NOT_APPLICABLE})


#: 아웃박스 행이 «태어났다»를 나르는 두 이름. 한 사건의 두 구간이라 «같이» 산다.
#:
#: 🔴 채널 이름은 상수가 «0» 이었고 리터럴이 일곱 곳이었다(2026-09-22 실측:
#:    database:392 · retroactive:1441 · main:6603 · main:6965 · system_reload:189 ·
#:    ingestion_worker:104 · :3690). `batch_refresh_message` 가 손으로 아홉 번 적히던
#:    바로 그 모양이고, 그쪽과 같은 이유로 여기 접는다.
#:
#: ⚠️ 둘은 «다른 전선»이다 — 채널은 PostgreSQL LISTEN/NOTIFY(서버끼리),
#:    사건 이름은 WebSocket(브라우저에게). 한쪽 이름을 다른 쪽에 쓰지 않는다.
OUTBOX_NOTIFY_CHANNEL = "outbox_event"
EVENT_OUTBOX_QUEUE_CHANGED = "outbox_queue_changed"


def chain_state_of(processed_chain, status):
    """(`processed_chain`, `status`) -> (상태, 사유). 「빈 칸」이 없다 — 모든 조합이 답을 받는다.

    🔴 `mark_processed` 가 status 와 `processed_chain=True` 를 «같이» 찍으므로 영구 실패는
       `processed_chain=true` 다. 그래서 「안 돌린 실패」는 도달 불가이고, 그 조합이 실제로
       오면 그것은 «모순»이라 숨기지 않고 사유로 말한다.
    """
    if not processed_chain:
        if status == "RETRYING":
            return CHAIN_STATE_WAITING, "retrying"
        if status in ("PENDING", None):
            return CHAIN_STATE_WAITING, None
        return CHAIN_STATE_WAITING, "unexpected_status:%s" % (status,)
    if status == "SUCCESS":
        return CHAIN_STATE_DONE, None
    if status == "FAILED":
        return CHAIN_STATE_FAILED, None
    return CHAIN_STATE_DONE, "unexpected_status:%s" % (status,)


def mark_processed(event, status: str):
    """The ONE place an outbox event stops being work. Status, the flag, and the time.

    🔴 BESIDE `chain_state_of`, the one reader of the same two columns (총괄 3c3f2b1f2).
    It lived in the chain worker; the scheduler drains rows too, did not import it, and
    hand-wrote the flag at five sites - three without a status, none with the time. Those
    rows read 「done · unexpected_status:PENDING」 on the queue.

    🔴 FAILURE IS STAMPED TOO. The column means "when this stopped being worked on", and
    a permanently failed event has stopped.

    ⚠️ `func.now()`, not Python's clock: `created_at` is a server default, so both ends
    of "queued until finished" have to be read from the same clock or the difference is
    a measurement of clock skew.
    """
    for column, value in processed_columns(status).items():
        setattr(event, column, value)


#: 「Ended without running」 - who ended it and why, in the payload, so the row's history
#: says it was skipped rather than run. Moved here from `scripts/outbox_triage` when the
#: failed-list retry became the second writer (총괄 f063c948e: a leaf whose row is gone).
CANCEL_MARK = "cancelled_by"
CANCEL_REASON = "cancel_reason"


def mark_cancelled(event, by: str, reason: str):
    """End an event without running it: the mark and the reason, then `mark_processed`."""
    from utils.payload_helper import get_payload_dict

    payload = dict(get_payload_dict(event) or {})
    payload[CANCEL_MARK] = by
    payload[CANCEL_REASON] = reason
    event.payload = payload
    mark_processed(event, "SUCCESS")


def processed_columns(status):
    """What 「this row stopped being work」 writes - ONE definition. `mark_processed` sets it
    on one object; a set-based UPDATE spreads it where rows are too many for the ORM
    (`scripts/outbox_triage` cancel: ~660,000 rows in production, 총괄 8a1f32f99)."""
    from sqlalchemy import func

    return {"status": status, "processed_chain": True, "processed_at": func.now()}


def _undelivered_when():
    """「미전달」 — ONE definition (총괄 ac3039494). `broadcast_state_of` reads it in Python and
    `undelivered_clause` in SQL; `idx_outbox_undelivered` indexes the same three columns."""
    return {"processed_chain": True, "status": UNDELIVERED_MARKER_STATUS, "broadcast_at": None}


def undelivered_clause(outbox):
    """The SQL of `_undelivered_when` over the outbox model - what a list of 「미전달」 rows asks."""
    from sqlalchemy import and_

    return and_(*[getattr(outbox, column).is_(None) if want is None
                  else getattr(outbox, column) == want
                  for column, want in _undelivered_when().items()])


#: 🔴 THE UNIT OF FAILURE IS THE ROW THAT STILL FAILS (총괄 e573a6edf ① ⑥). The worker marks a
#: grouped row it split FAILED with this key, but that row's rows are back in the queue as its
#: children, and they are what fail or pass. Counting the parent too counted one edit twice
#: (box 2026-09-25: 51 of 84 FAILED rows were split parents), and left it FAILED with no way
#: out - retry and re-split both refuse it, and its children's success never moved it.
SPLIT_INTO_KEY = "reexpanded_into"


def counts_as_failure(payload) -> bool:
    """A FAILED row that is a failure of its own - not a grouped row split into children."""
    return ((payload or {}).get("error_log") or {}).get(SPLIT_INTO_KEY) is None


def failure_clause(outbox):
    """SQL twin of `counts_as_failure`, with the status: FAILED and not split. Every reader
    that counts or lists failures passes here - the failed list, its summary, the retry."""
    from sqlalchemy import and_
    return and_(outbox.status == "FAILED",
                outbox.payload[("error_log", SPLIT_INTO_KEY)].as_string().is_(None))


def broadcast_state_of(processed_chain, status, broadcast_at):
    """통지 축. 「미전달」의 술어는 `idx_outbox_undelivered` «그대로»다 — 스윕이 집는 집합과
    화면이 말하는 집합이 갈리면 운영자가 「왜 안 없어지나」를 묻게 된다.
    """
    if broadcast_at is not None:
        return BROADCAST_STATE_DELIVERED
    row = {"processed_chain": bool(processed_chain), "status": status, "broadcast_at": None}
    if all(row[column] == want for column, want in _undelivered_when().items()):
        return BROADCAST_STATE_UNDELIVERED
    return BROADCAST_STATE_NOT_APPLICABLE

#: 「이 목록이 «잘렸다»」의 정본 모양 — 축마다 하나. 걷기 응답이 이미 그 모양이다
#: (`ledger_subgraph` 의 `truncated: {depth, nodes, edges, …}`), 그래서 새 모양이 아니다.
#: 🔴 「잘렸다」와 「버렸다」는 «다른 사실»이다. 앞은 운영자에게 「상한을 올려라」이고 뒤는
#:    「선언을 고쳐라」다. 그래서 `columns_omitted`(버림)와 `python_default_omitted`(드리프트
#:    라벨)는 이 안으로 «안 접힌다» — 접으면 운영자의 다음 행동이 사라진다.
#: ⚠️ `omitted` 가 `None` 이면 「잘렸는데 «몇 개인지 모른다»」다. 0 이 아니다 — 예산 비트만
#:    아는 자리가 실재한다(`chain_replay` 의 보고 예산).
def truncated_note(cut, omitted=None, reason=None):
    return {
        "cut": bool(cut),
        "omitted": (int(omitted) if omitted is not None else None),
        "reason": (str(reason) if (reason and cut) else None),
    }


#: 「얼마나 갔나」의 이벤트 이름 — 파일 인제션이 오래 쓰던 그것이다. 소급 실행도 «같은»
#: 이름으로 말한다: 운영자에게 「진행」은 하나이고, 이름이 둘이면 화면도 독자가 둘이 된다.
EVENT_INGESTION_PROGRESS = "file_ingestion_progress"

#: 진행이 «끝났다**. 완료든 취소든 이 이름 하나다 — 끝난 이유는 `status` 가 말한다.
PROGRESS_STATUS_RUNNING = "PROCESSING"
#: A collector's `last_status` in the scheduler's status file while it runs - written by the
#: scheduler, read by `runtime.running.collector_is_running`. One spelling for both ends.
COLLECTOR_STATUS_RUNNING = "RUNNING"
PROGRESS_STATUS_DONE = "FINISHED"
PROGRESS_STATUS_CANCELLED = "CANCELLED"


def progress_event(status, progress=None, processed_rows=None, total_rows=None,
                   **subject):
    """진행 봉투 — 짓는 자리 «하나**.

    🔴 [S-37] 종전 이 dict 는 `run_watcher.trigger_ws_progress` 가 «손으로» 지었고
       이벤트 이름을 그 자리에 리터럴로 적었다. 소급 러너가 같은 사실을 말하기 시작하는
       순간 그 봉투가 «둘**이 되고, 둘은 갈라져도 오류를 안 낸다 — 한쪽만 키를 하나 더
       실으면 화면은 그 발신자에 대해서만 조용히 덜 안다.

    `subject` 는 「무엇의 진행인가」다: 인제션은 `table_name`·`filename`, 소급은
    `run_id`·`op`. 키 «순서**가 인제션의 오늘 봉투와 같도록 subject 를 앞에 편다 —
    이 라운드의 ㉣ 가 「인제션 이벤트 바이트 동일」이기 때문이다.

    ⚠️ `progress`/`processed_rows`/`total_rows` 는 `None` 을 «그대로** 싣는다. 0 이 아니다:
       0 은 「하나도 안 했다」이고 None 은 「모른다」이며, 총계는 실제로 모를 수 있다.
    """
    return {"event": EVENT_INGESTION_PROGRESS, **subject,
            "progress": progress, "processed_rows": processed_rows,
            "total_rows": total_rows, "status": status}


#: 「성공했는데 «느렸다»」의 정본 — 문장 «하나», 자세 «하나».
#: 🔴 정의는 «시계»다: 「측정한 비용이 «선언된 예산»을 넘었다」. 상한에 닿은 사실은 이것이
#:    «아니다» — 상한에 닿고도 «빠른» 답이 있고(상한이 그래서 있다), 상한에 «안» 닿고
#:    느린 답이 있다(DB 가 느린 날 — 이 계기가 잡으려는 «바로 그» 경우). 그리고 「잘렸다」는
#:    이미 `truncated` 가 말한다 — 그것을 「느리다」라 부르면 한 사실에 철자가 둘이 된다.
def slow_sentence(elapsed_ms, warn_ms) -> str:
    """예산을 넘은 «성공»의 비용을 말한다. 사유·조언은 부르는 쪽이 «뒤에» 붙인다."""
    return "응답이 %sms 걸렸습니다 (예산 %sms)" % (int(elapsed_ms), int(warn_ms))


def slow_warn_ms(declared, where):
    """선언된 예산 -> 양의 정수, 또는 `None` = 「이 경로는 «재지 않는다»」.

    🔴 부재는 «세 상태의 첫째»다. 선언이 없으면 응답에 `slow_reason` 키가 «없다» —
       `None` 이 아니다. `None` 은 「재 봤는데 안 느리다」는 «주장»이고, 부재는 「안 쟀다」다.
    ⚠️ 0 · 음수 · 문자열 · 불리언은 «경고 후 무시»한다(= 선언 없음). 0 은 「모든 답이 느리다」
       이고, 모든 응답에 붙는 사유는 신호가 아니다 — 정본이 그 이유로 0 을 거른다.
    """
    if declared is None:
        return None
    if isinstance(declared, bool) or not isinstance(declared, int) or declared <= 0:
        logger.warning("[Slow] '%s' slow_warn_ms must be a positive integer (got %r); "
                       "not measuring.", where, declared)
        return None
    return declared


OUTBOX_OWNER_SCHEDULER = "scheduler"
OUTBOX_OWNER_CHAIN = "chain"
OUTBOX_OWNER_UNKNOWN = "unknown"


def outbox_owner(event_type, op=None, undelivered=False):
    """Which daemon empties a waiting row of this type - or that nobody has established it.

    🔴 `unknown` IS A REAL ANSWER AND MUST NOT BE FOLDED INTO `chain`. An unlisted type is
    one nobody has traced to a consumer, and "assume chain" reproduces exactly the
    misreading this split exists to end. `SYSTEM_RELOAD` is deliberately unlisted: the
    chain worker marks the LATEST one on a throttled branch of its own, so its fate
    depends on which row it is rather than on its type, and that is not a per-type answer.

    🔴 `op` 는 «한 타입이 주인 둘을 덮을 때»만 쓴다 — 지금은 `RETROACTIVE_RUN` 하나다.
       ⚠️ 바로 위 `SYSTEM_RELOAD` 와 «다른 경우»다. 저쪽은 운명이 「여럿 중 어느 행이냐」에
          달려 있어 «행을 봐도» 타입이 답을 못 준다(그래서 안 실렸다). 이쪽은 행이 «선언된
          칸»(op)을 들고 다녀서 행마다 답이 난다 — 못 세는 것이 아니라 «묻는 자리가 있다».
       op 를 «안 주면» 타입의 답이 그대로 나온다. 행을 못 가진 호출자
       (`/admin/chain/queue` 의 타입별 집계 둘)가 답을 «바꾸지» 않게 하기 위해서다.

    🔴 `undelivered` 는 «단계»다 (총괄 0f2825324 ㄴ). 돌았고 통지만 남은 행은 타입과 무관하게
       체인 워커가 뺀다 — `broadcast_at` 을 찍는 곳은 체인 워커뿐이다(그룹 뒤 · 미전달 스윕).
       `BROADCAST_RECOVERY` 는 태어날 때부터 이 단계다. 타입별 집계 둘은 `processed_chain =
       false` 만 세서 이 단계를 안 본다 — 그래서 안 넘긴다.
    """
    if undelivered:
        return OUTBOX_OWNER_CHAIN
    if event_type == EVENT_RETROACTIVE_RUN and op in CHAIN_OWNED_RETROACTIVE_OPS:
        return OUTBOX_OWNER_CHAIN
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


#: 「이 사건은 규칙 X «만» 원한다」 — 리플레이가 넣은 행이 드는 키. 없으면 «제한 없음»이고
#: 그것이 보통 사건이다. `CHAIN_DEPTH_KEY` 와 «같은 부류»다: 사건이 들고 다니는 값이고,
#: 부재가 0 이나 빈 문자열이 아니라 «다른 상태»다.
#:
#: 🔴 따라가는 범위가 둘로 갈린다 — 이 구분이 이 키의 전부다.
#:    확장 자식(`outbox_expand`)  같은 사건이 «모양만» 바뀐 것 -> «가져간다»
#:    체인이 낳은 자식            규칙 X 가 표 B 에 써서 난 «새» 사건 -> «버린다»
#:    버리지 않으면 X 가 B 를 안 보므로 리플레이가 한 홉만 돌고 «조용히» 끝난다.
ONLY_RULE_KEY = "only_rule"


#: [CHANNEL] WHO CAUSED A WRITE, apart from the layer it wrote under (총괄 5676b8bc6 ⓪).
#: `source_name` on the envelope is the item's LAYER on the batch door, so a chain write whose
#: layer is `enrichment_auto_confirm` read as 「not the chain」 and skipped every opt-in -
#: 판정 425's one variable carrying two facts (S-280). ABSENT = no door said (an event queued
#: before the key existed, or a writer that sets none).
CHANNEL_KEY = "channel"
CHANNEL_CHAIN = "chain"
CHANNEL_API = "api"
CHANNEL_FILE = "file"
CHANNEL_RETROACTIVE = "retroactive"
#: What a retroactive run writes wakes NO rule, opt-in or not (소유자 09-26 「그냥 뭐든 큰
#: 소급으로 한 거 체인 연쇄 안 되게 하는 거 해」, 총괄 c2995cdd8) - the run's downstream is run
#: by running it too. A replay's own trigger events carry no channel: they wake their rule.
#: [CASCADE] The one exception: a replay run with `cascade` - the grid's click replay - writes
#: with this key, and its writes wake the opted-in rules the way the chain's do (소유자
#: 「클릭 리플레이는 연쇄 도는 거 맞지?」, 총괄 146b208cb). Absent = no cascade.
CASCADE_KEY = "cascade"
#: [REPLAY] A replay's trigger event says so - written by the replay's staging seat alone. What
#: the group it wakes writes is the replay's write (retroactive). Its own key, not `only_rule`:
#: that one is a restriction, and reading it as 「a replay staged this」 would make any future
#: door that narrows to one rule silently retroactive.
REPLAY_KEY = "replay"
#: [WRITTEN-BY] The declarations whose rules wrote what this event names - stamped by the chain's
#: two write seats (a rule's own write in `rule_run.chain_envelope`, the proposals' write in
#: `apply_chain_writes`). A declaration is not woken by its own writes (소유자 09-28, 총괄
#: ebefd20e8). Absent = a door that is not the chain's, or an event queued before the key.
WRITTEN_BY_KEY = "written_by"


def channel_of(payload):
    """The channel an event says it came through, or `None` when it says none."""
    if not isinstance(payload, dict):
        return None
    value = payload.get(CHANNEL_KEY)
    return value if isinstance(value, str) and value else None


def replay_of(payload) -> bool:
    """Was this event staged by a replay run to wake its rule?"""
    return isinstance(payload, dict) and payload.get(REPLAY_KEY) is True


def cascade_of(payload) -> bool:
    """Did the replay that caused this event ask to cascade?"""
    return isinstance(payload, dict) and payload.get(CASCADE_KEY) is True


def written_by_of(payload) -> frozenset:
    """The declarations that wrote what this event names - empty when it does not say."""
    value = payload.get(WRITTEN_BY_KEY) if isinstance(payload, dict) else None
    return frozenset(str(v) for v in value if v) if isinstance(value, list) else frozenset()


def only_rule_of(payload):
    """이 사건이 «한 규칙만» 원하나 — 규칙 이름, 아니면 `None`.

    ⚠️ `chain_depth_of` 와 같은 모양으로 읽는다: 키가 없으면 `None`(제한 없음),
       있으면 그 값. 빈 문자열은 «제한이 아니다» — 이름이 아니니까.
    """
    if not isinstance(payload, dict):
        return None
    value = payload.get(ONLY_RULE_KEY)
    if not isinstance(value, str) or not value.strip():
        return None
    return value


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


#: 🔴 [S-279, 판정 431] WHAT THE AUDIT WRITES WHEN THE CALLER DID NOT SAY WHO. It was
#: `"system"`, as a DEFAULT ARGUMENT on the delete functions, which is not an absence - it is a
#: false author: the history said 「system 이 했다」 about a deletion a person asked for. An
#: unnamed caller is a fact and this is its word; 「모른다」를 적어야 하면 그 낱말을 적는다.
#: ⚠️ It lives here rather than in `crud` because the same word has to be recognisable to the
#: client and to anyone reading the history across processes - the reason every other
#: cross-process constant in this module is in this module.
AUTHOR_NOT_STATED = "unknown"


#: The `batch_row_delete` event name, and the ONE place its payload is built.
EVENT_BATCH_ROW_DELETE = "batch_row_delete"


def row_delete_message(table_name, row_ids, *, transaction_id=None,
                       updated_by=None, created_logs=None):
    """The `batch_row_delete` payload, built in one place.

    🔴 SIX SENDERS WERE EACH WRITING THIS DICT BY HAND, and three of its six keys were carried
    by exactly ONE of them (measured 2026-09-16 off the AST):

        chain/ingestion_worker.py:1912   event, row_ids, table_name, transaction_id
        main.py:2542                     event, row_ids, table_name
        main.py:2595                     event, row_ids, table_name, updated_by, created_logs
        main.py:3585 · :3936 · :4009     event, row_ids, table_name

    That is the same picture `batch_refresh_message`'s own docstring records for its nine, and
    the same consequence: the client reads `table_name` as a guard and the rest of the body
    loosely, so a sender that dropped a key produced no error and no visible change.

    ⛔ THE PAYLOAD IS UNCHANGED - NOT ONE KEY ADDED OR REMOVED, per sender. The optional three
    are omitted when not given, so each of the six still produces exactly the object it
    produced before. Making the six agree on WHICH keys they send is a boundary-contract
    decision and a different change; this one gives them one place to disagree in.
    """
    message = {
        "event": EVENT_BATCH_ROW_DELETE,
        "table_name": table_name,
        "row_ids": row_ids,
    }
    # `is not None` for the same reason the refresh builder gives: an empty list and a zero are
    # things a sender meant to say, and dropping them makes 「말 안 함」 look like 「없음」.
    if transaction_id is not None:
        message["transaction_id"] = transaction_id
    if updated_by is not None:
        message["updated_by"] = updated_by
    if created_logs is not None:
        message["created_logs"] = created_logs
    return message


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
    `truncated`, one adds the audit trio. Unifying the SHAPES is a different
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
    # 🔴 [S-279, 판정 427] THE TRUNCATION RULE IS THIS FUNCTION'S, because it was FIVE
    # senders' and they all had it wrong the same way: `if created_logs and
    # len(created_logs) <= 5000: msg["created_logs"] = created_logs` - over the limit the list
    # was dropped WHOLE and nothing said so. The client's contract (websocket.js) is
    # 「absent is not complete」: with no `total_log_count` it cannot compare, so it neither
    # appends nor reloads and the timeline silently falls behind. The 5,000 dates to
    # 2026-06-02, before that contract existed.
    #
    # 🔴 [판정 430] AND THE TOTAL IS THE CALLER'S TO SAY - THIS FUNCTION DOES NOT GUESS IT.
    # It did for one commit (`344d7464`), and that commit's own two callers dropped the
    # argument they were built to carry, so the derivation filled in `len(sample)` and put a
    # FALSE number on the wire. That is worse than the absence it replaced: the client's
    # contract reads a missing total as 「말 안 함」 and does nothing, but `total=500` beside
    # 500 rows reads as 「this is all of it」. A caller handing over a list without saying how
    # many there were cannot be told apart from one that forgot - so it is refused by name
    # rather than guessed at. 「조용한 불가 0」.
    #
    # ⚠️ A SENDER WITH NO LIST IS UNTOUCHED: both cells stay None and this branch is not
    # entered, which is the seven senders that have nothing to report.
    if created_logs is not None:
        if total_log_count is None:
            raise ValueError(
                "batch_refresh_message was handed created_logs (%d) with no total_log_count. "
                "The list may be a sample - `created_logs` is cut at %d - so the count before "
                "cutting is the only thing that tells a sample from the whole set, and this "
                "function must not invent it. Pass total_log_count=len(created_logs) if the "
                "list IS the whole set."
                % (len(created_logs), MAX_NOTIFY_CREATED_LOGS))
        message["created_logs"] = created_logs[:MAX_NOTIFY_CREATED_LOGS]
    if total_log_count is not None:
        message["total_log_count"] = total_log_count
    if deleted_row_ids_omitted is not None:
        # 정본 — 축 이름은 그 목록의 이름이다. 인자 이름은 «발신자의 말»이라 그대로 둔다.
        message["truncated"] = {"deleted_row_ids": truncated_note(
            int(deleted_row_ids_omitted) > 0, deleted_row_ids_omitted,
            "deleted ids beyond BROADCAST_ITEM_LIMIT")}
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
#: the safe direction needs no edit.
#:
#: ⚰️ [S-82, 2026-09-09] THIS USED TO ADD "the human/correction path must stay here:
#: a correction that reaches the DB but not the screen stops the correction loop".
#: MEASURED: the correction loop does not run through this table. The product door
#: broadcasts from `crud.apply_batch_updates`' own return value, and the recovery
#: sweep fires a table-level refresh keyed on `table_name`; the only consumer that
#: reads a payload's COLUMNS is the chain worker, which expands first. That sentence
#: was holding a door shut for a reason the door did not have.
OUTBOX_MODE_PER_ROW = "per_row"

#: Collapsed events - one row per (table, event_type) per flush, naming row_ids.
#: Opted into explicitly by the three write paths that carry volume: ingestion
#: (`directory_watcher`), the chain worker, and the product door
#: (`main.apply_batch_updates_endpoint`, S-82). NOT inferred from `request_source`
#: (that is a FILENAME on the ingestion path, not a channel) and NOT inferred from
#: row count - inference is how a FOURTH caller would collapse without anyone
#: having decided that it should.
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

    🔴 문장은 «안 짓는다» (총괄 69aad666e). SUCCESS / 그 밖 두 갈래의 한국어 문장이 SKIPPED 를
       「실패」로 부르게 했고, 그래서 워처가 건너뜀을 SUCCESS 로 보냈다. 이제 상태를 그대로 나르고,
       토스트 · 카드의 문장은 화면의 상태 판정 한 자리(retry_verdict)가 영어로 짓는다.
    """
    reason = str(error_msg) if error_msg else None
    msg = {
        "event": EVENT_FILE_INGESTION_COMPLETED,
        "table_name": table_name,
        "filename": filename,
        "status": status,
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
