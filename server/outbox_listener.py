# -*- coding: utf-8 -*-
"""아웃박스 탄생 통지를 «듣는» 자리. 프로세스에 매이지 않는다.

체인 워커 안에 살던 클래스를 여기로 «옮겼다»(복사 아님). 옮긴 이유는 듣는 쪽이 둘이
됐기 때문이다 — 워커는 행을 «처리»하려고 듣고, API 프로세스는 그 사실을 브라우저에
«흘리려고» 듣는다.

🔴 왜 API 가 직접 듣나 — `outbox_expand` 는 «체인 워커 프로세스»에서 행을 낳는다(실패한
   청크가 쪼개질 때). WS 허브는 API 프로세스에만 있으므로, API 가 ORM 훅으로만 알면
   그 행들은 화면에 «영영» 안 뜬다. NOTIFY 는 DB 수준이라 어느 프로세스의 출생이든
   듣는 쪽 모두에게 간다 — 그래서 좌석이 아니라 «청중»을 늘리는 것이 답이었다.

⚠️ 클래스를 둘로 «복사하지 않는다». 자기 factory·channel·lap_name 을 받는 자립형이라
   인스턴스가 둘이면 된다. 복사하는 순간 이 라운드가 세고 있는 그 병이 된다.
"""
import asyncio
import logging
import select
import time

from utils import heartbeat
from event_constants import OUTBOX_NOTIFY_CHANNEL

logger = logging.getLogger(__name__)


