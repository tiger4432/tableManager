# -*- coding: utf-8 -*-
"""The ledger process's work (총괄 7763dd6d0, 소유자 「원장 프로세스 ㄱ」): the follow-up, the row census, the
ledger's schema and cursor fingerprints at start, and the ledger's index line - moved out of the chain worker
unchanged, so the chain writes on when the ledger stops. The chain's Pause holds both loops too: no new batch or
source is taken while it lasts, and the one running finishes (소유자 10-08 «Pause 만 전부»). `start_ledger_worker` runs them; the launcher starts it as its
own process (`run_ledger_worker.py`), and a server run alone starts it beside the chain loop (`main.py`)."""
import asyncio
import logging
import time

from chain import control as chain_control
from chain import keyset_scan
from ledger import followup as ledger_followup
from utils import heartbeat
from utils.logger import count_crossed
from error_said import told

logger = logging.getLogger("Ledger")
#: This process's heartbeat name - its beat, and the laps of its follow-up and census (`runtime.loops`).
LEDGER_BEAT = "ledger"


#: What the follow-up loop waits when the queue is empty, whatever the declared pace says.
#: A pace of `fast` rests for zero seconds, and zero seconds around an empty deque is a hot
#: loop -- the pace answers "how hard may I push while there is work", not "how often do I
#: look".
FOLLOWUP_IDLE_SECONDS = 1.0


def _ledger_outbox_depth_sync(db_session_factory):
    """Events the ledger has yet to follow, in a thread."""
    db = db_session_factory()
    try:
        return ledger_followup.outbox_depth(db.get_bind())
    finally:
        db.close()


def _drain_ledger_followup_sync(db_session_factory, rows=None):
    """One follow-up batch of at most `rows` rows (one event when None), in a thread. The session is this call's and
    closes with it.

    🔴 INTO EVERY WORLD THAT FOLLOWS LIVE, EACH ON ITS OWN DECLARATION (총괄 092a6f9e5) - asked
    of the layout every batch (`schema.live_worlds`), so a world switched on or off takes the
    next batch with it."""
    from ledger import schema

    db = db_session_factory()
    try:
        engine = db.get_bind()
        followers = []
        for world in schema.live_worlds():
            try:
                followers.append((world, _compiled_setup(world)))
            except Exception as exc:                    # noqa: BLE001 - said by name below
                # 🔴 ONE WORLD'S BROKEN DECLARATION STOPS ONLY ITSELF (총괄 6c6ccad8f, 소유자 「ㄷ」) - the
                #    operating world's still stops everything; it never switches itself off.
                if world == schema.operating_world():
                    raise FollowUpStopped(world, exc) from exc
                _switch_off(world, exc)
        return ledger_followup.drain_outbox_once(engine, None, followers, rows=rows)
    finally:
        db.close()


#: {declaration root: (the stamps it was compiled at, the compiled declaration or what it raised)}
_COMPILED = {}


def _stamped(key, paths, build):
    """`build()` again only when one of `paths` changed (`file_stamp`) - THE one rule for a declaration read from its
    files, not every batch nor every walk request (총괄 86d5061a0 · 9166099d4). A failure is held the same way: the same
    files fail the same way, so they are not read again until one changes (총괄 558a46ef1) - held as its class, words and
    attributes and raised anew each time, so two threads never raise one object nor keep its frames."""
    from ledger.setup import file_stamp

    stamp = tuple(file_stamp(path) for path in paths)
    held = _COMPILED.get(key)
    if held is None or held[0] != stamp:
        try:
            held = (stamp, build(), None)
        except Exception as exc:                            # noqa: BLE001 - raised below
            held = (stamp, None, (type(exc), exc.args, dict(vars(exc))))
        _COMPILED[key] = held
    if held[2] is not None:
        kind, args, attributes = held[2]
        failure = kind.__new__(kind)
        failure.args = args
        failure.__dict__.update(attributes)
        raise failure
    return held[1]


def _compiled_setup(world):
    """A world's declaration, compiled again only when its file or the catalogue changed (`_stamped`)."""
    from ledger import schema
    from ledger.setup import load_setup, physical_catalog_path

    names = schema.world_names(world)
    return _stamped(names.declaration_root, (names.declaration_path, physical_catalog_path()),
                    lambda: load_setup(names.declaration_root))


