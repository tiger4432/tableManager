"""Ontology 매핑 config v2 로더/검증기 (docs/spec/ONTOLOGY_GRAPH_SPEC.md §3).

`server/config/ontology_mapping.json`(사용자 영역, gitignored)을 읽어 검증·정규화한다.
매핑 config는 "트랙의 심장" — 인제션되는 모든 로우가 이 선언에 따라 노드/엣지로
자동 승격된다(스펙 §0). description은 장식이 아니라 LLM 그라운딩용 **필수 필드**다.

v2 파일 스키마 (table_name -> mapping):
{
  "bonding_log": {
    "description": "본딩 설비가 chip 1개를 base에 실장한 이벤트",   // 필수 (LLM 그라운딩)
    "event_time_column": "eventtime",    // 선택 — 엣지 event_time의 **실 사건 시각** 컬럼
    "node": {
      "label": "Chip",
      "identity": "log_id",              // 단일 컬럼명 또는 복수 컬럼 리스트
      "node_class": "dynamic",           // 선택 — §7.5c. 파싱·보존만 하고 아직 강제하지 않음
      "props": [
        "eventtime",                     // 단순 컬럼 선언
        {"col": "cx", "spatial": {"coord_system": "wafer_grid", "axis": "x"}}  // §7.5 공간 속성
      ]
    },
    "edges": [
      {"type": "BONDED_FROM", "target_label": "Wafer",
       "target_identity_from": ["core_lot", "core_slot"],   // 복합 식별 → "|" 조인 identity
       "props": ["eventtime"],
       "description": "이 chip이 잘려 나온 원판 wafer"}      // 엣지에도 필수
    ]
  }
}

- 검증 실패 시 **해당 테이블만 스킵 + 명시 로그** (전체 기동 실패 금지).
- **선언되지 않은 키는 거부한다** (2026-07-29). 이전에는 모르는 키를 조용히 버렸기 때문에
  `node_class`/`event_time_column` 같은 신규 선언을 JSON에 써 넣어도 **아무 일도 일어나지
  않았다** — 선언이 무음으로 죽는 결함 계급. 이제 미선언 키는 해당 테이블 매핑을 사유와 함께
  스킵시키므로 오타(`node_clas`)가 즉시 드러난다. 주석용 `__` 접두 키는 어디서든 허용된다.
- v1 형식(`tables`/`default` 래퍼 — 구 Neo4j 경로 전용)은 v2 로더 대상이 아니다.
  v1 파일이 감지되면 info 로그 후 빈 매핑을 반환한다(구 경로는 graph_sync_worker의
  load_ontology_mapping이 그대로 소비 — 인터페이스 보존).
- enrichment 자동 승격(스펙 §3): enrichment_rules.json의 각 rule로부터 RESOLVED_AS
  엣지 매핑을 자동 합성 — rule 추가 = 온톨로지 확장.
- 핫리로드 대상: 그래프 워커의 SYSTEM_RELOAD 구독이 본 로더를 재호출한다(이슈 #8).
"""
import json
import logging
import os
import re

logger = logging.getLogger("OntologyConfig")

from paths import CONFIG_DIR  # single override point (ASSY_DATA_ROOT)
ONTOLOGY_PATH = os.path.join(CONFIG_DIR, "ontology_mapping.json")

_LABEL_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# 동적 테이블 공용 메타 컬럼 — 매핑 컬럼 참조 검증에서 허용 목록에 포함
_META_COLUMNS = {"row_id", "business_key_val", "created_at", "updated_at"}

# ----------------- 선언 가능한 키 (미선언 키는 거부) -----------------
# 이 집합이 "무엇을 선언할 수 있는가"의 단일 원천이다. 여기에 없는 키를 쓰면 매핑이
# 조용히 무시되는 대신 사유와 함께 스킵된다 — 신규 선언이 무음으로 죽지 않게 하는 장치.
_ALLOWED_TABLE_KEYS = {"description", "event_time_column", "node", "edges"}
_ALLOWED_NODE_KEYS = {"label", "identity", "node_class", "props"}
_ALLOWED_EDGE_KEYS = {
    "type", "target_label", "target_identity_from", "props", "description",
    "source_override",
}
_ALLOWED_PROP_KEYS = {"col", "spatial"}
_ALLOWED_SPATIAL_KEYS = {"coord_system", "axis"}

