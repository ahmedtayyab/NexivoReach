import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.mark.order(90)
def test_discovery_persists():
    client = TestClient(app)
    resp = client.post("/api/discovery/run", json={
        "user_prompt": "Find commercial gyms in UAE needing power racks.",
        "products": [],
        "icp": {}
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "prospect" in data and "agent_log" in data

    list_resp = client.get("/api/prospects/")
    assert list_resp.status_code == 200
    prospects = list_resp.json()
    assert isinstance(prospects, list)
    assert len(prospects) >= 1