#: How many sources' refusals a stop sentence names before it counts the rest.
FOLLOWUP_REFUSALS_SHOWN = 3
#: The `by` a world the follow-up switched off carries in the layout's history - its sentence follows.
FOLLOWUP_SWITCHED_OFF_BY = "ledger follow-up: "


def _declaration_failure(world, exc):
    """One world's declaration that did not compile, as one sentence - the world, its file, the
    code and the first sources' refusals (총괄 558a46ef1)."""
    from ledger import schema

    refusals = getattr(exc, "refusals", ())
    said = ["%s: %s %s" % refusal for refusal in refusals[:FOLLOWUP_REFUSALS_SHOWN]]
    if len(refusals) > FOLLOWUP_REFUSALS_SHOWN:
        said.append("+%d more" % (len(refusals) - FOLLOWUP_REFUSALS_SHOWN))
    return "world %s · declaration %s · %s · %s" % (
        world, schema.world_names(world).declaration_path,
        getattr(exc, "code", None) or type(exc).__name__,
        "; ".join(said) if said else (str(exc).strip().splitlines() or [""])[-1])


class FollowUpStopped(Exception):
    """The operating world's declaration does not compile, so the follow-up follows nothing."""

    def __init__(self, world, cause):
        self.world = world
        self.sentence = _declaration_failure(world, cause)
        super().__init__(self.sentence)


def _switch_off(world, exc):
    """A live world that is not the operating one and does not compile: its live off, once, with the
    sentence in the layout's history, and the next step said (총괄 6c6ccad8f)."""
    from ledger import schema
    from ledger.backfill import catch_up_command

    sentence = _declaration_failure(world, exc)
    schema.set_live(world, False, by=FOLLOWUP_SWITCHED_OFF_BY + sentence)
    logger.error("[LedgerFollowUp] live switched OFF: %s - the other worlds go on. Next: fix it, "
                 "switch its live on (the screen runs the catch-up), or from server/: %s",
                 sentence, catch_up_command(world))
    _record_followup_lap(state=FOLLOWUP_FLOWING)


def _switched_off_by_the_follow_up():
    """[{world, at, said}] - the worlds the follow-up switched off that are off still, read from the
    layout's history, which outlives this process."""
    from ledger import schema

    last = {}
    for entry in schema.layout().get("history") or ():
        if "live" in entry:
            last[entry.get("world")] = entry
    return [{"world": world, "at": entry.get("at"),
             "said": str(entry["by"])[len(FOLLOWUP_SWITCHED_OFF_BY):]}
            for world, entry in sorted(last.items())
            if entry.get("live") is False
            and str(entry.get("by") or "").startswith(FOLLOWUP_SWITCHED_OFF_BY)]


FOLLOWUP_FLOWING, FOLLOWUP_STOPPED = "flowing", "stopped"
#: Every how often a stop that lasts is said again, with what is waiting (총괄 558a46ef1 · cb419a8a0).
FOLLOWUP_STOP_REMINDER_SECONDS = 600.0
#: {"world", "sentence", "since", "said_at"} while the follow-up is stopped.
_FOLLOWUP_STOP = {}


def _record_followup_lap(**cells):
    """The follow-up's row on the admin (`/runtime`, loop `ledger_followup`) - its state, and the
    worlds it switched off, on every lap it records."""
    heartbeat.record_lap(LEDGER_BEAT, "ledger_followup",
                         switched_off=_switched_off_by_the_follow_up() or None, **cells)


def _say_the_follow_up(stop, waiting, now=None):
    """A stop said when it starts or changes, again every ten minutes while it lasts, and once
    when it ends - each line with what is waiting. `stop`: a `FollowUpStopped`, or None when the
    operating world compiles. `waiting`: a callable, asked only when a line is said."""
    now = time.time() if now is None else now
    held = _FOLLOWUP_STOP
    if stop is None:
        if held:
            count = waiting()
            logger.warning("[LedgerFollowUp] flowing again: world %s compiles, after %.0f s "
                           "stopped; %d event(s) waiting", held["world"], now - held["since"], count)
            held.clear()
            _record_followup_lap(depth=count, state=FOLLOWUP_FLOWING)
        return
    if held.get("sentence") == stop.sentence:
        if now - held["said_at"] < FOLLOWUP_STOP_REMINDER_SECONDS:
            return
        line = "[LedgerFollowUp] still stopped, %.0f s: %%s; %%d event(s) waiting" % (
            now - held["since"])
    else:
        held.update(world=stop.world, sentence=stop.sentence, since=held.get("since", now))
        line = ("[LedgerFollowUp] stopped: %s; %d event(s) waiting - nothing is followed until "
                "it compiles")
    held["said_at"] = now
    count = waiting()
    logger.error(line, stop.sentence, count)
    _record_followup_lap(depth=count, state=FOLLOWUP_STOPPED, since=held["since"],
                         world=stop.world, said=stop.sentence)


