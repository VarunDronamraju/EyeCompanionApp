import uuid
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field, validator, EmailStr
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text, JSON, ForeignKey, UUID
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database import Base

# ============================================================================
# ENUMS
# ============================================================================

class SessionStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    ENDED = "ended"

class ExportStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class ExportFormat(str, Enum):
    CSV = "csv"
    JSON = "json"
    PDF = "pdf"

class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"

# ============================================================================
# SQLALCHEMY DATABASE MODELS
# ============================================================================

class User(Base):
    """User model for authentication and profile management."""
    __tablename__ = "users"
    
    id = Column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cognito_sub = Column(String(255), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), nullable=False)
    avatar_url = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_login = Column(DateTime(timezone=True), nullable=True)
    settings = Column(JSONB, default={})
    
    # Relationships
    sessions = relationship("CloudSession", back_populates="user", cascade="all, delete-orphan")
    export_requests = relationship("ExportRequest", back_populates="user", cascade="all, delete-orphan")

class CloudSession(Base):
    """Cloud session model for tracking user sessions."""
    __tablename__ = "cloud_sessions"
    
    id = Column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(PostgresUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    local_session_id = Column(Integer, nullable=True)  # Reference to local SQLite session
    start_time = Column(DateTime(timezone=True), nullable=False, default=func.now())
    end_time = Column(DateTime(timezone=True), nullable=True)
    total_blinks = Column(Integer, default=0)
    avg_blink_rate = Column(Float, default=0.0)
    max_blink_rate = Column(Float, default=0.0)
    session_duration = Column(Integer, default=0)  # seconds
    device_info = Column(JSONB, nullable=True)
    system_metrics = Column(JSONB, nullable=True)
    health_score = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    user = relationship("User", back_populates="sessions")
    session_data = relationship("SessionData", back_populates="session", cascade="all, delete-orphan")

class SessionData(Base):
    """Detailed session data model for storing blink and performance metrics."""
    __tablename__ = "session_data"
    
    id = Column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(PostgresUUID(as_uuid=True), ForeignKey("cloud_sessions.id", ondelete="CASCADE"), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=func.now())
    blink_count = Column(Integer, nullable=False)
    blink_rate = Column(Float, nullable=False)
    eye_aspect_ratio = Column(Float, nullable=True)
    cpu_usage = Column(Float, nullable=True)
    memory_usage = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    session = relationship("CloudSession", back_populates="session_data")

class ExportRequest(Base):
    """Export request model for data export functionality."""
    __tablename__ = "export_requests"
    
    id = Column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(PostgresUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    export_type = Column(String(20), nullable=False)  # csv, json, pdf
    date_range_start = Column(DateTime(timezone=True), nullable=True)
    date_range_end = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), default="pending")  # pending, processing, completed, failed
    file_url = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="export_requests")

# ============================================================================
# PYDANTIC REQUEST MODELS
# ============================================================================

class GoogleAuthRequest(BaseModel):
    """Request model for Google OAuth authentication."""
    code: str = Field(..., description="Google OAuth authorization code")
    state: str = Field(..., description="OAuth state parameter for security")

class DeviceInfo(BaseModel):
    """Device information model."""
    os: str = Field(..., description="Operating system")
    resolution: str = Field(..., description="Screen resolution")
    app_version: Optional[str] = Field(None, description="Application version")
    device_id: Optional[str] = Field(None, description="Unique device identifier")

class SessionStartRequest(BaseModel):
    """Request model for starting a cloud session."""
    user_id: str = Field(..., description="User UUID")
    device_info: DeviceInfo = Field(..., description="Device information")
    
    @validator('user_id')
    def validate_user_id(cls, v):
        try:
            uuid.UUID(v)
            return v
        except ValueError:
            raise ValueError('Invalid user_id format')

class SessionEndRequest(BaseModel):
    """Request model for ending a cloud session."""
    session_id: str = Field(..., description="Session UUID")
    total_blinks: int = Field(..., ge=0, description="Total blinks in session")
    avg_blink_rate: float = Field(..., ge=0, description="Average blink rate")
    max_blink_rate: float = Field(..., ge=0, description="Maximum blink rate")
    session_duration: int = Field(..., ge=0, description="Session duration in seconds")
    health_score: Optional[int] = Field(None, ge=0, le=100, description="Health score (0-100)")
    
    @validator('session_id')
    def validate_session_id(cls, v):
        try:
            uuid.UUID(v)
            return v
        except ValueError:
            raise ValueError('Invalid session_id format')

class BlinkDataPoint(BaseModel):
    """Model for individual blink data points."""
    timestamp: datetime = Field(..., description="Timestamp of the data point")
    blink_count: int = Field(..., ge=0, description="Cumulative blink count")
    blink_rate: float = Field(..., ge=0, description="Current blink rate")
    eye_aspect_ratio: Optional[float] = Field(None, description="Eye aspect ratio")
    cpu_usage: Optional[float] = Field(None, ge=0, le=100, description="CPU usage percentage")
    memory_usage: Optional[float] = Field(None, ge=0, le=100, description="Memory usage percentage")

