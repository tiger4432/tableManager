"""[P2] 파일 인제션 오프셋 체크포인트 + 파일 시그니처 dedup.

해결하는 결함
--------------
P1(heavy 레인)까지의 워처는 1,000행 청크로 적재하되 **진행 오프셋을 어디에도 남기지
않았다**. 재기동/크래시가 나면 99,999행(≈7분) 작업이 통째로 소실되고 파일이 처음부터
재처리됐다. 또 동일 파일이 다시 떨어지거나 스윕이 같은 파일을 다시 집어 올려도 방어가
없었다.

설계 요지
--------------
1. **시그니처** `sha256:<size>:<hexdigest>` — 파일 내용 전체 해시.
   비용 실측(2026-07-26, 본 워크스테이션, 1MB 청크 스트리밍):

   | 크기 | sha256 | blake2b | 선두/말미 1MB 샘플링 |
   |---|---|---|---|
   | 16MB | 0.016s | 0.032s | 0.004s |
   | 100MB | 0.101s | 0.212s | 0.005s |
   | 500MB | 0.535s | 1.147s | 0.005s |

   sha256이 blake2b보다 2배 빠르다(CPU의 SHA 확장 명령 사용, ~935MB/s). 라이브 드릴
   실측 기준 15.6MB 파일의 총 처리 시간은 415초인데 전체 해시는 **16ms(0.004%)**,
   500MB 파일이라도 0.5초다. 샘플링은 더 빠르지만 **중간만 바뀐 파일을 같은 파일로
   오판**해 데이터 유실(재개 오프셋 오적용)·오검출(dedup 오스킵)을 낳는다. 비용이
   무시 가능한 수준이므로 **정확성을 택해 전체 해시**를 채택한다.

2. **체크포인트 갱신 시점** — 청크의 `db.commit()`과 **같은 트랜잭션**에서 UPDATE한다.
   지시서의 "청크 커밋 직후"보다 강한 보장이다: 커밋 전 기록은 유실 시 건너뜀을,
   커밋 후 별도 기록은 그 사이 크래시 시 재적재를 유발하지만, 동일 트랜잭션이면
   "적재된 행 수 == 기록된 오프셋"이 원자적으로 성립한다.

3. **재개 가부 판정** — (table_name, file_signature)로 찾은 IN_PROGRESS 행이
   `total_rows`·`source_kind`까지 일치하고 오프셋이 [0, total_rows] 범위일 때만 재개한다.
   하나라도 어긋나면 **오프셋 0부터 재처리하고 그 사유를 로그 + FileIngestionLog detail에
   명시**한다(조용한 폴백 금지 — P1 QA F1 규율).

4. **멱등성** — 재개 지점이 어긋나도 적재는 business key 기준 upsert이므로 중복 행이
   생기지 않는다(`test_ingestion_checkpoint.py`가 중간 오프셋 강제 재개로 실증).
   따라서 재개 실패의 최악 비용은 '느려짐'이지 '중복/유실'이 아니다.
"""

import hashlib
import logging
import os

logger = logging.getLogger("Watcher.IngestionCheckpoint")

# 시그니처 해시 스트리밍 읽기 단위
_HASH_CHUNK_BYTES = 1024 * 1024

SIGNATURE_ALGO = "sha256"

STATUS_IN_PROGRESS = "IN_PROGRESS"
STATUS_DONE = "DONE"

# 강제 재처리 마커 — 파일명에 이 토큰이 들어 있으면 dedup skip을 우회한다.
# (기존 `user(name)` 파일명 규약과 같은 계열의 명시적 사용자 의사 표현 경로)
FORCE_REINGEST_TOKEN = "__force__"


