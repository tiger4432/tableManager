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


def _source_priority(source_name, table_name: str = None) -> int:
    """[QA G1-⑥] 소스 서열은 crud를 단일 원천으로 재사용(테이블별 커스텀 포함).

    작을수록 우선(user=0). 미등재/결측은 99(최하) — 하드코딩 서열 이원화 금지.
    """
    from database import crud
    if not source_name:
        return 99
    return crud.get_source_priority(source_name, table_name)


def _normalize_identity_part(v):
    """identity 구성값 정규화 — number 컬럼의 정수값 float(3.0)은 "3"으로 안정화하여
    타 테이블의 string 표기("3")와 정확 일치 MERGE(§2)가 어긋나지 않도록 한다."""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def compose_identity(values) -> str:
    """복수 컬럼 identity를 "|" 조인 문자열로 정규화한다. 하나라도 비면 None(해석 불가).

    [QA G1-⑦] 값 내부의 구분자/이스케이프 문자는 이스케이프한다("\\"→"\\\\", "|"→"\\|") —
    ("A|B","C")와 ("A","B|C")가 같은 identity_key로 충돌하지 않도록.
    """
    parts = []
    for v in values:
        if v is None:
            return None
        s = _normalize_identity_part(v)
        if not s:
            return None
        parts.append(s.replace("\\", "\\\\").replace("|", "\\|"))
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

    rows: [{"row_id", "values": {col: value}, "col_sources": {col: 표시 우선 소스},
            "updated_by", "event_time"}]
    node_map: {(label, identity_key): props_dict} — 스텁(빈 props)은 기존 props를 덮지 않음.
    edges: {(from_key, type, to_key, source_name): edge_row_dict} — 배치 내 dedup(last wins).

    [QA G1-H1] 엣지 provenance는 이벤트의 source_name이 아니라 **셀 레이어 진실**로 결정:
    target_identity_from 컬럼들의 priority_source(CellSource 최우선 소스) 중 **가장 낮은
    서열**(보수적 — 관계 주장은 가장 신뢰도 낮은 입력만큼만 신뢰됨)을 날인한다.
    무관 컬럼의 user 편집이 엣지에 user를 위조 날인하는 경로가 구조적으로 없고,
    증분(materialize_events)·재동기화(resync_table) 두 경로가 동일 입력에 대해
    동일 (from, type, to, source_name) 레코드를 산출한다(경로 동등성).
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
            source_name = edge_cfg.get("source_override")
            if not source_name:
                # [QA G1-H1] 셀 레이어 진실: 식별 컬럼 winner들 중 최저 서열(보수적) 채택.
                col_sources = row.get("col_sources") or {}
                candidates = [
                    col_sources.get(c) or "unknown"
                    for c in edge_cfg["target_identity_from"]
                ]
                source_name = max(
                    candidates,
                    key=lambda s: (_source_priority(s, table_name), s),
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


def _retarget_stale_edges(db, rows: list, chunk_size: int = CHUNK_SIZE,
                          processed_refs: set = None) -> int:
    """[QA G1-H2 / H2-b] 이번 배치에서 처리한 원본 로우들의 stale 엣지 주장을 삭제한다.

    스코프: source_row_ref가 (processed_refs ∪ 이번 산출 엣지의 ref)에 포함된 엣지 중,
    (from_node, type, to_node)가 그 로우의 이번 산출 집합에 없는 것. **로우가 주장의
    단위** — 로우의 현재 상태가 산출하지 않는 주장은 provenance가 무엇이었든 무효다
    (사용자 교정은 winner 소스도 함께 바꾸므로 source_name을 매칭 키에 넣으면 구 소스
    엣지가 잔존한다). [H2-b] 산출이 **0개**인 로우(예: enrichment 소스 삭제로 타깃 blank
    복귀)도 processed_refs로 스코프에 들어와 잔존 엣지가 정리된다 — outbox EDIT payload는
    항상 전 컬럼 스냅샷(stage_event)이므로 "산출 없음 = 현재 로우가 주장 없음"이 보장된다.
    다른 로우가 주장한 엣지는 source_row_ref 스코프 밖이라 절대 건드리지 않는다.
    DELETE 이벤트(행 삭제) 정리는 스펙 §8 범위 밖 — 이 함수는 관여하지 않는다.
    idx_graph_edges_row_ref 인덱스 룩업 + id 청크 삭제(1000행 규율). 반환: 삭제 수.
    """
    from database.models import GraphEdge

    allowed = {}
    for r in rows:
        if not r.get("source_row_ref"):
            continue
        allowed.setdefault(r["source_row_ref"], set()).add(
            (r["from_node"], r["type"], r["to_node"])
        )

    ref_scope = set(processed_refs or ())
    ref_scope.update(allowed)
    if not ref_scope:
        return 0

    row_refs = sorted(ref_scope)
    stale_ids = []
    for i in range(0, len(row_refs), chunk_size):
        ref_chunk = row_refs[i:i + chunk_size]
        existing = db.query(
            GraphEdge.id, GraphEdge.from_node, GraphEdge.type,
            GraphEdge.source_row_ref, GraphEdge.to_node,
        ).filter(GraphEdge.source_row_ref.in_(ref_chunk)).all()
        for eid, from_node, e_type, row_ref, to_node in existing:
            if (from_node, e_type, to_node) not in allowed.get(row_ref, ()):
                stale_ids.append(eid)

    for i in range(0, len(stale_ids), chunk_size):
        id_chunk = stale_ids[i:i + chunk_size]
        db.query(GraphEdge).filter(GraphEdge.id.in_(id_chunk)).delete(
            synchronize_session=False
        )
    if stale_ids:
        logger.info(f"[Graph] retargeted {len(stale_ids)} stale edge(s) (H2 재교정 정리)")
    return len(stale_ids)


def bulk_upsert_edges(db, edges: dict, node_ids: dict, chunk_size: int = CHUNK_SIZE,
                      processed_refs: set = None) -> int:
    """엣지 벌크 UPSERT. 반환: 반영 시도한 엣지 수.

    processed_refs: 이번 배치에서 처리한 전체 로우 ref 집합(산출 0개 로우 포함) —
    [H2-b] 산출 없는 로우의 잔존 엣지 정리를 위해 edges가 비어도 retarget은 수행한다.
    """
    from database.models import GraphEdge

    rows = []
    for edge in (edges or {}).values():
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

    # [QA G1-H2 / H2-b] retarget 의미론: 같은 원본 로우(source_row_ref)가 과거에 주장했으나
    # 이번 산출 집합에 없는 엣지는 삭제 후 UPSERT — 재교정(W123→W124) 시 모순된 구 엣지가
    # 병존하지 않고, 산출이 0개인 로우(타깃 비움)의 잔존 엣지도 processed_refs 스코프로
    # 정리된다. 다른 로우가 주장한 엣지는 source_row_ref 스코프 밖이므로 건드리지 않는다.
    _retarget_stale_edges(db, rows, chunk_size=chunk_size, processed_refs=processed_refs)

    if not rows:
        return 0

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
    # [H2-b] 처리한 전체 로우 ref(산출 0개 로우 포함) — resync 경로에서도 현재 로우 상태에
    # 산출이 없으면 그 로우 ref의 잔존 엣지가 정리된다(증분 경로와 동일 의미론).
    processed_refs = {
        f"{table_name}:{r['row_id']}" for r in rows if r.get("row_id") is not None
    }
    edge_count = bulk_upsert_edges(db, edges, node_ids, chunk_size=chunk_size,
                                   processed_refs=processed_refs)
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
            "updated_by": payload.get("updated_by"),
            "event_time": payload.get("timestamp"),
        })

    node_map, edges = {}, {}
    processed_refs = set()
    total_rows = 0
    for table_name, rows in rows_by_table.items():
        # [QA G1-H1] 엣지 provenance는 이벤트 소스가 아니라 셀 레이어 winner로 결정(경로 동등성).
        attach_col_sources(db, table_name, rows, mappings[table_name])
        extract_graph_items(table_name, rows, mappings[table_name], node_map, edges)
        # [H2-b] 산출 0개 로우(예: 타깃 blank 복귀)도 retarget 스코프에 포함.
        processed_refs.update(
            f"{table_name}:{r['row_id']}" for r in rows if r.get("row_id") is not None
        )
        total_rows += len(rows)

    node_ids = bulk_upsert_nodes(db, node_map, chunk_size=chunk_size)
    edge_count = bulk_upsert_edges(db, edges, node_ids, chunk_size=chunk_size,
                                   processed_refs=processed_refs)
    return {
        "rows": total_rows,
        "nodes": len(node_map),
        "edges": edge_count,
        "skipped_deletes": skipped_deletes,
    }


