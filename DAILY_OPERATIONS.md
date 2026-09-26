# 📋 Daily Operations Guide

Quick reference for managing Mubashar's Book day-to-day.

---

## 🌅 Morning Routine (5 minutes)

### 1. Check Pending Payments
```
1. Go to: http://localhost:5050/admin
2. Look for red badge on "💳 Pending Payments"
3. If badge shows number, click to review
```

### 2. Verify Payments
For each pending payment:
- ✅ Check screenshot is clear
- ✅ Verify amount matches plan
- ✅ Click "Verify & Activate" or "Reject"

### 3. Check Email Logs (Optional)
```
1. Click "📬 Email Logs"
2. Check if any emails failed
3. If failures: check SMTP settings
```

---

## 👥 When New User Signs Up

**Automatic:**
1. ✅ Verification email sent
2. ✅ User verifies email
3. ✅ Trial starts (7 days)
4. ✅ Welcome email sent

**No action needed from you!**

---

## 💳 When User Submits Payment

**Automatic:**
1. ✅ Payment recorded in database
2. ✅ Screenshot saved
3. ✅ "Payment received" email sent to user
4. ✅ Red badge appears on your admin dashboard

**Your action (within 24 hours):**
1. Login to admin panel
2. Click "Pending Payments"
3. Review payment proof
4. Verify or reject

**After you verify:**
1. ✅ Subscription activated automatically
2. ✅ "Payment verified" email sent to user
3. ✅ User can now use full features

---

## ⏰ Automated Daily Tasks

These run automatically (no action needed):

### 9:00 AM - Trial Reminders
- Users with 3 days left → Email sent
- Users with 1 day left → Urgent email sent
- Check logs: "Running trial reminder check..."

### 12:00 AM (Midnight) - Trial Expiry
- Expired trials → Marked as expired
- Grace period activated (3 days)
- "Trial expired" email sent
- Check logs: "Running trial expiry check..."

### 3:00 AM - Renewal Prep
- Finds subscriptions expiring soon
- Prepares for renewal (placeholder for future payment gateway)

---

## 🔍 Common User Questions

### "How do I subscribe?"
```
1. Click "My Subscription" in sidebar
2. Choose plan (Basic or Premium)
3. Transfer money to NayaPay: 03129347067
4. Upload screenshot
5. Wait 24 hours for verification
```

### "How long until activation?"
```
"Within 24 hours after payment verification"
```

### "Which plan should I choose?"
```
- Basic (Rs 2,000): Single shop, no partners
- Premium (Rs 3,500): With shareholders/investors
```

### "Payment methods?"
```
Currently accepting:
- NayaPay: 03129347067
- EasyPaisa/JazzCash: Same number
- Bank Transfer: (Add IBAN to .env if needed)
```

### "Can I pay monthly?"
```
Yes! Both monthly and annual billing available.
Annual saves ~17%
```

---

## 📊 Quick Stats (Where to Find)

### Admin Dashboard Shows:
- Total users
- Trial users
- Active paid users
- Expired users
- Suspended users
- New signups (last 7 days)
- Total revenue
- Pending payments count (red badge)

### Email Logs Shows:
- All emails sent
- Success/failure status
- Filter by type and date

---

## 🚨 If Something Goes Wrong

### Email not sending?
```bash
1. Check email logs: /admin/email-logs
2. Look for error message
3. Verify SMTP settings in .env:
   - MAIL_USERNAME=mubasharmalik2014@gmail.com
   - MAIL_PASSWORD=ksaadpqsipmdivbm
4. Restart Flask
```

### Scheduler not running?
```bash
1. Check Flask console for:
   "Background scheduler started with 3 jobs"
2. If missing, check .env:
   SCHEDULER_ENABLED=True
3. Restart Flask
```

### Payment proof image not showing?
```bash
1. Check folder exists: app/static/payment_proofs/
2. Check file was uploaded
3. Restart Flask
4. Check browser console for errors
```

### User says "Can't login"?
```
1. Check if email verified
2. Go to /admin → Find user
3. Check "Email Verified" badge
4. If not verified, can manually verify:
   - Send new verification email
   - Or mark verified in database
```

### User says "Trial expired but paid"?
```
1. Go to /admin/pending-payments
2. Find their payment
3. Click "Verify & Activate"
4. Subscription activates immediately
```

---

## 🛠️ Admin Commands (Terminal)

### Make User Admin:
```bash
flask make-admin user@example.com
```

### Remove Admin Rights:
```bash
flask remove-admin user@example.com
```

