"""Landing page demo video: hero button opens a modal playing static/videos/2mints.mp4."""


def test_landing_hero_offers_demo_video(client, app):
    with app.app_context():
        resp = client.get('/')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'Watch 2-min demo' in html
    assert 'Watch 90-sec demo' not in html
    assert 'demo-modal' in html
    assert 'demo-video' in html
    assert '/static/videos/2mints.mp4' in html


def test_demo_video_file_served(client, app):
    with app.app_context():
        resp = client.get('/static/videos/2mints.mp4')
    assert resp.status_code == 200
    # real video, not a stub (file is ~29 MB)
    assert resp.content_length and resp.content_length > 1_000_000
