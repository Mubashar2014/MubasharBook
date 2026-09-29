# Admin Panel Setup Complete ✅

> **How to use the panel, day to day → see [`ADMIN_GUIDE.md`](ADMIN_GUIDE.md).**
> This file is the build/setup reference; the guide is the walkthrough.

## What's Been Built

### 1. Admin Authentication & Middleware
- ✅ `@admin_required` decorator for route protection
- ✅ Checks if user is logged in and has `is_admin=True`
- ✅ Redirects to login or shows 403 if not authorized
- ✅ Admins are force-redirected off every non-admin page

### 2. Layout & Navigation
- ✅ Sidebar layout (`admin_layout.html`) extending `base.html`, same `.sidebar`
  markup as the main app
- ✅ Grouped sections: Manage / Operations / Email / Audit / Account
- ✅ Pending-payment count badge (injected by a blueprint context processor)
- ✅ Flash messages, topbar title, and "active page" highlight on every page

### 3. Overview (`/admin/`)
- ✅ Headline stats: total users, trial, active, expired, suspended, new
  signups, revenue
- ✅ Status counts exclude admin accounts, so the breakdown equals Total Users
- ✅ "Needs attention": pending payments, expired subscriptions, trials
  ending within 3 days (with overdue badges)
- ✅ Recent signups and recent admin activity

### 4. Users (`/admin/users`)
- ✅ Searchable list, 50 per page
- ✅ Search by name, email, phone, or shop name (case-insensitive)
- ✅ Filter by subscription status (trial / active / expired / suspended)
- ✅ Subscription badges and last-login tracking
- ✅ Back link from a user preserves search, filter, and page

### 5. User Detail Page (`/admin/user/<id>`)
- ✅ Complete user information, shop details, subscription status
- ✅ Payment history
- ✅ Per-user admin activity log (last 20)
- ✅ Row counts + revenue impact for deletion

### 6. Admin Actions
#### Extend Trial
- Add X days to user's trial period
- Works for active trials or reactivates expired trials
- Logs action in admin_logs table

#### Quick Activate
- Plan (basic/premium) + duration (1/2/3/6/12 months, or custom days)
- Calendar-accurate end date; **no** payment record is created
- Logs action

#### Activate Subscription (Manual Payment)
- Activate paid subscription for users who paid via bank transfer
- Create payment record
- Choose payment method (bank transfer, JazzCash, EasyPaisa, cash)
- Add optional notes
- Logs action

#### Suspend/Unsuspend User
- Suspend account with reason
- Unsuspend previously suspended accounts
- Logs all actions

### 7. Delete User Permanently (`POST /admin/user/<id>/delete`)
- Hard-deletes every row the user owns: shop, subscription, payments,
  investors, partners, split rules, periods, snapshots, stock, cashbook,
  expenses + categories, khata, notifications, email logs — plus the
  uploaded payment-proof files on disk
- Type-to-confirm (email, falling back to phone) before the button enables
- Blocked for admin accounts and for your own account
- Writes the audit row **before** the purge, so the Activity Log survives
- Shows the row counts and revenue impact up front in a modal

### 8. Payments, Email & Activity pages
- ✅ `/admin/pending-payments` — verify or reject uploaded proofs
  (verification activates the subscription and emails the customer)
- ✅ `/admin/email-logs` — sent/failed/pending history, filterable
- ✅ `/admin/test-email` — send one test email of any type
- ✅ `/admin/activity` — every admin action, filter by action and by admin

### 9. Admin Activity Logging
- Every admin action is logged with:
  - Admin user ID
  - Action type
  - Description
  - Target (user/subscription)
  - IP address
  - User agent
  - Timestamp
  - Optional `changes` JSON (row counts/revenue for deletions)

## How to Use

### 1. Make Yourself Admin
```bash
python -m flask make-admin your-email@example.com
```

**Important:** The admin account should be separate from shop owner accounts. Create a new account just for admin purposes, or use an existing account and promote it to admin.

### 2. Login & Access Admin Panel
- Login with your admin account
- You'll be **automatically redirected** to: `http://localhost:5050/admin/`
- Admin users cannot access the regular app (stock, cashbook, etc.)
- Admin users have a clean, separate interface

### 3. Manage Users
- **Search**: Find users by name, email, phone, or shop name
- **Filter**: View only trial/active/expired/suspended users
- **View Details**: Click "View" to see full user information

### 4. Common Tasks

#### Extend a Tester's Trial
1. Go to user detail page
2. Find "Extend Trial" card
3. Enter number of days (default: 7)
4. Click "Extend Trial"

#### Activate Paid Subscription (Bank Transfer)
1. Go to user detail page
2. Find "Activate Paid Subscription" card
3. Enter amount (e.g., 500)
4. Select payment method
5. Add notes (optional, e.g., "Bank transfer ref: 123456")
6. Click "Activate Subscription"

#### Suspend Problematic User
1. Go to user detail page
2. Find "Account Status" card
3. Enter suspension reason
4. Click "Suspend Account"

## Quick Fixes Applied

### 1. Login Tracking ✅
- `user.mark_login()` is now called on successful login
- Last login timestamp is recorded

### 2. Email Verification ✅
- Using `user.verify_email()` method
- Sets `email_verified_at` timestamp

## What's Next

### Priority 2: Email Notifications
- Trial reminder emails (3 days, 1 day before expiry)
- Email logging integration
- Admin broadcast emails

### Priority 3: Enhanced Admin Features
- Export users to CSV
- Bulk actions
- Revenue analytics graphs
- User activity tracking

## Files Created

```
app/admin/
├── __init__.py           # Blueprint initialization
├── middleware.py         # @admin_required decorator
└── routes.py            # All admin routes (incl. hard user delete)

app/templates/
├── admin_layout.html     # Sidebar layout extending base.html
└── admin/
    ├── dashboard.html    # Overview page
    ├── users.html        # Searchable user list
    ├── user_detail.html  # User detail + Danger Zone delete
    ├── pending_payments.html
    ├── email_logs.html
    ├── test_email.html
    └── activity.html     # Global audit log

tests/test_admin_nav.py            # Navigation / IA / stat tests
tests/test_admin_delete_user.py    # Delete-user safety tests

ADMIN_GUIDE.md           # Day-to-day admin walkthrough
manage.py                # CLI commands for admin management
```

## Testing Checklist

- [ ] Make yourself admin with CLI command
- [ ] Login and access `/admin/`
- [ ] View dashboard statistics
- [ ] Search for a user
- [ ] Filter by subscription status
- [ ] View user detail page
- [ ] Extend a user's trial
- [ ] Quick activate a subscription
- [ ] Manually activate a subscription
- [ ] Check payment record was created
- [ ] Check admin action was logged
- [ ] Suspend a user
- [ ] Unsuspend a user
- [ ] Verify / reject a pending payment
- [ ] Send a test email and see it in Email Logs
- [ ] Filter the Activity Log
- [ ] Delete a test user (wrong confirmation must delete nothing)
- [ ] Confirm admin and self deletion are blocked

Run them with:

```bash
python -m pytest tests -q
```

## Notes

- Admin users are excluded from the user list and from every Overview stat
- All admin actions are logged for audit purposes
- Pagination shows 50 users per page
- Search is case-insensitive
- Trial countdown shows on Overview and detail pages
