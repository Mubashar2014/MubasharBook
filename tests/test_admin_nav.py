"""Admin IA: sidebar navigation, the Overview/Users split, and the activity log."""
import pathlib
import re
from datetime import datetime

import pytest

from app.extensions import db
from app.models.user import User
from app.models.shop import Shop
from app.models.subscription import Subscription
from app.models.payment import Payment
from app.models.admin_log import AdminLog


@pytest.fixture
def admin_client(app, test_user):
    test_user.is_admin = True
    db.session.commit()
    c = app.test_client()
    with c.session_transaction() as sess:
        sess['_user_id'] = str(test_user.id)
    return c


# Every destination the sidebar must expose, on every page.
DESTINATIONS = [
    '/admin/',
    '/admin/users',
    '/admin/pending-payments',
    '/admin/email-logs',
    '/admin/test-email',
    '/admin/activity',
]

PAGES = [
    '/admin/',
    '/admin/users',
    '/admin/pending-payments',
    '/admin/email-logs',
    '/admin/test-email',
    '/admin/activity',
]


def test_sidebar_exposes_every_destination_on_every_page(admin_client):
    for path in PAGES:
        html = admin_client.get(path).get_data(as_text=True)
        for dest in DESTINATIONS:
            assert f'href="{dest}"' in html, f'{dest} missing from sidebar on {path}'


def test_sidebar_marks_the_current_page_active(admin_client):
    expected = {
        '/admin/': '/admin/',
        '/admin/users': '/admin/users',
        '/admin/pending-payments': '/admin/pending-payments',
        '/admin/email-logs': '/admin/email-logs',
        '/admin/test-email': '/admin/test-email',
        '/admin/activity': '/admin/activity',
    }
    for path, href in expected.items():
        html = admin_client.get(path).get_data(as_text=True)
        found = None
        for chunk in html.split('<a class="side-link')[1:]:
            tag = chunk.split('>', 1)[0]
            if f'href="{href}"' in tag:
                found = 'active' in tag
                break
        assert found is True, f'{href} not active on {path}'


def test_user_detail_keeps_users_link_active(admin_client, app):
    from tests.test_admin_delete_user import make_victim
    victim, _ = make_victim('Nav Victim', '03009990010')

    html = admin_client.get(f'/admin/user/{victim.id}').get_data(as_text=True)
    active = any(
        'active' in chunk.split('>', 1)[0]
        for chunk in html.split('<a class="side-link')[1:]
        if 'href="/admin/users"' in chunk.split('>', 1)[0]
    )
    assert active, 'Users should stay highlighted on a user detail page'


def test_sidebar_shows_pending_payment_badge(admin_client, app):
    from tests.test_admin_delete_user import make_victim
    victim, shop = make_victim('Badge Person', '03009990017')
    sub = shop.subscription
    db.session.add(Payment(subscription_id=sub.id, user_id=victim.id,
                           amount=1500, payment_method='bank_transfer',
                           status='pending', description='Awaiting review'))
    db.session.commit()

    html = admin_client.get('/admin/users').get_data(as_text=True)
    assert 'href="/admin/pending-payments"' in html
    # the red count pill next to Payments
    assert 'background:#A13D2E' in html
    assert '>1</span>' in html


# ── OVERVIEW / USERS SPLIT ────────────────────────────────


def test_overview_has_stats_and_needs_attention(admin_client):
    html = admin_client.get('/admin/').get_data(as_text=True)
    assert 'Total Users' in html
    assert 'Total Revenue' in html
    assert 'Needs attention' in html
    assert 'Recent signups' in html
    assert 'Recent admin activity' in html


def test_overview_no_longer_contains_the_user_table(admin_client):
    html = admin_client.get('/admin/').get_data(as_text=True)
    assert 'Last Login' not in html          # column only exists on the Users page
    assert 'name="search"' not in html       # search moved to /admin/users
    assert '/admin/users' in html            # ...but is linked from here


def _stat(html, label):
    m = re.search(
        rf'{re.escape(label)}</h6>\s*<h2 class="mb-0">([\d,]+)</h2>', html
    )
    assert m, f'stat card {label!r} not rendered on Overview'
    return int(m.group(1).replace(',', ''))


def test_overview_status_counts_ignore_the_admins_own_shop(
    admin_client, test_user, second_user
):
    """The admin also has a trial shop; it must not inflate the breakdown."""
    from tests.test_admin_delete_user import make_victim
    make_victim('Active Victim', '03009990021')   # subscription status='active'

    def _set_status(user, status):
        sub = user.shop.subscription
        if sub is None:
            sub = Subscription(shop_id=user.shop.id, plan='basic', status=status)
            db.session.add(sub)
        else:
            sub.status = status
        db.session.commit()

    _set_status(test_user, 'trial')     # the admin's own shop
    _set_status(second_user, 'trial')   # a real customer

    html = admin_client.get('/admin/').get_data(as_text=True)

    assert _stat(html, 'Total Users') == 2
    assert _stat(html, 'Trial Users') == 1        # second_user only
    assert _stat(html, 'Active (Paid)') == 1
    assert _stat(html, 'Expired') == 0
    assert _stat(html, 'Suspended') == 0

    breakdown = sum(_stat(html, l) for l in
                    ('Trial Users', 'Active (Paid)', 'Expired', 'Suspended'))
    assert breakdown == _stat(html, 'Total Users')


