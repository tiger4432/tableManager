"""
panel_dashboard.py
앱 시작 시 보여줄 현대적인 홈 대시보드 패널.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QFrame, QGridLayout, QScrollArea, QSizePolicy
)
from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QFont, QColor

class StatCard(QFrame):
    """지표를 강조해서 보여주는 세련된 카드."""
    def __init__(self, title, value, icon_str, color="#89b4fa"):
        super().__init__()
        self.setFixedSize(190, 140)
        self.color = color
        self.setStyleSheet(f"""
            StatCard {{
                background-color: #1e1e2e;
                border: 1px solid #313244;
                border-radius: 16px;
            }}
            StatCard:hover {{
                border-color: {color};
                background-color: #242437;
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        header_layout = QHBoxLayout()
        self.icon_label = QLabel(icon_str)
        self.icon_label.setStyleSheet(f"font-size: 24px; color: {color}; background: transparent;")
        self.title_label = QLabel(title.upper())
        self.title_label.setStyleSheet("color: #9399b2; font-size: 10px; font-weight: bold; letter-spacing: 1px; background: transparent;")
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        header_layout.addWidget(self.icon_label)
        
        layout.addLayout(header_layout)
        
        self.value_label = QLabel(str(value))
        self.value_label.setStyleSheet("color: #cdd6f4; font-size: 28px; font-weight: bold; margin-top: 5px; background: transparent;")
        layout.addWidget(self.value_label)
        
        self.status_label = QLabel("● SYSTEM OPTIMIZED")
        self.status_label.setStyleSheet(f"color: {color}; font-size: 9px; font-weight: bold; margin-top: 5px; background: transparent;")
        layout.addWidget(self.status_label)

    def set_value(self, value):
        self.value_label.setText(str(value))

class TableStatusCard(QFrame):
    """개별 테이블의 현황을 요약해서 보여주는 콤팩트 카드. 드래그 앤 드롭 지원."""
    
    fileDropped = Signal(str, str) # table_name, file_path
    doubleClicked = Signal(str)    # [Phase 2] 더블 클릭 시 테이블 오픈용

    def __init__(self, name, rows, updated, status):
        super().__init__()
        self.setFixedHeight(80)
        self.table_name = name
        self.status_color = "#a6e3a1" if status == "Active" else "#9399b2"
        
        self.setAcceptDrops(True)
        self._set_normal_style()
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 10)
        
        # 이름 및 상태 아이콘
        info_layout = QVBoxLayout()
        name_label = QLabel(name)
        name_label.setStyleSheet("color: #cdd6f4; font-size: 14px; font-weight: bold; background: transparent;")
        status_layout = QHBoxLayout()
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {self.status_color}; font-size: 12px; background: transparent;")
        status_text = QLabel(status)
        status_text.setStyleSheet(f"color: {self.status_color}; font-size: 10px; font-weight: bold; background: transparent;")
        status_layout.addWidget(dot)
        status_layout.addWidget(status_text)
        status_layout.addStretch()
        info_layout.addWidget(name_label)
        info_layout.addLayout(status_layout)
        
        layout.addLayout(info_layout)
        layout.addStretch()
        
        # 행 개수
        count_layout = QVBoxLayout()
        count_val = QLabel(f"{rows:,}")
        count_val.setAlignment(Qt.AlignmentFlag.AlignRight)
        count_val.setStyleSheet("color: #f5e0dc; font-size: 18px; font-weight: bold; background: transparent;")
        count_label = QLabel("LOADED ROWS")
        count_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        count_label.setStyleSheet("color: #6c7086; font-size: 9px; font-weight: bold; background: transparent;")
        count_layout.addWidget(count_val)
        count_layout.addWidget(count_label)
        
        layout.addLayout(count_layout)
        
        # 마지막 업데이트
        update_layout = QVBoxLayout()
        update_layout.setContentsMargins(20, 0, 0, 0)
        update_val = QLabel(updated if updated else "N/A")
        update_val.setAlignment(Qt.AlignmentFlag.AlignRight)
        update_val.setStyleSheet("color: #bac2de; font-size: 11px; background: transparent;")
        update_label = QLabel("LAST ACTIVITY")
        update_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        update_label.setStyleSheet("color: #6c7086; font-size: 9px; font-weight: bold; background: transparent;")
        update_layout.addWidget(update_val)
        update_layout.addWidget(update_label)
        
        layout.addLayout(update_layout)

    def _set_normal_style(self):
        self.setStyleSheet(f"""
            TableStatusCard {{
                background-color: #181825;
                border: 1px solid #313244;
                border-radius: 10px;
            }}
            TableStatusCard:hover {{
                background-color: #1e1e2e;
                border-color: #45475a;
            }}
        """)

    def _set_drag_style(self):
        self.setStyleSheet(f"""
            TableStatusCard {{
                background-color: #313244;
                border: 2px dashed #89b4fa;
                border-radius: 10px;
            }}
        """)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._set_drag_style()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._set_normal_style()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            file_path = urls[0].toLocalFile()
            print(f"[Dashboard] File dropped on {self.table_name}: {file_path}")
            self.fileDropped.emit(self.table_name, file_path)
        self._set_normal_style()

    def mouseDoubleClickEvent(self, event):
        """더블 클릭 시 해당 테이블을 오픈하도록 시그널 발생."""
        self.doubleClicked.emit(self.table_name)

class DashboardPanel(QWidget):
    """메인 레이아웃의 중앙에 위치할 환영 및 상세 통계 화면."""
    
    tableFileDropped = Signal(str, str) # MainWindow와 연결할 시그널
    tableDoubleClicked = Signal(str)    # [Phase 2] 테이블 오픈 시그널

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dashboard")
        self.setStyleSheet("background-color: #1e1e2e;") # Base
        
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(40, 40, 40, 40)
        main_layout.setSpacing(30)
        
        # 1. 환영 배너
        welcome_layout = QVBoxLayout()
        title = QLabel("System Dashboard")
        title.setStyleSheet("font-size: 32px; font-weight: bold; color: #cdd6f4; letter-spacing: -0.5px;")
        subtitle = QLabel("Real-time operational metrics and table ingestion status. Drag & Drop files to inject data.")
        subtitle.setStyleSheet("font-size: 14px; color: #9399b2;")
        welcome_layout.addWidget(title)
        welcome_layout.addWidget(subtitle)
        main_layout.addLayout(welcome_layout)
        
        # 2. 전역 통계 카드
        stats_scroll = QScrollArea()
        stats_scroll.setWidgetResizable(True)
        stats_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        stats_scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical {
                border: none;
                background: transparent;
                width: 6px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #313244;
                min-height: 30px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical:hover {
                background: #45475a;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                border: none; background: none;
            }
        """)
        stats_content = QWidget()
        stats_content.setStyleSheet("background: transparent;")
        stats_main_layout = QVBoxLayout(stats_content)
        stats_main_layout.setContentsMargins(0, 0, 0, 0)
        stats_main_layout.setSpacing(30)
        
        header_stats_layout = QHBoxLayout()
        header_stats_layout.setSpacing(20)
        
        self.card_tables = StatCard("Active Tables", "0", "📁", "#cba6f7")
        self.card_rows = StatCard("Total Rows", "0", "📊", "#89b4fa")
        self.card_updates = StatCard("Today's Updates", "0", "✍️", "#fab387")
        self.card_health = StatCard("System Health", "Optimal", "🛡️", "#a6e3a1")
        
        header_stats_layout.addWidget(self.card_tables)
        header_stats_layout.addWidget(self.card_rows)
        header_stats_layout.addWidget(self.card_updates)
        header_stats_layout.addWidget(self.card_health)
        header_stats_layout.addStretch()
        
        stats_main_layout.addLayout(header_stats_layout)
        
        # 3. 테이블 상세 현황 섹션
        table_section = QVBoxLayout()
        table_header = QLabel("Table Ingestion Status")
        table_header.setStyleSheet("font-size: 18px; font-weight: bold; color: #cdd6f4; margin-top: 20px;")
        table_section.addWidget(table_header)
        
        self.table_grid = QGridLayout()
        self.table_grid.setSpacing(15)
        # Placeholder for dynamic cards
        table_section.addLayout(self.table_grid)
        
        stats_main_layout.addLayout(table_section)
        stats_main_layout.addStretch()
        
        stats_scroll.setWidget(stats_content)
        main_layout.addWidget(stats_scroll)

    def update_dashboard(self, data: dict):
        """서버로부터 받은 요약 데이터를 UI에 반영합니다."""
        # 전역 카드 업데이트
        self.card_tables.set_value(data.get("total_tables", 0))
        self.card_rows.set_value(f"{data.get('total_rows', 0):,}")
        self.card_updates.set_value(f"{data.get('today_updates', 0):,}")
        self.card_health.set_value(data.get("system_health", "Excellent"))
        
        # 테이블 그리드 초기화 후 재생성
        # Clear layout
        while self.table_grid.count():
            item = self.table_grid.takeAt(0)
            widget = item.widget()
            if widget: widget.deleteLater()
            
        # 테이블 카드 배치 (2열 그리드)
        table_stats = data.get("table_stats", [])
        for i, stat in enumerate(table_stats):
            row = i // 2
            col = i % 2
            card = TableStatusCard(
                stat["table_name"], 
                stat["row_count"], 
                stat["last_updated"], 
                stat["status"]
            )
            # 카드 시그널 연결
            card.fileDropped.connect(self.tableFileDropped.emit)
            card.doubleClicked.connect(self.tableDoubleClicked.emit)
            self.table_grid.addWidget(card, row, col)