def _measure_one_source_sync(db_session_factory, source):
    """One source's census, in a thread. The session is this call's and closes with it.

    🔴 THE PACED TICK DOES NOT SCAN (S-122). `exact_rows=False` makes the relation count
    the planner's free estimate instead of a `count(*)` over the whole relation - measured
    on this box 1.18 s over 1.43M rows, run per source, per tick, without resting, so on a
    production-sized table the census is never NOT scanning and every other query waits
    behind it. The number is published AS an estimate; the exact count belongs to the
    command a person runs.

    It is measured in the operating world (총괄 092a6f9e5); its declaration comes from the
    compile cache (`_compiled_setup`) - compiling it costs 91 ms on this box, and it was once
    done for every source of a lap.
    """
    from ledger import backfill as ledger_backfill
    from ledger.store import LedgerStore

    db = db_session_factory()
    try:
        engine = db.get_bind()
        return ledger_backfill.measure_and_store(
            engine, _compiled_setup(None), source, LedgerStore(engine), exact_rows=False)
    finally:
        db.close()


async def run_ledger_row_census(db_session_factory):
    """Measure 「table rows · indexed · not yet translated」 per source, at the declared pace.

    🔴 IT EXISTS SO THE REQUEST PATH DOES NOT DO THIS (D5, 판정 180). Both numbers are
    scans; a declaration response that counted them would be a screen that waits for a
    ten-million-row table. This writes, `/declaration` reads, and the answer carries the
    instant it was true.

    ⚠️ ONE SOURCE PER UNIT, NOT ONE SWEEP PER CYCLE. The pace's `units_per_cycle` is
    counted in SOURCES, so an operator slowing this down slows the individual counts rather
    than the gap between full sweeps -- which is the knob that matters when the concern is
    「this is crowding the database right now」.

    ⛔ ONE SOURCE'S FAILURE COSTS THAT SOURCE ONLY, and it is named. A source whose
    relation was dropped must not silence the fourteen after it.
    """
    import pacing
    from ledger.backfill import ROW_CENSUS_JOB, census_sources

    while True:
        try:
            units, rest = pacing.job_pace(ROW_CENSUS_JOB)
        except Exception as exc:
            logger.warning("[LedgerCensus] pace unreadable, using the default: %s", told(exc))
            units, rest = 1, 60.0
        # 🔴 ONE COMPILE PER LAP, NOT ONE PER SOURCE (S-122). `load_setup()` compiles the
        # whole declaration - 91 ms on this box - and it cannot change inside a lap, so
        # fifteen sources were paying for fifteen identical answers.
        setup = None
        try:
            setup = await asyncio.to_thread(_load_setup_sync, db_session_factory)
            # 🔴 A RETIRED SOURCE IS COUNTED BY NAME, NOT BY ROWS (S-177 ①). Nothing
            # arrives for it, so a remainder measured here would publish a backlog that
            # will never move - and after S-177 its relation may not be in the catalogue
            # at all, which would spend a lap failing once per source. The names ride on
            # the lap line, so the skip is a value rather than a silence. A source the
            # loader REFUSED is measured - its census is the refusal (총괄 7426f76b0 ㉤).
            sources, retired = census_sources(setup)
        except Exception as exc:
            logger.warning("[LedgerCensus] the declaration could not be read: %s", told(exc))
            # ✓ [S-284] NOTHING TO REPAIR HERE, AND THE REASON IS WORTH KEEPING. A census
            # instrument flagged `len(sources)` on the lap line below as 「a swallowed
            # failure that becomes a number」 - it is not: the whole block is guarded by
            # `if sources:`, so when the declaration could not be read this loop publishes
            # NO lap at all, which is 「말 안 함」 spelled as the absence of the whole entry.
            # The WARNING above is the only thing said, and that is correct.
            sources = []
            retired = []
        measured_now = 0
        refused = []
        lap_started = time.monotonic()
        measured_seconds = 0.0
        for source in sources:
            if chain_control.paused() is not None:
                break
            source_started = time.monotonic()
            census = None
            try:
                census = await asyncio.to_thread(_measure_one_source_sync, db_session_factory,
                                                 source)
            except Exception as exc:
                logger.warning("[LedgerCensus] %s failed: %s", source, told(exc))
            # ⚠️ THE FAILING SOURCE COSTS THE DATABASE TOO, so it is timed like any
            # other - counting only the successes would report a lap as cheaper than
            # it was, which is the direction a pacing number must never be wrong in.
            measured_seconds += time.monotonic() - source_started
            # 🔴 [총괄 3b3b6803f] THE REST IS FOR A SCAN. A refused source's census is the
            #    loader's refusal, taken without touching the database, so it earns none -
            #    the running sources keep the cadence they had.
            if census is not None and census.get("refused"):
                refused.append(source)
                continue
            measured_now += 1
            if units is not None and measured_now % max(units, 1) == 0:
                await asyncio.sleep(rest)
        # 🔴 THE TICK SAYS WHAT IT COST (S-122 gate). A background job that crowds the
        # database is invisible until somebody correlates two graphs; a line per lap with
        # its own wall clock is the value 「큐 깊이는 값으로 보임」 asks for, and it is what
        # tells an operator whether slowing the pace actually helped.
        if sources:
            lap_seconds = time.monotonic() - lap_started
            logger.info("[LedgerCensus] lap: %d source(s) in %.3fs, measured %.3fs "
                        "(rest %.0fs between, "
                        "relation rows are planner estimates - `python -m ledger census` "
                        "counts)%s", len(sources), lap_seconds,
                        measured_seconds, rest,
                        (f" · refused by the loader (no scan): {', '.join(refused)}"
                         if refused else "")
                        + (f" · retired (content unvalidated): {', '.join(retired)}"
                           if retired else ""))
            # S-176. `depth` is the number of sources this lap still had to walk, which is
            # this loop's remaining work in the sense every other entry uses.
            heartbeat.record_lap(LEDGER_BEAT, "ledger_census", seconds=lap_seconds,
                                 depth=len(sources), pace=rest)
        await asyncio.sleep(rest if sources else max(rest, 60.0))


