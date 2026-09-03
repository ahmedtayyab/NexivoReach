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
    assert "prospects" in data
    assert isinstance(data["prospects"], list)
