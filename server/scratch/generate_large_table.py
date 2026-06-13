import os
import json
import pandas as pd
import sys

# Ensure server path is available
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

def setup_large_table():
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(script_dir, "config", "table_config.json")
    
    # 1. table_config.json 읽기
    with open(config_path, "r", encoding="utf-8") as f:
        table_config = json.load(f)
        
    # 2. 100개 컬럼 정의 생성
    table_name = "large_table_100"
    cols = {
        "item_id": "string"
    }
    # col_1 ~ col_99 추가
    for i in range(1, 100):
        # 홀수는 number, 짝수는 string으로 타입 배분
        cols[f"col_{i}"] = "number" if i % 2 != 0 else "string"
        
    table_config[table_name] = {
        "business_key": "item_id",
        "column_types": cols,
        "display_columns": ["item_id"] + [f"col_{i}" for i in range(1, 100)]
    }
    
    # 3. table_config.json 저장
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(table_config, f, indent=2, ensure_ascii=False)
    print("1. Successfully updated table_config.json with 'large_table_100'.")
    
    # 4. 폴더 구조 생성
    workspace_dir = os.path.join(script_dir, "ingestion_workspace", table_name)
    raws_dir = os.path.join(workspace_dir, "raws")
    scripts_dir = os.path.join(workspace_dir, "scripts")
    
    os.makedirs(raws_dir, exist_ok=True)
    os.makedirs(os.path.join(workspace_dir, "err"), exist_ok=True)
    os.makedirs(os.path.join(workspace_dir, "archives"), exist_ok=True)
    os.makedirs(scripts_dir, exist_ok=True)
    print("2. Created ingestion workspace directory structure.")
    
    # 5. 커스텀 파서 스크립트 작성
    parser_content = """import pandas as pd
from pipeline_base import BasePipelineParser

class LargeTable100CSVParser(BasePipelineParser):
    @classmethod
    def match(cls, file_path: str) -> bool:
        return file_path.lower().endswith('.csv')
        
    def process_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        return df
"""
    parser_path = os.path.join(scripts_dir, "custom_parser.py")
    with open(parser_path, "w", encoding="utf-8") as f:
        f.write(parser_content)
    print("3. Created custom_parser.py in scripts folder.")
    
    # 6. 1000행 x 100열짜리 CSV 샘플 생성
    data = []
    for r in range(1, 1001):
        row = {"item_id": f"ITEM_{r:04d}"}
        for i in range(1, 100):
            if i % 2 != 0:
                row[f"col_{i}"] = r * 10 + i # number
            else:
                row[f"col_{i}"] = f"str_{r}_{i}" # string
        data.append(row)
        
    df = pd.DataFrame(data)
    csv_file_name = "user(kk980)_large_table_100_sample1000.csv"
    csv_path = os.path.join(raws_dir, csv_file_name)
    df.to_csv(csv_path, index=False, encoding="utf-8")
    print(f"4. Generated 1000 rows x 100 columns sample file at: {csv_path}")

    # 7. 로컬 PostgreSQL 데이터베이스에 즉시 물리 테이블 DDL 생성 반영
    from database.database import engine, Base
    from database import models
    models.init_dynamic_models(table_config)
    Base.metadata.create_all(bind=engine)
    print("5. Reflected physical table creation in PostgreSQL database.")

if __name__ == "__main__":
    setup_large_table()
