# Partner Phone Funding (Investor Portal Completion) - Requirements

## Overview
Complete the half-built partner/investor feature: link stock items ("phones") to the investor who funded them, so investors can see which phones their money bought and their live status. The profit-split engine is **not** touched — funding is a visibility/transparency feature only.

Today `StockItem.funded_by_partner_id` exists (migration `7f3a9c2d5e18`) but nothing ever sets it, so the investor portal's "My Phones" and dashboard count always show empty/zero.

## Business Goals
1. Give investors transparency: see the actual phones their investment funded
2. Let shop owners tag purchases with the funding investor at the time of buy
3. Backfill existing stock without re-entering purchases
4. Keep profit distribution unchanged (period engine, investment ratios, split rule)
5. Keep the feature multi-tenant and mobile-friendly (existing card-view tables)

### Decisions (confirmed)
| # | Decision | Choice |
|---|----------|--------|
| 1 | How phones get linked | **"Funded by" dropdown at Stock In**, editable on stock edit, bulk backfill from stock list |
| 2 | Economic impact | **Visibility only** — no change to period splits or payouts |
| 3 | Who can fund | **Investors only** (`Partner.role == 'investor'`) |

---

## User Stories & Acceptance Criteria

### 1. Owner: Assign a Funder

#### 1.1 Stock In Form — Funded By Dropdown
**As a shop owner**
**I want to** choose which investor funded the phones I'm buying
**So that** the purchase is attributed to the right partner from day one

