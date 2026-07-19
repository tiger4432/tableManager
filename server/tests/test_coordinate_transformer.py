import pytest
from utils.coordinate_transformer import WaferMapCoordinateTransformer

def test_coordinate_transformer_roundtrip():
    # 1. 테스트 매개변수 설정
    cols = 15
    rows = 15
    start_x = -5
    start_y = -5
    
    # 다양한 회전, 단면, Y 반전 조합 테스트
    configs = [
        {"rotation": 0, "side": "front", "invert_y": False},
        {"rotation": 90, "side": "front", "invert_y": True},
        {"rotation": 180, "side": "back", "invert_y": False},
        {"rotation": 270, "side": "back", "invert_y": True},
    ]

    for conf in configs:
        transformer = WaferMapCoordinateTransformer(
            cols=cols,
            rows=rows,
            start_x=start_x,
            start_y=start_y,
            rotation=conf["rotation"],
            side=conf["side"],
            invert_y=conf["invert_y"]
        )

        # 2. 물리 칩 좌표 <-> 화면 시각 좌표 상호 변환 왕복(Roundtrip) 검증
        for xp in range(cols):
            for yp in range(rows):
                # 물리 -> 시각 -> 물리
                xv, yv = transformer.physical_to_visual(xp, yp)
                xp_rec, yp_rec = transformer.visual_to_physical(xv, yv)
                assert (xp, yp) == (xp_rec, yp_rec), f"Roundtrip failed for config {conf} at physical ({xp}, {yp})"

                # cell -> physical -> cell
                c, r = transformer.physical_to_cell(xp, yp)
                xp_cell, yp_cell = transformer.cell_to_physical(c, r)
                assert (xp, yp) == (xp_cell, yp_cell), f"Cell roundtrip failed for config {conf}"

                # 표준 좌표계(Standard Coordinates) 변환 왕복 검증
                x_std, y_std = transformer.to_standard_coords(xv, yv)
                assert (xp, yp) == (x_std, y_std), f"Standard conversion failed for config {conf}"

                xv_rec, yv_rec = transformer.from_standard_coords(x_std, y_std)
                assert (xv, yv) == (xv_rec, yv_rec), f"Standard reverse conversion failed for config {conf}"

def test_edge_classification():
    # 10x10 격자에서의 최외곽 에지 자동 분류 기능 검증
    transformer = WaferMapCoordinateTransformer(
        cols=10,
        rows=10,
        start_x=0,
        start_y=0,
        rotation=0,
        side="front",
        invert_y=False
    )

    classification = transformer.get_edge_classification()
    e1 = classification["E1"]
    e2 = classification["E2"]

    # E1과 E2는 절대 겹쳐서는 안 됨
    assert e1.isdisjoint(e2)

    # 원 내부의 셀들이 일부라도 지정되었는지 검사
    assert len(e1) > 0
    assert len(e2) > 0

    # 원 밖의 셀(예: 모서리 부분 (0,0))은 원 내부가 아니므로 E1, E2에 포함되지 않아야 함
    assert not transformer.is_inside_wafer(0, 0)
    assert (0, 0) not in e1
    assert (0, 0) not in e2
