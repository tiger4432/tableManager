"""Universal Transfer Plan(M2) 엔진용 인덱스 셋업 (멱등 — IF NOT EXISTS).

가용 엔진의 진입 필터는 전부 (lot, slot) 동치다 — 1,000만 행 규모에서 풀스캔을 막기 위해
DT 원천·계획 저장소에 복합 인덱스를 보장한다.
- dt_log: 테이프 identity(tape_lot, tape_slot) = total/origin 조회의 진입점.
          (core_lot, core_slot)은 fail 투영 대상 코어 역조회·계보 질의용.
- dt_map: 영역 귀속 강등 경로 진입점.
- map_doe / map_doe_source: 계획 v2의 진입점은 `(ref_table, map_key)` 동치다
  (계획 정체성 = 지금 열어 편집 중인 맵). 구 `transfer_plan*` 인덱스는 테이블 폐기와 함께
  제거했다 — 물리 DROP은 총괄이 별도로 수행한다.
- 계획 맵의 페인팅 값 group-by는 **대상 맵 자신**(bonding_map/dt_map)의 맵 키 인덱스를
  그대로 탄다(아래 idx_*_base / idx_dt_map_lot_slot).
M1 인덱스(core_defect_map/eds_fail_map/wafer_process/bonding_log/wafer_map_metadata)는
setup_bonding_plan_indexes.py가 담당한다 — 중복 선언하지 않는다.

실행: conda run -n assy_manager python server/scripts/setup_transfer_plan_indexes.py
(운영 config에서 역할 바인딩 테이블명이 다르면 아래 목록을 그에 맞게 조정해 실행)
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import text
from database.database import engine

INDEXES = [
    ("idx_dt_log_tape_lot_slot", "dt_log", "(tape_lot, tape_slot)"),
    ("idx_dt_log_core_lot_slot", "dt_log", "(core_lot, core_slot)"),
    ("idx_dt_map_lot_slot", "dt_map", "(lot, slot)"),
    # v2: DOE·자재 묶음은 계획 맵 정체성 (ref_table, map_key) 동치가 진입점
    ("idx_map_doe_ref_map", "map_doe", "(ref_table, map_key)"),
    ("idx_map_doe_source_ref_map", "map_doe_source", "(ref_table, map_key)"),
    # ②: 소스 사용 영역 (휴면 — 테이블 미적용 시 자동 skip)
    ("idx_map_source_region_ref_map_src", "map_source_region",
     "(ref_table, map_key, source_lot, source_slot)"),
    # [QA S1] 오버레이가 맵 키 컬럼으로 진입한다 — 인덱스가 없으면 175만 행 풀스캔(214ms 실측).
    # 요청당 소스 8종까지 가능하므로 왕복마다 반복된다.
    ("idx_bonding_map_base", "bonding_map", "(base)"),
    ("idx_sample_map_base", "sample_map", "(base)"),
]


def main():
    with engine.connect() as conn:
        for name, table, cols in INDEXES:
            # [교훈] DDL 전 존재 게이트 + 실패 시 즉시 rollback (트랜잭션 오염 방지)
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
