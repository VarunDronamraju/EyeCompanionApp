"""
SQLite Database Manager for Local Eye Tracking Storage
Provides auto-session creation, real-time blink logging, and efficient data management
"""

import sqlite3
import json
import logging
import threading
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
import queue
import time

from .models import LocalSession, BlinkData, PerformanceLog, SyncQueue

logger = logging.getLogger(__name__)

class SQLiteManager:
    """
    SQLite database manager with auto-session creation and real-time blink logging.
    Implements connection pooling, batch operations, and automatic cleanup.
    """
    
    def __init__(self, db_path: str = "eye_tracker.db", user_data: Optional[Dict[str, Any]] = None):
        """
        Initialize SQLite manager with database path and user data
        
        Args:
            db_path: Path to SQLite database file
            user_data: User data from authentication (optional)
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # User data for session association
        self.user_data = user_data or {}
        self.user_id = user_data.get('id') if user_data else None
        self.user_email = user_data.get('email') if user_data else None
        
        # Connection management
        self._connection = None
        self._lock = threading.RLock()
        
        # Batch processing for blink data
        self.blink_queue = queue.Queue()
        self.batch_size = 50  # Process blink data in batches
        self.batch_timeout = 2.0  # seconds
        
        # Background processing thread
        self._processing_thread = None
        self._stop_processing = threading.Event()
        
        # Current active session
        self._current_session_id: Optional[int] = None
        
        # Initialize database
        self._initialize_database()
        self._start_background_processing()
        
        logger.info(f"SQLite manager initialized with database: {self.db_path}")
        if self.user_id:
            logger.info(f"User associated: {self.user_email} (ID: {self.user_id})")
        else:
            logger.info("No user association - authentication required")
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection with proper configuration"""
        if self._connection is None:
            self._connection = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
                timeout=30.0
            )
            self._connection.row_factory = sqlite3.Row
            
            # Enable foreign keys and WAL mode for better performance
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.execute("PRAGMA journal_mode = WAL")
            self._connection.execute("PRAGMA synchronous = NORMAL")
            self._connection.execute("PRAGMA cache_size = 10000")
            self._connection.execute("PRAGMA temp_store = MEMORY")
            
            logger.debug("Database connection established")
        
        return self._connection
    
    def _initialize_database(self):
        """Create database tables if they don't exist"""
        with self._lock:
            conn = self._get_connection()
            
            # Create local_sessions table with user association
            conn.execute("""
                CREATE TABLE IF NOT EXISTS local_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NULL,
                    user_email TEXT NULL,
                    start_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                    end_time DATETIME NULL,
                    total_blinks INTEGER DEFAULT 0,
                    max_blink_rate REAL DEFAULT 0,
                    avg_blink_rate REAL DEFAULT 0,
                    session_duration INTEGER DEFAULT 0,
                    is_synced BOOLEAN DEFAULT FALSE,
                    cloud_session_id TEXT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create blink_data table with user association and indexing for performance
            conn.execute("""
                CREATE TABLE IF NOT EXISTS blink_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    user_id TEXT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    blink_count INTEGER NOT NULL,
                    blink_rate REAL NOT NULL,
                    eye_aspect_ratio REAL,
                    is_synced BOOLEAN DEFAULT FALSE,
                    FOREIGN KEY (session_id) REFERENCES local_sessions(id) ON DELETE CASCADE
                )
            """)
            
            # Create performance_logs table with user association
            conn.execute("""
                CREATE TABLE IF NOT EXISTS performance_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    user_id TEXT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    cpu_usage REAL,
                    memory_usage REAL,
                    battery_level INTEGER,
                    FOREIGN KEY (session_id) REFERENCES local_sessions(id) ON DELETE CASCADE
                )
            """)
            
            # Create sync_queue table with user association
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sync_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NULL,
                    table_name TEXT NOT NULL,
                    record_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    data TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    synced_at DATETIME NULL
                )
            """)
            
            # Create indexes for better query performance
            conn.execute("CREATE INDEX IF NOT EXISTS idx_blink_data_session_id ON blink_data(session_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_blink_data_timestamp ON blink_data(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_blink_data_synced ON blink_data(is_synced)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_start_time ON local_sessions(start_time)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_synced ON local_sessions(is_synced)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sync_queue_synced ON sync_queue(synced_at)")
            
            conn.commit()
            
            # Migrate existing tables to add user_id columns if they don't exist
            self._migrate_existing_tables()
            
            logger.info("Database tables and indexes created")
    
    def _migrate_existing_tables(self):
        """Migrate existing tables to add user_id columns if they don't exist"""
        with self._lock:
            conn = self._get_connection()
            
            try:
                # Check if user_id column exists in local_sessions
                cursor = conn.execute("PRAGMA table_info(local_sessions)")
                columns = [column[1] for column in cursor.fetchall()]
                
                if 'user_id' not in columns:
                    logger.info("Adding user_id column to local_sessions table")
                    conn.execute("ALTER TABLE local_sessions ADD COLUMN user_id TEXT NULL")
                    conn.execute("ALTER TABLE local_sessions ADD COLUMN user_email TEXT NULL")
                
                # Check if user_id column exists in blink_data
                cursor = conn.execute("PRAGMA table_info(blink_data)")
                columns = [column[1] for column in cursor.fetchall()]
                
                if 'user_id' not in columns:
                    logger.info("Adding user_id column to blink_data table")
                    conn.execute("ALTER TABLE blink_data ADD COLUMN user_id TEXT NULL")
                
                # Check if user_id column exists in performance_logs
                cursor = conn.execute("PRAGMA table_info(performance_logs)")
                columns = [column[1] for column in cursor.fetchall()]
                
                if 'user_id' not in columns:
                    logger.info("Adding user_id column to performance_logs table")
                    conn.execute("ALTER TABLE performance_logs ADD COLUMN user_id TEXT NULL")
                
                # Check if user_id column exists in sync_queue
                cursor = conn.execute("PRAGMA table_info(sync_queue)")
                columns = [column[1] for column in cursor.fetchall()]
                
                if 'user_id' not in columns:
                    logger.info("Adding user_id column to sync_queue table")
                    conn.execute("ALTER TABLE sync_queue ADD COLUMN user_id TEXT NULL")
                
                conn.commit()
                logger.info("Database migration completed")
                
            except Exception as e:
                logger.error(f"Error during database migration: {e}")
                conn.rollback()
    
    def _start_background_processing(self):
        """Start background thread for processing blink data batches"""
        self._processing_thread = threading.Thread(
            target=self._process_blink_batches,
            daemon=True,
            name="BlinkDataProcessor"
        )
        self._processing_thread.start()
        logger.info("Background blink processing started")
    
    def _process_blink_batches(self):
        """Background thread for processing blink data in batches"""
        batch = []
        last_batch_time = time.time()
        
        while not self._stop_processing.is_set():
            try:
                # Get blink data from queue with timeout
                try:
                    blink_data = self.blink_queue.get(timeout=0.5)
                    batch.append(blink_data)
                except queue.Empty:
                    pass
                
                current_time = time.time()
                
                # Process batch if full or timeout reached
                if (len(batch) >= self.batch_size or 
                    (batch and current_time - last_batch_time >= self.batch_timeout)):
                    
                    if batch:
                        self._insert_blink_batch(batch)
                        batch = []
                        last_batch_time = current_time
                
            except Exception as e:
                logger.error(f"Error in blink batch processing: {e}")
                time.sleep(0.1)
        
        # Process remaining items
        if batch:
            try:
                self._insert_blink_batch(batch)
            except Exception as e:
                logger.error(f"Error processing final batch: {e}")
    
    def _insert_blink_batch(self, blink_data_list: List[BlinkData]):
        """Insert multiple blink data records efficiently"""
        with self._lock:
            conn = self._get_connection()
            
            try:
                conn.execute("BEGIN TRANSACTION")
                
                for blink_data in blink_data_list:
                    conn.execute("""
                        INSERT INTO blink_data 
                        (session_id, timestamp, blink_count, blink_rate, eye_aspect_ratio, is_synced)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        blink_data.session_id,
                        blink_data.timestamp.isoformat(),
                        blink_data.blink_count,
                        blink_data.blink_rate,
                        blink_data.eye_aspect_ratio,
                        blink_data.is_synced
                    ))
                
                conn.commit()
                logger.debug(f"Inserted {len(blink_data_list)} blink records in batch")
                
            except Exception as e:
                conn.rollback()
                logger.error(f"Error inserting blink batch: {e}")
                raise
    
    def auto_create_session(self) -> int:
        """
        Automatically create a new session when app launches.
        This ensures no data is ever lost.
        
        Returns:
            int: Session ID of the created session
        """
        with self._lock:
            conn = self._get_connection()
            
            try:
                # Check if there's an active session (no end_time)
                cursor = conn.execute("""
                    SELECT id FROM local_sessions 
                    WHERE end_time IS NULL 
                    ORDER BY start_time DESC 
                    LIMIT 1
                """)
                
                active_session = cursor.fetchone()
                
                if active_session:
                    # Use existing active session
                    session_id = active_session['id']
                    logger.info(f"Using existing active session: {session_id}")
                else:
                    # Create new session with user information
                    cursor = conn.execute("""
                        INSERT INTO local_sessions 
                        (user_id, user_email, start_time, created_at) 
                        VALUES (?, ?, ?, ?)
                    """, (
                        self.user_id,
                        self.user_email,
                        datetime.now().isoformat(),
                        datetime.now().isoformat()
                    ))
                    
                    session_id = cursor.lastrowid
                    user_info = f" for user {self.user_email}" if self.user_email else " (authentication required)"
                    logger.info(f"Auto-created new session: {session_id}{user_info}")
                
                self._current_session_id = session_id
                return session_id
                
            except Exception as e:
                logger.error(f"Error auto-creating session: {e}")
                raise
    
    def log_blink(self, blink_count: int, blink_rate: float, eye_aspect_ratio: Optional[float] = None):
        """
        Log blink data in real-time with minimal latency.
        Uses background batch processing for efficiency.
        
        Args:
            blink_count: Current total blink count
            blink_rate: Current blink rate (blinks per minute)
            eye_aspect_ratio: Optional eye aspect ratio value
        """
        if self._current_session_id is None:
            logger.warning("No active session for blink logging")
            return
        
        try:
            blink_data = BlinkData(
                session_id=self._current_session_id,
                user_id=self.user_id,
                blink_count=blink_count,
                blink_rate=blink_rate,
                eye_aspect_ratio=eye_aspect_ratio
            )
            
            # Add to processing queue (non-blocking)
            self.blink_queue.put(blink_data, block=False)
            
            # Update session totals immediately
            self._update_session_totals(blink_count, blink_rate)
            
            logger.debug(f"Blink logged: count={blink_count}, rate={blink_rate:.1f}")
            
        except queue.Full:
            logger.warning("Blink queue full, dropping blink data")
        except Exception as e:
            logger.error(f"Error logging blink: {e}")
    
    def _update_session_totals(self, blink_count: int, blink_rate: float):
        """Update session totals immediately for real-time display"""
        with self._lock:
            conn = self._get_connection()
            
            try:
                conn.execute("""
                    UPDATE local_sessions 
                    SET total_blinks = ?, 
                        max_blink_rate = CASE WHEN ? > max_blink_rate THEN ? ELSE max_blink_rate END,
                        avg_blink_rate = (
                            SELECT AVG(blink_rate) 
                            FROM blink_data 
                            WHERE session_id = ?
                        )
                    WHERE id = ?
                """, (blink_count, blink_rate, blink_rate, self._current_session_id, self._current_session_id))
                
                conn.commit()
                
            except Exception as e:
                logger.error(f"Error updating session totals: {e}")
    
    def log_performance(self, cpu_usage: float, memory_usage: float, battery_level: Optional[int] = None):
        """Log system performance metrics"""
        if self._current_session_id is None:
            return
        
        with self._lock:
            conn = self._get_connection()
            
            try:
                conn.execute("""
                    INSERT INTO performance_logs 
                    (session_id, user_id, timestamp, cpu_usage, memory_usage, battery_level)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    self._current_session_id,
                    self.user_id,
                    datetime.now().isoformat(),
                    cpu_usage,
                    memory_usage,
                    battery_level
                ))
                
                conn.commit()
                
            except Exception as e:
                logger.error(f"Error logging performance: {e}")
    
    def end_current_session(self) -> Optional[LocalSession]:
        """
        End the current active session
        
        Returns:
            LocalSession: The ended session data
        """
        if self._current_session_id is None:
            return None
        
        with self._lock:
            conn = self._get_connection()
            
            try:
                # Wait for any pending blink data to be processed
                while not self.blink_queue.empty():
                    time.sleep(0.1)
                
                # Update session end time and calculate duration
                end_time = datetime.now()
                conn.execute("""
                    UPDATE local_sessions 
                    SET end_time = ?, session_duration = ? 
                    WHERE id = ?
                """, (
                    end_time.isoformat(),
                    int((end_time - datetime.fromisoformat(
                        conn.execute("SELECT start_time FROM local_sessions WHERE id = ?", 
                                   (self._current_session_id,)).fetchone()['start_time']
                    )).total_seconds()),
                    self._current_session_id
                ))
                
                conn.commit()
                
                # Get the updated session data
                session_data = self.get_session(self._current_session_id)
                self._current_session_id = None
                
                logger.info(f"Session {session_data.id} ended with {session_data.total_blinks} blinks")
                return session_data
                
            except Exception as e:
                logger.error(f"Error ending session: {e}")
                return None
    
    def get_current_session(self) -> Optional[LocalSession]:
        """Get the current active session"""
        if self._current_session_id is None:
            return None
        
        return self.get_session(self._current_session_id)
    
    def get_session(self, session_id: int) -> Optional[LocalSession]:
        """Get session by ID"""
        with self._lock:
            conn = self._get_connection()
            
            try:
                cursor = conn.execute("""
                    SELECT * FROM local_sessions WHERE id = ?
                """, (session_id,))
                
                row = cursor.fetchone()
                if row:
                    return LocalSession.from_dict(dict(row))
                return None
                
            except Exception as e:
                logger.error(f"Error getting session {session_id}: {e}")
                return None
    
    def get_session_stats(self, session_id: int) -> Dict[str, Any]:
        """Get comprehensive session statistics"""
        with self._lock:
            conn = self._get_connection()
            
            try:
                # Get session data
                session = self.get_session(session_id)
                if not session:
                    return {}
                
                # Get blink data summary
                cursor = conn.execute("""
                    SELECT 
                        COUNT(*) as total_blinks,
                        AVG(blink_rate) as avg_rate,
                        MAX(blink_rate) as max_rate,
                        MIN(timestamp) as first_blink,
                        MAX(timestamp) as last_blink
                    FROM blink_data 
                    WHERE session_id = ?
                """, (session_id,))
                
                blink_stats = cursor.fetchone()
                
                # Get performance summary
                cursor = conn.execute("""
                    SELECT 
                        AVG(cpu_usage) as avg_cpu,
                        AVG(memory_usage) as avg_memory,
                        AVG(battery_level) as avg_battery
                    FROM performance_logs 
                    WHERE session_id = ?
                """, (session_id,))
                
                perf_stats = cursor.fetchone()
                
                return {
                    'session': session.to_dict(),
                    'blink_stats': dict(blink_stats) if blink_stats else {},
                    'performance_stats': dict(perf_stats) if perf_stats else {},
                    'duration_minutes': session.session_duration / 60 if session.session_duration else 0
                }
                
            except Exception as e:
                logger.error(f"Error getting session stats: {e}")
                return {}
    
    def get_recent_sessions(self, limit: int = 10, user_id: Optional[str] = None) -> List[LocalSession]:
        """Get recent sessions for display, filtered by user (authentication required)"""
        with self._lock:
            conn = self._get_connection()
            
            try:
                if not user_id:
                    logger.warning("Authentication required to view sessions")
                    return []
                
                # Get sessions for specific user
                cursor = conn.execute("""
                    SELECT * FROM local_sessions 
                    WHERE user_id = ?
                    ORDER BY start_time DESC 
                    LIMIT ?
                """, (user_id, limit))
                
                sessions = []
                for row in cursor.fetchall():
                    sessions.append(LocalSession.from_dict(dict(row)))
                
                return sessions
                
            except Exception as e:
                logger.error(f"Error getting recent sessions: {e}")
                return []
    
    def cleanup_old_data(self, days_to_keep: int = 30):
        """Clean up old data to keep database size manageable"""
        with self._lock:
            conn = self._get_connection()
            cutoff_date = datetime.now() - timedelta(days=days_to_keep)
            
            try:
                conn.execute("BEGIN TRANSACTION")
                
                # Delete old sessions and related data (cascade will handle blink_data and performance_logs)
                deleted_sessions = conn.execute("""
                    DELETE FROM local_sessions 
                    WHERE start_time < ? AND end_time IS NOT NULL
                """, (cutoff_date.isoformat(),)).rowcount
                
                # Delete old sync queue items
                deleted_sync = conn.execute("""
                    DELETE FROM sync_queue 
                    WHERE created_at < ? AND synced_at IS NOT NULL
                """, (cutoff_date.isoformat(),)).rowcount
                
                conn.commit()
                
                logger.info(f"Cleanup completed: {deleted_sessions} sessions, {deleted_sync} sync items")
                
            except Exception as e:
                conn.rollback()
                logger.error(f"Error during cleanup: {e}")
    
    def get_database_size(self) -> int:
        """Get database file size in bytes"""
        try:
            return self.db_path.stat().st_size
        except Exception as e:
            logger.error(f"Error getting database size: {e}")
            return 0
    
    def close(self):
        """Close database connection and stop background processing"""
        self._stop_processing.set()
        
        if self._processing_thread and self._processing_thread.is_alive():
            self._processing_thread.join(timeout=5.0)
        
        if self._connection:
            self._connection.close()
            self._connection = None
        
        logger.info("SQLite manager closed")
    
    def __del__(self):
        """Cleanup on destruction"""
        self.close()
