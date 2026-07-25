"""[Ontology G1] 자동 승격 materializer 코어 (docs/spec/ONTOLOGY_GRAPH_SPEC.md §2·§5).

로우 이벤트/테이블 로우 → 매핑 config(v2) 적용 → graph_nodes/graph_edges 벌크 UPSERT.
저장소 중립 원칙(§4): 이 모듈은 **PG 엣지 스토어 전용 materialize**만 담당하고,
Neo4j 경로는 graph_sync_worker의 기존 Cypher 빌더 인터페이스를 그대로 보존한다.

처리량 규율(§5, 헌장 [확장성 최우선]):
- 모든 UPSERT는 1,000행 청킹(ON CONFLICT 벌크) — 행 단위 쿼리 금지.
- 노드 id 해석은 (label, identity_key) UNIQUE 인덱스 룩업(라벨별 IN 청크).
- 배치 내 중복 키는 사전 dedup (ON CONFLICT는 같은 문장 내 중복 키를 허용하지 않음).
- 데드락 예방: 청크 내 정렬로 락 획득 순서 고정 (C-6 교훈).

멱등성: 같은 이벤트 배치를 2회 materialize해도 노드/엣지 수는 불변(UPSERT 키:
nodes=(label, identity_key), edges=(from_node, type, to_node, source_name)).
"""
import logging
from datetime import datetime

from sqlalchemy import func

logger = logging.getLogger("GraphMaterializer")

CHUNK_SIZE = 1000

# 동적 테이블 공용 메타 컬럼 — 로우 평탄화에서 제외
_META_COLUMNS = {
    "row_id", "business_key_val", "created_at", "updated_at",
    "is_graph_synced", "needs_graph_rollback", "graph_synced_at",
}

# 매핑 없는 테이블 무시 로그 1회 규율용 (프로세스 수명 동안 테이블당 1회)
_unmapped_logged = set()

# 셀 소스 → 우선순위 서열 (crud.compute_priority_value와 동일 서열 — user 최우선)
_SOURCE_PRIORITY = {"user": 0, "collision_merge": 1, "pipeline_parser": 2, "custom_script": 3}


def compose_identity(values) -> str:
    """복수 컬럼 identity를 "|" 조인 문자열로 정규화한다. 하나라도 비면 None(해석 불가).

    number 컬럼의 정수값 float(3.0)은 "3"으로 안정화 — 타 테이블의 string 표기("3")와
    identity 정확 일치 MERGE(§2)가 어긋나지 않도록.
    """
    parts = []
    for v in values:
        if v is None:
            return None
        if isinstance(v, float) and v.is_integer():
            v = int(v)
        s = str(v).strip()
        if not s:
            return None
        parts.append(s)
    return "|".join(parts)