# §7.5c 정적/동적 분류. G1에서는 **파싱·보존만** 하고 탐색 정책은 강제하지 않는다
# (정책 엔진은 G2.5). 여기서 받아두는 이유는 선언 채널을 미리 여는 것이 아니라,
# 스펙 §3 예시를 그대로 따라 쓴 config가 미선언 키로 거부되지 않게 하기 위함이다.
_NODE_CLASSES = {"static", "dynamic"}


def _unknown_keys(raw: dict, allowed: set, where: str):
    """선언되지 않은 키를 사유 문자열로 돌려준다(없으면 None). `__` 접두는 주석으로 허용."""
    unknown = sorted(
        k for k in raw.keys()
        if isinstance(k, str) and not k.startswith("__") and k not in allowed
    )
    if not unknown:
        return None
    return (
        f"{where}: unknown key(s) {unknown} — allowed: {sorted(allowed)}. "
        "Declarations are rejected rather than ignored so that a typo cannot "
        "silently disable the declaration it was meant to make."
    )


def _as_col_list(value):
    """단일 컬럼명(str) 또는 컬럼 리스트를 정규화 리스트로. 실패 시 None."""
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    if isinstance(value, list) and len(value) > 0 and all(
        isinstance(v, str) and v.strip() for v in value
    ):
        return [v.strip() for v in value]
    return None


def _normalize_props(raw_props, where: str):
    """props 선언을 [{"col": str, "spatial": dict|None}] 형태로 정규화한다.

    반환: (normalized_list, error|None). 항목 하나라도 무효면 에러(테이블 스킵 사유).
    공간 속성(spatial)은 §7.5 — G1은 저장 스키마까지: coord_system/axis 선언을 그대로 보존.
    """
    props = []
    if raw_props is None:
        return props, None
    if not isinstance(raw_props, list):
        return None, f"{where}: 'props' must be a list"
    for i, raw in enumerate(raw_props):
        if isinstance(raw, str) and raw.strip():
            props.append({"col": raw.strip(), "spatial": None})
            continue
        if isinstance(raw, dict):
            err = _unknown_keys(raw, _ALLOWED_PROP_KEYS, f"{where}: props[{i}]")
            if err is not None:
                return None, err
            col = raw.get("col")
            if not isinstance(col, str) or not col.strip():
                return None, f"{where}: props[{i}] requires non-empty 'col'"
            spatial = raw.get("spatial")
            if spatial is not None:
                if not isinstance(spatial, dict):
                    return None, f"{where}: props[{i}].spatial must be an object"
                err = _unknown_keys(
                    spatial, _ALLOWED_SPATIAL_KEYS, f"{where}: props[{i}].spatial"
                )
                if err is not None:
                    return None, err
                coord = spatial.get("coord_system")
                axis = spatial.get("axis")
                if not isinstance(coord, str) or not coord.strip():
                    return None, f"{where}: props[{i}].spatial requires 'coord_system'"
                if not isinstance(axis, str) or not axis.strip():
                    return None, f"{where}: props[{i}].spatial requires 'axis'"
                spatial = {"coord_system": coord.strip(), "axis": axis.strip()}
            props.append({"col": col.strip(), "spatial": spatial})
            continue
        return None, f"{where}: props[{i}] must be a column name or an object"
    return props, None


