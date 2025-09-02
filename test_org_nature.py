#!/usr/bin/env python3
"""
Test script to check organization nature and download behavior
"""
import requests
import json

def test_organization_nature():
    """Test the organization nature and download behavior"""
    
    print("🔍 Testing organization nature and download behavior...")
    
    organization_id = "b02dbcca-a215-4081-838d-977bbde883ee"
    
    # Test the download API
    print(f"\n📥 Testing download API for organization: {organization_id}")
    
    try:
        response = requests.get(f'http://localhost:8000/api/download/sample-file/{organization_id}')
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            print("✅ File downloaded successfully")
            # Check the filename in the response headers
            content_disposition = response.headers.get('content-disposition', '')
            print(f"Content-Disposition: {content_disposition}")
            
            # Extract filename from content-disposition
            if 'filename=' in content_disposition:
                filename = content_disposition.split('filename=')[1].strip('"')
                print(f"Downloaded filename: {filename}")
                
                if 'sample_staff_records_.xlsx' in filename:
                    print("✅ Serving SINGLE organization file (correct)")
                elif 'sample_staff_records.xlsx' in filename:
                    print("✅ Serving BRANCH organization file (correct)")
                else:
                    print(f"❓ Unknown file type: {filename}")
        else:
            print(f"❌ Error: {response.text}")
            
    except requests.exceptions.ConnectionError:
        print("❌ Server not running. Please start the server first.")
    except Exception as e:
        print(f"❌ Error: {e}")

def test_multiple_requests():
    """Test multiple requests to see if there's any caching"""
    print(f"\n🔄 Testing multiple requests for consistency...")
    
    organization_id = "b02dbcca-a215-4081-838d-977bbde883ee"
    
    for i in range(3):
        try:
            response = requests.get(f'http://localhost:8000/api/download/sample-file/{organization_id}')
            content_disposition = response.headers.get('content-disposition', '')
            filename = content_disposition.split('filename=')[1].strip('"') if 'filename=' in content_disposition else 'unknown'
            print(f"Request {i+1}: Status {response.status_code}, File: {filename}")
        except Exception as e:
            print(f"Request {i+1}: Error - {e}")

if __name__ == "__main__":
    test_organization_nature()
    test_multiple_requests()
