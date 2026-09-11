"""Support ticket customer + admin reply flow."""

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.main import app
from app.database.session import engine
from app.services import notifications as notif_mod


client = TestClient(app)


def test_support_ticket_create_admin_reply_notifies():
    created = client.post(
        "/api/support/tickets",
        json={
            "subject": "Need more hunts",
            "body": "Hitting the daily hunt cap on pilots.",
            "category": "limits",
            "priority": "high",
        },
    )
    assert created.status_code == 200, created.text
    ticket = created.json()
    assert ticket["subject"] == "Need more hunts"
    assert ticket["status"] == "open"
    tid = ticket["id"]

    mine = client.get("/api/support/tickets")
    assert mine.status_code == 200
    ids = [t["id"] for t in mine.json()["tickets"]]
    assert tid in ids

    admin_list = client.get("/api/admin/tickets")
    assert admin_list.status_code == 200, admin_list.text
    assert any(t["id"] == tid for t in admin_list.json()["tickets"])

    replied = client.patch(
        f"/api/admin/tickets/{tid}",
        json={"adminReply": "Raised your hunt limit to 20.", "status": "resolved"},
    )
    assert replied.status_code == 200, replied.text
    assert replied.json()["adminReply"].startswith("Raised")
    assert replied.json()["status"] == "resolved"

    detail = client.get(f"/api/support/tickets/{tid}")
    assert detail.status_code == 200
    assert "Raised your hunt limit" in detail.json()["adminReply"]

    with Session(engine) as session:
        rows = notif_mod.list_for_user(session, "local", limit=20)
        kinds = [r.kind for r in rows]
        assert "ticket" in kinds
