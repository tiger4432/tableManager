from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from typing import Any, Optional
from . import models, schemas
from contextlib import contextmanager

@contextmanager
def transaction_context(user: str, tx_id: str, source: str):
    from database.context import request_user, request_transaction_id, request_source
    token_user = request_user.set(user)
    token_tx = request_transaction_id.set(tx_id)
    token_src = request_source.set(source)
    try:
        yield
    finally:
        request_user.reset(token_user)
        request_transaction_id.reset(token_tx)
        request_source.reset(token_src)
import uuid
import uuid6
import codecs
import json
import math
import os
import logging
from datetime import datetime, date, timezone

logger = logging.getLogger("Server")

# [P2-C9] 감사 로그 값 길이 상한 — 공용 상수(server/event_constants.py) 단일 정의를 공유한다.
# crud는 server/ 상위가 sys.path에 없는 컨텍스트에서 import될 수 있으므로(플러그인 shim 등)
# 실패 시 무제한 폴백 대신 **동일 기본값을 내장한 로컬 구현**으로 폴백한다(조용한 무상한 금지).
try:
    from event_constants import MAX_AUDIT_VALUE_CHARS, truncate_audit_value
except ImportError:  # pragma: no cover - 방어적 폴백
    import sys as _sys
    _sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from event_constants import MAX_AUDIT_VALUE_CHARS, truncate_audit_value

# 값 절단 경고는 (테이블, 컬럼)별 1회만 — create_audit_log는 셀 단위 핫패스라
# 무조건 로깅하면 대형 파일 1건이 수십만 줄의 WARNING을 쏟아 로그 자체가 병목이 된다.
_audit_truncation_warned = set()


def _warn_audit_truncation_once(table_name: str, col_name: str):
    key = (table_name, col_name)
    if key in _audit_truncation_warned:
        return
    _audit_truncation_warned.add(key)
    logger.warning(
        f"[Audit] Audit value(s) exceeded {MAX_AUDIT_VALUE_CHARS} chars and were truncated "
        f"with an explicit marker (table='{table_name}', column='{col_name}'). "
        f"This warning is emitted once per (table, column) per process."
    )


# [Schema] A column that is absent from table_config.json is dropped from the update
# while the write still reports success, so a config that lags its client loses fields
# silently (map_doe/map_doe_source lost `eventtime` this way). Surface the first drop
# per (table, column); repeating it from a per-cell loop would flood the log and get
# the whole log ignored.
#
# Shape note: this is probed as a dict of per-table sets rather than one set of
# (table, column) tuples so the already-warned path allocates nothing — building a
# tuple key on every cell of a 100k-row ingest is exactly the cost this path cannot
# afford. Entries are never cleared; a column added to the config simply stops
# reaching the drop branch.
_undeclared_column_warned = {}

# Per-table budget. For a correct caller the registry is bounded by schema size, but
# the keys come from the payload, so junk column names (a malformed header row, a
# parser emitting values as headers) could otherwise grow it without limit. On
# saturation the table stops both growing and warning — drops go silent again, which
# is announced once so the silence is never a surprise.
_MAX_UNDECLARED_WARNED_PER_TABLE = 64


def _warn_undeclared_column_once(table_name: str, col_name: str):
    warned = _undeclared_column_warned.get(table_name)
    if warned is None:
        warned = _undeclared_column_warned[table_name] = set()
    elif col_name in warned or len(warned) >= _MAX_UNDECLARED_WARNED_PER_TABLE:
        return
    warned.add(col_name)
    logger.warning(
        f"[Schema] Column '{col_name}' is not declared in column_types for table "
        f"'{table_name}' and was DROPPED from the update; the write still succeeded "
        f"for the declared columns. Add it to config/table_config.json to persist it. "
        f"This warning is emitted once per (table, column) per process."
    )
    if len(warned) >= _MAX_UNDECLARED_WARNED_PER_TABLE:
        logger.warning(
            f"[Schema] Reached {_MAX_UNDECLARED_WARNED_PER_TABLE} distinct undeclared "
            f"columns for table '{table_name}'; further undeclared columns on this table "
            f"will be dropped WITHOUT a warning."
        )


# ---------------------------------------------------------------------------
# [Version gate] Version is the authority, arrival order is not.
# ---------------------------------------------------------------------------
# A table whose single business key must always hold the LATEST row declares
# `version_column` in table_config.json. A machine write against an EXISTING row of such
# a table is applied only when the incoming version is strictly GREATER than the one the
# row already holds. Without it this path is last-write-wins, so re-dropping a superseded
# file makes current state regress with no record of any kind.
#
# 🔴 The gate is a VETO, never a promotion. A row that passes still goes cell by cell
# through `compute_priority_value`, where `user` (0) outranks every machine source. That
# is the whole of "version orders only WITHIN a priority tier, never across one": a newer
# version can decide whether the parser's row is considered at all, and it can never
# decide a cell a person has corrected. Writing the payload onto the row once the version
# passes - the plausible reading of "version is the authority" - would silently undo human
# corrections on the next ingestion, and `test_human_correction_survives_a_newer_version`
# exists to turn red the moment anyone does.
#
# The declaration is per TABLE, not per REQUEST. A table either has a version column or it
# does not, and this function is the funnel six direct callers plus HTTP converge on: a
# request-level flag is one every caller has to remember, and the caller who forgets falls
# back to exactly the last-write-wins regression this closes. A table that declares
# nothing is byte-identical to before.

# The names refusals are reported under. Same vocabulary and same shape as
# `enrichment_candidates.REASON_*` - a refusal is counted under a name, never folded into
# a generic failure.
REASON_VERSION_MISSING = "version_missing"
REASON_VERSION_UNORDERABLE = "version_unorderable"
REASON_VERSION_OLDER = "version_older"
REASON_VERSION_SAME = "version_same"
# Not a refusal: the row is applied. Named anyway because it happens exactly once per row
# and only while a table is adopting the gate.
NOTE_ROW_VERSION_ABSENT = "row_version_absent"
# A no-op that is a genuine upstream defect: the version did not move but the content
# this same source writes did.
NOTE_SAME_VERSION_CONTENT_DIFFERS = "version_same_content_differs"

# table_name -> {reasons already announced at WARNING in this process}. Bounded by the
# constant set of reason names above, so unlike the undeclared-column registry it needs
# no budget. Entries are never cleared; a feed that stops regressing simply stops
# reaching the branch.
_version_gate_announced = {}

# How many differing column names ride in the per-batch summary. The names come from the
# payload, so a malformed file could otherwise put a full schema in one log line.
MAX_VERSION_DIFF_COLUMNS_REPORTED = 8

# What each outcome MEANS, in the log, in one sentence. Two of these outcomes APPLY the
# row and four refuse it; a single generic sentence would describe the applied ones as
# refusals, which is how a diagnostic starts lying.
_VERSION_OUTCOME_EXPLANATION = {
    REASON_VERSION_MISSING:
        "the incoming row carries no usable value in the version column, and an unknown "
        "version is read neither as older nor as newer - the stored row is kept",
    REASON_VERSION_UNORDERABLE:
        "the version value cannot be ordered (not a number, not an ISO-8601 timestamp, "
        "or the two sides are different kinds) - the stored row is kept",
    REASON_VERSION_OLDER:
        "the incoming version is LOWER than the stored one, so this is a superseded file "
        "arriving late - the stored row is kept",
    REASON_VERSION_SAME:
        "the incoming version equals the stored one, so the write is a no-op",
    NOTE_SAME_VERSION_CONTENT_DIFFERS:
        "the version did NOT move but the content this source writes DID. The write was "
        "dropped; check version management upstream, because this is how a real change "
        "gets silently discarded",
    NOTE_ROW_VERSION_ABSENT:
        "the stored row had no usable version, so the incoming one was ADOPTED and the "
        "row WAS written. Expected while a table takes up version gating; it should stop",
}


def _naive_utc(value):
    """One instant, one spelling - the doctrine `temporal_text_value` already pins.

    Aware values are converted to UTC; naive values are taken as already-UTC (that is
    what the SQLite dialect hands back and the only shape a naive column can be here).
    Returning naive UTC on both arms is what makes the two sides comparable at all:
    comparing an aware datetime to a naive one raises TypeError.
    """
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc)
        return value.replace(tzinfo=None)
    return datetime(value.year, value.month, value.day)


def _parse_temporal_version(text: str):
    try:
        return ("temporal", _naive_utc(datetime.fromisoformat(text)))
    except ValueError:
        return None


def parse_version_key(raw: Any, col_type: str):
    """A version value rendered to `(kind, sortable)`, or None when it cannot be ordered.

    🔴 The comparison is chosen from the VALUE, not only from the declaration, and it is
    never a text comparison. `column_text_sql` / `TEMPORAL_TEXT_FORMAT` are deliberately
    NOT used here: they exist to render a column to text for a SQL predicate, and text is
    precisely what mis-orders a version - `'10' < '9'`. What IS reused is the reasoning
    behind `TEMPORAL_TEXT_FORMAT`: an ISO-8601 timestamp is an ordered value, arbitrary
    text is not.

    Both sides must produce the same `kind`. A feed that emits `7` and then
    `2026-08-04T09:00:00` has not moved forward; it has changed what a version means, and
    coercing the two into one order would invent an answer. Different kinds are refused
    by the caller under `version_unorderable`.

    A `string` column is tried as a number FIRST (numeric revisions live in text columns
    all the time) and then as ISO-8601. Anything else is unorderable - `REV_B > REV_A` is
    a lexical accident, not a version order, and the ruling on this feature is that an
    unknown version is refused by name rather than read as older OR as newer.
    """
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None  # a flag is not a version
    if isinstance(raw, (datetime, date)):
        return ("temporal", _naive_utc(raw))
    if isinstance(raw, (int, float)):
        return ("numeric", float(raw)) if math.isfinite(raw) else None

    text = str(raw).strip()
    if text == "":
        return None

    if col_type == "number":
        try:
            parsed = float(text)
        except ValueError:
            return None
        return ("numeric", parsed) if math.isfinite(parsed) else None

    if col_type == "datetime":
        return _parse_temporal_version(text)

    try:
        parsed = float(text)
        if math.isfinite(parsed):
            return ("numeric", parsed)
    except ValueError:
        pass
    return _parse_temporal_version(text)


def _same_source_content_differs(db, table_name, row, update_item, config, version_col,
                                 is_new, sources_cache, overwrites_cache,
                                 cell_sources_to_upsert, cell_overwrites_to_upsert):
    """Columns whose incoming value differs from what THIS SAME SOURCE last wrote.

    🔴 Measured against the source's own previous value, not against the displayed cell.
    A human correction makes the displayed value differ from the file permanently, so
    comparing against the cell would put a false "version management is broken" warning on
    every single re-drop - and a warning that is always there is a warning nobody reads.
    Against the source's own history the predicate is exact: same version, different
    content, same writer.

    Reads come from the batch-preloaded caches (`_load_metadata_row_cell` is cache-first),
    so this costs a dict lookup per payload cell and issues no query on the batch path. It
    only runs on the equal-version arm, which is the re-drop case.
    """
    col_types = config.get("column_types", {})
    differing = []
    for col_name, val in update_item.updates.items():
        if col_name == version_col or col_name not in col_types:
            continue
        col_type = col_types.get(col_name, "string")
        try:
            incoming = cast_value_by_type(val, col_type, col_name)
        except ValueError:
            differing.append(col_name)
            continue
        col_srcs, _ow = _load_metadata_row_cell(
            db, table_name, row.row_id, col_name, is_new, sources_cache, overwrites_cache,
            cell_sources_to_upsert, cell_overwrites_to_upsert)
        prev = next((s.value for s in col_srcs if s.source_name == update_item.source_name),
                    None)
        # The source has never written this cell: that is a NEW field appearing at an
        # unchanged version, which is the same upstream defect.
        if prev is None and incoming is None:
            continue
        if (prev is None) != (incoming is None):
            differing.append(col_name)
            continue
        if col_type == "number":
            try:
                if float(prev) != float(incoming):
                    differing.append(col_name)
                continue
            except (ValueError, TypeError):
                pass
        if str(prev).strip() != str(incoming).strip():
            differing.append(col_name)
    return differing


def version_gate_verdict(table_name, config, row, is_new, update_item):
    """Per-ROW verdict: `(applied: bool, reason: str | None)`.

    Judged at the row and not at the cell. A per-cell version check would accept some
    columns of a stale row and refuse others, leaving the row half-updated and internally
    inconsistent - which is worse than either taking it or refusing it whole. If the row
    is applied, the ordinary per-cell layering then decides every cell.
    """
    version_col = config.get("version_column")
    if not version_col:
        return True, None  # not a version-gated table - the untouched default

    # A person's correction is not version-ordered. A grid edit carries one cell and no
    # version column at all; gating it would make the table read-only for people, and
    # `user` already outranks every machine source cell by cell.
    if update_item.source_name == "user":
        return True, None

    # Creating a row is not an overwrite: there is nothing to regress.
    if is_new:
        return True, None

    col_type = config.get("column_types", {}).get(version_col, "string")

    if version_col not in update_item.updates:
        return False, REASON_VERSION_MISSING
    incoming_raw = update_item.updates.get(version_col)
    if incoming_raw is None or str(incoming_raw).strip() == "":
        return False, REASON_VERSION_MISSING
    incoming = parse_version_key(incoming_raw, col_type)
    if incoming is None:
        return False, REASON_VERSION_UNORDERABLE

    stored = parse_version_key(getattr(row, version_col, None), col_type)
    if stored is None:
        # Adoption. A row written before the column existed has nothing to regress to,
        # and refusing it would wedge the table behind a manual backfill forever. Named
        # so the one-time adoption is visible rather than assumed.
        return True, NOTE_ROW_VERSION_ABSENT

    if incoming[0] != stored[0]:
        return False, REASON_VERSION_UNORDERABLE
    if incoming[1] > stored[1]:
        return True, None
    if incoming[1] == stored[1]:
        return False, REASON_VERSION_SAME
    return False, REASON_VERSION_OLDER


def log_version_gate_summary(table_name, version_col, source_name, stats):
    """Individual silence, named aggregate - the shape the ingestion drop report uses.

    Nothing per row: at 10M rows a per-row line buries every real event. A WARNING on
    FIRST sighting per (table, reason) per process, because that is the moment something
    genuinely changed; a later warning is therefore by definition news. Then one INFO per
    batch carrying the counts, so "nothing was refused" and "200 rows were refused" can
    never look the same to anyone who goes looking.

    ASCII only - this reaches a cp949 console.
    """
    if not stats:
        return
    counts = {k: v for k, v in stats.get("counts", {}).items() if v}
    if not counts:
        return

    announced = _version_gate_announced.setdefault(table_name, set())
    diff_cols = sorted(stats.get("differing_columns", set()))[:MAX_VERSION_DIFF_COLUMNS_REPORTED]
    for reason in sorted(counts):
        if reason in announced:
            continue
        announced.add(reason)
        detail = ""
        if reason == NOTE_SAME_VERSION_CONTENT_DIFFERS and diff_cols:
            detail = (f" Differing column(s): {', '.join(diff_cols)}.")
        logger.warning(
            f"[VersionGate] '{table_name}' is version-gated on column '{version_col}': "
            f"outcome '{reason}' seen for the first time in this process (source "
            f"'{source_name}'), {counts[reason]} row(s) in this batch - "
            f"{_VERSION_OUTCOME_EXPLANATION.get(reason, 'no explanation registered')}."
            f"{detail} Repeats are reported at INFO, once per batch."
        )

    named = ", ".join(f"{reason}={counts[reason]}" for reason in sorted(counts))
    detail = ""
    if NOTE_SAME_VERSION_CONTENT_DIFFERS in counts and diff_cols:
        capped = " (list capped)" if len(stats.get("differing_columns", ())) > len(diff_cols) else ""
        detail = f" Differing column(s): {', '.join(diff_cols)}{capped}."
    logger.info(
        f"[VersionGate] '{table_name}' version column '{version_col}', source "
        f"'{source_name}': {named} out of {stats.get('rows', 0)} row(s) in this batch.{detail}"
    )


class LightCellSource:
    __slots__ = ('table_name', 'row_id', 'column_name', 'source_name', 'value', 'updated_by', 'ingested_at')
    def __init__(self, table_name, row_id, column_name, source_name, value, updated_by, ingested_at):
        self.table_name = table_name
        self.row_id = row_id
        self.column_name = column_name
        self.source_name = source_name
        self.value = value
        self.updated_by = updated_by
        self.ingested_at = ingested_at

class LightCellOverwrite:
    __slots__ = ('table_name', 'row_id', 'column_name', 'is_overwrite', 'updated_by', 'updated_at', 'manual_priority_source')
    def __init__(self, table_name, row_id, column_name, is_overwrite, updated_by, updated_at, manual_priority_source):
        self.table_name = table_name
        self.row_id = row_id
        self.column_name = column_name
        self.is_overwrite = is_overwrite
        self.updated_by = updated_by
        self.updated_at = updated_at
        self.manual_priority_source = manual_priority_source

