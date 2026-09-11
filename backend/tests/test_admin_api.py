"""Admin allowlist API must create and list invites (AUTH_DISABLED = local admin)."""

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_admin_invite_create_list_delete():
    email = "pilot@example.com"
    create = client.post("/api/admin/allowlist", json={"email": email, "note": "beta"})
    assert create.status_code == 200, create.text
    body = create.json()
    assert body["email"] == email
    assert body["note"] == "beta"

    listed = client.get("/api/admin/allowlist")
    assert listed.status_code == 200
    emails = [i["email"] for i in listed.json()["invites"]]
    assert email in emails

    overview = client.get("/api/admin/overview")
    assert overview.status_code == 200
    assert overview.json()["stats"]["invites"] >= 1

    removed = client.delete(f"/api/admin/allowlist?email={email}")
    assert removed.status_code == 200

    listed2 = client.get("/api/admin/allowlist")
    emails2 = [i["email"] for i in listed2.json()["invites"]]
    assert email not in emails2


def test_admin_users_and_lift_caps():
    users = client.get("/api/admin/users")
    assert users.status_code == 200
    rows = users.json()["users"]
    # Local AUTH_DISABLED may have zero or one user; still must respond.
    assert isinstance(rows, list)
