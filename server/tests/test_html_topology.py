import pytest
from parsers.html_topology_parser import HTMLTableGraphParser, TableNode, TableEdge

def test_standard_table_parsing():
    html = """
    <table>
        <tr>
            <th>구분</th>
            <th>값</th>
        </tr>
        <tr>
            <td>A</td>
            <td>100</td>
        </tr>
        <tr>
            <td>B</td>
            <td>200</td>
        </tr>
    </table>
    """
    parser = HTMLTableGraphParser()
    nodes, edges = parser.parse_to_graph(html)
    
    # 노드 개수 검증 (구분, 값, A, 100, B, 200 => 총 6개)
    assert len(nodes) == 6
    
    # 엣지 개수 검증 (인접 엣지들이 잘 만들어졌는지)
    # 구분 -> 값 (RIGHT), 값 -> 구분 (LEFT)
    # 구분 -> A (DOWN), A -> 구분 (UP)
    # 값 -> 100 (DOWN), 100 -> 값 (UP)
    # ...
    assert len(edges) > 0
    
    # 의미적 튜플 매핑 검증
    # A와 100은 인접하며, 100의 UP 엣지를 타고 올라가면 '값' 헤더, LEFT 엣지를 타고 가면 'A'는 td라 헤더가 아님. 
    # 기본적으로 top_down + left_right 이나, H가 아닌 것들은 매핑되지 않음.
    # 이 경우 '100' 셀에서 위로 가면 '값'(th, 헤더), 왼쪽으로 가면 'A'(td, 비헤더).
    # 따라서 100의 키는 ('값',) 이고 값은 '100'이 되며,
    # '200' 셀에서 위로 가면 '값'(th), 왼쪽으로 가면 'B'(td). 키는 ('값',) 이고 값은 '200'이 됨.
    # (헤더 판정 함수가 td인 'A', 'B'를 비헤더로 판단하기 때문)
    mappings = parser.extract_semantic_tuples(nodes, edges)
    
    assert mappings.get(("값",)) == "100" or mappings.get(("값",)) == "200"