# 소스별 우선순위 정의 (숫자가 낮을수록 높음)
SOURCE_PRIORITY = {
    "user": 0,
    "collision_merge": 1,
    "pipeline_parser": 2,
    "custom_script": 3,
    # [QA G1-⑥] 체인 파생 쓰기 소스 서열 명시(구: 미등재 기본 99). 기존 4대 소스와의
    # 상대 서열은 불변(4 > 3)이라 표시값 레이어링 결과는 유지되며, 미등재 소스 대비로만 승격된다.
    "chain_ingestion": 4,
}

# The priority-0 layer above is the only source that means "a human typed this".
# Every other writer is machine-driven: `collision_merge` is the merge engine,
# `chain_ingestion` is the derived-table worker, and file parsers write under the
# *ingested filename* as their source name (so the set of automatic source values is
# open-ended - 10,750 distinct values on the live DB as of 2026-07-27). That is why
# human writes must be selected POSITIVELY by this constant and never by blacklisting
# automatic ones.
USER_SOURCE = "user"

# Config location comes from the single override point (server/paths.py, ASSY_DATA_ROOT).
# Same import guard as event_constants above: crud can be imported without server/ on sys.path.
try:
    import paths as _paths
except ImportError:  # pragma: no cover - defensive fallback
    import sys as _sys
    _sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    import paths as _paths

CONFIG_PATH = _paths.config_path("table_config.json")

def sanitize_to_utf8(data: Any) -> Any:
    """
    데이터 객체(Dict, List, Str 등) 내부의 모든 문자열을 재귀적으로 탐색하여 
    비유효한 UTF-8 바이트 시퀀스를 제거/정정합니다.
    JSON 직렬화가 불가능한 datetime/UUID 등도 문자열로 변환합니다.
    """
    if isinstance(data, dict):
        return {k: sanitize_to_utf8(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_to_utf8(v) for v in data]
    elif isinstance(data, str):
        # 비유효한 UTF-8 바이트를 무시(ignore)하고 다시 디코딩하여 깨끗한 문자열 생성
        return data.encode("utf-8", "ignore").decode("utf-8")
    elif isinstance(data, datetime):
        return data.isoformat()
    elif isinstance(data, uuid.UUID):
        return str(data)
    elif hasattr(data, "isoformat"):
        return data.isoformat()
    else:
        return data

class TableConfigError(RuntimeError):
    """table_config.json exists but cannot be read as a table map.

    Two causes, both parse-level: the bytes are not decodable/parsable JSON, or
    they parse into something that is not a JSON object. Raised only by
    `load_table_config_or_raise`. Deliberately narrow: see the scope note on
    that function for what does NOT raise.
    """


def _parse_position(exc) -> str:
    """Where the parse gave up, in a form an operator can act on."""
    if isinstance(exc, json.JSONDecodeError):
        return f"line {exc.lineno} column {exc.colno} (char {exc.pos}): {exc.msg}"
    if isinstance(exc, UnicodeDecodeError):
        return f"byte offset {exc.start}: not valid UTF-8 ({exc.reason})"
    return str(exc)


def _decode_config_text(raw: bytes) -> str:
    """Decode config bytes, honouring whatever BOM the operator's editor wrote.

    On Windows a BOM is the DEFAULT, not an exotic case. PowerShell 5.1 writes a
    UTF-8 BOM from `Set-Content -Encoding utf8` and `Out-File`, a bare `>`
    redirect writes UTF-16 LE with a BOM, and Notepad offers "UTF-8 with BOM"
    outright. A plain `raw.decode("utf-8")` turns every one of those into a
    UnicodeDecodeError - and because boot is fail-fast on decode/parse failures,
    an operator who added one column with the wrong editor would get a file that
    looks perfect in every editor and a web server that never starts again.

    A BOM is an encoding marker, not content: stripping it is not leniency about
    corrupt input, it is reading the file in the encoding it was written in.
    Bytes with no BOM are still strict UTF-8, so genuinely mis-encoded files
    (e.g. cp949 Korean saved without a BOM) still raise.
    """
    # UTF-32 LE (ff fe 00 00) must be tested BEFORE UTF-16 LE (ff fe), which is
    # its prefix - otherwise every UTF-32 LE file decodes as UTF-16 garbage.
    if raw.startswith(codecs.BOM_UTF8):
        return raw.decode("utf-8-sig")
    if raw.startswith(codecs.BOM_UTF32_LE) or raw.startswith(codecs.BOM_UTF32_BE):
        return raw.decode("utf-32")
    if raw.startswith(codecs.BOM_UTF16_LE) or raw.startswith(codecs.BOM_UTF16_BE):
        return raw.decode("utf-16")
    return raw.decode("utf-8")


def load_table_config_or_raise():
    """Boot-time loader. Raises TableConfigError when the file cannot be parsed.

    [#13] Coming up "successfully" with zero tables is the worst outcome
    available on a restart: the UI looks wiped, the log is clean, and nobody has
    a thread to pull. Callers on the boot path use this one so the process dies
    with the reason attached.

    SCOPE - what raises and what deliberately does not:
      raises : the file is present and is not JSON, or its bytes cannot be
               decoded. A leading BOM is read as the encoding marker it is
               (see _decode_config_text), so BOM-prefixed files are NOT failures.
      returns: the file is absent (a fresh install has no config yet).
      returns: the file cannot be read (OSError - a lock, a permission blip).
               An unreadable file is not a corrupt one, and refusing to boot on
               a transient read failure trades one outage for another.
      returns: the file parses but declares something odd. Semantic complaints
               must never keep a production server down.
      raises : the file parses but is not a JSON object. That is not a semantic
               complaint - `[]` or `null` cannot be a table map at all, and
               every consumer here treats the result as a mapping. Letting one
               through produces exactly the failure #13 exists to abolish: a
               server that boots with zero dynamic models and a near-clean log.
    """
    if not os.path.exists(CONFIG_PATH):
        return {}
    try:
        with open(CONFIG_PATH, "rb") as f:
            raw = f.read()
    except OSError as exc:
        # Not a parse failure -> loud, but not fatal (see scope note above).
        logger.error(
            f"[Config] Could not read table_config.json at '{CONFIG_PATH}' "
            f"([{type(exc).__name__}] {exc}). Continuing with an EMPTY table config."
        )
        return {}
    try:
        parsed = json.loads(_decode_config_text(raw))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TableConfigError(
            f"table_config.json is not valid JSON: '{CONFIG_PATH}' -> {_parse_position(exc)}"
        ) from exc
    if not isinstance(parsed, dict):
        # Measured: `[]` reached models.init_dynamic_models(), died on
        # AttributeError, was caught by main's broad `except Exception`, and the
        # server came up with ZERO dynamic models behind a single ERROR line -
        # the UI looks wiped, the log looks fine. `null` was worse: TABLE_CONFIG
        # stayed None for the whole process lifetime.
        raise TableConfigError(
            f"table_config.json must be a JSON object mapping table name -> "
            f"declaration, but its top level is {type(parsed).__name__}: '{CONFIG_PATH}'"
        )
    return parsed


def load_table_config():
    """Runtime-safe loader: returns {} on failure, but never silently.

    [#13] The old body was `except Exception: return {}` with no log. Live, the
    empty-config guard in models.refresh_dynamic_models absorbed it, so the only
    visible symptom was a schema change that never arrived; on a restart it was
    every table disappearing at once. Returning {} is still right here - it is
    what stops a bad read from wiping the live singleton - but the log line is
    what turns "everything vanished" into "line 3, column 5 of this file".
    """
    try:
        return load_table_config_or_raise()
    except TableConfigError as exc:
        logger.error(
            f"[Config] {exc}. Returning an EMPTY table config - the in-memory "
            f"config and the physical schema are left UNCHANGED."
        )
        return {}

def update_table_config(new_config: dict):
    """테이블 설정을 갱신하고 디스크에 저장합니다."""
    global TABLE_CONFIG
    TABLE_CONFIG.update(new_config)
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(TABLE_CONFIG, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[crud] Failed to save table config: {e}")

import sys
if not hasattr(sys, "_table_config_singleton"):
    sys._table_config_singleton = load_table_config()
TABLE_CONFIG = sys._table_config_singleton


def normalize_stored_text(value: Any) -> Any:
    """THE write-boundary normalizer for text. Strips a string; leaves anything else alone.

    [Why storage, and not a cleverer comparison]
    `clean_str_value` (the read/compare spelling) strips with Python's `str.strip()`,
    which removes ALL Unicode whitespace - tab, newline, CR, FF, VT, NBSP (U+00A0),
    ideographic space (U+3000), the U+2000-200A range: 29 codepoints. Postgres
    `btrim(x)` with no second argument strips exactly ONE of them, U+0020.

    So if storage were allowed to hold `"\t"`, Python would call it empty and SQL would
    call it non-empty, and any pushed-down predicate would disagree with the payload the
    user is looking at. The fix is NOT to teach SQL Python's whitespace table - that is a
    second spelling that drifts. The fix is that the divergent input never reaches
    storage, after which `col IS NULL OR col = ''` and `clean_str_value(v) == ""` are the
    same predicate BY CONSTRUCTION.

    This is not a new policy; it is the layer that was never told. `clean_str_value`
    already strips on every read and compare, `_update_row_business_key` already strips
    `business_key_val`, and the line below already mapped a whitespace-only value to NULL.
    Only the non-empty case still let surrounding whitespace through.

    Only `str` is stripped. A list/dict (the JSON columns - `map_doe.mat_*` carries raw
    material tokens where "the token text IS the identity") is returned untouched: those
    are containers, not text, and their elements are not this boundary's business.
    """
    return value.strip() if isinstance(value, str) else value


def cast_value_by_type(value: Any, col_type: str, col_name: str) -> Any:
    """컬럼의 타입 스펙에 맞춰 데이터를 int, float 등으로 명시적으로 형변환합니다.

    This is the write boundary: `apply_row_update_internal` runs EVERY value through it,
    and that function's only caller is `apply_batch_updates` - the funnel every write
    path converges on. Normalizing here rather than at each call site is the same
    reasoning `refuse_virtual_join_columns` records: a per-call-site rule is one the next
    author has to remember.
    """
    if value is None or str(value).strip() == "":
        return None

    if col_type == "number":
        val_str = str(value).strip()
        try:
            if "." in val_str:
                return float(val_str)
            else:
                return int(val_str)
        except ValueError:
            # [NUM1, found by contracts/blank_predicate 2026-07-31] The branch above
            # decides int-vs-float by asking whether the REPR contains a '.'. `str(1e16)`
            # is `'1e+16'` and `str(1e-05)` is `'1e-05'` - neither has one - so both went
            # to `int()` and were REFUSED, for values that are ordinary doubles the column
            # (`double precision`) holds exactly. Decide from the VALUE, not from its repr.
            #
            # Strictly additive: every input that already parsed still takes the branch
            # above and returns the same type it always did. This arm only converts a
            # refusal into a value.
            #
            # nan/inf stay REFUSED. They parse as floats but are not data - letting them
            # through would put a NaN in a numeric column, where every comparison against
            # it is false and no filter can ever find the row again.
            try:
                parsed = float(val_str)
            except ValueError:
                parsed = None
            if parsed is not None and math.isfinite(parsed):
                return parsed
            raise ValueError(f"컬럼 '{col_name}'의 값 '{value}'은(는) 올바른 숫자 형식이 아닙니다.")

    # Strip BEFORE sanitizing: the UTF-8 scrub can only remove bytes, so it can turn
    # `"abc\udcff"` into `"abc"` but never introduces whitespace - order is not
    # load-bearing today, and doing it first keeps "normalize, then sanitize" readable.
    return sanitize_to_utf8(normalize_stored_text(value))

def clean_str_value(val: Any) -> str:
    """값을 깔끔하게 문자열로 변환합니다. float인 경우 소수점 이하가 .0이면 정수로 처리합니다.

    ⚠️ **The `7.0` -> `'7'` fold does NOT diverge from PostgreSQL, and a green SQLite test
    is what makes people think it does.** (Recorded 2026-07-31 because it was got wrong
    once already, in a task brief.) `number` maps to `Float` maps to `double precision`,
    and Postgres renders `cast(col AS varchar)` of 7.0 as `'7'` - agreeing with this
    function. It is the SQLite TEST dialect that renders `'7.0'`. So a suite run on SQLite
    shows a divergence that production does not have, and reasoning from it produces a fix
    for a bug that is not there.
    `contracts/blank_predicate` scores the production dialect as an opt-in axis
    (`ASSY_CONTRACT_PG_URL`); `dialect_facts` in its vectors.json holds the measurement.

    The one float case that DOES diverge is exponent notation - `str(1e16)` is
    `'10000000000000000'` here and `'1e+16'` in Postgres. That is
    `declared_divergences.FLOAT_EXPONENT`, deliberately not chased (Lead PM, 2026-07-31),
    and it is out of reach of every production column measured that day.
    """
    if val is None:
        return ""
    if isinstance(val, float):
        if val.is_integer():
            return str(int(val))
        return str(val)
    return str(val).strip()


def is_blank_value(val: Any) -> bool:
    """THE emptiness predicate, Python side. Its SQL twin is `blank_sql_condition`.

    One name for what was previously written out as `clean_str_value(x) == ""` in
    `virtual_join_executor._resolve_one`, `AutoConfirmCollector.flush` and
    `enrichment_candidates`. Same meaning, so those keep working unchanged; having a
    name is what lets the SQL spelling below point at something instead of re-deriving
    the rule from a comment.
    """
    return clean_str_value(val) == ""


def blank_sql_condition(col_expr):
    """THE emptiness predicate, SQL side. Must answer exactly like `is_blank_value`.

    🔴 **This is only correct because `normalize_stored_text` makes storage canonical.**
    It tests NULL-or-empty and nothing else - deliberately no `btrim`, because `btrim`
    would be an incomplete imitation of `str.strip()` (1 codepoint of 29) and a complete
    one would be a 29-character class that the next schema change silently invalidates.
    Storage carries the invariant instead, so the SQL stays this short.

    If you are tempted to add trimming here, the actual bug is upstream: something wrote
    a value that did not pass through `cast_value_by_type`.

    ⚠️ **PRECONDITION: `col_expr` must be text-typed.** This compares against `''`, and
    PostgreSQL rejects `double precision = ''` outright. Casting inside instead was
    considered and rejected - a `CAST` wrapped around an already-varchar column can cost
    the planner an index. Every caller therefore passes a cast expression:
    `main.get_column_filter_condition` (`col_expr` is already `cast(raw_col, String)` on
    the blank path) and `enrichment_analysis._human_resolved_cells`
    (`cast(tgt, String)`).

    🔴 **Callers, so a future reader can check that this is still the only spelling:**
    `blank_to_null` · `not_blank_sql_condition` · `main.get_column_filter_condition`
    (`blank`/`notBlank`) · `enrichment_analysis._human_resolved_cells`. The 2026-07-31
    contract counts these by AST; a new inline `or_(x.is_(None), x == "")` is a finding,
    not a style preference.
    """
    from sqlalchemy import or_
    return or_(col_expr.is_(None), col_expr == "")


def blank_to_null(col_expr):
    """`col_expr`, or SQL NULL wherever `blank_sql_condition` calls it blank.

    The COALESCE-shaped building block the virtual-join resolved value is made of.
    Written as a CASE over `blank_sql_condition` rather than as `NULLIF(col, '')` on
    purpose: NULLIF would be a THIRD spelling of "blank", indistinguishable today and
    free to drift tomorrow. Deriving it means the resolved value cannot disagree with
    the emptiness test it is built on.
    """
    from sqlalchemy import case
    return case((blank_sql_condition(col_expr), None), else_=col_expr)


def not_blank_sql_condition(col_expr):
    """Negation of `blank_sql_condition`, spelled so NULL never leaks through.

    `~blank_sql_condition(c)` would be `NOT (c IS NULL OR c = '')`, which is correct in
    SQL's three-valued logic, but this form is the one that reads the same as the
    `notBlank` filter already in `main.get_column_filter_condition`.

    Same text-typed precondition as `blank_sql_condition`; see there.
    """
    from sqlalchemy import and_
    return and_(col_expr.isnot(None), col_expr != "")


# The BIGINT-safe magnitude guard in `numeric_text_sql`. Conservative: 9.2e18 < 2**63,
# so the CAST(... AS BIGINT) arm can never raise "bigint out of range" on PostgreSQL.
BIGINT_SAFE_NUMERIC_TEXT_BOUND = 9.2e18


def numeric_text_sql(col_expr):
    """A NUMERIC column rendered to its canonical comparison text - the SQL twin of
    `clean_str_value`'s numeric branch, INT spelling included (7.0 -> '7', 7.5 -> '7.5').

    Exists for `virtual_join_executor.resolved_expression` (board item N7, user report
    2026-08-02): a numeric expose column cannot sit in `COALESCE(..., '<label>')` as a
    number. On PostgreSQL the pre-fix expression died twice over - `blank_to_null`'s
    `col = ''` arm violates `blank_sql_condition`'s stated text-typed precondition
    (`double precision = ''` is refused outright), and `COALESCE(double precision, text)`
    cannot be matched to one type. The user ruling: cast to STRING for the COALESCE, and
    spell integral values as INT (a slot comes back as 3, never 3.0).

    Why not a plain `cast(col, String)`: the dialects disagree about it. PostgreSQL
    renders float8 7.0 as '7' (shortest round-trip - `contracts/blank_predicate`
    `dialect_facts`, measured 2026-07-31); SQLite renders '7.0'. Python's
    `clean_str_value` folds integral floats through `str(int(v))`. This expression
    produces the int spelling ON EVERY DIALECT instead of leaning on the agreement
    Postgres happens to share with Python:

        CASE WHEN col BETWEEN -9.2e18 AND 9.2e18
             THEN CASE WHEN CAST(col AS BIGINT) = col
                       THEN CAST(CAST(col AS BIGINT) AS VARCHAR)
                       ELSE CAST(col AS VARCHAR) END
             ELSE CAST(col AS VARCHAR) END

    - NULL needs no arm of its own: every branch propagates NULL (CAST(NULL) is NULL,
      `NULL = col` is UNKNOWN -> else -> CAST(NULL AS VARCHAR) is NULL). That is also
      why this does NOT wrap `blank_to_null`: for a number the blank rule genuinely is
      IS NULL alone - a number is never `''` (the blank-predicate contract's own
      wording: "numbers are not text; the SQL blank arm is IS NULL"). Adding the text
      blank test here would be a per-row no-op bought at WHERE-clause cost on a
      10-million-row scan.
    - The magnitude guard is what keeps the BIGINT cast from raising on PostgreSQL for
      |v| >= 2**63. Beyond the bound the plain cast runs and the dialects may reach
      exponent notation - the same reach as `declared_divergences.FLOAT_EXPONENT`
      (deliberately not chased, Lead PM 2026-07-31), out of range of every production
      column measured that day. WITHIN the bound this actually agrees with Python even
      at 1e16, where the plain Postgres cast does not.
    - Dialect rounding differences in the BIGINT cast (SQLite truncates 3.7 -> 3,
      Postgres rounds 3.7 -> 4) cannot change any answer: the folded spelling is used
      only when the cast round-trips EQUAL to the original value, i.e. only when the
      value was integral to begin with.
    """
    from sqlalchemy import case, cast, String, BigInteger, and_
    as_big = cast(col_expr, BigInteger)
    folded = case((as_big == col_expr, cast(as_big, String)),
                  else_=cast(col_expr, String))
    return case(
        (and_(col_expr >= -BIGINT_SAFE_NUMERIC_TEXT_BOUND,
              col_expr <= BIGINT_SAFE_NUMERIC_TEXT_BOUND), folded),
        else_=cast(col_expr, String),
    )


# ---------------------------------------------------------------------------
# Rendering a column to its canonical comparison TEXT - one funnel, every type
#
# [Board item N8, 2026-08-04. Why this is a family and not a second numeric patch]
# `virtual_join_executor.resolved_expression` builds `COALESCE(<parts>, '<label>')`.
# The label is TEXT, so EVERY part must be text. N7 shipped that insight as "numeric
# needs a cast", and the next type through the same door - `datetime` - died with the
# identical failure (`InvalidDatetimeFormat`, measured on PostgreSQL 18.3). Boolean
# dies too (`InvalidTextRepresentation`, same measurement), and on SQLite it does not
# even crash: it answers `True` for every unmatched row, which is worse.
#
# So the question is not "which types need a cast" but "which types are ALREADY text".
# `column_text_sql` below inverts the test accordingly: only the string family goes
# through untouched; everything else is rendered, and anything this file has never
# heard of falls to a plain CAST rather than to a 500. A type added tomorrow cannot
# reopen this defect.
#
# THE COLUMN TYPES THIS SYSTEM CAN ACTUALLY PUT HERE (measured 2026-08-04):
# `models.init_dynamic_models` maps `table_config` `column_types` to exactly three
# SQLAlchemy types - `number`->Float, `datetime`->DateTime(timezone=True), everything
# else->String - plus the shared metadata columns, which add Boolean
# (`is_graph_synced`, `needs_graph_rollback`) and DateTime (`created_at`, `updated_at`,
# `graph_synced_at`). A metadata NAME declared in `column_types` is skipped by the
# model builder but still resolves to the metadata column, and `virtual_join_config`
# validates `expose` against `column_types` keys - so Boolean and DateTime are both
# reachable through an ordinary declaration. The live config declares
# `production_plan.created_at/updated_at` as `datetime` today.
# Numeric / Integer / Enum / JSON / ARRAY / UUID are NOT produced by the model builder;
# they are handled defensively (Enum explicitly, the rest by the CAST fallback) because
# "not produced today" is exactly the reasoning that left `datetime` broken.
#
# EACH RENDERER HAS A PYTHON TWIN, and that pairing is the point. The SQL text is what
# a filter / `?q=` / CSV export compares; the twin is what the row payload carries into
# the browser. A renderer added without its twin re-creates the seam this closes.
# ---------------------------------------------------------------------------

# The canonical temporal text. UTC, space-separated, microseconds ALWAYS six digits.
#
# 🔴 It is pinned, not inherited from the dialect, and here is what the dialect default
# actually is (PostgreSQL 18.3, live, 2026-08-04): `CAST(timestamptz AS varchar)` renders
# `2026-08-04 06:23:39.123456+00` in the SESSION's TimeZone (measured `+09` here, because
# the GUC is Asia/Seoul) and DROPS the fractional part entirely when it is zero. Both
# halves of that are moving targets - the offset follows a server GUC, the width follows
# the value - so a text comparison built on it would answer differently on two servers
# holding the same row. SQLite, by contrast, stores DATETIME as this exact literal text,
# which is why the default arm of `temporal_text_sql` is a plain CAST.
#
# Fixed width also buys an accident that is worth naming: lexical order equals
# chronological order, so `lessThan` on a resolved temporal column is not a lie.
TEMPORAL_TEXT_FORMAT = "%Y-%m-%d %H:%M:%S.%f"
_PG_TEMPORAL_TEXT_FORMAT = "YYYY-MM-DD HH24:MI:SS.US"


def _install_temporal_text_construct():
    """The one dialect-branching construct in this module, built once at import.

    A `@compiles` variant rather than a runtime `if dialect == 'postgresql'` because the
    expression is handed to callers that never see a connection (`resolved_expression`
    takes a Session but the expression outlives the call, and the CSV export re-binds it
    to a streaming statement). Letting the compiler choose keeps one expression object
    correct on every bind.
    """
    from sqlalchemy import String as _String, cast as _cast, func as _func
    from sqlalchemy.ext.compiler import compiles
    from sqlalchemy.sql.functions import FunctionElement

    class _TemporalText(FunctionElement):
        type = _String()
        name = "temporal_text"
        inherit_cache = True

    @compiles(_TemporalText)
    def _default(element, compiler, **kw):
        # SQLite (this suite) stores DATETIME as 'YYYY-MM-DD HH:MM:SS.ffffff' - the
        # canonical spelling verbatim - so the plain cast IS the pinned format. Any
        # other dialect lands here too; that is the no-crash floor, not a promise
        # that its spelling matches. Add a variant when a third dialect appears.
        return compiler.process(_cast(list(element.clauses)[0], _String), **kw)

    @compiles(_TemporalText, "postgresql")
    def _postgresql(element, compiler, **kw):
        col = list(element.clauses)[0]
        # `timezone('UTC', ts)` is the function spelling of `ts AT TIME ZONE 'UTC'`.
        return compiler.process(
            _func.to_char(_func.timezone("UTC", col), _PG_TEMPORAL_TEXT_FORMAT), **kw)

    return _TemporalText


_TemporalText = _install_temporal_text_construct()


def temporal_text_sql(col_expr):
    """A DATE/TIME column rendered to `TEMPORAL_TEXT_FORMAT`. SQL twin of
    `temporal_text_value`.

    NULL propagates (CAST and `to_char` both return NULL for NULL), which is the whole
    blank rule for a temporal column: a timestamp is never `''`, so - exactly as with
    `numeric_text_sql` - this is deliberately NOT wrapped in `blank_to_null`. Wrapping it
    would put `col = ''` back in front of a non-text column, which is the crash.
    """
    return _TemporalText(col_expr)


def temporal_text_value(value):
    """Python twin of `temporal_text_sql`: the same instant, the same spelling.

    Aware values are converted to UTC first, so the text does not depend on the
    connection's session timezone. Naive values are taken as already-UTC (that is what
    the SQLite test dialect hands back, and the only shape a naive column can be here).
    """
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc)
        return value.strftime(TEMPORAL_TEXT_FORMAT)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day).strftime(TEMPORAL_TEXT_FORMAT)
    return value


