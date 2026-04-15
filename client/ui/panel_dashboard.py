"""
panel_dashboard.py
앱 시작 시 보여줄 현대적인 홈 대시보드 패널.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QFrame, QGridLayout, QScrollArea
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QColor

class StatCard(QFrame):
    """지표를 강조해서 보여주는 세련된 카드."""
    def __init__(self, title, value, icon_str, color="#89b4fa"):
        super().__init__()
        self.setFixedSize(200, 120)
        self.setStyleSheet(f"""
            StatCard {{
                background-color: #1e1e2e;
                border: 1px solid #313244;
                border-radius: 12px;
            }}
            StatCard:hover {{
                border-color: {color};
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        
        header_layout = QHBoxLayout()
        icon_label = QLabel(icon_str)
        icon_label.setStyleSheet(f"font-size: 20px; color: {color};")
        title_label = QLabel(title)
        title_label.setStyleSheet("color: #9399b2; font-size: 11px; font-weight: bold;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        header_layout.addWidget(icon_label)
        
        layout.addLayout(header_layout)
        
        value_label = QLabel(str(value))
        value_label.setStyleSheet("color: #cdd6f4; font-size: 24px; font-weight: bold; margin-top: 5px;")
        layout.addWidget(value_label)
        
        trend_label = QLabel("▲ 12% from last week") # Placeholder
        trend_label.setStyleSheet("color: #a6e3a1; font-size: 9px;")
        layout.addWidget(trend_label)

class DashboardPanel(QWidget):
    """메인 레이아웃의 중앙에 위치할 환영 및 통계 화면."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dashboard")
        self.setStyleSheet("background-color: #181825;")
        
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(40, 40, 40, 40)
        main_layout.setSpacing(30)
        
        # 1. 환영 배너
        welcome_layout = QVBoxLayout()
        title = QLabel("Welcome back, Assy Manager")
        title.setStyleSheet("font-size: 28px; font-weight: bold; color: #cdd6f4;")
        subtitle = QLabel("현재 시스템 운영 현황 및 데이터 인제션 지표입니다.")
        subtitle.setStyleSheet("font-size: 14px; color: #bac2de;")
        welcome_layout.addWidget(title)
        welcome_layout.addWidget(subtitle)
        main_layout.addLayout(welcome_layout)
        
        # 2. 통계 카드 그리드
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(20)
        
        self.card_tables = StatCard("활성 테이블", "5", "📁", "#cba6f7")
        self.card_updates = StatCard("오늘의 수정", "128", "✍️", "#89b4fa")
        self.card_ws = StatCard("네트워크 상태", "Stable", "📡", "#a6e3a1")
        self.card_errors = StatCard("감시 중인 오류", "0", "🛡️", "#f38ba8")
        
        stats_layout.addWidget(self.card_tables)
        stats_layout.addWidget(self.card_updates)
        stats_layout.addWidget(self.card_ws)
        stats_layout.addWidget(self.card_errors)
        stats_layout.addStretch()
        
        main_layout.addLayout(stats_layout)
        
        # 3. 최근 활동 (간소화된 리스트)
        activity_section = QVBoxLayout()
        activity_label = QLabel("최근 시스템 활동")
        activity_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #cdd6f4; margin-top: 20px;")
        activity_section.addWidget(activity_label)
        
        activity_list = QFrame()
        activity_list.setStyleSheet("""
            QFrame {
                background-color: #1e1e2e;
                border-radius: 12px;
                border: 1px solid #313244;
            }
        """)
        list_layout = QVBoxLayout(activity_list)
        list_layout.setContentsMargins(10, 10, 10, 10)
        
        # Placeholder activities
        for act in [
            "✅ inventory_master 테이블 데이터 인제션 완료 (14:30)",
            "🛠️ production_plan 수정 이력 12건 발생 (13:15)",
            "📡 WebSocket 서버 연결 성공 (09:00)"
        ]:
            item = QLabel(act)
            item.setStyleSheet("color: #bac2de; padding: 10px; border-bottom: 1px solid #313244;")
            list_layout.addWidget(item)
            
        activity_section.addWidget(activity_list)
        main_layout.addLayout(activity_section)
        
        main_layout.addStretch()

    def update_stats(self, table_count, ws_status):
        self.card_tables.findChild(QLabel, "", Qt.FindChildOption.FindDirectChildren).setText(str(table_count))
        # More thorough logic to update labels...
        pass
