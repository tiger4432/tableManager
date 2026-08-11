from sqlalchemy import Column, Integer, String, Boolean, JSON, DateTime, Index, text, BigInteger
from sqlalchemy.sql import func
from .database import Base, is_sqlite

from sqlalchemy.dialects.postgresql import JSONB

# [2026-07-25 정리] 레거시 JSONB blob 저장 모델 `DataRow`(data_rows)는 동적 네이티브 테이블로
# 완전 대체되어 제거됨(0행·런타임 인스턴스화 지점 전무). 물리 테이블 DROP은
# scripts/drop_legacy_tables_20260725.sql 참조.

class AuditLog(Base):
    __tablename__ = "audit_logs"

    # [D3] NO `index=True` HERE, and the same applies to every `primary_key=True` column
    # in this file. PostgreSQL builds the primary key's own UNIQUE btree regardless, so
    # `index=True` emits a SECOND, identical, non-unique btree that is maintained on
    # every write and that the planner never needs - it can always use the PK index
    # instead. Measured on the dev catalogue 2026-08-07: 29 such duplicates, 382.3 MB,
    # of which `ix_cell_sources_id` alone was 314 MB against a 314 MB
    # `cell_sources_pkey`. `create_all` never drops an index, so removing the flag only
    # stops NEW databases from growing them; existing ones are cleaned by
    # `server/migrations/add_business_key_unique_index.py --drop-redundant`.
    id = Column(Integer, primary_key=True)
    table_name = Column(String, index=True)
    row_id = Column(String, index=True)
    column_name = Column(String)
    
    old_value = Column(JSON, nullable=True) # Previous value
    new_value = Column(JSON)                # New value
    
    source_name = Column(String)            # user, parser_a, etc.
    updated_by = Column(String)             # user_id or agent_name
    transaction_id = Column(String, index=True, nullable=True) # [Phase 2] 배치 작업 그룹화용 ID
    
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    business_key = Column(String, nullable=True, index=True)

    __table_args__ = (
        # [재교정률] 대시보드가 매 로드마다 감사 테이블을 훑지 않게 하는 유일한 수단.
        # 이 인덱스가 없으면 7일 창 집계가 병렬 Seq Scan으로 떨어진다(2026-07-27 실측:
        # 2,628,453행/1.6GB 기준 512ms, 128,523 블록 판독). 1,000만 행에서는 그대로 초 단위다.
        #
        # 부분 인덱스로 만드는 이유: source_name의 값 집합이 열려 있다(파서가 파일명을 소스명으로
        # 쓰므로 실측 10,750종). 전량 색인은 수백 MB인데 사람이 쓴 행은 그중 2.8%뿐이다.
        # 부분 술어가 planner에 매칭되는 근거: 드라이버가 psycopg2(클라이언트측 보간)라
        # `source_name = 'user'`가 리터럴로 서버에 도달한다(2026-07-27 current_query()로 확인).
        #
        # INCLUDE 4컬럼은 GROUP BY 키 + count(DISTINCT) 대상 전부 → Index Only Scan이 되어
        # 힙 방문이 사라진다. 사람 쓰기만 담으므로 현재 규모에서 수 MB 수준.
        # PostgreSQL 전용 옵션(postgresql_*)은 SQLite에서 무시되어 일반 timestamp 인덱스가 된다.
        Index(
            "idx_audit_user_recorrection",
            "timestamp",
            postgresql_include=["table_name", "row_id", "column_name", "transaction_id"],
            postgresql_where=text("source_name = 'user'"),
        ),

        # [history keyset] The two indexes that make a row click cost O(page)
        # instead of O(everything ever written to that row).
        #
        # WITHOUT THEM, `LIMIT` DOES NOT HELP THE DATABASE AT ALL. Measured on
        # `assy_qa` 2026-08-11, one row inflated to 300,019 audit entries inside
        # 1,131,008 rows, `LIMIT 201` already applied:
        #     no index : Parallel Bitmap Heap Scan + top-N sort of all 300,019
        #                -> 9,421 buffers, 121.6 ms
        #     with this: Index Scan, stops at 201
        #                ->   207 buffers,   0.4 ms
        # The LIMIT only removed the 54 MB of rows crossing the wire; the scan
        # was still proportional to the row's whole history until this existed.
        #
        # WHY THE SECOND ONE, WITH `column_name`. The first index makes
        # column_name a Filter inside the row's range, so the cell tab costs
        # "walk until 201 matches are found" - fine for a dense column, unbounded
        # for a SPARSE one, which is exactly the human-edit case this feature is
        # for. Measured on a column with ONE entry inside that 300,019-deep row:
        #     row index only : 9,421 buffers, 117.7 ms (planner abandons it entirely)
        #     this index     :     5 buffers,   0.09 ms
        #
        # WHY PLAIN ASC when the query sorts `timestamp DESC, id DESC`: a btree
        # is scanned backwards just as cheaply. Measured both ways - same plan
        # shape (`Index Scan Backward`), same `Index Cond` including the
        # row-value keyset bound, same buffer counts, same 91 MB. ASC is chosen
        # because it needs no raw SQL here and so applies to SQLite too.
        #
        # ⚠️ `create_all` NEVER adds an index to a table that already exists, so
        # this declaration only reaches NEW databases. Existing ones (production
        # included) get them from
        # `server/migrations/add_audit_history_keyset_indexes.sql`.
        Index("idx_audit_row_history", "table_name", "row_id", "timestamp", "id"),
        Index("idx_audit_cell_history", "table_name", "row_id", "column_name",
              "timestamp", "id"),

        # [recent groups] The ONLY index whose leading column is `timestamp`
        # without a predicate, and therefore the only one that can serve the
        # global history scan `/audit_logs/recent` runs
        # (`ORDER BY timestamp DESC, id DESC`, no WHERE).
        #
        # WITHOUT IT THE SCAN IS A SORT OF THE WHOLE TABLE, ONCE PER CHUNK.
        # Measured on a 2,900,000-row fixture built from production's own column
        # widths, 2026-08-11, for ONE 5,000-row chunk:
        #     Parallel Seq Scan -> Sort (timestamp DESC, id DESC)
        #     Sort Method: external merge  Disk: 400,848 kB
        #     153,307 buffers read, 287,412 temp blocks written, 3,658 ms
        # and `load_initial` issued ~41 of those, because the newest 200,000
        # rows of that fixture carry TWO transaction_ids (one ingestion writes
        # one transaction_id per file). Cold first call: 212,634 ms.
        #
        # WHY `INCLUDE (transaction_id)` AND NOT A THIRD KEY COLUMN. The walk
        # never orders or ranges by `transaction_id`; it only needs to READ it
        # to tell one group from the next. An INCLUDE column rides in the leaf
        # tuples only - it is absent from the internal pages, so the tree stays
        # shallower than a three-key index while still making the walk an Index
        # Only Scan (no heap visit for 200,000 rows).
        #
        # WHY ASC when the query sorts DESC: identical cost scanned backwards,
        # and ASC is what `__table_args__` can declare without raw SQL, so one
        # declaration covers PostgreSQL and the SQLite test database. The same
        # reasoning as the two history indexes above.
        #
        # ⚠️ `create_all` NEVER adds an index to a table that already exists, so
        # this declaration only reaches NEW databases. Existing ones (production
        # included) get it from
        # `server/migrations/add_audit_recent_groups_index.sql`.
        Index("idx_audit_recent_groups", "timestamp", "id",
              postgresql_include=["transaction_id"]),
    )


