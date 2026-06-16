# HTML Table Adjacency Graph Topology Parser User Guide

이 가이드는 HTML 테이블 구조에서 셀 병합(`rowspan`, `colspan`)과 불규칙한 레이아웃 위상(Topology)을 분석하여 데이터와 헤더 간의 의미론적 관계를 역추적하고, 노드와 엣지 기반의 유향 그래프 및 연결 행렬을 생성하는 **`HTMLTableGraphParser`**의 사용 방법과 통합 방안에 대해 다룹니다.

---

## 1. 핵심 아키텍처 및 원리

`HTMLTableGraphParser`는 단순히 2D 행렬을 루프 도는 수준을 넘어, 테이블 구조를 수학적인 **인접 그래프(Cell Adjacency Graph)** 모델로 추상화하여 해석합니다.

1. **가상 2D 그리드 재구성 (Grid Reconstruction)**:
   HTML `rowspan`, `colspan` 속성을 읽어 기하학적인 가상 2D 좌표 그리드로 테이블을 전개합니다. 병합된 넓은 셀은 단 **하나의 `TableNode`** 객체로 생성되며, 병합이 시작된 첫 좌표뿐 아니라 커버하는 모든 2D 공간 영역 좌표들이 이 노드 객체를 공유 참조합니다.
2. **공간 인접 엣지 정의**:
   가상 그리드 상에서 각 셀 경계를 기준으로 상하좌우(`UP`, `DOWN`, `LEFT`, `RIGHT`)에 접해 있는 이웃 노드들을 탐색하여 방향성 **`TableEdge`**를 빌드합니다.
3. **물리적 방향 제약 및 장벽 규칙 (Barrier Rule)**:
   특정 노드에서 조상 헤더를 찾기 위해 DFS 탐색을 수행할 때, 탐색 방향(UP, LEFT)에 대해 기하학적 범위 조건(예: UP이면 행 인덱스가 감소하고 열 범위가 겹칠 것)을 엄격히 적용하여 무분별한 엣지 추적 누수를 차단합니다. 또한 가로 전체를 덮는 수평 병합 셀(섹션 헤더)은 **차단 장벽(Barrier)**으로 판단하여 그 장벽을 가로질러 윗행으로 탐색이 흘러가는 것을 즉시 차단합니다.
4. **위치 및 값 기반 Row Header 자동 감지**:
   `<th>` 태그나 볼드체 등의 스타일링이 지정되지 않은 일반 `<td>` 태그 형태라도, 숫자가 아닌 일반 텍스트 문자열이면서 테이블의 마지막 열 이전(`c < max_cols - 1`)에 위치한 노드는 구조적인 **Row Header**로 인지합니다. 이 하이브리드 휴리스틱 덕분에, 병합 셀(`colspan` 등)로 인해 첫 열(`c=0`)을 벗어난 우측 열에 나타나는 계층적 행 속성(예: `lot`, `value`)들까지 완벽하게 헤더로 자동 판단하여 튜플 키에 수집합니다.
5. **빈 행(Empty TR)에 대한 인덱스 복원**:
   셀 병합(`rowspan`)의 영향으로 `td`/`th` 요소를 하나도 갖지 않는 빈 `<tr></tr>` 태그가 생성되는 경우에도, 가상 2D 그리드 내에서의 물리적 행 위치(`row_idx`)를 올바르게 보정하여 노드 간의 공간 인접 엣지가 뒤틀리지 않도록 처리합니다.

---

## 2. 모듈 가져오기 및 파서 생성

```python
from parsers.html_topology_parser import HTMLTableGraphParser

# 1. 기본 생성 (<th> 태그 및 볼드/인라인 스타일 기반 자동 헤더 판정)
parser = HTMLTableGraphParser()

# 2. 커스텀 헤더 판정식 주입 생성 (선택 사항)
# 예: class 명에 'data-header'가 포함된 경우만 헤더로 판정
custom_parser = HTMLTableGraphParser(
    is_header_fn=lambda tag: "data-header" in tag.get("class", [])
)
```

---

## 3. 주요 기능 및 API 사용법

### 3.1 의미론적 튜플 매핑 추출 (`extract_semantic_tuples`)
헤더와 데이터 셀 간의 위상 관계를 역추적하여 **`{(header_hierarchy_tuple): value}`** 구조의 사전을 획득합니다. 데이터베이스의 스키마에 맞게 매핑 적재할 때 가장 추천하는 메서드입니다.

```python
html_data = """
<table>
    <tr>
        <th colspan="2">2026년 실적</th>
    </tr>
    <tr>
        <th>1분기</th>
        <th>2분기</th>
    </tr>
    <tr>
        <td>1000</td>
        <td>2000</td>
    </tr>
</table>
"""

# 1. 2D 그래프 전개 (Nodes & Edges 획득)
nodes, edges = parser.parse_to_graph(html_data)

# 2. DFS 역추적 및 의미론적 매핑 추출
mappings = parser.extract_semantic_tuples(nodes, edges)

for headers, val in mappings.items():
    print(f"계층구조: {headers} => 값: {val}")

# [출력 결과]
# 계층구조: ('2026년 실적', '1분기') => 값: 1000
# 계층구조: ('2026년 실적', '2분기') => 값: 2000
```