def _json_safe(value):
    """props JSON 컬럼에 안전한 값으로 변환(datetime → ISO 문자열)."""
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _parse_event_time(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


def flatten_payload_data(data: dict) -> dict:
    """outbox payload의 data({col: {value,...}} 셀 형태)를 {col: value} 평면 dict로."""
    flat = {}
    for col, cell in (data or {}).items():
        if isinstance(cell, dict) and "value" in cell:
            flat[col] = cell.get("value")
        else:
            flat[col] = cell
    return flat


def extract_graph_items(table_name: str, rows: list, mapping: dict,
                        node_map: dict = None, edges: dict = None):
    """로우 목록 → (node_map, edges) 누적 추출.

    rows: [{"row_id", "values": {col: value}, "source_name", "updated_by", "event_time"}]
    node_map: {(label, identity_key): props_dict} — 스텁(빈 props)은 기존 props를 덮지 않음.
    edges: {(from_key, type, to_key, source_name): edge_row_dict} — 배치 내 dedup(last wins).
    """
    node_map = node_map if node_map is not None else {}
    edges = edges if edges is not None else {}

    node_cfg = mapping["node"]
    label = node_cfg["label"]
    identity_cols = node_cfg["identity"]
    prop_decls = node_cfg["props"]
    spatial_meta = {
        p["col"]: p["spatial"] for p in prop_decls if p.get("spatial")
    }

    for row in rows:
        values = row["values"]
        identity_key = compose_identity([values.get(c) for c in identity_cols])
        if identity_key is None:
            continue  # identity 해석 불가 로우는 스킵(§2: 정확 일치 MERGE 전제)

        node_key = (label, identity_key)
        props = {}
        for p in prop_decls:
            v = values.get(p["col"])
            if v is not None:
                props[p["col"]] = _json_safe(v)
        if spatial_meta:
            # §7.5 공간 스키마 표준화 — 좌표 컬럼의 좌표계 선언을 노드 props에 보존(G1: 저장까지)
            props["_spatial"] = spatial_meta
        existing = node_map.get(node_key)
        if existing:
            existing.update(props)
        else:
            node_map[node_key] = props

        for edge_cfg in mapping["edges"]:
            target_identity = compose_identity(
                [values.get(c) for c in edge_cfg["target_identity_from"]]
            )
            if target_identity is None:
                continue  # 타깃 미해석(예: enrichment target 미기입) — 엣지 없음
            target_key = (edge_cfg["target_label"], target_identity)
            node_map.setdefault(target_key, {})  # 타깃 스텁 노드 MERGE (props 보존)

            e_props = {}
            for p in edge_cfg["props"]:
                v = values.get(p["col"])
                if v is not None:
                    e_props[p["col"]] = _json_safe(v)
            source_name = (
                edge_cfg.get("source_override")
                or row.get("source_name")
                or "unknown"
            )
            edge_key = (node_key, edge_cfg["type"], target_key, source_name)
            edges[edge_key] = {
                "from_key": node_key,
                "to_key": target_key,
                "type": edge_cfg["type"],
                "props": e_props,
                "source_name": source_name,
                "source_row_ref": f"{table_name}:{row.get('row_id')}",
                "updated_by": row.get("updated_by"),
                "event_time": _parse_event_time(row.get("event_time")),
            }
    return node_map, edges


def _props_merge_expr(db, stmt, table_column):
    """UPSERT 충돌 시 props 병합식(shallow merge — 새 키가 이기고 스텁({})은 무해).

    PG: existing || excluded / SQLite: json_patch(existing, excluded).
    """
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        return table_column.op("||")(stmt.excluded.props)
    return func.json_patch(table_column, stmt.excluded.props)


def _insert_stmt_for(db, model):
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as dialect_insert
    else:
        from sqlalchemy.dialects.sqlite import insert as dialect_insert
    return dialect_insert(model.__table__)


def bulk_upsert_nodes(db, node_map: dict, chunk_size: int = CHUNK_SIZE) -> dict:
    """노드 벌크 UPSERT 후 {(label, identity_key): id} 해석 맵을 반환한다."""
    from database.models import GraphNode

    node_ids = {}
    if not node_map:
        return node_ids

    keys = sorted(node_map.keys())  # 정렬 — 락 획득 순서 고정(C-6)
    for i in range(0, len(keys), chunk_size):
        chunk = keys[i:i + chunk_size]
        values = [
            {"label": label, "identity_key": ident, "props": node_map[(label, ident)]}
            for label, ident in chunk
        ]
        stmt = _insert_stmt_for(db, GraphNode).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["label", "identity_key"],
            set_={
                "props": _props_merge_expr(db, stmt, GraphNode.__table__.c.props),
                "updated_at": func.now(),
            },
        )
        db.execute(stmt)

    # id 해석 — (label, identity_key) UNIQUE 인덱스 룩업(라벨별 IN 청크)
    by_label = {}
    for label, ident in keys:
        by_label.setdefault(label, []).append(ident)
    for label, idents in by_label.items():
        for i in range(0, len(idents), chunk_size):
            chunk = idents[i:i + chunk_size]
            rows = db.query(GraphNode.id, GraphNode.identity_key).filter(
                GraphNode.label == label,
                GraphNode.identity_key.in_(chunk),
            ).all()
            for node_id, ident in rows:
                node_ids[(label, ident)] = node_id
    return node_ids


