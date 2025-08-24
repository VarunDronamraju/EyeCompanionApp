"""
API Backend Module
Contains the FastAPI backend components for Wellness at Work.
"""

__version__ = "1.0.0"
__author__ = "Wellness at Work Team"

# Import main components for easy access
try:
    from .main import app
    from .database import get_database
except ImportError:
    # Components may not be implemented yet
    pass
