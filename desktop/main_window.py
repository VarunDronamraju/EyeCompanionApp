"""
Main Application Window - Eye Tracking Interface
Complete UI with camera feed, real-time stats, and controls
"""

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                            QLabel, QPushButton, QFrame, QGridLayout, QProgressBar,
                            QSystemTrayIcon, QMenu, QMessageBox, QSpacerItem, 
                            QSizePolicy, QTextEdit)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QThread, pyqtSlot
from PyQt6.QtGui import QFont, QPixmap, QPainter, QColor, QBrush, QAction, QIcon
import random
import time
import logging
from datetime import datetime, timedelta

# Import the real EyeTracker
from .eye_tracker import EyeTracker
# Import database manager
from .database import SQLiteManager
# Import the real SystemMonitor
from .services.system_monitor import SystemMonitor

class SystemMonitorThread(QThread):
    """Thread wrapper for real SystemMonitor to update UI"""
    stats_updated = pyqtSignal(dict)
    
    def __init__(self, system_monitor):
        super().__init__()
        self.system_monitor = system_monitor
        self.running = False
    
    def start_monitoring(self):
        """Start system monitoring"""
        self.running = True
        self.start()
    
    def stop_monitoring(self):
        """Stop monitoring"""
        self.running = False
    
    def run(self):
        """Monitor system performance and emit updates"""
        while self.running:
            try:
                # Get current metrics from the real SystemMonitor
                metrics = self.system_monitor.get_current_metrics()
                if metrics:
                    stats = {
                        'cpu': round(metrics.cpu_percent, 1),
                        'memory': round(metrics.memory_used_mb, 1),
                        'memory_percent': round(metrics.memory_percent, 1),
                        'battery': metrics.battery_percent or 0,
                        'battery_plugged': metrics.battery_plugged,
                        'disk_usage': round(metrics.disk_usage_percent, 1),
                        'network_sent': round(metrics.network_sent_mb, 2),
                        'network_recv': round(metrics.network_recv_mb, 2),
                        'monitor_overhead': round(self.system_monitor.monitor_overhead, 2),
                        'is_charging': metrics.is_charging
                    }
                    self.stats_updated.emit(stats)
            except Exception as e:
                print(f"Error updating system stats: {e}")
            
            self.sleep(2)  # Update every 2 seconds

