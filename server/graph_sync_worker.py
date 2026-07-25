import asyncio
import json
import os
import logging
import time
from datetime import datetime

# Setup Unified Logger
from utils.logger import get_process_logger
from utils.payload_helper import get_payload_dict

logger = get_process_logger("GraphSync", "graph_sync.log")

ONTOLOGY_PATH = os.path.join(os.path.dirname(__file__), "config", "ontology_mapping.json")

def load_ontology_mapping():
    if not os.path.exists(ONTOLOGY_PATH):
        logger.warning(f"Ontology mapping file not found at {ONTOLOGY_PATH}. Using default schema.")
        return {}
    try:
        with open(ONTOLOGY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load ontology mapping from {ONTOLOGY_PATH}: {e}")
        return {}

# Neo4j Driver setup
neo4j_enabled = os.getenv("NEO4J_ENABLED", "false").lower() == "true"
neo4j_driver = None

if neo4j_enabled:
    try:
        from neo4j import GraphDatabase
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "password")
        neo4j_driver = GraphDatabase.driver(uri, auth=(user, password))
        logger.info(f"Neo4j driver initialized successfully. Connecting to {uri}")
    except ImportError:
        logger.warning("neo4j package not installed. GraphSync running in Mock Mode.")
        neo4j_enabled = False
    except Exception as e:
        logger.error(f"Failed to initialize Neo4j driver: {e}. Running in Mock Mode.")
        neo4j_enabled = False
else:
    logger.info("Neo4j is disabled (NEO4J_ENABLED=false). Running in Mock Mode.")

# ----------------- Cypher Query Builders for Neo4j Ingestion -----------------

def build_cypher_create(table_name, payload, ontology):
    table_cfg = ontology.get("tables", {}).get(table_name, ontology.get("default", {}))
    node_label = table_cfg.get("node_label", "Row")
    identity_prop = table_cfg.get("identity_property", "row_id")
    
    cypher = (
        f"MERGE (r:{node_label} {{{identity_prop}: $row_id}})\n"
        f"SET r.created_at = datetime($timestamp),\n"
        f"    r.updated_at = datetime($timestamp)\n"
    )
    if payload.get("business_key"):
        cypher += f"SET r.business_key = $business_key\n"
        
    params = {
        "row_id": payload.get("row_id"),
        "business_key": payload.get("business_key"),
        "timestamp": payload.get("timestamp")
    }

    data_payload = payload.get("data", {})
    prop_mappings = table_cfg.get("property_mappings", {})
    
    cypher_parts = []
    param_idx = 0
    
    for col_name, val_dict in data_payload.items():
        if not isinstance(val_dict, dict):
            continue
        val = val_dict.get("value")
        graph_prop_name = prop_mappings.get(col_name, col_name)
        
        # 1. Map properties
        param_key = f"val_{param_idx}"
        cypher += f"SET r.{graph_prop_name} = ${param_key}\n"
        params[param_key] = val
        param_idx += 1

        # 2. Map relationships
        rel_cfg = table_cfg.get("relationships", {}).get(col_name)
        if rel_cfg and val:
            rel_type = rel_cfg.get("type", "RELATED_TO")
            target_label = rel_cfg.get("target_label", "Entity")
            target_ident = rel_cfg.get("target_identity", "id")
            
            target_param_key = f"target_val_{param_idx}"
            rel_cypher = (
                f"MATCH (r:{node_label} {{{identity_prop}: $row_id}})\n"
                f"MERGE (target:{target_label} {{{target_ident}: ${target_param_key}}})\n"
                f"MERGE (r)-[rel:{rel_type}]->(target)\n"
                f"SET rel.updated_at = datetime($timestamp)\n"
            )
            cypher_parts.append((rel_cypher, {
                "row_id": payload.get("row_id"),
                "timestamp": payload.get("timestamp"),
                target_param_key: val
            }))
            param_idx += 1

    # 3. Create Audit relation if update user is present
    if payload.get("updated_by"):
        audit_cypher = (
            f"MATCH (r:{node_label} {{{identity_prop}: $row_id}})\n"
            f"MERGE (src:DataSource {{name: $source_name}})\n"
            f"CREATE (src)-[:UPDATED {{\n"
            f"    timestamp: datetime($timestamp),\n"
            f"    updated_by: $updated_by,\n"
            f"    transaction_id: $transaction_id\n"
            f"}}]->(r)"
        )
        cypher_parts.append((audit_cypher, {
            "row_id": payload.get("row_id"),
            "timestamp": payload.get("timestamp"),
            "source_name": payload.get("source_name", "user"),
            "updated_by": payload.get("updated_by"),
            "transaction_id": payload.get("transaction_id", "")
        }))

    # 4. Connect to Table node
    table_node_cypher = (
        f"MATCH (r:{node_label} {{{identity_prop}: $row_id}})\n"
        f"MERGE (t:Table {{name: $table_name}})\n"
        f"MERGE (r)-[:BELONGS_TO]->(t)"
    )
    cypher_parts.append((table_node_cypher, {
        "row_id": payload.get("row_id"),
        "table_name": table_name
    }))
    
    return [(cypher, params)] + cypher_parts

