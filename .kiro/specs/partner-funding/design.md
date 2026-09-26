# Partner Phone Funding - Design Document

## 1. Overview

This document designs the completion of the partner/investor "funded phones" feature: an owner-facing assignment flow (Stock In dropdown → stock edit → bulk backfill) and an investor-facing read-only view (dashboard count + My Phones list). Funding is **purely informational**; money flows are untouched.

### 1.1 Design Goals

1. **Minimal Schema Change**: reuse the already-migrated `stock_items.funded_by_partner_id` — no new tables
2. **Visibility Only**: zero coupling to `calculate_split`, `Period`, `PeriodSnapshot`
3. **Tenant Safe**: every read/write scoped by `shop_id`; partner must belong to the same shop and have `role='investor'`
4. **UI Consistency**: existing form-grid, card-view tables (`data-label`), badges, and palette
5. **Deletable Partners**: no dangling references — partner delete nullifies links

### 1.2 Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Nullable plain int column, no FK** | Matches the existing "Links" pattern in `StockItem` (avoids circular dependencies) |
| **Dropdown filtered to `role='investor'`** | Confirmed requirement; owners operate the shop, investors only observe |
| **Validation in route, not form class** | `stock/in` and `stock/edit` routes already do shop-scoped business validation; keeps one source of truth |
| **Bulk assign = single POST with `item_ids`** | Simple, transactional, easy to tenant-guard; selection UI reuses stock list checkboxes |
| **Partner delete → nullify, not block** | Phones are shop assets regardless of funder; blocking would trap owners. Locked-snapshot rule stays for the partner record itself |
| **Investor query = partner id lookup** | Investor → `Partner(investor_user_id=...)` → filter stock; already implemented, no changes |

---

## 2. Architecture Overview

### 2.1 Component Map

```
OWNER SIDE                              INVESTOR SIDE
──────────                              ─────────────
stock/form.html                         investor_layout.html
  "Funded by" dropdown                    ├─ dashboard.html  (count)
        │                                 └─ my_phones.html  (list)
        ▼                                        ▲
stock routes                          investor routes (unchanged)
  POST /stock/in   ── validates ──┐              │
  POST /stock/<id>/edit           │              │
  POST /stock/assign-funder (new) │              │
        │                         │              │
        ▼                         ▼              │
   Partner.query.filter_by(shop_id, role='investor')  ← validation source
        │
        ▼
   StockItem.funded_by_partner_id  ─────────────┘
   (migration 7f3a9c2d5e18)

shareholders routes
  POST /partner/<id>/delete → UPDATE stock_items SET funded_by_partner_id=NULL
                              WHERE funded_by_partner_id = <id>
```

### 2.2 Technology Stack
- No new dependencies — Flask + Flask-SQLAlchemy + Jinja2 + existing CSS

---

## 3. Data Model Design

### 3.1 Existing — `StockItem` (already migrated)

```python
class StockItem(db.Model):
    ...
    # Links (plain IDs — no FK to avoid circular dependency)
    ...
    funded_by_partner_id = db.Column(db.Integer, nullable=True, index=True)  # NEW (added)
```

### 3.2 Existing — `Partner`

```python
class Partner(db.Model):
    id, shop_id, name
    role                 # 'owner' | 'investor'  ← filter uses 'investor'
    investment_amount, investment_ratio
    investor_user_id     # portal login link (nullable — funding doesn't require login)
```

### 3.3 Invariants

1. `funded_by_partner_id IS NULL` → unassigned phone (default; back-compatible)
2. If not NULL → referenced `Partner` must satisfy `partner.shop_id == stock_item.shop_id` and `partner.role == 'investor'`
3. Deleting a partner nullifies (2) references before the row is removed
4. `funded_by_partner_id` never participates in any aggregate used by the split engine

---

## 4. Interface Design

### 4.1 Stock In Form (`/stock/in`)

New optional field:

```html
<div class="field">
  <label>Funded by (optional)</label>
  <select name="funded_by_partner_id">
    <option value="0">Not assigned</option>
    {% for inv in investors %}
    <option value="{{ inv.id }}">{{ inv.name }} — {{ "%.1f"|format(inv.investment_ratio) }}%</option>
    {% endfor %}
  </select>
</div>
```

Route logic (in `add_stock`):

```python
funded_by = request.form.get('funded_by_partner_id', type=int) or None
if funded_by:
    inv = Partner.query.filter_by(
        id=funded_by, shop_id=shop.id, role='investor').first()
    funded_by = inv.id if inv else None      # foreign/invalid → NULL
# applied to every StockItem created for quantity N
```

- Dropdown rendered only when the shop has ≥1 investor partner
- `value="0"` avoids `int('')` parsing issues; treated as NULL

### 4.2 Stock Edit (`/stock/<id>/edit`)

Same field + validation; update `item.funded_by_partner_id` on save. Pre-select current value. Also accepts clearing (0 → NULL).

### 4.3 Stock List — Funder Column + Bulk Assign

