import logging
from bs4 import BeautifulSoup
from typing import List, Dict, Tuple, Set, Any, Optional

logger = logging.getLogger("HTMLTopologyParser")

class TableNode:
    """
    테이블 내의 하나의 고유 셀을 나타내는 그래프 노드입니다.
    rowspan/colspan 병합을 고려하여 실제 차지하는 기하학적 범위를 가집니다.
    """
    def __init__(self, node_id: str, value: str, r_start: int, r_end: int, c_start: int, c_end: int, is_header: bool, tag_name: str = "td"):
        self.id = node_id
        self.value = value.strip()
        self.row_range = (r_start, r_end)  # (시작 행 index, 끝 행 index)
        self.col_range = (c_start, c_end)  # (시작 열 index, 끝 열 index)
        self.is_header = is_header
        self.tag_name = tag_name

    @property
    def row_span(self) -> int:
        return self.row_range[1] - self.row_range[0] + 1

    @property
    def col_span(self) -> int:
        return self.col_range[1] - self.col_range[0] + 1

    def __repr__(self):
        role = "Header" if self.is_header else "Data"
        return f"Node({self.id}, '{self.value}', R:{self.row_range}, C:{self.col_range}, Role:{role})"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "value": self.value,
            "row_range": list(self.row_range),
            "col_range": list(self.col_range),
            "is_header": self.is_header,
            "tag_name": self.tag_name
        }


class TableEdge:
    """
    노드 간의 방향성 공간 인접성을 정의하는 엣지입니다.
    """
    def __init__(self, source: str, target: str, direction: str):
        self.source = source      # 출발 노드 id
        self.target = target      # 도착 노드 id
        self.direction = direction  # 'UP', 'DOWN', 'LEFT', 'RIGHT'

    def __repr__(self):
        return f"Edge({self.source} -{self.direction}-> {self.target})"

    def __eq__(self, other):
        if not isinstance(other, TableEdge):
            return False
        return (self.source == other.source and 
                self.target == other.target and 
                self.direction == other.direction)

    def __hash__(self):
        return hash((self.source, self.target, self.direction))

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "target": self.target,
            "direction": self.direction
        }


