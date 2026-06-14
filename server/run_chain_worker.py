import os
import sys
import asyncio

# Add server directory to path
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(script_dir)

from database.database import SessionLocal
from chain_ingestion_worker import start_chain_ingestion_worker

async def main():
    print("=" * 60)
    print(" Starting Standalone Chained Ingestion Worker Process...")
    print("=" * 60)
    
    try:
        await start_chain_ingestion_worker(SessionLocal)
    except KeyboardInterrupt:
        print("[Chain Ingestion Worker] Keyboard interrupt received.")
    except Exception as e:
        print(f"[Chain Ingestion Worker] Exception occurred: {e}")
    finally:
        print("[Chain Ingestion Worker] Process stopped.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("[Chain Ingestion Worker] Stopped via keyboard interrupt.")