class InteractionEffortLog(Base):
    """[V1 계기] 완료까지의 상호작용 점수 — 한 교정 트랜잭션이 든 **사람의 공수** 원시 카운트.

    SYSTEM_OVERVIEW §1 핵심가치 #1 "최소 공수 교정"의 **정본 계기**(사용자 2026-07-29 교체).
    재교정률은 원인이 UI 공수인지 데이터 품질인지 분리하지 못해 보조로 강등됐다 — 이 계기는
    "사람이 손을 몇 번 썼는가"를 에두르지 않고 직접 잰다. 낮을수록 좋다.

    설계 결정 — 왜 이렇게 저장하는가:

    1) **왜 `audit_logs`에 컬럼을 붙이지 않았는가.** `create_all`은 기존 테이블에 컬럼을
       추가하지 않으므로 운영 DB에서는 ALTER 마이그레이션이 모든 조회 프로세스보다 먼저
       돌아야 하고, 그 전에 웹서버가 SELECT하면 UndefinedColumn 500으로 죽는다. 또한 공수는
       **셀당**이 아니라 **tx당** 1건이라 2.6M행짜리 셀 단위 테이블에 얹으면 같은 값이
       수십 번 중복된다. 신규 테이블은 create_all이 만들어 주므로 순서 의존이 없다.

    2) **왜 점수가 아니라 원시 카운트인가.** 배점(key/mouse/nav 가중치)은 `effort_metric.json`
       선언이고 조회 시점에 곱해진다. 점수를 굳혀 저장하면 배점을 재조정하는 순간 과거
       데이터가 옛 배점에 갇혀 before/after 비교가 불가능해진다 — 이 계기의 존재 이유가
       바로 그 비교다.

    3) **왜 `transaction_id`가 UNIQUE인가.** 단위는 "한 tx 묶음 교정 완료"이고 그 경계는
       서버가 이미 긋고 있다(`AuditLog.transaction_id`). tx당 1행이 아니면 한 번의 교정이
       여러 번 계수되어 평균이 왜곡된다. 같은 tx로 요청이 재도달하면(클라 재시도) **첫 기록이
       이긴다** — 재전송은 새로 쓴 공수가 아니다. (SET 의미론으로 덮어쓰면 마지막 메시지가
       실제 공수를 대체해 버린다 — QA D-1에서 카운트 필드로 이미 겪은 함정.)

    4) **없음(NOT MEASURED)은 0이 아니다.** 워커·인제션·체인 경로에는 키보드 앞에 사람이
       없다. 그런 tx는 이 테이블에 **행 자체가 없어야** 하며, 0으로 적으면 평균이 조용히
       희석된다. 커버리지는 `measured_ratio`로 항상 함께 보고한다.
    """
    __tablename__ = "interaction_effort_logs"

    id = Column(Integer, primary_key=True)
    # AuditLog가 이미 쓰는 그 tx_id — 새 상관관계 개념을 만들지 않는다.
    transaction_id = Column(String, nullable=False)
    session_id = Column(String, nullable=False)
    # 원시 카운트만. 가중치는 조회 시점에 적용된다(위 결정 2).
    key_count = Column(Integer, nullable=False, default=0)
    mouse_count = Column(Integer, nullable=False, default=0)
    # nav_count = 컨텍스트를 **잃는** 전이 / nav_preserved_count = 유지하는 전이.
    # [총괄 addendum 2026-07-29] 면제된 전이도 **버리지 않고 따로 센다.** 분류를 수집
    # 시점에 확정해 nav 를 증가시키지 않는 방식은, 면제 판단이 틀린 것으로 밝혀져도
    # 되돌릴 수 없다 — 이 계기는 소급 산출이 불가능하므로 그 순간 기준선이 영구히
    # 틀린 채로 남는다. 두 카운트를 다 보관하면 허용목록이 **조회 시점 해석**이 되어
    # 가중치(nav_preserved, 기본 0)만 바꿔 과거 데이터를 재채점할 수 있다.
    nav_count = Column(Integer, nullable=False, default=0)
    nav_preserved_count = Column(Integer, nullable=False, default=0)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        # tx당 1행 불변식(위 결정 3). 재도달은 IntegrityError로 걸러 첫 기록을 보존한다.
        Index("uq_effort_transaction", "transaction_id", unique=True),

        # 집계(`crud.get_effort_stats`)는 창(window) 안의 행을 session_id로 묶어 평균한다.
        # INCLUDE에 GROUP BY 키와 합산 대상 전부를 담아 Index Only Scan으로 끝낸다 —
        # 이 테이블은 tx당 1행이라 audit_logs보다 훨씬 작지만, 대시보드 경로에 얹히는 이상
        # 1,000만 tx 시점에도 힙 방문이 없어야 한다.
        # PostgreSQL 전용 옵션(postgresql_*)은 SQLite에서 무시되어 일반 timestamp 인덱스가 된다.
        Index(
            "idx_effort_window",
            "timestamp",
            postgresql_include=["session_id", "key_count", "mouse_count",
                                "nav_count", "nav_preserved_count"],
        ),
    )


class DatabaseOutbox(Base):
    __tablename__ = "database_outbox"

    # [C-3] 레거시 중복 인덱스 정리: id의 index=True(pkey와 완전 중복·실측 124MB),
    # event_uuid의 unique/index(224MB — 조회처 전무, uuid4 유일성은 통계적으로 보장),
    # status의 비부분 index(44MB — 부분 인덱스 idx_outbox_pending/idx_outbox_failed로 대체)를 제거.
    # 기존 운영 DB의 해당 인덱스는 scripts/setup_db_performance.py의 멱등 DROP으로 정리한다.
    id = Column(Integer, primary_key=True)
    event_uuid = Column(String, nullable=False)
    event_type = Column(String(50), nullable=False)
    table_name = Column(String(100), nullable=False)
    payload = Column(JSON().with_variant(JSONB, "postgresql"), default=dict, nullable=False)
    status = Column(String(20), default="PENDING")
    retry_count = Column(Integer, default=0)
    # [Latency Fix #3] 비부분 boolean 인덱스(전체 행 색인) 대신 아래 부분 인덱스(WHERE processed_chain=false)로 대체.
    processed_chain = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    processed_at = Column(DateTime(timezone=True), nullable=True)
    # [Reliability F1] 브로드캐스트 전달 확정 시각. 커밋 직후엔 NULL(통지할 메시지가 있는 그룹) 또는
    # 즉시 스탬프(통지할 메시지가 없는 no-op 그룹). NULL로 남은 SUCCESS 행 = 통지 미확정 →
    # 주기 스윕이 감지·재발사(batch_refresh_required)·확정한다. eventual delivery 보장의 durable 마커.
    broadcast_at = Column(DateTime(timezone=True), nullable=True)

    # [핵심] Outbox 폴링 스캔 최적화 색인 일람.
    # 부분 인덱스(postgresql_where)는 PostgreSQL에서만 조건이 적용되고 SQLite에서는 조건이 무시된
    # 일반 인덱스로 생성되므로 두 dialect 모두 안전하게 create_all 가능하다.
    _outbox_index_list = [
        Index("idx_outbox_pending", "status", postgresql_where=text("status = 'PENDING'")),

        # [Latency Fix #1] SYSTEM_RELOAD 트리거 조회(event_type=='SYSTEM_RELOAD' order by id desc) 전용 부분 인덱스.
        # (event_type, id) 복합으로 id 정렬 first()까지 색인만으로 처리.
        Index("idx_outbox_reload", "event_type", "id", postgresql_where=text("event_type = 'SYSTEM_RELOAD'")),

        # [Latency Fix #3] 미처리 체인 이벤트 큐 스캔(processed_chain==false order by id asc) 전용 부분 인덱스.
        Index("idx_outbox_unprocessed", "processed_chain", "id", postgresql_where=text("processed_chain = false")),

        # [Reliability F1] 통지 미확정(broadcast_at IS NULL) 교정 행 안전망 스윕 전용 부분 인덱스.
        # 정상 상태(전달 확정)에선 거의 빈 인덱스이므로 1000만행 누적에도 스윕이 O(미전달)로 안전하다.
        Index("idx_outbox_undelivered", "id",
              postgresql_where=text("processed_chain = true AND status = 'SUCCESS' AND broadcast_at IS NULL")),

        # [C-3] 보관 정책(7일) purge 대상 탐색 전용 부분 인덱스 — 처리 완료 행의 created_at 정렬 탐색.
        # 7일 보관이 유지되는 정상 상태에선 테이블 자체가 소규모로 유지되어 인덱스도 작다.
        Index("idx_outbox_purge", "created_at",
              postgresql_where=text("processed_chain = true")),

        # [C-3] FAILED 격리 이벤트 관리 API(/admin/outbox/failed·retry-failed) 전용 부분 인덱스.
        # 비부분 status 인덱스(ix_database_outbox_status) DROP의 대체 — FAILED는 극소수라 사실상 빈 인덱스.
        Index("idx_outbox_failed", "status", "id",
              postgresql_where=text("status = 'FAILED'")),
    ]
    if not is_sqlite:
        _outbox_index_list.append(
            # [Latency Fix #3] tx 보완 쿼리(payload->>'transaction_id') 가속용 표현식 인덱스.
            # JSON 연산자는 PostgreSQL 전용이므로 dialect 가드로 SQLite에서는 생성하지 않는다.
            Index("idx_outbox_txid", text("((payload->>'transaction_id'))")),
        )
    __table_args__ = tuple(_outbox_index_list)

    @property
    def safe_payload(self) -> dict:
        """
        Guarantees payload is returned as a python dictionary even if stored as a JSON string.
        """
        from utils.payload_helper import get_payload_dict
        return get_payload_dict(self.payload)


