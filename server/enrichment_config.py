"""Enrichment Queue 규칙 로더/검증기 (docs/spec/ENRICHMENT_QUEUE_SPEC.md §5).

`server/config/enrichment_rules.json`(사용자 영역, gitignored)을 읽어 검증·정규화한다.
- 웹서버(main.py): `/enrichment/rules`, `/enrichment/rules/{rule}/references/{i}` 응답 소스.
  설정 파일이 작으므로 map-presets 패턴과 동일하게 **요청 시마다 디스크에서 읽는다**
  (무중단 반영 — 별도 캐시/워처 불필요).
- 체인 워커(chain_ingestion_worker.load_chain_rules): `load_enrichment_chain_rules()`로
  dedup 투영 체인 룰을 자동 파생(synthesize)하여 기존 chain_rules에 병합한다.
  SYSTEM_RELOAD 시 load_chain_rules가 재호출되므로 워커에도 무중단 반영된다.

파일 스키마 (rule_name -> rule):
{
  "bonding_wafer_attribution": {
    "source_table":  "bonding_log",            // 필수: 대량 원본 테이블
    "derived_table": "bonding_job_inventory",  // 필수: 파생 영속 테이블(table_config.json 등록 필요)
    "decision_key":  ["equipment", "event_time"],  // 필수: 판단키(1..N 컬럼)
    "target_fields": ["wafer_id"],             // 필수: 사람이 채울 필드(파생 테이블 컬럼)
    "list_columns":  ["chip_count", "lot_hint"],   // 선택: 워크리스트 표시 단서
    "aggregations":  { "chip_count": "count" },    // 선택(서버 전용): 집계 컬럼. v1은 count만
    "enabled": true,                            // 선택(기본 true)
    "reference_views": [                        // 선택: 참조뷰 — 쿼리는 서버에만, 클라엔 label만 노출
      { "label": "lot event",
        "query": "SELECT ... WHERE equipment = :equipment",  // 인라인 SQL (:bind는 decision_key만)
        "limit": 200,                                         // 선택(기본 200, 최대 1000)
        "candidate_for": { "wafer_id": "wf_id" } },            // 선택: 후보 선언(target_field -> 뷰 결과 컬럼)
      { "label": "lot-slot history", "query_ref": "lot_slot_history" }  // config/enrichment_queries/<ref>.sql
    ]
  }
}

`candidate_for` — ①"후보가 1개면 판단이 아니라 확인"의 **선언**(2026-07-30):
어떤 참조뷰의 어떤 결과 컬럼이 어떤 target_field의 후보값을 나르는지 **사람이 선언**한다.
선언이 없는 뷰는 표시 전용이며 **절대** 후보 원천이 되지 않는다 — 맵 오버레이의
`derive_table_binding`이 첫 데이터 컬럼을 추측해 DECOY를 붙인 것이 라이브에서 실증된 뒤로,
이 시스템에서 바인딩은 선언만 인정한다. 유도가 왜 위험한지는 사용자 실 config가 그대로 보여준다:
동일 규칙의 뷰 #0("lot-slot 웨이퍼 이력" — lot+slot 조회 → 후보 1개)과
뷰 #1("같은 lot 전체 슬롯" — lot만 조회 → 후보 N개)이 **둘 다 `wafer_id` 컬럼을 가진다.**
컬럼명으로 유도하는 구현은 #1까지 후보로 삼아 오답을 자동 확정했을 것이다.

파생 테이블 키 계약(중요): derived_table의 table_config는
`composite_key_source ⊆ decision_key` 이거나 `business_key ∈ decision_key` 여야 한다.
(dedup mapper가 판단키로부터 business_key_val을 결정론적으로 조립하기 위함 — 위반 시 규칙 스킵.)
"""
import json
import logging
import os
import re

logger = logging.getLogger("EnrichmentConfig")

from paths import CONFIG_DIR  # single override point (ASSY_DATA_ROOT)
ENRICHMENT_RULES_PATH = os.path.join(CONFIG_DIR, "enrichment_rules.json")
QUERY_REF_DIR = os.path.join(CONFIG_DIR, "enrichment_queries")

# ---------------------------------------------------------------------------
# READ CAPS - the numbers that CLIP A READ, each named for what it clips
# ---------------------------------------------------------------------------
# THREE DIFFERENT NUMBERS WERE ALL CALLED `limit`, AND AN OPERATOR PAID FOR IT
# [2026-08-05, live incident]
#     A sweep refused rows with `distinct_truncated`. The operator was told to
#     "raise the limit" and raised the only one within reach - the CLI's
#     `--probe-limit`, which is the KEY BUDGET and touches no read at all. It
#     changed nothing, because the number doing the clipping was a different one
#     with the same name. There were three:
#       1. how many KEYS we examine        - CLI `--probe-limit`, an outer budget
#       2. how many ROWS one read returns  - the view's `limit`, and, one layer
#          under it, a module constant no operator could reach
#       3. how many DISTINCT VALUES the probe's GROUP BY returns - which was
#          ALSO the view's `limit`, the same declaration wearing a second meaning
#     Two of them were spelled `limit` in the config, one was spelled `limit` in
#     the CLI, and the refusal named none of them. So the vocabulary is the fix,
#     not the size: below, and in the CLI, and in every truncation refusal, a cap
#     is named for WHAT IT CLIPS and says WHERE IT IS SET. Nothing here may be
#     called plain `limit` again.
#
# WHERE THEY LIVE
#     `ingestion_settings.json` -> `enrichment_read_caps` block. Not a new file
#     and not a new section: that file already carries this subsystem's other
#     operational ceiling (`enrichment_auto_confirm_max_keys`, the per-work-unit
#     KEY budget) beside its kill switch, so the read caps join their siblings
#     rather than starting a fourth home for enrichment numbers.
#
# AN ABSENT DECLARATION KEEPS TODAY'S VALUE, AND THE REFUSAL SAYS SO
#     Deliberately NOT the `map_alignment` posture, where an undeclared threshold
#     refuses to rank. That is right there because the missing number destroys
#     the MEANING of the answer - without a margin threshold, "winner" is a claim
#     nobody checked. These caps are not decision thresholds; they are safety
#     ceilings. A missing one does not make a verdict wrong, it only removes
#     protection, and refusing on absence would take every operator who has not
#     edited their config offline on upgrade - a bigger outage than the bug.
#     Infinity is equally wrong: a bind-less declared view scans the whole table
#     once per key, and `probe_scan_rows` is the only thing standing between that
#     and a 10M-row ingestion.
#     What absence must NOT do is stay invisible, which is what made this
#     incident expensive. Every truncation refusal reports `cap_declared`, so an
#     operator who never knew the knob existed is told its name, its value, and
#     the file it belongs in AT THE MOMENT THEY ARE REFUSED.
READ_CAPS_SETTINGS_KEY = "enrichment_read_caps"

CAP_REFERENCE_ROWS_DEFAULT = "reference_rows_default"
CAP_REFERENCE_ROWS_MAX = "reference_rows_max"
CAP_PROBE_SCAN_ROWS = "probe_scan_rows"
CAP_PROBE_DISTINCT_VALUES = "probe_distinct_values"

#: The values shipped with the code. These are what an UNDECLARED cap inherits -
#: never a second opinion about a declared one. `probe_distinct_values` is None
#: because its shipped behaviour is not a number at all: it inherits the view's
#: own row `limit`, which is exactly the double duty that caused the incident.
#: Declaring it is how an operator separates "how many rows a human reads" from
#: "how many distinct values the probe may see" - two questions that were one
#: declaration until today.
SHIPPED_READ_CAPS = {
    CAP_REFERENCE_ROWS_DEFAULT: 200,
    CAP_REFERENCE_ROWS_MAX: 1000,
    CAP_PROBE_SCAN_ROWS: 5000,
    CAP_PROBE_DISTINCT_VALUES: None,
}

INGESTION_SETTINGS_PATH = os.path.join(CONFIG_DIR, "ingestion_settings.json")

# SQLAlchemy text()와 동일 계열의 바인드 파라미터 패턴 (`::text` 캐스트는 매치되지 않음)
_BIND_PARAM_RE = re.compile(r"(?<![:\w]):([A-Za-z_]\w*)")
_QUERY_REF_NAME_RE = re.compile(r"^[A-Za-z0-9_\-]+$")

# `candidate_for`의 뷰 결과 컬럼명. 후보 프로브 SQL에는 이 이름이 **보간**되므로
# (바인딩 불가 — 식별자다) 로드 시점에 형태를 강제한다. 실행 시 인용부호로 감싸는 것과
# 이 검증은 **둘 다** 필요하다: 인용부호만으로는 `a" OR "1"="1` 류가 닫히지 않는다.
_CANDIDATE_COLUMN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_warned_caps = set()


