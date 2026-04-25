from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QFrame, QWidget, QScrollArea, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QColor, QPalette

class StatusBox(QFrame):
    """A styled box to display a single metric/status"""
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setObjectName("StatusBox")
        self.setStyleSheet("""
            QFrame#StatusBox {
                background-color: #1e1e1e;
                border: 1px solid #333333;
                border-radius: 6px;
                padding: 10px;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(4)
        
        self.lbl_title = QLabel(title)
        self.lbl_title.setStyleSheet("color: #888888; font-size: 11px; font-weight: bold;")
        
        self.lbl_value = QLabel("N/A")
        self.lbl_value.setStyleSheet("color: #ffffff; font-size: 14px; font-weight: bold;")
        self.lbl_value.setWordWrap(True)
        
        layout.addWidget(self.lbl_title)
        layout.addWidget(self.lbl_value)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

    def set_value(self, text, color="#ffffff"):
        self.lbl_value.setText(str(text))
        self.lbl_value.setStyleSheet(f"color: {color}; font-size: 14px; font-weight: bold;")

class FetchDebugger(QDialog):
    def __init__(self, main_win, parent=None):
        super().__init__(parent)
        self.main_win = main_win
        
        self.setWindowTitle("Fetch Pipeline Debugger")
        self.resize(450, 600)
        
        # Always on top, utility window style
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint | Qt.Tool)
        
        self.setStyleSheet("""
            QDialog {
                background-color: #121212;
                color: #e0e0e0;
                font-family: "Inter", "Segoe UI", sans-serif;
            }
            QLabel {
                font-family: "Inter", "Segoe UI", sans-serif;
            }
            QGroupBox {
                border: 1px solid #333333;
                border-radius: 8px;
                margin-top: 2ex;
                font-weight: bold;
                color: #00d2ff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 5px;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)
        
        # Header
        header = QLabel("📡 Fetch State Monitor")
        header.setStyleSheet("font-size: 18px; font-weight: 800; color: #ffffff;")
        layout.addWidget(header)
        
        # Model State Section
        model_layout = QHBoxLayout()
        self.box_table = StatusBox("ACTIVE TABLE")
        self.box_fetching = StatusBox("FETCHING STATE")
        model_layout.addWidget(self.box_table)
        model_layout.addWidget(self.box_fetching)
        layout.addLayout(model_layout)
        
        # Data Metrics Section
        metrics_layout = QHBoxLayout()
        self.box_loaded = StatusBox("LOADED ROWS")
        self.box_exposed = StatusBox("EXPOSED ROWS")
        self.box_chunk = StatusBox("CHUNK SIZE")
        metrics_layout.addWidget(self.box_loaded)
        metrics_layout.addWidget(self.box_exposed)
        metrics_layout.addWidget(self.box_chunk)
        layout.addLayout(metrics_layout)
        
        # FetchContext Section
        self.box_active_ctx = StatusBox("ACTIVE FETCH CONTEXT")
        self.box_pending_ctx = StatusBox("PENDING FETCH CONTEXT")
        layout.addWidget(self.box_active_ctx)
        layout.addWidget(self.box_pending_ctx)
        
        # Navigation Section
        nav_layout = QHBoxLayout()
        self.box_nav_state = StatusBox("HISTORY NAV STATE")
        self.box_nav_target = StatusBox("JUMP TARGET")
        nav_layout.addWidget(self.box_nav_state)
        nav_layout.addWidget(self.box_nav_target)
        layout.addLayout(nav_layout)
        
        layout.addStretch()
        
        # Setup Polling Timer
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._update_state)
        self.poll_timer.start(100) # 100ms updates

    def _update_state(self):
        # 1. Get current model
        idx = self.main_win.stacked.currentIndex()
        if idx <= 0:
            self.box_table.set_value("Dashboard / Settings", "#888")
            self._clear_model_stats()
            return
            
        page_widget = self.main_win.stacked.widget(idx)
        model = getattr(page_widget, "_source_model", None)
        
        if not model:
            self._clear_model_stats()
            return
            
        self.box_table.set_value(model.table_name, "#00d2ff")
        
        # Fetching State
        is_fetching = getattr(model, "_fetching", False)
        if is_fetching:
            self.box_fetching.set_value("🟢 RUNNING", "#00ff00")
        else:
            self.box_fetching.set_value("⚪ IDLE", "#888888")
            
        # Metrics
        total = getattr(model, "_total_count", 0)
        loaded = getattr(model, "_loaded_count", 0)
        exposed = getattr(model, "_exposed_rows", 0)
        chunk = getattr(model, "_chunk_size", 0)
        
        self.box_loaded.set_value(f"{loaded:,} / {total:,}")
        self.box_exposed.set_value(f"{exposed:,}")
        self.box_chunk.set_value(f"{chunk}")
        
        # Fetch Contexts
        active_ctx = getattr(model, "_active_fetch_ctx", None)
        pending_ctx = getattr(model, "_pending_fetch_ctx", None)
        
        if active_ctx:
            src = active_ctx.source.upper()
            sid = active_ctx.session_id[:8]
            target = active_ctx.params.get("target_row_id", "N/A")
            self.box_active_ctx.set_value(f"[{src}] ID: {sid}\nTarget: {target}", "#ffaa00" if src == "JUMP" else "#ffffff")
        else:
            self.box_active_ctx.set_value("None", "#555")
            
        if pending_ctx:
            src = pending_ctx.source.upper()
            sid = pending_ctx.session_id[:8]
            target = pending_ctx.params.get("target_row_id", "N/A")
            self.box_pending_ctx.set_value(f"[{src}] ID: {sid}\nTarget: {target}", "#ff5555")
        else:
            self.box_pending_ctx.set_value("None", "#555")
            
        # Navigation
        try:
            navigator = self.main_win._history_panel._navigator
            is_nav = getattr(navigator, "_is_navigating", False)
            if is_nav:
                self.box_nav_state.set_value("🔴 NAVIGATING", "#ff5555")
                ctx = getattr(navigator, "_ctx", {})
                target_id = ctx.get("row_id", "Unknown")
                self.box_nav_target.set_value(target_id, "#ffaa00")
            else:
                self.box_nav_state.set_value("⚪ IDLE", "#888888")
                self.box_nav_target.set_value("N/A", "#555")
        except Exception:
            pass

    def _clear_model_stats(self):
        self.box_fetching.set_value("N/A", "#555")
        self.box_loaded.set_value("N/A", "#555")
        self.box_exposed.set_value("N/A", "#555")
        self.box_chunk.set_value("N/A", "#555")
        self.box_active_ctx.set_value("None", "#555")
        self.box_pending_ctx.set_value("None", "#555")
