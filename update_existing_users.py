#!/usr/bin/env python3
"""
Update existing users to work with new email verification system.

This script:
1. Marks all existing users as email verified
2. Sets email_verified_at timestamp
3. Ensures existing users can still login

Run this ONCE after deploying email verification changes.
"""

from app import create_app
from app.extensions import db
from app.models.user import User
from datetime import datetime

def update_existing_users():
    """Mark all existing users as verified."""
    app = create_app()
    
    with app.app_context():
        # Find users who have is_verified=True but no email_verified_at
        users_to_update = User.query.filter(
            User.email_verified_at == None
        ).all()
        
        if not users_to_update:
            print("✅ No users need updating. All set!")
            return
        
        print(f"Found {len(users_to_update)} users to update...")
        
        for user in users_to_update:
            # Set email_verified_at to their creation date (or now)
            user.email_verified_at = user.created_at or datetime.utcnow()
            user.is_verified = True
            print(f"  ✓ Updated: {user.owner_name} ({user.email})")
        
        db.session.commit()
        print(f"\n✅ Successfully updated {len(users_to_update)} users!")
        print("All existing users can now login.")

if __name__ == '__main__':
    update_existing_users()