def bulk_upsert_edges(db, edges: dict, node_ids: dict, chunk_size: int = CHUNK_SIZE) -> int:
    """엣지 벌크 UPSERT. 반환: 반영 시도한 엣지 수."""
    from database.models import GraphEdge

    if not edges:
        return 0

    rows = []
    for edge in edges.values():
        from_id = node_ids.get(edge["from_key"])
        to_id = node_ids.get(edge["to_key"])
        if from_id is None or to_id is None:
            logger.warning(
                f"[Graph] edge skipped (unresolved node id): "
                f"{edge['from_key']} -[{edge['type']}]-> {edge['to_key']}"
            )
            continue
        rows.append({
            "type": edge["type"],
            "from_node": from_id,
            "to_node": to_id,
            "props": edge["props"],
            "source_name": edge["source_name"],
            "source_row_ref": edge["source_row_ref"],
            "updated_by": edge["updated_by"],
            "event_time": edge["event_time"],
        })

    rows.sort(key=lambda r: (r["from_node"], r["type"], r["to_node"], r["source_name"]))
    for i in range(0, len(rows), chunk_size):
        chunk = rows[i:i + chunk_size]
        stmt = _insert_stmt_for(db, GraphEdge).values(chunk)
        stmt = stmt.on_conflict_do_update(
            index_elements=["from_node", "type", "to_node", "source_name"],
            set_={
                "props": _props_merge_expr(db, stmt, GraphEdge.__table__.c.props),
                "source_row_ref": stmt.excluded.source_row_ref,
                "updated_by": stmt.excluded.updated_by,
                "event_time": stmt.excluded.event_time,
            },
        )
        db.execute(stmt)
    return len(rows)


def materialize_rows(db, table_name: str, rows: list, mapping: dict,
                     chunk_size: int = CHUNK_SIZE) -> dict:
    """로우 목록 1묶음을 그래프에 반영한다(commit은 호출자 책임)."""
    node_map, edges = extract_graph_items(table_name, rows, mapping)
    node_ids = bulk_upsert_nodes(db, node_map, chunk_size=chunk_size)
    edge_count = bulk_upsert_edges(db, edges, node_ids, chunk_size=chunk_size)
    return {"rows": len(rows), "nodes": len(node_map), "edges": edge_count}


def materialize_events(db, events: list, mappings: dict,
                       chunk_size: int = CHUNK_SIZE) -> dict:
    """outbox 이벤트 배치를 그래프에 반영한다(commit은 호출자 책임).

    - CREATE/EDIT → 매핑 적용 UPSERT. 매핑 없는 테이블은 무시(테이블당 로그 1회).
    - DELETE → G1에서는 스킵(노드/엣지 정리 정책은 스펙 §8 미결 — 카운트만 집계).
    """
    from utils.payload_helper import get_payload_dict

    rows_by_table = {}
    skipped_deletes = 0
    for event in events:
        if event.event_type == "DELETE":
            skipped_deletes += 1
            continue
        if event.event_type not in ("CREATE", "EDIT"):
            continue
        mapping = mappings.get(event.table_name)
        if mapping is None:
            if event.table_name not in _unmapped_logged:
                _unmapped_logged.add(event.table_name)
                logger.info(f"[Graph] table '{event.table_name}' has no ontology mapping — ignored")
            continue
        payload = get_payload_dict(event)
        if not isinstance(payload, dict):
            continue
        rows_by_table.setdefault(event.table_name, []).append({
            "row_id": payload.get("row_id"),
            "values": flatten_payload_data(payload.get("data")),
            "source_name": payload.get("source_name"),
            "updated_by": payload.get("updated_by"),
            "event_time": payload.get("timestamp"),
        })

    node_map, edges = {}, {}
    total_rows = 0
    for table_name, rows in rows_by_table.items():
        extract_graph_items(table_name, rows, mappings[table_name], node_map, edges)
        total_rows += len(rows)

    node_ids = bulk_upsert_nodes(db, node_map, chunk_size=chunk_size)
    edge_count = bulk_upsert_edges(db, edges, node_ids, chunk_size=chunk_size)
    return {
        "rows": total_rows,
        "nodes": len(node_map),
        "edges": edge_count,
        "skipped_deletes": skipped_deletes,
    }


# ----------------- 전체/부분 재동기화 (C-7 해소: 키셋 페이지네이션 청킹) -----------------