def build_cypher_edit(table_name, payload, ontology):
    table_cfg = ontology.get("tables", {}).get(table_name, ontology.get("default", {}))
    node_label = table_cfg.get("node_label", "Row")
    identity_prop = table_cfg.get("identity_property", "row_id")
    
    cypher = (
        f"MERGE (r:{node_label} {{{identity_prop}: $row_id}})\n"
        f"SET r.updated_at = datetime($timestamp)\n"
    )
    if payload.get("business_key"):
        cypher += f"SET r.business_key = $business_key\n"
        
    params = {
        "row_id": payload.get("row_id"),
        "business_key": payload.get("business_key"),
        "timestamp": payload.get("timestamp")
    }

    data_payload = payload.get("data", {})
    prop_mappings = table_cfg.get("property_mappings", {})
    
    cypher_parts = []
    param_idx = 0
    
    for col_name, val_dict in data_payload.items():
        if not isinstance(val_dict, dict):
            continue
        val = val_dict.get("value")
        graph_prop_name = prop_mappings.get(col_name, col_name)
        
        # 1. Update properties
        param_key = f"val_{param_idx}"
        cypher += f"SET r.{graph_prop_name} = ${param_key}\n"
        params[param_key] = val
        param_idx += 1

        # 2. Update relationships
        rel_cfg = table_cfg.get("relationships", {}).get(col_name)
        if rel_cfg and val:
            rel_type = rel_cfg.get("type", "RELATED_TO")
            target_label = rel_cfg.get("target_label", "Entity")
            target_ident = rel_cfg.get("target_identity", "id")
            
            target_param_key = f"target_val_{param_idx}"
            rel_cypher = (
                f"MATCH (r:{node_label} {{{identity_prop}: $row_id}})\n"
                f"MERGE (target:{target_label} {{{target_ident}: ${target_param_key}}})\n"
                f"MERGE (r)-[rel:{rel_type}]->(target)\n"
                f"SET rel.updated_at = datetime($timestamp)\n"
            )
            cypher_parts.append((rel_cypher, {
                "row_id": payload.get("row_id"),
                "timestamp": payload.get("timestamp"),
                target_param_key: val
            }))
            param_idx += 1

    # 3. Create Audit relation if update user is present
    if payload.get("updated_by"):
        audit_cypher = (
            f"MATCH (r:{node_label} {{{identity_prop}: $row_id}})\n"
            f"MERGE (src:DataSource {{name: $source_name}})\n"
            f"CREATE (src)-[:UPDATED {{\n"
            f"    timestamp: datetime($timestamp),\n"
            f"    updated_by: $updated_by,\n"
            f"    transaction_id: $transaction_id\n"
            f"}}]->(r)"
        )
        cypher_parts.append((audit_cypher, {
            "row_id": payload.get("row_id"),
            "timestamp": payload.get("timestamp"),
            "source_name": payload.get("source_name", "user"),
            "updated_by": payload.get("updated_by"),
            "transaction_id": payload.get("transaction_id", "")
        }))
        
    return [(cypher, params)] + cypher_parts

def build_cypher_delete(table_name, payload, ontology):
    table_cfg = ontology.get("tables", {}).get(table_name, ontology.get("default", {}))
    node_label = table_cfg.get("node_label", "Row")
    identity_prop = table_cfg.get("identity_property", "row_id")
    
    cypher = (
        f"MATCH (r:{node_label} {{{identity_prop}: $row_id}})\n"
        f"DETACH DELETE r"
    )
    params = {
        "row_id": payload.get("row_id")
    }
    return cypher, params

async def execute_batch_queries(queries, tx_id):
    if not queries:
        return True
        
    if neo4j_enabled and neo4j_driver:
        try:
            with neo4j_driver.session() as session:
                def execute_tx(tx):
                    for cypher, params in queries:
                        tx.run(cypher, **params)
                session.execute_write(execute_tx)
            logger.info(f"Successfully synced transaction '{tx_id}' ({len(queries)} queries) to Neo4j.")
        except Exception as e:
            logger.error(f"Neo4j sync fail for transaction '{tx_id}': {e}")
            return False
    else:
        # Mock Logging Mode
        logger.info(f"[MOCK GRAPH SYNC] Syncing transaction '{tx_id}' ({len(queries)} queries)")
        for idx, (cypher, params) in enumerate(queries):
            pass
            
    return True

def build_queries_for_event(event, ontology):
    event_type = event.event_type
    table_name = event.table_name
    payload = get_payload_dict(event)
    
    queries = []
    if event_type == "CREATE":
        cypher, params = build_cypher_create(table_name, payload, ontology)
        queries.append((cypher, params))
    elif event_type == "EDIT":
        edit_queries = build_cypher_edit(table_name, payload, ontology)
        queries.extend(edit_queries)
    elif event_type == "DELETE":
        cypher, params = build_cypher_delete(table_name, payload, ontology)
        queries.append((cypher, params))
    else:
        logger.warning(f"Unsupported event type: {event_type} on event: {event.event_uuid}")
        
    return queries

# ----------------- Manual Graph Sync CLI Spawner Support -----------------
VIRTUAL_GRAPH_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "database", "virtual_graph.json"))

def load_virtual_graph() -> dict:
    if os.path.exists(VIRTUAL_GRAPH_PATH):
        try:
            with open(VIRTUAL_GRAPH_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"nodes": {}, "edges": []}

