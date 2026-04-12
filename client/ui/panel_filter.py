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
from PySide6.QtCore import Qt, QSortFilterProxyModel, Signal
from PySide6.QtGui import QAction


class FilterToolBar(QToolBar):
    """상단 툴바 — 텍스트 검색으로 테이블 행을 실시간 필터링."""
    
    # ── Agent E v3: 새 탭 추가 요청 시그널 ──
    addTabRequested = Signal()
    # ── Agent E v4: 새 행 추가 요청 시그널 ──
    addRowRequested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__("필터", parent)
        self.setMovable(False)
        self.setFloatable(False)
        self.setStyleSheet(
            "QToolBar { background: #1e1e2e; border-bottom: 1px solid #313244; spacing: 6px; padding: 4px 8px; }"
            "QLabel { color: #89b4fa; font-weight: bold; font-size: 12px; }"
            "QLineEdit {"
            "  background: #313244; color: #cdd6f4; border: 1px solid #45475a;"
            "  border-radius: 4px; padding: 3px 8px; font-size: 12px; min-width: 220px;"
            "}"
            "QLineEdit:focus { border-color: #89b4fa; }"
        )

        # 라벨
        lbl = QLabel("🔍 검색:")
        self.addWidget(lbl)

        # 검색창
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("검색어 입력 (정규식 지원)...")
        self._search_box.setClearButtonEnabled(True)
        self.addWidget(self._search_box)

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

        # 내부 프록시 모델 저장소
        self._proxies: list[QSortFilterProxyModel] = []

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
        proxy.rowsInserted.connect(self._update_count_label)
        proxy.rowsRemoved.connect(self._update_count_label)
        proxy.modelReset.connect(self._update_count_label)

        return proxy

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _on_text_changed(self, text: str):
        for proxy in self._proxies:
            proxy.setFilterRegularExpression(text)
        self._update_count_label()

    def _update_count_label(self):
        if not self._proxies:
            self._count_label.setText("")
            return
        # 현재 활성 프록시의 visible row 수 표시 (첫 번째 프록시 기준)
        proxy = self._proxies[0]
        visible = proxy.rowCount()
        total = proxy.sourceModel().rowCount() if proxy.sourceModel() else 0
        if self._search_box.text():
            self._count_label.setText(f"{visible} / {total} 행")
        else:
            self._count_label.setText(f"총 {total} 행")
