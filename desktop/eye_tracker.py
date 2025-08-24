"""
Enhanced Eye Tracker - PyQt6 Integration
Transforms the original eye_blink.py into a threaded component for desktop application
"""

import cv2
import mediapipe as mp
import numpy as np
import json
import logging
from PyQt6.QtCore import QThread, Qt, pyqtSignal, QMutex, QTimer
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QLabel
from typing import Optional, Tuple

class EyeTracker(QThread):
    """
    Threaded eye tracking component with PyQt6 integration.
    Based on the original eye_blink.py with enhanced real-time capabilities.
    """
    
    # Signals for UI updates
    blink_detected = pyqtSignal(int, float)  # count, rate
    frame_updated = pyqtSignal(QPixmap)     # camera frame
    status_changed = pyqtSignal(str)        # tracking status
    error_occurred = pyqtSignal(str)        # error messages
    
    def __init__(self, camera_index: int = 0):
        super().__init__()
        self.camera_index = camera_index
        self.running = False
        self.paused = False
        
        # Eye tracking parameters (from original eye_blink.py)
        self.blink_count = 0
        self.blink_state = False
        self.EAR_THRESH = 0.21  # Threshold for blink detection
        self.CONSEC_FRAMES = 2  # Frames required to confirm a blink
        self.frame_counter = 0
        
        # MediaPipe initialization
        self.mp_face_mesh = mp.solutions.face_mesh
        self.mp_drawing = mp.solutions.drawing_utils
        
        # Eye landmark indices (from original eye_blink.py)
        self.LEFT_EYE = [33, 160, 158, 133, 153, 144]
        self.RIGHT_EYE = [362, 385, 387, 263, 373, 380]
        
        # Threading control
        self.mutex = QMutex()
        self.cap: Optional[cv2.VideoCapture] = None
        self.face_mesh: Optional[mp.solutions.face_mesh.FaceMesh] = None
        
        # Performance tracking
        self.session_start_time = None
        self.fps_counter = 0
        self.fps_timer = QTimer()
        self.fps_timer.timeout.connect(self._update_fps)
        self.current_fps = 0
        
        # Logging
        self.logger = logging.getLogger(__name__)
    
    def start_tracking(self):
        """Start eye tracking session"""
        self.mutex.lock()
        try:
            if not self.running:
                self.running = True
                self.session_start_time = np.datetime64('now')
                self.blink_count = 0
                self.frame_counter = 0
                self.status_changed.emit("Starting camera...")
                self.start()
                self.fps_timer.start(1000)  # Update FPS every second
                self.logger.info("Eye tracking started")
        finally:
            self.mutex.unlock()
    
    def stop_tracking(self):
        """Stop eye tracking session"""
        self.mutex.lock()
        try:
            self.running = False
            self.paused = False
            self.fps_timer.stop()
            self.status_changed.emit("Stopped")
            self.logger.info("Eye tracking stopped")
        finally:
            self.mutex.unlock()
    
    def pause_tracking(self):
        """Pause eye tracking"""
        self.mutex.lock()
        try:
            self.paused = True
            self.status_changed.emit("Paused")
            self.logger.info("Eye tracking paused")
        finally:
            self.mutex.unlock()
    
    def resume_tracking(self):
        """Resume eye tracking"""
        self.mutex.lock()
        try:
            self.paused = False
            self.status_changed.emit("Live Tracking")
            self.logger.info("Eye tracking resumed")
        finally:
            self.mutex.unlock()
    
    def reset_session(self):
        """Reset session data"""
        self.mutex.lock()
        try:
            self.blink_count = 0
            self.frame_counter = 0
            self.session_start_time = np.datetime64('now')
            self.logger.info("Session reset")
        finally:
            self.mutex.unlock()
    
    def get_session_stats(self) -> dict:
        """Get current session statistics"""
        self.mutex.lock()
        try:
            if self.session_start_time is None:
                return {
                    'blink_count': 0,
                    'blink_rate': 0.0,
                    'session_duration': 0,
                    'fps': self.current_fps
                }
            
            current_time = np.datetime64('now')
            elapsed_timedelta = current_time - self.session_start_time
            elapsed_seconds = elapsed_timedelta.astype('timedelta64[s]').astype(float)
            elapsed_minutes = elapsed_seconds / 60.0
            
            blink_rate = self.blink_count / elapsed_minutes if elapsed_minutes > 0 else 0.0
            
            return {
                'blink_count': self.blink_count,
                'blink_rate': round(blink_rate, 1),
                'session_duration': int(elapsed_seconds),
                'fps': self.current_fps
            }
        finally:
            self.mutex.unlock()
    
    def _initialize_camera(self) -> bool:
        """Initialize camera and MediaPipe face mesh"""
        try:
            # Initialize camera with optimized settings
            self.cap = cv2.VideoCapture(self.camera_index)
            if not self.cap.isOpened():
                self.error_occurred.emit("Camera not available")
                return False
            
            # Set camera properties for better performance and faster initialization
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self.cap.set(cv2.CAP_PROP_FPS, 30)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Reduce buffer size for lower latency
            
            # Initialize MediaPipe Face Mesh with optimized settings
            self.face_mesh = self.mp_face_mesh.FaceMesh(
                max_num_faces=1,
                refine_landmarks=False,  # Disable refinement for faster processing
                min_detection_confidence=0.3,  # Lower confidence for faster detection
                min_tracking_confidence=0.3
            )
            
            self.status_changed.emit("Camera initialized")
            return True
            
        except Exception as e:
            self.error_occurred.emit(f"Camera initialization failed: {str(e)}")
            self.logger.error(f"Camera initialization failed: {e}")
            return False
    
    def _cleanup_camera(self):
        """Clean up camera and MediaPipe resources"""
        try:
            if self.face_mesh:
                self.face_mesh.close()
                self.face_mesh = None
            
            if self.cap:
                self.cap.release()
                self.cap = None
                
        except Exception as e:
            self.logger.error(f"Camera cleanup error: {e}")
    
    def _euclidean_dist(self, pt1: Tuple[int, int], pt2: Tuple[int, int]) -> float:
        """Calculate Euclidean distance between two points"""
        return np.linalg.norm(np.array(pt1) - np.array(pt2))
    
    def _eye_aspect_ratio(self, eye_landmarks: list) -> float:
        """Compute the eye aspect ratio (EAR) - from original eye_blink.py"""
        A = self._euclidean_dist(eye_landmarks[1], eye_landmarks[5])
        B = self._euclidean_dist(eye_landmarks[2], eye_landmarks[4])
        C = self._euclidean_dist(eye_landmarks[0], eye_landmarks[3])
        ear = (A + B) / (2.0 * C)
        return ear
    
    def _process_frame(self, frame: np.ndarray) -> Tuple[np.ndarray, bool]:
        """Process a single frame for eye tracking"""
        try:
            # Convert BGR to RGB for MediaPipe (optimized)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.face_mesh.process(rgb)
            
            blink_detected = False
            
            if results.multi_face_landmarks:
                h, w, _ = frame.shape
                
                for face_landmarks in results.multi_face_landmarks:
                    # Get eye landmarks (optimized)
                    left_eye = [(int(face_landmarks.landmark[i].x * w), 
                                int(face_landmarks.landmark[i].y * h)) for i in self.LEFT_EYE]
                    right_eye = [(int(face_landmarks.landmark[i].x * w), 
                                 int(face_landmarks.landmark[i].y * h)) for i in self.RIGHT_EYE]
                    
                    # Draw eye landmarks (only if not paused for better performance)
                    if not self.paused:
                        for pt in left_eye + right_eye:
                            cv2.circle(frame, pt, 2, (0, 255, 0), -1)
                    
                    # Calculate EAR
                    left_ear = self._eye_aspect_ratio(left_eye)
                    right_ear = self._eye_aspect_ratio(right_eye)
                    ear = (left_ear + right_ear) / 2.0
                    
                    # Blink detection logic (from original eye_blink.py)
                    if ear < self.EAR_THRESH:
                        self.frame_counter += 1
                    else:
                        if self.frame_counter >= self.CONSEC_FRAMES:
                            self.blink_count += 1
                            blink_detected = True
                        self.frame_counter = 0
                    
                    # Draw detection overlay (only if not paused)
                    if not self.paused:
                        cv2.rectangle(frame, (left_eye[0][0] - 10, left_eye[0][1] - 10),
                                     (right_eye[3][0] + 10, right_eye[3][1] + 10),
                                     (0, 255, 0), 2)
            
            return frame, blink_detected
            
        except Exception as e:
            self.logger.error(f"Frame processing error: {e}")
            return frame, False
    
    def _cv_to_qpixmap(self, cv_image: np.ndarray) -> QPixmap:
        """Convert OpenCV image to QPixmap for PyQt6 display"""
        try:
            # Convert BGR to RGB
            rgb_image = cv2.cvtColor(cv_image, cv2.COLOR_BGR2RGB)
            
            # Convert to QImage
            h, w, ch = rgb_image.shape
            bytes_per_line = ch * w
            q_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
            
            # Convert to QPixmap and scale for display
            pixmap = QPixmap.fromImage(q_image)
            return pixmap.scaled(400, 300, Qt.AspectRatioMode.KeepAspectRatio, 
                               Qt.TransformationMode.SmoothTransformation)
            
        except Exception as e:
            self.logger.error(f"Image conversion error: {e}")
            # Return a blank pixmap on error
            return QPixmap(400, 300)
    
    def _update_fps(self):
        """Update FPS counter"""
        self.current_fps = self.fps_counter
        self.fps_counter = 0
    
    def run(self):
        """Main tracking loop - runs in separate thread"""
        if not self._initialize_camera():
            return
        
        self.status_changed.emit("Live Tracking")
        
        try:
            while self.running:
                if self.paused:
                    self.msleep(50)  # Faster response when paused
                    continue
                
                # Capture frame
                ret, frame = self.cap.read()
                if not ret:
                    self.error_occurred.emit("Failed to capture frame")
                    break
                
                # Process frame
                processed_frame, blink_detected = self._process_frame(frame)
                
                # Update FPS counter
                self.fps_counter += 1
                
                # Emit signals for UI updates
                if blink_detected:
                    # Log blink to terminal
                    self.logger.info(f"BLINK DETECTED! Total blinks: {self.blink_count}")
                    
                    # Emit blink count (rate will be calculated by main window timer)
                    self.blink_detected.emit(self.blink_count, 0.0)
                
                # Convert and emit frame
                pixmap = self._cv_to_qpixmap(processed_frame)
                self.frame_updated.emit(pixmap)
                
                # Optimized frame rate - reduced sleep for faster response
                self.msleep(25)  # ~40 FPS for better responsiveness
                
        except Exception as e:
            self.error_occurred.emit(f"Tracking error: {str(e)}")
            self.logger.error(f"Tracking error: {e}")
        
        finally:
            self._cleanup_camera()
            self.status_changed.emit("Stopped")
    
    def __del__(self):
        """Cleanup on destruction"""
        self.stop_tracking()
        self._cleanup_camera()
