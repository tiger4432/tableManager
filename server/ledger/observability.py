"""Heartbeat note and lag report - birth conditions, not follow-ups.

WHY LAG IS HERE ON DAY ONE
---------------------------
`LEDGER_SLICE_1_BRIEF` §4 names the precedent directly: the existing graph worker cannot
report how far behind its cursor is, and it earned a defect ruling for "뒤처지는 동안에도
신선해 보이는" - looking fresh while falling behind. A liveness beat proves a loop is
turning; it says nothing about whether that loop is keeping up. `utils/heartbeat.py`'s
own docstring makes the same distinction for work claims. So this translator publishes
BOTH from the start.

THE REPORT HAS TWO TIERS, AND THAT IS A SCALE DECISION
-------------------------------------------------------
🔴 The obvious lag metric - "how many source rows are past my cursor" - is a COUNT over
the source table. `lot_event` carries no index on `event_time` and this lane may not add
one (§6: every existing table schema is untouched), so at ten million rows that count is
a sequential scan. A monitoring feature that costs a table scan will be turned off, and
then there is no lag report at all.

  * **Tier 1, always on, zero queries.** `world_time_lag_seconds` (now minus the world
    time the cursor has reached) and `cursor_age_seconds` (how long since the translator
    last committed anything). Both come from the cursor row the caller already has. A
    translator that stops advancing is visible in these two numbers alone, which is
    precisely the failure the graph worker could not show.
  * **Tier 2, throttled, one query.** The real source head and the row count behind it,
    at most once per `lag.probe_interval_seconds`. This is the number that separates "the
    source is quiet" from "I am behind", and it is worth a query at that rate.

Tier 1 cannot answer "is the source quiet or am I stuck?" on its own. Saying so here is
the point - an instrument that hides its own blind spot is worse than one that names it.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from . import gate

#: Process-local throttle for the tier-2 probe: `{source: monotonic seconds}`.
_last_probe = {}


def note(extra=None):
    """The string that goes into `heartbeat.beat(..., note=...)`, or `None` when quiet.

    `None` on a healthy translator is deliberate and matches `chain_key_gate.note()`:
    a clean deployment's heartbeat stays byte-identical to an idle one, so a line
    APPEARING is itself the alarm.
    """
    parts = [p for p in (gate.note(), extra) if p]
    return " || ".join(parts) if parts else None


def lag_note(lag: dict):
    """A one-line digest of `lag_report`, for the heartbeat. Never `None`.

    Unlike the refusal note this is always emitted: "I am zero behind" is information an
    operator needs to see, because its ABSENCE is what the graph worker's defect looked
    like.
    """
    if not lag:
        return None
    pieces = [f"cursor={lag.get('cursor_position') or '<none>'}"]
    basis = lag.get("lag_basis")
    if basis == LAG_BASIS_ARRIVAL_WATERMARK:
        # Named differently on purpose - see `lag_report_keyset`. Printing an arrival lag
        # under the world-time label is how a two-month-old scan reads as a two-month-old
        # translator.
        pieces.append(f"wm_age={_fmt_seconds(lag.get('watermark_age_seconds'))}")
    elif basis == LAG_BASIS_GROUP_ORDER:
        # No time field AT ALL, and that is the point of the third basis: this cursor
        # moves in name order, so any duration printed beside it would be read as
        # progress through time and would not be.
        pieces.append("basis=group_order")
    else:
        pieces.append(f"world_lag={_fmt_seconds(lag.get('world_time_lag_seconds'))}")
    pieces.append(f"cursor_age={_fmt_seconds(lag.get('cursor_age_seconds'))}")
    unit, behind = ("groups_behind", lag.get("groups_behind")) \
        if basis == LAG_BASIS_GROUP_ORDER else ("rows_behind", lag.get("rows_behind"))
    if behind is not None:
        pieces.append(f"{unit}={behind}")
        pieces.append(f"head={lag.get('source_head') or '<none>'}")
    else:
        pieces.append(f"{unit}=? (last probed "
                      f"{_fmt_seconds(lag.get('head_probe_age_seconds'))} ago)")
    return "ledger lag[" + ", ".join(pieces) + "]"


def _fmt_seconds(value):
    if value is None:
        return "?"
    value = float(value)
    if value < 90:
        return f"{value:.0f}s"
    if value < 5400:
        return f"{value / 60:.0f}m"
    if value < 172800:
        return f"{value / 3600:.1f}h"
    return f"{value / 86400:.1f}d"


def lag_report(store, source, source_cfg, cursor_row, probe_interval=60, now=None,
               force_probe=False):
    """Tier 1 always; tier 2 when the throttle allows. Returns a dict, never raises.

    `probe_allowed` is reported alongside the numbers so a reader can tell "not behind"
    from "not asked" - collapsing those two into one absent field is how a lag report
    starts lying by omission.
    """
    now = now or datetime.now(timezone.utc)
    report = {
        "source": source,
        "cursor_position": None,
        "world_time_lag_seconds": None,
        "cursor_age_seconds": None,
        "source_head": None,
        "rows_behind": None,
        "head_probe_age_seconds": None,
        "probe_allowed": False,
    }
    if cursor_row is None:
        # Never translated. That is unambiguously "infinitely behind", and reporting it
        # as zero lag would be the graph worker's defect reproduced on day one.
        report["never_started"] = True
        return report

    position = (cursor_row.get("cursor_value") or {}).get("event_time")
    report["cursor_position"] = position
    if position:
        from .config import DEFAULT_OCCURRED_AT_FORMAT
        from .store import parse_occurred_at
        reached = parse_occurred_at(
            position, source_cfg.get("occurred_at_format", DEFAULT_OCCURRED_AT_FORMAT),
            source_cfg["occurred_at_timezone"])
        if reached is not None:
            report["world_time_lag_seconds"] = (now - reached).total_seconds()

    updated_at = cursor_row.get("updated_at")
    if isinstance(updated_at, datetime):
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        report["cursor_age_seconds"] = (now - updated_at).total_seconds()

    probed_at = cursor_row.get("head_probed_at")
    if isinstance(probed_at, datetime):
        if probed_at.tzinfo is None:
            probed_at = probed_at.replace(tzinfo=timezone.utc)
        report["head_probe_age_seconds"] = (now - probed_at).total_seconds()
    report["source_head"] = (cursor_row.get("source_head") or {}).get("event_time")

    last = _last_probe.get(source)
    allowed = force_probe or last is None or (time.monotonic() - last) >= probe_interval
    report["probe_allowed"] = bool(allowed)
    if not allowed:
        return report

    _last_probe[source] = time.monotonic()
    head, behind = probe_source_head(store, source, source_cfg, position)
    report["source_head"] = head
    report["rows_behind"] = behind
    report["head_probe_age_seconds"] = 0.0
    try:
        store.record_source_head(source, {"event_time": head, "rows_behind": behind})
    except Exception:                                            # pragma: no cover
        # A monitoring write must never take down the translator. `utils/heartbeat.py`
        # takes the same stance for the same reason.
        pass
    return report


#: What a lag number is measured against. SERVED, never inferred: the two drivers measure
#: DIFFERENT things and a reader who cannot tell them apart would compare a world-time lag
#: with an arrival-order one and conclude the translator had fallen behind by months.
LAG_BASIS_WORLD_TIME = "world_time"
LAG_BASIS_ARRIVAL_WATERMARK = "arrival_watermark"
#: 🔴 THE THIRD YARDSTICK, AND IT IS NEITHER OF THE OTHER TWO. A transfer source's cursor
#: is a GROUP KEY (`dt_job`), and group keys are ordered by name, not by time and not by
#: arrival. So "how far behind am I" is answerable only in GROUPS, and reporting it under
#: either of the fields above would be a number that reads like time and is not. Measured
#: on `assy_manager` 2026-08-14: `dt_job` name order and `event_time` order disagree - the
#: `DT-EQP-*` family sorts first and is the OLDEST (May), while `SYN-*` sorts last and is
#: the NEWEST (August), so a world-time lag taken from this cursor would swing by three
#: months depending on which letter the next job name starts with.
LAG_BASIS_GROUP_ORDER = "group_order"


def lag_report_keyset(store, source, source_cfg, cursor_row, probe_interval=60,
                      now=None, force_probe=False):
    """The observation driver's lag report. Same two tiers, a different yardstick.

    🔴 IT DOES NOT REPORT A WORLD-TIME LAG, AND THAT IS THE HONEST ANSWER RATHER THAN A
    GAP. An observation source's cursor is a KEYSET over `(updated_at, row_id)` - arrival
    order - because its world time is not on the row at all (it belongs to the inspection
    run). "How far behind in world time am I" is therefore unanswerable from the cursor:
    a scan performed in May can be loaded today and would sit at the HEAD of this cursor.
    So `world_time_lag_seconds` stays `None`, `lag_basis` says which yardstick was used,
    and `watermark_age_seconds` answers the question this cursor CAN answer - how old the
    newest row I have translated is, in the ingester's clock.

    Reporting the arrival lag under the world-time field would have been the easy version,
    and it is the one that tells an operator a two-month-old scan means a two-month-behind
    translator.
    """
    now = now or datetime.now(timezone.utc)
    report = {
        "source": source,
        "lag_basis": LAG_BASIS_ARRIVAL_WATERMARK,
        "cursor_position": None,
        "world_time_lag_seconds": None,
        "watermark_age_seconds": None,
        "cursor_age_seconds": None,
        "source_head": None,
        "rows_behind": None,
        "head_probe_age_seconds": None,
        "probe_allowed": False,
    }
    if cursor_row is None:
        report["never_started"] = True
        return report

    watermark = (cursor_row.get("cursor_value") or {}).get("watermark") or []
    report["cursor_position"] = "/".join(str(v) for v in watermark) or None
    if watermark:
        reached = _as_datetime(watermark[0])
        if reached is not None:
            report["watermark_age_seconds"] = (now - reached).total_seconds()

    updated_at = cursor_row.get("updated_at")
    if isinstance(updated_at, datetime):
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        report["cursor_age_seconds"] = (now - updated_at).total_seconds()

    probed_at = cursor_row.get("head_probed_at")
    if isinstance(probed_at, datetime):
        if probed_at.tzinfo is None:
            probed_at = probed_at.replace(tzinfo=timezone.utc)
        report["head_probe_age_seconds"] = (now - probed_at).total_seconds()
    head = (cursor_row.get("source_head") or {}).get("watermark")
    report["source_head"] = "/".join(str(v) for v in head) if head else None

    last = _last_probe.get(source)
    allowed = force_probe or last is None or (time.monotonic() - last) >= probe_interval
    report["probe_allowed"] = bool(allowed)
    if not allowed:
        return report

    _last_probe[source] = time.monotonic()
    head_values, behind = probe_keyset_head(store, source, source_cfg, watermark)
    report["source_head"] = "/".join(str(v) for v in head_values) if head_values else None
    report["rows_behind"] = behind
    report["head_probe_age_seconds"] = 0.0
    try:
        store.record_source_head(source, {"watermark": [str(v) for v in head_values],
                                          "rows_behind": behind})
    except Exception:                                            # pragma: no cover
        pass
    return report


def lag_report_group(store, source, source_cfg, cursor_row, probe_interval=60,
                     now=None, force_probe=False):
    """The transfer driver's lag report. Same two tiers, a third yardstick.

    🔴 `world_time_lag_seconds` STAYS `None` EVEN THOUGH THIS SOURCE HAS A WORLD TIME, and
    that is the honest answer rather than a gap. `dt_log` carries `event_time`, so the
    temptation is to report the last translated group's timestamp as a lag. It would be
    wrong: the cursor advances in GROUP NAME order, so the group the cursor sits on is not
    the newest one translated - it is merely the alphabetically last. A translator that had
    finished every August job and no May one would report itself three months behind, and
    one that had done the reverse would report itself current while most of the source was
    untranslated.

    What this cursor CAN answer is `groups_behind`, and that is what it answers.
    """
    now = now or datetime.now(timezone.utc)
    report = {
        "source": source,
        "lag_basis": LAG_BASIS_GROUP_ORDER,
        "cursor_position": None,
        "world_time_lag_seconds": None,
        "cursor_age_seconds": None,
        "source_head": None,
        "groups_behind": None,
        "head_probe_age_seconds": None,
        "probe_allowed": False,
    }
    if cursor_row is None:
        report["never_started"] = True
        return report

    position = (cursor_row.get("cursor_value") or {}).get("group_key")
    report["cursor_position"] = position

    updated_at = cursor_row.get("updated_at")
    if isinstance(updated_at, datetime):
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        report["cursor_age_seconds"] = (now - updated_at).total_seconds()

    probed_at = cursor_row.get("head_probed_at")
    if isinstance(probed_at, datetime):
        if probed_at.tzinfo is None:
            probed_at = probed_at.replace(tzinfo=timezone.utc)
        report["head_probe_age_seconds"] = (now - probed_at).total_seconds()
    report["source_head"] = (cursor_row.get("source_head") or {}).get("group_key")

    last = _last_probe.get(source)
    allowed = force_probe or last is None or (time.monotonic() - last) >= probe_interval
    report["probe_allowed"] = bool(allowed)
    if not allowed:
        return report

    _last_probe[source] = time.monotonic()
    head, behind = probe_group_head(store, source, source_cfg, position)
    report["source_head"] = head
    report["groups_behind"] = behind
    report["head_probe_age_seconds"] = 0.0
    try:
        store.record_source_head(source, {"group_key": None if head is None else str(head),
                                          "groups_behind": behind})
    except Exception:                                            # pragma: no cover
        pass
    return report


def probe_group_head(store, source, source_cfg, position):
    """`(head_group_key, groups_behind)` for a group cursor. Two statements, one scan each.

    🔴 `groups_behind` COUNTS DISTINCT GROUPS, NOT ROWS. A transfer molecule is a group, so
    rows-behind would answer a question nobody asked and would be off by the group size -
    on `dt_log` that is a factor of up to 150.
    """
    group_column = (source_cfg.get("group") or {}).get("column")
    if not group_column:
        return None, None
    connection = store.connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT max({group_column}) FROM {source}")
            head = (cursor.fetchone() or [None])[0]
            if position:
                cursor.execute(
                    f"SELECT count(DISTINCT {group_column}) FROM {source} "
                    f"WHERE {group_column} > %s", (position,))
            else:
                cursor.execute(f"SELECT count(DISTINCT {group_column}) FROM {source}")
            behind = cursor.fetchone()[0]
        return head, int(behind or 0)
    finally:
        connection.close()


def _as_datetime(value):
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def probe_keyset_head(store, source, source_cfg, watermark):
    """`(head_watermark, rows_behind)` for a keyset cursor. One statement.

    The `count(*) FILTER` uses the SAME row-value comparison the page fetch uses, so the
    declared watermark index serves both. That is why the watermark is declared rather
    than assumed: an index-less keyset would turn this probe into the sequential scan the
    tier split exists to avoid.
    """
    columns = list((source_cfg.get("watermark") or {}).get("columns") or ())
    if not columns:
        return None, None
    ordered = ", ".join(columns)
    descending = ", ".join(f"{c} DESC" for c in columns)
    connection = store.connection()
    try:
        with connection.cursor() as cursor:
            # 🔴 THE HEAD IS THE LAST ROW IN KEYSET ORDER, NOT `max()` PER COLUMN.
            # `(max(updated_at), max(row_id))` is a tuple that need not exist in the
            # table: the newest row and the largest identity are usually different rows,
            # and a cursor advanced to that fabricated pair would SKIP everything between
            # them. `ORDER BY … DESC LIMIT 1` walks the declared index backwards by one.
            cursor.execute(f"SELECT {ordered} FROM {source} "
                           f"ORDER BY {descending} LIMIT 1")
            head = cursor.fetchone()
            if watermark and len(watermark) == len(columns):
                placeholders = ", ".join(["%s"] * len(columns))
                cursor.execute(
                    f"SELECT count(*) FROM {source} "
                    f"WHERE ({ordered}) > ({placeholders})", tuple(watermark))
            else:
                cursor.execute(f"SELECT count(*) FROM {source}")
            behind = cursor.fetchone()[0]
        return (list(head) if head else None), int(behind or 0)
    finally:
        connection.close()


def probe_source_head(store, source, source_cfg, position):
    """`(head_event_time, rows_behind)` - the tier-2 query. One statement.

    Both numbers come from ONE scan, because two statements would be two scans of a
    table this lane is not allowed to index.
    """
    time_column = source_cfg["occurred_at_column"]
    connection = store.connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT max({time_column}), "
                f"       count(*) FILTER (WHERE {time_column} > %s) "
                f"FROM {source}",
                (position or "",))
            head, behind = cursor.fetchone()
        return head, int(behind or 0)
    finally:
        connection.close()


def reset_probe_throttle():
    """Tests only - so a test can prove the throttle both blocks and releases."""
    _last_probe.clear()
