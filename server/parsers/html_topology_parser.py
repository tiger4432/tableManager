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
        :param is_header_fn: BeautifulSoup Tag 객체, row_idx, col_idx 를 인자로 받아 
                              해당 셀이 헤더인지 여부(bool)를 리턴하는 커스텀 판정 함수.
        """
        self.is_header_fn = is_header_fn or self._default_is_header

    def _default_is_header(self, tag, r: int = 0, c: int = 0) -> bool:
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
        
        # 4. Row Header 자동 지원: 숫자가 아닌 유의미한 텍스트 문자열이면서 마지막 열이 아닌 경우
        text_val = tag.text.strip()
        if text_val:
            try:
                float(text_val)
                is_numeric = True
            except ValueError:
                is_numeric = False
            
            if not is_numeric:
                table = tag.find_parent("table")
                if table:
                    max_cols = 0
                    for tr in table.find_all("tr", recursive=True):
                        cols_in_row = 0
                        for cell in tr.find_all(["td", "th"], recursive=False):
                            cols_in_row += int(cell.get("colspan", 1))
                        max_cols = max(max_cols, cols_in_row)
                    
                    if max_cols > 1 and c < max_cols - 1:
                        return True
                else:
                    if c == 0:
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
                row_idx += 1
                continue

            col_idx = 0
            for cell in cells:
                while (row_idx, col_idx) in grid:
                    col_idx += 1

                rowspan = int(cell.get("rowspan", 1))
                colspan = int(cell.get("colspan", 1))

                node_id = f"cell_{row_idx}_{col_idx}_{node_counter}"
                node_counter += 1
                is_header = self.is_header_fn(cell, row_idx, col_idx)
                
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

    def parse_to_directed_graph(self, html_content: str, direction_type: str = "left_up") -> Tuple[List[TableNode], List[TableEdge]]:
        """
        HTML 콘텐츠에서 첫 번째 테이블을 찾아 유향 그래프(노드 및 엣지)를 반환합니다.
        :param direction_type: "left_up" (헤더 역추적용, LEFT & UP 엣지를 정방향으로 설정, 디폴트)
                               "right_down" (데이터 순방향 탐색용, RIGHT & DOWN 엣지를 정방향으로 설정)
        """
        nodes, all_edges = self.parse_to_graph(html_content)
        
        if direction_type == "left_up":
            target_directions = ("LEFT", "UP")
        elif direction_type == "right_down":
            target_directions = ("RIGHT", "DOWN")
        else:
            raise ValueError(f"Invalid direction_type: {direction_type}. Choose 'left_up' or 'right_down'.")
            
        directed_edges = [e for e in all_edges if e.direction in target_directions]
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

    def find_all_paths(self, start_node_id_or_value: str, nodes: List[TableNode], edges: List[TableEdge], by_value: bool = True, max_depth: Optional[int] = None) -> List[List[str]]:
        """
        특정 노드에서 시작하여 정방향 엣지를 따라 도달할 수 있는 모든 유효한 경로들의 리스트를 반환합니다.
        :param start_node_id_or_value: 출발 노드의 ID 또는 셀 텍스트 값
        :param by_value: True이면 셀 텍스트 값의 경로 리스트를, False이면 노드 ID의 경로 리스트를 반환
        :param max_depth: 경로 탐색 시 허용되는 최대 노드 깊이 (길이 제한)
        """
        node_map = {n.id: n for n in nodes}
        
        # 출발 노드 후보 탐색 (ID 매치 우선, 없으면 텍스트 값 매치)
        start_nodes = []
        if start_node_id_or_value in node_map:
            start_nodes.append(node_map[start_node_id_or_value])
        else:
            start_nodes = [n for n in nodes if n.value == start_node_id_or_value]
            
        if not start_nodes:
            return []

        # outgoing adjacency list 구축
        adj = {n.id: [] for n in nodes}
        for edge in edges:
            adj[edge.source].append(edge.target)

        all_paths = []

        def dfs(curr_id, current_path):
            current_path.append(curr_id)
            
            # max_depth 제한에 도달한 경우
            if max_depth is not None and len(current_path) >= max_depth:
                if by_value:
                    all_paths.append([node_map[node_id].value for node_id in current_path])
                else:
                    all_paths.append(list(current_path))
            else:
                neighbors = adj.get(curr_id, [])
                
                # 순환(cycle)을 방지하기 위해 방문하지 않은 이웃만 탐색
                unvisited_neighbors = [nb for nb in neighbors if nb not in current_path]
                
                if not unvisited_neighbors:
                    # 더 이상 나갈 엣지가 없는 리프에 도달 -> 경로 저장
                    if by_value:
                        all_paths.append([node_map[node_id].value for node_id in current_path])
                    else:
                        all_paths.append(list(current_path))
                else:
                    for neighbor in unvisited_neighbors:
                        dfs(neighbor, current_path)
            
            # Backtrack
            current_path.pop()

        for start_node in start_nodes:
            dfs(start_node.id, [])

        return all_paths

    def find_all_paths_for_all_nodes(self, nodes: List[TableNode], edges: List[TableEdge], by_value: bool = True, max_depth: Optional[int] = None) -> Dict[str, List[List[str]]]:
        """
        테이블 내의 모든 노드 각각에 대해 find_all_paths를 일괄 수행하여 딕셔너리 형태로 반환합니다.
        :param nodes: 노드 리스트
        :param edges: 유향 엣지 리스트
        :param by_value: True이면 셀 텍스트 값을 키 및 경로 요소로 사용, False이면 노드 ID를 사용
        :param max_depth: 경로 탐색 시 허용되는 최대 노드 깊이 (길이 제한)
        """
        results = {}
        for node in nodes:
            key = node.value if by_value else node.id
            
            # 개별 노드 ID를 시작점으로 지정해 경로 수집
            paths = self.find_all_paths(node.id, nodes, edges, by_value=by_value, max_depth=max_depth)
            
            if key in results:
                # 동일한 키(by_value=True 시 동일 값 셀 대응)가 있다면 경로 중복 방지하여 누적
                for p in paths:
                    if p not in results[key]:
                        results[key].append(p)
            else:
                results[key] = paths
                
        return results


class HTMLMatrixTableParser:
    """
    HTML 2D 매트릭스 테이블(X축/Y축 인덱스가 있고 상단에 계층 메타데이터가 있는 격자형 표)을
    평탄화된 관계형 데이터 레코드 목록으로 파싱하는 클래스입니다.
    """
    def __init__(self, is_header_fn=None):
        self.graph_parser = HTMLTableGraphParser(is_header_fn=is_header_fn)

    def parse_matrix_to_records(self, html_content: str) -> List[Dict[str, Any]]:
        soup = BeautifulSoup(html_content, "html.parser")
        table_tag = soup.find("table")
        if not table_tag:
            return []

        # 1. 2D 가상 그리드 구성
        grid, row_count, col_count = self.graph_parser._reconstruct_2d_grid(table_tag)
        if not grid:
            return []

        # 2. 인접 그래프 구성 및 매핑 사전 획득
        nodes, edges = self.graph_parser._build_adjacency_graph(grid, row_count, col_count)
        
        node_map = {n.id: n for n in nodes}
        in_edges = {n.id: [] for n in nodes}
        out_edges = {n.id: [] for n in nodes}
        for edge in edges:
            out_edges[edge.source].append(edge)
            in_edges[edge.target].append(edge)

        # A cell that spans most of the table width is a section header (the TITLE band).
        wide_threshold = int(col_count * 0.7)

        def _is_section_wide(n: TableNode) -> bool:
            return n.col_span > 1 and n.col_span >= wide_threshold

        def _is_int(text: str) -> bool:
            try:
                int(text)
                return True
            except (TypeError, ValueError):
                return False

        def _is_unmerged(n: TableNode) -> bool:
            """One cell, one coordinate.

            THE measured fact this whole file leans on, stated once. Across the entire
            archived corpus (19 files, 4 header shapes): every corner and every axis
            tick is 1x1, and every header-band cell is merged - 0 exceptions either
            way. Ruler cells are unmerged; header cells are not.
            """
            return n.row_span == 1 and n.col_span == 1

        def _ruler_row(r: int):
            """The X-axis tick cells of row `r`, or None if `r` is not ruler-shaped.

            Recognised by SHAPE, not by the fact that it holds numbers - the header
            band holds numbers too (a lot id, a wafer id, and after the 2026-08-04
            ruling, every `slot`). Its shape: an UNMERGED corner cell at column 0 that
            is NOT a coordinate, followed by two or more UNMERGED cells to its right
            that all are.
            """
            corner = grid.get((r, 0))
            if corner is None or not _is_unmerged(corner) or _is_int(corner.value):
                return None
            ticks = []
            seen = {corner.id}
            for c in range(1, col_count):
                node = grid.get((r, c))
                if node is None or node.id in seen:
                    continue
                seen.add(node.id)
                if not _is_unmerged(node) or not _is_int(node.value):
                    return None
                ticks.append(node)
            return ticks if len(ticks) >= 2 else None

        # 3. 격자 원점(=X축 눈금 행) 확정 — 서로 독립인 두 유도가 **일치할 때만** 채택한다.
        #
        #    THE GRID ORIGIN IS DERIVED TWICE, ON PURPOSE.
        #
        #    Each derivation alone is a guess, and each has a documented blind spot at
        #    the OPPOSITE end of the document:
        #
        #      TOP-ANCHORED (`_ruler_row`, scanning downward) reads the shape of a row.
        #        Blind spot: the TOP of a spreadsheet is exactly where operator junk
        #        lives. A `SLOT | 2 | 3 | 6 | ...` row, a `DATE | 2026 | 6 | 20` row, a
        #        two-entry legend - each is ruler-shaped, sits above the real ruler, and
        #        wins the top-down race. Measured: a SLOT row yields the right record
        #        count, the right values and a SILENTLY WRONG X.
        #
        #      BOTTOM-ANCHORED (the Y ruler's topmost label, minus one) reads where the
        #        grid begins. This is the derivation that shipped before 2026-08-04.
        #        Blind spot: any integer cell in column 0 above the grid - a numeric
        #        TITLE, a numeric GROUP label - drags the origin up into the header band.
        #        (Restricting it to UNMERGED cells closes the observed cases, because
        #        titles and group labels are merged, but it cannot see junk that is
        #        genuinely 1x1.)
        #
        #    The two fail on DISJOINT inputs, so agreement is real evidence and
        #    disagreement means the document is not the shape this parser understands.
        #    On disagreement we REFUSE - no records, and a named reason - rather than
        #    pick a winner. A wrong grid origin is not a degraded parse: X and Y are the
        #    business key (`composite_key_source: [base, x, y]`), so a plausible-looking
        #    wrong answer files every cell of the map under coordinates that do not
        #    exist. Zero rows with a stated reason is strictly better than that.
        top_anchor, top_ticks = None, []
        for r in range(row_count):
            ticks = _ruler_row(r)
            if ticks:
                top_anchor, top_ticks = r, ticks
                break

        y_label_rows = [n.row_range[0] for n in nodes
                        if n.col_range[0] == 0 and _is_unmerged(n) and _is_int(n.value)]
        bottom_anchor = (min(y_label_rows) - 1) if y_label_rows else None

        if top_anchor is None or bottom_anchor is None or top_anchor != bottom_anchor:
            # ASCII only - this reaches a cp949 console. One line, named reason, per
            # call (a refusal is by definition not the steady state, so there is no
            # repetition to suppress).
            if top_anchor is None and bottom_anchor is None:
                reason = ("no X-axis ruler row and no Y-axis labels were found; this "
                          "table does not have the shape of a 2D matrix map")
            elif top_anchor is None:
                reason = (f"no row has the shape of an X-axis ruler (unmerged "
                          f"non-numeric corner + 2 or more unmerged integer ticks), "
                          f"while the Y-axis labels imply the ruler is row "
                          f"{bottom_anchor}")
            elif bottom_anchor is None:
                reason = (f"row {top_anchor} is ruler-shaped but no unmerged integer "
                          f"labels sit in column 0, so there is no Y axis to confirm it")
            else:
                reason = (f"the two derivations disagree - row shape says the ruler is "
                          f"row {top_anchor} (ticks {[n.value for n in top_ticks]}), "
                          f"the Y-axis labels say row {bottom_anchor}. Something "
                          f"ruler-shaped sits above the real grid")
            logger.warning(
                "[matrix] REFUSED to parse: %s. Returning 0 records rather than a "
                "plausible-looking wrong grid origin, because X and Y are part of the "
                "business key.", reason
            )
            return []

        x_row_idx = top_anchor
        x_axis_nodes = top_ticks
        y_axis_nodes = [n for n in nodes
                        if n.col_range[0] == 0 and _is_unmerged(n) and _is_int(n.value)
                        and n.row_range[0] > x_row_idx]

        # 4. [Header predicate] Re-classify the header role STRUCTURALLY for this matrix.
        #
        #    "Is this a header cell?" must NOT be answered by "does this parse as a
        #    number." A lot id, a slot number and a wafer id are all legitimately numeric.
        #    `_default_is_header` rule 4 answers it lexically, and in a matrix table that
        #    is wrong in BOTH directions, measured on the real archive:
        #      - a numeric header value (`BDIE / LOT / 12312`) dropped out of the header
        #        set, the LEFT-ancestor chain shifted one cell right, and the next group
        #        label was consumed as BDIE's LOT value -> map key silently became "CDIE";
        #      - a non-numeric BIN letter inside the grid was promoted to a header, so
        #        grid data leaked back out as a phantom meta key ("F_AAA").
        #
        #    The real relation is 2D and positional: this document declares its own grid
        #    origin through the axis ticks, so the header block is exactly the rows
        #    STRICTLY ABOVE the X-axis tick row. Three conditions, no lexical test:
        #
        #      - above the ruler row (position);
        #      - non-empty - the LEFT-ancestor chain counts ancestors, and a blank
        #        spacer cell must not lengthen it;
        #      - MERGED - the other half of the one measured fact in `_is_unmerged`.
        #        A ruler-shaped row that the origin cross-check accepted (because it is
        #        ragged, or padded with blanks, so it never qualified as a ruler) still
        #        sits inside the band, and its 1x1 cells would otherwise form a
        #        GROUP/KEY/VALUE chain indistinguishable from a real one: a padded
        #        `DATE | 2026 | 6 | 20` row produced the phantom key `DATE_2026: "6"`.
        #        Requiring the band to be merged is what keeps operator junk out of the
        #        header without asking what its text looks like.
        #
        #    Only this matrix view is re-classified. `_default_is_header` is untouched, so
        #    `extract_semantic_tuples` and any caller-supplied `is_header_fn` keep their
        #    behaviour.
        for node in nodes:
            node.is_header = (bool(node.value)
                              and node.row_range[1] < x_row_idx
                              and not _is_unmerged(node))

        # 5. 최상단 섹션 헤더(TITLE) 추출 (colspan이 가로폭의 70% 이상인 최상위 헤더)
        title = "Default"
        section_headers = [n for n in nodes if n.is_header and _is_section_wide(n)]
        if section_headers:
            section_headers.sort(key=lambda n: n.row_range[0])
            title = section_headers[0].value

        # 6. 공통 메타데이터(BDIE_LOT, BDIE_WF 등) 추출
        # LEFT 방향 조상을 찾되, 열 정렬 순서대로 순회하며 이미 값으로 결정된 노드들은 장벽(sec_ids)으로 작용시킵니다.
        # 또한, 반환된 조상 목록에서도 기 수집된 값 노드들은 제거(필터링)하여 우회 누수를 차단합니다.
        meta_nodes = [n for n in nodes if n.is_header and n.value]
        meta_nodes = [
            n for n in meta_nodes 
            if (not section_headers or n.id != section_headers[0].id) and
               n.id not in [x.id for x in y_axis_nodes] and
               n.id not in [x.id for x in x_axis_nodes]
        ]
        meta_nodes.sort(key=lambda n: n.col_range[0])

        meta = {}
        detected_value_ids = set()
        for node in meta_nodes:
            ancestors = self.graph_parser._find_ancestors(node.id, "LEFT", node_map, in_edges, out_edges, detected_value_ids)
            ancestors = [a for a in ancestors if a.id not in detected_value_ids]
            
            # 메타데이터 계층구조 [Key, Group] 탐지 (길이가 정확히 2인 조상 체인)
            if len(ancestors) == 2:
                ancestors.sort(key=lambda n: n.col_range[0])
                ancestors_vals = [a.value for a in ancestors if a.value]
                if ancestors_vals:
                    meta_key = "_".join(ancestors_vals)
                    meta[meta_key] = node.value
                    detected_value_ids.add(node.id)

        # 7. X, Y축 눈금 좌표를 순회하며 2D 데이터 셀 값 추출 및 평탄화 레코드 생성
        y_axis_nodes.sort(key=lambda n: n.row_range[0])
        x_axis_nodes.sort(key=lambda n: n.col_range[0])

        records = []
        for y_node in y_axis_nodes:
            r_y = y_node.row_range[0]
            y_val = int(y_node.value)
            
            for x_node in x_axis_nodes:
                c_x = x_node.col_range[0]
                x_val = int(x_node.value)
                
                data_node = grid.get((r_y, c_x))
                if data_node:
                    if data_node.id == y_node.id or data_node.id == x_node.id:
                        continue
                    
                    val = data_node.value
                    
                    record = {
                        "TITLE": title,
                    }
                    record.update(meta)
                    record.update({
                        "X": x_val,
                        "Y": y_val,
                        "VALUE": val
                    })
                    records.append(record)
                    
        return records


