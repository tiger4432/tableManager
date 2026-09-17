# -*- coding: utf-8 -*-
"""What a chain mapper is doing RIGHT NOW, in this process, for the queue view.

Same shape as `ingestion_activity`: an in-memory registry that the thing doing the work
updates, and a route that READS it. No broadcast, no database column, no route of its
own - `GET /admin/chain/queue` already answers "what is the chain doing" and this is the
half of that answer the outbox cannot give. The outbox says what is WAITING; only the
process running the mapper knows what is IN it.

🔴 IT IS UPDATED BY A DIRECT CALL, NOT OVER HTTP, and that is a deliberate difference
from `ingestion_activity`. The watcher is always a separate process, so its state has to
travel; the chain loop is started inside the web server's own startup
(`main.py`, `start_chain_ingestion_worker`), so in that deployment the mapper and the
route share a process and an HTTP hop between them would be a hop to itself.

🔴 AND WHEN THEY DO NOT SHARE A PROCESS, THIS SAYS SO. Run `run_chain_worker.py`
separately and the loop updates ITS registry while the API serves an empty one - and an
empty list would read as "nothing is running" when the truth is "I cannot see it". That
is the same lying zero this repository spent the day removing elsewhere, so `attached`
is published beside the list: it is True only in the process whose own chain loop
started, and a reader that gets `attached: false` knows the list is blind rather than
empty.
"""

import contextlib
import threading
import time


