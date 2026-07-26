import os
import sys
import asyncio

# Add server directory to path
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(script_dir)

# Setup Unified Logger
from utils.logger import get_process_logger
logger = get_process_logger("Chain", "chain_worker.log")

from database.database import SessionLocal, engine
from database import models
from chain_ingestion_worker import start_chain_ingestion_worker

# Initialize dynamic database models
try:
    import json
    import paths  # single override point (ASSY_DATA_ROOT)
    config_path = paths.config_path("table_config.json")
    with open(config_path, "r", encoding="utf-8") as f:
        table_config = json.load(f)
    models.init_dynamic_models(table_config)
    try:
        models.sync_dynamic_tables_schema(engine)
        logger.info("Dynamic database models and schema sync completed.")
    except Exception as e:
        logger.error(f"Failed to sync dynamic tables schema: {e}")
except Exception as e:
    logger.error(f"Failed to load table_config or init dynamic models: {e}")

async def main():
    logger.info("=" * 60)
    logger.info(" Starting Standalone Chained Ingestion Worker Process...")
    logger.info("=" * 60)
    
    # [최적화] table_config.json의 동적 스키마 실시간 변경을 감시하는 config watcher 시작 (데몬이므로 engine=None 전달)
    config_watcher = None
    try:
        from database.config_watcher import start_config_watcher
        config_watcher = start_config_watcher(None)
    except Exception as e:
        logger.error(f"Failed to start config watcher: {e}")
    
    try:
        await start_chain_ingestion_worker(SessionLocal)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received.")
    except Exception as e:
        logger.error(f"Exception occurred: {e}")
    finally:
        if config_watcher:
            config_watcher.stop()
            config_watcher.join()
        logger.info("Process stopped.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped via keyboard interrupt.")