def _load_setup_sync(db_session_factory):
    """The compiled declaration, once, in a thread. The session closes with the call."""
    from ledger.setup import load_setup

    db = db_session_factory()
    try:
        return load_setup()
    finally:
        db.close()


async def run_ledger_followup(db_session_factory):
    """Drain the ledger follow-up queue at the declared pace, BESIDE the chain loop.

    🔴 THE PACE IS THIS LOOP'S, NOT `rescope`'S. `rescope` has no pacing of its own and
    keeps none (one seat, unchanged): a batch runs whole and then this rests. Pacing inside
    the re-translation would throttle one molecule's write, which is not what needs to
    yield -- the QUEUE is (ruling 129-ter).

    🔴 THE DECLARATION IS RE-READ EVERY CYCLE. An operator who slows this down at 2am
    edits one cell in `pacing.json`, which is the reason that file exists rather than a
    constant; re-reading once per cycle is what makes "no restart" true.

    ⛔ IT NEVER DIES QUIETLY. Anything this raises is named and the loop rests and goes on:
    the event stays unmarked in the outbox and is taken again, and a task that ended
    silently would cost every batch after it with nothing on screen.
    """
    import pacing

    while True:
        try:
            units, rest = pacing.job_pace(ledger_followup.FOLLOWUP_JOB)
        except Exception as exc:
            logger.warning("[LedgerFollowUp] pace unreadable, using the default: %s", told(exc))
            units, rest = None, FOLLOWUP_IDLE_SECONDS
        drained = 0
        confirmed_total = refused_total = 0
        skipped = {}
        lap_started = time.monotonic()
        # a batch's rows by the one page-size rule (총괄 796f04605 ② - the pace is seconds of work, not events)
        size = keyset_scan.PageSize()
        while (units is None or drained < units) and chain_control.paused() is None:
            try:
                # S-176 덧붙임: the batch already COUNTS what it auto-confirmed; the return
                # value was being discarded, so the two numbers died one frame above where
                # they were computed. Carried, not re-measured.
                done = await asyncio.to_thread(_drain_ledger_followup_sync,
                                               db_session_factory, size.next())
            except FollowUpStopped as stop:
                await asyncio.to_thread(_say_the_follow_up, stop,
                                        lambda: _ledger_outbox_depth_sync(db_session_factory))
                break
            except Exception as exc:
                # The event stays unmarked and is taken again after the rest - going on
                # here would take the same one in a tight loop. Its line is said on the 1st,
                # 10th, 100th ... of its error (총괄 cb419a8a0 - once a lap filled the log all day).
                nth = count_crossed(ledger_followup.REPEATS, ("batch", type(exc).__name__))
                if nth:
                    logger.warning("[LedgerFollowUp] batch failed: %s - #%d of this error (said at the "
                                   "1st, 10th, 100th ...)", told(exc), nth)
                break
            if _FOLLOWUP_STOP:
                await asyncio.to_thread(_say_the_follow_up, None,
                                        lambda: _ledger_outbox_depth_sync(db_session_factory))
            if done is None:
                break
            confirmed_total += done.get("auto_confirmed") or 0
            refused_total += done.get("auto_refused") or 0
            for source, said in (done.get("sources") or {}).items():
                if (said or {}).get("skipped"):
                    skipped[source] = skipped.get(source, 0) + 1
            drained += done.get("events", 1)
        # 🔴 A SUCCESSFUL DRAIN USED TO SAY NOTHING, and that silence cost a measurement
        # (S-160, 판정 269). Asked whether the drain was working DURING a reproduction
        # window, nothing could answer: failures warn, successes were mute, and the queue
        # depth lives in this process's memory where no query reaches it. 「큐 깊이는 값으로
        # 보임」 is the standing rule and this is the line it asks for - the same shape the
        # census lap already uses beside it.
        #
        # ⚠️ SILENT WHEN IT DID NOTHING, deliberately. This loop wakes on a timer whether or
        # not there is work; a line per idle lap would bury the laps that moved something,
        # which is the log equivalent of a screen explaining what it is not showing.
        if drained:
            lap_seconds = time.monotonic() - lap_started
            depth_left = await asyncio.to_thread(_ledger_outbox_depth_sync, db_session_factory)
            logger.info("[LedgerFollowUp] lap: %d item(s) in %.3fs, %d left in the queue "
                        "(rest %.0fs between)%s", drained, lap_seconds, depth_left, rest,
                        "".join(" · skipped %s=%d (no column it reads changed)" % (s, n)
                                for s, n in sorted(skipped.items())))
            # S-176: the same three numbers, carried instead of dropped. No new
            # measurement -- `lap_seconds` and `depth_left` are the log line's own.
            _record_followup_lap(seconds=lap_seconds,
                                 depth=depth_left, items=drained, pace=rest,
                                 # S-176 덧붙임 (판정 292): the auto-confirm half runs on
                                 # THIS lap, so its two counts belong on this row. A lap
                                 # that confirmed nothing and a lap where the sweep never
                                 # ran are different facts — both are values here.
                                 auto_confirmed=confirmed_total,
                                 auto_refused=refused_total,
                                 skipped=skipped or None, state=FOLLOWUP_FLOWING)
        await asyncio.sleep(rest if drained else max(rest, FOLLOWUP_IDLE_SECONDS))