def boolean_text_sql(col_expr):
    """A BOOLEAN column rendered to `'true'` / `'false'`. SQL twin of
    `boolean_text_value`.

    The NULL arm is written out FIRST and on purpose: `CASE WHEN col THEN ... ELSE ...`
    routes NULL to the ELSE, so without it every unmatched row would resolve to
    `'false'` - a value - instead of folding into the unresolved label.

    Spelling `'true'`, not Python's `'True'`: the payload carries the raw boolean, JSON
    writes it as `true`, and the browser prints `true`. `clean_str_value(True)` is
    `'True'` and is the one spelling nobody ever sees. (PostgreSQL's own
    `CAST(bool AS varchar)` agrees with this choice - measured 18.3, 2026-08-04 - but the
    CASE is written out anyway so SQLite, which would say `'1'`, cannot disagree.)
    """
    from sqlalchemy import case
    return case((col_expr.is_(None), None), (col_expr, "true"), else_="false")


def boolean_text_value(value):
    """Python twin of `boolean_text_sql`."""
    if value is None or not isinstance(value, bool):
        return value
    return "true" if value else "false"


def column_text_sql(col_expr):
    """THE funnel: any column expression rendered to the canonical comparison text.

    🔴 The test is "is this ALREADY text", not "is this one of the types we know to be a
    problem". The second shape is what shipped N7 and left `datetime` and `boolean`
    holding the identical crash; an unknown type therefore falls to a CAST, never to the
    raw column.

    `Enum` is pulled out of the string family explicitly: SQLAlchemy models it as a
    String subclass, but on PostgreSQL a native enum column compared to `''` raises the
    same way a float does. No dynamic table declares one - which is precisely the
    sentence that was true of `datetime` last week.
    """
    from sqlalchemy import cast, String
    from sqlalchemy.sql import sqltypes

    col_type = getattr(col_expr, "type", None)
    if isinstance(col_type, (sqltypes.Numeric, sqltypes.Float, sqltypes.Integer)):
        return numeric_text_sql(col_expr)
    if isinstance(col_type, sqltypes.Boolean):
        return boolean_text_sql(col_expr)
    if isinstance(col_type, (sqltypes.DateTime, sqltypes.Date, sqltypes.Time)):
        return temporal_text_sql(col_expr)
    if isinstance(col_type, sqltypes.String) and not isinstance(col_type, sqltypes.Enum):
        return blank_to_null(col_expr)
    # Unknown, or text-shaped but not text-typed. Cast FIRST so `blank_sql_condition`'s
    # stated text-typed precondition holds on every dialect.
    return blank_to_null(cast(col_expr, String))


def resolved_text_value(value):
    """Python twin of `column_text_sql`, for the value that goes into the row PAYLOAD.

    Renders exactly the families whose SQL spelling this module pins to text, so the
    grid paints the string a filter / `?q=` / CSV export will compare against.

    🔴 Numbers ride RAW, and that is a recorded gap, not an oversight. The numeric payload
    has shipped as a JSON number since N7; the browser stringifies it with JavaScript's
    rules, which agree with the SQL text everywhere except a measured band
    (`contracts/blank_predicate` `NUMERIC_BROWSER_SPELLING`, board item N9). Rendering it
    here would close that band AND change a shipped cell value's type, which is a
    boundary-contract decision for the Lead PM - not one to take in passing.
    """
    if isinstance(value, bool):
        return boolean_text_value(value)
    if isinstance(value, (datetime, date)):
        return temporal_text_value(value)
    return value


def comparison_text_value(value):
    """A FILTER value rendered the way the resolved column spells it.

    `main.get_column_filter_condition` bridges a non-string filter value against a
    text-resolved virtual column with this. `clean_str_value` alone is not enough: it
    spells a boolean `'True'` where the column spells `'true'`, and a datetime with
    whatever `str()` gives rather than `TEMPORAL_TEXT_FORMAT`.
    """
    rendered = resolved_text_value(value)
    return rendered if isinstance(rendered, str) else clean_str_value(rendered)


def get_row_by_business_key(db: Session, table_name: str, key_value: Any):
    """테이블별 비즈니스 키를 기반으로 행을 조회합니다. (인덱스 컬럼 사용으로 최적화)"""
    target_val = str(key_value).strip() if key_value is not None else ""
    if not target_val:
        return None
        
    table_model = models.DYNAMIC_TABLES.get(table_name)
    if not table_model:
        return None
        
    return db.query(table_model).filter(
        table_model.business_key_val == target_val
    ).first()

def resolve_priority_map(table_name: str = None) -> dict:
    """[QA G1-⑥] 소스 서열 맵 해석의 단일 원천 — 테이블별 source_priority 커스텀 포함.

    compute_priority_value(표시값 레이어링)와 graph_materializer(엣지 provenance)가
    같은 맵을 공유한다(서열 이원화 금지).
    """
    priority_map = SOURCE_PRIORITY
    if table_name:
        table_info = TABLE_CONFIG.get(table_name, {})
        custom_priority = table_info.get("source_priority")
        if custom_priority and isinstance(custom_priority, dict):
            priority_map = custom_priority
    return priority_map


def get_source_priority(source_name: str, table_name: str = None) -> int:
    """소스명 → 우선순위 값(작을수록 우선, 미등재 99). 레이어링과 동일 서열."""
    return resolve_priority_map(table_name).get(source_name, 99)


def compute_priority_value(sources: dict, manual_priority_source: str = None, table_name: str = None):
    """여러 소스들 중 가장 우선순위가 높은 값을 결정합니다."""
    if not sources:
        return None, None

    if manual_priority_source and manual_priority_source in sources:
        val_data = sources[manual_priority_source]
        val = val_data["value"] if isinstance(val_data, dict) and "value" in val_data else val_data
        return val, manual_priority_source

    priority_map = resolve_priority_map(table_name)

    sorted_sources = sorted(
        sources.keys(),
        key=lambda k: priority_map.get(k, 99)
    )
    
    top_source = sorted_sources[0]
    val_data = sources[top_source]
    val = val_data["value"] if isinstance(val_data, dict) and "value" in val_data else val_data
    return val, top_source

def create_audit_log(db: Session, table_name: str, row_id: str, col_name: str, old_val: Any, new_val: Any, source: str, user: str, transaction_id: str = None, business_key: str = None, add_to_cache: bool = True):
    """감사 로그를 기록합니다. (저장 전 인코딩 정제 수행)

    add_to_cache=False는 인메모리 캐시 추가뿐 아니라 DB persist(db.add)도 생략한다.
    이 경우 호출자가 반환된 log_dict를 모아 commit 전에 bulk_insert_audit_logs로
    직접 DB에 적재할 책임을 진다.
    """
    if not transaction_id:
        transaction_id = str(uuid6.uuid7())

    from datetime import timezone
    ts = datetime.now(timezone.utc)
    
    clean_old = sanitize_to_utf8(old_val)
    clean_new = sanitize_to_utf8(new_val)

    # [P2-C9] 값 길이 상한 — sanitize_to_utf8은 인코딩 정제만 하므로 길이는 무제한이었다.
    # 대형 텍스트 셀(맵 문자열류)이 대상이 되면 created_logs 500건 절단 후에도 페이로드가
    # 수십 MB가 될 수 있다(2026-07-25 이벤트 루프 동결 인시던트의 잔여 경로).
    # 절단은 **DB 저장본과 통지 dict 양쪽에 동일 적용**하고, 절단 사실은 값 안의 마커로 명시된다.
    clean_old, old_truncated = truncate_audit_value(clean_old)
    clean_new, new_truncated = truncate_audit_value(clean_new)
    if old_truncated or new_truncated:
        _warn_audit_truncation_once(table_name, col_name)

    if add_to_cache:
        log = models.AuditLog(
            table_name=table_name,
            row_id=row_id,
            column_name=col_name,
            old_value=clean_old,
            new_value=clean_new,
            source_name=source,
            updated_by=user,
            transaction_id=transaction_id,
            timestamp=ts,
            business_key=business_key
        )
        db.add(log)

    log_dict = {
        "id": 0,
        "table_name": table_name,
        "row_id": row_id,
        "column_name": col_name,
        "old_value": clean_old,
        "new_value": clean_new,
        "source_name": source,
        "updated_by": user,
        "transaction_id": transaction_id,
        "business_key": business_key,
        "timestamp": ts
    }
    if add_to_cache:
        from audit_cache import audit_cache
        audit_cache.add_log(log_dict)
        
    return log_dict

def bulk_insert_audit_logs(db: Session, logs: list[dict]):
    """AuditLog를 Bulk Insert로 초고속 적재합니다."""
    if not logs:
        return
    mappings = []
    for l in logs:
        mappings.append({
            "table_name": l["table_name"],
            "row_id": l["row_id"],
            "column_name": l["column_name"],
            "old_value": l["old_value"],
            "new_value": l["new_value"],
            "source_name": l["source_name"],
            "updated_by": l["updated_by"],
            "transaction_id": l["transaction_id"],
            "timestamp": l["timestamp"],
            "business_key": l.get("business_key")
        })
    db.bulk_insert_mappings(models.AuditLog, mappings)


