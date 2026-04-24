from __future__ import annotations
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QProgressBar, QPushButton, QScrollArea, QWidget, QFrame
)
from PySide6.QtCore import Qt, Signal, Slot

class DownloadItemWidget(QFrame):
    """개별 다운로드 항목을 표시하는 위젯."""
    cancelRequested = Signal(str) # task_id
    
    def __init__(self, task_id: str, filename: str, parent=None):
        QFrame.__init__(self, parent)
        self.task_id = task_id
        self._is_done = False # [신규] 상태 추적용 플래그
        self.setObjectName("DownloadItem")
        self.setStyleSheet("""
            #DownloadItem { background: #313244; border-radius: 8px; margin: 2px; }
            QLabel { color: #cdd6f4; font-size: 11px; }
        """)
        
        layout = QVBoxLayout(self)
        
        # 상단: 파일명 및 삭제 버튼
        top_layout = QHBoxLayout()
        self.name_label = QLabel(f"📄 {filename}")
        self.name_label.setStyleSheet("font-weight: bold;")
        
        self.cancel_btn = QPushButton("✕")
        self.cancel_btn.setFixedSize(20, 20)
        self.cancel_btn.setStyleSheet("background: #f38ba8; color: #1e1e2e; border-radius: 10px; font-weight: bold;")
        self.cancel_btn.clicked.connect(lambda: self.cancelRequested.emit(self.task_id))
        
        top_layout.addWidget(self.name_label)
        top_layout.addStretch()
        top_layout.addWidget(self.cancel_btn)
        
        # 중단: 진행 바
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar { background: #1e1e2e; border: none; border-radius: 4px; }
            QProgressBar::chunk { background: #89b4fa; border-radius: 4px; }
        """)
        self.progress_bar.setRange(0, 0) # Loading state
        
        # 하단: 상태 텍스트
        self.status_label = QLabel("준비 중...")
        self.status_label.setStyleSheet("color: #a6adc8; font-size: 10px;")
        
        layout.addLayout(top_layout)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.status_label)

    def update_progress(self, current_bytes, total_bytes):
        if self._is_done: return
        if total_bytes > 0:
            self.progress_bar.setRange(0, total_bytes)
            self.progress_bar.setValue(current_bytes)
            mb = current_bytes / (1024 * 1024)
            total_mb = total_bytes / (1024 * 1024)
            self.status_label.setText(f"다운로드 중... {mb:.1f} MB / {total_mb:.1f} MB")
        else:
            mb = current_bytes / (1024 * 1024)
            self.status_label.setText(f"받는 중... {mb:.1f} MB (크기 알 수 없음)")

    def mark_finished(self, file_path):
        """완료 상태로 전환 및 경로 저장."""
        self._is_done = True
        self.file_path = file_path
        self.setCursor(Qt.PointingHandCursor)
        self.status_label.setText(f"✅ 완료 (클릭하여 열기)")
        self.status_label.setStyleSheet("color: #a6e3a1;")
        
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.progress_bar.setStyleSheet("QProgressBar::chunk { background: #a6e3a1; }")
        
        # 취소 버튼을 삭제 버튼으로 용도 변경
        self.cancel_btn.setText("✕") # 다시 X로 표기 (삭제 의미)
        self.cancel_btn.setStyleSheet("background: #45475a; color: #f38ba8; border-radius: 10px;")
        self.cancel_btn.setEnabled(True)

    def mousePressEvent(self, event):
        """클릭 시 파일 실존 여부 검사 및 열기 수행."""
        if hasattr(self, "file_path") and self.file_path:
            import os
            try:
                if not os.path.exists(self.file_path):
                    self.status_label.setText("❌ 파일이 이동되었거나 삭제되었습니다.")
                    self.status_label.setStyleSheet("color: #f38ba8;")
                    self.setCursor(Qt.ArrowCursor) # 손 모양 제거
                    return
                
                # 파일 열기 시도
                os.startfile(self.file_path)
            except PermissionError:
                self.status_label.setText("❌ 권한 거부: 다른 프로그램에서 사용 중일 수 있습니다.")
                self.status_label.setStyleSheet("color: #f38ba8;")
            except Exception as e:
                self.status_label.setText(f"❌ 열기 실패: {str(e)}")
                self.status_label.setStyleSheet("color: #f38ba8;")
        
        QFrame.mousePressEvent(self, event)

class DownloadManagerDialog(QDialog):
    """전체 다운로드 트랜잭션을 관리하는 다이얼로그."""
    
    def __init__(self, parent=None):
        QDialog.__init__(self, parent)
        self.setWindowTitle("📥 다운로드 매니저")
        self.resize(400, 500)
        self.setStyleSheet("background-color: #1e1e2e;")
        
        self._items: dict[str, DownloadItemWidget] = {}
        self._workers: dict[str, object] = {} # task_id -> worker
        
        layout = QVBoxLayout(self)
        
        title = QLabel("현재 진행 중인 작업")
        title.setStyleSheet("color: #fab387; font-size: 14px; font-weight: bold; margin: 10px;")
        layout.addWidget(title)
        
        # 스크롤 영역
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("border: none; background: transparent;")
        
        self.scroll_content = QWidget()
        self.list_layout = QVBoxLayout(self.scroll_content)
        self.list_layout.setAlignment(Qt.AlignTop)
        self.list_layout.setSpacing(10)
        
        self.scroll.setWidget(self.scroll_content)
        layout.addWidget(self.scroll)
        
        # 하단 제어
        btn_layout = QHBoxLayout()
        self.clear_btn = QPushButton("완료 항목 제거")
        self.clear_btn.setStyleSheet("background: #45475a; color: #cdd6f4; padding: 5px;")
        self.clear_btn.clicked.connect(self.clear_finished)
        btn_layout.addStretch()
        btn_layout.addWidget(self.clear_btn)
        layout.addLayout(btn_layout)

    def add_download(self, task_id: str, filename: str, worker):
        item = DownloadItemWidget(task_id, filename)
        item.cancelRequested.connect(self.cancel_task)
        self.list_layout.addWidget(item)
        self._items[task_id] = item
        self._workers[task_id] = worker
        
        # 워커 시그널 연결
        worker.signals.progress.connect(self.on_progress)
        worker.signals.finished.connect(self.on_finished)
        worker.signals.error.connect(self.on_error)

    def cancel_task(self, task_id: str):
        """취소 또는 항목 삭제 처리."""
        item = self._items.get(task_id)
        if not item: return

        if not item._is_done:
            # 진행 중일 때는 '취소' (워커 중단 및 UI 정지)
            if task_id in self._workers:
                self._workers[task_id].cancel()
                item._is_done = True
                item.status_label.setText("취소됨")
                item.status_label.setStyleSheet("color: #f38ba8;")
                
                # [무한 로딩 방지] 프로그레스 바 상태 초기화
                item.progress_bar.setRange(0, 100)
                item.progress_bar.setValue(0)
                item.progress_bar.setStyleSheet("QProgressBar::chunk { background: #45475a; }")
                item.setCursor(Qt.ArrowCursor)

                item.cancel_btn.setStyleSheet("background: #45475a; color: #cdd6f4;")
        else:
            # 완료/취소/에러 상태일 때는 '항목 삭제'
            self.remove_item(task_id)

    def remove_item(self, task_id: str):
        """UI 및 리스트에서 실제 항목 제거."""
        if task_id in self._items:
            item = self._items.pop(task_id)
            self._workers.pop(task_id, None)
            item.setParent(None)
            item.deleteLater()

    @Slot(str, int, int)
    def on_progress(self, task_id, current, total):
        if task_id in self._items:
            self._items[task_id].update_progress(current, total)

    @Slot(str, str)
    def on_finished(self, task_id, path):
        if task_id in self._items:
            item = self._items[task_id]
            item.mark_finished(path)

    @Slot(str, str)
    def on_error(self, task_id, err_msg):
        if task_id in self._items:
            item = self._items[task_id]
            item._is_done = True
            item.status_label.setText(f"❌ 에러: {err_msg}")
            item.status_label.setStyleSheet("color: #f38ba8;")
            item.progress_bar.setStyleSheet("QProgressBar::chunk { background: #f38ba8; }")
            item.cancel_btn.setEnabled(True)

    def clear_finished(self):
        """완료(Done)된 모든 항목 일괄 삭제."""
        # 딕셔너리 순회 중 삭제 에러 방지를 위해 리스트 복사
        to_remove = [tid for tid, item in self._items.items() if item._is_done]
        
        for tid in to_remove:
            self.remove_item(tid)
