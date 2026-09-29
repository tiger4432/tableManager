"""System-wide config and module cache reload -- the half two callers share.

WHY THIS IS NOT IN `main.py`
    It was, and `ledger_api/ontology_config_explorer_router.py` reached it with
    `import main` from inside two write handlers. `main` is a process ENTRY POINT,
    not a library: `run_auto_update.py` and `parsers/directory_watcher.py` both put
    user-writable directories at `sys.path[0]` and never take them out, so after the
    first collector has run, an unqualified `import main` in that process binds to
    whatever `main.py` a user happens to have lying around.
    `server/tests/test_entrypoint_import_isolation.py` states the rule and names this
    remedy; `utils/time_format.py` and `column_filter.py` exist for the same reason.

    `main.py` re-exports both names, so anything that reached them through the entry
    point still can.
"""
import logging

from sqlalchemy.orm import Session

from database import models
from database.database import engine

#: Same name `crud` logs under, so the handlers `get_process_logger` attaches to the
#: root logger carry these lines to the same file with the same origin.
logger = logging.getLogger("Server")

#: The embedded workspace watcher, when this process runs one. `main` assigns it at
#: startup after `WorkspaceWatcher.start()`; in every other process it stays None and
#: the workspace sync below is skipped exactly as it was when the watcher was absent.
active_watcher = None

#: 🔴 [총괄 76aa4b6ed, 소유자 09-29 ㄱ] The scope a chain-rules save puts on its SYSTEM_RELOAD:
#:    the chain worker re-reads its rules and nothing else - no mapper re-import, no table
#:    shapes - and every other reader lets the row pass. A row without a scope is the whole
#:    reload (the Reload button, the code editor), unchanged.
SCOPE_CHAIN_RULES = "chain_rules"
#: What a reader does for a row without a scope, or with one this build does not know.
FULL = "full"
#: The readers of SYSTEM_RELOAD, by their heartbeat names.
CHAIN_WORKER, WATCHER, SCHEDULER = "chain", "watcher", "scheduler"


def publish_reload(db: Session, scope=None, **said):
    """Write one SYSTEM_RELOAD row - the daemons read it and reload."""
    import uuid
    from datetime import datetime

    from database.context import request_transaction_id

    payload = {"transaction_id": request_transaction_id.get() or f"reload_{str(uuid.uuid4())[:8]}",
               "timestamp": datetime.now().isoformat(), **said}
    if scope:
        payload["scope"] = scope
    event = models.DatabaseOutbox(event_uuid=str(uuid.uuid4()), event_type="SYSTEM_RELOAD",
                                  table_name="system", payload=payload, status="PENDING")
    db.add(event)
    db.commit()
    return event


def reloads_after(db: Session, after_id: int) -> list:
    """The SYSTEM_RELOAD rows past a reader's high-water mark, oldest first. Every one, not
    the newest only: a scoped row landing right after a button press must not hide it."""
    return (db.query(models.DatabaseOutbox)
            .filter(models.DatabaseOutbox.event_type == "SYSTEM_RELOAD",
                    models.DatabaseOutbox.id > after_id)
            .order_by(models.DatabaseOutbox.id.asc()).all())


def reload_for(reader: str, rows) -> str:
    """What `reader` does for these rows: FULL, SCOPE_CHAIN_RULES, or None. The one seat that
    asks a row's scope."""
    import json

    scopes = set()
    for row in rows or ():
        payload = row.payload
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except ValueError:
                payload = None
        scopes.add(payload.get("scope") if isinstance(payload, dict) else None)
    if not scopes:
        return None
    if scopes - {SCOPE_CHAIN_RULES}:
        return FULL
    return SCOPE_CHAIN_RULES if reader == CHAIN_WORKER else None


