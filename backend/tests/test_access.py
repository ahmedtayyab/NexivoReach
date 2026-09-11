"""Access control helpers for invite-only + daily caps."""

from app.models.schemas import User
from app.services import access as access_mod


def test_normalize_and_admin_email(monkeypatch):
    monkeypatch.setattr(access_mod.settings, "ADMIN_EMAILS", "Ops@Example.com, other@x.com")
    assert access_mod.normalize_email("  A@B.COM ") == "a@b.com"
    assert access_mod.is_admin_email("ops@example.com")
    assert not access_mod.is_admin_email("nope@example.com")


def test_limit_for_defaults_and_override(monkeypatch):
    monkeypatch.setattr(access_mod.settings, "DAILY_HUNT_LIMIT", 5)
    user = User(id="u1", google_id="g", email="a@b.com", daily_hunt_limit=12)
    assert access_mod._limit_for(user, "hunt") == 12
    user.daily_hunt_limit = None
    assert access_mod._limit_for(user, "hunt") == 5


def test_user_is_admin_flag_or_email(monkeypatch):
    monkeypatch.setattr(access_mod.settings, "ADMIN_EMAILS", "boss@x.com")
    flagged = User(id="u1", google_id="g", email="x@y.com", is_admin=True)
    via_email = User(id="u2", google_id="g2", email="boss@x.com", is_admin=False)
    none = User(id="u3", google_id="g3", email="c@d.com", is_admin=False)
    assert access_mod.user_is_admin(flagged)
    assert access_mod.user_is_admin(via_email)
    assert not access_mod.user_is_admin(none)