def test_users_page_holds_the_searchable_list(admin_client):
    from tests.test_admin_delete_user import make_victim
    make_victim('Listed Person', '03009990015')

    html = admin_client.get('/admin/users').get_data(as_text=True)
    assert 'name="search"' in html
    assert 'Last Login' in html
    assert 'Listed Person' in html


def test_users_page_filters_by_search(admin_client):
    from tests.test_admin_delete_user import make_victim
    make_victim('Zebedee Searchable', '03009990011')
    make_victim('Unrelated Person', '03009990016')

    html = admin_client.get('/admin/users?search=Zebedee').get_data(as_text=True)
    assert 'Zebedee Searchable' in html
    assert 'Unrelated Person' not in html


def test_users_page_filters_by_status(admin_client):
    from tests.test_admin_delete_user import make_victim
    victim, _ = make_victim('Trial Person', '03009990014')
    victim.shop.subscription.status = 'trial'
    db.session.commit()

    html = admin_client.get('/admin/users?status=trial').get_data(as_text=True)
    assert 'Trial Person' in html

    html = admin_client.get('/admin/users?status=suspended').get_data(as_text=True)
    assert 'Trial Person' not in html


def test_user_detail_back_link_preserves_the_search(admin_client):
    from tests.test_admin_delete_user import make_victim
    victim, _ = make_victim('Backlink Person', '03009990012')

    html = admin_client.get(
        f'/admin/user/{victim.id}?search=Backlink&status=trial&page=2'
    ).get_data(as_text=True)
    assert 'search=Backlink' in html
    assert 'status=trial' in html
    assert 'page=2' in html
    assert 'Back to Users' in html


# ── ACTIVITY LOG ──────────────────────────────────────────


def test_activity_log_renders_and_lists_actions(admin_client, test_user):
    AdminLog.log_action(admin_user_id=test_user.id, action='trial_extended',
                        description='Extended trial by 7 days', target_type='user',
                        target_id=1, ip_address='127.0.0.1')
    db.session.commit()

    html = admin_client.get('/admin/activity').get_data(as_text=True)
    assert html and admin_client.get('/admin/activity').status_code == 200
    assert 'Extended trial by 7 days' in html
    assert 'Trial Extended' in html
    assert 'name="action"' in html


def test_activity_log_filters_by_action(admin_client, test_user):
    AdminLog.log_action(admin_user_id=test_user.id, action='trial_extended',
                        description='kept by filter', target_type='user', target_id=1)
    AdminLog.log_action(admin_user_id=test_user.id, action='payment_rejected',
                        description='hidden by filter', target_type='payment', target_id=2)
    db.session.commit()

    html = admin_client.get('/admin/activity?action=trial_extended').get_data(as_text=True)
    assert 'kept by filter' in html
    assert 'hidden by filter' not in html


def test_user_detail_danger_zone_offers_delete(admin_client):
    from tests.test_admin_delete_user import make_victim
    victim, _ = make_victim('Danger Zone Person', '03009990013')

    html = admin_client.get(f'/admin/user/{victim.id}').get_data(as_text=True)
    assert 'Danger Zone' in html
    assert f'/admin/user/{victim.id}/delete' in html
    assert 'deleteUserModal' in html
    assert victim.email in html           # the string the admin must type
    assert 'Cashbook entries' in html     # row counts are listed up front


# ── CSRF ──────────────────────────────────────────────────
#
# Tests run with WTF_CSRF_ENABLED=False, so a missing token would never show
# up as a failing test — only as a "Your session expired" flash in the browser.


def _post_forms_missing_csrf():
    root = pathlib.Path(__file__).resolve().parents[1] / 'app' / 'templates'
    missing = []
    for path in sorted(root.rglob('*.html')):
        html = path.read_text()
        for m in re.finditer(r'<form\b[^>]*>', html, re.I):
            if not re.search(r'method\s*=\s*["\']post["\']', m.group(0), re.I):
                continue
            start = m.end()
            nxt = re.search(r'<form\b', html[start:], re.I)
            body = html[start:start + nxt.start()] if nxt else html[start:]
            if 'csrf_token' not in body and 'hidden_tag()' not in body:
                line = html[:m.start()].count('\n') + 1
                missing.append(f'{path.name}:{line}')
    return missing


def test_every_post_form_includes_a_csrf_token():
    missing = _post_forms_missing_csrf()
    assert not missing, (
        'POST forms with no CSRF token flash "Your session expired" in the '
        'browser: ' + ', '.join(missing)
    )


def test_admin_action_succeeds_with_csrf_enabled(app, admin_client):
    from tests.test_admin_delete_user import make_victim
    victim, _ = make_victim('CSRF Person', '03009990018')

    app.config['WTF_CSRF_ENABLED'] = True
    try:
        html = admin_client.get(f'/admin/user/{victim.id}').get_data(as_text=True)
        token = None
        for chunk in html.split('<form')[1:]:
            if 'extend-trial' in chunk.split('</form>')[0]:
                m = re.search(r'name="csrf_token" value="([^"]+)"', chunk)
                token = m.group(1) if m else None
                break
        assert token, 'Extend Trial form must carry a CSRF token'

        resp = admin_client.post(
            f'/admin/user/{victim.id}/extend-trial',
            data={'days': '5', 'csrf_token': token},
        )
        assert resp.status_code in (301, 302)
        page = admin_client.get(resp.headers['Location']).get_data(as_text=True)
        assert 'Your session expired' not in page
        assert 'Trial extended by 5 days' in page
    finally:
        app.config['WTF_CSRF_ENABLED'] = False
