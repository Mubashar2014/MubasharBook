# Subscription Management System - Requirements

## Overview
Transform Mubashar's Book from a trial-based system to a full subscription management platform with payment integration, email verification, password reset, and admin panel capabilities.

## Business Goals
1. Enable users to subscribe directly without mandatory trial period
2. Automate payment collection and subscription renewals
3. Provide email verification for security
4. Enable password reset functionality
5. Give admin complete control over user management
6. Track subscription metrics and revenue

---

## User Stories & Acceptance Criteria

### 1. User Registration & Onboarding

#### 1.1 Signup with Trial Option
**As a new user**  
**I want to** choose between starting a free trial or subscribing immediately  
**So that** I can use the app according to my preference

**Acceptance Criteria:**
- [ ] Signup page shows two clear options: "Start 7-Day Free Trial" and "Subscribe Now"
- [ ] Both options require email verification before access
- [ ] Trial option creates account with 7-day trial status
- [ ] Subscribe option redirects to payment page after signup
- [ ] User data is saved but account remains inactive until email is verified
- [ ] User receives verification email immediately after signup

#### 1.2 Email Verification Required
**As a new user**  
**I want to** verify my email before accessing the app  
**So that** my account is secure and my email is confirmed

**Acceptance Criteria:**
- [ ] After signup, user sees "Check your email" page
- [ ] Verification email contains clickable link valid for 24 hours
- [ ] Clicking link activates account and redirects to login (trial) or payment (subscribe)
- [ ] User cannot login until email is verified
- [ ] "Resend verification email" option available with rate limiting (max 3 per hour)
- [ ] Expired verification links show clear error message

#### 1.3 Onboarding Payment Flow
**As a new user who chose to subscribe**  
**I want to** complete payment during signup  
**So that** I can start using the app immediately without trial

**Acceptance Criteria:**
- [ ] After email verification, user is redirected to payment page
- [ ] Payment page shows plan details (price, features, billing cycle)
- [ ] Multiple payment methods supported (card, mobile wallet, bank transfer)
- [ ] Successful payment activates subscription immediately
- [ ] Failed payment allows retry without creating duplicate account
- [ ] User receives payment confirmation email

---

### 2. Subscription Plans & Pricing

#### 2.1 Plan Management
**As the system**  
**I want to** support multiple subscription plans  
**So that** users can choose the plan that fits their needs

**Acceptance Criteria:**
- [ ] Basic Plan: Rs 500/month - Single shop, basic features
- [ ] Premium Plan: Rs 1000/month - Multi-shop, advanced features
- [ ] Plan details stored in database (name, price, features, billing_cycle)
- [ ] Plans can be activated/deactivated by admin
- [ ] Price changes don't affect existing subscribers until renewal

#### 2.2 Billing Cycles
**As a user**  
**I want to** choose between monthly and annual billing  
**So that** I can save money with annual subscription

**Acceptance Criteria:**
- [ ] Monthly billing: Full price per month
- [ ] Annual billing: 20% discount (10 months price for 12 months)
- [ ] Clear display of savings for annual plan
- [ ] Billing cycle cannot be changed mid-period
- [ ] Pro-rated refunds not supported (use remaining days)

---

### 3. Payment Integration

#### 3.1 Payment Gateway Integration
**As a user**  
**I want to** pay securely using local payment methods  
**So that** I can subscribe easily

**Acceptance Criteria:**
- [ ] Integration with Pakistani payment gateway (JazzCash, EasyPaisa, or Stripe)
- [ ] Support credit/debit cards
- [ ] Support mobile wallets (JazzCash, EasyPaisa)
- [ ] Support bank transfers with verification
- [ ] PCI-DSS compliant payment handling
- [ ] No card details stored in our database

#### 3.2 Payment Processing
**As the system**  
**I want to** handle payments securely and reliably  
**So that** subscriptions are activated correctly

**Acceptance Criteria:**
- [ ] Payment creates transaction record in database
- [ ] Successful payment activates subscription immediately
- [ ] Failed payment sends user to retry page
- [ ] Payment webhooks update subscription status automatically
- [ ] Manual payment verification by admin (for bank transfers)
- [ ] Payment receipt sent via email

#### 3.3 Recurring Payments
**As a subscriber**  
**I want** my subscription to renew automatically  
**So that** I don't lose access due to forgotten payment

