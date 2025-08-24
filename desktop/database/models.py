"""
Database Models for Local SQLite Storage
Defines data structures for sessions, blink data, and sync operations
"""

import sqlite3
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict
import logging

logger = logging.getLogger(__name__)

@dataclass
class LocalSession:
    """Local session model for tracking eye blink sessions"""
    id: Optional[int] = None
    user_id: Optional[str] = None  # Google user ID from OAuth
    user_email: Optional[str] = None  # User's email for display
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    total_blinks: int = 0
    max_blink_rate: float = 0.0
    avg_blink_rate: float = 0.0
    session_duration: int = 0  # seconds
    is_synced: bool = False
    cloud_session_id: Optional[str] = None
    created_at: Optional[datetime] = None
    
    def __post_init__(self):
        """Initialize default values"""
        if self.start_time is None:
            self.start_time = datetime.now()
        if self.created_at is None:
            self.created_at = datetime.now()
    
    def calculate_duration(self) -> int:
        """Calculate session duration in seconds"""
        if self.start_time is None:
            return 0
        
        # Handle string timestamps
        start_time = self.start_time
        end_time = self.end_time or datetime.now()
        
        # Convert string timestamps to datetime objects
        if isinstance(start_time, str):
            try:
                start_time = datetime.fromisoformat(start_time)
            except (ValueError, TypeError):
                return 0
        
        if isinstance(end_time, str):
            try:
                end_time = datetime.fromisoformat(end_time)
            except (ValueError, TypeError):
                end_time = datetime.now()
        
        duration = (end_time - start_time).total_seconds()
        self.session_duration = int(duration)
        return self.session_duration
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database operations"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'user_email': self.user_email,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'total_blinks': self.total_blinks,
            'max_blink_rate': self.max_blink_rate,
            'avg_blink_rate': self.avg_blink_rate,
            'session_duration': self.session_duration,
            'is_synced': self.is_synced,
            'cloud_session_id': self.cloud_session_id,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LocalSession':
        """Create instance from dictionary"""
        # Convert string timestamps back to datetime objects
        if data.get('start_time') and isinstance(data['start_time'], str):
            try:
                data['start_time'] = datetime.fromisoformat(data['start_time'])
            except (ValueError, TypeError):
                data['start_time'] = None
        
        if data.get('end_time') and isinstance(data['end_time'], str):
            try:
                data['end_time'] = datetime.fromisoformat(data['end_time'])
            except (ValueError, TypeError):
                data['end_time'] = None
        
        if data.get('created_at') and isinstance(data['created_at'], str):
            try:
                data['created_at'] = datetime.fromisoformat(data['created_at'])
            except (ValueError, TypeError):
                data['created_at'] = None
        
        return cls(**data)

@dataclass
class BlinkData:
    """Blink data point model for real-time logging"""
    id: Optional[int] = None
    session_id: int = 0
    user_id: Optional[str] = None  # Google user ID from OAuth
    timestamp: Optional[datetime] = None
    blink_count: int = 0
    blink_rate: float = 0.0
    eye_aspect_ratio: Optional[float] = None
    is_synced: bool = False
    
    def __post_init__(self):
        """Initialize default values"""
        if self.timestamp is None:
            self.timestamp = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database operations"""
        return {
            'id': self.id,
            'session_id': self.session_id,
            'user_id': self.user_id,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'blink_count': self.blink_count,
            'blink_rate': self.blink_rate,
            'eye_aspect_ratio': self.eye_aspect_ratio,
            'is_synced': self.is_synced
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BlinkData':
        """Create instance from dictionary"""
        if data.get('timestamp') and isinstance(data['timestamp'], str):
            try:
                data['timestamp'] = datetime.fromisoformat(data['timestamp'])
            except (ValueError, TypeError):
                data['timestamp'] = None
        
        return cls(**data)

@dataclass
class PerformanceLog:
    """System performance log model"""
    id: Optional[int] = None
    session_id: int = 0
    user_id: Optional[str] = None  # Google user ID from OAuth
    timestamp: Optional[datetime] = None
    cpu_usage: Optional[float] = None
    memory_usage: Optional[float] = None
    battery_level: Optional[int] = None
    
    def __post_init__(self):
        """Initialize default values"""
        if self.timestamp is None:
            self.timestamp = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database operations"""
        return {
            'id': self.id,
            'session_id': self.session_id,
            'user_id': self.user_id,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'cpu_usage': self.cpu_usage,
            'memory_usage': self.memory_usage,
            'battery_level': self.battery_level
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PerformanceLog':
        """Create instance from dictionary"""
        if data.get('timestamp') and isinstance(data['timestamp'], str):
            try:
                data['timestamp'] = datetime.fromisoformat(data['timestamp'])
            except (ValueError, TypeError):
                data['timestamp'] = None
        
        return cls(**data)

@dataclass
class SyncQueue:
    """Sync queue item for offline capability"""
    id: Optional[int] = None
    user_id: Optional[str] = None  # Google user ID from OAuth
    table_name: str = ""
    record_id: int = 0
    action: str = ""  # 'INSERT', 'UPDATE', 'DELETE'
    data: Optional[str] = None  # JSON data
    created_at: Optional[datetime] = None
    synced_at: Optional[datetime] = None
    
    def __post_init__(self):
        """Initialize default values"""
        if self.created_at is None:
            self.created_at = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database operations"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'table_name': self.table_name,
            'record_id': self.record_id,
            'action': self.action,
            'data': self.data,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'synced_at': self.synced_at.isoformat() if self.synced_at else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SyncQueue':
        """Create instance from dictionary"""
        if data.get('created_at') and isinstance(data['created_at'], str):
            try:
                data['created_at'] = datetime.fromisoformat(data['created_at'])
            except (ValueError, TypeError):
                data['created_at'] = None
        
        if data.get('synced_at') and isinstance(data['synced_at'], str):
            try:
                data['synced_at'] = datetime.fromisoformat(data['synced_at'])
            except (ValueError, TypeError):
                data['synced_at'] = None
        
        return cls(**data)
