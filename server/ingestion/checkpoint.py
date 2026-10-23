"""[P2] 파일 인제션 오프셋 체크포인트 + «이미 읽었나» 체크리스트(`checked`).

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
   오판**해 데이터 유실(재개 오프셋 오적용)을 낳는다. 비용이
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

The checklist (소유자 10-21)
---------------------------
«Is this file already read?» has one answer: `checked`. A file log row of the same (path, table) carrying the
file's (mtime, size) - written where that read came to its answer - checks it; the watcher does not read it again.
Anything else (no row, a row without a stamp, the file saved again) is read. Every seat that asks - the two sweeps,
the tree walk, the event, the collector's wait - calls it. The content signature is no longer a judge: the same
bytes at another path are read (소유자 10-20 ㄱ); it stays the identity a read RESUMES by (above).

It replaced three judges that answered the same question differently (소유자 10-21 「문 나누지 말랬지」): the sweeps'
process memory of (mtime, size), this ledger's exact-path tier 1, and content dedup.

🔴 Failure direction: a file rewritten with its mtime and size kept is not read again - some copy tools keep mtime.
The way back for one file is the file screen's Retry (the retry door reads without asking, then stamps).
"""

import hashlib
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_

logger = logging.getLogger("Watcher.IngestionCheckpoint")

# 시그니처 해시 스트리밍 읽기 단위
_HASH_CHUNK_BYTES = 1024 * 1024

SIGNATURE_ALGO = "sha256"

# Ledger identity of an UNREADABLE file. `compute_file_signature` returns None
# when the content cannot be read at all, and the ledger's unique key is
# (table_name, file_signature) — so a failure on such a file had nowhere to be
# recorded and, with no move to `err/`, would be retried on every restart
# forever. This prefix is deliberately NOT `sha256:`, so a stat identity can
# never be confused with (or collide with) a content signature. It is a
# DECLARED key, not a marker pressed into service as one (SCHEMA_CANON R6).
STAT_SIGNATURE_PREFIX = "stat"

STATUS_IN_PROGRESS = "IN_PROGRESS"


#: [L-1] How long a claimed retry may go without checkpoint progress before the sweep
#: gives it back. 🔴 CITED, NOT COPIED. `heartbeat.DEFAULT_STALL_AFTER_SEC` is already the
#: derived answer to "a claimed unit of work has not progressed": its comment records the
#: measurement (chunk-to-chunk p50 9.20s, p95 9.70s, max 12.50s across a live 100,000-row
#: heavy ingestion) and the floor it clears (an opaque user parser that reports nothing for
#: minutes). Writing 300 here would be a second author for one number.
#:
#: ⚠️ IT IS COMPARED AGAINST CHUNK PROGRESS, NEVER AGAINST TOTAL RUNTIME. A seven-minute
#: ingestion is not stalled; one whose last chunk landed six minutes ago is. Judging on
#: runtime is how a reclaim turns LOSS into DUPLICATE work.
def reclaim_after_seconds(declared=None):
    """The sweep's grace, from the declaration when there is one."""
    from utils import heartbeat

    if isinstance(declared, bool) or not isinstance(declared, (int, float)):
        return heartbeat.DEFAULT_STALL_AFTER_SEC
    if declared <= 0:
        return heartbeat.DEFAULT_STALL_AFTER_SEC
    return float(declared)


def liveness(db, table_name, filename):
    """`(has_checkpoint, updated_at)` for this file's in-progress checkpoint.

    🔴 TWO ANSWERS, NOT ONE. "No checkpoint" and "a checkpoint that has not moved" look
    identical once collapsed into a boolean, and they must not be treated alike: three arms
    of `directory_watcher._plan_checkpoint` produce no checkpoint (no signature, planning
    threw, resume switched off) and none of them means the file is stuck.
    """
    from database.models import FileIngestionCheckpoint

    if not table_name or not filename:
        return False, None
    row = (db.query(FileIngestionCheckpoint)
           .filter(FileIngestionCheckpoint.table_name == table_name,
                   FileIngestionCheckpoint.filename == filename,
                   FileIngestionCheckpoint.status == STATUS_IN_PROGRESS)
           .order_by(FileIngestionCheckpoint.updated_at.desc(),
                     FileIngestionCheckpoint.id.desc())
           .first())
    if row is None:
        return False, None
    return True, row.updated_at
STATUS_DONE = "DONE"
# A terminal answer that is NOT success. Before the ledger carried this, the
# only record of "this file failed" was its LOCATION (`err/`); a mode that stops
# moving files therefore has to write the fact down instead of walking past it.
STATUS_FAILED = "FAILED"


