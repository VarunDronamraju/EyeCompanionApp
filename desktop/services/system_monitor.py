"""
System Performance Monitor Service

A lightweight system monitoring service that tracks CPU, memory, and battery usage
to ensure the wellness app runs efficiently without impacting work productivity.

Features:
- Real-time CPU, memory, and battery monitoring
- Cross-platform compatibility (Windows/macOS/Linux)
- Minimal overhead (< 1% CPU usage)
- 2-second update intervals
- System health alerts
- Performance data logging
- Thread-safe operations
"""

import psutil
import threading
import time
import logging
import platform
from typing import Dict, Optional, Callable
from dataclasses import dataclass
from datetime import datetime
import sqlite3
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class SystemMetrics:
    """Data class for system performance metrics"""
    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    memory_total_mb: float
    battery_percent: Optional[int]
    battery_plugged: Optional[bool]
    disk_usage_percent: float
    network_sent_mb: float
    network_recv_mb: float
    is_charging: Optional[bool] = None


@dataclass
class SystemAlert:
    """Data class for system health alerts"""
    timestamp: datetime
    alert_type: str  # 'high_cpu', 'high_memory', 'low_battery', 'performance_impact'
    severity: str    # 'warning', 'critical'
    message: str
    metrics: SystemMetrics


class SystemMonitor:
    """
    Comprehensive system monitoring service with minimal overhead.
    
    Updates every 2 seconds and provides real-time performance metrics
    to ensure the wellness app runs efficiently.
    """
    
    def __init__(self, db_path: str = "eye_tracker.db", update_interval: float = 2.0):
        """
        Initialize the system monitor.
        
        Args:
            db_path: Path to SQLite database for logging metrics
            update_interval: Update interval in seconds (default: 2.0)
        """
        self.db_path = db_path
        self.update_interval = update_interval
        self.is_running = False
        self.monitor_thread = None
        self.lock = threading.Lock()
        
        # Performance thresholds
        self.cpu_threshold = 80.0  # Alert if CPU > 80%
        self.memory_threshold = 85.0  # Alert if memory > 85%
        self.battery_threshold = 20  # Alert if battery < 20%
        
        # Current metrics
        self.current_metrics: Optional[SystemMetrics] = None
        self.last_network_stats = None
        
        # Alert callbacks
        self.alert_callbacks: list[Callable[[SystemAlert], None]] = []
        
        # Performance tracking
        self.start_time = None
        self.monitor_overhead = 0.0
        
        # Initialize database
        self._init_database()
        
        logger.info(f"SystemMonitor initialized for {platform.system()} platform")
    
    def _init_database(self):
        """Initialize database tables for performance logging"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Check if performance_logs table exists
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='performance_logs'
                """)
                table_exists = cursor.fetchone() is not None
                
                if not table_exists:
                    # Create performance_logs table if it doesn't exist
                    cursor.execute("""
                        CREATE TABLE performance_logs (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            session_id INTEGER NULL,
                            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                            cpu_usage REAL,
                            memory_usage REAL,
                            memory_used_mb REAL,
                            memory_total_mb REAL,
                            battery_level INTEGER,
                            battery_plugged BOOLEAN,
                            disk_usage_percent REAL,
                            network_sent_mb REAL,
                            network_recv_mb REAL,
                            is_charging BOOLEAN,
                            monitor_overhead REAL
                        )
                    """)
                else:
                    # Check if session_id has NOT NULL constraint and fix it
                    cursor.execute("PRAGMA table_info(performance_logs)")
                    columns = cursor.fetchall()
                    session_id_info = next((col for col in columns if col[1] == 'session_id'), None)
                    
                    if session_id_info and session_id_info[3] == 1:  # NOT NULL constraint
                        # Create new table with correct schema
                        cursor.execute("""
                            CREATE TABLE performance_logs_new (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                session_id INTEGER NULL,
                                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                                cpu_usage REAL,
                                memory_usage REAL,
                                memory_used_mb REAL,
                                memory_total_mb REAL,
                                battery_level INTEGER,
                                battery_plugged BOOLEAN,
                                disk_usage_percent REAL,
                                network_sent_mb REAL,
                                network_recv_mb REAL,
                                is_charging BOOLEAN,
                                monitor_overhead REAL
                            )
                        """)
                        
                        # Copy data from old table
                        cursor.execute("""
                            INSERT INTO performance_logs_new 
                            SELECT id, session_id, timestamp, cpu_usage, memory_usage,
                                   NULL, NULL, battery_level, NULL, NULL, NULL, NULL, NULL, NULL
                            FROM performance_logs
                        """)
                        
                        # Drop old table and rename new one
                        cursor.execute("DROP TABLE performance_logs")
                        cursor.execute("ALTER TABLE performance_logs_new RENAME TO performance_logs")
                        logger.info("Updated performance_logs table schema")
                    
                    # Add missing columns to existing table
                    try:
                        cursor.execute("ALTER TABLE performance_logs ADD COLUMN memory_used_mb REAL")
                    except sqlite3.OperationalError:
                        pass  # Column already exists
                    
                    try:
                        cursor.execute("ALTER TABLE performance_logs ADD COLUMN memory_total_mb REAL")
                    except sqlite3.OperationalError:
                        pass  # Column already exists
                    
                    try:
                        cursor.execute("ALTER TABLE performance_logs ADD COLUMN battery_plugged BOOLEAN")
                    except sqlite3.OperationalError:
                        pass  # Column already exists
                    
                    try:
                        cursor.execute("ALTER TABLE performance_logs ADD COLUMN disk_usage_percent REAL")
                    except sqlite3.OperationalError:
                        pass  # Column already exists
                    
                    try:
                        cursor.execute("ALTER TABLE performance_logs ADD COLUMN network_sent_mb REAL")
                    except sqlite3.OperationalError:
                        pass  # Column already exists
                    
                    try:
                        cursor.execute("ALTER TABLE performance_logs ADD COLUMN network_recv_mb REAL")
                    except sqlite3.OperationalError:
                        pass  # Column already exists
                    
                    try:
                        cursor.execute("ALTER TABLE performance_logs ADD COLUMN is_charging BOOLEAN")
                    except sqlite3.OperationalError:
                        pass  # Column already exists
                    
                    try:
                        cursor.execute("ALTER TABLE performance_logs ADD COLUMN monitor_overhead REAL")
                    except sqlite3.OperationalError:
                        pass  # Column already exists
                
                # Create system_alerts table if it doesn't exist
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS system_alerts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                        alert_type TEXT NOT NULL,
                        severity TEXT NOT NULL,
                        message TEXT NOT NULL,
                        cpu_usage REAL,
                        memory_usage REAL,
                        battery_level INTEGER
                    )
                """)
                
                conn.commit()
                logger.info("Database tables initialized successfully")
                
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
    
    def start_monitoring(self, session_id: Optional[int] = None):
        """
        Start the system monitoring service.
        
        Args:
            session_id: Optional session ID for database logging
        """
        if self.is_running:
            logger.warning("System monitoring is already running")
            return
        
        self.is_running = True
        self.start_time = time.time()
        self.session_id = session_id
        
        # Initialize network stats baseline
        self.last_network_stats = psutil.net_io_counters()
        
        # Start monitoring thread
        self.monitor_thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="SystemMonitor"
        )
        self.monitor_thread.start()
        
        logger.info(f"System monitoring started (interval: {self.update_interval}s)")
    
    def stop_monitoring(self):
        """Stop the system monitoring service."""
        if not self.is_running:
            return
        
        self.is_running = False
        
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=5.0)
        
        # Calculate final overhead
        if self.start_time:
            total_time = time.time() - self.start_time
            logger.info(f"System monitoring stopped. Total runtime: {total_time:.2f}s")
        
        logger.info("System monitoring stopped")
    
    def _monitor_loop(self):
        """Main monitoring loop that runs in a separate thread."""
        while self.is_running:
            try:
                loop_start = time.time()
                
                # Collect system metrics
                metrics = self._collect_metrics()
                
                # Update current metrics
                with self.lock:
                    self.current_metrics = metrics
                
                # Check for alerts
                self._check_alerts(metrics)
                
                # Log metrics to database
                self._log_metrics(metrics)
                
                # Calculate overhead
                loop_time = time.time() - loop_start
                self.monitor_overhead = (loop_time / self.update_interval) * 100
                
                # Sleep for remaining time
                sleep_time = max(0, self.update_interval - loop_time)
                if sleep_time > 0:
                    time.sleep(sleep_time)
                    
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                time.sleep(self.update_interval)
    
    def _collect_metrics(self) -> SystemMetrics:
        """Collect current system metrics."""
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=0.1)
            
            # Memory usage
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            memory_used_mb = memory.used / (1024 * 1024)
            memory_total_mb = memory.total / (1024 * 1024)
            
            # Battery information
            battery_percent = None
            battery_plugged = None
            is_charging = None
            
            if hasattr(psutil, 'sensors_battery'):
                battery = psutil.sensors_battery()
                if battery:
                    battery_percent = battery.percent
                    battery_plugged = battery.power_plugged
                    is_charging = battery.power_plugged
            
            # Disk usage
            disk_usage = psutil.disk_usage('/')
            disk_usage_percent = disk_usage.percent
            
            # Network usage (delta from last measurement)
            network_sent_mb = 0.0
            network_recv_mb = 0.0
            
            current_network = psutil.net_io_counters()
            if self.last_network_stats:
                sent_delta = current_network.bytes_sent - self.last_network_stats.bytes_sent
                recv_delta = current_network.bytes_recv - self.last_network_stats.bytes_recv
                network_sent_mb = sent_delta / (1024 * 1024)
                network_recv_mb = recv_delta / (1024 * 1024)
            
            self.last_network_stats = current_network
            
            return SystemMetrics(
                timestamp=datetime.now(),
                cpu_percent=cpu_percent,
                memory_percent=memory_percent,
                memory_used_mb=memory_used_mb,
                memory_total_mb=memory_total_mb,
                battery_percent=battery_percent,
                battery_plugged=battery_plugged,
                disk_usage_percent=disk_usage_percent,
                network_sent_mb=network_sent_mb,
                network_recv_mb=network_recv_mb,
                is_charging=is_charging
            )
            
        except Exception as e:
            logger.error(f"Error collecting metrics: {e}")
            # Return default metrics on error
            return SystemMetrics(
                timestamp=datetime.now(),
                cpu_percent=0.0,
                memory_percent=0.0,
                memory_used_mb=0.0,
                memory_total_mb=0.0,
                battery_percent=None,
                battery_plugged=None,
                disk_usage_percent=0.0,
                network_sent_mb=0.0,
                network_recv_mb=0.0
            )
    
    def _check_alerts(self, metrics: SystemMetrics):
        """Check for system health alerts."""
        alerts = []
        
        # High CPU usage
        if metrics.cpu_percent > self.cpu_threshold:
            alerts.append(SystemAlert(
                timestamp=metrics.timestamp,
                alert_type='high_cpu',
                severity='warning' if metrics.cpu_percent < 90 else 'critical',
                message=f"High CPU usage: {metrics.cpu_percent:.1f}%",
                metrics=metrics
            ))
        
        # High memory usage
        if metrics.memory_percent > self.memory_threshold:
            alerts.append(SystemAlert(
                timestamp=metrics.timestamp,
                alert_type='high_memory',
                severity='warning' if metrics.memory_percent < 95 else 'critical',
                message=f"High memory usage: {metrics.memory_percent:.1f}%",
                metrics=metrics
            ))
        
        # Low battery
        if metrics.battery_percent is not None and metrics.battery_percent < self.battery_threshold:
            alerts.append(SystemAlert(
                timestamp=metrics.timestamp,
                alert_type='low_battery',
                severity='warning' if metrics.battery_percent > 10 else 'critical',
                message=f"Low battery: {metrics.battery_percent}%",
                metrics=metrics
            ))
        
        # Monitor overhead alert
        if self.monitor_overhead > 1.0:
            alerts.append(SystemAlert(
                timestamp=metrics.timestamp,
                alert_type='performance_impact',
                severity='warning',
                message=f"Monitor overhead: {self.monitor_overhead:.2f}%",
                metrics=metrics
            ))
        
        # Log and trigger alerts
        for alert in alerts:
            self._log_alert(alert)
            self._trigger_alert_callbacks(alert)
    
    def _log_metrics(self, metrics: SystemMetrics):
        """Log metrics to database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO performance_logs (
                        session_id, timestamp, cpu_usage, memory_usage,
                        memory_used_mb, memory_total_mb, battery_level,
                        battery_plugged, disk_usage_percent, network_sent_mb,
                        network_recv_mb, is_charging, monitor_overhead
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    self.session_id, metrics.timestamp, metrics.cpu_percent,
                    metrics.memory_percent, metrics.memory_used_mb,
                    metrics.memory_total_mb, metrics.battery_percent,
                    metrics.battery_plugged, metrics.disk_usage_percent,
                    metrics.network_sent_mb, metrics.network_recv_mb,
                    metrics.is_charging, self.monitor_overhead
                ))
                conn.commit()
                
        except Exception as e:
            logger.error(f"Failed to log metrics: {e}")
    
    def _log_alert(self, alert: SystemAlert):
        """Log alert to database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO system_alerts (
                        timestamp, alert_type, severity, message,
                        cpu_usage, memory_usage, battery_level
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    alert.timestamp, alert.alert_type, alert.severity,
                    alert.message, alert.metrics.cpu_percent,
                    alert.metrics.memory_percent, alert.metrics.battery_percent
                ))
                conn.commit()
                
        except Exception as e:
            logger.error(f"Failed to log alert: {e}")
    
    def _trigger_alert_callbacks(self, alert: SystemAlert):
        """Trigger registered alert callbacks."""
        for callback in self.alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                logger.error(f"Error in alert callback: {e}")
    
    def get_current_metrics(self) -> Optional[SystemMetrics]:
        """Get current system metrics (thread-safe)."""
        with self.lock:
            return self.current_metrics
    
    def get_performance_summary(self) -> Dict:
        """Get a summary of current performance metrics."""
        metrics = self.get_current_metrics()
        if not metrics:
            return {}
        
        return {
            'cpu_percent': metrics.cpu_percent,
            'memory_percent': metrics.memory_percent,
            'memory_used_mb': metrics.memory_used_mb,
            'memory_total_mb': metrics.memory_total_mb,
            'battery_percent': metrics.battery_percent,
            'battery_plugged': metrics.battery_plugged,
            'disk_usage_percent': metrics.disk_usage_percent,
            'network_sent_mb': metrics.network_sent_mb,
            'network_recv_mb': metrics.network_recv_mb,
            'is_charging': metrics.is_charging,
            'monitor_overhead': self.monitor_overhead,
            'timestamp': metrics.timestamp.isoformat()
        }
    
    def add_alert_callback(self, callback: Callable[[SystemAlert], None]):
        """Add a callback function for system alerts."""
        self.alert_callbacks.append(callback)
    
    def remove_alert_callback(self, callback: Callable[[SystemAlert], None]):
        """Remove a callback function for system alerts."""
        if callback in self.alert_callbacks:
            self.alert_callbacks.remove(callback)
    
    def set_thresholds(self, cpu: float = None, memory: float = None, battery: int = None):
        """Update alert thresholds."""
        if cpu is not None:
            self.cpu_threshold = cpu
        if memory is not None:
            self.memory_threshold = memory
        if battery is not None:
            self.battery_threshold = battery
        
        logger.info(f"Thresholds updated - CPU: {self.cpu_threshold}%, "
                   f"Memory: {self.memory_threshold}%, Battery: {self.battery_threshold}%")
    
    def get_system_info(self) -> Dict:
        """Get system information."""
        return {
            'platform': platform.system(),
            'platform_version': platform.version(),
            'processor': platform.processor(),
            'python_version': platform.python_version(),
            'psutil_version': psutil.__version__,
            'cpu_count': psutil.cpu_count(),
            'memory_total_gb': round(psutil.virtual_memory().total / (1024**3), 2),
            'disk_total_gb': round(psutil.disk_usage('/').total / (1024**3), 2)
        }
    
    def get_performance_history(self, hours: int = 24) -> list[Dict]:
        """Get performance history from database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT timestamp, cpu_usage, memory_usage, battery_level,
                           monitor_overhead
                    FROM performance_logs
                    WHERE timestamp >= datetime('now', '-{} hours')
                    ORDER BY timestamp DESC
                """.format(hours))
                
                rows = cursor.fetchall()
                return [
                    {
                        'timestamp': row[0],
                        'cpu_usage': row[1],
                        'memory_usage': row[2],
                        'battery_level': row[3],
                        'monitor_overhead': row[4]
                    }
                    for row in rows
                ]
                
        except Exception as e:
            logger.error(f"Failed to get performance history: {e}")
            return []
    
    def cleanup_old_data(self, days: int = 30):
        """Clean up old performance data from database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Delete old performance logs
                cursor.execute("""
                    DELETE FROM performance_logs
                    WHERE timestamp < datetime('now', '-{} days')
                """.format(days))
                
                # Delete old alerts
                cursor.execute("""
                    DELETE FROM system_alerts
                    WHERE timestamp < datetime('now', '-{} days')
                """.format(days))
                
                conn.commit()
                logger.info(f"Cleaned up data older than {days} days")
                
        except Exception as e:
            logger.error(f"Failed to cleanup old data: {e}")


