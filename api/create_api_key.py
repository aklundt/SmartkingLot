#!/usr/bin/env python3
"""
Create an API key for the SmartParkingLot detector
"""
import sys
from pathlib import Path

# Add parent directory to path so we can import db
sys.path.insert(0, str(Path(__file__).parent.parent))
import db

def main():
    print("=" * 60)
    print("SmartParkingLot - Create API Key")
    print("=" * 60)
    print("\nThis script creates an API key for detector authentication.\n")
    
    # Initialize database
    db.init_db()
    
    # Get input
    name = input("API Key name (e.g., 'Main Detector'): ").strip()
    if not name:
        print("Error: Name cannot be empty")
        sys.exit(1)
    
    description = input("Description (optional, press Enter to skip): ").strip() or None
    
    # Create the API key
    print("\nCreating API key...")
    api_key = db.create_api_key(name, description)
    
    if api_key:
        print("\n" + "=" * 60)
        print("✓ SUCCESS!")
        print("=" * 60)
        print(f"\nAPI Key created: {name}")
        if description:
            print(f"Description: {description}")
        print(f"\n🔑 API Key: {api_key}")
        print("\n⚠️  IMPORTANT:")
        print("  1. Save this key now - it will NOT be shown again!")
        print("  2. Add it to your .env file:")
        print(f"     API_KEY={api_key}")
        print("  3. Restart detector.py after updating .env")
        print("=" * 60)
    else:
        print("\n✗ Error: Failed to create API key")
        sys.exit(1)

if __name__ == '__main__':
    main()