**Acceptance Criteria:**
- [ ] Auto-renewal enabled by default for card payments
- [ ] Renewal attempted 3 days before expiry
- [ ] Failed renewal sends notification email
- [ ] Grace period of 3 days after expiry before account locks
- [ ] Multiple retry attempts for failed payments
- [ ] User can disable auto-renewal from settings

---

### 4. Subscription Status Management

#### 4.1 Subscription States
**As the system**  
**I want to** track subscription status accurately  
**So that** access control works correctly

**Acceptance Criteria:**
- [ ] States: `pending`, `trial`, `active`, `expired`, `cancelled`, `suspended`
- [ ] `pending`: Email not verified OR payment pending
- [ ] `trial`: 7-day trial active
- [ ] `active`: Paid subscription active
- [ ] `expired`: Payment failed or not renewed
- [ ] `cancelled`: User cancelled subscription
- [ ] `suspended`: Admin suspended account
- [ ] State transitions logged with timestamp

#### 4.2 Trial to Paid Conversion
**As a trial user**  
**I want to** upgrade to paid subscription before trial ends  
**So that** I can continue using the app without interruption

**Acceptance Criteria:**
- [ ] "Upgrade to Premium" button visible during trial
- [ ] Trial users see days remaining in dashboard
- [ ] Upgrading mid-trial converts immediately
- [ ] Remaining trial days not credited (clean cutover)
- [ ] User receives upgrade confirmation email

#### 4.3 Expiry & Grace Period
**As a user whose subscription expired**  
**I want** a grace period to renew  
**So that** I don't lose my data immediately

**Acceptance Criteria:**
- [ ] 3-day grace period after subscription expiry
- [ ] During grace: Read-only access (view data, cannot add/edit)
- [ ] Grace period shows countdown banner
- [ ] After grace: Account locked, login redirects to payment page
- [ ] Data retained for 30 days after lock
- [ ] Renewal during grace/lock restores full access immediately

---

### 5. Email System

#### 5.1 Transactional Emails
**As a user**  
**I want to** receive important emails about my account  
**So that** I stay informed

**Acceptance Criteria:**
- [ ] Welcome email after signup (with verification link)
- [ ] Email verification success notification
- [ ] Payment receipt email
- [ ] Subscription activation email
- [ ] Trial ending reminder (3 days, 1 day before)
- [ ] Subscription renewal success
- [ ] Payment failed notification
- [ ] Account suspended/cancelled notification
- [ ] Password reset email
- [ ] All emails have professional design matching brand

#### 5.2 Email Delivery Infrastructure
**As the system**  
**I want to** send emails reliably  
**So that** users receive critical notifications

**Acceptance Criteria:**
- [ ] SMTP integration with reliable provider (SendGrid, AWS SES, Mailgun)
- [ ] Email sending queue for reliability
- [ ] Retry logic for failed sends
- [ ] Email logs stored in database
- [ ] Bounce/spam complaints tracked
- [ ] Unsubscribe link for marketing emails (not transactional)

---

### 6. Password Management

#### 6.1 Password Reset Flow
**As a user who forgot password**  
**I want to** reset my password securely  
**So that** I can regain access to my account

**Acceptance Criteria:**
- [ ] "Forgot Password" link on login page
- [ ] User enters email address
- [ ] Reset email sent with token link (valid 1 hour)
- [ ] Reset page allows setting new password
- [ ] Password requirements enforced (min 8 chars)
- [ ] Token expires after use or 1 hour
- [ ] Success message after reset, redirect to login
- [ ] Rate limiting: max 3 reset requests per hour per email

#### 6.2 Password Change (Logged In)
**As a logged-in user**  
**I want to** change my password  
**So that** I can keep my account secure

**Acceptance Criteria:**
- [ ] Password change option in settings
- [ ] Must enter current password to confirm
- [ ] New password must meet requirements
- [ ] Confirmation email sent after change
- [ ] User remains logged in after change
- [ ] All other sessions logged out (security)

---

### 7. Admin Panel

#### 7.1 Admin Authentication
**As an admin**  
**I want to** access admin panel securely  
**So that** I can manage the platform

**Acceptance Criteria:**
- [ ] Separate admin login at `/admin/login`
- [ ] Admin role flag in User model
- [ ] Admin middleware protects all admin routes
- [ ] Admin sessions separate from user sessions
- [ ] Admin login logs tracked
- [ ] 2FA optional for admin accounts

