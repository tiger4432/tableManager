# -*- coding: utf-8 -*-
"""무엇을 빌린 세션에 «요구»하는지 말하는 자리 — 그리고 그 요구가 안 맞으면 «이름을 대고» 거절한다.

🔴 [S-271, 판정 414] 가드는 «문장 옆의 한 줄»이 아니라 «그 문장을 돌리는 것»이다.
   이 라운드의 주어는 운영자가 «복사해 고치는 틀»(`mappers/*.py.sample`)이다. 가드가 옆줄이면
   복사한 사람이 그 줄을 지워도 코드가 «돈다» — 그러면 본보기가 다시 두 경로가 된다. 일을
   «감싸면» 지우는 순간 눈에 띄게 깨진다.
   판별식: 「그 줄을 지우면 기능이 도나」. 돌면 그 모양은 부족하다.

⚠️ 그리고 거절은 «드라이버 문장»이 아니다. `25P01 no_active_sql_transaction` 이 운영자에게
   그대로 가면 그 사람은 어느 좌석이 무엇을 못 했는지 모른다 — 로그를 붙여 물어볼 수도 없다
   (운영은 보안상 로그를 못 내보낸다). 그래서 한 줄은 `operator_line` 모양이고 «좌석 이름»을 싣는다.

🪦 실측이 이 파일의 «범위»를 정했다 (S-271 ①, 2026-09-16). 세션을 «빌리고» 트랜잭션 상태를
   건드리는 좌석 43 중, SAVEPOINT 를 여는 «추적 코드» 좌석은 «하나»였고 그 하나는 이미 묻고
   있었다. 가드가 없는 것은 «저장소가 배포하는 본보기» 쪽이었다.

🔴 그리고 «쌍»으로 다시 세니 둘째 부류가 나왔다 (D-41 · 판정 415). 「좌석 32 가 롤백한다」는
   틀린 질문이었다 — 물음은 «(좌석, 호출자) 쌍»이고, 그렇게 세니 빌린 세션을 통째로 되돌리는
   쌍이 이름 붙은 «16» 이다. 그중 원형은 건식 스윕이고, 그 좌석 안에서 `db.rollback()` 은
   옳으며 밖에서는 호출자의 미커밋 작업을 지운다. 답은 롤백을 지우는 것이 아니라 «되돌릴
   범위»를 자기 것으로 만드는 것이다. 그 형제 `discarding`(버린다)은 스윕이 쪽마다 «자기
   세션»을 쓰면서 운영 호출자가 0 이 되어 은퇴했다(총괄 59c0bfb8c 7) — 증상은
   `test_a_dry_run_undoes_only_what_it_wrote` 가 지킨다. commit 쪽은 아직 «안 셌다».
"""
import logging
from contextlib import contextmanager

import operator_line

logger = logging.getLogger(__name__)

#: 🔴 이 낱말이 오면 「트랜잭션 블록이 없다」다. PostgreSQL 이 `SAVEPOINT` 에 내는 코드이고,
#: 한국어 서버의 메시지(「savepoint 명령은 트랜잭션 블럭에서만 사용할 수 있음」)로는 못 가른다 —
#: 운영 서버의 locale 이 무엇이든 «코드»는 같다.
NO_ACTIVE_TRANSACTION = "25P01"


class SessionNotUsable(RuntimeError):
    """이 좌석이 요구한 상태를 세션이 «못 준다». 드라이버 예외가 아니라 이 이름이 나간다."""


def _is_no_active_transaction(exc) -> bool:
    """이 예외가 「트랜잭션 블록이 없다」인가 — 메시지가 아니라 «코드»로.

    ⚠️ 두 겹을 본다. SQLAlchemy 가 감싼 것(`exc.orig`)과 날것 둘 다 이 자리에 올 수 있고,
    감싸인 쪽만 보면 날것이 지나간다.
    """
    for candidate in (getattr(exc, "orig", None), exc):
        if candidate is None:
            continue
        if getattr(candidate, "pgcode", None) == NO_ACTIVE_TRANSACTION:
            return True
    return False


