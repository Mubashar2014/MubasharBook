import re
import pathlib
from datetime import date, timedelta

from app.extensions import db
from app.models.user import User, Investor
from app.models.shop import Shop
from app.models.shareholder import Partner, Period


MAIN_PAGES = [
    '/dashboard', '/cashbook/', '/stock/', '/khata/', '/expenses/',
    '/expenses/categories', '/reports/pnl', '/settings',
]


def _get(app, client, path):
    """Request inside a fresh app context so Flask-Login reloads identity."""
    with app.app_context():
        return client.get(path)


def _post(app, client, path, data=None):
    with app.app_context():
        return client.post(path, data=data or {})


def test_main_pages_render(logged_in_client, app):
    for path in MAIN_PAGES:
        resp = _get(app, logged_in_client, path)
        assert resp.status_code == 200, f'{path} -> {resp.status_code}'


def test_shareholders_pages_render(logged_in_client, app):
    resp = _get(app, logged_in_client, '/shareholders/')
    assert resp.status_code == 200
    resp = _get(app, logged_in_client, '/shareholders/periods')
    assert resp.status_code == 200


def test_shareholder_partner_crud(logged_in_client, app):
    _post(app, logged_in_client, '/shareholders/add-partner', {
        'name': 'Ahmed Raza', 'role': 'owner', 'investment_amount': 500000,
    })
    _post(app, logged_in_client, '/shareholders/add-partner', {
        'name': 'Bilal Investor', 'role': 'investor', 'investment_amount': 300000,
    })

    with app.app_context():
        partners = Partner.query.all()
        assert len(partners) == 2
        ratios = sorted(p.investment_ratio for p in partners)
        assert round(ratios[0], 1) == 37.5
        assert round(ratios[1], 1) == 62.5
        owner = Partner.query.filter_by(name='Ahmed Raza').first()
        owner_id = owner.id
        investor_partner_id = Partner.query.filter_by(name='Bilal Investor').first().id

    # Page renders with partners (exercises edit/delete url_for in template)
    resp = _get(app, logged_in_client, '/shareholders/')
    assert resp.status_code == 200
    assert b'Ahmed Raza' in resp.data

    # Edit
    _post(app, logged_in_client, f'/shareholders/partner/{owner_id}/edit', {
        'name': 'Ahmed Raza Updated', 'role': 'owner', 'investment_amount': 800000,
    })
    with app.app_context():
        p = db.session.get(Partner, owner_id)
        assert p.name == 'Ahmed Raza Updated'
        assert float(p.investment_amount) == 800000

    # Delete
    _post(app, logged_in_client, f'/shareholders/partner/{investor_partner_id}/delete')
    with app.app_context():
        assert db.session.get(Partner, investor_partner_id) is None
        remaining = Partner.query.all()
        assert len(remaining) == 1
        assert round(remaining[0].investment_ratio, 1) == 100.0


def test_create_period_flow(logged_in_client, app):
    _post(app, logged_in_client, '/shareholders/create-period')
    with app.app_context():
        periods = Period.query.all()
        assert len(periods) == 1
        assert periods[0].status == 'open'
        span = (periods[0].period_end - periods[0].period_start).days
        assert span == 29

    # Second open period blocked
    _post(app, logged_in_client, '/shareholders/create-period')
    with app.app_context():
        assert Period.query.count() == 1

    resp = _get(app, logged_in_client, '/shareholders/periods')
    assert resp.status_code == 200


def test_investor_pages_render(app):
    with app.app_context():
        u = User(owner_name='Shop Owner', phone='03007777777', email='owner7@t.com',
                 language='en', is_verified=True)
        u.set_password('password123')
        db.session.add(u)
        db.session.flush()
        shop = Shop(user_id=u.id, name="Owner Shop", initial_investment=100000)
        db.session.add(shop)
        db.session.flush()
        u.start_trial(days=7)
        inv = Investor(name='Bilal Investor', email='inv7@t.com', shop_id=shop.id)
        inv.set_password('inv12345')
        db.session.add(inv)
        db.session.flush()
        db.session.add(Partner(
            shop_id=shop.id, name='Bilal Investor', role='investor',
            investment_amount=300000, investment_ratio=100.0,
            investor_user_id=inv.id,
        ))
        db.session.commit()
        inv_id = inv.id

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['investor_id'] = inv_id

    for path in ['/investor/dashboard', '/investor/my-phones', '/investor/profit-share']:
        resp = _get(app, client, path)
        assert resp.status_code == 200, f'{path} -> {resp.status_code}'


def test_admin_pages_render(app):
    with app.app_context():
        admin = User(owner_name='Admin User', phone='03008888888', email='admin8@t.com',
                     language='en', is_verified=True, is_admin=True)
        admin.set_password('password123')
        db.session.add(admin)
        db.session.flush()
        Shop(user_id=admin.id, name="Admin Shop", initial_investment=100000)
        target = User(owner_name='Plain User', phone='03006666666', email='plain8@t.com',
                      language='en', is_verified=True)
        target.set_password('password123')
        db.session.add(target)
        db.session.flush()
        Shop(user_id=target.id, name="Plain Shop", initial_investment=100000)
        db.session.commit()
        admin_id = admin.id
        target_id = target.id

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(admin_id)

    resp = _get(app, client, '/admin/')
    assert resp.status_code == 200
    resp = _get(app, client, f'/admin/user/{target_id}')
    assert resp.status_code == 200


def test_template_url_for_endpoints_exist(app):
    endpoints = {r.endpoint for r in app.url_map.iter_rules()}
    tpl_dir = pathlib.Path(app.root_path) / 'templates'
    pat = re.compile(r"url_for\(\s*['\"]([\w.]+)['\"]")
    missing = []
    for f in tpl_dir.rglob('*.html'):
        for i, line in enumerate(f.read_text().splitlines(), 1):
            for m in pat.finditer(line):
                ep = m.group(1)
                if ep.startswith('static') or '.' not in ep:
                    continue
                if ep not in endpoints:
                    missing.append(f'{f.relative_to(tpl_dir)}:{i} -> {ep}')
    assert not missing, 'Missing endpoints:\n' + '\n'.join(missing)


def test_template_badge_classes_defined(app):
    css_path = pathlib.Path(app.static_folder) / 'css' / 'app.css'
    css = css_path.read_text()
    tpl_dir = pathlib.Path(app.root_path) / 'templates'
    used = set()
    for f in tpl_dir.rglob('*.html'):
        used.update(re.findall(r'badge-[a-z]+', f.read_text()))
    missing = sorted(b for b in used if not re.search(rf'\.{re.escape(b)}\b', css))
    assert not missing, f'Badge classes used in templates but not in app.css: {missing}'
