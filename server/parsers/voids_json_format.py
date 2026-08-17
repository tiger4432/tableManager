"""Parse the external ``WAFERID/WORK_DATETIME/voids.json`` feed.

The directory names are source data.  The watcher passes the path relative to
the configured external root; this module never infers a wafer from the host's
absolute directory layout.  The middle directory is ``{workid}_YYYYMMDD_HHMMSS``
in production; see ``parse_relative_source_path`` for the accepted forms and for
what the work id is (a descriptive column) and is not (key material).

One file states two facts and is therefore read by two table handlers:

* ``inspection_run`` records that a package layer was inspected (the
  denominator, including a clean run with zero findings).
* ``void_obs`` records the voids found by those runs.

The real producer payload was not available when this reader was introduced
(the only observed file was zero bytes).  Consequently the accepted JSON shape
is deliberately small and explicit instead of a permissive guess:

``[{...}, ...]``
    A list of void rows.  Runs are derived from the distinct package layers in
    those rows.  An empty list cannot describe a clean run.

``{"voids": [...], "runs": [...], "unit": "um"}``
    ``runs`` is optional when void rows exist, but is required to represent a
    clean scan.  ``scans`` is accepted as an alias for ``runs``.  File-level
    ``unit`` fills rows that do not carry one.

The reader is bounded before ``json.load``.  Refusing an oversized file is a
safer failure than exhausting the watcher process; a future streaming format
can replace this boundary after a real large sample is available.
"""
from __future__ import annotations

import json
import math
import os
import re
from datetime import datetime

from void_sat_format import (
    METHOD,
    RUN_TABLE,
    VOID_TABLE,
    UNITS,
    compose_run_uid,
    declare_offset,
    screen,
)


DEFAULT_MAX_FILE_MB = 128
# The producer's real folder is ``{workid}_YYYYMMDD_HHMMSS``; the work id is an
# arbitrary token, so it cannot be spelled out here.  The timestamp is anchored to
# the END of the name and everything before the last underscore-separated
# ``YYYYMMDD_HHMMSS`` is the work id - which makes the two forms this reader
# already accepted special cases rather than separate branches: ``WORK_...`` is
# simply a work id that reads ``WORK``, and a bare timestamp has no work id at all.
_WORK_DATETIME_RE = re.compile(r"^(?:(?P<work_id>.+)_)?(?P<date>\d{8})_(?P<time>\d{6})$")
_KEY_ALIASES = {
    "basewaferid": "base_wafer_id",
    "basewfid": "base_wafer_id",
    "basex": "base_x",
    "basey": "base_y",
    "gate": "stack_gate",
    "stackgate": "stack_gate",
    "satgate": "stack_gate",
    "layer": "stack_gate",
    "inchipx": "inchip_x",
    "inchipy": "inchip_y",
    "radiusx": "radius_x",
    "radiusy": "radius_y",
    "rx": "radius_x",
    "ry": "radius_y",
    "recipeid": "recipe_id",
    "eqpid": "eqp_id",
    "equipmentid": "eqp_id",
    "observedat": "observed_at",
    "unit": "unit",
    "method": "method",
}
_VOID_REQUIRED = (
    "base_x", "base_y", "stack_gate", "inchip_x", "inchip_y",
    "radius_x", "radius_y",
)
_RUN_REQUIRED = ("base_x", "base_y", "stack_gate")
_NUMERIC = frozenset(_VOID_REQUIRED)


def _fold(name) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name).strip().lower())


def _canonical_row(raw: dict, *, row_label: str) -> dict:
    if not isinstance(raw, dict):
        raise ValueError(f"{row_label} must be a JSON object, got {type(raw).__name__}.")
    out = {}
    claimed = {}
    for source_key, value in raw.items():
        canonical = _KEY_ALIASES.get(_fold(source_key), str(source_key).strip())
        if canonical in out and out[canonical] != value:
            raise ValueError(
                f"{row_label} has two conflicting fields for '{canonical}': "
                f"{claimed[canonical]!r} and {source_key!r}.")
        out[canonical] = value
        claimed[canonical] = source_key
    return out


