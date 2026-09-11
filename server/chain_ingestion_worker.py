import asyncio
import json
import math
import os
import logging
import importlib
import inspect
import uuid
import select
import time
from collections import defaultdict

import numpy as np
import pandas as pd
from sqlalchemy import type_coerce, text
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB

# Setup Unified Logger
from utils import logger as process_logging
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
import alignment_batch_counts
import event_constants
from event_constants import (MAX_NOTIFY_CREATED_LOGS, BROADCAST_ITEM_LIMIT,
                            OUTBOX_GROUP_MAX_ROWS, trim_events_to_row_budget)
# [OUTBOX-4] Collapsed outbox events name rows instead of carrying them; this is
# where they are read back into the payload shape the mappers take.
import outbox_expand

# `META_TABLE` — the meta-upsert rule points its edge at this name. (The M3
# auto-registration this import once served retired 2026-09-07.)
import map_meta_registrar

# [Enrichment ①] Absent-only automatic confirmation when the declared reference
# views leave exactly one candidate (per-rule knob `auto_confirm`, default OFF).
import enrichment_candidates

# [ChainKeyGate] A chain may not emit a row whose key columns are not filled. The gate
# sits on the write loop below - the one place every chain-emitted row passes through -
# rather than in each mapper, because `server/mappers/*.py` is gitignored and a guard
# written there does not deploy.
import chain_key_gate

# [Retraction] Removing what ONE SOURCE owns, for a map fed by several. `replace_map`
# removes by map and cannot express it - see the retract branch in the write loop.
import dt_map_derivation
import chain_activity
import chain_bindings
from ledger import followup as ledger_followup

#: 🔴 THE FILE THIS PROCESS LOGS TO, NAMED ONCE AND CARRIED ONTO THE MAPPER LINES.
#  A mapper runs in THIS process, so its lines land here and not in the web server's
#  `server.log`. On 2026-09-04 the owner put a `print` inside a mapper, watched "the
#  server log", saw nothing, and concluded the mapper had not run - it had, and the
#  line was in this file. A tag that says which file it is costs one string and closes
#  that question at the place where it is asked.
LOG_FILENAME = "chain_worker.log"

logger = get_process_logger("Chain", LOG_FILENAME)

#: Prefix on every mapper-execution line: what ran it, and where to read it.
#
# 🔴 READ FROM THE LOGGER, NOT FROM `LOG_FILENAME`. In the integrated server the chain
# loop runs inside the web server's process, whose log file was opened first, so these
# lines land in `server.log` - and a constant tag would print `mapper@chain_worker.log`
# on top of them. The rule this tag exists to serve is "say which file you are in", and
# a tag that names the file this module WANTED rather than the one it GOT breaks that
# rule while looking like it follows it.
MAPPER_LOG_TAG = "mapper@%s" % (process_logging.active_log_filename() or LOG_FILENAME)

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

import internal_event_client

API_BASE_URL = internal_event_client.api_base_url()

# [Warmup #3] 스레드별 keep-alive 세션은 internal_event_client가 소유한다.
#   [F8] 이전에는 이 파일이 `requests.Session()`을 직접 만들었다 — requests의 기본값
#   trust_env=True가 HTTP_PROXY와 Windows 프록시 레지스트리를 읽고, ProxyOverride의
#   `<local>`은 점 없는 호스트명만 우회하므로 127.0.0.1은 우회되지 않는다. 그래서
#   자기 자신에게 보내는 통지가 사내 프록시로 나갔고 403으로 거절됐다(2026-07-30).
#   세션 생성 지점을 단일화해 새 발신자가 같은 실수를 반복할 수 없게 한다.

async def post_event_async(endpoint: str, payload: dict) -> bool:
    """통지를 fire-and-forget으로 전송하고 전달 확정 여부(bool)를 반환한다.

    [Reliability F1] 반환값은 broadcast_at 스탬프 판정에만 쓰인다(전달 확정 시 True).
    데이터 처리 성공/재시도 판정에는 절대 반영하지 않는다(통지 실패 ≠ 처리 실패).
    """
    def do_post():
        try:
            # [Latency Fix #2] 통지는 커밋 이후 fire-and-forget으로 수행되므로
            # 워커 폴링을 오래 붙잡지 않도록 타임아웃을 짧게(3초) 유지한다.
            # [Warmup #3] 스레드-로컬 Session으로 keep-alive 재사용(매 호출 커넥션 수립 제거).
            # [B5] /internal/events/* carries the admin secret; inherited from
            # the launcher's environment. 401 here = worker started without it.
            # [S-37 · 판정 98] URL·헤더·판별자는 `internal_event_client` 가 짓는다.
            url, res, note = internal_event_client.send_internal_event(
                API_BASE_URL, endpoint, payload, timeout=3)
            if not res.ok:
                # [F8] The status code alone cannot say WHO refused, and the two
                # answers have unrelated remedies. The response already carries
                # the discriminator - the gate attaches WWW-Authenticate:
                # X-Admin-Token to every rejection it produces itself - and this
                # line used to throw it away, which is how a repeated 403 here
                # cost an incident's worth of source reading to attribute.
                suffix = f" | {note}" if note else ""
                logger.error(
                    f"[Chain Worker] API notification failed: {url} -> "
                    f"{res.status_code}{suffix}")
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
    # [P-6] 「상한에 닿았나」는 «행 수로 말할 수 없다». 이 루프는 사이클당 max_chunks 까지만
    # 지우고 나머지를 다음 사이클로 이월하므로, 「상한에 닿음」과 「그만큼만 만료됐음」이
    # «같은 수»로 나온다. 유입이 삭제보다 빠른 설치에서는 잔량이 자라는데 증상이 «디스크»뿐이다.
    # `drained` 는 「만료된 것을 다 지웠다」이고, 그것의 부정이 「더 있는데 멈췄다」이다.
    #
    # ⚠️ 예외로 빠지면 `capped` 는 `None` 으로 «남는다» — 세다 만 수라 참도 거짓도 아니다.
    #    False 로 적으면 「더 없다」는 «거짓 진술»이 된다.
    capped = None
    drained = False
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
                drained = True
                break
        capped = (max_chunks > 0) and not drained
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
    # 🔴 계기는 «호출자»가 아니라 여기서 낸다 — 유일한 호출자는 이 결과를 안 받는다
    # (`asyncio.create_task(asyncio.to_thread(...))`). 그래서 반환을 넓히면 «독자 0» 인
    # 값이 하나 더 생길 뿐이고, 대신 이미 GET /admin/chain/queue 가 펼치는 레지스트리에
    # 싣는다 — 새 표면이 아니라 «있는 표면의 한 칸»이다. 반환 모양은 «안 바꾼다».
    chain_activity.registry.note_outbox_purge(total_deleted, capped)
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

#: [DEPTH] The chain-rules DOCUMENT as last loaded, for the settings that sit beside
#: `rules` rather than inside a rule. Kept here instead of re-opening the file: a second
#: reader is a second answer the day the two run at different moments, which is the
#: fourth cleanliness rule. `load_chain_rules` refreshes it on every load and on every
#: SYSTEM_RELOAD, so the loop reads whatever the last load saw and never the disk.
_RULES_DOCUMENT = {}


#: 한 그룹이 «몇 번» 시도되고 격리되나 (S-139, 소유자 09-10 21:35 「3회 없애, 1회면 끝」).
#: 기본 1 = 첫 실패에 바로 FAILED 로 격리하고 «이름을 댄다».
DEFAULT_MAX_GROUP_ATTEMPTS = 1


def max_group_attempts() -> int:
    """선언된 상한, 없으면 기본 1. 판정·로그·격리 경계가 «이 한 수»를 본다.

    🔴 상수를 값만 바꾸지 않는 이유 (S-139). 종전엔 `>= 3` 이 판정에 박혀 있고 로그가
    「(N/3)」 를 «따로» 적었다 — 상한을 옮기면 둘이 갈라지고, 갈라진 로그는 「몇 번 남았나」에
    대해 조용히 거짓말한다. 이제 셋이 같은 함수를 부른다.

    ⚠️ 3 을 적으면 옛 동작이 «그대로» 돌아온다 — 이 변경은 기본값을 옮긴 것이지 기제를
    없앤 것이 아니다.
    """
    value = (_RULES_DOCUMENT or {}).get("max_group_attempts",
                                        DEFAULT_MAX_GROUP_ATTEMPTS)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        logger.warning(
            "[Chain] max_group_attempts=%r is not a number; using %d.",
            value, DEFAULT_MAX_GROUP_ATTEMPTS)
        return DEFAULT_MAX_GROUP_ATTEMPTS
    # 0 이하는 「한 번도 안 시도한다」가 되어 그룹이 «영원히» 격리된다. 1 로 바닥을 둔다.
    return parsed if parsed >= 1 else DEFAULT_MAX_GROUP_ATTEMPTS


