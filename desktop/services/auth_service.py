"""
Authentication Service - Google OAuth with AWS Cognito Integration
Handles secure authentication, token management, and user session management
"""

import os
import json
import logging
import base64
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from urllib.parse import urlencode, parse_qs, urlparse
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import time

import requests
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from config import config

class TokenStorage:
    """Secure token storage with encryption"""
    
    def __init__(self, storage_path: str = None):
        self.storage_path = storage_path or os.path.join(
            os.path.expanduser("~"), ".wellness_at_work", "auth_tokens.json"
        )
        self.encryption_key = self._get_or_create_key()
        self.cipher = Fernet(self.encryption_key)
        self._ensure_storage_dir()
    
    def _get_or_create_key(self) -> bytes:
        """Get or create encryption key for token storage"""
        key_file = os.path.join(os.path.expanduser("~"), ".wellness_at_work", ".key")
        
        if os.path.exists(key_file):
            with open(key_file, 'rb') as f:
                return f.read()
        else:
            # Generate new key
            key = Fernet.generate_key()
            os.makedirs(os.path.dirname(key_file), exist_ok=True)
            with open(key_file, 'wb') as f:
                f.write(key)
            return key
    
    def _ensure_storage_dir(self):
        """Ensure storage directory exists"""
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
    
    def store_tokens(self, tokens: Dict[str, Any]):
        """Store encrypted tokens"""
        encrypted_data = self.cipher.encrypt(json.dumps(tokens).encode())
        with open(self.storage_path, 'wb') as f:
            f.write(encrypted_data)
    
    def load_tokens(self) -> Optional[Dict[str, Any]]:
        """Load and decrypt tokens"""
        if not os.path.exists(self.storage_path):
            return None
        
        try:
            with open(self.storage_path, 'rb') as f:
                encrypted_data = f.read()
            decrypted_data = self.cipher.decrypt(encrypted_data)
            return json.loads(decrypted_data.decode())
        except Exception as e:
            logging.error(f"Error loading tokens: {e}")
            return None
    
    def clear_tokens(self):
        """Clear stored tokens"""
        if os.path.exists(self.storage_path):
            os.remove(self.storage_path)

class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """HTTP server to handle OAuth callback"""
    
    def __init__(self, *args, auth_service=None, **kwargs):
        self.auth_service = auth_service
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        """Handle OAuth callback"""
        try:
            # Parse query parameters
            query_components = parse_qs(urlparse(self.path).query)
            
            # Check for authorization code
            if 'code' in query_components:
                code = query_components['code'][0]
                
                # Send success response
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                
                success_html = """
                <html>
                <head><title>Authentication Successful</title></head>
                <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                    <h2 style="color: #28a745;">✅ Authentication Successful!</h2>
                    <p>You can close this window and return to the application.</p>
                    <script>setTimeout(function(){ window.close(); }, 2000);</script>
                </body>
                </html>
                """
                self.wfile.write(success_html.encode())
                
                # Process the authorization code
                if self.auth_service:
                    self.auth_service._process_authorization_code(code)
            
            elif 'error' in query_components:
                error = query_components['error'][0]
                
                # Send error response
                self.send_response(400)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                
                error_html = f"""
                <html>
                <head><title>Authentication Failed</title></head>
                <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                    <h2 style="color: #dc3545;">❌ Authentication Failed</h2>
                    <p>Error: {error}</p>
                    <p>Please try again.</p>
                    <script>setTimeout(function(){{ window.close(); }}, 3000);</script>
                </body>
                </html>
                """
                self.wfile.write(error_html.encode())
                
                if self.auth_service:
                    self.auth_service._handle_auth_error(f"OAuth error: {error}")
        
        except Exception as e:
            logging.error(f"Error handling OAuth callback: {e}")
            self.send_response(500)
            self.end_headers()