# ── 재교정률 (re-correction rate) — SYSTEM_OVERVIEW §1 핵심가치 #1 "최소 공수 교정"의 계기 ──
#
# 정의: 창(window) 안에서 사람이 쓴 셀 중, 사람이 **두 번 이상** 쓴 셀의 비율.
#       셀 = (table_name, row_id, column_name). 낮을수록 좋다.
#
# 이 값이 왜 그렇게 계산되는지(각 결정의 근거)는 아래 주석에 남긴다. 숫자만 보고
# 정의를 되짚을 수 없으면, 이 지표는 다시 "그럴듯해 보이는 틀린 숫자"가 된다.

RECORRECTION_WINDOW_DAYS = 7
# 감사 로그는 프루닝되지 않는다(2026-07-27 확인: outbox의 7일 보존은 database_outbox 전용이고
# audit_logs를 지우는 운영 경로는 존재하지 않는다 — 실측 2,628,453행이 프로젝트 개시일부터
# 연속). 창을 7일로 고정하는 것은 보존 한계 때문이 아니라 **지표를 현재 마찰에 반응하게**
# 하기 위해서다. 전 기간 창은 과거 누적에 희석돼 어떤 회귀에도 움직이지 않는다.


def _is_json_null(col):
    """JSON 컬럼이 '값 없음'인지 — SQL NULL과 JSON null 양쪽을 덮는다.

    AuditLog.old/new_value는 SQLAlchemy JSON 타입이라 파이썬 None이 SQL NULL이 아니라
    JSON 'null'로 저장된다(실측: old_value IS NULL = 0행, old_value::text='null' = 4,290행).
    한쪽만 검사하면 조용히 빗나간다.
    """
    import sqlalchemy as sa
    return sa.or_(col.is_(None), sa.cast(col, sa.String) == "null")


def get_recorrection_stats(db: Session, window_days: int = RECORRECTION_WINDOW_DAYS) -> dict:
    """사람이 같은 셀을 두 번 이상 고친 비율을 반환한다.

    반환: {window_days, measured_cells, recorrected_cells, rate_pct}
    `rate_pct`는 분모가 0이면 None — 표본이 없을 때 0%로 위장하지 않는다.
    분모(`measured_cells`)는 **항상 함께** 반환한다. 분모 없는 비율은 읽을 수 없다.
    """
    import sqlalchemy as sa
    from datetime import timezone, timedelta

    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    AL = models.AuditLog

    inner = (
        db.query(
            AL.table_name.label("t"),
            AL.row_id.label("r"),
            AL.column_name.label("c"),
            # [함정 2] 한 transaction_id 안의 여러 행은 **한 번의 사람 행위**다.
            # 엑셀 붙여넣기 한 번이 같은 셀을 두 번 건드릴 수 있다(실측: 643개 그룹/1,286행).
            # 행 수로 세면 44일 기준 3.88%로 부풀고, 트랜잭션으로 접으면 2.96%다.
            sa.func.count(sa.distinct(AL.transaction_id)).label("txs"),
        )
        .filter(
            # [함정 1] 자동 소스 제외. 파서/체인이 같은 셀을 반복해 덮는 것은 정상 동작이지
            # 사람의 재교정이 아니다. 자동 소스는 파일명을 소스명으로 쓰기 때문에 값 집합이
            # 열려 있다 — 블랙리스트가 아니라 USER_SOURCE 양성 선택이어야 한다.
            AL.source_name == USER_SOURCE,
            AL.timestamp >= cutoff,
            # [함정 3] "같은 값을 다시 쓴 것"의 처리.
            # 실제 값이 같은 재기입은 감사 로그에 **애초에 들어오지 않는다** —
            # apply_row_update_internal의 has_changed 가드가 값이 바뀐 컬럼만 기록한다.
            # (실측: 값이 동일한 user 행 중 진짜 동일값 재기입은 0건.)
            # 남는 것은 신규 행 생성 시 is_new=True가 가드를 건너뛰며 남기는 null→null 행뿐이다
            # (실측 4,290행). 이는 사람이 **빈칸으로 둔** 컬럼이지 쓴 셀이 아니므로 분모에서 뺀다.
            sa.not_(sa.and_(_is_json_null(AL.old_value), _is_json_null(AL.new_value))),
        )
        .group_by(AL.table_name, AL.row_id, AL.column_name)
        .subquery()
    )

    # FILTER 절 대신 CASE — SQLite/PostgreSQL 양쪽에서 동일하게 동작한다.
    measured, recorrected = db.query(
        sa.func.count(),
        sa.func.coalesce(sa.func.sum(sa.case((inner.c.txs > 1, 1), else_=0)), 0),
    ).select_from(inner).one()

    measured = int(measured or 0)
    recorrected = int(recorrected or 0)
    return {
        "window_days": window_days,
        "measured_cells": measured,
        "recorrected_cells": recorrected,
        "rate_pct": round(100.0 * recorrected / measured, 2) if measured else None,
    }


# ── 완료까지의 상호작용 점수 (interaction score to completion) ────────────────
#
# SYSTEM_OVERVIEW §1 핵심가치 #1 "최소 공수 교정"의 **정본 계기**(사용자 2026-07-29).
# 한 교정 tx를 완료하는 데 사람이 쓴 손의 양. 낮을수록 좋다.
#
#     점수(tx) = key×w_key + mouse×w_mouse + nav×w_nav
#
# 재교정률(위 get_recorrection_stats)은 보조 계기로 강등됐다 — 같은 셀을 두 번 고쳤다는
# 사실만으로는 UI 공수 탓인지 데이터 품질 탓인지 갈라지지 않기 때문이다. 이 계기는 그
# 중간 추론을 건너뛰고 공수 자체를 잰다.
#
# 이 값은 **소급 산출이 불가능**하다(과거 세션에 클릭 로그가 없다). 계측이 붙은 시점부터의
# 데이터만 존재하므로, 교정 표면을 고치기 전에 확보한 기준선이 유일한 "before"다.

EFFORT_WINDOW_DAYS = 7
# 재교정률과 같은 창을 쓴다. 이유도 같다 — 지표가 **현재 마찰**에 반응해야 하고, 전 기간
# 누적은 어떤 회귀에도 움직이지 않는다. 두 계기가 같은 창을 보면 나란히 읽을 수도 있다.


def record_interaction_effort(db: Session, transaction_id: str, session_id: str,
                              key: int, mouse: int, nav: int,
                              nav_preserved: int = 0) -> bool:
    """한 tx의 원시 상호작용 카운트를 기록한다. 기록됐으면 True.

    **계측은 계측 대상을 절대 깨뜨리지 않는다.** 이 함수는 교정이 이미 커밋된 뒤에
    별도 트랜잭션으로 호출되며, 실패하면 로그만 남기고 False를 돌려준다. 공수 한 건을
    놓치는 것이 사용자의 교정을 잃는 것보다 언제나 낫다.

    같은 tx가 재도달하면(클라 재시도) **첫 기록이 이긴다** — UNIQUE 제약 위반을 잡아
    조용히 통과시킨다. 재전송은 사람이 새로 쓴 공수가 아니다.
    """
    from sqlalchemy.exc import IntegrityError
    try:
        db.add(models.InteractionEffortLog(
            transaction_id=transaction_id,
            session_id=session_id,
            key_count=key, mouse_count=mouse, nav_count=nav,
            nav_preserved_count=nav_preserved,
        ))
        db.commit()
        return True
    except IntegrityError:
        # 같은 transaction_id가 이미 있다 = 재시도. 첫 기록 보존.
        db.rollback()
        return False
    except Exception as e:
        db.rollback()
        print(f"[EffortMetric] failed to record effort for tx {transaction_id}: {e}")
        return False


def get_effort_stats(db: Session, weights: dict,
                     window_days: int = EFFORT_WINDOW_DAYS) -> dict:
    """창 안의 상호작용 점수를 **세션별 평균 → 세션 간 평균**으로 반환한다.

    반환: {window_days, avg_score, tx_count, session_count, weights, measured_ratio}

    집계 단위가 왜 두 단계인가(사용자 지정 "세션별 평균"): tx를 통째로 평균하면 한 세션이
    500건을 처리한 날 그 세션이 전체 평균을 지배한다. 세션을 먼저 접으면 각 작업 세션이
    같은 무게를 갖는다 — 재교정률이 transaction_id로 사람 행위를 접는 것과 같은 이유다.

    `measured_ratio`(계측 tx / 전체 사람 tx)는 **필수 동반 값**이다. 계측은 클라이언트가
    보내 줄 때만 이뤄지므로 커버리지가 절대 1.0이라고 가정할 수 없고, 비율 없이 내보낸
    평균은 측정되지 않은 범위까지 대표하는 것처럼 읽힌다(재교정률의 분모와 같은 규율).
    """
    import sqlalchemy as sa
    from datetime import timezone, timedelta

    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    EL = models.InteractionEffortLog

    w_key = float(weights.get("key", 1))
    w_mouse = float(weights.get("mouse", 3))
    w_nav = float(weights.get("nav", 5))
    # 컨텍스트 유지 전이의 배점. 기본 0 = 오늘의 점수는 이 항이 없던 때와 **완전히 동일**하다.
    # 그런데도 카운트를 보관하는 이유: 면제 판단이 틀린 것으로 밝혀졌을 때 이 숫자 하나만
    # 바꿔 과거 데이터를 재채점할 수 있게 하기 위해서다(수집 시점에 버리면 되돌릴 길이 없다).
    w_nav_preserved = float(weights.get("nav_preserved", 0))

    # 1단계: tx당 점수 → 세션별 평균.
    per_session = (
        db.query(
            EL.session_id.label("s"),
            sa.func.avg(
                EL.key_count * w_key + EL.mouse_count * w_mouse + EL.nav_count * w_nav
                + EL.nav_preserved_count * w_nav_preserved
            ).label("avg_score"),
            sa.func.count().label("txs"),
        )
        .filter(EL.timestamp >= cutoff)
        .group_by(EL.session_id)
        .subquery()
    )

    # 2단계: 세션 간 평균. 세션 수·계측 tx 총수를 같은 스캔에서 얻는다.
    avg_of_avgs, session_count, tx_count = db.query(
        sa.func.avg(per_session.c.avg_score),
        sa.func.count(),
        sa.func.coalesce(sa.func.sum(per_session.c.txs), 0),
    ).select_from(per_session).one()

    tx_count = int(tx_count or 0)
    session_count = int(session_count or 0)

    # 분모: 같은 창에서 **사람이 만든 전체 tx** 수. audit_logs의 부분 커버링 인덱스
    # (idx_audit_user_recorrection: timestamp + INCLUDE transaction_id WHERE source_name='user')가
    # 그대로 이 쿼리도 커버한다 — 새 인덱스가 필요 없다.
    AL = models.AuditLog
    total_user_tx = (
        db.query(sa.func.count(sa.distinct(AL.transaction_id)))
        .filter(AL.source_name == USER_SOURCE, AL.timestamp >= cutoff)
        .scalar()
    ) or 0
    total_user_tx = int(total_user_tx)

    return {
        "window_days": window_days,
        "avg_score": round(float(avg_of_avgs), 2) if avg_of_avgs is not None else None,
        "tx_count": tx_count,
        "session_count": session_count,
        "weights": {"key": w_key, "mouse": w_mouse, "nav": w_nav,
                    "nav_preserved": w_nav_preserved},
        # 표본이 없으면 비율도 없다 — 0.0은 "전부 미계측"과 "측정할 것이 없었다"를 섞어버린다.
        "measured_ratio": round(tx_count / total_user_tx, 4) if total_user_tx else None,
    }


def bulk_upsert_cell_sources(db: Session, mappings: list[dict]):
    if not mappings:
        return
    
    # Deduplicate mappings to avoid psycopg2.errors.CardinalityViolation in PostgreSQL.
    # Keep the last (most recent) dictionary for each unique constraint key.
    deduped = {}
    for item in mappings:
        key = (item['table_name'], item['row_id'], item['column_name'], item['source_name'])
        deduped[key] = item
    
    # Sort deterministically by key to prevent Deadlocks in PostgreSQL.
    sorted_keys = sorted(deduped.keys())
    deduped_mappings = [deduped[k] for k in sorted_keys]
    
    is_sqlite = db.bind.dialect.name == "sqlite"
    if is_sqlite:
        from sqlalchemy.dialects.sqlite import insert as upsert_insert
    else:
        from sqlalchemy.dialects.postgresql import insert as upsert_insert
        
    stmt = upsert_insert(models.CellSource).values(deduped_mappings)
    stmt = stmt.on_conflict_do_update(
        index_elements=['table_name', 'row_id', 'column_name', 'source_name'],
        set_={
            'value': stmt.excluded.value,
            'updated_by': stmt.excluded.updated_by,
            'ingested_at': stmt.excluded.ingested_at
        }
    )
    db.execute(stmt)

def bulk_upsert_cell_overwrites(db: Session, mappings: list[dict]):
    if not mappings:
        return
    
    # Deduplicate mappings to avoid psycopg2.errors.CardinalityViolation in PostgreSQL.
    # Keep the last (most recent) dictionary for each unique constraint key.
    deduped = {}
    for item in mappings:
        key = (item['table_name'], item['row_id'], item['column_name'])
        deduped[key] = item
    
    # Sort deterministically by key to prevent Deadlocks in PostgreSQL.
    sorted_keys = sorted(deduped.keys())
    deduped_mappings = [deduped[k] for k in sorted_keys]
    
    is_sqlite = db.bind.dialect.name == "sqlite"
    if is_sqlite:
        from sqlalchemy.dialects.sqlite import insert as upsert_insert
    else:
        from sqlalchemy.dialects.postgresql import insert as upsert_insert
        
    stmt = upsert_insert(models.CellOverwrite).values(deduped_mappings)
    stmt = stmt.on_conflict_do_update(
        index_elements=['table_name', 'row_id', 'column_name'],
        set_={
            'is_overwrite': stmt.excluded.is_overwrite,
            'updated_by': stmt.excluded.updated_by,
            'updated_at': stmt.excluded.updated_at,
            'manual_priority_source': stmt.excluded.manual_priority_source
        }
    )
    db.execute(stmt)

def bulk_delete_cell_overwrites(db: Session, delete_keys: list[tuple[str, str, str]]):
    if not delete_keys:
        return
        
    from sqlalchemy import and_, or_
    conds = []
    for t_name, r_id, col_name in delete_keys:
        conds.append(
            and_(
                models.CellOverwrite.table_name == t_name,
                models.CellOverwrite.row_id == r_id,
                models.CellOverwrite.column_name == col_name
            )
        )
    db.query(models.CellOverwrite).filter(or_(*conds)).delete(synchronize_session=False)

def _get_or_create_row(db: Session, table_model: Any, update_item: schemas.GeneralUpdateItem, row_cache: dict, table_name: str) -> tuple[Any, bool]:
    """대상 행 객체를 캐시 또는 DB에서 획득하고, 존재하지 않으면 신규 생성합니다."""
    row = None
    if row_cache is not None:
        if update_item.row_id and update_item.row_id in row_cache:
            row = row_cache[update_item.row_id]
        elif update_item.business_key_val and update_item.business_key_val in row_cache:
            row = row_cache[update_item.business_key_val]
            
    if not row:
        if update_item.row_id:
            row = db.query(table_model).filter(table_model.row_id == update_item.row_id).first()
        if not row and update_item.business_key_val:
            row = get_row_by_business_key(db, table_name, update_item.business_key_val)
            
        if row and row_cache is not None:
            row_cache[row.row_id] = row
            if row.business_key_val:
                row_cache[row.business_key_val] = row
    
    is_new = False
    if not row:
        from sqlalchemy.sql import func
        row = table_model(
            row_id=update_item.row_id or str(uuid6.uuid7()),
            updated_at=func.now()
        )
        db.add(row)
        is_new = True
        if row_cache is not None:
            row_cache[row.row_id] = row
            if row.business_key_val:
                row_cache[row.business_key_val] = row
            
    return row, is_new

def _update_row_business_key(row: Any, key_col: str, update_item: schemas.GeneralUpdateItem, row_cache: dict):
    """비즈니스 키가 업데이트 항목에 있거나 기존 행에 존재하면 DYNAMIC 테이블의 business_key_val 필드를 최신화합니다."""
    if key_col and key_col in update_item.updates:
        new_bk_val = update_item.updates[key_col]
        if new_bk_val is not None:
            str_val = str(new_bk_val).strip()
            if row.business_key_val != str_val:
                row.business_key_val = str_val
                if row_cache is not None:
                    row_cache[str_val] = row
    elif key_col and hasattr(row, key_col):
        existing_val = getattr(row, key_col)
        new_bk_val = existing_val.get("value") if isinstance(existing_val, dict) else existing_val
        if new_bk_val is not None:
            str_val = str(new_bk_val).strip()
            if row.business_key_val != str_val:
                row.business_key_val = str_val
                if row_cache is not None:
                    row_cache[str_val] = row

