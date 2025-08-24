# Database System Documentation

## Overview

The database system provides a robust local-first storage solution for the Eye Tracker application. It automatically creates sessions when the app launches and logs blink data in real-time, ensuring no data is ever lost even in offline scenarios.

## Features

### ✅ Auto-Session Creation
- Sessions are automatically created when the app launches
- No manual intervention required
- Ensures continuous data collection

### ✅ Real-Time Blink Logging
- Blink data is logged immediately when detected
- Background batch processing for optimal performance
- Minimal latency for real-time tracking

### ✅ Performance Monitoring
- System metrics (CPU, memory, battery) are logged
- Performance data is associated with sessions
- Helps identify system impact

### ✅ Efficient Storage
- SQLite database with proper indexing
- WAL mode for better concurrency
- Automatic cleanup of old data
- Small database size (typically < 1MB)

### ✅ Session Management
- Multiple sessions support
- Session history and statistics
- Proper session start/end tracking

## Database Schema

### Tables

#### `local_sessions`
Stores session information and metadata.

```sql
CREATE TABLE local_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    end_time DATETIME NULL,
    total_blinks INTEGER DEFAULT 0,
    max_blink_rate REAL DEFAULT 0,
    avg_blink_rate REAL DEFAULT 0,
    session_duration INTEGER DEFAULT 0,
    is_synced BOOLEAN DEFAULT FALSE,
    cloud_session_id TEXT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### `blink_data`
Stores individual blink events with timestamps.

```sql
CREATE TABLE blink_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    blink_count INTEGER NOT NULL,
    blink_rate REAL NOT NULL,
    eye_aspect_ratio REAL,
    is_synced BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (session_id) REFERENCES local_sessions(id) ON DELETE CASCADE
);
```

#### `performance_logs`
Stores system performance metrics.

```sql
CREATE TABLE performance_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    cpu_usage REAL,
    memory_usage REAL,
    battery_level INTEGER,
    FOREIGN KEY (session_id) REFERENCES local_sessions(id) ON DELETE CASCADE
);
```

#### `sync_queue`
Stores pending sync operations for cloud integration.

```sql
CREATE TABLE sync_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name TEXT NOT NULL,
    record_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    data TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    synced_at DATETIME NULL
);
```

## Usage

### Basic Usage

```python
from desktop.database import SQLiteManager

# Initialize database manager
db_manager = SQLiteManager("eye_tracker.db")

# Auto-create session (happens automatically on app launch)
session_id = db_manager.auto_create_session()

# Log blink data in real-time
db_manager.log_blink(blink_count=5, blink_rate=12.5, eye_aspect_ratio=0.21)

# Log performance data
db_manager.log_performance(cpu_usage=25.5, memory_usage=150.2, battery_level=85)

# End session when app closes
ended_session = db_manager.end_current_session()
```

### Session Management

```python
# Get current session
current_session = db_manager.get_current_session()

# Get session statistics
stats = db_manager.get_session_stats(session_id)

# Get recent sessions
recent_sessions = db_manager.get_recent_sessions(limit=10)
```

### Data Cleanup

```python
# Clean up old data (keeps last 30 days by default)
db_manager.cleanup_old_data(days_to_keep=30)

# Get database size
db_size = db_manager.get_database_size()
```

## Integration with Main Application

The database system is integrated into the main application through:

1. **MainWindow**: Initializes database manager and auto-creates sessions
2. **EyeTracker**: Logs blink data when blinks are detected
3. **SystemMonitor**: Logs performance metrics
4. **Session Management**: Handles session start/end and statistics

### Key Integration Points

```python
# In MainWindow.__init__()
self.db_manager = SQLiteManager()
self.auto_create_session()

# In update_blink_stats()
if self.db_manager and self.is_tracking:
    self.db_manager.log_blink(count, rate)

# In update_performance_stats()
if self.db_manager and self.is_tracking:
    self.db_manager.log_performance(cpu, memory, battery)

# In quit_application()
if self.db_manager:
    ended_session = self.db_manager.end_current_session()
    self.db_manager.close()
```

## Performance Optimizations

### Batch Processing
- Blink data is processed in batches (50 records) for efficiency
- Background thread handles database writes
- Non-blocking queue for real-time logging

### Database Optimizations
- WAL mode for better concurrency
- Proper indexing on frequently queried columns
- Connection pooling and reuse
- Memory-based temporary storage

### Storage Efficiency
- Automatic cleanup of old data
- Compressed storage format
- Minimal metadata overhead

## Testing

Run the test suite to verify database functionality:

```bash
python test_database.py
```

Verify database contents:

```bash
python verify_database.py
```

## Database Location

The database file is stored in the application directory:
- **Default**: `eye_tracker.db`
- **Test**: `test_eye_tracker.db`

## Error Handling

The database system includes comprehensive error handling:

- Connection failures are logged and retried
- Data corruption is prevented with transactions
- Graceful degradation when database is unavailable
- Automatic recovery from common issues

## Monitoring

Database health can be monitored through:

- Database size tracking
- Session count and statistics
- Performance metrics
- Error logging

## Future Enhancements

- Cloud synchronization support
- Data export functionality
- Advanced analytics
- Multi-user support
- Backup and restore capabilities

## Troubleshooting

### Common Issues

1. **Database locked**: Ensure only one instance is accessing the database
2. **Large database size**: Run cleanup to remove old data
3. **Performance issues**: Check if indexes are properly created
4. **Data loss**: Verify WAL mode is enabled for crash recovery

### Debug Mode

Enable debug logging to troubleshoot issues:

```python
import logging
logging.getLogger('database').setLevel(logging.DEBUG)
```

## Security Considerations

- Database file should be stored in user's home directory
- No sensitive data is stored in plain text
- Access is restricted to the application process
- Regular backups recommended for data protection
