# HTML Table Adjacency Graph Topology Parser User Guide

> **Status:** 🟢 Living | **Last-verified:** 2026-09-13 | **Owner:** Ingester | **Source-of-truth:** `server/parsers/html_topology_parser.py` · 상위 [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md)

> 🔴 **[2026-09-13 갱신] 이 문서는 07-24 이후 «거절 경로»를 한 글자도 들고 있지 않았습니다.** `419cd8fa`(2026-08-04, 이 파일에 +151/−51)가 「격자 원점을 «두 번» 유도하고 어긋나면 파일을 거절한다」를 넣었고, 그 뒤 `b95d998b`(2026-09-07)까지 옵직였습니다. 그 경로가 **§3.6-bis** 로 들어왔습니다 — «0행으로 들어온 파일»을 만나면 그 절부터 열으십시오.
> ⚠️ 그 밖의 절(§1~§3.5 · §4)은 이번 패스가 «열지 않았습니다» — 그대로인지 재지 않았다는 뜻입니다.

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
특정 출발 셀(노드 ID 또는 텍스트 값)로부터 유향 그래프의 정방향 엣지를 따라 도달할 수 있는 **모든 가능한 경로(Paths)**들의 리스트를 획득합니다. 루프(Cycle) 감지가 내장되어 무한 탐색을 방지하며, `max_depth` 인자를 통해 탐색할 최대 깊이(경로의 최대 노드 개수)를 제한할 수 있습니다.

```python
# 1. '20' 값 셀에서 시작하는 역추적 경로 탐색 (left_up 유향 그래프 대상)
paths_20 = parser.find_all_paths("20", nodes, directed_edges, by_value=True)
print(paths_20)
# [출력 결과 예시] -> 20에서 도달 가능한 모든 리프 헤더 경로들
# [['20', 'B', 'A'], ['20', '10', 'A']]

# 2. max_depth=2를 사용하여 경로의 길이를 제한
paths_20_limited = parser.find_all_paths("20", nodes, directed_edges, by_value=True, max_depth=2)
print(paths_20_limited)
# [출력 결과 예시] -> 최대 2개 노드까지만 포함한 경로
# [['20', 'B'], ['20', '10']]

# 3. 'A' 최상위 헤더에서 시작하는 순방향 데이터 탐색 (right_down 유향 그래프 대상)
nodes, edges_rd = parser.parse_to_directed_graph(html_data, direction_type="right_down")
paths_A = parser.find_all_paths("A", nodes, edges_rd, by_value=True)
print(paths_A)
# [출력 결과 예시] -> A에서 도달 가능한 모든 리프 데이터 셀 경로들
# [['A', 'B', '20'], ['A', '10', '20']]
```

---

### 3.5 테이블 내 모든 셀의 경로 일괄 탐색 (`find_all_paths_for_all_nodes`)
테이블 상의 모든 셀들 각각에 대해 `find_all_paths`를 수행한 결과를 사전(Dictionary) 구조로 일괄 취득합니다. `find_all_paths`의 모든 인자(`by_value`, `max_depth` 등)를 그대로 상속합니다.

```python
# 모든 노드 각각에서 출발하는 역추적 경로를 일괄 획득 (left_up 유향 그래프 대상)
all_paths = parser.find_all_paths_for_all_nodes(nodes, directed_edges, by_value=True, max_depth=None)

for node_val, paths in all_paths.items():
    print(f"셀 '{node_val}' 출발 경로들: {paths}")
```

---

### 3.6 2D 매트릭스 테이블 평탄화 파싱 (`HTMLMatrixTableParser`)
X축과 Y축 정수형 인덱스 눈금으로 구성된 2D 매트릭스(격자 데이터)와 상단의 공통 계층형 메타데이터(예: `BDIE_LOT`, `BDIE_WF` 등)를 하나의 평탄화된 관계형 레코드 목록(`List[Dict[str, Any]]`)으로 변환합니다.
누적 장벽 알고리즘(Accumulative Barrier Algorithm)과 조상 필터링을 사용하여 메타데이터의 값 셀과 키 셀 간의 역추적 매핑을 정밀하게 추출합니다.

```python
from parsers.html_topology_parser import HTMLMatrixTableParser

# 1. 매트릭스 파서 초기화
matrix_parser = HTMLMatrixTableParser()

# 2. 평탄화 레코드 목록 추출
# 반환 형식: [ { "TITLE": "AAA", "BDIE_LOT": "A", "BDIE_WF": "B", "X": 2, "Y": 2, "VALUE": "F" }, ... ]
records = matrix_parser.parse_matrix_to_records(html_content)
```

---

### 3.6-bis 🔴 격자를 «거절»할 때 — 0행은 고장이 아닐 수 있습니다 (2026-09-13 실측)

`parse_matrix_to_records` 가 **격자 원점을 못 정하면 `[]` 를 돌려주고
«던지지 않습니다»**(`server/parsers/html_topology_parser.py` :633~660 @ `b95d998b`).
그래서 **status 는 SUCCESS 이고, 그것이 맞습니다** — 형식을 거부하는 것은
정당한 결과입니다. 문제는 그것이 «말없이» 정상처럼 보이는 것이고,
이 절은 그 문장이 «어디서 보이는지»를 적습니다.

