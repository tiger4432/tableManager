import asyncio
import json
import os
import logging
import importlib
import inspect
import uuid
import select
import threading
import time
from collections import defaultdict

from sqlalchemy import type_coerce, text
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB

# Setup Unified Logger
from utils.logger import get_process_logger
from utils.payload_helper import get_payload_dict
from utils import heartbeat
# [H4] Module-level, and deliberately NOT a lazy import of the web application
# module. That lazy import sat inside the notification try/except; importing
# `main` runs the #13 boot fail-fast, so a config that broke while the system was
# running made this worker COMMIT its rows and then silently drop the WebSocket
# notification, with the log line blaming "Failed to build chained update
# notification". Nothing in this worker may reach into `main`.
from utils.time_format import to_local_str

# [C-5 확장] 통지 동봉 created_logs 상한 — 워처(directory_watcher)와 공유하는 공용 상수.
from event_constants import MAX_NOTIFY_CREATED_LOGS

# [M3] Auto-registration of wafer_map_metadata for chain-ingested maps — shared
# with the file watcher (absent-only; knob `auto_register_map_meta`).
import map_meta_registrar

logger = get_process_logger("Chain", "chain_worker.log")

class OutboxListener:
    """[Latency Fix #4] 상시 유지되는 LISTEN 전용 raw 커넥션.

    기존 `blocking_wait`은 빈 폴링 이후 대기할 때마다 **새 커넥션으로 LISTEN을 재등록**했다.
    빈 폴링 시점과 LISTEN 등록 사이에 발행된 NOTIFY는 유실되어 최대 timeout(2초)만큼
    tail latency가 발생했다(LISTEN-after-check 레이스).

    개선: 워커 시작 시 LISTEN을 **1회만** 등록하고 커넥션을 재사용한다. LISTEN이 항상
    폴링보다 먼저 등록되어 있으므로, 폴링 이후 발행된 NOTIFY는 커넥션 소켓에 버퍼링되어
    다음 `wait()`에서 즉시 감지된다(재폴링 유도). 등록 전 발행분을 놓치지 않도록 대기 진입
    직후 버퍼된 통지를 먼저 소비(drain)한다.

    SYSTEM_RELOAD 통지도 같은 채널(`outbox_event`)을 쓰므로 그대로 공존한다(깨우기만 하고
    실제 판정은 루프 상단의 SYSTEM_RELOAD 조회가 담당).
    """

    def __init__(self, db_session_factory, channel="outbox_event"):
        self._factory = db_session_factory
        self._channel = channel
        self._connection = None  # 상시 유지되는 raw DBAPI 커넥션(psycopg2)

    def _ensure_connection(self):
        """LISTEN 커넥션이 없으면(최초/재생성) 생성하고 LISTEN을 1회 등록한다."""
        if self._connection is not None:
            return
        db = self._factory()
        try:
            engine = db.bind or db.get_bind()
            connection = engine.raw_connection()
            # autocommit 모드로 변경하여 LISTEN 명령이 즉시 반영되게 함
            connection.set_isolation_level(0)
            cursor = connection.cursor()
            cursor.execute(f"LISTEN {self._channel};")
            cursor.close()
            self._connection = connection
        finally:
            # 세션 래퍼만 닫고, 체크아웃한 raw 커넥션은 LISTEN 유지를 위해 계속 보유한다.
            db.close()

    def _reset_connection(self):
        """끊긴/오류 커넥션을 안전하게 폐기한다(리소스 누수 금지)."""
        conn = self._connection
        self._connection = None
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    def _wait_blocking(self, timeout):
        try:
            self._ensure_connection()
            connection = self._connection

            # 등록 전/폴링 이후 발행되어 소켓에 이미 버퍼된 통지를 먼저 소비 → 즉시 재폴링.
            connection.poll()
            if connection.notifies:
                while connection.notifies:
                    connection.notifies.pop()
                return True

            # select로 소켓에 데이터가 들어올 때까지 대기 (CPU 부하 0%)
            r, w, x = select.select([connection], [], [], timeout)
            if r:
                connection.poll()
                while connection.notifies:
                    connection.notifies.pop()
                return True
            return False
        except Exception as e:
            # 커넥션 끊김/예외 시 안전 재생성(다음 wait에서 새 LISTEN 커넥션 확보).
            logger.error(f"PostgreSQL LISTEN/NOTIFY socket wait failed, resetting listener connection: {e}")
            self._reset_connection()
            time.sleep(1.0)
            return False

    async def wait(self, timeout=30.0):
        """blocking select를 스레드로 오프로딩하여 asyncio 루프를 막지 않는다."""
        return await asyncio.to_thread(self._wait_blocking, timeout)

    def close(self):
        self._reset_connection()

import paths  # single override point (ASSY_DATA_ROOT)
RULES_PATH = paths.config_path("chain_rules.json")

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8080")

# [Warmup #3] 스레드별 requests.Session 저장소 (keep-alive 커넥션 재사용).
_http_local = threading.local()

def _get_http_session():
    """[Warmup #3] 호출 스레드 전용 requests.Session을 반환한다(keep-alive 재사용).

    매 호출 `requests.post`는 매번 새 TCP 커넥션을 수립해 첫 통지에 커넥션 비용이 붙는다.
    requests.Session은 스레드 안전이 보장되지 않으므로(쿠키 저장소 등 내부 상태 변이 레이스),
    threading.local로 스레드당 1개 세션을 유지한다. post_event_async는 asyncio.to_thread(기본
    ThreadPoolExecutor)로 실행되고 워커의 통지는 단일 태스크에서 순차 await되므로 실제로는
    유휴 스레드 1개가 재사용된다 → 스레드당 세션이어도 keep-alive 재사용 이득이 유지된다.
    """
    sess = getattr(_http_local, "session", None)
    if sess is None:
        import requests
        sess = requests.Session()
        _http_local.session = sess
    return sess

