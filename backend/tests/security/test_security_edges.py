"""
Tests for Security, Penetration, and Edge Cases (Section 5):
- 5.1 Password Security (PS1-PS4)
- 5.2 AES-256-GCM Crypto (CR1-CR6)
- 5.3 Audit Log Integrity & Hash Chain (HC1-HC5)
- 5.4 Input Validation & Injection (IV1-IV5)
- 5.5 CORS & Headers (CO1-CO5)
- 5.6 Error Handling (EH1-EH4)
"""
import base64
import json
import hashlib
import os
import pytest
from unittest.mock import patch, MagicMock
from jose import jwt as jose_jwt
from app.core.config import settings
from app.auth.security import get_password_hash, verify_password
from app.auth.jwt import create_access_token, decode_token
from app.security.crypto import AESGCMCipher, CryptoError
from app.core.audit import AuditLogger
from app.models.rbac import User
from tests.conftest import _create_user, get_auth_header


# =====================================================================
# 5.1 Password Security (PS1-PS4)
# =====================================================================

class TestPasswordSecurityEdges:

    def test_ps1_password_stored_as_hash(self, db):
        """PS1: Passwords in database are stored hashed with pbkdf2_sha256."""
        user = _create_user(db, "ps1_user", "VIEWER", password="MySecretPassword123")
        assert user.hashed_password != "MySecretPassword123"
        assert "pbkdf2" in user.hashed_password

    def test_ps2_same_password_different_hash(self, db):
        """PS2: Two users with identical passwords have distinct salted hashes."""
        u1 = _create_user(db, "ps2_u1", "VIEWER", password="IdenticalPassword123")
        u2 = _create_user(db, "ps2_u2", "VIEWER", password="IdenticalPassword123")
        assert u1.hashed_password != u2.hashed_password

    def test_ps3_password_not_in_api_response(self, client, admin_headers, db):
        """PS3: GET /users/ never returns password or hashed_password."""
        _create_user(db, "ps3_user", "VIEWER")
        resp = client.get("/api/v1/users/", headers=admin_headers)
        assert resp.status_code == 200
        users = resp.json()
        for u in users:
            assert "password" not in u
            assert "hashed_password" not in u

    def test_ps4_password_not_in_jwt(self, viewer_user):
        """PS4: Decoded JWT token payload never includes password."""
        token = create_access_token(data={"sub": viewer_user.id, "role": viewer_user.role})
        payload = decode_token(token)
        assert "password" not in payload
        assert "hashed_password" not in payload


# =====================================================================
# 5.2 AES-256-GCM Crypto Tests (CR1-CR6)
# =====================================================================

class TestCryptoEdges:

    def test_cr1_roundtrip(self):
        """CR1: Plaintext matches decrypted text after roundtrip."""
        cipher = AESGCMCipher()
        plaintext = "sensitive_financial_document_text"
        enc = cipher.encrypt(plaintext)
        dec = cipher.decrypt(enc["nonce"], enc["ciphertext"], enc["tag"])
        assert dec == plaintext

    def test_cr2_tampered_ciphertext(self):
        """CR2: Tampering 1 byte in ciphertext raises CryptoError tag validation failed."""
        cipher = AESGCMCipher()
        enc = cipher.encrypt("secret_payload")
        raw = base64.b64decode(enc["ciphertext"])
        tampered_raw = bytes([raw[0] ^ 0xFF]) + raw[1:]
        tampered_b64 = base64.b64encode(tampered_raw).decode("utf-8")

        with pytest.raises(CryptoError) as exc:
            cipher.decrypt(enc["nonce"], tampered_b64, enc["tag"])
        assert "Authentication tag validation failed" in str(exc.value)

    def test_cr3_wrong_key_decryption(self):
        """CR3: Decrypting with wrong key raises CryptoError."""
        cipher1 = AESGCMCipher()
        diff_key = base64.b64encode(os.urandom(32)).decode("utf-8")
        cipher2 = AESGCMCipher(base64_key=diff_key)
        enc = cipher1.encrypt("secret_payload")

        with pytest.raises(CryptoError):
            cipher2.decrypt(enc["nonce"], enc["ciphertext"], enc["tag"])

    def test_cr4_invalid_base64_key(self):
        """CR4: Invalid base64 string raises CryptoError."""
        with pytest.raises(CryptoError) as exc:
            AESGCMCipher(base64_key="not-valid-base64!@#$")
        assert "not valid base64" in str(exc.value)

    def test_cr5_wrong_key_length(self):
        """CR5: 16-byte key (AES-128) raises CryptoError: requires 32-byte key."""
        short_key = base64.b64encode(b"0123456789abcdef").decode("utf-8")
        with pytest.raises(CryptoError) as exc:
            AESGCMCipher(base64_key=short_key)
        assert "32-byte key" in str(exc.value)

    def test_cr6_unique_nonces(self):
        """CR6: Encrypting the same plaintext twice produces unique nonces."""
        cipher = AESGCMCipher()
        enc1 = cipher.encrypt("same_text")
        enc2 = cipher.encrypt("same_text")
        assert enc1["nonce"] != enc2["nonce"]
        assert enc1["ciphertext"] != enc2["ciphertext"]


