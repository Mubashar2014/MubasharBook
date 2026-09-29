"""Complete user deletion — FK-safe purge, confirmation guards, audit trail."""
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import text

from app.extensions import db
from app.models.user import User, Investor
from app.models.shop import Shop
from app.models.subscription import Subscription
from app.models.payment import Payment
from app.models.admin_log import AdminLog
from app.models.stock import StockItem
from app.models.cashbook import CashEntry
from app.models.expense import Expense, ExpenseCategory
from app.models.khata import KhataEntry
from app.models.notification import Notification
from app.models.email_log import EmailLog
from app.models.shareholder import Partner, SplitRule, Period, PeriodSnapshot


@pytest.fixture(autouse=True)
def _enforce_foreign_keys(app):
    """Match MySQL: all 17 FKs into users/shops are NO ACTION, but SQLite
    disables enforcement — turn it on so the delete ORDER is actually tested."""
    db.session.execute(text('PRAGMA foreign_keys=ON'))
    yield


@pytest.fixture
def admin_client(app, test_user):
    test_user.is_admin = True
    db.session.commit()
    c = app.test_client()
    with c.session_transaction() as sess:
        sess['_user_id'] = str(test_user.id)
    return c


def make_victim(name='Victim User', phone='03009990001', with_email=True):
    """A user with at least one row in every table a deletion must clean up."""
    user = User(
        owner_name=name, phone=phone,
        email=f'{phone}@victim.test' if with_email else None,
        language='en', is_verified=True, email_verified_at=datetime.utcnow(),
    )
    user.set_password('password123')
    db.session.add(user)
    db.session.flush()

    shop = Shop(user_id=user.id, name=f"{name}'s Shop", initial_investment=50000)
    db.session.add(shop)
    db.session.flush()

    sub = Subscription(
        shop_id=shop.id, plan='basic', status='active',
        current_period_start=datetime.utcnow(),
        current_period_end=datetime.utcnow() + timedelta(days=30),
    )
    db.session.add(sub)
    db.session.flush()

    investor = Investor(name='Silent Investor', email=f'{phone}@inv.test',
                        phone=f'{phone}9', password_hash='x', shop_id=shop.id)
    db.session.add(investor)
    db.session.flush()

    partner = Partner(shop_id=shop.id, name='Silent Investor', role='investor',
                      investment_amount=10000, investor_user_id=investor.id)
    db.session.add(partner)
    db.session.flush()

    db.session.add(SplitRule(shop_id=shop.id))

    period = Period(shop_id=shop.id, period_start=date(2026, 1, 1),
                    period_end=date(2026, 1, 30), status='locked')
    db.session.add(period)
    db.session.flush()

    db.session.add(PeriodSnapshot(
        period_id=period.id, partner_id=partner.id, shop_id=shop.id,
        investment_ratio_at_lock=100.0, management_base_pct_at_lock=30.0,
        net_profit=0, share_amount=0,
    ))

    db.session.add(StockItem(shop_id=shop.id, model_name='iPhone X',
                             cost_price=1000, purchase_date=date.today()))
    db.session.add(CashEntry(shop_id=shop.id, entry_type='in', amount=1000,
                             description='Opening capital',
                             entry_date=date.today(), balance_after=1000))
    cat = ExpenseCategory(shop_id=shop.id, name='Rent')
    db.session.add(cat)
    db.session.flush()
    db.session.add(Expense(shop_id=shop.id, category_id=cat.id, amount=100,
                           description='Rent', expense_date=date.today()))
    db.session.add(KhataEntry(shop_id=shop.id, party_name='Supplier',
                              entry_type='payable', amount=10,
                              description='Dues', entry_date=date.today()))
    db.session.add(Notification(user_id=user.id, title='Welcome',
                                message='Hi', notification_type='info'))
    db.session.add(EmailLog(user_id=user.id, recipient_email=user.email or user.phone,
                            subject='Welcome', email_type='welcome'))
    db.session.add(Payment(subscription_id=sub.id, user_id=user.id, amount=2000,
                           payment_method='bank_transfer', status='completed',
                           description='Annual plan', payment_proof='proof.png'))
    db.session.commit()
    return user, shop


def delete(admin_client, user_id, confirm):
    return admin_client.post(
        f'/admin/user/{user_id}/delete',
        data={'confirm_text': confirm},
        follow_redirects=False,
    )


# ── THE PURGE ─────────────────────────────────────────────