class AuthService:
    """Main authentication service with Google OAuth and AWS Cognito integration"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.token_storage = TokenStorage()
        self.current_user = None
        self.callback_server = None
        self.auth_complete_event = threading.Event()
        self.auth_result = None
        
        # OAuth state for security
        self.oauth_state = None
        
        # Token refresh timer
        self.refresh_timer = None
        
    def get_auth_status(self) -> Dict[str, Any]:
        """Get current authentication status"""
        tokens = self.token_storage.load_tokens()
        
        if not tokens:
            return {
                'authenticated': False,
                'user': None,
                'tokens': None
            }
        
        # Check if tokens are expired
        if self._is_token_expired(tokens.get('access_token')):
            if self._can_refresh_token(tokens):
                try:
                    tokens = self._refresh_tokens(tokens['refresh_token'])
                except Exception as e:
                    self.logger.error(f"Token refresh failed: {e}")
                    self.logout()
                    return {
                        'authenticated': False,
                        'user': None,
                        'tokens': None
                    }
            else:
                self.logout()
                return {
                    'authenticated': False,
                    'user': None,
                    'tokens': None
                }
        
        return {
            'authenticated': True,
            'user': tokens.get('user_info'),
            'tokens': tokens
        }
    
    def start_google_auth(self) -> bool:
        """Start Google OAuth authentication flow"""
        try:
            self.logger.info("Starting Google OAuth authentication")
            
            # Generate OAuth state for security
            self.oauth_state = secrets.token_urlsafe(32)
            
            # Start callback server
            self._start_callback_server()
            
            # Build Google OAuth URL
            auth_url = self._build_google_auth_url()
            
            # Open browser for authentication
            webbrowser.open(auth_url)
            
            # Wait for authentication to complete (with timeout)
            auth_completed = self.auth_complete_event.wait(timeout=300)  # 5 minutes timeout
            
            if not auth_completed:
                raise Exception("Authentication timeout")
            
            if self.auth_result.get('success'):
                self.logger.info("Google OAuth authentication successful")
                return True
            else:
                self.logger.error(f"Google OAuth authentication failed: {self.auth_result.get('error')}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error during Google OAuth: {e}")
            self._handle_auth_error(str(e))
            return False
        finally:
            self._stop_callback_server()
    
    def _build_google_auth_url(self) -> str:
        """Build Google OAuth authorization URL"""
        params = {
            'client_id': config.GOOGLE_CLIENT_ID,
            'redirect_uri': config.GOOGLE_REDIRECT_URI,
            'response_type': 'code',
            'scope': 'openid email profile',
            'state': self.oauth_state,
            'access_type': 'offline',
            'prompt': 'consent'
        }
        
        return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    
    def _start_callback_server(self):
        """Start HTTP server to handle OAuth callback"""
        try:
            # Parse redirect URI to get port
            parsed_uri = urlparse(config.GOOGLE_REDIRECT_URI)
            port = parsed_uri.port or 3000
            
            # Create custom handler with auth service reference
            def handler_factory(*args, **kwargs):
                return OAuthCallbackHandler(*args, auth_service=self, **kwargs)
            
            self.callback_server = HTTPServer(('localhost', port), handler_factory)
            
            # Start server in separate thread
            server_thread = threading.Thread(target=self.callback_server.serve_forever)
            server_thread.daemon = True
            server_thread.start()
            
            self.logger.info(f"OAuth callback server started on port {port}")
            
        except Exception as e:
            self.logger.error(f"Error starting callback server: {e}")
            raise
    
    def _stop_callback_server(self):
        """Stop OAuth callback server"""
        if self.callback_server:
            self.callback_server.shutdown()
            self.callback_server = None
            self.logger.info("OAuth callback server stopped")
    
    def _process_authorization_code(self, code: str):
        """Process authorization code from Google OAuth"""
        try:
            # Exchange authorization code for tokens
            tokens = self._exchange_code_for_tokens(code)
            
            # Get user info from Google
            user_info = self._get_google_user_info(tokens['access_token'])
            
            # Exchange Google tokens for Cognito tokens
            cognito_tokens = self._exchange_for_cognito_tokens(tokens['id_token'])
            
            # Store complete token set
            token_data = {
                'access_token': cognito_tokens['AccessToken'],
                'refresh_token': cognito_tokens['RefreshToken'],
                'id_token': cognito_tokens['IdToken'],
                'expires_at': datetime.now().timestamp() + cognito_tokens['ExpiresIn'],
                'user_info': user_info,
                'google_tokens': tokens
            }
            
            self.token_storage.store_tokens(token_data)
            self.current_user = user_info
            
            # Set up automatic token refresh
            self._schedule_token_refresh(cognito_tokens['ExpiresIn'])
            
            # Signal authentication completion
            self.auth_result = {'success': True, 'user': user_info}
            self.auth_complete_event.set()
            
        except Exception as e:
            self.logger.error(f"Error processing authorization code: {e}")
            self._handle_auth_error(str(e))
    
    def _exchange_code_for_tokens(self, code: str) -> Dict[str, Any]:
        """Exchange authorization code for Google tokens"""
        token_url = "https://oauth2.googleapis.com/token"
        
        data = {
            'client_id': config.GOOGLE_CLIENT_ID,
            'client_secret': config.GOOGLE_CLIENT_SECRET,
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': config.GOOGLE_REDIRECT_URI
        }
        
        response = requests.post(token_url, data=data)
        response.raise_for_status()
        
        return response.json()
    
    def _get_google_user_info(self, access_token: str) -> Dict[str, Any]:
        """Get user information from Google"""
        headers = {'Authorization': f'Bearer {access_token}'}
        response = requests.get('https://www.googleapis.com/oauth2/v2/userinfo', headers=headers)
        response.raise_for_status()
        
        user_data = response.json()
        return {
            'id': user_data['id'],
            'email': user_data['email'],
            'name': user_data.get('name', ''),
            'given_name': user_data.get('given_name', ''),
            'family_name': user_data.get('family_name', ''),
            'picture': user_data.get('picture', ''),
            'verified_email': user_data.get('verified_email', False)
        }
    
    def _exchange_for_cognito_tokens(self, id_token: str) -> Dict[str, Any]:
        """Exchange Google ID token for AWS Cognito tokens"""
        # This would typically use AWS Cognito's hosted UI or custom authentication
        # For now, we'll simulate the exchange process
        
        # In a real implementation, you would:
        # 1. Send the Google ID token to your Cognito User Pool
        # 2. Use Cognito's custom authentication flow
        # 3. Receive Cognito tokens in response
        
        # For demo purposes, we'll create mock Cognito tokens
        # In production, replace this with actual Cognito integration
        
        mock_cognito_tokens = {
            'AccessToken': f"mock_cognito_access_token_{secrets.token_urlsafe(32)}",
            'RefreshToken': f"mock_cognito_refresh_token_{secrets.token_urlsafe(32)}",
            'IdToken': f"mock_cognito_id_token_{secrets.token_urlsafe(32)}",
            'ExpiresIn': 3600  # 1 hour
        }
        
        return mock_cognito_tokens
    
    def _is_token_expired(self, access_token: str) -> bool:
        """Check if access token is expired"""
        tokens = self.token_storage.load_tokens()
        if not tokens or 'expires_at' not in tokens:
            return True
        
        # Add 5-minute buffer for token refresh
        return datetime.now().timestamp() > (tokens['expires_at'] - 300)
    
    def _can_refresh_token(self, tokens: Dict[str, Any]) -> bool:
        """Check if token can be refreshed"""
        return 'refresh_token' in tokens and tokens['refresh_token']
    
    def _refresh_tokens(self, refresh_token: str) -> Dict[str, Any]:
        """Refresh access token using refresh token"""
        try:
            # In a real implementation, this would call AWS Cognito's token refresh endpoint
            # For demo purposes, we'll simulate the refresh process
            
            # Mock token refresh
            new_tokens = {
                'AccessToken': f"refreshed_access_token_{secrets.token_urlsafe(32)}",
                'RefreshToken': refresh_token,  # Keep the same refresh token
                'IdToken': f"refreshed_id_token_{secrets.token_urlsafe(32)}",
                'ExpiresIn': 3600  # 1 hour
            }
            
            # Update stored tokens
            current_tokens = self.token_storage.load_tokens()
            current_tokens.update({
                'access_token': new_tokens['AccessToken'],
                'id_token': new_tokens['IdToken'],
                'expires_at': datetime.now().timestamp() + new_tokens['ExpiresIn']
            })
            
            self.token_storage.store_tokens(current_tokens)
            
            # Schedule next refresh
            self._schedule_token_refresh(new_tokens['ExpiresIn'])
            
            return current_tokens
            
        except Exception as e:
            self.logger.error(f"Error refreshing tokens: {e}")
            raise
    
    def _schedule_token_refresh(self, expires_in: int):
        """Schedule automatic token refresh"""
        # Schedule refresh 5 minutes before expiration
        refresh_delay = max(expires_in - 300, 60)  # At least 1 minute
        
        if self.refresh_timer:
            self.refresh_timer.cancel()
        
        self.refresh_timer = threading.Timer(refresh_delay, self._auto_refresh_tokens)
        self.refresh_timer.daemon = True
        self.refresh_timer.start()
        
        self.logger.info(f"Token refresh scheduled in {refresh_delay} seconds")
    
    def _auto_refresh_tokens(self):
        """Automatically refresh tokens"""
        try:
            tokens = self.token_storage.load_tokens()
            if tokens and self._can_refresh_token(tokens):
                self._refresh_tokens(tokens['refresh_token'])
                self.logger.info("Tokens automatically refreshed")
        except Exception as e:
            self.logger.error(f"Auto token refresh failed: {e}")
    
    def _handle_auth_error(self, error_message: str):
        """Handle authentication errors"""
        self.logger.error(f"Authentication error: {error_message}")
        self.auth_result = {'success': False, 'error': error_message}
        self.auth_complete_event.set()
    
    def logout(self):
        """Logout user and clear all authentication data"""
        try:
            # Cancel any pending token refresh
            if self.refresh_timer:
                self.refresh_timer.cancel()
                self.refresh_timer = None
            
            # Clear stored tokens
            self.token_storage.clear_tokens()
            
            # Clear current user
            self.current_user = None
            
            # Reset auth state
            self.auth_complete_event.clear()
            self.auth_result = None
            
            self.logger.info("User logged out successfully")
            
        except Exception as e:
            self.logger.error(f"Error during logout: {e}")
    
    def get_user_profile(self) -> Optional[Dict[str, Any]]:
        """Get current user profile"""
        auth_status = self.get_auth_status()
        if auth_status['authenticated']:
            return auth_status['user']
        return None
    
    def get_access_token(self) -> Optional[str]:
        """Get current access token for API calls"""
        auth_status = self.get_auth_status()
        if auth_status['authenticated']:
            return auth_status['tokens']['access_token']
        return None
    
    def is_authenticated(self) -> bool:
        """Check if user is currently authenticated"""
        return self.get_auth_status()['authenticated']