def parse_relative_source_path(rel_path: str, expected_filename: str = "voids.json") -> dict:
    """Return source identity parsed from ``WAFERID/WORK_DATETIME/voids.json``.

    Exactly three components are required.  Accepting an arbitrary deeper path
    would make it unclear which directory is the wafer identifier.

    The middle directory must END with ``YYYYMMDD_HHMMSS``.  Three forms are
    therefore accepted, and they are one rule rather than three:

    ``{workid}_YYYYMMDD_HHMMSS``
        The production shape.  ``workid`` is an arbitrary token and is returned
        verbatim as ``work_id``; it is descriptive only and is not key material.
    ``WORK_YYYYMMDD_HHMMSS``
        The sample/doc shape.  Its work id is literally ``WORK`` - not stripped
        away, because this reader cannot know that some producer's work ids are
        not spelled that way.
    ``YYYYMMDD_HHMMSS``
        No work id at all; ``work_id`` is ``None``.
    """
    if not isinstance(rel_path, str) or not rel_path.strip():
        raise ValueError(
            "voids_json requires the watcher-provided relative source path; "
            "an absolute filename alone cannot identify the wafer directory safely.")
    parts = tuple(part for part in rel_path.replace("\\", "/").split("/") if part)
    if len(parts) != 3:
        raise ValueError(
            f"source path must be WAFERID/WORK_DATETIME/{expected_filename}, "
            f"got {rel_path!r} ({len(parts)} component(s)).")
    wafer_id, work_datetime, filename = parts
    if filename.lower() != expected_filename.lower():
        raise ValueError(
            f"source filename must be {expected_filename!r}, got {filename!r}.")
    if wafer_id in (".", "..") or not wafer_id.strip():
        raise ValueError(f"invalid wafer id directory {wafer_id!r} in {rel_path!r}.")
    match = _WORK_DATETIME_RE.fullmatch(work_datetime)
    if not match:
        raise ValueError(
            f"work datetime directory must end with YYYYMMDD_HHMMSS "
            f"(WORKID_YYYYMMDD_HHMMSS, WORK_YYYYMMDD_HHMMSS or "
            f"YYYYMMDD_HHMMSS), got {work_datetime!r}.")
    try:
        # Named groups, not `match.groups()`: the work id is a third group and
        # joining all of them would feed it to strptime.
        local = datetime.strptime(
            match.group("date") + match.group("time"), "%Y%m%d%H%M%S")
    except ValueError as exc:
        raise ValueError(
            f"work datetime directory contains an invalid calendar value: "
            f"{work_datetime!r}.") from exc
    observed_at = declare_offset(local.isoformat())[0]
    return {
        "base_wafer_id": wafer_id.strip(),
        "work_id": match.group("work_id"),
        "work_datetime": work_datetime,
        "observed_at": observed_at,
        "filename": filename,
    }


def _positive_number(value, *, name: str, default):
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"voids_json option '{name}' must be a positive number, got {value!r}.")
    return value


def _read_payload(file_path: str, options: dict) -> tuple[list, list, dict]:
    max_mb = _positive_number(options.get("max_file_mb"), name="max_file_mb",
                              default=DEFAULT_MAX_FILE_MB)
    size = os.path.getsize(file_path)
    if size == 0:
        raise ValueError(
            f"{file_path}: empty voids.json. An empty file is indistinguishable "
            f"from an incomplete copy; use [] or {{\"voids\": [], \"runs\": [...]}} "
            f"for an intentional empty result.")
    if size > int(max_mb * 1024 * 1024):
        raise ValueError(
            f"{file_path}: {size} bytes exceeds the configured voids_json safety "
            f"ceiling ({max_mb} MB). Nothing was loaded; convert the producer to "
            f"a streaming format or raise external_sources[].options.max_file_mb "
            f"after measuring watcher memory.")
    try:
        with open(file_path, "r", encoding="utf-8-sig") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{file_path}: invalid JSON at line {exc.lineno}, column {exc.colno}: "
            f"{exc.msg}. Nothing was loaded.") from exc

    if isinstance(payload, list):
        return payload, [], {}
    if not isinstance(payload, dict):
        raise ValueError(
            f"{file_path}: root must be a JSON array or object, got "
            f"{type(payload).__name__}.")
    if "voids" not in payload:
        raise ValueError(f"{file_path}: JSON object root must contain a 'voids' array.")
    voids = payload.get("voids")
    runs = payload.get("runs", payload.get("scans", []))
    if not isinstance(voids, list):
        raise ValueError(f"{file_path}: 'voids' must be a JSON array.")
    if not isinstance(runs, list):
        raise ValueError(f"{file_path}: 'runs'/'scans' must be a JSON array when present.")
    metadata = {k: v for k, v in payload.items() if k not in ("voids", "runs", "scans")}
    return voids, runs, metadata


def _finite_number(value, *, column: str, row_label: str):
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        raise ValueError(f"{row_label}: '{column}' cannot be boolean {value!r}.")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{row_label}: '{column}' is not numeric: {value!r}.") from None
    if not math.isfinite(number):
        raise ValueError(f"{row_label}: '{column}' cannot be NaN/Inf: {value!r}.")
    return number


