import logging
import uuid
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc


from database import get_db
from models import (
    SessionStartRequest, SessionEndRequest, SessionResponse, SessionHistoryResponse,
    PaginationParams, DateRangeParams, CloudSession, SessionData, User, SessionStatus
)
from .auth import get_current_user

# Configure logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter()

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_active_session(db: Session, user_id: str) -> Optional[CloudSession]:
    """
    Get the currently active session for a user.
    """
    return db.query(CloudSession).filter(
        and_(
            CloudSession.user_id == user_id,
            CloudSession.end_time.is_(None)
        )
    ).first()

def calculate_session_duration(start_time: datetime, end_time: datetime) -> int:
    """
    Calculate session duration in seconds.
    """
    return int((end_time - start_time).total_seconds())

def calculate_health_score(avg_blink_rate: float, session_duration: int) -> int:
    """
    Calculate health score based on blink rate and session duration.
    Normal blink rate is 15-20 blinks per minute.
    """
    # Base score starts at 100
    score = 100
    
    # Deduct points for abnormal blink rates
    if avg_blink_rate < 10:  # Too few blinks (dry eyes)
        score -= 20
    elif avg_blink_rate > 30:  # Too many blinks (eye strain)
        score -= 15
    elif avg_blink_rate > 25:  # Slightly high
        score -= 10
    
    # Deduct points for very long sessions (eye strain)
    if session_duration > 7200:  # More than 2 hours
        score -= 20
    elif session_duration > 3600:  # More than 1 hour
        score -= 10
    
    # Ensure score is between 0 and 100
    return max(0, min(100, score))

# ============================================================================
# SESSION MANAGEMENT ENDPOINTS
# ============================================================================

@router.post(
    "/start",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start Cloud Session",
    description="Start a new cloud session for the authenticated user"
)
async def start_session(
    request: SessionStartRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Start a new cloud session.
    
    This endpoint:
    1. Validates the user ID matches the authenticated user
    2. Checks for any existing active session
    3. Creates a new cloud session
    4. Returns session information
    """
    # Validate user ID matches authenticated user
    if request.user_id != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User ID does not match authenticated user"
        )
    
    # Check for existing active session
    active_session = get_active_session(db, str(current_user.id))
    if active_session:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User already has an active session"
        )
    
    # Create new session
    session = CloudSession(
        user_id=current_user.id,
        start_time=datetime.utcnow(),
        device_info=request.device_info.dict(),
        created_at=datetime.utcnow()
    )
    
    db.add(session)
    db.commit()
    db.refresh(session)
    
    logger.info(f"Started new session for user {current_user.email}: {session.id}")
    
    return SessionResponse(
        id=str(session.id),
        start_time=session.start_time,
        end_time=session.end_time,
        duration=0,
        total_blinks=session.total_blinks,
        avg_blink_rate=session.avg_blink_rate,
        max_blink_rate=session.max_blink_rate,
        health_score=session.health_score,
        status=SessionStatus.ACTIVE
    )

@router.put(
    "/end",
    response_model=SessionResponse,
    summary="End Cloud Session",
    description="End the currently active cloud session"
)
async def end_session(
    request: SessionEndRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    End the currently active cloud session.
    
    This endpoint:
    1. Validates the session belongs to the authenticated user
    2. Updates session with end time and statistics
    3. Calculates health score
    4. Returns updated session information
    """
    # Get the session
    session = db.query(CloudSession).filter(
        CloudSession.id == request.session_id
    ).first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    
    # Validate session belongs to user
    if session.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Session does not belong to authenticated user"
        )
    
    # Check if session is already ended
    if session.end_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session is already ended"
        )
    
    # Update session
    session.end_time = datetime.utcnow()
    session.total_blinks = request.total_blinks
    session.avg_blink_rate = request.avg_blink_rate
    session.max_blink_rate = request.max_blink_rate
    session.session_duration = request.session_duration
    
    # Calculate health score
    health_score = calculate_health_score(request.avg_blink_rate, request.session_duration)
    session.health_score = health_score
    
    db.commit()
    db.refresh(session)
    
    logger.info(f"Ended session {session.id} for user {current_user.email}")
    
    return SessionResponse(
        id=str(session.id),
        start_time=session.start_time,
        end_time=session.end_time,
        duration=session.session_duration,
        total_blinks=session.total_blinks,
        avg_blink_rate=session.avg_blink_rate,
        max_blink_rate=session.max_blink_rate,
        health_score=session.health_score,
        status=SessionStatus.ENDED
    )