class SyncUploadRequest(BaseModel):
    """Request model for uploading local data to cloud."""
    user_id: str = Field(..., description="User UUID")
    sessions: List[Dict[str, Any]] = Field(..., description="List of sessions to sync")
    
    @validator('user_id')
    def validate_user_id(cls, v):
        try:
            uuid.UUID(v)
            return v
        except ValueError:
            raise ValueError('Invalid user_id format')

class ExportRequestModel(BaseModel):
    """Request model for data export."""
    user_id: str = Field(..., description="User UUID")
    format: ExportFormat = Field(..., description="Export format")
    date_range: Optional[Dict[str, date]] = Field(None, description="Date range for export")
    
    @validator('user_id')
    def validate_user_id(cls, v):
        try:
            uuid.UUID(v)
            return v
        except ValueError:
            raise ValueError('Invalid user_id format')

# ============================================================================
# PYDANTIC RESPONSE MODELS
# ============================================================================

class UserResponse(BaseModel):
    """Response model for user information."""
    id: str = Field(..., description="User UUID")
    email: str = Field(..., description="User email")
    username: str = Field(..., description="Username")
    avatar_url: Optional[str] = Field(None, description="Avatar URL")
    total_sessions: int = Field(0, description="Total number of sessions")
    total_blinks: int = Field(0, description="Total number of blinks")
    member_since: datetime = Field(..., description="Account creation date")
    
    class Config:
        from_attributes = True

class AuthResponse(BaseModel):
    """Response model for authentication."""
    access_token: str = Field(..., description="JWT access token")
    user: UserResponse = Field(..., description="User information")

class SessionResponse(BaseModel):
    """Response model for session information."""
    id: str = Field(..., description="Session UUID")
    start_time: datetime = Field(..., description="Session start time")
    end_time: Optional[datetime] = Field(None, description="Session end time")
    duration: int = Field(0, description="Session duration in seconds")
    total_blinks: int = Field(0, description="Total blinks in session")
    avg_blink_rate: float = Field(0.0, description="Average blink rate")
    max_blink_rate: float = Field(0.0, description="Maximum blink rate")
    health_score: Optional[int] = Field(None, description="Health score")
    status: SessionStatus = Field(..., description="Session status")
    
    class Config:
        from_attributes = True

class SessionHistoryResponse(BaseModel):
    """Response model for session history."""
    sessions: List[SessionResponse] = Field(..., description="List of sessions")
    total_count: int = Field(..., description="Total number of sessions")
    has_more: bool = Field(..., description="Whether there are more sessions")

class SyncResponse(BaseModel):
    """Response model for sync operations."""
    synced_sessions: int = Field(..., description="Number of sessions synced")
    synced_data_points: int = Field(..., description="Number of data points synced")
    conflicts: List[str] = Field(default_factory=list, description="List of conflicts")
    status: str = Field(..., description="Sync status")

class ExportResponse(BaseModel):
    """Response model for export requests."""
    export_id: str = Field(..., description="Export request UUID")
    status: ExportStatus = Field(..., description="Export status")
    estimated_completion: Optional[datetime] = Field(None, description="Estimated completion time")
    
    class Config:
        from_attributes = True

class HealthResponse(BaseModel):
    """Response model for health checks."""
    status: str = Field(..., description="Overall health status")
    timestamp: datetime = Field(..., description="Health check timestamp")
    database: Dict[str, Any] = Field(..., description="Database health information")
    api_version: str = Field(..., description="API version")
    uptime: float = Field(..., description="API uptime in seconds")

class ErrorResponse(BaseModel):
    """Standard error response model."""
    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Detailed error information")
    error_code: Optional[str] = Field(None, description="Error code")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Error timestamp")

# ============================================================================
# UTILITY MODELS
# ============================================================================

class PaginationParams(BaseModel):
    """Pagination parameters for list endpoints."""
    limit: int = Field(50, ge=1, le=100, description="Number of items per page")
    offset: int = Field(0, ge=0, description="Number of items to skip")

class DateRangeParams(BaseModel):
    """Date range parameters for filtering."""
    date_from: Optional[date] = Field(None, description="Start date")
    date_to: Optional[date] = Field(None, description="End date")
    
    @validator('date_to')
    def validate_date_range(cls, v, values):
        if v and 'date_from' in values and values['date_from']:
            if v < values['date_from']:
                raise ValueError('date_to must be after date_from')
        return v

# ============================================================================
# CONFIGURATION
# ============================================================================

# Pydantic model configuration
class Config:
    """Pydantic configuration for all models."""
    json_encoders = {
        datetime: lambda v: v.isoformat(),
        uuid.UUID: lambda v: str(v)
    }
    validate_assignment = True
    arbitrary_types_allowed = True
