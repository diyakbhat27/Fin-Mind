"""
Tests for Rate Limiting (RL1-RL4):
- RL1: POST /auth/login limit 5/min (6th call -> 429)
- RL2: POST /chat limit 20/min (21st call -> 429)
- RL3: Rate limit reset mechanism
- RL4: Separate limits per client IP
"""
import pytest
from unittest.mock import patch
from app.core.rate_limit import limiter, auth_backoff_tracker
from tests.conftest import get_auth_header, _create_user


@pytest.fixture
def enable_limiter():
    """Temporarily enable the rate limiter and reset its internal storage."""
    limiter.enabled = True
    auth_backoff_tracker.reset()
    if hasattr(limiter, "_storage") and hasattr(limiter._storage, "reset"):
        limiter._storage.reset()
    yield limiter
    auth_backoff_tracker.reset()
    limiter.enabled = False


class TestRateLimiting:

    def test_rl1_login_rate_limit_5_per_min(self, client, enable_limiter, viewer_user):
        """RL1: 5 login requests allowed within 1 minute; 6th returns 429."""
        ip = "192.168.10.1"
        headers = {"X-Forwarded-For": ip}
        
        # 5 attempts
        for _ in range(5):
            resp = client.post("/api/v1/auth/login", data={"username": "test_viewer", "password": "WrongPassword"}, headers=headers)
            assert resp.status_code == 400

        # 6th attempt should be blocked with 429
        resp6 = client.post("/api/v1/auth/login", data={"username": "test_viewer", "password": "WrongPassword"}, headers=headers)
        assert resp6.status_code == 429
        assert "Rate limit exceeded" in resp6.text

    @patch("app.api.endpoints.chat.supervisor_graph.invoke")
    def test_rl2_chat_rate_limit_20_per_min(self, mock_invoke, client, enable_limiter, viewer_headers):
        """RL2: 20 chat requests allowed within 1 minute; 21st returns 429."""
        mock_invoke.return_value = {"final_response": {"answer": "pong"}}
        ip = "192.168.10.2"
        headers = {**viewer_headers, "X-Forwarded-For": ip}

        for _ in range(20):
            resp = client.post("/api/v1/chat", json={"query": "ping"}, headers=headers)
            assert resp.status_code == 200

        # 21st attempt should be blocked with 429
        resp21 = client.post("/api/v1/chat", json={"query": "ping"}, headers=headers)
        assert resp21.status_code == 429

    def test_rl4_different_ips_have_separate_limits(self, enable_limiter, viewer_user):
        """RL4: IP-A hitting rate limit does not exhaust rate limit for IP-B."""
        from fastapi.testclient import TestClient
        from app.main import app

        client_a = TestClient(app, client=("10.0.0.1", 50000))
        client_b = TestClient(app, client=("10.0.0.2", 50000))

        # Exhaust limit for IP-A (5 requests)
        for _ in range(5):
            client_a.post("/api/v1/auth/login", data={"username": "test_viewer", "password": "WrongPassword"})

        # 6th request from IP-A is 429
        resp_a = client_a.post("/api/v1/auth/login", data={"username": "test_viewer", "password": "WrongPassword"})
        assert resp_a.status_code == 429

        # Request from IP-B should still be processed (returns 400 bad password, NOT 429)
        resp_b = client_b.post("/api/v1/auth/login", data={"username": "test_viewer", "password": "WrongPassword"})
        assert resp_b.status_code == 400

    def test_auth_exponential_backoff_with_retry_after(self, client, enable_limiter, viewer_user):
        """Consecutive auth failures past threshold trigger exponential backoff with Retry-After header."""
        # Record 6 failed attempts for a specific IP and user
        for i in range(6):
            client.post(
                "/api/v1/auth/login",
                data={"username": "test_viewer", "password": "BadPassword"},
                headers={"X-Forwarded-For": f"172.16.0.{i+1}"}
            )

        # Next attempt is caught by account backoff tracker
        resp = client.post(
            "/api/v1/auth/login",
            data={"username": "test_viewer", "password": "TestPass123"},
            headers={"X-Forwarded-For": "172.16.0.99"}
        )
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers
        assert int(resp.headers["Retry-After"]) >= 1
        assert "Too many failed login attempts" in resp.json()["detail"]

    def test_auth_per_account_backoff_cross_ip(self, client, enable_limiter, viewer_user):
        """Attacker rotating IPs targeting same account gets stopped by per-account backoff."""
        # 6 distinct IPs making 1 attempt each targeting test_viewer
        for i in range(6):
            resp = client.post(
                "/api/v1/auth/login",
                data={"username": "test_viewer", "password": "WrongPassword"},
                headers={"X-Forwarded-For": f"203.0.113.{i+1}"}
            )
            # Individual IPs are below IP slowapi limit (5/min), but account accumulates failures
            if i < 5:
                assert resp.status_code == 400

        # Attempt from a brand-new IP 203.0.113.200 is throttled due to per-account defense
        resp_fresh = client.post(
            "/api/v1/auth/login",
            data={"username": "test_viewer", "password": "WrongPassword"},
            headers={"X-Forwarded-For": "203.0.113.200"}
        )
        assert resp_fresh.status_code == 429
        assert "Retry-After" in resp_fresh.headers


