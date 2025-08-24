#!/usr/bin/env python3
"""
Wellness at Work - Main Entry Point
Launches the desktop eye tracking application.
"""

import sys
import os
import logging
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt
    from config import config
    from desktop.main_window import MainWindow
except ImportError as e:
    print(f"Error importing required modules: {e}")
    print("Please ensure all dependencies are installed: pip install -r requirements.txt")
    sys.exit(1)

def setup_logging():
    """Configure logging for the application."""
    logging.basicConfig(
        level=logging.INFO if not config.DEBUG else logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('wellness_at_work.log'),
            logging.StreamHandler(sys.stdout)
        ]
    )

class ApplicationManager:
    """Manages the application lifecycle and authentication flow"""
    
    def __init__(self):
        self.app = None
        self.auth_service = None
        self.current_window = None
        self.logger = logging.getLogger(__name__)
    
    def start(self):
        """Start the application"""
        # Setup logging
        setup_logging()
        
        try:
            self.logger.info(f"Starting {config.APP_NAME} v{config.APP_VERSION}")
            
            # Create Qt application
            self.app = QApplication(sys.argv)
            self.app.setApplicationName(config.APP_NAME)
            self.app.setApplicationVersion(config.APP_VERSION)
            self.app.setQuitOnLastWindowClosed(True)
            
            # Set application style
            self.app.setStyle('Fusion')
            
            # Import authentication components
            from desktop.auth_window import AuthWindow
            from desktop.services.auth_service import AuthService
            
            # Initialize authentication service
            self.auth_service = AuthService()
            
            # Start authentication flow
            self.show_auth_or_main()
            
            # Start the event loop
            sys.exit(self.app.exec())
            
        except Exception as e:
            self.logger.error(f"Failed to start application: {e}")
            print(f"Error: {e}")
            sys.exit(1)
    
    def show_auth_or_main(self):
        """Show authentication window or main application based on auth status"""
        # Check if user is already authenticated
        if self.auth_service.is_authenticated():
            self.logger.info("User already authenticated, launching main application")
            user_data = self.auth_service.get_user_profile()
            if not user_data:
                self.logger.error("Authentication status inconsistent - no user profile found")
                self.show_auth_window()
                return
            self.show_main_window(user_data)
        else:
            self.logger.info("User not authenticated, showing login window")
            self.show_auth_window()
    
    def show_auth_window(self):
        """Show authentication window"""
        from desktop.auth_window import AuthWindow
        
        # Close current window if any
        if self.current_window:
            self.current_window.close()
            self.current_window = None
        
        # Show authentication window
        auth_window = AuthWindow()
        
        # Handle authentication results
        def on_auth_success(user_data):
            self.logger.info(f"Authentication successful for user: {user_data.get('email', 'Unknown')}")
            auth_window.close()
            self.show_main_window(user_data)
        
        def on_auth_failed(error):
            self.logger.error(f"Authentication failed: {error}")
            # Show error and allow retry
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(auth_window, "Authentication Failed", 
                               f"Failed to authenticate: {error}\n\nPlease try again.")
        
        def on_skip_auth():
            self.logger.info("User chose to skip authentication")
            auth_window.close()
            # Return to auth window - no demo mode
            self.show_auth_window()
        
        # Connect signals
        auth_window.authentication_successful.connect(on_auth_success)
        auth_window.authentication_failed.connect(on_auth_failed)
        
        # Show auth window
        auth_window.show()
        self.current_window = auth_window
    
    def show_main_window(self, user_data):
        """Show main application window"""
        from desktop.main_window import MainWindow
        
        # Close current window if any
        if self.current_window:
            self.current_window.close()
            self.current_window = None
        
        # Launch main application with user data
        main_window = MainWindow(user_data)
        main_window.show()
        
        # Connect logout to restart auth flow
        def on_logout():
            self.auth_service.logout()
            self.logger.info("User logged out")
            # Restart authentication flow without restarting the app
            self.show_auth_or_main()
        
        main_window.logout_requested.connect(on_logout)
        self.current_window = main_window
        
        self.logger.info("Application started successfully")

def main():
    """Main application entry point."""
    app_manager = ApplicationManager()
    app_manager.start()

if __name__ == "__main__":
    main()
