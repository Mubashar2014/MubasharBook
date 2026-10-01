from datetime import date
from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required
from app.khata import khata_bp
from app.models.khata import KhataEntry
from app.models.cashbook import CashEntry
from app.models.stock import StockItem
from app.extensions import db
from app.utils import (
    get_user_shop, ensure_opening_cash, OPENING_CAPITAL_DESC,
    party_whatsapp_map, wa_share_link, reminder_text,
)
from sqlalchemy import func


@khata_bp.route('/')
@login_required
def list_khata():
    shop = get_user_shop()
    view = request.args.get('view', 'parties')  # parties or all

    # Party-wise summary (pending only)
    party_summary = db.session.query(
        KhataEntry.party_name,
        KhataEntry.entry_type,
        func.sum(KhataEntry.amount - KhataEntry.settled_amount).label('pending_amount'),
        func.count(KhataEntry.id).label('entry_count'),
    ).filter(
        KhataEntry.shop_id == shop.id,
        KhataEntry.status == 'pending',
    ).group_by(
        KhataEntry.party_name, KhataEntry.entry_type
    ).all()

    # All entries
    all_entries = KhataEntry.query.filter_by(shop_id=shop.id).order_by(
        KhataEntry.entry_date.desc()
    ).all()

    # Totals
    total_receivable = sum(float(p.pending_amount) for p in party_summary if p.entry_type == 'receivable')
    total_payable = sum(float(p.pending_amount) for p in party_summary if p.entry_type == 'payable')

    known_numbers = party_whatsapp_map(shop.id)
    wa_links = {
        p.party_name: wa_share_link(
            known_numbers.get(p.party_name),
            reminder_text(shop.name, p.party_name, p.pending_amount, p.entry_type),
        )
        for p in party_summary
    }

    return render_template('khata/list.html',
        party_summary=party_summary,
        all_entries=all_entries,
        total_receivable=total_receivable,
        total_payable=total_payable,
        view=view,
        wa_links=wa_links,
    )


@khata_bp.route('/party/<party_name>')
@login_required
def party_detail(party_name):
    shop = get_user_shop()
    entries = KhataEntry.query.filter_by(
        shop_id=shop.id, party_name=party_name
    ).order_by(KhataEntry.entry_date.desc()).all()

    pending = [e for e in entries if e.status == 'pending']
    settled = [e for e in entries if e.status == 'settled']
    total_pending = sum(float(e.amount) - float(e.settled_amount or 0) for e in pending)
    entry_type = pending[0].entry_type if pending else (settled[0].entry_type if settled else 'receivable')

    return render_template('khata/party.html',
        party_name=party_name,
        entries=entries,
        pending_entries=pending,
        settled_entries=settled,
        total_pending=total_pending,
        entry_type=entry_type,
        wa_link=wa_share_link(
            party_whatsapp_map(shop.id).get(party_name),
            reminder_text(shop.name, party_name, total_pending, entry_type),
        ) if total_pending > 0 else None,
    )


@khata_bp.route('/<int:entry_id>/settle', methods=['POST'])
@login_required
def settle_khata(entry_id):
    shop = get_user_shop()
    entry = KhataEntry.query.filter_by(id=entry_id, shop_id=shop.id).first_or_404()

    if entry.status == 'settled':
        flash('This entry is already settled.', 'warning')
        return redirect(url_for('khata.list_khata'))

    pending = float(entry.amount) - float(entry.settled_amount or 0)

    # Auto cash entry
    if entry.entry_type == 'receivable':
        cash_type = 'in'
        desc = f"Khata settled: {entry.party_name} — {entry.description}"
    else:
        cash_type = 'out'
        desc = f"Khata settled: paid to {entry.party_name} — {entry.description}"

    ensure_opening_cash(shop)
    prev = CashEntry.query.filter_by(shop_id=shop.id).order_by(CashEntry.id.desc()).first()
    prev_balance = float(prev.balance_after) if prev and prev.balance_after else float(shop.initial_investment or 0)
    new_balance = prev_balance + pending if cash_type == 'in' else prev_balance - pending

    cash = CashEntry(
        shop_id=shop.id,
        entry_type=cash_type,
        amount=pending,
        description=desc,
        entry_date=date.today(),
        linked_stock_id=entry.linked_stock_id,
        balance_after=new_balance,
    )
    db.session.add(cash)
    db.session.flush()

    entry.settled_amount = entry.amount
    entry.status = 'settled'
    entry.settled_date = date.today()
    entry.settled_cash_entry_id = cash.id
    db.session.commit()

    flash(f'Khata settled — Rs {pending:,.0f} added to cashbook.', 'success')

    # Linked to a phone? Send the settlement receipt right away.
    if entry.linked_stock_id:
        item = StockItem.query.filter_by(id=entry.linked_stock_id, shop_id=shop.id).first()
        if item:
            if item.purchase_khata_entry_id == entry.id:
                rtype = 'purchase'
            elif item.sale_khata_entry_id == entry.id:
                rtype = 'sale'
            else:
                rtype = 'sale' if item.status == 'sold' else 'purchase'
            return redirect(url_for('stock.receipt', item_id=item.id, type=rtype, settled=1))

    return redirect(url_for('khata.party_detail', party_name=entry.party_name))
