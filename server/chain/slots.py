"""Chain slots: one chain queue line runs in one slot process the chain worker gave it to
(총괄 19f6a9277, 소유자 「체인이든 뭐든 업데이트 스레드나 프로세스풀 안에서 하나 할당해서 실행시키고 그
리스트를 관리」 · 「그럼 내가 kill 9 pid 로도 지울 수 있잖아」 · 「뭐 큰 거 하나 돌리면 아주 시스템 마비」).

    python -m chain.slots <n>

The chain worker is the dispatcher (`SlotPool`): it keeps `chain_slots` slot processes up and
gives each a waiting line - from the queue's own lines (`chain.queue_lines`), not its first rows,
so a line behind a big replay is seen. A slot holds its line and runs it ONE batch at a time
through the chain's one batch body (`ingestion_worker.drain_events`), saying after each how it went.

  fair        after a batch a slot keeps its line unless a line that waited longer needs a slot,
              so a big line holds one slot and a new line takes the next batch boundary - a line
              drained to its end first would hold every slot two big lines got
  order       a line waits while a ROW-BY-ROW line ahead of it (its events carry their values)
              that touches one of its tables is unfinished - else the later value could land
              first. Tables two slots touch at once are held per group (`table_locks`).
  pace        a retroactive run's line rests by its run's pace (`pacing.json`) between batches
  stopped     a × or a kill of the slot's pid stops the line it holds only: the dispatcher sets
              aside what of it still waits, ends the slot's database connections, starts a new
              slot and never gives that line again on its own (`rerun_set_aside` brings it back)
  paused      no line is given; a slot ends its group at the next stage and answers `paused`
  logged      a slot writes no file: its lines go up its stderr and the dispatcher writes them
              into chain_worker.log under `[slot n pid P]` - one chain log, one writer

Asks go down a slot's stdin and answers come up a duplicate of its stdout, one JSON line each.
"""
import asyncio
import json
import logging
import os
import queue
import subprocess
import sys
import threading
import time

#: ingestion_settings.json - how many slot processes run the chain's queue lines. 1 runs them one
#: at a time; 0 or a wrong value reads as the default.
SLOTS_SETTING = "chain_slots"
DEFAULT_SLOTS = 2
#: The module a slot process runs - what its command line says, and what a kill checks first.
SLOT_MODULE = "chain.slots"
#: A slot's heartbeat file is `chain-slot-<n>`; the line it holds rides its `holds` lap.
BEAT_PREFIX = "chain-slot-"
HOLDS = "holds"
#: How a slot answers for a batch: nothing waited, a batch ran, it failed, the chain is paused.
DRAINED, RAN, FAILED, PAUSED = "drained", "ran", "failed", "paused"
#: A line that failed is given again after this long - the chain loop's own sleep after a failure.
FAILED_REST_SECONDS = 1.0
#: A slot index is not started again sooner than this - a slot that dies at start does not spin.
RESTART_REST_SECONDS = 10.0
#: How many lines the dispatcher reads, and how many rows of one line it looks at to know its
#: tables - the queue list's own cap, the chain loop's own fetch.
LINES_CAP = 50
WINDOW_ROWS = 200
#: The lines are read at most this often unless a NOTIFY says new rows came - the grouping scans
#: every waiting row, and a slot answers after every batch.
READ_EVERY_SECONDS = 1.0
#: A slot's own database pool - one group at a time needs its session and its lock connection;
#: measured on a slot running groups, reported with the landing (총괄 19f6a9277 ㉲).
SLOT_POOL = {"ASSY_DB_POOL_SIZE": "2", "ASSY_DB_MAX_OVERFLOW": "2"}
#: Who a set-aside by the dispatcher says did it.
CHAIN_WORKER = "chain worker"
#: How long a stop waits for a killed slot, and then for each of its connections, to end.
STOP_WAIT_SECONDS = 5

logger = logging.getLogger("Chain")


