# Admin Guide

A plain-language walkthrough of everything you can do in the admin panel.

The panel lives at **`/admin/`** (e.g. `http://localhost:5050/admin/`).
When an admin account logs in, it is sent there automatically.

---

## 1. Logging in

1. Go to `/login` and sign in with an **admin** account.
   - You are redirected straight to `/admin/`.
2. Admin accounts never see the normal shop app (stock, cashbook, khata).
   If you need to use the shop app, log in with a normal user account instead.

**Who is an admin?** Only accounts flagged as admin. Promote someone with:

```bash
python -m flask make-admin their-email@example.com
```

You can never make yourself admin from inside the panel.

---

## 2. The sidebar

The left sidebar is the same one the shop app uses, grouped into sections:

| Group | Page | What it is for |
|---|---|---|
| **Manage** | Overview | Headline numbers and things that need a decision |
| | Users | The searchable list of every customer |
| **Operations** | Payments | Payment proofs waiting for approval (red badge = count) |
| **Email** | Email Logs | Every email the system has sent, with status |
| | Test Email | Send one test email to check email is working |
| **Audit** | Activity Log | Every admin action, forever |
| **Account** | Logout | End your session |

At the bottom of the sidebar is the name of the account you are signed in as.

> There is no "Back to App" link — an admin account has no shop app to go
> back to. Use Logout, then log in as a normal user.

The current page is highlighted in gold in the sidebar, on every page.

---

## 3. Overview (`/admin/`)

The first screen. It answers *"is anything wrong right now?"*

**Headline numbers**

| Card | Meaning |
|---|---|
| Total Users | Customers only — admin accounts are not counted |
| Trial Users | Customers whose subscription is on trial |
| Active (Paid) | Customers with a paid, running subscription |
| Expired | Subscriptions that ran out |
| Suspended | Accounts you blocked |
| New Signups (7d) | Accounts created in the last 7 days |
| Total Revenue | Sum of **completed** payments only |

The four status cards always add up to **Total Users**. The admin's own
account and shop are excluded from every one of these numbers.

**Needs attention** — three shortcuts:

1. *Payments waiting for verification* → jumps to **Payments** (shows
   "All clear" when there is nothing waiting).
2. *Expired subscriptions* → jumps to Users filtered to Expired.
3. *Trials ending within 3 days* → a list of the people about to lose
   access, with a red **Overdue** badge if the trial already ended.

**Recent signups** — last five customers, with a link to search all users.

**Recent admin activity** — last six audit entries, with a link to the
full Activity Log.

---

## 4. Users (`/admin/users`)

The searchable customer list (50 per page).

- **Search box** — matches name, email, phone, or shop name
  (case-insensitive).
- **Status filter** — All statuses / Trial / Active / Expired / Suspended.
- **Status badge** — shows each account's current subscription state.
- **View** — opens that user's detail page.

Your search, filter, and page number are remembered: opening a user and
pressing **Back to Users** returns you to the exact list you were looking
at.

Admin accounts never appear in this list.

---

## 5. A user's detail page (`/admin/user/<id>`)

Everything about one customer, in one place:

- **Identity** — name, email, phone, language, verification, last login.
- **Shop** — shop name, opening balance, creation date.
- **Subscription** — status, plan, trial dates, current period.
- **Payments** — every payment they have made.
- **Admin history** — the last 20 audit entries for this person.
- **Admin Actions** — the four buttons below.
- **Danger Zone** — permanent deletion (section 7).

### 5.1 Extend Trial

Give someone more free time.

1. Enter **Days to add** (default 7).
2. Click **Extend Trial**.

If their trial is still running, the new end date is *added* to the old
one. If the trial already ended, a fresh trial is started. The new end
date is also copied onto the user account so the countdown in the app
matches.

*Use this for testers, friends, or someone who asked nicely.*

### 5.2 Quick Activate

Turn someone into a paying customer **without recording money** — for
free/discounted/deal-offline customers.

1. Choose a **Plan**: Basic or Premium.
2. Choose a **Duration**: 1, 2, 3, 6, or 12 months, or *Custom* days.
   Months are calendar-accurate (1 Feb + 1 month = 1 Mar, not 3 Mar).
3. Add **Notes** if you like.
4. Click **Activate Now**.

No payment row is created, so revenue is unaffected. It is logged as
`Quick Activation` in the Activity Log.

### 5.3 Activate Paid Subscription (manual payment)

Use this when someone paid you **offline** (bank transfer, cash,
JazzCash, EasyPaisa) and you want it counted as revenue.

1. Enter the **Amount (Rs)**.
2. Pick the **Payment Method**.
3. Add **Notes** (e.g. `Bank transfer ref: 123456`).
4. Click **Activate Subscription**.

This creates a **completed** payment record *and* activates the
subscription. The amount is included in **Total Revenue**.

> Choosing between 5.2 and 5.3:
> money changed hands → **5.3**. No money changed hands → **5.2**.

### 5.4 Suspend / Unsuspend

**Suspend** blocks the account and their subscription. It is reversible.

1. Enter a **Reason** (required).
2. Click **Suspend Account**.

The card then becomes **Unsuspend**, one click to bring them back.
Both actions are logged.

---

## 6. Payments (`/admin/pending-payments`)

Payment proofs uploaded by customers through the app, waiting for you.

For each pending payment you see the amount, method, who paid, and the
uploaded screenshot.

- **Verify** → marks the payment completed, activates the subscription
  for the plan described on the payment, sets the user to premium if the
  plan was premium, and **emails the customer a confirmation**.
- **Reject** → marks it failed and stores your reason. You can approve
  the same payment later if it was a mistake.