def compute_file_signature(file_path: str) -> str | None:
    """파일 내용 시그니처 `sha256:<size>:<hexdigest>`. 읽기 실패 시 None.

    None이면 호출자는 체크포인트/dedup을 **비활성화**하고 기존(P1) 동작으로 처리해야 한다
    (시그니처 없이 재개하면 다른 파일에 오프셋을 오적용할 수 있다)."""
    try:
        size = os.path.getsize(file_path)
        h = hashlib.new(SIGNATURE_ALGO)
        with open(file_path, "rb") as f:
            while True:
                block = f.read(_HASH_CHUNK_BYTES)
                if not block:
                    break
                h.update(block)
        return f"{SIGNATURE_ALGO}:{size}:{h.hexdigest()}"
    except PermissionError:
        # 복사 진행 중 잠긴 파일 — 호출자(process_with_retry)의 기존 재시도 경로로 넘긴다.
        # 여기서 None을 반환하면 잠금이 풀린 뒤에도 체크포인트가 조용히 꺼진 채 처리된다.
        raise
    except OSError as e:
        logger.warning(
            f"Could not compute file signature for '{file_path}': {e} — "
            f"checkpoint/dedup disabled for this file (falls back to full reprocessing)."
        )
        return None


def is_force_reingest(filename: str) -> bool:
    """파일명 기반 강제 재처리 요청 여부 (`__force__` 토큰, 대소문자 무시)."""
    return FORCE_REINGEST_TOKEN in (filename or "").lower()


class CheckpointPlan:
    """파일 1건에 대한 체크포인트 계획.

    resume_from: 적재를 건너뛸 선두 행 수 (0이면 처음부터)
    note:        재개/재시작 사유 — 로그와 FileIngestionLog detail에 **반드시** 남긴다.
    active:      False면 체크포인트 비활성(시그니처 계산 실패 등) — 기존 동작 그대로.
    """

    __slots__ = ("table_name", "file_signature", "filename", "filepath",
                 "source_kind", "total_rows", "resume_from", "note", "active")

    def __init__(self, table_name=None, file_signature=None, filename=None, filepath=None,
                 source_kind=None, total_rows=None, resume_from=0, note=None, active=False):
        self.table_name = table_name
        self.file_signature = file_signature
        self.filename = filename
        self.filepath = filepath
        self.source_kind = source_kind
        self.total_rows = total_rows
        self.resume_from = resume_from
        self.note = note
        self.active = active

    @classmethod
    def disabled(cls, note: str = None):
        """체크포인트 비활성 계획. note가 있으면 사용자 detail·이력에 사유가 노출된다
        (시그니처 계산 불가/기록 실패를 조용히 넘기지 않기 위함)."""
        return cls(active=False, note=note)

    @property
    def is_resume(self) -> bool:
        return self.active and self.resume_from > 0


def _get_model():
    from database.models import FileIngestionCheckpoint
    return FileIngestionCheckpoint


def find_checkpoint(db, table_name: str, file_signature: str):
    """(table_name, file_signature) 단일 조회 — UNIQUE 인덱스 사용."""
    Model = _get_model()
    return (
        db.query(Model)
        .filter(Model.table_name == table_name, Model.file_signature == file_signature)
        .one_or_none()
    )


def find_completed_ingestion(db, table_name: str, file_signature: str):
    """같은 테이블에 같은 내용이 이미 완료 적재됐는지 — dedup 판정용."""
    row = find_checkpoint(db, table_name, file_signature)
    if row is not None and row.status == STATUS_DONE:
        return row
    return None


