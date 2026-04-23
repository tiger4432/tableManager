"""
panel_filter.py
컬럼 필터 및 도구 모음 패널 (v1.5)

- QVBoxLayout 기반의 2행(Two-Row) 레이아웃
- Row 1: 검색 필드, 검색 범위 설정, 결과 카운터
- Row 2: 액션 버튼 그룹 (Add/Export/Upload/Sort/Load)
"""
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QLineEdit, QLabel, QVBoxLayout, QHBoxLayout, 
    QSizePolicy, QPushButton, QToolButton, QMenu
)
from PySide6.QtCore import Qt, QSortFilterProxyModel, Signal, QTimer
from PySide6.QtGui import QAction, QIcon


class DuplicateFilterProxyModel(QSortFilterProxyModel):
    """
    원본 모델(ApiLazyTableModel)에서 중복으로 판명되어 
    {'_is_duplicate': True} 마커가 박힌 행들을 시각적으로 숨기는 프록시 모델입니다.
    """
    def filterAcceptsRow(self, source_row: int, source_parent) -> bool:
        model = self.sourceModel()
        if not hasattr(model, "_data") or source_row >= len(model._data):
            return True
        
        row_data = model._data[source_row]
        # 중복 마커가 있으면 필터링 (숨김)
        if isinstance(row_data, dict) and row_data.get("_is_duplicate"):
            return False
            
        # 기본 필터링 (부모 클래스 로직 수행 - 필요 시 검색어 필터링 등)
        return super().filterAcceptsRow(source_row, source_parent)