async def post_event_async(endpoint: str, payload: dict) -> bool:
    """통지를 fire-and-forget으로 전송하고 전달 확정 여부(bool)를 반환한다.

    [Reliability F1] 반환값은 broadcast_at 스탬프 판정에만 쓰인다(전달 확정 시 True).
    데이터 처리 성공/재시도 판정에는 절대 반영하지 않는다(통지 실패 ≠ 처리 실패).
    """
    url = f"{API_BASE_URL}{endpoint}"
    def do_post():
        try:
            # [Latency Fix #2] 통지는 커밋 이후 fire-and-forget으로 수행되므로
            # 워커 폴링을 오래 붙잡지 않도록 타임아웃을 짧게(3초) 유지한다.
            # [Warmup #3] 스레드-로컬 Session으로 keep-alive 재사용(매 호출 커넥션 수립 제거).
            # [B5] /internal/events/* carries the admin secret; inherited from
            # the launcher's environment. 401 here = worker started without it.
            import admin_auth
            res = _get_http_session().post(
                url, json=payload, timeout=3,
                headers=admin_auth.internal_event_headers())
            if not res.ok:
                logger.error(f"[Chain Worker] API notification failed: {url} -> {res.status_code}")
                return False
            return True
        except Exception as e:
            logger.error(f"[Chain Worker] Failed to send API notification: {e}")
            return False
    return await asyncio.to_thread(do_post)


# [C-3] Outbox 보관 정책 (사용자 확정: 7일)
#   처리 완료(processed_chain=true)된 outbox 행을 7일 경과 후 주기적으로 삭제한다.
#   보존 기준은 created_at — 정상 운영에서 이벤트는 생성 후 수 초 내 처리되므로 생성시점 ≈ 처리시점이며,
#   created_at은 부분 인덱스(idx_outbox_purge: created_at WHERE processed_chain=true)로 O(대상건수) 탐색이
#   가능하다(1000만 행 안전). 미처리(processed_chain=false) 행은 나이와 무관하게 절대 삭제하지 않는다.
OUTBOX_RETENTION_DAYS = 7
OUTBOX_PURGE_INTERVAL = 3600.0   # 저빈도 주기(1시간) — 시간당 삭제량은 시간당 유입량 수준의 소량
OUTBOX_PURGE_CHUNK = 1000        # 1000행 청킹 (헌장 규칙: 대량 쓰기는 배치)
OUTBOX_PURGE_MAX_CHUNKS = 50     # 사이클당 상한(최대 5만 행) — 초과분은 다음 사이클로 이월


def purge_expired_outbox_sync(db_session_factory, retention_days=OUTBOX_RETENTION_DAYS,
                              chunk_size=OUTBOX_PURGE_CHUNK, max_chunks=OUTBOX_PURGE_MAX_CHUNKS):
    """[C-3] 보관기간 경과한 처리 완료 outbox 행을 청크 단위로 삭제한다(동기 — 스레드에서 실행).

    - 별도의 짧은 세션 사용(워커 메인 세션·스윕 세션과 격리, 청크마다 commit → 락 보유시간 최소화).
    - 청크 삭제 실패는 로깅 후 다음 사이클 재시도(멱등 — 남은 행은 다시 매치된다).
    - 반환: 삭제된 총 행 수.
    """
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import delete, select
    from database.models import DatabaseOutbox

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    total_deleted = 0
    db = db_session_factory()
    try:
        for _ in range(max_chunks):
            subq = select(DatabaseOutbox.id).where(
                DatabaseOutbox.processed_chain == True,
                DatabaseOutbox.created_at < cutoff,
            ).limit(chunk_size)
            res = db.execute(delete(DatabaseOutbox).where(DatabaseOutbox.id.in_(subq)))
            db.commit()
            deleted = res.rowcount or 0
            total_deleted += deleted
            if deleted < chunk_size:
                break
        if total_deleted:
            logger.info(
                f"[Outbox Purge] Deleted {total_deleted} processed outbox row(s) "
                f"older than {retention_days} day(s)."
            )
    except Exception as e:
        db.rollback()
        logger.error(f"[Outbox Purge] Failed (will retry next cycle): {e}")
    finally:
        db.close()
    return total_deleted


def _stamp_broadcast_at_sync(db_session_factory, event_ids):
    """[Reliability F1] 전달 확정된 그룹의 outbox 행에 broadcast_at을 찍는다.

    별도의 짧은 세션으로 즉시 UPDATE·commit·close 한다(워커 메인 세션과 격리, 커넥션 풀 즉시 반납).
    실패는 로깅만 — 스탬프가 실패해 broadcast_at이 NULL로 남아도 다음 스윕이 회수하므로 안전(멱등).
    """
    if not event_ids:
        return
    stamp_db = db_session_factory()
    try:
        from database.models import DatabaseOutbox
        stamp_db.query(DatabaseOutbox).filter(
            DatabaseOutbox.id.in_(list(event_ids))
        ).update({DatabaseOutbox.broadcast_at: func.now()}, synchronize_session=False)
        stamp_db.commit()
    except Exception as e:
        stamp_db.rollback()
        logger.error(f"[Chain Worker] Failed to stamp broadcast_at (rows will be re-swept): {e}")
    finally:
        stamp_db.close()

async def _dispatch_broadcasts(pending_broadcasts, db_session_factory):
    """[Reliability F1/F2] 한 배치의 그룹별 브로드캐스트를 group_order 순서대로 **단일 순차** 전송한다.

    [Latency SLO] 이 함수는 배치 커밋 직후 **인라인 await**로 호출된다(배경 태스크 아님).
      기존 `asyncio.create_task` 예약 방식은 폴링 루프의 동기 DB 쿼리에 이벤트 루프가 블로킹되는 동안
      태스크가 기아(starvation) 상태로 못 나가 통지가 수 초~수십 초 지연되고, 그 사이 broadcast_at NULL을
      스윕이 유실로 오인해 전체 리프레시를 오발사했다. commit은 이미 끝난 뒤이므로 인라인 전송이
      데이터 경로를 지연시키지 않으며(#2 commit-before-broadcast 이득 유지), 통지 실패는 여전히 삼킨다.

    - F2(순서 보존): pending_broadcasts는 (event_ids, messages, timing) 튜플의 group_order 순서 리스트다.
      그룹을 순서대로, 그룹 내 메시지도 순서대로(삭제 → upsert/refresh) 전송하므로 동일 target에 대한
      그룹 간 도착 역전이 발생하지 않는다.
    - F1(전달 확정): 그룹의 **모든** 메시지가 성공 전송되면 해당 그룹 이벤트에 broadcast_at을 스탬프한다.
      일부라도 실패하면 broadcast_at을 NULL로 남겨 주기 스윕이 감지·재발사한다(eventual delivery).
    - 계측: timing(dict)이 있으면 tx당 1줄 [Latency] INFO 로그로 구간별 ms를 남긴다(SLO 검증용).
    실패는 로깅만 하고 삼킨다(처리 성공/재시도에 영향 없음).
    """
    for event_ids, messages, timing in pending_broadcasts:
        all_ok = True
        for m in messages:
            try:
                ok = await post_event_async("/internal/events/broadcast", m)
                if not ok:
                    all_ok = False
            except Exception as e:
                all_ok = False
                logger.error(f"[Chain Worker] Broadcast dispatch failed (ignored): {e}")
        # 그룹의 모든 메시지가 전달 확정된 경우에만 broadcast_at 스탬프(전달 마킹).
        if all_ok and event_ids:
            try:
                await asyncio.to_thread(_stamp_broadcast_at_sync, db_session_factory, event_ids)
            except Exception as e:
                logger.error(f"[Chain Worker] broadcast_at stamp offload failed (rows will be re-swept): {e}")
        # [Latency SLO 계측] tx당 1줄: wake(감지→매퍼시작) mapper(매퍼+updates) commit notify(커밋→POST응답) total.
        if timing:
            t_notify_done = time.monotonic()
            notify_ms = (t_notify_done - timing["commit_done_ts"]) * 1000.0
            total_ms = (t_notify_done - timing["wake_ts"]) * 1000.0
            logger.info(
                f"[Latency] tx={timing['tx']} wake={timing['wake_ms']:.0f}ms "
                f"mapper={timing['mapper_ms']:.0f}ms commit={timing['commit_ms']:.0f}ms "
                f"notify={notify_ms:.0f}ms total={total_ms:.0f}ms ok={all_ok}"
            )