def reload_local_process_cache():
    """웹 서버 프로세스의 table_config 캐시 및 동적 모듈 캐시(mappers, pipeline plugins)를 명시적으로 무효화합니다.

    [이슈 #7] config 재로드 시 TABLE_CONFIG 싱글턴·DYNAMIC_TABLES(ORM) 갱신과 함께
    런타임에 추가된 신규 테이블의 물리 CREATE까지 동기적으로 수행한다
    (watchdog 스레드 디바운스 타이밍에 의존하지 않는 결정적 경로 — 기존 테이블 ALTER는 범위 밖).
    """
    import sys

    try:
        created = models.refresh_dynamic_models(engine)
        if created:
            logger.info(f"[Reload] Created missing physical tables at runtime: {created}")
    except Exception as e:
        print(f"[Reload] Failed to reload table_config.json: {e}")
        
    # [Join unique keys] 🔴 [판정 667] THE TTL THAT USED TO BE HERE IS GONE, AND THIS LINE IS
    # WHAT REPLACED IT. The old comment said the cache carried a TTL "for worker processes
    # that never reach this hook" - a clock standing in for an invalidation those processes
    # do not get. Expiry is keyed to LOADING now, so every process invalidates at its own
    # reload seat rather than waiting out a clock; this is the web server's.
    #
    # ⚰️ [판정 677 ② -> 652 3걸음] THE ABSOLUTE IS TRUE AGAIN, AND THIS IS WHY IT READS AS
    # ONE LINE NOW. 677 ② had to narrow 「none of them waits out a clock」 because the
    # read-time half of the same question held a 5-second TTL in
    # `chain.legacy_materialized_join`. That module was deleted, so the clock it predicted
    # would 「die with its grammar」 did. There is one invalidation seat left and it is
    # keyed to LOADING, not to a clock.
    try:
        from chain import synthesis
        synthesis.reset_right_key_cache()
    except Exception:
        pass
    # The rule set this process read (총괄 57ae5c2da): the next request reads the file again.
    try:
        from chain import ingestion_worker
        ingestion_worker.forget_loaded_chain_rules()
    except Exception as exc:                                   # noqa: BLE001
        # The reload goes on; what went quiet is said once (총괄 790511099 뒤).
        logger.error("[Reload] chain rules NOT forgotten - this process keeps the set it read "
                     "until restart: %s: %s", type(exc).__name__, exc)

    # [Notation normalization] Same shape and same reason as the line above: the
    # declaration carries a TTL for the worker processes, but one edited in the
    # admin UI has to take effect on the next QUERY here. (It is a query-time fold
    # now, not a write hook - see notation_norm's docstring.)
    try:
        import notation_norm
        notation_norm.reset_cache()
    except Exception:
        pass


    # 걷기가 들고 있는 파생 목록(fetch 집합·통과 술어)도 어휘에서 나온 사본이므로 같이
    # 버린다. 어휘만 갱신하고 이걸 두면 새 술어가 게이트에는 있고 걷기에는 없다.
    try:
        from ledger import trace
        trace.reset_walk_cache()
        # 🔴 그리고 해소기 캐시도. 선언형 소스의 `emit` 규칙이 «클래스»를 선언하므로
        # (`class: "inference"`), 그 목록은 이제 `ledger_config.json`에서 온다 — admin에서
        # 규칙 하나를 추가하고 이 캐시를 안 버리면, 새 규칙의 원자가 «다음 재기동까지»
        # 3류가 아니라 2류로 순위된다. 그건 조용히 가정이 실측을 이기는 상태다.
        trace.load_resolver_config(force_reload=True)
    except Exception:
        pass

    # 🔴 AND THE WALK'S COPY OF THE ENTITY DECLARATION (S-206). `ledger_subgraph` caches
    # key order AND attribute cardinality behind a process-lifetime sentinel, so a `many`
    # the operator declared and activated would read as `one` until a RESTART -- the
    # declaration changed and the thing that answers questions about it did not.
    # Same `try/except` posture as its neighbours: one cache that will not clear does not
    # kill the reload.
    try:
        from ledger_api import ledger_subgraph
        ledger_subgraph.reset_declaration_cache()
    except Exception:
        pass

    # [Ledger skeleton] The authoring screen GENERATES its form from
    # `ledger/ledger_skeleton.json`, and the loader caches it for the life of the process.
    # Without this line every edit to that document needs a restart to show up -- measured:
    # the lead had to restart the server twice to walk one field into the form and back out
    # again. The file ships with the code rather than with the operator's data, so this is
    # not about admin edits; it is so the document can be corrected while the screen it
    # draws is open.
    try:
        from ledger import config_authoring as ledger_authoring
        ledger_authoring.skeleton.cache_clear()
    except Exception:
        pass

    # Remove custom mappers from sys.modules cache
    mapper_keys = [k for k in sys.modules.keys() if k.startswith("mappers.")]
    for k in mapper_keys:
        sys.modules.pop(k, None)

    # 🔴 THE REGISTRY GOES WITH THEM (S-188 ⓒ). `mapper_sdk` is NOT evicted -- it is not
    # under `mappers.` -- so its registry would keep pointing at functions from the modules
    # just dropped, and the re-import would then refuse every name as 「claimed twice」. A
    # reload would break the thing it exists to refresh. Same `try/except` posture as the
    # blocks above: one cache that will not clear does not kill the reload.
    try:
        import mapper_sdk
        mapper_sdk.reset_registry()
        # 🔴 AND THEY COME BACK, BECAUSE THIS PROCESS JUDGES WITH THEM (S-204 (3), 판정 326).
        # The eviction above is half a reload: the chain worker evicts, resets AND re-runs
        # `discover()` in its warmup, so its registry is as fresh as the files. This process
        # only ever did the first half, which left the rule editor's grammar judge looking
        # at an empty registry from the first SYSTEM_RELOAD onward -- refusing every rule
        # written in the one-cell mapper form, including the ones it had just accepted.
        _registered, _refused = mapper_sdk.discover()
        logger.info("[Reload] Mapper registry: %d registered", len(_registered))
        for _module_name, _message in sorted(_refused.items()):
            logger.error("[Reload] Mapper module refused: %s — %s", _module_name, _message)
    except Exception:
        pass
        
    # Remove pipeline plugin parsers from sys.modules cache
    plugin_keys = [k for k in sys.modules.keys() if k.startswith("pipeline_plugin_")]
    for k in plugin_keys:
        sys.modules.pop(k, None)
        
    print("[Reload] Local web server process cache successfully cleared.")


def reload_system_configs(db: Session):
    """시스템 전역의 설정 및 파이썬 모듈 캐시를 리로드하는 이벤트를 Outbox에 적재하여 모든 워커에 전파합니다."""
    # 1. 웹 서버 자체 메모리 캐시 갱신
    reload_local_process_cache()

    # 1-1. [Std Ingestion] 임베디드 워처(비-decoupled 모드) 사용 시 신규 테이블 워크스페이스
    #      자동 생성 + 런타임 감시 등록. decoupled 모드에서는 run_watcher.py의 SYSTEM_RELOAD
    #      폴러가 동일 처리를 담당한다.
    if active_watcher is not None:
        try:
            active_watcher.sync_new_workspaces()
        except Exception as e:
            logger.error(f"[Reload] Embedded watcher workspace sync failed: {e}")

    # 2. SYSTEM_RELOAD Outbox 이벤트 적재 (데몬 프로세스들로 전파) — 범위 없음 = 전부
    publish_reload(db, msg="Reload configs and custom scripts modules")

    return {"status": "success", "message": "System configurations and custom scripts modules successfully reloaded."}
