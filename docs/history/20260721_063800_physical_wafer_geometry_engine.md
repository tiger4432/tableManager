# 2026-07-21 06:38:00 - 물리적 웨이퍼 기하학 규격 연산 엔진 및 센터링 오프셋 연동 구현

## 1. 개요
* **요구사항**: 단순 비율 원형 계산이 아닌, 반도체 실물 표준 규격인 **웨이퍼 직경(Wafer Diameter mm)**, **칩 피치 크기(Chip X, Y mm)**, **가두리 여백(Edge Exclusion mm)** 및 **센터링 오프셋(Centering Offset X, Y mm)** 수치를 기반으로 웨이퍼 맵 격자와 비대칭 테두리 유효 영역을 수학적으로 정밀 계산하여 렌더링하는 물리 기하학 연산 엔진 구현.

---

## 2. 세부 구현 사항

### A. 백엔드 물리 기하학 연산 엔진 (`physical_wafer_engine.py`)
* [`server/utils/physical_wafer_engine.py`](file:///c:/Users/kk980/Developments/assyManager/server/utils/physical_wafer_engine.py) 신설:
  * 유효 반지름 $R_{eff} = \frac{\text{Wafer Diameter}}{2} - \text{Edge Exclusion}$ 도출.
  * 각 격자 셀 $(c, r)$의 웨이퍼 중심점 대비 물리 mm 좌표 $X_{mm}(c), Y_{mm}(r)$ 정밀 연산.
  * Centering Offset $(O_x, O_y)$ 반영 유효 포함 조건 판별 ($X_{mm}^2 + Y_{mm}^2 \le R_{eff}^2$).

### B. 백엔드 좌표 변환기 연동 (`coordinate_transformer.py`)
* `WaferMapCoordinateTransformer`에 `physical_engine` 및 centering offset 연동 지원 추가.

### C. 프론트엔드 HTML/JS UI 컨트롤 패널 (`map_editor.html`, `map_editor.js`)
* 좌측 사이드바 패널에 **`📏 Physical Wafer Geometry`** 섹션 탑재:
  * **Wafer Diameter**: `300 mm (12")`, `200 mm (8")`, `150 mm (6")` 선택 및 커스텀 입력.
  * **Chip X / Chip Y (mm)**: 칩 물리적 길이 입력.
  * **Centering Offset X / Offset Y (mm)**: 물리적 중심 편차 mm 입력.
  * **Edge Exclusion (mm)**: 테두리 가두리 여백 mm 입력.
  * **`⚡ Apply Physical Geometry`** 버튼 클릭 및 수치 변경 시 격자 크기 및 비대칭 유효 칩 패턴이 캔버스 상에 실시간 드로잉됨.
* `pushMapData()` 및 `loadExistingMap()` 시 `grid_metadata`에 물리적 기하학 수치 파라미터가 자동으로 직렬화되어 DB에 보존 및 복원됨.

---

## 3. 검증 결과
* **프론트엔드 Vite 컴파일**: `map_editor-CUrLU6mr.js` 정상 컴파일 완료.
* **Pytest 단위 테스트**: `tests/test_physical_wafer_engine.py` 포함 **38개 백엔드 단위 테스트 100% 그린 패스**.