class FilterToolBar(QWidget):
    """상단 2행 레이아웃 패널 — 검색 및 도구 모음."""
    
    addTabRequested = Signal()
    addRowRequested = Signal()
    exportRequested = Signal()
    searchRequested = Signal(str, str)
    uploadRequested = Signal()
    sortLatestChanged = Signal(bool)
    batchLoadRequested = Signal(int)
    copyHeaderChanged = Signal(bool)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        
        # ── 메인 레이아웃 (2행 구성) ──
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(25, 18, 25, 18) # 좌우 여백 확대
        self._main_layout.setSpacing(12) # 행 간격 확대
        
        self.setStyleSheet("""
            QWidget { background: #1e1e2e; }
            QLabel { color: #bac2de; font-weight: 500; font-size: 13px; }
            QLineEdit {
                background: #1e1e2e; color: #cdd6f4; border: 1px solid #45475a;
                border-radius: 6px; padding: 6px 12px; font-size: 13px; min-width: 400px;
            }
            QLineEdit:focus { border-color: #89b4fa; background: #313244; }
            QPushButton { font-weight: bold; border-radius: 6px; padding: 6px 14px; font-size: 12px; }
            QToolButton {
                background: #313244; color: #cdd6f4; font-weight: bold;
                border-radius: 6px; padding: 6px 14px; font-size: 12px;
            }
            QToolButton:hover { background: #45475a; }
        """)

        # ── [1행] 검색 및 상태 표시줄 ────────────────────────────────
        self._row1_layout = QHBoxLayout()
        self._row1_layout.setSpacing(10)
        
        # 검색창
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("검색어 입력 (정규식 지원 / 전체 실시간 필터링)...")
        self._search_box.setClearButtonEnabled(True)
        self._row1_layout.addWidget(self._search_box)
        
        # 검색 범위 버튼
        self._scope_btn = QToolButton()
        self._scope_btn.setText("🔍 검색 범위")
        self._scope_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._scope_menu = QMenu(self)
        self._scope_menu.setStyleSheet("""
            QMenu { background: #1e1e2e; color: #cdd6f4; border: 1px solid #313244; }
            QMenu::item { padding: 6px 24px; }
            QMenu::item:selected { background: #313244; }
            QMenu::item:checked { color: #a6e3a1; }
        """)
        self._scope_btn.setMenu(self._scope_menu)
        self._row1_layout.addWidget(self._scope_btn)
        
        self._row1_layout.addStretch()
        
        # 결과 카운터 (고급스러운 태그 스타일)
        self._count_label = QLabel("  Loaded: 0 / Total: 0  ")
        self._count_label.setStyleSheet("""
            QLabel {
                background: #1e1e2e;
                color: #a6e3a1;
                border: 1px solid #313244;
                border-radius: 12px;
                padding: 4px 16px;
                font-family: 'JetBrains Mono', 'Consolas';
                font-size: 12px;
                font-weight: bold;
            }
        """)
        self._row1_layout.addWidget(self._count_label)
        
        self._main_layout.addLayout(self._row1_layout)

        # ── [2행] 액션 버튼 그룹 ────────────────────────────────────
        self._row2_container = QWidget()
        self._row2_layout = QHBoxLayout(self._row2_container)
        self._row2_layout.setContentsMargins(0, 0, 0, 0)
        self._row2_layout.setSpacing(10) # 모든 버튼 간격 일정하게
        
        # 1. 관리 그룹
        self._add_btn = QPushButton("+ 새 탭")
        self._add_btn.setStyleSheet("background: #a6e3a1; color: #1e1e2e;")
        self._add_btn.clicked.connect(self.addTabRequested.emit)
        self._row2_layout.addWidget(self._add_btn)

        self._add_row_btn = QPushButton("➕ 행 추가")
        self._add_row_btn.setStyleSheet("background: #89b4fa; color: #1e1e2e;")
        self._add_row_btn.clicked.connect(self.addRowRequested.emit)
        self._row2_layout.addWidget(self._add_row_btn)
        
        # 2. 데이터 그룹
        self._export_btn = QPushButton("📥 CSV 추출")
        self._export_btn.setStyleSheet("background: #fab387; color: #1e1e2e;")
        self._export_btn.clicked.connect(self.exportRequested.emit)
        self._row2_layout.addWidget(self._export_btn)

        self._upload_btn = QPushButton("📤 Upload")
        self._upload_btn.setStyleSheet("background: #cba6f7; color: #1e1e2e;")
        self._upload_btn.clicked.connect(self.uploadRequested.emit)
        self._row2_layout.addWidget(self._upload_btn)
        
        # 3. 최적화 그룹
        self._sort_btn = QPushButton("⚡ 최신순 ON")
        self._sort_btn.setCheckable(True)
        self._sort_btn.setChecked(True)
        self._sort_btn.clicked.connect(self._on_sort_toggled)
        self._row2_layout.addWidget(self._sort_btn)

        self._batch_btn = QPushButton("⚡ 1k 로드")
        self._batch_btn_style = """
            QPushButton { background: #94e2d5; color: #111111; }
            QPushButton:disabled { background: #45475a; color: #7f849c; }
        """
        self._batch_btn.setStyleSheet(self._batch_btn_style)
        self._batch_btn.clicked.connect(self._on_batch_btn_clicked)
        self._row2_layout.addWidget(self._batch_btn)
        
        self._copy_header_btn = QPushButton("📋 헤더 포함")
        self._copy_header_btn.setCheckable(True)
        self._copy_header_btn.setChecked(False)
        self._copy_header_btn.clicked.connect(self._on_copy_header_toggled)
        self._row2_layout.addWidget(self._copy_header_btn)
        
        self._row2_layout.addStretch()
        
        self._main_layout.addWidget(self._row2_container)

        # ── 내부 상태 및 로직 ───────────────────────────────────────
        self._selected_cols = set()
        self._proxies: dict[str, QSortFilterProxyModel] = {} # [Refactor] list -> dict
        self._active_proxy: QSortFilterProxyModel | None = None
        self._sort_latest = True
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._emit_search_requested)
        self._search_box.textChanged.connect(self._on_text_changed)
        
        self._update_sort_btn_style()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_proxy(self, table_name: str, source_model) -> QSortFilterProxyModel:
        """
        원본 모델을 DuplicateFilterProxyModel 로 래핑하여 중복 처리를 지원합니다.
        """
        proxy = DuplicateFilterProxyModel(self)
        proxy.setSourceModel(source_model)
        proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        proxy.setFilterKeyColumn(-1)          # 모든 컬럼 검색
        self._proxies[table_name] = proxy     # [Refactor] 테이블 명을 키로 하여 저장

        # [Req] Loaded 수치는 실시간 데이터 삽입/삭제가 아닌, 서버 페칭 완료 시점에만 갱신
        if hasattr(source_model, "batch_fetch_finished"):
            source_model.batch_fetch_finished.connect(self._update_count_label)
        
        # [신규] 원본 모델의 실시간 전체(Total) 카운트 시그널 연결
        if hasattr(source_model, "total_count_changed"):
            source_model.total_count_changed.connect(self._update_count_label)


        self._active_proxy = proxy

        return proxy

    def _request_count_update(self, *args):
        """10ms 뒤에 카운트 레이블을 갱신합니다. (Debounce)"""
        QTimer.singleShot(10, self._update_count_label)

    def set_active_proxy(self, proxy: QSortFilterProxyModel | None):
        """현재 활성 탭이 바뀔 때 MainWindow에서 호출하여 모드 및 데이터를 전환합니다."""
        self._active_proxy = proxy
        
        # ── [Phase 73.8] 모드 전환 (시스템 vs 테이블) ──
        is_table = proxy is not None
        self._update_ui_mode(is_table)

        if is_table:
            source = proxy.sourceModel()
            # 글로벌 정렬 상태 주입
            if source and hasattr(source, "set_sort_latest"):
                source.set_sort_latest(self._sort_latest)

            # 탭 전환 시 해당 모델의 검색 범위 복구
            if source and hasattr(source, "_search_cols_state"):
                self._selected_cols = set(source._search_cols_state)
            else:
                self._selected_cols = set()
            
            self._refresh_scope_menu()
            self._update_count_label()
        else:
            self._selected_cols = set()

    def _update_ui_mode(self, is_table: bool):
        """테이블 모드와 시스템 모드(대시보드 등)에 따라 UI 구성 요소를 가립니다."""
        # 1행 제어: 검색창, 범위 버튼, 카운트 레이블
        self._search_box.setVisible(is_table)
        self._scope_btn.setVisible(is_table)
        self._count_label.setVisible(is_table)
        
        # 2행 제어: 테이블 관련 액션 버튼들
        self._add_row_btn.setVisible(is_table)
        self._export_btn.setVisible(is_table)
        self._upload_btn.setVisible(is_table)
        self._sort_btn.setVisible(is_table)
        self._batch_btn.setVisible(is_table)
        self._copy_header_btn.setVisible(is_table)
        
        # '+ 새 탭'은 시스템/테이블 공용
        self._add_btn.setVisible(True)

        # 시스템 모드일 때 레이아웃 간격 조정
        self._main_layout.setSpacing(12 if is_table else 0)
        if not is_table:
            self._search_box.clear()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _on_text_changed(self, text: str):
        # [Phase 73.8] 검색어 입력 즉시 카운트 레이블을 '검색 중...' 상태로 변경하여 반응성 확보
        self._count_label.setText("  Searching...  ")
        
        # [Phase 73.5] 기존 로컬 필터링 비활성화 유지
        
        # 타이머 재시작 (마지막 입력 후 500ms 뒤에 서버 검색 요청)
        self._search_timer.start(500)

    def _emit_search_requested(self):
        query = self._search_box.text()
        cols_str = ",".join(sorted(list(self._selected_cols))) if self._selected_cols else ""
        
        # [Phase 73.8] 검색 수행 시점의 컬럼 선택 상태를 소스 모델에 보관 (영구 보존 원칙)
        if self._active_proxy:
            source = self._active_proxy.sourceModel()
            if source and hasattr(source, "_search_cols_state"):
                source._search_cols_state = list(self._selected_cols)
                
        self.searchRequested.emit(query, cols_str)

    def _refresh_scope_menu(self):
        """현재 활성 모델의 컬럼 정보를 기반으로 검색 범위 메뉴를 갱신합니다."""
        self._scope_menu.clear()
        if not self._active_proxy: return
        
        source = self._active_proxy.sourceModel()
        if not source: return
        
        cols = getattr(source, "_columns", [])
        
        from PySide6.QtGui import QAction
        for col in cols:
            action = QAction(col.upper(), self._scope_menu)
            action.setCheckable(True)
            
            # [Phase 73.8] 복구된 _selected_cols 상태를 기반으로 체크박스 렌더링
            action.setChecked(col in self._selected_cols)
            
            # 클로저 이슈 방지를 위한 default argument 사용
            action.triggered.connect(lambda checked, c=col: self._on_scope_toggled(c, checked))
            self._scope_menu.addAction(action)

    def _on_batch_btn_clicked(self):
        """1K 로드 클릭 시 시각적 피드백 제공 및 시그널 발생."""
        self._batch_btn.setEnabled(False)
        self._batch_btn.setText("⏳ Loading...")
        self.batchLoadRequested.emit(1000)
        
        # 안전장치: 5초 뒤 강제 복구 (네트워크 오류 대비)
        QTimer.singleShot(5000, self.reset_batch_btn)

    def reset_batch_btn(self):
        """버튼을 원래 상태로 복구합니다."""
        self._batch_btn.setEnabled(True)
        self._batch_btn.setText("⚡ 1k 로드")

    def _on_scope_toggled(self, col: str, checked: bool):
        if checked:
            self._selected_cols.add(col)
        else:
            if col in self._selected_cols:
                self._selected_cols.remove(col)
        
        # 필터링 즉시 재실행 (Debounce 적용)
        self._search_timer.start(500)

    def _update_count_label(self):
        proxy = self._active_proxy
        if not proxy:
            self._count_label.setText("")
            return
            
        source = proxy.sourceModel()
        if not source: return
        
        # [Phase 73.8] 용어 표준화: Matches(전체 검색 결과) / Loaded(현재 화면에 로드됨)
        exposed = getattr(source, "_exposed_rows", proxy.rowCount())
        total = getattr(source, "_total_count", exposed)
        
        self._count_label.setText(f" Loaded: {exposed:,} /  Total: {total:,}")

    def _on_sort_toggled(self, checked: bool):
        self._sort_latest = checked
        self._update_sort_btn_style()
        self.sortLatestChanged.emit(checked)

    def _update_sort_btn_style(self):
        if self._sort_latest:
            self._sort_btn.setText("⚡ 최신순 ON")
            self._sort_btn.setStyleSheet("""
                QPushButton { background: #f9e2af; color: #1e1e2e; font-weight: bold; border-radius: 4px; padding: 4px 12px; }
                QPushButton:hover { background: #f2cdcd; }
            """)
        else:
            self._sort_btn.setText("⏸ 정렬 OFF")
            self._sort_btn.setStyleSheet("""
                QPushButton { background: #45475a; color: #cdd6f4; font-weight: bold; border-radius: 4px; padding: 4px 12px; }
                QPushButton:hover { background: #585b70; }
            """)

    def _on_copy_header_toggled(self, checked: bool):
        self._update_copy_header_btn_style()
        self.copyHeaderChanged.emit(checked)

    def _update_copy_header_btn_style(self):
        if self._copy_header_btn.isChecked():
            self._copy_header_btn.setText("📋 헤더 포함 ON")
            self._copy_header_btn.setStyleSheet("""
                QPushButton { background: #89dceb; color: #1e1e2e; font-weight: bold; border-radius: 4px; padding: 4px 12px; }
                QPushButton:hover { background: #94e2d5; }
            """)
        else:
            self._copy_header_btn.setText("📋 헤더 포함 OFF")
            self._copy_header_btn.setStyleSheet("""
                QPushButton { background: #45475a; color: #cdd6f4; font-weight: bold; border-radius: 4px; padding: 4px 12px; }
                QPushButton:hover { background: #585b70; }
            """)
