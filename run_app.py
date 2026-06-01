import sys
import os
import subprocess
import time

def main():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    server_dir = os.path.join(root_dir, "server")
    
    # Use the current python executable (guarantees the active conda environment is used!)
    python_exe = sys.executable
    
    print("=" * 60)
    print(" Starting AssyManager Enterprise (Backend + Client)...")
    print(f" Python Executable: {python_exe}")
    print("=" * 60)
    
    # 1. Start FastAPI server (run without --reload for robust process cleanup)
    server_cmd = [python_exe, "-m", "uvicorn", "main:app", "--port", "8080"]
    print(f"[Launcher] Starting Backend Server: {' '.join(server_cmd)}")
    
    # Start the server process
    server_process = subprocess.Popen(
        server_cmd,
        cwd=server_dir,
    )
    
    # 2. Wait 2 seconds for server to initialize
    print("[Launcher] Waiting for server to initialize...")
    time.sleep(2.0)
    
    # 3. Start PySide6 Desktop wrapper
    client_cmd = [python_exe, os.path.join(root_dir, "client", "desktop_wrapper.py")]
    print(f"[Launcher] Starting Desktop Client: {' '.join(client_cmd)}")
    
    try:
        # Run the client and wait for it to close
        client_process = subprocess.Popen(client_cmd, cwd=root_dir)
        client_process.wait()
        print("[Launcher] Desktop Client window closed.")
    except KeyboardInterrupt:
        print("[Launcher] Keyboard interrupt received.")
    finally:
        # 4. Clean up the backend server process
        print("[Launcher] Stopping Backend Server...")
        try:
            server_process.terminate()
            server_process.wait(timeout=3.0)
            print("[Launcher] Backend Server stopped successfully.")
        except Exception as e:
            print(f"[Launcher] Error stopping server: {e}")
            try:
                server_process.kill()
                print("[Launcher] Backend Server force-killed.")
            except Exception:
                pass
                
    print("=" * 60)
    print(" AssyManager has stopped.")
    print("=" * 60)

if __name__ == "__main__":
    main()
