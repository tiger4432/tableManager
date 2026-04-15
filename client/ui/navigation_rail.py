"""
navigation_rail.py
현대적인 수직 사이드바 내비게이션 컴포넌트.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QLabel, 
    QSpacerItem, QSizePolicy, QFrame, QMenu
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QIcon, QColor

class NavButton(QPushButton):
    """커스텀 스타일이 적용된 사이드바 버튼."""
    def __init__(self, icon_str, text, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedWidth(82)
        self.setMinimumHeight(82)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(2)
        layout.setContentsMargins(0, 8, 0, 8)
        
        icon_label = QLabel(icon_str)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet("font-size: 20px; background: transparent; border: none;")
        
        text_label = QLabel(text)
        text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text_label.setWordWrap(True)
        text_label.setStyleSheet("font-size: 10px; font-weight: bold; background: transparent; border: none; padding: 0 2px;")
        
        layout.addWidget(icon_label)
        layout.addWidget(text_label)
        
        self.setStyleSheet("""
            NavButton {
                background-color: transparent;
                border: none;
                border-radius: 8px;
                color: #bac2de;
                margin: 4px;
            }
            NavButton:hover {
                background-color: #313244;
                color: #cdd6f4;
            }
            NavButton:checked {
                background-color: #45475a;
                color: #89b4fa;
                border-left: 3px solid #89b4fa;
                border-top-left-radius: 0;
                border-bottom-left-radius: 0;
            }
        """)

    def contextMenuEvent(self, event):
        """우클릭 시 메뉴 표출 (테이블인 경우 닫기 옵션 제공)."""
        # 부모 NavigationRail에 위임하여 시그널 발생
        parent = self.parent()
        while parent and not hasattr(parent, "_on_button_context_menu"):
            parent = parent.parent()
        
        if parent:
            parent._on_button_context_menu(self, event.globalPos())

class NavigationRail(QFrame):
    """메인 레이아웃의 좌측에 위치할 수직 내비게이션 바."""
    
    navigateRequested = Signal(str) # 'home', 'table:name', 'settings' 등
    closeRequested = Signal(str)    # 'table:name' 제거 요청
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(94)
        self.setObjectName("navRail")
        self.setStyleSheet("""
            #navRail {
                background-color: #11111b;
                border-right: 1px solid #313244;
            }
        """)
        
        self._buttons = {}
        self._init_ui()

    def _init_ui(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(5, 15, 5, 15)
        self.layout.setSpacing(10)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        # 앱 로고 영역 (심플)
        logo = QLabel("🚀")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setStyleSheet("font-size: 24px; margin-bottom: 20px;")
        self.layout.addWidget(logo)
        
        # 홈 버튼 (대시보드)
        #self.add_nav_item("home", "🏠", "Home")
        
        # 구분선
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("background-color: #313244; max-height: 1px; margin: 5px 10px;")
        self.layout.addWidget(line)
        
        # 테이블 목록 버튼들은 동적으로 추가될 예정
        self.tab_container_layout = QVBoxLayout()
        self.tab_container_layout.setSpacing(10)
        self.tab_container_layout.setContentsMargins(0, 0, 0, 0)
        self.layout.addLayout(self.tab_container_layout)
        
        self.layout.addStretch()
        
        # 설정 버튼
        self.add_nav_item("settings", "⚙️", "Settings")

    def add_nav_item(self, id_str, icon_str, text, is_table=False):
        # 테이블 이름의 언더바(_)를 공백으로 치환하여 가독성 높이고 자동 줄바꿈 유도
        display_text = text.replace("_", " ") if is_table else text
        btn = NavButton(icon_str, display_text)
        btn.clicked.connect(lambda: self._on_btn_clicked(id_str))
        
        if is_table:
            self.tab_container_layout.addWidget(btn)
        else:
            self.layout.insertWidget(self.layout.count() - 2 if id_str == "settings" else self.layout.count(), btn)
        
        self._buttons[id_str] = btn
        
        # 첫 번째 아이템(홈) 자동 선택
        if id_str == "home":
            btn.setChecked(True)

    def remove_nav_item(self, id_str):
        if id_str in self._buttons:
            btn = self._buttons.pop(id_str)
            btn.deleteLater()
            # 레이아웃에서 자동 제거됨

    def _on_button_context_menu(self, btn, pos):
        # 버튼 ID 찾기
        id_str = None
        for bid, b in self._buttons.items():
            if b == btn:
                id_str = bid
                break
        
        if not id_str or not id_str.startswith("table:"):
            return
            
        menu = QMenu(self)
        menu.setStyleSheet("background-color: #1e1e2e; color: #cdd6f4; border: 1px solid #313244;")
        close_action = menu.addAction("🗑️ 테이블 닫기")
        
        action = menu.exec(pos)
        if action == close_action:
            self.closeRequested.emit(id_str)

    def _on_btn_clicked(self, id_str):
        # 다른 버튼들 체크 해제 (Exclusive behavior)
        for bid, btn in self._buttons.items():
            btn.setChecked(bid == id_str)
        
        self.navigateRequested.emit(id_str)

    def set_active(self, id_str):
        if id_str in self._buttons:
            for bid, btn in self._buttons.items():
                btn.setChecked(bid == id_str)
