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
from error_said import told

#: Same name `crud` logs under, so the handlers `get_process_logger` attaches to the
#: root logger carry these lines to the same file with the same origin.
logger = logging.getLogger("Server")

#: The embedded workspace watcher, when this process runs one. `main` assigns it at
#: startup after `WorkspaceWatcher.start()`; in every other process it stays None and
#: the workspace sync below is skipped exactly as it was when the watcher was absent.
active_watcher = None

#: ⚰️ [e6a0bdbbd] `SCOPE_CHAIN_RULES` - a chain-rules save's row (76aa4b6ed) - is retired: every process watches
#:    the file itself (`database.config_watcher`), a hand edit too. A row without a scope is the Reload button.
#: 🔴 [총괄 10-20] The index line built or took back a join's unique index: each process that writes forgets the
#:    join keys its write gate learned (`synthesis.reset_right_key_cache`), nothing else. Without it a process that
#:    learned 「no index」 before the index stood kept its gate off until somebody reloaded by hand.
SCOPE_JOIN_KEYS = "join_keys"
#: What a reader does for a row without a scope, or with one this build does not know.
FULL = "full"
#: The readers of SYSTEM_RELOAD, by their heartbeat names - and the API's outbox listener and the scheduler's index
#: line (`runtime.maintenance_line`), which read the rows too.
CHAIN_WORKER, WATCHER, SCHEDULER = "chain", "watcher", "scheduler"
API, INDEX_LINE = "api", "index_line"
#: Who each scope is for.
SCOPE_READERS = ((SCOPE_JOIN_KEYS, frozenset({CHAIN_WORKER, WATCHER, API})),)


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


def latest_reload_id(db: Session) -> int:
    """The newest SYSTEM_RELOAD row's id, 0 if none - where a reader that starts now sets its mark."""
    from sqlalchemy import func

    return db.query(func.max(models.DatabaseOutbox.id)).filter(
        models.DatabaseOutbox.event_type == "SYSTEM_RELOAD").scalar() or 0


def reloads_after(db: Session, after_id: int) -> list:
    """The SYSTEM_RELOAD rows past a reader's high-water mark, oldest first. Every one, not
    the newest only: a scoped row landing right after a button press must not hide it."""
    return (db.query(models.DatabaseOutbox)
            .filter(models.DatabaseOutbox.event_type == "SYSTEM_RELOAD",
                    models.DatabaseOutbox.id > after_id)
            .order_by(models.DatabaseOutbox.id.asc()).all())


def reload_for(reader: str, rows) -> str:
    """What `reader` does for these rows: FULL, a scope of `SCOPE_READERS`, or None. The one seat that
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
    if scopes - {scope for scope, _readers in SCOPE_READERS}:
        return FULL
    return next((scope for scope, readers in SCOPE_READERS if scope in scopes and reader in readers), None)


def reload_local_process_cache():
    """The Reload button in the web server: every declaration and mapper read again by the one table
    (`config_watcher.reload_everything` - the table config with its physical sync, as this process writes) and the
    authoring skeleton."""
    from database import config_watcher

    # 🔴 [e6a0bdbbd] THE ONE TABLE (`config_watcher.ROWS`), NOT A SECOND LIST OF IT. Eleven clears stood here one by
    #    one - the table config, the join keys, the external sources, the chain rules, notation, the walk's vocabulary
    #    and resolver, the kept walks, the pool, the mappers - and a cache added to the table and not here was a
    #    reload that left it.
    config_watcher.reload_everything(engine)

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
    except Exception as exc:
        logger.warning("[Reload] the authoring skeleton cache was not cleared: %s", told(exc), exc_info=exc)
        pass

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
            logger.error(f"[Reload] Embedded watcher workspace sync failed: {told(e)}", exc_info=e)

    # 2. SYSTEM_RELOAD Outbox 이벤트 적재 (데몬 프로세스들로 전파) — 범위 없음 = 전부
    publish_reload(db, msg="Reload configs and custom scripts modules")

    return {"status": "success", "message": "System configurations and custom scripts modules successfully reloaded."}
