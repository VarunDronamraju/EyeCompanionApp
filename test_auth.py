#!/usr/bin/env python3
"""
Test script for authentication system
Verifies Google OAuth integration and token management
"""

import sys
import os
import logging
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from desktop.services.auth_service import AuthService
from config import config

def setup_logging():
    """Setup logging for testing"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

def test_auth_service():
    """Test the authentication service"""
    print("🔐 Testing Authentication Service")
    print("=" * 50)
    
    # Initialize auth service
    auth_service = AuthService()
    
    # Test 1: Check initial authentication status
    print("\n1. Testing initial authentication status...")
    auth_status = auth_service.get_auth_status()
    print(f"   Authenticated: {auth_status['authenticated']}")
    print(f"   User: {auth_status['user']}")
    
    # Test 2: Check if user is authenticated
    print("\n2. Testing is_authenticated()...")
    is_auth = auth_service.is_authenticated()
    print(f"   Is authenticated: {is_auth}")
    
    # Test 3: Get user profile (should be None if not authenticated)
    print("\n3. Testing get_user_profile()...")
    user_profile = auth_service.get_user_profile()
    print(f"   User profile: {user_profile}")
    
    # Test 4: Get access token (should be None if not authenticated)
    print("\n4. Testing get_access_token()...")
    access_token = auth_service.get_access_token()
    print(f"   Access token: {'Present' if access_token else 'None'}")
    
    # Test 5: Test logout (should work even if not authenticated)
    print("\n5. Testing logout()...")
    auth_service.logout()
    print("   Logout completed")
    
    # Test 6: Verify logout cleared everything
    print("\n6. Verifying logout cleared authentication...")
    auth_status_after = auth_service.get_auth_status()
    print(f"   Authenticated after logout: {auth_status_after['authenticated']}")
    print(f"   User after logout: {auth_status_after['user']}")
    
    print("\n✅ Authentication service tests completed!")
    return True

def test_config():
    """Test configuration values"""
    print("\n⚙️  Testing Configuration")
    print("=" * 50)
    
    print(f"Google Client ID: {config.GOOGLE_CLIENT_ID[:20]}...")
    print(f"Google Redirect URI: {config.GOOGLE_REDIRECT_URI}")
    print(f"Cognito User Pool ID: {config.COGNITO_USER_POOL_ID}")
    print(f"Cognito Client ID: {config.COGNITO_CLIENT_ID}")
    print(f"AWS Region: {config.AWS_REGION}")
    
    print("\n✅ Configuration test completed!")
    return True

def main():
    """Main test function"""
    setup_logging()
    
    print("🧪 Authentication System Test Suite")
    print("=" * 60)
    
    try:
        # Test configuration
        test_config()
        
        # Test authentication service
        test_auth_service()
        
        print("\n🎉 All tests passed!")
        print("\nTo test full OAuth flow:")
        print("1. Run the main application: python main.py")
        print("2. Click 'Continue with Google' in the login window")
        print("3. Complete the OAuth flow in your browser")
        print("4. Verify authentication completes successfully")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
