#!/usr/bin/env python3
"""
Setup script for SmartParkingLot
Creates the first admin user account
"""
import sys
import getpass
from pathlib import Path

# Add parent directory to path so we can import db
sys.path.insert(0, str(Path(__file__).parent.parent))
import db

def main():
    print("=" * 60)
    print("SmartParkingLot - Initial Setup")
    print("=" * 60)
    print("\nThis script will create your first admin user.\n")
    
    # Initialize database
    db.init_db()
    print("✓ Database initialized\n")
    
    # Get user input
    username = input("Admin username: ").strip()
    if not username:
        print("Error: Username cannot be empty")
        sys.exit(1)
    
    email = input("Email (optional, press Enter to skip): ").strip() or None
    
    # Get password securely
    while True:
        password = getpass.getpass("Password: ")
        if not password:
            print("Error: Password cannot be empty")
            continue
        
        password_confirm = getpass.getpass("Confirm password: ")
        if password == password_confirm:
            break
        else:
            print("Error: Passwords do not match. Try again.\n")
    
    # Create the admin user
    print("\nCreating admin user...")
    user = db.create_user(username, password, email, is_admin=True)
    
    if user:
        print("\n" + "=" * 60)
        print("✓ SUCCESS!")
        print("=" * 60)
        print(f"\nAdmin user created:")
        print(f"  Username: {user['username']}")
        if user['email']:
            print(f"  Email:    {user['email']}")
        print(f"  Role:     Admin")
        print("\nYou can now log in to the dashboard with these credentials.")
        print("=" * 60)
    else:
        print("\n✗ Error: Username already exists")
        sys.exit(1)

if __name__ == '__main__':
    main()