#### 7.2 User Management
**As an admin**  
**I want to** view and manage all users  
**So that** I can provide support and moderate accounts

**Acceptance Criteria:**
- [ ] User list with search and filters
- [ ] Filter by: status, plan, join date, trial/paid
- [ ] Search by: name, email, phone, shop name
- [ ] View user details: account info, subscription, payment history
- [ ] Actions: Suspend, Unsuspend, Delete, Reset password
- [ ] Activity log per user (logins, payments, changes)
- [ ] Bulk actions: export, send email
- [ ] Pagination (50 users per page)

#### 7.3 Subscription Management
**As an admin**  
**I want to** manage subscriptions  
**So that** I can handle special cases and support issues

**Acceptance Criteria:**
- [ ] View all subscriptions with status
- [ ] Extend subscription (add days/months)
- [ ] Cancel subscription
- [ ] Refund and cancel
- [ ] Manually activate subscription (for bank transfer)
- [ ] Change plan (upgrade/downgrade)
- [ ] Add notes to subscription record
- [ ] View subscription history

#### 7.4 Payment Management
**As an admin**  
**I want to** manage payments and transactions  
**So that** I can resolve payment issues

**Acceptance Criteria:**
- [ ] View all transactions with filters
- [ ] Filter by: status, date range, amount, method
- [ ] Transaction details: user, amount, method, status, gateway response
- [ ] Mark manual payment as verified (bank transfers)
- [ ] Issue refunds (with reason)
- [ ] Export payment reports (CSV, Excel)
- [ ] Monthly revenue dashboard

#### 7.5 Platform Analytics
**As an admin**  
**I want to** see platform metrics  
**So that** I can track business performance

**Acceptance Criteria:**
- [ ] Dashboard with key metrics:
  - Total users (active, trial, expired)
  - Monthly Recurring Revenue (MRR)
  - Churn rate
  - Trial to paid conversion rate
  - New signups today/week/month
  - Payment success rate
- [ ] Graphs: signups over time, revenue over time
- [ ] Plan distribution (Basic vs Premium)
- [ ] Top users by spend
- [ ] Exportable reports

#### 7.6 Email Management
**As an admin**  
**I want to** manage email communications  
**So that** I can send announcements and troubleshoot delivery

**Acceptance Criteria:**
- [ ] Email log with search
- [ ] Filter by: type, status, recipient
- [ ] View email content and delivery status
- [ ] Resend failed emails
- [ ] Send broadcast email to users (filter by plan/status)
- [ ] Email templates management
- [ ] Bounce and complaint tracking

---

### 8. User Account Settings

#### 8.1 Subscription Settings
**As a user**  
**I want to** manage my subscription  
**So that** I have control over billing

**Acceptance Criteria:**
- [ ] View current plan and billing cycle
- [ ] View next billing date and amount
- [ ] Upgrade/downgrade plan
- [ ] Change billing cycle (at renewal)
- [ ] Update payment method
- [ ] View payment history
- [ ] Download invoices/receipts
- [ ] Enable/disable auto-renewal
- [ ] Cancel subscription (with confirmation)

#### 8.2 Profile Settings
**As a user**  
**I want to** manage my profile  
**So that** my information is current

**Acceptance Criteria:**
- [ ] Update name, phone
- [ ] Email change requires re-verification
- [ ] Change password
- [ ] Change language preference
- [ ] Update shop details
- [ ] Delete account (with confirmation, exports data)

---

### 9. Notifications & Alerts

#### 9.1 In-App Notifications
**As a user**  
**I want to** see important alerts in the app  
**So that** I don't miss critical information

**Acceptance Criteria:**
- [ ] Trial ending soon (3 days, 1 day)
- [ ] Subscription expiring soon (5 days, 1 day)
- [ ] Payment failed
- [ ] Account locked (grace period ended)
- [ ] Dismissible notification banner
- [ ] Notification history page

---

### 10. Security & Compliance

#### 10.1 Data Security
**As the system**  
**I want to** protect user data  
**So that** users trust the platform