def _load_metadata_row_cell(db: Session, table_name: str, row_id: str, col_name: str, is_new: bool, sources_cache: dict, overwrites_cache: dict, cell_sources_to_upsert: dict, cell_overwrites_to_upsert: dict) -> tuple[list, Any]:
    """해당 셀의 CellSource 리스트와 CellOverwrite 객체를 캐시 혹은 DB로부터 획득합니다."""
    key = (row_id, col_name)
    
    # CellSource 로드
    if sources_cache is not None:
        if key not in sources_cache:
            if is_new:
                col_srcs = []
            else:
                col_srcs = db.query(models.CellSource).filter(
                    models.CellSource.table_name == table_name,
                    models.CellSource.row_id == row_id,
                    models.CellSource.column_name == col_name
                ).all()
                if cell_sources_to_upsert is not None:
                    for s in col_srcs:
                        db.expunge(s)
            sources_cache[key] = col_srcs
        else:
            col_srcs = sources_cache[key]
    else:
        if is_new:
            col_srcs = []
        else:
            col_srcs = db.query(models.CellSource).filter(
                models.CellSource.table_name == table_name,
                models.CellSource.row_id == row_id,
                models.CellSource.column_name == col_name
            ).all()
            if cell_sources_to_upsert is not None:
                for s in col_srcs:
                    db.expunge(s)
            
    # CellOverwrite 로드
    if overwrites_cache is not None:
        if key not in overwrites_cache:
            if is_new:
                ow = None
            else:
                ow = db.query(models.CellOverwrite).filter(
                    models.CellOverwrite.table_name == table_name,
                    models.CellOverwrite.row_id == row_id,
                    models.CellOverwrite.column_name == col_name
                ).first()
                if ow and cell_overwrites_to_upsert is not None:
                    db.expunge(ow)
            overwrites_cache[key] = ow
        else:
            ow = overwrites_cache[key]
    else:
        if is_new:
            ow = None
        else:
            ow = db.query(models.CellOverwrite).filter(
                models.CellOverwrite.table_name == table_name,
                models.CellOverwrite.row_id == row_id,
                models.CellOverwrite.column_name == col_name
            ).first()
            if ow and cell_overwrites_to_upsert is not None:
                db.expunge(ow)
            
    return col_srcs, ow

def apply_row_update_internal(
    db: Session, 
    table_name: str, 
    update_item: schemas.GeneralUpdateItem,
    row_cache: dict = None,
    sources_cache: dict = None,
    overwrites_cache: dict = None,
    transaction_id: str = None,
    logs_to_cache: list = None,
    cell_sources_to_upsert: dict = None,
    cell_overwrites_to_upsert: dict = None,
    cell_overwrites_to_delete: set = None,
    deleted_row_ids: list = None,
    version_stats: dict = None
) -> tuple[Any, bool, list[str]]:
    """[통합 코어] row_id 또는 business_key 기반으로 행을 찾아 업데이트하고 메타데이터 테이블을 갱신합니다."""
    system_cols = ["created_at", "updated_at", "row_id", "id", "updated_by", "is_graph_synced", "needs_graph_rollback", "graph_synced_at"]
    
    table_model = models.DYNAMIC_TABLES.get(table_name)
    if not table_model:
        raise ValueError(f"Table model for '{table_name}' is not initialized. Please define the table in config/table_config.json and restart the server/watcher processes.")
    config = TABLE_CONFIG.get(table_name, {})
    key_col = config.get("business_key")
    composite_src = config.get("composite_key_source")
    composite_sep = config.get("composite_key_separator", "_")

    # 인제션 매칭을 위해 updates 기반 선제 키 조립
    if not update_item.row_id and not update_item.business_key_val and composite_src and key_col:
        has_all_srcs = all(col in update_item.updates for col in composite_src)
        if has_all_srcs:
            vals = [clean_str_value(update_item.updates.get(col)) for col in composite_src]
            if all(v != "" for v in vals):
                computed_key = composite_sep.join(vals)
                update_item.business_key_val = computed_key
                if key_col not in update_item.updates:
                    update_item.updates[key_col] = computed_key

    row, is_new = _get_or_create_row(db, table_model, update_item, row_cache, table_name)
    changed_cols = []
    config = TABLE_CONFIG.get(table_name, {})
    key_col = config.get("business_key")

    # [Version gate] Judged HERE - after the row is resolved (so the verdict sees the row
    # the write would actually land on, however it was keyed) and before a single cell is
    # touched. A refusal returns an EMPTY changed_cols, so no value moves, no CellSource
    # is upserted, no audit log is written and nothing is broadcast as changed.
    gate_applied, gate_reason = version_gate_verdict(
        table_name, config, row, is_new, update_item)
    if gate_reason is not None and version_stats is not None:
        counts = version_stats.setdefault("counts", {})
        counts[gate_reason] = counts.get(gate_reason, 0) + 1
        if gate_reason == REASON_VERSION_SAME:
            differing = _same_source_content_differs(
                db, table_name, row, update_item, config,
                config.get("version_column"), is_new, sources_cache, overwrites_cache,
                cell_sources_to_upsert, cell_overwrites_to_upsert)
            if differing:
                counts[NOTE_SAME_VERSION_CONTENT_DIFFERS] = \
                    counts.get(NOTE_SAME_VERSION_CONTENT_DIFFERS, 0) + 1
                version_stats.setdefault("differing_columns", set()).update(differing)
    if not gate_applied:
        return row, is_new, changed_cols

    # Update business key first
    _update_row_business_key(row, key_col, update_item, row_cache)

    # Old values snapshot for auditing
    old_values_snapshot = {}
    for col_name in update_item.updates.keys():
        if col_name in system_cols: continue
        old_values_snapshot[col_name] = getattr(row, col_name, None)

    for col_name, val in update_item.updates.items():
        if col_name in system_cols: continue
            
        col_types = config.get("column_types", {})
        if col_name not in col_types:
            # Drop behaviour is deliberately unchanged: rejecting the write would turn a
            # lagging config into an outage. Only the silence is fixed.
            _warn_undeclared_column_once(table_name, col_name)
            continue

        key = (row.row_id, col_name)
        col_srcs, ow = _load_metadata_row_cell(db, table_name, row.row_id, col_name, is_new, sources_cache, overwrites_cache, cell_sources_to_upsert, cell_overwrites_to_upsert)

        # 3. 소스 데이터 upsert
        col_type = col_types.get(col_name, "string")
        clean_val = cast_value_by_type(val, col_type, col_name)
        
        src_obj = next((s for s in col_srcs if s.source_name == update_item.source_name), None)
        if not src_obj:
            src_obj = models.CellSource(
                table_name=table_name,
                row_id=row.row_id,
                column_name=col_name,
                source_name=update_item.source_name
            )
            if cell_sources_to_upsert is None:
                db.add(src_obj)
            col_srcs.append(src_obj)
            
        src_obj.value = clean_val
        src_obj.updated_by = update_item.updated_by
        src_obj.ingested_at = datetime.now()

        if cell_sources_to_upsert is not None:
            upsert_key = (table_name, row.row_id, col_name, update_item.source_name)
            cell_sources_to_upsert[upsert_key] = {
                "table_name": table_name,
                "row_id": row.row_id,
                "column_name": col_name,
                "source_name": update_item.source_name,
                "value": clean_val,
                "updated_by": update_item.updated_by,
                "ingested_at": src_obj.ingested_at
            }

        # 4. 우선순위 결정
        sources_dict = {}
        for s in col_srcs:
            sources_dict[s.source_name] = {
                "value": s.value,
                "timestamp": s.ingested_at.isoformat() if s.ingested_at else datetime.now().isoformat(),
                "updated_by": s.updated_by
            }
            
        manual_pin = ow.manual_priority_source if ow else None
        if update_item.source_name == "user":
            manual_pin = None # 수동 값 입력 시 핀 초기화
            
        new_val, top_src = compute_priority_value(sources_dict, manual_pin, table_name)
        old_val = old_values_snapshot.get(col_name)
        
        # 6. cell_overwrites 마킹
        is_overwrite = ("user" in sources_dict) or (manual_pin is not None)
        if is_overwrite:
            if not ow:
                ow = models.CellOverwrite(
                    table_name=table_name,
                    row_id=row.row_id,
                    column_name=col_name
                )
                if cell_overwrites_to_upsert is None:
                    db.add(ow)
                if overwrites_cache is not None:
                    overwrites_cache[key] = ow
            ow.is_overwrite = True
            ow.updated_by = update_item.updated_by or "system"
            ow.updated_at = datetime.now()
            ow.manual_priority_source = manual_pin
            
            if cell_overwrites_to_upsert is not None:
                ow_key = (table_name, row.row_id, col_name)
                cell_overwrites_to_upsert[ow_key] = {
                    "table_name": table_name,
                    "row_id": row.row_id,
                    "column_name": col_name,
                    "is_overwrite": True,
                    "updated_by": ow.updated_by,
                    "updated_at": ow.updated_at,
                    "manual_priority_source": ow.manual_priority_source
                }
                if cell_overwrites_to_delete is not None:
                    cell_overwrites_to_delete.discard(ow_key)
        else:
            if ow:
                ow_key = (table_name, row.row_id, col_name)
                if cell_overwrites_to_delete is not None:
                    cell_overwrites_to_delete.add(ow_key)
                    if cell_overwrites_to_upsert is not None:
                        cell_overwrites_to_upsert.pop(ow_key, None)
                else:
                    db.delete(ow)
                if overwrites_cache is not None:
                    overwrites_cache[key] = None

        has_changed = False
        if is_new:
            has_changed = True
        else:
            if old_val is None and new_val is None:
                has_changed = False
            elif (old_val is None) != (new_val is None):
                has_changed = True
            elif col_type == "number":
                try:
                    has_changed = float(old_val) != float(new_val)
                except (ValueError, TypeError):
                    has_changed = str(old_val).strip() != str(new_val).strip()
            else:
                has_changed = str(old_val).strip() != str(new_val).strip()

        if has_changed:
            setattr(row, col_name, new_val)
            changed_cols.append(col_name)
            if update_item.source_name == "user":
                log_dict = create_audit_log(
                    db, table_name, row.row_id, col_name, old_val, new_val, 
                    update_item.source_name, (update_item.updated_by or "user"), 
                    transaction_id=transaction_id, business_key=row.business_key_val,
                    add_to_cache=(logs_to_cache is None)
                )
                if logs_to_cache is not None:
                    logs_to_cache.append(log_dict)

    if changed_cols and update_item.source_name != "user":
        new_summary_parts = []
        for col in changed_cols:
            new_val = getattr(row, col, None)
            new_val_str = "비어있음" if new_val is None else str(new_val)
            new_summary_parts.append(f"{col}: {new_val_str}")
            
        if is_new:
            old_summary = None
            summary_msg = "신규 데이터 생성: " + ", ".join(new_summary_parts)
        else:
            old_summary_parts = []
            for col in changed_cols:
                old_val = old_values_snapshot.get(col)
                old_val_str = "비어있음" if old_val is None else str(old_val)
                old_summary_parts.append(f"{col}: {old_val_str}")
            old_summary = ", ".join(old_summary_parts)
            summary_msg = ", ".join(new_summary_parts)
            
        log_dict = create_audit_log(
            db, table_name, row.row_id, "ROW_UPDATE",
            old_summary, summary_msg, update_item.source_name,
            (update_item.updated_by or "system"),
            transaction_id=transaction_id,
            business_key=row.business_key_val,
            add_to_cache=(logs_to_cache is None)
        )
        if logs_to_cache is not None:
            logs_to_cache.append(log_dict)

    # [Notation normalization] Derived `<col>_norm` columns, refreshed from the value
    # that WON above (not from one source's contribution). Placed after the audit block
    # on purpose: the raw change is already logged, and a derived column is not an edit
    # anyone made. It IS appended to changed_cols so the broadcast carries it and a live
    # grid does not sit on a stale derived value.
    #
    # 🔴 This only ever writes the DERIVED column. `notation_norm._validate_column`
    # refuses `derived == raw` and refuses a derived column that is the business key or
    # part of composite_key_source, so nothing here can move a raw value or a row's
    # identity - which is what makes a wrong folding rule repairable by re-deriving.
    try:
        import notation_norm
        derived_cols = notation_norm.apply_derivations(
            table_name, row, changed_cols, is_new)
    except Exception as e:
        # A derivation failure must not fail the write it rides on: the raw value is
        # the record, the derived column is a projection, and re-deriving is a
        # supported repair. Loud in the log, silent to the caller.
        logger.error(f"[NotationNorm] derivation failed for '{table_name}' "
                     f"(the write itself is unaffected): {e}")
        derived_cols = []
    if derived_cols:
        changed_cols.extend(derived_cols)

    # 2. 복합 비즈니스 키 실시간 재계산 및 동기화, 유일성 검사
    if composite_src and key_col:
        is_src_changed = any(col in changed_cols for col in composite_src)
        if is_src_changed or is_new:
            vals = [clean_str_value(getattr(row, col, None)) for col in composite_src]
            if all(v != "" for v in vals):
                new_bk_val = composite_sep.join(vals)
            else:
                # 조합 소스 컬럼들이 누락되었으나 신규 생성 시 business_key_val이 유효하게 주어져 있다면 폴백 사용
                new_bk_val = update_item.business_key_val if (is_new and update_item.business_key_val) else None

            current_bk = getattr(row, "business_key_val", None)
            if current_bk != new_bk_val:
                if new_bk_val is not None:
                    conflict_row = db.query(table_model).filter(
                        table_model.business_key_val == new_bk_val,
                        table_model.row_id != row.row_id
                    ).first()
                    if conflict_row:
                        # -------------------------------------------------------------
                        # [대안 B: Silent Merge & Overwrite]
                        # -------------------------------------------------------------
                        # 1. 중복되어 버려질 임시 껍데기 행 기록
                        row_to_delete = row
                        
                        # 2. 가공 대상 행을 기존 존재하던 충돌 행으로 스위칭
                        row = conflict_row
                        is_new = False
                        
                        # 3. 임시 행(row_to_delete)에 채워진 모든 실제 값을 충돌 행(row)에 덮어쓰기 병합
                        columns_to_merge = [c.name for c in table_model.__table__.columns]
                        for col_name in columns_to_merge:
                            if col_name in [key_col, "row_id", "business_key_val", "created_at", "updated_at"]:
                                continue
                            
                            is_explicitly_edited = (col_name in update_item.updates)
                            
                            # [병합 보호 정책] 충돌 행(row)에 이미 사용자 수정(user)이나 핀이 들어있고, 이번에 직접 수정하는 셀이 아니면 기존 값 보존
                            old_ow = overwrites_cache.get((row.row_id, col_name)) if overwrites_cache else None
                            if not old_ow:
                                old_ow = db.query(models.CellOverwrite).filter(
                                    models.CellOverwrite.table_name == table_name,
                                    models.CellOverwrite.row_id == row.row_id,
                                    models.CellOverwrite.column_name == col_name
                                ).first()
                                
                            is_old_user_overwritten = False
                            if old_ow:
                                # collision_merge인 경우는 단순 병합 충돌 메타이므로 보호 가드 대상에서 제외
                                if old_ow.updated_by != "collision_merge" and old_ow.manual_priority_source != "collision_merge":
                                    is_old_user_overwritten = old_ow.is_overwrite or (old_ow.manual_priority_source is not None)
                                
                            # 새 값이 사용자 입력값인지 판단
                            is_new_user_overwritten = (update_item.source_name == "user" or (update_item.updated_by and update_item.updated_by != "system" and "parser" not in str(update_item.updated_by).lower()))
                            new_ow = overwrites_cache.get((row_to_delete.row_id, col_name)) if overwrites_cache else None
                            if not new_ow:
                                new_ow = db.query(models.CellOverwrite).filter(
                                    models.CellOverwrite.table_name == table_name,
                                    models.CellOverwrite.row_id == row_to_delete.row_id,
                                    models.CellOverwrite.column_name == col_name
                                ).first()
                            if new_ow:
                                if new_ow.updated_by != "collision_merge" and new_ow.manual_priority_source != "collision_merge":
                                    is_new_user_overwritten = is_new_user_overwritten or new_ow.is_overwrite or (new_ow.manual_priority_source is not None)

                            if is_old_user_overwritten and is_new_user_overwritten:
                                # User vs User collision: apply the newly overwritten value
                                is_value_protected = False
                            else:
                                is_value_protected = is_old_user_overwritten and not is_explicitly_edited

                            new_val = getattr(row_to_delete, col_name, None)
                            
                            # update_item.updates에도 명시적으로 새로 기입된 값이 있으면 그 값을 우선적으로 선정
                            if col_name in update_item.updates:
                                new_val = update_item.updates[col_name]
                                
                            old_val = getattr(row, col_name, None)
                            
                            has_cell_changed = False
                            if new_val is not None:
                                if old_val is None:
                                    has_cell_changed = True
                                else:
                                    has_cell_changed = str(old_val).strip() != str(new_val).strip()
                                
                            if has_cell_changed and not is_value_protected:
                                setattr(row, col_name, new_val)
                                if col_name not in changed_cols:
                                    changed_cols.append(col_name)

                                # 중복키 충돌 병합이 발생했음을 가벼운 Overwrite 테이블에도 기록하여 그리드 성능 최적화 지원
                                if cell_overwrites_to_upsert is not None:
                                    from sqlalchemy.sql import func
                                    ow_key = (table_name, row.row_id, col_name)
                                    cell_overwrites_to_upsert[ow_key] = {
                                        "table_name": table_name,
                                        "row_id": row.row_id,
                                        "column_name": col_name,
                                        "is_overwrite": True,
                                        "updated_by": "collision_merge",
                                        "updated_at": func.now(),
                                        "manual_priority_source": "collision_merge"
                                    }
                                    if cell_overwrites_to_delete is not None:
                                        cell_overwrites_to_delete.discard(ow_key)
                                    
                                # AuditLog 기록
                                create_audit_log(
                                    db, table_name, row.row_id, col_name, old_val, new_val,
                                    "collision_merge", (update_item.updated_by or "system"),
                                    transaction_id=transaction_id, business_key=row.business_key_val,
                                    add_to_cache=(logs_to_cache is None)
                                )

                            # [소스 이력 적재] 값 덮어쓰기 보호 여부와 상관없이, 껍데기 행이 가졌던 오리지널 소스 목록은 무조건 적재(Append)
                            if cell_sources_to_upsert is not None:
                                from sqlalchemy.sql import func
                                # 껍데기 행이 원래 가졌던 소스 명칭 추적 계승
                                old_srcs, _ = _load_metadata_row_cell(
                                    db, table_name, row_to_delete.row_id, col_name,
                                    is_new=False,
                                    sources_cache=sources_cache,
                                    overwrites_cache=overwrites_cache,
                                    cell_sources_to_upsert=cell_sources_to_upsert,
                                    cell_overwrites_to_upsert=cell_overwrites_to_upsert
                                )
                                
                                # 대상 행(row)에 이미 등록되어 있거나 upsert 대기 중인 소스명 목록 추출
                                target_srcs, _ = _load_metadata_row_cell(
                                    db, table_name, row.row_id, col_name,
                                    is_new=False,
                                    sources_cache=sources_cache,
                                    overwrites_cache=overwrites_cache,
                                    cell_sources_to_upsert=cell_sources_to_upsert,
                                    cell_overwrites_to_upsert=cell_overwrites_to_upsert
                                )
                                existing_names = {s.source_name for s in target_srcs} if target_srcs else set()
                                for (t, r, c, s_name) in (cell_sources_to_upsert or {}).keys():
                                    if t == table_name and r == row.row_id and c == col_name:
                                        existing_names.add(s_name)

                                # user 간 충돌 시 기존의 standard "user" 값을 "user (old_exist_xyz)"로 백업하여 원천에 기존 user값을 보존
                                if is_old_user_overwritten and is_new_user_overwritten:
                                    old_user_src = next((s for s in target_srcs if s.source_name == "user"), None) if target_srcs else None
                                    pending_user_key = (table_name, row.row_id, col_name, "user")
                                    pending_user_data = cell_sources_to_upsert.get(pending_user_key) if cell_sources_to_upsert else None
                                    
                                    old_val_to_backup = pending_user_data["value"] if pending_user_data else (old_user_src.value if old_user_src else None)
                                    old_by_to_backup = pending_user_data["updated_by"] if pending_user_data else (old_user_src.updated_by if old_user_src else "system")
                                    
                                    if old_val_to_backup is not None:
                                        backup_src_name = f"user (old_exist_{row.row_id[:6]})"
                                        backup_key = (table_name, row.row_id, col_name, backup_src_name)
                                        cell_sources_to_upsert[backup_key] = {
                                            "table_name": table_name,
                                            "row_id": row.row_id,
                                            "column_name": col_name,
                                            "source_name": backup_src_name,
                                            "value": clean_str_value(old_val_to_backup),
                                            "updated_by": old_by_to_backup,
                                            "ingested_at": func.now()
                                        }

                                src_list = []
                                if old_srcs:
                                    for s in old_srcs:
                                        src_list.append((s.source_name, s.value, s.updated_by))
                                else:
                                    # 폴백 소스
                                    src_list.append((update_item.source_name or "user", new_val, update_item.updated_by or "system"))

                                for s_name, s_val, s_by in src_list:
                                    effective_src_name = s_name
                                    if s_name == "user" and is_old_user_overwritten and is_new_user_overwritten:
                                        effective_src_name = "user"
                                    else:
                                        r_id_6 = row_to_delete.row_id[:6] if row_to_delete.row_id else "merged"
                                        suffix = f" ({row_to_delete.business_key_val}_{r_id_6})" if getattr(row_to_delete, "business_key_val", None) else f" ({r_id_6})"
                                        effective_src_name = f"{effective_src_name}{suffix}"
                                        
                                    src_key = (table_name, row.row_id, col_name, effective_src_name)
                                    cell_sources_to_upsert[src_key] = {
                                        "table_name": table_name,
                                        "row_id": row.row_id,
                                        "column_name": col_name,
                                        "source_name": effective_src_name,
                                        "value": clean_str_value(s_val),
                                        "updated_by": s_by or "system",
                                        "ingested_at": func.now()
                                    }

                        # 4. 캐시 맵 마이그레이션 (row_to_delete.row_id ➡️ conflict_row.row_id)
                        if cell_sources_to_upsert is not None:
                            keys_to_migrate = [k for k in cell_sources_to_upsert.keys() if k[1] == row_to_delete.row_id]
                            for k in keys_to_migrate:
                                src_data = cell_sources_to_upsert.pop(k)
                                new_k = (k[0], row.row_id, k[2], k[3])
                                src_data["row_id"] = row.row_id
                                cell_sources_to_upsert[new_k] = src_data
                                
                        if cell_overwrites_to_upsert is not None:
                            keys_to_migrate = [k for k in cell_overwrites_to_upsert.keys() if k[1] == row_to_delete.row_id]
                            for k in keys_to_migrate:
                                ow_data = cell_overwrites_to_upsert.pop(k)
                                new_k = (k[0], row.row_id, k[2])
                                ow_data["row_id"] = row.row_id
                                cell_overwrites_to_upsert[new_k] = ow_data
                                
                        if cell_overwrites_to_delete is not None:
                            keys_to_migrate = [k for k in cell_overwrites_to_delete if k[1] == row_to_delete.row_id]
                            for k in keys_to_migrate:
                                cell_overwrites_to_delete.discard(k)
                                cell_overwrites_to_delete.add((k[0], row.row_id, k[2]))
                                
                        if logs_to_cache is not None:
                            for log in logs_to_cache:
                                if log.get("row_id") == row_to_delete.row_id:
                                    log["row_id"] = row.row_id
                                    
                        for obj in db.new:
                            if isinstance(obj, models.AuditLog) and obj.row_id == row_to_delete.row_id:
                                obj.row_id = row.row_id

                        # 5. 무의미한 껍데기 행을 DB 세션 및 메모리 캐시에서 완전 소거
                        try:
                            db.delete(row_to_delete)
                            if deleted_row_ids is not None:
                                deleted_row_ids.append(row_to_delete.row_id)
                        except Exception:
                            pass
                        if row_cache is not None:
                            row_cache.pop(row_to_delete.row_id, None)
                            if row_to_delete.business_key_val:
                                row_cache.pop(row_to_delete.business_key_val, None)

                old_bk_col_val = getattr(row, key_col, None)
                
                row.business_key_val = new_bk_val
                if row_cache is not None:
                    if current_bk in row_cache and row_cache[current_bk] == row:
                        del row_cache[current_bk]
                    if new_bk_val is not None:
                        row_cache[new_bk_val] = row

                setattr(row, key_col, new_bk_val)
                
                if old_bk_col_val != new_bk_val:
                    changed_cols.append(key_col)
                    if update_item.source_name == "user":
                        log_dict = create_audit_log(
                            db, table_name, row.row_id, key_col, old_bk_col_val, new_bk_val, 
                            update_item.source_name, (update_item.updated_by or "user"), 
                            transaction_id=transaction_id, business_key=row.business_key_val,
                            add_to_cache=(logs_to_cache is None)
                        )
                        if logs_to_cache is not None:
                            logs_to_cache.append(log_dict)

    if changed_cols or is_new:
        from sqlalchemy.sql import func
        row.updated_at = func.now()
        row.is_graph_synced = False
        if is_new:
            row.needs_graph_rollback = False
        else:
            row.needs_graph_rollback = row.needs_graph_rollback or check_needs_rollback(table_name, changed_cols)

    return row, is_new, changed_cols


