#!/usr/bin/env python3
"""
Test script for Summary WebSocket endpoint
"""
import asyncio
import websockets
import json
import sys

async def test_summary_websocket():
    """Test the Summary WebSocket endpoint"""
    
    # Test data
    organization_id = "b02dbcca-a215-4081-838d-977bbde883ee"
    user_id = "5620b05f-0ac9-4248-85da-fd14180cba9a"
    
    # JWT token (same as employee test)
    token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiNTYyMGIwNWYtMGFjOS00MjQ4LTg1ZGEtZmQxNDE4MGNiYTlhIiwidXNlcm5hbWUiOiJrZHVhaDU0QGdtYWlsLmNvbSIsInJvbGVfaWQiOiI2NTMxZmI5Mi1iMDczLTRkZDYtOGRmMC1iODFkYzg4M2Y0NTUiLCJvcmdhbml6YXRpb25faWQiOiJiMDJkYmNjYS1hMjE1LTQwODEtODM4ZC05NzdiYmRlODgzZWUiLCJsb2dpbl9vcHRpb24iOiJwYXNzd29yZCIsImlhdCI6MTc1NjgzMDU1NS4wMDIyODMsImxhc3RfYWN0aXZpdHkiOjE3NTY4MzA1NTUuMDAyMjgzLCJleHAiOjE3NTY4NTkzNTV9.8VOG0Fxs3kh_QV-0rM1vdincP7xVNFjpHddVtFtVtxE"
    
    # WebSocket URL
    uri = f"ws://localhost:8000/ws/summary/{organization_id}/{user_id}?token={token}"
    
    try:
        print(f"🔌 Connecting to Summary WebSocket...")
        print(f"📍 URL: {uri}")
        print(f"👤 User ID: {user_id}")
        print(f"🏢 Organization ID: {organization_id}")
        print("-" * 50)
        
        async with websockets.connect(uri) as websocket:
            print("✅ Connected successfully!")
            
            # Wait for initial payload
            print("⏳ Waiting for initial summary payload...")
            initial_message = await websocket.recv()
            initial_data = json.loads(initial_message)
            
            print("📦 Initial summary payload received:")
            print(f"   Type: {initial_data.get('type')}")
            payload = initial_data.get('payload', {})
            
            print("\n📊 Organization Summary Structure:")
            for key, value in payload.items():
                if isinstance(value, (int, float)):
                    print(f"  📈 {key}: {value}")
                elif isinstance(value, dict):
                    print(f"  📁 {key}: {len(value)} items")
                    for sub_key, sub_value in list(value.items())[:3]:
                        print(f"      └─ {sub_key}: {sub_value}")
                elif isinstance(value, list):
                    print(f"  📋 {key}: {len(value)} items")
                else:
                    print(f"  📄 {key}: {value}")
            
            # Test heartbeat/ping functionality
            print("\n💓 Testing heartbeat...")
            await websocket.send("ping")
            print("✅ Heartbeat sent")
            
            # Wait for potential automatic updates
            print("\n⏳ Waiting for potential automatic updates (15 seconds)...")
            try:
                auto_update = await asyncio.wait_for(websocket.recv(), timeout=15.0)
                auto_data = json.loads(auto_update)
                print("📦 Automatic update received:")
                print(f"   Type: {auto_data.get('type')}")
                print(f"   Payload keys: {list(auto_data.get('payload', {}).keys())}")
            except asyncio.TimeoutError:
                print("⏰ No automatic updates received (this is normal)")
            
            # Test token revalidation by waiting longer
            print("\n⏳ Testing token revalidation (waiting 65 seconds)...")
            print("   (This will test the 60-second token validation)")
            try:
                # Wait for token revalidation
                await asyncio.wait_for(websocket.recv(), timeout=65.0)
                print("✅ Connection still active after token revalidation")
            except asyncio.TimeoutError:
                print("⏰ No messages during revalidation period (connection maintained)")
            
            print("\n✅ Summary WebSocket test completed successfully!")
            
    except websockets.exceptions.ConnectionClosed as e:
        print(f"❌ Connection closed: {e}")
        print("💡 This might be due to:")
        print("   - Invalid JWT token")
        print("   - Insufficient permissions")
        print("   - User not found")
        print("   - Organization mismatch")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        print("💡 Make sure:")
        print("   - Server is running on localhost:8000")
        print("   - JWT token is valid")
        print("   - User and Organization IDs exist")

if __name__ == "__main__":
    print("🧪 Summary WebSocket Test")
    print("=" * 50)
    asyncio.run(test_summary_websocket())