def save_virtual_graph(graph: dict):
    os.makedirs(os.path.dirname(VIRTUAL_GRAPH_PATH), exist_ok=True)
    with open(VIRTUAL_GRAPH_PATH, "w", encoding="utf-8") as f:
        json.dump(graph, f, indent=2, ensure_ascii=False)

def rollback_virtual_graph(dirty_time):
    graph = load_virtual_graph()
    import dateutil.parser
    
    nodes_to_keep = {}
    deleted_ids = set()
    for row_id, node in graph.get("nodes", {}).items():
        props = node.get("properties", {})
        upd_str = props.get("updated_at") or props.get("created_at")
        if upd_str:
            try:
                t = dateutil.parser.isoparse(upd_str)
                if t.tzinfo is not None and dirty_time.tzinfo is None:
                    t = t.replace(tzinfo=None)
                elif t.tzinfo is None and dirty_time.tzinfo is not None:
                    dirty_time = dirty_time.replace(tzinfo=None)
                if t >= dirty_time:
                    deleted_ids.add(row_id)
                    continue
            except Exception:
                pass
        nodes_to_keep[row_id] = node
        
    edges_to_keep = []
    for edge in graph.get("edges", []):
        src = edge.get("source_id")
        tgt = edge.get("target_id")
        upd_str = edge.get("updated_at")
        if src in deleted_ids or tgt in deleted_ids:
            continue
        if upd_str:
            try:
                t = dateutil.parser.isoparse(upd_str)
                if t.tzinfo is not None and dirty_time.tzinfo is None:
                    t = t.replace(tzinfo=None)
                elif t.tzinfo is None and dirty_time.tzinfo is not None:
                    dirty_time = dirty_time.replace(tzinfo=None)
                if t >= dirty_time:
                    continue
            except Exception:
                pass
        edges_to_keep.append(edge)
        
    graph["nodes"] = nodes_to_keep
    graph["edges"] = edges_to_keep
    save_virtual_graph(graph)

def upsert_virtual_graph_row(table_name: str, row, ontology_cfg: dict, timestamp, graph: dict = None):
    should_save = False
    if graph is None:
        graph = load_virtual_graph()
        should_save = True
        
    table_cfg = ontology_cfg.get("tables", {}).get(table_name, ontology_cfg.get("default", {}))
    node_label = table_cfg.get("node_label", "Row")
    prop_mappings = table_cfg.get("property_mappings", {})
    rel_cfgs = table_cfg.get("relationships", {})
    
    properties = {
        "row_id": row.row_id,
        "business_key": row.business_key_val,
        "created_at": row.created_at.isoformat() if getattr(row, "created_at", None) else timestamp.isoformat(),
        "updated_at": row.updated_at.isoformat() if getattr(row, "updated_at", None) else timestamp.isoformat()
    }
    
    mapper = getattr(row, "_sa_class_manager", None)
    if mapper:
        for col_name in mapper.keys():
            if col_name in ["row_id", "business_key_val", "created_at", "updated_at", "is_graph_synced", "needs_graph_rollback", "graph_synced_at"]:
                continue
            val = getattr(row, col_name, None)
            if isinstance(val, dict) and "value" in val:
                val = val.get("value")
            graph_prop = prop_mappings.get(col_name, col_name)
            properties[graph_prop] = val
    elif getattr(row, "data", None) and isinstance(row.data, dict):
        for col_name, val_dict in row.data.items():
            if not isinstance(val_dict, dict):
                continue
            val = val_dict.get("value")
            graph_prop = prop_mappings.get(col_name, col_name)
            properties[graph_prop] = val
            
    graph["nodes"][row.row_id] = {
        "labels": [node_label],
        "properties": properties
    }
    
    graph["edges"] = [e for e in graph["edges"] if e["source_id"] != row.row_id]
    graph["edges"].append({
        "source_id": row.row_id,
        "target_id": f"Table_{table_name}",
        "type": "BELONGS_TO",
        "updated_at": timestamp.isoformat()
    })
    
    if mapper:
        for col_name in rel_cfgs.keys():
            val = getattr(row, col_name, None)
            if isinstance(val, dict) and "value" in val:
                val = val.get("value")
            rel_cfg = rel_cfgs.get(col_name)
            if rel_cfg and val:
                rel_type = rel_cfg.get("type", "RELATED_TO")
                target_label = rel_cfg.get("target_label", "Entity")
                target_ident = rel_cfg.get("target_identity", "id")
                
                target_node_id = f"{target_label}_{val}"
                if target_node_id not in graph["nodes"]:
                    graph["nodes"][target_node_id] = {
                        "labels": [target_label],
                        "properties": { target_ident: val, "created_at": timestamp.isoformat(), "updated_at": timestamp.isoformat() }
                    }
                graph["edges"].append({
                    "source_id": row.row_id,
                    "target_id": target_node_id,
                    "type": rel_type,
                    "updated_at": timestamp.isoformat()
                })
    elif getattr(row, "data", None) and isinstance(row.data, dict):
        for col_name, val_dict in row.data.items():
            if not isinstance(val_dict, dict):
                continue
            val = val_dict.get("value")
            rel_cfg = rel_cfgs.get(col_name)
            if rel_cfg and val:
                rel_type = rel_cfg.get("type", "RELATED_TO")
                target_label = rel_cfg.get("target_label", "Entity")
                target_ident = rel_cfg.get("target_identity", "id")
                
                target_node_id = f"{target_label}_{val}"
                if target_node_id not in graph["nodes"]:
                    graph["nodes"][target_node_id] = {
                        "labels": [target_label],
                        "properties": { target_ident: val, "created_at": timestamp.isoformat(), "updated_at": timestamp.isoformat() }
                    }
                graph["edges"].append({
                    "source_id": row.row_id,
                    "target_id": target_node_id,
                    "type": rel_type,
                    "updated_at": timestamp.isoformat()
                })
                
    if should_save:
        save_virtual_graph(graph)

