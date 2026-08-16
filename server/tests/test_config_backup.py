"""C3 - the weekly config snapshot, and the check that says one is missing.

The failures this exists to prevent, in order of how badly they bite:

* **A backup nobody can pick out of a lineup.** ``install_product_tables.py``
  already writes ``table_config.json.bak.<ts>``. If the weekly snapshot were
  named indistinguishably, an operator mid-rollback would have to guess which
  kind they were looking at - and the two mean completely different things (an
  install history vs. a deploy history). ``test_naming_is_distinguishable_*``
  fails if the two forms ever converge.
* **A backup that eats itself.** The snapshots live in the directory they are
  snapshotting. ``test_snapshots_are_not_themselves_snapshotted`` fails if the
  source filter ever stops excluding them, which would grow the directory
  quadratically.
* **A job that stopped and said nothing.** ``probe()`` reads the files, never a
  "last run" field the job wrote about itself, so it stays true precisely when
  the job is dead. ``test_health_reports_a_stale_backup`` is the wiring that
  carries that to an operator.
* **A prune that deletes the history it was protecting.** A job resuming after a
  two-month outage would find every snapshot outside the retention window.
  ``test_retention_floor_survives_a_long_outage`` fails if the floor is removed.
"""
import os
import sys
import json
import time
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config_backup
import health as health_mod


NOW = datetime(2026, 7, 28, 3, 0, 0)


def write(d, name, content):
    p = os.path.join(str(d), name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)
    return p


def backup_dir(d):
    path = config_backup.backup_dir(str(d))
    os.makedirs(path, exist_ok=True)
    return path


def backup_names(d):
    path = backup_dir(d)
    return sorted(os.listdir(path))


@pytest.fixture
def cfg(tmp_path):
    """A config directory shaped like the real one, mess included."""
    d = tmp_path / "config"
    d.mkdir()
    write(d, "table_config.json", json.dumps({"t": {"columns": ["a"]}}))
    write(d, "transfer_plan_config.json", json.dumps({"stages": []}))
    write(d, "maps.json", json.dumps({"m": 1}))
    # Product-owned, tracked in git - recoverable without a backup.
    sample = d / "sample"
    sample.mkdir()
    write(sample, "table_config.json.sample", "{}")
    # The install script's backups: an install history, not a deploy history.
    history = backup_dir(d)
    write(history, "table_config.json.bak.20260727-225922", "{}")
    write(history, "transfer_plan_config.json.bak-20260727_004642", "{}")
    write(history, "ontology_mapping.json.v1.bak", "{}")
    # Written by running processes, not edited by anyone.
    write(d, "scheduler_status.json", json.dumps({"collectors": []}))
    write(d, "supervisor_status.json", json.dumps({"children": {}}))
    return str(d)


# --------------------------------------------------------------------- naming
def test_snapshot_name_puts_the_date_before_the_extension(cfg):
    assert (config_backup.snapshot_name("table_config.json", NOW)
            == "table_config_260728.json.bak")


def test_new_snapshots_leave_the_live_config_root_clean(cfg):
    config_backup.take_snapshot(cfg, NOW)
    assert backup_names(cfg)
    assert not [name for name in os.listdir(cfg) if config_backup._parse(name)]


def test_legacy_root_snapshot_remains_readable_during_migration(cfg):
    name = "table_config_260728.json.bak"
    legacy = write(cfg, name, "{}")
    assert config_backup.list_snapshots(cfg)["table_config"][0][2] == name
    assert config_backup.snapshot_path(name, cfg) == legacy


def test_naming_is_distinguishable_from_the_install_scripts(cfg):
    """The whole point: `ls` alone must separate the two kinds of .bak."""
    config_backup.take_snapshot(cfg, NOW)
    weekly = [n for n in backup_names(cfg) if config_backup._parse(n)]
    install = [n for n in backup_names(cfg)
               if ".json.bak." in n or ".json.bak-" in n]
    assert weekly, "no weekly snapshot was written"
    assert install, "fixture lost the install-script backups"
    # No filename can be read as both kinds.
    assert not (set(weekly) & set(install))
    # And the difference is where the date sits, which is visible without
    # opening anything: date-then-extension vs extension-then-date.
    assert all(n.endswith(".json.bak") for n in weekly)
    assert not any(n.endswith(".json.bak") for n in install)