**Acceptance Criteria:**
- [ ] All passwords hashed with bcrypt
- [ ] HTTPS enforced in production
- [ ] CSRF protection on all forms
- [ ] SQL injection prevention (parameterized queries)
- [ ] XSS protection (escaped outputs)
- [ ] Rate limiting on sensitive endpoints
- [ ] Session timeout after 30 days inactivity
- [ ] Secure cookie settings

#### 10.2 Data Privacy
**As a user**  
**I want** my data to be private  
**So that** I comply with regulations

**Acceptance Criteria:**
- [ ] Privacy policy page
- [ ] Terms of service page
- [ ] Data export feature (download all my data)
- [ ] Account deletion with data removal
- [ ] No data shared with third parties
- [ ] Audit logs for admin access to user data

---

## Payment Gateway Options (Pakistan)

### Option 1: JazzCash/EasyPaisa (Recommended for Pakistan)
**Pros:**
- Widely used in Pakistan
- Mobile wallet + card support
- Local customer support
- Lower transaction fees (2-3%)

**Cons:**
- Integration complexity
- Less international support

### Option 2: Stripe (International Standard)
**Pros:**
- Best developer experience
- Excellent documentation
- Automatic recurring billing
- Supports Pakistani cards

**Cons:**
- Higher fees (2.9% + Rs30)
- Bank account required outside Pakistan

### Option 3: PayFast (Hybrid)
**Pros:**
- Pakistani + international cards
- Multiple payment methods
- Good API

**Cons:**
- Moderate fees
- Less known

**Recommendation:** Start with **JazzCash/EasyPaisa** for local market, add Stripe later for international expansion.

---

## Technical Requirements

### Database Changes Required
1. **Users table:**
   - Add `is_admin` boolean column
   - Add `email_verified_at` timestamp
   - Add `last_login_at` timestamp
   
2. **Subscriptions table:**
   - Add `payment_method` (card, wallet, bank)
   - Add `auto_renew` boolean
   - Add `cancelled_at` timestamp
   - Add `grace_period_end` timestamp
   
3. **New tables:**
   - `payments`: Track all transactions
   - `admin_logs`: Track admin actions
   - `email_logs`: Track email delivery
   - `notifications`: In-app notifications

### Email Infrastructure
- SMTP provider: SendGrid, Mailgun, or AWS SES
- Email templates: HTML + plain text
- Queue system for async sending

### Payment Gateway Integration
- Webhook endpoints for payment status
- Secure API key storage
- Test mode for development
- Production mode for live

---

## Implementation Phases

### Phase 1: Foundation (Week 1-2)
- Database migrations
- Email infrastructure setup
- Email verification flow
- Password reset flow

### Phase 2: Payment Integration (Week 2-3)
- Payment gateway integration (test mode)
- Subscription activation logic
- Payment webhook handling
- Receipt generation

### Phase 3: Admin Panel (Week 3-4)
- Admin authentication
- User management interface
- Subscription management
- Payment management
- Basic analytics

### Phase 4: User Experience (Week 4-5)
- Signup flow refinement
- Subscription settings page
- In-app notifications
- Email notifications

### Phase 5: Testing & Launch (Week 5-6)
- End-to-end testing
- Security audit
- Payment testing (live mode)
- Production deployment
- Monitoring setup

---

## Success Metrics
- 30%+ trial to paid conversion rate
- <5% churn rate monthly
- 95%+ payment success rate
- <1 hour average support response time
- 99.9% uptime

---

## Open Questions & Decisions Needed

1. **Which payment gateway to integrate first?**
   - JazzCash/EasyPaisa (local)
   - Stripe (international)
   - Both?

2. **Free trial mandatory or optional?**
   - Always require trial
   - Make trial optional
   - No trial, direct subscribe only

3. **Pricing strategy?**
   - Single plan or multiple tiers?
   - Monthly only or annual option?
   - Price points? (Rs 500/mo? Rs 1000/mo?)

4. **Email provider?**
   - SendGrid (recommended)
   - Mailgun
   - AWS SES
   - Gmail SMTP (development only)

5. **Admin access control?**
   - Single admin account
   - Multiple admin levels (super admin, support admin)
   - Role-based permissions

6. **Data retention policy?**
   - How long to keep cancelled accounts?
   - Automatic deletion after X days?
   - Paid data backup service?

---

## Next Steps
1. Review and approve requirements
2. Decide on payment gateway
3. Decide on pricing plans
4. Choose email provider
5. Create detailed design document
6. Begin Phase 1 implementation
