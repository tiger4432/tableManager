import os
import sys
import asyncio

# Add server directory to path
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(script_dir)

from database.database import SessionLocal
from database import models
from graph_sync_worker import start_graph_sync_worker

# Initialize dynamic database models
try:
    import json
    config_path = os.path.join(script_dir, "config", "table_config.json")
    with open(config_path, "r", encoding="utf-8") as f:
        table_config = json.load(f)
    models.init_dynamic_models(table_config)
    print("[Graph Sync Worker] Dynamic database models initialized successfully.")
except Exception as e:
    print(f"[Graph Sync Worker] Failed to load table_config or init dynamic models: {e}")

async def main():
    print("=" * 60)
    print(" Starting Standalone Graph DB Sync Worker Process...")
    print("=" * 60)
    
    try:
        await start_graph_sync_worker(SessionLocal)
    except KeyboardInterrupt:
        print("[Graph Sync Worker] Keyboard interrupt received.")
    except Exception as e:
        print(f"[Graph Sync Worker] Exception occurred: {e}")
    finally:
        print("[Graph Sync Worker] Process stopped.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("[Graph Sync Worker] Stopped via keyboard interrupt.")