class FileIngestionLog(Base):
    __tablename__ = "file_ingestion_logs"

    id = Column(Integer, primary_key=True)  # [D3] see AuditLog.id - no index=True on a PK
    filename = Column(String, index=True)
    filepath = Column(String)
    table_name = Column(String, index=True)
    status = Column(String(20), default="FAILED", index=True) # "FAILED", "SUCCESS", "PENDING"
    error_message = Column(String, nullable=True)
    retry_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class FileIngestionCheckpoint(Base):
    """[P2] 파일 인제션 오프셋 체크포인트 + 해시 dedup 원장.

    설계 결정 — 왜 `file_ingestion_logs`에 컬럼을 추가하지 않았는가:
      1) `Base.metadata.create_all`은 **기존 테이블에 컬럼을 추가하지 않는다**. 운영 DB에
         이미 존재하는 `file_ingestion_logs`에 컬럼을 늘리면 ALTER 마이그레이션이 모든
         조회 프로세스보다 **먼저** 돌아야 하고, 그 전에 웹서버가 SELECT하면 admin File 탭이
         UndefinedColumn 500으로 죽는다. 신규 테이블 CREATE는 그런 순서 의존이 없다.
      2) 수명이 다르다 — `file_ingestion_logs`는 시도(attempt)마다 append되는 이력이고,
         체크포인트는 (테이블, 파일내용)당 **단일 최신 상태**다. 후자에 필요한
         UNIQUE(table_name, file_signature)는 전자의 append 의미론과 양립하지 않는다.
      3) 체크포인트는 청크 커밋마다(=1000행마다) 쓰이는 핫패스다. 이력 테이블을 계속
         UPDATE하면 이력의 불변성(append-only) 계약이 깨진다.
    재개/스킵 **사실 자체**는 기존 `FileIngestionLog.error_message`(=detail 슬롯,
    main.py의 SUCCESS detail 관례와 동일)에 사람이 읽는 문장으로 함께 남긴다.

    [확장성] (table_name, file_signature) UNIQUE 인덱스 단일 조회 — 파일 1건당 1행이므로
    1,000만 행 데이터에서도 이 테이블은 '처리한 파일 수' 규모로만 자란다.
    """

    __tablename__ = "file_ingestion_checkpoints"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    table_name = Column(String(100), nullable=False)
    # "sha256:<size_bytes>:<hexdigest>" — §B 시그니처(compute_file_signature)
    file_signature = Column(String(120), nullable=False)
    filename = Column(String, nullable=True)
    filepath = Column(String, nullable=True)
    # 이 시그니처를 해석했을 때의 파서 정체성("std" / "pipeline:<ClassName>") —
    # 파서가 바뀌면 행 순서·건수가 달라질 수 있으므로 재개 가부 판정에 사용한다.
    source_kind = Column(String(120), nullable=True)
    total_rows = Column(Integer, nullable=True)
    # 커밋이 완료된 행 수 = 다음 실행의 재개 오프셋 (청크 커밋과 **같은 트랜잭션**에서 갱신)
    processed_rows = Column(Integer, nullable=False, default=0)
    chunk_index = Column(Integer, nullable=False, default=0)
    # "IN_PROGRESS"(재개 대상) | "DONE"(dedup 대상)
    status = Column(String(20), nullable=False, default="IN_PROGRESS")
    note = Column(String, nullable=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_fic_identity", "table_name", "file_signature", unique=True),
        Index("idx_fic_signature", "file_signature", "status"),
    )


