"""
Authentication Window - Google OAuth Login Interface
Handles user authentication with real Google OAuth integration through AWS Cognito
"""

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                            QPushButton, QFrame, QSpacerItem, QSizePolicy,
                            QProgressBar, QMessageBox, QTextEdit)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QThread, pyqtSlot
from PyQt6.QtGui import QFont, QPixmap, QPainter, QColor, QBrush, QIcon
import logging
import time

from .services.auth_service import AuthService

class AuthWorkerThread(QThread):
    """Worker thread for authentication process"""
    auth_complete = pyqtSignal(dict)
    auth_error = pyqtSignal(str)
    status_update = pyqtSignal(str)
    
    def __init__(self, auth_service):
        super().__init__()
        self.auth_service = auth_service
    
    def run(self):
        """Run authentication process"""
        try:
            self.status_update.emit("Starting Google OAuth...")
            
            # Start Google OAuth authentication
            success = self.auth_service.start_google_auth()
            
            if success:
                user_data = self.auth_service.get_user_profile()
                self.auth_complete.emit(user_data)
            else:
                self.auth_error.emit("Authentication failed")
                
        except Exception as e:
            self.auth_error.emit(str(e))

class AuthWindow(QWidget):
    """Authentication window with Google OAuth integration"""
    
    authentication_successful = pyqtSignal(dict)
    authentication_failed = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.auth_service = AuthService()
        self.auth_thread = None
        self.logger = logging.getLogger(__name__)
        
        self.setup_ui()
        self.apply_styles()
        
        # Check if user is already authenticated
        self.check_existing_auth()
    
    def setup_ui(self):
        """Setup the authentication UI"""
        self.setWindowTitle("Wellness at Work - Login")
        self.setFixedSize(450, 650)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint)
        
        # Main layout
        layout = QVBoxLayout()
        layout.setSpacing(25)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Logo/Header section
        self.create_header(layout)
        
        # Spacer
        layout.addItem(QSpacerItem(20, 30, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))
        
        # Login form section
        self.create_login_section(layout)
        
        # Status section
        self.create_status_section(layout)
        
        # Footer section
        layout.addItem(QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))
        self.create_footer(layout)
        
        self.setLayout(layout)
        
        # Center window on screen
        self.center_window()
    
    def create_header(self, layout):
        """Create header with logo and title"""
        header_frame = QFrame()
        header_layout = QVBoxLayout()
        header_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.setSpacing(15)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        # App logo (placeholder)
        logo_label = QLabel()
        logo_pixmap = self.create_logo_pixmap()
        logo_label.setPixmap(logo_pixmap)
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_label.setStyleSheet("margin-bottom: 10px;")
        
        # App title
        title_label = QLabel("Wellness at Work")
        title_font = QFont("Segoe UI", 32, QFont.Weight.Bold)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("color: #000000; margin: 10px 0; background-color: transparent; border: none;")
        title_label.setWordWrap(True)
        
        # Subtitle
        subtitle_label = QLabel("Eye Tracking & Wellness Monitoring")
        subtitle_font = QFont("Segoe UI", 16)
        subtitle_label.setFont(subtitle_font)
        subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle_label.setStyleSheet("color: #000000; margin-bottom: 20px; font-weight: 400; background-color: transparent; border: none;")
        subtitle_label.setWordWrap(True)
        
        header_layout.addWidget(logo_label)
        header_layout.addWidget(title_label)
        header_layout.addWidget(subtitle_label)
        
        header_frame.setLayout(header_layout)
        layout.addWidget(header_frame)
    
    def create_login_section(self, layout):
        """Create login form section"""
        login_frame = QFrame()
        login_frame.setObjectName("loginFrame")
        login_layout = QVBoxLayout()
        login_layout.setSpacing(20)
        login_layout.setContentsMargins(0, 0, 0, 0)
        login_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Security info text (above button)
        security_label = QLabel("Secure authentication powered by Google OAuth\nYour data is encrypted and protected")
        security_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        security_label.setWordWrap(True)
        security_label.setStyleSheet("""
            color: #6c757d;
            font-size: 13px;
            line-height: 1.4;
            margin-bottom: 25px;
            font-weight: 400;
            background-color: transparent;
            border: none;
        """)
        
        # Welcome message
        welcome_label = QLabel("Sign in to sync your wellness data\nacross all your devices")
        welcome_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        welcome_label.setWordWrap(True)
        welcome_label.setStyleSheet("""
            color: #000000;
            font-size: 16px;
            line-height: 1.5;
            margin-bottom: 20px;
            font-weight: 500;
            background-color: transparent;
            border: none;
        """)
        
        # Google login button
        self.google_btn = QPushButton("Continue with Google")
        self.google_btn.setObjectName("googleButton")
        self.google_btn.clicked.connect(self.start_google_auth)
        self.google_btn.setMinimumHeight(50)
        self.google_btn.setMinimumWidth(240)
        
        login_layout.addWidget(security_label)
        login_layout.addWidget(welcome_label)
        login_layout.addWidget(self.google_btn)
        
        login_frame.setLayout(login_layout)
        layout.addWidget(login_frame)
    
    def create_status_section(self, layout):
        """Create status display section"""
        status_frame = QFrame()
        status_frame.setObjectName("statusFrame")
        status_layout = QVBoxLayout()
        status_layout.setSpacing(15)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Progress bar (initially hidden)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate progress
        self.progress_bar.hide()
        self.progress_bar.setMinimumHeight(8)
        self.progress_bar.setMaximumWidth(300)
        
        # Status label
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #000000; font-size: 14px; margin: 10px 0; font-weight: 500;")
        self.status_label.hide()
        
        # Status text area for detailed information
        self.status_text = QTextEdit()
        self.status_text.setMaximumHeight(120)
        self.status_text.setMaximumWidth(350)
        self.status_text.setStyleSheet("""
            QTextEdit {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 8px;
                padding: 12px;
                font-size: 12px;
                color: #000000;
                font-weight: 500;
            }
        """)
        self.status_text.hide()
        
        status_layout.addWidget(self.progress_bar)
        status_layout.addWidget(self.status_label)
        status_layout.addWidget(self.status_text)
        
        status_frame.setLayout(status_layout)
        layout.addWidget(status_frame)
    
    def create_footer(self, layout):
        """Create footer section"""
        footer_label = QLabel("By signing in, you agree to our Terms of Service\nand Privacy Policy")
        footer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer_label.setWordWrap(True)
        footer_label.setStyleSheet("""
            color: #000000;
            font-size: 12px;
            line-height: 1.5;
            margin-top: 15px;
            font-weight: 400;
            background-color: transparent;
            border: none;
        """)
        layout.addWidget(footer_label)
    
    def create_logo_pixmap(self):
        """Create a placeholder logo pixmap"""
        pixmap = QPixmap(80, 80)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw circular background
        painter.setBrush(QBrush(QColor("#495057")))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(0, 0, 80, 80)
        
        # Draw eye icon (simple representation)
        painter.setBrush(QBrush(QColor("white")))
        painter.drawEllipse(20, 30, 40, 20)
        
        painter.setBrush(QBrush(QColor("#495057")))
        painter.drawEllipse(35, 35, 10, 10)
        
        painter.end()
        return pixmap
    
    def check_existing_auth(self):
        """Check if user is already authenticated"""
        try:
            if self.auth_service.is_authenticated():
                user_data = self.auth_service.get_user_profile()
                if user_data:
                    self.logger.info("User already authenticated")
                    self.show_already_authenticated(user_data)
                else:
                    self.logger.warning("Authentication status inconsistent")
        except Exception as e:
            self.logger.error(f"Error checking existing auth: {e}")
    
    def show_already_authenticated(self, user_data):
        """Show already authenticated state"""
        self.status_label.setText(f"Welcome back, {user_data.get('name', 'User')}!")
        self.status_label.setStyleSheet("color: #28a745; font-size: 14px; font-weight: bold;")
        self.status_label.show()
        
        self.google_btn.setText("Continue as " + user_data.get('given_name', 'User'))
        self.google_btn.setStyleSheet("""
            QPushButton#googleButton {
                background-color: #28a745;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 15px 25px;
                font-size: 15px;
                font-weight: 600;
                min-height: 50px;
                margin: 5px 0;
            }
            QPushButton#googleButton:hover {
                background-color: #218838;
            }
        """)
    
    def start_google_auth(self):
        """Start Google OAuth authentication process"""
        try:
            # UI feedback
            self.google_btn.setText("Authenticating...")
            self.google_btn.setEnabled(False)
            
            self.progress_bar.show()
            self.status_label.setText("Connecting to Google...")
            self.status_label.setStyleSheet("color: #17a2b8; font-size: 13px;")
            self.status_label.show()
            
            # Start authentication in separate thread
            self.auth_thread = AuthWorkerThread(self.auth_service)
            self.auth_thread.auth_complete.connect(self.on_auth_success)
            self.auth_thread.auth_error.connect(self.on_auth_error)
            self.auth_thread.status_update.connect(self.update_status)
            self.auth_thread.start()
            
        except Exception as e:
            self.logger.error(f"Error starting authentication: {e}")
            self.on_auth_error(str(e))
    
    def skip_authentication(self):
        """Skip authentication - return to auth window"""
        # This method is kept for compatibility but doesn't create demo user
        self.authentication_failed.emit("Authentication required")
    
    @pyqtSlot(dict)
    def on_auth_success(self, user_data):
        """Handle successful authentication"""
        try:
            self.progress_bar.hide()
            self.status_label.setText("Authentication successful!")
            self.status_label.setStyleSheet("color: #28a745; font-size: 14px; font-weight: bold;")
            
            # Show user info
            self.status_text.setPlainText(f"""
✅ Authentication Successful!

User: {user_data.get('name', 'Unknown')}
Email: {user_data.get('email', 'Unknown')}
Verified: {'Yes' if user_data.get('verified_email', False) else 'No'}

Your data will now sync securely across devices.
            """)
            self.status_text.show()
            
            # Brief delay before closing
            QTimer.singleShot(2000, lambda: self.authentication_successful.emit(user_data))
            
        except Exception as e:
            self.logger.error(f"Error handling auth success: {e}")
            self.on_auth_error(str(e))
    
    @pyqtSlot(str)
    def on_auth_error(self, error_message):
        """Handle authentication error"""
        try:
            self.progress_bar.hide()
            self.status_label.setText("Authentication failed")
            self.status_label.setStyleSheet("color: #dc3545; font-size: 13px;")
            
            # Show detailed error
            self.status_text.setPlainText(f"""
❌ Authentication Failed

Error: {error_message}

Please check your internet connection and try again.
If the problem persists, contact support.
            """)
            self.status_text.show()
            
            # Reset buttons
            self.google_btn.setText("Continue with Google")
            self.google_btn.setEnabled(True)
            
            # Emit failure signal
            self.authentication_failed.emit(error_message)
            
        except Exception as e:
            self.logger.error(f"Error handling auth error: {e}")
    
    @pyqtSlot(str)
    def update_status(self, status_message):
        """Update status message during authentication"""
        self.status_label.setText(status_message)
        self.logger.info(f"Auth status: {status_message}")
    
    def center_window(self):
        """Center the window on the screen"""
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        screen_geometry = screen.availableGeometry()
        
        x = (screen_geometry.width() - self.width()) // 2
        y = (screen_geometry.height() - self.height()) // 2
        self.move(x, y)
    
    def apply_styles(self):
        """Apply custom styles to the window"""
        self.setStyleSheet("""
            QWidget {
                background-color: #ffffff;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            
            QFrame {
                background-color: transparent;
                border: none;
                border-radius: 0px;
                margin: 0px;
                padding: 0px;
            }
            
            QLabel {
                background-color: transparent;
                border: none;
                padding: 0px;
                margin: 0px;
            }
            
            QPushButton#googleButton {
                background-color: #4285f4;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 15px 25px;
                font-size: 15px;
                font-weight: 600;
                min-height: 50px;
                margin: 10px 0;
                box-shadow: 0 2px 4px rgba(66, 133, 244, 0.3);
            }
            
            QPushButton#googleButton:hover {
                background-color: #3367d6;
                box-shadow: 0 4px 8px rgba(66, 133, 244, 0.4);
            }
            
            QPushButton#googleButton:pressed {
                background-color: #2d5aa0;
            }
            
            QPushButton#googleButton:disabled {
                background-color: #adb5bd;
                color: #6c757d;
            }
            

            
            QProgressBar {
                border: none;
                border-radius: 4px;
                background-color: #e9ecef;
                height: 8px;
                margin: 10px 0;
            }
            
            QProgressBar::chunk {
                background-color: #495057;
                border-radius: 4px;
            }
        """)
    
    def closeEvent(self, event):
        """Handle window close event"""
        if self.auth_thread and self.auth_thread.isRunning():
            self.auth_thread.terminate()
            self.auth_thread.wait()
        event.accept()