def test_newest_is_obvious_from_lexicographic_order(cfg):
    """`ls` sorts these into chronological order, including the same-day letters."""
    names = ["table_config_260728.json.bak", "table_config_260728b.json.bak",
             "table_config_260729.json.bak", "table_config_260801.json.bak"]
    assert sorted(names) == names


# ------------------------------------------------------------ source selection
def test_only_real_config_is_snapshotted(cfg):
    assert config_backup.source_files(cfg) == [
        "maps.json", "table_config.json", "transfer_plan_config.json"]


def test_snapshots_are_not_themselves_snapshotted(cfg):
    """Two cycles must not produce backups of backups."""
    first = config_backup.take_snapshot(cfg, NOW)
    assert len(first["created"]) == 3

    later = NOW + timedelta(days=7)
    second = config_backup.take_snapshot(cfg, later)
    assert len(second["created"]) == 3
    assert all(config_backup._parse(n) for n in second["created"])
    # Nothing named after a .bak file was ever created.
    assert not [n for n in backup_names(cfg) if n.count(".bak") > 1]


def test_runtime_status_files_are_never_snapshotted(cfg):
    config_backup.take_snapshot(cfg, NOW)
    written = os.listdir(cfg)
    assert not [n for n in written if n.startswith("scheduler_status_")]
    assert not [n for n in written if n.startswith("supervisor_status_")]


def test_a_new_config_file_is_picked_up_automatically(cfg):
    write(cfg, "brand_new_config.json", "{}")
    config_backup.take_snapshot(cfg, NOW)
    assert os.path.exists(os.path.join(
        config_backup.backup_dir(cfg), "brand_new_config_260728.json.bak"))


# ------------------------------------------------------- two snapshots one day
def test_same_day_identical_content_is_skipped_not_duplicated(cfg):
    config_backup.take_snapshot(cfg, NOW)
    again = config_backup.take_snapshot(cfg, NOW + timedelta(hours=2))
    assert again["created"] == []
    assert "table_config_260728.json.bak" in again["skipped"]


def test_same_day_changed_content_gets_a_letter_and_never_overwrites(cfg):
    config_backup.take_snapshot(cfg, NOW)
    original = open(os.path.join(config_backup.backup_dir(cfg),
                                 "table_config_260728.json.bak"),
                    encoding="utf-8").read()

    write(cfg, "table_config.json", json.dumps({"t": {"columns": ["a", "b"]}}))
    second = config_backup.take_snapshot(cfg, NOW + timedelta(hours=2))

    assert "table_config_260728b.json.bak" in second["created"]
    # The first one is untouched - this is the "overwriting silently is not
    # acceptable" requirement.
    assert open(os.path.join(config_backup.backup_dir(cfg),
                             "table_config_260728.json.bak"),
                encoding="utf-8").read() == original

    write(cfg, "table_config.json", json.dumps({"t": {"columns": ["a", "b", "c"]}}))
    third = config_backup.take_snapshot(cfg, NOW + timedelta(hours=4))
    assert "table_config_260728c.json.bak" in third["created"]


# ------------------------------------------------------------------ retention
def seed_history(cfg, dates, stem="table_config"):
    for d in dates:
        write(backup_dir(cfg), f"{stem}_{d:%y%m%d}.json.bak",
              json.dumps({"as_of": f"{d:%Y-%m-%d}"}))


def test_retention_drops_what_is_older_than_a_month_fifo(cfg):
    # Weekly for ~3 months: the oldest must be displaced, newest kept.
    dates = [NOW - timedelta(days=7 * i) for i in range(12)]
    seed_history(cfg, dates)
    result = config_backup.take_snapshot(cfg, NOW)

    kept = sorted(n for n in backup_names(cfg)
                  if config_backup._parse(n)
                  and config_backup._parse(n)[0] == "table_config")
    ages = [(NOW - config_backup._parse(n)[1]).days for n in kept]
    assert max(ages) <= config_backup.RETENTION_DAYS, \
        f"kept a snapshot older than the retention window: {kept}"
    # FIFO: what went is the oldest, and it is reported, not silent.
    assert result["pruned"], "a prune happened but was not reported"
    assert all("table_config_" in n for n in result["pruned"])


