#!/usr/bin/env python3
"""
Check employees in the database
"""
import sys
sys.path.append('App')

from database.db_session import get_db
from Models.models import Employee, User
from sqlalchemy.orm import Session

def check_employees():
    """Check what employees exist in the database"""
    db: Session = next(get_db())
    
    try:
        print("🔍 Checking employees in database...")
        
        # Get all employees
        employees = db.query(Employee).all()
        print(f"📊 Total employees found: {len(employees)}")
        
        if employees:
            print("\n👥 Employee list:")
            for emp in employees[:10]:  # Show first 10
                print(f"  - ID: {emp.id}")
                print(f"    Email: {emp.email}")
                print(f"    Name: {emp.first_name} {emp.last_name}")
                print(f"    Organization: {emp.organization_id}")
                print()
        else:
            print("❌ No employees found in database")
        
        # Check users
        users = db.query(User).all()
        print(f"👤 Total users found: {len(users)}")
        
        if users:
            print("\n🔐 User list:")
            for user in users[:5]:  # Show first 5
                print(f"  - ID: {user.id}")
                print(f"    Email: {user.email}")
                print(f"    Organization: {user.organization_id}")
                print()
        
        # Check if the specific employee exists
        target_employee_id = "b02dbcca-a215-4081-838d-977bbde883ee"
        emp = db.query(Employee).filter(Employee.id == target_employee_id).first()
        
        if emp:
            print(f"✅ Employee {target_employee_id} found!")
            print(f"   Email: {emp.email}")
            print(f"   Name: {emp.first_name} {emp.last_name}")
        else:
            print(f"❌ Employee {target_employee_id} NOT found")
            
        # Check if there's a user with the same ID
        user = db.query(User).filter(User.id == target_employee_id).first()
        if user:
            print(f"✅ User {target_employee_id} found!")
            print(f"   Email: {user.email}")
        else:
            print(f"❌ User {target_employee_id} NOT found")
            
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    check_employees()
