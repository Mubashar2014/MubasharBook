from decimal import Decimal
from datetime import date, timedelta
from app.extensions import db
from app.models.shareholder import Partner, SplitRule, Period, PeriodSnapshot
from app.models.cashbook import CashEntry
from app.models.expense import Expense
from app.shareholders.engine import calculate_split, lock_period


def _create_partner(shop_id, name, role, investment_amount):
    p = Partner(
        shop_id=shop_id, name=name, role=role,
        investment_amount=Decimal(str(investment_amount)),
    )
    db.session.add(p)
    db.session.flush()
    return p


def test_loss_split_by_ratio(premium_user, app):
    with app.app_context():
        from app.models.shop import Shop
        shop = Shop.query.filter_by(user_id=premium_user.id).first()

        _create_partner(shop.id, 'Ali', 'owner', 100000)
        _create_partner(shop.id, 'Ahmed', 'investor', 100000)
        db.session.commit()

        result = calculate_split(shop.id, -10000)

        assert result['net_profit'] == Decimal('-10000')
        assert len(result['splits']) == 2
        assert result['management_base_total'] == 0

        shares = {s['name']: s['share_amount'] for s in result['splits']}
        assert shares['Ali'] == Decimal('-5000')
        assert shares['Ahmed'] == Decimal('-5000')


def test_profit_split_with_management_base(premium_user, app):
    with app.app_context():
        from app.models.shop import Shop
        shop = Shop.query.filter_by(user_id=premium_user.id).first()

        _create_partner(shop.id, 'Owner1', 'owner', 100000)
        _create_partner(shop.id, 'Owner2', 'owner', 100000)
        rule = SplitRule(shop_id=shop.id, management_base_pct=30.0)
        db.session.add(rule)
        db.session.commit()

        result = calculate_split(shop.id, 96400)

        assert result['management_base_total'] == Decimal('28920.00')
        assert result['remainder'] == Decimal('67480.00')

        shares = {s['name']: s['share_amount'] for s in result['splits']}
        assert shares['Owner1'] == Decimal('48200.00')
        assert shares['Owner2'] == Decimal('48200.00')


def test_profit_split_no_management_base(premium_user, app):
    with app.app_context():
        from app.models.shop import Shop
        shop = Shop.query.filter_by(user_id=premium_user.id).first()

        _create_partner(shop.id, 'A', 'owner', 100000)
        _create_partner(shop.id, 'B', 'investor', 100000)
        rule = SplitRule(shop_id=shop.id, management_base_pct=0.0)
        db.session.add(rule)
        db.session.commit()

        result = calculate_split(shop.id, 50000)

        assert result['management_base_total'] == Decimal('0.00')
        assert result['remainder'] == Decimal('50000.00')

        shares = {s['name']: s['share_amount'] for s in result['splits']}
        assert shares['A'] == Decimal('25000.00')
        assert shares['B'] == Decimal('25000.00')


def test_multiple_partners_split(premium_user, app):
    with app.app_context():
        from app.models.shop import Shop
        shop = Shop.query.filter_by(user_id=premium_user.id).first()

        _create_partner(shop.id, 'Major', 'owner', 50000)
        _create_partner(shop.id, 'Medium', 'owner', 30000)
        _create_partner(shop.id, 'Minor', 'investor', 20000)
        db.session.commit()

        result = calculate_split(shop.id, -10000)

        shares = {s['name']: s['share_amount'] for s in result['splits']}
        assert shares['Major'] == Decimal('-5000')
        assert shares['Medium'] == Decimal('-3000')
        assert shares['Minor'] == Decimal('-2000')


def test_split_empty_partners(premium_user, app):
    with app.app_context():
        from app.models.shop import Shop
        shop = Shop.query.filter_by(user_id=premium_user.id).first()
        db.session.commit()

        result = calculate_split(shop.id, 10000)
        assert result['splits'] == []


def test_split_zero_total_investment(premium_user, app):
    with app.app_context():
        from app.models.shop import Shop
        shop = Shop.query.filter_by(user_id=premium_user.id).first()

        _create_partner(shop.id, 'Zero', 'owner', 0)
        db.session.commit()

        result = calculate_split(shop.id, 10000)
        assert result['splits'] == []


def test_profit_split_mixed_owners_investors(premium_user, app):
    with app.app_context():
        from app.models.shop import Shop
        shop = Shop.query.filter_by(user_id=premium_user.id).first()

        _create_partner(shop.id, 'Managing', 'owner', 60000)
        _create_partner(shop.id, 'Silent', 'investor', 40000)
        rule = SplitRule(shop_id=shop.id, management_base_pct=30.0)
        db.session.add(rule)
        db.session.commit()

        result = calculate_split(shop.id, 100000)

        assert result['management_base_total'] == Decimal('30000.00')
        assert result['remainder'] == Decimal('70000.00')

        splits = {s['name']: s for s in result['splits']}
        assert splits['Managing']['management_base_amount'] == Decimal('30000.00')
        assert splits['Managing']['remainder_share'] == Decimal('42000.00')
        assert splits['Managing']['share_amount'] == Decimal('72000.00')

        assert splits['Silent']['management_base_amount'] == Decimal('0')
        assert splits['Silent']['remainder_share'] == Decimal('28000.00')
        assert splits['Silent']['share_amount'] == Decimal('28000.00')


