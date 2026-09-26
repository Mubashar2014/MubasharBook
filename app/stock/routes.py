from datetime import date
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app.stock import stock_bp
from app.stock.forms import StockInForm, StockOutForm
from app.models.stock import StockItem
from app.models.cashbook import CashEntry
from app.models.khata import KhataEntry
from app.models.shop import Shop
from app.models.shareholder import Partner
from app.extensions import db
from app.utils import get_user_shop, ensure_opening_cash, recalc_cash_balances, OPENING_CAPITAL_DESC
from sqlalchemy import or_


def _shop_investors(shop_id):
    return Partner.query.filter_by(shop_id=shop_id, role='investor').order_by(Partner.name.asc()).all()


def _resolve_funder(shop_id, raw):
    """Validate a submitted funder id: same shop + role investor, else None."""
    try:
        pid = int(raw) if raw else 0
    except (TypeError, ValueError):
        return None
    if not pid:
        return None
    partner = Partner.query.filter_by(id=pid, shop_id=shop_id, role='investor').first()
    return partner.id if partner else None


def _get_last_balance(shop_id):
    last = CashEntry.query.filter_by(shop_id=shop_id).order_by(CashEntry.id.desc()).first()
    if last and last.balance_after is not None:
        return float(last.balance_after)
    shop = db.session.get(Shop, shop_id)
    if shop is not None:
        return ensure_opening_cash(shop)
    return 0.0


def _create_cash_entry(shop_id, entry_type, amount, description, entry_date, linked_stock_id=None):
    if amount <= 0:
        return None
    prev_balance = _get_last_balance(shop_id)
    new_balance = prev_balance + amount if entry_type == 'in' else prev_balance - amount
    entry = CashEntry(
        shop_id=shop_id,
        entry_type=entry_type,
        amount=amount,
        description=description,
        entry_date=entry_date,
        linked_stock_id=linked_stock_id,
        balance_after=new_balance,
    )
    db.session.add(entry)
    db.session.flush()
    return entry


def _create_khata_entry(shop_id, party_name, entry_type, amount, description, entry_date, linked_stock_id=None):
    if amount <= 0 or not party_name:
        return None
    entry = KhataEntry(
        shop_id=shop_id,
        party_name=party_name.strip(),
        entry_type=entry_type,
        amount=amount,
        description=description,
        entry_date=entry_date,
        linked_stock_id=linked_stock_id,
        status='pending',
    )
    db.session.add(entry)
    db.session.flush()
    return entry


# ── LIST ──────────────────────────────────────────────────

@stock_bp.route('/')
@login_required
def list_stock():
    shop = get_user_shop()
    status_filter = request.args.get('status', 'all')
    search = request.args.get('q', '').strip()

    all_items = StockItem.query.filter_by(shop_id=shop.id).order_by(StockItem.created_at.desc()).all()

    # Stats always reflect all items (regardless of filter)
    total_items = len(all_items)
    in_stock_count = sum(1 for item in all_items if item.status == 'in_stock')
    sold_count = sum(1 for item in all_items if item.status == 'sold')
    total_value = sum(float(item.cost_price) * item.quantity for item in all_items if item.status == 'in_stock')

    # Server-side filter for initial page load; JS also filters live in the browser
    items = all_items
    if status_filter in ('in_stock', 'sold'):
        items = [i for i in items if i.status == status_filter]
    if search:
        term = search.lower()
        items = [
            i for i in items
            if term in (i.model_name or '').lower()
            or term in (i.imei or '').lower()
            or term in (i.supplier_name or '').lower()
            or term in (i.customer_name or '').lower()
        ]

    return render_template(
        'stock/list.html',
        items=items,
        total_items=total_items,
        in_stock_count=in_stock_count,
        sold_count=sold_count,
        total_value=total_value,
        status_filter=status_filter,
        search=search,
        funder_names={p.id: p.name for p in _shop_investors(shop.id)},
    )


# ── BULK ASSIGN FUNDER ───────────────────────────────────