def test_column_spanned_headers():
    # 상단 헤더 병합 케이스
    html = """
    <table>
        <tr>
            <th colspan="2">분기실적</th>
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
    parser = HTMLTableGraphParser()
    nodes, edges = parser.parse_to_graph(html)
    
    # '1000' 셀의 기하학적 좌표는 R:2, C:0. 
    # '1분기'는 R:1, C:0. '분기실적'은 R:0, C:0~1 (colspan=2).
    # 1000에서 UP 엣지를 타고 올라가면 '1분기' (th) -> '분기실적' (th) 순서로 도달해야 함.
    mappings = parser.extract_semantic_tuples(nodes, edges)
    print("\n--- NODES ---")
    for n in nodes: print(n)
    print("--- EDGES ---")
    for e in edges: print(e)
    print("--- MAPPINGS ---")
    for k, v in mappings.items(): print(f"{k} => {v}")
    
    assert mappings.get(("분기실적", "1분기")) == "1000"
    assert mappings.get(("분기실적", "2분기")) == "2000"

def test_row_spanned_headers():
    # 좌측 카테고리 헤더 병합 케이스
    # Category1 아래 Sub1(100), Sub2(200)이 매치되는 케이스
    # 이때 Category1과 Sub1, Sub2 모두 <th> 태그로 구성됨
    html = """
    <table>
        <tr>
            <th rowspan="2">가전</th>
            <th>냉장고</th>
            <td>50</td>
        </tr>
        <tr>
            <th>세탁기</th>
            <td>70</td>
        </tr>
    </table>
    """
    parser = HTMLTableGraphParser()
    nodes, edges = parser.parse_to_graph(html)
    
    # '50' (R:0, C:2) 에서 LEFT 로 가면 '냉장고' (R:0, C:1) -> '가전' (R:0~1, C:0).
    # '70' (R:1, C:1) 에서 LEFT 로 가면 '세탁기' (R:1, C:0).
    # '70'의 행 범위는 R:1이고, '가전'은 R:0~1 을 커버하고 있으므로 
    # '세탁기'에서 LEFT 로 갈 때 '가전'과 인접해 연결되어 있어야 함.
    mappings = parser.extract_semantic_tuples(nodes, edges)
    
    assert mappings.get(("가전", "냉장고")) == "50"
    assert mappings.get(("가전", "세탁기")) == "70"

def test_multi_dimensional_cross_headers():
    # 상단 및 좌측 헤더가 결합된 2D 교차 테이블
    # R0, C0: 헤더 (비어있음 or 구분)
    # R0, C1: 1분기 (th)
    # R1, C0: 서울본사 (th)
    # R1, C1: 500 (td)
    html = """
    <table>
        <tr>
            <th>구분</th>
            <th>1분기</th>
        </tr>
        <tr>
            <th>서울본사</th>
            <td>500</td>
        </tr>
    </table>
    """
    parser = HTMLTableGraphParser()
    nodes, edges = parser.parse_to_graph(html)
    
    # 500 에서 UP 으로 가면 '1분기' (th), LEFT 로 가면 '서울본사' (th)
    # 최종 경로: 서울본사 + 1분기 = ('서울본사', '1분기')
    mappings = parser.extract_semantic_tuples(nodes, edges)
    
    assert mappings.get(("서울본사", "1분기")) == "500"

def test_section_headers_colspan():
    # 테이블 중간 가로지르는 전체 병합 섹션 헤더
    html = """
    <table>
        <tr>
            <th colspan="2" style="font-weight: bold;">[공통지표]</th>
        </tr>
        <tr>
            <th>KPI</th>
            <td>85%</td>
        </tr>
        <tr>
            <th colspan="2" style="font-weight: bold;">[영업지표]</th>
        </tr>
        <tr>
            <th>매출액</th>
            <td>500억</td>
        </tr>
    </table>
    """
    # [공통지표]와 [영업지표]는 colspan=2 로 테이블 전체 폭을 채움.
    # '85%' 의 조상에는 [공통지표]가 들어가야 하고,
    # '500억'의 조상에는 [영업지표]가 들어가야 함.
    parser = HTMLTableGraphParser()
    nodes, edges = parser.parse_to_graph(html)
    mappings = parser.extract_semantic_tuples(nodes, edges)
    
    assert mappings.get(("[공통지표]", "KPI")) == "85%"
    assert mappings.get(("[공통지표]", "[영업지표]", "매출액")) == "500억"

def test_directed_graph_and_adjacency_matrix():
    html = """
    <table>
        <tr>
            <th>A</th>
            <th>B</th>
        </tr>
        <tr>
            <td>10</td>
            <td>20</td>
        </tr>
    </table>
    """
    parser = HTMLTableGraphParser()

    # ----------------------------------------------------
    # 1. 디폴트: left_up 모드 (헤더 역추적용: LEFT & UP)
    # ----------------------------------------------------
    nodes, edges_lu = parser.parse_to_directed_graph(html, direction_type="left_up")
    
    # 엣지 방향이 오직 LEFT, UP만 있어야 함 (RIGHT, DOWN 배제)
    directions_lu = {e.direction for e in edges_lu}
    assert "RIGHT" not in directions_lu
    assert "DOWN" not in directions_lu
    assert "LEFT" in directions_lu
    assert "UP" in directions_lu
    
    # 연결 행렬 생성
    adj_data_lu = parser.generate_adjacency_matrix(nodes, edges_lu)
    matrix_lu = adj_data_lu["matrix"]
    node_values = adj_data_lu["node_values"]
    
    assert node_values == ["A", "B", "10", "20"]
    node_to_idx = {val: idx for idx, val in enumerate(node_values)}
    
    idx_A = node_to_idx["A"]
    idx_B = node_to_idx["B"]
    idx_10 = node_to_idx["10"]
    idx_20 = node_to_idx["20"]
    
    # 정방향 연결 검증 (B -> A (LEFT), 10 -> A (UP), 20 -> B (UP), 20 -> 10 (LEFT))
    assert matrix_lu[idx_B][idx_A] == 1   # B -> A
    assert matrix_lu[idx_10][idx_A] == 1  # 10 -> A
    assert matrix_lu[idx_20][idx_B] == 1  # 20 -> B
    assert matrix_lu[idx_20][idx_10] == 1 # 20 -> 10
    
    # 역방향(RIGHT, DOWN 방향)은 0이어야 함
    assert matrix_lu[idx_A][idx_B] == 0
    assert matrix_lu[idx_A][idx_10] == 0
    
    # ----------------------------------------------------
    # 2. 선택: right_down 모드 (데이터 탐색용: RIGHT & DOWN)
    # ----------------------------------------------------
    _, edges_rd = parser.parse_to_directed_graph(html, direction_type="right_down")
    
    directions_rd = {e.direction for e in edges_rd}
    assert "LEFT" not in directions_rd
    assert "UP" not in directions_rd
    assert "RIGHT" in directions_rd
    assert "DOWN" in directions_rd
    
    adj_data_rd = parser.generate_adjacency_matrix(nodes, edges_rd)
    matrix_rd = adj_data_rd["matrix"]
    
    # 정방향 연결 검증 (A -> B (RIGHT), A -> 10 (DOWN), B -> 20 (DOWN), 10 -> 20 (RIGHT))
    assert matrix_rd[idx_A][idx_B] == 1
    assert matrix_rd[idx_A][idx_10] == 1
    assert matrix_rd[idx_B][idx_20] == 1
    assert matrix_rd[idx_10][idx_20] == 1
    
    # 역방향은 0이어야 함
    assert matrix_rd[idx_B][idx_A] == 0