def in_savepoint(db, where: str, work):
    """`work()` 를 SAVEPOINT 안에서 «돌린다» — 필요한 트랜잭션을 먼저 세우고.

    `where`  어느 좌석이 요구했나. 거절 줄의 대괄호에 들어가 운영자의 «검색어»가 된다
    `work`   인자 없는 콜러블. 이 함수가 «부른다» — 그래서 이 줄을 지우면 일이 «안 돈다»

    🔴 왜 SAVEPOINT 인가: PostgreSQL 에서 실패한 문장은 «감싼 트랜잭션을 죽인다». 그 뒤의
    `COMMIT` 은 «정상 반환»하면서 서버는 ROLLBACK 한다 — 그래서 try/except 는 격리가 아니다.
    SAVEPOINT 안에서 실패하면 세션이 산다(실측: `enrichment/config._isolated_execute` 의 표).

    ⚠️ 트랜잭션이 «없으면 연다». 읽기 전용 경로는 여기까지 한 문장도 안 보냈을 수 있고,
    그것은 이 좌석이 «가정할 수 없는» 것이다 — 호출자가 무엇을 했는지에 달렸다.

    🔴 그리고 그래도 25P01 이 나면 «그것이 이 함수의 답»이다. `in_transaction()` 은 «세션»의
    사실이고 autocommit 은 «연결»의 사실이라 서로 모른다 — 연결이 autocommit 이면 `db.begin()`
    이 BEGIN 을 «안 보내고» SAVEPOINT 는 앉을 곳이 없다. S-167 이 그 갈래를 112회 재 두었고,
    S-272 가 그것을 만드는 자리를 닫았다. 여기서는 «남은 경우»를 드라이버 문장이 아니라 한 줄로
    바꾼다: 어느 좌석이 · 무엇을 못 했나 · 다음에 무엇을 하나.
    """
    if not db.in_transaction():
        db.begin()
    try:
        nested = db.begin_nested()
    except Exception as exc:                                           # noqa: BLE001
        if not _is_no_active_transaction(exc):
            raise
        raise _refused(where, exc)

    # 🔴 THE 25P01 DOES NOT COME OUT OF `begin_nested()` — MEASURED, 2026-09-16.
    # SQLAlchemy defers the `SAVEPOINT` statement, so on a poisoned connection
    # `begin_nested()` RETURNS a SessionTransaction and the server refuses on the FIRST
    # statement inside it. A guard that only wrapped the opener would have been green here
    # and silent in production - which is the exact shape this round exists to end. The
    # first cut of this function did that, and this comment is what the probe bought.
    try:
        answer = work()
    except Exception as exc:                                           # noqa: BLE001
        if _is_no_active_transaction(exc):
            # ⚠️ NO `nested.rollback()` ON THIS ARM. There is no savepoint to roll back
            # to - the server never took it - and asking raises a second 25P01 that would
            # replace the seat's name with a driver sentence again.
            raise _refused(where, exc)
        nested.rollback()
        raise
    try:
        nested.commit()                                                # RELEASE: the work stands
    except Exception as exc:                                           # noqa: BLE001
        if _is_no_active_transaction(exc):
            raise _refused(where, exc)
        raise
    return answer


#: `session.info` key - the savepoint of the write step in progress while a seat holds this transaction's commit
#: (`hold_commit`, 총괄 09f58844f: a chain group's writes, withdrawals, shells and processed mark are ONE commit).
HELD_STEP = "held_step"
#: set while the seat itself releases a held step's savepoint (`end_step` · `release_hold`)
_HOLDER_COMMITS = "held_step_releasing"
#: the refusal of any other commit while one is held - the queue's last failure says it (총괄 09f58844f 안 1)
COMMIT_REFUSED = "a mapper may not commit inside the write stage"


class CommitRefused(RuntimeError):
    """A commit asked of a held transaction by someone other than its holder."""