**Read:** template shows `item.funder_name` resolved via a per-shop dict passed from the route:

```python
investors = {p.id: p.name for p in Partner.query.filter_by(
    shop_id=shop.id, role='investor').all()}
# template: investors.get(item.funded_by_partner_id) → chip or '—'
```

(One query per page, no N+1.)

**New endpoint:**

```
POST /stock/assign-funder
  form: item_ids[] (list[int]), partner_id (int, 0 = clear)
  guards: @login_required, CSRF, shop scoping
  1. partner_id → validate partner in shop + role investor (unless 0/clear)
  2. load StockItems WHERE id IN (item_ids) AND shop_id = shop.id   ← foreign ids silently skipped
  3. if none matched → flash warning, redirect
  4. set/clear funded_by_partner_id, commit
  5. flash "N phones assigned to <name>" (or "N phones unassigned")
  redirect back to /stock/ (preserving filters)
```

**UI:** checkboxes in first column of the table (hidden `thead` label in card view), a bulk bar:

```
[ n selected ]  [Assign funder ▾]  [Apply]   ← hidden when 0 selected
```

Mobile: bar stacks vertically (`flex-direction: column` in the ≤767 media query), checkboxes remain tappable (min 44px row hit area already provided by card padding).

### 4.4 Partner Delete Cascade

In `delete_partner` (already written this session), before `db.session.delete(partner)`:

```python
n = StockItem.query.filter_by(funded_by_partner_id=partner.id).update(
    {StockItem.funded_by_partner_id: None})
```

Flush → recalc ratios → commit (single transaction). Flash: `Partner X removed. N phones returned to unassigned stock.`

### 4.5 Investor Side (verify only)

```python
# dashboard
my_phones_count = StockItem.query.filter_by(
    shop_id=partner.shop_id, funded_by_partner_id=partner.id).count()

# my-phones
phones = StockItem.query.filter_by(
    shop_id=partner.shop_id, funded_by_partner_id=partner.id
).order_by(StockItem.created_at.desc()).all()
```

Both already exist — require only tests. Template guard for unsold phones:

```jinja
{{ "Rs {:,.0f}".format(phone.sale_price | float) if phone.sale_price else '—' }}
```

---

## 5. Business Logic Rules

| # | Rule | Enforcement |
|---|------|-------------|
| 1 | Only `role='investor'` partners selectable | Dropdown source + server-side filter (defense in depth) |
| 2 | Partner and stock must share `shop_id` | Validation in every route |
| 3 | Assignment optional, default NULL | `value="0"` → None |
| 4 | Foreign item IDs in bulk are skipped, not error'd | `WHERE ... AND shop_id=` filter |
| 5 | Partner delete nullifies links | `UPDATE ... WHERE funded_by_partner_id=` in same transaction |
| 6 | Split engine never reads the column | Code search invariant + regression test |
| 7 | Investor sees only own phones | Filter by `partner.id` reached via own `investor_user_id` |

---

## 6. Security Considerations

1. **Tenant isolation** — all new queries carry `shop_id`; bulk endpoint filters both items and partner by shop
2. **CSRF** — all forms include `csrf_token()`; global `CSRFProtect` already active
3. **Role forgery** — posting an `owner` partner id or another shop's partner id → silently treated as NULL/empty (no info leak about existence)
4. **Investor read-only** — no new investor endpoints; existing `investor_login_required`
5. **No mass assignment** — `funded_by_partner_id` never taken from raw JSON/body without whitelist validation described above

---

## 7. Testing Strategy

| Layer | Cases |
|-------|-------|
| Unit/route (owner) | assign at stock-in (valid, foreign id, owner-role id, 0/absent); edit reassign + clear; bulk assign (mixed valid/foreign ids, empty selection, foreign partner) |
| Cascade | partner delete nullifies phones + flash count; partner with snapshots still blocked |
| Investor | count == list length; own phones only; other tenant's phones invisible; NULL sale price renders; empty state |
| Regression | `test_pnl` / `test_shareholder_engine` unchanged; profit-share output identical with funding set |
| Template guards | `test_template_url_for_endpoints_exist`, `test_template_badge_classes_defined` (existing) |
| Responsive | headless Chrome: `/stock/`, `/investor/my-phones` → no overflow at 375px/768px |

---

## 8. Migration & Rollout

1. Migration `7f3a9c2d5e18` already written — run `flask db upgrade` on production **before** deploying code that selects the column (selecting a missing column would 500 stock pages)
2. Deploy code + `?v=6` cache-buster bump if CSS changes
3. No backfill script needed — NULL is valid; owners use bulk assign to backfill
4. Rollback: `flask db downgrade` (drops column; app code must be rolled back first)

---

## 9. Open Items (proposed defaults, confirm at review)

1. Investors see **only** funded phones (not all shop stock) — matches existing template
2. Funder chip **always visible** in owner stock list
3. Bulk bar uses the existing filter/search area (`.filter-bar`) rather than a new floating element
4. `reserved` status: untouched — display logic only
