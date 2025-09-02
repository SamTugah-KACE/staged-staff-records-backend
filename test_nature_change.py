#!/usr/bin/env python3
"""
Test script to simulate organization nature changes and check file serving
"""
import requests
import json

def test_nature_scenarios():
    """Test different organization nature scenarios"""
    
    print("🔍 Testing organization nature scenarios...")
    
    organization_id = "b02dbcca-a215-4081-838d-977bbde883ee"
    
    # Test scenarios
    test_cases = [
        {"nature": "single", "expected_file": "sample_staff_records_.xlsx"},
        {"nature": "single managed", "expected_file": "sample_staff_records_.xlsx"},
        {"nature": "branch", "expected_file": "sample_staff_records.xlsx"},
        {"nature": "branched", "expected_file": "sample_staff_records.xlsx"},
        {"nature": "multi", "expected_file": "sample_staff_records.xlsx"},
        {"nature": "unknown", "expected_file": "sample_staff_records.xlsx"},
    ]
    
    print(f"\n📋 Testing different nature scenarios:")
    print(f"Organization ID: {organization_id}")
    
    for i, test_case in enumerate(test_cases, 1):
        nature = test_case["nature"]
        expected_file = test_case["expected_file"]
        
        print(f"\n{i}. Testing nature: '{nature}'")
        print(f"   Expected file: {expected_file}")
        
        # Note: We can't actually change the database nature in this test
        # But we can show what the logic should do
        if "single" in nature.lower():
            logic_result = "SINGLE file (sample_staff_records_.xlsx)"
        else:
            logic_result = "BRANCH file (sample_staff_records.xlsx)"
        
        print(f"   Logic result: {logic_result}")
        
        # Test the current API response
        try:
            response = requests.get(f'http://localhost:8000/api/download/sample-file/{organization_id}')
            content_disposition = response.headers.get('content-disposition', '')
            filename = content_disposition.split('filename=')[1].strip('"') if 'filename=' in content_disposition else 'unknown'
            
            print(f"   Current API response: {filename}")
            
            if filename == expected_file:
                print(f"   ✅ CORRECT - API serves expected file")
            else:
                print(f"   ❌ MISMATCH - API serves {filename} but expected {expected_file}")
                
        except Exception as e:
            print(f"   ❌ Error: {e}")

def check_current_behavior():
    """Check the current behavior of the API"""
    print(f"\n🔍 Current API behavior analysis:")
    
    organization_id = "b02dbcca-a215-4081-838d-977bbde883ee"
    
    try:
        response = requests.get(f'http://localhost:8000/api/download/sample-file/{organization_id}')
        
        if response.status_code == 200:
            content_disposition = response.headers.get('content-disposition', '')
            filename = content_disposition.split('filename=')[1].strip('"') if 'filename=' in content_disposition else 'unknown'
            
            print(f"✅ API is serving: {filename}")
            
            if filename == "sample_staff_records_.xlsx":
                print("   → This means the organization nature contains 'single'")
                print("   → Organization is treated as SINGLE organization")
            elif filename == "sample_staff_records.xlsx":
                print("   → This means the organization nature does NOT contain 'single'")
                print("   → Organization is treated as BRANCH/MULTI organization")
            else:
                print(f"   → Unknown file type: {filename}")
        else:
            print(f"❌ API error: {response.status_code} - {response.text}")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    check_current_behavior()
    test_nature_scenarios()
