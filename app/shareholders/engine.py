"""
Shareholder Profit-Split Engine

Encodes the core business logic for splitting profit and loss among partners.
This is the most critical financial module — Shariah-compliant rules apply.

Rules:
  - LOSS is always split strictly by investment ratio
  - PROFIT is split: management base % off top for managing owners, remainder by investment ratio
  - When a period is LOCKED, ratios and amounts are snapshotted permanently
  - Past locked periods NEVER recalculate
"""

from decimal import Decimal
from app.extensions import db
from app.models.shareholder import Partner, SplitRule, Period, PeriodSnapshot


def calculate_split(shop_id, net_profit):
    """
    Calculate profit/loss split for all partners in a shop.

    Args:
        shop_id: The shop to calculate for
        net_profit: Positive = profit, Negative = loss (Decimal or float)

    Returns:
        dict with keys:
            - net_profit: the input profit/loss
            - splits: list of dicts, one per partner, each with:
                - partner_id, name, role
                - investment_ratio
                - share_amount (positive = receives, negative = owes)
                - management_base_amount (only for managing owners on profit)
                - remainder_share
            - management_base_total
            - remainder
    """
    net_profit = Decimal(str(net_profit))

    partners = Partner.query.filter_by(shop_id=shop_id).all()
    if not partners:
        return {'net_profit': net_profit, 'splits': [], 'management_base_total': 0, 'remainder': 0}

    total_investment = sum(p.investment_amount for p in partners)
    if total_investment == 0:
        return {'net_profit': net_profit, 'splits': [], 'management_base_total': 0, 'remainder': 0}

    # Recalculate ratios from current investment amounts
    for p in partners:
        p.investment_ratio = float(p.investment_amount / total_investment * 100)

    split_rule = SplitRule.query.filter_by(shop_id=shop_id).first()
    mgmt_base_pct = Decimal(str(split_rule.management_base_pct)) if split_rule else Decimal('0')

    managing_owners = [p for p in partners if p.role == 'owner']
    splits = []

    if net_profit < 0:
        # LOSS: always split strictly by investment ratio
        for p in partners:
            ratio = Decimal(str(p.investment_ratio)) / Decimal('100')
            share = net_profit * ratio  # negative
            splits.append({
                'partner_id': p.id,
                'name': p.name,
                'role': p.role,
                'investment_ratio': p.investment_ratio,
                'share_amount': share,
                'management_base_amount': Decimal('0'),
                'remainder_share': share,
            })
        remainder = Decimal('0')
        mgmt_base_total = Decimal('0')
    else:
        # PROFIT: management base off top, then remainder by ratio
        mgmt_base_total = (net_profit * mgmt_base_pct / Decimal('100')).quantize(Decimal('0.01'))

        # Distribute management base among managing owners proportionally
        if managing_owners:
            total_owner_investment = sum(p.investment_amount for p in managing_owners)
            mgmt_per_owner = {}
            for p in managing_owners:
                if total_owner_investment > 0:
                    share = (mgmt_base_total * p.investment_amount / total_owner_investment).quantize(Decimal('0.01'))
                else:
                    share = mgmt_base_total / len(managing_owners)
                mgmt_per_owner[p.id] = share
        else:
            mgmt_per_owner = {}

        remainder = net_profit - mgmt_base_total

        for p in partners:
            ratio = Decimal(str(p.investment_ratio)) / Decimal('100')
            remainder_share = (remainder * ratio).quantize(Decimal('0.01'))
            mgmt_amount = mgmt_per_owner.get(p.id, Decimal('0'))
            total_share = mgmt_amount + remainder_share

            splits.append({
                'partner_id': p.id,
                'name': p.name,
                'role': p.role,
                'investment_ratio': p.investment_ratio,
                'share_amount': total_share,
                'management_base_amount': mgmt_amount,
                'remainder_share': remainder_share,
            })

    return {
        'net_profit': net_profit,
        'splits': splits,
        'management_base_total': mgmt_base_total,
        'remainder': remainder,
    }


def lock_period(period_id):
    """
    Lock an accounting period. Snapshots all partner splits permanently.

    This is an irreversible operation. Once locked, the snapshot is never
    recalculated even if investment ratios change later.

    Args:
        period_id: The period to lock

    Returns:
        The locked period object
    """
    period = db.session.get(Period, period_id)
    if period is None:
        raise ValueError(f"Period {period_id} not found")
    if period.status == 'locked':
        raise ValueError(f"Period {period_id} is already locked")

    # Calculate net profit for this period from cashbook + expenses
    net_profit = _calculate_period_net_profit(period)

    # Get current split (using current ratios at time of lock)
    split_result = calculate_split(period.shop_id, net_profit)

    # Create snapshot for each partner
    for s in split_result['splits']:
        snapshot = PeriodSnapshot(
            period_id=period.id,
            partner_id=s['partner_id'],
            shop_id=period.shop_id,
            investment_ratio_at_lock=s['investment_ratio'],
            management_base_pct_at_lock=split_result['management_base_total'] / net_profit * 100 if net_profit > 0 else 0,
            net_profit=net_profit,
            loss_amount=abs(net_profit) if net_profit < 0 else Decimal('0'),
            share_amount=s['share_amount'],
        )
        db.session.add(snapshot)

    period.status = 'locked'
    period.locked_at = db.session.execute(
        db.func.now()
    ).scalar() or __import__('datetime').datetime.utcnow()

    db.session.commit()
    return period


def _calculate_period_net_profit(period):
    """
    Calculate net profit for a given period.

    Net Profit = Total Cash In - Total Cash Out - Total Expenses
    """
    from app.models.cashbook import CashEntry
    from app.models.expense import Expense

    cash_in = db.session.query(
        db.func.coalesce(db.func.sum(CashEntry.amount), 0)
    ).filter(
        CashEntry.shop_id == period.shop_id,
        CashEntry.entry_type == 'in',
        CashEntry.entry_date >= period.period_start,
        CashEntry.entry_date <= period.period_end,
    ).scalar()

    cash_out = db.session.query(
        db.func.coalesce(db.func.sum(CashEntry.amount), 0)
    ).filter(
        CashEntry.shop_id == period.shop_id,
        CashEntry.entry_type == 'out',
        CashEntry.entry_date >= period.period_start,
        CashEntry.entry_date <= period.period_end,
    ).scalar()

    expenses = db.session.query(
        db.func.coalesce(db.func.sum(Expense.amount), 0)
    ).filter(
        Expense.shop_id == period.shop_id,
        Expense.expense_date >= period.period_start,
        Expense.expense_date <= period.period_end,
    ).scalar()

    return Decimal(str(cash_in)) - Decimal(str(cash_out)) - Decimal(str(expenses))