def load_chain_rules():
    global _RULES_DOCUMENT
    rules = []
    if not os.path.exists(RULES_PATH):
        logger.warning(f"Chain rules configuration file not found at {RULES_PATH}. Using empty rules.")
    else:
        try:
            with open(RULES_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                rules = data.get("rules", [])
                _RULES_DOCUMENT = data if isinstance(data, dict) else {}
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

    _validate_chain_cascade_graph(rules)
    _report_unwatchable_trigger_columns(rules)
    # 🔴 선언된 규칙을 «값»으로 세운다 — 처리 루프가 결과를 덮어쓰고, 한 번도 안 걸린 규칙은
    #    「아직 평가 안 됨」으로 «말해진다». 부재는 「옛 서버」 하나만 뜻해야 한다.
    #    로더 «안»이라 호출자가 둘이어도 저자는 하나다.
    chain_activity.registry.seed_rules(
        (r or {}).get("name") or "<unnamed rule>" for r in (rules or ()))
    return rules


def rule_watches_changed_columns(rule, event) -> bool:
    """Did this write touch a column the rule asked to be woken by? (S-140 ②③)

    🔴 ABSENCE IS 「모른다」, NOT 「아무것도 아니다」. An event staged before this key
    existed - and every non-collapsed per-row event - carries no `columns`, so it lands
    in the RUN branch. Reading a missing key as an empty set would silently stop every
    column-scoped rule on exactly the events nobody re-staged, which is the class where
    five different zeros render the same.

    ⚠️ A rule with no `trigger_columns` is table-scoped as it has always been.
    """
    wanted = rule.get("trigger_columns")
    if not wanted:
        return True
    changed = get_payload_dict(event).get("columns")
    if changed is None:
        return True
    return bool(set(wanted) & set(changed))


def _rule_accepts_event(rule, event) -> bool:
    """Chain-produced events are opt-in per downstream rule, never globally live."""
    if get_payload_dict(event).get("source_name") != "chain_ingestion":
        return True
    return bool(rule.get("allow_chain_trigger"))


def _report_unwatchable_trigger_columns(rules):
    """Name every `trigger_columns` entry the trigger table does not declare (S-140 ④).

    🔴 OTHERWISE THE RULE STANDS AND NEVER FIRES. A typo there intersects nothing, so the
    rule is enabled, looks live, and is silently never woken - which reads as 「the chain
    is broken」 rather than 「this name is wrong」.

    ⚠️ REFUSED PER CELL, NOT PER FILE, and never raising: a load that dies over one bad
    name would take every other rule down with it. The rule keeps running TABLE-scoped,
    which is the behaviour it had before the cell existed.
    """
    from database import crud

    for rule in rules or ():
        wanted = rule.get("trigger_columns")
        if not wanted:
            continue
        table = rule.get("trigger_table")
        declared = set(((crud.TABLE_CONFIG.get(table) or {}).get("column_types") or {}))
        if not declared:
            # 「모른다」 — 카탈로그를 못 보는 것과 컬럼이 없는 것은 다르다.
            continue
        unknown = sorted(set(wanted) - declared)
        if unknown:
            logger.error(
                "[Chain] rule %s declares trigger_columns %s that '%s' does not have; "
                "that rule can never be woken by them and stays TABLE-scoped. "
                "Fix the names or remove the cell.",
                rule.get("name") or rule.get("target_table"), unknown, table)


def _validate_chain_cascade_graph(rules):
    """Reject cycles made solely from opt-in chain-trigger edges at config load."""
    graph = defaultdict(set)
    for rule in rules:
        if not rule.get("enabled", True) or not rule.get("allow_chain_trigger"):
            continue
        src = rule.get("trigger_table")
        if not src:
            continue
        # 🔴 A RULE CAN WRITE TWO TABLES, AND THE GRAPH USED TO SEE ONE. `target_table` is
        # where the mapper's rows go; a rule that also declares `allow_map_metadata_upsert`
        # writes MAP METADATA as well, and that write raises its own chain event. So the
        # edge to the metadata table existed in the running system and not in this graph.
        #
        # MEASURED 2026-09-04: rule #3 (dt_inventory -> dt_map) wrote 5 metadata rows per
        # run under that flag, those woke rule #2 (wafer_map_metadata -> dt_inventory),
        # and #3 consumes dt_inventory under allow_chain_trigger. That is a cycle, it was
        # live, and this validator passed it - the lead PM enabled the middle hop, saw the
        # loop, and had to reverse it by hand. A guard that cannot see one of the two
        # writes is not guarding the graph, it is guarding half of it.
        # ⚠️ THE METADATA TABLE COMES FROM THE REGISTRAR, NOT FROM THE RULE. Rule #3 sets
        # `allow_map_metadata_upsert` and declares no metadata table at all, and
        # `metadata_target_table` cannot be borrowed for it - in `dt_metadata_to_dt_inventory`
        # that same key names the mapper's SOURCE. The one place the metadata actually
        # lands is `map_meta_registrar.META_TABLE`, so that is what the edge points at.
        for dst in (rule.get("target_table"),
                    map_meta_registrar.META_TABLE if rule.get("allow_map_metadata_upsert") else None):
            if dst:
                graph[src].add(dst)

    visiting, visited = set(), set()
    def visit(node, trail):
        if node in visiting:
            raise ValueError("allow_chain_trigger cycle: " + " -> ".join(trail + [node]))
        if node in visited:
            return
        visiting.add(node)
        for nxt in graph.get(node, ()):
            visit(nxt, trail + [node])
        visiting.remove(node)
        visited.add(node)
    for node in graph:
        visit(node, [])

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

def _is_missing_scalar(value) -> bool:
    """Is this ONE value a missing marker? Same rule as `parsers/pipeline_base.py:73-75`.

    🔴 THE SPELLING IS COPIED FROM THERE ON PURPOSE, INCLUDING `inf`. That file already
    decided what "no value" means when a frame becomes rows - `pd.isna` for None/NaN/NaT,
    and a second clause turning float infinities into None as well - and the mapper
    boundary is the same decision in a third place, not a new one. If these two ever
    disagree, the same source value becomes a number on one path and a blank on the other.

    ⚠️ `pd.isna` ANSWERS ELEMENTWISE FOR CONTAINERS, so a DataFrame or an ndarray comes
    back as an array of booleans rather than one. Those are not scalars and are left
    alone; taking their truth value here would raise, which is how this kind of guard
    usually fails - loudly, on the one payload shape nobody tested.
    """
    if value is None:
        return True
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return True
    try:
        answer = pd.isna(value)
    except (TypeError, ValueError):                      # unhashable / odd objects
        return False
    return bool(answer) if isinstance(answer, (bool, np.bool_)) else False


def _missing_as_none(value):
    """Deep-replace missing markers with `None`. Returns `(value, changed)`.

    🔴 UNCHANGED INPUT COMES BACK AS THE SAME OBJECT, not a rebuilt copy. A payload with
    no missing value in it must pass through byte-identical: a normaliser that quietly
    rewrites healthy values is a silent regression, and one that copies every payload
    would also make every mapper's `is` comparison and every large batch pay for a defect
    that was not there.
    """
    if isinstance(value, dict):
        changed = False
        rebuilt = {}
        for key, item in value.items():
            new_item, item_changed = _missing_as_none(item)
            rebuilt[key] = new_item
            changed = changed or item_changed
        return (rebuilt, True) if changed else (value, False)

    if isinstance(value, (list, tuple)):
        changed = False
        rebuilt = []
        for item in value:
            new_item, item_changed = _missing_as_none(item)
            rebuilt.append(new_item)
            changed = changed or item_changed
        if not changed:
            return value, False
        return (tuple(rebuilt) if isinstance(value, tuple) else rebuilt), True

    if value is None:
        return value, False                              # already missing; nothing to do
    if _is_missing_scalar(value):
        return None, True
    return value, False


def without_missing(value):
    """`_missing_as_none` without the flag - the shape the call sites want."""
    return _missing_as_none(value)[0]


def mark_processed(event, status: str):
    """The ONE place an outbox event stops being work. Status, the flag, and the time.

    🔴 IT IS ONE FUNCTION BECAUSE IT WAS FOUR PLACES. "Processed" was hand-written at
    four sites - the group's success, two failure branches, and the SYSTEM_RELOAD
    trigger - each setting `status` and `processed_chain` itself. `processed_at` was
    declared on the model, reported by `/admin/outbox/failed`, and written by NOBODY, so
    the column answered "unknown" forever; adding a line at each of the four would have
    made eight hand-written copies of one judgement, and the fifth branch to appear
    would have been the one that forgot.

    🔴 FAILURE IS STAMPED TOO. The column means "when this stopped being worked on", and
    a permanently failed event has stopped. Stamping only success would leave every row
    on the failed-events route - the one route that publishes this column - answering
    "unknown" about itself.

    ⚠️ `func.now()`, not Python's clock: `created_at` is a server default, so both ends
    of "queued until finished" have to be read from the same clock or the difference is
    a measurement of clock skew.
    """
    event.status = status
    event.processed_chain = True
    event.processed_at = func.now()


def _payload_row_count(payload):
    """How many trigger rows this call carries. A batch mapper is handed a list."""
    if isinstance(payload, (list, tuple)):
        return len(payload)
    return 1 if payload else 0


def _result_row_count(result):
    """How many rows the mapper produced, counted across the shapes a mapper returns.

    Counted rather than assumed. A mapper returns `{"updates": [...]}`, or
    `{"batches": [{"updates": [...]}, ...]}`, and either may also carry
    `map_metadata_updates` - the three shapes are all in production today. A number
    that read only the first would report 0 for a mapper that did a map's worth of
    work, and "0" is the answer the operator is trying to tell apart from "did not
    run".
    """
    if not isinstance(result, dict):
        return 0
    total = len(result.get("updates") or ())
    for batch in result.get("batches") or ():
        if isinstance(batch, dict):
            total += len(batch.get("updates") or ())
    total += len(result.get("map_metadata_updates") or ())
    return total


def execute_custom_mapper(module_name: str, function_name: str, db, payload, rule=None):
    """
    Dynamically imports a python mapper module and executes the mapping function.

    rule: 현재 실행 중인 체인 룰 dict. 맵퍼가 `rule` 인자를 선언한 경우에만 전달한다
    (generic 맵퍼가 룰 설정을 참조하는 용도 — 예: enrichment_mapper.map_enrichment_dedup).
    기존 (db, payload) 시그니처 맵퍼는 종전과 완전히 동일하게 호출된다.

    🔴 IT ALSO SAYS, ONCE PER GROUP, THAT THE MAPPER RAN. This is the only place every
    custom mapper is called through, so one pair of lines here covers all of them and
    no mapper author has to remember to log. What goes on the line is the identity
    (rule, mapper, target table), the size (rows in, rows out) and the time - never the
    payload body, which is operator data, and never one line per row: a mapper handed a
    thousand-row group must not turn into a thousand log lines.

    ⚠️ INFO, NOT DEBUG. A line that only exists when somebody remembered to raise the
    level does not exist on the deployment where the question is being asked.
    """
    started = time.monotonic()
    rule_name = (rule or {}).get("name") or "<unnamed rule>"
    target_table = (rule or {}).get("target_table") or "<none>"
    who = "%s.%s" % (module_name, function_name)
    rows_in = _payload_row_count(payload)
    logger.info("[%s] START rule=%s mapper=%s target=%s rows_in=%d",
                MAPPER_LOG_TAG, rule_name, who, target_table, rows_in)
    # The log says what RAN; this says what is running. A line in a file cannot answer
    # "is it in one right now" without somebody tailing it.
    token = chain_activity.registry.start(rule_name, who, target_table, rows_in)
    try:
        module = importlib.import_module(module_name)
        mapper_func = getattr(module, function_name)
        # 🔴 NaN IS NOT A VALUE AND A MAPPER AUTHOR SHOULD NOT HAVE TO KNOW THAT. Owner
        # report 2026-09-04: `cannot convert float NaN to integer` from the chain. This is
        # the one place every custom mapper is called through, so the rule is applied here
        # rather than remembered in each mapper - a rule that has to be remembered is a
        # trap, and it fires in production the first time somebody forgets.
        #
        # ⚠️ WHAT THIS DOES NOT FIX, stated so nobody reads more into it: it stops a NaN
        # arriving IN the payload. A mapper that builds its own frame with pandas can
        # still create a NaN inside itself and raise before returning, and no boundary can
        # see that.
        #
        # Missing becomes None, never 0: a zero is a VALUE, and the two being confused is
        # the defect this repository spent the day removing elsewhere.
        payload = without_missing(payload)
        # 🔴 ONE SEAT FOR BOTH ARMS (S-94, 판정 241). The group line has to be able to say
        # how much of its wall clock the MAPPER took, as opposed to the writes and the
        # outbox read around it; timing the two arms separately would be two spellings of
        # one number, free to disagree the day a third arm appears.
        with alignment_batch_counts.stage("mapper"):
            if rule is not None and _mapper_accepts_rule(mapper_func):
                result = mapper_func(db, payload, rule=rule)
            else:
                result = mapper_func(db, payload)
        # The way out as well: whatever the mapper returns goes on to the write path,
        # which has its own integer columns and would hit the same conversion.
        cleaned = without_missing(result)
        rows_out = _result_row_count(cleaned)
        logger.info("[%s] END   rule=%s mapper=%s target=%s rows_in=%d rows_out=%d "
                    "elapsed=%.3fs",
                    MAPPER_LOG_TAG, rule_name, who, target_table, rows_in,
                    rows_out, time.monotonic() - started)
        # ⚠️ 이 층이 아는 것은 「매퍼가 «행을 냈나»」다. 「쓰기가 «바꿨나»」를 아는 층은
        #    `crud.apply_batch_updates` 이고 그 수는 규칙별로 여기까지 안 온다. 그래서
        #    `ran:unchanged` 는 «확실»하고(행이 0이면 바뀐 것이 없다), `ran:changed` 는
        #    「행을 냈다」까지가 참이다. 그 마지막 한 걸음은 별도 줄이다 — 대리를 성질처럼
        #    적지 않으려고 여기 적는다.
        chain_activity.registry.record_outcome(
            rule_name,
            event_constants.RULE_OUTCOME_RAN_CHANGED if rows_out
            else event_constants.RULE_OUTCOME_RAN_UNCHANGED,
            None if rows_out else "the mapper produced no rows")
        return cleaned
    except Exception as e:
        # The throw gets its OWN line rather than being folded into the end line: a
        # mapper that raised produced no rows, and "rows_out=0" would be the same text
        # a mapper that legitimately had nothing to do writes.
        logger.error("[%s] RAISED rule=%s mapper=%s target=%s rows_in=%d elapsed=%.3fs "
                     "-> %s: %s",
                     MAPPER_LOG_TAG, rule_name, who, target_table, rows_in,
                     time.monotonic() - started, type(e).__name__, e)
        chain_activity.registry.record_outcome(
            rule_name, event_constants.RULE_OUTCOME_FAILED,
            "%s: %s" % (type(e).__name__, e))
        raise e
    finally:
        # 🔴 IN `finally`, NOT AFTER THE RETURN. A mapper that throws is exactly the case
        # where an entry left behind would sit in the view forever, saying a mapper is
        # still running - and a stuck-looking chain is the symptom this whole step exists
        # to stop inventing.
        chain_activity.registry.finish(token)

def _rule_outcome_before_running(rule, events):
    """이 규칙이 이 그룹에 대해 «돌기 전에» 결정되는 결과 — 또는 `(None, None)`(돌 자격 있음).

    🔴 판정이 여기 «한 자리»다. 아래 `valid_events` 가 같은 술어를 쓰지만 그것은 「이 그룹에
       할 일이 있나」를 묻고 이것은 「이 «규칙»이 왜 안 도나」를 묻는다 — 답이 갈리면 안 되므로
       둘 다 `_rule_accepts_event` 와 `enabled` «같은 것»을 지난다.
    ⚠️ 꺼짐이 안 걸림을 «이긴다». 둘 다 참일 때 운영자가 고칠 수 있는 쪽이 그것이다.
    """
    if not rule.get("enabled", True):
        return event_constants.RULE_OUTCOME_SKIPPED_DISABLED, "rule declares enabled: false"
    refused_chain = False
    for e in events:
        if e.event_type not in ("CREATE", "EDIT"):
            continue
        if rule.get("trigger_table") != e.table_name:
            continue
        if not rule_watches_changed_columns(rule, e):
            # 한 줄로 말한다 — 「안 돌았다」가 「고장났다」처럼 읽히지 않게.
            logger.info(
                "[Chain] rule %s skipped: none of %s changed",
                rule.get("name") or rule.get("target_table"),
                sorted(rule.get("trigger_columns") or ()))
            continue
        if _rule_accepts_event(rule, e):
            return None, None
        refused_chain = True
    if refused_chain:
        return (event_constants.RULE_OUTCOME_SKIPPED_NOT_TRIGGERED,
                "chain-produced event; this rule does not declare allow_chain_trigger")
    return event_constants.RULE_OUTCOME_SKIPPED_NOT_TRIGGERED, None


def _record_pre_run_outcomes(rules, events):
    """평가된 «모든» 규칙이 이름 있는 결과를 갖는다 — 걸린 것만이 아니라.

    🔴 걸린 것만 남기면, «평가돼서 할 일이 없던» 규칙이 영원히 `never_evaluated` 로 남는다.
       그건 이 라운드가 없애려는 그 침묵이고, 부재는 「옛 서버」 «하나»만 뜻해야 한다.
    """
    for rule in rules or ():
        outcome, reason = _rule_outcome_before_running(rule, events)
        if outcome is not None:
            chain_activity.registry.record_outcome(
                (rule or {}).get("name") or "<unnamed rule>", outcome, reason)


def _group_triggered_rules(events_in_tx, rules):
    """이 그룹이 «깨우는» 규칙들. `_group_target_tables` 와 아래 읽기 집합이 «같은 술어»를
    지나야 한다 — 갈리면 한쪽이 보는 표를 다른 쪽이 못 본다.
    """
    trigger_tables = set(
        e.table_name for e in events_in_tx if e.event_type in ("CREATE", "EDIT")
        and any(r.get("trigger_table") == e.table_name and r.get("enabled", True)
                and _rule_accepts_event(r, e) for r in rules)
    )
    if not trigger_tables:
        return []
    return [r for r in rules
            if (r.get("enabled", True) and r.get("trigger_table") in trigger_tables
                and any(e.table_name == r.get("trigger_table") and _rule_accepts_event(r, e)
                        for e in events_in_tx))]


def _group_read_tables(events_in_tx, rules):
    """이 그룹이 «읽을» 표 집합 — 열거는 `chain_bindings.RULE_TABLE_KEYS` «하나»가 든다.

    🔴 순서 가드가 이것을 못 봐서 선언된 교차 «다섯»이 통째로 안 보였다. 상류가 실패한 표를
       읽는 하류 규칙이 그대로 돌았고, 그 답은 «낡은 값 위»에서 나왔다 — 오류 없이.
    ⚠️ `_group_target_tables` 를 «고쳐서» 쓰지 않는다. 그 함수는 소비자가 «둘»이고 둘째는
       순서가 아니라 «미전달 행 스윕»이라(:`affected_targets`), 뜻을 바꾸면 그쪽이 같이 움직인다.
    """
    return {t for r in _group_triggered_rules(events_in_tx, rules)
            for t in chain_bindings.rule_tables(r, chain_bindings.TABLE_ROLE_READ)}


def _group_target_tables(events_in_tx, rules):
    """[Latency Fix #5] 이 트랜잭션 그룹이 기록할 target_table 집합을 매퍼 실행 없이 규칙에서 추정한다.

    실패 그룹을 건너뛰되 '동일 target_table을 건드리는 후속 그룹만' 보류(순서 보존)하기 위한 판정용.
    target_table은 매퍼 반환값이 아니라 규칙 설정(rule['target_table'])에서 결정되므로 정적 추정이 정확하다.
    순환 루프 필터(source_name == 'chain_ingestion' 제외)와 트리거 이벤트 타입(CREATE/EDIT)은
    `process_chain_transaction_group`의 판정과 동일하게 맞춘다. 체인 생성 이벤트는
    allow_chain_trigger를 선언한 규칙이 있을 때만 target 영향으로 계산한다.
    """
    trigger_tables = set(
        e.table_name for e in events_in_tx if e.event_type in ("CREATE", "EDIT")
        and any(r.get("trigger_table") == e.table_name and r.get("enabled", True)
                and _rule_accepts_event(r, e) for r in rules)
    )
    if not trigger_tables:
        return set()
    targets = set()
    for r in rules:
        if (r.get("enabled", True) and r.get("trigger_table") in trigger_tables
                and any(e.table_name == r.get("trigger_table") and _rule_accepts_event(r, e)
                        for e in events_in_tx)):
            tgt = r.get("target_table")
            if tgt:
                targets.add(tgt)
    return targets

def _process_chain_transaction_group_sync(tx_id, events, db, rules):
    """The whole of one transaction group's work, and every line of it is BLOCKING.

    🔴 판정 193 / S-93 — THIS BODY DID NOT MOVE; ITS THREAD DID. It was written as an
    `async def` and contained no `await` at any point, so every mapper call, every query
    that mapper makes and the target write that follows ran ON THE EVENT LOOP. While it
    ran, no other request could resume - including the response owed to the very user
    whose write woke the chain.

    Measured live 2026-09-09 by the lead (PID 38168, dt_job source, 1,000 fresh rows
    through the real route): the PUT answered in 22.8-33.5 s, while the same code with
    the same PostgreSQL and no chain worker answered in 1.36 s. The decisive experiment
    was a GET issued every 3 s during the PUT: a route that normally costs 0.07 s took
    22.76 s at t+3 and 5.94 s at t+9. So the wait was not in the writer's thread; the
    LOOP was blocked, and the PUT's own answer was queued behind it. py-spy put 58% of
    its samples under `execute_custom_mapper` on the loop thread.

    ⚠️ THE GRANULARITY IS ONE GROUP, AND THAT IS NOT AN ARBITRARY CHOICE. `db` is a
    single SQLAlchemy Session, which one thread may use at a time. Groups are awaited one
    after another in `process_pending_groups` (no gather), so exactly one worker thread
    ever holds this session. Splitting finer would put two threads on it.

    ⚠️ AND THE CONTEXTVARS STILL WORK. `asyncio.to_thread` runs this inside a COPY of the
    caller's context, so the four tokens set below are visible to everything this calls -
    and, better than before, the copy is discarded afterwards, so they cannot leak into
    the loop's own context even if a `reset` were missed.

    Pacing, ordering and error handling are untouched: the wrapper returns exactly what
    this returns, including the failure tuple.
    """
    # [Latency Fix #2] 커밋 이후 fire-and-forget으로 발사할 브로드캐스트 메시지 큐.
    # 여기에는 이벤트명/페이로드 형식이 그대로(batch_row_*, batch_refresh_required) 담긴다.
    broadcast_messages = []

    # Chain-created events remain blocked by default.  Only a downstream rule that
    # declares allow_chain_trigger may consume them; config-load cycle validation
    # makes this opt-in graph acyclic.
    # 🔴 여섯 원인이 «한 조용한 반환»으로 나가던 자리. 입구에서 «돌기 전»에 정해지는 둘을
    #    이름 대어 남기면, 아래 어느 출구로 나가든 규칙마다 결과가 있다. 돌 자격이 있는
    #    규칙은 여기서 아무것도 안 남기고 `_run_mapper` 가 자기 결과를 남긴다.
    _record_pre_run_outcomes(rules, events)

    # 🔴 THE LEDGER LISTENS HERE, ABOVE THE TRIGGER FILTER, AND ONLY DROPS A NOTE.
    #    Its subject is the OUTBOX EVENT and not a chain rule: a person editing a cell in
    #    the grid produces the same event, and the source that reads that table has to be
    #    followed the same way (ruling 129 ㉤). So it sits above `valid_events`, which
    #    both filters on `trigger_table`/`enabled` and RETURNS EARLY when nothing matches
    #    - two decisions this step must not inherit.
    # ⛔ AND IT TRANSLATES NOTHING. `enqueue` appends to a memory deque and returns, so
    #    a chain transaction costs what it cost before this line existed; the paced task
    #    beside this loop does the work (ruling 129-bis).
    with alignment_batch_counts.stage("ledger enqueue"):
        for event in events:
            # `tx_id` and not `chain_tx_id`: the receipt this batch will write has to group
            # with the table change that CAUSED it, and that change carries the original
            # writer's transaction. `chain_tx_id` is what the chain's OWN writes take, one
            # step further down (S-117, 판정 248).
            ledger_followup.enqueue(
                event.table_name,
                ledger_followup.row_ids_of(get_payload_dict(event)),
                event.event_type,
                tx_id)

    valid_events = [e for e in events if e.event_type in ["CREATE", "EDIT"] and any(
        r.get("trigger_table") == e.table_name and r.get("enabled", True)
        and _rule_accepts_event(r, e) for r in rules)]
    if not valid_events:
        return True, None, broadcast_messages

    # [OUTBOX-4] One materialization for the whole group, before any rule runs.
    # A collapsed event NAMES rows; the mappers - including every user-owned one in
    # the gitignored `server/mappers/` tree - take the nested payload shape. This is
    # where the row is read back into that shape, the way `chain_replay._to_payloads`
    # already does it. Per-row events pass through untouched, so a batch with no
    # collapsed event in it issues no query here at all.
    with alignment_batch_counts.stage("outbox read"):
        expanded = outbox_expand.expand_events(db, valid_events)

    # 🔴 ZERO LOADED IS NOT "NOTHING TO DO" - IT IS A READ THAT FAILED (S-158).
    # A collapsed event NAMES its rows. If not one of them can be read back, the mapper
    # is handed an empty payload, does nothing, and the group ends SUCCESS - so the event
    # is stamped processed and those rows derive NOTHING, with no error, no retry and no
    # quarantine anywhere. Measured 2026-09-11: four events of 1,000 rows each went that
    # way and 3,000 rows silently failed to reach their derived table.
    #
    # ⚠️ AND THE OLD EXPLANATION WAS WRONG, WHICH IS WHY THIS CANNOT BE LEFT TO A LOG
    # LINE. `expand_events` says the rows were "deleted between the write and the chain
    # run"; measured, every one of those 3,000 rows was present in the table the whole
    # time. Whatever the cause, the honest answer here is "could not read them", and the
    # honest outcome is a REFUSAL that retries - not a success that loses them.
    #
    # ⚠️ PARTIAL IS DELIBERATELY NOT REFUSED. Some rows missing is the documented
    # delete-between case and the warning above names it; ALL of them missing, for an
    # event that named some, is the shape that cannot be a legitimate answer.
    unreadable = [e for e in valid_events
                  if event_constants.is_collapsed_payload(get_payload_dict(e))
                  and (get_payload_dict(e).get("row_ids") or ())
                  and not expanded.get(outbox_expand.event_key(e))]
    if unreadable:
        named = ", ".join(
            "%s(%d rows)" % (getattr(e, "event_uuid", "?"),
                             len(get_payload_dict(e).get("row_ids") or ()))
            for e in unreadable[:3])
        return False, (
            "rows_not_visible: %d collapsed event(s) named rows that could not be read "
            "back in this pass (%s). The rows were NOT derived; the group is refused so "
            "it retries rather than being stamped SUCCESS with an empty payload (S-158)."
            % (len(unreadable), named)), broadcast_messages

    # 2. Map of updates grouped by target table
    # target_table -> list of GeneralUpdateItem dicts
    table_updates = defaultdict(list)
    # A mapper may request one or more isolated scoped replacements.  They are
    # deliberately separate from the normal per-target aggregation: one batch
    # has one replace scope, and merging two DT jobs would make a purge broader
    # than either mapper decision.
    scoped_batches = []
    # A map projection may need to register/update its own map metadata before
    # writing cells. This is deliberately an ancillary write of the same rule,
    # not a third chain hop: the mapper remains read-only and the worker owns
    # all persistence and outbox semantics.
    map_metadata_updates = []
    # [ChainKeyGate] target_table -> the rule names that contributed to it. Collected
    # here, at the ONE place a rule is bound to its target, so the gate below can name
    # the rule an operator has to fix without any emission site having to remember to
    # tag its items. `table_updates` aggregates several rules onto one target, so this
    # cannot be recovered after the fact.
    rules_by_target = defaultdict(set)

    # 3. Evaluate rules for this transaction
    # To support batch rules, we group rules by trigger table to execute them efficiently.
    # First, gather trigger tables present in valid_events
    trigger_tables = set(e.table_name for e in valid_events if e.event_type in ["CREATE", "EDIT"])
    
    for table_name in trigger_tables:
        matched_rules = [
            r for r in rules
            if r.get("trigger_table") == table_name and r.get("enabled", True)
            and any(_rule_accepts_event(r, e) for e in valid_events if e.table_name == table_name)
        ]
        if not matched_rules:
            continue
            
        for rule in matched_rules:
            target_table = rule.get("target_table")
            module_name = rule.get("mapper_module")
            func_name = rule.get("mapper_function")
            is_batch = rule.get("is_batch", False)
            _rule_name = rule.get("name") or "<unnamed rule>"
            rules_by_target[target_table].add(_rule_name)
            if rule.get("allow_map_metadata_upsert"):
                rules_by_target[map_meta_registrar.META_TABLE].add(_rule_name)

            try:
                trigger_events = [e for e in valid_events
                                  if e.table_name == table_name
                                  and _rule_accepts_event(rule, e)]
                if is_batch:
                    # Collect all payloads for this trigger table in the current transaction group
                    payloads = [p for e in trigger_events
                                for p in expanded[outbox_expand.event_key(e)]]
                    # Pass the whole list to custom mapper
                    target_payload = execute_custom_mapper(module_name, func_name, db, payloads, rule=rule)
                    if target_payload and isinstance(target_payload, dict) and target_payload.get("updates"):
                        table_updates[target_table].extend(target_payload.get("updates"))
                    if target_payload and isinstance(target_payload, dict) and target_payload.get("map_metadata_updates"):
                        if not rule.get("allow_map_metadata_upsert", False):
                            raise ValueError(
                                f"rule '{rule.get('name')}' returned map metadata without allow_map_metadata_upsert")
                        for requested in target_payload.get("map_metadata_updates") or []:
                            updates = requested.get("updates") if isinstance(requested, dict) else None
                            if not isinstance(updates, dict):
                                raise ValueError("chain map metadata update requires an updates object")
                            if updates.get("target_table") != target_table:
                                raise ValueError(
                                    f"rule '{rule.get('name')}' cannot register metadata for '{updates.get('target_table')}'")
                            if not isinstance(updates.get("map_id"), str) or not updates["map_id"]:
                                raise ValueError("chain map metadata update requires a non-empty map_id")
                            map_metadata_updates.append(requested)
                    if target_payload and isinstance(target_payload, dict) and target_payload.get("batches"):
                        # Either permission opens the envelope; the per-batch checks below
                        # then require the one that matches the strategy the batch actually
                        # asked for. A retract-only rule must not have to grant itself
                        # `allow_replace_map` to be heard - that would leave a purge
                        # permission standing for a rule that never purges.
                        # 🔴 [C-15] 봉투 검증은 «한 독자»가 한다. 이 여섯 규칙이 여기와
                        #    `chain_replay` 에 «두 사본»으로 있었고, 그 옆 주석이 「손으로
                        #    맞춘다」고 적어 두었다 — 형제(retract 봉투)는 이미 한 독자였다.
                        dt_map_derivation.require_scoped_batches_allowed(rule)
                        for requested in target_payload.get("batches") or []:
                            scoped_batches.append(
                                dt_map_derivation.normalize_scoped_batch(
                                    requested, rule, target_table))
                else:
                    # Single event execution - one call per ROW, which for a per-row
                    # event is one call per event exactly as before.
                    for event in trigger_events:
                        # Indexed, not `.get(..., ())`: a missing key means the
                        # expander and this loop disagree about the batch, and
                        # deriving nothing silently is the failure mode to avoid.
                        for row_payload in expanded[outbox_expand.event_key(event)]:
                            target_payload = execute_custom_mapper(module_name, func_name, db, row_payload, rule=rule)
                            if target_payload and isinstance(target_payload, dict) and target_payload.get("updates"):
                                table_updates[target_table].extend(target_payload.get("updates"))
            except Exception as e:
                import traceback
                error_msg = traceback.format_exc()
                logger.error(f"Failed to execute mapper in tx {tx_id} for rule '{rule.get('name')}': {error_msg}")
                return False, error_msg, []

    # 4. Perform chained batch updates by target table
    if table_updates or map_metadata_updates or scoped_batches:
        from database import schemas, crud
        from database.context import (request_user, request_transaction_id, request_source,
                                      request_chain_depth, outbox_mode)

        chain_tx_id = f"chain_{tx_id}"
        token_user = request_user.set("chain_worker")
        token_tx = request_transaction_id.set(chain_tx_id)
        token_src = request_source.set("chain_ingestion")
        # 🔴 [DEPTH] STAMPED ONCE, HERE, BECAUSE THIS IS WHERE THE CHAIN'S WRITES CONVERGE.
        # Ten mappers spell `source_name: "chain_ingestion"` in the rows they return, but
        # that is the ROW's source column; the OUTBOX envelope is built in exactly one
        # place (`database._outbox_envelope`, whose own docstring says it exists so the
        # per-row and collapsed events cannot drift) and it reads these context vars.
        # Stamping in the mappers would be ten places to keep in step - the fourth
        # cleanliness rule, and the same shape as `bffa792b`.
        #
        # The depth of what we are ABOUT to write is one more than the deepest thing that
        # woke us. Events from outside the chain carry no depth, so `chain_depth_of`
        # answers `None` for them and `max(..., default)` starts the count at 1.
        incoming_depth = max(
            [d for d in (event_constants.chain_depth_of(get_payload_dict(e))
                         for e in events) if d is not None] or [0])
        token_depth = request_chain_depth.set(incoming_depth + 1)

        try:
            # Map metadata goes first. Its fixed standard frame and
            # valid_die_ref must be visible before the job's dt_map cells are
            # created; otherwise the absent-only auto registrar could preserve
            # a synthetic bbox frame for this map.
            write_batches = []
            if map_metadata_updates:
                write_batches.append((map_meta_registrar.META_TABLE,
                                      map_metadata_updates, False, None, None))
            write_batches.extend((target, updates, False, None, None)
                                 for target, updates in table_updates.items())
            # `retract` batches carry replace_map=False: the removal happens AFTER the
            # write, against what the write actually keyed. A purge cannot be scoped to
            # one source, so there is nothing for the write path to do up front.
            write_batches.extend((target, updates, scope is not None, scope, retract)
                                 for target, updates, scope, retract in scoped_batches)
            for target_table, updates_list, replace_map, scope, retract in write_batches:
                batch_data = schemas.GeneralUpdateBatch(
                    updates=updates_list,
                    transaction_id=chain_tx_id,
                    silent=False,
                    replace_map=replace_map,
                    scope=scope,
                )

                # [ChainKeyGate] 🔴 THE GATE. Every chain-emitted row reaches
                # `apply_batch_updates` through this loop and only through this loop, so
                # this is the one place a row with no resolvable identity can be stopped
                # without asking seven mappers to remember to do it.
                #
                # It runs AFTER the batch is built (one validator has already normalised
                # every mapper's dict/model shape) and BEFORE the write, and it is
                # read-only - it must not assemble the composite key here, because
                # writing it into `updates[key_col]` before `derive_replace_map_scope`
                # runs inside `apply_batch_updates` would narrow a whole-map purge to a
                # single die.
                with alignment_batch_counts.stage("key gate"):
                    kept, key_gate_report = chain_key_gate.screen(
                        target_table, batch_data.updates,
                        rule_names=rules_by_target.get(target_table, ()),
                        transaction_id=chain_tx_id)
                if key_gate_report["refused_rows"]:
                    batch_data.updates = kept
                    if not kept:
                        # 🔴 EVERY row was refused. Writing the batch anyway would be
                        # actively destructive on a `replace_map`: the purge (or the
                        # scope diff) removes the map's rows and nothing replaces them.
                        # A DECLARED empty replace - `scope` with an empty payload - is
                        # still honoured, because this arm is only reached when the gate
                        # is what emptied the list.
                        logger.error(
                            f"🔴 [ChainKeyGate] Table: '{target_table}' | TX: "
                            f"'{chain_tx_id}' | rule(s): "
                            f"{', '.join(key_gate_report['rules']) or '<unknown>'} | the "
                            f"whole batch of {key_gate_report['refused_rows']} row(s) "
                            f"carried no key value in {sorted(key_gate_report['by_column'])}. "
                            f"Nothing was written and no map was replaced.")
                        continue

                logger.info(
                    f"Executing chained batch updates to '{target_table}' under tx '{chain_tx_id}' "
                    f"(size: {len(batch_data.updates)}, replace_map={replace_map}, scope={scope}, "
                    f"unkeyed_refused={key_gate_report['refused_rows']})")

                # [Drop report] What the WRITE discards is a different question from what
                # the gate refuses, and 94954cb built the channel for it. Asking for it
                # here costs one dict and turns "the chain reported success and the row
                # has no identity" into a named table, transaction, column and count.
                drop_report = {}

                # Apply updates
                #
                # [OUTBOX-4] The DERIVED write is bulk too: a 10M-row dt_log file
                # produces ~10M dt_map rows, so leaving this side per-row would leave
                # half the outbox volume standing. Nothing a user sees depends on
                # these events - the chain's own WS broadcast is built from
                # `apply_batch_updates`' return values, not from the outbox, and the
                # chain worker filters its own events out as circular. The graph
                # materializer is their one real consumer and it takes the collapsed
                # shape through `resync_table(row_ids=...)`.
                #
                # 🔴 SCOPED TO THIS ONE CALL, not to the enclosing block. This is an
                # async function and the block below contains the map-meta and
                # enrichment hooks; a mode token held across an `await` (or across a
                # hook that writes on a human's behalf) is how a human-visible write
                # collapses by accident - the one thing the design says must never
                # happen. The narrowest possible scope is the whole guarantee.
                # Per TABLE, because a group writing several targets has to be able to
                # say WHICH one it waited on - one number for "the writes" would leave the
                # next question unanswerable without another round of measuring.
                with (alignment_batch_counts.stage("write:%s" % target_table),
                      outbox_mode(event_constants.OUTBOX_MODE_COLLAPSED)):
                    results, changed_cells, created_logs, deleted_row_ids = crud.apply_batch_updates(
                        db, target_table, batch_data, drop_report=drop_report)

                if drop_report.get("dropped_cells") or drop_report.get("empty_rows_suppressed"):
                    logger.warning(
                        f"⚠️ [Chain Write Discard] Table: '{target_table}' | TX: "
                        f"'{chain_tx_id}' | rule(s): "
                        f"{', '.join(sorted(rules_by_target.get(target_table, ()))) or '<unknown>'} | "
                        f"{drop_report['dropped_cells']} cell(s) on "
                        f"{drop_report['rows_affected']} row(s) were dropped "
                        f"({drop_report['by_reason']}, columns {sorted(drop_report['by_column'])}); "
                        f"{drop_report['empty_rows_suppressed']} row(s) were not created "
                        f"because every key they carried was dropped. Fix "
                        f"config/table_config.json or the mapper's column names.")

                # [Retraction] Remove what THIS SOURCE owns and no longer derives.
                #
                # 🔴 THIS IS WHAT LETS SEVERAL SOURCES SHARE ONE MAP. `replace_map`
                # removes by map, and once a map key is the physical unit rather than the
                # acquisition unit, several jobs converge on one map - so a purge scoped
                # to the map would delete a sibling job's cells to correct this one's.
                # `plan_retraction` selects POSITIVELY by the source column that travels
                # on every derived cell, so a sibling's rows are not in the population it
                # considers at all.
                #
                # Runs AFTER the write, deliberately: the keys it spares are the keys the
                # write composed, read back off the items the write mutated. Planning it
                # before the write would mean guessing at them.
                #
                # Contained like the M3 and enrichment hooks below and for the same
                # reason - except that a failure here leaves STALE ROWS, which is the
                # conservative direction. It never leaves a hole.
                with alignment_batch_counts.stage("retraction"):
                    if retract:
                        try:
                            source_column, source_value = retract
                            derived_keys = dt_map_derivation.derived_keys_of(
                                batch_data.updates, target_table, source_column)
                            plan = dt_map_derivation.plan_retraction(
                                db, target_table, source_column, source_value, derived_keys,
                                #: 선언을 읽는 것은 «규칙을 쥔 여기»다 — 순수 함수는 값만 받는다.
                                slow_warn_ms=event_constants.slow_warn_ms(
                                    (rule or {}).get("slow_warn_ms"),
                                    (rule or {}).get("name") or "<unnamed rule>"))
                            logger.info("%s", dt_map_derivation.format_retraction_summary(plan))
                            if plan.get("declined"):
                                logger.warning(
                                    f"⚠️ [DtMapRetraction] Table: '{target_table}' | TX: "
                                    f"'{chain_tx_id}' | {source_column}='{source_value}' | "
                                    f"DECLINED: {plan['declined']['reason']}. Stale rows were "
                                    f"LEFT IN PLACE; nothing was deleted.")
                            elif plan.get("delete_row_ids"):
                                n = dt_map_derivation.apply_retraction(db, plan)
                                # The rows are gone from the database; a client that is not
                                # told still draws them. Folded into the SAME delete event the
                                # replace_map path already emits rather than a second one.
                                deleted_row_ids = list(deleted_row_ids or []) + list(
                                    plan["delete_row_ids"])
                                logger.info(
                                    f"🔄 [DtMapRetraction] Table: '{target_table}' | TX: "
                                    f"'{chain_tx_id}' | {source_column}='{source_value}' | "
                                    f"retracted {n} stale row(s), protected "
                                    f"{plan.get('protected', 0)} human-touched row(s)")
                        except Exception as retract_err:
                            logger.error(
                                f"🔴 [DtMapRetraction] Table: '{target_table}' | TX: "
                                f"'{chain_tx_id}' | retraction failed AFTER a committed write; "
                                f"stale rows may remain: "
                                f"[{type(retract_err).__name__}] {retract_err}", exc_info=True)

                # [M3] Absent-only wafer_map_metadata auto-registration for
                # chain-created maps. Uses the VALIDATED batch items (same
                # column names the upsert wrote). One existence check per
                # distinct map key per tx group; log and continue on failure.
                # Recursion-safe: the registrar refuses META_TABLE and the meta
                # table declares no map_key_columns, so meta creation can never
                # re-trigger itself.
                #
                # 🔴 WHAT `except` DOES AND DOES NOT BUY (corrected 2026-07-30).
                # `crud.apply_batch_updates` DOES commit (crud.py, end of the
                # `transaction_context` block), so the chain rows above really
                # are durable before these hooks run. But catching the exception
                # is NOT the same as containing the failure: on PostgreSQL a
                # failed statement aborts the transaction, and everything the
                # worker does afterwards on this session — including
                # `process_pending_groups`' commit of `processed_chain=True` —
                # then fails or silently rolls back, so the group is replayed
                # forever without the retry quarantine ever advancing.
                # Containment has to happen where the statement runs, which is
                # why `enrichment_config._isolated_execute` wraps every
                # reference query in a SAVEPOINT.
                # [Enrichment ①] Absent-only automatic confirmation of SINGLE
                # candidates for this rule's target fields: runs on the VALIDATED
                # batch items after the committed write, per-rule opt-in (default
                # OFF), and a failure here is logged rather than propagated. The
                # note directly above says what that `except` does NOT protect
                # against — it was written for the map-meta hook that stood here
                # until 2026-09-07 and it holds for this one unchanged.
                # Not a loop: writes land on the DERIVED table while the
                # enrichment rule triggers on the SOURCE table, and the
                # absent-only gate makes a second pass a no-op regardless.
                with alignment_batch_counts.stage("enrichment hook"):
                    try:
                        ac = enrichment_candidates.AutoConfirmCollector(target_table)
                        if ac.active:
                            ac.collect(batch_data.updates)
                            ac_stats = ac.flush(db)
                            if ac_stats.get("confirmed"):
                                logger.info(
                                    f"[Enrichment ①] Auto-confirmed {ac_stats['confirmed']} single "
                                    f"candidate(s) on '{target_table}' (source "
                                    f"'{enrichment_candidates.SOURCE_NAME}', lowest priority)")
                    except Exception as ac_err:
                        logger.error(f"[Enrichment ①] Auto-confirm failed for '{target_table}' (chain write unaffected): {ac_err}")

                # 5. Collect WebSocket broadcast messages (dispatched AFTER commit, fire-and-forget).
                #    이벤트명/페이로드 형식은 절대 변경하지 않고 타이밍만 커밋 이후로 미룬다.
                with alignment_batch_counts.stage("broadcast build"):
                    try:
                        cfg = crud.TABLE_CONFIG.get(target_table, {})
                        col_types = cfg.get("column_types", {})
                        user_cols = [c for c in col_types.keys() if c not in ["created_at", "updated_at"]]

                        # [P1b] Fourth copy of the discarded item build. Above the threshold the
                        # message below carries only `change_count`, so every item here is
                        # thrown away - and building one is not free: `crud.apply_batch_updates`
                        # commits, `expire_on_commit` is true, and `row.created_at` is the first
                        # attribute read, so each row is reloaded by its own SELECT before the
                        # O(cols) wrapping loop even starts. This site has no metadata merge
                        # (the main.py endpoints do), so its whole bill IS those reloads.
                        #
                        # ⚠️ Same predicate, moved. The loop appends exactly one item per entry
                        # of `results`, unconditionally, so `len(msg_items) == len(results)`.
                        # A `continue` added to that loop breaks the equality and this must
                        # move back.
                        needs_items = len(results) <= BROADCAST_ITEM_LIMIT
                        msg_items = []
                        for row, is_new in (results if needs_items else ()):
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

                        if not needs_items:
                            # len(msg_items) before; empty by construction on this arm now.
                            msg = event_constants.batch_refresh_message(
                                target_table, len(results),
                                transaction_id=chain_tx_id,
                                created_logs=serialized_logs,
                                total_log_count=total_log_count)
                        else:
                            msg = {
                                "event": "batch_row_upsert",
                                "table_name": target_table,
                                "items": msg_items,
                                # 표준 계약 필드 — «항상» 실린다(§event_constants `:185`: 0 과
                                # 「키 없음」은 다른 사실이다). 이 발신자«만» 안 싣고 있었고,
                                # 그래서 이 경로에서만 「체인이 몇 칸을 바꿨나」가 «말해지지 않았다».
                                # 🔴 `len(results)` 가 아니라 «이 메시지가 싣고 있는 수»다. 지금은
                                #    둘이 같지만(위 불변 주석), 그 불변이 깨지는 날 이 수는 메시지에
                                #    대해 계속 참이고 `len(results)` 는 과대가 된다.
                                "change_count": len(msg_items),
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
            # Reset with the others: a depth left set would stamp the NEXT write, and the
            # next write may not be the chain's at all.
            request_chain_depth.reset(token_depth)

    return True, None, broadcast_messages


def _log_alignment_group_work(tx_id, summary) -> None:
    """One line saying how much alignment work this group asked for (S-94, 판정 235).

    🔴 A VALUE, NOT AN INFERENCE. Whether a group's reference resolutions REPEAT is a
    property of its data - no config file can answer it - and 「큰 깊이는 값으로 보임」 is the
    standing rule that says such a depth belongs on the screen rather than in somebody's
    arithmetic. `distinct_maps` against `reference_resolutions` is exactly the number that
    decides whether caching the reference across a group is worth anything.

    ⚠️ SILENT FOR A GROUP THAT DID NONE. Most chain groups never touch alignment, and a
    line of zeros for each of them would bury the ones that did - the log equivalent of a
    screen explaining what it is not showing.
    """
    if not summary or not summary.get("view_builds"):
        return
    phases = summary.get("phases") or {}
    stages = summary.get("stages") or {}
    write_steps = summary.get("write_steps") or {}
    # The write steps are subtracted from the `write:*` stages they sit inside, not from
    # the group's wall clock - they are a layer down, the way the phases are a layer down
    # from `mapper`.
    write_total = sum(seconds for name, seconds in stages.items()
                      if name.startswith("write:"))
    logger.info(
        "[Chain] group %s: view builds %d · reference resolutions %d · distinct maps %d "
        "· %.3f s · MACHINERY%s · unnamed %.3f s"
        " · INSIDE THE VIEW%s · unnamed %.3f s"
        " · INSIDE THE WRITE%s · unnamed %.3f s",
        tx_id, summary["view_builds"], summary["reference_resolutions"],
        summary["distinct_maps"], summary["wall_seconds"],
        "".join(" · %s %.3f s" % (name, seconds)
                for name, seconds in sorted(stages.items())) or " (none named)",
        max(summary["wall_seconds"] - sum(stages.values()), 0.0),
        "".join(" · %s %.3f s" % (name, seconds)
                for name, seconds in sorted(phases.items())) or " (none named)",
        max(stages.get("mapper", summary["wall_seconds"]) - sum(phases.values()), 0.0),
        "".join(" · %s %.3f s" % (name, seconds)
                for name, seconds in sorted(write_steps.items())) or " (none named)",
        max(write_total - sum(write_steps.values()), 0.0))


async def process_chain_transaction_group(tx_id, events, db, rules):
    """Run one group off the event loop.

    🔴 판정 193. The name, the signature and the 3-tuple are unchanged because thirteen
    tests and one production caller address this function - what changed is which thread
    the work happens on. See `_process_chain_transaction_group_sync` for the measurement.
    """
    return await asyncio.to_thread(
        _process_chain_transaction_group_sync, tx_id, events, db, rules)


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
        internal_event_client.internal_event_session()
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
        # 🔴 «읽기»도 순서에 걸린다. 앞선 그룹이 실패한 표를 이 그룹이 «읽으면», 그 답은
        #    낡은 값 위에서 나오고 오류가 «안 난다» — 선언된 교차 다섯이 그 모양이었다.
        # ⚠️ 실측(출하 아홉): 어느 규칙에서도 `target_table` 이 자기 «읽기 집합 안»에 없다.
        #    그래서 읽기«만»으로 바꾸면 오늘의 미룸이 통째로 «사라진다» — 대체가 아니라 맞바꿈이다.
        #    합집합이라야 오늘의 판단이 «그 안»에 들어오고, 과잉 미룸은 안전하다.
        group_touches = group_targets | _group_read_tables(events_in_tx, rules)

        # 순서 보존 가드: 앞선 실패 그룹이 «쓴» 표를 건드리는(읽거나 쓰는) 그룹은 이번 배치에서
        # 보류한다. (retry_count를 올리지 않고 processed_chain=False 유지 → 다음 배치에서 재시도)
        if blocked_targets and (group_touches & blocked_targets):
            logger.info(
                f"[HOL Guard] Deferring tx '{tx_id}' this batch: table(s) "
                f"{sorted(group_touches & blocked_targets)} held by an earlier failed group."
            )
            continue

        # Process transaction group atomically
        t_mapper_start = time.monotonic()
        # 🔴 THE GROUP IS THE BOUNDARY, AND ONLY THIS LOOP KNOWS IT (S-94, 판정 235).
        # The scope is a `contextvars` one, so it reaches the sync body `to_thread` runs and
        # reaches nothing else - a concurrent group or a route in this process counts into
        # its own scope or into none.
        with alignment_batch_counts.counting_group() as alignment_summary:
            success, error_reason, broadcast_messages = await process_chain_transaction_group(tx_id, events_in_tx, db, rules)

            if success:
                t_mapper_done = time.monotonic()
                has_messages = bool(broadcast_messages)
                # commit 시 expire_on_commit으로 속성이 만료되므로 id를 커밋 전에 캡처(재조회 N+1 방지).
                event_ids = [event.id for event in events_in_tx]
                for event in events_in_tx:
                    mark_processed(event, "SUCCESS")
                    # [Reliability F1] 통지할 메시지가 없는 no-op 그룹은 전달할 것이 없으므로 즉시 전달 확정(스윕 제외).
                    # 메시지가 있는 그룹은 broadcast_at을 NULL로 두고, 통지 성공 시 _dispatch_broadcasts가 스탬프한다.
                    if not has_messages:
                        event.broadcast_at = func.now()
                with alignment_batch_counts.stage("commit"):
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
                with alignment_batch_counts.stage("rollback"):
                    db.rollback()

                # Increment retry count for all events in the failed transaction group
                failed_permanently_count = 0
                retrying_count = 0
                max_retry_num = 0
                # 한 번 읽어 «판정·사유·로그»가 같은 수를 본다.
                attempts_cap = max_group_attempts()

                reexpanded_rows = 0
                for event in events_in_tx:
                    event.retry_count += 1
                    max_retry_num = max(max_retry_num, event.retry_count)
                    if event.retry_count >= attempts_cap:
                        pay_dict = get_payload_dict(event)
                        payload_copy = dict(pay_dict) if pay_dict else {}
                        reason = error_reason or (
                            f"Mapper execution failed in tx group {tx_id} after "
                            f"{attempts_cap} attempt(s).")

                        # [OUTBOX-4] COARSE ON THE HAPPY PATH, FINE ON THE FAILURE PATH.
                        # A collapsed event covers up to 1,000 rows, so quarantining it
                        # whole would take 999 innocent rows with the poison one. At the
                        # quarantine boundary - and only here, after the cheap chunk-level
                        # retries are exhausted - it re-expands into per-row events, each
                        # its own transaction group, so the next passes narrow the failure
                        # to the row that actually breaks. Never quarantine a chunk without
                        # having tried to narrow it first.
                        if event_constants.is_collapsed_payload(pay_dict):
                            try:
                                n = outbox_expand.reexpand_collapsed_event(db, event, pay_dict, reason)
                            except Exception as rx_err:
                                n = 0
                                logger.error(
                                    f"[OUTBOX-4] re-expansion of collapsed event {event.event_uuid} "
                                    f"failed; falling back to whole-chunk quarantine: {rx_err}",
                                    exc_info=True)
                            if n:
                                reexpanded_rows += n
                                payload_copy["error_log"] = {
                                    "failed_at": datetime.now().isoformat(),
                                    "reason": reason,
                                    "reexpanded_into": n,
                                }
                                mark_processed(event, "FAILED")
                                event.payload = payload_copy
                                failed_permanently_count += 1
                                continue

                        mark_processed(event, "FAILED")   # Quarantine from worker queries
                        payload_copy["error_log"] = {
                            "failed_at": datetime.now().isoformat(),
                            "reason": reason
                        }
                        event.payload = payload_copy
                        failed_permanently_count += 1
                    else:
                        event.status = "RETRYING"
                        retrying_count += 1

                with alignment_batch_counts.stage("commit"):
                    db.commit()

                if reexpanded_rows:
                    logger.warning(
                        f"Transaction {tx_id}: {reexpanded_rows} per-row retry event(s) written "
                        # No em dash: the production console is Korean Windows (cp949)
                        # and one unencodable character deletes the whole log line.
                        f"from failed collapsed chunk(s). The failure will be narrowed to the "
                        f"offending row(s) instead of quarantining whole chunks."
                    )
                if failed_permanently_count > 0:
                    logger.error(f"Transaction {tx_id} permanently failed: {failed_permanently_count} events moved to FAILED status.")
                if retrying_count > 0:
                    logger.warning(f"Transaction {tx_id} marked for retry: {retrying_count} events set to RETRYING status ({max_retry_num}/{attempts_cap}).")

                failed_any = True
                # [Latency Fix #5] break 제거 — 동일 target_table 그룹만 보류(순서 보존)하고 나머지는 계속 처리.
                blocked_targets |= group_targets
        _log_alignment_group_work(tx_id, alignment_summary())

    # [Latency SLO] 배치의 모든 성공 그룹 통지를 group_order 순서대로 **인라인** 발사한다.
    #   배경 태스크(create_task) 예약은 폴링 루프의 동기 구간에 이벤트 루프가 블로킹되는 동안 기아 상태가 되어
    #   통지가 수 초 지연되고 스윕 오발동(전체 리프레시 폭주)을 유발했다. commit은 위에서 이미 완료됐으므로
    #   인라인 await가 데이터 경로를 지연시키지 않는다(F2 순서 보존·F1 스탬프 로직은 _dispatch_broadcasts 내 유지).
    if pending_broadcasts:
        # 🔴 PER BATCH, NOT PER GROUP, SO IT IS ITS OWN LINE (S-151, 판정 261). The group
        # line's stages have to sum to one group's wall clock; this fires once for every
        # group in the batch, so charging it to any single group would make that sum a
        # number no arithmetic could check.
        t_dispatch = time.monotonic()
        await _dispatch_broadcasts(pending_broadcasts, db_session_factory)
        logger.info("[Chain] batch: broadcast dispatch %.3f s · groups %d",
                    time.monotonic() - t_dispatch, len(pending_broadcasts))

    return failed_any

async def sweep_undelivered_broadcasts(db, rules, db_session_factory):
    """[Reliability F1 안전망] 커밋됐으나 통지 미확정(broadcast_at IS NULL)인 행을 주기적으로 감지해
    영향 테이블에 table-level batch_refresh_required를 발사하고 broadcast_at을 확정한다.

    발사 대상 = (체인 규칙이 지목하는 target_table) ∪ (그 행이 기록된 table_name).
    후자가 없으면 체인 규칙의 target 이 아닌 테이블은 복구 자체가 불가능하다 —
    이 스윕은 워처(run_watcher.post_event)가 통지 실패 시 남기는 durable 마커의
    수거자이기도 하므로, 그 마커의 table_name 이 곧 새로고침 대상이다.

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

    # 🔴 THE SAME SPELLING THE WRITER USES. The two sides used to name the marker's shape
    # independently, so a change to either made the sweeper silently stop collecting what
    # the writer still produced - see the note in `event_constants`.
    stale = db.query(DatabaseOutbox).filter(
        DatabaseOutbox.processed_chain == event_constants.UNDELIVERED_MARKER_PROCESSED_CHAIN,
        DatabaseOutbox.status == event_constants.UNDELIVERED_MARKER_STATUS,
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

    # [Broadcast Recovery] 미전달 행이 **기록된 테이블 자신**도 항상 새로고침 대상이다.
    #   기존 구현은 chain target 만 대상으로 삼았고, 어떤 규칙에도 매핑되지 않는 행
    #   (규칙 비활성, 트리거 아님, 그리고 워처가 남기는 BROADCAST_RECOVERY 마커)은
    #   "무한 재스윕 방지"를 이유로 **아무것도 발사하지 않은 채 broadcast_at 만 찍고** 반환했다.
    #   durable 마커는 소비되고 통지는 사라지므로, 체인 룰의 target 이 아닌 테이블에 대한
    #   쓰기는 복구 경로가 아예 없었다("행은 들어왔는데 화면은 끝내 모른다").
    #   table_name 은 NOT NULL 이므로 이 합집합은 항상 비어 있지 않다 → 스윕은 언제나
    #   발사 후 확정(stamp)으로 끝나고, 확정으로 끝나는 한 재스윕은 구조적으로 불가능하다.
    #   (무한 스윕을 막는 것은 "발사 안 함"이 아니라 "확정을 찍는 것"이다.)
    source_tables = {e.table_name for e in stale if e.table_name}
    refresh_targets = affected_targets | source_tables

    if not refresh_targets:
        # 테이블명조차 없는 병리적 행(방어) → 재스윕만 막고 종료.
        logger.warning(
            f"[Broadcast Recovery] {len(stale_ids)} undelivered row(s) name no table at all; "
            "stamping them so the sweep cannot spin on rows it can never announce."
        )
        db.query(DatabaseOutbox).filter(DatabaseOutbox.id.in_(stale_ids)).update(
            {DatabaseOutbox.broadcast_at: func.now()}, synchronize_session=False)
        db.commit()
        return

    # table당 1건 dedup된 batch_refresh_required 발사(기존 계약 재사용). 전부 성공해야 확정한다.
    all_ok = True
    for tgt in sorted(refresh_targets):
        # change_count 0 은 «표준 계약 필드»(정보성). 스윕 복구는 테이블 전체 새로고침 신호다.
        msg = event_constants.batch_refresh_message(tgt, 0)
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
        f"[Reliability F1] Recovery sweep re-delivered {len(refresh_targets)} table refresh(es) "
        f"for {len(stale_ids)} undelivered row(s): {sorted(refresh_targets)}"
    )

# [Schema] Digest of crud.undeclared_column_drops() for the heartbeat note.
# Only the worst offenders: the note is republished on every beat and lands in a
# ~200 byte file, so a table with 64 dropped columns must not be able to inflate it.
_DROP_NOTE_TOP_N = 5


def _undeclared_drop_note():
    """`None` while nothing is being dropped, so a healthy beat is unchanged.

    `(table, None)` keys mean "drops past this table's distinct-column budget", i.e.
    counted but no longer attributable to a column name - rendered as `<over budget>`
    rather than dropped from the digest, because a total that silently stops adding
    up is how the original defect hid.
    """
    from database import crud

    drops = crud.undeclared_column_drops()
    if not drops:
        return None
    top = sorted(drops.items(), key=lambda kv: -kv[1])[:_DROP_NOTE_TOP_N]
    parts = [f"{t}.{c if c is not None else '<over budget>'}={n}" for (t, c), n in top]
    if len(drops) > len(top):
        parts.append(f"(+{len(drops) - len(top)} more)")
    return f"undeclared column drops: total={sum(drops.values())} " + ", ".join(parts)


def _worker_note():
    """Everything this process needs to say through the heartbeat, or `None`.

    Two digests share one note because there is one note: the undeclared-column drops
    the WRITE made, and the unkeyed rows the GATE refused. They are different questions
    with different fixes (declare a column / fix the mapper or its source), so they are
    never summed into one number - they are joined and both named.

    `None` when both are clean, so a healthy deployment's heartbeat file is unchanged.
    """
    parts = [p for p in (_undeclared_drop_note(), chain_key_gate.note(),
                         ledger_followup.note()) if p]
    return " | ".join(parts) or None


class QueueHeadWatch:
    """Says when the loop keeps picking the SAME head and nothing drains.

    🔴 THIS IS THE SIGNATURE OF THE 2026-09-04 INCIDENT, and the reason it is worth
    instrumenting rather than guessing: 570 rows waiting, the oldest 9 minutes old, NO
    error anywhere, and "it does not clear until a restart". A loop that picks work up and
    puts nothing down looks exactly like a busy loop from outside - the only observable
    difference is that the head never moves.

    ⛔ A NORMAL LOOP MUST STAY SILENT. The queue draining, the queue being empty, and the
    head advancing are all ordinary; this speaks only when the head has been the same row
    for `stall_after` seconds WHILE still being fetched, and then at most once per that
    interval. An instrument that talks during healthy operation gets filtered out, and
    then it is not an instrument.

    ⚠️ THE THRESHOLD IS NOT A NEW NUMBER. It is `heartbeat.DEFAULT_STALE_AFTER_SEC`, which
    this system already uses for "a worker that is not progressing".
    """

    def __init__(self, stall_after=None, now=None):
        self.stall_after = (heartbeat.DEFAULT_STALE_AFTER_SEC if stall_after is None
                            else stall_after)
        started = time.time() if now is None else now
        self.started_at = started
        self.reloaded_at = None
        self.head_id = None
        self.head_since = started
        self.last_said = None

    def note_reload(self, now=None):
        """A SYSTEM_RELOAD re-imported the mappers. Recorded because "a restart clears it"
        is the operator's own description of this failure, and the distance from the last
        reload is what turns that sentence into a number."""
        self.reloaded_at = time.time() if now is None else now

    def observe(self, picked, head_id, now=None):
        """One iteration. Returns a sentence to log, or None to stay quiet."""
        now = time.time() if now is None else now

        if not picked:
            # An empty queue is not a stall - there is nothing to drain.
            self.head_id, self.head_since = None, now
            return None

        if head_id != self.head_id:
            self.head_id, self.head_since = head_id, now
            return None

        stuck_for = now - self.head_since
        if stuck_for < self.stall_after:
            return None
        if self.last_said is not None and (now - self.last_said) < self.stall_after:
            return None
        self.last_said = now

        since_reload = ("never" if self.reloaded_at is None
                        else "%.0fs" % (now - self.reloaded_at))
        return ("[Chain Loop] the queue head has not moved for %.0fs: outbox#%s is still "
                "first and %d row(s) were fetched again with no error. Uptime %.0fs, last "
                "mapper reload %s. If a restart clears this, the state is in this process "
                "(module cache) rather than in the data."
                % (stuck_for, head_id, picked, now - self.started_at, since_reload))


def another_chain_loop_is_running(now=None):
    """Is a DIFFERENT, LIVE process already running the chain loop? Returns its identity
    or None.

    🔴 IT USES THE HEARTBEAT, NOT A NEW MECHANISM. `main.py` starts this loop from the web
    server's startup event unconditionally, so running `run_chain_worker.py` beside it
    produces TWO loops on one queue - measured 2026-09-04, two pids alternating in one
    heartbeat file, the same rows picked up twice, and a restart of the standalone worker
    leaving the older code live inside uvicorn. The heartbeat already answers "who is
    beating and how long ago", which is exactly the question, so nothing new is declared.

    🔴 IT IS DELIBERATELY PERMISSIVE. Three conditions must ALL hold before it says yes:
    the beat is FRESH, the pid is NOT this process, and that pid is ALIVE. If any of them
    cannot be established - no psutil, unreadable file, a beat older than the stale
    threshold - the answer is None and the loop starts, which is today's behaviour. The
    common case this must not break is a RESTART: a killed worker leaves a heartbeat that
    stays fresh for another minute, and refusing to start then would be a false positive
    on the most ordinary operation there is. Checking that the pid is alive is what
    separates "someone is running" from "someone was running".
    """
    import os as _os
    try:
        from utils import heartbeat as _hb
        entry = _hb.read_all(now=now).get("chain") or {}
    except Exception:                                            # noqa: BLE001
        return None
    pid = entry.get("pid")
    if entry.get("stale") or not pid or pid == _os.getpid():
        return None
    try:
        import psutil
        if not psutil.pid_exists(int(pid)):
            return None
    except Exception:                                            # noqa: BLE001
        # Cannot tell whether it is alive. Start, rather than refuse on a guess.
        return None
    return "pid %s, last beat %.1fs ago" % (pid, entry.get("age_seconds") or 0.0)


#: What the follow-up loop waits when the queue is empty, whatever the declared pace says.
#: A pace of `fast` rests for zero seconds, and zero seconds around an empty deque is a hot
#: loop -- the pace answers "how hard may I push while there is work", not "how often do I
#: look".
FOLLOWUP_IDLE_SECONDS = 1.0


def _drain_ledger_followup_sync(db_session_factory):
    """One follow-up batch, in a thread. The session is this call's and closes with it."""
    from ledger.setup import load_setup

    db = db_session_factory()
    try:
        return ledger_followup.drain_once(db.get_bind(), load_setup())
    finally:
        db.close()


def _measure_one_source_sync(db_session_factory, source, setup=None):
    """One source's census, in a thread. The session is this call's and closes with it.

    🔴 THE PACED TICK DOES NOT SCAN (S-122). `exact_rows=False` makes the relation count
    the planner's free estimate instead of a `count(*)` over the whole relation - measured
    on this box 1.18 s over 1.43M rows, run per source, per tick, without resting, so on a
    production-sized table the census is never NOT scanning and every other query waits
    behind it. The number is published AS an estimate; the exact count belongs to the
    command a person runs.

    ⚠️ `setup` IS PASSED IN, NOT LOADED HERE. Compiling the whole declaration costs 91 ms
    on this box and it was being done once per SOURCE - fifteen times a lap for an answer
    that cannot change inside one lap.
    """
    from ledger import backfill as ledger_backfill
    from ledger.setup import load_setup
    from ledger.store import LedgerStore

    db = db_session_factory()
    try:
        engine = db.get_bind()
        return ledger_backfill.measure_and_store(
            engine, setup if setup is not None else load_setup(), source,
            LedgerStore(engine), exact_rows=False)
    finally:
        db.close()


async def run_ledger_row_census(db_session_factory):
    """Measure 「table rows · indexed · not yet translated」 per source, at the declared pace.

    🔴 IT EXISTS SO THE REQUEST PATH DOES NOT DO THIS (D5, 판정 180). Both numbers are
    scans; a declaration response that counted them would be a screen that waits for a
    ten-million-row table. This writes, `/declaration` reads, and the answer carries the
    instant it was true.

    ⚠️ ONE SOURCE PER UNIT, NOT ONE SWEEP PER CYCLE. The pace's `units_per_cycle` is
    counted in SOURCES, so an operator slowing this down slows the individual counts rather
    than the gap between full sweeps -- which is the knob that matters when the concern is
    「this is crowding the database right now」.

    ⛔ ONE SOURCE'S FAILURE COSTS THAT SOURCE ONLY, and it is named. A source whose
    relation was dropped must not silence the fourteen after it.
    """
    import pacing
    from ledger.backfill import ROW_CENSUS_JOB

    while True:
        try:
            units, rest = pacing.job_pace(ROW_CENSUS_JOB)
        except Exception as exc:
            logger.warning("[LedgerCensus] pace unreadable, using the default: %s", exc)
            units, rest = 1, 60.0
        # 🔴 ONE COMPILE PER LAP, NOT ONE PER SOURCE (S-122). `load_setup()` compiles the
        # whole declaration - 91 ms on this box - and it cannot change inside a lap, so
        # fifteen sources were paying for fifteen identical answers.
        setup = None
        try:
            setup = await asyncio.to_thread(_load_setup_sync, db_session_factory)
            sources = sorted(setup.snapshot.source_plans)
        except Exception as exc:
            logger.warning("[LedgerCensus] the declaration could not be read: %s", exc)
            sources = []
        measured_now = 0
        lap_started = time.monotonic()
        measured_seconds = 0.0
        for source in sources:
            source_started = time.monotonic()
            try:
                await asyncio.to_thread(_measure_one_source_sync, db_session_factory,
                                        source, setup)
            except Exception as exc:
                logger.warning("[LedgerCensus] %s failed: %s", source, exc)
            # ⚠️ THE FAILING SOURCE COSTS THE DATABASE TOO, so it is timed like any
            # other - counting only the successes would report a lap as cheaper than
            # it was, which is the direction a pacing number must never be wrong in.
            measured_seconds += time.monotonic() - source_started
            measured_now += 1
            if units is not None and measured_now % max(units, 1) == 0:
                await asyncio.sleep(rest)
        # 🔴 THE TICK SAYS WHAT IT COST (S-122 gate). A background job that crowds the
        # database is invisible until somebody correlates two graphs; a line per lap with
        # its own wall clock is the value 「큐 깊이는 값으로 보임」 asks for, and it is what
        # tells an operator whether slowing the pace actually helped.
        if sources:
            logger.info("[LedgerCensus] lap: %d source(s) in %.3fs, measured %.3fs "
                        "(rest %.0fs between, "
                        "relation rows are planner estimates - `python -m ledger census` "
                        "counts)", len(sources), time.monotonic() - lap_started,
                        measured_seconds, rest)
        await asyncio.sleep(rest if sources else max(rest, 60.0))


def _load_setup_sync(db_session_factory):
    """The compiled declaration, once, in a thread. The session closes with the call."""
    from ledger.setup import load_setup

    db = db_session_factory()
    try:
        return load_setup()
    finally:
        db.close()


async def run_ledger_followup(db_session_factory):
    """Drain the ledger follow-up queue at the declared pace, BESIDE the chain loop.

    🔴 THE PACE IS THIS LOOP'S, NOT `rescope`'S. `rescope` has no pacing of its own and
    keeps none (one seat, unchanged): a batch runs whole and then this rests. Pacing inside
    the re-translation would throttle one molecule's write, which is not what needs to
    yield -- the QUEUE is (ruling 129-ter).

    🔴 THE DECLARATION IS RE-READ EVERY CYCLE. An operator who slows this down at 2am
    edits one cell in `pacing.json`, which is the reason that file exists rather than a
    constant; re-reading once per cycle is what makes "no restart" true.

    ⛔ IT NEVER DIES QUIETLY. Anything this raises is named and the loop continues: the
    queue is loss-tolerant by design, so one bad batch costs promptness, and a task that
    ended silently would cost every batch after it with nothing on screen.
    """
    import pacing

    while True:
        try:
            units, rest = pacing.job_pace(ledger_followup.FOLLOWUP_JOB)
        except Exception as exc:
            logger.warning("[LedgerFollowUp] pace unreadable, using the default: %s", exc)
            units, rest = None, FOLLOWUP_IDLE_SECONDS
        drained = 0
        while ledger_followup.queue_depth() and (units is None or drained < units):
            try:
                await asyncio.to_thread(_drain_ledger_followup_sync, db_session_factory)
            except Exception as exc:
                logger.warning("[LedgerFollowUp] batch failed: %s", exc)
            drained += 1
        await asyncio.sleep(rest if drained else max(rest, FOLLOWUP_IDLE_SECONDS))


def _ensure_ledger_schema_sync(db_session_factory):
    """Bring the ledger's own schema up to date. Catalogue-first and idempotent.

    🔴 S-88 — WITHOUT THIS, A LANDED COLUMN NEVER REACHES A LIVE DATABASE.
    `schema.CURSOR_ADDITIONS` is the ADD COLUMN list, `ensure_schema` applies it, and
    MEASURED 2026-09-09 its only callers were seed scripts and tests: no production path ran
    it at all. The procedure that used to — 「배포 뒤 소스마다 백필 한 번」 — went away with the
    cursor read path (S-76), and the ensure it carried went with it, unnoticed because
    nothing had needed a new column since.

    S-58 is what found it: the census column landed, the job ran every tick, and every tick
    failed on a column that did not exist. The fix is not that column; it is that a landed
    column must reach live WITHOUT a person running one line by hand.

    ⚠️ IT DOES NOT TAKE THE PROCESS DOWN. This daemon also does chain work that owes the
    ledger nothing, so a ledger schema that cannot be ensured costs the ledger jobs and is
    named — loudly, once, at startup, where an operator is already reading.
    """
    from ledger.store import LedgerStore

    db = db_session_factory()
    try:
        LedgerStore(db.get_bind()).ensure_schema()
    finally:
        db.close()


def _restamp_moved_fingerprints_sync(db_session_factory):
    """Move the stored fingerprint of every cursor whose DECLARATION did not change.

    \U0001f534 S-87, AND IT IS THE HALF THAT MAKES THE OTHER HALF SAFE. A cursor whose stored
    string differs from the current one is REFUSED (`cursor_snapshot_reset_required`), which
    is correct when the declaration moved and is a full stop when only the grammar did.
    Measured 2026-09-09: removing one unused descriptor field moved all 15 fingerprints, the
    operator's ledger stopped at the previous day's backfill, and it took a person running
    `scripts/ledger_restamp_cursor.py --apply` by hand to start again. A landed change must
    reach live WITHOUT that line, for the same reason S-88 exists three functions up.

    \u26d4 THE POSITION IS NOT TOUCHED, and that is why this is safe to do unattended.
    `restamp_cursor` writes `translator_ver` and nothing else - not `cursor_value`, not the
    counters, not one atom - so the next batch reads the rows AFTER the unchanged position.
    A reset or a rewind would re-read rows that are already in the ledger, and under a new
    fingerprint they would land AGAIN rather than dedupe: on millions of rows, doubled.

    \u26a0\ufe0f IT DECIDES NOTHING OF ITS OWN. `LedgerStore.restamp_decision` is the one
    predicate, shared with the script, so a v1-shaped cursor is refused here exactly as it is
    there rather than being quietly moved by the daemon that runs unattended.

    Every move is NAMED in the log. A fingerprint that changes silently is a fingerprint
    nobody can audit, and this runs on every boot.
    """
    from ledger.setup import load_setup
    from ledger.setup_registry import cursor_translator_version
    from ledger.store import LedgerStore

    db = db_session_factory()
    try:
        setup = load_setup()
        store = LedgerStore(db.get_bind())
        read = store.connection()
        try:
            stored_rows = {source: store.read_cursor(read, source)
                           for source in setup.snapshot.source_plans}
        finally:
            read.close()
        moved, refused = [], []
        for source in sorted(stored_rows):
            existing = stored_rows[source]
            wanted = cursor_translator_version(setup.snapshot, source)
            stored = existing.get("translator_ver") if existing else None
            verdict, reason = store.restamp_decision(stored, wanted)
            if verdict == "refused":
                refused.append(f"{source} ({reason})")
                continue
            if verdict != "restamp":
                continue
            if store.restamp_cursor(source, expect=stored, translator_ver=wanted):
                moved.append(f"{source}: {stored} -> {wanted} "
                             f"(position stays {existing.get('cursor_value')!r})")
            else:
                refused.append(f"{source} (row changed under us)")
        if moved:
            logger.info("[Ledger] re-stamped %d cursor(s) whose declaration did not "
                        "change: %s", len(moved), " | ".join(moved))
        if refused:
            logger.warning("[Ledger] %d cursor(s) were NOT re-stamped: %s",
                           len(refused), " | ".join(refused))
    finally:
        db.close()


def _ensure_alignment_decision_key_indexes_sync(db_session_factory):
    """Build the index an alignment rule's per-job query needs (S-94, 판정 239).

    🔴 THE BUILDER WAS WIRED ONLY INTO CONFIG RELOAD, WHICH IS NOT A BOOT. It sat
    beside `ensure_map_key_indexes` in `create_missing_dynamic_tables`, and that runs on a
    reload - so a deployment could restart, find the index still missing, and go on scanning
    109,877 rows per view build. 「착지는 배선이 아니다」, measured on my own change one commit
    after writing it down.

    ⚠️ IT ONLY WEAKENS, so unlike its neighbour above it needs no surplus count: an
    index that is not unique cannot fail on the rows already there. What it can do is find
    nothing to build, which is the ordinary outcome on every boot after the first.
    """
    from database import models

    db = db_session_factory()
    try:
        created = models.ensure_alignment_decision_key_indexes(db.get_bind())
    finally:
        db.close()
    # ⚠️ IT SAYS SO EITHER WAY (판정 239). A line only on the build would make
    # "nothing was built" and "the ensure never ran" the same silence - and this round's
    # first boot proved that matters: the ensure DID run and failed by name, and the only
    # reason anybody saw it was that the failure spoke.
    if created:
        logger.info("[Chain] built %d alignment decision-key index(es): %s",
                    len(created), ", ".join(created))
    else:
        logger.info("[Chain] alignment decision-key indexes are already in place.")


def _analyze_stale_tables_sync(db_session_factory):
    """`ANALYZE` every catalogued table whose statistics the database says are stale (S-130).

    🔴 S-124 ② ONLY COVERS TABLES THAT ARE LOADED AGAIN. It re-analyses after a big load,
    so a relation that took 440,000 rows BEFORE that landed keeps planning against
    statistics from whenever it was last analysed - and production is exactly that shape.
    Nothing announces it: the rows are right, the index is there, and only the plan is
    wrong.

    ⚠️ THE DATABASE ALREADY KNOWS. `pg_stat_user_tables.n_mod_since_analyze` is the count
    of rows changed since the last analyse, so this asks rather than guesses - and a table
    under the threshold is not touched, which is every table on every boot after the first.

    ⚠️ SAME FUNCTION AND SAME THRESHOLD as the load path. Two spellings of 「is this table
    stale enough to re-analyse」 would drift, and the one that ran at boot would not be the
    one anybody had measured.
    """
    from database import crud, models
    from parsers import directory_watcher as dw

    threshold = dw.analyze_after_rows()
    if threshold <= 0:
        logger.info("[Chain] boot ANALYZE is off by declaration (analyze_after_rows=0).")
        return []

    # 🔴 THE CATALOGUE ALONE MISSES THE TABLES THAT WERE ACTUALLY STALE. Measured on this
    # box: of the four relations over the threshold, NONE was a catalogued dynamic table -
    # they were `cell_sources` (1,059,219 rows modified since its last analyse) and
    # `audit_logs`, which the grid reads on the same page as the dynamic table it is
    # showing. Scoping this to `TABLE_CONFIG` would have made it a no-op on exactly the
    # shape it was written for.
    #
    # ⚠️ STILL BOUNDED to tables THIS APPLICATION DECLARES - the dynamic catalogue plus
    # the framework models. Not "every user table", because a shared database may carry
    # relations that are not ours to touch.
    tables = set(crud.TABLE_CONFIG or {}) | set(models.Base.metadata.tables)

    # 🔴 THE LEDGER'S OWN RELATIONS ARE IN SCOPE TOO (판정 16:36). They are declared by
    # this application - `ledger/schema.py` holds their names and their DDL - and the
    # walk reads them, so a stale `ledger_source_row_ref` costs the same kind of plan
    # as a stale dynamic table. They are not in `Base.metadata` because that module
    # creates them itself.
    #
    # ⚠️ THE SPELLING IS `schema.owns_table`, NOT A SECOND LIST HERE. Monthly
    # partitions are named by month, so which ones EXIST is a fact about the
    # database; asking it about the names it just reported is how 「existing
    # partitions only」 is satisfied without generating a single month name.
    if not tables:
        return []

    db = db_session_factory()
    try:
        from sqlalchemy import text as sql_text

        rows = db.execute(sql_text(
            "SELECT relname, n_mod_since_analyze FROM pg_stat_user_tables "
            "WHERE n_mod_since_analyze >= :threshold"), {"threshold": threshold}).all()
    except Exception as exc:                                           # noqa: BLE001
        # Not PostgreSQL, or the view is unreadable. A boot must not die over statistics.
        logger.warning("[Chain] could not read table statistics, so no boot ANALYZE ran: "
                       "%s", exc)
        return []
    finally:
        db.close()

    from ledger import schema as ledger_schema

    stale = [(name, int(modified or 0)) for name, modified in rows
             if name in tables or ledger_schema.owns_table(name)]
    if not stale:
        logger.info("[Chain] statistics are current on all %d declared table(s) "
                    "(threshold %d modified rows).", len(tables), threshold)
        return []

    analysed = []
    for name, modified in sorted(stale, key=lambda item: -item[1]):
        if dw._analyze_after_load(
                name, modified,
                why="the planner was costing this table against statistics taken "
                    "before those rows arrived"):
            analysed.append(name)
    return analysed


def _ensure_dynamic_table_indexes_sync(db_session_factory):
    """Build the indexes a dynamic table's model declares but its database lacks (S-124).

    🔴 A TABLE MADE BEFORE THE DECLARATION KEEPS RUNNING WITHOUT IT. `create_all` adds
    indexes only while it creates a table, so a relation older than either of these two
    never got them - and nothing said so, because the model reads correctly and only the
    database disagrees. The grid's page query orders by `updated_at`, so on such a table it
    sorts the whole relation instead of walking an index.

    ⚠️ IT ONLY WEAKENS, so it needs no surplus count: neither index is unique, and building
    one cannot make a query wrong. What it can do is find nothing to build, which is the
    ordinary outcome on every boot after the first - and it says so either way.
    """
    from database import models

    db = db_session_factory()
    try:
        created = models.ensure_dynamic_table_indexes(db.get_bind())
    finally:
        db.close()
    if created:
        logger.info("[Chain] built %d dynamic-table index(es): %s",
                    len(created), ", ".join(created))
    else:
        logger.info("[Chain] dynamic-table indexes are already in place.")


def _ensure_human_claims_index_sync(db_session_factory):
    """Build the human-claims index, and NAME the full-table one it replaces (판정 245-b).

    🔴 CREATION IS AUTOMATIC, DELETION IS A PERSON'S (판정 243). Adding an index only
    weakens - it costs disk and write time and cannot make a query wrong - so a boot may
    build one. Dropping 5 GB is not reversible inside a maintenance window, and a box may
    be mid-replay when this line runs, so the ensure states the name, the size and the
    exact command and stops there.

    ⚠️ AND IT SPEAKS EITHER WAY. A line only when something happens makes "nothing to do"
    and "the ensure never ran" the same silence - which is exactly how the decision-key
    ensure's first failure nearly went unseen.
    """
    from sqlalchemy import text as _text

    from database import models

    db = db_session_factory()
    try:
        engine = db.get_bind()
        name, statement = models.human_claims_index_ddl()
        # 🔴 THE SAME WORDS THE OTHER THREE CALLERS USE. This read the builder's return as
        # a truth value, and when `False` came to mean "already there" the boot printed
        # `COULD NOT BE ENSURED` about an index that exists - a false line, in the opposite
        # direction from the false line the same round had just fixed.
        state = models._ensure_one_index(engine, name, statement, "human-claims")
        logger.info("[Chain] human-claims index %s: %s", name, {
            models.INDEX_BUILT: "built",
            models.INDEX_PRESENT: "already in place",
        }.get(state, "COULD NOT BE ENSURED - see the line above"))
        # ⚠️ THE LEFTOVER LOOKUP IS A REPORT, NOT A REQUIREMENT. If it cannot run, the
        # line above has already said whether the index this boot needed is there; letting
        # the lookup take that line down with it would trade a fact for a warning.
        leftover = None
        try:
            with engine.connect() as connection:
                leftover = connection.execute(_text(
                    "SELECT pg_size_pretty(pg_relation_size(c.oid)) FROM pg_class c "
                    " WHERE c.relname = :name AND c.relkind = 'i'"),
                    {"name": models.RETIRED_CLAIMS_INDEX}).scalar()
        except Exception as err:                                       # noqa: BLE001
            logger.warning("[Chain] could not check whether %s is still present: %s",
                           models.RETIRED_CLAIMS_INDEX, err)
    finally:
        db.close()
    if leftover:
        # ⛔ NOT DROPPED HERE. The size is in the line because "an index is redundant" and
        # "an index is costing you five gigabytes on every cell write" are read very
        # differently by whoever decides when the window is.
        # ⚠️ NOT "NOTHING READS IT" - that would be false and an operator would find out
        # the hard way. The parameterised half of the replay path DOES read it, and drops
        # to a parallel Seq Scan without it; measured on 34M rows, that costs seconds on a
        # path that runs by hand. What is true is the trade, so the line states the trade.
        logger.warning(
            "[Chain] %s (%s) is retired and still present: every cell write maintains it, "
            "and what still reads it is the by-hand replay path, which falls back to a "
            "scan (measured: seconds). Drop it when the box is quiet with: python "
            "migrations/drop_redundant_layering_indexes.py --apply",
            models.RETIRED_CLAIMS_INDEX, leftover)


def _ensure_business_key_unique_indexes_sync(db_session_factory):
    """Build the UNIQUE index that makes `business_key_val` an enforced identity.

    \U0001f534 판정 189 — S-88's SIBLING, WITH A GUARD S-88 DID NOT NEED. `models.py` keeps
    this column NON-unique on purpose (`create_all` does not add indexes to tables that
    already exist, so declaring it there is a no-op on exactly the databases where duplicates
    accumulate) and says the migration "belongs in the setup sequence and not only in the
    upgrade one". Measured 2026-09-09: nothing invoked it, so a fresh install enforced
    nothing — and ㉡'s identity lookup is about to lean on this index.

    \u26d4 AND IT MUST NOT BE S-88's ONE-LINER. That ensure only WEAKENS (add a column, drop
    a check) and cannot fail on existing rows. A UNIQUE index STRENGTHENS: on a table that
    already carries duplicates the build fails, so the surplus is COUNTED FIRST and a table
    that cannot take the index is NAMED and left alone. Creating nothing is the correct
    outcome there; the number is what an operator needs to decide whether to clean.

    \u26a0\ufe0f AN INVALID LEFTOVER IS NOT "ALREADY DONE". A cancelled CONCURRENTLY build
    leaves an index under the right NAME enforcing nothing, which is why the predicate is
    「a VALID unique index on exactly (business_key_val)」 and not 「a name exists」. Dropping
    that leftover is the script's job with an operator watching, not a daemon's at startup.

    Startup continues whatever happens here, exactly as it does for the ledger schema: this
    daemon also does chain work that owes none of this anything.
    """
    from migrations import add_business_key_unique_index as uq

    db = db_session_factory()
    try:
        engine = db.get_bind()
        built, refused, invalid = [], [], []
        with engine.connect() as conn:
            tables = uq.tables_with_business_key(conn)
            for table in tables:
                found = uq.existing_unique_index(conn, table)
                if found is not None:
                    if not found[1]:
                        invalid.append((table, found[0]))
                    continue
                census = uq.duplicate_census(conn, table)
                if census["surplus"]:
                    refused.append((table, census["surplus"]))
                    continue
                name = uq.unique_index_name(table)
                with engine.connect().execution_options(
                        isolation_level="AUTOCOMMIT") as write_conn:
                    verdict, detail = uq.build_index(write_conn, table, name)
                built.append((table, verdict, detail))
        for table, verdict, detail in built:
            logger.info("[Ledger] business-key unique index on %s: %s (%s)",
                        table, verdict, detail)
        # \U0001f534 NAMES AND NUMBERS, NOT A COUNT. "3 tables refused" tells an operator
        # nothing they can act on; the table and its surplus are what they clean.
        for table, surplus in refused:
            logger.warning("[Ledger] %s cannot take its business-key unique index: %d "
                           "surplus row(s) share a key. The index was NOT created and the "
                           "column is not an enforced identity there.", table, surplus)
        for table, name in invalid:
            logger.warning("[Ledger] %s carries an INVALID index %r under the unique name, "
                           "so nothing is enforced. Left alone: dropping it belongs to "
                           "scripts/migrations/add_business_key_unique_index.py with an "
                           "operator watching.", table, name)
        return {"built": built, "refused": refused, "invalid": invalid}
    finally:
        db.close()


async def start_chain_ingestion_worker(db_session_factory):
    logger.info("Initializing Chained Ingestion Worker Daemon...")

    # 🔴 BEFORE ANY LEDGER LOOP STARTS (S-88). Both loops below write to the ledger, and
    # one of them was added the same day this gap was found.
    try:
        await asyncio.to_thread(_ensure_ledger_schema_sync, db_session_factory)
    except Exception as exc:
        logger.error("[Ledger] the ledger schema could not be ensured, so a column that "
                     "landed in code may be missing here: %s", exc)
    # \U0001f534 S-87 — AFTER THE SCHEMA ENSURE AND BEFORE ANY LOOP READS A CURSOR. The
    # ensure above may have added the very column this reads, and both ledger loops below
    # refuse to run against a cursor whose fingerprint does not match.
    try:
        await asyncio.to_thread(_restamp_moved_fingerprints_sync, db_session_factory)
    except Exception as exc:
        logger.error("[Ledger] cursor fingerprints could not be re-stamped, so a source "
                     "whose declaration did not change may still refuse to run: %s", exc)
    # \U0001f534 판정 189. Separate from the ensure above because it STRENGTHENS: it can
    # refuse, and a refusal is a number an operator has to see rather than an error.
    try:
        await asyncio.to_thread(_ensure_business_key_unique_indexes_sync,
                                db_session_factory)
    except Exception as exc:
        logger.error("[Ledger] the business-key unique indexes could not be ensured, "
                     "so that column may not be an enforced identity here: %s", exc)
    # 🔴 판정 239. The same seat, because "at boot" is where an index a query
    # depends on has to appear - the reload path alone leaves a restarted deployment
    # scanning.
    try:
        await asyncio.to_thread(_ensure_alignment_decision_key_indexes_sync,
                                db_session_factory)
    except Exception as exc:
        logger.error("[Chain] the alignment decision-key indexes could not be ensured, "
                     "so every alignment view build may still scan its source: %s", exc)
    # 🔴 판정 245-b. Same seat, opposite direction: this one exists so a btree can come OFF
    # the cell write, which is the ingestion path's largest cost.
    try:
        await asyncio.to_thread(_ensure_human_claims_index_sync, db_session_factory)
    except Exception as exc:
        logger.error("[Chain] the human-claims index could not be ensured, so an "
                     "interactive withdraw may scan instead: %s", exc)
    # 🔴 S-124 ①. Same seat, same builder: what a model declares and an existing table
    # lacks is invisible until a query is slow, and the grid's page query is the one that
    # goes slow.
    try:
        await asyncio.to_thread(_ensure_dynamic_table_indexes_sync, db_session_factory)
    except Exception as exc:
        logger.error("[Chain] the dynamic-table indexes could not be ensured, so a table "
                     "older than the declaration may still sort instead of scanning: %s",
                     exc)

    # 🔴 AND THE INDEX IS NOT ENOUGH IF THE PLANNER WILL NOT COST IT (S-130). A table
    # loaded before any of this landed still plans against statistics from before those
    # rows, which is what the owner is looking at.
    try:
        await asyncio.to_thread(_analyze_stale_tables_sync, db_session_factory)
    except Exception as exc:
        logger.error("[Chain] stale table statistics could not be refreshed, so a page "
                     "query may sort instead of walking its index: %s", exc)

    # 🔴 ONE LOOP PER QUEUE, AND IT SAYS SO WHEN IT STANDS DOWN. Two loops on one outbox
    # pick the same rows up twice and write one heartbeat file between them, so neither
    # "is the chain alive" nor "which code is running" has an answer. Standing down
    # SILENTLY would be the worse half of that - a process that does nothing and says
    # nothing is indistinguishable from one that is working.
    _other = another_chain_loop_is_running()
    if _other:
        logger.warning(
            "[Chain Worker] NOT starting: another chain loop is already running (%s). "
            "This process will not consume the outbox. Two loops on one queue pick the "
            "same rows up twice and share one heartbeat, so neither can be observed. "
            "If this is the process you meant to run, stop the other one first.", _other)
        return

    # 🔴 THIS PROCESS RUNS THE LOOP, AND THE QUEUE VIEW HAS TO KNOW THAT. Without it an
    # empty "running" list means both "no mapper is in flight" and "the loop is in
    # another process and I cannot see it" - the second dressed as the first.
    chain_activity.registry.attach()

    # [F8] Everything about this process's path to /internal/events/*, before any
    # data is in flight: which token it holds (as a one-way fingerprint the API
    # server prints too), what proxy configuration exists, and whether /health
    # answers directly. This worker is the one that took the 2026-07-30 403s, and
    # nothing it logged at startup could have told an operator why.
    for _lvl, _msg in internal_event_client.startup_lines("Chain Worker"):
        getattr(logger, _lvl)(_msg)

    rules = load_chain_rules()
    logger.info(f"Loaded {len(rules)} active chain ingestion rules.")
    
    last_reload_event_id = 0
    # [Latency Fix #1] SYSTEM_RELOAD 조회를 매 루프가 아니라 최소 간격(초)으로만 수행하여
    # 고처리량 버스트 중 불필요한 반복 조회를 줄인다. (부분 인덱스 idx_outbox_reload 와 병행)
    last_reload_check_ts = 0.0
    RELOAD_CHECK_INTERVAL = 1.0

    # [Reliability F1] 통지 미확정 교정 행 안전망 스윕도 매 루프가 아니라 최소 간격(초)으로만 수행한다.
    last_sweep_ts = 0.0
    head_watch = QueueHeadWatch()
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

    # The ledger's follow-up runs BESIDE this loop and never inside it, so the chain's
    # transaction time is what it was (ruling 129-bis ㉩).
    asyncio.create_task(run_ledger_followup(db_session_factory))
    # 🔴 ITS OWN LOOP, NOT A BRANCH OF THE FOLLOW-UP'S IDLE ARM. Two jobs sharing one
    # loop share one pace, and these two want opposite ones: the follow-up is latency
    # (a row is waiting), the census is politeness (nothing waits for it).
    asyncio.create_task(run_ledger_row_census(db_session_factory))

    while True:
        # [B1/B2] Progress beat, emitted from the work loop itself. Idle
        # iterations are bounded by the 2 s LISTEN timeout below, so a beat that
        # stops advancing means this loop stopped advancing - the freeze case a
        # pid check cannot see.
        #
        # [Schema] The beat also carries this process's undeclared-column drop
        # counts. Those drops happen HERE, in the worker, and the question they
        # raise ("is this deployment still losing a column?") has to be answerable
        # from the web server, which is a different process. `beat`'s note is the
        # cross-process channel that already exists and `/health` already reads, so
        # no second channel is built for this. The note is None on a healthy worker,
        # so a clean deployment's heartbeat is byte-identical to what it is today.
        #
        # [ChainKeyGate] The same argument applies verbatim to the rows the key gate
        # refused, and for the same reason they ride the same note rather than a new
        # channel - see `_worker_note`.
        heartbeat.beat("chain", note=_worker_note())
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
                    head_watch.note_reload()
                    chain_activity.registry.note_reload()
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
                        mark_processed(latest_reload, "SUCCESS")
                        db.commit()

                # Fetch pending outbox records
                pending_events = db.query(DatabaseOutbox).filter(
                    DatabaseOutbox.processed_chain == False
                ).order_by(DatabaseOutbox.id.asc()).limit(200).all()

                # The head of this ordered fetch is the oldest waiting row. If it is still
                # the head next time round, and the time after that, the loop is running
                # and draining nothing - see QueueHeadWatch.
                stalled = head_watch.observe(
                    len(pending_events),
                    pending_events[0].id if pending_events else None)
                if stalled:
                    logger.error(stalled)
                
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
                # 1. First unpack/normalize all payloads in pending_events and filter out
                #    CONTROL events (instructions to another daemon, not data changes).
                #    Membership in the shared set, not a literal: a second control type was
                #    added (RETROACTIVE_RUN) and a hardcoded name here would have let it
                #    fall through into process_chain_transaction_group, where a trigger
                #    payload would be read as a set of changed rows.
                normalized_events = []
                # Read once per batch, not per event: the declaration cannot change
                # mid-batch and reading it N times would invite N different answers.
                max_depth = event_constants.max_chain_depth(_RULES_DOCUMENT)
                depth_refused = 0
                for event in pending_events:
                    payload_data = get_payload_dict(event)
                    event._parsed_payload = payload_data
                    if isinstance(event.payload, str):
                        event.payload = payload_data

                    if event.event_type in event_constants.CONTROL_EVENT_TYPES:
                        continue

                    # 🔴 [DEPTH] THE LIMIT IS ENFORCED HERE, ONCE, AND IT SAYS SO.
                    # Not inside `_rule_accepts_event`: that is a pure predicate called
                    # five times per event, so refusing there would log five times or
                    # (worse) stay silent - and "silently not running" is the failure this
                    # whole mechanism exists to replace.
                    #
                    # ⚠️ AND THE ROW IS FINISHED, not left pending. An over-deep event that
                    # kept `processed_chain=False` would be re-read on every tick forever
                    # and block the queue behind it - the defect repaired in `92d1c1ff`,
                    # which this must not reintroduce one file away.
                    depth = event_constants.chain_depth_of(payload_data)
                    if depth is not None and depth > max_depth:
                        logger.warning(
                            "[Chain Depth] outbox#%s (%s) reached hop %d, over the "
                            "declared limit of %d; refusing it and marking it finished so "
                            "the queue behind it runs. Raise `max_chain_depth` in "
                            "chain_rules.json if this cascade is meant to be this long.",
                            event.id, event.table_name, depth, max_depth)
                        mark_processed(event, "FAILED")
                        depth_refused += 1
                        continue

                    normalized_events.append(event)

                if depth_refused:
                    db.commit()          # the FAILED marks, so they are not re-read

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

                # [OUTBOX-4] 🔴 THE 20,000 CAP ABOVE COUNTS EVENTS, AND AFTER THE COLLAPSE
                # AN EVENT IS UP TO 1,000 ROWS. Left alone it would pull 20,000 chunks =
                # 20,000,000 rows into ONE mapper call - a 1,000x amplification of the
                # working set in the one place this codebase is most careful about.
                # Re-charge the budget in ROWS so the batch stays the size it was before
                # the collapse. A prefix is kept, never a filter: the tail stays
                # processed_chain=False and returns in the same order next iteration.
                trimmed = trim_events_to_row_budget(normalized_events, OUTBOX_GROUP_MAX_ROWS)
                if len(trimmed) < len(normalized_events):
                    logger.info(
                        f"[OUTBOX-4] Deferring {len(normalized_events) - len(trimmed)} event(s) "
                        f"to the next iteration: this batch already covers ~{OUTBOX_GROUP_MAX_ROWS} "
                        f"ingested rows."
                    )
                    normalized_events = trimmed

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
                # ── 유지보수는 «일 뒤»에 ─────────────────────────────────────────────
                # 🔴 이 자리로 옮긴 이유: 앞에 있으면 «이번 회차의 일»이 유지보수를 기다린다.
                # sweep 은 진짜 미전달을 잡으면 표마다 통지를 쏘고, 그 통지는 3초 타임아웃을 가진
                # POST 다 — 웹서버가 느린 순간(= 통지가 유실되는 순간)에 fetch 가 그 뒤에 줄을 선다.
                # 이제는 «다음 회차»가 기다린다. 이번 회차의 일은 이미 끝나 있다.
                #
                # 🔴 그리고 `finally` 인 이유: 위 본문은 «일이 없으면» continue 로 빠져나간다.
                # 그 경로가 가장 흔하고, 유지보수가 가장 필요한 자리다. 본문 «끝»에 두면 한가한
                # 루프에서 스윕이 영영 안 돈다 — 순서를 고치려다 안전망을 끄는 것이 된다.
                #
                # ⚠️ sweep 은 `await` 그대로다. 백그라운드로 돌리면 본 루프의 «배치-끝» 발사와
                # 창이 겹쳐 같은 그룹을 두 번 발사한다 (실측: 1000행 배치 21.4초 vs grace 5초).
                # 순차라는 것 하나가 지금 그 안전을 만든다.
                try:
                    # 시각을 «다시» 읽는다: 위의 now_ts 는 배치 «시작» 시각이라, 긴 배치 뒤에는
                    # 그만큼 낡아 스로틀이 매 회차 열린다.
                    maint_ts = time.monotonic()
                    # [Reliability F1] 통지 미확정(broadcast_at IS NULL) 교정 행 안전망 스윕(throttle).
                    #   commit됐으나 통지가 유실된 행을 주기적으로 재발사하여 eventual delivery를 보장한다.
                    if maint_ts - last_sweep_ts >= SWEEP_INTERVAL:
                        last_sweep_ts = maint_ts
                        await sweep_undelivered_broadcasts(db, rules, db_session_factory)

                    # [C-3] outbox 7일 보관 purge (저빈도·비블로킹·별도 세션)
                    if (purge_task is None or purge_task.done()) and (
                        last_purge_ts is None or maint_ts - last_purge_ts >= OUTBOX_PURGE_INTERVAL
                    ):
                        last_purge_ts = maint_ts
                        purge_task = asyncio.create_task(
                            asyncio.to_thread(purge_expired_outbox_sync, db_session_factory)
                        )
                except Exception as maint_err:                       # noqa: BLE001
                    # 유지보수의 실패가 «일»의 오류를 덮지 않게 한다. 이 finally 는 예외 경로에서도
                    # 돌고, 거기서 새 예외를 던지면 원래 예외가 사라진다.
                    logger.error(f"[Chain Worker] maintenance pass failed: {maint_err}")
                db.close()
        except Exception as e:
            logger.error(f"Database session setup failed in Chain Worker: {e}")
            await asyncio.sleep(5)