def _validate_table_mapping(table_name: str, raw: dict, known_tables: dict):
    """테이블 매핑 1건을 검증·정규화한다. 반환: (normalized|None, 실패사유|None)."""
    if not isinstance(raw, dict):
        return None, "mapping must be an object"

    err = _unknown_keys(raw, _ALLOWED_TABLE_KEYS, "table mapping")
    if err is not None:
        return None, err

    description = raw.get("description")
    if not isinstance(description, str) or not description.strip():
        return None, "'description' is required (LLM grounding — spec §3)"

    # [INV-O-2] 엣지 event_time의 실 사건 시각 컬럼. 미선언 시 현행(인제션 시각) 유지 —
    # 선언한 테이블만 교정되므로 가산적이다.
    event_time_column = raw.get("event_time_column")
    if event_time_column is not None:
        if not isinstance(event_time_column, str) or not event_time_column.strip():
            return None, "'event_time_column' must be a non-empty column name"
        event_time_column = event_time_column.strip()

    node_raw = raw.get("node")
    if not isinstance(node_raw, dict):
        return None, "'node' is required"
    err = _unknown_keys(node_raw, _ALLOWED_NODE_KEYS, "node")
    if err is not None:
        return None, err
    label = node_raw.get("label")
    if not isinstance(label, str) or not _LABEL_RE.match(label.strip() or ""):
        return None, f"node.label must be a valid identifier: {label!r}"
    identity = _as_col_list(node_raw.get("identity"))
    if identity is None:
        return None, "node.identity must be a column name or non-empty list of columns"
    # §7.5c — 받아서 보존만 한다. 탐색 정책 강제는 G2.5(정책 엔진)의 일이며 현재 소비자 없음.
    node_class = node_raw.get("node_class")
    if node_class is not None:
        if not isinstance(node_class, str) or node_class.strip() not in _NODE_CLASSES:
            return None, (
                f"node.node_class must be one of {sorted(_NODE_CLASSES)}: {node_class!r}"
            )
        node_class = node_class.strip()
    node_props, err = _normalize_props(node_raw.get("props"), "node")
    if err is not None:
        return None, err

    edges = []
    raw_edges = raw.get("edges") or []
    if not isinstance(raw_edges, list):
        return None, "'edges' must be a list"
    for i, e in enumerate(raw_edges):
        if not isinstance(e, dict):
            return None, f"edges[{i}] must be an object"
        err = _unknown_keys(e, _ALLOWED_EDGE_KEYS, f"edges[{i}]")
        if err is not None:
            return None, err
        e_type = e.get("type")
        if not isinstance(e_type, str) or not _LABEL_RE.match(e_type.strip() or ""):
            return None, f"edges[{i}].type must be a valid identifier: {e_type!r}"
        t_label = e.get("target_label")
        if not isinstance(t_label, str) or not _LABEL_RE.match(t_label.strip() or ""):
            return None, f"edges[{i}].target_label must be a valid identifier: {t_label!r}"
        t_identity = _as_col_list(e.get("target_identity_from"))
        if t_identity is None:
            return None, f"edges[{i}].target_identity_from must be a column name or non-empty list"
        e_desc = e.get("description")
        if not isinstance(e_desc, str) or not e_desc.strip():
            return None, f"edges[{i}] ('{e_type}') requires 'description' (spec §3)"
        e_props, err = _normalize_props(e.get("props"), f"edges[{i}]")
        if err is not None:
            return None, err
        edge = {
            "type": e_type.strip(),
            "target_label": t_label.strip(),
            "target_identity_from": t_identity,
            "props": e_props,
            "description": e_desc.strip(),
        }
        # 내부 전용: enrichment 승격 엣지의 provenance 고정(user). 사용자 파일에서도 지정 가능.
        override = e.get("source_override")
        if isinstance(override, str) and override.strip():
            edge["source_override"] = override.strip()
        edges.append(edge)

    # 컬럼 존재 검증 (table_config가 주어진 경우에만 — 순수 구조 검증과 분리)
    if known_tables is not None:
        table_cfg = known_tables.get(table_name)
        if table_cfg is None:
            return None, f"table '{table_name}' is not registered in table_config.json"
        cols = set(table_cfg.get("column_types", {}).keys()) | _META_COLUMNS
        referenced = list(identity)
        referenced += [p["col"] for p in node_props]
        if event_time_column is not None:
            referenced.append(event_time_column)
        for e in edges:
            referenced += e["target_identity_from"]
            referenced += [p["col"] for p in e["props"]]
        missing = sorted({c for c in referenced if c not in cols})
        if missing:
            return None, f"column(s) not found in table_config: {missing}"

    return {
        "table": table_name,
        "description": description.strip(),
        "event_time_column": event_time_column,
        "node": {
            "label": label.strip(),
            "identity": identity,
            "node_class": node_class,
            "props": node_props,
        },
        "edges": edges,
    }, None


def validate_ontology_mapping(raw_config, known_tables: dict = None) -> dict:
    """설정 dict 전체를 검증한다. {table_name: normalized} 반환(무효 테이블은 로깅 후 스킵)."""
    mappings = {}
    if not isinstance(raw_config, dict):
        logger.error("ontology_mapping.json must be an object {table_name: mapping}")
        return mappings
    # v1 형식(구 Neo4j 경로) 감지 — v2 항목이 아니므로 로더 대상에서 제외
    v1_keys = {"tables", "default"}
    for table_name, raw in raw_config.items():
        if isinstance(table_name, str) and table_name.startswith("__"):
            continue  # 주석 키(__comment 등) 허용
        if table_name in v1_keys:
            logger.info(
                f"[Ontology] v1-format key '{table_name}' ignored by v2 loader "
                "(legacy Neo4j path only)"
            )
            continue
        if not isinstance(table_name, str) or not table_name.strip():
            logger.warning("[Ontology] mapping with empty table name skipped")
            continue
        normalized, err = _validate_table_mapping(table_name, raw, known_tables)
        if err is not None:
            logger.warning(f"[Ontology:{table_name}] mapping skipped: {err}")
            continue
        mappings[table_name] = normalized
    return mappings


