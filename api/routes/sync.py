import logging
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import and_

from database import get_db
from models import (
    SyncUploadRequest, SyncResponse, BlinkDataPoint,
    CloudSession, SessionData, User
)
from .auth import get_current_user

# Configure logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter()

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def process_blink_data(db: Session, session_id: str, blink_data: List[Dict[str, Any]]) -> int:
    """
    Process and store blink data points for a session.
    Returns the number of data points processed.
    """
    data_points_processed = 0
    
    for data_point in blink_data:
        try:
            # Create session data record
            session_data = SessionData(
                session_id=session_id,
                timestamp=data_point.get("timestamp"),
                blink_count=data_point.get("blink_count", 0),
                blink_rate=data_point.get("blink_rate", 0.0),
                eye_aspect_ratio=data_point.get("eye_aspect_ratio"),
                cpu_usage=data_point.get("cpu_usage"),
                memory_usage=data_point.get("memory_usage"),
                created_at=datetime.utcnow()
            )
            
            db.add(session_data)
            data_points_processed += 1
            
        except Exception as e:
            logger.error(f"Failed to process blink data point: {e}")
            continue
    
    return data_points_processed

def resolve_session_conflicts(db: Session, user_id: str, local_sessions: List[Dict[str, Any]]) -> List[str]:
    """
    Resolve conflicts between local and cloud sessions.
    Returns list of conflict messages.
    """
    conflicts = []
    
    for local_session in local_sessions:
        local_session_id = local_session.get("local_id")
        start_time = local_session.get("start_time")
        
        if not start_time or not local_session_id:
            continue
        
        # Check for existing cloud session with same start time
        existing_session = db.query(CloudSession).filter(
            and_(
                CloudSession.user_id == user_id,
                CloudSession.start_time == start_time
            )
        ).first()
        
        if existing_session:
            conflicts.append(
                f"Session {local_session_id} conflicts with existing cloud session {existing_session.id}"
            )
    
    return conflicts

# ============================================================================
# SYNCHRONIZATION ENDPOINTS
# ============================================================================