@stock_bp.route('/assign-funder', methods=['POST'])
@login_required
def assign_funder():
    shop = get_user_shop()

    back_qs = request.form.get('back_qs', '')
    redirect_target = url_for('stock.list_stock')
    if back_qs and all(c.isalnum() or c in '&=_%.-+' for c in back_qs):
        redirect_target += '?' + back_qs

    try:
        item_ids = [int(x) for x in request.form.getlist('item_ids') if str(x).strip().isdigit()]
    except (TypeError, ValueError):
        item_ids = []
    if not item_ids:
        flash('No phones selected.', 'warning')
        return redirect(redirect_target)

    raw_partner = (request.form.get('partner_id') or '').strip()
    try:
        partner_id = int(raw_partner or 0)
    except ValueError:
        partner_id = -1

    partner = None
    if partner_id > 0:
        partner = Partner.query.filter_by(id=partner_id, shop_id=shop.id, role='investor').first()
        if not partner:
            flash('Invalid funder selected.', 'warning')
            return redirect(redirect_target)
    elif partner_id < 0:
        flash('Invalid funder selected.', 'warning')
        return redirect(redirect_target)

    items = StockItem.query.filter(
        StockItem.id.in_(item_ids), StockItem.shop_id == shop.id
    ).all()
    if not items:
        flash('No matching phones found.', 'warning')
        return redirect(redirect_target)

    new_funder = partner.id if partner else None
    for item in items:
        item.funded_by_partner_id = new_funder
    db.session.commit()

    if partner:
        flash(f'{len(items)} phone(s) assigned to {partner.name}.', 'success')
    else:
        flash(f'{len(items)} phone(s) unassigned.', 'success')
    return redirect(redirect_target)


# ── STOCK IN (BUY) ───────────────────────────────────────

@stock_bp.route('/in', methods=['GET', 'POST'])
@login_required
def stock_in():
    shop = get_user_shop()
    form = StockInForm()
    investors = _shop_investors(shop.id)
    selected_funder = _resolve_funder(shop.id, request.form.get('funded_by_partner_id')) if request.method == 'POST' else None

    if form.validate_on_submit():
        total_cost = float(form.cost_price.data) * form.quantity.data
        paid_now = float(form.purchase_paid.data or 0)
        pending = total_cost - paid_now
        expense_amt = float(form.purchase_expense_amount.data or 0)
        supplier = form.supplier_name.data.strip() if form.supplier_name and form.supplier_name.data.strip() else None

        # If there's a pending amount, supplier name is required
        if pending > 0 and not supplier:
            flash(f'Rs {pending:,.0f} is pending — please enter a supplier name to track in khata.', 'warning')
            return render_template('stock/stock_in.html', form=form, action='Add', investors=investors, selected_funder=selected_funder)

        # Cannot overpay at purchase
        if pending < 0:
            flash(f'You cannot pay more than the total cost (Rs {total_cost:,.0f}).', 'warning')
            return render_template('stock/stock_in.html', form=form, action='Add', investors=investors, selected_funder=selected_funder)

        item = StockItem(
            shop_id=shop.id,
            model_name=form.model_name.data.strip(),
            imei=form.imei.data.strip() if form.imei.data else None,
            quantity=form.quantity.data,
            cost_price=form.cost_price.data,
            supplier_name=supplier,
            purchase_date=form.purchase_date.data,
            purchase_paid=paid_now,
            purchase_pending=pending,
            purchase_expense_desc=form.purchase_expense_desc.data.strip() if form.purchase_expense_desc and form.purchase_expense_desc.data.strip() else None,
            purchase_expense_amount=expense_amt,
            funded_by_partner_id=selected_funder,
        )
        db.session.add(item)
        db.session.flush()

        # Auto cash entry: paid amount
        if paid_now > 0:
            supplier_label = form.supplier_name.data.strip() if form.supplier_name else 'cash'
            cash = _create_cash_entry(
                shop.id, 'out', paid_now,
                f"Stock: {item.model_name} x{item.quantity} — paid to {supplier_label}",
                form.purchase_date.data, item.id,
            )
            item.purchase_cash_entry_id = cash.id if cash else None

        # Auto cash entry: extra expense
        if expense_amt > 0:
            desc = form.purchase_expense_desc.data.strip() if form.purchase_expense_desc.data else 'Stock purchase expense'
            cash = _create_cash_entry(
                shop.id, 'out', expense_amt,
                f"{desc} — {item.model_name}",
                form.purchase_date.data, item.id,
            )
            item.purchase_expense_cash_entry_id = cash.id if cash else None

        # Auto khata entry: pending amount to supplier
        if pending > 0 and form.supplier_name and form.supplier_name.data.strip():
            khata = _create_khata_entry(
                shop.id, form.supplier_name.data.strip(), 'payable', pending,
                f"Stock: {item.model_name} x{item.quantity}",
                form.purchase_date.data, item.id,
            )
            item.purchase_khata_entry_id = khata.id if khata else None

        db.session.commit()
        flash('Stock added successfully.', 'success')
        return redirect(url_for('stock.list_stock'))

    form.purchase_date.data = date.today()
    return render_template('stock/stock_in.html', form=form, action='Add', investors=investors, selected_funder=selected_funder)