class CellOverwrite(Base):
    __tablename__ = "cell_overwrites"

    # [D3] no index=True on a PK column - see AuditLog.id
    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    table_name = Column(String, nullable=False, index=True)
    row_id = Column(String, nullable=False, index=True)
    column_name = Column(String, nullable=False, index=True)
    is_overwrite = Column(Boolean, default=True)
    updated_by = Column(String, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    manual_priority_source = Column(String, nullable=True)

    __table_args__ = (
        Index("idx_overwrites_lookup", "table_name", "row_id"),
        Index("idx_overwrites_lookup_col", "table_name", "row_id", "column_name", unique=True),
    )

class CellSource(Base):
    __tablename__ = "cell_sources"

    # [D3] no index=True on a PK column - see AuditLog.id
    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    table_name = Column(String, nullable=False, index=True)
    row_id = Column(String, nullable=False, index=True)
    column_name = Column(String, nullable=False, index=True)
    source_name = Column(String, nullable=False)
    value = Column(JSON, nullable=True)
    ingested_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_by = Column(String, nullable=True)
    # [Frame confirmation, spec MAP_ALIGNMENT §0.2 layer 8 / §0.3 note 4] Which frame
    # confirmation this cell was derived under. NULL means "not derived from a confirmed
    # coordinate system" and is the state of every pre-existing row.
    #
    # This is a SEPARATE AXIS from `source_name`, deliberately. Spelling the stamp as a
    # source name (`frame_confirm:<uid>`) was the obvious move and it is wrong:
    # `crud.get_source_priority` is an exact-name dict lookup returning 99 on a miss, and a
    # per-confirmation name can never be pre-registered in SOURCE_PRIORITY. Every stamped
    # cell would sink below `custom_script` and `chain_ingestion`, so the stamp would demote
    # the very value it stamps. A confirmation supplies no value; it names the frame the
    # value was computed IN. Different axis, different column.
    #
    # The scoping question this answers is "which cells were derived under this
    # confirmation" - it does NOT introduce a re-derivation mechanism. Retraction stays
    # `chain_replay.withdraw_source`; `frame_trigger_scope`, `chain_replay` R1/R2 and
    # `plan_retraction` remain the only spellings of that.
    confirmation_uid = Column(String, nullable=True)

    __table_args__ = (
        Index("idx_sources_lookup", "table_name", "row_id", "column_name"),
        Index("idx_sources_lookup_source", "table_name", "row_id", "column_name", "source_name", unique=True),
        # [R2 withdraw] The ONLY index that can bound "which cells does this source
        # claim". `idx_sources_lookup_source` cannot: `source_name` is its LAST key,
        # so a `(table_name, source_name)` predicate leaves it unusable and the
        # planner falls back to a full parallel Seq Scan of the WHOLE table --
        # measured 2026-07-31 on 13,148,355 rows: 861ms, 263,369 buffers, 13.07M
        # rows discarded by Filter, for 75,000 matches.
        #
        # Key order: `column_name` third because `chain_replay._claimed_filter`
        # takes an optional column list, and third position turns that from an
        # in-index filter into part of the Index Cond. `row_id` fourth makes the
        # scan COVERING for `withdraw_source` step 1, which selects exactly
        # (row_id, column_name) -- without it the planner weighs one heap fetch per
        # match against a seq scan and can go back to the seq scan.
        #
        # ALSO DECLARED in server/scripts/setup_db_performance.py Step 3.10 --
        # **fix both places**. create_all does not add indices to a table that
        # already exists, so that script is the only path onto an existing
        # database (`idx_audit_user_recorrection` is here for the same reason).
        Index("idx_sources_by_source", "table_name", "source_name", "column_name", "row_id"),

        # [Frame confirmation] "which cells were derived under this confirmation". PARTIAL
        # so it indexes only stamped rows -- the overwhelming majority of this table is and
        # will stay NULL here, and a non-partial index would carry all of them for nothing.
        # Same caveat as the sibling above: create_all skips an existing table, so
        # migrations/add_frame_confirmation.py is the path onto a live database.
        Index("idx_sources_confirmation", "confirmation_uid", "table_name", "row_id",
              postgresql_where=text("confirmation_uid IS NOT NULL")),
    )


# ----------------- [Ontology G1] PG 엣지 스토어 (docs/spec/ONTOLOGY_GRAPH_SPEC.md §2) -----------------
# 저장소 중립 속성 그래프의 PostgreSQL 물리화. table_config과 무관한 **시스템 테이블**이며
# 부팅 create_all + ensure_graph_tables(핫리로드/워커 부팅 경로)로 항상 존재가 보장된다.

class GraphNode(Base):
    __tablename__ = "graph_nodes"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    label = Column(String(100), nullable=False)
    # 복수 컬럼 identity는 "|" 조인 문자열로 정규화(graph_materializer.compose_identity 참조)
    identity_key = Column(String, nullable=False)
    props = Column(JSON().with_variant(JSONB, "postgresql"), default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        # [인덱스 규율 §2] (label, identity_key) UNIQUE — 정확 일치 MERGE의 물리적 실체.
        Index("idx_graph_nodes_identity", "label", "identity_key", unique=True),
    )


class GraphEdge(Base):
    __tablename__ = "graph_edges"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    type = Column(String(100), nullable=False)
    from_node = Column(BigInteger().with_variant(Integer, "sqlite"), nullable=False)
    to_node = Column(BigInteger().with_variant(Integer, "sqlite"), nullable=False)
    props = Column(JSON().with_variant(JSONB, "postgresql"), default=dict)
    # 엣지 provenance = 셀 레이어링의 그래프 확장(§2). G1은 저장까지 — 표시 우선순위 계산은 G2.
    source_name = Column(String, nullable=False, default="unknown")
    source_row_ref = Column(String, nullable=True)   # "table_name:row_id"
    updated_by = Column(String, nullable=True)
    event_time = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        # [인덱스 규율 §2] k-hop 순회가 인덱스 룩업의 연쇄가 되도록 — 인덱스 없는 엣지 접근 경로 금지.
        Index("idx_graph_edges_from_type", "from_node", "type"),
        Index("idx_graph_edges_to_type", "to_node", "type"),
        # 멱등 UPSERT 키: 동일 (from, type, to, source_name) 엣지는 1개만 존재.
        # source_name은 nullable=False(기본 "unknown") — NULL 중복 우회를 구조적으로 차단.
        Index("idx_graph_edges_upsert", "from_node", "type", "to_node", "source_name", unique=True),
        # [QA H2] 재교정(retarget) 시 같은 원본 로우가 과거에 주장한 구 엣지 조회용 —
        # source_row_ref 기반 stale 엣지 삭제가 인덱스 룩업이 되도록.
        Index("idx_graph_edges_row_ref", "source_row_ref"),
    )


class GraphSyncState(Base):
    """[Ontology G1] materializer의 outbox 소비 커서 (프로세스 재시작에도 durable).

    outbox의 processed_chain 플래그는 체인 워커 전용이므로, 그래프 materializer는
    자체 keyset 커서(last_outbox_id)로 증분 소비한다. id=1 단일 행 규약.
    """
    __tablename__ = "graph_sync_state"

    id = Column(Integer, primary_key=True)
    last_outbox_id = Column(BigInteger().with_variant(Integer, "sqlite"), nullable=False, default=0)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# --------- [맵 정렬 스펙 §0.2 층 ⑧] 좌표계 확정 기록 — 사슬에서 쓰는 유일한 층 ---------
# 사람이 「이 설비·제품의 좌표계는 이것이다」라고 정한 사실의 정본. 계산하지 않는다.
#
# [왜 enrichment 위에 얹는가 — 대체가 아니라 보완이다]
# 확정의 **몸짓**은 `enrichment_rules.json`의 `eqp_product_frame_attribution`이 이미 갖고
# 있고 그것을 그대로 쓴다: 판단 단위가 `decision_key = (dt_eqp, product)`로 이미 이 층의
# 단위이고, 사람 확인 경로·auto_confirm 스윕·reference_views·후보 제시가 전부 있으며
# 누가·언제는 cell_overwrites가 이미 나른다. 여기서 그 어느 것도 다시 만들지 않는다.
# 다만 그 경로가 **구조적으로 담을 수 없는 것**이 셋이라 이 표가 필요하다.
#
#   1. 소스 목록 — `eqp_frame_attribution`의 bk는 `dt_eqp|product` 하나라 단위당 한 행이
#      영원히 한 행이다. N개 소스는 N행이 필요하고, 한 셀에 JSON으로 접으면 기여자가 한
#      덩어리로 뭉개져 「가장 약한 기여자」 계산이 시작되기도 전에 불가능해진다.
#   2. 소스별 정렬 — `map_alignment.score_candidates`는 소스 맵마다 (프레임, dx, dy)를
#      **푼다**. 스칼라 target_field 둘은 프레임 하나씩만 담고 시프트를 담을 자리가 없다.
#      시프트는 장식이 아니다. 0이 아닌 시프트를 버리면 다이가 통째로 밀린다.
#   3. 판(version) — 이것이 결정적이다. `idx_sources_lookup_source`가
#      (table, row, column, source_name) UNIQUE라 재확정은 같은 셀을 제자리에서 덮어쓴다.
#      셀 이력 테이블은 없고 audit_logs 행은 가리킬 수 있는 대상이 아니다. 파생 행이
#      「내가 어느 확정 아래에서 만들어졌나」를 가리키려면 안정된 식별자가 있어야 한다.