def _ensure_ledger_schema_sync(db_session_factory):
    """Bring the ledger's own schema up to date. Catalogue-first and idempotent.

    🔴 S-88 — WITHOUT THIS, A LANDED COLUMN NEVER REACHES A LIVE DATABASE.
    `schema.CURSOR_ADDITIONS` is the ADD COLUMN list, `ensure_schema` applies it, and
    MEASURED 2026-09-09 its only callers were seed scripts and tests: no production path ran
    it at all. The procedure that used to — 「배포 뒤 소스마다 백필 한 번」 — went away with the
    cursor read path (S-76), and the ensure it carried went with it, unnoticed because
    nothing had needed a new column since.

    S-58 is what found it: the census column landed, the job ran every tick, and every tick
    failed on a column that did not exist. The fix is not that column; it is that a landed
    column must reach live WITHOUT a person running one line by hand.

    ⚠️ IT DOES NOT TAKE THE PROCESS DOWN. A ledger schema that cannot be ensured costs the
    ledger jobs and is named — loudly, once, at startup, where an operator is already reading.
    """
    from ledger.store import LedgerStore

    db = db_session_factory()
    try:
        LedgerStore(db.get_bind()).ensure_schema()
    finally:
        db.close()


def _set_partitions_autoanalyze_sync(db_session_factory):
    """`schema.set_partitions_autoanalyze` on the ledger's database (총괄 53338e99b). Contained: a line, never a process
    that will not start."""
    from ledger import schema

    try:
        db = db_session_factory()
        try:
            engine = db.get_bind()
        finally:
            db.close()
        if engine.dialect.name != "postgresql":
            return
        connection = engine.raw_connection()
        try:
            schema.set_partitions_autoanalyze(connection)
        finally:
            connection.close()
    except Exception as exc:                                            # noqa: BLE001
        logger.warning("[Ledger] the partitions' autoanalyze setting was not compared (this process goes on): %s: %s",
                       type(exc).__name__, told(exc), exc_info=exc)