class ChainActivityRegistry:
    """Mapper executions in flight in THIS process. Thread-safe, bounded by concurrency."""

    def __init__(self):
        self._lock = threading.Lock()
        self._running = {}
        #: 규칙 이름 -> 그 규칙의 «마지막 결과». 이력이 아니다 — 수명은 프로세스이고
        #: `_running` 과 같다. 새 표도 새 기록면도 아니고 이 객체의 칸 하나다.
        self._outcomes = {}
        self._attached = False
        self._attached_at = None
        self._reloaded_at = None
        self._purged_at = None
        self._purged_rows = None
        self._purge_capped = None
        self._seq = 0

    def attach(self):
        """Called by the chain loop as it starts. Marks this process as the one that runs
        mappers, which is what makes an empty list mean "idle" instead of "blind"."""
        with self._lock:
            self._attached = True
            self._attached_at = time.time()

    def note_reload(self):
        """A SYSTEM_RELOAD re-imported the mapper modules in THIS process.

        🔴 IT WAS ALREADY RECORDED AND COULD NOT LEAVE. `QueueHeadWatch.note_reload` has
        kept this instant since the stall watcher landed, and it leaves only as TEXT
        inside a sentence the loop logs -- and only once the queue head has already been
        stuck for a minute. So the one question this answers ("is the state in this
        process rather than in the data?") could be asked only by someone already reading
        the log of a system already stalled.

        ⚠️ NEVER-RELOADED STAYS `None`. `0` would read as "just now", which is the
        opposite fact, and the loop starting is not a reload.
        """
        with self._lock:
            self._reloaded_at = time.time()

    def note_outbox_purge(self, deleted, capped):
        """The last outbox retention purge in this process: how many rows went, and
        whether it stopped at its PER-CYCLE cap with more still expired.

        🔴 THE COUNT ALONE CANNOT SAY IT. The purge deletes in chunks up to
        `OUTBOX_PURGE_MAX_CHUNKS` and carries the remainder to the next cycle, so
        "the cap bound" and "that is all there was" arrive as the SAME number. A
        deployment whose arrival rate outruns the purge rate therefore grows a
        backlog whose only symptom is disk, and nothing in the system says so.

        ⚠️ `capped=None` IS A THIRD STATE, not a shy False. The cycle raised partway,
        so the count is partial and the question has no answer yet -- exactly the
        distinction `mapper_reload_age_seconds` keeps with its own `None`.
        """
        with self._lock:
            self._purged_at = time.time()
            self._purged_rows = int(deleted or 0)
            self._purge_capped = None if capped is None else bool(capped)

    @property
    def attached(self) -> bool:
        with self._lock:
            return self._attached

    def start(self, rule, mapper, target_table, rows_in):
        """Record an execution and return the token that ends it."""
        with self._lock:
            self._seq += 1
            token = self._seq
            self._running[token] = {
                "rule": rule, "mapper": mapper, "target_table": target_table,
                "rows_in": rows_in, "started": time.time(),
            }
        return token

    def record_outcome(self, rule, outcome, reason=None):
        """이 규칙의 «마지막 결과». `finish` 와 «다른 이름»인 이유가 있다.

        🔴 `finish(token)` 이 하는 일은 「도는 목록에서 뺀다」 하나이고 그 토큰은 `start` 만
           만든다 — 그래서 «시작한 적 없는» 규칙(꺼짐·안 걸림)은 그 문을 지날 수 없다.
           두 사실(도는 중 / 마지막 결과)에 한 이름을 얹으면 호출자가 여섯이 되고,
           그때 「이 함수를 부르는 자리가 하나인가」를 아무도 못 묻는다.
        ⚠️ `finish` 와 마찬가지로 «절대 던지지 않는다». 자기를 설명하는 대상을 계측이
           쓰러뜨릴 수 있으면 안 된다.
        """
        try:
            with self._lock:
                self._outcomes[str(rule)] = {
                    "outcome": outcome,
                    "reason": (str(reason) if reason else None),
                    "at": time.time(),
                }
        except Exception:                                        # noqa: BLE001
            pass

    def seed_rules(self, names):
        """선언된 규칙을 «값»으로 세워 둔다 — 「아직 평가 안 됨」이 부재가 아니라 답이 되게.

        🔴 부재는 「옛 서버라 이 칸이 없다」 «하나»만 뜻해야 한다. 씨를 안 뿌리면 「평가돼서
           할 일이 없던 규칙」과 「이 프로세스가 아직 못 본 규칙」이 «같은 없음»이 된다.
        ⚠️ 이미 있는 이름은 «안 건드린다** — 재적재가 지난 결과를 지우면 안 된다.
        """
        try:
            with self._lock:
                for name in names or ():
                    self._outcomes.setdefault(str(name), {
                        "outcome": "never_evaluated", "reason": None, "at": time.time()})
        except Exception:                                        # noqa: BLE001
            pass

    def outcomes(self) -> dict:
        """규칙 이름 -> `{outcome, reason, age_seconds}`. 빈 dict = 이 프로세스가 아직
        «아무 규칙도» 평가하지 않았다 — 그것도 답이다."""
        now = time.time()
        with self._lock:
            return {name: {"outcome": e["outcome"], "reason": e["reason"],
                           "age_seconds": round(now - e["at"], 3)}
                    for name, e in self._outcomes.items()}

    def finish(self, token):
        """Idempotent, and never raises: a registry that can fail must not be able to take
        down the mapper it is describing."""
        with self._lock:
            self._running.pop(token, None)

    def snapshot(self) -> list:
        now = time.time()
        with self._lock:
            entries = sorted(self._running.values(), key=lambda e: e["started"])
            return [{"rule": e["rule"], "mapper": e["mapper"],
                     "target_table": e["target_table"], "rows_in": e["rows_in"],
                     "running_seconds": round(now - e["started"], 3)}
                    for e in entries]

    def ages(self) -> dict:
        """How long this process's loop has been up, and how long since it re-imported.

        Ages rather than instants: the reader is comparing them with each other and with
        `oldest_waiting_seconds`, and a clock string would have to be reconciled against
        the reader's own clock first.
        """
        now = time.time()
        with self._lock:
            attached_at, reloaded_at = self._attached_at, self._reloaded_at
            purged_at = self._purged_at
            purged_rows, purge_capped = self._purged_rows, self._purge_capped
        return {
            "loop_uptime_seconds": (None if attached_at is None
                                    else round(now - attached_at, 3)),
            "mapper_reload_age_seconds": (None if reloaded_at is None
                                          else round(now - reloaded_at, 3)),
            # [P-6] Flat, like the two above, so the route that spreads this dict does
            # not change. `outbox_purge_capped` is the one that carries the fact the
            # row count cannot: True = stopped at the per-cycle cap with more expired
            # rows waiting, False = drained everything expired, None = never ran, or
            # the last cycle raised before it could tell.
            "outbox_purge_age_seconds": (None if purged_at is None
                                         else round(now - purged_at, 3)),
            "outbox_purge_deleted": purged_rows,
            "outbox_purge_capped": purge_capped,
        }

    def clear(self):
        with self._lock:
            self._running.clear()
            self._outcomes.clear()
            self._attached_at = None
            self._reloaded_at = None
            self._purged_at = None
            self._purged_rows = None
            self._purge_capped = None
            self._seq = 0


