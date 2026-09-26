from datetime import date, timedelta
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app.shareholders import shareholders_bp
from app.shareholders.forms import PartnerForm, SplitRuleForm
from app.shareholders.engine import calculate_split, lock_period
from app.extensions import db
from app.models.user import Investor
from app.models.shareholder import Partner, SplitRule, Period, PeriodSnapshot
from app.models.shop import Shop
from app.models.stock import StockItem


def get_shop():
    return Shop.query.filter_by(user_id=current_user.id).first()


def _recalc_ratios(shop_id):
    partners = Partner.query.filter_by(shop_id=shop_id).all()
    total = sum(float(p.investment_amount) for p in partners)
    for p in partners:
        p.investment_ratio = (float(p.investment_amount) / total * 100) if total > 0 else 0.0
    return partners


@shareholders_bp.route('/')
@login_required
def setup():
    shop = get_shop()
    if not shop:
        flash('No shop found.', 'warning')
        return redirect(url_for('main.dashboard'))

    partners = Partner.query.filter_by(shop_id=shop.id).all()
    split_rule = SplitRule.query.filter_by(shop_id=shop.id).first()
    form = PartnerForm()
    rule_form = SplitRuleForm(obj=split_rule)

    total_investment = sum(p.investment_amount for p in partners) if partners else 0

    return render_template(
        'shareholders/setup.html',
        partners=partners,
        split_rule=split_rule,
        form=form,
        rule_form=rule_form,
        total_investment=total_investment,
        shop=shop,
    )


@shareholders_bp.route('/add-partner', methods=['POST'])
@login_required
def add_partner():
    shop = get_shop()
    if not shop:
        flash('No shop found.', 'warning')
        return redirect(url_for('main.dashboard'))

    form = PartnerForm()
    if form.validate_on_submit():
        partner = Partner(
            shop_id=shop.id,
            name=form.name.data.strip(),
            role=form.role.data,
            investment_amount=form.investment_amount.data,
        )

        if form.role.data == 'investor' and form.investor_email.data:
            investor = Investor(
                name=form.name.data.strip(),
                email=form.investor_email.data.strip().lower(),
                phone=form.investor_phone.data.strip() if form.investor_phone.data else None,
                shop_id=shop.id,
            )
            investor.set_password('investor123')
            db.session.add(investor)
            db.session.flush()
            partner.investor_user_id = investor.id

        db.session.add(partner)
        db.session.flush()
        _recalc_ratios(shop.id)

        db.session.commit()
        flash(f'Partner {partner.name} added successfully.', 'success')
    else:
        flash('Please correct the errors in the form.', 'danger')

    return redirect(url_for('shareholders.setup'))


@shareholders_bp.route('/partner/<int:partner_id>/edit', methods=['POST'])
@login_required
def edit_partner(partner_id):
    shop = get_shop()
    if not shop:
        flash('No shop found.', 'warning')
        return redirect(url_for('main.dashboard'))

    partner = Partner.query.filter_by(id=partner_id, shop_id=shop.id).first()
    if not partner:
        flash('Partner not found.', 'danger')
        return redirect(url_for('shareholders.setup'))

    form = PartnerForm()
    if form.validate_on_submit():
        partner.name = form.name.data.strip()
        partner.role = form.role.data
        partner.investment_amount = form.investment_amount.data
        _recalc_ratios(shop.id)
        db.session.commit()
        flash('Partner updated successfully.', 'success')
    else:
        flash('Please correct the errors in the form.', 'danger')

    return redirect(url_for('shareholders.setup'))