def beat_name(index):
    return "%s%d" % (BEAT_PREFIX, index)


def process_name(index):
    """The slot's logger - and so its database connections' application name (`assy_chainslot<n>`;
    `process_name("")` is every slot's prefix)."""
    return "ChainSlot%s" % index


def chain_slots(settings=None):
    """How many slots - read every tick, so a save takes effect without a restart."""
    from parsers.directory_watcher import load_ingestion_settings

    settings = load_ingestion_settings() if settings is None else settings
    value = settings.get(SLOTS_SETTING, DEFAULT_SLOTS)
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 1 else DEFAULT_SLOTS


# ------------------------------------------------------------------------------ the dispatcher

def line_of(db, line):
    """A queue line (`chain.queue_lines`) with its first waiting rows: `{"line", "run", "per_row", "events"}`."""
    import event_constants
    from chain import ingestion_worker
    from utils.payload_helper import get_payload_dict

    events = ingestion_worker.pending_chain_events(db, limit=WINDOW_ROWS, line=line.key, run=bool(line.run))
    return {"line": line.key, "run": bool(line.run), "events": events,
            "per_row": any(not event_constants.is_collapsed_payload(get_payload_dict(e) or {}) for e in events)}


def lines_to_give(lines, rules, behind=(), skip=(), limit=None):
    """The lines that may be given now, oldest first, up to `limit`. A line waits while a ROW-BY-ROW
    line ahead of it touching one of its tables is unfinished - held, resting or waiting: those
    events carry the value of their moment, and a later line run first would leave the earlier value
    last. `behind` is the tables of the row-by-row lines slots hold; `skip` the keys not to give.
    The tables a line touches are the order guard's own set, kept on the line as `touches`."""
    from chain.ingestion_worker import _group_read_tables, _group_target_tables

    given, behind = [], set(behind)
    for line in lines:
        if limit is not None and len(given) >= limit:
            break
        line["touches"] = _group_target_tables(line["events"], rules) | _group_read_tables(line["events"], rules)
        waits = bool(line["touches"] & behind)
        if line["per_row"]:
            behind |= line["touches"]
        if not (waits or line["line"] in skip):
            given.append(line)
    return given


class _Slot:
    """One slot process, as the dispatcher sees it. `line` is the line it holds - from the ask
    until it answers anything but `ran`, or is asked another; `ready` is «a batch of it ran, the
    slot waits to be told what next»."""

    def __init__(self, index, proc, woken):
        self.index, self.proc, self.line, self.ready, self.leaving = index, proc, None, False, False
        self.answers = queue.Queue()
        self._woken = woken
        threading.Thread(target=self._read, name="chain-slot-%d-answers" % index, daemon=True).start()
        threading.Thread(target=self._relay, name="chain-slot-%d-log" % index, daemon=True).start()

    @property
    def pid(self):
        return self.proc.pid

    def _read(self):
        for raw in self.proc.stdout:
            try:
                self.answers.put(json.loads(raw))
            except ValueError:
                continue
            self._woken.set()
        self._woken.set()

    def _relay(self):
        """The slot's log lines, into this process's log - under the logger that wrote them."""
        from utils.logger import relayed

        level, name = logging.WARNING, "Chain"
        for raw in self.proc.stderr:
            said = relayed(raw)
            if said is not None:
                level, name, message = said
            else:
                message = raw.rstrip("\r\n")
            logging.getLogger(name).log(level, "[slot %d pid %d] %s", self.index, self.pid, message)

    def _send(self, ask):
        try:
            self.proc.stdin.write(json.dumps(ask) + "\n")
            self.proc.stdin.flush()
            return True
        except (OSError, ValueError):
            return False

    def ask(self, line):
        """Run a batch of `line`. -> False when it can no longer be asked (it is reaped next tick)."""
        self.line, self.ready = line, False
        if self._send({"line": line["line"], "run": line["run"]}):
            return True
        self.line = None
        return False

    def release(self):
        """Hold nothing - the slot clears what its beat says it holds."""
        self.line, self.ready = None, False
        self._send({"line": None})

    def let_go(self):
        """Close its stdin - an idle slot ends at once."""
        try:
            self.proc.stdin.close()
        except OSError:
            pass


