import os
import sys
import asyncio

script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(script_dir)

from utils.logger import get_process_logger
logger = get_process_logger("Ledger", "ledger.log")

from database.database import SessionLocal
from database import models
from ledger.worker import start_ledger_worker
from error_said import told

try:
    import json
    import paths  # single override point (ASSY_DATA_ROOT)
    config_path = paths.config_path("table_config.json")
    with open(config_path, "r", encoding="utf-8") as f:
        table_config = json.load(f)
    models.init_dynamic_models(table_config)
except Exception as e:
    logger.error(f"Failed to load table_config or init dynamic models: {told(e)}", exc_info=e)

async def main():
    logger.info("=" * 60)
    logger.info(" Starting Standalone Ledger Worker Process...")
    logger.info("=" * 60)

    config_watcher = None
    try:
        from database.config_watcher import start_config_watcher
        config_watcher = start_config_watcher(None)
    except Exception as e:
        logger.error(f"Failed to start config watcher: {told(e)}", exc_info=e)

    try:
        await start_ledger_worker(SessionLocal)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received.")
    except Exception as e:
        logger.error(f"Exception occurred: {told(e)}", exc_info=e)
    finally:
        if config_watcher:
            handler = getattr(config_watcher, "config_handler", None)
            if handler is not None:
                handler.cancel_pending()
            config_watcher.stop()
            config_watcher.join()
        logger.info("Process stopped.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped via keyboard interrupt.")