@shareholders_bp.route('/partner/<int:partner_id>/delete', methods=['POST'])
@login_required
def delete_partner(partner_id):
    shop = get_shop()
    if not shop:
        flash('No shop found.', 'warning')
        return redirect(url_for('main.dashboard'))

    partner = Partner.query.filter_by(id=partner_id, shop_id=shop.id).first()
    if not partner:
        flash('Partner not found.', 'danger')
        return redirect(url_for('shareholders.setup'))

    has_snapshots = PeriodSnapshot.query.filter_by(partner_id=partner.id).first() is not None
    if has_snapshots:
        flash('Cannot remove a partner that appears in locked period snapshots.', 'warning')
        return redirect(url_for('shareholders.setup'))

    if partner.investor_user_id:
        investor = db.session.get(Investor, partner.investor_user_id)
        if investor:
            db.session.delete(investor)

    unassigned = StockItem.query.filter_by(funded_by_partner_id=partner.id).update(
        {StockItem.funded_by_partner_id: None}, synchronize_session=False)

    name = partner.name
    db.session.delete(partner)
    db.session.flush()
    _recalc_ratios(shop.id)
    db.session.commit()
    if unassigned:
        flash(f'Partner {name} removed. {unassigned} phone(s) returned to unassigned stock.', 'success')
    else:
        flash(f'Partner {name} removed.', 'success')
    return redirect(url_for('shareholders.setup'))


@shareholders_bp.route('/create-period', methods=['POST'])
@login_required
def create_period():
    shop = get_shop()
    if not shop:
        flash('No shop found.', 'warning')
        return redirect(url_for('main.dashboard'))

    open_period = Period.query.filter_by(shop_id=shop.id, status='open').first()
    if open_period:
        flash('An open period already exists. Lock it before creating a new one.', 'warning')
        return redirect(url_for('shareholders.periods'))

    last = Period.query.filter_by(shop_id=shop.id).order_by(Period.period_end.desc()).first()
    start = last.period_end + timedelta(days=1) if last else date.today()
    if start < date.today():
        start = date.today()

    period = Period(
        shop_id=shop.id,
        period_start=start,
        period_end=start + timedelta(days=29),
        status='open',
    )
    db.session.add(period)
    db.session.commit()
    flash('New 30-day period created.', 'success')
    return redirect(url_for('shareholders.periods'))


@shareholders_bp.route('/update-ratio', methods=['POST'])
@login_required
def update_ratio():
    shop = get_shop()
    if not shop:
        flash('No shop found.', 'warning')
        return redirect(url_for('main.dashboard'))

    rule_form = SplitRuleForm()
    if rule_form.validate_on_submit():
        rule = SplitRule.query.filter_by(shop_id=shop.id).first()
        if rule:
            rule.management_base_pct = rule_form.management_base_pct.data
        else:
            rule = SplitRule(
                shop_id=shop.id,
                management_base_pct=rule_form.management_base_pct.data,
            )
            db.session.add(rule)
        db.session.commit()
        flash('Split rule updated.', 'success')

    return redirect(url_for('shareholders.setup'))


@shareholders_bp.route('/lock-period', methods=['POST'])
@login_required
def lock_period_view():
    shop = get_shop()
    if not shop:
        flash('No shop found.', 'warning')
        return redirect(url_for('main.dashboard'))

    period_id = request.form.get('period_id')
    if period_id:
        period = db.session.get(Period, int(period_id))
        if period is None or period.shop_id != shop.id:
            flash('Period not found.', 'danger')
            return redirect(url_for('shareholders.periods'))
        try:
            lock_period(period.id)
            flash('Period locked successfully.', 'success')
        except ValueError as e:
            flash(str(e), 'danger')

    return redirect(url_for('shareholders.periods'))


@shareholders_bp.route('/periods')
@login_required
def periods():
    shop = get_shop()
    if not shop:
        flash('No shop found.', 'warning')
        return redirect(url_for('main.dashboard'))

    all_periods = Period.query.filter_by(shop_id=shop.id).order_by(Period.period_end.desc()).all()
    partners = Partner.query.filter_by(shop_id=shop.id).all()

    return render_template(
        'shareholders/periods.html',
        periods=all_periods,
        partners=partners,
        shop=shop,
    )
