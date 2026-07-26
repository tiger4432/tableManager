"""Universal Transfer Plan(M2) 엔진용 인덱스 셋업 (멱등 — IF NOT EXISTS).

가용 엔진의 진입 필터는 전부 (lot, slot) 동치다 — 1,000만 행 규모에서 풀스캔을 막기 위해
DT 원천·계획 저장소에 복합 인덱스를 보장한다.
- dt_log: 테이프 identity(tape_lot, tape_slot) = total/origin 조회의 진입점.
          (core_lot, core_slot)은 fail 투영 대상 코어 역조회·계보 질의용.
- dt_map: 영역 귀속 강등 경로 진입점.
- transfer_plan*: 계획 로드·검증(plan_id)과 페인팅 group-by 진입점.
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
    ("idx_transfer_plan_stage", "transfer_plan", "(stage)"),
    ("idx_transfer_plan_doe_plan", "transfer_plan_doe", "(plan_id)"),
    ("idx_transfer_plan_map_plan", "transfer_plan_map", "(plan_id)"),
    # S3: 층 배정은 doe_key(= plan_id|doe_value) 접두 조회가 진입점
    ("idx_transfer_plan_doe_layer_doe", "transfer_plan_doe_layer", "(doe_key)"),
    # ②: 소스 사용 영역은 (plan_id, source_lot, source_slot) 캔버스 단위 조회가 진입점
    #     (테이블은 모델 재설계 대기로 보류 — 적용 시 자동 생성된다)
    ("idx_transfer_plan_region_plan_src", "transfer_plan_source_region",
     "(plan_id, source_lot, source_slot)"),
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
