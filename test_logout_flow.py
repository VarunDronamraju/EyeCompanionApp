#!/usr/bin/env python3
"""
Test Logout Flow
Verifies that logout works correctly without causing application crashes
"""

import sys
import os
import logging
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from desktop.services.auth_service import AuthService

def test_logout_flow():
    """Test the logout flow"""
    print("🧪 Testing Logout Flow")
    print("=" * 50)
    
    # Initialize auth service
    auth_service = AuthService()
    
    # Test 1: Check initial state
    print("\n1. Testing initial authentication state...")
    is_auth = auth_service.is_authenticated()
    print(f"   Is authenticated: {is_auth}")
    
    # Test 2: Test logout (should work even if not authenticated)
    print("\n2. Testing logout functionality...")
    try:
        auth_service.logout()
        print("   ✅ Logout completed successfully")
    except Exception as e:
        print(f"   ❌ Logout failed: {e}")
        return False
    
    # Test 3: Verify logout cleared everything
    print("\n3. Verifying logout cleared authentication...")
    is_auth_after = auth_service.is_authenticated()
    print(f"   Is authenticated after logout: {is_auth_after}")
    
    if not is_auth_after:
        print("   ✅ Logout properly cleared authentication")
    else:
        print("   ❌ Logout did not clear authentication")
        return False
    
    # Test 4: Test token storage
    print("\n4. Testing token storage...")
    tokens = auth_service.token_storage.load_tokens()
    if tokens is None:
        print("   ✅ Token storage properly cleared")
    else:
        print("   ❌ Token storage not cleared")
        return False
    
    print("\n🎉 Logout flow test completed successfully!")
    return True

def main():
    """Main test function"""
    logging.basicConfig(level=logging.INFO)
    
    try:
        success = test_logout_flow()
        if success:
            print("\n✅ All logout tests passed!")
            print("\nThe logout flow should now work correctly without causing application crashes.")
        else:
            print("\n❌ Some logout tests failed!")
            return False
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
