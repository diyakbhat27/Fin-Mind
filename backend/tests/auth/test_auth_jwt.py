"""
Tests A1-A9, T1-T7, R1-R3: Authentication, JWT validation, and Refresh Token tests.
"""
import time
import pytest
from datetime import timedelta
from jose import jwt as jose_jwt
from app.core.config import settings
from app.auth.jwt import create_access_token, create_refresh_token, verify_refresh_token, decode_token
from app.auth.security import get_password_hash, verify_password


# =====================================================================
# 1.1 Login Tests (A1-A9)
# =====================================================================

class TestLogin:
    """POST /api/v1/auth/login"""

    def test_a1_valid_login(self, client, viewer_user):
        """A1: Valid credentials → 200 + access_token."""
        resp = client.post("/api/v1/auth/login", data={"username": "test_viewer", "password": "TestPass123"})
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"

    def test_a2_wrong_password(self, client, viewer_user):
        """A2: Correct username, wrong password → 400."""
        resp = client.post("/api/v1/auth/login", data={"username": "test_viewer", "password": "WrongPass"})
        assert resp.status_code == 400
        assert "Incorrect" in resp.json()["detail"]

    def test_a3_non_existent_user(self, client):
        """A3: Non-existent username → 400."""
        resp = client.post("/api/v1/auth/login", data={"username": "ghost", "password": "anything"})
        assert resp.status_code == 400

    def test_a4_inactive_user(self, client, inactive_user):
        """A4: Inactive user login → 400 'Inactive user'."""
        resp = client.post("/api/v1/auth/login", data={"username": "test_inactive", "password": "TestPass123"})
        assert resp.status_code == 400
        assert "Inactive" in resp.json()["detail"]

    def test_a5_empty_username(self, client):
        """A5: Empty username → 400 or 422."""
        resp = client.post("/api/v1/auth/login", data={"username": "", "password": "TestPass123"})
        assert resp.status_code in [400, 422]

    def test_a6_empty_password(self, client, viewer_user):
        """A6: Empty password → 400 or 422."""
        resp = client.post("/api/v1/auth/login", data={"username": "test_viewer", "password": ""})
        assert resp.status_code in [400, 422]

    def test_a7_sql_injection(self, client):
        """A7: SQL injection in username → 400 (no bypass)."""
        resp = client.post("/api/v1/auth/login", data={"username": "' OR 1=1 --", "password": "anything"})
        assert resp.status_code == 400

    def test_a9_token_contains_role(self, client, analyst_user):
        """A9: JWT payload includes role claim."""
        resp = client.post("/api/v1/auth/login", data={"username": "test_analyst", "password": "TestPass123"})
        assert resp.status_code == 200
        token = resp.json()["access_token"]
        payload = jose_jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        assert payload["role"] == "ANALYST"


# =====================================================================
# 1.2 Token Validation Tests (T1-T7)
# =====================================================================

class TestTokenValidation:
    """Token-based access to protected endpoints."""

    def test_t1_valid_token(self, client, viewer_headers):
        """T1: Valid token → request succeeds."""
        resp = client.get("/api/v1/admin/config", headers=viewer_headers)
        # VIEWER gets 403 (not enough privileges) but NOT 401
        assert resp.status_code == 403

    def test_t2_expired_token(self, client, viewer_user):
        """T2: Expired token → 401."""
        expired_token = create_access_token(
            data={"sub": viewer_user.id, "role": "VIEWER"},
            expires_delta=timedelta(seconds=-1)
        )
        resp = client.get("/api/v1/admin/config", headers={"Authorization": f"Bearer {expired_token}"})
        assert resp.status_code == 401

    def test_t3_tampered_token(self, client, viewer_user):
        """T3: Tampered token → 401."""
        token = create_access_token(data={"sub": viewer_user.id, "role": "VIEWER"})
        # Corrupt the signature by flipping a character
        tampered = token[:-5] + "XXXXX"
        resp = client.get("/api/v1/admin/config", headers={"Authorization": f"Bearer {tampered}"})
        assert resp.status_code == 401

    def test_t4_missing_token(self, client):
        """T4: No Authorization header → 401."""
        resp = client.get("/api/v1/admin/config")
        assert resp.status_code == 401

    def test_t5_malformed_token(self, client):
        """T5: Garbage token → 401."""
        resp = client.get("/api/v1/admin/config", headers={"Authorization": "Bearer abc123garbage"})
        assert resp.status_code == 401

    def test_t6_deleted_user_token(self, client, db, viewer_user):
        """T6: Delete user, reuse old token → 401."""
        headers = {"Authorization": f"Bearer {create_access_token(data={'sub': viewer_user.id, 'role': 'VIEWER'})}"}
        db.delete(viewer_user)
        db.commit()
        resp = client.get("/api/v1/admin/config", headers=headers)
        assert resp.status_code == 401

    def test_t7_deactivated_user_token(self, client, db, viewer_user):
        """T7: Deactivate user, reuse token → 400."""
        headers = {"Authorization": f"Bearer {create_access_token(data={'sub': viewer_user.id, 'role': 'VIEWER'})}"}
        viewer_user.is_active = False
        db.commit()
        resp = client.get("/api/v1/admin/config", headers=headers)
        assert resp.status_code == 400


# =====================================================================
# 1.3 Refresh Token Tests (R1-R3)
# =====================================================================

class TestRefreshToken:
    """Unit tests for refresh token logic."""

    def test_r1_valid_refresh_same_ip(self, viewer_user):
        """R1: Correct refresh token + matching IP → succeeds."""
        token = create_refresh_token(data={"sub": viewer_user.id}, client_ip="127.0.0.1")
        payload = verify_refresh_token(token, request_ip="127.0.0.1")
        assert payload["sub"] == viewer_user.id

    def test_r2_refresh_different_ip(self, viewer_user):
        """R2: Correct token, mismatched IP → ValueError."""
        token = create_refresh_token(data={"sub": viewer_user.id}, client_ip="127.0.0.1")
        with pytest.raises(ValueError, match="not bound to this IP"):
            verify_refresh_token(token, request_ip="192.168.1.100")

    def test_r3_access_token_as_refresh(self, viewer_user):
        """R3: Access token used as refresh → ValueError."""
        token = create_access_token(data={"sub": viewer_user.id, "role": "VIEWER"})
        with pytest.raises(ValueError, match="Not a refresh token"):
            verify_refresh_token(token, request_ip="127.0.0.1")


# =====================================================================
# Password Security Tests (PS1-PS4)
# =====================================================================

class TestPasswordSecurity:

    def test_ps1_password_stored_as_hash(self, viewer_user):
        """PS1: DB column contains hash, not plaintext."""
        assert viewer_user.hashed_password != "TestPass123"
        assert "$" in viewer_user.hashed_password  # PBKDF2 format

    def test_ps2_same_password_different_hash(self, db):
        """PS2: Same password → different hashes (salted)."""
        hash1 = get_password_hash("SamePassword123")
        hash2 = get_password_hash("SamePassword123")
        assert hash1 != hash2

    def test_ps3_verify_password_works(self):
        """Verify that password verification roundtrips correctly."""
        hashed = get_password_hash("MySecret")
        assert verify_password("MySecret", hashed) is True
        assert verify_password("WrongSecret", hashed) is False