### List All Admins:
```bash
flask list-admins
```

### Extend Trial (Manual):
```bash
flask shell
>>> from app import db
>>> from app.models.user import User
>>> user = User.query.filter_by(email='user@example.com').first()
>>> user.shop.subscription.trial_end += timedelta(days=7)
>>> db.session.commit()
```

### Send Test Email:
```
Use admin panel: /admin/test-email
No terminal needed!
```

---

## 📱 User Access URLs

### For Regular Users:
```
Signup:           http://localhost:5050/auth/signup
Login:            http://localhost:5050/auth/login
Dashboard:        http://localhost:5050/dashboard
My Subscription:  http://localhost:5050/subscription/my-subscription
Subscribe:        http://localhost:5050/subscription/subscribe
```

### For Admin:
```
Admin Dashboard:     http://localhost:5050/admin
Pending Payments:    http://localhost:5050/admin/pending-payments
Email Logs:          http://localhost:5050/admin/email-logs
User Details:        http://localhost:5050/admin/user/{id}
```

### For Investors:
```
Investor Login:   http://localhost:5050/investor/login
Dashboard:        http://localhost:5050/investor/dashboard
```

---

## 💰 Revenue Tracking

### Check Total Revenue:
- Admin Dashboard → "Total Revenue" card
- Shows sum of all completed payments

### Check Revenue by User:
1. Go to: /admin
2. Click on user name
3. Scroll to "Payment History"
4. See all their payments

### Export Revenue Data:
```bash
# Future feature - not implemented yet
# For now: Check admin dashboard or database
```

---

## 🔐 Security Checklist (Weekly)

- [ ] Check email logs for suspicious activity
- [ ] Review recent admin actions in user detail pages
- [ ] Verify payment proof images are legitimate
- [ ] Check for users with unusual patterns
- [ ] Review failed login attempts (future feature)

---

## 📅 Monthly Tasks

### 1st of Month:
- Review previous month revenue
- Check trial to paid conversion rate
- Note: Users who expired but didn't subscribe

### User Retention:
- Check: Users with expired trials
- Consider: Re-engagement email (future feature)
- Maybe: Discount offer for comeback

### System Health:
- Check: Email delivery rate in logs
- Check: Any failed automated jobs in console
- Check: Database size (if growing too large)

---

## 📞 Quick Contact Templates

### Verify Payment (WhatsApp/SMS):
```
Hi! I've verified your payment for Mubashar's Book. Your subscription is now active. You can login and start using all features. Let me know if you need any help!
```

### Reject Payment (WhatsApp/SMS):
```
Hi! I checked your payment for Mubashar's Book but [REASON]. Please upload a new screenshot showing [DETAILS]. Thanks!
```

### Trial Ending Soon (WhatsApp/SMS):
```
Hi! Your 7-day trial ends soon. To keep using Mubashar's Book, subscribe now: http://localhost:5050/subscription/subscribe

Plans:
- Basic: Rs 2,000/month
- Premium: Rs 3,500/month
```

---

## 🎯 Success Metrics to Track

### Weekly:
- New signups
- Trial users
- Paid conversions
- Pending payments (should be low)

### Monthly:
- Total active users
- Total revenue
- Trial to paid conversion rate
- Churn rate (users who didn't renew)

---

## ✅ End of Day Checklist

- [ ] All pending payments verified (or scheduled for tomorrow)
- [ ] No failed emails that need attention
- [ ] No urgent user issues
- [ ] Flask still running (check console)
- [ ] Scheduler active (look for job logs)

---

## 🚀 Growth Tips

### Encourage Upgrades (Basic → Premium):
- Show shareholder features in app
- Highlight investor portal benefits
- Offer smooth transition (prorated)

### Reduce Churn:
- Send reminders 3 days before expiry (already automated!)
- Offer annual plans (save 17%)
- Quick support response

### Get Testimonials:
- Ask happy users for feedback
- Share success stories
- Build trust with new users

---

## 📞 Support Info

### Your Email:
mubasharmalik2014@gmail.com

### Payment Number:
03129347067 (NayaPay)

### Admin Login:
http://localhost:5050/admin

---

**Remember:** 
- Trial reminders are automatic
- Payment emails are automatic
- You only need to verify payments manually
- Everything else runs on autopilot!

**Your daily task is just:**
Check pending payments + Verify them = Done! ✅

---

**Last Updated:** 2026-09-26  
**System:** Mubashar's Book  
**Status:** Fully Operational 🚀
