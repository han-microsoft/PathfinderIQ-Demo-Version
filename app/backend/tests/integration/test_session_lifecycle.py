"""Session CRUD integration tests."""


def test_create_list_get_delete(client):
    """Full session CRUD lifecycle — create, verify in list, get, delete."""
    # Create
    res = client.post("/api/sessions", json={"title": "Test"})
    assert res.status_code == 201
    sid = res.json()["id"]

    # List — should appear
    res = client.get("/api/sessions")
    assert any(s["id"] == sid for s in res.json())

    # Get — full content
    res = client.get(f"/api/sessions/{sid}")
    assert res.json()["title"] == "Test"

    # Delete
    res = client.delete(f"/api/sessions/{sid}")
    assert res.status_code == 204

    # Gone
    res = client.get(f"/api/sessions/{sid}")
    assert res.status_code == 404


def test_get_nonexistent_returns_404(client):
    """GET unknown session returns 404."""
    assert client.get("/api/sessions/nonexistent").status_code == 404


def test_rename_session(client):
    """PATCH updates session title."""
    res = client.post("/api/sessions", json={"title": "Original"})
    sid = res.json()["id"]
    res = client.patch(f"/api/sessions/{sid}", json={"title": "Renamed"})
    assert res.json()["title"] == "Renamed"


def test_delete_nonexistent_returns_404(client):
    """DELETE unknown session returns 404."""
    assert client.delete("/api/sessions/nonexistent-id").status_code == 404


def test_create_default_title(client):
    """POST without title uses default."""
    res = client.post("/api/sessions", json={})
    assert res.status_code == 201
    assert res.json()["title"] == "New conversation"