def format_id_list(id_list: list, max_show: int = 6) -> str:
    """대량 ID 목록 출력 시 로그 가독성을 위해 중간 생략 형태로 축약 가공합니다."""
    if not id_list:
        return "[]"
    if len(id_list) <= max_show:
        return str(id_list)
    half = max_show // 2
    left = id_list[:half]
    right = id_list[-half:]
    return f"[{', '.join(map(repr, left))}, ... ({len(id_list) - max_show}개 생략) ..., {', '.join(map(repr, right))}]"

def to_local_str(dt):
    if not dt: return ""
    return dt.strftime("%Y-%m-%d %H:%M:%S")

async def post_event_async(endpoint: str, payload: dict):
    import requests
    api_url = os.getenv("API_BASE_URL", "http://127.0.0.1:8080")
    url = f"{api_url}{endpoint}"
    def do_post():
        try:
            res = requests.post(url, json=payload, timeout=20)
            if not res.ok:
                logger.error(f"[GraphSync Process] API notification failed: {url} -> {res.status_code}")
        except Exception as e:
            logger.error(f"[GraphSync Process] Failed to send API notification: {e}")
    await asyncio.to_thread(do_post)

# ----------------- [Ontology G1] PG 엣지 스토어 materializer -----------------
# outbox 증분 소비(자체 keyset 커서) → 매핑 config(v2) 적용 → graph_nodes/graph_edges UPSERT.
# 1차 타깃은 PG 엣지 스토어(스펙 §1 확정). Neo4j 경로(위 Cypher 빌더들)는 저장소 중립(§4)
# 원칙에 따라 인터페이스를 보존하며, 수동 재동기화에서 청크 훅으로 병행 동승한다.

GRAPH_BATCH_LIMIT = 1000  # 배치당 outbox 소비 상한 (1000행 청킹 규율 — 스펙 §5)


def _load_graph_mappings():
    """v2 온톨로지 매핑(+enrichment RESOLVED_AS 자동 승격)을 로드한다."""
    from database import crud
    import ontology_config
    known = crud.TABLE_CONFIG if crud.TABLE_CONFIG else None
    return ontology_config.load_ontology_mappings(known_tables=known)


def _get_or_init_graph_cursor(db) -> int:
    """materializer의 outbox 소비 커서를 조회한다(최초 1회 현재 최대 id로 초기화).

    최초 초기화가 백로그를 건너뛰는 것은 의도된 동작 — 과거 데이터는 전체 재동기화
    (/api/graph/sync)가 커버하고, 커서는 이후 증분만 따라간다.
    """
    from database.models import GraphSyncState, DatabaseOutbox
    from sqlalchemy import func as sa_func

    state = db.query(GraphSyncState).filter(GraphSyncState.id == 1).first()
    if state is None:
        max_id = db.query(sa_func.max(DatabaseOutbox.id)).scalar() or 0
        state = GraphSyncState(id=1, last_outbox_id=max_id)
        db.add(state)
        db.commit()
        logger.info(
            f"[Graph] materializer cursor initialized at outbox id {max_id} "
            "(기존 백로그는 전체 재동기화로 커버)"
        )
        return max_id
    return state.last_outbox_id or 0


def _advance_graph_cursor(db, last_id: int):
    """커서 전진(commit은 호출자 — 그래프 반영과 같은 트랜잭션으로 원자화)."""
    from database.models import GraphSyncState
    db.query(GraphSyncState).filter(GraphSyncState.id == 1).update(
        {GraphSyncState.last_outbox_id: last_id}, synchronize_session=False
    )


def _lag_ms_from(created_at) -> float:
    """이벤트 적재 시각 → 그래프 반영 완료 시각의 지연(ms). tz-aware/naive 모두 안전."""
    if not created_at:
        return 0.0
    now = datetime.now(created_at.tzinfo) if created_at.tzinfo else datetime.now()
    return max((now - created_at).total_seconds() * 1000.0, 0.0)


