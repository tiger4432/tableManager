import sys
import os
import subprocess
import time
import signal

def log_launcher(msg, level="INFO"):
    RESET = "\033[0m"
    BOLD = "\033[1m"
    WHITE = "\033[97m"
    
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    prefix = f"{WHITE}{BOLD}[Launcher]{RESET}"
    print(f"{prefix} [{timestamp}] {level} - {msg}")

def main():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    server_dir = os.path.join(root_dir, "server")
    
    # Use the current python executable (guarantees the active conda environment is used)
    python_exe = sys.executable
    
    print("=" * 60)
    print(" Starting AssyManager Enterprise in Decoupled Process Mode...")
    print(f" Python Executable: {python_exe}")
    print("=" * 60)
    
    processes = []
    
    # Helper to spawn subprocess
    def spawn_process(name, cmd, cwd, env=None):
        log_launcher(f"Starting {name}: {' '.join(cmd)}")
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        
        creationflags = 0
        if os.name == 'nt':
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

        proc = subprocess.Popen(cmd, cwd=cwd, env=merged_env, creationflags=creationflags)
        processes.append((name, proc))
        return proc

    # 1. Start FastAPI server with DECOUPLED=True env var
    server_env = {"DECOUPLED": "True"}
    server_cmd = [python_exe, "-m", "uvicorn", "main:app", "--port", "8080"]
    if "--reload" in sys.argv:
        server_cmd.extend(["--reload", "--reload-dir", server_dir])
    spawn_process("Backend FastAPI Server", server_cmd, server_dir, env=server_env)
    
    # Wait for web server to initialize
    log_launcher("Waiting for server to initialize...")
    time.sleep(2.0)
    
    # 2. Start File Ingestion Watcher
    watcher_cmd = [python_exe, "run_watcher.py"]
    spawn_process("File Ingestion Watcher", watcher_cmd, server_dir)
    
    # 3. Start Graph DB Sync Worker
    graph_cmd = [python_exe, "run_graph_sync.py"]
    spawn_process("Graph DB Sync Worker", graph_cmd, server_dir)
    
    # 4. Start Chained Ingestion Worker
    chain_cmd = [python_exe, "run_chain_worker.py"]
    spawn_process("Chained Ingestion Worker", chain_cmd, server_dir)
    
    # 5. Start Auto Update Scheduler
    schedule_cmd = [python_exe, "run_auto_update.py"]
    spawn_process("Auto Update Scheduler", schedule_cmd, server_dir)
    
    # Check command-line arguments for server-only mode
    server_only = "--no-client" in sys.argv or "--server-only" in sys.argv
    
    # 5. Start PySide6 Desktop wrapper (if not server-only)
    desktop_process = None
    if not server_only:
        client_cmd = [python_exe, os.path.join(root_dir, "client", "desktop_wrapper.py")]
        desktop_process = spawn_process("Desktop Client UI", client_cmd, root_dir)
    
    # Graceful shutdown handler
    def shutdown_all(signum=None, frame=None):
        if signum:
            log_launcher(f"Signal {signum} received. Cleaning up all background processes...", level="WARNING")
        elif server_only:
            log_launcher("Stopping all backend server processes...")
        else:
            log_launcher("Desktop Client window closed. Cleaning up all background processes...")
            
        # Terminate all processes in reverse order
        for name, proc in reversed(processes):
            if proc.poll() is None:  # Still running
                log_launcher(f"Stopping {name}...")
                try:
                    proc.terminate()
                    proc.wait(timeout=3.0)
                    log_launcher(f"{name} stopped successfully.")
                except Exception as e:
                    log_launcher(f"Error stopping {name}: {e}. Killing process...", level="ERROR")
                    try:
                        proc.kill()
                    except:
                        pass
        print("=" * 60)
        print(" AssyManager has stopped cleanly.")
        print("=" * 60)
        sys.exit(0)

    # Register signal handler for Ctrl+C (SIGINT) and SIGTERM
    signal.signal(signal.SIGINT, shutdown_all)
    signal.signal(signal.SIGTERM, shutdown_all)
    
    try:
        if server_only:
            log_launcher("Running in Server-only mode. Press Ctrl+C to stop.")
            while True:
                time.sleep(1)
        else:
            # Wait for the desktop wrapper window to close
            desktop_process.wait()
            log_launcher("Desktop client closed.")
            shutdown_all()
    except KeyboardInterrupt:
        shutdown_all()

if __name__ == "__main__":
    main()