def _restamp_moved_fingerprints_sync(db_session_factory):
    """Move the stored fingerprint of every cursor whose DECLARATION did not change.

    \U0001f534 S-87, AND IT IS THE HALF THAT MAKES THE OTHER HALF SAFE. A cursor whose stored
    string differs from the current one is REFUSED (`cursor_snapshot_reset_required`), which
    is correct when the declaration moved and is a full stop when only the grammar did.
    Measured 2026-09-09: removing one unused descriptor field moved all 15 fingerprints, the
    operator's ledger stopped at the previous day's backfill, and it took a person running
    `scripts/ledger_restamp_cursor.py --apply` by hand to start again. A landed change must
    reach live WITHOUT that line, for the same reason S-88 exists three functions up.

    \u26d4 THE POSITION IS NOT TOUCHED, and that is why this is safe to do unattended.
    `restamp_cursor` writes `translator_ver` and nothing else - not `cursor_value`, not the
    counters, not one atom - so the next batch reads the rows AFTER the unchanged position.
    A reset or a rewind would re-read rows that are already in the ledger, and under a new
    fingerprint they would land AGAIN rather than dedupe: on millions of rows, doubled.

    \u26a0\ufe0f IT DECIDES NOTHING OF ITS OWN. `LedgerStore.restamp_decision` is the one
    predicate, shared with the script, so a v1-shaped cursor is refused here exactly as it is
    there rather than being quietly moved by the daemon that runs unattended.

    Every move is NAMED in the log. A fingerprint that changes silently is a fingerprint
    nobody can audit, and this runs on every boot.
    """
    from ledger import schema
    from ledger.setup_registry import cursor_translator_version
    from ledger.store import LedgerStore

    db = db_session_factory()
    try:
        engine = db.get_bind()
        setup = _compiled_setup(None)
        # The operating world's cursors, on its declaration (총괄 092a6f9e5): another world's
        # are a person's `--world` restamp.
        world = schema.world_names().name
        store = LedgerStore(engine, world=world)
        moved, refused = [], []
        # 🔴 ONLY WHAT IS STILL READ IS RE-STAMPED (S-177 ①②). The stamp says which
        # declaration a source is translating on; a source that is retired or that the
        # loader refused translates nothing and is compiled with no material to
        # fingerprint at all - so asking for its stamp raises, and this loop has no
        # per-source guard, which would take every source AFTER it down too.
        for source in sorted(name for name, plan in setup.snapshot.source_plans.items()
                             if plan.runs):
            read = store.connection()
            try:
                existing = store.read_cursor(read, source)
            finally:
                read.close()
            wanted = cursor_translator_version(setup.snapshot, source)
            stored = existing.get("translator_ver") if existing else None
            verdict, reason = store.restamp_decision(stored, wanted)
            if verdict == "refused":
                refused.append(f"{source} ({world}) ({reason})")
                continue
            if verdict != "restamp":
                continue
            if store.restamp_cursor(source, expect=stored, translator_ver=wanted):
                # 🔴 TWO KINDS MOVE ON ONE DEPLOY (총괄 10-07): a source whose translator now
                # registers bound attributes has rows read before this boot carrying none of
                # them - a rescope covers those - while any other source is a re-stamp only.
                plan = setup.snapshot.source_plans[source]
                registers = sorted({
                    str(mapping.bindings[role].get("entity_type")).split("@")[0]
                    for mapping in plan.profile.mappings.values()
                    for role in mapping.registered_roles})
                moved.append(f"{source} ({world}): {stored} -> {wanted} "
                             f"(position stays {existing.get('cursor_value')!r})"
                             + (f" - the translator registers the bound attributes of "
                                f"{', '.join(registers)}: rows read before carry none of them "
                                f"until this source is rescoped whole" if registers else ""))
            else:
                refused.append(f"{source} ({world}) (row changed under us)")
        if moved:
            logger.info("[Ledger] re-stamped %d cursor(s) whose declaration did not "
                        "change: %s", len(moved), " | ".join(moved))
        if refused:
            logger.warning("[Ledger] %d cursor(s) were NOT re-stamped: %s",
                           len(refused), " | ".join(refused))
    finally:
        db.close()