# ----------------- enrichment rule 자동 승격 (spec §3) -----------------

def _default_label_for_table(table_name: str) -> str:
    return "".join(part.capitalize() for part in table_name.split("_"))


def _default_label_for_field(field_name: str) -> str:
    base = field_name[:-3] if field_name.lower().endswith("_id") else field_name
    return _default_label_for_table(base) or "Entity"


def synthesize_enrichment_mappings(mappings: dict, enrichment_rules: list) -> dict:
    """enrichment rule의 decision_key → target 정의를 RESOLVED_AS 엣지 매핑으로 자동 합성한다.

    - 파생 테이블에 사용자 노드 매핑이 있으면 그대로 쓰고 RESOLVED_AS 엣지만 보충한다.
      (동일 target으로의 RESOLVED_AS를 사용자가 이미 선언했다면 사용자 정의가 이긴다.)
    - 사용자 매핑이 없으면 기본 노드(라벨=PascalCase(derived_table), identity=decision_key)를
      합성한다 — rule 추가 = 온톨로지 확장.
    - 승격 엣지는 source_override="user" — 사람 교정 결과이므로 provenance는 항상 user
      (집계 재계산 등 chain_ingestion 발 EDIT가 덮어써도 유지, 레이어링 서열과 정합).
    - 입력 mappings를 변경하지 않고 합성 결과 사본을 반환한다.
    """
    result = {t: dict(m) for t, m in mappings.items()}
    for rule in enrichment_rules or []:
        derived = rule.get("derived_table")
        decision_key = rule.get("decision_key") or []
        target_fields = rule.get("target_fields") or []
        if not derived or not decision_key or not target_fields:
            continue

        entry = result.get(derived)
        if entry is None:
            entry = {
                "table": derived,
                "description": (
                    f"enrichment rule '{rule.get('name')}'의 파생 테이블 — "
                    f"{decision_key} 판단키에 대한 사람 교정 결과(auto-promoted)"
                ),
                # 합성 매핑은 사용자 선언이 없으므로 실 사건 시각 컬럼을 알 수 없다 —
                # 추측하지 않고 현행(인제션 시각)으로 둔다. 교정하려면 그 테이블에
                # 사용자 매핑을 두고 event_time_column을 선언하면 된다(합성이 이를 보존).
                "event_time_column": None,
                "node": {
                    "label": _default_label_for_table(derived),
                    "identity": list(decision_key),
                    "node_class": None,
                    "props": [],
                },
                "edges": [],
            }
            result[derived] = entry
        else:
            entry = dict(entry)
            entry["edges"] = list(entry.get("edges", []))
            result[derived] = entry

        existing_types = {
            (e["type"], tuple(e["target_identity_from"]))
            for e in entry.get("edges", [])
        }
        for field in target_fields:
            key = ("RESOLVED_AS", (field,))
            if key in existing_types:
                continue  # 사용자 정의 우선
            entry.setdefault("edges", []).append({
                "type": "RESOLVED_AS",
                "target_label": _default_label_for_field(field),
                "target_identity_from": [field],
                "props": [],
                "description": (
                    f"enrichment rule '{rule.get('name')}'의 사람 교정 결과 — "
                    f"{decision_key} 표기를 {field}로 해석"
                ),
                "source_override": "user",
            })
    return result


def load_ontology_mappings(path: str = None, known_tables: dict = None,
                           include_enrichment: bool = True) -> dict:
    """ontology_mapping.json(v2)을 읽어 검증·정규화하고 enrichment 승격 매핑을 병합한다.

    반환: {table_name: normalized_mapping}. 파일 없음/손상 → (승격분만 있는) 부분 결과.
    """
    mapping_path = path or ONTOLOGY_PATH
    raw_config = {}
    if os.path.exists(mapping_path):
        try:
            with open(mapping_path, "r", encoding="utf-8") as f:
                raw_config = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load ontology mapping from {mapping_path}: {e}")
            raw_config = {}
    mappings = validate_ontology_mapping(raw_config, known_tables=known_tables)

    if include_enrichment:
        try:
            from enrichment_config import load_enrichment_rules
            rules = load_enrichment_rules(known_tables=known_tables)
        except Exception as e:
            logger.error(f"[Ontology] enrichment promotion skipped (rule load failed): {e}")
            rules = []
        mappings = synthesize_enrichment_mappings(mappings, rules)
    return mappings