def load_chain_rules():
    rules = []
    if not os.path.exists(RULES_PATH):
        logger.warning(f"Chain rules configuration file not found at {RULES_PATH}. Using empty rules.")
    else:
        try:
            with open(RULES_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                rules = data.get("rules", [])
        except Exception as e:
            logger.error(f"Failed to load chain rules: {e}")

    # [Enrichment Queue] enrichment_rules.json으로부터 dedup 투영 체인 룰을 자동 파생하여 병합.
    #   파생 룰은 일반 체인 룰과 동일 형태이므로 워커 파이프라인(HOL 가드·SLO 계측·warmup·재시도)을
    #   그대로 탄다. SYSTEM_RELOAD 시 본 함수가 재호출되므로 enrichment 규칙도 무중단 반영된다.
    try:
        from database import crud
        import enrichment_config
        enrich_rules = enrichment_config.load_enrichment_chain_rules(known_tables=crud.TABLE_CONFIG)
        if enrich_rules:
            rules = rules + enrich_rules
            logger.info(
                f"[Enrichment] Synthesized {len(enrich_rules)} dedup chain rule(s) from enrichment_rules.json"
            )
    except Exception as e:
        logger.error(f"[Enrichment] Failed to synthesize enrichment chain rules: {e}")

    return rules

def _mapper_accepts_rule(mapper_func) -> bool:
    """맵퍼 함수가 선택적 `rule` 키워드 인자를 받는지 판정한다(기존 맵퍼 하위호환 유지)."""
    try:
        sig = inspect.signature(mapper_func)
    except (TypeError, ValueError):
        return False
    params = sig.parameters
    if "rule" in params:
        return True
    return any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())

def execute_custom_mapper(module_name: str, function_name: str, db, payload, rule=None):
    """
    Dynamically imports a python mapper module and executes the mapping function.

    rule: 현재 실행 중인 체인 룰 dict. 맵퍼가 `rule` 인자를 선언한 경우에만 전달한다
    (generic 맵퍼가 룰 설정을 참조하는 용도 — 예: enrichment_mapper.map_enrichment_dedup).
    기존 (db, payload) 시그니처 맵퍼는 종전과 완전히 동일하게 호출된다.
    """
    try:
        module = importlib.import_module(module_name)
        mapper_func = getattr(module, function_name)
        if rule is not None and _mapper_accepts_rule(mapper_func):
            return mapper_func(db, payload, rule=rule)
        return mapper_func(db, payload)
    except Exception as e:
        logger.error(f"Error executing custom mapper {module_name}.{function_name}: {e}")
        raise e

def _group_target_tables(events_in_tx, rules):
    """[Latency Fix #5] 이 트랜잭션 그룹이 기록할 target_table 집합을 매퍼 실행 없이 규칙에서 추정한다.

    실패 그룹을 건너뛰되 '동일 target_table을 건드리는 후속 그룹만' 보류(순서 보존)하기 위한 판정용.
    target_table은 매퍼 반환값이 아니라 규칙 설정(rule['target_table'])에서 결정되므로 정적 추정이 정확하다.
    순환 루프 필터(source_name == 'chain_ingestion' 제외)와 트리거 이벤트 타입(CREATE/EDIT)은
    `process_chain_transaction_group`의 판정과 동일하게 맞춘다(체인 생성 이벤트만 있는 그룹은 no-op → 빈 집합).
    """
    trigger_tables = set(
        e.table_name for e in events_in_tx
        if e.event_type in ("CREATE", "EDIT")
        and get_payload_dict(e).get("source_name") != "chain_ingestion"
    )
    if not trigger_tables:
        return set()
    targets = set()
    for r in rules:
        if r.get("enabled", True) and r.get("trigger_table") in trigger_tables:
            tgt = r.get("target_table")
            if tgt:
                targets.add(tgt)
    return targets

