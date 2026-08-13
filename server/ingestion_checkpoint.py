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

Two-tier ledger (2026-08-13)
----------------------------
The content signature above answers "have I processed this?" **only by reading
the whole file**. That was affordable only because a processed file was MOVED
out of `raws/`, so the tree the sweep walks was normally empty. Once files stay
where they land, the sweep's cost becomes O(files in tree) *hashes*.

Measured on this box over the 22,626 files that today's `archives/` holds
(194.6 MB) — i.e. exactly the set that would accumulate in `raws/`:

    listdir + stat   1.0 s      (575 files/s hashing is per-FILE-bound, not
    full sha256     39.4 s       byte-bound: 4.9 MB/s over many small files)

So a cheap first tier is added:

  * **Tier 1** — `(table_name, filepath, file_mtime, file_size)` all match a
    ledger row in a TERMINAL state (`DONE` or `FAILED`) -> skip, **one stat, no
    read**. "Terminal" and not "DONE" on purpose: today a failed file is not
    retried because it was moved to `err/`; with no move, the FAILED ledger row
    is what carries that same fact.
  * **Tier 2** — anything differs -> hash, exactly as before. **The content
    signature remains the final authority.** A completed row found by content
    under a different path still skips, and the ledger adopts the new location
    when the recorded one is gone.

