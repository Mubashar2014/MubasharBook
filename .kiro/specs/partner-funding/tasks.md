# Partner Phone Funding - Tasks

> Spec: `requirements.md` + `design.md` in this folder.
> Mark tasks done as they land; keep commits small and tested.
> Test command: `cd ~/mmmw_mobiles && bahi/venv/bin/python -m pytest bahi/tests -q`

## Phase 1 — Owner Assignment (core)

- [x] 1.1 `app/stock/routes.py::add_stock` — read `funded_by_partner_id` (0/absent → NULL), validate `role='investor'` + `shop_id`, apply to all created StockItems
- [x] 1.2 Pass shop investors (`id, name, investment_ratio`) to stock form template context
- [x] 1.3 `app/templates/stock/form.html` — "Funded by" dropdown (rendered only if ≥1 investor; first option "Not assigned")
- [x] 1.4 `app/stock/routes.py::edit_stock` — same field: pre-select, reassign, clear
- [x] 1.5 `app/shareholders/routes.py::delete_partner` — nullify `funded_by_partner_id` before delete + flash with count
- [x] 1.6 Tests: assign valid / foreign-partner-id → NULL / owner-role-id → NULL / absent → NULL; edit reassign + clear; delete cascade

## Phase 2 — Backfill & Visibility

- [x] 2.1 Stock list route: build `{partner_id: name}` for shop investors, pass to template (single query, no N+1)
- [x] 2.2 `app/templates/stock/list.html` — funder chip column with `data-label="Funded By"` (card view)
- [x] 2.3 Row checkboxes + bulk action bar (dropdown + Apply); bar hidden at 0 selected; stacks ≤767px
- [x] 2.4 `POST /stock/assign-funder` — shop-scoped item fetch (foreign ids skipped), partner validation, 0 → clear, flash "N phones …", redirect preserving filters
- [x] 2.5 Tests: bulk mixed ids, empty selection warning, foreign partner, foreign items untouched, other tenant cannot assign

## Phase 3 — Investor Wiring

- [x] 3.1 Verify `/investor/dashboard` count == My Phones rows (test)
- [x] 3.2 `app/templates/investor/my_phones.html` — NULL `sale_price` → "—" guard
- [x] 3.3 Tests: investor sees only own funded phones; other tenant's phones invisible; empty state; count match

## Phase 4 — Regression & Polish

- [x] 4.1 Regression test: profit-share / split engine output identical with and without `funded_by_partner_id` set
- [x] 4.2 Existing guards still green: `test_template_url_for_endpoints_exist`, `test_template_badge_classes_defined`
- [x] 4.3 Full suite green (74 baseline + new tests)
- [x] 4.4 Headless Chrome overflow check: `/stock/`, `/stock/in`, `/investor/my-phones` at 375px + 768px (fix if any; bump `?v=6` → `?v=7` on CSS change)
- [x] 4.5 Update `PROJECT_STATUS.md` — mark investor portal items accurate (funded phones now functional)

## Phase 5 — Deploy

- [ ] 5.1 Production: `flask db upgrade` (applies `7f3a9c2d5e18` — **must run before code deploy**)
- [ ] 5.2 Deploy code, restart, hard-refresh (Ctrl+Shift+R)
- [ ] 5.3 Smoke: buy stock with investor selected → investor portal shows phone; bulk-assign old stock; delete test partner → phones unassigned