_EPOCH_UTC = datetime(1970, 1, 1, tzinfo=timezone.utc)

def compute_file_signature(file_path: str) -> str | None:
    """파일 내용 시그니처 `sha256:<size>:<hexdigest>`. 읽기 실패 시 None.

    None이면 호출자는 체크포인트를 **비활성화**하고 기존(P1) 동작으로 처리해야 한다
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
            f"checkpoint disabled for this file (falls back to full reprocessing)."
        )
        return None


def mtime_ns_to_datetime(mtime_ns: int) -> datetime:
    """`st_mtime_ns` -> tz-aware UTC datetime **truncated to whole microseconds**.

    Integer arithmetic on purpose. `datetime.fromtimestamp(st.st_mtime)` goes
    through a float, and `checked` compares this value with `=`: a value that is
    not reproduced bit-for-bit from the same file simply MISSES, silently, and
    every file is read again. The ONE spelling a stamp is written and asked in. Truncation (not rounding) to
    microseconds is what PostgreSQL's `timestamptz` stores anyway, so the value
    written and the value re-derived on the next sweep are identical.
    """
    return _EPOCH_UTC + timedelta(microseconds=int(mtime_ns) // 1000)


def stamp_of(st) -> tuple:
    """An `os.stat` result as the stamp `checked` asks and a read writes: `(mtime_datetime, size_bytes)` - every seat
    that turns a stat into a stamp calls this, so a stored stamp and the same file stat'd again are one value."""
    return mtime_ns_to_datetime(st.st_mtime_ns), int(st.st_size)


def read_file_stat(file_path: str):
    """The file's stamp (`stamp_of`), or `None` when unavailable."""
    try:
        st = os.stat(file_path)
    except OSError:
        return None
    return stamp_of(st)


def stat_identity_signature(file_stat) -> str | None:
    """Ledger key for a file whose CONTENT could not be read — `stat:<size>:<us>`.

    Only ever used to record a FAILURE (see `record_failure`). `find_completed_ingestion` is called with a real
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
    started_at:  그 (표, 시그니처) 행이 처음 생긴 시각 — 같은 파일이면 Retry 에도 같음(총괄 4311a51ed nokey)
    transaction_id: the read's transaction - the checkpoint's own when it resumes, a new one otherwise (총괄 10-20)
    """

    __slots__ = ("table_name", "file_signature", "filename", "filepath",
                 "source_kind", "total_rows", "resume_from", "note", "active", "started_at", "transaction_id")

    def __init__(self, table_name=None, file_signature=None, filename=None, filepath=None,
                 source_kind=None, total_rows=None, resume_from=0, note=None, active=False,
                 started_at=None, transaction_id=None):
        self.table_name = table_name
        self.file_signature = file_signature
        self.filename = filename
        self.filepath = filepath
        self.source_kind = source_kind
        self.total_rows = total_rows
        self.resume_from = resume_from
        self.note = note
        self.active = active
        self.started_at = started_at
        self.transaction_id = transaction_id

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
    """같은 테이블에 같은 내용이 이미 완료 적재됐는지 — Retry 가 0 부터 다시 넣나(`_retry_should_restart`)."""
    row = find_checkpoint(db, table_name, file_signature)
    if row is not None and row.status == STATUS_DONE:
        return row
    return None


def _same_path(recorded: str, filepath: str) -> bool:
    return os.path.normcase(os.path.abspath(recorded)) == os.path.normcase(filepath)


#: Files one `checked` query asks about - the OR of (path, mtime, size) clauses. 500 is the top of the flat band
#: measured for the same OR shape on the ledger (2026-08-13: ms/file flat from 50 to 500, 3x worse at 2,000).
CHECKED_BATCH_SIZE = 500


#: Why a file is read (총괄 64b264610 «보낼 때마다 왜를 하나»): the checklist's words (`checked(words=)`), then the
#: retry door's (`reread.why_handed`). The watcher's line and the file page's counts say these, and only these.
WHY_NEW, WHY_CHANGED, WHY_UNSTAMPED = "new", "changed", "unstamped"
WHY_RETRY, WHY_READ_AGAIN, WHY_READ_NOW = "retry", "read again", "read now"
WHY_UNREAD = "checklist not read"