# ----------------- 전체/부분 재동기화 (C-7 해소: 키셋 페이지네이션 청킹) -----------------

def _edge_provenance_cols(mapping: dict) -> set:
    """엣지 provenance 결정에 필요한 컬럼 집합(source_override 엣지는 제외)."""
    cols = set()
    for edge_cfg in mapping.get("edges", []):
        if not edge_cfg.get("source_override"):
            cols.update(edge_cfg["target_identity_from"])
    return cols


def _load_best_cell_sources(db, table_name: str, row_ids: list, columns: set,
                            chunk_size: int = CHUNK_SIZE) -> dict:
    """로우들의 엣지 관련 컬럼별 표시 우선(winner) 셀 소스를 일괄 조회한다.

    반환: {(row_id, column_name): source_name} — crud 서열(단일 원천, 테이블 커스텀 포함).
    idx_sources_lookup(table_name, row_id, column_name) 인덱스 경로 + row_id IN 청킹.
    """
    from database.models import CellSource

    best = {}
    if not row_ids or not columns:
        return best
    col_list = list(columns)
    for i in range(0, len(row_ids), chunk_size):
        id_chunk = row_ids[i:i + chunk_size]
        rows = db.query(
            CellSource.row_id, CellSource.column_name, CellSource.source_name
        ).filter(
            CellSource.table_name == table_name,
            CellSource.row_id.in_(id_chunk),
            CellSource.column_name.in_(col_list),
        ).all()
        for row_id, col, source in rows:
            key = (row_id, col)
            prev = best.get(key)
            if prev is None or (
                _source_priority(source, table_name) < _source_priority(prev, table_name)
            ):
                best[key] = source
    return best


