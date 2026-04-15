"""
panel_settings.py
사용자 환경설정을 관리하는 설정 패널.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QLineEdit, QPushButton, QFrame, QMessageBox,
    QSpacerItem, QSizePolicy
)
from PySide6.QtCore import Qt, Signal
import config

class SettingsPanel(QWidget):
    """서버 주소, 사용자 ID 등 앱 엔진 설정을 변경할 수 있는 UI."""
    
    settingsChanged = Signal() # 설정 저장 시 알림 (필요 시)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("settingsPage")
        self.setStyleSheet("background-color: #181825;")
        
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)
        
        # 타이틀
        header = QLabel("Settings")
        header.setStyleSheet("font-size: 28px; font-weight: bold; color: #cdd6f4;")
        layout.addWidget(header)
        
        desc = QLabel("애플리케이션 환경 및 접속 정보를 설정합니다.")
        desc.setStyleSheet("font-size: 14px; color: #bac2de; margin-bottom: 10px;")
        layout.addWidget(desc)
        
        # 설정 폼 컨테이너
        form_frame = QFrame()
        form_frame.setStyleSheet("""
            QFrame {
                background-color: #1e1e2e;
                border-radius: 12px;
                border: 1px solid #313244;
            }
            QLabel { border: none; font-weight: bold; color: #9399b2; }
            QLineEdit {
                background-color: #313244; 
                color: #cdd6f4; 
                border: 1px solid #45475a; 
                border-radius: 6px; 
                padding: 8px;
            }
        """)
        form_layout = QVBoxLayout(form_frame)
        form_layout.setContentsMargins(20, 20, 20, 20)
        form_layout.setSpacing(15)
        
        # 1. 사용자 이름
        u_layout = QVBoxLayout()
        u_layout.addWidget(QLabel("User Name (Identity Tracking)"))
        self.edit_user = QLineEdit(config.CURRENT_USER, enabled=False)
        u_layout.addWidget(self.edit_user)
        form_layout.addLayout(u_layout)
        
        # 2. 서버 호스트
        h_layout = QVBoxLayout()
        h_layout.addWidget(QLabel("Server Host"))
        self.edit_host = QLineEdit(config.SERVER_HOST)
        h_layout.addWidget(self.edit_host)
        form_layout.addLayout(h_layout)
        
        # 3. 서버 포트
        p_layout = QVBoxLayout()
        p_layout.addWidget(QLabel("Server Port"))
        self.edit_port = QLineEdit(str(config.SERVER_PORT))
        p_layout.addWidget(self.edit_port)
        form_layout.addLayout(p_layout)
        
        layout.addWidget(form_frame)
        
        # 저당 버튼
        btn_layout = QHBoxLayout()
        self.btn_save = QPushButton("Save Settings")
        self.btn_save.setFixedSize(150, 40)
        self.btn_save.setStyleSheet("""
            QPushButton {
                background-color: #89b4fa;
                color: #11111b;
                font-weight: bold;
                border-radius: 8px;
            }
            QPushButton:hover { background-color: #b4befe; }
        """)
        self.btn_save.clicked.connect(self._on_save_clicked)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_save)
        
        layout.addLayout(btn_layout)
        layout.addStretch()

    def _on_save_clicked(self):
        host = self.edit_host.text().strip()
        port = self.edit_port.text().strip()
        user = self.edit_user.text().strip()
        
        if not host or not port or not user:
            QMessageBox.warning(self, "경고", "모든 필드를 채워주세요.")
            return
            
        try:
            config.save_settings(host, port, user)
            QMessageBox.information(self, "저장 완료", "설정이 성공적으로 저장되었습니다.\n변경사항을 적용하려면 앱 재시작이 권장될 수 있습니다.")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"설정 저장 중 오류 발생: {e}")

