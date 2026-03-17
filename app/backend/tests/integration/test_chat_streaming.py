"""Chat SSE streaming integration tests (echo provider)."""


def test_chat_nonexistent_session_404(client):
    """POST to unknown session returns 404."""
    res = client.post("/api/chat/nonexistent", json={"content": "hi"})
    assert res.status_code == 404


def test_abort_no_active_generation_409(client):
    """Abort with no active generation returns 409."""
    res = client.post("/api/sessions")
    sid = res.json()["id"]
    res = client.post(f"/api/chat/{sid}/abort")
    assert res.status_code == 409


def test_empty_message_rejected_422(client):
    """Empty message body triggers Pydantic validation error."""
    res = client.post("/api/sessions")
    sid = res.json()["id"]
    res = client.post(f"/api/chat/{sid}", json={"content": ""})
    assert res.status_code == 422


def test_too_long_message_rejected_422(client):
    """Message exceeding max_length triggers Pydantic validation error."""
    res = client.post("/api/sessions")
    sid = res.json()["id"]
    res = client.post(f"/api/chat/{sid}", json={"content": "x" * 100_001})
    assert res.status_code == 422
