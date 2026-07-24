import asyncio
import json
import os
import logging
import importlib
import uuid
import select
import time
from collections import defaultdict

# Setup Unified Logger
from utils.logger import get_process_logger
from utils.payload_helper import get_payload_dict

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

RULES_PATH = os.path.join(os.path.dirname(__file__), "config", "chain_rules.json")

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8080")

async def post_event_async(endpoint: str, payload: dict):
    import requests
    url = f"{API_BASE_URL}{endpoint}"
    def do_post():
        try:
            # [Latency Fix #2] 통지는 커밋 이후 fire-and-forget으로 수행되므로
            # 워커 폴링을 오래 붙잡지 않도록 타임아웃을 짧게(3초) 유지한다.
            res = requests.post(url, json=payload, timeout=3)
            if not res.ok:
                logger.error(f"[Chain Worker] API notification failed: {url} -> {res.status_code}")
        except Exception as e:
            logger.error(f"[Chain Worker] Failed to send API notification: {e}")
    await asyncio.to_thread(do_post)


# [Latency Fix #2] 커밋 이후 브로드캐스트 통지를 fire-and-forget으로 디스패치하기 위한 배경 태스크 레지스트리.
# 통지의 성공/실패는 데이터 처리 성공 여부·재시도 판정에 절대 반영하지 않는다.
_background_broadcast_tasks = set()

async def _dispatch_broadcasts(messages):
    """수집된 브로드캐스트 메시지를 순서대로(삭제 → upsert) 전송한다. 실패는 로깅만 하고 삼킨다."""
    for m in messages:
        try:
            await post_event_async("/internal/events/broadcast", m)
        except Exception as e:
            logger.error(f"[Chain Worker] Broadcast dispatch failed (ignored): {e}")

def dispatch_broadcasts_bg(messages):
    """이미 커밋된 그룹의 통지를 배경 태스크로 발사하고 즉시 반환한다(폴링 루프 비차단)."""
    if not messages:
        return
    task = asyncio.create_task(_dispatch_broadcasts(messages))
    _background_broadcast_tasks.add(task)
    task.add_done_callback(_background_broadcast_tasks.discard)