Both are written to the Activity Log. Already-processed payments cannot
be processed again — you get a "Payment already processed" notice.

When the list is empty the page simply says **All Clear!**.

---

## 7. Deleting a user permanently (Danger Zone)

**This is a full, irreversible erase of everything that belongs to that
person. Nothing is archived.**

Open the user → scroll to the red **Danger Zone** card.

### What it deletes

The card lists the exact row counts before you commit:

- the user account, their shop, and their subscription
- investors, shareholders (partners), split rules
- periods and period snapshots
- stock items, **cashbook entries**, **expenses** and expense categories
- khata entries, payments, notifications, email logs

Payment proof screenshot **files** are deleted from disk too (after the
database change succeeds).

Your own **audit entry survives** — it is written first, so the Activity
Log still records who deleted whom, what was removed, and how much
revenue went away.

### How to do it

1. Read the row counts and the **Revenue impact** warning
   (completed payments for this user leave Total Revenue on Overview).
2. Type the user's **email** into the box — or their **phone number** if
   the account has no email. The exact value to type is shown under the
   box.
3. Only then does **Delete permanently** light up.
4. Confirm. You land back on the detail page with a success message.

### Safety rules

- You **cannot delete your own account** — "You cannot delete your own
  account."
- You **cannot delete admin accounts** — "Admin accounts cannot be
  deleted."
- A wrong confirmation string deletes **nothing** —
  "Confirmation did not match — nothing was deleted."
- If the account has neither email nor phone, it cannot be confirmed, so
  it cannot be deleted.

> Prefer a softer touch? **Suspend** the account instead — it blocks
> access and can be undone.

---

## 8. Email

### Test Email (`/admin/test-email`)

Checks that sending works before you rely on it.

1. Select a **user** (this is who it is addressed to).
2. Select an **Email Type**:
   Verification, Welcome, Trial Reminder (3 days / 1 day), Trial Expired.
3. Click **Send Test Email**.

Then open **Email Logs** to confirm it says *Sent*.

### Email Logs (`/admin/email-logs`)

Every email the system produced, newest first.

- Filter by **Status**: Sent / Failed / Pending.
- Filter by **Type**: welcome, verification, trial reminder, etc.

A row stuck on *Failed* means the outgoing mail settings are wrong —
fix them, then use Test Email to re-check.

### Emails sent automatically

A background scheduler runs these; you do not need to trigger them:

| Time | Job |
|---|---|
| 00:00 | Expire finished trials |
| 00:15 | Expire finished subscriptions |
| 03:00 | Subscription renewals |
| 09:00 | Trial reminder emails (3 days and 1 day before the end) |

*(The scheduler only runs in the normal app configuration, not in tests.)*

---

## 9. Activity Log (`/admin/activity`)

The audit trail — one row per admin action, newest first. Records who
did it, when, from which IP address, and what changed.

Actions you will see:

| Action | Triggered by |
|---|---|
| Trial Extended | Extend Trial |
| Subscription Activated | Activate Paid Subscription |
| Quick Activation | Quick Activate |
| User Suspended / User Unsuspended | Suspend buttons |
| Payment Verified / Payment Rejected | Payments page |
| User Deleted | Danger Zone delete |

Filters:

- **Action** — show only one kind of action.
- **Admin** — show only actions by one admin.

The user detail page shows only the last 20 entries for that person;
this page shows everything, and is where you look after any "did I really
do that?" moment.

---

## 10. Recipes for common jobs

**Give a tester 14 more days**
Users → find them → *Extend Trial* → `14` → Extend Trial.

**Someone paid by bank transfer**
Users → find them → *Activate Paid Subscription* → amount + method +
reference in Notes → Activate Subscription.

**Gift a friend a free year**
Users → find them → *Quick Activate* → Basic → 12 → Activate Now.

**Block someone who is abusing the app**
Users → find them → *Account Status* → reason → Suspend Account.

**A payment proof looks fake**
Payments → open it → Reject, with a reason.

**"Why did revenue drop?"**
Activity Log → filter Action = *User Deleted*.

**"Did that email actually go out?"**
Email Logs → filter by status/type, or send a Test Email first.

---

## 11. Troubleshooting

| Symptom | What to do |
|---|---|
| Redirected to the login page on `/admin/` | You are not signed in. |
| "403 Forbidden" on `/admin/` | The account is not an admin. Promote it with `flask make-admin`. |
| Taken back to Overview when opening a user | That user *is* an admin — admin detail pages are blocked. |
| "User has no shop" / "User has no subscription" | The account was created without a shop. It cannot be trial-activated. |
| Delete button stays grey | The text does not match the email/phone exactly (case does not matter). |
| Pending payment badge stuck | A payment is still awaiting review — open Payments. |
| Email says *Failed* in Email Logs | Fix outgoing mail settings, then send a Test Email. |
| Overview numbers look wrong | Status counts exclude admin accounts and count **distinct** users; a user with no subscription shows only in Total Users. |

---

## 12. Where the code lives

| Piece | File |
|---|---|
| All admin routes | `app/admin/routes.py` |
| Admin login guard | `app/admin/middleware.py` (`@admin_required`) |
| Sidebar layout | `app/templates/admin_layout.html` |
| Overview | `app/templates/admin/dashboard.html` |
| User list | `app/templates/admin/users.html` |
| User detail + Danger Zone | `app/templates/admin/user_detail.html` |
| Payments / Email / Activity | `app/templates/admin/*.html` |
| Audit log model | `app/models/admin_log.py` |
| Tests | `tests/test_admin_nav.py`, `tests/test_admin_delete_user.py` |

Run the tests with:

```bash
python -m pytest tests -q
```

Setup notes and the original build checklist live in `ADMIN_SETUP.md`.