@router.get(
    "/current",
    response_model=SessionResponse,
    summary="Get Current Session",
    description="Get information about the currently active session"
)
async def get_current_session(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get the currently active session for the authenticated user.
    """
    session = get_active_session(db, str(current_user.id))
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active session found"
        )
    
    # Calculate current duration
    duration = calculate_session_duration(session.start_time, datetime.utcnow())
    
    return SessionResponse(
        id=str(session.id),
        start_time=session.start_time,
        end_time=session.end_time,
        duration=duration,
        total_blinks=session.total_blinks,
        avg_blink_rate=session.avg_blink_rate,
        max_blink_rate=session.max_blink_rate,
        health_score=session.health_score,
        status=SessionStatus.ACTIVE
    )

@router.get(
    "/history",
    response_model=SessionHistoryResponse,
    summary="Get Session History",
    description="Get paginated session history for the authenticated user"
)
async def get_session_history(
    limit: int = Query(50, ge=1, le=100, description="Number of sessions to return"),
    offset: int = Query(0, ge=0, description="Number of sessions to skip"),
    date_from: Optional[datetime] = Query(None, description="Filter sessions from this date"),
    date_to: Optional[datetime] = Query(None, description="Filter sessions until this date"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get paginated session history for the authenticated user.
    
    Supports filtering by date range and pagination.
    """
    # Build query
    query = db.query(CloudSession).filter(CloudSession.user_id == current_user.id)
    
    # Apply date filters
    if date_from:
        query = query.filter(CloudSession.start_time >= date_from)
    if date_to:
        query = query.filter(CloudSession.start_time <= date_to)
    
    # Get total count
    total_count = query.count()
    
    # Apply pagination and ordering
    sessions = query.order_by(desc(CloudSession.start_time)).offset(offset).limit(limit).all()
    
    # Convert to response models
    session_responses = []
    for session in sessions:
        duration = 0
        if session.end_time:
            duration = calculate_session_duration(session.start_time, session.end_time)
        
        session_responses.append(SessionResponse(
            id=str(session.id),
            start_time=session.start_time,
            end_time=session.end_time,
            duration=duration,
            total_blinks=session.total_blinks,
            avg_blink_rate=session.avg_blink_rate,
            max_blink_rate=session.max_blink_rate,
            health_score=session.health_score,
            status=SessionStatus.ENDED if session.end_time else SessionStatus.ACTIVE
        ))
    
    return SessionHistoryResponse(
        sessions=session_responses,
        total_count=total_count,
        has_more=(offset + limit) < total_count
    )

@router.get(
    "/{session_id}",
    response_model=SessionResponse,
    summary="Get Session Details",
    description="Get detailed information about a specific session"
)
async def get_session_details(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get detailed information about a specific session.
    """
    # Validate session ID format
    try:
        uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid session ID format"
        )
    
    # Get session
    session = db.query(CloudSession).filter(CloudSession.id == session_id).first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    
    # Validate session belongs to user
    if session.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Session does not belong to authenticated user"
        )
    
    # Calculate duration
    duration = 0
    if session.end_time:
        duration = calculate_session_duration(session.start_time, session.end_time)
    
    return SessionResponse(
        id=str(session.id),
        start_time=session.start_time,
        end_time=session.end_time,
        duration=duration,
        total_blinks=session.total_blinks,
        avg_blink_rate=session.avg_blink_rate,
        max_blink_rate=session.max_blink_rate,
        health_score=session.health_score,
        status=SessionStatus.ENDED if session.end_time else SessionStatus.ACTIVE
    )

@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Session",
    description="Delete a specific session (admin only)"
)
async def delete_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete a specific session.
    
    Note: This is a destructive operation and should be used with caution.
    In production, consider soft deletion instead.
    """
    # Validate session ID format
    try:
        uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid session ID format"
        )
    
    # Get session
    session = db.query(CloudSession).filter(CloudSession.id == session_id).first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    
    # Validate session belongs to user
    if session.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Session does not belong to authenticated user"
        )
    
    # Delete session (cascade will delete related data)
    db.delete(session)
    db.commit()
    
    logger.info(f"Deleted session {session_id} for user {current_user.email}")

# ============================================================================
# ANALYTICS ENDPOINTS
# ============================================================================

@router.get(
    "/analytics/summary",
    summary="Get Session Analytics Summary",
    description="Get summary statistics for user sessions"
)
async def get_session_analytics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get summary analytics for user sessions.
    """
    # Get all sessions for user
    sessions = db.query(CloudSession).filter(
        CloudSession.user_id == current_user.id,
        CloudSession.end_time.isnot(None)  # Only completed sessions
    ).all()
    
    if not sessions:
        return {
            "total_sessions": 0,
            "total_duration": 0,
            "total_blinks": 0,
            "avg_blink_rate": 0,
            "avg_session_duration": 0,
            "avg_health_score": 0,
            "best_health_score": 0,
            "worst_health_score": 0
        }
    
    # Calculate statistics
    total_sessions = len(sessions)
    total_duration = sum(s.session_duration for s in sessions)
    total_blinks = sum(s.total_blinks for s in sessions)
    avg_blink_rate = sum(s.avg_blink_rate for s in sessions) / total_sessions
    avg_session_duration = total_duration / total_sessions
    avg_health_score = sum(s.health_score or 0 for s in sessions) / total_sessions
    
    health_scores = [s.health_score for s in sessions if s.health_score is not None]
    best_health_score = max(health_scores) if health_scores else 0
    worst_health_score = min(health_scores) if health_scores else 0
    
    return {
        "total_sessions": total_sessions,
        "total_duration": total_duration,
        "total_blinks": total_blinks,
        "avg_blink_rate": round(avg_blink_rate, 2),
        "avg_session_duration": round(avg_session_duration, 2),
        "avg_health_score": round(avg_health_score, 2),
        "best_health_score": best_health_score,
        "worst_health_score": worst_health_score
    }
