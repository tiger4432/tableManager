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
    # 첫 번째 열(c == 0)인 'A'와 'B'는 숫자가 아닌 문자열이므로 디폴트 Row Header 규칙에 의해 헤더(is_header = True)로 판정됩니다.
    # 따라서 '100' 셀의 키는 ('A', '값')이 되고, '200' 셀의 키는 ('B', '값')이 됩니다.
    mappings = parser.extract_semantic_tuples(nodes, edges)
    
    assert mappings.get(("A", "값")) == "100"
    assert mappings.get(("B", "값")) == "200"

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
    assert matrix_rd[idx_20][idx_10] == 0

def test_connector_value_spanned_edge():
    # 사용자가 제공한 실제 병합 엑셀-HTML 변환 데이터 형태
    html = """
    <table border="0" cellpadding="0" cellspacing="0" width="360" style="border-collapse: collapse;width:270pt">
     <colgroup><col width="72" span="5" style="width:54pt"></colgroup>
     <tbody>
      <tr height="22" style="height:16.5pt">
       <td colspan="5" rowspan="2" height="44" class="xl65" width="360" style="height:33.0pt; width:270pt">afsdfsfds</td>
      </tr>
      <tr height="22" style="height:16.5pt"></tr>
      <tr height="22" style="height:16.5pt">
       <td colspan="2" rowspan="2" height="44" class="xl65" style="height:33.0pt">Connector</td>
       <td>lot</td>
       <td align="right">13</td>
       <td rowspan="2" class="xl66">359.05</td>
      </tr>
      <tr height="22" style="height:16.5pt">
       <td height="22" style="height:16.5pt">value</td>
       <td align="right">31</td>
      </tr>
     </tbody>
    </table>
    """
    parser = HTMLTableGraphParser()
    nodes, edges = parser.parse_to_graph(html)
    
    # Connector와 value 사이의 엣지 존재 여부 체크
    val_node = [n for n in nodes if n.value == "value"][0]
    conn_node = [n for n in nodes if n.value == "Connector"][0]
    
    left_edges = [e for e in edges if e.source == val_node.id and e.target == conn_node.id and e.direction == "LEFT"]
    right_edges = [e for e in edges if e.source == conn_node.id and e.target == val_node.id and e.direction == "RIGHT"]
    
    assert len(left_edges) == 1
    assert len(right_edges) == 1

    # 의미론적 튜플 매핑 결과 검증
    mappings = parser.extract_semantic_tuples(nodes, edges)
    
    assert mappings.get(("afsdfsfds", "Connector", "lot")) == "13"
    assert mappings.get(("afsdfsfds", "Connector", "value")) == "31"


def test_all_paths_extraction():
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
    
    # 1. left_up (역추적) 방향 엣지 셋
    nodes, edges_lu = parser.parse_to_directed_graph(html, direction_type="left_up")
    
    # '20' 셀에서 시작하는 역추적 경로들
    # 20 -> B (UP), 20 -> 10 (LEFT)
    # B -> A (LEFT), 10 -> A (UP)
    # 20 -> B -> A
    # 20 -> 10 -> A
    paths_20 = parser.find_all_paths("20", nodes, edges_lu, by_value=True)
    
    assert ["20", "B", "A"] in paths_20
    assert ["20", "10", "A"] in paths_20
    assert len(paths_20) == 2

    # max_depth = 2 제한인 경우
    # 20 -> B, 20 -> 10 까지만 탐색되어야 함
    paths_20_depth_2 = parser.find_all_paths("20", nodes, edges_lu, by_value=True, max_depth=2)
    assert ["20", "B"] in paths_20_depth_2
    assert ["20", "10"] in paths_20_depth_2
    assert len(paths_20_depth_2) == 2

    # max_depth = 1 제한인 경우
    # 20 자체까지만 탐색되어야 함
    paths_20_depth_1 = parser.find_all_paths("20", nodes, edges_lu, by_value=True, max_depth=1)
    assert [["20"]] == paths_20_depth_1

    # 2. right_down (순방향) 엣지 셋
    nodes, edges_rd = parser.parse_to_directed_graph(html, direction_type="right_down")
    
    # 'A' 셀에서 시작하는 순방향 경로들
    # A -> B -> 20
    # A -> 10 -> 20
    paths_A = parser.find_all_paths("A", nodes, edges_rd, by_value=True)
    
    assert ["A", "B", "20"] in paths_A
    assert ["A", "10", "20"] in paths_A
    assert len(paths_A) == 2

    # max_depth = 2 제한인 경우
    # A -> B, A -> 10 까지만 탐색되어야 함
    paths_A_depth_2 = parser.find_all_paths("A", nodes, edges_rd, by_value=True, max_depth=2)
    assert ["A", "B"] in paths_A_depth_2
    assert ["A", "10"] in paths_A_depth_2
    assert len(paths_A_depth_2) == 2


def test_find_all_paths_for_all_nodes():
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
    
    # 1. left_up (역추적) 방향 엣지 셋
    nodes, edges_lu = parser.parse_to_directed_graph(html, direction_type="left_up")
    
    # 모든 셀들에 대해 일괄 경로 탐색 수행 (by_value=True, max_depth=None)
    all_paths_val = parser.find_all_paths_for_all_nodes(nodes, edges_lu, by_value=True)
    
    # A는 최상위 헤더이므로 A에서 시작하는 LEFT/UP 경로는 자기 자신 [['A']]
    assert [["A"]] == all_paths_val.get("A")
    # B -> A (LEFT)
    assert ["B", "A"] in all_paths_val.get("B")
    # 10 -> A (UP)
    assert ["10", "A"] in all_paths_val.get("10")
    # 20 -> B -> A, 20 -> 10 -> A
    assert ["20", "B", "A"] in all_paths_val.get("20")
    assert ["20", "10", "A"] in all_paths_val.get("20")
    
    # 2. right_down (순방향) 엣지 셋 + max_depth 제한
    nodes, edges_rd = parser.parse_to_directed_graph(html, direction_type="right_down")
    all_paths_rd_limited = parser.find_all_paths_for_all_nodes(nodes, edges_rd, by_value=True, max_depth=2)
    
    # A에서 시작하는 순방향 경로 (max_depth=2 제한): A -> B, A -> 10
    assert ["A", "B"] in all_paths_rd_limited.get("A")
    assert ["A", "10"] in all_paths_rd_limited.get("A")
    assert len(all_paths_rd_limited.get("A")) == 2