def _held(db):
    """The held step's savepoint, or None - also when the transaction it was held in has ended (it is not on the
    session's chain of transactions any more)."""
    info = getattr(db, "info", None)
    step = info.get(HELD_STEP) if isinstance(info, dict) else None      # a stand-in session holds nothing
    if step is None:
        return None
    t = db.get_nested_transaction()
    while t is not None and t is not step:
        t = t.parent
    if t is None:
        db.info.pop(HELD_STEP, None)
    return t


def hold_commit(db) -> bool:
    """From here a write step does not commit: each step's `end_step` releases a savepoint, its `undo_step` rolls back
    to one, and any other commit is refused (`refuse_a_commit_while_held`) - until its holder lets go
    (`release_hold`), and the caller's one commit takes them all. -> whether this call opened it (asked again inside a
    held transaction, nothing)."""
    if _held(db) is not None:
        return False
    # ⚠️ a driver that opens its transaction only at its first write (pysqlite) takes this savepoint as the outermost,
    #    and its release COMMITS - so the transaction is begun first (measured: a rolled-back group left its rows)
    connection = db.connection()
    if getattr(connection.connection.dbapi_connection, "in_transaction", True) is False:
        connection.exec_driver_sql("BEGIN")
    db.info[HELD_STEP] = db.begin_nested()
    return True


def release_hold(db):
    """The holder's end (`hold_commit`): the last step's savepoint released, nothing committed - the transaction
    stays open for its caller's one commit, and a step called after this commits as it always did."""
    step = _held(db)
    if step is None:
        return
    db.info[_HOLDER_COMMITS] = True
    try:
        step.commit()
    finally:
        db.info.pop(_HOLDER_COMMITS, None)
        db.info.pop(HELD_STEP, None)


@contextmanager
def held(db):
    """`hold_commit` for a block - let go at its end when it opened it; a block that raised leaves the transaction to
    its caller's rollback."""
    opened = hold_commit(db)
    yield
    if opened:
        release_hold(db)


def end_step(db):
    """A write step's end - THE ONE SEAT of a write's commit. Held (`hold_commit`): its savepoint released and the
    next begun. Not held: a commit, as a step called alone always did."""
    step = _held(db)
    if step is None:
        db.commit()
        return
    db.info[_HOLDER_COMMITS] = True
    try:
        step.commit()
    finally:
        db.info.pop(_HOLDER_COMMITS, None)
    db.info[HELD_STEP] = db.begin_nested()


def undo_step(db):
    """A write step's failure undone - `end_step`'s pair. Held: back to the step's savepoint, what the steps before
    it wrote kept. Not held: a rollback, as a step called alone always did."""
    step = _held(db)
    if step is None:
        db.rollback()
        return
    step.rollback()
    db.info[HELD_STEP] = db.begin_nested()


def refuse_a_commit_while_held(session):
    """`before_commit`: a commit of a held transaction by anyone but the seat - a mapper's `db.commit()` inside a
    paging proposal's next page (more()) - is refused. SQLAlchemy 2's commit ends the OUTER transaction whatever
    savepoint is open (measured: both rows seen by another connection), so it would commit the group's writes
    without their processed mark. ⚠️ SQLAlchemy asks this of a savepoint's release too, the first of such a commit:
    one with the held step innermost that is not the holder's is refused; a savepoint opened inside the step
    (`in_savepoint`) releases as it always did."""
    if session.info.get(_HOLDER_COMMITS):
        return
    step = _held(session)
    if step is not None and session.get_nested_transaction() is step:
        raise CommitRefused("%s (return rows; the worker writes them)" % COMMIT_REFUSED)


def _refused(where: str, exc) -> SessionNotUsable:
    """한 줄을 찍고, 드라이버 예외를 «이 저장소의 이름»으로 바꿔 돌려준다."""
    logger.error("%s", operator_line.line(
        "Session", where,
        "이 세션의 연결이 트랜잭션을 열 수 없는 상태라 문장을 «격리해서» 돌릴 수 "
        "없었습니다 — 이 요청은 거절했고 세션은 그대로 둡니다",
        operator_line.restart_to_clear_the_pool()))
    return SessionNotUsable(
        "%s: the session's connection cannot open a transaction" % where)
