import os
import sys
import asyncio

# Add server directory to path
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(script_dir)

from database.database import SessionLocal, engine
from database import models
from chain_ingestion_worker import start_chain_ingestion_worker

# Initialize dynamic database models
try:
    import json
    config_path = os.path.join(script_dir, "config", "table_config.json")
    with open(config_path, "r", encoding="utf-8") as f:
        table_config = json.load(f)
    models.init_dynamic_models(table_config)
    try:
        models.sync_dynamic_tables_schema(engine)
        print("[Chain Ingestion Worker] Dynamic database models and schema sync completed.")
    except Exception as e:
        print(f"[Chain Ingestion Worker] Failed to sync dynamic tables schema: {e}")
except Exception as e:
    print(f"[Chain Ingestion Worker] Failed to load table_config or init dynamic models: {e}")

async def main():
    print("=" * 60)
    print(" Starting Standalone Chained Ingestion Worker Process...")
    print("=" * 60)
    
    # [최적화] table_config.json의 동적 스키마 실시간 변경을 감시하는 config watcher 시작 (데몬이므로 engine=None 전달)
    config_watcher = None
    try:
        from database.config_watcher import start_config_watcher
        config_watcher = start_config_watcher(None)
    except Exception as e:
        print(f"[Chain Ingestion Worker] Failed to start config watcher: {e}")
    
    try:
        await start_chain_ingestion_worker(SessionLocal)
    except KeyboardInterrupt:
        print("[Chain Ingestion Worker] Keyboard interrupt received.")
    except Exception as e:
        print(f"[Chain Ingestion Worker] Exception occurred: {e}")
    finally:
        if config_watcher:
            config_watcher.stop()
            config_watcher.join()
        print("[Chain Ingestion Worker] Process stopped.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("[Chain Ingestion Worker] Stopped via keyboard interrupt.")
