from sqlalchemy import create_engine, event
from sqlalchemy.orm import (sessionmaker, declarative_base, Session,
                            SessionTransactionOrigin)
import os
import uuid
from datetime import datetime

# Database connection URL. Precedence (pinned by test_database_url_config.py):
#   env DATABASE_URL  >  <config dir>/database.json  >  DEFAULT_PG_URL
# Resolution logic lives in server/paths.py (stdlib-only, shared with the
# process supervisor's reachability probe). Read ONCE at import - a connection
# string is not hot-swappable, so there is deliberately no hot reload;
# changing database.json requires a full restart of every process.
# URL format: postgresql://[user]:[password]@[host]:[port]/[dbname]
try:
    import paths as _paths
    import db_safety as _db_safety
except ImportError:  # imported without server/ on sys.path (same guard as crud.py)
    import sys as _sys
    _sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    import paths as _paths
    import db_safety as _db_safety

DEFAULT_PG_URL = "postgresql://postgres:admin@localhost:5432/assy_manager"
# DB_URL_SOURCE: "env" | "config file" | "default" - logged (masked) at boot by main.py.
SQLALCHEMY_DATABASE_URL, DB_URL_SOURCE = _paths.resolve_database_url(DEFAULT_PG_URL)

# [#16a] Arm the test-process guard BEFORE any engine exists in this process.
# Outside pytest this registers a listener that always returns immediately; the
# production connection path is unchanged. Inside a test process it makes a
# connection to anything but an isolated database impossible - including from an
# engine a test builds for itself, which is why it is registered on the Engine
# CLASS. See server/db_safety.py for why this lives in production code rather
# than in conftest.py.
_db_safety.install_global_test_database_guard(production_url=DEFAULT_PG_URL)

# SQLite 호환성을 위해 체크 (SQLite 파일이 존재하고 URL에 sqlite가 포함된 경우)
is_sqlite = "sqlite" in SQLALCHEMY_DATABASE_URL

# 엔진 설정 (PostgreSQL용 커넥션 풀링 최적화 포함)
if is_sqlite:
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        pool_size=20,           # 커넥션 풀 크기 (1,000만 행 동시 접속 대응)
        max_overflow=10,        # 피크 시 추가 허용 커넥션
        pool_recycle=3600,      # 커넥션 재사용 시간
        connect_args={"options": "-c client_encoding=utf8"} # [핵심] DB 연결 시 UTF-8 강제
    )

# [#16a] This is the one engine in the process built from the RESOLVED url - i.e.
# the only one that can be pointed at production by an ambient environment
# variable rather than by someone typing production's credentials into a test.
# It gets the stricter hook: `do_connect` refuses before the socket opens, so a
# test process never contacts a real database at all, not even to be turned away.
_db_safety.install_test_database_guard(engine, production_url=DEFAULT_PG_URL)

# [Notation normalization] SQLite has neither `regexp_replace` nor `translate`, so the
# query-time notation fold has no SQL spelling there. Register it as a scalar function
# instead, on the Engine CLASS - the suite and the contracts each build their own
# engine, so a listener attached to `engine` alone would miss both (same reasoning as
# `install_global_test_database_guard` above). A no-op on PostgreSQL, which is every
# production connection.
try:
    import notation_norm as _notation_norm
    _notation_norm.install_sqlite_fold()
except Exception as _e:  # pragma: no cover - never block boot on this
    import logging as _logging
    _logging.getLogger("database").warning(
        "notation fold could not be registered for non-PostgreSQL dialects: %s", _e)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# [P5] `session.info` key meaning "this transaction has already told the listeners to
# wake up". See `stage_event` for why one is enough and `_clear_outbox_notify_latch`
# for why it must be cleared aggressively.
_OUTBOX_NOTIFY_SENT = "_outbox_notify_sent"


@event.listens_for(Session, "after_transaction_end")
def _clear_outbox_notify_latch(session, transaction):
    """Drop the once-per-transaction NOTIFY latch when a transaction scope ends.

    ⚠️ `SUBTRANSACTION` IS EXCLUDED, AND THAT EXCLUSION IS THE WHOLE POINT.
    SQLAlchemy opens and closes an internal subtransaction around EVERY `flush()`,
    so this event fires once per flush as well as once per real transaction
    (measured: `origin=SUBTRANSACTION, nested=False` at each flush;
    `origin=AUTOBEGIN/BEGIN, parent=None` at commit). Clearing on those would make
    the latch per-FLUSH, and the budget would silently be "one NOTIFY per flush"
    while claiming to be one per write.

    How much that costs depends on the caller, and the honest measurement is: a
    plain `crud.apply_batch_updates` of 200 cells fires `before_flush` exactly ONCE,
    so per-flush and per-transaction happen to coincide there. They do not coincide
    when the batch also purges (`replace_map` flushes the DELETE before the upserts)
    or when any caller flushes mid-transaction, and nothing stops a future one from
    doing so. `test_one_transaction_with_several_flushes_still_sends_one_notify`
    is the test that tells the two policies apart.

    Everything else clears, and deliberately so, because the failure directions are
    not symmetric. An EXTRA notify costs one round trip and PostgreSQL collapses it;
    a MISSING one means the chain worker does not wake and every downstream write
    waits for its 2 s poll timeout instead. So commit, rollback, AND the end of a
    SAVEPOINT scope (`origin=BEGIN_NESTED`) all clear it. The savepoint case is
    correctness, not tidiness: PostgreSQL discards a NOTIFY issued inside a
    subtransaction that rolls back, so a latch surviving that rollback would swallow
    the wake-up for every outbox row staged afterwards.
    """
    if transaction.origin is SessionTransactionOrigin.SUBTRANSACTION:
        return
    session.info.pop(_OUTBOX_NOTIFY_SENT, None)


