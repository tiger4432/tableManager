"""Let one already-ingested file be read again — without touching the file.

WHY THIS EXISTS
---------------
A managed file is replayed by renaming it to carry ``__force__``.  An EXTERNAL source is
read-only by design: the watcher never moves or renames what it finds there, and neither
should you.  That left only two levers, both wrong for one file: turn dedup off globally
(every file under that tree re-ingests on every sweep, forever, because nothing moves) or
edit the database by hand.

This is the missing middle.  It clears the ingestion ledger's memory of ONE file, so the
next sweep treats it as new.  The file is not read, moved, renamed or hashed into
anything; only the checkpoint row is removed.

    python scripts/replay_ingestion.py --path "D:/feeds/WF-001/JOB1_20260818_140000/voids.json"
    python scripts/replay_ingestion.py --path "..." --apply

Dry run by default: it prints the row it would forget and changes nothing.  Re-ingestion
UPDATES rows that carry the same business key rather than duplicating them, so a replay
of unchanged content lands the same values again.
"""
from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.dirname(HERE)
for path in (SERVER, os.path.join(SERVER, "parsers")):
    if path not in sys.path:
        sys.path.insert(0, path)


def _rows_for(db, model, filepath: str, signature: str | None, table: str | None):
    """Every checkpoint row that would make the watcher skip this file.

    Matched by absolute path first, because that is what the operator has in hand.  The
    content signature is also tried: the same bytes may have been ingested from an older
    location, and it is that row -- not the path -- the dedup actually consults.
    """
    found = {}
    query = db.query(model).filter(model.filepath == filepath)
    if table:
        query = query.filter(model.table_name == table)
    for row in query.all():
        found[row.id] = row
    if signature:
        query = db.query(model).filter(model.file_signature == signature)
        if table:
            query = query.filter(model.table_name == table)
        for row in query.all():
            found[row.id] = row
    return list(found.values())


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--path", required=True, help="the file to let through again")
    parser.add_argument("--table", help="narrow to one table (a file may feed two)")
    parser.add_argument("--apply", action="store_true",
                        help="actually forget it; without this nothing changes")
    args = parser.parse_args(argv)

    import ingestion_checkpoint
    from database.database import SessionLocal
    from database.models import FileIngestionCheckpoint as Model

    filepath = os.path.abspath(args.path)
    print(f"file      : {filepath}")
    exists = os.path.exists(filepath)
    print(f"존재 여부 : {'있음' if exists else '없음 (원장 기록만 지웁니다)'}")

    signature = ingestion_checkpoint.compute_file_signature(filepath) if exists else None
    print(f"signature : {signature or '(계산 못 함)'}")

    db = SessionLocal()
    try:
        rows = _rows_for(db, Model, filepath, signature, args.table)
        if not rows:
            print()
            print("이 파일에 대한 인제션 기록이 없습니다 — 이미 다시 읽힐 상태입니다.")
            print("그래도 안 들어온다면 원인은 dedup이 아닙니다("
                  "폴더 모양·options.filename·enabled 를 보십시오).")
            return 0

        print()
        print(f"=== 지울 기록 {len(rows)}건 ===")
        for row in rows:
            print(f"  표 {row.table_name:20s} status={row.status:10s} "
                  f"행 {row.processed_rows or 0:,}  {row.filename}")
            print(f"      signature={str(row.file_signature)[:40]}…  updated={row.updated_at}")

        if not args.apply:
            print()
            print("(미적용 — --apply 를 붙이면 실제로 지웁니다)")
            return 0

        for row in rows:
            db.delete(row)
        db.commit()
        print()
        print(f"지웠습니다 — {len(rows)}건. 다음 스윕(외부 소스는 최대 300초)에서 "
              f"이 파일을 새 파일로 봅니다.")
        print("업서트라 같은 business key 행은 늘지 않고 갱신됩니다.")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
