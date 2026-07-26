import os
import sys
import asyncio

# Add server directory to path
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(script_dir)

# Setup Unified Logger
from utils.logger import get_process_logger
logger = get_process_logger("GraphSync", "graph_sync.log")

from database.database import SessionLocal, engine
from database import models

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
    import uvicorn
    import os
    port = int(os.getenv("GRAPH_SYNC_PORT", "8090"))
    logger.info(f"Starting decoupled GraphSync HTTP service on port {port}...")
    
    def start_server():
        uvicorn.run("graph_sync_worker:app", host="127.0.0.1", port=port, log_level="info")
        
    try:
        await asyncio.to_thread(start_server)
    except Exception as e:
        logger.error(f"GraphSync worker HTTP service execution failed: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped via keyboard interrupt.")
