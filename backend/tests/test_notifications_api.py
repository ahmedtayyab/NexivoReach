"""Notification list + mark-read APIs (AUTH_DISABLED = local user)."""

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.main import app
from app.database.session import engine
from app.services import notifications as notif_mod


client = TestClient(app)


def test_notifications_list_and_mark_read():
    with Session(engine) as session:
        row = notif_mod.notify_user(
            session,
            "local",
            kind="info",
            title="Test notice",
            body="Hello from admin",
            href="#support",
        )
        assert row is not None
        nid = row.id

    listed = client.get("/api/notifications")
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["unreadCount"] >= 1
    ids = [n["id"] for n in body["notifications"]]
    assert nid in ids

    read = client.post(f"/api/notifications/{nid}/read")
    assert read.status_code == 200, read.text
    assert read.json()["notification"]["readAt"]

    all_read = client.post("/api/notifications/read-all")
    assert all_read.status_code == 200
    assert all_read.json()["unreadCount"] == 0


def test_admin_plan_patch_creates_notification():
    # Ensure a real user row exists to patch.
    from uuid import uuid4
    from datetime import datetime, timezone
    from app.models.schemas import User

    uid = f"u-test-{uuid4().hex[:8]}"
    with Session(engine) as session:
        session.add(
            User(
                id=uid,
                google_id=f"g-{uid}",
                email=f"{uid}@example.com",
                name="Pilot",
                created_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                plan="pilot",
            )
        )
        session.commit()

    patched = client.patch(f"/api/admin/users/{uid}", json={"plan": "pro"})
    assert patched.status_code == 200, patched.text
    assert patched.json()["plan"] == "pro"

    with Session(engine) as session:
        rows = notif_mod.list_for_user(session, uid, limit=10)
        titles = [r.title for r in rows]
        assert any("pro" in t.lower() for t in titles)
