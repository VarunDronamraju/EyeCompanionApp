"""
Desktop Application Module
Contains the main desktop application components for Wellness at Work.
"""

__version__ = "1.0.0"
__author__ = "Wellness at Work Team"

# Import main components for easy access
try:
    from .main_window import MainWindow
    from .eye_tracker import EyeTracker
    from .auth_window import AuthWindow
except ImportError:
    # Components may not be implemented yet
    pass