class MainWindow(QMainWindow):
    """Main application window"""
    
    logout_requested = pyqtSignal()
    
    def __init__(self, user_data):
        super().__init__()
        self.user_data = user_data
        self.eye_tracker = None
        self.system_monitor = None
        self.system_monitor_thread = None
        self.session_timer = QTimer()
        self.session_start_time = None
        self.is_tracking = False
        self.tray_icon = None
        
        # Initialize database manager with user data
        self.db_manager = SQLiteManager(user_data=user_data)
        
        # Initialize logger
        self.logger = logging.getLogger(__name__)
        
        self.setup_ui()
        self.setup_system_tray()
        self.setup_timers()
        self.apply_styles()
        
        # Auto-create session on app launch
        self.auto_create_session()
        
        # Start monitoring by default
        self.start_system_monitoring()
    
    def setup_ui(self):
        """Setup the main user interface"""
        self.setWindowTitle("Wellness at Work - Eye Tracker")
        self.setMinimumSize(1000, 700)
        self.resize(1200, 800)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QHBoxLayout()
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(12, 12, 12, 12)
        
        # Create sections
        self.create_left_panel(main_layout)
        self.create_camera_section(main_layout)
        
        central_widget.setLayout(main_layout)
        
        # Add bottom section
        self.create_bottom_section()
        
        # Center window
        self.center_window()
    
    def create_left_panel(self, parent_layout):
        """Create left panel with stats and controls"""
        left_panel = QWidget()
        left_panel.setFixedWidth(350)
        left_layout = QVBoxLayout()
        left_layout.setSpacing(12)
        
        # Session statistics card
        self.create_session_card(left_layout)
        
        # Performance monitoring card
        self.create_performance_card(left_layout)
        
        # Spacer
        left_layout.addItem(QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, 
                                       QSizePolicy.Policy.Expanding))
        
        left_panel.setLayout(left_layout)
        parent_layout.addWidget(left_panel)
    
    def create_session_card(self, layout):
        """Create session statistics card"""
        session_card = QFrame()
        session_card.setObjectName("sessionCard")
        card_layout = QVBoxLayout()
        card_layout.setContentsMargins(16, 16, 16, 16)  # Reduced margins
        card_layout.setSpacing(15)  # Reduced spacing
        
        # Title
        title_label = QLabel("Blink Session Details")
        title_label.setObjectName("cardTitle")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Stats container - vertical layout
        stats_frame = QFrame()
        stats_layout = QVBoxLayout()
        stats_layout.setSpacing(12)  # Reduced spacing for better fit
        stats_layout.setContentsMargins(8, 8, 8, 8)  # Reduced margins to prevent truncation
        
        # Blink count
        self.count_widget = self.create_stat_widget("0", "Blink Count")
        stats_layout.addWidget(self.count_widget)
        
        # Blink rate
        self.rate_widget = self.create_stat_widget("0.0", "Blinks/Min")
        stats_layout.addWidget(self.rate_widget)
        
        # Time elapsed
        self.time_widget = self.create_stat_widget("00:00:00", "Session Time")
        stats_layout.addWidget(self.time_widget)
        
        stats_frame.setLayout(stats_layout)
        
        # Control buttons
        controls_frame = QFrame()
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(8)
        
        self.start_btn = QPushButton("Start")
        self.start_btn.setObjectName("startButton")
        self.start_btn.clicked.connect(self.toggle_tracking)
        
        self.reset_btn = QPushButton("Reset")
        self.reset_btn.setObjectName("resetButton")
        self.reset_btn.clicked.connect(self.reset_session)
        self.reset_btn.setEnabled(False)  # Disable until session starts
        
        controls_layout.addWidget(self.start_btn)
        controls_layout.addWidget(self.reset_btn)
        
        controls_frame.setLayout(controls_layout)
        
        card_layout.addWidget(title_label)
        card_layout.addWidget(stats_frame)
        card_layout.addWidget(controls_frame)
        
        session_card.setLayout(card_layout)
        layout.addWidget(session_card)
    
    def create_stat_widget(self, value, label):
        """Create individual stat widget"""
        widget = QFrame()
        widget.setObjectName("statWidget")
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(4)
        layout.setContentsMargins(4, 4, 4, 4)  # Minimal margins to prevent text truncation
        
        value_label = QLabel(value)
        value_label.setObjectName("statValue")
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        value_label.setWordWrap(True)  # Allow text wrapping
        
        label_label = QLabel(label)
        label_label.setObjectName("statLabel")
        label_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label_label.setWordWrap(True)  # Allow text wrapping
        
        layout.addWidget(value_label)
        layout.addWidget(label_label)
        
        widget.setLayout(layout)
        
        # Store references for updates
        widget.value_label = value_label
        widget.label_label = label_label
        
        return widget
    
    def create_performance_card(self, layout):
        """Create system performance monitoring card"""
        performance_card = QFrame()
        performance_card.setObjectName("performanceCard")
        card_layout = QVBoxLayout()
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(12)
        
        # Title
        title_label = QLabel("System Performance")
        title_label.setObjectName("cardSubtitle")
        
        # Performance metrics
        self.cpu_row = self.create_metric_row("CPU Usage", "0%")
        self.memory_row = self.create_metric_row("Memory Usage", "0 MB")
        self.battery_row = self.create_metric_row("Battery Level", "0%")
        self.disk_row = self.create_metric_row("Disk Usage", "0%")
        self.network_row = self.create_metric_row("Network I/O", "0 MB/s")
        self.energy_row = self.create_metric_row("Monitor Overhead", "0%")
        
        card_layout.addWidget(title_label)
        card_layout.addWidget(self.cpu_row)
        card_layout.addWidget(self.memory_row)
        card_layout.addWidget(self.battery_row)
        card_layout.addWidget(self.disk_row)
        card_layout.addWidget(self.network_row)
        card_layout.addWidget(self.energy_row)
        
        performance_card.setLayout(card_layout)
        layout.addWidget(performance_card)
    
    def create_metric_row(self, name, value):
        """Create performance metric row"""
        row = QFrame()
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 8, 0, 8)
        
        name_label = QLabel(name)
        name_label.setObjectName("metricName")
        name_label.setStyleSheet("color: #000000; font-weight: 500;")  # Black text for visibility
        
        value_label = QLabel(value)
        value_label.setObjectName("metricValue")
        
        layout.addWidget(name_label)
        layout.addStretch()
        layout.addWidget(value_label)
        
        row.setLayout(layout)
        
        # Store reference for updates
        row.value_label = value_label
        
        return row
    
    def create_camera_section(self, parent_layout):
        """Create camera feed section"""
        camera_widget = QWidget()
        camera_layout = QVBoxLayout()
        camera_layout.setSpacing(12)
        
        # Camera header
        camera_header = QFrame()
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(16, 16, 16, 0)
        
        camera_title = QLabel("Eye Tracking Camera")
        camera_title.setObjectName("cameraTitle")
        
        # Status indicator
        self.status_widget = QFrame()
        self.status_widget.setObjectName("statusWidget")
        status_layout = QHBoxLayout()
        status_layout.setContentsMargins(8, 4, 8, 4)
        status_layout.setSpacing(4)
        
        self.status_dot = QLabel("●")
        self.status_dot.setObjectName("statusDot")
        self.status_text = QLabel("Ready")
        self.status_text.setObjectName("statusText")
        
        status_layout.addWidget(self.status_dot)
        status_layout.addWidget(self.status_text)
        self.status_widget.setLayout(status_layout)
        
        header_layout.addWidget(camera_title)
        header_layout.addStretch()
        header_layout.addWidget(self.status_widget)
        camera_header.setLayout(header_layout)
        
        # Camera display
        self.camera_label = QLabel()
        self.camera_label.setObjectName("cameraDisplay")
        self.camera_label.setMinimumSize(400, 300)
        self.camera_label.setMaximumSize(800, 600)
        self.camera_label.setScaledContents(True)
        self.camera_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.camera_label.setStyleSheet("""
            QLabel#cameraDisplay {
                background-color: #2c2c2c;
                border: 2px solid #495057;
                border-radius: 8px;
                color: #6c757d;
                font-size: 16px;
            }
        """)
        self.camera_label.setText("Camera feed will display here\nEnsure proper lighting for optimal tracking")
        
        camera_layout.addWidget(camera_header)
        camera_layout.addWidget(self.camera_label, 1)
        
        camera_widget.setLayout(camera_layout)
        parent_layout.addWidget(camera_widget, 1)
    
    def create_bottom_section(self):
        """Create bottom profile section"""
        # Add to main window as status bar alternative
        profile_widget = QWidget()
        profile_widget.setObjectName("profileSection")
        profile_widget.setFixedHeight(80)
        
        profile_layout = QHBoxLayout()
        profile_layout.setContentsMargins(24, 16, 24, 16)
        
        # User info
        user_info = QFrame()
        user_layout = QHBoxLayout()
        user_layout.setSpacing(10)
        
        # Avatar
        if self.user_data.get('picture'):
            # TODO: Load actual profile picture from URL
            avatar_label = QLabel(self.user_data['name'][:2].upper())
        else:
            avatar_label = QLabel(self.user_data['name'][:2].upper())
        avatar_label.setObjectName("profileAvatar")
        avatar_label.setFixedSize(32, 32)
        avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # User details
        details_widget = QWidget()
        details_layout = QVBoxLayout()
        details_layout.setSpacing(2)
        details_layout.setContentsMargins(0, 0, 0, 0)
        
        name_label = QLabel(self.user_data['name'])
        name_label.setObjectName("profileName")
        
        email_label = QLabel(self.user_data['email'])
        email_label.setObjectName("profileEmail")
        
        # Add authentication status
        auth_status = "🔐 Authenticated" if self.user_data.get('access_token') else "🔐 Authenticated"
        status_label = QLabel(auth_status)
        status_label.setObjectName("profileStatus")
        status_label.setStyleSheet("color: #6c757d; font-size: 11px;")
        
        details_layout.addWidget(name_label)
        details_layout.addWidget(email_label)
        details_layout.addWidget(status_label)
        details_widget.setLayout(details_layout)
        
        user_layout.addWidget(avatar_label)
        user_layout.addWidget(details_widget)
        user_info.setLayout(user_layout)
        
        # Action buttons
        actions_widget = QWidget()
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(12)
        
        dashboard_btn = QPushButton("Dashboard")
        dashboard_btn.setObjectName("actionButton")
        dashboard_btn.clicked.connect(self.open_dashboard)
        
        history_btn = QPushButton("History")
        history_btn.setObjectName("actionButton")
        history_btn.clicked.connect(self.view_session_history)
        
        sync_btn = QPushButton("Sync")
        sync_btn.setObjectName("actionButton")
        sync_btn.clicked.connect(self.manual_sync)
        
        settings_btn = QPushButton("Settings")
        settings_btn.setObjectName("actionButton")
        settings_btn.clicked.connect(self.open_settings)
        
        logout_btn = QPushButton("Logout")
        logout_btn.setObjectName("logoutButton")
        logout_btn.clicked.connect(self.logout)
        
        actions_layout.addWidget(dashboard_btn)
        actions_layout.addWidget(history_btn)
        actions_layout.addWidget(sync_btn)
        actions_layout.addWidget(settings_btn)
        actions_layout.addWidget(logout_btn)
        actions_widget.setLayout(actions_layout)
        
        profile_layout.addWidget(user_info)
        profile_layout.addStretch()
        profile_layout.addWidget(actions_widget)
        
        profile_widget.setLayout(profile_layout)
        
        # Add to main layout
        main_widget = self.centralWidget()
        main_layout = main_widget.layout()
        
        # Create new layout with profile at bottom
        container_widget = QWidget()
        container_layout = QVBoxLayout()
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        
        # Move existing content
        old_layout = main_widget.layout()
        if old_layout:
            # Create temporary widget to hold existing content
            temp_widget = QWidget()
            temp_widget.setLayout(old_layout)
            container_layout.addWidget(temp_widget, 1)
        
        container_layout.addWidget(profile_widget)
        container_widget.setLayout(container_layout)
        self.setCentralWidget(container_widget)
    
    def setup_system_tray(self):
        """Setup system tray functionality"""
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon = QSystemTrayIcon(self)
            
            # Create tray icon (placeholder)
            icon = self.create_tray_icon()
            self.tray_icon.setIcon(icon)
            
            # Create tray menu
            tray_menu = QMenu()
            
            show_action = QAction("Show Window", self)
            show_action.triggered.connect(self.show)
            
            start_action = QAction("Start Tracking", self)
            start_action.triggered.connect(self.toggle_tracking)
            
            sync_action = QAction("Sync Now", self)
            sync_action.triggered.connect(self.manual_sync)
            
            quit_action = QAction("Quit", self)
            quit_action.triggered.connect(self.quit_application)
            
            tray_menu.addAction(show_action)
            tray_menu.addSeparator()
            tray_menu.addAction(start_action)
            tray_menu.addAction(sync_action)
            tray_menu.addSeparator()
            tray_menu.addAction(quit_action)
            
            self.tray_icon.setContextMenu(tray_menu)
            self.tray_icon.activated.connect(self.tray_icon_activated)
            self.tray_icon.show()
    
    def create_tray_icon(self):
        """Create system tray icon"""
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        painter.setBrush(QBrush(QColor("#495057")))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(2, 2, 28, 28)
        
        painter.setBrush(QBrush(QColor("white")))
        painter.drawEllipse(8, 12, 16, 8)
        
        painter.setBrush(QBrush(QColor("#495057")))
        painter.drawEllipse(14, 14, 4, 4)
        
        painter.end()
        return QIcon(pixmap)
    
    def setup_timers(self):
        """Setup application timers"""
        # Session timer for elapsed time display
        self.session_timer.timeout.connect(self.update_session_time)
        
    def start_system_monitoring(self):
        """Start system performance monitoring"""
        if not self.system_monitor:
            # Initialize the real SystemMonitor with a separate database for performance logs
            self.system_monitor = SystemMonitor(db_path="performance_monitor.db")
            # Start the monitoring service
            self.system_monitor.start_monitoring()
            
            # Create and start the UI update thread
            self.system_monitor_thread = SystemMonitorThread(self.system_monitor)
            self.system_monitor_thread.stats_updated.connect(self.update_performance_stats)
            self.system_monitor_thread.start_monitoring()
        
        elif not self.system_monitor_thread.isRunning():
            self.system_monitor_thread.start_monitoring()
    
    def toggle_tracking(self):
        """Toggle eye tracking on/off"""
        if not self.eye_tracker:
            self.start_tracking()
        elif self.is_tracking and not self.eye_tracker.paused:
            self.pause_tracking()
        elif self.eye_tracker.paused:
            self.resume_tracking()
        else:
            self.stop_tracking()
    
    def start_tracking(self):
        """Start eye tracking"""
        if not self.eye_tracker:
            self.eye_tracker = EyeTracker()
            self.eye_tracker.blink_detected.connect(self.update_blink_stats)
            self.eye_tracker.frame_updated.connect(self.update_camera_frame)
            self.eye_tracker.status_changed.connect(self.update_tracking_status)
            self.eye_tracker.error_occurred.connect(self.handle_tracking_error)
        
        self.eye_tracker.start_tracking()
        # Don't start timer yet - wait for camera initialization
        self.is_tracking = True
        self.start_btn.setText("Pause")
        self.reset_btn.setEnabled(True)  # Enable reset button
        self.update_status("Live", "#28a745")
        
        # TODO: Real implementation
        """
        REAL IMPLEMENTATION PLACEHOLDER:
        
        from desktop.eye_tracker import EyeTracker
        from desktop.database.sqlite_manager import SQLiteManager
        
        # Start local session
        self.db_manager = SQLiteManager()
        self.local_session_id = self.db_manager.create_session()
        
        # Start cloud session if authenticated
        if self.user_data.get('access_token'):
            # API call to start cloud session
            pass
        
        # Initialize real eye tracker
        self.eye_tracker = EyeTracker()
        self.eye_tracker.start()
        """
    
    def pause_tracking(self):
        """Pause eye tracking"""
        if self.eye_tracker:
            self.eye_tracker.pause_tracking()
        
        self.session_timer.stop()
        self.start_btn.setText("Resume")
        self.reset_btn.setEnabled(True)  # Keep reset enabled when paused
        self.update_status("Paused", "#ffc107")
        
        # Show notification
        if self.tray_icon:
            self.tray_icon.showMessage("Wellness at Work", "Eye tracking paused", 
                                     QSystemTrayIcon.MessageIcon.Information, 3000)
    
    def resume_tracking(self):
        """Resume eye tracking"""
        if self.eye_tracker:
            self.eye_tracker.resume_tracking()
        
        # Resume timer if it was active
        if self.session_start_time and not self.session_timer.isActive():
            self.session_timer.start(1000)  # Update every second
        self.start_btn.setText("Pause")
        self.update_status("Live", "#28a745")
        
        # Show notification
        if self.tray_icon:
            self.tray_icon.showMessage("Wellness at Work", "Eye tracking resumed", 
                                     QSystemTrayIcon.MessageIcon.Information, 3000)
    
    def reset_session(self):
        """Reset session data and end tracking"""
        # Stop tracking if active
        if self.is_tracking:
            self.stop_tracking()
        
        # Reset UI elements
        self.count_widget.value_label.setText("0")
        self.rate_widget.value_label.setText("0.0")
        self.time_widget.value_label.setText("00:00:00")
        
        # Reset session timer
        self.session_start_time = None
        self.session_timer.stop()
        
        # Show notification
        if self.tray_icon:
            self.tray_icon.showMessage("Wellness at Work", "Session ended", 
                                     QSystemTrayIcon.MessageIcon.Information, 2000)
        
        self.logger.info("Session reset and ended")
    
    def stop_tracking(self):
        """Stop eye tracking"""
        if self.eye_tracker:
            self.eye_tracker.stop_tracking()
        
        self.session_timer.stop()
        self.is_tracking = False
        self.start_btn.setText("Start")
        self.reset_btn.setEnabled(False)  # Disable reset button
        self.update_status("Inactive", "#6c757d")  # Changed to "Inactive"
        
        # Show notification
        if self.tray_icon:
            self.tray_icon.showMessage("Wellness at Work", "Eye tracking stopped", 
                                     QSystemTrayIcon.MessageIcon.Information, 3000)
    
    def reset_session(self):
        """Reset current session"""
        if self.eye_tracker:
            self.eye_tracker.reset_session()
        
        self.session_start_time = datetime.now() if self.is_tracking else None
        
        # Reset UI
        self.count_widget.value_label.setText("0")
        self.rate_widget.value_label.setText("0.0")
        self.time_widget.value_label.setText("00:00")
        
        QMessageBox.information(self, "Session Reset", "Session data has been reset.")
    
    def auto_create_session(self):
        """Auto-create session when app launches"""
        try:
            session_id = self.db_manager.auto_create_session()
            self.logger.info(f"Auto-created session with ID: {session_id}")
        except Exception as e:
            self.logger.error(f"Error auto-creating session: {e}")
    
    def update_blink_stats(self, count, rate):
        """Update blink statistics display and log to database"""
        self.count_widget.value_label.setText(str(count))
        
        # Log blink data to database in real-time
        if self.db_manager and self.is_tracking:
            try:
                self.db_manager.log_blink(count, rate)
                self.logger.debug(f"Blink logged to database: count={count}, rate={rate:.1f}")
            except Exception as e:
                self.logger.error(f"Error logging blink to database: {e}")
        
        # Don't update rate here - it's updated every second in update_session_time
    
    def update_camera_frame(self, pixmap):
        """Update camera display with new frame"""
        self.camera_label.setPixmap(pixmap)
    
    def update_session_time(self):
        """Update session elapsed time and blink rate"""
        if self.session_start_time:
            elapsed = datetime.now() - self.session_start_time
            hours, remainder = divmod(elapsed.total_seconds(), 3600)
            minutes, seconds = divmod(remainder, 60)
            time_str = f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"
            self.time_widget.value_label.setText(time_str)
            
            # Update blink rate every second based on elapsed time
            if self.eye_tracker:
                stats = self.eye_tracker.get_session_stats()
                blink_rate = stats.get('blink_rate', 0.0)
                self.rate_widget.value_label.setText(f"{blink_rate:.1f}")
    
    @pyqtSlot(dict)
    def update_performance_stats(self, stats):
        """Update system performance statistics and log to database"""
        # Update CPU usage with color coding
        cpu_text = f"{stats['cpu']}%"
        if stats['cpu'] > 80:
            self.cpu_row.value_label.setStyleSheet("color: #dc3545; font-weight: bold;")  # Red for high CPU
        elif stats['cpu'] > 60:
            self.cpu_row.value_label.setStyleSheet("color: #ffc107; font-weight: bold;")  # Yellow for moderate CPU
        else:
            self.cpu_row.value_label.setStyleSheet("color: #28a745;")  # Green for normal CPU
        self.cpu_row.value_label.setText(cpu_text)
        
        # Update memory usage (show both MB and percentage) with color coding
        memory_text = f"{stats['memory']} MB ({stats['memory_percent']}%)"
        if stats['memory_percent'] > 85:
            self.memory_row.value_label.setStyleSheet("color: #dc3545; font-weight: bold;")  # Red for high memory
        elif stats['memory_percent'] > 70:
            self.memory_row.value_label.setStyleSheet("color: #ffc107; font-weight: bold;")  # Yellow for moderate memory
        else:
            self.memory_row.value_label.setStyleSheet("color: #28a745;")  # Green for normal memory
        self.memory_row.value_label.setText(memory_text)
        
        # Update battery level with charging status and color coding
        battery_text = f"{stats['battery']}%"
        if stats['battery_plugged'] is not None:
            battery_text += " 🔌" if stats['battery_plugged'] else " 🔋"
        
        if stats['battery'] < 20:
            self.battery_row.value_label.setStyleSheet("color: #dc3545; font-weight: bold;")  # Red for low battery
        elif stats['battery'] < 50:
            self.battery_row.value_label.setStyleSheet("color: #ffc107; font-weight: bold;")  # Yellow for moderate battery
        else:
            self.battery_row.value_label.setStyleSheet("color: #28a745;")  # Green for good battery
        self.battery_row.value_label.setText(battery_text)
        
        # Update disk usage with color coding
        disk_text = f"{stats['disk_usage']}%"
        if stats['disk_usage'] > 90:
            self.disk_row.value_label.setStyleSheet("color: #dc3545; font-weight: bold;")  # Red for high disk usage
        elif stats['disk_usage'] > 80:
            self.disk_row.value_label.setStyleSheet("color: #ffc107; font-weight: bold;")  # Yellow for moderate disk usage
        else:
            self.disk_row.value_label.setStyleSheet("color: #28a745;")  # Green for normal disk usage
        self.disk_row.value_label.setText(disk_text)
        
        # Update network I/O (combined sent/received)
        network_total = stats['network_sent'] + stats['network_recv']
        network_text = f"{network_total:.2f} MB/s"
        self.network_row.value_label.setText(network_text)
        
        # Update monitor overhead with color coding
        overhead_text = f"{stats['monitor_overhead']}%"
        if stats['monitor_overhead'] > 1.0:
            self.energy_row.value_label.setStyleSheet("color: #dc3545; font-weight: bold;")  # Red for high overhead
        else:
            self.energy_row.value_label.setStyleSheet("color: #28a745;")  # Green for low overhead
        self.energy_row.value_label.setText(overhead_text)
        
        # Log performance data to database
        if self.db_manager and self.is_tracking:
            try:
                self.db_manager.log_performance(
                    cpu_usage=stats['cpu'],
                    memory_usage=stats['memory'],
                    battery_level=stats['battery']
                )
            except Exception as e:
                self.logger.error(f"Error logging performance to database: {e}")
    
    def update_status(self, text, color):
        """Update tracking status display"""
        self.status_text.setText(text)
        self.status_dot.setStyleSheet(f"QLabel {{ color: {color}; }}")
    
    def update_tracking_status(self, status):
        """Update tracking status from eye tracker"""
        if status == "Live Tracking":
            self.update_status("Live", "#28a745")
            # Start timer only when camera is ready and tracking starts
            if self.is_tracking and not self.session_timer.isActive():
                self.session_start_time = datetime.now()
                self.session_timer.start(1000)  # Update every second
                self.logger.info("Session timer started - camera initialized")
            # Show notification only after camera is initialized and tracking starts
            if self.tray_icon and self.is_tracking:
                self.tray_icon.showMessage("Wellness at Work", "Eye tracking started", 
                                         QSystemTrayIcon.MessageIcon.Information, 3000)
        elif status == "Paused":
            self.update_status("Paused", "#ffc107")
        elif status == "Stopped":
            self.update_status("Inactive", "#6c757d")  # Changed to "Inactive"
        elif status == "Starting camera...":
            self.update_status("Initializing...", "#17a2b8")
        elif status == "Camera initialized":
            self.update_status("Camera Ready", "#17a2b8")
        elif status == "Camera not available":
            self.update_status("Inactive", "#dc3545")  # Red for camera error
        else:
            self.update_status("Inactive", "#6c757d")  # Default to inactive
    
    def handle_tracking_error(self, error_message):
        """Handle eye tracking errors"""
        self.update_status("Error", "#dc3545")
        QMessageBox.critical(self, "Eye Tracking Error", 
                           f"An error occurred during eye tracking:\n{error_message}")
        self.logger.error(f"Eye tracking error: {error_message}")
    
    def tray_icon_activated(self, reason):
        """Handle tray icon activation"""
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.isVisible():
                self.hide()
            else:
                self.show()
                self.raise_()
                self.activateWindow()
    
    def open_dashboard(self):
        """Open web dashboard"""
        msg = QMessageBox(self)
        msg.setWindowTitle("Dashboard")
        msg.setText("Web dashboard would open in browser\n(Feature not implemented in demo)")
        msg.setStyleSheet("QLabel { color: #000000; }")
        msg.exec()
        # TODO: Open Streamlit dashboard
    
    def manual_sync(self):
        """Perform manual data synchronization"""
        msg = QMessageBox(self)
        msg.setWindowTitle("Sync")
        msg.setText("Data synchronization completed\n(Mock implementation)")
        msg.setStyleSheet("QLabel { color: #000000; }")
        msg.exec()
        # TODO: Real sync implementation
    
    def view_session_history(self):
        """View session history from database"""
        if not self.db_manager:
            msg = QMessageBox(self)
            msg.setWindowTitle("Database Error")
            msg.setText("Database not available")
            msg.setStyleSheet("QLabel { color: #000000; }")
            msg.exec()
            return
        
        try:
            # Get user-specific sessions (authentication required)
            user_id = self.user_data.get('id')
            if not user_id:
                msg = QMessageBox(self)
                msg.setWindowTitle("Authentication Required")
                msg.setText("Please authenticate with Google to view session history")
                msg.setStyleSheet("QLabel { color: #000000; }")
                msg.exec()
                return
            
            sessions = self.db_manager.get_recent_sessions(limit=10, user_id=user_id)
            
            if not sessions:
                msg = QMessageBox(self)
                msg.setWindowTitle("Session History")
                msg.setText("No sessions found in database")
                msg.setStyleSheet("QLabel { color: #000000; }")
                msg.exec()
                return
            
            # Create session history display
            history_text = "Recent Sessions:\n\n"
            for session in sessions:
                duration = session.session_duration // 60 if session.session_duration else 0
                start_time = session.start_time.strftime("%Y-%m-%d %H:%M") if session.start_time else "Unknown"
                history_text += f"Session {session.id}: {start_time}\n"
                history_text += f"  Duration: {duration} minutes\n"
                history_text += f"  Blinks: {session.total_blinks}\n"
                history_text += f"  Avg Rate: {session.avg_blink_rate:.1f}/min\n"
                history_text += f"  Status: {'Active' if session.end_time is None else 'Completed'}\n\n"
            
            # Show database size
            db_size = self.db_manager.get_database_size()
            db_size_mb = db_size / (1024 * 1024)
            history_text += f"Database Size: {db_size_mb:.2f} MB"
            
            msg = QMessageBox(self)
            msg.setWindowTitle("Session History")
            msg.setText(history_text)
            msg.setStyleSheet("QLabel { color: #000000; }")
            msg.exec()
            
        except Exception as e:
            msg = QMessageBox(self)
            msg.setWindowTitle("Database Error")
            msg.setText(f"Error retrieving session history: {e}")
            msg.setStyleSheet("QLabel { color: #000000; }")
            msg.exec()
            self.logger.error(f"Error viewing session history: {e}")
    
    def open_settings(self):
        """Open settings dialog"""
        msg = QMessageBox(self)
        msg.setWindowTitle("Settings")
        msg.setText("Settings dialog would open\n(Feature not implemented in demo)")
        msg.setStyleSheet("QLabel { color: #000000; }")
        msg.exec()
        # TODO: Create settings dialog
    
    def quit_application(self):
        """Properly quit the application"""
        self.logger.info("Application quit requested")
        
        # End current session in database
        if self.db_manager:
            try:
                ended_session = self.db_manager.end_current_session()
                if ended_session:
                    self.logger.info(f"Session ended: {ended_session.total_blinks} blinks recorded")
            except Exception as e:
                self.logger.error(f"Error ending session: {e}")
        
        # Stop tracking if active
        if self.is_tracking:
            self.stop_tracking()
        
        # Stop system monitoring
        if self.system_monitor_thread and self.system_monitor_thread.isRunning():
            self.system_monitor_thread.stop_monitoring()
            self.system_monitor_thread.wait(5000)  # Wait up to 5 seconds for thread to finish
        
        if self.system_monitor:
            self.system_monitor.stop_monitoring()
        
        # Close database connection
        if self.db_manager:
            self.db_manager.close()
        
        # Hide tray icon
        if self.tray_icon:
            self.tray_icon.hide()
        
        # Close the application
        QApplication.quit()
    
    def logout(self):
        """Handle user logout"""
        reply = QMessageBox.question(self, "Logout", 
                                   "Are you sure you want to logout?\n\nThis will clear your authentication and return to the login screen.",
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            # Stop tracking if active
            if self.is_tracking:
                self.stop_tracking()
            
            # End current session in database
            if self.db_manager:
                try:
                    ended_session = self.db_manager.end_current_session()
                    if ended_session:
                        self.logger.info(f"Session ended before logout: {ended_session.total_blinks} blinks recorded")
                except Exception as e:
                    self.logger.error(f"Error ending session before logout: {e}")
            
            # Emit logout signal to trigger authentication flow restart
            self.logout_requested.emit()
    
    def center_window(self):
        """Center window on screen"""
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        screen_geometry = screen.availableGeometry()
        
        x = (screen_geometry.width() - self.width()) // 2
        y = (screen_geometry.height() - self.height()) // 2
        self.move(x, y)
    
    def apply_styles(self):
        """Apply custom styles from QSS file"""
        try:
            import os
            qss_file = os.path.join(os.path.dirname(__file__), 'styles', 'main.qss')
            with open(qss_file, 'r') as f:
                self.setStyleSheet(f.read())
        except Exception as e:
            # Fallback to basic styling if QSS file not found
            self.logger.warning(f"Could not load QSS file: {e}")
            self.setStyleSheet("""
                QMainWindow { background-color: #f8f9fa; }
                QPushButton { background-color: #007bff; color: white; border-radius: 6px; padding: 8px; }
                QPushButton:hover { background-color: #0056b3; }
            """)
    
    def closeEvent(self, event):
        """Handle window close event"""
        if self.tray_icon and self.tray_icon.isVisible():
            # Hide to tray instead of closing
            self.hide()
            self.tray_icon.showMessage("Wellness at Work", 
                                     "Application minimized to tray", 
                                     QSystemTrayIcon.MessageIcon.Information, 2000)
            event.ignore()
        else:
            # Actually close the application
            self.quit_application()
            event.accept()