"""
Session Manager - Dual Session Management System
Manages local auto-start sessions and cloud manual sessions with clear user controls
"""

import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass
from enum import Enum

from ..database.sqlite_manager import SQLiteManager
from ..database.models import LocalSession

logger = logging.getLogger(__name__)

class SessionType(Enum):
    """Session types for dual management"""
    LOCAL = "local"
    CLOUD = "cloud"

class SessionState(Enum):
    """Session states for clear user feedback"""
    INACTIVE = "inactive"
    ACTIVE = "active"
    PAUSED = "paused"
    ENDED = "ended"

@dataclass
class SessionInfo:
    """Session information for UI display"""
    session_id: str
    session_type: SessionType
    state: SessionState
    start_time: datetime
    end_time: Optional[datetime] = None
    total_blinks: int = 0
    blink_rate: float = 0.0
    duration_seconds: int = 0
    is_synced: bool = False

class SessionManager:
    """
    Dual session manager with local auto-start and cloud manual control.
    Provides clear session state management and immediate user feedback.
    """
    
    def __init__(self, db_manager: SQLiteManager, user_data: Optional[Dict[str, Any]] = None):
        """
        Initialize session manager
        
        Args:
            db_manager: SQLite database manager for local sessions
            user_data: User authentication data for cloud sessions
        """
        self.db_manager = db_manager
        self.user_data = user_data or {}
        self.user_id = user_data.get('id') if user_data else None
        
        # Session state management
        self._local_session: Optional[SessionInfo] = None
        self._cloud_session: Optional[SessionInfo] = None
        self._session_lock = threading.RLock()
        
        # Callbacks for UI updates
        self._state_change_callbacks: list[Callable] = []
        self._session_update_callbacks: list[Callable] = []
        
        # Auto-start local session on initialization
        self._auto_start_local_session()
        
        logger.info("Session manager initialized")
        if self.user_id:
            logger.info(f"User authenticated: {self.user_data.get('email', 'Unknown')}")
        else:
            logger.info("No user authentication - cloud features disabled")
    
    def _auto_start_local_session(self):
        """Automatically start local session for privacy-first tracking"""
        try:
            with self._session_lock:
                # Create or get existing local session
                session_id = self.db_manager.auto_create_session()
                
                self._local_session = SessionInfo(
                    session_id=str(session_id),
                    session_type=SessionType.LOCAL,
                    state=SessionState.ACTIVE,
                    start_time=datetime.now(),
                    is_synced=False
                )
                
                logger.info(f"Local session auto-started: {session_id}")
                self._notify_state_change()
                
        except Exception as e:
            logger.error(f"Error auto-starting local session: {e}")
    
    def start_cloud_session(self) -> bool:
        """
        Start cloud session manually (requires authentication)
        
        Returns:
            bool: True if cloud session started successfully
        """
        if not self.user_id:
            logger.warning("Cannot start cloud session - authentication required")
            return False
        
        try:
            with self._session_lock:
                if self._cloud_session and self._cloud_session.state == SessionState.ACTIVE:
                    logger.info("Cloud session already active")
                    return True
                
                # Create cloud session (placeholder for API integration)
                cloud_session_id = f"cloud_{int(time.time())}"
                
                self._cloud_session = SessionInfo(
                    session_id=cloud_session_id,
                    session_type=SessionType.CLOUD,
                    state=SessionState.ACTIVE,
                    start_time=datetime.now(),
                    is_synced=True
                )
                
                logger.info(f"Cloud session started: {cloud_session_id}")
                self._notify_state_change()
                return True
                
        except Exception as e:
            logger.error(f"Error starting cloud session: {e}")
            return False
    
    def pause_session(self, session_type: SessionType) -> bool:
        """
        Pause specified session type
        
        Args:
            session_type: Type of session to pause
            
        Returns:
            bool: True if session paused successfully
        """
        try:
            with self._session_lock:
                if session_type == SessionType.LOCAL:
                    if self._local_session and self._local_session.state == SessionState.ACTIVE:
                        self._local_session.state = SessionState.PAUSED
                        logger.info("Local session paused")
                        self._notify_state_change()
                        return True
                elif session_type == SessionType.CLOUD:
                    if self._cloud_session and self._cloud_session.state == SessionState.ACTIVE:
                        self._cloud_session.state = SessionState.PAUSED
                        logger.info("Cloud session paused")
                        self._notify_state_change()
                        return True
                
                return False
                
        except Exception as e:
            logger.error(f"Error pausing {session_type.value} session: {e}")
            return False
    
    def resume_session(self, session_type: SessionType) -> bool:
        """
        Resume specified session type
        
        Args:
            session_type: Type of session to resume
            
        Returns:
            bool: True if session resumed successfully
        """
        try:
            with self._session_lock:
                if session_type == SessionType.LOCAL:
                    if self._local_session and self._local_session.state == SessionState.PAUSED:
                        self._local_session.state = SessionState.ACTIVE
                        logger.info("Local session resumed")
                        self._notify_state_change()
                        return True
                elif session_type == SessionType.CLOUD:
                    if self._cloud_session and self._cloud_session.state == SessionState.PAUSED:
                        self._cloud_session.state = SessionState.ACTIVE
                        logger.info("Cloud session resumed")
                        self._notify_state_change()
                        return True
                
                return False
                
        except Exception as e:
            logger.error(f"Error resuming {session_type.value} session: {e}")
            return False
    
    def stop_session(self, session_type: SessionType) -> bool:
        """
        Stop specified session type
        
        Args:
            session_type: Type of session to stop
            
        Returns:
            bool: True if session stopped successfully
        """
        try:
            with self._session_lock:
                if session_type == SessionType.LOCAL:
                    if self._local_session:
                        self._local_session.state = SessionState.ENDED
                        self._local_session.end_time = datetime.now()
                        self._local_session.duration_seconds = int(
                            (self._local_session.end_time - self._local_session.start_time).total_seconds()
                        )
                        
                        # End session in database
                        ended_session = self.db_manager.end_current_session()
                        if ended_session:
                            self._local_session.total_blinks = ended_session.total_blinks
                            self._local_session.blink_rate = ended_session.avg_blink_rate
                        
                        logger.info(f"Local session ended: {self._local_session.total_blinks} blinks")
                        self._notify_state_change()
                        return True
                        
                elif session_type == SessionType.CLOUD:
                    if self._cloud_session:
                        self._cloud_session.state = SessionState.ENDED
                        self._cloud_session.end_time = datetime.now()
                        self._cloud_session.duration_seconds = int(
                            (self._cloud_session.end_time - self._cloud_session.start_time).total_seconds()
                        )
                        
                        logger.info("Cloud session ended")
                        self._notify_state_change()
                        return True
                
                return False
                
        except Exception as e:
            logger.error(f"Error stopping {session_type.value} session: {e}")
            return False
    
    def reset_session(self, session_type: SessionType) -> bool:
        """
        Reset specified session type (creates new session)
        
        Args:
            session_type: Type of session to reset
            
        Returns:
            bool: True if session reset successfully
        """
        try:
            with self._session_lock:
                if session_type == SessionType.LOCAL:
                    # Stop current local session
                    if self._local_session:
                        self.stop_session(SessionType.LOCAL)
                    
                    # Auto-start new local session
                    self._auto_start_local_session()
                    return True
                    
                elif session_type == SessionType.CLOUD:
                    # Stop current cloud session
                    if self._cloud_session:
                        self.stop_session(SessionType.CLOUD)
                    
                    # Start new cloud session
                    return self.start_cloud_session()
                
                return False
                
        except Exception as e:
            logger.error(f"Error resetting {session_type.value} session: {e}")
            return False
    
    def get_session_info(self, session_type: SessionType) -> Optional[SessionInfo]:
        """
        Get current session information
        
        Args:
            session_type: Type of session to get info for
            
        Returns:
            SessionInfo: Current session information or None
        """
        with self._session_lock:
            if session_type == SessionType.LOCAL:
                return self._local_session
            elif session_type == SessionType.CLOUD:
                return self._cloud_session
            return None
    
    def get_all_sessions(self) -> Dict[SessionType, Optional[SessionInfo]]:
        """
        Get information for all session types
        
        Returns:
            Dict mapping session types to their current info
        """
        with self._session_lock:
            return {
                SessionType.LOCAL: self._local_session,
                SessionType.CLOUD: self._cloud_session
            }
    
    def update_session_stats(self, blink_count: int, blink_rate: float):
        """
        Update session statistics (called from eye tracker)
        
        Args:
            blink_count: Current total blink count
            blink_rate: Current blink rate
        """
        try:
            with self._session_lock:
                # Update local session stats
                if self._local_session and self._local_session.state == SessionState.ACTIVE:
                    self._local_session.total_blinks = blink_count
                    self._local_session.blink_rate = blink_rate
                    self._local_session.duration_seconds = int(
                        (datetime.now() - self._local_session.start_time).total_seconds()
                    )
                
                # Update cloud session stats
                if self._cloud_session and self._cloud_session.state == SessionState.ACTIVE:
                    self._cloud_session.total_blinks = blink_count
                    self._cloud_session.blink_rate = blink_rate
                    self._cloud_session.duration_seconds = int(
                        (datetime.now() - self._cloud_session.start_time).total_seconds()
                    )
                
                # Notify UI of updates
                self._notify_session_update()
                
        except Exception as e:
            logger.error(f"Error updating session stats: {e}")
    
    def get_session_summary(self) -> Dict[str, Any]:
        """
        Get comprehensive session summary for UI display
        
        Returns:
            Dict containing session summary information
        """
        with self._session_lock:
            summary = {
                'local_session': {
                    'active': self._local_session is not None and self._local_session.state == SessionState.ACTIVE,
                    'paused': self._local_session is not None and self._local_session.state == SessionState.PAUSED,
                    'ended': self._local_session is not None and self._local_session.state == SessionState.ENDED,
                    'total_blinks': self._local_session.total_blinks if self._local_session else 0,
                    'blink_rate': self._local_session.blink_rate if self._local_session else 0.0,
                    'duration': self._local_session.duration_seconds if self._local_session else 0,
                    'start_time': self._local_session.start_time if self._local_session else None
                },
                'cloud_session': {
                    'available': self.user_id is not None,
                    'active': self._cloud_session is not None and self._cloud_session.state == SessionState.ACTIVE,
                    'paused': self._cloud_session is not None and self._cloud_session.state == SessionState.PAUSED,
                    'ended': self._cloud_session is not None and self._cloud_session.state == SessionState.ENDED,
                    'total_blinks': self._cloud_session.total_blinks if self._cloud_session else 0,
                    'blink_rate': self._cloud_session.blink_rate if self._cloud_session else 0.0,
                    'duration': self._cloud_session.duration_seconds if self._cloud_session else 0,
                    'start_time': self._cloud_session.start_time if self._cloud_session else None
                },
                'user_authenticated': self.user_id is not None,
                'user_email': self.user_data.get('email', 'Not authenticated')
            }
            
            return summary
    
    def validate_session_integrity(self) -> Dict[str, Any]:
        """
        Validate session data integrity
        
        Returns:
            Dict containing validation results
        """
        validation_results = {
            'local_session_valid': True,
            'cloud_session_valid': True,
            'database_connection': True,
            'errors': []
        }
        
        try:
            with self._session_lock:
                # Validate local session
                if self._local_session:
                    if self._local_session.start_time > datetime.now():
                        validation_results['local_session_valid'] = False
                        validation_results['errors'].append("Local session start time is in the future")
                    
                    if self._local_session.total_blinks < 0:
                        validation_results['local_session_valid'] = False
                        validation_results['errors'].append("Local session has negative blink count")
                
                # Validate cloud session
                if self._cloud_session:
                    if self._cloud_session.start_time > datetime.now():
                        validation_results['cloud_session_valid'] = False
                        validation_results['errors'].append("Cloud session start time is in the future")
                    
                    if self._cloud_session.total_blinks < 0:
                        validation_results['cloud_session_valid'] = False
                        validation_results['errors'].append("Cloud session has negative blink count")
                
                # Validate database connection
                try:
                    current_session = self.db_manager.get_current_session()
                    if not current_session:
                        validation_results['database_connection'] = False
                        validation_results['errors'].append("No active database session found")
                except Exception as e:
                    validation_results['database_connection'] = False
                    validation_results['errors'].append(f"Database connection error: {e}")
                
        except Exception as e:
            validation_results['errors'].append(f"Validation error: {e}")
        
        return validation_results
    
    def export_session_data(self, session_type: SessionType) -> Optional[Dict[str, Any]]:
        """
        Export session data for external use
        
        Args:
            session_type: Type of session to export
            
        Returns:
            Dict containing exported session data or None
        """
        try:
            with self._session_lock:
                if session_type == SessionType.LOCAL:
                    if not self._local_session:
                        return None
                    
                    # Get detailed session data from database
                    session_stats = self.db_manager.get_session_stats(int(self._local_session.session_id))
                    
                    export_data = {
                        'session_type': 'local',
                        'session_id': self._local_session.session_id,
                        'start_time': self._local_session.start_time.isoformat(),
                        'end_time': self._local_session.end_time.isoformat() if self._local_session.end_time else None,
                        'total_blinks': self._local_session.total_blinks,
                        'avg_blink_rate': self._local_session.blink_rate,
                        'duration_seconds': self._local_session.duration_seconds,
                        'is_synced': self._local_session.is_synced,
                        'user_id': self.user_id,
                        'user_email': self.user_data.get('email'),
                        'detailed_stats': session_stats,
                        'export_timestamp': datetime.now().isoformat()
                    }
                    
                    return export_data
                    
                elif session_type == SessionType.CLOUD:
                    if not self._cloud_session:
                        return None
                    
                    export_data = {
                        'session_type': 'cloud',
                        'session_id': self._cloud_session.session_id,
                        'start_time': self._cloud_session.start_time.isoformat(),
                        'end_time': self._cloud_session.end_time.isoformat() if self._cloud_session.end_time else None,
                        'total_blinks': self._cloud_session.total_blinks,
                        'avg_blink_rate': self._cloud_session.blink_rate,
                        'duration_seconds': self._cloud_session.duration_seconds,
                        'is_synced': self._cloud_session.is_synced,
                        'user_id': self.user_id,
                        'user_email': self.user_data.get('email'),
                        'export_timestamp': datetime.now().isoformat()
                    }
                    
                    return export_data
                
                return None
                
        except Exception as e:
            logger.error(f"Error exporting {session_type.value} session data: {e}")
            return None
    
    def register_state_change_callback(self, callback: Callable):
        """Register callback for session state changes"""
        self._state_change_callbacks.append(callback)
    
    def register_session_update_callback(self, callback: Callable):
        """Register callback for session data updates"""
        self._session_update_callbacks.append(callback)
    
    def _notify_state_change(self):
        """Notify registered callbacks of state changes"""
        for callback in self._state_change_callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"Error in state change callback: {e}")
    
    def _notify_session_update(self):
        """Notify registered callbacks of session updates"""
        for callback in self._session_update_callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"Error in session update callback: {e}")
    
    def cleanup(self):
        """Clean up session manager resources"""
        try:
            with self._session_lock:
                # End any active sessions
                if self._local_session and self._local_session.state == SessionState.ACTIVE:
                    self.stop_session(SessionType.LOCAL)
                
                if self._cloud_session and self._cloud_session.state == SessionState.ACTIVE:
                    self.stop_session(SessionType.CLOUD)
                
                # Clear callbacks
                self._state_change_callbacks.clear()
                self._session_update_callbacks.clear()
                
                logger.info("Session manager cleaned up")
                
        except Exception as e:
            logger.error(f"Error during session manager cleanup: {e}")
    
    def __del__(self):
        """Cleanup on destruction"""
        self.cleanup()