def _reload_graph_worker_configs():
    """[이슈 #8] SYSTEM_RELOAD 구독 처리 — 신규 테이블 모델/매핑 리로드.

    #7의 refresh_dynamic_models 공용 진입점을 재사용한다(신규 테이블 ORM 등록 +
    물리 CREATE 보충 + 그래프 시스템 테이블 보장). 이후 온톨로지 매핑을 재로드한다.
    """
    from database.database import engine as _db_engine
    from database import models as _db_models, crud as _crud
    try:
        created = _db_models.refresh_dynamic_models(_db_engine)
        if created:
            logger.info(f"[Graph Reload] Created missing physical tables at runtime: {created}")
    except Exception as e:
        logger.error(f"[Graph Reload] Dynamic model refresh failed: {e}")
    # 웹서버 rollback-flag 판정용 온톨로지 캐시도 이 프로세스에서는 무효화(다음 접근 시 재로드)
    try:
        _crud._ontology_cache = None
    except Exception:
        pass
    mappings = _load_graph_mappings()
    logger.info(f"[Graph Reload] Reloaded ontology mappings for {len(mappings)} table(s).")
    return mappings


async def run_graph_materializer_loop():
    """outbox 증분 소비 메인 루프 (chain_ingestion_worker의 소비 골격 준용).

    - 자체 커서(graph_sync_state.last_outbox_id) 기반 keyset 소비 — 체인 워커의
      processed_chain 플래그와 완전 독립.
    - LISTEN/NOTIFY(outbox_event 채널)로 저지연 wake, 폴백 폴링 2s.
    - 배치 내 SYSTEM_RELOAD 이벤트 감지 시 모델/매핑 핫리로드(이슈 #8).
    - [GraphLatency] 계측 상시 (SLO: 배치당 10초 이내 — 스펙 §5).
    """
    from database.database import SessionLocal, engine
    from database.models import DatabaseOutbox, ensure_graph_tables
    import graph_materializer

    try:
        ensure_graph_tables(engine)
    except Exception as e:
        logger.error(f"[Graph] ensure_graph_tables failed at loop start: {e}")

    mappings = _load_graph_mappings()
    logger.info(
        f"[Graph] materializer loop started — {len(mappings)} mapped table(s): {sorted(mappings)}"
    )

    listener = None
    if engine.dialect.name == "postgresql":
        try:
            from chain_ingestion_worker import OutboxListener
            listener = OutboxListener(SessionLocal, "outbox_event")
        except Exception as e:
            logger.warning(f"[Graph] LISTEN unavailable, falling back to polling: {e}")

    def _run_one_batch(current_mappings):
        """[QA G1-M3] 동기 DB 배치 처리 본체 — to_thread에서 실행되어 이 프로세스의
        이벤트 루프(/sync HTTP 서빙)를 백로그 소진 중에도 블로킹하지 않는다.
        반환: (wait_needed, mappings)."""
        db = SessionLocal()
        try:
            cursor = _get_or_init_graph_cursor(db)
            events = db.query(DatabaseOutbox).filter(
                DatabaseOutbox.id > cursor
            ).order_by(DatabaseOutbox.id.asc()).limit(GRAPH_BATCH_LIMIT).all()

            if not events:
                return True, current_mappings

            # [이슈 #8] 배치 내 SYSTEM_RELOAD 감지 → 모델/매핑 리로드 후 배치 처리 계속.
            # (커서가 스캔한 범위만 전진하므로 리로드 이벤트를 놓치는 경로가 없다.)
            if any(e.event_type == "SYSTEM_RELOAD" for e in events):
                current_mappings = _reload_graph_worker_configs()

            t0 = time.monotonic()
            stats = graph_materializer.materialize_events(db, events, current_mappings)
            _advance_graph_cursor(db, events[-1].id)
            db.commit()  # 그래프 반영 + 커서 전진 원자 커밋(재처리 시에도 UPSERT 멱등)
            exec_ms = (time.monotonic() - t0) * 1000.0
            lag_ms = _lag_ms_from(events[0].created_at)
            logger.info(
                f"[GraphLatency] batch={len(events)} rows={stats['rows']} "
                f"nodes={stats['nodes']} edges={stats['edges']} "
                f"lag_ms={lag_ms:.0f} exec_ms={exec_ms:.0f}"
                + (f" skipped_deletes={stats['skipped_deletes']}"
                   if stats.get("skipped_deletes") else "")
            )
            return False, current_mappings
        finally:
            db.close()

    while True:
        try:
            # [QA G1-M3] 배치 처리를 스레드로 격리 — 연속 배치(백로그 소진) 중에도
            # 이벤트 루프가 자유로워 /sync 요청이 기아 상태에 빠지지 않는다.
            wait_needed, mappings = await asyncio.to_thread(_run_one_batch, mappings)
        except Exception as e:
            logger.error(f"[Graph] materializer loop error: {e}")
            await asyncio.sleep(1.0)
            continue

        if wait_needed:
            if listener is not None:
                await listener.wait(2.0)
            else:
                await asyncio.sleep(2.0)


# ----------------- 리팩토링 Core: 모듈식 비즈니스 함수 세트 -----------------

from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="AssyManager GraphSync Worker HTTP Service")

class GraphSyncRequest(BaseModel):
    table_name: str
    row_ids: Optional[list[str]] = None