def _load_ingestion_settings() -> dict:
    """Read `ingestion_settings.json`, or `{}`.

    Small file, read at a work-unit boundary and passed down as a snapshot - the
    D1 discipline. Used only when a caller supplies no settings; the auto-confirm
    paths hand their OWN already-loaded snapshot to `load_read_caps`, so a work
    unit reads this file once and the knobs and the caps cannot come from two
    different reads of it.
    """
    try:
        if os.path.exists(INGESTION_SETTINGS_PATH):
            with open(INGESTION_SETTINGS_PATH, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                return loaded
    except Exception as e:
        logger.warning("Could not load ingestion settings (%s): %s", INGESTION_SETTINGS_PATH, e)
    return {}


def read_cap_home(name: str) -> str:
    """Where an operator SETS this cap. Carried into refusals verbatim.

    A refusal that names no repair sends someone to a person, and the person they
    reach may name the wrong number - that is precisely how this incident ran.
    """
    return f"ingestion_settings.json -> \"{READ_CAPS_SETTINGS_KEY}\": {{\"{name}\": ...}}"


def load_read_caps(settings: dict = None) -> dict:
    """Snapshot of the four read caps.

    Returns `{name: {"value": int|None, "declared": bool}}`. `declared` is not
    decoration: it is the difference between "your cap is 5000" and "nobody ever
    set a cap, and 5000 is what the code shipped with", and only the second one
    tells an operator there is a knob to turn.

    An unreadable declaration (not a positive integer) is NOT a declaration: it
    warns once and falls back to the shipped value, the same posture
    `max_keys_per_unit` already takes. Folding a typo into a number silently is
    how a config file starts lying about what is in force.
    """
    raw = (settings if settings is not None else _load_ingestion_settings()).get(
        READ_CAPS_SETTINGS_KEY)
    raw = raw if isinstance(raw, dict) else {}
    out = {}
    for name, shipped in SHIPPED_READ_CAPS.items():
        val = raw.get(name)
        if val is None:
            out[name] = {"value": shipped, "declared": False}
            continue
        if isinstance(val, bool) or not isinstance(val, int) or val <= 0:
            key = (name, repr(val))
            if key not in _warned_caps:
                _warned_caps.add(key)
                logger.warning(
                    "Ignoring '%s.%s' value %r in ingestion_settings.json - expected a "
                    "positive integer. Falling back to the shipped value %r.",
                    READ_CAPS_SETTINGS_KEY, name, val, shipped)
            out[name] = {"value": shipped, "declared": False}
            continue
        out[name] = {"value": val, "declared": True}
    return out


def cap_value(caps: dict, name: str):
    """The number in force for `name`, from a snapshot (or freshly loaded)."""
    return (caps if caps is not None else load_read_caps())[name]["value"]


def cap_declared(caps: dict, name: str) -> bool:
    return bool((caps if caps is not None else load_read_caps())[name]["declared"])


def reset_cap_warnings():
    """Test hook - forget warn-once state for the read caps."""
    _warned_caps.clear()


def _record(rejections, scope: str, subject, detail: str):
    """무효 선언 1건을 수집기에 남긴다(수집기 미제공 시 기존 동작 = 로그만).

    `ontology_config._record`와 같은 자세이고 같은 이유다 — 로그에만 있는 스킵은
    아무도 보지 못하는 스킵이다. 형태는 `{scope, subject, detail}`이며 **명명된 사유는
    싣지 않는다**: 닫힌 어휘(`config_resolve_report.REASONS`)로의 사상은 보고서 계층의
    책임이고, 로더는 사람이 읽을 구체적 사유만 만든다.
    (ontology_config는 같은 자리를 `table`로 부른다 — enrichment의 주체는 규칙/뷰라
    `subject`로 일반화했다.)
    """
    if rejections is None:
        return
    rejections.append({"scope": scope, "subject": subject, "detail": detail})


def _is_str_list(value) -> bool:
    return isinstance(value, list) and len(value) > 0 and all(
        isinstance(v, str) and v.strip() for v in value
    )


def _resolve_view_query(view: dict) -> tuple:
    """참조뷰의 SQL 본문을 해석한다. 반환: (sql|None, 실패사유|None)."""
    inline = view.get("query")
    ref = view.get("query_ref")
    if inline is not None:
        if not isinstance(inline, str) or not inline.strip():
            return None, "'query' must be a non-empty string"
        return inline.strip(), None
    if ref is not None:
        if not isinstance(ref, str) or not _QUERY_REF_NAME_RE.match(ref):
            return None, f"invalid query_ref name: {ref!r}"
        ref_path = os.path.join(QUERY_REF_DIR, f"{ref}.sql")
        if not os.path.exists(ref_path):
            return None, f"query_ref file not found: {ref_path}"
        try:
            with open(ref_path, "r", encoding="utf-8") as f:
                return f.read().strip(), None
        except Exception as e:
            return None, f"failed to read query_ref file: {e}"
    return None, "reference view requires 'query' or 'query_ref'"


def _validate_view_sql(sql: str, decision_key: list) -> str:
    """참조뷰 SQL 안전성 검증. 통과 시 None, 실패 시 사유 문자열 반환.

    - 단일 SELECT(또는 WITH … SELECT)문만 허용, ';' 다중 스테이트먼트 금지.
    - 바인드 파라미터는 decision_key 컬럼명만 허용(경계 계약: params도 동일 제약).
    실행 시엔 SQLAlchemy text() 바인딩만 사용하므로 값 주입(injection)은 구조적으로 불가.
    """
    body = sql.strip().rstrip(";").strip()
    if not body:
        return "empty query"
    if ";" in body:
        return "multiple statements are not allowed"
    head = body.lstrip("(").lstrip().lower()
    if not (head.startswith("select") or head.startswith("with")):
        return "only SELECT (or WITH ... SELECT) statements are allowed"
    binds = set(_BIND_PARAM_RE.findall(body))
    invalid = sorted(binds - set(decision_key))
    if invalid:
        return f"bind params must be decision_key columns only; invalid: {invalid}"
    return None


def required_bind_params(sql: str) -> set:
    """참조뷰 SQL이 **실제로 요구하는** 바인드 파라미터 이름 집합.

    같은 규칙의 뷰들이 서로 다른 부분집합을 쓴다(뷰 #0은 lot+slot, 뷰 #1은 lot만).
    호출자가 판단키 전체를 넘기면 남는 값은 무해하지만, "이 뷰를 이 판단키로 실행할 수
    있는가"를 **실행 전에** 알아야 후보 해석이 `missing_bind`라는 이름 있는 거절을
    돌려줄 수 있다(추측해서 실행하고 예외를 삼키는 대신).
    """
    return set(_BIND_PARAM_RE.findall((sql or "").strip().rstrip(";")))


def _normalize_candidate_for(rule_name: str, label: str, raw, target_fields: list,
                             rejections: list = None) -> dict:
    """참조뷰의 `candidate_for` 선언을 정규화한다: {target_field: 뷰 결과 컬럼명}.

    **선언만 인정하고 절대 유도하지 않는다.** 무효 항목은 그 항목만 버리고(뷰 자체는
    표시용으로 살린다) 이유를 로그에 남긴다 — 조용히 남겨두면 "선언했다"고 읽히는데
    동작은 아니게 되고, 그 불일치를 아무도 말해 주지 않는다(effort_metric의
    와일드카드 거절과 같은 자세).

    뷰 결과 컬럼이 실제로 **존재**하는지는 SQL을 실행해야 알 수 있으므로 로드 시점에
    검증하지 않는다 — 해석 시점의 이름 있는 거절(`candidate_column_missing`)로 다룬다.
    다만 **형태**(식별자 문법)는 여기서 강제한다: 이 이름은 후보 프로브 SQL에 보간되므로
    검증이 실행보다 먼저 와야 한다.
    """
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        msg = (f"reference view '{label}': 'candidate_for' must be an object "
               f"{{target_field: view_column}}; ignored (view stays display-only)")
        logger.warning(f"[Enrichment:{rule_name}] {msg}")
        _record(rejections, "reference_view", f"{rule_name}/{label}", msg)
        return {}
    allowed = set(target_fields or [])
    out = {}
    for field, column in raw.items():
        if field not in allowed:
            msg = (f"reference view '{label}': candidate_for key '{field}' is not a "
                   f"target_field of this rule; REJECTED (not a candidate source)")
            logger.warning(f"[Enrichment:{rule_name}] {msg}")
            _record(rejections, "reference_view", f"{rule_name}/{label}", msg)
            continue
        if not isinstance(column, str) or not column.strip():
            msg = (f"reference view '{label}': candidate_for['{field}'] must be a non-empty "
                   f"view column name (got {column!r}); REJECTED")
            logger.warning(f"[Enrichment:{rule_name}] {msg}")
            _record(rejections, "reference_view", f"{rule_name}/{label}", msg)
            continue
        name = column.strip()
        if not _CANDIDATE_COLUMN_RE.match(name):
            msg = (f"reference view '{label}': candidate_for['{field}'] = {name!r} is not a "
                   f"plain SQL identifier ([A-Za-z_][A-Za-z0-9_]*); REJECTED. This name is "
                   f"interpolated into the candidate probe query, so its shape is checked "
                   f"BEFORE anything runs.")
            logger.warning(f"[Enrichment:{rule_name}] {msg}")
            _record(rejections, "reference_view", f"{rule_name}/{label}", msg)
            continue
        out[field] = name
    return out


def _normalize_reference_views(rule_name: str, raw_views, decision_key: list,
                               target_fields: list = None, rejections: list = None,
                               caps: dict = None) -> list:
    """참조뷰 목록을 정규화한다. 유효하지 않은 뷰는 **목록에서 제외**된다.

    주의: 제외는 로드 시점에 일어나므로 `/enrichment/rules`의 label 목록과
    `/references/{index}`의 인덱스가 항상 같은 (필터링된) 목록을 가리킨다 — 인덱스 정합 보장.
    """
    views = []
    if raw_views is None:
        return views
    if not isinstance(raw_views, list):
        logger.warning(f"[Enrichment:{rule_name}] 'reference_views' must be a list; ignoring")
        _record(rejections, "rule", rule_name, "'reference_views' must be a list; ignored")
        return views
    for i, raw in enumerate(raw_views):
        if not isinstance(raw, dict) or not isinstance(raw.get("label"), str) or not raw.get("label").strip():
            logger.warning(f"[Enrichment:{rule_name}] reference view #{i} dropped: missing 'label'")
            _record(rejections, "reference_view", f"{rule_name}/#{i}",
                    "reference view dropped: missing 'label'")
            continue
        sql, err = _resolve_view_query(raw)
        if err is None:
            err = _validate_view_sql(sql, decision_key)
        if err is not None:
            logger.warning(f"[Enrichment:{rule_name}] reference view '{raw.get('label')}' dropped: {err}")
            _record(rejections, "reference_view", f"{rule_name}/{raw.get('label')}",
                    f"reference view dropped: {err}")
            continue
        # The view's `limit` is a ROW cap for the human-facing display, and it is
        # kept spelled `limit` because it is the product owner's declaration in
        # their own file. Its default and its ceiling are no longer code: an
        # operator whose reference table is wider than someone's guess can move
        # `reference_rows_max` instead of being clamped without being told.
        default_rows = cap_value(caps, CAP_REFERENCE_ROWS_DEFAULT)
        max_rows = cap_value(caps, CAP_REFERENCE_ROWS_MAX)
        limit = raw.get("limit", default_rows)
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = default_rows
        # A declaration ABOVE the ceiling used to be clamped in silence, and
        # silence is what let "raise the limit" look like it had been tried.
        if limit > max_rows:
            logger.warning(
                "[Enrichment:%s] reference view '%s' declares limit=%s, above the "
                "'%s.%s' ceiling of %s - clamped. Raise that cap in "
                "ingestion_settings.json if the view really needs to be wider.",
                rule_name, raw.get("label"), limit,
                READ_CAPS_SETTINGS_KEY, CAP_REFERENCE_ROWS_MAX, max_rows)
        limit = max(1, min(limit, max_rows))
        label = raw["label"].strip()
        body = sql.strip().rstrip(";").strip()
        views.append({
            "label": label,
            "query": body,
            "limit": limit,
            "candidate_for": _normalize_candidate_for(
                rule_name, label, raw.get("candidate_for"), target_fields,
                rejections=rejections),
            "required_binds": sorted(required_bind_params(body)),
        })
    return views


def _normalize_claim_contract(rule_name: str, raw, decision_key: list,
                              target_fields: list, reference_views: list,
                              rejections: list = None):
    """Validate the optional ontology/action projection contract.

    A bad additive contract must not disable the legacy Enrichment rule.  It is dropped
    by name and reported, while dedup/queue/reference behaviour remains unchanged.
    Nothing is inferred from field spelling: the Claim anchor, slot semantics and supply
    sources are all declarations.
    """
    if raw is None:
        return None

    def reject(detail):
        message = f"claim_contract ignored: {detail}"
        logger.warning(f"[Enrichment:{rule_name}] {message}")
        _record(rejections, "claim_contract", rule_name, message)
        return None

    if not isinstance(raw, dict):
        return reject("must be an object")
    version = raw.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        return reject("version must be an integer >= 1")
    label = raw.get("label_ko")
    if not isinstance(label, str) or not label.strip():
        return reject("label_ko must be a non-empty string")
    anchor = raw.get("anchor")
    if not isinstance(anchor, dict):
        return reject("anchor must be an object")
    predicate = anchor.get("predicate")
    payload_path = anchor.get("payload_path")
    object_type = anchor.get("object_type")
    key_map = anchor.get("decision_key_map")
    for name, value in (("predicate", predicate), ("payload_path", payload_path),
                        ("object_type", object_type)):
        if not isinstance(value, str) or not value.strip():
            return reject(f"anchor.{name} must be a non-empty string")
    from ledger import vocabulary as ledger_vocabulary
    known_predicates = set(ledger_vocabulary.PREDICATES)
    if predicate.strip() not in known_predicates:
        return reject("anchor.predicate is not in the canonical ledger vocabulary")
    if not all(_CANDIDATE_COLUMN_RE.match(part)
               for part in payload_path.strip().split(".")):
        return reject("anchor.payload_path must be a dot path of plain identifiers")
    if not isinstance(key_map, dict) or set(key_map) != set(decision_key):
        return reject("anchor.decision_key_map must cover every decision_key exactly")
    if not all(isinstance(value, str) and _CANDIDATE_COLUMN_RE.match(value)
               for value in key_map.values()):
        return reject("anchor.decision_key_map values must be plain key names")

    raw_slots = raw.get("slots")
    if not isinstance(raw_slots, list) or not raw_slots:
        return reject("slots must be a non-empty list")
    slots = []
    for index, slot in enumerate(raw_slots):
        if not isinstance(slot, dict):
            return reject(f"slots[{index}] must be an object")
        target = slot.get("target_field")
        slot_predicate = slot.get("predicate")
        slot_path = slot.get("payload_path")
        if target not in target_fields:
            return reject(f"slots[{index}].target_field is not a rule target_field")
        if not isinstance(slot_predicate, str) or not slot_predicate.strip():
            return reject(f"slots[{index}].predicate must be a non-empty string")
        if slot_predicate.strip() not in known_predicates:
            return reject(
                f"slots[{index}].predicate is not in the canonical ledger vocabulary")
        if (not isinstance(slot_path, str) or not slot_path.strip()
                or not all(_CANDIDATE_COLUMN_RE.match(part)
                           for part in slot_path.strip().split("."))):
            return reject(f"slots[{index}].payload_path must be a dot path of identifiers")
        slots.append({
            "target_field": target,
            "predicate": slot_predicate.strip(),
            "payload_path": slot_path.strip(),
        })
    slot_targets = [slot["target_field"] for slot in slots]
    if len(slot_targets) != len(set(slot_targets)):
        return reject("slots must not repeat a target_field")
    if set(slot_targets) != set(target_fields):
        return reject("slots must cover every target_field exactly")

    raw_sources = raw.get("sources") or []
    if not isinstance(raw_sources, list):
        return reject("sources must be a list")
    sources = []
    for index, source in enumerate(raw_sources):
        if not isinstance(source, dict):
            return reject(f"sources[{index}] must be an object")
        kind = source.get("kind")
        if kind not in {"reference_view", "human", "translator"}:
            return reject(
                f"sources[{index}].kind must be reference_view, human, or translator")
        targets = source.get("targets")
        if not _is_str_list(targets) or not set(targets).issubset(target_fields):
            return reject(f"sources[{index}].targets must name rule target_fields")
        authority = source.get("authority")
        if authority not in {"candidate", "observe", "confirm"}:
            return reject(
                f"sources[{index}].authority must be candidate, observe, or confirm")
        normalized = {"kind": kind, "targets": list(targets),
                      "authority": authority}
        if kind == "reference_view":
            view_index = source.get("view_index")
            if (not isinstance(view_index, int) or isinstance(view_index, bool)
                    or view_index < 0 or view_index >= len(reference_views)):
                return reject(f"sources[{index}].view_index is out of range")
            declared = set(reference_views[view_index].get("candidate_for") or {})
            if authority == "candidate" and not set(targets).issubset(declared):
                return reject(
                    f"sources[{index}] candidate targets are not declared by that view")
            normalized["view_index"] = view_index
        else:
            source_name = source.get("source")
            if not isinstance(source_name, str) or not source_name.strip():
                return reject(f"sources[{index}].source must be a non-empty string")
            normalized["source"] = source_name.strip()
        sources.append(normalized)

    return {
        "version": version,
        "label_ko": label.strip(),
        "anchor": {
            "predicate": predicate.strip(),
            "payload_path": payload_path.strip(),
            "object_type": object_type.strip(),
            "decision_key_map": dict(key_map),
        },
        "slots": slots,
        "sources": sources,
    }


def _validate_rule(name: str, raw: dict, known_tables: dict, rejections: list = None,
                   caps: dict = None) -> tuple:
    """규칙 1건을 검증·정규화한다. 반환: (normalized|None, 실패사유|None)."""
    if not isinstance(raw, dict):
        return None, "rule must be an object"
    if raw.get("enabled", True) is False:
        return None, None  # 비활성 — 오류 아님, 조용히 제외
    source_table = raw.get("source_table")
    derived_table = raw.get("derived_table")
    if not isinstance(source_table, str) or not source_table.strip():
        return None, "'source_table' is required"
    if not isinstance(derived_table, str) or not derived_table.strip():
        return None, "'derived_table' is required (spec §5 확정: 필수)"
    decision_key = raw.get("decision_key")
    if not _is_str_list(decision_key):
        return None, "'decision_key' must be a non-empty list of column names"
    target_fields = raw.get("target_fields")
    if not _is_str_list(target_fields):
        return None, "'target_fields' must be a non-empty list of column names"
    overlap = sorted(set(decision_key) & set(target_fields))
    if overlap:
        return None, f"decision_key and target_fields must not overlap: {overlap}"

    list_columns = raw.get("list_columns") or []
    if not isinstance(list_columns, list) or not all(isinstance(c, str) for c in list_columns):
        return None, "'list_columns' must be a list of column names"

    aggregations = {}
    raw_aggs = raw.get("aggregations") or {}
    if not isinstance(raw_aggs, dict):
        return None, "'aggregations' must be an object {column: fn}"
    for col, fn in raw_aggs.items():
        if fn != "count":
            logger.warning(f"[Enrichment:{name}] aggregation '{col}: {fn}' dropped (v1 supports 'count' only)")
            continue
        aggregations[col] = fn

    # 테이블/컬럼 존재 검증 (table_config가 주어진 경우에만 — 순수 구조 검증과 분리)
    if known_tables is not None:
        src_cfg = known_tables.get(source_table)
        if src_cfg is None:
            return None, f"source_table '{source_table}' is not registered in table_config.json"
        drv_cfg = known_tables.get(derived_table)
        if drv_cfg is None:
            return None, f"derived_table '{derived_table}' is not registered in table_config.json"
        src_cols = set(src_cfg.get("column_types", {}).keys())
        drv_cols = set(drv_cfg.get("column_types", {}).keys())
        missing = [c for c in decision_key if c not in src_cols]
        if missing:
            return None, f"decision_key column(s) missing in source table: {missing}"
        missing = [c for c in decision_key if c not in drv_cols]
        if missing:
            return None, f"decision_key column(s) missing in derived table: {missing}"
        missing = [c for c in target_fields if c not in drv_cols]
        if missing:
            return None, f"target_fields column(s) missing in derived table: {missing}"
        kept_list_cols = []
        for c in list_columns:
            if c in drv_cols:
                kept_list_cols.append(c)
            else:
                logger.warning(f"[Enrichment:{name}] list_column '{c}' dropped: not in derived table columns")
        list_columns = kept_list_cols
        aggregations = {c: fn for c, fn in aggregations.items() if c in drv_cols}
        # 파생 테이블 키 계약: dedup mapper가 판단키로 business_key_val을 조립할 수 있어야 한다.
        comp_src = drv_cfg.get("composite_key_source")
        bk_col = drv_cfg.get("business_key")
        if comp_src:
            not_in_key = [c for c in comp_src if c not in decision_key]
            if not_in_key:
                return None, (
                    f"derived table composite_key_source must be a subset of decision_key "
                    f"(violation: {not_in_key})"
                )
        elif not (bk_col and bk_col in decision_key):
            return None, (
                "derived table must declare composite_key_source ⊆ decision_key "
                "or business_key ∈ decision_key (dedup upsert key contract)"
            )

    reference_views = _normalize_reference_views(
        name, raw.get("reference_views"), decision_key, target_fields,
        rejections=rejections, caps=caps)
    normalized = {
        "name": name,
        # ① auto-confirm opt-in. Carried through RAW (not coerced) so
        # enrichment_candidates.rule_auto_confirm_enabled can warn-once about a
        # non-boolean instead of silently reading it as truthy.
        "auto_confirm": raw.get("auto_confirm", False),
        # 「선언이 없다」와 「false로 선언했다」는 다른 사실이고, 위 필드만으로는 구별되지
        # 않는다. `config_resolve_report`가 그 둘을 다른 문장으로 렌더하려면 존재 여부가
        # 필요하다 — 값이 아니라 **선언의 유무**를 나르는 필드다(클라 노출 대상 아님).
        "auto_confirm_declared": isinstance(raw, dict) and "auto_confirm" in raw,
        # ② 이 규칙이 **맵 정렬 화면이 다룰 수 있는 규칙인가** - 현장이 선언한다.
        # 🔴 유도하지 않는다. 오늘 이것을 말하는 것이 아무것도 없어서 화면은 규칙을 전부
        #    늘어놓고 첫 번째를 제안했고, 운영에서 그 첫 번째는 정렬이 불가능한
        #    `dt_job_lot_slot_attribution`이었다. 「target_field 이름에 frame이 들어 있으면
        #    정렬 규칙」 같은 유도는 **이 화면이 다른 모든 자리에서 거부하는 바로 그 추론**이다
        #    (I4: 그럴듯한 기본값이 선언을 사칭한다).
        # 🔴 `is True`가 엄격한 이유는 `map_push_ok`와 같다: config 오타("true"/1)가 선언으로
        #    승격되면 안 된다. 미선언은 「정렬 대상 아님」이고 그것은 기본값이 아니라 사실이다
        #    - 아무도 정렬 가능하다고 주장한 적이 없다는 뜻이므로.
        "alignment": raw.get("alignment") is True,
        "source_table": source_table.strip(),
        "derived_table": derived_table.strip(),
        "decision_key": list(decision_key),
        "target_fields": list(target_fields),
        "list_columns": list(list_columns),
        "aggregations": aggregations,
        "reference_views": reference_views,
        "claim_contract": _normalize_claim_contract(
            name, raw.get("claim_contract"), decision_key, target_fields,
            reference_views, rejections=rejections),
    }
    return normalized, None


def validate_enrichment_rules(raw_config: dict, known_tables: dict = None,
                              rejections: list = None, caps: dict = None) -> list:
    """설정 dict 전체를 검증한다. 유효 규칙의 정규화 리스트를 반환(무효 규칙은 로깅 후 스킵).

    rejections: 선택 수집기 리스트 — 스킵된 선언을 `{scope, subject, detail}`로 누적한다
    (`_record` 참조). 반환값 형태는 수집기 유무와 무관하게 동일하다.
    """
    rules = []
    # ONE snapshot for the whole file, not one read per view (the D1 discipline:
    # a work unit that re-reads config mid-walk can normalize two views against
    # two different ceilings and neither of them is what the file says).
    caps = caps if caps is not None else load_read_caps()
    if not isinstance(raw_config, dict):
        logger.error("enrichment_rules.json must be an object {rule_name: rule}")
        _record(rejections, "file", None,
                "enrichment_rules.json must be an object {rule_name: rule} — "
                "the whole file was ignored")
        return rules
    for name, raw in raw_config.items():
        if not isinstance(name, str) or not name.strip():
            logger.warning("[Enrichment] rule with empty name skipped")
            _record(rejections, "rule", name, "rule with an empty name skipped")
            continue
        normalized, err = _validate_rule(name, raw, known_tables, rejections=rejections,
                                         caps=caps)
        if err is not None:
            logger.warning(f"[Enrichment:{name}] rule skipped: {err}")
            _record(rejections, "rule", name, f"rule skipped: {err}")
            continue
        if normalized is not None:
            rules.append(normalized)
    return rules


def load_enrichment_rules(path: str = None, known_tables: dict = None,
                          rejections: list = None, caps: dict = None) -> list:
    """enrichment_rules.json을 읽어 검증된 규칙 리스트를 반환한다(파일 없음 → 빈 목록).

    파일 **부재**는 거부가 아니다(선언이 없을 뿐) — 수집기에 남기지 않는다.
    `/graph/mapping-summary`가 `source.exists`로 같은 구분을 하는 것과 같은 규율이다.
    """
    rules_path = path or ENRICHMENT_RULES_PATH
    if not os.path.exists(rules_path):
        return []
    try:
        with open(rules_path, "r", encoding="utf-8") as f:
            raw_config = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load enrichment rules from {rules_path}: {e}")
        _record(rejections, "file", None,
                f"enrichment_rules.json could not be read ({e.__class__.__name__}) — "
                f"NO rule is in effect")
        return []
    return validate_enrichment_rules(raw_config, known_tables=known_tables,
                                     rejections=rejections, caps=caps)


def load_enrichment_chain_rules(path: str = None, known_tables: dict = None) -> list:
    """enrichment 규칙으로부터 dedup 투영용 체인 인제션 룰을 자동 파생한다.

    파생 룰은 기존 chain_rules와 완전히 동일한 형태(trigger/target/mapper/is_batch)라서
    체인 워커 파이프라인(HOL 가드·SLO 계측·warmup·재시도)을 그대로 탄다.
    전체 enrichment 규칙을 `enrichment` 키에 내장하여 generic mapper가 참조한다.
    """
    chain_rules = []
    for rule in load_enrichment_rules(path=path, known_tables=known_tables):
        chain_rules.append({
            "name": f"enrichment_dedup:{rule['name']}",
            "trigger_table": rule["source_table"],
            "target_table": rule["derived_table"],
            "mapper_module": "enrichment_mapper",
            "mapper_function": "map_enrichment_dedup",
            "is_batch": True,
            "enabled": True,
            "enrichment": rule,
        })
    return chain_rules


# 서버가 강제하는 LIMIT 래핑 — 참조뷰 **표시** 실행의 유일한 형태.
# (2026-07-30 [F9]: main.py `get_enrichment_reference`가 갖고 있던 인라인 사본을 제거하고
#  라우트가 `execute_reference_view`를 호출하도록 합쳤다 — 정의는 이제 하나다.)
REFERENCE_LIMIT_WRAP_SQL = "SELECT * FROM ({query}) AS __enrichment_ref LIMIT :__enrichment_limit"

# 후보 프로브 래핑 — **표시 경로와 다른 질문**을 던지기 때문에 형제 정의로 존재한다.
#
# 왜 필요한가 (2026-07-30 실측): 라이브 참조뷰 `공정 이력(wafer_process)`는 `limit: 50`인데
# (lot,slot) 하나당 행이 최소 69 · 평균 135.4 · 최대 217이다 — **80개 키 전부가 상한을 넘는다.**
# distinct 계산은 서버가 행을 잘라낸 **뒤** 파이썬에서 일어나므로(`enrichment_candidates`),
# 51번째 행이 다른 wafer_id를 나르고 있어도 보이지 않고 `ambiguous`는 영영 발화하지 않는다.
# 즉 오늘의 `single` 판정은 "매핑이 우연히 정상"이라는 아무도 검사하지 않는 가정 위에 있다.
#
# 왜 뷰를 고치지 않는가: 그 뷰에는 두 번째 소비자(사람의 표시 — 시간순 **행**이 필요하다)가
# 있다. 선언은 하나로 두고 **실행 형태만 질문에 맞춰 갈라진다.**
#
# `{column}`은 바인딩할 수 없는 **식별자**라 보간된다 — 그래서 ① 로드 시점
# `_CANDIDATE_COLUMN_RE` 검증이 실행보다 먼저 오고 ② 여기서 인용부호로 감싼다.
# 값은 여전히 SQLAlchemy 바인딩으로만 전달된다.
#
# 🔴 컬럼 참조는 **반드시 별칭으로 한정한다**(`__enrichment_ref."col"`). SQLite는
# 큰따옴표 안의 이름이 컬럼으로 해석되지 않으면 **문자열 리터럴로 강등**한다(DQS 호환
# 동작). 그래서 `SELECT "not_a_column"`은 에러가 아니라 'not_a_column'이라는 값 1개를
# 돌려주고, 프로브는 그것을 **후보 1개**로 읽어 컬럼명 자체를 자동 확정한다 —
# 이 모듈이 절대 하지 말아야 할 거짓말이 정확히 그것이다(2026-07-30 실측).
# 한정된 참조는 문자열 리터럴이 될 수 없으므로 SQLite도 `no such column`으로 실패하고,
# 호출자의 `candidate_column_missing` 진단으로 흘러간다. Postgres에도 그대로 옳다.
# 🔴 `SUM(COUNT(*)) OVER ()` — 스캔한 **전체** 행수. 창 함수는 GROUP BY 뒤·LIMIT 앞에
# 평가되므로, 바깥 LIMIT이 그룹을 잘라내도 이 값은 **잘리기 전 전체 합**이다.
# (2026-07-30 QA: 종전엔 반환된(=잘린) 그룹의 count만 합산해 `scanned`가 과소 보고됐고,
#  그 값이 `CANDIDATE_PROBE_MAX_ROWS`와 비교되던 탓에 **진짜로 잘린 읽기가
#  `row_truncated=False`로 읽힐 수 있었다.** 그룹이 잘렸는지와 행이 잘렸는지는 별개
#  사실이므로 별개로 세야 한다.) Postgres는 numeric을 돌려주므로 호출부에서 int로 접는다.
CANDIDATE_GROUP_WRAP_SQL = (
    'SELECT __c, COUNT(*) AS __n, SUM(COUNT(*)) OVER () AS __scanned FROM ('
    'SELECT __enrichment_ref."{column}" AS __c FROM ({query}) AS __enrichment_ref '
    'LIMIT :__enrichment_scan_rows'
    ') AS __enrichment_cand GROUP BY __c LIMIT :__enrichment_limit'
)

# 프로브가 훑을 **행** 상한은 이제 `enrichment_read_caps.probe_scan_rows`다(위 블록).
# GROUP BY는 상위 LIMIT으로 조기 종료할 수 없으므로, 바인드 없는 뷰
# (`required_binds == []`)가 선언되면 키마다 전체 테이블을 훑게 된다 — 1,000만 행 규율의
# 유일한 방어선이다. 상한에 닿으면 결과는 **잘린 읽기**이므로 `single`을 주장하지 않고
# 이름 있는 거절(`probe_truncated`)이 된다.
# 🔴 **이 상수는 사라졌다.** 종전 이름은 `CANDIDATE_PROBE_MAX_ROWS`였고 값이 코드에만
#    있어 조작자가 닿을 수 없었다 — 2026-08-05 사고에서 「limit을 올려라」가 아무 효과도
#    없었던 이유의 절반이 이것이다. 나머지 절반은 세 숫자가 같은 이름으로 불린 것이다.


class ReferenceViewError(Exception):
    """참조뷰 실행 실패. 메시지에 쿼리 본문을 절대 담지 않는다(경계 계약: 본문 비노출)."""


# ---------------------------------------------------------------------------
# DRIVER DIAGNOSTICS - name the cause WITHOUT quoting the statement
# ---------------------------------------------------------------------------
# THE CONTRACT ABOVE IS REAL, AND SO WAS THE BUG UNDER IT  [2026-08-05]
#     `ReferenceViewError` used to be built from `e.__class__.__name__` alone.
#     `str(e)` - where PostgreSQL puts `column "foo" does not exist` - was
#     dropped, and `main.py` logged that same already-stripped message, so an
#     authoring mistake in a reference view had its cause NOWHERE: not in the
#     response, not in the server log. The view was undebuggable.
#
#     The intent was not paranoia. MEASURED (PostgreSQL 18.0, psycopg2 2.9.11,
#     SQLAlchemy 2.x, read-only, local instance), the obvious "just include
#     str(e)" repair ships the ENTIRE statement AND the bind values:
#
#       str(sa_exc) == '(psycopg2.errors.UndefinedColumn) ... "nosuchcol" ...
#                       LINE 1: ...FROM (SELECT nosuchcol AS wafer_id FROM ...
#                       [SQL: SELECT * FROM (SELECT __enrichment_ref."wafer_id"
#                             AS __c FROM (SELECT nosuchcol ...) AS ...]
#                       [parameters: {...}]'
#
#     So both halves are true at once: the body must not ship, and the diagnosis
#     must. PostgreSQL separates them for us - the `LINE n:`/caret echo lives in
#     the exception's TEXT, while the condition lives in structured fields on
#     `psycopg2.Error.diag`, and `diag.message_primary` is the one sentence with
#     no echo in it. Measured over 19 error classes: always single-line, 13..26
#     characters.
#
# 🔴 MEASURED, AND THE OPPOSITE OF WHAT EVERYONE ASSUMES: for `42703
#    undefined_column`, PostgreSQL does **NOT** populate `diag.column_name`.
#    Verified on three separate undefined-column statements - the attribute is
#    simply absent. `column_name` is populated for constraint/not-null
#    conditions, not for name RESOLUTION. On the flagship case of this defect
#    the offending column name therefore exists ONLY inside `message_primary`,
#    which is why that field is load-bearing here rather than a nicety. Anyone
#    "hardening" this by dropping `message_primary` and keeping only the
#    structured identifier fields re-creates the original bug exactly.
#
# 🔴 MESSAGES ARE LOCALIZED. This server answers in Korean (`lc_messages`), so
#    `message_primary` and `severity` are Korean while `sqlstate` and the
#    psycopg2 condition CLASS name are not. That is why both of the
#    language-independent handles always ship, and why no test may assert on
#    English message text.

# Diagnostic fields we are willing to put in an HTTP response. Every one is an
# identifier PostgreSQL RESOLVED, never text it copied out of the statement.
DIAG_IDENTIFIER_FIELDS = ("schema_name", "table_name", "column_name",
                          "constraint_name", "datatype_name")

# Deliberately NOT read, each for its own reason:
#   `internal_query` / `context`  - can carry a PL/pgSQL body, i.e. a statement.
#   `message_detail`              - carries DATA values (e.g. the key of a
#                                   unique violation), which the body ban is
#                                   about just as much as the SQL text.
#   `statement_position`          - an offset into the WRAPPED statement, not
#                                   into the author's query. Remapping it by
#                                   subtracting the wrapper prefix was
#                                   considered and REJECTED: SQLAlchemy
#                                   re-renders `:__enrichment_limit` into the
#                                   driver's own placeholder before PostgreSQL
#                                   parses the string, so the prefix we would
#                                   subtract is not the prefix PostgreSQL
#                                   counted. An offset pointing at the wrong
#                                   character is worse than no offset.

# The longest `message_primary` measured was 26 characters. This cap is not a
# tuning knob, it is the second half of the shape guard below.
DIAG_MESSAGE_MAX_CHARS = 200

# SQLSTATEs whose PRIMARY message quotes STATEMENT TEXT rather than an
# identifier. Measured, not assumed:
#   42601 syntax_error            -> 'syntax error at or near "SELCT"'
#                                    the quoted token is raw statement text.
#   22xxx data_exception          -> 'invalid input syntax for type integer: "x"'
#                                    where "x" was copied out of a literal in
#                                    the statement (measured with a literal the
#                                    view author wrote, not a bind value).
# For these, PostgreSQL's prose is withheld but the diagnosis is NOT silent: the
# psycopg2 condition class name still ships (`SyntaxError`,
# `InvalidTextRepresentation`, ...). psycopg2 generates those class names from
# PostgreSQL's own errcodes table, so they are stable, English, and contain no
# statement text - "your SQL does not parse" is still said out loud, and the
# message names the log as the place the full text is.
SQLSTATE_QUOTES_STATEMENT = ("42601",)
SQLSTATE_CLASS_QUOTES_STATEMENT = ("22",)

_SEE_LOG = "see server log"


def _quotes_statement_text(sqlstate: str) -> bool:
    # `str()` on purpose: an exception raised INSIDE error reporting would
    # replace the error being reported, which is the failure mode this whole
    # block exists to end. Nothing here may assume the driver's field types.
    code = str(sqlstate or "")
    return code in SQLSTATE_QUOTES_STATEMENT or code[:2] in SQLSTATE_CLASS_QUOTES_STATEMENT


def _diag_shape_ok(text_value: str) -> bool:
    """Is this short enough and single-line enough to be a CONDITION, not an echo?

    The guard exists so the SQLSTATE list above does not have to be complete. A
    statement echo is structurally multi-line (`LINE n:` plus a caret line) and
    long; every measured `message_primary` was one line of at most 26
    characters. A future PostgreSQL condition that pastes statement text into
    its primary message is caught here without anyone having measured it first.
    """
    return ("\n" not in text_value and "\r" not in text_value
            and 0 < len(text_value) <= DIAG_MESSAGE_MAX_CHARS)


def describe_driver_error(exc) -> str:
    """One line naming WHY a user-authored statement failed - safe for a response.

    NEVER returns an empty or contentless string. Every branch, INCLUDING every
    way of failing to read the diagnostics, degrades BY NAME: "no driver error
    attached", "no structured diagnostics from this driver", "diagnostics
    unreadable". Silence is the defect this function exists to remove, so "I
    could not read the diagnostics" has to be sayable - otherwise a driver
    without `.diag` (SQLite, which is what the test suite runs on) quietly falls
    back to exactly the behaviour being repaired.
    """
    exc_cls = exc.__class__.__name__
    orig = getattr(exc, "orig", None)      # SQLAlchemy keeps the DBAPI error here
    if orig is None:
        return f"{exc_cls}; no driver error attached, {_SEE_LOG}"

    orig_cls = orig.__class__.__name__     # psycopg2 names this after PG's condition
    try:
        diag = getattr(orig, "diag", None)
        sqlstate = str(getattr(diag, "sqlstate", None) or "") if diag is not None else ""
    except Exception:
        # A driver whose diagnostics object raises on access. Say so; do not
        # let an exception inside error REPORTING replace the error.
        return f"{orig_cls}; driver diagnostics unreadable, {_SEE_LOG}"

    if diag is None or not sqlstate:
        return f"{orig_cls}; no structured diagnostics from this driver, {_SEE_LOG}"

    parts = []
    if _quotes_statement_text(sqlstate):
        parts.append(f"message withheld (this condition's text quotes the "
                     f"statement), {_SEE_LOG}")
    else:
        try:
            message = (getattr(diag, "message_primary", None) or "").strip()
            hint = (getattr(diag, "message_hint", None) or "").strip()
        except Exception:
            message, hint = "", ""
        if _diag_shape_ok(message):
            parts.append(message)
        else:
            parts.append(f"no usable primary message, {_SEE_LOG}")
        # The hint is where PostgreSQL says "Perhaps you meant to reference the
        # column \"tables.table_name\"" - measured, identifier-shaped, and the
        # single most actionable sentence it can produce for a typo.
        if _diag_shape_ok(hint):
            parts.append(f"hint: {hint}")

    for field in DIAG_IDENTIFIER_FIELDS:
        try:
            value = (getattr(diag, field, None) or "").strip()
        except Exception:
            continue
        if _diag_shape_ok(value):
            parts.append(f"{field}={value}")

    return f"{orig_cls}/{sqlstate}: " + "; ".join(parts)


# ---------------------------------------------------------------------------
# INCIDENT THROTTLE - a diagnostic that buries itself is the defect again
# ---------------------------------------------------------------------------
# WHY THE FULL TRACEBACK CANNOT BE UNCONDITIONAL  [2026-08-05, ruled]
#     The display path is bounded by clicks. The PROBE path is not: the chain
#     worker probes up to `enrichment_candidates.DEFAULT_MAX_KEYS_PER_UNIT`
#     (200) keys per work unit, per declaring view, and it runs continuously. A
#     single broken view therefore produced ~400 identical tracebacks per unit,
#     forever. That is a disk problem, but the worse half is that it makes the
#     ONE traceback that matters unfindable - which is the same defect this
#     round exists to fix, wearing a different hat.
#
# WHAT IS KEPT, AND WHY THE KEY HAS TWO PARTS
#     First occurrence of a (site, condition) pair: the FULL driver text and
#     traceback, exactly as before. Repeats: counted, not retraced.
#     The condition is part of the key so a SECOND, GENUINELY DIFFERENT failure
#     at the same site can never be swallowed by the first one's entry - a
#     throttle that hid a new defect behind an old one would be a worse bug
#     than the flood.
#
# SUPPRESSED IS NOT SILENT
#     Repeats are counted and the count is stated twice over: periodically
#     (`DRIVER_ERROR_REPEAT_EVERY`) so a long unit never goes quiet, and
#     exactly at the work-unit boundary via `drain_driver_error_incidents`,
#     which reports the true total and clears the state. Clearing matters as
#     much as counting: without it a view broken at 09:00 logs one traceback
#     and is silent for the rest of the day.
#
# Not locked. The counters are log bookkeeping, a lost increment under a race
# costs one unit off a count, and a lock on the ERROR path is a worse trade
# than that. Same posture as `_warned_caps` above.

DRIVER_ERROR_REPEAT_EVERY = 50

# The two sites, named once. The tests assert on these strings and the raise
# sites read them, so there is no third spelling to drift.
SITE_REFERENCE_VIEW = "reference query execution failed"
SITE_CANDIDATE_PROBE = "candidate probe execution failed"

_driver_error_incidents = {}   # (site, condition) -> repeats suppressed since the first


def _incident_condition(exc) -> str:
    """The half of the key that must not collapse two different failures.

    SQLSTATE when the driver has one; otherwise the driver's exception class,
    so a driver WITHOUT structured diagnostics still distinguishes `no such
    column` from `no such table` instead of throttling them as one thing.
    """
    orig = getattr(exc, "orig", None)
    try:
        diag = getattr(orig, "diag", None)
        sqlstate = str(getattr(diag, "sqlstate", None) or "") if diag is not None else ""
    except Exception:
        sqlstate = ""
    if sqlstate:
        return sqlstate
    return (orig if orig is not None else exc).__class__.__name__


def reset_driver_error_incidents() -> None:
    """Test hook - forget throttle state (same shape as `reset_cap_warnings`)."""
    _driver_error_incidents.clear()


def drain_driver_error_incidents() -> list:
    """Report every suppressed repeat, then forget. Call at a work-unit boundary.

    Returns `[(site, condition, total_occurrences), ...]` for callers that want
    to say it in their own summary; it also logs, because the caller that most
    needs this (`AutoConfirmCollector.flush`) is the one whose log the operator
    actually reads.
    """
    drained = sorted((site, condition, repeats + 1)
                     for (site, condition), repeats in _driver_error_incidents.items()
                     if repeats)
    _driver_error_incidents.clear()
    for site, condition, total in drained:
        logger.error(
            "[Enrichment] %s (%s) failed %d time(s) in this work unit. The first one "
            "was logged above with the driver's full text and traceback; the other "
            "%d were identical by SQLSTATE and were counted instead of retraced.",
            site, condition, total, total - 1)
    return drained


def _reference_view_failure(what: str, exc: Exception, *, throttle: bool = False,
                            follow_up: bool = False) -> ReferenceViewError:
    """Log the driver's error IN FULL; return the redacted one for the caller to raise.

    THE LOG IS NOT THE BROWSER. The no-body contract governs the HTTP RESPONSE.
    An operator reading the server log must see the driver's own text and its
    traceback, or the cause exists nowhere - which is precisely the state this
    replaced: the response carried a class name and `main.py` logged that same
    stripped message, so the diagnosis had been destroyed before either reader
    could reach it. (Nothing re-raised either, so the implicit `__context__`
    chain was never printed. The raise sites now use `raise ... from exc` as
    well, so a debugger sees the chain explicitly.)

    BOTH RAISE SITES GO THROUGH HERE ON PURPOSE. The reason there is a helper
    for four lines is that the previous four lines existed TWICE - the display
    path and the candidate-probe path - and both copies were wrong in the same
    way. One fact, one spelling.

    `throttle` - only the worker's probe path sets it. The display path is
    bounded by a person clicking, and that person is USUALLY MID-REPAIR: the
    client caches a 400 per (row, view), so a second request means the author
    actually changed something. Throttling that would answer their second
    attempt with silence, which is a worse trade than a few duplicate
    tracebacks. So the two paths deliberately do NOT share the throttle.

    `follow_up` - this failure is already explained by an incident the caller
    just reported, so it opens no incident and prints no traceback. Exactly one
    caller sets it: `enrichment_candidates._diagnose_probe_failure`, whose
    re-query exists to tell `candidate_column_missing` from `view_error`. When
    that re-query ALSO fails, it has told us what it exists to tell us and has
    added no new cause - the driver error is the same root failure reached by a
    second route.
    """
    described = describe_driver_error(exc)
    error = ReferenceViewError(f"{what} ({described})")

    if follow_up:
        # DEBUG, no traceback: this is a diagnostic probe's expected outcome,
        # not a second incident.
        logger.debug("[Enrichment] %s - follow-up read for an already-reported "
                     "failure (%s); no new incident.", what, described)
        return error

    if not throttle:
        logger.error(
            "[Enrichment] %s - full driver error follows. The HTTP response carries "
            "only the redacted form; the query body is never returned to a client.",
            what, exc_info=exc)
        return error

    key = (what, _incident_condition(exc))
    repeats = _driver_error_incidents.get(key)
    if repeats is None:
        _driver_error_incidents[key] = 0
        logger.error(
            "[Enrichment] %s - full driver error follows. The HTTP response carries "
            "only the redacted form; the query body is never returned to a client. "
            "Further failures of THIS condition (%s) at this site will be counted "
            "rather than retraced; a different condition here still gets its own "
            "traceback.",
            what, key[1], exc_info=exc)
        return error

    repeats += 1
    _driver_error_incidents[key] = repeats
    if repeats % DRIVER_ERROR_REPEAT_EVERY == 0:
        logger.error(
            "[Enrichment] %s (%s) has now failed %d time(s); the first was logged "
            "above with its traceback. Still failing - this is a count, not a new "
            "cause.", what, key[1], repeats + 1)
    return error


def _isolated_execute(db, stmt, params) -> tuple:
    """Execute ONE user-authored reference statement inside a SAVEPOINT.

    WHY A SAVEPOINT AND NOT A BARE try/except  [2026-07-30, measured live]
        On PostgreSQL a failed statement ABORTS the enclosing transaction. Every
        later statement on that connection then raises InFailedSqlTransaction,
        and - this is the part that makes it silent - `COMMIT` on an aborted
        transaction RETURNS NORMALLY while the server converts it to ROLLBACK.
        Catching the driver error is therefore not containment: the session is
        already dead and neither the caller nor the log can tell.

        Read-only measurement against the live database:
            bad SELECT            -> ProgrammingError
            next SELECT           -> InternalError          (session poisoned)
            db.commit()           -> returned normally      (server rolled back)
            same inside SAVEPOINT -> next SELECT succeeds    (session alive)

        Two things depended on that not happening, and both were broken:
        - `enrichment_candidates._diagnose_probe_failure` re-queries the view on
          the SAME session to tell `candidate_column_missing` from `view_error`.
          On an aborted session that re-query can only fail, so
          `candidate_column_missing` was UNREACHABLE on PostgreSQL - the one
          refusal the diagnostic exists to produce.
        - the chain worker swallows any exception out of the auto-confirm hook,
          so a poisoned session escaped into `process_pending_groups`, whose
          `db.commit()` of the outbox bookkeeping (`processed_chain=True`) then
          rolled back. The group was never marked processed, so the batch loop
          re-ran it forever and the retry quarantine never advanced.

        Cost is two extra round trips (SAVEPOINT + RELEASE) per reference
        statement - noise next to a GROUP BY over up to `probe_scan_rows`
        rows of a user-authored view, and the alternative price was a stuck
        worker.

        pysqlite has NO such rule (it does not even open a transaction for a
        SELECT), which is why the suite could certify a refusal production could
        not reach. The fault injection that restores the rule for the test suite
        lives in `tests/test_enrichment_candidates.py` (`pg_abort_semantics`).
    """
    nested = db.begin_nested()
    try:
        result = db.execute(stmt, params)
        columns = list(result.keys())
        rows = result.fetchall()
    except Exception:
        nested.rollback()
        raise
    nested.commit()
    return columns, rows


def missing_binds(view: dict, bind_params: dict = None) -> list:
    """Which required bind params this view cannot be asked with.

    A bind whose value is BLANK is missing, not supplied. The two facts read the
    same from the view's side - there is no value to put in the WHERE clause -
    but only one of them used to be named. Passing `slot=''` through produced a
    legal query that matched nothing, and a zero-row read is indistinguishable
    from "no such evidence exists" at the call site.

    `enrichment_candidates.resolve_target_candidate` has always folded blank into
    missing (`clean_str_value(v) != ""`); this is the same funnel, applied where
    the SQL is actually built, so the DISPLAY path and the CANDIDATE path refuse
    the same view for the same reason. That matters now that a partial decision
    key is workable: the views that still bind get asked, and the view that
    cannot be asked says so instead of returning an empty table.
    """
    from database import crud

    needed = set(view.get("required_binds") or required_bind_params(view.get("query", "")))
    have = {k for k, v in (bind_params or {}).items() if crud.clean_str_value(v) != ""}
    return sorted(needed - have)


def blank_key_columns(rule: dict, key_values: dict) -> list:
    """Which of THIS rule's decision-key columns did not survive.

    `missing_binds` one level up. Same funnel (`crud.is_blank_value`), asked of
    the RULE's decision key instead of a view's binds, because after the
    2026-08-05 ruling - a partial decision key is worked on whatever survives -
    "which parts are gone" stopped being an internal detail of one function and
    became the question three separate paths ask:

      - `enrichment_mapper.map_enrichment_dedup`  (may this row make a derived
        identity at all?)
      - `enrichment_candidates.resolve_target_candidate` (`no_decision_key`, and
        the `partial_key` stamp that rides on every verdict)
      - `enrichment_candidates.AutoConfirmCollector.collect` (skip the probe
        queries for a row that can bind nothing)

    and, through the mapper, `enrichment_backfill`. Those were four spellings of
    one question, and two of them (mapper, backfill) answered `any blank` while
    the ruling says `all blank` - so a retroactive sweep and a live increment
    could not have disagreed only because BOTH were still on the old answer.

    Read from the RULE, not from `key_values`: a caller that omits a column
    entirely has the same blank key as one that passes "" for it, and only the
    rule knows the full list.
    """
    from database import crud

    return sorted(k for k in (rule.get("decision_key") or [])
                  if crud.is_blank_value(key_values.get(k)))


def key_is_wholly_blank(rule: dict, key_values: dict) -> bool:
    """Nothing survives - there is nothing to match on.

    THE line between "incomplete" and "empty", and the only blankness that is
    still a refusal. Arithmetic, not policy: a key with one part in it IS the
    surviving key and selects real rows; a key with no parts in it selects the
    same rule-wide everything for every keyless row, which is a statement about
    no row in particular.

    A rule with no `decision_key` cannot happen (`_validate_rule` rejects it) and
    is reported as wholly blank rather than as a survivable key, so a malformed
    rule refuses instead of matching the entire source table.
    """
    decision_key = rule.get("decision_key") or []
    if not decision_key:
        return True
    return len(blank_key_columns(rule, key_values)) == len(decision_key)


def partial_key_identity_supported(decision_key: list, derived_cfg: dict) -> bool:
    """Can a derived row whose decision key is only PARTLY present own an identity?

    🔴 THE ENRICHMENT MAPPER DOES NOT DECIDE THIS - `crud` DOES, and it decides it
    from the DERIVED TABLE's declaration, not from the rule. Measured in
    `crud.apply_row_update_internal` (§"복합 비즈니스 키 실시간 재계산"), the three
    key contracts `_validate_rule` accepts behave differently on a blank key part:

      composite_key_source == decision_key  -> SAFE. A blank component makes
          `all(v != "")` false, and the branch under it falls back to
          `update_item.business_key_val` on insert - i.e. to the positional
          identity the mapper supplied. A later refinement never re-derives,
          because the composite source columns ARE the decision key and therefore
          never appear in `changed_cols` for an existing row.

      composite_key_source ⊊ decision_key   -> DESTRUCTIVE. The surviving columns
          are the whole composite source, so `all(v != "")` is TRUE and crud
          OVERRIDES the mapper with the identity of the COMPLETE key - then finds
          the complete key's row as a conflict and runs [Silent Merge &
          Overwrite]: the partial row's values are merged over the complete row's
          and one row is deleted. No error, no count, whole table.

      business_key ∈ decision_key (no composite) -> DESTRUCTIVE the other way.
          `_update_row_business_key` copies `updates[business_key]` verbatim, so a
          partial key whose blank column IS the business key gets the EMPTY
          identity - and every such row on the table gets the same one.

    So the ruling is honoured where the declaration can carry it and REFUSED BY
    NAME where it cannot. The refusal is not a policy preference: on those two
    contracts the write does not mean what it says. The repair is one config line
    - declare `composite_key_source` = the rule's decision key on the derived
    table - and the refusal says so.

    (Widening `crud`'s composition to be partial-aware would fix all three, but
    that is the identity rule for EVERY table and every writer, not an enrichment
    decision. Named here so the question is answerable rather than rediscovered.)
    """
    comp_src = derived_cfg.get("composite_key_source")
    return bool(comp_src) and set(comp_src) == set(decision_key or [])


def execute_reference_view(db, view: dict, bind_params: dict = None,
                           caps: dict = None, *, follow_up: bool = False) -> tuple:
    """참조뷰 1건을 서버측 정의로 실행한다. 반환: (columns, rows).

    LIMIT은 서버가 강제한다(뷰 설정값, 내부 LIMIT이 더 작으면 그 값 유지) — 사용자 쿼리를
    서브쿼리로 감싸 상한을 바인딩한다. 값은 SQLAlchemy 바인딩으로만 전달되어 주입이
    구조적으로 불가하다.

    바인드는 **SQL이 실제로 요구하는 이름만** 넘긴다: 호출자가 판단키 전체를 넘겨도
    되고, 요구 바인드가 빠졌거나 **값이 비었으면** 실행하지 않고 `ReferenceViewError`를
    올린다(드라이버 예외를 삼켜 "후보 없음"으로 위장하지 않는다 - `missing_binds`).
    """
    from sqlalchemy import text

    needed = set(view.get("required_binds") or required_bind_params(view.get("query", "")))
    supplied = dict(bind_params or {})
    missing = missing_binds(view, supplied)
    if missing:
        raise ReferenceViewError(f"missing required bind param(s): {missing}")

    exec_params = _probe_params(view, supplied, needed, caps)
    stmt = text(REFERENCE_LIMIT_WRAP_SQL.format(query=view["query"]))
    try:
        columns, raw_rows = _isolated_execute(db, stmt, exec_params)
    except Exception as e:
        # `_isolated_execute` has ALREADY rolled back to its SAVEPOINT by the
        # time we get here, and reading `.diag` touches no connection - the
        # diagnostics are a snapshot the exception carries. Measured: every diag
        # field above was read AFTER the rollback. Nothing about when the
        # rollback happens, or what it rolls back to, changes here.
        #
        # NOT throttled: this path is bounded by a person clicking, and that
        # person is usually mid-repair. See `_reference_view_failure`.
        raise _reference_view_failure(SITE_REFERENCE_VIEW, e,
                                      follow_up=follow_up) from e
    return columns, [list(r) for r in raw_rows]


def _probe_params(view: dict, supplied: dict, needed: set, caps: dict = None) -> dict:
    params = {k: v for k, v in supplied.items() if k in needed}
    params["__enrichment_limit"] = (view.get("limit")
                                    or cap_value(caps, CAP_REFERENCE_ROWS_DEFAULT))
    return params


def probe_distinct_cap(view: dict, caps: dict = None) -> tuple:
    """How many DISTINCT values the probe may see, and whether that was declared.

    Returns `(value, declared)`. Undeclared it is the view's own row `limit`,
    which is exactly today's behaviour and exactly the double duty that made the
    incident hard to see: one declaration answering "how many rows should a human
    read" was silently also answering "how many distinct values may the probe
    consider". Declaring `probe_distinct_values` separates them.
    """
    declared = cap_value(caps, CAP_PROBE_DISTINCT_VALUES)
    if declared is not None:
        return declared, True
    return (view.get("limit") or cap_value(caps, CAP_REFERENCE_ROWS_DEFAULT)), False


def execute_candidate_probe(db, view: dict, column: str, bind_params: dict = None,
                            caps: dict = None) -> dict:
    """후보 프로브 1건 — 뷰 결과 **전체**에 대해 `column`의 distinct 값과 행수를 센다.

    반환: `{"pairs": [(value, count), ...], "scanned": int,
             "row_truncated": bool, "distinct_truncated": bool,
             "scan_rows_cap": int, "scan_rows_cap_declared": bool,
             "distinct_values_cap": int, "distinct_values_cap_declared": bool}`

    🔴 **절단 사실에는 반드시 「어느 상한이 잘랐는가」가 따라붙는다**(2026-08-05 사고).
    `row_truncated`만 돌려주면 호출자는 「읽기가 잘렸다」까지만 말할 수 있고, 조작자는
    세 개의 `limit` 중 무엇을 올려야 하는지 알 수 없다 — 실제로 틀린 것을 올렸다.

    `pairs`는 DB의 GROUP BY 결과(정규화 이전)다 — `clean_str_value` 접기는 호출자가
    수행하고 count를 합산한다. 'WF01 '과 'WF01'은 DB에선 두 그룹이지만 접은 뒤 하나다.

    두 종류의 절단을 **구분해서** 알린다. **둘 다 「읽기가 잘렸다」는 같은 사실이고,
    잘린 읽기에서 「후보가 정확히 하나」는 증명할 수 없으므로 호출자는 둘 다 이름 있는
    거절로 바꿔야 한다**(`probe_truncated` / `distinct_truncated`):
      - `distinct_truncated`: distinct 값이 `limit`을 넘었다(그래서 limit+1을 요청한다 —
        `value_suggest`가 truncated를 증명하는 방식과 같다).
        🔴 **「>limit이면 어차피 2개 이상이니 `ambiguous`가 알아서 잡는다」는 틀렸다**
        (2026-07-30 QA 실증). 호출자는 `clean_str_value`로 값을 **접는다** — 잘려 돌아온
        limit+1개 그룹이 전부 같은 정규값으로 접히면 distinct는 1개가 되고, 판정은
        보이지 않는 그룹에 진짜 모순이 있는 채로 `single`이 된다. 실증(`limit: 1`):
        `pairs=[('WF01',1), ('WF01 ',1)]` → 접으면 {WF01} → `single`, 그러나 잘려나간
        곳에 WF02가 있었다. 그래서 절단은 **접기 이전 사실**로서 그 자체가 거절이다.
        🔴 이 상한의 이름은 `enrichment_read_caps.probe_distinct_values`이고, 미선언이면
        뷰의 표시용 `limit`을 그대로 쓴다 — 「사람이 읽을 행 수」와 「프로브가 볼 distinct
        수」가 한 선언에 묶여 있던 것이 2026-08-05 사고의 절반이다.
      - `row_truncated`: 스캔이 `enrichment_read_caps.probe_scan_rows`에 닿았다. `scanned`는 그룹이
        잘리기 전의 전체 행수(`SUM(COUNT(*)) OVER ()`)이므로 그룹 절단과 무관하게 참이다.
    """
    from sqlalchemy import text

    if not _CANDIDATE_COLUMN_RE.match(column or ""):
        # 로더가 이미 막지만, 이 함수는 SQL을 보간하므로 자기 입력을 스스로 검증한다.
        raise ReferenceViewError("candidate column is not a plain SQL identifier")

    needed = set(view.get("required_binds") or required_bind_params(view.get("query", "")))
    supplied = dict(bind_params or {})
    missing = missing_binds(view, supplied)
    if missing:
        raise ReferenceViewError(f"missing required bind param(s): {missing}")

    caps = caps if caps is not None else load_read_caps()
    distinct_cap, distinct_declared = probe_distinct_cap(view, caps)
    scan_rows = cap_value(caps, CAP_PROBE_SCAN_ROWS)
    exec_params = _probe_params(view, supplied, needed, caps)
    # distinct_cap + 1: (cap+1)번째 distinct 값이 돌아오면 그것이 절단의 증거다.
    exec_params["__enrichment_limit"] = distinct_cap + 1
    exec_params["__enrichment_scan_rows"] = scan_rows
    stmt = text(CANDIDATE_GROUP_WRAP_SQL.format(query=view["query"], column=column))
    try:
        _, raw = _isolated_execute(db, stmt, exec_params)
    except Exception as e:
        # Same helper as the display path - see `_reference_view_failure`. These
        # two sites are the whole of this file's user-SQL error handling and
        # they move together by construction now.
        #
        # THROTTLED: the worker probes up to 200 keys per unit per declaring
        # view, continuously, and nothing bounds that but this flag.
        raise _reference_view_failure(SITE_CANDIDATE_PROBE, e, throttle=True) from e

    rows = [(r[0], int(r[1] or 0)) for r in raw]
    # `__scanned`는 바깥 LIMIT이 그룹을 자르기 **전**의 전체 행수다. 반환된 그룹의
    # count 합으로 대신하면, 그룹이 잘린 순간 `scanned`가 과소 보고되고 `row_truncated`가
    # 진짜 잘린 읽기를 놓친다(2026-07-30 QA). 두 절단은 별개 사실이므로 별개로 센다.
    scanned = int(raw[0][2] or 0) if raw else 0
    return {
        "pairs": rows,
        "scanned": scanned,
        "row_truncated": scanned >= scan_rows,
        "distinct_truncated": len(rows) > distinct_cap,
        # WHICH cap, and whether anyone declared it. The refusal downstream is
        # only as useful as these four fields: without them it says a read was
        # clipped and leaves the operator to guess which of three numbers spelled
        # `limit` was responsible.
        "scan_rows_cap": scan_rows,
        "scan_rows_cap_declared": cap_declared(caps, CAP_PROBE_SCAN_ROWS),
        "distinct_values_cap": distinct_cap,
        "distinct_values_cap_declared": distinct_declared,
    }


def to_public_rule(rule: dict) -> dict:
    """경계 계약(총괄 확정)에 따른 클라이언트 노출 형태.

    참조뷰의 쿼리 본문·limit은 절대 노출하지 않는다 — label과 (암묵적) 인덱스,
    그리고 **`candidate_for`**만.

    `candidate_for` (총괄 승인 2026-07-30, [F9] — 가산적 필드):
    노출되는 것은 **뷰 결과 컬럼명**이고, 그 컬럼명은 `/enrichment/rules/{r}/references/{i}`가
    돌려주는 참조뷰 결과에 이미 헤더로 나타난다 → 신규 노출 0. 숨겨야 하는 것(쿼리 본문·limit)은
    그대로 숨겨져 있다. 이 필드가 없으면 클라이언트는 「어느 뷰가 후보 원천인가」를
    **스스로 유도**해야 하고, 유도가 왜 위험한지는 이 모듈 상단 주석의 실 config가 보여준다.

    queue_predicate: THE queue, asked for BY NAME  [2026-08-05, user ruling]
        The queue is not an arbitrary filter that happens to be shaped like one.
        It is one specific question - which rows still need work - and the rule
        already declares everything needed to answer it. Encoding it as a
        client-visible filter dict put its definition in the CALLER and made its
        meaning depend on how many targets a rule happens to declare: every
        consumer ANDs the per-column specs, so on a multi-target rule
        `queue_filters` means EVERY target blank, and filling one column dropped
        the row out of the queue while its sibling was still blank. Same shape as
        N36 - a row with work left, silently counted as answered - and both live
        rules declare two targets, so it was reachable the day it was measured.

        The answer is a NAMED server-side predicate, not a wider DSL: the queue
        needs a cross-column OR, and growing the public filter grammar to express
        it would hand that surface to every existing caller for the sake of one
        question. So the client sends `?enrichment_queue=<rule name>` and the
        server composes the condition from the rule's own `target_fields` -
        `queue_predicate_condition` below is the single implementation and every
        consumer reaches it. See that function for the four scopes.

    queue_filters: the pre-existing GENERAL filter, kept working as what it is -
    one `blank` spec per target field, which the caller conjoins. It is NOT the
    queue on a multi-target rule (see above), and it is still emitted because
    anything already asking for targets-blank in this shape must keep getting
    that answer. New consumers take `queue_predicate`.

    WHY THE DECISION-KEY `notBlank` CONDITIONS ARE NO LONGER IN IT
    [2026-08-04, user ruling; boarded as N36]
        They were, and that is what made the progress bar read 100% with work
        left. The bar's denominator (`enrichment.js fetchTotalAll`) filters
        NOTHING - it is every derived row - while the remainder demanded the
        keys as well. Two different populations, so a row with a blank decision
        key sat INSIDE the denominator and OUTSIDE the remainder: silently
        counted as answered. Measured: 33% -> 100% from a one-line config edit
        with zero data change, worklist empty while two genuinely unanswered
        rows sat in the table. Both sides now count the same thing - rows whose
        targets are blank - and `total` is what both already returned.

        Surfacing those rows is the intent, not a side effect: a missing
        decision key is an upstream defect, and an invisible defect is never
        fixed.

    keyed_queue_filters: the queue entries whose decision key is COMPLETE - the
    queue AND every decision key non-blank.

    IT IS NO LONGER THE WRITE PREDICATE  [2026-08-05, user ruling]
        It was, and the sentence here said so. The ruling is that a partial key
        is worked on whatever survives, everywhere - human and sweep alike -
        because `auto_confirm` is itself the consent for unattended writes and a
        second gate under it would be code re-deciding what config decided.
        `enrichment_analysis.run_auto_confirm_sweep` therefore walks
        `queue_filters`, and the refusals that remain are arithmetic rather than
        predicate: a view that binds the blank column cannot be asked
        (`missing_bind`), and a wholly blank key has nothing to ask with
        (`no_decision_key`).

        What this composition is still FOR: the named count below, and ②'s
        learning walk, which cannot attribute a judgement to key columns that
        were not present. `queue_filters.total - keyed_queue_filters.total` is the named
    aggregate the client shows as "판단키 없음 N건" - both are conjunctive
    filters the existing DSL already translates, so the count needs no new
    endpoint and no cross-column OR (which the DSL cannot express: `operator`/
    `conditions` combine specs for ONE column).
    """
    queue_filters = {t: {"type": "blank"} for t in rule["target_fields"]}
    keyed_queue_filters = dict(queue_filters)
    for k in rule["decision_key"]:
        keyed_queue_filters[k] = {"type": "notBlank"}
    return {
        "name": rule["name"],
        "source_table": rule["source_table"],
        "derived_table": rule["derived_table"],
        "decision_key": list(rule["decision_key"]),
        "target_fields": list(rule["target_fields"]),
        "list_columns": list(rule["list_columns"]),
        # 정렬 화면이 고를 수 있는 규칙인가. **선언이지 유도가 아니다** (§_validate_rule ②).
        # 항상 실린다 - 키가 없으면 클라가 「이 서버는 이 필드를 모른다」와 「이 규칙은 정렬
        # 대상이 아니다」를 구별하려고 버전 검사를 하게 되고, 그 검사는 자기보다 오래 산다.
        "alignment": rule.get("alignment") is True,
        "reference_views": [
            {"label": v["label"], "candidate_for": dict(v.get("candidate_for") or {})}
            for v in rule.get("reference_views", [])
        ],
        "queue_filters": queue_filters,
        "keyed_queue_filters": keyed_queue_filters,
        # How to ASK for the queue. The client sends `param=value` (plus an
        # optional `scope_param`) on `GET /tables/{derived}/data`; it does not
        # compose the predicate. Its ABSENCE is how a client detects an old
        # server and falls back to `queue_filters` - which is the old, wrong-on-
        # multi-target answer, but it is the answer that server can give.
        "queue_predicate": {
            "param": QUEUE_PREDICATE_PARAM,
            "value": rule["name"],
            "scope_param": QUEUE_SCOPE_PARAM,
            "scopes": list(QUEUE_SCOPES),
        },
    }


# ---------------------------------------------------------------------------
# The named queue predicate — "which rows still need work"
# ---------------------------------------------------------------------------

# Query-parameter spelling on `GET /tables/{t}/data`. Named here, beside the rule
# that answers it, so the route and the analysis cannot drift apart.
QUEUE_PREDICATE_PARAM = "enrichment_queue"
QUEUE_SCOPE_PARAM = "enrichment_queue_scope"

# THE queue: at least one target field still blank. Nothing else.
QUEUE_SCOPE_QUEUE = "queue"
# The queue entries a human can actually work: every decision key present.
QUEUE_SCOPE_KEYED = "keyed"
# Its complement INSIDE the queue: at least one decision key blank. Together with
# `keyed` this partitions the queue exactly, which is what keeps ④'s total equal
# to the worklist remainder and the badge.
QUEUE_SCOPE_BLANK_KEY = "blank_key"
# The queue's complement on the target axis: every target filled AND every key
# present. What ② learns from.
QUEUE_SCOPE_RESOLVED = "resolved"
QUEUE_SCOPES = (QUEUE_SCOPE_QUEUE, QUEUE_SCOPE_KEYED,
                QUEUE_SCOPE_BLANK_KEY, QUEUE_SCOPE_RESOLVED)


class QueuePredicateError(Exception):
    """The named queue predicate could not be built. The message states why."""


def _queue_spec_condition(table_model, rule: dict, col: str, spec: dict):
    """One column's blank/notBlank condition, through the SHARED filter translator.

    `column_filter.get_column_filter_condition` is the same translator
    `GET /tables/{t}/data` runs, which in turn delegates blank/notBlank to
    `crud.blank_sql_condition` / `crud.not_blank_sql_condition`. So this composes
    a new SHAPE out of the existing vocabulary and does not spell "blank" a second
    time. (`import column_filter`, NOT `main` - see that module's docstring: in
    the scheduler and watcher processes `main` is not a stable name.)
    """
    import column_filter

    cond = column_filter.get_column_filter_condition(table_model, col, spec)
    if cond is None:
        raise QueuePredicateError(
            f"filter for column '{col}' could not be translated on table "
            f"'{rule['derived_table']}' - is the column declared in table_config?")
    return cond


def queue_predicate_condition(table_model, rule: dict,
                              scope: str = QUEUE_SCOPE_QUEUE):
    """SQL condition for the named queue predicate. THE single implementation.

    🔴 THE QUEUE IS *ANY* TARGET BLANK, NOT EVERY TARGET BLANK  [2026-08-05 ruling]
        A row stays in the list while ANY target field is still blank. The
        conjunctive spelling (`queue_filters`, one `blank` spec per target, ANDed
        by whoever applies it) said EVERY, so filling one column of a two-target
        rule silently removed the row while its sibling was still empty. That is
        not a filter preference, it is rows leaving the queue with work in them.

    WHY THIS IS NOT AN EXTENSION OF THE FILTER DSL
        The repair needs a cross-column OR. The public DSL cannot express one -
        `operator`/`conditions` combine specs for ONE column - and widening it
        would grow a surface every existing caller inherits, to answer a question
        only this rule asks. One named question, one implementation.

    EVERY CONSUMER REACHES THIS FUNCTION. The worklist rows, the progress
    remainder, the main-grid badge and the admin missing-count arrive through
    `GET /tables/{t}/data?enrichment_queue=<rule>`; `classify_queue`, ②'s walk
    and ①'s sweep arrive through `enrichment_analysis._queue_condition`. The
    progress bar's DENOMINATOR stays unfiltered (every derived row) - the same
    population this predicate is a subset of, which is the N36 invariant.

    Scopes (`QUEUE_SCOPES`), and why `resolved` is now an exact complement:
      queue     = ANY target blank
      keyed     = queue AND every decision key non-blank
      blank_key = queue AND at least one decision key blank
      resolved  = every target non-blank AND every decision key non-blank
    `keyed` + `blank_key` partition `queue`. And `resolved`'s target half is now
    the exact negation of `queue`'s: under the old EVERY-blank spelling a partly
    filled row was in NEITHER, which is precisely where the defect lived.
    """
    from sqlalchemy import and_, or_

    if scope not in QUEUE_SCOPES:
        raise QueuePredicateError(
            f"unknown queue scope '{scope}' - expected one of {list(QUEUE_SCOPES)}")

    targets = list(rule["target_fields"])
    keys = list(rule["decision_key"])

    def cond(col, kind):
        return _queue_spec_condition(table_model, rule, col, {"type": kind})

    if scope == QUEUE_SCOPE_RESOLVED:
        return and_(*[cond(t, "notBlank") for t in targets],
                    *[cond(k, "notBlank") for k in keys])

    # The one shape the public DSL cannot express, and the whole reason this
    # predicate has a name.
    any_target_blank = or_(*[cond(t, "blank") for t in targets])
    if scope == QUEUE_SCOPE_QUEUE:
        return any_target_blank
    if scope == QUEUE_SCOPE_KEYED:
        return and_(any_target_blank, *[cond(k, "notBlank") for k in keys])
    return and_(any_target_blank, or_(*[cond(k, "blank") for k in keys]))
