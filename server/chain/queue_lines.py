"""The chain queue's LINES - the waiting rows grouped by their line key (`event_constants.queue_line_key`)
and ranked by each line's first id, cut at a cap in SQL. ONE grouping: `GET /admin/chain/queue` lists
it and the slot dispatcher gives lines from it (총괄 19f6a9277 - «배정자는 행이 아니라 줄을 본다»: a
window of the first 200 ROWS held only a big replay's rows, and the line behind it was never seen).
"""
from types import SimpleNamespace

import event_constants


def waiting_lines(db, cap):
    """-> the first `cap` waiting lines, oldest first - `SimpleNamespace(key, run, events, rows, first_id,
    created_at, max_retry, lines_total, pairs)`, `pairs` its (table, event type) groups.

    🔴 THE PAYLOAD OF THE WAITING ROWS IS READ ONCE (소유자 10-08 「대기열 화면 로딩 5초」 · 총괄 6d7046a42):
    the lines and each line's tables and kinds come from one grouping by (line, kind, table), ranked
    by the line's first id and cut at the cap in SQL, so only the listed lines come back. It scans
    the waiting rows only (`idx_outbox_unprocessed`).
    🔴 [총괄 b3a4334db] 줄의 신원은 소급 실행(`run_id`)이 있으면 그것, 없으면 `transaction_id`,
    둘 다 없으면 그 행 하나 — `event_constants.queue_line_key`, × 와 워커가 같이 부르는 하나.
    상한은 «줄»에 건다(⚰️ «앞 200 이벤트»를 자른 뒤 접으면 큰 잡 뒤의 잡이 안 보였다).
    """
    from sqlalchemy import func as _f
    from sqlalchemy import select as _select
    from database import models

    outbox = models.DatabaseOutbox
    waiting_only = (outbox.processed_chain == False)  # noqa: E712 - 부분 인덱스의 술어 철자
    run_of = outbox.payload["run_id"].as_string()
    line_key = event_constants.queue_line_key(outbox)
    pairs = (_select(line_key.label("key"), _f.max(run_of).label("run"), outbox.table_name,
                     outbox.event_type, _f.count().label("events"),
                     # 묶인 이벤트는 «몇 행»을 싣는지 들고 있다(`row_count`); 행 하나짜리는 1
                     _f.sum(_f.coalesce(outbox.payload["row_count"].as_integer(), 1)).label("rows"),
                     _f.min(outbox.id).label("first_id"), _f.min(outbox.created_at).label("created_at"),
                     _f.max(outbox.retry_count).label("max_retry"))
             .where(waiting_only).group_by(line_key, outbox.table_name, outbox.event_type).subquery())
    by_line = _select(pairs, _f.min(pairs.c.first_id).over(partition_by=pairs.c.key)
                      .label("line_first")).subquery()
    numbered = _select(by_line, _f.dense_rank().over(order_by=(by_line.c.line_first, by_line.c.key))
                       .label("line_no")).subquery()
    counted = _select(numbered, _f.max(numbered.c.line_no).over().label("lines_total")).subquery()
    folded = {}
    for pair in db.execute(_select(counted).where(counted.c.line_no <= cap)
                           .order_by(counted.c.line_no, counted.c.table_name, counted.c.event_type)):
        line = folded.setdefault(pair.key, {
            "key": pair.key, "run": None, "events": 0, "rows": 0, "first_id": pair.line_first,
            "created_at": None, "max_retry": 0, "lines_total": pair.lines_total, "pairs": []})
        line["run"] = max(filter(None, (line["run"], pair.run)), default=None)
        line["events"] += pair.events
        line["rows"] += pair.rows or 0
        line["created_at"] = min(filter(None, (line["created_at"], pair.created_at)), default=None)
        line["max_retry"] = max(line["max_retry"], pair.max_retry or 0)
        line["pairs"].append((pair.table_name, pair.event_type))
    return [SimpleNamespace(**line) for line in folded.values()]
