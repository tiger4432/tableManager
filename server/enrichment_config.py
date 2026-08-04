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

DEFAULT_REFERENCE_LIMIT = 200
MAX_REFERENCE_LIMIT = 1000

# SQLAlchemy text()와 동일 계열의 바인드 파라미터 패턴 (`::text` 캐스트는 매치되지 않음)
_BIND_PARAM_RE = re.compile(r"(?<![:\w]):([A-Za-z_]\w*)")
_QUERY_REF_NAME_RE = re.compile(r"^[A-Za-z0-9_\-]+$")

# `candidate_for`의 뷰 결과 컬럼명. 후보 프로브 SQL에는 이 이름이 **보간**되므로
# (바인딩 불가 — 식별자다) 로드 시점에 형태를 강제한다. 실행 시 인용부호로 감싸는 것과
# 이 검증은 **둘 다** 필요하다: 인용부호만으로는 `a" OR "1"="1` 류가 닫히지 않는다.
_CANDIDATE_COLUMN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


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
                               target_fields: list = None, rejections: list = None) -> list:
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
        limit = raw.get("limit", DEFAULT_REFERENCE_LIMIT)
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = DEFAULT_REFERENCE_LIMIT
        limit = max(1, min(limit, MAX_REFERENCE_LIMIT))
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


def _validate_rule(name: str, raw: dict, known_tables: dict, rejections: list = None) -> tuple:
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
        # ① auto-confirm opt-in. Carried through RAW (not coerced) so
        # enrichment_candidates.rule_auto_confirm_enabled can warn-once about a
        # non-boolean instead of silently reading it as truthy.
        "auto_confirm": raw.get("auto_confirm", False),
        # 「선언이 없다」와 「false로 선언했다」는 다른 사실이고, 위 필드만으로는 구별되지
        # 않는다. `config_resolve_report`가 그 둘을 다른 문장으로 렌더하려면 존재 여부가
        # 필요하다 — 값이 아니라 **선언의 유무**를 나르는 필드다(클라 노출 대상 아님).
        "auto_confirm_declared": isinstance(raw, dict) and "auto_confirm" in raw,
        "source_table": source_table.strip(),
        "derived_table": derived_table.strip(),
        "decision_key": list(decision_key),
        "target_fields": list(target_fields),
        "list_columns": list(list_columns),
        "aggregations": aggregations,
        "reference_views": _normalize_reference_views(
            name, raw.get("reference_views"), decision_key, target_fields,
            rejections=rejections),
    }
    return normalized, None


def validate_enrichment_rules(raw_config: dict, known_tables: dict = None,
                              rejections: list = None) -> list:
    """설정 dict 전체를 검증한다. 유효 규칙의 정규화 리스트를 반환(무효 규칙은 로깅 후 스킵).

    rejections: 선택 수집기 리스트 — 스킵된 선언을 `{scope, subject, detail}`로 누적한다
    (`_record` 참조). 반환값 형태는 수집기 유무와 무관하게 동일하다.
    """
    rules = []
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
        normalized, err = _validate_rule(name, raw, known_tables, rejections=rejections)
        if err is not None:
            logger.warning(f"[Enrichment:{name}] rule skipped: {err}")
            _record(rejections, "rule", name, f"rule skipped: {err}")
            continue
        if normalized is not None:
            rules.append(normalized)
    return rules


def load_enrichment_rules(path: str = None, known_tables: dict = None,
                          rejections: list = None) -> list:
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
                                     rejections=rejections)


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

# 프로브가 훑을 **행** 상한. 뷰의 `limit`(표시용)과 별개이고 운영 노브가 아니다.
# GROUP BY는 상위 LIMIT으로 조기 종료할 수 없으므로, 바인드 없는 뷰
# (`required_binds == []`)가 선언되면 키마다 전체 테이블을 훑게 된다 — 1,000만 행 규율의
# 유일한 방어선이다. 상한에 닿으면 결과는 **잘린 읽기**이므로 `single`을 주장하지 않고
# 이름 있는 거절(`probe_truncated`)이 된다. 실측 최대 217행의 약 23배로 잡았다.
CANDIDATE_PROBE_MAX_ROWS = 5000


class ReferenceViewError(Exception):
    """참조뷰 실행 실패. 메시지에 쿼리 본문을 절대 담지 않는다(경계 계약: 본문 비노출)."""


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
        statement - noise next to a GROUP BY over up to CANDIDATE_PROBE_MAX_ROWS
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


