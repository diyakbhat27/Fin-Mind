"""
Tests C1-C9, AL1-AL9, SR1-SR5, SM1-SM5, U1-U12, Q1-Q4:
REST API endpoint access control per role.
"""
import uuid
import pytest
from unittest.mock import patch
from tests.conftest import get_auth_header, _create_user


# =====================================================================
# 3.1 Admin Config (GET/PUT /api/v1/admin/config)
# =====================================================================

class TestAdminConfig:

    def test_c1_get_config_as_viewer(self, client, viewer_headers):
        resp = client.get("/api/v1/admin/config", headers=viewer_headers)
        assert resp.status_code == 403

    def test_c2_get_config_as_analyst(self, client, analyst_headers):
        resp = client.get("/api/v1/admin/config", headers=analyst_headers)
        assert resp.status_code == 403

    def test_c3_get_config_as_admin(self, client, admin_headers):
        resp = client.get("/api/v1/admin/config", headers=admin_headers)
        assert resp.status_code == 200

    def test_c4_get_config_as_super_admin(self, client, super_admin_headers):
        resp = client.get("/api/v1/admin/config", headers=super_admin_headers)
        assert resp.status_code == 200

    def test_c5_put_config_as_admin(self, client, admin_headers):
        """ADMIN cannot update config (SUPER_ADMIN only)."""
        resp = client.put("/api/v1/admin/config", json={"key": "test_key", "value": "test_val"}, headers=admin_headers)
        assert resp.status_code == 403

    def test_c6_put_config_as_super_admin(self, client, super_admin_headers):
        resp = client.put("/api/v1/admin/config", json={"key": "rag_llm_model", "value": "gemini-3.8-flash"}, headers=super_admin_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"

    def test_c7_put_config_empty_key(self, client, super_admin_headers):
        """Empty key → should still work (or 422 depending on validation)."""
        resp = client.put("/api/v1/admin/config", json={"key": "", "value": "val"}, headers=super_admin_headers)
        # At minimum it should not crash (200 or 422)
        assert resp.status_code in [200, 422]


# =====================================================================
# 3.2 Audit Logs (GET /api/v1/admin/audit-logs)
# =====================================================================

class TestAuditLogs:

    def test_al1_viewer_blocked(self, client, viewer_headers):
        resp = client.get("/api/v1/admin/audit-logs", headers=viewer_headers)
        assert resp.status_code == 403

    def test_al2_analyst_blocked(self, client, analyst_headers):
        resp = client.get("/api/v1/admin/audit-logs", headers=analyst_headers)
        assert resp.status_code == 403

    def test_al3_admin_sees_filtered(self, client, admin_headers):
        resp = client.get("/api/v1/admin/audit-logs", headers=admin_headers)
        assert resp.status_code == 200

    def test_al4_super_admin_sees_all(self, client, super_admin_headers):
        resp = client.get("/api/v1/admin/audit-logs", headers=super_admin_headers)
        assert resp.status_code == 200

    def test_al5_pagination(self, client, admin_headers):
        resp = client.get("/api/v1/admin/audit-logs?skip=0&limit=5", headers=admin_headers)
        assert resp.status_code == 200
        assert len(resp.json()) <= 5

    def test_al6_pagination_past_end(self, client, admin_headers):
        resp = client.get("/api/v1/admin/audit-logs?skip=1000", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_al7_limit_zero(self, client, admin_headers):
        """limit=0 should fail validation (ge=1)."""
        resp = client.get("/api/v1/admin/audit-logs?limit=0", headers=admin_headers)
        assert resp.status_code == 422

    def test_al8_limit_too_large(self, client, admin_headers):
        """limit=200 should fail validation (le=100)."""
        resp = client.get("/api/v1/admin/audit-logs?limit=200", headers=admin_headers)
        assert resp.status_code == 422

    def test_al9_negative_skip(self, client, admin_headers):
        """skip=-1 should fail validation (ge=0)."""
        resp = client.get("/api/v1/admin/audit-logs?skip=-1", headers=admin_headers)
        assert resp.status_code == 422


# =====================================================================
# 3.3 Secrets Reload (POST /api/v1/admin/secrets/reload)
# =====================================================================

class TestSecretsReload:

    def test_sr1_viewer_blocked(self, client, viewer_headers):
        resp = client.post("/api/v1/admin/secrets/reload", headers=viewer_headers)
        assert resp.status_code == 403

    def test_sr2_analyst_blocked(self, client, analyst_headers):
        resp = client.post("/api/v1/admin/secrets/reload", headers=analyst_headers)
        assert resp.status_code == 403

    def test_sr3_admin_blocked(self, client, admin_headers):
        resp = client.post("/api/v1/admin/secrets/reload", headers=admin_headers)
        assert resp.status_code == 403

    def test_sr4_super_admin_allowed(self, client, super_admin_headers):
        """SUPER_ADMIN can reload secrets (may 200 or 404 if .env missing in test env)."""
        resp = client.post("/api/v1/admin/secrets/reload", headers=super_admin_headers)
        assert resp.status_code in [200, 404]


# =====================================================================
# 3.4 Secrets Management (GET/PUT /api/v1/secrets)
# =====================================================================

class TestSecretsManagement:

    def test_sm1_viewer_blocked(self, client, viewer_headers):
        resp = client.get("/api/v1/secrets/", headers=viewer_headers)
        assert resp.status_code == 403

    def test_sm2_admin_can_list(self, client, admin_headers):
        resp = client.get("/api/v1/secrets/", headers=admin_headers)
        assert resp.status_code == 200
        # Values should never be returned
        for secret in resp.json():
            assert "value" not in secret
            assert "key" in secret
            assert "is_set" in secret

    def test_sm3_admin_cannot_update(self, client, admin_headers):
        resp = client.put("/api/v1/secrets/", json={"key": "TEST_KEY", "value": "test"}, headers=admin_headers)
        assert resp.status_code == 403

    def test_sm4_super_admin_can_update(self, client, super_admin_headers):
        resp = client.put("/api/v1/secrets/", json={"key": "TEST_KEY", "value": "test_value"}, headers=super_admin_headers)
        assert resp.status_code == 200

    def test_sm5_no_value_leak(self, client, super_admin_headers):
        """After setting a secret, GET should show is_set=True but never the value."""
        client.put("/api/v1/secrets/", json={"key": "GROQ_API_KEY", "value": "super-secret"}, headers=super_admin_headers)
        resp = client.get("/api/v1/secrets/", headers=super_admin_headers)
        for s in resp.json():
            assert "value" not in s or s.get("value") is None


# =====================================================================
# 3.5 User Management (/api/v1/users)
# =====================================================================

class TestUserManagement:

    def test_u1_viewer_blocked(self, client, viewer_headers):
        resp = client.get("/api/v1/users/", headers=viewer_headers)
        assert resp.status_code == 403

    def test_u2_analyst_blocked(self, client, analyst_headers):
        resp = client.get("/api/v1/users/", headers=analyst_headers)
        assert resp.status_code == 403

    def test_u3_admin_can_list(self, client, admin_headers):
        resp = client.get("/api/v1/users/", headers=admin_headers)
        assert resp.status_code == 200

    def test_u4_create_viewer_as_admin(self, client, admin_headers):
        resp = client.post("/api/v1/users/", json={"username": "new_viewer", "password": "Pass123", "role": "VIEWER"}, headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["role"] == "VIEWER"

    def test_u5_create_admin_as_admin(self, client, admin_headers):
        """ADMIN cannot create ADMIN users → 403."""
        resp = client.post("/api/v1/users/", json={"username": "new_admin", "password": "Pass123", "role": "ADMIN"}, headers=admin_headers)
        assert resp.status_code == 403
        assert "ADMINs can only create" in resp.json()["detail"]

    def test_u6_create_super_admin_as_admin(self, client, admin_headers):
        """ADMIN cannot create SUPER_ADMIN → 403."""
        resp = client.post("/api/v1/users/", json={"username": "new_sa", "password": "Pass123", "role": "SUPER_ADMIN"}, headers=admin_headers)
        assert resp.status_code == 403

    def test_u7_create_admin_as_super_admin(self, client, super_admin_headers):
        """SUPER_ADMIN can create any role."""
        resp = client.post("/api/v1/users/", json={"username": "new_admin_ok", "password": "Pass123", "role": "ADMIN"}, headers=super_admin_headers)
        assert resp.status_code == 200
        assert resp.json()["role"] == "ADMIN"

    def test_u8_duplicate_username(self, client, admin_headers, viewer_user):
        """Duplicate username → 400."""
        resp = client.post("/api/v1/users/", json={"username": "test_viewer", "password": "Pass123", "role": "VIEWER"}, headers=admin_headers)
        assert resp.status_code == 400
        assert "already registered" in resp.json()["detail"]

    def test_u9_deactivate_viewer_as_admin(self, client, admin_headers, db):
        """ADMIN can deactivate VIEWER."""
        target = _create_user(db, "deactivate_me", "VIEWER")
        resp = client.put(f"/api/v1/users/{target.id}/deactivate", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

    def test_u10_deactivate_admin_as_admin(self, client, admin_headers, db):
        """ADMIN cannot deactivate ADMIN users → 403."""
        target = _create_user(db, "admin_target", "ADMIN")
        resp = client.put(f"/api/v1/users/{target.id}/deactivate", headers=admin_headers)
        assert resp.status_code == 403

    def test_u11_deactivate_admin_as_super_admin(self, client, super_admin_headers, db):
        """SUPER_ADMIN can deactivate anyone."""
        target = _create_user(db, "admin_target_sa", "ADMIN")
        resp = client.put(f"/api/v1/users/{target.id}/deactivate", headers=super_admin_headers)
        assert resp.status_code == 200

    def test_u12_deactivate_nonexistent(self, client, admin_headers):
        """Non-existent user → 404."""
        resp = client.put("/api/v1/users/99999/deactivate", headers=admin_headers)
        assert resp.status_code == 404


# =====================================================================
# 3.6 Direct Quantitative (POST /api/v1/quant/analyze) — RBAC (Q1-Q4)
# =====================================================================

class TestQuantitativeRBAC:

    def test_q1_viewer_blocked(self, client, viewer_headers):
        """Q1: VIEWER blocked from quant endpoint -> 403."""
        resp = client.post("/api/v1/quant/analyze", json={"query": "leverage ratio for AAPL 2023"}, headers=viewer_headers)
        assert resp.status_code == 403

    @patch("app.api.endpoints.quantitative.QuantitativeAgent")
    def test_q2_analyst_allowed(self, mock_agent_cls, client, analyst_headers):
        """Q2: ANALYST allowed."""
        mock_instance = mock_agent_cls.return_value
        mock_instance.analyze.return_value = {"metric": "leverage_ratio", "value": 1.5}
        resp = client.post("/api/v1/quant/analyze", json={"query": "leverage ratio for AAPL 2023"}, headers=analyst_headers)
        assert resp.status_code == 200

    @patch("app.api.endpoints.quantitative.QuantitativeAgent")
    def test_q3_admin_allowed(self, mock_agent_cls, client, admin_headers):
        """Q3: ADMIN allowed (fixed RBAC)."""
        mock_instance = mock_agent_cls.return_value
        mock_instance.analyze.return_value = {"metric": "leverage_ratio", "value": 1.5}
        resp = client.post("/api/v1/quant/analyze", json={"query": "leverage ratio for AAPL 2023"}, headers=admin_headers)
        assert resp.status_code == 200

    @patch("app.api.endpoints.quantitative.QuantitativeAgent")
    def test_q4_super_admin_allowed(self, mock_agent_cls, client, super_admin_headers):
        """Q4: SUPER_ADMIN allowed."""
        mock_instance = mock_agent_cls.return_value
        mock_instance.analyze.return_value = {"metric": "leverage_ratio", "value": 1.5}
        resp = client.post("/api/v1/quant/analyze", json={"query": "leverage ratio for AAPL 2023"}, headers=super_admin_headers)
        assert resp.status_code == 200
