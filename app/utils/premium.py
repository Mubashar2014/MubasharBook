"""Premium (shareholders + investor profit-split) is not launch-ready yet.

Every premium surface is gated behind PREMIUM_ENABLED. Production config
never defines the key, so `premium_enabled()` is False by default and the
feature goes dark the moment code deploys — no config or DB change needed.
Tests turn it on in conftest; coming-soon tests flip it off per test.
"""
from flask import current_app


def premium_enabled():
    return bool(current_app.config.get('PREMIUM_ENABLED', False))