#: Process singleton, the same shape `ingestion_activity` publishes.
registry = ChainActivityRegistry()


# 🪦 [판정 525 ①] `NO_ROWS_REASON = "the mapper produced no rows"` STOOD HERE AS A DEFAULT,
#   and 판정 509 had already settled that shape this morning: a default is an absence that
#   looks like an answer. Nobody had given a reason, and the operator read a sentence that
#   only restated the symptom - 「행이 없다」 written as 「행을 안 만들었다」. No default now:
#   a run nobody explained carries `None`, and absence looks like absence.


class _Run:
    """What a caller inside `running` can say: how many rows came out, and why none did.

    🔴 [판정 525 ②] THE REASON RIDES WITH THE COUNT, deliberately. They are one fact -
    「what happened」 - and a second call to set the reason is a second author for it, with
    the usual consequence that one of them is forgotten on some path.
    """

    def __init__(self):
        self.rows_out = None
        self.reason = None

    def produced(self, rows_out, reason=None):
        self.rows_out = rows_out
        self.reason = reason


@contextlib.contextmanager
def running(rule, mapper, target_table, rows_in):
    """Register ONE run of ONE rule - whichever door is running it (S-246).

    🔴 THE REGISTRATION LIVED INSIDE THE CUSTOM-MAPPER DOOR, AND THERE ARE TWO DOORS.
    `execute_custom_mapper` started an entry, recorded an outcome and finished the entry;
    `synthesis.run_builtin` did none of the three. So `join_into`, `builtin:join` and
    `auto_confirm` ran with no entry in the queue view and no outcome ever recorded - and
    because the loader SEEDS every declared rule as `never_evaluated`, a builtin that ran a
    thousand times still said 「아직 평가 안 됨」 forever. 소유자 2026-09-15: 「체인 대기열에서
    안 뜨고 돌고 있었네」.

    ⚠️ AN ABSENT ROW COUNT IS NOT ZERO. A caller that never says `produced` leaves the
    outcome alone rather than claiming 「ran, changed nothing」 - the two are different facts
    and this registry exists because they were being told apart wrongly.

    ⛔ AND IT NEVER RAISES ON ITS OWN BEHALF. Instrumentation that can take down the thing
    it describes is worse than no instrumentation; `record_outcome` and `finish` already
    hold that line and this adds nothing that can break it.
    """
    import event_constants

    entry = _Run()
    token = registry.start(rule, mapper, target_table, rows_in)
    try:
        yield entry
    except Exception as error:                                     # noqa: BLE001
        registry.record_outcome(rule, event_constants.RULE_OUTCOME_FAILED,
                                "%s: %s" % (type(error).__name__, error))
        raise
    else:
        if entry.rows_out is not None:
            registry.record_outcome(
                rule,
                event_constants.RULE_OUTCOME_RAN_CHANGED if entry.rows_out
                else event_constants.RULE_OUTCOME_RAN_UNCHANGED,
                None if entry.rows_out else entry.reason)
    finally:
        # 🔴 IN `finally`. A run that threw is exactly the case where an entry left
        # behind sits in the view forever saying something is still running.
        registry.finish(token)