def checked(db, table_name: str, entries, words=None) -> dict:
    """The checklist (소유자 10-21): `{filepath: status}` for the `(filepath, file_stat)` entries a file log row of
    `table_name` checks - the same path as `path_key` spells it (both sides folded in SQL, one spelling), the same
    (mtime, size). Its status is the newest such row's (SUCCESS, FAILED, or PENDING once handed to the retry door).
    A path absent is not checked: it is read - and `words`, when given, gets why for each such path, off its file's
    newest row (`newest_of_its_file`): WHY_NEW none · WHY_UNSTAMPED no stamp · WHY_CHANGED another stamp."""
    from sqlalchemy import literal, select

    from database.models import FileIngestionLog as Log, path_key

    if not table_name:
        return {}
    items = list({filepath: (filepath, file_stat) for filepath, file_stat in entries if filepath and file_stat}.values())
    found = {}
    for start in range(0, len(items), CHECKED_BATCH_SIZE):
        chunk = items[start:start + CHECKED_BATCH_SIZE]
        keys = db.execute(select(*[path_key(literal(filepath)) for filepath, _stat in chunk])).one()
        asked = {}
        for (filepath, file_stat), key in zip(chunk, keys):
            asked.setdefault((key, file_stat[0], file_stat[1]), []).append(filepath)
        rows = db.query(path_key(Log.filepath), Log.file_mtime, Log.file_size, Log.status).filter(
            Log.table_name == table_name,
            or_(*[and_(path_key(Log.filepath) == key, Log.file_mtime == file_stat[0], Log.file_size == file_stat[1])
                  for (_filepath, file_stat), key in zip(chunk, keys)]),
        ).order_by(Log.id.desc()).all()
        by_key = {}
        for key, _mtime, size, status in rows:
            by_key.setdefault((key, size), status)
        for (key, _mtime, size), paths in asked.items():
            if (key, size) in by_key:
                for filepath in paths:
                    found[filepath] = by_key[(key, size)]
    if words is not None:
        _why_not_checked(db, table_name, [filepath for filepath, _stat in items if filepath not in found], words)
    return found


def _why_not_checked(db, table_name, filepaths, words):
    """`checked`'s words for the paths it did not check - only those: one query a batch over their newest rows."""
    from sqlalchemy import literal, select

    from database.models import FileIngestionLog as Log, path_key

    for start in range(0, len(filepaths), CHECKED_BATCH_SIZE):
        chunk = filepaths[start:start + CHECKED_BATCH_SIZE]
        keys = db.execute(select(*[path_key(literal(filepath)) for filepath in chunk])).one()
        stamped = dict(db.query(path_key(Log.filepath), Log.file_mtime.isnot(None)).filter(
            Log.table_name == table_name, path_key(Log.filepath).in_(list(keys)), newest_of_its_file(Log)))
        for filepath, key in zip(chunk, keys):
            words[filepath] = (WHY_NEW if key not in stamped else WHY_CHANGED if stamped[key] else WHY_UNSTAMPED)


def newest_of_its_file(Log):
    """SQL: the row is its file's newest - no row of the same table and path (`path_key`) after it. A re-read writes a
    new row and leaves the older ones as they were, so «the checklist» is the newest row of each (table, path) (소유자
    10-21; 총괄 10-23: the progress count and the first-start stamping ask this one condition)."""
    from sqlalchemy import exists
    from sqlalchemy.orm import aliased

    from database.models import path_key

    newer = aliased(Log)
    return ~exists().where(newer.table_name == Log.table_name, path_key(newer.filepath) == path_key(Log.filepath),
                           newer.id > Log.id)


def read_progress(db) -> list:
    """The checklist's progress (소유자 10-23 「몇 개 중 몇 개 읽고 있는지」): per (table, source) its files - the newest row
    of each (`newest_of_its_file`) - `total`, `read` (stamped: checked, not read again) and `left` (no stamp: waiting,
    being read, failed and let go, or unchecked) by state. A file no row names yet (not reached by a sweep) is in no
    count. One GROUP BY. -> [{"table_name", "source", "total", "read", "left", "left_by_status"}]."""
    from sqlalchemy import func

    from database.models import FileIngestionLog as Log

    stamped = Log.file_mtime.isnot(None)
    out = {}
    for table, source, status, read, n in (db.query(Log.table_name, Log.source, Log.status, stamped, func.count(Log.id))
                                           .filter(newest_of_its_file(Log))
                                           .group_by(Log.table_name, Log.source, Log.status, stamped)):
        entry = out.setdefault((table, source), {"table_name": table, "source": source, "total": 0, "read": 0,
                                                  "left": 0, "left_by_status": {}})
        entry["total"] += n
        if read:
            entry["read"] += n
        else:
            entry["left"] += n
            entry["left_by_status"][status] = entry["left_by_status"].get(status, 0) + n
    return sorted(out.values(), key=lambda e: (str(e["table_name"]), str(e["source"])))


