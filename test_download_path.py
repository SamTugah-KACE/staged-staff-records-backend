#!/usr/bin/env python3
"""
Test script to check download sample file paths
"""
import os
import sys
from pathlib import Path

# Add App to path
sys.path.append('App')

def test_paths():
    """Test the path construction for download sample files"""
    
    print("🔍 Testing download sample file paths...")
    print(f"Current working directory: {os.getcwd()}")
    print(f"Script location: {__file__}")
    
    # Simulate the path construction from download_sample.py
    BASE_DIR = Path(__file__).resolve().parent
    print(f"BASE_DIR from this script: {BASE_DIR}")
    
    # Test the actual download_sample.py path construction
    download_sample_path = Path("App/Apis/download_sample.py").resolve()
    print(f"download_sample.py path: {download_sample_path}")
    
    # Get the directory where download_sample.py is located
    apis_dir = download_sample_path.parent
    print(f"APIs directory: {apis_dir}")
    
    # Test file paths
    excel_file_name = "sample_staff_records.xlsx"
    excel_file_name_single = "sample_staff_records_.xlsx"
    
    file_path_branch = apis_dir / excel_file_name
    file_path_single = apis_dir / excel_file_name_single
    
    print(f"\n📁 File paths:")
    print(f"Branch file: {file_path_branch}")
    print(f"Branch exists: {file_path_branch.exists()}")
    print(f"Single file: {file_path_single}")
    print(f"Single exists: {file_path_single.exists()}")
    
    # List files in the APIs directory
    print(f"\n📋 Files in {apis_dir}:")
    for file in apis_dir.iterdir():
        if file.is_file() and file.suffix in ['.xlsx', '.xls']:
            print(f"  ✅ {file.name}")
    
    # Test the organization nature logic
    print(f"\n🧪 Testing organization nature logic:")
    test_natures = ["single", "single managed", "branch", "branched", "multi"]
    
    for nature in test_natures:
        org_nature = nature.strip().lower()
        if "single" in org_nature:
            file_path = apis_dir / excel_file_name_single
            filename = excel_file_name_single
            file_type = "SINGLE"
        else:
            file_path = apis_dir / excel_file_name
            filename = excel_file_name
            file_type = "BRANCH"
        
        print(f"  {nature} -> {file_type} -> {filename} -> Exists: {file_path.exists()}")

if __name__ == "__main__":
    test_paths()
