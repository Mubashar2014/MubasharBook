# 💰 Mubashar's Book Pricing

## Plans & Pricing (PKR)

### Basic Plan
**Rs 2,000 per month**  
**Rs 20,000 per year** (Save ~17% - equivalent to 10 months)

**Perfect for:** Single shop owners

**Includes:**
- ✅ Stock management (unlimited phones)
- ✅ Cashbook with auto-generated entries
- ✅ Khata for receivables/payables
- ✅ Expense tracking by category
- ✅ Profit & Loss reports
- ✅ Daily & monthly net balance
- ✅ Mobile-friendly design
- ✅ Email support
- ❌ Shareholder profit-split
- ❌ Investor portal
- ❌ Priority support

---

### Premium Plan
**Rs 3,500 per month**  
**Rs 35,000 per year** (Save ~17% - equivalent to 10 months)

**Perfect for:** Shops with investors & partners

**Includes:**
- ✅ **Everything in Basic Plan**
- ✅ Shareholder profit-split engine
- ✅ Investor portal accounts
- ✅ Phone funding tracking (who funded which phone)
- ✅ Profit distribution per Shariah rules
- ✅ Period locking for transparency
- ✅ Priority email support

---

## Trial Period

**7 Days Free Trial**
- No credit card required
- Full access to all features
- Email verification required
- Automatic expiry after 7 days
- Account becomes read-only after trial

---

## Payment Methods (Coming Soon)

### Option 1: Online Payment
- Credit/Debit Card (Stripe)
- JazzCash
- EasyPaisa

### Option 2: Bank Transfer
- Manual verification by admin
- Payment proof required
- Activation within 24 hours

---

## Billing

### Monthly Billing
- Charged on the same day each month
- Auto-renewal by default
- Cancel anytime
- No refunds for partial months

### Annual Billing
- Charged once per year
- Save ~17% compared to monthly
- Auto-renewal by default
- Cancel anytime
- No refunds for unused months

---

## Grace Period

**3 Days** after subscription expiry:
- Account remains accessible (read-only)
- Cannot add new entries
- Can view all existing data
- Email reminders sent
- Subscription can be renewed

After grace period:
- Account locked
- Data preserved
- Reactivate anytime by subscribing

---

## Refund Policy

**No refunds** for:
- Unused trial days
- Partial months
- Annual subscriptions (unused months)

**Exception:**
- Technical issues preventing app usage
- Billed in error
- Contact support for review

---

## Cancellation

**Can cancel anytime:**
- No questions asked
- Account remains active until period end
- Data preserved for 30 days
- Reactivate by subscribing again
- Auto-renewal stops

---

## Data Retention

**Active Subscription:**
- All data stored indefinitely
- Regular backups
- Full access 24/7

**After Cancellation:**
- Data preserved for **30 days**
- Read-only access during grace period
- Can reactivate and restore
- After 30 days: data deleted permanently

---

## Price Lock Guarantee

**Current prices locked:**
- Existing subscribers keep their price
- Price increases don't apply to current users
- Only new signups pay new prices
- Cancel and rejoin = new price applies

---

## Frequently Asked Questions

### Can I switch plans?
Yes, anytime:
- **Upgrade (Basic → Premium):** Immediate access, prorated charge
- **Downgrade (Premium → Basic):** Takes effect next billing cycle

### What happens if payment fails?
1. Email notification sent
2. 3-day grace period activated
3. Account becomes read-only
4. Update payment method to reactivate

### Can I get a discount?
- **Annual billing:** ~17% savings
- **Volume discounts:** Contact for multiple shops
- **Special offers:** Subscribe to newsletter

### Is there a free plan?
- No free plan after trial
- 7-day free trial available
- All features included in trial

### What payment methods do you accept?
**Coming soon:**
- Credit/Debit cards (Stripe)
- JazzCash
- EasyPaisa
- Bank transfer (manual verification)

**Currently:**
- Manual bank transfer only
- Contact admin for activation

---

## Implementation Status

### ✅ Implemented:
- Trial system (7 days)
- Trial reminder emails
- Trial expiry automation
- Grace period system
- Read-only enforcement
- Admin manual activation

### 🚧 Coming Soon:
- Online payment integration
- Auto-renewal system
- Plan upgrade/downgrade
- User subscription settings page
- Payment receipts
- Invoice generation

---

## Technical Details

### Price Configuration

**In `app/config.py`:**
```python
BASIC_PLAN_PRICE_MONTHLY = 2000
BASIC_PLAN_PRICE_ANNUAL = 20000
PREMIUM_PLAN_PRICE_MONTHLY = 3500
PREMIUM_PLAN_PRICE_ANNUAL = 35000
```

### Helper Functions

**In `app/utils/pricing.py`:**
```python
get_plan_price(plan, billing_cycle)
format_price(amount)
get_plan_features(plan)
calculate_savings(plan)
```

---

## Pricing Updated

**Last Updated:** 2026-09-26

**Changes:**
- Basic: Rs 2,000/month (was Rs 500)
- Premium: Rs 3,500/month (was Rs 500)
- Annual pricing added
- Email templates updated
- Landing page updated
- Config updated

---

## Contact

**Questions about pricing?**
- Email: support@mubasharsbook.com
- WhatsApp: [Coming soon]
- Reply to any automated email

---

**Ready to start?**  
[Start 7-day free trial](http://localhost:5050/auth/signup) →

