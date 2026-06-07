import json
import sys
import os
import time

# Add server to path
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "server"))

from websockets.sync.client import connect

def main():
    url = "ws://127.0.0.1:8080/ws"
    print(f"Connecting to {url}...")
    try:
        with connect(url, open_timeout=5.0) as ws:
            print("Connected! Listening for messages (timeout 15s)...")
            start_time = time.time()
            while time.time() - start_time < 15:
                try:
                    message = ws.recv(timeout=1.0)
                    print(f"Received message: {message[:200]}...")
                    data = json.loads(message)
                    print(f"Parsed Event: {data.get('event')}, Table: {data.get('table_name')}")
                    print(f"Created Logs: {data.get('created_logs')}")
                except TimeoutError:
                    continue
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