class FrameConfirmation(Base):
    """확정 한 판의 머리. 설비·제품 하나에 판이 여럿 쌓이고, 지난 판은 지우지 않는다."""
    __tablename__ = "frame_confirmation"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    # 파생 셀(cell_sources.confirmation_uid)이 가리키는 안정 식별자. 판마다 새로 난다.
    confirmation_uid = Column(String, nullable=False)

    # [결정 단위 — 컬럼명을 여기 적지 않는다]
    # 단위의 정본은 인리치먼트 규칙의 `decision_key` 선언이다(`map_alignment` 모듈 상단과
    # 같은 규율). 그래서 저장도 규칙 이름 + 키 값으로 한다.
    #   rule_name    선언한 규칙(예 eqp_product_frame_attribution)
    #   unit_key     그 규칙 파생 테이블의 business_key_val과 **같은 방식으로** 조립한 문자열.
    #                (composite_key_separator.join(decision_key 값)) — 새 조립 규칙이 아니다.
    #   decision_key 컬럼→값 원본. 나중에 어느 컬럼이었는지 되찾을 수 있어야 한다.
    rule_name = Column(String, nullable=True)
    unit_key = Column(String, nullable=True)
    decision_key = Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)

    # ⚠️ 아래 둘은 **첫 선언(eqp_product_frame_attribution)의 흔적**이고 신규 코드의 단위가
    # 아니다. 지우지 않는 이유는 추가 전용 규율 때문이며, 다른 decision_key를 가진 규칙에서는
    # NULL로 남는다. 판 번호의 유일성은 (rule_name, unit_key, version)이 강제한다.
    dt_eqp = Column(String, nullable=True)
    product = Column(String, nullable=True)
    version = Column(Integer, nullable=False)          # 단위 안에서 1부터

    # [확정의 주체 — 무엇을 정렬했는가]
    # 🔴 제품 소유자 판정 2026-08-05: **확정이 기록하는 것은 「어느 좌표를 정렬했나」다.**
    #    `core_frame`은 이름(프리셋)이고 단위는 좌표 삼중항이다(`map_alignment` §2484,
    #    `client2/src/map2/api.js:349`). 클라는 이 넷을 이미 보내고 있었고 라우트가 하나도
    #    읽지 않았다 — 화면으로 만든 확정은 전부 「무엇을 확정했는지」가 빈 채로 남았다.
    confirmed_frame = Column(String, nullable=True)     # 예 rot90_front
    map_table = Column(String, nullable=True)           # 그 좌표가 사는 테이블
    x_col = Column(String, nullable=True)
    y_col = Column(String, nullable=True)
    value_col = Column(String, nullable=True)           # 없이 간 실행은 NULL(점유 전용)

    # [확정된 값 — 규칙이 선언한 target_field 그대로]
    # 🔴 **키가 규칙 선언에서 온다.** `decision_key`가 컬럼명을 박지 않고 dict로 사는 것과
    #    같은 이유이고 같은 모양이다. 규칙마다 target_fields가 다르므로 컬럼 두 개로는
    #    첫 규칙 하나밖에 담지 못한다 — 실측 2026-08-06: `dt_job_lot_slot_attribution`의
    #    답이 통째로 NULL로 들어가고 라우트는 200을 냈다.
    # 조회는 언제나 (rule_name, unit_key) 색인으로 머리 한 행을 집는 방향이라 프레임 값으로
    # 되짚는 질의가 없다. 생기면 JSONB + GIN이지 컬럼 추가가 아니다.
    frames = Column(JSON().with_variant(JSONB, "postgresql"), nullable=True)

    # ⚠️ 아래 둘은 **첫 선언(eqp_product_frame_attribution)의 target_fields 흔적**이고 위
    # `dt_eqp`/`product`와 정확히 같은 계급이다 — 신규 코드의 단위가 아니다. 그 규칙이 그
    # 이름을 선언할 때만 채워지고 다른 규칙에서는 NULL이다. 지우지 않는 이유는 추가 전용
    # 규율이고, 정본은 위 `frames`다.
    core_frame = Column(String, nullable=True)
    dt_frame = Column(String, nullable=True)

    # 공통 바닥(기준). 무엇 위에 올려놓고 정했는지가 없으면 판정을 재현할 수 없다.
    reference_table = Column(String, nullable=True)
    reference_map_id = Column(String, nullable=True)
    # 🔴 [2026-08-06] **신원만으로는 「그 바닥이 아직 그 바닥인가」에 답하지 못한다.**
    #    위 두 컬럼은 「어느 바닥」에 답하고, 이 컬럼은 「그 바닥이 그때와 같은가」에 답한다.
    #    제품 소유자 요청(「확정 저장시 valid die ref도 저장해줘」)과 같은 아침 QA 지적
    #    (`declared_frame_source: confirmed`가 기준을 이름 대지 못해, 남의 바닥 위에서 난
    #    판정이 이 맵 자신의 것처럼 보인다)이 같은 구멍의 두 얼굴이다.
    #
    #    담는 것은 **채점이 실제로 쓴 기준 셀 수**이지 「그 맵의 크기」가 아니다. 그 구분이
    #    절단(`cell_cap`)을 거짓말로 만들지 않는다 — 채점은 정말 그만큼 썼다.
    #
    #    ⚠️ **이 수가 못 잡는 것**: ① 셀 수가 그대로인 변경(다이 하나가 자리를 옮김) —
    #       개수는 그 축에 대해 눈이 없다. ② 절단된 읽기에서 상한을 넘나드는 변경 —
    #       그때 이 수는 상한이므로 상한 이상은 전부 같아 보인다. 해시면 ①을 잡지만,
    #       총괄 판정(2026-08-06): **개수가 답하는 질문이 실제 질문이므로 해시를 만들지 않는다.**
    #
    #    NULL의 뜻은 **옆 컬럼과 짝으로** 읽는다(§frame_confirmation._reference_of):
    #      · reference_table NULL + 이 값 NULL = **기준을 안 썼다**(정상 상태다 —
    #        소스가 자기 `valid_die_ref` 선언을 따라 채점될 수 있다).
    #      · reference_table 있음 + 이 값 NULL = 판정이 개수를 안 실어 왔다(옛 판 또는
    #        전달 누락). 「0개짜리 바닥」이 아니다.
    reference_cell_count = Column(Integer, nullable=True)

    # 🔴 [2026-08-06] **이 판이 선언된 문턱 위에 섰는가, 개발 기본값 위에 섰는가.**
    #    `map_alignment._rule_on`이 미선언 문턱을 `DEFAULT_THRESHOLDS`로 메우고 그 사실을
    #    `ruling.thresholds_defaulted`로 싣는다(「없는 키와 빈 목록은 받는 쪽에서 같아
    #    보인다」— 그래서 언제나 실린다). 그 사실이 화면에만 있고 기록에 없으면, 잠정 순위로
    #    확정된 판과 선언된 문턱으로 확정된 판이 나중에 구별되지 않는다.
    #
    #    Boolean이 아니라 **어느 키가 기본값을 먹었는지** 담는다 — 같은 자리·같은 비용이고,
    #    「둘 다 미선언」과 「하나만 미선언」은 다른 사실이다. 저장 형태는 쉼표로 이은 키 이름.
    #    세 상태를 가른다: NULL = 판정이 이 사실을 안 실어 왔다(옛 판/전달 누락) ·
    #    `''` = 전부 선언돼 있었다 · `'min_margin_dies,...'` = 이 키들이 기본값이었다.
    thresholds_defaulted = Column(String, nullable=True)

    # 판정 근거 — `map_alignment`가 낸 것을 그대로 옮긴다. 여기서 다시 계산하지 않는다.
    # 백분율을 만들지 않는 규율도 그대로 따라온다(개수만 저장).
    # 🔴 어휘의 정본은 `map_alignment.STATE_*` 하나다. `/view`는 이 값을 **응답 최상위**
    #    `state`에 싣고 `ruling` 안에는 넣지 않는다 — 그래서 「`ruling`을 그대로 넘겨라」를
    #    따른 요청은 상태를 통째로 흘렸고, 이 컬럼은 어휘에 없는 낱말(`unscored`)로
    #    기본값을 먹었다(실측 2026-08-06: `winner=rot0_front` 옆에 `unscored`).
    #    전달되지 않았으면 그 사실을 이름으로 말한다(`frame_confirmation.STATE_NOT_TRANSPORTED`)
    #    — 「채점 안 됨」은 채점이 없었다는 주장이라 거짓이 된다.
    ruling_state = Column(String, nullable=False)       # map_alignment.STATE_*
    ruling_reason = Column(String, nullable=True)       # ruling["reason_code"]
    winner_frame = Column(String, nullable=True)
    margin = Column(Integer, nullable=True)
    discriminating = Column(Integer, nullable=True)

    # [가장 약한 기여자] 스펙 §0.2 ⑨: 합쳐진 셀은 최약 기여자를 따라간다. 산출은
    # graph_materializer의 규칙과 **같은 식**이고, 둘 다 crud.get_source_priority를
    # 부르므로 서열의 원천이 하나다. 여기 저장하는 것은 그 계산의 결과이지 두 번째 규칙이
    # 아니다 — 매번 다시 세지 않으려고 굳혀 둘 뿐이다.
    weakest_source = Column(String, nullable=False)
    weakest_priority = Column(Integer, nullable=False)

    # [D3] **이 판이 가정 위에 서 있는가.** 규격 선언이 없는 소스 맵을 기준 맵의 웨이퍼
    # 치수를 빌려 채점했으면 True다(스펙 §9ⓐ). 가정 위에서 나온 판정은 선언된 기하 위에서
    # 나온 판정과 **다른 사실**이고, 확정을 기록하는 이유 자체가 「나중에 그 가정이 거짓으로
    # 밝혀지면 어느 결정이 그 위에 서 있었나」에 답하기 위해서다 — `cell_sources`의
    # `confirmation_uid`와 같은 논거다. 그 질문이 조인 없이 한 색인으로 풀리도록 머리에 둔다.
    # ⚠️ 이 값은 요청이 실어 오지 않는다. 기여자 행의 `geometry_basis`에서 **쓰기 시점에
    #    유도**한다(`weakest_source`와 같은 계급: 저장된 계산이지 두 번째 규칙이 아니다).
    # NULL = 이 어휘가 생기기 전에 남은 판. 「가정 아님」이 아니라 「모름」이다.
    geometry_assumed = Column(Boolean, nullable=True)

    confirmed_by = Column(String, nullable=False)
    confirmed_at = Column(DateTime(timezone=True), server_default=func.now())

    # 다음 판의 confirmation_uid. **삭제도 UPDATE 아닌 것도 아니다** — 지난 판은 남고
    # 그 아래에서 파생된 셀도 남는다. 무엇을 다시 만들지는 이 표가 정하지 않는다.
    superseded_by = Column(String, nullable=True)
    # 이 판이 밀어낸 직전 판. 위와 짝이라 스캔 없이 양방향으로 사슬을 걷는다 — 재확정 화면이
    # 「무엇을 대체했는가」를 물을 때 버전으로 역산하지 않게 한다.
    supersedes_uid = Column(String, nullable=True)

    # 같은 결정을 담은 enrichment 파생 행. 두 경로가 같은 사실을 말하는지 대조하는 끈.
    enrichment_row_id = Column(String, nullable=True)

    __table_args__ = (
        Index("idx_frame_conf_uid", "confirmation_uid", unique=True),
        # 판 번호는 단위 안에서 유일하다. 동시 확정 두 건이 같은 번호를 받는 것을
        # 애플리케이션 락이 아니라 여기서 막는다.
        Index("idx_frame_conf_rule_unit_ver", "rule_name", "unit_key", "version",
              unique=True),
        # 「이 단위의 현행 판」 조회 — 부분 인덱스라 지난 판이 쌓여도 크기가 안 자란다.
        Index("idx_frame_conf_rule_live", "rule_name", "unit_key",
              postgresql_where=text("superseded_by IS NULL")),
        # [D3] 「어느 결정이 가정 위에 서 있나」 — 가정이 거짓으로 밝혀진 날 물어질 질문
        # 하나. 부분 인덱스라 가정 없는 판이 아무리 쌓여도 크기가 안 자란다.
        # ⚠️ 이 선언은 **두 곳**이다 — migrations/add_frame_confirmation.py도 같이 고쳐야
        # 한다(create_all은 기존 테이블에 인덱스를 만들지 않는다).
        Index("idx_frame_conf_assumed", "rule_name", "unit_key",
              postgresql_where=text("geometry_assumed")),
        # ⚠️ 아래 둘은 첫 선언의 흔적이다(위 dt_eqp/product 주석 참조). 다른 규칙에서는 두 값이
        # NULL이고 PostgreSQL의 UNIQUE는 NULL을 서로 다르게 보므로 아무것도 막지 않는다 —
        # 유일성을 실제로 강제하는 것은 위의 (rule_name, unit_key, version)이다.
        Index("idx_frame_conf_unit_ver", "dt_eqp", "product", "version", unique=True),
        Index("idx_frame_conf_live", "dt_eqp", "product",
              postgresql_where=text("superseded_by IS NULL")),
    )


