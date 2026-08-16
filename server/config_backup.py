"""Weekly snapshots of ``server/config/``, and the check that says one is missing.

WHY THIS EXISTS
---------------
``server/config/`` is gitignored on purpose (see PRODUCTION_READINESS C3), so
``git`` is not a restore path for it. The rollback procedure's step 2 is "copy the
config back from a backup" -- and until this module existed, the only backups in
that directory were the ones ``install_product_tables.py`` writes. Those are an
**install history, not a deploy history**: they appear only when that script runs,
so a hand edit through the admin UI or an editor leaves no backup at all.

This takes a snapshot of every config file on a weekly cadence, so that step 2 has
an origin regardless of who edited what.

STORAGE: ``server/config/backup/``
------------------------------------
The live config directory is an operator surface, not a history listing. Only
active ``*.json`` files and runtime status files belong at its top level.
Weekly snapshots, one-off change backups and rollback evidence all live under
``backup/``; their established filenames distinguish their roles. Tracked
templates live separately under ``sample/``.

Legacy snapshots left directly under ``server/config`` or the retired
``_archive/weekly`` remain readable so an upgrade never makes the previous
recovery history disappear. New snapshots are always written to ``backup/``.

NAMING: ``table_config_260728.json.bak``
----------------------------------------
The date sits **before** the extension. ``install_product_tables.py`` writes
``table_config.json.bak.20260727-225922`` -- date **after**. The two are therefore
distinguishable in a plain ``ls`` without opening anything, which is the whole
point: the B4 drill's finding was that an operator mid-rollback cannot tell one
``.bak`` from another and picks wrong under pressure.

Ordering is carried by the filename, not by ``mtime``. ``yymmdd`` sorts
lexicographically into chronological order, so ``ls`` alone answers "which is the
newest". This module reads that same signal -- it never sorts by ``mtime`` -- so
the operator and the code can never disagree about which snapshot is current.
Copies are made with ``shutil.copy`` rather than ``copy2`` for the same reason: the
snapshot's mtime is when the snapshot was taken, so ``ls -lt`` and ``ls`` agree.

**One snapshot per config file, not one combined archive.** Restoring a combined
archive would discard legitimate edits made to the *other* configs since the
snapshot; per-file lets an operator restore only the one they broke.

TWO SNAPSHOTS ON ONE DAY
------------------------
``yymmdd`` has no time component, so a second snapshot on the same day would
collide -- and a manual snapshot before a risky change is exactly when someone
takes one. Overwriting silently is not an option, so:

  * identical content -> **skipped**, and logged as skipped. Nothing is lost,
    because the existing file already is that content.
  * different content -> a letter is appended: ``..._260728b.json.bak``, then
    ``c``, ``d``. ``'.'`` (0x2E) sorts before ``'b'`` (0x62) and ``260728b`` still
    sorts before ``260729``, so chronological order survives.

RETENTION: ONE MONTH, FIFO
--------------------------
Weekly forever grows without bound on a machine nobody is watching. The window is
one month (``RETENTION_DAYS``), which is how far back a rollback can plausibly
need to reach: a deploy older than that has had its config edited by normal site
work many times over, and restoring it wholesale would revert those edits too.

The prune is by **age**, with a floor of ``RETENTION_MIN_KEEP`` newest kept
whatever their age. Without the floor, a job that stopped for two months and then
resumed would delete every snapshot it had -- all of them older than the window --
leaving one file, at the exact moment the history mattered most. Every removal is
logged with the filename.

WHAT IS SNAPSHOTTED
-------------------
Every ``*.json`` directly in the config directory, minus ``RUNTIME_FILES``.

Requiring the name to end in exactly ``.json`` is what keeps this from feeding on
itself: the product-owned tracked templates are in the ``sample/`` directory,
while ``.bak.<ts>``, ``.bak-<ts>`` and this module's own ``.json.bak`` output are
all in ``backup/``. None can be selected as a top-level active ``*.json``. A
config file added later is picked up automatically -- for a backup tool,
over-capturing config is the safe direction.

CADENCE IS DERIVED FROM THE FILES, NOT FROM A CRON INSTANT
----------------------------------------------------------
``due()`` asks "is the newest snapshot older than ``INTERVAL_DAYS``", not "is it
Sunday 03:00". A cron instant is missed outright when the machine is off at that
moment, and a weekly job that skips a week because of a reboot is exactly the
silent failure this is supposed to prevent. Deriving the cadence from what is on
disk makes the job self-healing: whenever the scheduler is running and a week has
passed, the snapshot happens. It also survives a scheduler restart without
duplicating or losing a cycle, because no state is held in memory.
"""
import os
import re
import shutil
import logging
from datetime import datetime, timedelta

