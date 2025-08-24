import os
import time
import logging
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.openapi.utils import get_openapi
import uvicorn

# Import local modules
from database import check_database_health, init_database, get_database_stats
from models import HealthResponse, ErrorResponse
from routes import auth_router, sessions_router, sync_router, export_router, ROUTER_METADATA

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Application metadata
APP_NAME = "Wellness at Work API"
APP_VERSION = "1.0.0"
APP_DESCRIPTION = """
# Wellness at Work API

A robust FastAPI backend for the Wellness at Work eye tracking application.

## Features

- **Authentication**: Google OAuth with AWS Cognito integration
- **Session Management**: Cloud session tracking and management
- **Data Synchronization**: Real-time sync between desktop and cloud
- **Data Export**: CSV, JSON, and PDF export functionality
- **Health Monitoring**: Comprehensive health checks and monitoring
- **Rate Limiting**: Built-in rate limiting for API protection
- **Documentation**: Auto-generated OpenAPI documentation

## API Endpoints

- `/auth/*` - Authentication and user management
- `/sessions/*` - Session tracking and management  
- `/sync/*` - Data synchronization
- `/export/*` - Data export functionality
- `/health` - Health checks and monitoring
- `/docs` - Interactive API documentation

## Authentication

This API uses Google OAuth with AWS Cognito for secure authentication.
All protected endpoints require a valid JWT token in the Authorization header.
"""

# Global variables for application state
app_start_time = None
request_count = 0

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown events."""
    global app_start_time
    
    # Startup
    logger.info("Starting Wellness at Work API...")
    app_start_time = time.time()
    
    # Initialize database
    logger.info("Initializing database...")
    try:
        if not init_database():
            logger.warning("Failed to initialize database - continuing in development mode")
        else:
            # Check database health
            health_status = check_database_health()
            if health_status["status"] != "healthy":
                logger.warning(f"Database health check failed: {health_status} - continuing in development mode")
    except Exception as e:
        logger.warning(f"Database connection failed: {e} - continuing in development mode")
    
    logger.info("Wellness at Work API started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Wellness at Work API...")
    logger.info(f"Total requests processed: {request_count}")

# Create FastAPI application
app = FastAPI(
    title=APP_NAME,
    description=APP_DESCRIPTION,
    version=APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan
)

# ============================================================================
# MIDDLEWARE CONFIGURATION
# ============================================================================

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # Streamlit dashboard
        "http://localhost:8000",  # FastAPI docs
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000",
        # Add production domains here
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Trusted host middleware
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=[
        "localhost",
        "127.0.0.1",
        "*.amazonaws.com",  # AWS domains
        # Add production domains here
    ]
)

# ============================================================================
# REQUEST MIDDLEWARE
# ============================================================================

@app.middleware("http")
async def request_middleware(request: Request, call_next):
    """Middleware for request logging and monitoring."""
    global request_count
    
    # Increment request counter
    request_count += 1
    
    # Log request
    start_time = time.time()
    logger.info(f"Request {request_count}: {request.method} {request.url.path}")
    
    # Process request
    try:
        response = await call_next(request)
        
        # Log response
        process_time = time.time() - start_time
        logger.info(f"Request {request_count} completed in {process_time:.3f}s - Status: {response.status_code}")
        
        # Add custom headers
        response.headers["X-Process-Time"] = str(process_time)
        response.headers["X-Request-ID"] = str(request_count)
        
        return response
        
    except Exception as e:
        # Log error
        process_time = time.time() - start_time
        logger.error(f"Request {request_count} failed after {process_time:.3f}s: {str(e)}")
        raise

# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions with consistent error response format."""
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=exc.detail,
            error_code=f"HTTP_{exc.status_code}",
            timestamp=datetime.utcnow()
        ).dict()
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions with consistent error response format."""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error="Internal server error",
            detail=str(exc) if app.debug else "An unexpected error occurred",
            error_code="INTERNAL_ERROR",
            timestamp=datetime.utcnow()
        ).dict()
    )

# ============================================================================
# HEALTH CHECK ENDPOINTS
# ============================================================================

@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["Health"],
    summary="Health Check",
    description="Check the health status of the API and database"
)
async def health_check():
    """Comprehensive health check endpoint."""
    global app_start_time
    
    # Check database health
    db_health = check_database_health()
    
    # Calculate uptime
    uptime = time.time() - app_start_time if app_start_time else 0
    
    # Determine overall status
    overall_status = "healthy" if db_health["status"] == "healthy" else "unhealthy"
    
    return HealthResponse(
        status=overall_status,
        timestamp=datetime.utcnow(),
        database=db_health,
        api_version=APP_VERSION,
        uptime=uptime
    )

@app.get(
    "/health/database",
    tags=["Health"],
    summary="Database Health Check",
    description="Check database connectivity and performance"
)
async def database_health():
    """Database-specific health check."""
    return check_database_health()

@app.get(
    "/health/stats",
    tags=["Health"],
    summary="API Statistics",
    description="Get API usage statistics and performance metrics"
)
async def api_stats():
    """Get API statistics and performance metrics."""
    global request_count, app_start_time
    
    uptime = time.time() - app_start_time if app_start_time else 0
    db_stats = get_database_stats()
    
    return {
        "requests_total": request_count,
        "uptime_seconds": uptime,
        "requests_per_second": request_count / uptime if uptime > 0 else 0,
        "database_stats": db_stats,
        "timestamp": datetime.utcnow().isoformat()
    }

# ============================================================================
# API DOCUMENTATION CUSTOMIZATION
# ============================================================================

def custom_openapi():
    """Customize OpenAPI schema for better documentation."""
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title=APP_NAME,
        version=APP_VERSION,
        description=APP_DESCRIPTION,
        routes=app.routes,
    )
    
    # Add security schemes
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "JWT token from Google OAuth authentication"
        }
    }
    
    # Add server information
    openapi_schema["servers"] = [
        {
            "url": "http://localhost:8000",
            "description": "Development server"
        },
        {
            "url": "https://api.wellnessatwork.com",
            "description": "Production server"
        }
    ]
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

# ============================================================================
# ROUTE REGISTRATION
# ============================================================================

# Register all route modules
app.include_router(
    auth_router,
    prefix=ROUTER_METADATA["auth"]["prefix"],
    tags=ROUTER_METADATA["auth"]["tags"]
)

app.include_router(
    sessions_router,
    prefix=ROUTER_METADATA["sessions"]["prefix"],
    tags=ROUTER_METADATA["sessions"]["tags"]
)

app.include_router(
    sync_router,
    prefix=ROUTER_METADATA["sync"]["prefix"],
    tags=ROUTER_METADATA["sync"]["tags"]
)

app.include_router(
    export_router,
    prefix=ROUTER_METADATA["export"]["prefix"],
    tags=ROUTER_METADATA["export"]["tags"]
)

# ============================================================================
# ROOT ENDPOINT
# ============================================================================

@app.get(
    "/",
    tags=["Root"],
    summary="API Root",
    description="Welcome endpoint with API information"
)
async def root():
    """Root endpoint with API information."""
    return {
        "message": "Welcome to Wellness at Work API",
        "version": APP_VERSION,
        "status": "running",
        "timestamp": datetime.utcnow().isoformat(),
        "documentation": "/docs",
        "health_check": "/health"
    }

# ============================================================================
# DEVELOPMENT SERVER
# ============================================================================

if __name__ == "__main__":
    # Development server configuration
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
        access_log=True
    )