def execute_reference_view(db, view: dict, bind_params: dict = None) -> tuple:
    """참조뷰 1건을 서버측 정의로 실행한다. 반환: (columns, rows).

    LIMIT은 서버가 강제한다(뷰 설정값, 내부 LIMIT이 더 작으면 그 값 유지) — 사용자 쿼리를
    서브쿼리로 감싸 상한을 바인딩한다. 값은 SQLAlchemy 바인딩으로만 전달되어 주입이
    구조적으로 불가하다.

    바인드는 **SQL이 실제로 요구하는 이름만** 넘긴다: 호출자가 판단키 전체를 넘겨도
    되고, 요구 바인드가 빠졌으면 실행하지 않고 `ReferenceViewError`를 올린다
    (드라이버 예외를 삼켜 "후보 없음"으로 위장하지 않는다).
    """
    from sqlalchemy import text

    needed = set(view.get("required_binds") or required_bind_params(view.get("query", "")))
    supplied = dict(bind_params or {})
    missing = sorted(needed - set(supplied))
    if missing:
        raise ReferenceViewError(f"missing required bind param(s): {missing}")

    exec_params = _probe_params(view, supplied, needed)
    stmt = text(REFERENCE_LIMIT_WRAP_SQL.format(query=view["query"]))
    try:
        columns, raw_rows = _isolated_execute(db, stmt, exec_params)
    except Exception as e:
        raise ReferenceViewError(f"reference query execution failed ({e.__class__.__name__})")
    return columns, [list(r) for r in raw_rows]


def _probe_params(view: dict, supplied: dict, needed: set) -> dict:
    params = {k: v for k, v in supplied.items() if k in needed}
    params["__enrichment_limit"] = view.get("limit") or DEFAULT_REFERENCE_LIMIT
    return params


def execute_candidate_probe(db, view: dict, column: str, bind_params: dict = None) -> dict:
    """후보 프로브 1건 — 뷰 결과 **전체**에 대해 `column`의 distinct 값과 행수를 센다.

    반환: `{"pairs": [(value, count), ...], "scanned": int,
             "row_truncated": bool, "distinct_truncated": bool}`

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
      - `row_truncated`: 스캔이 `CANDIDATE_PROBE_MAX_ROWS`에 닿았다. `scanned`는 그룹이
        잘리기 전의 전체 행수(`SUM(COUNT(*)) OVER ()`)이므로 그룹 절단과 무관하게 참이다.
    """
    from sqlalchemy import text

    if not _CANDIDATE_COLUMN_RE.match(column or ""):
        # 로더가 이미 막지만, 이 함수는 SQL을 보간하므로 자기 입력을 스스로 검증한다.
        raise ReferenceViewError("candidate column is not a plain SQL identifier")

    needed = set(view.get("required_binds") or required_bind_params(view.get("query", "")))
    supplied = dict(bind_params or {})
    missing = sorted(needed - set(supplied))
    if missing:
        raise ReferenceViewError(f"missing required bind param(s): {missing}")

    limit = view.get("limit") or DEFAULT_REFERENCE_LIMIT
    exec_params = _probe_params(view, supplied, needed)
    # limit + 1: (limit+1)번째 distinct 값이 돌아오면 그것이 절단의 증거다.
    exec_params["__enrichment_limit"] = limit + 1
    exec_params["__enrichment_scan_rows"] = CANDIDATE_PROBE_MAX_ROWS
    stmt = text(CANDIDATE_GROUP_WRAP_SQL.format(query=view["query"], column=column))
    try:
        _, raw = _isolated_execute(db, stmt, exec_params)
    except Exception as e:
        raise ReferenceViewError(f"candidate probe execution failed ({e.__class__.__name__})")

    rows = [(r[0], int(r[1] or 0)) for r in raw]
    # `__scanned`는 바깥 LIMIT이 그룹을 자르기 **전**의 전체 행수다. 반환된 그룹의
    # count 합으로 대신하면, 그룹이 잘린 순간 `scanned`가 과소 보고되고 `row_truncated`가
    # 진짜 잘린 읽기를 놓친다(2026-07-30 QA). 두 절단은 별개 사실이므로 별개로 센다.
    scanned = int(raw[0][2] or 0) if raw else 0
    return {
        "pairs": rows,
        "scanned": scanned,
        "row_truncated": scanned >= CANDIDATE_PROBE_MAX_ROWS,
        "distinct_truncated": len(rows) > limit,
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

    queue_filters: the ONE server-composed definition of "a queue entry" for
    the generic /tables/{t}/data filter DSL - EVERY TARGET FIELD BLANK, and
    nothing else. The worklist, the admin missing-count, the main-grid badge and
    the progress bar's remainder all consume this same object - one blank rule,
    not four hand-built copies.

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

    keyed_queue_filters: the queue entries that can actually be ACTED on - the
    queue AND every decision key non-blank. A reference view is queried WITH the
    key's value, so a blank key finds no evidence and nothing can be resolved
    from it. Every path that WRITES or reasons from evidence stays on this one
    (`enrichment_analysis._queue_condition`); only the display counts the whole
    queue. `queue_filters.total - keyed_queue_filters.total` is the named
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
        "reference_views": [
            {"label": v["label"], "candidate_for": dict(v.get("candidate_for") or {})}
            for v in rule.get("reference_views", [])
        ],
        "queue_filters": queue_filters,
        "keyed_queue_filters": keyed_queue_filters,
    }