try:
    import paths as _paths
except ImportError:  # imported without server/ on sys.path
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import paths as _paths

logger = logging.getLogger("ConfigBackup")

# Snapshot cadence, in days. See the module docstring: this is compared against
# the newest snapshot on disk, not against a wall-clock schedule.
INTERVAL_DAYS = 7

# How old the newest snapshot may get before it is reported as a problem. A
# healthy weekly job is checked into place within INTERVAL_DAYS; the extra days
# absorb a machine that was off over a weekend without crying wolf.
STALE_AFTER_DAYS = 10

# Retention window and the floor that protects the history from a long outage.
RETENTION_DAYS = 31
RETENTION_MIN_KEEP = 4

# How often the scheduler re-asks whether a snapshot is due. The check is a
# listdir, so this is about avoiding pointless churn on a 5 s tick, not about cost.
CHECK_INTERVAL_SEC = 1800.0

# Written by running processes, not edited by anyone. Restoring one would push
# stale process state back into a live system, and scheduler_status.json is
# rewritten on every scheduler tick, so snapshotting it captures noise.
RUNTIME_FILES = frozenset({
    "scheduler_status.json",
    "supervisor_status.json",
})

SUFFIX = ".json.bak"

BACKUP_DIRNAME = "backup"

# table_config_260728b.json.bak -> stem=table_config date=260728 seq=b
_SNAPSHOT_RE = re.compile(r"^(?P<stem>.+)_(?P<date>\d{6})(?P<seq>[b-z]?)\.json\.bak$")

_SEQ_LETTERS = "bcdefghijklmnopqrstuvwxyz"


def _config_dir(config_dir=None):
    return config_dir or _paths.CONFIG_DIR


def backup_dir(config_dir=None):
    return os.path.join(_config_dir(config_dir), BACKUP_DIRNAME)


def backup_dir_for(path):
    """Backup directory for a live or ``sample/`` config file."""
    directory = os.path.dirname(os.path.abspath(path))
    if os.path.basename(directory).lower() == "sample":
        directory = os.path.dirname(directory)
    return backup_dir(directory)


def snapshot_path(filename, config_dir=None):
    """Resolve a weekly snapshot, preferring ``backup/`` over legacy locations."""
    root = _config_dir(config_dir)
    for directory in (
            backup_dir(root),
            os.path.join(root, "_archive", "weekly"),
            root):
        candidate = os.path.join(directory, filename)
        if os.path.isfile(candidate):
            return candidate
    return os.path.join(backup_dir(root), filename)


def snapshot_name(source_filename, when, seq=""):
    """``table_config.json`` + 2026-07-28 -> ``table_config_260728.json.bak``."""
    stem = source_filename[:-len(".json")]
    return "{}_{}{}{}".format(stem, when.strftime("%y%m%d"), seq, SUFFIX)


def source_files(config_dir=None):
    """Config files eligible for snapshotting, sorted."""
    d = _config_dir(config_dir)
    if not os.path.isdir(d):
        return []
    out = []
    for name in sorted(os.listdir(d)):
        if not name.endswith(".json"):
            # Also excludes .sample, .bak.<ts> and this module's own .json.bak.
            continue
        if name in RUNTIME_FILES:
            continue
        if os.path.isfile(os.path.join(d, name)):
            out.append(name)
    return out


def _parse(name):
    """Snapshot filename -> ``(stem, date, seq, name)``, or None if not one of ours."""
    m = _SNAPSHOT_RE.match(name)
    if not m:
        return None
    raw = m.group("date")
    try:
        when = datetime.strptime(raw, "%y%m%d")
    except ValueError:
        return None
    return (m.group("stem"), when, m.group("seq"), name)