def test_period_lock_creates_snapshots(premium_user, app):
    with app.app_context():
        from app.models.shop import Shop
        shop = Shop.query.filter_by(user_id=premium_user.id).first()

        p1 = _create_partner(shop.id, 'Owner1', 'owner', 100000)
        p2 = _create_partner(shop.id, 'Investor1', 'investor', 100000)
        rule = SplitRule(shop_id=shop.id, management_base_pct=30.0)
        db.session.add(rule)

        period = Period(
            shop_id=shop.id,
            period_start=date(2024, 6, 1),
            period_end=date(2024, 6, 30),
            status='open',
        )
        db.session.add(period)
        db.session.commit()

        _db = __import__('app.extensions', fromlist=['db']).db
        _db.session.add_all([
            CashEntry(shop_id=shop.id, entry_type='in', amount=200000,
                      description='Revenue', entry_date=date(2024, 6, 15)),
            CashEntry(shop_id=shop.id, entry_type='out', amount=60000,
                      description='Cost', entry_date=date(2024, 6, 20)),
            Expense(shop_id=shop.id, category_id=1, amount=10000,
                    description='Rent', expense_date=date(2024, 6, 10)),
        ])
        _db.session.commit()

        locked = lock_period(period.id)

        assert locked.status == 'locked'
        assert locked.locked_at is not None

        snapshots = PeriodSnapshot.query.filter_by(period_id=period.id).all()
        assert len(snapshots) == 2

        snap_map = {s.partner_id: s for s in snapshots}
        assert p1.id in snap_map
        assert p2.id in snap_map

        assert snap_map[p1.id].share_amount != Decimal('0')
        assert snap_map[p2.id].share_amount != Decimal('0')


def test_locked_period_never_recalculates(premium_user, app):
    with app.app_context():
        from app.models.shop import Shop
        shop = Shop.query.filter_by(user_id=premium_user.id).first()

        p1 = _create_partner(shop.id, 'Original', 'owner', 100000)
        p2 = _create_partner(shop.id, 'Partner', 'investor', 100000)
        rule = SplitRule(shop_id=shop.id, management_base_pct=30.0)
        db.session.add(rule)

        period = Period(
            shop_id=shop.id,
            period_start=date(2024, 6, 1),
            period_end=date(2024, 6, 30),
            status='open',
        )
        db.session.add(period)
        db.session.commit()

        _db = __import__('app.extensions', fromlist=['db']).db
        _db.session.add_all([
            CashEntry(shop_id=shop.id, entry_type='in', amount=200000,
                      description='Revenue', entry_date=date(2024, 6, 15)),
            Expense(shop_id=shop.id, category_id=1, amount=10000,
                    description='Rent', expense_date=date(2024, 6, 10)),
        ])
        _db.session.commit()

        lock_period(period.id)

        snap_before = PeriodSnapshot.query.filter_by(period_id=period.id).all()
        snap_before_map = {s.partner_id: s for s in snap_before}
        amount_before = {pid: s.share_amount for pid, s in snap_before_map.items()}

        p1.investment_amount = Decimal('200000')
        p2.investment_amount = Decimal('100000')
        _db.session.commit()

        snap_after = PeriodSnapshot.query.filter_by(period_id=period.id).all()
        snap_after_map = {s.partner_id: s for s in snap_after}

        for pid, amt in amount_before.items():
            assert snap_after_map[pid].share_amount == amt


def test_period_lock_requires_open_status(premium_user, app):
    with app.app_context():
        from app.models.shop import Shop
        shop = Shop.query.filter_by(user_id=premium_user.id).first()

        _create_partner(shop.id, 'A', 'owner', 100000)
        rule = SplitRule(shop_id=shop.id, management_base_pct=30.0)
        db.session.add(rule)

        period = Period(
            shop_id=shop.id,
            period_start=date(2024, 6, 1),
            period_end=date(2024, 6, 30),
            status='open',
        )
        db.session.add(period)
        db.session.commit()

        _db = __import__('app.extensions', fromlist=['db']).db
        _db.session.add(CashEntry(
            shop_id=shop.id, entry_type='in', amount=100000,
            description='Rev', entry_date=date(2024, 6, 15),
        ))
        _db.session.commit()

        lock_period(period.id)

        try:
            lock_period(period.id)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert 'already locked' in str(e)


def test_period_lock_not_found(premium_user, app):
    with app.app_context():
        try:
            lock_period(99999)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert 'not found' in str(e)


def test_split_profit_with_investor_only(premium_user, app):
    with app.app_context():
        from app.models.shop import Shop
        shop = Shop.query.filter_by(user_id=premium_user.id).first()

        _create_partner(shop.id, 'Silent', 'investor', 100000)
        rule = SplitRule(shop_id=shop.id, management_base_pct=30.0)
        db.session.add(rule)
        db.session.commit()

        result = calculate_split(shop.id, 100000)

        assert result['management_base_total'] == Decimal('30000.00')
        assert result['remainder'] == Decimal('70000.00')

        splits = result['splits']
        assert len(splits) == 1
        assert splits[0]['management_base_amount'] == Decimal('0')
        assert splits[0]['share_amount'] == Decimal('70000.00')