class FrameConfirmationSource(Base):
    """확정 한 판이 **어느 소스들을 무슨 정렬로** 합쳤는가. 소스 하나에 한 행이다.

    JSON 배열이 아니라 행인 이유: 최약 기여자 계산이 기여자별 서열을 필요로 하고, 한 셀에
    접으면 그 서열이 사라진다. 그리고 소스가 늘어도 색인 조회로 남는다.
    """
    __tablename__ = "frame_confirmation_source"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    confirmation_uid = Column(String, nullable=False)

    role = Column(String, nullable=False)              # bonding_plan 역할명
    source_table = Column(String, nullable=False)
    # NULL 대신 빈 문자열 — 아래 UNIQUE 색인에서 NULL은 서로 같지 않아 중복을 못 막는다.
    map_id = Column(String, nullable=False, default="")

    # 레이어링 소스명. 서열의 정본은 crud.get_source_priority 하나다.
    source_name = Column(String, nullable=False)
    source_priority = Column(Integer, nullable=False)

    # 이 소스에 실제로 적용한 정렬. 프레임만으로는 부족하다 — 시프트가 빠지면 밀린다.
    applied_frame = Column(String, nullable=True)
    shift_dx = Column(Integer, nullable=True)
    shift_dy = Column(Integer, nullable=True)

    agreement = Column(Integer, nullable=True)
    discriminating = Column(Integer, nullable=True)

    # 합의에 못 낀 소스도 **기록한다**. 빠진 소스가 조용히 사라지면 나중에 그것이 없었던
    # 것인지 거절된 것인지 구별할 수 없다. 값은 map_alignment.EXCLUDE_*.
    excluded_reason = Column(String, nullable=True)

    # [D3] 이 소스가 **무엇 위에서** 정렬됐는가 — `map_overlay.GEOMETRY_*` 토큰.
    # `declared`면 이 맵이 스스로 선언한 기하 위에서, `assumed`면 기준 맵에서 빌린 웨이퍼
    # 치수 위에서 정렬됐다는 뜻이다(스펙 §9ⓐ). 제외된 소스는 어디에도 정렬되지 않았으므로
    # 자기 토큰(`auto_registered`·`absent`…)을 그대로 갖는다 — 일어나지 않은 일에 근거를
    # 붙이지 않는다. 판정은 `map_alignment.geometry_basis_of` 하나가 한다.
    # NULL = 이 어휘가 생기기 전의 행. 「선언 위였다」가 아니라 「모름」이다.
    geometry_basis = Column(String, nullable=True)

    __table_args__ = (
        Index("idx_frame_conf_src_unique", "confirmation_uid", "role", "source_table",
              "map_id", unique=True),
        Index("idx_frame_conf_src_lookup", "confirmation_uid"),
        # 층 ⑨(계획)가 「이 맵이 어느 확정의 기여자였나」를 묻는 방향. 위 UNIQUE는 선두가
        # confirmation_uid라 이 질문에 쓰이지 못한다. ⚠️ 이 선언은 **두 곳**이다 —
        # migrations/add_frame_confirmation.py도 같이 고쳐야 한다(create_all은 기존 테이블에
        # 인덱스를 만들지 않는다). `idx_sources_confirmation`과 같은 계급이다.
        Index("idx_frame_conf_src_map", "source_table", "map_id"),
    )


