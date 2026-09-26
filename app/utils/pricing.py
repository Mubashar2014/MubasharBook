"""
Pricing utilities and helper functions.
"""

from flask import current_app


def get_plan_price(plan='basic', billing_cycle='monthly'):
    """
    Get the price for a specific plan and billing cycle.
    
    Args:
        plan: 'basic' or 'premium'
        billing_cycle: 'monthly' or 'annual'
    
    Returns:
        Price in PKR
    """
    if plan == 'premium':
        if billing_cycle == 'annual':
            return current_app.config.get('PREMIUM_PLAN_PRICE_ANNUAL', 35000)
        return current_app.config.get('PREMIUM_PLAN_PRICE_MONTHLY', 3500)
    else:  # basic
        if billing_cycle == 'annual':
            return current_app.config.get('BASIC_PLAN_PRICE_ANNUAL', 20000)
        return current_app.config.get('BASIC_PLAN_PRICE_MONTHLY', 2000)


def format_price(amount):
    """
    Format price in PKR with proper formatting.
    
    Args:
        amount: Price amount
    
    Returns:
        Formatted string like "Rs 2,000"
    """
    return f"Rs {amount:,.0f}"


def get_plan_features(plan='basic'):
    """
    Get list of features for a plan.
    
    Args:
        plan: 'basic' or 'premium'
    
    Returns:
        List of feature dictionaries with 'name' and 'included' keys
    """
    basic_features = [
        {'name': 'Stock management', 'included': True},
        {'name': 'Cashbook & Khata', 'included': True},
        {'name': 'Expense tracking', 'included': True},
        {'name': 'Profit/loss calculation', 'included': True},
        {'name': 'Daily & monthly net balance', 'included': True},
        {'name': 'Unlimited users', 'included': True},
        {'name': 'Mobile-friendly design', 'included': True},
        {'name': 'Email support', 'included': True},
        {'name': 'Shareholder profit-split', 'included': False},
        {'name': 'Investor portal', 'included': False},
        {'name': 'Priority support', 'included': False},
    ]
    
    premium_features = [
        {'name': 'Everything in Basic', 'included': True},
        {'name': 'Shareholder profit-split engine', 'included': True},
        {'name': 'Investor portal accounts', 'included': True},
        {'name': 'Phone funding tracking', 'included': True},
        {'name': 'Priority email support', 'included': True},
    ]
    
    return premium_features if plan == 'premium' else basic_features


def calculate_savings(plan='basic'):
    """
    Calculate savings when choosing annual billing.
    
    Args:
        plan: 'basic' or 'premium'
    
    Returns:
        Tuple of (annual_price, monthly_equivalent, savings_amount, savings_percentage)
    """
    monthly_price = get_plan_price(plan, 'monthly')
    annual_price = get_plan_price(plan, 'annual')
    
    monthly_equivalent = monthly_price * 12
    savings_amount = monthly_equivalent - annual_price
    savings_percentage = (savings_amount / monthly_equivalent) * 100
    
    return annual_price, monthly_equivalent, savings_amount, savings_percentage


# Plan metadata
PLANS = {
    'basic': {
        'name': 'Basic',
        'description': 'Perfect for single shop owners',
        'monthly_price': 2000,
        'annual_price': 20000,
        'features': [
            'Stock management',
            'Cashbook & Khata',
            'Expense tracking',
            'Profit/loss reports',
            'Email support',
        ]
    },
    'premium': {
        'name': 'Premium',
        'description': 'For shops with investors & partners',
        'monthly_price': 3500,
        'annual_price': 35000,
        'features': [
            'Everything in Basic',
            'Shareholder profit-split',
            'Investor portal',
            'Phone funding tracking',
            'Priority support',
        ]
    }
}