🔴 **Failure direction of tier 1, stated so nobody has to rediscover it.**
Tier 1 fails toward **not re-reading a file whose content changed while mtime
and size stayed identical**. That is reachable: some copy tools preserve mtime,
and a same-microsecond rewrite of equal length does it too. For a fab feed that
writes each file once this is the right trade (39x cheaper sweeps), but it is a
**judgement, not a free lunch**. Two escapes exist and both must keep working:
`ingestion_settings.json` `dedup_by_path_stat: false` (forces hashing), and the
`__force__` filename token (forces full re-ingestion of one file).
"""

import hashlib
import logging
import os
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("Watcher.IngestionCheckpoint")

# 시그니처 해시 스트리밍 읽기 단위
_HASH_CHUNK_BYTES = 1024 * 1024

SIGNATURE_ALGO = "sha256"

# Tier-1 identity of an UNREADABLE file. `compute_file_signature` returns None
# when the content cannot be read at all, and the ledger's unique key is
# (table_name, file_signature) — so a failure on such a file had nowhere to be
# recorded and, with no move to `err/`, would be retried on every restart
# forever. This prefix is deliberately NOT `sha256:`, so a stat identity can
# never be confused with (or collide with) a content signature. It is a
# DECLARED key, not a marker pressed into service as one (SCHEMA_CANON R6).
STAT_SIGNATURE_PREFIX = "stat"

STATUS_IN_PROGRESS = "IN_PROGRESS"
STATUS_DONE = "DONE"
# A terminal answer that is NOT success. Before the ledger carried this, the
# only record of "this file failed" was its LOCATION (`err/`); a mode that stops
# moving files therefore has to write the fact down instead of walking past it.
STATUS_FAILED = "FAILED"

# States that mean "I have already reached a terminal answer about this exact
# file". Tier 1 skips on these; tier 2 (content dedup) still skips on DONE only.
TERMINAL_STATUSES = (STATUS_DONE, STATUS_FAILED)

_EPOCH_UTC = datetime(1970, 1, 1, tzinfo=timezone.utc)

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


def mtime_ns_to_datetime(mtime_ns: int) -> datetime:
    """`st_mtime_ns` -> tz-aware UTC datetime **truncated to whole microseconds**.

    Integer arithmetic on purpose. `datetime.fromtimestamp(st.st_mtime)` goes
    through a float, and tier 1 compares this value with `=`: a value that is
    not reproduced bit-for-bit from the same file simply MISSES, silently, and
    the fast path quietly stops existing. Truncation (not rounding) to
    microseconds is what PostgreSQL's `timestamptz` stores anyway, so the value
    written and the value re-derived on the next sweep are identical.
    """
    return _EPOCH_UTC + timedelta(microseconds=int(mtime_ns) // 1000)


def read_file_stat(file_path: str):
    """`(mtime_datetime, size_bytes)` for tier 1, or `None` when unavailable.

    One `os.stat`. `None` (vanished / unstattable) makes tier 1 MISS, which is
    the safe direction: the file falls through to the existing full-hash path.
    """
    try:
        st = os.stat(file_path)
    except OSError:
        return None
    return mtime_ns_to_datetime(st.st_mtime_ns), int(st.st_size)


def stat_identity_signature(file_stat) -> str | None:
    """Ledger key for a file whose CONTENT could not be read — `stat:<size>:<us>`.

    Only ever used to record a FAILURE (see `record_failure`). Never used for
    dedup-by-content: `find_completed_ingestion` is called with a real
    `sha256:` signature or not at all.
    """
    if not file_stat:
        return None
    mtime, size = file_stat
    micros = int((mtime - _EPOCH_UTC).total_seconds() * 1_000_000)
    return f"{STAT_SIGNATURE_PREFIX}:{size}:{micros}"


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
    """같은 테이블에 같은 내용이 이미 완료 적재됐는지 — dedup 판정용.

    **DONE만** 해당한다. FAILED는 「이 파일에 대한 결론」이지 「이 내용을 적재했다」가
    아니므로, 같은 내용이 다른 경로로 다시 오면 재시도하는 것이 맞다(종전 동작 유지)."""
    row = find_checkpoint(db, table_name, file_signature)
    if row is not None and row.status == STATUS_DONE:
        return row
    return None


def find_terminal_by_path_stat(db, table_name: str, filepath: str, file_stat):
    """**Tier 1** — 같은 경로·같은 (mtime, size)에 대해 이미 종결된 행. 없으면 None.

    조회 조건이 `idx_fic_path_stat`(table_name, filepath, file_mtime, file_size)를
    그대로 탄다. 세 값 중 하나라도 NULL이면 SQL `=`가 참이 될 수 없으므로 tier 1은
    **자동으로 miss**한다 — 이 컬럼들이 없던 시절에 적힌 행(그리고 filepath가 NULL인
    행)은 tier 1의 대상이 아니라는 NULL 계약이 여기서 강제된다.

    행이 둘 이상일 수 있다(같은 경로가 여러 내용을 담았다가 mtime까지 같아진 경우).
    상한이 걸린 읽기이므로 **전순서**를 준다(SCHEMA_CANON R7): 최신 갱신 → id 역순.
    """
    if not table_name or not filepath or not file_stat:
        return None
    file_mtime, file_size = file_stat
    Model = _get_model()
    return (
        db.query(Model)
        .filter(
            Model.table_name == table_name,
            Model.filepath == filepath,
            Model.file_mtime == file_mtime,
            Model.file_size == file_size,
            Model.status.in_(TERMINAL_STATUSES),
        )
        .order_by(Model.updated_at.desc(), Model.id.desc())
        .first()
    )


def adopt_new_location(db, row, filepath: str, file_stat) -> bool:
    """Tier-2 dedup 적중 시 **새 경로를 원장에 기록**한다. 반영했으면 True.

    이 원장의 유일 키는 `(table_name, file_signature)` 하나뿐이므로 한 내용은 한 행,
    즉 **경로를 하나만** 기억할 수 있다. 그래서 규칙은:

      - 기록된 경로가 디스크에 **없으면** 새 위치를 채택한다 (파일이 옮겨졌거나
        정리된 뒤 다시 떨어진 정상 경우 — 다음 스윕부터 tier 1이 적중한다).
      - 기록된 경로가 **아직 살아 있으면** 건드리지 않는다. 사본 둘이 공존하는데
        경로를 옮기면 스윕마다 두 사본이 서로를 밀어내며(ping-pong) 매번 해시가
        다시 돈다. 대신 그 사본은 `note`에 위치가 남고, **스윕당 해시 1회**의
        비용이 남는다(사본 수에 비례할 뿐 트리 크기와 무관 — 보고서에 명시).
    """
    if row is None or not filepath or not file_stat:
        return False
    file_mtime, file_size = file_stat
    recorded = row.filepath
    if recorded and os.path.normcase(os.path.abspath(recorded)) == os.path.normcase(filepath):
        # Same place, possibly touched: refresh the stat so tier 1 hits again.
        if row.file_mtime == file_mtime and row.file_size == file_size:
            return False
    elif recorded and os.path.exists(recorded):
        note = f"[dedup-alt-location] 같은 내용의 사본이 여기에도 있음: {filepath}"
        if row.note == note:
            return False
        row.note = note
        db.commit()
        return True
    row.filepath = filepath
    row.file_mtime = file_mtime
    row.file_size = file_size
    db.commit()
    return True


def plan_ingestion(db, table_name: str, file_signature: str, filename: str, filepath: str,
                   total_rows: int, source_kind: str, force_restart: bool = False,
                   file_stat=None) -> CheckpointPlan:
    """체크포인트 행을 준비하고 재개 오프셋을 결정한다 (커밋은 호출자 책임 아님 — 여기서 커밋).

    force_restart=True면 기존 진행분을 무시하고 0부터 재적재한다(사용자 명시 재처리 경로).
    file_stat=`(mtime, size)`가 오면 tier-1 조회 키를 같이 심는다 — **적재를 시작한
    시점의 파일 모습**이므로, 도중에 파일이 바뀌면 다음 스윕의 tier 1이 miss하여
    재적재로 떨어진다(안전한 방향).
    """
    Model = _get_model()
    file_mtime, file_size = file_stat if file_stat else (None, None)
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
            file_mtime=file_mtime, file_size=file_size,
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
    # SCHEMA_CANON R4: only name the tier-1 columns when we actually have values.
    # Writing NULL over a good stat because this call site had none would turn a
    # tier-1 hit into a permanent miss.
    if file_stat:
        row.file_mtime = file_mtime
        row.file_size = file_size
    row.status = STATUS_IN_PROGRESS
    row.note = plan.note
    if plan.resume_from == 0:
        row.processed_rows = 0
        row.chunk_index = 0
    db.commit()
    return plan


def record_failure(db, table_name: str, file_signature: str, filename: str, filepath: str,
                   reason: str, file_stat=None) -> bool:
    """파일 처리 **실패**를 원장에 종결 상태로 남긴다. 기록했으면 True.

    왜 필요한가: 종전에 「이 파일은 실패했다」는 사실은 **파일의 위치**(`err/`)로만
    표현됐다. 파일을 옮기지 않는 모드에서는 그 폴더가 사라지므로, 사실이 갈 곳이
    없으면 ⓐ 운영자가 '무엇이 왜 실패했나'를 못 묻고 ⓑ 스윕이 재기동마다 같은 파일을
    영원히 다시 시도한다. 두 결함 다 「옮기기를 멈춘 것」이 만들어 내는 것이다.

    사람이 읽는 사유·트레이스는 종전대로 `FileIngestionLog(status="FAILED")`에 남는다.
    여기 남는 것은 **종결 사실 + 짧은 사유**이고, 둘은 filepath로 이어진다.

    시그니처가 없으면(내용을 읽지 못한 파일) stat 기반 키로 기록한다 —
    `stat_identity_signature` 참조.
    """
    key = file_signature or stat_identity_signature(file_stat)
    if not table_name or not key:
        logger.warning(
            f"Cannot record ingestion failure for '{filepath}': no content signature and "
            f"no usable stat identity — the failure is recorded in FileIngestionLog only."
        )
        return False
    Model = _get_model()
    file_mtime, file_size = file_stat if file_stat else (None, None)
    brief = (reason or "").strip().splitlines()
    brief = brief[-1][:500] if brief else "unknown error"
    note = f"[failed] {brief}"
    row = find_checkpoint(db, table_name, key)
    if row is None:
        row = Model(
            table_name=table_name, file_signature=key, filename=filename,
            filepath=filepath, file_mtime=file_mtime, file_size=file_size,
            processed_rows=0, chunk_index=0, status=STATUS_FAILED, note=note,
        )
        db.add(row)
    else:
        row.filename = filename
        row.filepath = filepath
        if file_stat:
            row.file_mtime = file_mtime
            row.file_size = file_size
        row.status = STATUS_FAILED
        row.note = note
    db.commit()
    return True


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