async def start_ledger_worker(db_session_factory):
    """The ledger process (`run_ledger_worker.py`), or its half of a server run alone (`main.py`): the schema and the
    cursors' fingerprints, the ledger's index line beside, the follow-up and the census, and a beat carrying the
    follow-up's note. Never returns."""
    from database import models

    # Before the first beat - from then on the beat is this process's own. Two would follow every event twice: the
    # chain worker's guard kept the ledger's loops single while they lived inside it.
    other = heartbeat.another_process_beats(LEDGER_BEAT)
    if other:
        logger.warning("[Ledger Worker] NOT starting: another ledger process is already running (%s). Two follow "
                       "every event twice. If this is the process you meant to run, stop the other one first.", other)
        return
    heartbeat.beat(LEDGER_BEAT, note="starting", force=True, state="starting")
    # 🔴 BEFORE ANY LEDGER LOOP STARTS (S-88). Both loops below write to the ledger.
    try:
        await asyncio.to_thread(_ensure_ledger_schema_sync, db_session_factory)
    except Exception as exc:
        logger.error("[Ledger] the ledger schema could not be ensured, so a column that "
                     "landed in code may be missing here: %s", told(exc), exc_info=exc)
    # 🔴 S-87 — AFTER THE SCHEMA ENSURE AND BEFORE ANY LOOP READS A CURSOR. The ensure above may
    # have added the very column this reads, and both loops below refuse to run against a cursor
    # whose fingerprint does not match.
    try:
        await asyncio.to_thread(_restamp_moved_fingerprints_sync, db_session_factory)
    except Exception as exc:
        logger.error("[Ledger] cursor fingerprints could not be re-stamped, so a source "
                     "whose declaration did not change may still refuse to run: %s", told(exc), exc_info=exc)
    # The partitions' build waits on the database's older transactions - beside the loops, on a thread. Their
    # autoanalyze setting first, on the same line, so its ALTER and a CONCURRENTLY build never wait on each other.
    async def index_line():
        await asyncio.to_thread(_set_partitions_autoanalyze_sync, db_session_factory)
        await asyncio.to_thread(models.ensure_model_indexes_sync, db_session_factory, ("ledger",), logger.warning)
    asyncio.create_task(index_line())
    asyncio.create_task(run_ledger_followup(db_session_factory))
    # 🔴 ITS OWN LOOP, NOT A BRANCH OF THE FOLLOW-UP'S IDLE ARM. Two jobs sharing one
    # loop share one pace, and these two want opposite ones: the follow-up is latency
    # (a row is waiting), the census is politeness (nothing waits for it).
    asyncio.create_task(run_ledger_row_census(db_session_factory))
    logger.info("[Ledger] started - the follow-up, the census and the ledger's index line")
    while True:
        heartbeat.beat(LEDGER_BEAT, note=ledger_followup.note())
        await asyncio.sleep(heartbeat.HEARTBEAT_SLICE_SECONDS)
