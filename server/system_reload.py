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
        
    # [Virtual join] Verified-declaration cache. It carries a TTL of its own for worker
    # processes that never reach this hook, but the web server must not wait it out:
    # a declaration edited in the admin UI has to take effect on the next read.
    try:
        import virtual_join_executor
        virtual_join_executor.reset_cache()
    except Exception:
        pass

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
        import ledger_trace
        ledger_trace.reset_walk_cache()
        # 🔴 그리고 해소기 캐시도. 선언형 소스의 `emit` 규칙이 «클래스»를 선언하므로
        # (`class: "inference"`), 그 목록은 이제 `ledger_config.json`에서 온다 — admin에서
        # 규칙 하나를 추가하고 이 캐시를 안 버리면, 새 규칙의 원자가 «다음 재기동까지»
        # 3류가 아니라 2류로 순위된다. 그건 조용히 가정이 실측을 이기는 상태다.
        ledger_trace.load_resolver_config(force_reload=True)
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
        
    # Remove pipeline plugin parsers from sys.modules cache
    plugin_keys = [k for k in sys.modules.keys() if k.startswith("pipeline_plugin_")]
    for k in plugin_keys:
        sys.modules.pop(k, None)
        
    print("[Reload] Local web server process cache successfully cleared.")


def reload_system_configs(db: Session):
    """시스템 전역의 설정 및 파이썬 모듈 캐시를 리로드하는 이벤트를 Outbox에 적재하여 모든 워커에 전파합니다."""
    import uuid
    from datetime import datetime
    from sqlalchemy import text
    
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

    # 2. SYSTEM_RELOAD Outbox 이벤트 적재 (데몬 프로세스들로 전파)
    from database.models import DatabaseOutbox
    from database.context import request_transaction_id
    
    tx_id = request_transaction_id.get() or f"reload_{str(uuid.uuid4())[:8]}"
    
    reload_event = DatabaseOutbox(
        event_uuid=str(uuid.uuid4()),
        event_type="SYSTEM_RELOAD",
        table_name="system",
        payload={
            "transaction_id": tx_id,
            "timestamp": datetime.now().isoformat(),
            "msg": "Reload configs and custom scripts modules"
        },
        status="PENDING"
    )
    db.add(reload_event)
    db.commit()
    
    try:
        db.execute(text("NOTIFY outbox_event;"))
    except:
        pass
        
    return {"status": "success", "message": "System configurations and custom scripts modules successfully reloaded."}
