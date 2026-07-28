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
        "limit": 200 },                                       // 선택(기본 200, 최대 1000)
      { "label": "lot-slot history", "query_ref": "lot_slot_history" }  // config/enrichment_queries/<ref>.sql
    ]
  }
}

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

DEFAULT_REFERENCE_LIMIT = 200
MAX_REFERENCE_LIMIT = 1000

# SQLAlchemy text()와 동일 계열의 바인드 파라미터 패턴 (`::text` 캐스트는 매치되지 않음)
_BIND_PARAM_RE = re.compile(r"(?<![:\w]):([A-Za-z_]\w*)")
_QUERY_REF_NAME_RE = re.compile(r"^[A-Za-z0-9_\-]+$")


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


def _normalize_reference_views(rule_name: str, raw_views, decision_key: list) -> list:
    """참조뷰 목록을 정규화한다. 유효하지 않은 뷰는 **목록에서 제외**된다.

    주의: 제외는 로드 시점에 일어나므로 `/enrichment/rules`의 label 목록과
    `/references/{index}`의 인덱스가 항상 같은 (필터링된) 목록을 가리킨다 — 인덱스 정합 보장.
    """
    views = []
    if raw_views is None:
        return views
    if not isinstance(raw_views, list):
        logger.warning(f"[Enrichment:{rule_name}] 'reference_views' must be a list; ignoring")
        return views
    for i, raw in enumerate(raw_views):
        if not isinstance(raw, dict) or not isinstance(raw.get("label"), str) or not raw.get("label").strip():
            logger.warning(f"[Enrichment:{rule_name}] reference view #{i} dropped: missing 'label'")
            continue
        sql, err = _resolve_view_query(raw)
        if err is None:
            err = _validate_view_sql(sql, decision_key)
        if err is not None:
            logger.warning(f"[Enrichment:{rule_name}] reference view '{raw.get('label')}' dropped: {err}")
            continue
        limit = raw.get("limit", DEFAULT_REFERENCE_LIMIT)
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = DEFAULT_REFERENCE_LIMIT
        limit = max(1, min(limit, MAX_REFERENCE_LIMIT))
        views.append({
            "label": raw["label"].strip(),
            "query": sql.strip().rstrip(";").strip(),
            "limit": limit,
        })
    return views


def _validate_rule(name: str, raw: dict, known_tables: dict) -> tuple:
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

    normalized = {
        "name": name,
        "source_table": source_table.strip(),
        "derived_table": derived_table.strip(),
        "decision_key": list(decision_key),
        "target_fields": list(target_fields),
        "list_columns": list(list_columns),
        "aggregations": aggregations,
        "reference_views": _normalize_reference_views(name, raw.get("reference_views"), decision_key),
    }
    return normalized, None


def validate_enrichment_rules(raw_config: dict, known_tables: dict = None) -> list:
    """설정 dict 전체를 검증한다. 유효 규칙의 정규화 리스트를 반환(무효 규칙은 로깅 후 스킵)."""
    rules = []
    if not isinstance(raw_config, dict):
        logger.error("enrichment_rules.json must be an object {rule_name: rule}")
        return rules
    for name, raw in raw_config.items():
        if not isinstance(name, str) or not name.strip():
            logger.warning("[Enrichment] rule with empty name skipped")
            continue
        normalized, err = _validate_rule(name, raw, known_tables)
        if err is not None:
            logger.warning(f"[Enrichment:{name}] rule skipped: {err}")
            continue
        if normalized is not None:
            rules.append(normalized)
    return rules


def load_enrichment_rules(path: str = None, known_tables: dict = None) -> list:
    """enrichment_rules.json을 읽어 검증된 규칙 리스트를 반환한다(파일 없음 → 빈 목록)."""
    rules_path = path or ENRICHMENT_RULES_PATH
    if not os.path.exists(rules_path):
        return []
    try:
        with open(rules_path, "r", encoding="utf-8") as f:
            raw_config = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load enrichment rules from {rules_path}: {e}")
        return []
    return validate_enrichment_rules(raw_config, known_tables=known_tables)


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


def to_public_rule(rule: dict) -> dict:
    """경계 계약(총괄 확정)에 따른 클라이언트 노출 형태.

    참조뷰의 쿼리 본문·limit은 절대 노출하지 않는다 — label과 (암묵적) 인덱스만.

    queue_filters: the ONE server-composed definition of "a queue entry" for
    the generic /tables/{t}/data filter DSL - every target field blank AND
    every decision key non-blank. A row without its decision keys cannot be
    resolved by a human, so it must never surface in the worklist (worklist,
    admin missing-count, and main-grid badge all consume this same object -
    one blank rule, not three hand-built copies).
    """
    queue_filters = {k: {"type": "notBlank"} for k in rule["decision_key"]}
    for t in rule["target_fields"]:
        queue_filters[t] = {"type": "blank"}
    return {
        "name": rule["name"],
        "source_table": rule["source_table"],
        "derived_table": rule["derived_table"],
        "decision_key": list(rule["decision_key"]),
        "target_fields": list(rule["target_fields"]),
        "list_columns": list(rule["list_columns"]),
        "reference_views": [{"label": v["label"]} for v in rule.get("reference_views", [])],
        "queue_filters": queue_filters,
    }