import sys
if not hasattr(sys, "_dynamic_tables_singleton"):
    sys._dynamic_tables_singleton = {}
DYNAMIC_TABLES = sys._dynamic_tables_singleton

from sqlalchemy.orm import registry
mapper_registry = registry()

def init_dynamic_models(config_dict: dict):
    """
    table_config.json 설정을 기반으로 SQLAlchemy Table 객체들을 동적으로 빌드하고
    Imperative Mapping을 사용하여 완전한 ORM 모델 클래스로 매핑해 DYNAMIC_TABLES에 등록합니다.
    이미 로드된 테이블에 새 컬럼이 추가된 경우, 런타임에 동적으로 매핑에 결합(Hot-swap)합니다.
    """
    from sqlalchemy import Table, Column, String, DateTime, Float, Index, Boolean
    from sqlalchemy.sql import func
    from sqlalchemy.orm import class_mapper
    
    for table_name, table_cfg in config_dict.items():
        col_types = table_cfg.get("column_types", {})
        
        # 이미 로드된 동적 테이블 모델 클래스가 존재하는 경우 -> 새 컬럼 핫스왑 처리
        if table_name in DYNAMIC_TABLES:
            dynamic_class = DYNAMIC_TABLES[table_name]
            table_obj = dynamic_class.__table__
            mapper = class_mapper(dynamic_class)
            
            for col_name, type_str in col_types.items():
                if col_name in ["created_at", "updated_at", "is_graph_synced", "needs_graph_rollback", "graph_synced_at"]:
                    continue
                if col_name not in table_obj.columns:
                    if type_str == "number":
                        sql_type = Float
                    elif type_str == "datetime":
                        sql_type = DateTime(timezone=True)
                    else:
                        sql_type = String
                        
                    col_obj = Column(col_name, sql_type, nullable=True)
                    table_obj.append_column(col_obj)
                    mapper.add_property(col_name, col_obj)
            continue
            
        # 1. 모든 동적 물리 테이블이 공유할 메타데이터 컬럼들
        columns = [
            # [D3] no index=True on a PK column - see AuditLog.id. This one declaration
            # produced 26 of the 29 duplicates measured, one per dynamic table
            # (`ix_<table>_row_id` beside `<table>_pkey`), which is why reading the four
            # named model classes and stopping there misses most of the extension.
            Column("row_id", String, primary_key=True),
            # NOTE: `business_key_val` keeps its NON-unique index here, and the UNIQUE
            # index that makes it an enforced identity is built by
            # `server/migrations/add_business_key_unique_index.py` instead. Declaring
            # `unique=True` here would not remove the need for that migration -
            # `create_all` does not add indexes to tables that already exist, so it
            # would be a no-op on exactly the databases where duplicates can already
            # have accumulated. ⚠️ The honest cost of that choice: a FRESHLY created
            # database is unprotected until the migration is run, so the migration
            # belongs in the setup sequence and not only in the upgrade one.
            Column("business_key_val", String, index=True, nullable=True),
            Column("created_at", DateTime(timezone=True), server_default=func.now(), index=True),
            Column("updated_at", DateTime(timezone=True), server_default=func.now(), index=True),
            Column("is_graph_synced", Boolean, default=False, nullable=True, index=True),
            Column("needs_graph_rollback", Boolean, default=False, nullable=True, index=True),
            Column("graph_synced_at", DateTime(timezone=True), nullable=True),
        ]
        
        # 2. table_config에 정의된 사용자 컬럼들을 native 타입으로 바인딩
        col_types = table_cfg.get("column_types", {})
        for col_name, type_str in col_types.items():
            if col_name in ["created_at", "updated_at", "is_graph_synced", "needs_graph_rollback", "graph_synced_at"]:
                continue
            if type_str == "number":
                sql_type = Float
            elif type_str == "datetime":
                sql_type = DateTime(timezone=True)
            else:
                sql_type = String
            columns.append(Column(col_name, sql_type, nullable=True))
            
        # 3. 1,000만 행 스케일에 최적화된 복합 색인(Covering Index) 정의
        idx_bk_name = f"idx_{table_name}_bk"
        idx_updated_name = f"idx_{table_name}_updated"
        
        table_args = (
            Index(idx_bk_name, "business_key_val", "row_id"),
            Index(idx_updated_name, "updated_at", "row_id"),
        )
        
        # 4. Table 객체 동적 생성 및 metadata 등록
        table_obj = Table(
            table_name,
            Base.metadata,
            *columns,
            *table_args,
            extend_existing=True
        )
        
        # 5. 동적 PascalCase 클래스 생성 및 Imperative Mapping 바인딩
        class_name = "".join(part.capitalize() for part in table_name.split("_"))
        dynamic_class = type(class_name, (object,), {
            "__table__": table_obj
        })
        
        mapper_registry.map_imperatively(dynamic_class, table_obj)
        DYNAMIC_TABLES[table_name] = dynamic_class


def sync_dynamic_tables_schema(engine):
    """
    DYNAMIC_TABLES의 정의와 실제 DB 물리 테이블의 스키마를 비교하여,
    설정에는 존재하지만 DB에는 없는 컬럼들을 ALTER TABLE DDL을 통해 자동으로 추가합니다.
    """
    from sqlalchemy import inspect, text
    from sqlalchemy.schema import CreateColumn
    
    inspector = inspect(engine)
    dialect = engine.dialect
    
    for table_name, model_class in DYNAMIC_TABLES.items():
        if not inspector.has_table(table_name):
            continue
            
        db_cols = {c["name"].lower() for c in inspector.get_columns(table_name)}
        table_obj = model_class.__table__
        
        for column in table_obj.columns:
            col_name = column.name
            if col_name.lower() not in db_cols:
                col_ddl = str(CreateColumn(column).compile(dialect=dialect)).strip()
                alter_query = f'ALTER TABLE "{table_name}" ADD COLUMN {col_ddl}'
                print(f"[Schema Sync] Altering table '{table_name}': {alter_query}")
                
                # 각 컬럼 추가 DDL을 개별 독립 트랜잭션으로 격리하여, 한 곳의 실패가 전체 세션을 오염시키는 문제를 영구 방지
                try:
                    with engine.begin() as conn:
                        conn.execute(text(alter_query))
                    print(f"[Schema Sync] Successfully added column '{col_name}' to table '{table_name}'.")
                except Exception as err:
                    print(f"[Schema Sync] Failed to add column '{col_name}' to table '{table_name}': {err}")


