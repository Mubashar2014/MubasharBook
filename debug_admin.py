#!/usr/bin/env python
"""Debug script to check why admin dashboard is empty."""
from app import create_app
from app.models.user import User
from app.models.shop import Shop
from app.models.subscription import Subscription

app = create_app()

with app.app_context():
    print("=" * 60)
    print("DEBUG: Admin Dashboard Data")
    print("=" * 60)
    
    # Check total users
    all_users = User.query.all()
    print(f"\n1. Total users in database: {len(all_users)}")
    for user in all_users:
        print(f"   - {user.owner_name} ({user.email}) - is_admin: {user.is_admin}")
    
    # Check non-admin users
    non_admin_users = User.query.filter_by(is_admin=False).all()
    print(f"\n2. Non-admin users: {len(non_admin_users)}")
    for user in non_admin_users:
        print(f"   - {user.owner_name} ({user.email})")
    
    # Check shops
    shops = Shop.query.all()
    print(f"\n3. Total shops: {len(shops)}")
    for shop in shops:
        print(f"   - Shop ID {shop.id}: {shop.name} (User: {shop.owner.owner_name})")
    
    # Check subscriptions
    subscriptions = Subscription.query.all()
    print(f"\n4. Total subscriptions: {len(subscriptions)}")
    for sub in subscriptions:
        shop = Shop.query.get(sub.shop_id)
        print(f"   - Sub ID {sub.id}: Shop '{shop.name}' - Status: {sub.status}")
    
    # Test the query from admin dashboard
    print(f"\n5. Testing admin dashboard query...")
    from sqlalchemy import or_
    query = User.query.outerjoin(Shop).outerjoin(Subscription, Shop.id == Subscription.shop_id)
    query = query.filter(User.is_admin == False)
    result = query.all()
    print(f"   Query returned: {len(result)} users")
    for user in result:
        print(f"   - {user.owner_name}: Shop={user.shop.name if user.shop else 'None'}, Sub={user.shop.subscription.status if user.shop and user.shop.subscription else 'None'}")
    
    print("\n" + "=" * 60)