@event.listens_for(Session, "before_flush")
def auto_stage_database_outbox(session, flush_context, instances):
    from .models import DYNAMIC_TABLES
    from .context import request_outbox_mode
    from sqlalchemy import inspect
    dynamic_classes = tuple(DYNAMIC_TABLES.values())
    if not dynamic_classes:
        return

    try:
        from event_constants import OUTBOX_MODE_COLLAPSED
    except ImportError:  # pragma: no cover - same sys.path guard as crud.py
        import sys as _sys
        _sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
        from event_constants import OUTBOX_MODE_COLLAPSED

    collapsed = request_outbox_mode.get() == OUTBOX_MODE_COLLAPSED
    # [OUTBOX-4] (table_name, event_type) -> [row_id, ...] for the collapsed path.
    # Insertion-ordered so the events this flush stages come out in a stable order.
    pending_chunks = {}

    def _emit(event_type, obj):
        if collapsed:
            pending_chunks.setdefault((obj.__table__.name, event_type), []).append(obj.row_id)
        else:
            stage_event(session, event_type, obj.__table__.name, obj)

    for obj in session.new:
        if isinstance(obj, dynamic_classes):
            _emit("CREATE", obj)

    for obj in session.dirty:
        if isinstance(obj, dynamic_classes):
            # 변경된 속성 컬럼 목록 검출
            try:
                insp = inspect(obj)
                dirty_cols = [attr.key for attr in insp.attrs if attr.history.has_changes()]
            except Exception:
                dirty_cols = []

            # 변경 항목이 오직 그래프 동기화 메타 컬럼(is_graph_synced 등)뿐이면 Outbox 발행 생략
            if dirty_cols:
                graph_meta_cols = {"is_graph_synced", "needs_graph_rollback", "graph_synced_at"}
                if all(col in graph_meta_cols for col in dirty_cols):
                    continue

            _emit("EDIT", obj)

    for obj in session.deleted:
        if isinstance(obj, dynamic_classes):
            # 🔴 DELETE NEVER COLLAPSES, in either mode. A collapsed event is a
            # POINTER and a deleted row cannot be re-read, so a collapsed DELETE
            # would name rows nobody can ever resolve. The volume this round
            # exists for is CREATE/EDIT (an ingested file is upserts); DELETEs are
            # shell-row cleanups, orders of magnitude fewer.
            stage_event(session, "DELETE", obj.__table__.name, obj)

    for (table_name, event_type), row_ids in pending_chunks.items():
        stage_collapsed_event(session, event_type, table_name, row_ids)


def _outbox_envelope():
    """The (tx_id, user, source, timestamp) every outbox payload carries.

    One place, so the collapsed event and the per-row event cannot drift on the
    fields every consumer greps for (`transaction_id` drives grouping, and
    `source_name == 'chain_ingestion'` is the circular-loop filter - a collapsed
    event that lost either would be read as a foreign transaction, or would loop).
    """
    from .context import request_user, request_transaction_id, request_source
    return (
        request_transaction_id.get() or str(uuid.uuid4()),
        request_user.get(),
        request_source.get(),
        datetime.now().isoformat(),
    )