def load_chain_rules():
    if not os.path.exists(RULES_PATH):
        logger.warning(f"Chain rules configuration file not found at {RULES_PATH}. Using empty rules.")
        return []
    try:
        with open(RULES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("rules", [])
    except Exception as e:
        logger.error(f"Failed to load chain rules: {e}")
        return []

def execute_custom_mapper(module_name: str, function_name: str, db, payload):
    """
    Dynamically imports a python mapper module and executes the mapping function.
    """
    try:
        module = importlib.import_module(module_name)
        mapper_func = getattr(module, function_name)
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
                    target_payload = execute_custom_mapper(module_name, func_name, db, payloads)
                    if target_payload and isinstance(target_payload, dict) and target_payload.get("updates"):
                        table_updates[target_table].extend(target_payload.get("updates"))
                else:
                    # Single event execution
                    for event in valid_events:
                        if event.table_name == table_name and event.event_type in ["CREATE", "EDIT"]:
                            target_payload = execute_custom_mapper(module_name, func_name, db, get_payload_dict(event))
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
                
                # 5. Collect WebSocket broadcast messages (dispatched AFTER commit, fire-and-forget).
                #    이벤트명/페이로드 형식은 절대 변경하지 않고 타이밍만 커밋 이후로 미룬다.
                try:
                    from main import to_local_str
                    
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
                    serialized_logs = []
                    if created_logs:
                        from datetime import datetime
                        for log in created_logs:
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
                            "created_logs": serialized_logs
                        }
                    else:
                        msg = {
                            "event": "batch_row_upsert",
                            "table_name": target_table,
                            "items": msg_items,
                            "updated_by": user_name,
                            "transaction_id": chain_tx_id,
                            "created_logs": serialized_logs
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
                    logger.error(f"Failed to build chained update notification: {ws_err}")
                    
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

async def process_pending_groups(db, group_order, groups, rules):
    """[Latency Fix #5] 한 배치 안의 트랜잭션 그룹들을 순차 처리한다.

    기존 로직은 한 그룹이 실패하면 `break`로 **배치 전체를 중단**하고 `sleep(1)` 후 다음 배치에서
    처음부터 재시도했다. 실패 그룹이 큐 선두(id asc)에 있으면 3회 재시도 동안 뒤의 정상 이벤트가
    전부 정체되는 head-of-line 블로킹이 발생했다.

    개선: 실패 그룹은 **건너뛰되(break 제거)**, 데이터 유실/중복 없이 미처리 상태로 남겨 다음 배치에서
    재시도한다(rollback → retry_count 증가 → 3회 후 격리 유지). 다만 **순서 의존성 보존**을 위해,
    실패 그룹이 기록하려던 target_table을 건드리는 **후속 그룹만** 이번 배치에서 보류한다(동일 target에
    대해 나중 그룹이 먼저 적용되어 순서가 뒤집히는 것을 방지). 서로 다른 target_table 그룹은 계속 처리된다.

    반환: 이번 배치에 실패 그룹이 하나라도 있었는지(failed_any) — 호출부의 백오프 sleep 판단용.
    """
    from datetime import datetime
    failed_any = False
    # 실패 그룹이 점유(보류)한 target_table 집합. 이후 동일 target 그룹은 순서 보존을 위해 이번 배치 보류.
    blocked_targets = set()

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
        success, error_reason, broadcast_messages = await process_chain_transaction_group(tx_id, events_in_tx, db, rules)

        if success:
            for event in events_in_tx:
                event.processed_chain = True
                event.status = "SUCCESS"
            db.commit()
            # [Latency Fix #2] 데이터 처리 성공 + 커밋 이후에만 통지를 fire-and-forget으로 발사한다.
            # 통지 실패는 이미 커밋된 그룹의 재처리/중복을 유발하지 않는다(재시도는 오직 처리 실패로만 트리거).
            dispatch_broadcasts_bg(broadcast_messages)
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

    return failed_any

async def start_chain_ingestion_worker(db_session_factory):
    logger.info("Initializing Chained Ingestion Worker Daemon...")
    rules = load_chain_rules()
    logger.info(f"Loaded {len(rules)} active chain ingestion rules.")
    
    last_reload_event_id = 0
    # [Latency Fix #1] SYSTEM_RELOAD 조회를 매 루프가 아니라 최소 간격(초)으로만 수행하여
    # 고처리량 버스트 중 불필요한 반복 조회를 줄인다. (부분 인덱스 idx_outbox_reload 와 병행)
    last_reload_check_ts = 0.0
    RELOAD_CHECK_INTERVAL = 1.0

    # [Latency Fix #4] LISTEN 전용 커넥션을 워커 수명 동안 상시 유지(대기마다 재등록하던 레이스 제거).
    listener = OutboxListener(db_session_factory, "outbox_event")

    import sys
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if script_dir not in sys.path:
        sys.path.append(script_dir)

    while True:
        try:
            db = db_session_factory()
            try:
                from database.models import DatabaseOutbox

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
                    # 2. Reload chain rules configurations from disk
                    rules = load_chain_rules()
                    logger.info(f"[Reload] Loaded {len(rules)} active chain ingestion rules.")
                    
                    # Mark the trigger event as SUCCESS in this tx if it is not processed yet
                    # (This event only serves as IPC notify signal, does not execute mappers)
                    if latest_reload.processed_chain == False:
                        latest_reload.processed_chain = True
                        latest_reload.status = "SUCCESS"
                        db.commit()

                # Fetch pending outbox records
                pending_events = db.query(DatabaseOutbox).filter(
                    DatabaseOutbox.processed_chain == False
                ).order_by(DatabaseOutbox.id.asc()).limit(200).all()
                
                if not pending_events:
                    await listener.wait(2.0)
                    continue
                
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
                        DatabaseOutbox.payload['transaction_id'].as_string() == last_tx_id
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
                failed_any = await process_pending_groups(db, group_order, groups, rules)

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
