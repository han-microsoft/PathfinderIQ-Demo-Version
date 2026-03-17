"""Feedback endpoint — integration tests.

Tests the POST /api/feedback endpoint for bug report submission.
Covers:
    - Successful submission returns 201 with report ID
    - Missing title returns 422
    - Missing description returns 422
    - Empty title returns 422
    - Title too long returns 422
    - Structured log emitted on submission (no Cosmos in tests)
"""

import logging

import pytest

from tests.integration.conftest import parse_sse_body


class TestFeedbackSubmission:
    """POST /api/feedback — submit a bug report."""

    def test_submit_returns_201(self, client):
        """Valid submission returns 201 with a report ID."""
        res = client.post("/api/feedback", json={
            "title": "Graph not loading",
            "description": "The graph panel shows 'Failed to fetch' on startup.",
        })
        assert res.status_code == 201
        body = res.json()
        assert "id" in body
        assert len(body["id"]) == 12  # uuid4().hex[:12]
        assert body["status"] == "submitted"

    def test_submit_missing_title_returns_422(self, client):
        """Missing title field returns 422."""
        res = client.post("/api/feedback", json={
            "description": "Something is broken.",
        })
        assert res.status_code == 422

    def test_submit_missing_description_returns_422(self, client):
        """Missing description field returns 422."""
        res = client.post("/api/feedback", json={
            "title": "Bug",
        })
        assert res.status_code == 422

    def test_submit_empty_title_returns_422(self, client):
        """Empty title returns 422."""
        res = client.post("/api/feedback", json={
            "title": "",
            "description": "Something is broken.",
        })
        assert res.status_code == 422

    def test_submit_title_too_long_returns_422(self, client):
        """Title exceeding 200 chars returns 422."""
        res = client.post("/api/feedback", json={
            "title": "A" * 201,
            "description": "Something is broken.",
        })
        assert res.status_code == 422

    def test_submit_logs_to_log_without_cosmos(self, client, caplog):
        """Without Cosmos, feedback is logged (not lost)."""
        with caplog.at_level(logging.INFO, logger="app.routers.feedback"):
            res = client.post("/api/feedback", json={
                "title": "Test bug",
                "description": "Test description for logging.",
            })
        assert res.status_code == 201

        # Verify the fallback log was emitted
        log_records = [
            r for r in caplog.records
            if r.message == "feedback.submitted_to_log"
        ]
        assert len(log_records) == 1
        assert log_records[0].title == "Test bug"

    def test_submit_returns_unique_ids(self, client):
        """Two submissions return different IDs."""
        r1 = client.post("/api/feedback", json={
            "title": "Bug 1", "description": "First",
        })
        r2 = client.post("/api/feedback", json={
            "title": "Bug 2", "description": "Second",
        })
        assert r1.json()["id"] != r2.json()["id"]
