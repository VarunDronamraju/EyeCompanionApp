#!/usr/bin/env python3
"""
Check Last Session in SQLite Database
"""

import sys
import os
import sqlite3
from datetime import datetime

# Add the desktop directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'desktop'))

def check_last_session():
    """Check the last session in the database"""
    print("🔍 Checking Last Session in Database")
    print("=" * 50)
    
    # Check for database files
    db_files = ["eye_tracker.db", "test_eye_tracker.db"]
    db_found = None
    
    for db_file in db_files:
        if os.path.exists(db_file):
            db_found = db_file
            break
    
    if not db_found:
        print("❌ No database file found")
        return
    
    print(f"📁 Found database: {db_found}")
    
    # Connect to database
    conn = sqlite3.connect(db_found)
    conn.row_factory = sqlite3.Row
    
    try:
        # Get the last session
        cursor = conn.execute("""
            SELECT * FROM local_sessions 
            ORDER BY start_time DESC 
            LIMIT 1
        """)
        
        last_session = cursor.fetchone()
        
        if last_session:
            print(f"\n📊 LAST SESSION:")
            print("-" * 30)
            print(f"Session ID: {last_session['id']}")
            
            # Show user information if available
            user_id = last_session['user_id'] if 'user_id' in last_session.keys() else None
            user_email = last_session['user_email'] if 'user_email' in last_session.keys() else None
            
            if user_id:
                print(f"User ID: {user_id}")
                print(f"User Email: {user_email or 'N/A'}")
                print(f"Authentication: 🔐 Authenticated User")
            else:
                print(f"User ID: None")
                print(f"User Email: None")
                print(f"Authentication: 🔐 Authentication Required")
            
            print(f"Start Time: {last_session['start_time']}")
            print(f"End Time: {last_session['end_time']}")
            print(f"Duration: {last_session['session_duration']} seconds")
            print(f"Total Blinks: {last_session['total_blinks']}")
            print(f"Avg Blink Rate: {last_session['avg_blink_rate']:.1f}/min")
            print(f"Max Blink Rate: {last_session['max_blink_rate']:.1f}/min")
            print(f"Status: {'Active' if last_session['end_time'] is None else 'Completed'}")
            print(f"Synced: {last_session['is_synced']}")
            
            # Get blink data for this session
            cursor = conn.execute("""
                SELECT COUNT(*) as blink_count, 
                       MIN(timestamp) as first_blink,
                       MAX(timestamp) as last_blink
                FROM blink_data 
                WHERE session_id = ?
            """, (last_session['id'],))
            
            blink_info = cursor.fetchone()
            if blink_info:
                print(f"\n👁️ BLINK DATA:")
                print(f"Total Blink Records: {blink_info['blink_count']}")
                print(f"First Blink: {blink_info['first_blink']}")
                print(f"Last Blink: {blink_info['last_blink']}")
            
            # Get performance data for this session
            cursor = conn.execute("""
                SELECT COUNT(*) as perf_count,
                       AVG(cpu_usage) as avg_cpu,
                       AVG(memory_usage) as avg_memory
                FROM performance_logs 
                WHERE session_id = ?
            """, (last_session['id'],))
            
            perf_info = cursor.fetchone()
            if perf_info:
                print(f"\n⚡ PERFORMANCE DATA:")
                print(f"Performance Records: {perf_info['perf_count']}")
                if perf_info['avg_cpu']:
                    print(f"Avg CPU: {perf_info['avg_cpu']:.1f}%")
                if perf_info['avg_memory']:
                    print(f"Avg Memory: {perf_info['avg_memory']:.1f}MB")
            
        else:
            print("❌ No sessions found in database")
        
        # Show all sessions summary
        cursor = conn.execute("SELECT COUNT(*) as total FROM local_sessions")
        total_sessions = cursor.fetchone()['total']
        
        cursor = conn.execute("SELECT COUNT(*) as total FROM blink_data")
        total_blinks = cursor.fetchone()['total']
        
        cursor = conn.execute("SELECT COUNT(*) as total FROM performance_logs")
        total_perf = cursor.fetchone()['total']
        
        print(f"\n📈 DATABASE SUMMARY:")
        print("-" * 30)
        print(f"Total Sessions: {total_sessions}")
        print(f"Total Blink Records: {total_blinks}")
        print(f"Total Performance Records: {total_perf}")
        
        # Database size
        db_size = os.path.getsize(db_found)
        db_size_mb = db_size / (1024 * 1024)
        print(f"Database Size: {db_size_mb:.2f} MB")
        
    except Exception as e:
        print(f"❌ Error checking database: {e}")
    
    finally:
        conn.close()

if __name__ == "__main__":
    check_last_session()