# =====================================================================
# 5.3 Audit Log Hash Chain & Redaction Tests (HC1-HC5)
# =====================================================================

class TestAuditLogIntegrity:

    def test_hc1_first_log_zero_prev_hash(self, db):
        """HC1: First log entry has prev_hash = '0' * 64."""
        log = AuditLogger.log_event(db, event_type="HC1_EVENT", status_code=200, payload={"key": "val"})
        assert log.prev_hash == "0" * 64

    def test_hc2_chain_integrity(self, db):
        """HC2: Each log's prev_hash matches the preceding log's entry_hash."""
        log1 = AuditLogger.log_event(db, event_type="E1", status_code=200, payload={"a": 1})
        log2 = AuditLogger.log_event(db, event_type="E2", status_code=200, payload={"b": 2})
        log3 = AuditLogger.log_event(db, event_type="E3", status_code=200, payload={"c": 3})
        assert log2.prev_hash == log1.entry_hash
        assert log3.prev_hash == log2.entry_hash

    def test_hc3_tampering_detection(self, db):
        """HC3: Modifying payload invalidates recalculated hash."""
        log = AuditLogger.log_event(db, event_type="E_ORIG", status_code=200, payload={"amount": 100})
        original_hash = log.entry_hash
        
        # Tamper payload
        log.payload_sanitized = json.dumps({"amount": 1000000}, sort_keys=True)
        recalculated = hashlib.sha256((log.prev_hash + log.payload_sanitized).encode("utf-8")).hexdigest()
        assert recalculated != original_hash

    def test_hc4_sensitive_password_redaction(self, db):
        """HC4: Password field is redacted to [REDACTED]."""
        log = AuditLogger.log_event(db, event_type="AUTH", status_code=200, payload={"username": "alice", "password": "Secret123"})
        parsed = json.loads(log.payload_sanitized)
        assert parsed["password"] == "[REDACTED]"

    def test_hc5_all_sensitive_keys_redacted(self, db):
        """HC5: token, access_token, refresh_token, secret, key are redacted."""
        payload = {
            "token": "tok123",
            "access_token": "acc123",
            "refresh_token": "ref123",
            "secret": "sec123",
            "key": "key123",
            "public_data": "safe"
        }
        log = AuditLogger.log_event(db, event_type="SECURITY_TEST", status_code=200, payload=payload)
        parsed = json.loads(log.payload_sanitized)
        assert parsed["token"] == "[REDACTED]"
        assert parsed["access_token"] == "[REDACTED]"
        assert parsed["refresh_token"] == "[REDACTED]"
        assert parsed["secret"] == "[REDACTED]"
        assert parsed["key"] == "[REDACTED]"
        assert parsed["public_data"] == "safe"


# =====================================================================
# 5.4 Input Validation & Injection Tests (IV1-IV5)
# =====================================================================

class TestInputValidation:

    @patch("app.api.endpoints.chat.supervisor_graph.invoke")
    def test_iv1_sql_injection_in_chat(self, mock_invoke, client, viewer_headers):
        """IV1: SQL injection attempt in chat handled safely without DB syntax error."""
        mock_invoke.return_value = {"final_response": {"answer": "Safe response"}}
        sqli_query = "'; DROP TABLE users; --"
        resp = client.post("/api/v1/chat", json={"query": sqli_query}, headers=viewer_headers)
        assert resp.status_code in [200, 400, 422]

    @patch("app.api.endpoints.chat.supervisor_graph.invoke")
    def test_iv2_nosql_injection(self, mock_invoke, client, viewer_headers):
        """IV2: NoSQL dictionary injection payload handled safely."""
        mock_invoke.return_value = {"final_response": {"answer": "Safe response"}}
        resp = client.post("/api/v1/chat", json={"query": "{'$gt': ''}"}, headers=viewer_headers)
        assert resp.status_code in [200, 400, 422]

    def test_iv3_path_traversal(self, client, super_admin_headers):
        """IV3: Path traversal attempt in secrets/config handled safely."""
        resp = client.put("/api/v1/secrets", json={"key": "../../etc/passwd", "value": "hacked"}, headers=super_admin_headers)
        assert resp.status_code in [200, 400, 422]

    @patch("app.api.endpoints.chat.supervisor_graph.invoke")
    def test_iv4_unicode_overflow(self, mock_invoke, client, viewer_headers):
        """IV4: Unicode emoji overflow safely handled."""
        mock_invoke.return_value = {"final_response": {"answer": "Safe response"}}
        emoji_query = "🔥" * 500
        resp = client.post("/api/v1/chat", json={"query": emoji_query}, headers=viewer_headers)
        assert resp.status_code in [200, 400, 422]

    @patch("app.api.endpoints.chat.supervisor_graph.invoke")
    def test_iv5_null_byte_injection(self, mock_invoke, client, viewer_headers):
        """IV5: Null byte injection handled safely."""
        mock_invoke.return_value = {"final_response": {"answer": "Safe response"}}
        null_query = "test\x00malicious"
        resp = client.post("/api/v1/chat", json={"query": null_query}, headers=viewer_headers)
        assert resp.status_code in [200, 400, 422]