# [이슈 #7] 런타임 신규 테이블 물리 CREATE — 동일 프로세스 내 watchdog 스레드와
# /admin/reload-configs 요청 스레드가 동시에 진입할 수 있으므로 in-process 직렬화 락 사용.
import threading
_runtime_ddl_lock = threading.Lock()


def create_missing_dynamic_tables(engine):
    """[이슈 #7] DYNAMIC_TABLES에 등록됐지만 물리 DB에 아직 없는 **신규 테이블만** CREATE한다.

    부팅 시에는 Base.metadata.create_all이 전 테이블을 생성하지만, 런타임 config 핫리로드로
    추가된 테이블은 재기동 전까지 물리 테이블이 없어 조회가 UndefinedTable 500이 된다.
    이 함수가 그 갭을 메운다. 기존 테이블에 대한 런타임 ALTER는 **수행하지 않는다**
    (락 컨보이 방지 — 이슈 #5/C-8 범위 밖).

    안전장치:
    - information_schema 게이트(inspector.has_table): 존재하는 테이블에는 DDL 자체를 발행하지 않음.
    - checkfirst=True: 게이트 통과 직후 타 프로세스가 먼저 CREATE한 경합도 무해화.
    - engine 단위 독립 커넥션/트랜잭션(create_all 내부): 실패 시 자체 rollback되며
      공유 세션 트랜잭션을 오염시키지 않음. 개별 테이블 실패는 격리되어 다음 테이블로 진행.

    반환: 새로 CREATE한 테이블명 리스트.
    """
    from sqlalchemy import inspect

    created = []
    with _runtime_ddl_lock:
        try:
            inspector = inspect(engine)
        except Exception as err:
            print(f"[Schema Sync] Failed to inspect database for missing tables: {err}")
            return created

        for table_name, model_class in list(DYNAMIC_TABLES.items()):
            try:
                if inspector.has_table(table_name):
                    continue
                Base.metadata.create_all(
                    bind=engine, tables=[model_class.__table__], checkfirst=True
                )
                created.append(table_name)
                print(f"[Schema Sync] Created missing physical table '{table_name}' at runtime.")
            except Exception as err:
                # CREATE 경합(DuplicateTable 등) 포함 — 실패를 격리하고 계속 진행
                print(f"[Schema Sync] Failed to create missing table '{table_name}': {err}")
    return created


def ensure_graph_tables(engine):
    """[Ontology G1] 그래프 시스템 테이블(graph_nodes/graph_edges/graph_sync_state)의 존재를 보장한다.

    table_config과 무관한 시스템 테이블이므로 부팅 create_all(웹서버) 외에도
    핫리로드(refresh_dynamic_models)와 그래프 워커 부팅 경로에서 항상 호출된다.
    #7 패턴 준용: information_schema 게이트 + checkfirst + engine 단위 독립 트랜잭션
    (실패가 공유 세션을 오염시키지 않음).

    반환: 새로 CREATE한 테이블명 리스트.
    """
    from sqlalchemy import inspect

    created = []
    graph_models = (GraphNode, GraphEdge, GraphSyncState)
    with _runtime_ddl_lock:
        try:
            inspector = inspect(engine)
        except Exception as err:
            print(f"[Graph Schema] Failed to inspect database for graph tables: {err}")
            return created

        for model_class in graph_models:
            table_name = model_class.__tablename__
            try:
                if inspector.has_table(table_name):
                    continue
                Base.metadata.create_all(
                    bind=engine, tables=[model_class.__table__], checkfirst=True
                )
                created.append(table_name)
                print(f"[Graph Schema] Created graph system table '{table_name}'.")
            except Exception as err:
                # CREATE 경합(DuplicateTable 등) 포함 — 실패를 격리하고 계속 진행
                print(f"[Graph Schema] Failed to create graph table '{table_name}': {err}")
    return created


def ensure_ingestion_checkpoint_table(engine):
    """[P2] 파일 인제션 체크포인트 테이블(file_ingestion_checkpoints)의 존재를 보장한다.

    table_config과 무관한 시스템 테이블이므로 웹서버 부팅 create_all 외에도
    워처 프로세스 부팅(run_watcher)·핫리로드(refresh_dynamic_models)에서 호출한다.
    #7 패턴 준용: information_schema 게이트 + checkfirst + engine 단위 독립 트랜잭션.

    반환: 새로 CREATE한 테이블명 리스트.
    """
    from sqlalchemy import inspect

    created = []
    with _runtime_ddl_lock:
        try:
            inspector = inspect(engine)
        except Exception as err:
            print(f"[Ingestion Schema] Failed to inspect database for checkpoint table: {err}")
            return created

        table_name = FileIngestionCheckpoint.__tablename__
        try:
            if inspector.has_table(table_name):
                return created
            Base.metadata.create_all(
                bind=engine, tables=[FileIngestionCheckpoint.__table__], checkfirst=True
            )
            created.append(table_name)
            print(f"[Ingestion Schema] Created ingestion checkpoint table '{table_name}'.")
        except Exception as err:
            print(f"[Ingestion Schema] Failed to create table '{table_name}': {err}")
    return created


def refresh_dynamic_models(engine=None):
    """[이슈 #7] config 핫리로드 공용 진입점 — table_config.json을 디스크에서 재로드하여
    crud.TABLE_CONFIG 싱글턴과 DYNAMIC_TABLES(ORM 모델)를 갱신하고, engine이 주어지면
    신규 테이블의 물리 CREATE(create_missing_dynamic_tables)까지 수행한다.

    호출처: 웹서버 reload_local_process_cache(/admin/reload-configs),
            워커 SYSTEM_RELOAD 핸들러(run_watcher 폴러, chain_ingestion_worker 루프).
    기존 테이블 ALTER는 수행하지 않는다(부팅 경로 sync_dynamic_tables_schema 전용).

    반환: 새로 CREATE된 테이블명 리스트 (engine 미지정 또는 config 로드 실패 시 []).
    """
    from database import crud  # 순환 import 방지를 위한 지연 import

    new_config = crud.load_table_config()
    if not new_config:
        # 빈/손상 config로 기존 싱글턴을 지우지 않는다 (일시적 파일 읽기 실패 방어)
        return []
    crud.TABLE_CONFIG.clear()
    crud.TABLE_CONFIG.update(new_config)
    init_dynamic_models(new_config)
    if engine is not None:
        created = create_missing_dynamic_tables(engine)
        # [Ontology G1] 그래프 시스템 테이블도 핫리로드 경로에서 항상 존재 보장(#7 패턴 동승).
        created.extend(ensure_graph_tables(engine))
        # [P2] 인제션 체크포인트 테이블도 동일 보장 (워처가 부팅 전 이 경로로 먼저 도달할 수 있음)
        created.extend(ensure_ingestion_checkpoint_table(engine))
        return created
    return []
