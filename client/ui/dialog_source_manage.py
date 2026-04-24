"""
dialog_source_manage.py
특정 셀의 중첩된 데이터 원천(Sources)을 시각화하고 관리(우선순위 지정, 삭제)하는 다이얼로그.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, 
    QTableWidgetItem, QPushButton, QHeaderView, QRadioButton, 
    QMessageBox, QWidget, QButtonGroup
)

from PySide6.QtGui import QColor
from PySide6.QtCore import Qt, Signal
import httpx
import config

class CellSourceManageDialog(QDialog):
    """셀의 모든 데이터 레이어를 보여주고 사용자가 제어할 수 있게 하는 다이얼로그."""
    
    sourceChanged = Signal() # 데이터 변경 발생 시 테이블 갱신을 위해 상위에 알림

    def __init__(self, table_name: str, row_id: str, col_name: str, parent=None):
        super().__init__(parent)
        self.table_name = table_name
        self.row_id = row_id
        self.col_name = col_name
        
        self.setWindowTitle(f"데이터 원천 관리 - {col_name}")
        self.resize(650, 400)
        self.setModal(True)
        
        # UI 구성
        self._init_ui()
        
        # 데이터 로드
        self._fetch_sources()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        self.setStyleSheet("""
            QDialog { background-color: #1e1e2e; color: #cdd6f4; }
            QLabel { color: #89b4fa; font-weight: bold; }
            QTableWidget { 
                background-color: #1e1e2e; color: #cdd6f4; 
                gridline-color: #313244; border: 1px solid #45475a;
                border-radius: 8px;
            }
            QTableWidget::item { padding: 8px; }
            QTableWidget::item:selected { background-color: #313244; color: #89b4fa; }
            QHeaderView::section { 
                background-color: #11111b; color: #bac2de; 
                border: none; padding: 6px; font-weight: bold;
                border-bottom: 1px solid #45475a;
            }
            QPushButton#deleteBtn { 
                background-color: transparent; color: #f38ba8; font-size: 14px; border: none;
            }
            QPushButton#deleteBtn:hover { background-color: #313244; border-radius: 4px; }
            QPushButton#closeBtn { 
                background-color: #45475a; color: #cdd6f4; border-radius: 6px; padding: 8px 20px;
                font-weight: bold; border: 1px solid #585b70;
            }
            QPushButton#closeBtn:hover { background-color: #585b70; }
            
            QRadioButton::indicator { width: 18px; height: 18px; }
            QRadioButton::indicator:unchecked { 
                border: 2px solid #585b70; border-radius: 9px; background: none; 
            }
            QRadioButton::indicator:checked { 
                border: 2px solid #89b4fa; border-radius: 9px; background: #89b4fa; 
            }
        """)

        header_label = QLabel(f"🧬 Cell Sources Tracker")
        header_label.setStyleSheet("font-size: 16px; margin-bottom: 10px; color: #cba6f7;")
        layout.addWidget(header_label)
        
        info_label = QLabel(f"📍 {self.table_name} > {self.col_name} (Row: {self.row_id[:8]})")
        info_label.setStyleSheet("font-size: 12px; color: #9399b2; margin-bottom: 5px;")
        layout.addWidget(info_label)

        # 소스 리스트 테이블
        self.table = QTableWidget(0, 6) # Column count increased to 6
        self.table.setHorizontalHeaderLabels(["Priority", "Source", "Value", "By", "Timestamp", "Del"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        
        self.table.setColumnWidth(0, 60)
        self.table.setColumnWidth(4, 140)
        self.table.setColumnWidth(5, 40)
        
        # 행 클릭 시 라디오 버튼도 활성화되도록 연결
        self.table.cellClicked.connect(self._on_cell_clicked)
        
        layout.addWidget(self.table)

        # 하단 닫기 버튼
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton("닫기")
        close_btn.setObjectName("closeBtn")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

    def _fetch_sources(self):
        """서버에서 해당 셀의 모든 소스 정보를 가져옵니다."""
        url = f"{config.API_BASE_URL}/tables/{self.table_name}/{self.row_id}/{self.col_name}/sources"
        try:
            with httpx.Client() as client:
                res = client.get(url)
                if res.status_code == 200:
                    data = res.json()
                    self._render_sources(data)
                else:
                    QMessageBox.warning(self, "오류", f"데이터를 가져오는데 실패했습니다: {res.text}")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"통신 중 오류 발생: {e}")

    def _render_sources(self, data):
        sources = data.get("sources", {})
        manual_priority = data.get("manual_priority_source")
        priority_source = data.get("priority_source")
        
        self.table.setRowCount(0)
        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)
        
        # 정렬: 소스명 우선순위 (User가 먼저 오게 하거나 등등)
        sorted_keys = sorted(sources.keys(), key=lambda k: (0 if k == "user" else 1, k))
        
        for i, src_name in enumerate(sorted_keys):
            self.table.insertRow(i)
            src_data = sources[src_name]
            
            # 1. Priority 선택 (Radio)
            radio = QRadioButton()
            is_active = src_name == (manual_priority or priority_source)
            radio.setChecked(is_active)
            self.button_group.addButton(radio, i)
            
            # UI 상에서 manual_priority 여부 표시
            if manual_priority and src_name == manual_priority:
                radio.setToolTip("Manually Pinned Source")
            
            radio_container = QWidget()
            radio_layout = QHBoxLayout(radio_container)
            radio_layout.addWidget(radio)
            radio_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            radio_layout.setContentsMargins(0, 0, 0, 0)
            self.table.setCellWidget(i, 0, radio_container)

            # 2. Source
            item_src = QTableWidgetItem(src_name)
            item_src.setFlags(item_src.flags() ^ Qt.ItemFlag.ItemIsEditable)
            if src_name == priority_source:
                item_src.setText(f"⭐ {src_name}")
                item_src.setForeground(QColor("#a6e3a1"))
            self.table.setItem(i, 1, item_src)

            # 3. Value
            item_val = QTableWidgetItem(str(src_data.get("value", "")))
            item_val.setFlags(item_val.flags() ^ Qt.ItemFlag.ItemIsEditable)
            if is_active:
                item_val.setFont("Consolas")
                item_val.setForeground(QColor("#f9e2af")) # 강조색
            self.table.setItem(i, 2, item_val)

            # 4. Updated By
            user = src_data.get("updated_by", "system")
            item_user = QTableWidgetItem(user)
            item_user.setFlags(item_user.flags() ^ Qt.ItemFlag.ItemIsEditable)
            item_user.setForeground(QColor("#cba6f7"))
            self.table.setItem(i, 3, item_user)

            # 5. Timestamp
            ts = src_data.get("timestamp", "")
            if ts and "T" in ts: ts = ts.split(".")[0].replace("T", " ")
            item_ts = QTableWidgetItem(ts)
            item_ts.setFlags(item_ts.flags() ^ Qt.ItemFlag.ItemIsEditable)
            item_ts.setForeground(QColor("#9399b2"))
            self.table.setItem(i, 4, item_ts)

            # 6. Delete
            del_btn = QPushButton("🗑️")
            del_btn.setObjectName("deleteBtn")
            del_btn.setFixedSize(30, 30)
            del_btn.setProperty("source_name", src_name)
            del_btn.clicked.connect(self._on_delete_btn_clicked)
            
            del_container = QWidget()
            del_layout = QHBoxLayout(del_container)
            del_layout.addWidget(del_btn)
            del_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            del_layout.setContentsMargins(0, 0, 0, 0)
            self.table.setCellWidget(i, 5, del_container)

        # 버튼 그룹 시그널 한 번에 연결
        self.button_group.idClicked.connect(self._on_radio_group_clicked)

    def _on_delete_btn_clicked(self):
        """삭제 버튼 클릭 시 호출되는 슬롯입니다."""
        btn = self.sender()
        if not btn: return
        source_name = btn.property("source_name")
        if source_name:
            self._on_delete_source(source_name)


    def _on_cell_clicked(self, row, col):
        """행을 클릭하면 해당 행의 라디오 버튼도 체크되도록 함."""
        radio_container = self.table.cellWidget(row, 0)
        if radio_container:
            radio = radio_container.findChild(QRadioButton)
            if radio:
                radio.setChecked(True)
                # radio.setChecked(True) 가 _on_radio_group_clicked 를 트리거함

    def _on_radio_group_clicked(self, row_index):
        # 소스명 찾기
        item = self.table.item(row_index, 1)
        if not item: return
        source_name = item.text().replace("⭐ ", "")
        self._on_priority_changed(source_name, True)

    def _on_priority_changed(self, source_name, checked):
        if not checked: return
        
        url = f"{config.API_BASE_URL}/tables/{self.table_name}/{self.row_id}/{self.col_name}/priority"
        try:
            with httpx.Client() as client:
                payload = {
                    "source_name": source_name,
                    "updated_by": config.CURRENT_USER
                }
                res = client.put(url, json=payload)
                if res.status_code == 200:
                    # 갱신은 WebSocket 브로드캐스트가 처리하겠지만 다이얼로그도 갱신
                    self._fetch_sources()
                    self.sourceChanged.emit()
                else:
                    QMessageBox.warning(self, "실패", f"우선순위 변경 실패: {res.text}")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"통신 오류: {e}")

    def _on_delete_source(self, source_name):
        reply = QMessageBox.question(
            self, "삭제 확인", 
            f"'{source_name}' 원천 데이터를 이 셀에서 영구 삭제하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        url = f"{config.API_BASE_URL}/tables/{self.table_name}/{self.row_id}/{self.col_name}/sources/{source_name}"
        try:
            with httpx.Client() as client:
                res = client.delete(url)
                if res.status_code == 200:
                    self._fetch_sources()
                    self.sourceChanged.emit()
                else:
                    QMessageBox.warning(self, "실패", f"삭제 실패: {res.text}")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"통신 오류: {e}")