async def process_chain_transaction_group(tx_id, events, db, rules):
    # [Latency Fix #2] 커밋 이후 fire-and-forget으로 발사할 브로드캐스트 메시지 큐.
    # 여기에는 이벤트명/페이로드 형식이 그대로(batch_row_*, batch_refresh_required) 담긴다.
    broadcast_messages = []

    # 1. Filter out events already generated by chain_ingestion to prevent circular loops
    valid_events = [e for e in events if get_payload_dict(e).get("source_name") != "chain_ingestion"]
    if not valid_events:
        return True, None, broadcast_messages

    # 2. Map of updates grouped by target table
    # target_table -> list of GeneralUpdateItem dicts
    table_updates = defaultdict(list)
    
    # 3. Evaluate rules for this transaction
    # To support batch rules, we group rules by trigger table to execute them efficiently.
    # First, gather trigger tables present in valid_events
    trigger_tables = set(e.table_name for e in valid_events if e.event_type in ["CREATE", "EDIT"])
    
    for table_name in trigger_tables:
        matched_rules = [r for r in rules if r.get("trigger_table") == table_name and r.get("enabled", True)]
        if not matched_rules:
            continue
            
        for rule in matched_rules:
            target_table = rule.get("target_table")
            module_name = rule.get("mapper_module")
            func_name = rule.get("mapper_function")
            is_batch = rule.get("is_batch", False)
            
            try:
                if is_batch:
                    # Collect all payloads for this trigger table in the current transaction group
                    payloads = [get_payload_dict(e) for e in valid_events if e.table_name == table_name and e.event_type in ["CREATE", "EDIT"]]
                    # Pass the whole list to custom mapper
                    target_payload = execute_custom_mapper(module_name, func_name, db, payloads, rule=rule)
                    if target_payload and isinstance(target_payload, dict) and target_payload.get("updates"):
                        table_updates[target_table].extend(target_payload.get("updates"))
                else:
                    # Single event execution
                    for event in valid_events:
                        if event.table_name == table_name and event.event_type in ["CREATE", "EDIT"]:
                            target_payload = execute_custom_mapper(module_name, func_name, db, get_payload_dict(event), rule=rule)
                            if target_payload and isinstance(target_payload, dict) and target_payload.get("updates"):
                                table_updates[target_table].extend(target_payload.get("updates"))
            except Exception as e:
                import traceback
                error_msg = traceback.format_exc()
                logger.error(f"Failed to execute mapper in tx {tx_id} for rule '{rule.get('name')}': {error_msg}")
                return False, error_msg, []

    # 4. Perform chained batch updates by target table
    if table_updates:
        from database import schemas, crud
        from database.context import request_user, request_transaction_id, request_source
        
        chain_tx_id = f"chain_{tx_id}"
        token_user = request_user.set("chain_worker")
        token_tx = request_transaction_id.set(chain_tx_id)
        token_src = request_source.set("chain_ingestion")
        
        try:
            for target_table, updates_list in table_updates.items():
                batch_data = schemas.GeneralUpdateBatch(
                    updates=updates_list,
                    transaction_id=chain_tx_id,
                    silent=False
                )
                logger.info(f"Executing chained batch updates to '{target_table}' under tx '{chain_tx_id}' (size: {len(updates_list)})")
                
                # Apply updates
                results, changed_cells, created_logs, deleted_row_ids = crud.apply_batch_updates(db, target_table, batch_data)

                # [M3] Absent-only wafer_map_metadata auto-registration for
                # chain-created maps. Uses the VALIDATED batch items (same
                # column names the upsert wrote). One existence check per
                # distinct map key per tx group; a failure here must never fail
                # the (already committed) chain write — log and continue.
                # Recursion-safe: the registrar refuses META_TABLE and the meta
                # table declares no map_key_columns, so meta creation can never
                # re-trigger itself.
                try:
                    meta_collector = map_meta_registrar.MapMetaCollector(target_table)
                    if meta_collector.active:
                        meta_collector.collect(item.updates for item in batch_data.updates)
                        created_meta = meta_collector.flush(db)
                        if created_meta:
                            logger.info(f"[M3] Auto-registered {created_meta} wafer_map_metadata row(s) for chain target '{target_table}'")
                except Exception as meta_err:
                    logger.error(f"[M3] Map-meta auto-registration failed for '{target_table}' (chain write unaffected): {meta_err}")

                # 5. Collect WebSocket broadcast messages (dispatched AFTER commit, fire-and-forget).
                #    이벤트명/페이로드 형식은 절대 변경하지 않고 타이밍만 커밋 이후로 미룬다.
                try:
                    cfg = crud.TABLE_CONFIG.get(target_table, {})
                    col_types = cfg.get("column_types", {})
                    user_cols = [c for c in col_types.keys() if c not in ["created_at", "updated_at"]]

                    msg_items = []
                    for row, is_new in results:
                        c_at_str = to_local_str(row.created_at)
                        u_at_str = to_local_str(row.updated_at)
                        
                        r_data = {}
                        for col in user_cols:
                            val = getattr(row, col)
                            if val is None:
                                val = {"value": None, "is_overwrite": False, "sources": {}, "updated_by": "system"}
                            r_data[col] = val
                        r_data["created_at"] = {"value": c_at_str, "is_overwrite": False, "sources": {}, "updated_by": "system"}
                        r_data["updated_at"] = {"value": u_at_str, "is_overwrite": False, "sources": {}, "updated_by": "system"}
                        
                        msg_items.append({
                            "row_id": row.row_id,
                            "is_new": is_new,
                            "data": r_data,
                            "created_at": c_at_str,
                            "updated_at": u_at_str
                        })
                        
                    user_name = "chain_worker"
                    
                    # Ensure created_logs has clean string timestamps
                    # [C-5 확장] 절단은 직렬화 루프 **앞**에서 수행 — 6.5만 건 dict copy/isoformat 자체가 낭비.
                    # 재기동 스윕 재인제션 등 대형 tx에서 전량(수만 건, ~50MB JSON) 전송 시
                    # 웹서버 이벤트 루프가 동결되던 인시던트(2026-07-25)의 재발 방지.
                    # 실제 총 건수는 total_log_count로 별도 전달(순수 추가 필드, 계약 불변).
                    total_log_count = len(created_logs) if created_logs else 0
                    serialized_logs = []
                    if created_logs:
                        from datetime import datetime
                        for log in created_logs[:MAX_NOTIFY_CREATED_LOGS]:
                            log_copy = dict(log)
                            ts = log_copy.get("timestamp")
                            if ts is not None and isinstance(ts, datetime):
                                log_copy["timestamp"] = ts.isoformat()
                            serialized_logs.append(log_copy)

                    if len(msg_items) > 100:
                        msg = {
                            "event": "batch_refresh_required",
                            "table_name": target_table,
                            "change_count": len(msg_items),
                            "transaction_id": chain_tx_id,
                            "created_logs": serialized_logs,
                            "total_log_count": total_log_count
                        }
                    else:
                        msg = {
                            "event": "batch_row_upsert",
                            "table_name": target_table,
                            "items": msg_items,
                            "updated_by": user_name,
                            "transaction_id": chain_tx_id,
                            "created_logs": serialized_logs,
                            "total_log_count": total_log_count
                        }
                    # 껍데기 행 실시간 제거 이벤트를 먼저(순서 보존) 큐잉한 뒤 upsert/refresh 이벤트를 큐잉
                    if deleted_row_ids:
                        broadcast_messages.append({
                            "event": "batch_row_delete",
                            "table_name": target_table,
                            "row_ids": deleted_row_ids,
                            "transaction_id": chain_tx_id
                        })

                    broadcast_messages.append(msg)
                except Exception as ws_err:
                    # 통지 메시지 구성 실패는 로깅만 하고 그룹 처리(성공/커밋)에는 영향 주지 않는다.
                    # [H4] 다만 **결과를 숨기지 않는다** — 여기서 떨어지면 행은 이미 커밋됐는데
                    # 어떤 클라이언트도 그 사실을 모른다(핵심가치 #3, 실시간 신뢰 전파).
                    # 예외 타입과 스택을 남기지 않으면 이 한 줄이 엉뚱한 원인을 가리킨다.
                    logger.error(
                        f"Failed to build chained update notification for '{target_table}' "
                        f"(tx {chain_tx_id}) - rows are COMMITTED but clients will NOT be "
                        f"notified: [{type(ws_err).__name__}] {ws_err}",
                        exc_info=True,
                    )
                    
        except Exception as e:
            import traceback
            error_msg = traceback.format_exc()
            logger.error(f"Failed executing chained batch update for tx {tx_id}: {error_msg}")
            return False, error_msg, []
        finally:
            request_user.reset(token_user)
            request_transaction_id.reset(token_tx)
            request_source.reset(token_src)

    return True, None, broadcast_messages