def _load_best_cell_sources(db, table_name: str, row_ids: list, columns: set) -> dict:
    """청크 로우들의 엣지 관련 컬럼별 최우선 셀 소스를 일괄 조회한다.

    반환: {(row_id, column_name): source_name} — user 최우선 서열(레이어링과 동일).
    idx_sources_lookup(table_name, row_id, column_name) 인덱스 경로.
    """
    from database.models import CellSource

    best = {}
    if not row_ids or not columns:
        return best
    rows = db.query(
        CellSource.row_id, CellSource.column_name, CellSource.source_name
    ).filter(
        CellSource.table_name == table_name,
        CellSource.row_id.in_(row_ids),
        CellSource.column_name.in_(list(columns)),
    ).all()
    for row_id, col, source in rows:
        key = (row_id, col)
        prev = best.get(key)
        if prev is None or _SOURCE_PRIORITY.get(source, 9) < _SOURCE_PRIORITY.get(prev, 9):
            best[key] = source
    return best


def resync_table(db, table_name: str, mappings: dict, chunk_size: int = CHUNK_SIZE,
                 row_ids: list = None, chunk_hook=None, stamp_synced: bool = True) -> dict:
    """테이블 로우를 키셋 페이지네이션(row_id asc) 청크로 그래프에 재동기화한다.

    [C-7 해소] 무제한 `.all()` 로드 금지 — 청크 로드→materialize→(스탬프)→commit 반복.
    - row_ids 지정 시 해당 로우들만(부분 동기화), 미지정 시 테이블 전체.
    - 엣지 provenance는 셀 레이어(CellSource)의 최우선 소스로 복원한다(user 최우선).
    - chunk_hook(rows): 저장소 중립(§4) 확장점 — Neo4j 등 병행 타깃이 청크 단위로 동승.
    - stamp_synced: 청크마다 is_graph_synced/graph_synced_at 벌크 스탬프(+ per-chunk commit).
    """
    from database.models import DYNAMIC_TABLES

    model = DYNAMIC_TABLES.get(table_name)
    mapping = mappings.get(table_name)
    stats = {"rows": 0, "nodes": 0, "edges": 0, "chunks": 0}
    if model is None or mapping is None:
        return stats

    # 엣지 provenance 복원 대상 컬럼: 모든 엣지의 target_identity_from 합집합
    provenance_cols = set()
    for edge_cfg in mapping["edges"]:
        if not edge_cfg.get("source_override"):
            provenance_cols.update(edge_cfg["target_identity_from"])

    data_columns = [
        c.name for c in model.__table__.columns if c.name not in _META_COLUMNS
    ]

    last_row_id = None
    while True:
        q = db.query(model)
        if row_ids:
            q = q.filter(model.row_id.in_(row_ids))
        if last_row_id is not None:
            q = q.filter(model.row_id > last_row_id)
        chunk = q.order_by(model.row_id.asc()).limit(chunk_size).all()
        if not chunk:
            break

        chunk_ids = [r.row_id for r in chunk]
        cell_sources = _load_best_cell_sources(db, table_name, chunk_ids, provenance_cols)

        rows = []
        for r in chunk:
            values = {c: getattr(r, c, None) for c in data_columns}
            # 로우 대표 소스: provenance 컬럼들 중 최우선 소스(없으면 unknown).
            row_source = None
            for col in provenance_cols:
                s = cell_sources.get((r.row_id, col))
                if s is not None and (
                    row_source is None
                    or _SOURCE_PRIORITY.get(s, 9) < _SOURCE_PRIORITY.get(row_source, 9)
                ):
                    row_source = s
            rows.append({
                "row_id": r.row_id,
                "values": values,
                "source_name": row_source or "unknown",
                "updated_by": "graph_resync",
                "event_time": getattr(r, "updated_at", None),
            })

        chunk_stats = materialize_rows(db, table_name, rows, mapping, chunk_size=chunk_size)

        if chunk_hook is not None:
            try:
                chunk_hook(chunk)
            except Exception as e:
                logger.error(f"[Graph] chunk_hook failed for '{table_name}': {e}")

        if stamp_synced:
            db.query(model).filter(model.row_id.in_(chunk_ids)).update(
                {
                    model.is_graph_synced: True,
                    model.needs_graph_rollback: False,
                    model.graph_synced_at: func.now(),
                },
                synchronize_session=False,
            )
        db.commit()  # 청크 단위 커밋 — 수십만 행 단일 커밋 금지(C-7)

        stats["rows"] += chunk_stats["rows"]
        stats["nodes"] += chunk_stats["nodes"]
        stats["edges"] += chunk_stats["edges"]
        stats["chunks"] += 1
        last_row_id = chunk_ids[-1]
        if len(chunk) < chunk_size:
            break
    return stats