def _merge_path_identity(row: dict, path_data: dict, *, row_label: str) -> dict:
    out = dict(row)
    source_wafer = out.get("base_wafer_id")
    path_wafer = path_data["base_wafer_id"]
    if source_wafer is not None and str(source_wafer).strip() != path_wafer:
        raise ValueError(
            f"{row_label}: body base_wafer_id {source_wafer!r} conflicts with "
            f"path wafer id {path_wafer!r}. Refusing rather than assigning the "
            f"finding to one plausible-but-unknown wafer.")
    out["base_wafer_id"] = path_wafer

    # The directory is the feed's identity contract, not merely a fallback.
    # Accept a body timestamp only as a redundant assertion of the same instant;
    # allowing it to override WORK_DATETIME would make one path name two runs.
    path_stamp = path_data["observed_at"]
    stamp = out.get("observed_at")
    if stamp is not None and str(stamp).strip():
        declared = declare_offset(str(stamp))[0]
        try:
            declared_dt = datetime.fromisoformat(declared.replace("Z", "+00:00"))
            path_dt = datetime.fromisoformat(path_stamp.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(
                f"{row_label}: body observed_at {stamp!r} is not an ISO datetime."
            ) from exc
        if declared_dt != path_dt:
            raise ValueError(
                f"{row_label}: body observed_at {stamp!r} conflicts with path work "
                f"datetime {path_data['work_datetime']!r}. Refusing rather than "
                f"assigning the row to one plausible-but-unknown run."
            )
    out["observed_at"] = path_stamp

    # Merged HERE, beside the other two path facts, so that every caller -
    # void rows, run carriers and explicit runs - reads one value from one
    # place and the run tables cannot disagree with the observation table.
    # Unlike base_wafer_id/observed_at this one does NOT refuse a conflicting
    # body field: the work id is descriptive, never key material, so a
    # disagreement can only mislabel a column, and refusing the whole file over
    # it would break exactly the production feed this reader exists to accept.
    # The directory wins.
    out["work_id"] = path_data.get("work_id")
    return out


def _normalise_void_rows(raw_rows: list, path_data: dict, metadata: dict,
                         options: dict) -> list[dict]:
    file_unit = metadata.get("unit", options.get("unit"))
    rows = []
    for index, raw in enumerate(raw_rows):
        label = f"voids[{index}]"
        row = _merge_path_identity(_canonical_row(raw, row_label=label), path_data,
                                   row_label=label)
        for column in _NUMERIC:
            if column in row:
                row[column] = _finite_number(row[column], column=column, row_label=label)
        missing = [c for c in _VOID_REQUIRED if row.get(c) is None]
        if missing:
            raise ValueError(f"{label}: missing required finding field(s) {missing!r}.")
        gate = row["stack_gate"]
        if gate != int(gate):
            raise ValueError(f"{label}: stack_gate must be a whole layer, got {gate!r}.")
        row["stack_gate"] = int(gate)

        unit = row.get("unit", file_unit)
        if unit is None or str(unit).strip() not in UNITS:
            raise ValueError(
                f"{label}: unit must be one of {list(UNITS)}, got {unit!r}. "
                f"Declare it in the row, the JSON object root, or "
                f"external_sources[].options.unit; no unit is guessed.")
        row["unit"] = str(unit).strip()
        row["run_uid"] = compose_run_uid(
            row["base_wafer_id"], row["base_x"], row["base_y"],
            row["stack_gate"], row["observed_at"])
        rows.append(row)
    return rows


def _normalise_run_carriers(raw_rows: list, path_data: dict) -> list[dict]:
    """Read only the package-layer facts needed to derive scan denominators.

    A missing/unknown radius unit makes an observation unusable, but it does not
    erase the independent fact that the package layer was scanned.  Keeping this
    gate separate is the JSON counterpart of the two-table schema itself.
    """
    rows = []
    for index, raw in enumerate(raw_rows):
        label = f"voids[{index}]"
        row = _merge_path_identity(_canonical_row(raw, row_label=label), path_data,
                                   row_label=label)
        for column in _RUN_REQUIRED:
            if column in row:
                row[column] = _finite_number(row[column], column=column, row_label=label)
        missing = [c for c in _RUN_REQUIRED if row.get(c) is None]
        if missing:
            raise ValueError(
                f"{label}: missing package-layer field(s) needed to identify the "
                f"inspection run: {missing!r}.")
        gate = row["stack_gate"]
        if gate != int(gate):
            raise ValueError(f"{label}: stack_gate must be a whole layer, got {gate!r}.")
        rows.append({
            "base_wafer_id": row["base_wafer_id"],
            "work_id": row["work_id"],
            "base_x": row["base_x"],
            "base_y": row["base_y"],
            "stack_gate": int(gate),
            "observed_at": row["observed_at"],
        })
    return rows


def _normalise_explicit_runs(raw_runs: list, path_data: dict, metadata: dict) -> list[dict]:
    rows = []
    for index, raw in enumerate(raw_runs):
        label = f"runs[{index}]"
        row = _merge_path_identity(_canonical_row(raw, row_label=label), path_data,
                                   row_label=label)
        method = row.get("method", METHOD)
        if str(method).strip().lower() != METHOD:
            raise ValueError(
                f"{label}: method {method!r} conflicts with this declared SAT feed.")
        row["method"] = METHOD
        for column in _RUN_REQUIRED:
            if column in row:
                row[column] = _finite_number(row[column], column=column, row_label=label)
        missing = [c for c in _RUN_REQUIRED if row.get(c) is None]
        if missing:
            raise ValueError(f"{label}: missing required scan field(s) {missing!r}.")
        gate = row["stack_gate"]
        if gate != int(gate):
            raise ValueError(f"{label}: stack_gate must be a whole layer, got {gate!r}.")
        row["stack_gate"] = int(gate)
        for optional in ("recipe_id", "eqp_id"):
            if optional not in row and optional in metadata:
                row[optional] = metadata[optional]
        rows.append({
            "method": METHOD,
            "base_wafer_id": row["base_wafer_id"],
            "work_id": row["work_id"],
            "base_x": row["base_x"],
            "base_y": row["base_y"],
            "stack_gate": row["stack_gate"],
            "observed_at": row["observed_at"],
            "recipe_id": row.get("recipe_id"),
            "eqp_id": row.get("eqp_id"),
        })
    return rows


def _derived_runs(void_rows: list[dict], metadata: dict) -> list[dict]:
    by_key = {}
    for row in void_rows:
        key = (
            row["base_wafer_id"], row["base_x"], row["base_y"],
            row["stack_gate"], row["observed_at"],
        )
        candidate = {
            "method": METHOD,
            "base_wafer_id": key[0],
            # Not in `key`: the work id comes from the one directory this file
            # was read from, so it is constant across the file and adding it
            # would only lengthen the identity tuple the coverage check reads.
            "work_id": row.get("work_id"),
            "base_x": key[1],
            "base_y": key[2],
            "stack_gate": key[3],
            "observed_at": key[4],
            "recipe_id": metadata.get("recipe_id"),
            "eqp_id": metadata.get("eqp_id"),
        }
        previous = by_key.get(key)
        if previous is not None and previous != candidate:
            raise ValueError(f"conflicting run metadata for package layer {key!r}.")
        by_key[key] = candidate
    return list(by_key.values())


def _run_identity(row: dict):
    return tuple(row.get(key) for key in (
        "base_wafer_id", "base_x", "base_y", "stack_gate", "observed_at"))


def parse_voids_json(file_path: str, *, rel_path: str, table_name: str,
                     options: dict | None = None):
    """Return ``(rows, total_rows, refused_rows)`` for the target table.

    The shape matches ``IngestionHandler._resolve_rows``.  ``file_path`` is the
    full watcher-supplied filename; ``rel_path`` is the path relative to the
    configured external source and is where the wafer identifier is parsed.
    """
    options = dict(options or {})
    expected_filename = str(options.get("filename", "voids.json"))
    path_data = parse_relative_source_path(rel_path, expected_filename)
    raw_voids, raw_runs, metadata = _read_payload(file_path, options)

    if table_name == VOID_TABLE:
        void_rows = _normalise_void_rows(raw_voids, path_data, metadata, options)
        kept, report = screen(VOID_TABLE, void_rows, source=file_path)
    elif table_name == RUN_TABLE:
        carriers = _normalise_run_carriers(raw_voids, path_data)
        runs = _normalise_explicit_runs(raw_runs, path_data, metadata)
        derived = _derived_runs(carriers, metadata)
        if not runs:
            runs = derived
        elif derived:
            declared_ids = {_run_identity(row) for row in runs}
            missing = sorted(
                (_run_identity(row) for row in derived
                 if _run_identity(row) not in declared_ids),
                key=repr,
            )
            if missing:
                raise ValueError(
                    f"{file_path}: explicit runs/scans omit {len(missing)} package "
                    f"layer(s) carried by void rows: {missing[:10]!r}. The observations "
                    f"would point to denominator rows that do not exist.")
        if not runs:
            raise ValueError(
                f"{file_path}: this is an intentional empty finding result but it "
                f"does not declare any 'runs'/'scans'. A clean scan must still say "
                f"which base_x/base_y/stack_gate was inspected; otherwise clean and "
                f"never-scanned are indistinguishable.")
        kept, report = screen(RUN_TABLE, runs, source=file_path)
    else:
        raise ValueError(
            f"voids_json parser targets only {VOID_TABLE!r} and {RUN_TABLE!r}, "
            f"not {table_name!r}.")

    refused = int(report.get("refused_rows") or 0)
    if refused:
        raise ValueError(
            f"{file_path}: {table_name} key gate refused {refused} row(s): "
            f"{report.get('by_reason')}. Nothing from this file was written; "
            f"fix the ambiguous/unkeyed rows and deliver it again.")
    return kept, len(kept), 0
