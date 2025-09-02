#!/usr/bin/env python3
"""
Test script for Employee WebSocket endpoint
"""
import asyncio
import websockets
import json
import sys

async def test_employee_websocket():
    """Test the Employee WebSocket endpoint"""
    
    # Test data
    employee_id = "2e4d175f-a5e8-4074-9729-d0d7784b4624"  # Correct employee ID
    organization_id = "b02dbcca-a215-4081-838d-977bbde883ee"
    
    # JWT token provided for testing
    token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiNTYyMGIwNWYtMGFjOS00MjQ4LTg1ZGEtZmQxNDE4MGNiYTlhIiwidXNlcm5hbWUiOiJrZHVhaDU0QGdtYWlsLmNvbSIsInJvbGVfaWQiOiI2NTMxZmI5Mi1iMDczLTRkZDYtOGRmMC1iODFkYzg4M2Y0NTUiLCJvcmdhbml6YXRpb25faWQiOiJiMDJkYmNjYS1hMjE1LTQwODEtODM4ZC05NzdiYmRlODgzZWUiLCJsb2dpbl9vcHRpb24iOiJwYXNzd29yZCIsImlhdCI6MTc1NjgzMDU1NS4wMDIyODMsImxhc3RfYWN0aXZpdHkiOjE3NTY4MzA1NTUuMDAyMjgzLCJleHAiOjE3NTY4NTkzNTV9.8VOG0Fxs3kh_QV-0rM1vdincP7xVNFjpHddVtFtVtxE"
    
    # WebSocket URL
    uri = f"ws://localhost:8000/ws/employee/{organization_id}/{employee_id}?token={token}"
    
    try:
        print(f"🔌 Connecting to Employee WebSocket...")
        print(f"📍 URL: {uri}")
        print(f"👤 Employee ID: {employee_id}")
        print(f"🏢 Organization ID: {organization_id}")
        print("-" * 50)
        
        async with websockets.connect(uri) as websocket:
            print("✅ Connected successfully!")
            
            # Wait for initial payload
            print("⏳ Waiting for initial payload...")
            initial_message = await websocket.recv()
            initial_data = json.loads(initial_message)
            
            print("📦 Initial payload received:")
            print(f"   Type: {initial_data.get('type')}")
            print(f"   Payload keys: {list(initial_data.get('payload', {}).keys())}")
            
            # Test refresh functionality
            print("\n🔄 Testing refresh functionality...")
            await websocket.send("refresh")
            
            refresh_message = await websocket.recv()
            refresh_data = json.loads(refresh_message)
            
            print("📦 Refresh payload received:")
            print(f"   Type: {refresh_data.get('type')}")
            print(f"   Payload keys: {list(refresh_data.get('payload', {}).keys())}")
            
            # Test ping/pong (heartbeat)
            print("\n💓 Testing heartbeat...")
            await websocket.send("ping")
            
            # Wait a bit to see if we get any automatic updates
            print("\n⏳ Waiting for potential automatic updates (10 seconds)...")
            try:
                auto_update = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                auto_data = json.loads(auto_update)
                print("📦 Automatic update received:")
                print(f"   Type: {auto_data.get('type')}")
                print(f"   Employee ID: {auto_data.get('employee_id')}")
            except asyncio.TimeoutError:
                print("⏰ No automatic updates received (this is normal)")
            
            print("\n✅ WebSocket test completed successfully!")
            
    except websockets.exceptions.ConnectionClosed as e:
        print(f"❌ Connection closed: {e}")
        print("💡 This might be due to:")
        print("   - Invalid JWT token")
        print("   - Insufficient permissions")
        print("   - Employee not found")
        print("   - Organization mismatch")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        print("💡 Make sure:")
        print("   - Server is running on localhost:8000")
        print("   - JWT token is valid")
        print("   - Employee and Organization IDs exist")

if __name__ == "__main__":
    print("🧪 Employee WebSocket Test")
    print("=" * 50)
    
    if len(sys.argv) > 1:
        # Allow token to be passed as command line argument
        token = sys.argv[1]
        # Update the token in the test function
        import test_employee_websocket
        test_employee_websocket.token = token
    
    asyncio.run(test_employee_websocket())