def test_retention_floor_survives_a_long_outage(cfg):
    """Every snapshot is outside the window; the newest few must still survive."""
    dates = [NOW - timedelta(days=60 + 7 * i) for i in range(6)]
    seed_history(cfg, dates)
    # An empty config dir apart from the history, so nothing new is written for
    # this stem beyond today's snapshot.
    config_backup.take_snapshot(cfg, NOW)

    kept = [n for n in backup_names(cfg)
            if config_backup._parse(n)
            and config_backup._parse(n)[0] == "table_config"]
    assert len(kept) >= config_backup.RETENTION_MIN_KEEP, \
        ("the prune deleted the history it was protecting: only "
         f"{len(kept)} left of {len(dates)} plus today's")


def test_prune_reports_every_file_it_removed(cfg):
    seed_history(cfg, [NOW - timedelta(days=40 + 7 * i) for i in range(8)])
    result = config_backup.take_snapshot(cfg, NOW)
    for name in result["pruned"]:
        assert not os.path.exists(os.path.join(config_backup.backup_dir(cfg), name))


# -------------------------------------------------------------------- cadence
def test_due_is_derived_from_the_files_not_from_a_clock(cfg):
    assert config_backup.due(cfg, NOW) is True, "no snapshot at all must be due"

    config_backup.take_snapshot(cfg, NOW)
    assert config_backup.due(cfg, NOW + timedelta(days=6)) is False
    assert config_backup.due(cfg, NOW + timedelta(days=7)) is True


def test_a_missed_week_is_taken_at_the_next_opportunity(cfg):
    """The reason the cadence is not a cron instant: a machine that was off."""
    config_backup.take_snapshot(cfg, NOW)
    # Three weeks of downtime, then the scheduler starts.
    back_up = NOW + timedelta(days=21)
    assert config_backup.due(cfg, back_up) is True
    result = config_backup.run_scheduled(cfg, back_up)
    assert result["snapshot"]["created"]
    assert result["probe"]["status"] == "ok"


# ---------------------------------------------------------------------- probe
def test_probe_says_missing_when_nothing_was_ever_taken(cfg):
    status = config_backup.probe(cfg, NOW)
    assert status["status"] == "missing"
    assert "nothing to restore" in status["detail"]


def test_probe_says_ok_right_after_a_snapshot(cfg):
    config_backup.take_snapshot(cfg, NOW)
    status = config_backup.probe(cfg, NOW)
    assert status["status"] == "ok"
    assert status["newest"].endswith(".json.bak")
    assert status["configs_covered"] == 3


def test_probe_goes_stale_when_the_job_stops(cfg):
    config_backup.take_snapshot(cfg, NOW)
    fresh = config_backup.probe(cfg, NOW + timedelta(days=config_backup.STALE_AFTER_DAYS))
    assert fresh["status"] == "ok", "must not cry wolf inside the grace window"

    dead = config_backup.probe(cfg, NOW + timedelta(days=21))
    assert dead["status"] == "stale"
    assert dead["age_days"] == 21


def test_probe_ignores_the_install_scripts_backups(cfg):
    """A directory full of install backups is still a directory with no C3 backup."""
    status = config_backup.probe(cfg, NOW)
    assert status["status"] == "missing", \
        "install-script .bak files were counted as a config backup"


def test_probe_reads_names_not_mtimes(cfg):
    """An old snapshot touched today must not look fresh."""
    seed_history(cfg, [NOW - timedelta(days=30)])
    path = os.path.join(config_backup.backup_dir(cfg),
                        f"table_config_{(NOW - timedelta(days=30)):%y%m%d}.json.bak")
    os.utime(path, None)  # mtime = now
    status = config_backup.probe(cfg, NOW)
    assert status["status"] == "stale"
    assert status["age_days"] == 30


# -------------------------------------------------------- /health integration
def _health(backup):
    return health_mod.compute_health(
        db_result={"status": "ok", "latency_ms": 1.0},
        heartbeats={},
        supervisor_status=None,
        outbox_result={"pending": 0, "oldest_age_seconds": None},
        stale_after=60.0,
        backup_result=backup)