def derive_replace_map_scope(table_name: str, batch: schemas.GeneralUpdateBatch) -> Optional[dict]:
    """Resolve the exact {column: value} filters a replace_map purge will DELETE by.

    Single source of truth for the purge scope: apply_batch_updates deletes with the
    returned filters and the API layer echoes the same dict to the caller, so what the
    client is told IS what was deleted (both sides call this pure function - no drift).

    Resolution order:
      1. batch.scope (explicit) - validated strictly: every key must be a declared
         column, inside the table's map-key contract, physically on the model, and
         carry a non-empty value. Any violation raises ValueError - a dropped filter
         would WIDEN a DELETE, so nothing is silently skipped on this path.
      2. batch.updates[0] (derived) - map_key_columns when declared, else the legacy
         fallback (every non-coordinate column that the first payload row carries).

    Returns None when no filter can be resolved. Callers MUST treat None as a refusal:
    an empty filter set would either delete the whole table or (the historical bug)
    delete nothing while still answering 200 - rows then accumulate silently.
    """
    config = TABLE_CONFIG.get(table_name, {})
    col_types = config.get("column_types", {})
    map_key_cols = config.get("map_key_columns", [])
    col_types_lower = {k.lower(): k for k in col_types.keys()}
    table_model = models.DYNAMIC_TABLES.get(table_name)

    if map_key_cols and isinstance(map_key_cols, list) and len(map_key_cols) > 0:
        target_cols = [str(c) for c in map_key_cols]
    else:
        skip_cols = {"x", "y", "col_x", "col_y", "val", "code", "die_id", "grid_metadata", "leg"}
        target_cols = [c for c in col_types.keys() if c.lower() not in skip_cols]
    allowed_lower = {c.lower() for c in target_cols}

    if batch.scope is not None:
        resolved = {}
        for c_name, c_val in batch.scope.items():
            real_col_name = col_types_lower.get(str(c_name).lower())
            if real_col_name is None:
                raise ValueError(
                    f"replace_map scope column '{c_name}' is not a declared column of '{table_name}'"
                )
            if str(c_name).lower() not in allowed_lower:
                raise ValueError(
                    f"replace_map scope column '{c_name}' is outside the map-key contract of "
                    f"'{table_name}' (allowed: {sorted(target_cols)})"
                )
            if c_val is None or str(c_val).strip() == "":
                raise ValueError(f"replace_map scope column '{c_name}' has an empty value")
            if table_model is not None and getattr(table_model, real_col_name, None) is None:
                raise ValueError(
                    f"replace_map scope column '{real_col_name}' does not physically exist on '{table_name}'"
                )
            resolved[real_col_name] = c_val
        return resolved or None

    if not batch.updates:
        return None
    sample_item = batch.updates[0]
    resolved = {}
    for target_col in target_cols:
        real_col_name = col_types_lower.get(target_col.lower())
        if not real_col_name:
            continue
        # Mirrors the historical derived-path behaviour: a config column missing on the
        # model is skipped (config/model mismatch is transient during schema rollout).
        if table_model is not None and getattr(table_model, real_col_name, None) is None:
            continue
        for c_name, c_val in sample_item.updates.items():
            if c_name.lower() == real_col_name.lower() and c_val is not None and str(c_val).strip() != "":
                resolved[real_col_name] = c_val
                break
    return resolved or None


def refuse_virtual_join_columns(db: Session, table_name: str, batch: schemas.GeneralUpdateBatch):
    """A write aimed at a virtual-join column is REFUSED here, for every write path.

    A `virtual_only` column is not stored on the left table - it exists only in the read
    payload, computed from a verified join. A write targeting it would target a column
    that does not exist, and the pre-existing undeclared-column gate in
    `apply_row_update_internal` would DROP it silently: the API answers 200, the client
    re-renders from the joined value, and the user's edit vanishes with no explanation.
    Silence is the defect; the drop was always correct.

    This lives in `apply_batch_updates` because that is the single funnel every write
    converges on - the grid edit and paste and the map/DOE Push (all `PUT
    /tables/{t}/data/updates`), file ingestion, the chain worker, enrichment
    auto-confirm, replay, map-meta registration. `apply_row_update_internal` has exactly
    one caller (this function), so there is no write that can reach a column while
    bypassing this check, and a new call site cannot forget it.

    `collide` columns are deliberately NOT refused. They are ordinary stored columns that
    a join also feeds; writing one is how a user overrides the joined value, and that
    write is precisely the "left value present" arm of the absent-only rule. Refusing it
    would leave the user no way to correct a joined cell.

    Raises ValueError, which the API layer already maps to 400 (same as the replace_map
    scope refusal). Batch-level, so one message names every offending column at once.
    """
    if not batch.updates:
        return
    try:
        import virtual_join_executor
        virtual_cols = virtual_join_executor.virtual_only_columns(db, table_name)
    except Exception as e:
        # Unreadable declarations mean NO join is in effect (the executor logs it and
        # attaches nothing), so there is no virtual column to protect and nothing to
        # refuse. Failing the write here would turn a config problem into an outage.
        logger.error(f"[VirtualJoin] write guard could not load declarations for "
                     f"'{table_name}', no column is refused: {e}")
        return
    if not virtual_cols:
        return
    offending = sorted({c for u in batch.updates for c in (u.updates or {}) if c in virtual_cols})
    if offending:
        raise ValueError(
            f"'{table_name}' 테이블의 컬럼 {', '.join(offending)}은(는) 가상 조인으로 "
            f"조회 시점에 계산되는 값이라 저장할 수 없습니다. 이 테이블에는 그 컬럼이 "
            f"실제로 존재하지 않습니다. 값을 고치려면 조인 원본 테이블에서 수정하세요."
        )


def refuse_notation_derived_columns(table_name: str, batch: schemas.GeneralUpdateBatch):
    """A write aimed at a notation-derived `<col>_norm` column is REFUSED here.

    A derived column is a pure function of its raw column (`notation_norm`). If a
    write could land a value in it, that value would survive until the raw column
    next changed and then vanish without explanation - and worse, the row would
    meanwhile carry a normalized value that its own raw value does not produce,
    which is exactly the disagreement the derived column exists to remove.

    Same funnel and same reasoning as `refuse_virtual_join_columns`: the check
    lives in `apply_batch_updates` because that is the single funnel every write
    converges on, so a new call site cannot forget it. Unlike that one it needs
    no database session - the declarations are config.

    An unreadable declaration refuses nothing (the loader already logged it);
    turning a config problem into a write outage would be the worse trade.
    """
    if not batch.updates:
        return
    try:
        import notation_norm
        derived_cols = notation_norm.derived_columns_for(table_name)
    except Exception as e:
        logger.error(f"[NotationNorm] write guard could not load declarations for "
                     f"'{table_name}', no column is refused: {e}")
        return
    if not derived_cols:
        return
    offending = sorted({c for u in batch.updates for c in (u.updates or {}) if c in derived_cols})
    if offending:
        raise ValueError(
            f"'{table_name}' 테이블의 컬럼 {', '.join(offending)}은(는) 원본 컬럼에서 "
            f"자동으로 계산되는 표기 정규화 값이라 직접 저장할 수 없습니다. 값을 "
            f"바꾸려면 원본 컬럼을 수정하세요."
        )