#### 왜 거절하나 — X·Y 가 «비즈니스 키의 일부»이기 때문입니다
소스의 로그 문장이 그 이유를 적습니다(:654~658):
「Returning 0 records rather than a plausible-looking wrong grid origin, because X and Y are
part of the business key.」
🔴 즉 **그러도는척 맞아 보이는 틀린 원점**은 0행보다 나쁘다는 판단입니다 —
원점이 한 칸 밀리면 모든 셀이 «다른 다이»의 값으로 들어가고, 그것은 나중에
세어도 안 보입니다.

#### 원점을 «두 번» 유도합니다 (`419cd8fa`)
```
① 행의 모양    X축 눈금 행 = «병합 안 된» 비숫자 모퉁이 + 병합 안 된 정수 눈금 2개 이상
② Y축 라벨   0번 열의 «병합 안 된 정수» 라벨들 — 그 최소행 − 1 이 눈금 행이어야 합니다
둘이 어긋나면  거절
```
그래서 사유가 **네 가지로 갈라 이름이 붙습니다**(:638~652):
```
① 둘 다 없음    「no X-axis ruler row and no Y-axis labels … does not have the shape of a 2D matrix map」
② 눈금만 없음   「no row has the shape of an X-axis ruler … while the Y-axis labels imply the ruler is row N」
③ 라벨만 없음   「row N is ruler-shaped but no unmerged integer labels sit in column 0」
④ 둘이 불일치  「the two derivations disagree … Something ruler-shaped sits above the real grid」
```
🔵 ④ 가 이 기제의 존재 이유입니다 — «진짜 격자 위에 눈금처럼 생긴 것이
하나 더 있는» 문서는 한 가지 유도만 쓰면 «조용히» 틀린 답을 냅니다.

#### 🔴 그러면 그 사유를 «어디서 읽나» — 로그가 아닙니다
```
쓰는 곳   html_topology_parser.note_refusal(reason)      :809   (거절 자리에서 :660)
채널    _REFUSAL = threading.local()                      :806   — 모듈 곁의 쓰레드-로컬
가져감  html_topology_parser.take_refusal()              :814   «가져가며 비울1»
비움    html_topology_parser.clear_refusal()             :822
워처가  directory_watcher._grid_refusal()                :2028  -> take_refusal()
        directory_watcher._compose_detail(…, grid_refusal)  :2047  -> detail 문자열
        그 detail 이 «완료 통지»의 네번째 인자로 가고(:1985 · :2543),
        `file_ingestion_completed` 메시지 문자열과 인젝션 성공 로그에 붙습니다
```
🔵 **그래서 운영자가 보는 자리는 «파일 완료 메시지»입니다** — 로그를 안 열어도
「왜 0행인가」가 거기 있습니다. 사유가 «없으면» 그때만 기본 문장(「파싱 결과 0행 ―
저장된 셀 없음…」)이 나갑니다(:2059~2069).
⛔ 그 둘을 «같이» 쓰지 않습니다 — 사유를 주면서 「로그 확인」을 남기면 운영자가
«이미 답을 받았는데» 또 로그를 보라는 말을 듣습니다(그 주석이 그렇게 적습니다).

#### ⚠️ 채널의 수명 — «한 파일»에서 끝납니다
```
시작   워처가 (표, 파일) 한 건을 넘기기 «전» clear_refusal()          directory_watcher :2748
끝    take_refusal() 이 «가져가며 비울1니다»                        :814
위험   한 파일의 사유가 «다음 파일의 화면»에 붙는 것 — 위 둘이 그것을 닫습니다
```
🔴 **왜 파서 «인스턴스»에 안 달고 모듈 곁 채널인가** — 그 객체를 만드는 것은
«운영자의 플러그인»이고 워처는 그것을 절대 못 봅니다(:2744~2747의 주석).
그래서 모듈 옆에 놓고, 수명의 양끝을 «워처가» 쇥니다.
⚠️ 그 파서를 안 쓰는 워크스페이스가 대부분이라, `clear_refusal` import 가 실패해도
인제션을 막지 않습니다 — «없는 것은 정상»입니다(같은 주석).

#### 🔵 `_grid_refusal` 은 「실패했나」를 «안» 묻습니다
:2030~2034 가 그것을 명시합니다 — 사유만 가져오고 판정을 흔내지 않습니다.
🔴 이 함수가 판정을 흔내면 **정당한 성공이 화면에서 실패로 보입니다.**
즉 «0행 거절»은 SUCCESS 이고, 화면이 달라지는 것은 **상태가 아니라 문장**입니다.

#### 시험
`server/tests/test_a_refused_grid_says_why_on_the_screen.py` 가 이 경로를 못 박습니다 —
사유의 존재·가져가며 비움·쓰레드 경계·`clear_refusal()` 호출이 «한 번»인 것까지.

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
