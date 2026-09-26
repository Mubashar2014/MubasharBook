# Email Setup Guide

## 📧 Email Verification & Notification System

The email system is now enabled! Here's how to configure it.

---

## ⚙️ Email Configuration

### Step 1: Choose Email Provider

#### Option A: Gmail (For Testing/Development)

**Pros:**
- Free
- Easy to set up
- Good for testing

**Cons:**
- 500 emails/day limit
- Less reliable deliverability
- May block you if sending too many

**Setup Steps:**

1. **Enable 2-Factor Authentication** on your Gmail account:
   - Go to https://myaccount.google.com/security
   - Enable 2-Step Verification

2. **Create App Password**:
   - Go to https://myaccount.google.com/apppasswords
   - Select "Mail" and "Other (Custom name)"
   - Name it "Mubashars Book"
   - Copy the 16-character password

3. **Update `.env` file**:
   ```env
   MAIL_SERVER=smtp.gmail.com
   MAIL_PORT=587
   MAIL_USE_TLS=True
   MAIL_USERNAME=your-gmail@gmail.com
   MAIL_PASSWORD=your-app-password-here  # 16-char app password
   MAIL_DEFAULT_SENDER=noreply@yourdomain.com
   BASE_URL=http://localhost:5050
   ```

---

#### Option B: SendGrid (Recommended for Production)

**Pros:**
- 100 free emails/day
- Better deliverability
- Professional
- Email tracking & analytics

**Cons:**
- Requires signup

**Setup Steps:**

1. Sign up at https://sendgrid.com
2. Verify your sender email
3. Create API key
4. Update `.env`:
   ```env
   MAIL_SERVER=smtp.sendgrid.net
   MAIL_PORT=587
   MAIL_USE_TLS=True
   MAIL_USERNAME=apikey
   MAIL_PASSWORD=your-sendgrid-api-key-here
   MAIL_DEFAULT_SENDER=noreply@yourdomain.com
   BASE_URL=https://yourdomain.com
   ```

---

#### Option C: Mailgun (Alternative)

**Pros:**
- 5,000 free emails/month
- Good deliverability
- Simple API

**Setup Steps:**

1. Sign up at https://mailgun.com
2. Add and verify your domain
3. Get SMTP credentials
4. Update `.env`:
   ```env
   MAIL_SERVER=smtp.mailgun.org
   MAIL_PORT=587
   MAIL_USE_TLS=True
   MAIL_USERNAME=postmaster@yourdomain.mailgun.org
   MAIL_PASSWORD=your-mailgun-password
   MAIL_DEFAULT_SENDER=noreply@yourdomain.com
   BASE_URL=https://yourdomain.com
   ```

---

## 🧪 Testing Email Setup

### 1. Start Flask App
```bash
flask run
```

### 2. Login as Admin
Go to: http://localhost:5050/admin

### 3. Test Email Sending
- Click "📧 Test Email" button
- Select a test user
- Choose email type
- Click "Send Test Email"
- Check the user's email inbox

### 4. View Email Logs
- Click "📬 Email Logs" to see all sent emails
- Check for any failures

---

## 📬 Email Flow

### New User Signup:
```
1. User signs up → Verification email sent
2. User clicks verification link → Email verified
3. Trial starts (7 days) → Welcome email sent
4. User can now login
```

### Trial Reminders (Automated):
```
Day 4: "3 days left" reminder
Day 6: "1 day left" reminder
Day 7: "Trial expired" notification
```

---

## 🔧 Manual Testing

### Send Trial Reminders Manually:
1. Go to Admin Dashboard
2. Click "⏰ Send Trial Reminders"
3. System will:
   - Find users with trials ending in 3 days → send reminder
   - Find users with trials ending in 1 day → send reminder
   - Find users with trials expired today → send expired email

---

## 📊 Email Types

| Email Type | When Sent | Template |
|------------|-----------|----------|
| **Verification** | User signs up | `emails/verify_email.html` |
| **Welcome** | Email verified | `emails/welcome.html` |
| **Password Reset** | User requests reset | `emails/reset_password.html` |
| **Trial 3 Days** | 3 days before trial ends | `emails/trial_reminder_3days.html` |
| **Trial 1 Day** | 1 day before trial ends | `emails/trial_reminder_1day.html` |
| **Trial Expired** | Trial ends | `emails/trial_expired.html` |

---

## 🚀 Next Steps

### Phase A: ✅ COMPLETE
- [x] Email verification enabled
- [x] Email logging implemented
- [x] Trial reminder templates created
- [x] Admin test routes added

### Phase B: TODO (Automation)
- [ ] Install APScheduler
- [ ] Setup daily cron jobs
- [ ] Auto-send trial reminders
- [ ] Auto-expire trials

---

## ⚠️ Troubleshooting

### "Email not configured" error
- Check `.env` file has `MAIL_USERNAME` and `MAIL_PASSWORD`
- Make sure app is restarted after `.env` changes

### Email not received
- Check spam folder
- Check email logs in admin panel
- Verify SMTP credentials are correct
- For Gmail: Make sure you're using App Password, not regular password

### "Authentication failed" error
- Gmail: Use App Password, not regular password
- SendGrid: Username must be exactly "apikey"
- Check for typos in password

---

## 📝 Database

Email logs are stored in `email_logs` table:
- `id` - Log entry ID
- `user_id` - Recipient user
- `recipient_email` - Email address
- `subject` - Email subject
- `email_type` - Type of email
- `status` - sent/failed/pending
- `sent_at` - When sent
- `error_message` - If failed
- `created_at` - When logged

---

## 🔒 Security Notes

1. **Never commit `.env` file** to git
2. **Use App Passwords** for Gmail (not regular password)
3. **Rotate API keys** periodically
4. **Monitor email logs** for suspicious activity
5. **Set rate limits** in production

---

## 📞 Support

If you need help:
1. Check email logs in admin panel
2. Check Flask app logs
3. Test with different email providers
4. Verify email credentials are correct

---

**Last Updated:** 2026-09-26