def test_health_reports_a_missing_backup_without_calling_the_stack_unhealthy(cfg):
    payload, code = _health(config_backup.probe(cfg, NOW))
    assert payload["status"] == health_mod.STATUS_DEGRADED
    # 200, not 503: a missing backup makes the NEXT incident worse, it does not
    # mean this stack is failing now. A 503 would tell a monitor to restart it.
    assert code == 200
    assert any("config backup" in p for p in payload["problems"])
    assert payload["checks"]["config_backup"]["status"] == "missing"


def test_health_reports_a_stale_backup(cfg):
    config_backup.take_snapshot(cfg, NOW)
    payload, code = _health(config_backup.probe(cfg, NOW + timedelta(days=30)))
    assert payload["status"] == health_mod.STATUS_DEGRADED
    assert code == 200
    assert any("has not run" in p for p in payload["problems"])


def test_health_is_clean_when_the_backup_is_fresh(cfg):
    config_backup.take_snapshot(cfg, NOW)
    payload, code = _health(config_backup.probe(cfg, NOW))
    assert payload["status"] == health_mod.STATUS_OK
    assert payload["problems"] == []
    assert payload["checks"]["config_backup"]["status"] == "ok"


def test_health_treats_could_not_check_as_a_problem(cfg):
    """"Could not check" must never be reported as "nothing is wrong"."""
    payload, code = _health({"status": "unknown", "error": "PermissionError: nope"})
    assert payload["status"] == health_mod.STATUS_DEGRADED
    assert any("PermissionError" in p for p in payload["problems"])


def test_health_probe_defaults_on_so_the_route_needs_no_argument(monkeypatch):
    """main.py does not pass backup_result; the check must still happen."""
    monkeypatch.setattr(health_mod, "_backup_cache", {"at": 0.0, "value": None})
    sentinel = {"status": "missing", "detail": "probe ran"}
    monkeypatch.setattr(health_mod, "probe_config_backups", lambda now=None: sentinel)
    payload, code = health_mod.compute_health(
        db_result={"status": "ok", "latency_ms": 1.0},
        heartbeats={}, supervisor_status=None,
        outbox_result={"pending": 0, "oldest_age_seconds": None},
        stale_after=60.0)
    assert payload["checks"]["config_backup"]["detail"] == "probe ran"


def test_health_probe_never_raises(monkeypatch):
    monkeypatch.setattr(health_mod, "_backup_cache", {"at": 0.0, "value": None})

    def boom(*a, **k):
        raise OSError("disk gone")

    monkeypatch.setattr(config_backup, "probe", boom)
    out = health_mod.probe_config_backups()
    assert out["status"] == "unknown"
    assert "disk gone" in out["error"]


# ------------------------------------------------------ the scheduler's wiring
def test_scheduler_takes_the_snapshot(tmp_path, cfg, monkeypatch):
    """The hook in run_auto_update.py is executed, not merely defined.

    Without this, the module could be perfect and never called - which is the
    exact shape of a weekly job that silently never ran.
    """
    import run_auto_update

    sched = run_auto_update.MultiDiscoveryScheduler(server_dir=str(tmp_path))
    # The fixture's config dir is the one to snapshot.
    sched.config_dir = cfg

    result = sched.maybe_backup_configs(now=NOW)
    assert result is not None, "the first tick must check, not wait 30 minutes"
    assert result["snapshot"]["created"], "the scheduler ran but wrote nothing"
    assert os.path.exists(os.path.join(
        config_backup.backup_dir(cfg), "table_config_260728.json.bak"))
    assert result["probe"]["status"] == "ok"


def test_scheduler_throttles_repeat_checks(tmp_path, cfg):
    import run_auto_update

    sched = run_auto_update.MultiDiscoveryScheduler(server_dir=str(tmp_path))
    sched.config_dir = cfg
    assert sched.maybe_backup_configs(now=NOW) is not None
    # A 5 s tick must not listdir the config directory every 5 s.
    assert sched.maybe_backup_configs(now=NOW) is None


def test_scheduler_survives_a_broken_backup(tmp_path, monkeypatch):
    """A backup failure must never stop the collectors from running."""
    import run_auto_update

    sched = run_auto_update.MultiDiscoveryScheduler(server_dir=str(tmp_path))
    sched.config_dir = os.path.join(str(tmp_path), "does_not_exist")
    result = sched.maybe_backup_configs(now=NOW)
    assert result["snapshot"]["errors"], "a missing config dir was not reported"
    assert result["probe"]["status"] == "missing"