def stage_collapsed_event(session, event_type, table_name, row_ids):
    """[OUTBOX-4] Stage ONE outbox event naming `row_ids` instead of N events.

    🔴 THE TRANSACTIONAL-OUTBOX GUARANTEE IS PRESERVED, AND HERE IS WHY IT SURVIVES
    THE COLLAPSE. The event must commit atomically with the rows it names; an
    event staged outside their transaction re-opens the exact failure this pattern
    exists to prevent (rows durable, nobody ever told). Two facts make that hold:

      1. `row_id` is minted in PYTHON (`crud._get_or_create_row`:
         `row_id=update_item.row_id or str(uuid6.uuid7())`), not by a SERIAL, so
         the complete id list is already known at `before_flush` time. No round
         trip is needed to learn what to name, so nothing has to happen after the
         flush.
      2. This is `session.add`-ed on the SAME session inside `before_flush`,
         exactly as `stage_event` is, so SQLAlchemy includes it in the very flush
         that writes the rows - one transaction, one commit, all or nothing.

    `event_type` stays CREATE/EDIT rather than becoming BATCH_*: every consumer
    that only asks "did table T change" keeps working unmodified. The payload's
    `row_ids` key is the discriminator (`event_constants.is_collapsed_payload`).
    """
    from .models import DatabaseOutbox
    try:
        from event_constants import OUTBOX_COLLAPSE_CHUNK_ROWS
    except ImportError:  # pragma: no cover
        OUTBOX_COLLAPSE_CHUNK_ROWS = 1000

    tx_id, user, source, ts = _outbox_envelope()

    # Split a huge flush into 1,000-id chunks: bounds the JSONB payload (~40 KB),
    # keeps the project's chunking discipline, and bounds the failure path (a
    # poison row re-expands at most one chunk into per-row retries).
    for i in range(0, len(row_ids), OUTBOX_COLLAPSE_CHUNK_ROWS):
        id_chunk = row_ids[i:i + OUTBOX_COLLAPSE_CHUNK_ROWS]
        session.add(DatabaseOutbox(
            event_uuid=str(uuid.uuid4()),
            event_type=event_type,
            table_name=table_name or "unknown",
            payload={
                # An explicit LIST, not a (lo, hi) range. uuid7 row_ids are
                # time-ordered so NEW rows would range cleanly - but an upsert
                # chunk also touches EXISTING rows whose ids were minted long ago,
                # so the ids in one chunk are not contiguous and a range would
                # silently over- or under-select.
                "row_ids": id_chunk,
                "row_count": len(id_chunk),
                "table_name": table_name or "unknown",
                "transaction_id": tx_id,
                "updated_by": user,
                "source_name": source,
                "timestamp": ts,
            },
            status="PENDING",
        ))

    _notify_outbox_once(session)


def stage_event(session, event_type, table_name, data_row):
    from .models import DatabaseOutbox
    try:
        from event_constants import OUTBOX_PAYLOAD_EXCLUDED_COLUMNS as _EXCLUDED
    except ImportError:  # pragma: no cover
        _EXCLUDED = frozenset({"row_id", "business_key_val", "created_at", "updated_at",
                               "is_graph_synced", "needs_graph_rollback", "graph_synced_at"})

    tx_id, user, source, ts = _outbox_envelope()

    data_dict = {}
    for col in data_row.__table__.columns:
        if col.name not in _EXCLUDED:
            val = getattr(data_row, col.name, None)
            data_dict[col.name] = {
                "value": val,
                "is_overwrite": False,
                "updated_by": "system"
            }

    event_obj = DatabaseOutbox(
        event_uuid=str(uuid.uuid4()),
        event_type=event_type,
        table_name=table_name or "unknown",
        payload={
            "row_id": data_row.row_id,
            "business_key": data_row.business_key_val,
            "data": data_dict,
            "transaction_id": tx_id,
            "updated_by": user,
            "source_name": source,
            "timestamp": ts
        },
        status="PENDING"
    )
    session.add(event_obj)

    _notify_outbox_once(session)


def _notify_outbox_once(session):
    # [최적화] PostgreSQL 데이터베이스 환경인 경우, 트랜잭션이 commit될 때 실시간 이벤트를 전파하도록 NOTIFY 실행
    #
    # [P5] ONCE PER TRANSACTION, not once per staged row. This is called from
    # `before_flush` for every created/dirty/deleted dynamic row, so a 200-cell map push
    # sent 200 NOTIFY statements - one extra round trip per row, growing linearly with
    # the write.
    #
    # 🔴 WHY THIS IS NOT AN APPROXIMATION OF THE OLD BEHAVIOUR. The signal delivered to
    # listeners is unchanged, and the reason is PostgreSQL's own documented rule rather
    # than a reading of our code: duplicate notifications on the same channel with the
    # same (here: empty) payload within one transaction are collapsed to a single
    # delivered event. The listener - `chain_ingestion_worker.OutboxListener` - drains
    # `connection.notifies` to empty and treats any wake as "repoll the outbox", so it
    # could not distinguish 1 from 200 even if PostgreSQL delivered them. What the
    # listener needs is AT LEAST ONE notify in any transaction that stages an outbox
    # row, and that is exactly the invariant below.
    #
    # The latch is set only AFTER the statement succeeds, so a NOTIFY that failed (dead
    # connection) does not suppress the next row's attempt.
    try:
        if session.info.get(_OUTBOX_NOTIFY_SENT):
            return
        bind = session.bind or session.get_bind()
        if bind and bind.dialect.name == "postgresql":
            from sqlalchemy import text
            session.execute(text("NOTIFY outbox_event;"))
            session.info[_OUTBOX_NOTIFY_SENT] = True
    except Exception:
        # Fallback: DB 연결 상태 등으로 실패하더라도 메인 트랜잭션에 영향을 주지 않도록 무시
        pass