# 2) RDB 데이터 수집 및 조회 함수
def get_row_data_for_sync(db, table_name: str, row_ids: list[str]) -> dict:
    """[DEPRECATED — C-7] 무제한 `.all()` 로드를 수행하는 구 수집 경로.

    /api/graph/sync 흐름에서는 더 이상 사용하지 않는다(키셋 청킹 resync_table로 대체).
    Neo4j rollback&replay(G4) 참고 구현으로만 보존 — 신규 배선 금지.
    """
    from database.models import DYNAMIC_TABLES
    from datetime import datetime, timezone
    
    if table_name not in DYNAMIC_TABLES:
        raise HTTPException(status_code=400, detail=f"유효하지 않은 테이블 이름입니다: {table_name}")
        
    model_class = DYNAMIC_TABLES[table_name]
    target_rows_map = {}
    has_rollback_target = False
    deleted_row_ids = []
    
    if row_ids:
        all_rows = db.query(model_class).filter(model_class.row_id.in_(row_ids)).all()
        found_ids = {r.row_id for r in all_rows}
        deleted_row_ids = [rid for rid in row_ids if rid not in found_ids]
        
        # 이미 동기화 완료되었고 롤백도 필요하지 않은 행들은 수집 대상에서 제외
        rows = [r for r in all_rows if (not getattr(r, "is_graph_synced", False)) or getattr(r, "needs_graph_rollback", False)]
        target_rows_map[table_name] = rows
        
        if deleted_row_ids:
            has_rollback_target = True
        if any(getattr(r, "needs_graph_rollback", False) for r in rows):
            has_rollback_target = True
    else:
        rows = db.query(model_class).filter(
            (model_class.is_graph_synced == False) | (model_class.needs_graph_rollback == True)
        ).all()
        target_rows_map[table_name] = rows
        if any(getattr(r, "needs_graph_rollback", False) for r in rows):
            has_rollback_target = True
            
    total_sync_targets = sum(len(lst) for lst in target_rows_map.values())
    
    all_dirty_rows = []
    dirty_timestamp = None
    mode = "incremental_update"
    
    if has_rollback_target and (total_sync_targets > 0 or deleted_row_ids):
        mode = "rollback_and_replay"
        dirty_timestamp = datetime.now(timezone.utc)
        for t_name, rows in target_rows_map.items():
            for r in rows:
                s_at = getattr(r, "graph_synced_at", None)
                if s_at:
                    if s_at.tzinfo is None:
                        s_at = s_at.replace(tzinfo=timezone.utc)
                    if s_at < dirty_timestamp:
                        dirty_timestamp = s_at
                        
        for t_name, model in DYNAMIC_TABLES.items():
            dirty_rows = db.query(model).filter(model.updated_at >= dirty_timestamp).all()
            for r in dirty_rows:
                all_dirty_rows.append((t_name, r))
        all_dirty_rows.sort(key=lambda x: x[1].updated_at if x[1].updated_at else datetime.now(timezone.utc))
        
    return {
        "mode": mode,
        "target_rows_map": target_rows_map,
        "all_dirty_rows": all_dirty_rows,
        "deleted_row_ids": deleted_row_ids,
        "dirty_timestamp": dirty_timestamp,
        "total_sync_targets": total_sync_targets
    }

# 4) 각 저장소 모드별 실행 전담 함수군

def sync_virtual_graph_rollback_and_replay(sync_data: dict, ontology: dict):
    """가상 그래프 파일(virtual_graph.json) 상에서 롤백 및 재생 작업을 완료합니다."""
    dirty_time = sync_data["dirty_timestamp"]
    all_dirty_rows = sync_data["all_dirty_rows"]
    deleted_row_ids = sync_data["deleted_row_ids"]
    
    rollback_virtual_graph(dirty_time)
    
    v_graph = load_virtual_graph()
    for t_name, row in all_dirty_rows:
        upsert_virtual_graph_row(t_name, row, ontology, datetime.now(), graph=v_graph)
        
    if deleted_row_ids:
        for rid in deleted_row_ids:
            v_graph["nodes"].pop(rid, None)
        v_graph["edges"] = [e for e in v_graph.get("edges", []) if e.get("source_id") not in deleted_row_ids and e.get("target_id") not in deleted_row_ids]
        
    save_virtual_graph(v_graph)

def sync_virtual_graph_incremental(sync_data: dict, ontology: dict):
    """가상 그래프 파일(virtual_graph.json) 상에서 특정 타겟들만 증분 업데이트합니다."""
    target_rows_map = sync_data["target_rows_map"]
    v_graph = load_virtual_graph()
    for t_name, rows in target_rows_map.items():
        for r in rows:
            upsert_virtual_graph_row(t_name, r, ontology, datetime.now(), graph=v_graph)
    save_virtual_graph(v_graph)

async def sync_neo4j_rollback_and_replay(sync_data: dict, ontology: dict):
    """Neo4j 데이터베이스 상에서 시점 롤백 및 배치 사이퍼 쿼리를 재생 실행합니다."""
    dirty_time = sync_data["dirty_timestamp"]
    all_dirty_rows = sync_data["all_dirty_rows"]
    deleted_row_ids = sync_data["deleted_row_ids"]
    
    rollback_cypher = (
        "MATCH (n)\n"
        "WHERE n.updated_at >= datetime($dirty_time) OR n.created_at >= datetime($dirty_time)\n"
        "DETACH DELETE n"
    )
    await execute_batch_queries([(rollback_cypher, {"dirty_time": dirty_time.isoformat()})], "rollback_tx")
    
    queries_to_run = []
    for t_name, row in all_dirty_rows:
        event_mock = create_light_event_mock("EDIT", t_name, row)
        queries_to_run.extend(build_queries_for_event(event_mock, ontology))
    if queries_to_run:
        await execute_batch_queries(queries_to_run, f"replay_{int(dirty_time.timestamp())}")
        
    if deleted_row_ids:
        del_queries = [("MATCH (n {row_id: $row_id}) DETACH DELETE n", {"row_id": rid}) for rid in deleted_row_ids]
        await execute_batch_queries(del_queries, "delete_nodes_tx")