def reload_worker_process_cache():
    """체인 워커 프로세스의 동적 모듈 캐시(mappers, pipeline plugins)를 명시적으로 무효화합니다."""
    import sys
    
    # Remove custom mappers from sys.modules cache
    mapper_keys = [k for k in sys.modules.keys() if k.startswith("mappers.")]
    for k in mapper_keys:
        sys.modules.pop(k, None)
        
    # Remove pipeline plugin parsers from sys.modules cache
    plugin_keys = [k for k in sys.modules.keys() if k.startswith("pipeline_plugin_")]
    for k in plugin_keys:
        sys.modules.pop(k, None)
        
    logger.info("[Reload] Chain worker modules cache cleared.")

def warmup_worker(rules, db_session_factory=None):
    """[Warmup] 첫 체인 처리의 콜드 스타트를 기동/리로드 시점으로 앞당긴다.

    실측(2026-07-25): 워커 기동 후 첫 체인만 total≈1.3s(mapper=1125ms notify=172ms), 2번째부터 ≈47ms.
    원인은 ①매퍼 모듈 첫 동적 import ②SQLAlchemy 풀 첫 커넥션 수립 ③requests 첫 import·커넥션.
    SYSTEM_RELOAD가 매퍼 캐시를 비우면(reload_worker_process_cache) 콜드 스타트가 운영 중에도
    재발하므로, 리로드 직후에도 이 함수로 재웜업한다(리로드 시엔 DB 풀이 유지되므로
    db_session_factory=None으로 호출해 DB 프라임은 생략).

    웜업 실패는 치명 아님 — 경고 로깅 후 계속 기동한다(실제 처리 경로에서 재시도됨).
    HTTP는 requests import + Session 준비까지만 수행한다(웹서버가 아직 기동 전일 수 있어
    실제 커넥션 수립은 시도하지 않음 — 첫 통지에서 수립 후 keep-alive로 재사용).
    """
    t0 = time.monotonic()
    # 1) 활성 규칙의 매퍼 모듈 선(先)import — importlib 캐시를 덥힌다(기동 + 리로드 재웜업 공통).
    for rule in rules:
        if not rule.get("enabled", True):
            continue
        module_name = rule.get("mapper_module")
        if not module_name:
            continue
        try:
            importlib.import_module(module_name)
        except Exception as e:
            logger.warning(f"[Warmup] Mapper pre-import failed ({module_name}): {e}")
    t1 = time.monotonic()
    # 2) DB 커넥션 프라임 — 풀 첫 커넥션·다이얼렉트 초기화(기동 시에만).
    if db_session_factory is not None:
        try:
            db = db_session_factory()
            try:
                db.execute(text("SELECT 1"))
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"[Warmup] DB connection prime failed: {e}")
    t2 = time.monotonic()
    # 3) HTTP 클라이언트 준비 — requests 모듈 import(전역 캐시)로 첫 통지의 import 비용 제거.
    try:
        _get_http_session()
    except Exception as e:
        logger.warning(f"[Warmup] HTTP session init failed: {e}")
    t3 = time.monotonic()
    logger.info(
        f"[Warmup] mappers={(t1 - t0) * 1000.0:.0f}ms db={(t2 - t1) * 1000.0:.0f}ms "
        f"total={(t3 - t0) * 1000.0:.0f}ms"
    )