# ── STOCK OUT (SELL) ─────────────────────────────────────

@stock_bp.route('/<int:item_id>/sell', methods=['GET', 'POST'])
@login_required
def stock_out(item_id):
    shop = get_user_shop()
    item = StockItem.query.filter_by(id=item_id, shop_id=shop.id, status='in_stock').first_or_404()
    form = StockOutForm()

    if form.validate_on_submit():
        sale_total = float(form.sale_price.data) * item.quantity
        received_now = float(form.sale_received.data or 0)
        pending = sale_total - received_now
        expense_amt = float(form.sale_expense_amount.data or 0)
        customer = form.customer_name.data.strip() if form.customer_name and form.customer_name.data.strip() else None

        # If there's a pending amount, customer name is required
        if pending > 0 and not customer:
            flash(f'Rs {pending:,.0f} is pending — please enter a customer name to track in khata.', 'warning')
            return render_template('stock/stock_out.html', form=form, item=item)

        # Update stock item
        item.status = 'sold'
        item.sale_price = form.sale_price.data
        item.customer_name = customer
        item.sale_date = form.sale_date.data
        item.sale_received = received_now
        item.sale_pending = pending
        item.sale_expense_desc = form.sale_expense_desc.data.strip() if form.sale_expense_desc.data else None
        item.sale_expense_amount = expense_amt
        db.session.flush()

        # Auto cash entry: received amount
        if received_now > 0:
            customer_label = item.customer_name if item.customer_name else 'cash'
            cash = _create_cash_entry(
                shop.id, 'in', received_now,
                f"Sold: {item.model_name} x{item.quantity} — received from {customer_label}",
                form.sale_date.data, item.id,
            )
            item.sale_cash_entry_id = cash.id if cash else None

        # Auto cash entry: extra expense
        if expense_amt > 0:
            desc = form.sale_expense_desc.data.strip() if form.sale_expense_desc.data else 'Sale expense'
            cash = _create_cash_entry(
                shop.id, 'out', expense_amt,
                f"{desc} — {item.model_name}",
                form.sale_date.data, item.id,
            )
            item.sale_expense_cash_entry_id = cash.id if cash else None

        # Auto khata entry: pending from customer
        if pending > 0 and item.customer_name:
            khata = _create_khata_entry(
                shop.id, item.customer_name, 'receivable', pending,
                f"Sold: {item.model_name} x{item.quantity}",
                form.sale_date.data, item.id,
            )
            item.sale_khata_entry_id = khata.id if khata else None

        db.session.commit()
        flash('Stock sold successfully.', 'success')
        return redirect(url_for('stock.list_stock'))

    form.sale_date.data = date.today()
    return render_template('stock/stock_out.html', form=form, item=item)


# ── EDIT ─────────────────────────────────────────────────