def list_snapshots(config_dir=None):
    """``{stem: [(date, seq, filename), ...]}``, each list oldest -> newest.

    Ordered by the date and sequence letter *in the name*. Never by mtime -- see
    the module docstring.
    """
    root = _config_dir(config_dir)
    if not os.path.isdir(root):
        return {}
    grouped = {}
    seen = set()
    # New path first; the two older locations remain readable during upgrades.
    for directory in (
            backup_dir(root),
            os.path.join(root, "_archive", "weekly"),
            root):
        if not os.path.isdir(directory):
            continue
        for name in os.listdir(directory):
            if name in seen:
                continue
            parsed = _parse(name)
            if not parsed:
                continue
            seen.add(name)
            stem, when, seq, fname = parsed
            grouped.setdefault(stem, []).append((when, seq, fname))
    for stem in grouped:
        grouped[stem].sort(key=lambda t: (t[0], t[1]))
    return grouped


def newest(config_dir=None):
    """The newest snapshot across all config files: ``(date, filename)`` or None.

    Freshness is a property of the whole set, because ``take_snapshot`` writes
    every eligible file in one pass -- if one is current they all are.
    """
    best = None
    for entries in list_snapshots(config_dir).values():
        when, seq, fname = entries[-1]
        if best is None or when > best[0]:
            best = (when, fname)
    return best


def _same_bytes(a, b):
    try:
        if os.path.getsize(a) != os.path.getsize(b):
            return False
        with open(a, "rb") as fa, open(b, "rb") as fb:
            return fa.read() == fb.read()
    except OSError:
        return False


def _prune(entries, config_dir, now):
    """Drop snapshots outside the retention window, keeping the floor. Returns names."""
    removed = []
    cutoff = now - timedelta(days=RETENTION_DAYS)
    # entries is oldest -> newest; everything but the newest RETENTION_MIN_KEEP is
    # a prune candidate, and of those only the ones outside the window go.
    candidates = entries[:-RETENTION_MIN_KEEP] if RETENTION_MIN_KEEP else list(entries)
    for when, seq, fname in candidates:
        if when >= cutoff:
            continue
        try:
            os.remove(snapshot_path(fname, config_dir))
            removed.append(fname)
            logger.info(
                "[ConfigBackup] pruned '%s' (%d days old; retention window is %d "
                "days, and the newest %d are kept whatever their age)",
                fname, (now - when).days, RETENTION_DAYS, RETENTION_MIN_KEEP)
        except OSError as e:
            logger.warning("[ConfigBackup] could not prune '%s': %s", fname, e)
    return removed


def take_snapshot(config_dir=None, now=None):
    """Snapshot every eligible config file. Returns a result dict.

    ``{"created": [...], "skipped": [...], "pruned": [...], "errors": [...]}``

    Safe to call more often than the cadence: a same-day call whose content has
    not changed creates nothing.
    """
    d = _config_dir(config_dir)
    snapshots = backup_dir(d)
    now = now or datetime.now()
    result = {"created": [], "skipped": [], "pruned": [], "errors": [],
              "config_dir": d, "snapshot_dir": snapshots,
              "taken_at": now.strftime("%Y-%m-%d %H:%M:%S")}

    if not os.path.isdir(d):
        result["errors"].append("config directory does not exist: %s" % d)
        return result

    try:
        os.makedirs(snapshots, exist_ok=True)
    except OSError as e:
        result["errors"].append(
            "cannot create snapshot directory %s: %s" % (snapshots, e))
        return result

    grouped = list_snapshots(d)
    for name in source_files(d):
        src = os.path.join(d, name)
        stem = name[:-len(".json")]
        today = [e for e in grouped.get(stem, []) if e[0].date() == now.date()]

        # Same day already covered by an identical snapshot -> nothing to do.
        if today and _same_bytes(src, snapshot_path(today[-1][2], d)):
            result["skipped"].append(today[-1][2])
            continue

        seq = ""
        if today:
            used = {e[1] for e in today}
            seq = next((c for c in _SEQ_LETTERS if c not in used), None)
            if seq is None:
                result["errors"].append(
                    "%s: 26 differing snapshots already exist for today; refusing "
                    "to overwrite one" % name)
                continue

        dest_name = snapshot_name(name, now, seq)
        dest = os.path.join(snapshots, dest_name)
        tmp = dest + ".tmp"
        try:
            # copy, not copy2: the snapshot's mtime should be when it was taken,
            # so `ls -lt` and the date in the name never contradict each other.
            shutil.copy(src, tmp)
            os.replace(tmp, dest)
            result["created"].append(dest_name)
            logger.info("[ConfigBackup] wrote '%s'", dest_name)
        except OSError as e:
            result["errors"].append("%s: %s" % (name, e))
            logger.error("[ConfigBackup] failed to snapshot '%s': %s", name, e)
            try:
                os.remove(tmp)
            except OSError:
                pass

    # Prune after writing, so a failed write can never leave the set below the floor.
    for entries in list_snapshots(d).values():
        result["pruned"].extend(_prune(entries, d, now))

    return result