async def sync_neo4j_incremental(sync_data: dict, ontology: dict):
    """Neo4j 데이터베이스 상에서 특정 로우 변경점들만 사이퍼 쿼리로 빌드해 증분 업데이트합니다."""
    target_rows_map = sync_data["target_rows_map"]
    queries_to_run = []
    for t_name, rows in target_rows_map.items():
        for r in rows:
            event_mock = create_light_event_mock("EDIT", t_name, r)
            queries_to_run.extend(build_queries_for_event(event_mock, ontology))
    if queries_to_run:
        await execute_batch_queries(queries_to_run, "incremental_tx")

def create_light_event_mock(event_type: str, t_name: str, row):
    """사이퍼 쿼리 생성을 위해 Outbox 이벤트의 인터페이스를 갖춘 모의 객체를 조립합니다."""
    from datetime import datetime
    row_data = {}
    mapper = getattr(row, "_sa_class_manager", None)
    if mapper:
        for col_name in mapper.keys():
            if col_name in ["row_id", "business_key_val", "created_at", "updated_at", "is_graph_synced", "needs_graph_rollback", "graph_synced_at"]:
                continue
            val = getattr(row, col_name, None)
            row_data[col_name] = {"value": val}
    elif getattr(row, "data", None) and isinstance(row.data, dict):
        row_data = row.data
        
    class LightEventMock:
        def __init__(self):
            self.event_type = event_type
            self.table_name = t_name
            self.event_uuid = row.row_id
            self.payload = {
                "row_id": row.row_id,
                "business_key": row.business_key_val,
                "timestamp": row.updated_at.isoformat() if row.updated_at else datetime.now().isoformat(),
                "data": row_data,
                "updated_by": "manual_sync"
            }
    return LightEventMock()

# 3) [진입 분기부] build_graph_db_ingestion
async def build_graph_db_ingestion(sync_data: dict, ontology: dict):
    """동기화 정보를 토대로 Neo4j 드라이버 유무에 따라 타겟 저장소 기동을 분기 결정합니다."""
    mode = sync_data["mode"]
    if neo4j_enabled and neo4j_driver:
        if mode == "rollback_and_replay":
            await sync_neo4j_rollback_and_replay(sync_data, ontology)
        else:
            await sync_neo4j_incremental(sync_data, ontology)
    else:
        if mode == "rollback_and_replay":
            sync_virtual_graph_rollback_and_replay(sync_data, ontology)
        else:
            sync_virtual_graph_incremental(sync_data, ontology)

# 10) [동기화 메인 오케스트레이션] execute_manual_sync — [C-7 해소] 키셋 청킹 재동기화
def _neo4j_chunk_hook_factory(table_name: str):
    """[저장소 중립 §4] Neo4j 병행 타깃 청크 훅 — 기존 Cypher 빌더 인터페이스 보존.

    PG materialize와 같은 청크 단위로 Cypher MERGE를 동승시킨다(무제한 로드 없음).
    neo4j 비활성 시 None을 반환하는 게이트는 호출부가 담당.
    """
    ontology_v1 = load_ontology_mapping()

    def hook(chunk_rows):
        queries = []
        for r in chunk_rows:
            event_mock = create_light_event_mock("EDIT", table_name, r)
            queries.extend(build_queries_for_event(event_mock, ontology_v1))
        if not queries:
            return
        with neo4j_driver.session() as session:
            def execute_tx(tx):
                for cypher, params in queries:
                    tx.run(cypher, **params)
            session.execute_write(execute_tx)
    return hook