class OutboxListener:
    """[Latency Fix #4] 상시 유지되는 LISTEN 전용 raw 커넥션.

    기존 `blocking_wait`은 빈 폴링 이후 대기할 때마다 **새 커넥션으로 LISTEN을 재등록**했다.
    빈 폴링 시점과 LISTEN 등록 사이에 발행된 NOTIFY는 유실되어 최대 timeout(2초)만큼
    tail latency가 발생했다(LISTEN-after-check 레이스).

    개선: 워커 시작 시 LISTEN을 **1회만** 등록하고 커넥션을 재사용한다. LISTEN이 항상
    폴링보다 먼저 등록되어 있으므로, 폴링 이후 발행된 NOTIFY는 커넥션 소켓에 버퍼링되어
    다음 `wait()`에서 즉시 감지된다(재폴링 유도). 등록 전 발행분을 놓치지 않도록 대기 진입
    직후 버퍼된 통지를 먼저 소비(drain)한다.

    SYSTEM_RELOAD 통지도 같은 채널(`outbox_event`)을 쓰므로 그대로 공존한다(깨우기만 하고
    실제 판정은 루프 상단의 SYSTEM_RELOAD 조회가 담당).
    """

    def __init__(self, db_session_factory, channel=OUTBOX_NOTIFY_CHANNEL,
                 lap_name="chain"):
        self._factory = db_session_factory
        #: 하트비트에 «누가» 듣고 있는지. 프로세스마다 다르므로 값이다 —
        #: API 인스턴스가 자기를 「chain」 이라 적으면 그 줄이 거짓이 된다.
        #:
        #: 🔴 `None` 이면 lap 을 «안 찍는다», 그리고 그것이 API 인스턴스의 값이다.
        #:    [Q-207 QA] `record_lap` 은 프로세스 안 dict 에 적고, 그 dict 를 파일로
        #:    내보내는 것은 `beat(<name>)` 뿐이다. 실측(2026-09-22): `beat(` 를 부르는
        #:    이름은 chain · ledger · scheduler · watcher «넷»이고 `main.py` 의 호출은
        #:    «0» 이다. 그래서 "api" 로 적으면 `api.json` 이 안 써지고 `read_all` 이 못
        #:    걷는다 — 터지지도 않고 관찰만 안 되는 값이 된다.
        #: ⛔ 그래서 「안 보이는 값을 적는」 대신 «안 적는다». 대가는 적어 둔다:
        #:    **API 리스너의 재접속 횟수는 오늘 셀 수 없다** (S-176 이 워커용으로 세운 값).
        #:    보이게 하려면 /health 에 레인이 하나 늘고, 그건 «낳은 항목»이라 총괄 판정이다.
        self._lap_name = lap_name
        self._channel = channel
        self._connection = None  # 상시 유지되는 raw DBAPI 커넥션(psycopg2)
        # S-176: how many times this listener has had to rebuild its connection. A count
        # rather than a flag, because 「it reconnected once at boot」 and 「it is
        # reconnecting every minute」 are the two states an operator needs told apart, and
        # a boolean renders them alike.
        self._reconnects = 0
        #: 🔴 CLOSED ON PURPOSE. The reader sits in `select` on ANOTHER THREAD, so
        #:   closing the connection under it makes that select raise. Without this
        #:   the reader cannot tell a shutdown from a dead connection: it logged the
        #:   shutdown as an ERROR and then REBUILT the connection the shutdown had
        #:   just closed (소유자 2026-09-23 「서버 종료시 아웃박스 리스너 얼레디
        #:   클로즈 에러라는데」). One flag, read in the two places that care.
        self._closed = False

    def _ensure_connection(self):
        """LISTEN 커넥션이 없으면(최초/재생성) 생성하고 LISTEN을 1회 등록한다."""
        if self._connection is not None:
            return
        db = self._factory()
        try:
            engine = db.bind or db.get_bind()
            url = engine.url
        finally:
            db.close()

        # 🔴 A DEDICATED CONNECTION, NEVER THE POOL'S (S-167). LISTEN needs autocommit,
        # and `engine.raw_connection()` hands out a POOLED one: `set_isolation_level(0)`
        # mutates it, and closing the proxy RETURNS IT TO THE POOL still in autocommit.
        # Measured on this box - the very next checkout was the SAME connection with
        # `autocommit=True`. Whatever session took it next never began a transaction, so
        # every `begin_nested()` on it raised 25P01 `no_active_sql_transaction`: the
        # chain's shared write scope and the reference view were both answering with that.
        #
        # ⚠️ THE `in_transaction()` GUARDS CANNOT CLOSE IT. On an autocommit connection
        # `session.begin()` issues no BEGIN, so the SAVEPOINT still has nothing to sit in -
        # measured 112 times on the build that already carried those guards. They stay as
        # correct defences one layer up; this is the seat that has to stop leaking.
        #
        # ⛔ SO IT IS NEVER RETURNED. `psycopg2.connect` gives a connection the pool has
        # never seen, and `_reset_connection`'s `close()` is then a real close, not a
        # checkin that would put this autocommit connection back into circulation.
        import psycopg2
        connection = psycopg2.connect(
            url.set(drivername="postgresql").render_as_string(hide_password=False))
        connection.set_isolation_level(0)
        cursor = connection.cursor()
        cursor.execute(f"LISTEN {self._channel};")
        cursor.close()
        self._connection = connection
        if self._lap_name:
            heartbeat.record_lap(self._lap_name, "listen", state="connected",
                                 reconnects=self._reconnects)

    def _reset_connection(self):
        """끊긴/오류 커넥션을 안전하게 폐기한다(리소스 누수 금지)."""
        conn = self._connection
        self._connection = None
        if conn is not None:
            self._reconnects += 1
            if self._lap_name:
                heartbeat.record_lap(self._lap_name, "listen", state="reconnecting",
                                     reconnects=self._reconnects)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    def _wait_blocking(self, timeout):
        # ⛔ NOT A RECONNECT POINT. Once closed, this listener does not build another
        #    connection - the caller's loop is on its way out and a fresh LISTEN
        #    connection at shutdown is exactly the leak `close()` exists to prevent.
        if self._closed:
            return False
        try:
            self._ensure_connection()
            connection = self._connection

            # 등록 전/폴링 이후 발행되어 소켓에 이미 버퍼된 통지를 먼저 소비 → 즉시 재폴링.
            connection.poll()
            if connection.notifies:
                while connection.notifies:
                    connection.notifies.pop()
                return True

            # select로 소켓에 데이터가 들어올 때까지 대기 (CPU 부하 0%)
            r, w, x = select.select([connection], [], [], timeout)
            if r:
                connection.poll()
                while connection.notifies:
                    connection.notifies.pop()
                return True
            return False
        except Exception as e:
            # 🔴 TWO REASONS, TWO WORDS. `close()` while a wait is in flight is a SHUTDOWN
            #    and the exception is the shutdown arriving, not a fault; folding it into
            #    the line below made a normal stop read as an error and, worse, sent this
            #    listener to build a connection nobody would close.
            if self._closed:
                logger.info(
                    "[Outbox Queue] listener connection closed while a wait was in "
                    "flight - that is the shutdown, not a fault (%s)", e)
                return False
            # 커넥션 끊김/예외 시 안전 재생성(다음 wait에서 새 LISTEN 커넥션 확보).
            logger.error(f"PostgreSQL LISTEN/NOTIFY socket wait failed, resetting listener connection: {e}")
            self._reset_connection()
            time.sleep(1.0)
            return False

    async def wait(self, timeout=30.0):
        """blocking select를 스레드로 오프로딩하여 asyncio 루프를 막지 않는다."""
        return await asyncio.to_thread(self._wait_blocking, timeout)

    def close(self):
        """Close for good. 🔴 SAYS SO FIRST, because the reader is on another thread and
        finds out by having its `select` raise - see `_closed`."""
        self._closed = True
        self._reset_connection()