def _spawn(index):
    import paths
    from utils import logger as process_logging

    env = dict(os.environ, **SLOT_POOL, **{RELAY_LOG_ENV: process_logging.active_log_filename() or "chain_worker.log"})
    return subprocess.Popen(
        [sys.executable, "-m", SLOT_MODULE, str(index)], cwd=paths.SERVER_DIR, env=env,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        encoding="utf-8", errors="replace", bufsize=1, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _held(line):
    """What the dispatcher keeps of a line it gave: key, run, and - row by row - its tables."""
    return {"line": line["line"], "run": line["run"],
            "behind": sorted(line["touches"]) if line["per_row"] else []}


class SlotPool:
    """The dispatcher's slots. `tick` is one turn of the chain loop."""

    def __init__(self, spawn=_spawn):
        self._spawn, self.slots = spawn, {}
        self._resting = {}            # line key -> monotonic time it may be given again
        self._ran = {}                # line key -> monotonic time a batch of it last ran
        self._batches = {}            # retroactive line key -> batches run, for its pace
        self._started = {}            # slot index -> monotonic time it was last started
        self._wanted = DEFAULT_SLOTS
        self._read_at, self._waiting = -READ_EVERY_SECONDS, []
        self.woken = threading.Event()

    def busy(self):
        return any(slot.line is not None and not slot.ready for slot in self.slots.values())

    def tick(self, db, rules, notified=False):
        """Answers read, dead slots reaped, the pool sized, then - not paused - each slot that is
        free, or ready after a batch, given what it runs next. -> how many batches were asked."""
        from chain import control

        self.woken.clear()
        self._read_answers(db)
        self._reap(db)
        self._size(chain_slots())
        open_slots = [slot for _i, slot in sorted(self.slots.items())
                      if not slot.leaving and (slot.line is None or slot.ready)]
        if control.paused() is not None:
            for slot in open_slots:
                if slot.line is not None:
                    slot.release()
            return 0
        if not open_slots:
            return 0
        now = time.monotonic()
        self._resting = {key: until for key, until in self._resting.items() if until > now}
        held = {slot.line["line"] for slot in self.slots.values() if slot.line is not None}
        if notified or now - self._read_at >= READ_EVERY_SECONDS:
            self._read_at, self._waiting = now, self._givable(db, rules, held, len(open_slots))
        waiting = sorted((line for line in self._waiting
                          if line["line"] not in held and line["line"] not in self._resting),
                         key=lambda line: self._ran.get(line["line"], 0.0))       # longest unrun first
        asked = 0
        for slot in open_slots:
            mine = slot.line
            if mine is not None and mine["line"] not in self._resting and not (
                    waiting and self._ran.get(waiting[0]["line"], 0.0) < self._ran.get(mine["line"], 0.0)):
                nxt = mine                                   # it keeps its line
            elif waiting:
                nxt = _held(waiting.pop(0))
            else:
                if mine is not None:
                    slot.release()                           # its line rests and nothing waits
                continue
            if slot.ask(nxt):
                asked += 1
                if nxt is not mine:
                    logger.info("[Chain] slot %d (pid %d) runs line %s", slot.index, slot.pid, nxt["line"])
        return asked

    def _givable(self, db, rules, held, wanted):
        """The waiting lines a slot may take, oldest first, from the queue's own lines - each
        line's rows read only as far as the order needs them."""
        from chain import queue_lines

        behind = {t for slot in self.slots.values() if slot.line is not None for t in slot.line["behind"]}
        lines = (line_of(db, line) for line in queue_lines.waiting_lines(db, LINES_CAP) if line.key not in held)
        return lines_to_give(lines, rules, behind, set(self._resting), limit=wanted)

    def _read_answers(self, db):
        now = time.monotonic()
        for slot in self.slots.values():
            while True:
                try:
                    answer = slot.answers.get_nowait()
                except queue.Empty:
                    break
                if slot.line is None or answer.get("line") != slot.line["line"]:
                    continue
                key, outcome = slot.line["line"], answer.get("outcome")
                if outcome == RAN:
                    slot.ready = True
                    self._ran[key] = now
                    if slot.line["run"]:
                        self._rest_by_pace(db, key, now)
                else:
                    if outcome == FAILED:
                        self._resting[key] = now + FAILED_REST_SECONDS
                    if outcome == DRAINED:
                        self._ran.pop(key, None)
                        self._batches.pop(key, None)
                        # the window read before it drained still lists it: given again from there, it
                        # was asked, drained at once and given again every few ms until the next read
                        self._waiting = [line for line in self._waiting if line["line"] != key]
                    slot.line, slot.ready = None, False
            if slot.leaving and (slot.line is None or slot.ready):
                slot.line = None
                slot.let_go()

    def _rest_by_pace(self, db, key, now):
        per_cycle, rest = _pace(db, key)
        self._batches[key] = self._batches.get(key, 0) + 1
        if per_cycle and rest and self._batches[key] % per_cycle == 0:
            self._resting[key] = now + rest

    def _reap(self, db):
        """A slot that ended holding a line ended before finishing it: what of the line still
        waits is set aside, its database connections are ended, and the line is not given again."""
        from chain import set_aside

        for index, slot in sorted(self.slots.items()):
            code = slot.proc.poll()
            if code is None:
                continue
            del self.slots[index]
            if index > self._wanted:
                _remove_beat(beat_name(index))           # not started again - its file would read stale
            if slot.line is None:
                continue
            end_connections(db, index)
            why = "slot pid %d ended (exit %s) before finishing" % (slot.pid, code)
            done = set_aside.set_aside_line(db, slot.line["line"], CHAIN_WORKER, run=slot.line["run"], reason=why)
            logger.warning("[Chain] %s line %s - %d waiting event(s) set aside; run them again with "
                           "rerun_set_aside", why, slot.line["line"], done["marked"])

    def _size(self, wanted):
        now = time.monotonic()
        self._wanted = wanted
        for index in range(1, wanted + 1):
            if index in self.slots or now - self._started.get(index, -RESTART_REST_SECONDS) < RESTART_REST_SECONDS:
                continue
            self._started[index] = now
            try:
                self.slots[index] = _Slot(index, self._spawn(index), self.woken)
                logger.info("[Chain] slot %d started, pid %d", index, self.slots[index].pid)
            except Exception as exc:                                    # noqa: BLE001
                logger.error("[Chain] slot %d could not start: %s", index, exc)
        for index, slot in self.slots.items():
            if index > wanted and not slot.leaving:
                slot.leaving = True
                if slot.line is None or slot.ready:
                    slot.line = None
                    slot.let_go()

def _pace(db, run_id):
    """`(batches per cycle, rest seconds)` of the run's own pace - the default when it named none."""
    from chain import replay
    from database import models

    params = db.query(models.RetroactiveRun.params).filter(models.RetroactiveRun.run_id == run_id).scalar()
    if isinstance(params, str):
        try:
            params = json.loads(params)
        except ValueError:
            params = None
    try:
        return replay.resolve_pace(params.get("pace") if isinstance(params, dict) else None)
    except Exception:                                                   # noqa: BLE001 - checked when it was asked
        return replay.resolve_pace(None)


def _remove_beat(name):
    from utils import heartbeat

    try:
        os.remove(heartbeat.heartbeat_path(name))
    except OSError:
        pass


def holding(key, beats=None):
    """`(index, pid)` of the slot whose beat says it holds line `key`, or None."""
    from utils import heartbeat

    for name, beat in (heartbeat.read_all() if beats is None else beats).items():
        if (name.startswith(BEAT_PREFIX) and name[len(BEAT_PREFIX):].isdigit() and not beat.get("stale")
                and ((beat.get("laps") or {}).get(HOLDS) or {}).get("line") == key):
            return int(name[len(BEAT_PREFIX):]), beat.get("pid")
    return None


def is_slot(pid, index):
    """Is `pid` slot `index`'s process - by its command line, so a pid the system gave to
    another program is never killed."""
    try:
        import psutil

        return ["-m", SLOT_MODULE, str(index)] == psutil.Process(int(pid)).cmdline()[-3:]
    except Exception:                                                   # noqa: BLE001 - gone, or not ours to ask
        return False


def stop_slot(db, key):
    """Stop the slot process holding line `key` (a ×, 총괄 19f6a9277): killed and waited for, then
    its database connections ended and waited for - what it committed is in the table when this
    returns (총괄 54a53f894: the × counts after it). The dispatcher reaps it, sets aside what of the
    line still waits and starts a new slot. -> the pid stopped, or None."""
    found = holding(key)
    if found is None or not is_slot(found[1], found[0]):
        return None
    import psutil

    try:
        process = psutil.Process(int(found[1]))
        process.kill()
    except psutil.NoSuchProcess:
        return None
    try:
        process.wait(STOP_WAIT_SECONDS)
    except psutil.TimeoutExpired:
        logger.warning("[Chain] slot %d pid %s had not ended %d s after its kill - its line is "
                       "counted as it stands", found[0], found[1], STOP_WAIT_SECONDS)
    end_connections(db, found[0])
    return found[1]


def end_connections(db, index):
    """End slot `index`'s database connections and wait, up to `STOP_WAIT_SECONDS` each, until
    they have gone (`pg_terminate_backend(pid, timeout)`, PG 14+) - a killed process's query runs
    on until it next writes to the client, and a commit it sent lands before its connection goes.
    -> how many. PostgreSQL only."""
    from sqlalchemy import text
    from database.database import connection_name

    if db.get_bind().dialect.name != "postgresql":
        return 0
    ended = db.execute(text(
        "SELECT count(pg_terminate_backend(pid, :wait_ms)) FROM pg_stat_activity"
        " WHERE application_name = :name AND datname = current_database()"),
        {"name": connection_name(process_name(index)), "wait_ms": STOP_WAIT_SECONDS * 1000}).scalar()
    db.commit()
    return ended


# ------------------------------------------------------------------------------ the slot

def main(argv=None):
    index = int((sys.argv[1:] if argv is None else argv)[0])
    answers = os.fdopen(os.dup(sys.stdout.fileno()), "w", encoding="utf-8", buffering=1)
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    sys.stdout = sys.stderr
    from utils.logger import get_process_logger

    # FIRST, before anything opens a log of its own: no file here - the lines go up stderr and the
    # dispatcher writes them into the file it names (its own).
    log = get_process_logger(process_name(index), os.environ[RELAY_LOG_ENV], relay=sys.stderr)
    from database import crud, models

    models.init_dynamic_models(crud.TABLE_CONFIG)
    from chain import ingestion_worker

    ingestion_worker.GROUP_BEAT = beat_name(index)
    log.info("[Chain] slot %d up, pid %d", index, os.getpid())
    asyncio.run(_serve(index, answers))


#: The environment cell the dispatcher names its log file in - where its slots' lines land.
RELAY_LOG_ENV = "ASSY_SLOT_RELAY_LOG"


def _read_asks(loop, asks):
    for raw in sys.stdin:
        try:
            loop.call_soon_threadsafe(asks.put_nowait, json.loads(raw))
        except ValueError:
            continue
    # The dispatcher let this slot go, or is gone: a group in flight is rolled back by the
    # database, and its events wait for the next dispatcher. Its beat goes with it - a file left
    # behind would read as a wedged slot.
    from utils import heartbeat

    heartbeat.forget(heartbeat.own_name() or "")
    os._exit(0)


async def _serve(index, answers):
    from chain import activity, ingestion_worker
    from database.database import SessionLocal
    from utils import heartbeat

    name = beat_name(index)
    activity.registry.attach()
    rules = ingestion_worker.load_chain_rules()
    ingestion_worker.warmup_worker(rules, SessionLocal)
    seen = _newest_reload()
    asks = asyncio.Queue()
    threading.Thread(target=_read_asks, args=(asyncio.get_running_loop(), asks),
                     name="chain-slot-asks", daemon=True).start()
    while True:
        heartbeat.beat(name, note=ingestion_worker._worker_note())
        try:
            ask = await asyncio.wait_for(asks.get(), heartbeat.HEARTBEAT_SLICE_SECONDS)
        except asyncio.TimeoutError:
            continue
        if ask.get("line") is None:
            heartbeat.record_lap(name, HOLDS)
            heartbeat.beat(name, note=ingestion_worker._worker_note(), force=True)
            continue
        heartbeat.record_lap(name, HOLDS, line=ask["line"])
        heartbeat.beat(name, note=ingestion_worker._worker_note(), force=True)
        outcome, rules, seen = await _run_batch(ask["line"], bool(ask.get("run")), rules, seen)
        if outcome != RAN:
            heartbeat.record_lap(name, HOLDS)
            heartbeat.beat(name, note=ingestion_worker._worker_note(), force=True)
        answers.write(json.dumps({"line": ask["line"], "outcome": outcome}) + "\n")


async def _run_batch(key, run, rules, seen):
    """One batch of the line's waiting events, through the chain's batch body."""
    from chain import activity, control, ingestion_worker
    from database.database import SessionLocal
    from utils import heartbeat
    from utils import logger as process_logging

    if control.paused() is not None:
        return PAUSED, rules, seen
    rules, seen = _reloaded(rules, seen)
    started = time.monotonic()
    db = SessionLocal()
    try:
        events = ingestion_worker.pending_chain_events(db, line=key, run=run)
        if not events:
            return DRAINED, rules, seen
        failed = await ingestion_worker.drain_events(db, events, rules, SessionLocal, batch_wake_ts=started)
    except Exception as exc:                                            # noqa: BLE001
        # The chain loop's own contract, kept: a batch that raised is said and tried again, its
        # events as they were - a set-aside cutting a group's wait for a table lands here. Raised
        # on, it ended the slot, and the slot's end set its whole line aside (총괄 10-08).
        db.rollback()
        logger.error("[Chain] a batch of line %s raised - its events wait as they were and run again: %s",
                     key, exc)
        failed = True
    finally:
        db.close()
    heartbeat.record_lap(ingestion_worker.GROUP_BEAT, "chain", seconds=time.monotonic() - started,
                         log_filename=process_logging.active_log_filename(),
                         **activity.registry.instants())
    if control.paused() is not None:
        return PAUSED, rules, seen
    return (FAILED if failed else RAN), rules, seen


def _newest_reload():
    from sqlalchemy import func
    from database.database import SessionLocal
    from database.models import DatabaseOutbox

    session = SessionLocal()
    try:
        return session.query(func.max(DatabaseOutbox.id)).filter(
            DatabaseOutbox.event_type == "SYSTEM_RELOAD").scalar() or 0
    finally:
        session.close()


def _reloaded(rules, seen):
    """The reloads past `seen`, applied as the chain loop applies them."""
    from chain import ingestion_worker
    from database.database import SessionLocal
    from runtime import system_reload

    session = SessionLocal()
    try:
        rows = system_reload.reloads_after(session, seen)
    finally:
        session.close()
    if not rows:
        return rules, seen
    work = system_reload.reload_for(system_reload.CHAIN_WORKER, rows)
    return (ingestion_worker.reload_rules(work) if work else rules), rows[-1].id


if __name__ == "__main__":
    main()