**Acceptance Criteria:**
- [ ] Stock In form has an optional "Funded by" dropdown
- [ ] Dropdown lists only partners with `role='investor'` belonging to the current shop (name + investment ratio)
- [ ] Dropdown includes a first option: "Not assigned"
- [ ] Investors with no linked portal account still appear (funding does not require a login)
- [ ] Selecting an investor saves `funded_by_partner_id` on every StockItem row created by that purchase (multi-quantity)
- [ ] Leaving "Not assigned" stores NULL — purchase flow behaves exactly as before
- [ ] Invalid/foreign partner IDs (another shop's partner) are rejected and stored as NULL
- [ ] Form still passes validation when no investor exists in the shop (dropdown hidden or disabled)

#### 1.2 Stock Edit — Change or Clear Funder
**As a shop owner**
**I want to** change the funder of an existing phone
**So that** mistakes can be corrected

**Acceptance Criteria:**
- [ ] Stock edit page shows the same "Funded by" dropdown, pre-selected with current funder
- [ ] Owner can reassign to a different investor of the same shop
- [ ] Owner can set it back to "Not assigned" (NULL)
- [ ] Change takes effect immediately for the investor's portal
- [ ] Only items in the current shop can be edited (shop scoping unchanged)

#### 1.3 Stock List — Bulk Backfill
**As a shop owner with existing stock**
**I want to** select multiple phones and assign them to an investor in one action
**So that** I don't have to open every edit page

**Acceptance Criteria:**
- [ ] Stock list rows have a checkbox (desktop) that participates in the existing mobile card view
- [ ] A bulk action bar appears when ≥1 row is selected: "Assign funder" + investor dropdown + Apply
- [ ] Apply sets `funded_by_partner_id` on all selected items of the current shop
- [ ] Bulk endpoint rejects item IDs from other shops (they are skipped, not modified)
- [ ] Empty selection → no-op with a warning flash
- [ ] Stock list shows the current funder per phone (column/chip with `data-label` for mobile card view)

---

### 2. Investor: See Funded Phones

#### 2.1 My Phones Page
**As an investor**
**I want to** see every phone my investment funded with its current status
**So that** I can track what my money is doing

**Acceptance Criteria:**
- [ ] `/investor/my-phones` lists all StockItems where `funded_by_partner_id` equals the logged-in investor's partner id, scoped to the partner's shop
- [ ] Columns: Model, IMEI, Cost Price, Sale Price, Status, Added (as currently templated)
- [ ] Status badges render: In Stock (green), Sold (muted), Reserved (gold) — classes already defined
- [ ] Sale Price shows "—" when the phone is not sold (template robustness for NULL)
- [ ] Empty state shows the existing "No phones funded by your investment yet." message
- [ ] Header shows investment amount + ratio (already implemented, must keep working)
- [ ] Investor cannot see phones funded by other partners or other shops

#### 2.2 Dashboard Count
**As an investor**
**I want** the dashboard "My Funded Phones" tile to show the real count
**So that** the number matches my phones list

**Acceptance Criteria:**
- [ ] `/investor/dashboard` count == number of rows on My Phones page
- [ ] "View all →" link navigates to My Phones
- [ ] Works with zero phones (shows 0, no errors)

#### 2.3 Profit Share Unchanged
**As an investor**
**I want** my profit share to keep being calculated by the period engine
**So that** funding phones doesn't change what I'm paid

**Acceptance Criteria:**
- [ ] Funded phones have **zero effect** on `calculate_split`, period locking, snapshots, or management base %
- [ ] `/investor/profit-share` output is byte-identical before and after assigning phones (regression-tested)
- [ ] Spec/design documents state explicitly: funding ≠ economic entitlement

---

### 3. Lifecycle & Safety

#### 3.1 Partner Deletion
**As a shop owner**
**I want** deleting an investor partner to behave predictably for already-funded phones
**So that** no phone is left pointing at a dead record

**Acceptance Criteria:**
- [ ] Deleting a partner sets `funded_by_partner_id = NULL` on all phones they funded (phones return to unassigned shop stock)
- [ ] Confirmation flash mentions how many phones were unassigned
- [ ] Existing rule preserved: partners with locked-period snapshots cannot be deleted
- [ ] Linked portal login (Investor account) deletion behavior unchanged

#### 3.2 Multi-tenancy & Security
**Acceptance Criteria:**
- [ ] Every query involving partners or funded phones filters by the current shop
- [ ] Owner endpoints require login; investor endpoints keep `investor_login_required`
- [ ] Bulk assign endpoint validates: item ownership, partner ownership, partner role
- [ ] CSRF token on all new/modified forms
- [ ] No new endpoints leak data across tenants (covered by tests)

#### 3.3 Responsive & UI Consistency
**Acceptance Criteria:**
- [ ] New stock-list funder chip/column has `data-label` → renders in mobile card view (≤767px)
- [ ] Bulk action bar stacks correctly at 375px (no horizontal overflow)
- [ ] Uses existing palette/classes (`badge-*`, `.chip`, `.btn`); no new CSS framework
- [ ] Cache-buster bumped (`?v=6` → `?v=7`) when CSS changes

---

## Technical Requirements

### Database Changes Required
1. `stock_items.funded_by_partner_id` (nullable int, indexed) — **already added**, migration `7f3a9c2d5e18` must be applied on production (`flask db upgrade`)
2. No new tables
3. No changes to `partners`, `split_rule`, `periods`, `period_snapshots`

### Code Changes Required
- `app/stock/forms.py` / routes: accept + validate `funded_by_partner_id` on add & edit
- `app/stock/routes.py`: bulk assign endpoint; funder shown in list context
- `app/shareholders/routes.py`: nullify funded phones on partner delete
- `app/templates/stock/list.html`: funder chip, checkboxes, bulk action bar
- `app/templates/stock/form.html`: "Funded by" dropdown
- `app/templates/investor/my_phones.html`: NULL sale-price guard
- Investor routes: verify existing queries (no change expected)

### Explicit Non-Goals
- No per-phone economics, no changes to `calculate_split` / `lock_period`
- No new `reserved` status workflow (display support stays as-is)
- No investor-side editing (view only)
- No automatic funding by ratio

---

## Implementation Phases

### Phase 1: Owner Assignment (core)
- Dropdown on stock add + edit with shop-scoped investor list
- Server-side validation (role + ownership)
- Partner delete nullifies funded phones

### Phase 2: Backfill & Visibility
- Stock list funder chip + checkboxes + bulk assign endpoint
- Mobile card-view support for new controls

### Phase 3: Investor Wiring
- Verify dashboard count, My Phones list, NULL sale price guard
- Empty states

### Phase 4: Tests & Verification
- Route tests: assign, reassign, clear, invalid/foreign IDs, bulk, delete-cascade
- Investor visibility tests (own phones only, other tenants invisible)
- Profit-share regression test (identical output with/without funding)
- Headless Chrome overflow check at 375px/768px for changed pages

---

## Success Metrics
- 100% of investor portal "My Phones" rows correspond to correct partner + shop
- Zero cross-tenant leaks (tests green)
- Full suite green (`pytest` — currently 74 tests)
- No horizontal overflow on changed pages at 375px/768px

---

## Open Questions & Decisions Needed
1. ~~How to assign?~~ — **Decided:** dropdown at Stock In + edit + bulk backfill
2. ~~Economic impact?~~ — **Decided:** visibility only
3. ~~Who funds?~~ — **Decided:** investors only
4. Should investors see unfunded shop stock at all? — **Proposed: no** (My Phones = funded only)
5. Should the stock list show funder to owner by default, or behind a toggle? — **Proposed: always show** (chip, collapses in card view)

---

## Next Steps
1. Review this requirements document
2. Review `design.md` (data flow, endpoints, validation rules)
3. Approve → generate `tasks.md` checklist
4. Implement Phase 1-4 with tests