@router.post(
    "/upload",
    response_model=SyncResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload Local Data",
    description="Upload local session data to cloud storage"
)
async def upload_local_data(
    request: SyncUploadRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Upload local session data to cloud storage.
    
    This endpoint:
    1. Validates the user ID matches the authenticated user
    2. Resolves conflicts between local and cloud sessions
    3. Creates cloud sessions for new local sessions
    4. Uploads blink data points
    5. Returns sync status and statistics
    """
    # Validate user ID matches authenticated user
    if request.user_id != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User ID does not match authenticated user"
        )
    
    synced_sessions = 0
    synced_data_points = 0
    conflicts = []
    
    try:
        # Process each session
        for session_data in request.sessions:
            local_session_id = session_data.get("local_id")
            start_time = session_data.get("start_time")
            end_time = session_data.get("end_time")
            blink_data = session_data.get("blink_data", [])
            
            if not start_time:
                logger.warning(f"Skipping session {local_session_id}: missing start_time")
                continue
            
            # Check for existing cloud session
            existing_session = db.query(CloudSession).filter(
                and_(
                    CloudSession.user_id == current_user.id,
                    CloudSession.start_time == start_time
                )
            ).first()
            
            if existing_session:
                # Update existing session with new data
                if end_time and not existing_session.end_time:
                    existing_session.end_time = end_time
                
                # Update session statistics
                if blink_data:
                    total_blinks = max([d.get("blink_count", 0) for d in blink_data])
                    avg_blink_rate = sum([d.get("blink_rate", 0) for d in blink_data]) / len(blink_data)
                    max_blink_rate = max([d.get("blink_rate", 0) for d in blink_data])
                    
                    existing_session.total_blinks = max(existing_session.total_blinks, total_blinks)
                    existing_session.avg_blink_rate = max(existing_session.avg_blink_rate, avg_blink_rate)
                    existing_session.max_blink_rate = max(existing_session.max_blink_rate, max_blink_rate)
                
                # Process blink data
                data_points_added = process_blink_data(db, str(existing_session.id), blink_data)
                synced_data_points += data_points_added
                
                logger.info(f"Updated existing session {existing_session.id} with {data_points_added} data points")
                
            else:
                # Create new cloud session
                cloud_session = CloudSession(
                    user_id=current_user.id,
                    local_session_id=local_session_id,
                    start_time=start_time,
                    end_time=end_time,
                    created_at=datetime.utcnow()
                )
                
                db.add(cloud_session)
                db.flush()  # Get the session ID
                
                # Process blink data
                data_points_added = process_blink_data(db, str(cloud_session.id), blink_data)
                synced_data_points += data_points_added
                
                # Update session statistics
                if blink_data:
                    total_blinks = max([d.get("blink_count", 0) for d in blink_data])
                    avg_blink_rate = sum([d.get("blink_rate", 0) for d in blink_data]) / len(blink_data)
                    max_blink_rate = max([d.get("blink_rate", 0) for d in blink_data])
                    
                    cloud_session.total_blinks = total_blinks
                    cloud_session.avg_blink_rate = avg_blink_rate
                    cloud_session.max_blink_rate = max_blink_rate
                
                synced_sessions += 1
                logger.info(f"Created new session {cloud_session.id} with {data_points_added} data points")
        
        # Commit all changes
        db.commit()
        
        logger.info(f"Sync completed for user {current_user.email}: {synced_sessions} sessions, {synced_data_points} data points")
        
        return SyncResponse(
            synced_sessions=synced_sessions,
            synced_data_points=synced_data_points,
            conflicts=conflicts,
            status="success"
        )
        
    except Exception as e:
        db.rollback()
        logger.error(f"Sync failed for user {current_user.email}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sync failed: {str(e)}"
        )

@router.get(
    "/download",
    summary="Download Cloud Data",
    description="Download cloud session data for local synchronization"
)
async def download_cloud_data(
    last_sync_time: Optional[datetime] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Download cloud session data for local synchronization.
    
    This endpoint returns:
    1. Sessions created/updated since last sync
    2. Session data points
    3. User settings and preferences
    """
    try:
        # Get sessions since last sync
        query = db.query(CloudSession).filter(CloudSession.user_id == current_user.id)
        
        if last_sync_time:
            query = query.filter(CloudSession.updated_at >= last_sync_time)
        
        sessions = query.all()
        
        # Prepare response data
        session_data = []
        for session in sessions:
            # Get session data points
            data_points = db.query(SessionData).filter(
                SessionData.session_id == session.id
            ).all()
            
            session_info = {
                "id": str(session.id),
                "local_session_id": session.local_session_id,
                "start_time": session.start_time,
                "end_time": session.end_time,
                "total_blinks": session.total_blinks,
                "avg_blink_rate": session.avg_blink_rate,
                "max_blink_rate": session.max_blink_rate,
                "session_duration": session.session_duration,
                "health_score": session.health_score,
                "device_info": session.device_info,
                "system_metrics": session.system_metrics,
                "created_at": session.created_at,
                "data_points": [
                    {
                        "timestamp": dp.timestamp,
                        "blink_count": dp.blink_count,
                        "blink_rate": dp.blink_rate,
                        "eye_aspect_ratio": dp.eye_aspect_ratio,
                        "cpu_usage": dp.cpu_usage,
                        "memory_usage": dp.memory_usage
                    }
                    for dp in data_points
                ]
            }
            
            session_data.append(session_info)
        
        # Get user settings
        user_settings = current_user.settings or {}
        
        return {
            "sessions": session_data,
            "user_settings": user_settings,
            "sync_timestamp": datetime.utcnow().isoformat(),
            "total_sessions": len(session_data)
        }
        
    except Exception as e:
        logger.error(f"Download failed for user {current_user.email}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Download failed: {str(e)}"
        )

@router.post(
    "/manual",
    response_model=SyncResponse,
    summary="Manual Sync",
    description="Trigger manual synchronization for testing purposes"
)
async def manual_sync(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Trigger manual synchronization.
    
    This endpoint is useful for testing and debugging sync functionality.
    """
    try:
        # Get all sessions for user
        sessions = db.query(CloudSession).filter(
            CloudSession.user_id == current_user.id
        ).all()
        
        total_sessions = len(sessions)
        total_data_points = 0
        
        for session in sessions:
            data_points = db.query(SessionData).filter(
                SessionData.session_id == session.id
            ).count()
            total_data_points += data_points
        
        logger.info(f"Manual sync completed for user {current_user.email}")
        
        return SyncResponse(
            synced_sessions=total_sessions,
            synced_data_points=total_data_points,
            conflicts=[],
            status="manual_sync_completed"
        )
        
    except Exception as e:
        logger.error(f"Manual sync failed for user {current_user.email}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Manual sync failed: {str(e)}"
        )

@router.get(
    "/status",
    summary="Sync Status",
    description="Get synchronization status and statistics"
)
async def get_sync_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get synchronization status and statistics.
    """
    try:
        # Get session statistics
        total_sessions = db.query(CloudSession).filter(
            CloudSession.user_id == current_user.id
        ).count()
        
        active_sessions = db.query(CloudSession).filter(
            and_(
                CloudSession.user_id == current_user.id,
                CloudSession.end_time.is_(None)
            )
        ).count()
        
        # Get data point statistics
        total_data_points = db.query(SessionData).join(CloudSession).filter(
            CloudSession.user_id == current_user.id
        ).count()
        
        # Get last sync time (approximate)
        last_session = db.query(CloudSession).filter(
            CloudSession.user_id == current_user.id
        ).order_by(CloudSession.created_at.desc()).first()
        
        last_sync_time = last_session.created_at if last_session else None
        
        return {
            "user_id": str(current_user.id),
            "total_sessions": total_sessions,
            "active_sessions": active_sessions,
            "total_data_points": total_data_points,
            "last_sync_time": last_sync_time.isoformat() if last_sync_time else None,
            "sync_status": "healthy",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get sync status for user {current_user.email}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get sync status: {str(e)}"
        )

# ============================================================================
# CONFLICT RESOLUTION ENDPOINTS
# ============================================================================

@router.post(
    "/resolve-conflicts",
    summary="Resolve Conflicts",
    description="Resolve data conflicts between local and cloud storage"
)
async def resolve_conflicts(
    conflict_resolutions: List[Dict[str, Any]],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Resolve data conflicts between local and cloud storage.
    
    This endpoint allows clients to specify how to resolve conflicts:
    - Keep local data
    - Keep cloud data
    - Merge data
    """
    try:
        resolved_conflicts = 0
        
        for resolution in conflict_resolutions:
            conflict_id = resolution.get("conflict_id")
            resolution_type = resolution.get("resolution_type")  # local, cloud, merge
            session_id = resolution.get("session_id")
            
            if not all([conflict_id, resolution_type, session_id]):
                continue
            
            # Get the session
            session = db.query(CloudSession).filter(
                and_(
                    CloudSession.id == session_id,
                    CloudSession.user_id == current_user.id
                )
            ).first()
            
            if not session:
                continue
            
            # Apply resolution based on type
            if resolution_type == "local":
                # Update cloud session with local data
                local_data = resolution.get("local_data", {})
                if local_data:
                    session.total_blinks = local_data.get("total_blinks", session.total_blinks)
                    session.avg_blink_rate = local_data.get("avg_blink_rate", session.avg_blink_rate)
                    session.max_blink_rate = local_data.get("max_blink_rate", session.max_blink_rate)
                    session.health_score = local_data.get("health_score", session.health_score)
            
            elif resolution_type == "cloud":
                # Keep cloud data as is (no changes needed)
                pass
            
            elif resolution_type == "merge":
                # Merge local and cloud data
                local_data = resolution.get("local_data", {})
                if local_data:
                    session.total_blinks = max(session.total_blinks, local_data.get("total_blinks", 0))
                    session.avg_blink_rate = max(session.avg_blink_rate, local_data.get("avg_blink_rate", 0))
                    session.max_blink_rate = max(session.max_blink_rate, local_data.get("max_blink_rate", 0))
                    # For health score, take the better one
                    local_health = local_data.get("health_score")
                    if local_health and (session.health_score is None or local_health > session.health_score):
                        session.health_score = local_health
            
            resolved_conflicts += 1
        
        db.commit()
        
        logger.info(f"Resolved {resolved_conflicts} conflicts for user {current_user.email}")
        
        return {
            "resolved_conflicts": resolved_conflicts,
            "status": "success",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"Conflict resolution failed for user {current_user.email}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Conflict resolution failed: {str(e)}"
        )
