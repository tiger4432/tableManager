import os
import json

def setup_workspace():
    # [경로 보정] scripts 폴더로 이동됨에 따라 상위 폴더(server/)를 기준으로 base_dir 설정
    current_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = os.path.abspath(os.path.join(current_dir, ".."))
    
    config_path = os.path.join(base_dir, "config", "table_config.json")
    workspace_root = os.path.join(base_dir, "ingestion_workspace")

    if not os.path.exists(config_path):
        print(f"Error: Table config not found at {config_path}")
        return

    with open(config_path, "r", encoding="utf-8") as f:
        table_config = json.load(f)

    print(f"Initializing ingestion workspace at {workspace_root}...")

    subdirs = ["config", "scripts", "raws", "archives"]

    for table_name in table_config.keys():
        table_dir = os.path.join(workspace_root, table_name)
        print(f"Creating folders for table: {table_name}")
        
        for sub in subdirs:
            path = os.path.join(table_dir, sub)
            os.makedirs(path, exist_ok=True)
            print(f"  - {sub}/")

    print("\nWorkspace setup complete.")
    print("Next steps: Place your config.json in the respective 'config/' folders.")

if __name__ == "__main__":
    setup_workspace()
