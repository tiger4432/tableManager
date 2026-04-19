"""
panel_filter.py
컬럼 필터 툴바 (PanelUIExpert 스킬 규칙 2번 준수)

- QToolBar 기반의 FilterToolBar
- QSortFilterProxyModel 을 통해 원본 모델을 수정하지 않고 실시간 필터링
- QLineEdit 입력 → filterRegularExpression() 갱신
- 필터 적용된 프록시 모델을 반환(TableView.setModel 에 사용)
"""

from __future__ import annotations

from PySide6.QtWidgets import QToolBar, QLineEdit, QLabel, QWidget, QSizePolicy, QPushButton
from PySide6.QtCore import Qt, QSortFilterProxyModel, Signal, QTimer
from PySide6.QtGui import QAction


class FilterToolBar(QToolBar):
    """상단 툴바 — 텍스트 검색으로 테이블 행을 실시간 필터링."""
    
    # ── Agent E v3: 새 탭 추가 요청 시그널 ──
    addTabRequested = Signal()
    # ── Agent E v4: 새 행 추가 요청 시그널 ──
    addRowRequested = Signal()
    # ── CSV 익스포트 요청 시그널 ──
    exportRequested = Signal()
    # ── 글로벌 서버 사이드 검색 요청 시그널 ──
    # [Phase 73.7] 검색어와 명시적 컬럼 리스트(comma separated)를 함께 전달
    searchRequested = Signal(str, str)
    # ── 파일 업로드 요청 시그널 ──
    uploadRequested = Signal()
    # ── 최신순 정렬 토글 시그널 ──
    sortLatestChanged = Signal(bool)
    # ── 일괄 로드 요청 시그널 ──
    batchLoadRequested = Signal(int)

    def __init__(self, parent: QWidget | None = None):
        super().__init__("필터", parent)
        self.setMovable(False)
        self.setFloatable(False)
        self.setStyleSheet("""
            QToolBar { 
                background: #11111b; 
                border-bottom: 1px solid #313244; 
                spacing: 12px; 
                padding: 12px 20px; 
                min-height: 60px;
            }
            QLabel { color: #bac2de; font-weight: 500; font-size: 13px; }
            QLineEdit {
                background: #1e1e2e; 
                color: #cdd6f4; 
                border: 1px solid #45475a;
                border-radius: 6px; 
                padding: 6px 12px; 
                font-size: 13px; 
                min-width: 300px;
            }
            QLineEdit:focus { border-color: #89b4fa; background: #313244; }
            
            QPushButton {
                font-weight: bold;
                border-radius: 6px;
                padding: 6px 16px;
                font-size: 12px;
            }
        """)

        # 검색창 (라벨 대신 Placeholder 사용)

        # 검색창
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("검색어 입력 (정규식 지원)...")
        self._search_box.setClearButtonEnabled(True)
        self.addWidget(self._search_box)

        # [Phase 73.7] 검색 대상 컬럼 선택 버튼 (Dropdown)
        from PySide6.QtWidgets import QToolButton, QMenu
        from PySide6.QtGui import QAction
        
        self._scope_btn = QToolButton()
        self._scope_btn.setText("🔍 검색 범위")
        self._scope_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._scope_btn.setStyleSheet("""
            QToolButton {
                background: #313244; color: #cdd6f4; font-weight: bold;
                border-radius: 4px; padding: 6px 12px; font-size: 12px; margin-left: 4px;
            }
            QToolButton::menu-indicator { image: none; }
            QToolButton:hover { background: #45475a; }
        """)
        
        self._scope_menu = QMenu(self)
        self._scope_menu.setStyleSheet("""
            QMenu { background: #1e1e2e; color: #cdd6f4; border: 1px solid #313244; }
            QMenu::item { padding: 4px 24px; }
            QMenu::item:selected { background: #313244; }
            QMenu::item:checked { color: #a6e3a1; }
        """)
        self._scope_btn.setMenu(self._scope_menu)
        self.addWidget(self._scope_btn)
        
        self._selected_cols = set() # 현재 선택된 검색 대상 컬럼

        # 오른쪽 여백
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.addWidget(spacer)

        # 결과 카운터 레이블
        self._count_label = QLabel("")
        self._count_label.setStyleSheet("color: #a6e3a1; font-size: 11px; margin-right: 10px;")
        self.addWidget(self._count_label)

        # ── Agent E v3: 새 탭 추가 버튼 ──
        self._add_btn = QPushButton("+ 새 탭")
        self._add_btn.setToolTip("새 테이블 탭 추가")
        self._add_btn.setStyleSheet(
            "QPushButton {"
            "  background: #a6e3a1; color: #1e1e2e; font-weight: bold;"
            "  border-radius: 4px; padding: 4px 12px; font-size: 12px;"
            "}"
            "QPushButton:hover { background: #94e2d5; }"
        )
        self._add_btn.clicked.connect(self.addTabRequested.emit)
        self.addWidget(self._add_btn)

        # ── Agent E v4: 새 행 추가 버튼 ──
        self._add_row_btn = QPushButton("➕ 행 추가")
        self._add_row_btn.setToolTip("활성 테이블에 새 행 추가")
        self._add_row_btn.setStyleSheet(
            "QPushButton {"
            "  background: #89b4fa; color: #1e1e2e; font-weight: bold;"
            "  border-radius: 4px; padding: 4px 12px; font-size: 12px;"
            "}"
            "QPushButton:hover { background: #b4befe; }"
        )
        self._add_row_btn.clicked.connect(self.addRowRequested.emit)
        self.addWidget(self._add_row_btn)

        # ── CSV 익스포트 버튼 ──
        self._export_btn = QPushButton("📥 CSV 추출")
        self._export_btn.setToolTip("현재 테이블 전체 데이터를 CSV로 다운로드")
        self._export_btn.setStyleSheet(
            "QPushButton {"
            "  background: #fab387; color: #1e1e2e; font-weight: bold;"
            "  border-radius: 4px; padding: 4px 12px; font-size: 12px; margin-left: 4px;"
            "}"
            "QPushButton:hover { background: #f9e2af; }"
        )
        self._export_btn.clicked.connect(self.exportRequested.emit)
        self.addWidget(self._export_btn)

        # ── 📤 파일 업로드 버튼 ──
        self._upload_btn = QPushButton("📤 Upload")
        self._upload_btn.setToolTip("서버 인제션 워크스페이스에 로그 파일 업로드")
        self._upload_btn.setStyleSheet("""
            QPushButton { background: #cba6f7; color: #111111; font-weight: bold; border-radius: 4px; padding: 4px 12px; font-size: 12px; }
            QPushButton:hover { background: #f5c2e7; }
        """)
        self._upload_btn.clicked.connect(self.uploadRequested.emit)
        self.addWidget(self._upload_btn)

        # ── ⚡ 최신순 정렬 토글 버튼 ──
        self._sort_latest = True
        self._sort_btn = QPushButton("⚡ 최신순 ON")
        self._sort_btn.setCheckable(True)
        self._sort_btn.setChecked(True)
        self._sort_btn.setToolTip("데이터 수정 시 최상단으로 자동 정렬 (Toggle)")
        self._update_sort_btn_style()
        self._sort_btn.clicked.connect(self._on_sort_toggled)
        self.addWidget(self._sort_btn)

        # ── ⚡ 1k 일괄 로드 버튼 ──
        self._batch_btn = QPushButton("⚡ 1k 로드")
        self._batch_btn.setToolTip("다음 1,000개의 행을 한 번에 가져옵니다.")
        self._batch_btn.setStyleSheet("""
            QPushButton { background: #94e2d5; color: #111111; font-weight: bold; border-radius: 4px; padding: 4px 12px; font-size: 12px; margin-left: 4px; }
            QPushButton:hover { background: #89dceb; }
        """)
        self._batch_btn.clicked.connect(lambda: self.batchLoadRequested.emit(1000))
        self.addWidget(self._batch_btn)

        # 내부 프록시 모델 저장소
        self._proxies: list[QSortFilterProxyModel] = []
        self._active_proxy: QSortFilterProxyModel | None = None  # 현재 활성 탭의 프록시

        # 검색 타이머 (서버 부하 방지를 위한 Debounce: 500ms)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._emit_search_requested)

        # 검색창 텍스트 변경 시 모든 프록시에 반영
        self._search_box.textChanged.connect(self._on_text_changed)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_proxy(self, source_model) -> QSortFilterProxyModel:
        """
        원본 모델(ApiLazyTableModel)을 QSortFilterProxyModel 로 래핑하여 반환합니다.
        반환된 프록시를 QTableView.setModel() 에 넘겨야 필터가 동작합니다.
        """
        proxy = QSortFilterProxyModel(self)
        proxy.setSourceModel(source_model)
        proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        proxy.setFilterKeyColumn(-1)          # 모든 컬럼 검색
        self._proxies.append(proxy)

        # 결과 수 갱신을 위해 rowsInserted / rowsRemoved 연결
        # [Phase 73.8] 10ms 지연 제거: 실시간 반응성 확보
        proxy.rowsInserted.connect(self._update_count_label)
        proxy.rowsRemoved.connect(self._update_count_label)
        proxy.modelReset.connect(self._update_count_label)
        
        # [신규] 원본 모델의 실시간 전체 카운트 시그널 연결
        if hasattr(source_model, "total_count_changed"):
            source_model.total_count_changed.connect(self._update_count_label)

        # 첫 번째로 생성된 프록시를 기본 활성으로 설정
        if self._active_proxy is None:
            self._active_proxy = proxy

        return proxy

    def _request_count_update(self, *args):
        """10ms 뒤에 카운트 레이블을 갱신합니다. (Debounce)"""
        QTimer.singleShot(10, self._update_count_label)

    def set_active_proxy(self, proxy: QSortFilterProxyModel):
        """현재 활성 탭이 바뀔 때 MainWindow에서 호출하여 행 수 갱신 기준을 전환합니다."""
        self._active_proxy = proxy
        # [Phase 73.7] 탭 전환 시 검색 범위 메뉴와 선택 상태 초기화
        self._refresh_scope_menu()
        # [Phase 73.8] 탭 전환 즉시 카운트 레이블 업데이트
        self._update_count_label()

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
            # 기존에 선택되어 있었거나, 선택된 적이 없으면(초기 상태) 체크
            action.setChecked(col in self._selected_cols)
            
            # 클로저 이슈 방지를 위한 default argument 사용
            action.triggered.connect(lambda checked, c=col: self._on_scope_toggled(c, checked))
            self._scope_menu.addAction(action)

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
        
        self._count_label.setText(f" Loaded: {exposed:,} /  Totals: {total:,}")

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