async def process_pending_groups(db, group_order, groups, rules, db_session_factory, batch_wake_ts=None):
    """[Latency Fix #5] 한 배치 안의 트랜잭션 그룹들을 순차 처리한다.

    기존 로직은 한 그룹이 실패하면 `break`로 **배치 전체를 중단**하고 `sleep(1)` 후 다음 배치에서
    처음부터 재시도했다. 실패 그룹이 큐 선두(id asc)에 있으면 3회 재시도 동안 뒤의 정상 이벤트가
    전부 정체되는 head-of-line 블로킹이 발생했다.

    개선: 실패 그룹은 **건너뛰되(break 제거)**, 데이터 유실/중복 없이 미처리 상태로 남겨 다음 배치에서
    재시도한다(rollback → retry_count 증가 → 3회 후 격리 유지). 다만 **순서 의존성 보존**을 위해,
    실패 그룹이 기록하려던 target_table을 건드리는 **후속 그룹만** 이번 배치에서 보류한다(동일 target에
    대해 나중 그룹이 먼저 적용되어 순서가 뒤집히는 것을 방지). 서로 다른 target_table 그룹은 계속 처리된다.

    batch_wake_ts: outbox 이벤트 감지 시각(time.monotonic). [Latency SLO] 계측 로그의 wake 구간 기준점.

    반환: 이번 배치에 실패 그룹이 하나라도 있었는지(failed_any) — 호출부의 백오프 sleep 판단용.
    """
    from datetime import datetime
    failed_any = False
    # 실패 그룹이 점유(보류)한 target_table 집합. 이후 동일 target 그룹은 순서 보존을 위해 이번 배치 보류.
    blocked_targets = set()
    # [Reliability F2] 성공 그룹의 통지를 group_order 순서대로 모아 배치 끝에서 단일 순차 발사.
    #   각 원소: (event_ids, messages, timing). 그룹 간 도착 역전(F2)을 방지한다.
    pending_broadcasts = []

    for tx_id in group_order:
        events_in_tx = groups[tx_id]
        group_targets = _group_target_tables(events_in_tx, rules)

        # 순서 보존 가드: 앞선 실패 그룹과 동일 target을 건드리는 그룹은 이번 배치에서 보류한다.
        # (retry_count를 올리지 않고 processed_chain=False 유지 → 다음 배치에서 blocker 뒤에 재시도)
        if blocked_targets and (group_targets & blocked_targets):
            logger.info(
                f"[HOL Guard] Deferring tx '{tx_id}' this batch: target(s) "
                f"{sorted(group_targets & blocked_targets)} held by an earlier failed group."
            )
            continue

        # Process transaction group atomically
        t_mapper_start = time.monotonic()
        success, error_reason, broadcast_messages = await process_chain_transaction_group(tx_id, events_in_tx, db, rules)

        if success:
            t_mapper_done = time.monotonic()
            has_messages = bool(broadcast_messages)
            # commit 시 expire_on_commit으로 속성이 만료되므로 id를 커밋 전에 캡처(재조회 N+1 방지).
            event_ids = [event.id for event in events_in_tx]
            for event in events_in_tx:
                event.processed_chain = True
                event.status = "SUCCESS"
                # [Reliability F1] 통지할 메시지가 없는 no-op 그룹은 전달할 것이 없으므로 즉시 전달 확정(스윕 제외).
                # 메시지가 있는 그룹은 broadcast_at을 NULL로 두고, 통지 성공 시 _dispatch_broadcasts가 스탬프한다.
                if not has_messages:
                    event.broadcast_at = func.now()
            db.commit()
            t_commit_done = time.monotonic()
            # [Reliability F1/F2] 데이터 처리 성공 + 커밋 이후에만 통지 대상으로 누적한다(발사는 배치 끝 단일 순차).
            # 통지 실패는 이미 커밋된 그룹의 재처리/중복을 유발하지 않는다(재시도는 오직 처리 실패로만 트리거).
            if has_messages:
                # [Latency SLO 계측] wake 기준점이 없으면(테스트/드문 경로) 매퍼 시작 시각으로 대체.
                wake_ref = batch_wake_ts if batch_wake_ts is not None else t_mapper_start
                timing = {
                    "tx": tx_id,
                    "wake_ts": wake_ref,
                    "wake_ms": (t_mapper_start - wake_ref) * 1000.0,
                    "mapper_ms": (t_mapper_done - t_mapper_start) * 1000.0,
                    "commit_ms": (t_commit_done - t_mapper_done) * 1000.0,
                    "commit_done_ts": t_commit_done,
                }
                pending_broadcasts.append((event_ids, broadcast_messages, timing))
        else:
            # 실패 그룹의 매퍼 쓰기는 rollback으로 폐기되어 target에 커밋되지 않는다(유실/중복 없음).
            # 앞선 성공 그룹은 이미 각자 commit되었으므로 rollback 영향 밖이다.
            db.rollback()

            # Increment retry count for all events in the failed transaction group
            failed_permanently_count = 0
            retrying_count = 0
            max_retry_num = 0

            for event in events_in_tx:
                event.retry_count += 1
                max_retry_num = max(max_retry_num, event.retry_count)
                if event.retry_count >= 3:
                    event.status = "FAILED"
                    event.processed_chain = True  # Quarantine from worker queries
                    pay_dict = get_payload_dict(event)
                    payload_copy = dict(pay_dict) if pay_dict else {}
                    payload_copy["error_log"] = {
                        "failed_at": datetime.now().isoformat(),
                        "reason": error_reason or f"Mapper execution failed in tx group {tx_id} after 3 retries."
                    }
                    event.payload = payload_copy
                    failed_permanently_count += 1
                else:
                    event.status = "RETRYING"
                    retrying_count += 1

            db.commit()

            if failed_permanently_count > 0:
                logger.error(f"Transaction {tx_id} permanently failed: {failed_permanently_count} events moved to FAILED status.")
            if retrying_count > 0:
                logger.warning(f"Transaction {tx_id} marked for retry: {retrying_count} events set to RETRYING status ({max_retry_num}/3).")

            failed_any = True
            # [Latency Fix #5] break 제거 — 동일 target_table 그룹만 보류(순서 보존)하고 나머지는 계속 처리.
            blocked_targets |= group_targets

    # [Latency SLO] 배치의 모든 성공 그룹 통지를 group_order 순서대로 **인라인** 발사한다.
    #   배경 태스크(create_task) 예약은 폴링 루프의 동기 구간에 이벤트 루프가 블로킹되는 동안 기아 상태가 되어
    #   통지가 수 초 지연되고 스윕 오발동(전체 리프레시 폭주)을 유발했다. commit은 위에서 이미 완료됐으므로
    #   인라인 await가 데이터 경로를 지연시키지 않는다(F2 순서 보존·F1 스탬프 로직은 _dispatch_broadcasts 내 유지).
    if pending_broadcasts:
        await _dispatch_broadcasts(pending_broadcasts, db_session_factory)

    return failed_any