def apply_batch_updates(db: Session, table_name: str, batch: schemas.GeneralUpdateBatch,
                        replace_report: Optional[dict] = None):
    """통합 업데이트를 배치로 처리합니다.

    replace_report: optional out-param (dict). When batch.replace_map is set and a dict
    is passed, it is filled with {"filters": <scope dict>, "deleted": <purged row count>}
    so the API layer can report the exact purge honestly without changing this
    function's widely-unpacked 4-tuple return signature (worker/parser/test call sites).
    """
    # Before anything is opened or purged: a batch aimed at a virtual-join column is
    # refused whole. Placed ahead of transaction_context so the refusal cannot leave a
    # half-applied transaction, and ahead of the replace_map purge so a bad payload
    # cannot delete rows on its way to being rejected.
    refuse_virtual_join_columns(db, table_name, batch)
    refuse_notation_derived_columns(table_name, batch)

    tx_id = batch.transaction_id or str(uuid6.uuid7())
    
    user_val = batch.updates[0].updated_by if batch.updates else "system"
    source_val = batch.updates[0].source_name if batch.updates else "batch"
    
    with transaction_context(user_val, tx_id, source_val):
        table_model = models.DYNAMIC_TABLES.get(table_name)
        if not table_model:
            raise ValueError(f"Table model for '{table_name}' is not initialized. Please define the table in config/table_config.json and restart the server/watcher processes.")
            
        target_ids = [u.row_id for u in batch.updates if u.row_id]
        target_bks = [str(u.business_key_val).strip() for u in batch.updates if u.business_key_val]

        if batch.replace_map:
            # [U6] The purge scope comes from ONE shared resolver (also called by the API
            # layer to echo the scope in the response). No resolvable scope = honest 4xx
            # refusal instead of the historical silent 200-noop that deleted nothing and
            # let map rows accumulate. An explicit batch.scope with an empty payload is
            # the legitimate erase-all of that scope.
            scope_filters = derive_replace_map_scope(table_name, batch)
            if not scope_filters:
                raise ValueError(
                    f"replace_map on '{table_name}' could not derive a purge scope: "
                    f"declare 'map_key_columns' in table_config and send their values in the "
                    f"payload (or pass an explicit 'scope' object). Refusing instead of "
                    f"silently replacing nothing."
                )

            meta_conditions = [
                getattr(table_model, col_name) == col_val
                for col_name, col_val in scope_filters.items()
            ]

            from sqlalchemy import and_
            matching_rows = db.query(table_model.row_id).filter(and_(*meta_conditions)).all()
            purged_row_ids = [r[0] for r in matching_rows if r[0]]

            if purged_row_ids:
                # 1. Purge cell sources & overwrites for old map rows
                db.query(models.CellSource).filter(
                    models.CellSource.table_name == table_name,
                    models.CellSource.row_id.in_(purged_row_ids)
                ).delete(synchronize_session=False)

                db.query(models.CellOverwrite).filter(
                    models.CellOverwrite.table_name == table_name,
                    models.CellOverwrite.row_id.in_(purged_row_ids)
                ).delete(synchronize_session=False)

                # 2. Purge main dynamic table rows
                db.query(table_model).filter(
                    table_model.row_id.in_(purged_row_ids)
                ).delete(synchronize_session=False)

                db.flush()

            if replace_report is not None:
                replace_report["filters"] = scope_filters
                replace_report["deleted"] = len(purged_row_ids)

            logger.info(
                f"🔄 [Map Replace Executed] Table: '{table_name}' | TX: {tx_id} | "
                f"Filters: {scope_filters} | Purged Old Rows: {len(purged_row_ids)} | "
                f"Incoming Active Cells: {len(batch.updates)}"
            )

        from sqlalchemy import or_
        existing_rows_list = db.query(table_model).filter(
            or_(
                table_model.row_id.in_(target_ids) if target_ids else False,
                table_model.business_key_val.in_(target_bks) if target_bks else False
            )
        ).all()
        
        row_cache = {}
        for r in existing_rows_list:
            row_cache[r.row_id] = r
            if r.business_key_val:
                row_cache[r.business_key_val] = r
                
        all_row_ids = list(set(r.row_id for r in existing_rows_list))
        
        sources_cache = {}
        overwrites_cache = {}
        
        if all_row_ids:
            all_sources = db.query(
                models.CellSource.table_name,
                models.CellSource.row_id,
                models.CellSource.column_name,
                models.CellSource.source_name,
                models.CellSource.value,
                models.CellSource.updated_by,
                models.CellSource.ingested_at
            ).filter(
                models.CellSource.table_name == table_name,
                models.CellSource.row_id.in_(all_row_ids)
            ).all()
            for t_name, r_id, col_name, src_name, val, upd_by, ing_at in all_sources:
                key = (r_id, col_name)
                if key not in sources_cache:
                    sources_cache[key] = []
                sources_cache[key].append(LightCellSource(t_name, r_id, col_name, src_name, val, upd_by, ing_at))
                
            all_overwrites = db.query(
                models.CellOverwrite.table_name,
                models.CellOverwrite.row_id,
                models.CellOverwrite.column_name,
                models.CellOverwrite.is_overwrite,
                models.CellOverwrite.updated_by,
                models.CellOverwrite.updated_at,
                models.CellOverwrite.manual_priority_source
            ).filter(
                models.CellOverwrite.table_name == table_name,
                models.CellOverwrite.row_id.in_(all_row_ids)
            ).all()
            for t_name, r_id, col_name, is_ow, upd_by, upd_at, man_pin in all_overwrites:
                overwrites_cache[(r_id, col_name)] = LightCellOverwrite(t_name, r_id, col_name, is_ow, upd_by, upd_at, man_pin)
    
        unique_results = {}
        total_changed_cells = []
        logs_to_cache = []
        
        # Batch containers for bulk operations (deduplicated early via dict/set)
        cell_sources_to_upsert = {}
        cell_overwrites_to_upsert = {}
        cell_overwrites_to_delete = set()
        deleted_row_ids = []

        # [Version gate] Per-batch accumulator. Only allocated for a table that declares
        # a version column, so an ordinary table pays one dict lookup for the whole batch.
        version_col = TABLE_CONFIG.get(table_name, {}).get("version_column")
        version_stats = {"rows": len(batch.updates)} if version_col else None

        with db.no_autoflush:
            for item in batch.updates:
                row, is_new, changed_cols = apply_row_update_internal(
                    db, table_name, item,
                    row_cache=row_cache,
                    sources_cache=sources_cache,
                    overwrites_cache=overwrites_cache,
                    transaction_id=tx_id,
                    logs_to_cache=logs_to_cache,
                    cell_sources_to_upsert=cell_sources_to_upsert,
                    cell_overwrites_to_upsert=cell_overwrites_to_upsert,
                    cell_overwrites_to_delete=cell_overwrites_to_delete,
                    deleted_row_ids=deleted_row_ids,
                    version_stats=version_stats
                )
                prev_row, prev_is_new = unique_results.get(row.row_id, (None, False))
                unique_results[row.row_id] = (row, is_new or prev_is_new)
                
                for col in changed_cols:
                    total_changed_cells.append((row.row_id, col))

        # Reported before the flush so a later failure cannot swallow the reason a batch
        # wrote nothing - "the file did not take" with no explanation is the exact class
        # of silence this gate exists to end.
        if version_stats is not None:
            log_version_gate_summary(table_name, version_col, source_val, version_stats)

        # Execute Bulk Upserts, Bulk Inserts, and Deletes
        if logs_to_cache:
            bulk_insert_audit_logs(db, logs_to_cache)
        bulk_upsert_cell_sources(db, list(cell_sources_to_upsert.values()))
        bulk_upsert_cell_overwrites(db, list(cell_overwrites_to_upsert.values()))
        bulk_delete_cell_overwrites(db, list(cell_overwrites_to_delete))
        
        db.flush()
        
        serialized_logs = []
        for l in logs_to_cache:
            ts_val = l["timestamp"]
            serialized_logs.append({
                "id": 0,
                "table_name": l["table_name"],
                "row_id": l["row_id"],
                "column_name": l["column_name"],
                "old_value": l["old_value"],
                "new_value": l["new_value"],
                "source_name": l["source_name"],
                "updated_by": l["updated_by"],
                "transaction_id": l["transaction_id"],
                "timestamp": ts_val.isoformat() if hasattr(ts_val, "isoformat") else ts_val,
                "business_key": l.get("business_key")
            })
            
        db.commit()
        
        if logs_to_cache:
            from audit_cache import audit_cache
            audit_cache.add_logs_batch(logs_to_cache)
            
        results = list(unique_results.values())
        return results, total_changed_cells, serialized_logs, deleted_row_ids

def create_empty_row(db: Session, table_name: str):
    """신규 빈 행을 하나 생성합니다."""
    new_rows = create_empty_rows_batch(db, table_name, 1)
    return new_rows[0] if new_rows else None

def create_empty_rows_batch(db: Session, table_name: str, count: int, user_name: str = "system"):
    """신규 빈 행을 일괄 생성하고 요약 히스토리를 남깁니다."""
    from sqlalchemy.sql import func
    
    tx_id = str(uuid6.uuid7())
    
    with transaction_context(user_name, tx_id, "batch_create"):
        table_model = models.DYNAMIC_TABLES.get(table_name)
        if not table_model:
            raise ValueError(f"Table model for '{table_name}' is not initialized. Please define the table in config/table_config.json and restart the server/watcher processes.")
            
        new_rows = []
        for _ in range(count):
            row = table_model(
                row_id=str(uuid6.uuid7()),
                updated_at=func.now()
            )
            new_rows.append(row)
        
        db.add_all(new_rows)
        
        logs_to_cache = []
        if count > 0:
            for row in new_rows:
                log_dict = create_audit_log(
                    db, table_name, row.row_id, "CREATE",
                    None, "새 행 생성됨", "system", user_name,
                    transaction_id=tx_id,
                    business_key=row.business_key_val,
                    add_to_cache=False
                )
                logs_to_cache.append(log_dict)

        if logs_to_cache:
            bulk_insert_audit_logs(db, logs_to_cache)

        db.commit()

        if logs_to_cache:
            from audit_cache import audit_cache
            audit_cache.add_logs_batch(logs_to_cache)

        return new_rows

def delete_row(db: Session, table_name: str, row_id: str, user_name: str = "system"):
    """단일 행을 삭제합니다 (배치 로직으로 통합)."""
    return delete_rows_batch(db, table_name, [row_id], user_name) > 0

def delete_rows_batch(db: Session, table_name: str, row_ids: list[str], user_name: str = "system"):
    """여러 행을 일괄 삭제하고 개별 히스토리를 남기며 메타데이터도 연쇄 삭제합니다."""
    if not row_ids:
        return 0
        
    tx_id = str(uuid6.uuid7())
    
    with transaction_context(user_name, tx_id, "batch_delete"):
        table_model = models.DYNAMIC_TABLES.get(table_name)
        if not table_model:
            raise ValueError(f"Table model for '{table_name}' is not initialized. Please define the table in config/table_config.json and restart the server/watcher processes.")
            
        # 삭제하기 전 row_id와 business_key_val을 먼저 조회
        rows_to_delete = db.query(table_model).filter(
            table_model.row_id.in_(row_ids)
        ).all()
            
        # 메타데이터 연쇄 삭제
        db.query(models.CellOverwrite).filter(
            models.CellOverwrite.table_name == table_name,
            models.CellOverwrite.row_id.in_(row_ids)
        ).delete(synchronize_session=False)

        db.query(models.CellSource).filter(
            models.CellSource.table_name == table_name,
            models.CellSource.row_id.in_(row_ids)
        ).delete(synchronize_session=False)

        # 기본 데이터 삭제
        deleted_count = db.query(table_model).filter(
            table_model.row_id.in_(row_ids)
        ).delete(synchronize_session=False)
                
        if deleted_count > 0:
            logs_to_cache = []
            for row in rows_to_delete:
                log_dict = create_audit_log(
                    db, table_name, row.row_id, "DELETE", 
                    None, "행 삭제됨", "system", user_name,
                    transaction_id=tx_id,
                    business_key=row.business_key_val,
                    add_to_cache=False
                )
                logs_to_cache.append(log_dict)
            if logs_to_cache:
                bulk_insert_audit_logs(db, logs_to_cache)
            db.commit()

            if logs_to_cache:
                from audit_cache import audit_cache
                audit_cache.add_logs_batch(logs_to_cache)
                
            from audit_cache import audit_cache
            audit_cache.remove_deleted_rows(row_ids)
            
        return deleted_count

def get_row_cell(db: Session, table_name: str, row_id: str):
    table_model = models.DYNAMIC_TABLES.get(table_name)
    if not table_model:
        return None
    return db.query(table_model).filter(table_model.row_id == row_id).first()


def delete_cell_source_batch(db: Session, table_name: str, cells: list[dict], source_name: str):
    """여러 셀의 특정 데이터 원천(Source)을 일괄 삭제합니다."""
    if not cells:
        return [], []

    row_ids = list(set(c["row_id"] for c in cells))
    table_model = models.DYNAMIC_TABLES.get(table_name)
    if not table_model:
        return [], []
        
    rows = db.query(table_model).filter(table_model.row_id.in_(row_ids)).all()
    row_map = {r.row_id: r for r in rows}

    # 1. 특정 소스 일괄 삭제 실행 (동일 트랜잭션 내)
    from sqlalchemy import and_, or_
    delete_conds = []
    for item in cells:
        delete_conds.append(
            and_(
                models.CellSource.table_name == table_name,
                models.CellSource.row_id == item["row_id"],
                models.CellSource.column_name == item["column_name"],
                models.CellSource.source_name == source_name
            )
        )
    db.query(models.CellSource).filter(or_(*delete_conds)).delete(synchronize_session=False)

    # 2. 캐시 일괄 생성 (N+1 SELECT 차단)
    all_sources = db.query(
        models.CellSource.table_name,
        models.CellSource.row_id,
        models.CellSource.column_name,
        models.CellSource.source_name,
        models.CellSource.value,
        models.CellSource.updated_by,
        models.CellSource.ingested_at
    ).filter(
        models.CellSource.table_name == table_name,
        models.CellSource.row_id.in_(row_ids)
    ).all()
    
    sources_cache = {}
    for t_name, r_id, col_name, src_name, val, upd_by, ing_at in all_sources:
        key = (r_id, col_name)
        if key not in sources_cache:
            sources_cache[key] = []
        sources_cache[key].append(LightCellSource(t_name, r_id, col_name, src_name, val, upd_by, ing_at))

    all_overwrites = db.query(
        models.CellOverwrite.table_name,
        models.CellOverwrite.row_id,
        models.CellOverwrite.column_name,
        models.CellOverwrite.is_overwrite,
        models.CellOverwrite.updated_by,
        models.CellOverwrite.updated_at,
        models.CellOverwrite.manual_priority_source
    ).filter(
        models.CellOverwrite.table_name == table_name,
        models.CellOverwrite.row_id.in_(row_ids)
    ).all()
    
    overwrites_cache = {}
    for t_name, r_id, col_name, is_ow, upd_by, upd_at, man_pin in all_overwrites:
        overwrites_cache[(r_id, col_name)] = LightCellOverwrite(t_name, r_id, col_name, is_ow, upd_by, upd_at, man_pin)

    # 3. 인메모리 비교 루프 실행
    changed_rows = []
    tx_id = str(uuid6.uuid7())
    logs_to_cache = []
    
    cell_overwrites_to_upsert = {}
    cell_overwrites_to_delete = set()

    for item in cells:
        r_id = item["row_id"]
        col_name = item["column_name"]
        row = row_map.get(r_id)
        if not row:
            continue

        key = (r_id, col_name)
        col_srcs = sources_cache.get(key, [])
        ow = overwrites_cache.get(key)

        manual_pin = ow.manual_priority_source if ow else None
        if manual_pin == source_name:
            manual_pin = None
            if ow:
                ow.manual_priority_source = None

        sources_dict = {
            s.source_name: {
                "value": s.value,
                "timestamp": s.ingested_at.isoformat() if s.ingested_at else datetime.now().isoformat(),
                "updated_by": s.updated_by
            }
            for s in col_srcs
        }

        old_val = getattr(row, col_name, None)
        new_val, top_src = compute_priority_value(sources_dict, manual_pin, table_name)
        setattr(row, col_name, new_val)

        is_overwrite = ("user" in sources_dict) or (manual_pin is not None)
        ow_key = (table_name, r_id, col_name)
        if is_overwrite:
            ow_updated_by = ow.updated_by if ow else "system"
            ow_updated_at = ow.updated_at if ow else datetime.now()
            cell_overwrites_to_upsert[ow_key] = {
                "table_name": table_name,
                "row_id": r_id,
                "column_name": col_name,
                "is_overwrite": True,
                "updated_by": ow_updated_by,
                "updated_at": ow_updated_at,
                "manual_priority_source": manual_pin
            }
            cell_overwrites_to_delete.discard(ow_key)
        else:
            if ow:
                cell_overwrites_to_delete.add(ow_key)
                cell_overwrites_to_upsert.pop(ow_key, None)

        if str(old_val) != str(new_val):
            log_dict = create_audit_log(
                db, table_name, r_id, col_name, old_val, new_val,
                f"delete_source:{source_name}", "system",
                transaction_id=tx_id, business_key=row.business_key_val,
                add_to_cache=False
            )
            logs_to_cache.append(log_dict)

        if row not in changed_rows:
            changed_rows.append(row)

    # 4. 벌크 갱신 및 삭제
    if logs_to_cache:
        bulk_insert_audit_logs(db, logs_to_cache)
    bulk_upsert_cell_overwrites(db, list(cell_overwrites_to_upsert.values()))
    bulk_delete_cell_overwrites(db, list(cell_overwrites_to_delete))

    db.commit()

    if logs_to_cache:
        from audit_cache import audit_cache
        audit_cache.add_logs_batch(logs_to_cache)

    serialized_logs = []
    for log in logs_to_cache:
        log_copy = log.copy()
        if isinstance(log_copy.get("timestamp"), datetime):
            log_copy["timestamp"] = log_copy["timestamp"].isoformat()
        serialized_logs.append(log_copy)

    return changed_rows, serialized_logs

def delete_cell_source(db: Session, table_name: str, row_id: str, col_name: str, source_name: str):
    """특정 소스의 데이터를 삭제하고 값을 재계산합니다."""
    changed_rows, logs = delete_cell_source_batch(db, table_name, [{"row_id": row_id, "column_name": col_name}], source_name)
    return changed_rows[0] if changed_rows else None, [col_name] if logs else []

