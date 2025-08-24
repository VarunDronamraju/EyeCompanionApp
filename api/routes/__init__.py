"""
API Routes Module

This module contains all FastAPI route handlers for the Wellness at Work API.
Routes are organized by functionality and imported into the main FastAPI application.
"""

from .auth import router as auth_router
from .sessions import router as sessions_router
from .sync import router as sync_router
from .export import router as export_router

# Export all routers for easy import
__all__ = [
    "auth_router",
    "sessions_router", 
    "sync_router",
    "export_router"
]

# Router metadata for documentation
ROUTER_METADATA = {
    "auth": {
        "prefix": "/auth",
        "tags": ["Authentication"],
        "description": "User authentication and authorization endpoints"
    },
    "sessions": {
        "prefix": "/sessions", 
        "tags": ["Sessions"],
        "description": "Session management and tracking endpoints"
    },
    "sync": {
        "prefix": "/sync",
        "tags": ["Synchronization"],
        "description": "Data synchronization between local and cloud storage"
    },
    "export": {
        "prefix": "/export",
        "tags": ["Export"],
        "description": "Data export and download functionality"
    }
}