def stamp_read_files(db, table_name: str, entries) -> dict:
    """The checklist's first start (총괄 10-21, 소유자 「좀 가볍게 돌게 만들어」): a log row from before it carries no
    stamp, so every file a sweep looks at would be read again. For the `(filepath, file_stat)` entries a sweep has just
    stat'd - the disk is not looked at again - the newest row of each (table, path) with no stamp: SUCCESS and written
    at or after the file's mtime (unchanged since that read) gets the file's stamp; FAILED is not stamped (read once
    more). -> {"stamped", "failed", "changed"}: the log row ids - a file asked again (its read's own ask) is one."""
    from sqlalchemy import literal, select

    from database.models import FileIngestionLog as Log, path_key

    said = {"stamped": [], "failed": [], "changed": []}
    items = list({filepath: (filepath, file_stat) for filepath, file_stat in entries if filepath and file_stat}.values())
    for start in range(0, len(items), CHECKED_BATCH_SIZE):
        chunk = items[start:start + CHECKED_BATCH_SIZE]
        keys = db.execute(select(*[path_key(literal(filepath)) for filepath, _stat in chunk])).one()
        stat_of = dict(zip(keys, (file_stat for _filepath, file_stat in chunk)))
        newest = {}
        for row in db.query(Log.id, path_key(Log.filepath), Log.status, Log.updated_at, Log.created_at,
                            Log.file_mtime).filter(Log.table_name == table_name,
                                                   path_key(Log.filepath).in_(list(stat_of)), newest_of_its_file(Log)):
            newest[row[1]] = row
        stamps = []
        for log_id, key, status, updated, created, stamped in newest.values():
            if stamped is not None:
                continue
            if status == STATUS_FAILED:
                said["failed"].append(log_id)
                continue
            if status != "SUCCESS":
                continue
            when = updated or created
            if when is not None and when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            mtime, size = stat_of[key]
            if when is not None and when >= mtime:
                stamps.append({"id": log_id, "file_mtime": mtime, "file_size": size})
            else:
                said["changed"].append(log_id)
        if stamps:
            db.bulk_update_mappings(Log, stamps)
            db.commit()
        said["stamped"] += [stamp["id"] for stamp in stamps]
    return said


def plan_ingestion(db, table_name: str, file_signature: str, filename: str, filepath: str,
                   total_rows: int, source_kind: str, force_restart: bool = False) -> CheckpointPlan:
    """체크포인트 행을 준비하고 재개 오프셋을 결정한다 (커밋은 호출자 책임 아님 — 여기서 커밋).

    force_restart=True면 기존 진행분을 무시하고 0부터 재적재한다(Retry 가 완료된 내용을 다시 넣는 경로).
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
            # Stated rather than left to the server default, so the plan holds it with no read back.
            started_at=datetime.now(timezone.utc), transaction_id=str(uuid.uuid4()),
        )
        db.add(row)
        db.commit()
        plan.started_at, plan.transaction_id = row.started_at, row.transaction_id
        return plan

    plan.started_at = row.started_at
    # 기존 행이 있다 — 재개 가부를 명시적으로 판정한다.
    reason = None
    if force_restart:
        reason = "Retry 로 다시 넣음"
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

    # The same content DONE at another path is another file (총괄 10-20): read from the start, nothing aborted.
    another_file = (row.status == STATUS_DONE and not force_restart
                    and not (row.filepath and _same_path(row.filepath, filepath)))
    if another_file:
        plan.resume_from = 0
    elif reason is None:
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
    # 총괄 10-20: a resumed read writes under the transaction its first run wrote under - a new one only for a read
    # from the start, or a checkpoint written before the column
    if plan.resume_from == 0 or not row.transaction_id:
        row.transaction_id = str(uuid.uuid4())
    plan.transaction_id = row.transaction_id
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
    brief = (reason or "").strip().splitlines()
    brief = brief[-1][:500] if brief else "unknown error"
    note = f"[failed] {brief}"
    row = find_checkpoint(db, table_name, key)
    if row is None:
        row = Model(
            table_name=table_name, file_signature=key, filename=filename,
            filepath=filepath, processed_rows=0, chunk_index=0, status=STATUS_FAILED, note=note,
        )
        db.add(row)
    else:
        row.filename = filename
        row.filepath = filepath
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
    """파일 처리 성공 확정 — 같은 시그니처의 다음 Retry 는 0 부터(`find_completed_ingestion`)."""
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
