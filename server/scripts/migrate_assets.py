"""
migrate_assets.py
다른 서버의 구 버전 'config' 및 'ingestion_workspace'를 현재 서버로 이관하는 마이그레이션 유틸리티.

- 사용법: python server/scripts/migrate_assets.py --source <이전_서버_루트_경로>
- 특징: 
  1. 기존 로컬 데이터를 .bak 폴더로 자동 백업 (안전성)
  2. ingestion_workspace 내의 'archives' 폴더는 제외 (사용자 요청)
  3. table_config.json 및 raws, scripts, config 폴더 이관
"""

import os
import shutil
import argparse
from datetime import datetime
from pathlib import Path

def backup_existing(target_path: Path):
    """기존 폴더가 있으면 .bak_타임스탬프 형식으로 백업합니다."""
    if target_path.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        bak_name = f"{target_path.name}.bak_{timestamp}"
        bak_path = target_path.parent / bak_name
        print(f"[*] Backing up local {target_path.name} to {bak_name}...")
        shutil.move(str(target_path), str(bak_path))

def migrate_workspace(src_root: Path, dst_root: Path):
    """
    ingestion_workspace 내부를 순회하며 테이블별 데이터를 이관합니다.
    'archives' 폴더는 제외합니다.
    """
    if not src_root.exists():
        print(f"[!] Source workspace not found at {src_root}")
        return

    dst_root.mkdir(parents=True, exist_ok=True)
    
    for table_dir in src_root.iterdir():
        if not table_dir.is_dir():
            continue
            
        table_name = table_dir.name
        dst_table_path = dst_root / table_name
        dst_table_path.mkdir(exist_ok=True)
        
        print(f"[*] Migrating table: {table_name}")
        
        for sub in table_dir.iterdir():
            # 사용자의 요청에 따라 archives 폴더는 건너뜀
            if sub.name == "archives" and sub.is_dir():
                print(f"    - Skipping 'archives' for {table_name}")
                continue
                
            dst_sub = dst_table_path / sub.name
            if sub.is_dir():
                # 폴더 병합 복사
                shutil.copytree(str(sub), str(dst_sub), dirs_exist_ok=True)
            else:
                shutil.copy2(str(sub), str(dst_sub))

def main():
    parser = argparse.ArgumentParser(description="AssyManager Server Asset Migrator")
    parser.add_argument("--source", required=True, help="Path to the source server root directory")
    args = parser.parse_args()

    src_server = Path(args.source)
    dst_server = Path(__file__).parent.parent # server/

    # 1. 경로 정의
    src_config = src_server / "config"
    src_workspace = src_server / "ingestion_workspace"
    
    dst_config = dst_server / "config"
    dst_workspace = dst_server / "ingestion_workspace"

    print(f"=== AssyManager Asset Migration ===")
    print(f"Source: {src_server}")
    print(f"Target: {dst_server}")
    print("-" * 40)

    if not src_config.exists() and not src_workspace.exists():
        print("[!] Fatal: Source directory does not appear to be an AssyManager server (missing config/workspace).")
        return

    # 2. 백업 수행
    backup_existing(dst_config)
    backup_existing(dst_workspace)

    # 3. 마이그레이션 수행
    print("[1/2] Migrating config assets...")
    if src_config.exists():
        dst_config.mkdir(parents=True, exist_ok=True)
        shutil.copytree(str(src_config), str(dst_config), dirs_exist_ok=True)
        print("    - Table configs migrated.")
    else:
        print("    - No config found in source.")

    print("[2/2] Migrating ingestion workspace (skipping archives)...")
    migrate_workspace(src_workspace, dst_workspace)

    print("-" * 40)
    print("[*] Migration completed successfully!")
    print(f"[*] Note: archives folders were skipped as requested.")

if __name__ == "__main__":
    main()
