"""
Desktop Services Module

This module contains all service components for the desktop application:
- System monitoring and performance tracking
- Authentication and user management
- Data synchronization with cloud services
- Notification and system tray management
"""

from .system_monitor import SystemMonitor

# Import other services when they are implemented
try:
    from .auth_service import AuthService
except ImportError:
    AuthService = None

try:
    from .sync_service import SyncService
except ImportError:
    SyncService = None

try:
    from .notification_service import NotificationService
except ImportError:
    NotificationService = None

__all__ = [
    'SystemMonitor',
    'AuthService', 
    'SyncService',
    'NotificationService'
]
