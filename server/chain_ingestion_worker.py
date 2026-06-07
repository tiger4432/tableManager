import asyncio
import json
import os
import logging
import importlib
import uuid

# Logger setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ChainIngestionWorker")

RULES_PATH = os.path.join(os.path.dirname(__file__), "config", "chain_rules.json")

def load_chain_rules():
    if not os.path.exists(RULES_PATH):
        logger.warning(f"Chain rules configuration file not found at {RULES_PATH}. Using empty rules.")
        return []
    try:
        with open(RULES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("rules", [])
    except Exception as e:
        logger.error(f"Failed to load chain rules: {e}")
        return []

def execute_custom_mapper(module_name: str, function_name: str, db, payload):
    """
    Dynamically imports a python mapper module and executes the mapping function.
    """
    try:
        module = importlib.import_module(module_name)
        mapper_func = getattr(module, function_name)
        return mapper_func(db, payload)
    except Exception as e:
        logger.error(f"Error executing custom mapper {module_name}.{function_name}: {e}")
        raise e

async def process_chain_event(event, db, rules):
    event_type = event.event_type
    table_name = event.table_name
    payload = event.payload
    
    # 1. Infinite loop prevention: Skip if the event was triggered by chain_ingestion itself
    if payload.get("source_name") == "chain_ingestion":
        logger.debug(f"Event {event.event_uuid} skipped to avoid infinite circular trigger loops.")
        return True

    # 2. Only trigger chain rules for CREATE/EDIT mutations
    if event_type not in ["CREATE", "EDIT"]:
        return True

    # 3. Match rules for this trigger table
    matched_rules = [r for r in rules if r.get("trigger_table") == table_name and r.get("enabled", True)]
    if not matched_rules:
        return True

    for rule in matched_rules:
        name = rule.get("name")
        target_table = rule.get("target_table")
        module_name = rule.get("mapper_module")
        func_name = rule.get("mapper_function")
        
        logger.info(f"Triggering chain rule '{name}': {table_name} -> {target_table} using {module_name}.{func_name}")
        
        try:
            # 4. Execute dynamic mapper function
            target_payload = execute_custom_mapper(module_name, func_name, db, payload)
            
            if not target_payload or not target_payload.get("updates"):
                logger.info(f"Mapper returned empty or invalid payload for rule '{name}'. Skipping.")
                continue
                
            from database import schemas, crud
            batch_data = schemas.GeneralUpdateBatch(**target_payload)
            
            # 5. Bind request context variables to identify this as a chained update
            from database.context import request_user, request_transaction_id, request_source
            token_user = request_user.set("chain_worker")
            token_tx = request_transaction_id.set(payload.get("transaction_id") or str(uuid.uuid4()))
            token_src = request_source.set("chain_ingestion")
            
            try:
                # 6. Perform chained ingestion
                crud.apply_batch_updates(db, target_table, batch_data)
                logger.info(f"Successfully processed chained ingestion to '{target_table}' for rule '{name}'.")
            finally:
                request_user.reset(token_user)
                request_transaction_id.reset(token_tx)
                request_source.reset(token_src)
                
        except Exception as e:
            logger.error(f"Failed to process chain rule '{name}' on event {event.event_uuid}: {e}")
            return False
            
    return True

async def start_chain_ingestion_worker(db_session_factory):
    logger.info("Initializing Chained Ingestion Worker Daemon...")
    rules = load_chain_rules()
    logger.info(f"Loaded {len(rules)} active chain ingestion rules.")
    
    # Python path dynamic setup to support loading from server/mappers package
    import sys
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if script_dir not in sys.path:
        sys.path.append(script_dir)
        
    while True:
        try:
            db = db_session_factory()
            try:
                from database.models import DatabaseOutbox
                # Query oldest unprocessed events for chain ingestion
                pending_events = db.query(DatabaseOutbox).filter(
                    DatabaseOutbox.processed_chain == False
                ).order_by(DatabaseOutbox.id.asc()).limit(50).all()
                
                if not pending_events:
                    await asyncio.sleep(1)
                    continue
                    
                for event in pending_events:
                    success = await process_chain_event(event, db, rules)
                    
                    if success:
                        # Mark this event as processed for the chain worker
                        event.processed_chain = True
                    else:
                        # Event failed. Increment retry count or handle backoff
                        # Note: We rollback so we don't commit the half-failed chain, 
                        # but we can retry on next loop iteration.
                        db.rollback()
                        logger.warning(f"Chain execution failed for event {event.event_uuid}. Retrying next loop...")
                        await asyncio.sleep(2)
                        break
                        
                    db.commit()
            except Exception as e:
                db.rollback()
                logger.error(f"Error in Chain Worker execution loop: {e}")
                await asyncio.sleep(3)
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Database session setup failed in Chain Worker: {e}")
            await asyncio.sleep(5)
