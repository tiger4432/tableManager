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

# [C-5] 인제션/체인 완료 통지에 동봉하는 감사 로그(created_logs) 상한.
# 웹서버(main.py /internal/events/*)와 audit_cache는 어차피 트랜잭션당 500건만 유지하므로,
# 발신 측이 전량(수만~수십만 dict, 직렬화 시 수십 MB JSON)을 메모리 누적·HTTP POST하는 것은
# 순수 낭비이자 웹서버 이벤트 루프 동결(대형 json.loads / pydantic 검증의 GIL 점유) 요인이다.
# 이벤트 필드 형태(created_logs: list)는 그대로 유지하고 항목 수만 제한하며(경계 계약 불변),
# 실제 총 로그 건수는 total_log_count 필드로 별도 전달한다(순수 추가 필드).
MAX_NOTIFY_CREATED_LOGS = 500

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