def set_cell_manual_priority_batch(db: Session, table_name: str, updates: list[dict], source_name: Optional[str], updated_by: str = "user"):
    """여러 셀의 표시 우선순위 소스를 수동으로 일괄 지정합니다 (Pin)."""
    if not updates:
        return [], []

    row_ids = list(set(u["row_id"] for u in updates))
    table_model = models.DYNAMIC_TABLES.get(table_name)
    if not table_model:
        return [], []
        
    rows = db.query(table_model).filter(table_model.row_id.in_(row_ids)).all()
    row_map = {r.row_id: r for r in rows}

    # 1. 인메모리 캐시 일괄 조회 및 적재
    all_sources = db.query(
        models.CellSource.table_name,
        models.CellSource.row_id,
        models.CellSource.column_name,
        models.CellSource.source_name,
        models.CellSource.value,
        models.CellSource.updated_by,
        models.CellSource.ingested_at
    ).filter(
        models.CellSource.table_name == table_name,
        models.CellSource.row_id.in_(row_ids)
    ).all()
    
    sources_cache = {}
    for t_name, r_id, col_name, src_name, val, upd_by, ing_at in all_sources:
        key = (r_id, col_name)
        if key not in sources_cache:
            sources_cache[key] = []
        sources_cache[key].append(LightCellSource(t_name, r_id, col_name, src_name, val, upd_by, ing_at))

    all_overwrites = db.query(
        models.CellOverwrite.table_name,
        models.CellOverwrite.row_id,
        models.CellOverwrite.column_name,
        models.CellOverwrite.is_overwrite,
        models.CellOverwrite.updated_by,
        models.CellOverwrite.updated_at,
        models.CellOverwrite.manual_priority_source
    ).filter(
        models.CellOverwrite.table_name == table_name,
        models.CellOverwrite.row_id.in_(row_ids)
    ).all()
    
    overwrites_cache = {}
    for t_name, r_id, col_name, is_ow, upd_by, upd_at, man_pin in all_overwrites:
        overwrites_cache[(r_id, col_name)] = LightCellOverwrite(t_name, r_id, col_name, is_ow, upd_by, upd_at, man_pin)

    # 2. 인메모리 연산 루프
    changed_rows = []
    tx_id = str(uuid6.uuid7())
    logs_to_cache = []
    deleted_row_ids = []
    
    cell_overwrites_to_upsert = {}
    cell_overwrites_to_delete = set()
    
    for item in updates:
        r_id = item["row_id"]
        col_name = item["column_name"]
        row = row_map.get(r_id)
        if not row:
            continue

        key = (r_id, col_name)
        col_srcs = sources_cache.get(key, [])
        ow = overwrites_cache.get(key)

        current_pin = ow.manual_priority_source if ow else None
        effective_source = None if (current_pin == source_name) else source_name

        if effective_source and not any(s.source_name == effective_source for s in col_srcs):
            continue

        sources_dict = {
            s.source_name: {
                "value": s.value,
                "timestamp": s.ingested_at.isoformat() if s.ingested_at else datetime.now().isoformat(),
                "updated_by": s.updated_by
            }
            for s in col_srcs
        }

        old_val = getattr(row, col_name, None)
        new_val, top_src = compute_priority_value(sources_dict, effective_source, table_name)
        setattr(row, col_name, new_val)

        is_overwrite = ("user" in sources_dict) or (effective_source is not None)
        ow_key = (table_name, r_id, col_name)
        if is_overwrite:
            ow_updated_by = ow.updated_by if ow else "system"
            ow_updated_at = ow.updated_at if ow else datetime.now()
            cell_overwrites_to_upsert[ow_key] = {
                "table_name": table_name,
                "row_id": r_id,
                "column_name": col_name,
                "is_overwrite": True,
                "updated_by": updated_by or ow_updated_by,
                "updated_at": datetime.now(),
                "manual_priority_source": effective_source
            }
            cell_overwrites_to_delete.discard(ow_key)
        else:
            if ow:
                cell_overwrites_to_delete.add(ow_key)
                cell_overwrites_to_upsert.pop(ow_key, None)

        if str(old_val) != str(new_val):
            log_dict = create_audit_log(
                db, table_name, r_id, col_name, old_val, new_val,
                f"set_priority:{effective_source}", updated_by,
                transaction_id=tx_id, business_key=row.business_key_val,
                add_to_cache=False
            )
            logs_to_cache.append(log_dict)

        # 복합 비즈니스 키 실시간 재계산 및 갱신 가드
        table_info = TABLE_CONFIG.get(table_name, {})
        composite_src = table_info.get("composite_key_source")
        key_col = table_info.get("business_key")
        composite_sep = table_info.get("composite_key_separator", "_")

        if composite_src and key_col and col_name in composite_src:
            vals = [clean_str_value(getattr(row, col, None)) for col in composite_src]
            if all(v != "" for v in vals):
                new_bk_val = composite_sep.join(vals)
            else:
                new_bk_val = None

            current_bk = getattr(row, "business_key_val", None)
            if current_bk != new_bk_val:
                if new_bk_val is not None:
                    # 중복 충돌 검사
                    conflict_row = db.query(table_model).filter(
                        table_model.business_key_val == new_bk_val,
                        table_model.row_id != row.row_id
                    ).first()
                    
                    if conflict_row:
                        # [Silent Merge & Overwrite] 그냥 덮어씌우고 기존 껍데기 행은 삭제
                        row_to_delete = row
                        row = conflict_row
                        
                        # 1. 임시 행의 모든 실제 값을 충돌 행에 덮어쓰기 병합
                        columns_to_merge = [c.name for c in table_model.__table__.columns]
                        for c_name in columns_to_merge:
                            if c_name in [key_col, "row_id", "business_key_val", "created_at", "updated_at"]:
                                continue
                            
                            is_explicitly_edited = any(u["column_name"] == c_name for u in updates)
                            
                            # [병합 보호 정책] 충돌 행(row)에 이미 사용자 수정(user)이나 핀이 들어있고, 이번에 직접 핀 고정 수정하는 셀이 아니면 기존 값 보존
                            old_ow = overwrites_cache.get((row.row_id, c_name)) if overwrites_cache else None
                            if not old_ow:
                                old_ow = db.query(models.CellOverwrite).filter(
                                    models.CellOverwrite.table_name == table_name,
                                    models.CellOverwrite.row_id == row.row_id,
                                    models.CellOverwrite.column_name == c_name
                                ).first()
                                
                            is_old_user_overwritten = False
                            if old_ow:
                                # collision_merge인 경우는 단순 병합 충돌 메타이므로 보호 가드 대상에서 제외
                                if old_ow.updated_by != "collision_merge" and old_ow.manual_priority_source != "collision_merge":
                                    is_old_user_overwritten = old_ow.is_overwrite or (old_ow.manual_priority_source is not None)
                                
                            # 새 값이 사용자 입력값인지 판단
                            is_new_user_overwritten = (source_name == "user" or (updated_by and updated_by != "system" and "parser" not in str(updated_by).lower()))
                            new_ow = overwrites_cache.get((row_to_delete.row_id, c_name)) if overwrites_cache else None
                            if not new_ow:
                                new_ow = db.query(models.CellOverwrite).filter(
                                    models.CellOverwrite.table_name == table_name,
                                    models.CellOverwrite.row_id == row_to_delete.row_id,
                                    models.CellOverwrite.column_name == c_name
                                ).first()
                            if new_ow:
                                if new_ow.updated_by != "collision_merge" and new_ow.manual_priority_source != "collision_merge":
                                    is_new_user_overwritten = is_new_user_overwritten or new_ow.is_overwrite or (new_ow.manual_priority_source is not None)

                            if is_old_user_overwritten and is_new_user_overwritten:
                                # User vs User collision: apply the newly overwritten value
                                is_value_protected = False
                            else:
                                is_value_protected = is_old_user_overwritten and not is_explicitly_edited

                            new_v = getattr(row_to_delete, c_name, None)
                            
                            old_v = getattr(row, c_name, None)
                            has_changed = False
                            if new_v is not None:
                                if old_v is None:
                                    has_changed = True
                                else:
                                    has_changed = str(old_v).strip() != str(new_v).strip()
                                    
                            if has_changed and not is_value_protected:
                                setattr(row, c_name, new_v)
                                
                                # cell_overwrites_to_upsert 에 충돌 병합 기록
                                ow_key = (table_name, row.row_id, c_name)
                                cell_overwrites_to_upsert[ow_key] = {
                                    "table_name": table_name,
                                    "row_id": row.row_id,
                                    "column_name": c_name,
                                    "is_overwrite": True,
                                    "updated_by": "collision_merge",
                                    "updated_at": datetime.now(),
                                    "manual_priority_source": "collision_merge"
                                }
                                cell_overwrites_to_delete.discard(ow_key)
                                
                                # Audit Log 기록
                                log_dict = create_audit_log(
                                    db, table_name, row.row_id, c_name, old_v, new_v,
                                    "collision_merge", updated_by,
                                    transaction_id=tx_id, business_key=row.business_key_val,
                                    add_to_cache=False
                                )
                                logs_to_cache.append(log_dict)
                                
                                if c_name not in changed_cols:
                                    changed_cols.append(c_name)

                            # [소스 이력 적재] 값 덮어쓰기 보호 여부와 상관없이, 껍데기 행이 가졌던 오리지널 소스 목록은 무조건 적재(Append)
                            from database.models import CellSource
                            # 껍데기 행이 원래 가졌던 진짜 소스 추적
                            old_srcs, _ = _load_metadata_row_cell(
                                db, table_name, row_to_delete.row_id, c_name,
                                is_new=False,
                                sources_cache=None,
                                overwrites_cache=overwrites_cache,
                                cell_sources_to_upsert=None,
                                cell_overwrites_to_upsert=cell_overwrites_to_upsert
                            )
                            
                            # 대상 행에 이미 등록되어 있는 소스명 목록 추출
                            target_srcs, _ = _load_metadata_row_cell(
                                db, table_name, row.row_id, c_name,
                                is_new=False,
                                sources_cache=None,
                                overwrites_cache=overwrites_cache,
                                cell_sources_to_upsert=None,
                                cell_overwrites_to_upsert=cell_overwrites_to_upsert
                            )
                            existing_names = {s.source_name for s in target_srcs} if target_srcs else set()

                            # user 간 충돌 시 기존의 standard "user" 값을 "user (old_exist_xyz)"로 백업하여 원천에 기존 user값을 보존
                            if is_old_user_overwritten and is_new_user_overwritten:
                                old_user_src = next((s for s in target_srcs if s.source_name == "user"), None) if target_srcs else None
                                old_val_to_backup = old_user_src.value if old_user_src else None
                                old_by_to_backup = old_user_src.updated_by if old_user_src else "system"
                                
                                if old_val_to_backup is not None:
                                    backup_src_name = f"user (old_exist_{row.row_id[:6]})"
                                    # 중복 삽입 방지를 위한 선제 삭제
                                    db.query(CellSource).filter(
                                        CellSource.table_name == table_name,
                                        CellSource.row_id == row.row_id,
                                        CellSource.column_name == c_name,
                                        CellSource.source_name == backup_src_name
                                    ).delete()
                                    
                                    backup_src = CellSource(
                                        table_name=table_name,
                                        row_id=row.row_id,
                                        column_name=c_name,
                                        source_name=backup_src_name,
                                        value=clean_str_value(old_val_to_backup),
                                        updated_by=old_by_to_backup
                                    )
                                    db.add(backup_src)

                            src_list = []
                            if old_srcs:
                                for s in old_srcs:
                                    src_list.append((s.source_name, s.value, s.updated_by))
                            else:
                                src_list.append((source_name or "user", new_v, updated_by or "user"))

                            for s_name, s_val, s_by in src_list:
                                effective_src_name = s_name
                                if s_name == "user" and is_old_user_overwritten and is_new_user_overwritten:
                                    effective_src_name = "user"
                                else:
                                    r_id_6 = row_to_delete.row_id[:6] if row_to_delete.row_id else "merged"
                                    suffix = f" ({row_to_delete.business_key_val}_{r_id_6})" if getattr(row_to_delete, "business_key_val", None) else f" ({r_id_6})"
                                    effective_src_name = f"{effective_src_name}{suffix}"

                                db.query(CellSource).filter(
                                    CellSource.table_name == table_name,
                                    CellSource.row_id == row.row_id,
                                    CellSource.column_name == c_name,
                                    CellSource.source_name == effective_src_name
                                ).delete()
                                
                                new_src = CellSource(
                                    table_name=table_name,
                                    row_id=row.row_id,
                                    column_name=c_name,
                                    source_name=effective_src_name,
                                    value=clean_str_value(s_val),
                                    updated_by=s_by or "user"
                                )
                                db.add(new_src)
                                    
                        # 2. 임시 껍데기 행 삭제
                        try:
                            db.delete(row_to_delete)
                            deleted_row_ids.append(row_to_delete.row_id)
                        except Exception:
                            pass
                            
                        # 3. 변경 대상 변경사항 캐시 스위칭
                        if row not in changed_rows:
                            changed_rows.append(row)

                row.business_key_val = new_bk_val
                setattr(row, key_col, new_bk_val)
                
                # 감사 로그 생성
                log_dict = create_audit_log(
                    db, table_name, r_id, key_col, current_bk, new_bk_val,
                    "set_priority_sync", updated_by,
                    transaction_id=tx_id, business_key=new_bk_val,
                    add_to_cache=False
                )
                logs_to_cache.append(log_dict)
            
        if row not in changed_rows:
            changed_rows.append(row)
            
    for r in changed_rows:
        r.is_graph_synced = False
        r.needs_graph_rollback = True
            
    # 3. 벌크 갱신 및 삭제 수행
    if logs_to_cache:
        bulk_insert_audit_logs(db, logs_to_cache)
    bulk_upsert_cell_overwrites(db, list(cell_overwrites_to_upsert.values()))
    bulk_delete_cell_overwrites(db, list(cell_overwrites_to_delete))

    db.commit()
    
    if logs_to_cache:
        from audit_cache import audit_cache
        audit_cache.add_logs_batch(logs_to_cache)
        
    serialized_logs = []
    for log in logs_to_cache:
        log_copy = log.copy()
        if isinstance(log_copy.get("timestamp"), datetime):
            log_copy["timestamp"] = log_copy["timestamp"].isoformat()
        serialized_logs.append(log_copy)
        
    return changed_rows, serialized_logs, deleted_row_ids

def set_cell_manual_priority(db: Session, table_name: str, row_id: str, col_name: str, source_name: Optional[str], updated_by: str = "user"):
    """수동 소스 우선순위(Pin)를 설정합니다."""
    changed_rows, logs, deleted_row_ids = set_cell_manual_priority_batch(db, table_name, [{"row_id": row_id, "column_name": col_name}], source_name, updated_by)
    return changed_rows[0] if changed_rows else None, [col_name] if logs else [], deleted_row_ids


# ----------------- 그래프 싱크 메타 관리 헬퍼 -----------------
_ontology_cache = None

def get_ontology_mapping():
    """온톨로지 매핑 캐시 조회 (check_needs_rollback 판정용).

    [QA G1-④] v2 항목은 검증·정규화 + enrichment RESOLVED_AS 자동 승격을 적용해
    graph materializer가 보는 매핑과 **같은 신호원**을 쓴다(enrichment target 컬럼 변경이
    rollback 신호에 잡히도록). v1 키(tables/default)는 원본 그대로 보존(레거시 폴백).
    """
    global _ontology_cache
    if _ontology_cache is not None:
        return _ontology_cache

    import os, json
    ont_path = _paths.config_path("ontology_mapping.json")
    raw = {}
    if os.path.exists(ont_path):
        try:
            with open(ont_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception:
            raw = {}

    merged = {}
    if isinstance(raw, dict):
        # v1 레거시 키는 원본 유지 (check_needs_rollback의 v1 폴백 경로)
        for k in ("tables", "default"):
            if k in raw:
                merged[k] = raw[k]
    try:
        import ontology_config
        from enrichment_config import load_enrichment_rules
        normalized = ontology_config.validate_ontology_mapping(raw, known_tables=None)
        normalized = ontology_config.synthesize_enrichment_mappings(
            normalized, load_enrichment_rules(known_tables=None)
        )
        merged.update(normalized)
    except Exception:
        # 검증/승격 실패 시에도 v1 폴백은 유지 — 판정 신호가 전멸하지 않게
        pass

    _ontology_cache = merged
    return _ontology_cache

def check_needs_rollback(table_name: str, modified_cols: list) -> bool:
    """변경된 컬럼 중 그래프 관계(엣지/identity) 형성에 영향을 주는 컬럼이 있는지 판별합니다.

    [Ontology G1] v2 형식({table: {node, edges}})과 v1 형식({tables: {..relationships..}})을
    모두 인식한다. v2에서는 노드 identity 또는 엣지 target_identity_from 컬럼 변경 시 True.
    """
    if not modified_cols:
        return False
    ontology = get_ontology_mapping()

    # v2 형식: 최상위 {table_name: {node/edges}} 항목
    v2_cfg = ontology.get(table_name)
    if isinstance(v2_cfg, dict) and isinstance(v2_cfg.get("node"), dict):
        relation_cols = set()
        identity = v2_cfg["node"].get("identity")
        if isinstance(identity, str):
            relation_cols.add(identity)
        elif isinstance(identity, list):
            relation_cols.update(c for c in identity if isinstance(c, str))
        for edge in v2_cfg.get("edges") or []:
            if not isinstance(edge, dict):
                continue
            t_from = edge.get("target_identity_from")
            if isinstance(t_from, str):
                relation_cols.add(t_from)
            elif isinstance(t_from, list):
                relation_cols.update(c for c in t_from if isinstance(c, str))
        return any(col in relation_cols for col in modified_cols)

    # v1 형식(구 Neo4j 경로) 폴백
    table_cfg = ontology.get("tables", {}).get(table_name, ontology.get("default", {}))
    rel_cfgs = table_cfg.get("relationships", {})

    for col in modified_cols:
        if col in rel_cfgs:
            return True
    return False