# =====================================================================
# 5.5 CORS & Response Headers (CO1-CO5)
# =====================================================================

class TestCORSAndHeaders:

    def test_co1_localhost_cors_allowed(self, client):
        """CO1: Requests from localhost:5173 include CORS allow origin."""
        resp = client.options("/api/v1/auth/login", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"})
        # CORS middleware returns 200 with Access-Control-Allow-Origin
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"

    def test_co2_evil_origin_blocked(self, client):
        """CO2: Origin from unauthorized domain has no Access-Control-Allow-Origin."""
        resp = client.options("/api/v1/auth/login", headers={"Origin": "http://evil-site.com", "Access-Control-Request-Method": "POST"})
        assert resp.headers.get("access-control-allow-origin") != "http://evil-site.com"

    def test_co3_x_request_id_in_response(self, client):
        """CO3: Every response has X-Request-ID header."""
        resp = client.get("/health")
        assert "x-request-id" in resp.headers

    def test_co4_x_process_time_in_response(self, client):
        """CO4: Every response has X-Process-Time header."""
        resp = client.get("/health")
        assert "x-process-time" in resp.headers

    def test_co5_custom_x_request_id_echoed(self, client):
        """CO5: Custom X-Request-ID passed in request is echoed back."""
        custom_id = "test-custom-request-id-999"
        resp = client.get("/health", headers={"X-Request-ID": custom_id})
        assert resp.headers.get("x-request-id") == custom_id


# =====================================================================
# 5.6 Error Handling (EH1-EH4)
# =====================================================================

class TestErrorHandling:

    def test_eh1_unhandled_exception_returns_500(self, admin_headers):
        """EH1: Unhandled exception returns 500 status."""
        from fastapi.testclient import TestClient
        from app.database.session import get_db
        from app.main import app

        def broken_db():
            raise RuntimeError("Simulated fatal internal error")

        original_override = app.dependency_overrides.get(get_db)
        app.dependency_overrides[get_db] = broken_db
        client_500 = TestClient(app, raise_server_exceptions=False)
        try:
            resp = client_500.get("/api/v1/admin/config", headers=admin_headers)
            assert resp.status_code == 500
        finally:
            if original_override is not None:
                app.dependency_overrides[get_db] = original_override
            else:
                app.dependency_overrides.pop(get_db, None)

    def test_eh2_no_stack_trace_leaked(self, admin_headers):
        """EH2: 500 error response does not leak file paths or stack trace in body."""
        from fastapi.testclient import TestClient
        from app.database.session import get_db
        from app.main import app

        def broken_db():
            raise RuntimeError("Simulated internal error in C:\\Internal\\Secret\\Path")

        original_override = app.dependency_overrides.get(get_db)
        app.dependency_overrides[get_db] = broken_db
        client_500 = TestClient(app, raise_server_exceptions=False)
        try:
            resp = client_500.get("/api/v1/admin/config", headers=admin_headers)
            assert resp.status_code == 500
            body = resp.text
            assert "Traceback" not in body
            assert "C:\\Internal\\Secret\\Path" not in body
        finally:
            if original_override is not None:
                app.dependency_overrides[get_db] = original_override
            else:
                app.dependency_overrides.pop(get_db, None)

    def test_eh3_invalid_json_body_returns_422(self, client, viewer_headers):
        """EH3: Invalid JSON body returns 422 Unprocessable Content."""
        resp = client.post(
            "/api/v1/chat",
            content="{bad_json: invalid}",
            headers={**viewer_headers, "Content-Type": "application/json"}
        )
        assert resp.status_code == 422

    def test_eh4_wrong_http_method_returns_405(self, client):
        """EH4: Sending GET to POST endpoint returns 405 Method Not Allowed."""
        resp = client.get("/api/v1/auth/login")
        assert resp.status_code == 405

    def test_eh5_rag_endpoint_exception_sanitized(self, client, analyst_headers):
        """EH5: RAG endpoint exception masks internal paths and raw exceptions."""
        with patch("app.api.endpoints.rag.get_rag_chain") as mock_chain:
            mock_chain.side_effect = RuntimeError("FATAL: ChromaDB sqlite error at C:\\Users\\Internal\\chroma.sqlite3")
            resp = client.post(
                "/api/v1/rag/query",
                json={"query": "What are Apple's capital lease obligations?"},
                headers=analyst_headers
            )
            assert resp.status_code == 500
            data = resp.json()
            assert data["detail"] == "An error occurred while querying the financial knowledge base."
            assert "chroma" not in resp.text.lower()
            assert "C:\\Users" not in resp.text
            assert "Traceback" not in resp.text

    def test_eh6_quant_endpoint_exception_sanitized(self, client, analyst_headers):
        """EH6: Quantitative endpoint masks raw database/AST internal errors."""
        with patch("app.api.endpoints.quantitative.QuantitativeAgent.analyze") as mock_analyze:
            mock_analyze.side_effect = RuntimeError("SQLAlchemy syntax error: SELECT secret_column FROM users_table")
            resp = client.post(
                "/api/v1/quant/analyze",
                json={"query": "Calculate operating margin for AAPL in 2023"},
                headers=analyst_headers
            )
            assert resp.status_code == 500
            data = resp.json()
            assert data["detail"] == "An error occurred while executing the quantitative analysis."
            assert "secret_column" not in resp.text
            assert "users_table" not in resp.text
            assert "SQLAlchemy" not in resp.text

    def test_eh7_chat_endpoint_exception_sanitized(self, client, viewer_headers):
        """EH7: Chat endpoint masks graph failures and never leaks python traceback."""
        with patch("app.api.endpoints.chat.supervisor_graph.invoke") as mock_invoke:
            mock_invoke.side_effect = RuntimeError("StateGraph execution failed in C:\\App\\services\\supervisor.py line 88")
            resp = client.post(
                "/api/v1/chat",
                json={"query": "What is the net revenue of AAPL?"},
                headers=viewer_headers
            )
            assert resp.status_code == 500
            data = resp.json()
            assert data["detail"] == "An error occurred while processing your chat request."
            assert "supervisor.py" not in resp.text
            assert "StateGraph" not in resp.text
            assert "Traceback" not in resp.text

    def test_eh8_db_error_masked_and_rollback(self, client, admin_headers):
        """EH8: Database transaction failure rolls back cleanly and returns generic error."""
        with patch("sqlalchemy.orm.Session.commit") as mock_commit:
            mock_commit.side_effect = RuntimeError("OperationalError: database disk image is malformed")
            resp = client.post(
                "/api/v1/users/",
                json={"username": "new_eh8_user", "password": "Password123!", "role": "VIEWER"},
                headers=admin_headers
            )
            assert resp.status_code == 500
            data = resp.json()
            assert data["detail"] == "A database error occurred while creating user account."
            assert "OperationalError" not in resp.text
            assert "malformed" not in resp.text

    def test_eh9_server_side_logger_captures_exc_info(self, admin_headers):
        """EH9: Server-side logger captures full exc_info=True with request correlation ID."""
        from fastapi.testclient import TestClient
        from app.database.session import get_db
        from app.main import app

        def broken_db():
            raise RuntimeError("Secret internal failure detail for debugging")

        original_override = app.dependency_overrides.get(get_db)
        app.dependency_overrides[get_db] = broken_db
        client_500 = TestClient(app, raise_server_exceptions=False)
        try:
            with patch("app.main.logger.error") as mock_logger_error:
                resp = client_500.get(
                    "/api/v1/admin/config",
                    headers={**admin_headers, "X-Request-ID": "test-req-12345"}
                )
                assert resp.status_code == 500
                assert resp.json()["detail"] == "Internal Server Error"
                assert resp.json()["request_id"] == "test-req-12345"

                # Verify server-side logging was invoked with exc_info=True
                assert mock_logger_error.called
                args, kwargs = mock_logger_error.call_args
                assert kwargs.get("exc_info") is True
                assert "test-req-12345" in args
        finally:
            if original_override is not None:
                app.dependency_overrides[get_db] = original_override
            else:
                app.dependency_overrides.pop(get_db, None)