async def sweep_undelivered_broadcasts(db, rules, db_session_factory):
    """[Reliability F1 안전망] 커밋됐으나 통지 미확정(broadcast_at IS NULL)인 교정 행을 주기적으로 감지해
    영향 target_table에 table-level batch_refresh_required를 발사하고 broadcast_at을 확정한다.

    - eventual delivery: 통지 유실(웹서버 재시작/타임아웃/3s 초과)로 그리드가 영구 stale이 되는 경로를 없앤다.
      broadcast_at IS NULL 마커는 DB에 durable하므로 워커가 재시작돼도 복구된다(#3 신뢰 전파 회복).
    - [Latency SLO] 정상 경로 오발동 제로: 통지·스탬프가 배치 처리와 **같은 반복 안에서 인라인**으로 완료되므로
      (단일 이벤트 루프 순차 실행) 스윕은 "커밋됐지만 아직 발사 안 된" 그룹을 구조적으로 볼 수 없다.
      스윕이 잡는 NULL은 POST 실패/스탬프 실패/커밋 직후 워커 크래시 등 **진짜 유실**뿐이다. → grace 5s 유지.
    - 확장성: 부분 인덱스 idx_outbox_undelivered + LIMIT(500) + grace(created_at < now()-5s)로 1000만행 안전.
      grace는 방금 커밋되어 정상 통지가 in-flight인 행을 제외해 중복 refresh 발사를 억제한다.
    - 경계 계약 불변: 신규 이벤트 없이 기존 batch_refresh_required(table_name, change_count)를 그대로 재사용.
      클라이언트는 table_name으로 가드하고 change_count는 refresh 판정에 쓰지 않는다(websocket.js).
    """
    from database.models import DatabaseOutbox

    stale = db.query(DatabaseOutbox).filter(
        DatabaseOutbox.processed_chain == True,
        DatabaseOutbox.status == "SUCCESS",
        DatabaseOutbox.broadcast_at.is_(None),
        DatabaseOutbox.created_at < func.now() - text("interval '5 seconds'"),
    ).order_by(DatabaseOutbox.id.asc()).limit(500).all()

    if not stale:
        return

    stale_ids = [e.id for e in stale]

    # 미전달 행을 tx 그룹으로 묶어 규칙 정적 추정(_group_target_tables)으로 영향 target_table을 유도한다.
    # (매퍼 재실행 없음 — target_table은 규칙 설정에서 결정되므로 정적 추정이 정확하다.)
    sweep_groups = defaultdict(list)
    for e in stale:
        pay = get_payload_dict(e)
        e._parsed_payload = pay
        tx = pay.get("transaction_id") if isinstance(pay, dict) else None
        if not tx:
            tx = f"single_{e.event_uuid}"
        sweep_groups[tx].append(e)

    affected_targets = set()
    for evs in sweep_groups.values():
        affected_targets |= _group_target_tables(evs, rules)

    if not affected_targets:
        # 어떤 target에도 매핑되지 않는 행(규칙 비활성/트리거 아님 등) → 무한 재스윕 방지 위해 확정만 찍는다.
        db.query(DatabaseOutbox).filter(DatabaseOutbox.id.in_(stale_ids)).update(
            {DatabaseOutbox.broadcast_at: func.now()}, synchronize_session=False)
        db.commit()
        return

    # table당 1건 dedup된 batch_refresh_required 발사(기존 계약 재사용). 전부 성공해야 확정한다.
    all_ok = True
    for tgt in sorted(affected_targets):
        msg = {
            "event": "batch_refresh_required",
            "table_name": tgt,
            "change_count": 0,  # 표준 계약 필드(정보성). 스윕 복구는 테이블 전체 새로고침 신호로 동작.
        }
        try:
            ok = await post_event_async("/internal/events/broadcast", msg)
            if not ok:
                all_ok = False
        except Exception as ex:
            all_ok = False
            logger.error(f"[Chain Worker] Recovery sweep broadcast failed for '{tgt}' (retry next sweep): {ex}")

    if not all_ok:
        # 일부 발사 실패 → broadcast_at을 확정하지 않고 다음 스윕에서 재시도(eventual delivery 유지).
        return

    db.query(DatabaseOutbox).filter(DatabaseOutbox.id.in_(stale_ids)).update(
        {DatabaseOutbox.broadcast_at: func.now()}, synchronize_session=False)
    db.commit()
    logger.info(
        f"[Reliability F1] Recovery sweep re-delivered {len(affected_targets)} table refresh(es) "
        f"for {len(stale_ids)} undelivered row(s): {sorted(affected_targets)}"
    )