class HTMLTableGraphParser:
    """
    HTML <table> 데이터를 읽어 노드 및 엣지로 구성된 그래프 모델을 구축하고,
    그래프 탐색을 통해 헤더-값 매핑 관계 {(headers): value} 를 추출하는 클래스입니다.
    """
    def __init__(self, is_header_fn=None):
        """
        :param is_header_fn: BeautifulSoup Tag 객체를 인자로 받아 
                              해당 셀이 헤더인지 여부(bool)를 리턴하는 커스텀 판정 함수.
        """
        self.is_header_fn = is_header_fn or self._default_is_header

    def _default_is_header(self, tag) -> bool:
        """기본 헤더 판별 규칙"""
        if not tag:
            return False
        # 1. <th> 태그는 당연히 헤더
        if tag.name == "th":
            return True
        # 2. 인라인 볼드 스타일이나 class 에 header 를 명시적으로 포함하는 경우
        style = tag.get("style", "")
        if "font-weight" in style and ("bold" in style or "700" in style or "800" in style):
            return True
        class_list = tag.get("class", [])
        if any("header" in str(c).lower() or "head" in str(c).lower() for c in class_list):
            return True
        # 3. <td> 태그 안에 <b> or <strong> 태그가 셀 내용 전체를 감싸고 있는 경우
        bold_child = tag.find(["b", "strong"])
        if bold_child and bold_child.text.strip() == tag.text.strip():
            return True
        return False

    def parse_to_graph(self, html_content: str) -> Tuple[List[TableNode], List[TableEdge]]:
        """
        HTML 콘텐츠에서 첫 번째 테이블을 찾아 노드 및 엣지 리스트로 구성된 그래프 구조로 반환합니다.
        """
        soup = BeautifulSoup(html_content, "html.parser")
        table_tag = soup.find("table")
        if not table_tag:
            return [], []

        # 1. 2D 가상 그리드 구성
        grid, row_count, col_count = self._reconstruct_2d_grid(table_tag)
        if not grid:
            return [], []

        # 2. 2D 그리드를 기반으로 인접 엣지 및 노드 리스트 빌드
        nodes, edges = self._build_adjacency_graph(grid, row_count, col_count)
        return nodes, edges

    def extract_semantic_tuples(self, nodes: List[TableNode], edges: List[TableEdge]) -> Dict[Tuple[str, ...], Any]:
        """
        그래프 내의 비헤더(데이터) 노드들에서 시작하여 
        역방향 인접 엣지를 따라 헤더들을 탐색(DFS)한 후,
        {(header_hierarchy_tuple): value} 구조의 사전을 추출합니다.
        """
        node_map = {n.id: n for n in nodes}
        
        # 각 노드별 방향성 엣지 맵 구성 (인접 딕셔너리)
        in_edges = {n.id: [] for n in nodes}
        out_edges = {n.id: [] for n in nodes}
        for edge in edges:
            out_edges[edge.source].append(edge)
            in_edges[edge.target].append(edge)

        # 전체 컬럼 수 측정 (섹션 헤더 탐색용)
        max_col_idx = 0
        for n in nodes:
            max_col_idx = max(max_col_idx, n.col_range[1])
        total_cols = max_col_idx + 1

        results = {}

        for node in nodes:
            # 헤더가 아니고 값(value)이 비어있지 않은 데이터 셀을 출발점으로 삼음
            if node.is_header or not node.value:
                continue

            # 테이블 가로폭의 70% 이상을 차지하며 데이터 셀 상단에 존재하는 섹션 헤더 탐색
            section_headers = []
            for other in nodes:
                is_wide = False
                if total_cols <= 2:
                    is_wide = (other.col_span == total_cols)
                else:
                    is_wide = (other.col_span >= int(total_cols * 0.7))
                
                # 섹션 헤더는 반드시 가로 병합 셀이어야 함 (col_span > 1)
                if other.is_header and other.col_span > 1 and is_wide:
                    # 데이터 셀보다 행 번호가 상단인 섹션 헤더
                    if other.row_range[1] < node.row_range[0]:
                        section_headers.append(other)
            
            # 섹션 헤더들은 행 순서대로 정렬
            section_headers.sort(key=lambda n: n.row_range[0])
            section_header_vals = [sh.value for sh in section_headers if sh.value]
            section_ids = {sh.id for sh in section_headers}

            # 이 노드에 영향을 주는 헤더들을 수집 (단, 섹션 헤더로 이미 선점된 노드는 제외)
            top_headers = [h for h in self._find_ancestors(node.id, "UP", node_map, in_edges, out_edges, section_ids) if h.id not in section_ids]
            left_headers = [h for h in self._find_ancestors(node.id, "LEFT", node_map, in_edges, out_edges, section_ids) if h.id not in section_ids]

            # 상단 헤더들은 위에서 아래 순서(행 index 오름차순)로 정렬
            top_headers.sort(key=lambda n: n.row_range[0])
            top_header_vals = [h.value for h in top_headers if h.value]

            # 좌측 헤더들은 왼쪽에서 오른쪽 순서(열 index 오름차순)로 정렬
            left_headers.sort(key=lambda n: n.col_range[0])
            left_header_vals = [h.value for h in left_headers if h.value]

            # 전체 계층 구조 결합: [섹션 헤더] + [좌측 헤더] + [상단 헤더]
            raw_path = section_header_vals + left_header_vals + top_header_vals
            clean_path = []
            for p in raw_path:
                if not clean_path or clean_path[-1] != p:
                    clean_path.append(p)

            # 데이터 적재를 위해, 헤더 튜플 키가 빈값인 경우 'Default' 처리
            if not clean_path:
                key_tuple = ("Default",)
            else:
                key_tuple = tuple(clean_path)

            results[key_tuple] = node.value

        return results

    def _reconstruct_2d_grid(self, table_tag) -> Tuple[Dict[Tuple[int, int], TableNode], int, int]:
        """
        HTML <table> 내 행과 열을 스캔하여, rowspan/colspan 공간이 채워진 가상 2D 그리드를 복원합니다.
        """
        rows = table_tag.find_all("tr", recursive=True)
        if not rows:
            return {}, 0, 0

        # grid[(r, c)] = TableNode
        grid: Dict[Tuple[int, int], TableNode] = {}
        row_idx = 0
        max_col_idx = 0
        node_counter = 0

        for tr in rows:
            cells = tr.find_all(["td", "th"], recursive=False)
            if not cells:
                continue

            col_idx = 0
            for cell in cells:
                while (row_idx, col_idx) in grid:
                    col_idx += 1

                rowspan = int(cell.get("rowspan", 1))
                colspan = int(cell.get("colspan", 1))

                node_id = f"cell_{row_idx}_{col_idx}_{node_counter}"
                node_counter += 1
                is_header = self.is_header_fn(cell)
                
                node = TableNode(
                    node_id=node_id,
                    value=cell.text,
                    r_start=row_idx,
                    r_end=row_idx + rowspan - 1,
                    c_start=col_idx,
                    c_end=col_idx + colspan - 1,
                    is_header=is_header,
                    tag_name=cell.name
                )

                for r in range(row_idx, row_idx + rowspan):
                    for c in range(col_idx, col_idx + colspan):
                        grid[(r, c)] = node
                        max_col_idx = max(max_col_idx, c)

                col_idx += colspan
            row_idx += 1

        row_count = row_idx
        col_count = max_col_idx + 1
        return grid, row_count, col_count

    def _build_adjacency_graph(self, grid: Dict[Tuple[int, int], TableNode], row_count: int, col_count: int) -> Tuple[List[TableNode], List[TableEdge]]:
        """
        가상 그리드의 인접성을 분석하여 유일한 노드 리스트와 중복되지 않은 인접성 엣지를 빌드합니다.
        """
        unique_nodes_map = {}
        for node in grid.values():
            unique_nodes_map[node.id] = node
        nodes = list(unique_nodes_map.values())

        edges: Set[TableEdge] = set()

        for r in range(row_count):
            for c in range(col_count):
                current_node = grid.get((r, c))
                if not current_node:
                    continue

                # 1. 우측 인접 분석 (RIGHT / LEFT)
                right_node = grid.get((r, c + 1))
                if right_node and right_node.id != current_node.id:
                    edges.add(TableEdge(current_node.id, right_node.id, "RIGHT"))
                    edges.add(TableEdge(right_node.id, current_node.id, "LEFT"))

                # 2. 하단 인접 분석 (DOWN / UP)
                down_node = grid.get((r + 1, c))
                if down_node and down_node.id != current_node.id:
                    edges.add(TableEdge(current_node.id, down_node.id, "DOWN"))
                    edges.add(TableEdge(down_node.id, current_node.id, "UP"))

        return nodes, list(edges)

    def _find_ancestors(self, start_node_id: str, direction: str, node_map: Dict[str, TableNode], in_edges: Dict[str, List[TableEdge]], out_edges: Dict[str, List[TableEdge]], section_ids: Set[str] = None) -> List[TableNode]:
        """
        특정 방향의 인접 엣지(UP, LEFT)를 추적하여 도달 가능한 조상 헤더 노드 체인을 DFS로 탐색합니다.
        물리적 좌표 제약(UP이면 y좌표 감소 및 x좌표 겹침, LEFT면 x좌표 감소 및 y좌표 겹침)을 엄격히 적용합니다.
        섹션 헤더 노드(기하학적 장벽)를 만나면 위쪽 탐색을 즉시 차단(Barrier Rule)합니다.
        """
        ancestors = []
        visited = set()
        sec_ids = section_ids or set()

        def dfs(curr_id):
            visited.add(curr_id)
            curr_node = node_map[curr_id]
            
            candidates = []
            
            # in_edges (target 이 curr_id 인 엣지들)
            for edge in in_edges.get(curr_id, []):
                if direction == "UP" and edge.direction == "DOWN":
                    candidates.append(edge.source)
                elif direction == "LEFT" and edge.direction == "RIGHT":
                    candidates.append(edge.source)

            # out_edges (source 가 curr_id 인 엣지들)
            for edge in out_edges.get(curr_id, []):
                if edge.direction == direction:
                    candidates.append(edge.target)

            for p_id in candidates:
                if p_id in visited:
                    continue
                p_node = node_map[p_id]
                
                # 엄격한 물리적 인접 및 방향 필터링
                if direction == "UP":
                    # 부모는 현재 노드보다 위에 있어야 함 (row index가 작아야 함)
                    is_above = p_node.row_range[1] < curr_node.row_range[0]
                    # 열 범위가 겹쳐야 함
                    cols_overlap = max(p_node.col_range[0], curr_node.col_range[0]) <= min(p_node.col_range[1], curr_node.col_range[1])
                    if is_above and cols_overlap:
                        if p_node.is_header:
                            ancestors.append(p_node)
                        # 장벽 규칙: 부모가 섹션 헤더인 경우 더 이상 위로 전진하지 않음
                        if p_id not in sec_ids:
                            dfs(p_id)
                elif direction == "LEFT":
                    # 부모는 현재 노드보다 왼쪽에 있어야 함 (col index가 작아야 함)
                    is_left = p_node.col_range[1] < curr_node.col_range[0]
                    # 행 범위가 겹쳐야 함
                    rows_overlap = max(p_node.row_range[0], curr_node.row_range[0]) <= min(p_node.row_range[1], curr_node.row_range[1])
                    if is_left and rows_overlap:
                        if p_node.is_header:
                            ancestors.append(p_node)
                        # 장벽 규칙: 부모가 섹션 헤더인 경우 더 이상 왼쪽으로 전진하지 않음
                        if p_id not in sec_ids:
                            dfs(p_id)

        dfs(start_node_id)
        
        seen = set()
        unique_ancestors = []
        for a in ancestors:
            if a.id not in seen:
                seen.add(a.id)
                unique_ancestors.append(a)
        return unique_ancestors

    def parse_to_directed_graph(self, html_content: str) -> Tuple[List[TableNode], List[TableEdge]]:
        """
        HTML 콘텐츠에서 첫 번째 테이블을 찾아 RIGHT 와 DOWN 을 정방향으로 하는 유향 그래프(노드 및 엣지)를 반환합니다.
        """
        nodes, all_edges = self.parse_to_graph(html_content)
        # RIGHT 와 DOWN 방향의 엣지만 필터링
        directed_edges = [e for e in all_edges if e.direction in ("RIGHT", "DOWN")]
        return nodes, directed_edges

    def generate_adjacency_matrix(self, nodes: List[TableNode], edges: List[TableEdge]) -> Dict[str, Any]:
        """
        노드 리스트와 유향 엣지 리스트를 기반으로 연결 행렬(Adjacency Matrix)을 생성합니다.
        출력 형식:
        {
            "node_ids": [node_id_1, node_id_2, ...],
            "node_values": [val_1, val_2, ...],
            "matrix": [[0, 1, ...], ...]
        }
        """
        # 노드 ID 순서로 정렬하여 인덱스 일관성 확보 (row_range[0], col_range[0] 순)
        sorted_nodes = sorted(nodes, key=lambda n: (n.row_range[0], n.col_range[0]))
        node_ids = [n.id for n in sorted_nodes]
        node_values = [n.value for n in sorted_nodes]
        
        node_to_idx = {node_id: idx for idx, node_id in enumerate(node_ids)}
        n = len(sorted_nodes)
        
        # Matrix 초기화 (0으로 채워진 N x N)
        matrix = [[0] * n for _ in range(n)]
        
        for edge in edges:
            if edge.source in node_to_idx and edge.target in node_to_idx:
                src_idx = node_to_idx[edge.source]
                tgt_idx = node_to_idx[edge.target]
                matrix[src_idx][tgt_idx] = 1 # 연결됨 표시
                
        return {
            "node_ids": node_ids,
            "node_values": node_values,
            "matrix": matrix
        }

