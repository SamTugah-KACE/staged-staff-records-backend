#!/usr/bin/env python3
"""
Helper script to get a JWT token for testing WebSockets
"""
import requests
import json
import sys

def get_auth_token():
    """Get JWT token for testing"""
    
    # You'll need to provide valid credentials
    # Replace these with actual credentials from your system
    username = "your_username_here"  # Replace with actual username
    password = "your_password_here"   # Replace with actual password
    
    try:
        print("🔐 Attempting to get JWT token...")
        print("💡 You need to provide valid credentials in the script first!")
        
        # Try to login and get token (using Form data, not JSON)
        response = requests.post(
            "http://localhost:8000/auth/login",
            data={
                "username": username,
                "password": password
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token") or data.get("token")
            if token:
                print("✅ Token obtained successfully!")
                print(f"🔑 Token: {token[:50]}...")
                return token
            else:
                print("❌ No token found in response")
                print(f"Response: {data}")
        else:
            print(f"❌ Login failed with status: {response.status_code}")
            print(f"Response: {response.text}")
            
    except Exception as e:
        print(f"❌ Error getting token: {e}")
        print("💡 Make sure:")
        print("   - Server is running")
        print("   - Login endpoint is correct")
        print("   - Credentials are valid")
    
    return None

def test_without_auth():
    """Test WebSocket without authentication (will fail but show the error)"""
    import asyncio
    import websockets
    
    async def test_connection():
        employee_id = "b02dbcca-a215-4081-838d-977bbde883ee"
        organization_id = "b02dbcca-a215-4081-838d-977bbde883ee"
        uri = f"ws://localhost:8000/ws/employee/{organization_id}/{employee_id}?token=invalid_token"
        
        try:
            print("🧪 Testing WebSocket connection with invalid token...")
            async with websockets.connect(uri) as websocket:
                print("✅ Connected (unexpected!)")
        except websockets.exceptions.ConnectionClosed as e:
            print(f"❌ Connection closed as expected: {e}")
            print("✅ WebSocket endpoint is working (rejected invalid token)")
        except Exception as e:
            print(f"❌ Error: {e}")
    
    asyncio.run(test_connection())

if __name__ == "__main__":
    print("🔐 JWT Token Helper")
    print("=" * 50)
    
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        # Test WebSocket endpoint without valid auth
        test_without_auth()
    else:
        # Try to get a valid token
        token = get_auth_token()
        if token:
            print(f"\n🚀 Use this token to test the WebSocket:")
            print(f"python test_employee_websocket.py {token}")
        else:
            print(f"\n🧪 Test WebSocket endpoint (will fail with auth error):")
            print(f"python get_auth_token.py test")