async def start_chain_ingestion_worker(db_session_factory):
    logger.info("Initializing Chained Ingestion Worker Daemon...")
    rules = load_chain_rules()
    logger.info(f"Loaded {len(rules)} active chain ingestion rules.")
    
    last_reload_event_id = 0
    # [Latency Fix #1] SYSTEM_RELOAD 조회를 매 루프가 아니라 최소 간격(초)으로만 수행하여
    # 고처리량 버스트 중 불필요한 반복 조회를 줄인다. (부분 인덱스 idx_outbox_reload 와 병행)
    last_reload_check_ts = 0.0
    RELOAD_CHECK_INTERVAL = 1.0

    # [Reliability F1] 통지 미확정 교정 행 안전망 스윕도 매 루프가 아니라 최소 간격(초)으로만 수행한다.
    last_sweep_ts = 0.0
    SWEEP_INTERVAL = 5.0

    # [C-3] outbox 보관 정책(7일) purge — 기동 직후 1회(다운타임 백로그 소화) + 이후 1시간 주기.
    #   전달 기한이 없는 유지보수 작업이므로 백그라운드 태스크(to_thread)로 발사해 폴링 루프를 막지 않는다
    #   (통지처럼 기아가 문제되는 경로가 아님 — 늦게 완료돼도 무해·멱등). done 가드로 중복 실행을 방지한다.
    last_purge_ts = None
    purge_task = None

    # [Latency Fix #4] LISTEN 전용 커넥션을 워커 수명 동안 상시 유지(대기마다 재등록하던 레이스 제거).
    listener = OutboxListener(db_session_factory, "outbox_event")

    # [Latency SLO 계측] 마지막 LISTEN wake 시각. NOTIFY로 깨어난 직후 기록하고, 배치 처리 시 소비한다.
    #   wake 없이 연속 배치를 처리하는 경우(백로그 소진 중)는 반복 시작 시각을 기준점으로 쓴다.
    loop_wake_ts = None

    import sys
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if script_dir not in sys.path:
        sys.path.append(script_dir)

    # [Warmup] 콜드 스타트 제거: 매퍼 선(先)import + DB 풀 프라임 + HTTP 클라이언트 준비.
    #   sys.path에 server 디렉토리가 추가된 뒤에 실행해야 mappers.* import가 해석된다.
    warmup_worker(rules, db_session_factory)

    while True:
        # [B1/B2] Progress beat, emitted from the work loop itself. Idle
        # iterations are bounded by the 2 s LISTEN timeout below, so a beat that
        # stops advancing means this loop stopped advancing - the freeze case a
        # pid check cannot see.
        heartbeat.beat("chain")
        try:
            db = db_session_factory()
            try:
                from database.models import DatabaseOutbox

                iter_start_ts = time.monotonic()

                # Check for SYSTEM_RELOAD outbox event to reload configs and code on-demand (throttled)
                now_ts = time.monotonic()
                if now_ts - last_reload_check_ts >= RELOAD_CHECK_INTERVAL:
                    last_reload_check_ts = now_ts
                    latest_reload = db.query(DatabaseOutbox).filter(
                        DatabaseOutbox.event_type == "SYSTEM_RELOAD"
                    ).order_by(DatabaseOutbox.id.desc()).first()
                else:
                    latest_reload = None

                if latest_reload and latest_reload.id > last_reload_event_id:
                    # Sync tracker id
                    last_reload_event_id = latest_reload.id
                    logger.info(f"[Reload] SYSTEM_RELOAD trigger detected (Event ID: {latest_reload.id}). Reloading configurations...")
                    # 1. Reload dynamic modules cache
                    reload_worker_process_cache()
                    # 1-1. [이슈 #7] config 재로드 + 신규 테이블 ORM 등록 + 물리 CREATE 보충
                    #      (웹서버가 1차 CREATE — information_schema 게이트 + checkfirst로 경합 무해)
                    try:
                        from database.database import engine as _db_engine
                        from database import models as _db_models
                        created_tables = _db_models.refresh_dynamic_models(_db_engine)
                        if created_tables:
                            logger.info(f"[Reload] Created missing physical tables at runtime: {created_tables}")
                    except Exception as e:
                        logger.error(f"[Reload] Dynamic model refresh failed: {e}")
                    # 2. Reload chain rules configurations from disk
                    rules = load_chain_rules()
                    logger.info(f"[Reload] Loaded {len(rules)} active chain ingestion rules.")
                    # 3. [Warmup] 캐시 무효화로 콜드 스타트가 재발하지 않도록 매퍼를 즉시 재웜업.
                    #    (DB 풀은 리로드에도 유지되므로 프라임 생략 — db_session_factory=None)
                    warmup_worker(rules)
                    
                    # Mark the trigger event as SUCCESS in this tx if it is not processed yet
                    # (This event only serves as IPC notify signal, does not execute mappers)
                    if latest_reload.processed_chain == False:
                        latest_reload.processed_chain = True
                        latest_reload.status = "SUCCESS"
                        db.commit()

                # [Reliability F1] 통지 미확정(broadcast_at IS NULL) 교정 행 안전망 스윕(throttle).
                #   commit됐으나 통지가 유실된 행을 주기적으로 재발사하여 eventual delivery를 보장한다.
                if now_ts - last_sweep_ts >= SWEEP_INTERVAL:
                    last_sweep_ts = now_ts
                    await sweep_undelivered_broadcasts(db, rules, db_session_factory)

                # [C-3] outbox 7일 보관 purge (저빈도·비블로킹·별도 세션)
                if (purge_task is None or purge_task.done()) and (
                    last_purge_ts is None or now_ts - last_purge_ts >= OUTBOX_PURGE_INTERVAL
                ):
                    last_purge_ts = now_ts
                    purge_task = asyncio.create_task(
                        asyncio.to_thread(purge_expired_outbox_sync, db_session_factory)
                    )

                # Fetch pending outbox records
                pending_events = db.query(DatabaseOutbox).filter(
                    DatabaseOutbox.processed_chain == False
                ).order_by(DatabaseOutbox.id.asc()).limit(200).all()
                
                if not pending_events:
                    loop_wake_ts = None
                    if await listener.wait(2.0):
                        # [Latency SLO 계측] NOTIFY 감지 시각 — 다음 반복의 배치 처리에서 wake 기준점으로 소비.
                        loop_wake_ts = time.monotonic()
                    continue

                # [Latency SLO 계측] 배치의 wake 기준점: NOTIFY로 깨어났으면 그 시각, 아니면(백로그 연속 처리
                #   /타임아웃 폴링 발견) 이번 반복 시작 시각. 소비 후 리셋(다음 배치에 이월 금지).
                batch_wake_ts = loop_wake_ts if loop_wake_ts is not None else iter_start_ts
                loop_wake_ts = None


                # Dynamic fetch guard: if the last element belongs to a transaction, fetch all remaining events of the same tx
                # 1. First unpack/normalize all payloads in pending_events and mark/filter SCHEDULER_RUN_NOW control events
                normalized_events = []
                for event in pending_events:
                    payload_data = get_payload_dict(event)
                    event._parsed_payload = payload_data
                    if isinstance(event.payload, str):
                        event.payload = payload_data
                    
                    if event.event_type == "SCHEDULER_RUN_NOW":
                        continue
                        
                    normalized_events.append(event)

                if not normalized_events:
                    continue

                last_event = normalized_events[-1]
                last_tx_id = last_event._parsed_payload.get("transaction_id") if isinstance(last_event._parsed_payload, dict) else None
                if last_tx_id:
                    current_ids = {e.id for e in normalized_events}
                    candidates = db.query(DatabaseOutbox).filter(
                        DatabaseOutbox.processed_chain == False,
                        ~DatabaseOutbox.id.in_(current_ids),
                        # [Reliability F3] .as_string()은 CAST(payload -> 'transaction_id' AS VARCHAR)로 컴파일되어
                        # 표현식 인덱스 idx_outbox_txid(= payload ->> 'transaction_id')와 식이 달라 미사용되었다.
                        # payload를 JSONB로 type_coerce 후 .astext를 쓰면 ->> 로 컴파일되어 인덱스와 정확히 일치한다.
                        # (컬럼 타입이 JSON().with_variant(JSONB)라 ORM 레벨 제네릭 JSON엔 .astext가 없어 직접 호출은 불가.)
                        type_coerce(DatabaseOutbox.payload, JSONB)['transaction_id'].astext == last_tx_id
                    ).limit(20000).all()
                    
                    extra_events = []
                    for e in candidates:
                        e_pay = get_payload_dict(e)
                        e._parsed_payload = e_pay
                        if isinstance(e.payload, str):
                            e.payload = e_pay
                        extra_events.append(e)
                            
                    if extra_events:
                        normalized_events.extend(extra_events)
                        logger.info(f"Loaded {len(extra_events)} extra events to complete tx '{last_tx_id}' (Total size: {len(normalized_events)})")
                
                # Group events by transaction_id
                groups = defaultdict(list)
                group_order = []
                
                for event in normalized_events:
                    tx_id = event._parsed_payload.get("transaction_id") if isinstance(event._parsed_payload, dict) else None
                    if not tx_id:
                        tx_id = f"single_{event.event_uuid}"
                    if tx_id not in groups:
                        group_order.append(tx_id)
                    groups[tx_id].append(event)
                
                # [Latency Fix #5] 실패 그룹은 배치 전체를 중단(break)하지 않고 건너뛴다(순서 보존 가드는 내부 처리).
                failed_any = await process_pending_groups(db, group_order, groups, rules, db_session_factory, batch_wake_ts=batch_wake_ts)

                if failed_any:
                    await asyncio.sleep(1)
                    
            except Exception as e:
                db.rollback()
                logger.error(f"Error in Chain Worker execution loop: {e}")
                await asyncio.sleep(3)
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Database session setup failed in Chain Worker: {e}")
            await asyncio.sleep(5)