async def execute_manual_sync(table_name: str, row_ids: list[str]) -> dict:
    """수동 재동기화 메인 프로세스 — PG 엣지 스토어 1차 타깃, 테이블별 키셋 청킹.

    [C-7 해소] 구 경로의 ①무제한 로드 ②무제한 items 브로드캐스트 ③수십만 행 단일 커밋을
    모두 제거: resync_table이 1000행 keyset 청크로 로드→materialize→스탬프→커밋을 반복하고,
    통지는 테이블당 batch_refresh_required 1건(기존 WS 계약 재사용)으로 강등한다.
    무거운 동기 구간은 to_thread로 이벤트 루프에서 격리한다.
    """
    from database.database import SessionLocal, engine
    from database.models import ensure_graph_tables, DYNAMIC_TABLES
    import graph_materializer

    logger.info(
        f"[GraphSync Server] ==================== 수동 동기화 시작 "
        f"(Table: {table_name}, Request Row Count: {len(row_ids) if row_ids else 'All'}) ===================="
    )
    if row_ids:
        logger.info(f"[GraphSync Server] 요청된 로우 ID 목록: {format_id_list(row_ids)}")

    try:
        ensure_graph_tables(engine)
    except Exception as e:
        logger.error(f"[GraphSync Server] ensure_graph_tables failed: {e}")

    mappings = _load_graph_mappings()

    if table_name and table_name != "all":
        if table_name not in DYNAMIC_TABLES:
            raise HTTPException(status_code=400, detail=f"유효하지 않은 테이블 이름입니다: {table_name}")
        if table_name not in mappings:
            return {
                "status": "success", "mode": "no_mapping", "synced_count": 0, "deleted_count": 0,
                "message": f"'{table_name}' 테이블에 온톨로지 매핑이 없어 동기화할 대상이 없습니다.",
            }
        targets = [table_name]
    else:
        targets = [t for t in sorted(mappings.keys()) if t in DYNAMIC_TABLES]
        if not targets:
            return {
                "status": "success", "mode": "no_mapping", "synced_count": 0, "deleted_count": 0,
                "message": "온톨로지 매핑이 선언된 테이블이 없습니다.",
            }

    use_neo4j = bool(neo4j_enabled and neo4j_driver)
    target_db_name = "PG 엣지 스토어" + (" + Neo4j 병행" if use_neo4j else "")
    logger.info(f"[GraphSync Server] 대상 저장소: {target_db_name} | 대상 테이블: {targets}")

    def run_sync():
        db = SessionLocal()
        results = {}
        try:
            for t in targets:
                hook = _neo4j_chunk_hook_factory(t) if use_neo4j else None
                t0 = time.monotonic()
                stats = graph_materializer.resync_table(
                    db, t, mappings, row_ids=(row_ids or None), chunk_hook=hook
                )
                stats["exec_ms"] = (time.monotonic() - t0) * 1000.0
                results[t] = stats
            return results
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    try:
        results = await asyncio.to_thread(run_sync)
    except Exception as e:
        logger.error(f"[GraphSync Server] Background manual sync failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    total_rows = 0
    for t, stats in results.items():
        total_rows += stats["rows"]
        logger.info(
            f"[GraphLatency] resync table={t} chunks={stats['chunks']} rows={stats['rows']} "
            f"nodes={stats['nodes']} edges={stats['edges']} exec_ms={stats['exec_ms']:.0f}"
        )
        # [C-7 ②] 무제한 items 브로드캐스트 제거 — 테이블당 refresh 1건(기존 계약 재사용).
        if stats["rows"] > 0:
            await post_event_async("/internal/events/broadcast", {
                "event": "batch_refresh_required",
                "table_name": t,
                "change_count": stats["rows"],
            })

    logger.info(
        f"[GraphSync Server] ==================== 수동 동기화 성공 완료 "
        f"(Mode: chunked_resync, Synced: {total_rows}개) ===================="
    )
    return {
        "status": "success",
        "mode": "chunked_resync",
        "synced_count": total_rows,
        "deleted_count": 0,
        "tables": {t: {k: v for k, v in s.items() if k != "exec_ms"} for t, s in results.items()},
    }

# 1) [서버부] handle_manual_sync API 및 락 래핑
sync_lock = asyncio.Lock()

@app.post("/sync")
async def handle_manual_sync(req: GraphSyncRequest):
    """수동 그래프 동기화 위임 API (백그라운드 비동기 태스크 즉시 전환 + 동시성 뮤텍스 락)"""
    async def locked_sync_task():
        async with sync_lock:
            try:
                await execute_manual_sync(req.table_name, req.row_ids or [])
            except Exception as e:
                logger.error(f"[GraphSync Server] Locked background sync task failed: {e}")
                
    asyncio.create_task(locked_sync_task())
    return {
        "status": "accepted", 
        "message": "그래프 동기화 연산이 백그라운드에서 기동되었습니다. 완료 시 화면이 자동으로 동기화됩니다."
    }

@app.on_event("startup")
async def startup_event():
    try:
        from database import crud, models
        new_config = crud.load_table_config()
        if new_config:
            models.init_dynamic_models(new_config)
            crud.TABLE_CONFIG.clear()
            crud.TABLE_CONFIG.update(new_config)
        logger.info("[GraphSync Worker Server] Dynamic models pre-initialized successfully.")
    except Exception as e:
        logger.error(f"[GraphSync Worker Server] Failed to pre-init dynamic models: {e}")

    # [Ontology G1] 그래프 시스템 테이블 보장 + PG materializer 루프 기동(outbox 증분 소비)
    try:
        from database.database import engine
        from database.models import ensure_graph_tables
        ensure_graph_tables(engine)
    except Exception as e:
        logger.error(f"[GraphSync Worker Server] ensure_graph_tables failed at startup: {e}")

    if os.getenv("GRAPH_MATERIALIZER_ENABLED", "true").lower() == "true":
        asyncio.create_task(run_graph_materializer_loop())
        logger.info("[GraphSync Worker Server] PG materializer loop task started.")
    else:
        logger.info("[GraphSync Worker Server] PG materializer loop disabled by env.")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("GRAPH_SYNC_PORT", "8090"))
    logger.info(f"Starting GraphSync Worker Service on port {port}...")
    uvicorn.run("graph_sync_worker:app", host="127.0.0.1", port=port, log_level="info")
