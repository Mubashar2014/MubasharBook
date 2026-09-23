#!/usr/bin/env python
"""
Script to create subscriptions for existing users who don't have one.
Run this after deploying the new subscription management system.
"""
from app import create_app
from app.extensions import db
from app.models.user import User
from app.models.shop import Shop
from app.models.subscription import Subscription

app = create_app()

with app.app_context():
    # Find all shops without subscriptions
    shops_without_subs = Shop.query.outerjoin(Subscription).filter(
        Subscription.id == None
    ).all()
    
    print(f"Found {len(shops_without_subs)} shops without subscriptions")
    
    for shop in shops_without_subs:
        user = shop.owner
        print(f"Creating subscription for: {user.owner_name} ({user.email})")
        
        # Create subscription based on user's trial status
        sub = Subscription(
            shop_id=shop.id,
            plan='basic',
            status='trial' if user.is_trial_active else 'expired',
            trial_start=user.trial_start,
            trial_end=user.trial_end,
            current_period_start=user.trial_start,
            current_period_end=user.trial_end,
        )
        db.session.add(sub)
    
    db.session.commit()
    print(f"✓ Successfully created {len(shops_without_subs)} subscriptions")
