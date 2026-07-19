import math
from typing import Dict, Tuple, Set, Optional

class WaferMapCoordinateTransformer:
    """
    웨이퍼 맵의 메타데이터(크기, 오프셋, 회전각, 앞/뒷면, Y축 반전)를 기반으로
    물리 좌표(Physical Coordinates)와 시각 화면 좌표(Visual Coordinates) 간의 상호 변환 및
    수학적 에지(E1/E2) 영역 분류를 수행하는 파이썬 일반화 클래스입니다.
    """

    def __init__(
        self,
        cols: int,
        rows: int,
        start_x: int = 0,
        start_y: int = 0,
        rotation: int = 0,
        side: str = "front",
        invert_y: bool = False
    ):
        """
        좌표 변환기 초기화
        
        :param cols: 물리 가로 셀 개수 (Columns)
        :param rows: 물리 세로 셀 개수 (Rows)
        :param start_x: 시작 X 오프셋 (원점 기준 최소 가로 인덱스)
        :param start_y: 시작 Y 오프셋 (원점 기준 최소 세로 인덱스)
        :param rotation: 맵 회전 각도 (0, 90, 180, 270)
        :param side: 웨이퍼 기판 단면 ("front" or "back")
        :param invert_y: Y축 상하반전 적용 여부 (기입 시 True)
        """
        self.cols = cols
        self.rows = rows
        self.start_x = start_x
        self.start_y = start_y
        self.rotation = rotation
        self.side = side.lower()
        self.invert_y = invert_y

        # 회전(90, 270) 상태에 따른 시각적(화면상) 격자 가로/세로 크기 판별
        self.is_rotated_90_or_270 = self.rotation in (90, 270)
        self.visual_cols = self.rows if self.is_rotated_90_or_270 else self.cols
        self.visual_rows = self.cols if self.is_rotated_90_or_270 else self.rows

    def cell_to_physical(self, c: int, r: int) -> Tuple[int, int]:
        """
        DOM 셀 인덱스 (c, r)를 물리 칩 좌표 (xp, yp)로 변환합니다. (getPhysicalCoords 매칭)
        """
        xp = c
        yp = r

        if self.rotation == 0:
            xp = c
            yp = r
        elif self.rotation == 90:
            xp = r
            yp = (self.visual_cols - 1) - c
        elif self.rotation == 180:
            xp = (self.visual_cols - 1) - c
            yp = (self.visual_rows - 1) - r
        elif self.rotation == 270:
            xp = (self.visual_rows - 1) - r
            yp = c

        return xp, yp

    def physical_to_cell(self, xp: int, yp: int) -> Tuple[int, int]:
        """
        물리 칩 좌표 (xp, yp)를 DOM 셀 인덱스 (c, r)로 역변환합니다.
        """
        c = xp
        r = yp

        if self.rotation == 0:
            c = xp
            r = yp
        elif self.rotation == 90:
            c = (self.visual_cols - 1) - yp
            r = xp
        elif self.rotation == 180:
            c = (self.visual_cols - 1) - xp
            r = (self.visual_rows - 1) - yp
        elif self.rotation == 270:
            c = yp
            r = (self.visual_rows - 1) - xp

        return c, r

    def cell_to_visual(self, c: int, r: int) -> Tuple[int, int]:
        """
        DOM 셀 인덱스 (c, r)를 화면 시각 좌표 (xv, yv)로 변환합니다. (getVisualCoords 매칭)
        """
        c_screen = c
        r_screen = r

        # 백면(Back Side)인 경우 CSS 미러링 효과와 매칭되도록 보정
        if self.side == "back":
            if self.is_rotated_90_or_270:
                r_screen = (self.visual_rows - 1) - r
            else:
                c_screen = (self.visual_cols - 1) - c

        xv = c_screen + self.start_x
        yv = r_screen

        if self.invert_y:
            yv = (self.visual_rows - 1) - yv
        yv = yv + self.start_y

        return xv, yv

    def visual_to_cell(self, xv: int, yv: int) -> Tuple[int, int]:
        """
        화면 시각 좌표 (xv, yv)를 DOM 셀 인덱스 (c, r)로 역변환합니다.
        """
        c_screen = xv - self.start_x
        r_screen = yv - self.start_y

        if self.invert_y:
            r_screen = (self.visual_rows - 1) - r_screen

        c = c_screen
        r = r_screen

        if self.side == "back":
            if self.is_rotated_90_or_270:
                r = (self.visual_rows - 1) - r_screen
            else:
                c = (self.visual_cols - 1) - c_screen

        return c, r

    def physical_to_visual(self, xp: int, yp: int) -> Tuple[int, int]:
        """
        물리 칩 좌표 (xp, yp)를 바로 화면 시각 좌표 (xv, yv)로 일괄 변환합니다.
        """
        c, r = self.physical_to_cell(xp, yp)
        return self.cell_to_visual(c, r)

    def visual_to_physical(self, xv: int, yv: int) -> Tuple[int, int]:
        """
        화면 시각 좌표 (xv, yv)를 바로 물리 칩 좌표 (xp, yp)로 일괄 역변환합니다.
        """
        c, r = self.visual_to_cell(xv, yv)
        return self.cell_to_physical(c, r)

    def to_standard_coords(self, xv: int, yv: int) -> Tuple[int, int]:
        """
        현재 구성 인프라 하의 시각 좌표 (xv, yv)를 표준 좌표계(Front, start_x=0, start_y=0, rot=0, invert_y=False) 좌표로 변환합니다.
        표준 좌표계의 시각 좌표는 기하학적 정렬 상 물리 좌표 (xp, yp)와 완벽히 1대1 일치합니다.
        """
        return self.visual_to_physical(xv, yv)

    def from_standard_coords(self, x_std: int, y_std: int) -> Tuple[int, int]:
        """
        표준 좌표계(Front, start_x=0, start_y=0, rot=0, invert_y=False)의 좌표 (x_std, y_std)를
        현재 인스턴스가 가진 커스텀 기하 구조의 시각 화면 좌표 (xv, yv)로 변환합니다.
        """
        return self.physical_to_visual(x_std, y_std)

    def is_inside_wafer(self, c: int, r: int) -> bool:
        """
        DOM 셀 인덱스 (c, r)가 웨이퍼 유효 원 영역 경계 내부에 완벽히 포함되는지 판별합니다.
        """
        u1 = (2 * c - self.visual_cols) / self.visual_cols
        u2 = (2 * (c + 1) - self.visual_cols) / self.visual_cols
        v1 = (2 * r - self.visual_rows) / self.visual_rows
        v2 = (2 * (r + 1) - self.visual_rows) / self.visual_rows

        max_u2 = max(u1 * u1, u2 * u2)
        max_v2 = max(v1 * v1, v2 * v2)

        return (max_u2 + max_v2) <= 1.0

    def get_edge_classification(self) -> Dict[str, Set[Tuple[int, int]]]:
        """
        현재 시각 격자 상에서 E1(가장 외곽 1줄) 및 E2(외곽에서 2줄째)에 속하는 셀 세트를 추출합니다.
        
        :return: {"E1": {(c1, r1), ...}, "E2": {(c2, r2), ...}}
        """
        # 1. 원 내부 여부 테이블 구축
        is_inside = [
            [self.is_inside_wafer(c, r) for c in range(self.visual_cols)]
            for r in range(self.visual_rows)
        ]

        e1_cells = set()
        e2_cells = set()

        # 2. E1 분류 (원 내부 셀 중 8방향 이웃 중 하나라도 원 외곽이거나 격자 경계인 경우)
        for r in range(self.visual_rows):
            for c in range(self.visual_cols):
                if not is_inside[r][c]:
                    continue

                touches_outside = False
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        if dr == 0 and dc == 0:
                            continue
                        nr, nc = r + dr, c + dc
                        # 격자 밖이거나 내부 원 구역이 아닌 경우
                        if (
                            nr < 0 or nr >= self.visual_rows or
                            nc < 0 or nc >= self.visual_cols or
                            not is_inside[nr][nc]
                        ):
                            touches_outside = True
                            break
                    if touches_outside:
                        break
                
                if touches_outside:
                    e1_cells.add((c, r))

        # 3. E2 분류 (원 내부 셀 중 E1이 아니며, 8방향 이웃 중 최소 하나가 E1인 경우)
        for r in range(self.visual_rows):
            for c in range(self.visual_cols):
                if not is_inside[r][c] or (c, r) in e1_cells:
                    continue

                touches_e1 = False
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        if dr == 0 and dc == 0:
                            continue
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < self.visual_rows and 0 <= nc < self.visual_cols:
                            if (nc, nr) in e1_cells:
                                touches_e1 = True
                                break
                    if touches_e1:
                        break
                
                if touches_e1:
                    e2_cells.add((c, r))

        return {"E1": e1_cells, "E2": e2_cells}