def attach_col_sources(db, table_name: str, rows: list, mapping: dict):
    """[QA G1-H1] 로우 목록에 col_sources(식별 컬럼별 winner 소스)를 부착한다.

    증분·재동기화 두 경로가 이 함수를 공유 — 엣지 provenance 산출의 단일 지점.
    """
    cols = _edge_provenance_cols(mapping)
    if not cols:
        for row in rows:
            row["col_sources"] = {}
        return
    winners = _load_best_cell_sources(db, table_name, [r["row_id"] for r in rows], cols)
    for row in rows:
        row["col_sources"] = {
            c: winners.get((row["row_id"], c)) for c in cols
            if winners.get((row["row_id"], c)) is not None
        }


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

    data_columns = [
        c.name for c in model.__table__.columns if c.name not in _META_COLUMNS
    ]

    def _process_chunk(chunk):
        chunk_ids = [r.row_id for r in chunk]
        rows = [
            {
                "row_id": r.row_id,
                "values": {c: getattr(r, c, None) for c in data_columns},
                "updated_by": "graph_resync",
                "event_time": getattr(r, "updated_at", None),
            }
            for r in chunk
        ]
        # [QA G1-H1] 증분 경로와 동일 지점(attach_col_sources)에서 provenance 결정 — 경로 동등성.
        attach_col_sources(db, table_name, rows, mapping)
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

    if row_ids:
        # [QA G1-⑤] 부분 동기화: row_ids를 청크 크기로 슬라이스 — 청크마다 전체 목록
        # IN 반복 없이 슬라이스 단위 IN 조회(대량 선택에도 페이로드/플랜 안정).
        unique_ids = sorted(set(row_ids))
        for i in range(0, len(unique_ids), chunk_size):
            id_slice = unique_ids[i:i + chunk_size]
            chunk = db.query(model).filter(
                model.row_id.in_(id_slice)
            ).order_by(model.row_id.asc()).all()
            if chunk:
                _process_chunk(chunk)
        return stats

    last_row_id = None
    while True:
        q = db.query(model)
        if last_row_id is not None:
            q = q.filter(model.row_id > last_row_id)
        chunk = q.order_by(model.row_id.asc()).limit(chunk_size).all()
        if not chunk:
            break
        last_row_id = chunk[-1].row_id  # commit 전 캡처(expire_on_commit 재조회 방지)
        _process_chunk(chunk)
        if len(chunk) < chunk_size:
            break
    return stats