class TestStrictInputValidation:
    """Validate every input against strict schemas (type, length, format) and reject invalid input with 422/400."""

    def test_chat_input_validation(self, client, viewer_headers):
        # Empty string
        resp1 = client.post("/api/v1/chat", json={"query": ""}, headers=viewer_headers)
        assert resp1.status_code == 422

        # Whitespace-only string
        resp2 = client.post("/api/v1/chat", json={"query": "     "}, headers=viewer_headers)
        assert resp2.status_code == 422

        # Null byte injection
        resp3 = client.post("/api/v1/chat", json={"query": "tell me about\x00 AAPL"}, headers=viewer_headers)
        assert resp3.status_code == 422

        # Exceed max length
        resp4 = client.post("/api/v1/chat", json={"query": "A" * 1001}, headers=viewer_headers)
        assert resp4.status_code == 422

    def test_quant_input_validation(self, client, analyst_headers):
        # Too short (< 3 chars)
        resp1 = client.post("/api/v1/quant/analyze", json={"query": "hi"}, headers=analyst_headers)
        assert resp1.status_code == 422

        # Null byte injection
        resp2 = client.post("/api/v1/quant/analyze", json={"query": "net income\x00 AAPL"}, headers=analyst_headers)
        assert resp2.status_code == 422

        # Whitespace only
        resp3 = client.post("/api/v1/quant/analyze", json={"query": "    "}, headers=analyst_headers)
        assert resp3.status_code == 422

    def test_rag_input_validation(self, client, viewer_headers):
        # Query too short
        resp1 = client.post("/api/v1/rag/query", json={"query": "ab"}, headers=viewer_headers)
        assert resp1.status_code == 422

        # Invalid company format (control characters / HTML injection)
        resp2 = client.post("/api/v1/rag/query", json={"query": "valid query", "company": "<script>alert(1)</script>"}, headers=viewer_headers)
        assert resp2.status_code == 422

        # Out-of-bounds fiscal year
        resp3 = client.post("/api/v1/rag/query", json={"query": "valid query", "year": 1850}, headers=viewer_headers)
        assert resp3.status_code == 422

    def test_user_creation_validation(self, client, super_admin_headers):
        # Invalid username characters
        resp1 = client.post("/api/v1/users/", json={"username": "bad!user#name", "password": "ValidPass123", "role": "VIEWER"}, headers=super_admin_headers)
        assert resp1.status_code == 422

        # Invalid password length (< 6 chars)
        resp2 = client.post("/api/v1/users/", json={"username": "valid_user", "password": "123", "role": "VIEWER"}, headers=super_admin_headers)
        assert resp2.status_code == 422

        # Invalid RBAC role
        resp3 = client.post("/api/v1/users/", json={"username": "valid_user", "password": "ValidPass123", "role": "HACKER"}, headers=super_admin_headers)
        assert resp3.status_code == 422

    def test_config_update_validation(self, client, super_admin_headers):
        # Null byte in key
        resp1 = client.put("/api/v1/admin/config", json={"key": "test\x00key", "value": "val"}, headers=super_admin_headers)
        assert resp1.status_code == 422

        # Invalid characters in key
        resp2 = client.put("/api/v1/admin/config", json={"key": "test key with spaces!", "value": "val"}, headers=super_admin_headers)
        assert resp2.status_code == 422

    def test_secrets_update_validation(self, client, super_admin_headers):
        # Null byte in secret key
        resp1 = client.put("/api/v1/secrets/", json={"key": "KEY\x00", "value": "val"}, headers=super_admin_headers)
        assert resp1.status_code == 422

        # Invalid character in secret key (e.g. lowercase or symbols)
        resp2 = client.put("/api/v1/secrets/", json={"key": "bad-key$name", "value": "val"}, headers=super_admin_headers)
        assert resp2.status_code == 422

