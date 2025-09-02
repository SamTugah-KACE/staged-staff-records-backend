#!/usr/bin/env python3
"""
Direct test of download sample functionality
"""
import sys
sys.path.append('App')

from pathlib import Path
from sqlalchemy.orm import Session
from database.db_session import get_db
from Models.Tenants.organization import Organization

def test_download_logic():
    """Test the download logic directly"""
    
    print("🔍 Testing download sample logic directly...")
    
    # Test organization lookup
    organization_id = "b02dbcca-a215-4081-838d-977bbde883ee"
    db: Session = next(get_db())
    
    try:
        org = db.query(Organization).filter(Organization.id == organization_id).first()
        if not org:
            print(f"❌ Organization not found: {organization_id}")
            return
        
        print(f"✅ Organization found: {org.name}")
        print(f"   Nature: '{org.nature}'")
        
        org_nature = org.nature.strip().lower() if org.nature else "unknown"
        print(f"   Processed nature: '{org_nature}'")
        
        # Test file selection logic
        EXCEL_FILE_NAME = "sample_staff_records.xlsx"
        EXCEL_FILE_NAME_SINGLE = "sample_staff_records_.xlsx"
        BASE_DIR = Path("App/Apis").resolve()
        
        print(f"   BASE_DIR: {BASE_DIR}")
        
        if "single" in org_nature:
            print("   → Serving SINGLE organization file")
            file_path = BASE_DIR / EXCEL_FILE_NAME_SINGLE
            filename = EXCEL_FILE_NAME_SINGLE
        else:
            print("   → Serving BRANCH organization file")
            file_path = BASE_DIR / EXCEL_FILE_NAME
            filename = EXCEL_FILE_NAME
        
        print(f"   File path: {file_path}")
        print(f"   File exists: {file_path.exists()}")
        print(f"   Filename: {filename}")
        
        if file_path.exists():
            print("✅ File found - download should work!")
        else:
            print("❌ File not found - this is the issue!")
            
            # List files in the directory
            print(f"   Files in {BASE_DIR}:")
            for file in BASE_DIR.iterdir():
                if file.is_file() and file.suffix in ['.xlsx', '.xls']:
                    print(f"      ✅ {file.name}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    test_download_logic()
