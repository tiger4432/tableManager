import os
import sys
import json

# server 디렉토리를 path에 추가하여 database 모듈 임포트 가능하도록 설정
script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.join(script_dir, "server")
if server_dir not in sys.path:
    sys.path.append(server_dir)

try:
    from database.database import SessionLocal
    from database import models
    from sqlalchemy.orm.attributes import flag_modified
except ImportError as e:
    print(f"Error importing database modules. Make sure server modules exist: {e}")
    sys.exit(1)

def cast_value(val):
    if val is None or str(val).strip() == "":
        return None
    val_str = str(val).strip()
    try:
        if "." in val_str:
            return float(val_str)
        else:
            return int(val_str)
    except ValueError:
        # 변환 불가 시 원래 문자열 그대로 유지
        return val

def run_migration():
    config_path = os.path.join(server_dir, "config", "table_config.json")
    if not os.path.exists(config_path):
        print(f"Error: table_config.json not found at {config_path}")
        return

    print("Loading table configurations...")
    with open(config_path, "r", encoding="utf-8") as f:
        table_config = json.load(f)

    db = SessionLocal()
    total_migrated_rows = 0

    try:
        print("Starting DB migration for numeric columns in JSONB...")
        for table_name, config in table_config.items():
            col_types = config.get("column_types", {})
            number_cols = [col for col, c_type in col_types.items() if c_type == "number"]
            
            if not number_cols:
                continue

            print(f"\nScanning table '{table_name}' for columns: {number_cols}")
            
            # Fetch all rows belonging to the current table
            rows = db.query(models.DataRow).filter(models.DataRow.table_name == table_name).all()
            table_migrated_count = 0

            for row in rows:
                if not row.data:
                    continue

                modified = False
                for col in number_cols:
                    if col not in row.data:
                        continue

                    cell = row.data[col]
                    
                    # 1. cell["value"] 변환 (문자열 -> 숫자)
                    old_val = cell.get("value")
                    if old_val is not None and not isinstance(old_val, (int, float)):
                        new_val = cast_value(old_val)
                        if new_val != old_val:
                            cell["value"] = new_val
                            modified = True

                    # 2. cell["sources"] 내 각 원천 소스 value 변환
                    if "sources" in cell and isinstance(cell["sources"], dict):
                        for src_name, src_data in cell["sources"].items():
                            if isinstance(src_data, dict) and "value" in src_data:
                                old_src_val = src_data["value"]
                                if old_src_val is not None and not isinstance(old_src_val, (int, float)):
                                    new_src_val = cast_value(old_src_val)
                                    if new_src_val != old_src_val:
                                        src_data["value"] = new_src_val
                                        modified = True

                if modified:
                    # JSONB 수정 감지를 위해 flag_modified 설정 필수
                    flag_modified(row, "data")
                    table_migrated_count += 1
                    total_migrated_rows += 1

            if table_migrated_count > 0:
                print(f"  -> Migrated {table_migrated_count} rows in '{table_name}'")
            else:
                print(f"  -> No migration needed for '{table_name}'")

        if total_migrated_rows > 0:
            print(f"\nCommitting changes. Total rows migrated: {total_migrated_rows}")
            db.commit()
            print("Migration completed successfully.")
        else:
            print("\nNo database changes detected. Already up-to-date.")

    except Exception as e:
        db.rollback()
        print(f"Error occurred during migration: {e}", file=sys.stderr)
    finally:
        db.close()

if __name__ == "__main__":
    run_migration()
