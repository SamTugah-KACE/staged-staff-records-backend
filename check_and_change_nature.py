#!/usr/bin/env python3
"""
Script to check and change organization nature for testing
"""
import sys
sys.path.append('App')

from sqlalchemy.orm import Session
from database.db_session import get_db
from Models.Tenants.organization import Organization

def check_organization_nature():
    """Check the current organization nature"""
    print("🔍 Checking current organization nature...")
    
    organization_id = "b02dbcca-a215-4081-838d-977bbde883ee"
    db: Session = next(get_db())
    
    try:
        org = db.query(Organization).filter(Organization.id == organization_id).first()
        if not org:
            print(f"❌ Organization not found: {organization_id}")
            return None
        
        print(f"✅ Organization found: {org.name}")
        print(f"   Current nature: '{org.nature}'")
        print(f"   Processed nature: '{org.nature.strip().lower() if org.nature else 'unknown'}'")
        
        # Determine what file should be served
        org_nature = org.nature.strip().lower() if org.nature else "unknown"
        if "single" in org_nature:
            expected_file = "sample_staff_records_.xlsx"
            file_type = "SINGLE"
        else:
            expected_file = "sample_staff_records.xlsx"
            file_type = "BRANCH/MULTI"
        
        print(f"   Expected file: {expected_file} ({file_type})")
        
        return org
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        db.close()

def change_organization_nature(new_nature):
    """Change the organization nature"""
    print(f"\n🔄 Changing organization nature to: '{new_nature}'")
    
    organization_id = "b02dbcca-a215-4081-838d-977bbde883ee"
    db: Session = next(get_db())
    
    try:
        org = db.query(Organization).filter(Organization.id == organization_id).first()
        if not org:
            print(f"❌ Organization not found: {organization_id}")
            return False
        
        old_nature = org.nature
        org.nature = new_nature
        db.commit()
        
        print(f"✅ Organization nature changed:")
        print(f"   From: '{old_nature}'")
        print(f"   To: '{new_nature}'")
        
        # Determine what file should now be served
        org_nature = new_nature.strip().lower() if new_nature else "unknown"
        if "single" in org_nature:
            expected_file = "sample_staff_records_.xlsx"
            file_type = "SINGLE"
        else:
            expected_file = "sample_staff_records.xlsx"
            file_type = "BRANCH/MULTI"
        
        print(f"   Expected file after change: {expected_file} ({file_type})")
        
        return True
        
    except Exception as e:
        print(f"❌ Error changing nature: {e}")
        db.rollback()
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()

def test_api_after_change():
    """Test the API after nature change"""
    print(f"\n🧪 Testing API after nature change...")
    
    import requests
    
    organization_id = "b02dbcca-a215-4081-838d-977bbde883ee"
    
    try:
        response = requests.get(f'http://localhost:8000/api/download/sample-file/{organization_id}')
        
        if response.status_code == 200:
            content_disposition = response.headers.get('content-disposition', '')
            filename = content_disposition.split('filename=')[1].strip('"') if 'filename=' in content_disposition else 'unknown'
            
            print(f"✅ API response: {filename}")
            
            if filename == "sample_staff_records_.xlsx":
                print("   → API is now serving SINGLE organization file")
            elif filename == "sample_staff_records.xlsx":
                print("   → API is serving BRANCH organization file")
            else:
                print(f"   → Unknown file type: {filename}")
        else:
            print(f"❌ API error: {response.status_code} - {response.text}")
            
    except Exception as e:
        print(f"❌ Error testing API: {e}")

if __name__ == "__main__":
    # Check current nature
    org = check_organization_nature()
    
    if org:
        print(f"\n" + "="*60)
        print("TESTING NATURE CHANGE")
        print("="*60)
        
        # Test changing to single
        if change_organization_nature("single"):
            test_api_after_change()
        
        print(f"\n" + "="*60)
        print("REVERTING TO ORIGINAL")
        print("="*60)
        
        # Revert back to original (assuming it was not single)
        if change_organization_nature("branch"):
            test_api_after_change()
