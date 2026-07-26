import os
import json

def setup_workspace():
    # Paths come from the single override point (server/paths.py, ASSY_DATA_ROOT).
    import sys
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))
    import paths

    config_path = paths.config_path("table_config.json")
    workspace_root = paths.WORKSPACE_DIR

    if not os.path.exists(config_path):
        print(f"Error: Table config not found at {config_path}")
        return

    with open(config_path, "r", encoding="utf-8") as f:
        table_config = json.load(f)

    print(f"Initializing ingestion workspace at {workspace_root}...")

    subdirs = ["config", "scripts", "raws", "archives", "auto_update"]

    for table_name in table_config.keys():
        table_dir = os.path.join(workspace_root, table_name)
        print(f"Creating folders for table: {table_name}")
        
        for sub in subdirs:
            path = os.path.join(table_dir, sub)
            os.makedirs(path, exist_ok=True)
            print(f"  - {sub}/")

    print("\nWorkspace setup complete.")
    print("Note: workspace config.json is deprecated — folder name = table name by default;")
    print("      use 'workspace_name'/'std_parse' fields in config/table_config.json instead.")

if __name__ == "__main__":
    setup_workspace()
