import os
import logging
from typing import Generator, Optional
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from sqlalchemy.exc import SQLAlchemyError, OperationalError
import sys
import traceback

# Add parent directory to path to import config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database configuration
DATABASE_URL = config.DATABASE_URL

# Create SQLAlchemy engine with connection pooling
engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=20,  # Number of connections to maintain
    max_overflow=30,  # Additional connections that can be created
    pool_pre_ping=True,  # Verify connections before use
    pool_recycle=3600,  # Recycle connections after 1 hour
    echo=False,  # Set to True for SQL query logging
    connect_args={
        "connect_timeout": 10,
        "application_name": "wellness_at_work_api"
    }
)

# Create SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create Base class for models
Base = declarative_base()

def get_db() -> Generator[Session, None, None]:
    """
    Dependency to get database session.
    Handles connection errors and ensures proper cleanup.
    """
    db = SessionLocal()
    try:
        yield db
    except SQLAlchemyError as e:
        logger.error(f"Database error: {e}")
        db.rollback()
        raise
    except Exception as e:
        logger.error(f"Unexpected error in database session: {e}")
        db.rollback()
        raise
    finally:
        db.close()

def check_database_health() -> dict:
    """
    Check database connectivity and health.
    Returns health status with detailed information.
    """
    try:
        with engine.connect() as connection:
            # Test basic connectivity
            result = connection.execute(text("SELECT 1 as health_check"))
            health_check = result.fetchone()
            
            # Get database info
            db_info = connection.execute(text("SELECT version() as version"))
            version = db_info.fetchone()
            
            # Check connection pool status
            pool_status = {
                "pool_size": engine.pool.size(),
                "checked_in": engine.pool.checkedin(),
                "checked_out": engine.pool.checkedout(),
                "overflow": engine.pool.overflow()
            }
            
            return {
                "status": "healthy",
                "message": "Database connection successful",
                "health_check": health_check[0] if health_check else None,
                "version": version[0] if version else "Unknown",
                "pool_status": pool_status,
                "database_url": DATABASE_URL.split("@")[1] if "@" in DATABASE_URL else "Hidden"
            }
    except OperationalError as e:
        logger.error(f"Database connection failed: {e}")
        return {
            "status": "unhealthy",
            "message": f"Database connection failed: {str(e)}",
            "error_type": "OperationalError",
            "database_url": DATABASE_URL.split("@")[1] if "@" in DATABASE_URL else "Hidden"
        }
    except Exception as e:
        logger.error(f"Unexpected database error: {e}")
        return {
            "status": "unhealthy",
            "message": f"Unexpected database error: {str(e)}",
            "error_type": type(e).__name__,
            "database_url": DATABASE_URL.split("@")[1] if "@" in DATABASE_URL else "Hidden"
        }

def init_database() -> bool:
    """
    Initialize database tables.
    Creates all tables defined in models.
    """
    try:
        # Import models to ensure they're registered with Base
        import models
        
        # Create all tables
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        logger.error(traceback.format_exc())
        return False

def get_database_stats() -> dict:
    """
    Get database statistics and performance metrics.
    """
    try:
        with engine.connect() as connection:
            # Get table counts
            tables = ['users', 'cloud_sessions', 'session_data', 'export_requests']
            table_counts = {}
            
            for table in tables:
                try:
                    result = connection.execute(text(f"SELECT COUNT(*) FROM {table}"))
                    count = result.fetchone()
                    table_counts[table] = count[0] if count else 0
                except Exception:
                    table_counts[table] = 0
            
            # Get database size
            size_result = connection.execute(text("""
                SELECT pg_size_pretty(pg_database_size(current_database())) as db_size
            """))
            db_size = size_result.fetchone()
            
            return {
                "table_counts": table_counts,
                "database_size": db_size[0] if db_size else "Unknown",
                "connection_pool": {
                    "size": engine.pool.size(),
                    "checked_in": engine.pool.checkedin(),
                    "checked_out": engine.pool.checkedout(),
                    "overflow": engine.pool.overflow()
                }
            }
    except Exception as e:
        logger.error(f"Failed to get database stats: {e}")
        return {"error": str(e)}

# Database session context manager for manual operations
class DatabaseSession:
    """Context manager for database sessions."""
    
    def __init__(self):
        self.db: Optional[Session] = None
    
    def __enter__(self) -> Session:
        self.db = SessionLocal()
        return self.db
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.db:
            if exc_type is not None:
                self.db.rollback()
            else:
                self.db.commit()
            self.db.close()

# Export for use in other modules
__all__ = [
    "engine", 
    "SessionLocal", 
    "Base", 
    "get_db", 
    "check_database_health", 
    "init_database", 
    "get_database_stats",
    "DatabaseSession"
]