def plan_ingestion(db, table_name: str, file_signature: str, filename: str, filepath: str,
                   total_rows: int, source_kind: str, force_restart: bool = False) -> CheckpointPlan:
    """체크포인트 행을 준비하고 재개 오프셋을 결정한다 (커밋은 호출자 책임 아님 — 여기서 커밋).

    force_restart=True면 기존 진행분을 무시하고 0부터 재적재한다(사용자 명시 재처리 경로).
    """
    Model = _get_model()
    plan = CheckpointPlan(
        table_name=table_name, file_signature=file_signature, filename=filename,
        filepath=filepath, source_kind=source_kind, total_rows=total_rows,
        resume_from=0, active=True,
    )

    row = find_checkpoint(db, table_name, file_signature)
    if row is None:
        row = Model(
            table_name=table_name, file_signature=file_signature, filename=filename,
            filepath=filepath, source_kind=source_kind, total_rows=total_rows,
            processed_rows=0, chunk_index=0, status=STATUS_IN_PROGRESS,
        )
        db.add(row)
        db.commit()
        return plan

    # 기존 행이 있다 — 재개 가부를 명시적으로 판정한다.
    reason = None
    if force_restart:
        reason = "사용자 명시 재처리(force) 요청"
    elif row.status == STATUS_DONE:
        reason = f"이전 적재가 이미 완료(DONE, {row.processed_rows}행) 상태"
    elif row.source_kind != source_kind:
        reason = f"파서 정체성 불일치({row.source_kind!r} → {source_kind!r})"
    elif row.total_rows != total_rows:
        reason = f"총 행 수 불일치({row.total_rows} → {total_rows})"
    elif row.processed_rows is None or row.processed_rows < 0 or (
        total_rows is not None and row.processed_rows > total_rows
    ):
        reason = f"오프셋 손상(processed_rows={row.processed_rows}, total_rows={total_rows})"

    if reason is None:
        plan.resume_from = int(row.processed_rows or 0)
        if plan.resume_from > 0:
            plan.note = (
                f"[resume] 이전 실행의 체크포인트 {plan.resume_from:,}행에서 재개 "
                f"(총 {total_rows:,}행, chunk_index={row.chunk_index})"
            )
            logger.info(f"[{table_name}] ⏩ {plan.note} — {filename}")
    else:
        plan.resume_from = 0
        plan.note = (
            f"[resume-abort] 체크포인트를 사용할 수 없어 처음부터 재처리 — 사유: {reason} "
            f"(기록된 오프셋 {row.processed_rows}행은 폐기)"
        )
        logger.warning(f"[{table_name}] ⚠️ {plan.note} — {filename}")

    row.filename = filename
    row.filepath = filepath
    row.source_kind = source_kind
    row.total_rows = total_rows
    row.status = STATUS_IN_PROGRESS
    row.note = plan.note
    if plan.resume_from == 0:
        row.processed_rows = 0
        row.chunk_index = 0
    db.commit()
    return plan


def record_chunk_progress(db, plan: CheckpointPlan, processed_rows: int, chunk_index: int):
    """청크 적재와 **같은 세션·같은 트랜잭션**에서 오프셋을 갱신한다.

    호출 위치 계약: `crud.apply_batch_updates(...)` **직전**, 같은 세션.
    `apply_batch_updates`는 내부에서 `db.commit()`을 수행하므로, 그 이전에 발행한
    이 UPDATE가 청크 데이터와 **한 번의 커밋으로 함께 확정**된다
    ("커밋된 행 수 == 기록된 오프셋"의 원자적 성립). 호출 이후에 쓰면 별도 트랜잭션이 되어
    두 커밋 사이에 크래시하면 데이터만 들어가고 오프셋은 안 오르는 창이 생긴다
    (업서트 멱등성 덕에 유실이 아니라 재적재로만 열화되지만, 원자성이 더 낫다).

    ORM 객체가 아닌 Core UPDATE를 쓰는 이유: before_flush(outbox 스테이징) 리스너와
    무관하게 동작시키고, 청크 세션에 불필요한 ORM 아이덴티티를 남기지 않기 위함.
    """
    if not plan.active:
        return
    Model = _get_model()
    db.query(Model).filter(
        Model.table_name == plan.table_name,
        Model.file_signature == plan.file_signature,
    ).update(
        {"processed_rows": processed_rows, "chunk_index": chunk_index},
        synchronize_session=False,
    )


def mark_done(db, plan: CheckpointPlan, processed_rows: int = None, note: str = None):
    """파일 처리 성공 확정 — 이후 같은 시그니처는 dedup skip 대상이 된다."""
    if not plan.active:
        return
    Model = _get_model()
    values = {"status": STATUS_DONE}
    if processed_rows is not None:
        values["processed_rows"] = processed_rows
    if note is not None:
        values["note"] = note
    db.query(Model).filter(
        Model.table_name == plan.table_name,
        Model.file_signature == plan.file_signature,
    ).update(values, synchronize_session=False)
    db.commit()