def test_delete_purges_every_owned_row(admin_client, app):
    user, shop = make_victim()
    uid, sid = user.id, shop.id
    assert User.query.get(uid) is not None

    resp = delete(admin_client, uid, user.email)
    assert resp.status_code == 302
    assert resp.headers['Location'].endswith('/admin/users')

    # users + shop
    assert db.session.get(User, uid) is None
    assert db.session.get(Shop, sid) is None
    # subscriptions + payments
    assert Subscription.query.filter_by(shop_id=sid).count() == 0
    assert Payment.query.filter_by(user_id=uid).count() == 0
    # shareholders / investors
    assert Investor.query.filter_by(shop_id=sid).count() == 0
    assert Partner.query.filter_by(shop_id=sid).count() == 0
    assert SplitRule.query.filter_by(shop_id=sid).count() == 0
    assert Period.query.filter_by(shop_id=sid).count() == 0
    assert PeriodSnapshot.query.filter_by(shop_id=sid).count() == 0
    # business data
    assert StockItem.query.filter_by(shop_id=sid).count() == 0
    assert CashEntry.query.filter_by(shop_id=sid).count() == 0
    assert Expense.query.filter_by(shop_id=sid).count() == 0
    assert ExpenseCategory.query.filter_by(shop_id=sid).count() == 0
    assert KhataEntry.query.filter_by(shop_id=sid).count() == 0
    # user-scoped
    assert Notification.query.filter_by(user_id=uid).count() == 0
    assert EmailLog.query.filter_by(user_id=uid).count() == 0


def test_delete_leaves_other_users_alone(admin_client, app, test_user):
    victim, vshop = make_victim('Collateral', '03009990002')
    other, oshop = make_victim('Bystander', '03009990003')

    delete(admin_client, victim.id, victim.email)

    assert db.session.get(User, other.id) is not None
    assert db.session.get(Shop, oshop.id) is not None
    assert StockItem.query.filter_by(shop_id=oshop.id).count() == 1
    assert CashEntry.query.filter_by(shop_id=oshop.id).count() == 1
    # the admin (test_user) is untouched
    assert db.session.get(User, test_user.id) is not None


def test_delete_keeps_the_audit_trail(admin_client, app):
    victim, _ = make_victim()
    uid = victim.id

    delete(admin_client, uid, victim.email)

    logs = AdminLog.query.filter_by(action='user_deleted', target_id=uid).all()
    assert len(logs) == 1
    log = logs[0]
    assert log.target_type == 'user'
    assert 'Permanently deleted Victim User' in log.description
    assert 'Rs 2,000' in log.description          # completed revenue removed
    assert 'cashbook entries' in log.description
    assert '"revenue_removed": 2000.0' in log.changes
    assert log.ip_address is not None


# ── GUARDS ────────────────────────────────────────────────


def test_delete_requires_exact_confirmation(admin_client, app):
    victim, _ = make_victim()
    uid = victim.id

    resp = delete(admin_client, uid, 'wrong@example.com')
    assert resp.status_code == 302
    assert db.session.get(User, uid) is not None
    assert Payment.query.filter_by(user_id=uid).count() == 1
    assert AdminLog.query.filter_by(action='user_deleted').count() == 0


def test_delete_confirmation_is_case_insensitive(admin_client, app):
    victim, _ = make_victim()
    resp = delete(admin_client, victim.id, victim.email.upper())
    assert resp.status_code == 302
    assert db.session.get(User, victim.id) is None


def test_delete_refuses_admin_target(admin_client, app, second_user):
    second_user.is_admin = True
    db.session.commit()

    resp = delete(admin_client, second_user.id, second_user.email)
    assert resp.status_code == 302
    assert db.session.get(User, second_user.id) is not None
    assert AdminLog.query.filter_by(action='user_deleted').count() == 0


def test_delete_refuses_own_account(admin_client, app, test_user):
    resp = delete(admin_client, test_user.id, test_user.email)
    assert resp.status_code == 302
    assert db.session.get(User, test_user.id) is not None


def test_delete_user_without_email_confirms_with_phone(admin_client, app):
    victim, _ = make_victim('No Email', '03009990004', with_email=False)
    uid = victim.id

    # email confirm must fail — the account has no email
    assert delete(admin_client, uid, '').status_code == 302
    assert db.session.get(User, uid) is not None

    assert delete(admin_client, uid, victim.phone).status_code == 302
    assert db.session.get(User, uid) is None


def test_delete_requires_admin_role(app, test_user):
    """A non-admin session cannot reach the delete route at all."""
    victim, _ = make_victim()
    c = app.test_client()
    with c.session_transaction() as sess:
        sess['_user_id'] = str(test_user.id)

    resp = c.post(f'/admin/user/{victim.id}/delete',
                  data={'confirm_text': victim.email}, follow_redirects=True)
    assert resp.status_code == 403
    assert db.session.get(User, victim.id) is not None


# ── UPLOADED PROOFS ───────────────────────────────────────


def test_delete_removes_uploaded_payment_proof(admin_client, app):
    import os

    victim, _ = make_victim()
    proof_dir = os.path.join(app.static_folder, 'payment_proofs')
    os.makedirs(proof_dir, exist_ok=True)
    proof_path = os.path.join(proof_dir, 'proof.png')
    with open(proof_path, 'wb') as fh:
        fh.write(b'png-bytes')
    assert os.path.isfile(proof_path)

    try:
        delete(admin_client, victim.id, victim.email)
        assert not os.path.exists(proof_path)
    finally:
        if os.path.exists(proof_path):
            os.remove(proof_path)
