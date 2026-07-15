import asyncio
import json
import os
import logging
import select
import time
from datetime import datetime

# Setup Unified Logger
from utils.logger import get_process_logger
logger = get_process_logger("GraphSync", "graph_sync.log")

def blocking_wait(db_session_factory, channel, timeout):
    db = db_session_factory()
    try:
        engine = db.bind or db.get_bind()
        if engine and engine.dialect.name == "postgresql":
            connection = engine.raw_connection()
            # autocommit 모드로 변경하여 LISTEN 명령이 즉시 반영되게 함
            connection.set_isolation_level(0)
            cursor = connection.cursor()
            cursor.execute(f"LISTEN {channel};")
            
            # select를 활용하여 소켓에 데이터가 들어올 때까지 대기 (CPU 부하 0%)
            r, w, x = select.select([connection], [], [], timeout)
            if r:
                connection.poll()
                while connection.notifies:
                    connection.notifies.pop()
                cursor.close()
                connection.close()
                return True
            cursor.close()
            connection.close()
            return False
    except Exception:
        # DB 연결 실패, SQLite 사용 시 등 예외가 발생하면 Fallback 처리
        pass
    finally:
        db.close()
        
    time.sleep(timeout)
    return False

async def wait_for_notification(db_session_factory, channel="outbox_event", timeout=1.0):
    """PostgreSQL LISTEN/NOTIFY 기반으로 대기하며, SQLite 환경 등에서는 단순 sleep으로 폴백합니다."""
    return await asyncio.to_thread(blocking_wait, db_session_factory, channel, timeout)

ONTOLOGY_PATH = os.path.join(os.path.dirname(__file__), "config", "ontology_mapping.json")

def load_ontology_mapping():
    if not os.path.exists(ONTOLOGY_PATH):
        logger.warning(f"Ontology mapping file not found at {ONTOLOGY_PATH}. Using default schema.")
        return {}
    try:
        with open(ONTOLOGY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load ontology mapping: {e}")
        return {}

# Lazy load Neo4j Driver
neo4j_driver = None
neo4j_enabled = os.getenv("NEO4J_ENABLED", "false").lower() == "true"

if neo4j_enabled:
    try:
        from neo4j import GraphDatabase
        neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        neo4j_user = os.getenv("NEO4J_USER", "neo4j")
        neo4j_password = os.getenv("NEO4J_PASSWORD", "admin")
        neo4j_driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_password))
        logger.info(f"Initialized real Neo4j driver connected to {neo4j_uri}")
    except ImportError:
        logger.warning("neo4j driver not installed. Defaulting to Mock Mode.")
        neo4j_enabled = False
    except Exception as e:
        logger.error(f"Failed to connect to Neo4j host: {e}. Defaulting to Mock Mode.")
        neo4j_enabled = False
else:
    logger.info("Neo4j is disabled (NEO4J_ENABLED=false). Running in Mock Mode.")


def build_cypher_create(table_name, payload, ontology):
    table_cfg = ontology.get("tables", {}).get(table_name, ontology.get("default", {}))
    node_label = table_cfg.get("node_label", "Row")
    identity_prop = table_cfg.get("identity_property", "row_id")
    
    cypher = (
        f"MERGE (t:Table {{name: $table_name}})\n"
        f"MERGE (r:{node_label} {{{identity_prop}: $row_id}})\n"
        f"ON CREATE SET r.created_at = datetime($timestamp)\n"
        f"SET r.updated_at = datetime($timestamp)\n"
    )
    if payload.get("business_key"):
        cypher += f"SET r.business_key = $business_key\n"
        
    cypher += f"MERGE (r)-[:BELONGS_TO]->(t)"
    
    params = {
        "table_name": table_name,
        "row_id": payload.get("row_id"),
        "business_key": payload.get("business_key"),
        "timestamp": payload.get("timestamp")
    }
    return cypher, params


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


def build_queries_for_event(event, ontology):
    event_type = event.event_type
    table_name = event.table_name
    payload = event.payload
    
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
            #logger.info(f"Query #{idx+1} in Tx:\n{cypher}\nParameters: {json.dumps(params, default=str)}\n")
            
    return True


async def start_graph_sync_worker(db_session_factory):
    logger.info("Initializing Graph Database Sync Worker Daemon...")
    ontology = load_ontology_mapping()
    from collections import defaultdict
    
    while True:
        try:
            db = db_session_factory()
            try:
                from database.models import DatabaseOutbox
                pending_events = db.query(DatabaseOutbox).filter(
                    DatabaseOutbox.status == "PENDING"
                ).order_by(DatabaseOutbox.id.asc()).limit(200).all()
                
                if not pending_events:
                    await wait_for_notification(db_session_factory, "outbox_event", 1.0)
                    continue
                
                # Group pending events by transaction_id to process them atomically
                groups = defaultdict(list)
                group_order = []
                
                for event in pending_events:
                    tx_id = event.payload.get("transaction_id")
                    if not tx_id:
                        tx_id = f"single_{event.event_uuid}"
                    if tx_id not in groups:
                        group_order.append(tx_id)
                    groups[tx_id].append(event)
                
                failed_any = False
                for tx_id in group_order:
                    events_in_tx = groups[tx_id]
                    
                    # 1. Consolidate queries for all events under this transaction
                    all_queries = []
                    for event in events_in_tx:
                        queries_for_event = build_queries_for_event(event, ontology)
                        all_queries.extend(queries_for_event)
                    
                    # 2. Execute unified Neo4j transaction write
                    success = await execute_batch_queries(all_queries, tx_id)
                    
                    # 3. Update outbox statuses
                    if success:
                        for event in events_in_tx:
                            event.status = "DISPATCHED"
                            event.processed_at = datetime.now()
                    else:
                        for event in events_in_tx:
                            event.retry_count += 1
                            if event.retry_count >= 3:
                                event.status = "FAILED"
                                logger.error(f"Event {event.event_uuid} in Tx {tx_id} failed permanently.")
                        
                        db.rollback()
                        logger.warning(f"Transaction group commit failed for {tx_id}. Retrying next loop...")
                        failed_any = True
                        await asyncio.sleep(2)
                        break
                        
                    db.commit()
                
                if failed_any:
                    await asyncio.sleep(1)
                    
            except Exception as e:
                db.rollback()
                logger.error(f"Error in Sync Worker execution loop: {e}")
                await asyncio.sleep(3)
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Database session setup failed in Sync Worker: {e}")
            await asyncio.sleep(5)
