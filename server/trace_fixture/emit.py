# -*- coding: utf-8 -*-
"""Writes a generated batch out: ingestion CSVs, and the five oracle files.

[Why the business-key column is not written]

Every fixture table declares `composite_key_source`, and `std_parser._build_header_map`
accepts EITHER the business-key column OR all of the composite sources
(std_parser.py:87-98). Emitting the sources and letting `crud.apply_batch_updates`
compose the key (crud.py:1051-1059) removes a whole class of failure: a key I compose
by hand could differ from the one crud recomposes from the stored row afterwards
(crud.py:1237-1265), and the row would then be silently re-keyed on the next write.

[Why files are written .tmp then renamed]

The directory watcher fires on creation of a direct child of `raws/`; a partially
written file would be picked up mid-flush. `os.replace` is atomic on Windows and
POSIX alike, and it is what the existing collectors do.
"""

import csv
import json
import os
import tempfile

from . import world as _world

# Column order per table. Every name here must exist in that table's
# `display_columns`; anything else is dropped by the parser with a warning, which is
# a silent partial load rather than a refusal.
ORDER = {
    "lot_event": ["lot", "event_type", "parent_lot", "child_lot",
                  "slot_numbers", "wafer_ids", "equipment", "event_time"],
    "core_wafer_map": ["core_lot", "core_slot", "core_x", "core_y",
                       "c_bn", "wafer_id", "event_time"],
    "dt_log": ["dt_job", "dt_eqp", "product", "dt_lot", "dt_slot", "dt_x", "dt_y",
               "core_lot", "core_slot", "core_wafer", "core_x", "core_y",
               "c_bn", "event_time"],
    "bonding_log": ["bond_lot", "bond_slot", "bond_x", "bond_y", "b_bn",
                    "stack_height", "dt_lot", "dt_slot", "dt_x", "dt_y",
                    "bond_eqp", "event_time"],
    "wafer_id_status": ["core_lot", "core_slot", "wafer_id", "valid_from"],
    "wafer_map_metadata": ["target_table", "map_id", "grid_metadata"],
}

ORACLE_ORDER = {
    "truth_wafer_position": ["wafer_id", "event_time", "lot", "slot"],
    # core_lot/core_slot are the MEASUREMENT-time position (where core_wafer_map holds
    # the die); core_lot_at_dt/core_slot_at_dt are the position at DT time. They differ
    # whenever a split or merge intervened, and the gap between them is exactly the
    # lot_event walk the scenario is built to require.
    "truth_die_lineage": ["bond_lot", "bond_slot", "bond_x_true", "bond_y_true",
                          "dt_job", "dt_x_true", "dt_y_true", "core_wafer",
                          "core_lot", "core_slot", "core_lot_at_dt", "core_slot_at_dt",
                          "core_x_true", "core_y_true"],
    "truth_frame": ["space", "scope", "true_frame", "declared_frame",
                    "declaration_is_honest"],
    "truth_ambiguous": ["case", "subject", "question", "expected_answer",
                        "why", "candidates"],
    "truth_missing": ["table", "business_key_val", "column", "true_value",
                      "kind", "recorded_value"],
}

PREFIX = "trace_fixture"


def _atomic_write_csv(path, fieldnames, rows, append=False):
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    if append and os.path.exists(path):
        with open(path, "a", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
            for r in rows:
                w.writerow(r)
        return path
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    os.close(fd)
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    os.replace(tmp, path)
    return path


def oracle_dir(data_root):
    # Deliberately OUTSIDE ingestion_workspace: the watcher registers every directory
    # named `raws` under that tree, and truth files must never be ingestible.
    return os.path.join(data_root, "trace_fixture_oracle")


def staging_dir(data_root):
    return os.path.join(data_root, "trace_fixture_staging")


def emit_batch(built, data_root, stamp, write_ingestion=True, write_oracle=True,
               to_raws=False):
    """Write one built batch. Returns a summary dict.

    `to_raws` DEFAULTS TO FALSE, and that default was bought the hard way. `raws/` is a
    hot directory: a live watcher picked up a batch within seconds of it being written
    and had begun ingesting before there was any chance to review it. Generating and
    ingesting are separate decisions -- one is "make the data", the other is "put it in
    the database" -- so the default writes to a staging directory the watcher does not
    scan, and moving the files into `raws/` is a deliberate second act.

    The auto-update collector passes to_raws=True: for a scheduled job, ingesting IS
    the intent.

    The oracle is APPEND-ONLY and guarded by a per-batch marker, so re-running a batch
    cannot double-count the truth and thereby flatter a later score.
    """
    out = {"ingestion": [], "oracle": [], "oracle_skipped": False,
           "target": "raws" if to_raws else "staging"}
    ws = os.path.join(data_root, "ingestion_workspace")

    if write_ingestion:
        for table, order in ORDER.items():
            rows = built.tables.get(table) or []
            if not rows:
                continue
            name = "%s_%s_b%03d_%s.csv" % (PREFIX, table, built.cfg.batch, stamp)
            if to_raws:
                path = os.path.join(ws, table, "raws", name)
            else:
                path = os.path.join(staging_dir(data_root), table, name)
            _atomic_write_csv(path, order, rows)
            out["ingestion"].append((table, len(rows), path))

    if write_oracle:
        od = oracle_dir(data_root)
        marker = os.path.join(od, ".batch_%03d.done" % built.cfg.batch)
        if os.path.exists(marker):
            out["oracle_skipped"] = True
        else:
            for name, order in ORACLE_ORDER.items():
                rows = built.oracle.get(name) or []
                path = os.path.join(od, name + ".csv")
                _atomic_write_csv(path, order, rows, append=os.path.exists(path))
                out["oracle"].append((name, len(rows), path))
            os.makedirs(od, exist_ok=True)
            with open(marker, "w", encoding="utf-8") as fh:
                json.dump(built.stats, fh, ensure_ascii=False, indent=2)
    return out