---

### 3.2 정방향 유향 그래프 생성 (`parse_to_directed_graph`)
양방향 엣지가 섞인 기본 그래프에서, 필요에 따라 특정 방향만을 정방향으로 가지는 유향 그래프(Directed Graph)를 필터링하여 반환합니다.

```python
# 1. left_up 모드 (Default: 헤더 역추적용 - LEFT 및 UP 엣지만 수집)
nodes, directed_edges = parser.parse_to_directed_graph(html_data, direction_type="left_up")

# 2. right_down 모드 (선택: 데이터 순방향 탐색용 - RIGHT 및 DOWN 엣지만 수집)
nodes, directed_edges_rd = parser.parse_to_directed_graph(html_data, direction_type="right_down")
```

---

### 3.3 연결 행렬 생성 (`generate_adjacency_matrix`)
노드 목록과 필터링된 유향 엣지 목록을 전달하여 노드 간의 엣지 존재 유무를 $N \times N$ 연결 행렬(Adjacency Matrix)로 도출합니다.

```python
adj_data = parser.generate_adjacency_matrix(nodes, directed_edges)

# 연결 행렬 (0과 1로 구성된 2차원 리스트)
matrix = adj_data["matrix"]

# 행렬의 인덱스 순서와 1:1 매칭되는 노드 정보
node_ids = adj_data["node_ids"]
node_values = adj_data["node_values"] # 예: ['A', 'B', '10', '20']

# 특정 노드 간 연결 조회 예시
idx_src = node_values.index("10")
idx_tgt = node_values.index("A")

if matrix[idx_src][idx_tgt] == 1:
    print(f"'{node_values[idx_src]}' 노드에서 '{node_values[idx_tgt]}' 노드로 정방향 유향 엣지가 존재합니다.")
```

---

### 3.4 가능한 모든 경로 탐색 (`find_all_paths`)
특정 출발 셀(노드 ID 또는 텍스트 값)로부터 유향 그래프의 정방향 엣지를 따라 도달할 수 있는 **모든 가능한 경로(Paths)**들의 리스트를 획득합니다. 루프(Cycle) 감지가 내장되어 무한 탐색을 안전하게 방지합니다.

```python
# 1. '20' 값 셀에서 시작하는 역추적 경로 탐색 (left_up 유향 그래프 대상)
paths_20 = parser.find_all_paths("20", nodes, directed_edges, by_value=True)
print(paths_20)
# [출력 결과 예시] -> 20에서 도달 가능한 모든 리프 헤더 경로들
# [['20', 'B', 'A'], ['20', '10', 'A']]

# 2. 'A' 최상위 헤더에서 시작하는 순방향 데이터 탐색 (right_down 유향 그래프 대상)
nodes, edges_rd = parser.parse_to_directed_graph(html_data, direction_type="right_down")
paths_A = parser.find_all_paths("A", nodes, edges_rd, by_value=True)
print(paths_A)
# [출력 결과 예시] -> A에서 도달 가능한 모든 리프 데이터 셀 경로들
# [['A', 'B', '20'], ['A', '10', '20']]
```

---

## 4. AssyManager Ingestion Pipeline 실전 연동 예시

클라이언트가 붙여넣기(Smart Paste)를 통해 전송한 `.html` 파일을 실시간 감지하여, 파이프라인에서 계층 구조를 플래튼(Flatten)한 후 데이터베이스 동적 테이블 스키마에 맞추어 적재하는 커스텀 파서 플러그인(`server/ingestion_workspace/{table_name}/scripts/`) 구현 샘플입니다.

```python
import os
import pandas as pd
from pipeline_base import BasePipelineParser
from html_topology_parser import HTMLTableGraphParser

class CustomHtmlIngestionParser(BasePipelineParser):
    @classmethod
    def match(cls, file_path: str) -> bool:
        # 업로드된 파일 중 HTML 확장자 매칭
        return file_path.lower().endswith('.html')

    def parse(self, file_path: str) -> list[dict]:
        # 1. 파일 읽기
        with open(file_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        # 2. 그래프 파서 가동 및 계층 튜플 추출
        parser = HTMLTableGraphParser()
        nodes, edges = parser.parse_to_graph(html_content)
        mappings = parser.extract_semantic_tuples(nodes, edges)

        # 3. 비즈니스 스키마 컬럼에 맞게 변환
        # 목표 적재 스키마 예시: {"kpi_category", "metric_name", "metric_value"}
        cleaned_records = []
        for headers, val in mappings.items():
            # 예: ('[공통지표]', 'KPI') => 85%
            #     ('[공통지표]', '[영업지표]', '매출액') => 500억
            category = "미분류"
            metric = "Default"
            
            if len(headers) >= 2:
                # 가장 바깥쪽 섹션 헤더를 category로, 바로 위 헤더를 metric으로 사용
                category = headers[0]
                metric = " > ".join(headers[1:])
            elif len(headers) == 1:
                metric = headers[0]

            cleaned_records.append({
                "kpi_category": category,
                "metric_name": metric,
                "metric_value": val
            })

        return cleaned_records
```