@stock_bp.route('/<int:item_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_stock(item_id):
    shop = get_user_shop()
    item = StockItem.query.filter_by(id=item_id, shop_id=shop.id).first_or_404()
    form = StockInForm(obj=item)
    investors = _shop_investors(shop.id)
    selected_funder = _resolve_funder(shop.id, request.form.get('funded_by_partner_id')) if request.method == 'POST' else item.funded_by_partner_id

    if form.validate_on_submit():
        total_cost = float(form.cost_price.data) * form.quantity.data
        paid_now = float(form.purchase_paid.data or 0)
        pending = total_cost - paid_now
        supplier = form.supplier_name.data.strip() if form.supplier_name and form.supplier_name.data.strip() else None

        # If there's a pending amount, supplier name is required
        if pending > 0 and not supplier:
            flash(f'Rs {pending:,.0f} is pending — please enter a supplier name to track in khata.', 'warning')
            return render_template('stock/stock_in.html', form=form, action='Edit', item=item, investors=investors, selected_funder=selected_funder)

        # Cannot overpay at purchase
        if pending < 0:
            flash(f'You cannot pay more than the total cost (Rs {total_cost:,.0f}).', 'warning')
            return render_template('stock/stock_in.html', form=form, action='Edit', item=item, investors=investors, selected_funder=selected_funder)

        item.model_name = form.model_name.data.strip()
        item.imei = form.imei.data.strip() if form.imei.data else None
        item.quantity = form.quantity.data
        item.cost_price = form.cost_price.data
        item.supplier_name = supplier
        item.purchase_date = form.purchase_date.data
        item.purchase_paid = paid_now
        item.purchase_pending = pending
        item.purchase_expense_desc = form.purchase_expense_desc.data.strip() if form.purchase_expense_desc.data else None
        item.purchase_expense_amount = form.purchase_expense_amount.data or 0
        item.funded_by_partner_id = selected_funder

        # Update linked cash entry (paid amount)
        if item.purchase_cash_entry_id:
            cash = db.session.get(CashEntry, item.purchase_cash_entry_id)
            if cash:
                supplier_label = supplier if supplier else 'cash'
                cash.amount = paid_now
                cash.description = f"Stock: {item.model_name} x{item.quantity} — paid to {supplier_label}"
                cash.entry_date = form.purchase_date.data
        elif paid_now > 0:
            supplier_label = supplier if supplier else 'cash'
            cash = _create_cash_entry(
                shop.id, 'out', paid_now,
                f"Stock: {item.model_name} x{item.quantity} — paid to {supplier_label}",
                form.purchase_date.data, item.id,
            )
            item.purchase_cash_entry_id = cash.id if cash else None

        # Update linked cash entry (extra expense)
        expense_amt = float(form.purchase_expense_amount.data or 0)
        if item.purchase_expense_cash_entry_id:
            cash = db.session.get(CashEntry, item.purchase_expense_cash_entry_id)
            if cash and expense_amt > 0:
                desc = form.purchase_expense_desc.data.strip() if form.purchase_expense_desc.data else 'Stock purchase expense'
                cash.amount = expense_amt
                cash.description = f"{desc} — {item.model_name}"
                cash.entry_date = form.purchase_date.data
            elif cash and expense_amt <= 0:
                db.session.delete(cash)
                item.purchase_expense_cash_entry_id = None
        elif expense_amt > 0:
            desc = form.purchase_expense_desc.data.strip() if form.purchase_expense_desc.data else 'Stock purchase expense'
            cash = _create_cash_entry(
                shop.id, 'out', expense_amt,
                f"{desc} — {item.model_name}",
                form.purchase_date.data, item.id,
            )
            item.purchase_expense_cash_entry_id = cash.id if cash else None

        # Update linked khata entry (pending amount)
        if item.purchase_khata_entry_id:
            khata = db.session.get(KhataEntry, item.purchase_khata_entry_id)
            if khata:
                if pending > 0 and supplier:
                    khata.amount = pending
                    khata.party_name = supplier
                    khata.description = f"Stock: {item.model_name} x{item.quantity}"
                    khata.entry_date = form.purchase_date.data
                else:
                    db.session.delete(khata)
                    item.purchase_khata_entry_id = None
        elif pending > 0 and supplier:
            khata = _create_khata_entry(
                shop.id, supplier, 'payable', pending,
                f"Stock: {item.model_name} x{item.quantity}",
                form.purchase_date.data, item.id,
            )
            item.purchase_khata_entry_id = khata.id if khata else None

        db.session.commit()
        flash('Stock item updated.', 'success')
        return redirect(url_for('stock.list_stock'))

    return render_template('stock/stock_in.html', form=form, action='Edit', item=item, investors=investors, selected_funder=selected_funder)


# ── UN-SELL (REVERT A SALE) ──────────────────────────────

def _collect_linked(item, sale_side_only=False):
    """Cash entries + khata entries belonging to this stock item."""
    cash_ids, khata_ids = set(), set()
    if sale_side_only:
        cash_ids.update({item.sale_cash_entry_id, item.sale_expense_cash_entry_id})
        khata_ids.add(item.sale_khata_entry_id)
    else:
        cash_ids.update({
            item.purchase_cash_entry_id, item.purchase_expense_cash_entry_id,
            item.sale_cash_entry_id, item.sale_expense_cash_entry_id,
        })
        khata_ids.update({item.purchase_khata_entry_id, item.sale_khata_entry_id})
        # Catch-all: khata settle creates cash entries carrying linked_stock_id
        cash_ids.update(r.id for r in CashEntry.query.filter_by(linked_stock_id=item.id).all())
        khata_ids.update(r.id for r in KhataEntry.query.filter_by(linked_stock_id=item.id).all())
    cash_ids.discard(None)
    khata_ids.discard(None)

    cash_rows = [c for c in (db.session.get(CashEntry, cid) for cid in cash_ids) if c]
    khata_rows = [k for k in (db.session.get(KhataEntry, kid) for kid in khata_ids) if k]
    # Cash created by settling one of these khata entries
    settled_ids = {k.settled_cash_entry_id for k in khata_rows if k.settled_cash_entry_id}
    for cid in settled_ids - {c.id for c in cash_rows}:
        settled = db.session.get(CashEntry, cid)
        if settled:
            cash_rows.append(settled)
    return cash_rows, khata_rows


@stock_bp.route('/<int:item_id>/unsell', methods=['POST'])
@login_required
def unsell_stock(item_id):
    shop = get_user_shop()
    item = StockItem.query.filter_by(id=item_id, shop_id=shop.id, status='sold').first_or_404()

    cash_rows, khata_rows = _collect_linked(item, sale_side_only=True)
    for cash in cash_rows:
        db.session.delete(cash)
    for khata in khata_rows:
        db.session.delete(khata)

    item.status = 'in_stock'
    item.sale_price = None
    item.customer_name = None
    item.sale_date = None
    item.sale_received = None
    item.sale_pending = None
    item.sale_expense_desc = None
    item.sale_expense_amount = None
    item.sale_cash_entry_id = None
    item.sale_expense_cash_entry_id = None
    item.sale_khata_entry_id = None
    db.session.flush()
    recalc_cash_balances(shop.id)
    db.session.commit()

    flash(
        f'Sale reversed — {len(cash_rows)} cash entries and {len(khata_rows)} khata entries '
        'removed, balances recalculated. Phone is back in stock.',
        'success',
    )
    return redirect(url_for('stock.list_stock'))


# ── DELETE (REMOVE EVERYTHING) ───────────────────────────

@stock_bp.route('/<int:item_id>/delete', methods=['POST'])
@login_required
def delete_stock(item_id):
    shop = get_user_shop()
    item = StockItem.query.filter_by(id=item_id, shop_id=shop.id).first_or_404()

    cash_rows, khata_rows = _collect_linked(item, sale_side_only=False)
    for cash in cash_rows:
        db.session.delete(cash)
    for khata in khata_rows:
        db.session.delete(khata)
    db.session.delete(item)
    db.session.flush()
    recalc_cash_balances(shop.id)
    db.session.commit()

    flash(
        f'Phone deleted — {len(cash_rows)} cash entries and {len(khata_rows)} khata entries '
        'removed, balances recalculated.',
        'success',
    )
    return redirect(url_for('stock.list_stock'))