def due(config_dir=None, now=None):
    """True when no snapshot exists, or the newest is older than ``INTERVAL_DAYS``."""
    now = now or datetime.now()
    best = newest(config_dir)
    if best is None:
        return True
    return (now - best[0]).days >= INTERVAL_DAYS


def probe(config_dir=None, now=None):
    """Freshness of the config backups, for ``/health`` and for the CLI.

    ``{"status": "ok"|"stale"|"missing"|"unknown", ...}``

    This reads the **files on disk**, never a "last run" field written by the job.
    A job that stopped three weeks ago would still be reporting its last success;
    the absence of a recent file is the only signal that cannot lie about itself.
    """
    now = now or datetime.now()
    d = _config_dir(config_dir)
    out = {"config_dir": d,
           "snapshot_dir": backup_dir(d),
           "interval_days": INTERVAL_DAYS,
           "stale_after_days": STALE_AFTER_DAYS}
    try:
        snapshots = list_snapshots(d)
        best = newest(d)
    except OSError as e:
        out["status"] = "unknown"
        out["error"] = str(e)
        return out

    out["files"] = sum(len(v) for v in snapshots.values())
    out["configs_covered"] = len(snapshots)
    if best is None:
        out["status"] = "missing"
        out["detail"] = ("no config snapshot has ever been taken; a rollback "
                         "would have nothing to restore from")
        return out

    when, fname = best
    age = (now - when).days
    out["newest"] = fname
    out["newest_date"] = when.strftime("%Y-%m-%d")
    out["age_days"] = age
    if age > STALE_AFTER_DAYS:
        out["status"] = "stale"
        out["detail"] = ("newest config snapshot is %d days old (%s); the weekly "
                         "job has not run" % (age, fname))
    else:
        out["status"] = "ok"
    return out


def run_scheduled(config_dir=None, now=None):
    """One maintenance cycle: snapshot if due, then report freshness.

    This is what the auto-update scheduler process calls. It logs rather than
    raising, because a backup failure must not take a daemon down -- the failure
    surfaces through ``probe()`` (and therefore ``/health``) instead, which is the
    signal that stays true even if this function is never called again.
    """
    now = now or datetime.now()
    out = {"snapshot": None}
    try:
        if due(config_dir, now):
            out["snapshot"] = take_snapshot(config_dir, now)
            snap = out["snapshot"]
            logger.info(
                "[ConfigBackup] weekly snapshot: %d written, %d unchanged, %d pruned",
                len(snap["created"]), len(snap["skipped"]), len(snap["pruned"]))
            for err in snap["errors"]:
                logger.error("[ConfigBackup] %s", err)
    except Exception as e:  # never take the daemon down
        logger.error("[ConfigBackup] snapshot cycle failed: %s", e)
        out["error"] = str(e)

    status = probe(config_dir, now)
    out["probe"] = status
    if status.get("status") == "missing":
        logger.error("[ConfigBackup] %s", status.get("detail"))
    elif status.get("status") == "stale":
        logger.error("[ConfigBackup] %s", status.get("detail"))
    return out
