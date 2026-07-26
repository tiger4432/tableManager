"""본딩 실험계획(M1) 집계 API용 인덱스 셋업 (멱등 — IF NOT EXISTS).

core-summary 집계는 (lot, slot) 동치 필터가 전 쿼리의 진입점이다 — 1,000만 행 규모에서
풀스캔을 막기 위해 역할 소스 테이블들에 복합 인덱스를 보장한다.
맵 메타 조회는 (target_table, map_id) 동치 필터.

실행: conda run -n assy_manager python server/scripts/setup_bonding_plan_indexes.py
(운영 config에서 역할 바인딩 테이블명이 다르면 아래 목록을 그에 맞게 조정해 실행)
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import text
from database.database import engine

INDEXES = [
    ("idx_core_defect_map_lot_slot", "core_defect_map", "(lot, slot)"),
    ("idx_eds_fail_map_lot_slot", "eds_fail_map", "(lot, slot)"),
    ("idx_wafer_process_lot_slot", "wafer_process", "(lot, slot)"),
    ("idx_bonding_log_core_lot_slot", "bonding_log", "(core_lot, core_slot)"),
    ("idx_wafer_map_metadata_target_map", "wafer_map_metadata", "(target_table, map_id)"),
]


def main():
    with engine.connect() as conn:
        for name, table, cols in INDEXES:
            exists = conn.execute(text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name=:t"
            ), {"t": table}).fetchone()
            if not exists:
                print(f"[skip] table '{table}' not found — index {name} skipped")
                continue
            try:
                conn.execute(text(f"CREATE INDEX IF NOT EXISTS {name} ON {table} {cols}"))
                conn.commit()
                print(f"[ok] {name} ON {table} {cols}")
            except Exception as e:
                conn.rollback()
                print(f"[fail] {name}: {e}")


if __name__ == "__main__":
    main()