# Convenience functions for quick access
def get_system_metrics() -> Optional[SystemMetrics]:
    """Get current system metrics without starting the monitor."""
    try:
        monitor = SystemMonitor()
        return monitor._collect_metrics()
    except Exception as e:
        logger.error(f"Failed to get system metrics: {e}")
        return None


def get_performance_summary() -> Dict:
    """Get a quick performance summary."""
    try:
        monitor = SystemMonitor()
        metrics = monitor._collect_metrics()
        return {
            'cpu_percent': metrics.cpu_percent,
            'memory_percent': metrics.memory_percent,
            'battery_percent': metrics.battery_percent,
            'battery_plugged': metrics.battery_plugged,
            'timestamp': metrics.timestamp.isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to get performance summary: {e}")
        return {}


if __name__ == "__main__":
    # Example usage and testing
    monitor = SystemMonitor()
    
    # Add alert callback
    def alert_handler(alert: SystemAlert):
        print(f"ALERT: {alert.severity.upper()} - {alert.message}")
    
    monitor.add_alert_callback(alert_handler)
    
    # Start monitoring
    monitor.start_monitoring()
    
    try:
        # Run for 30 seconds
        time.sleep(30)
        
        # Print summary
        print("Performance Summary:")
        print(monitor.get_performance_summary())
        
        print("\nSystem Info:")
        print(monitor.get_system_info())
        
    finally:
        monitor.stop_monitoring()
