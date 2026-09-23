import pytest
from fastapi import HTTPException
from app.auth.jwt import create_access_token, create_refresh_token, verify_refresh_token
from app.auth.dependencies import require_role, require_permission
from app.models.rbac import User

class MockUser:
    def __init__(self, role: str):
        self.role = role

def test_require_role_success():
    user = MockUser("ANALYST")
    checker = require_role(["ANALYST"])
    assert checker(user) == user

def test_require_role_forbidden():
    user = MockUser("VIEWER")
    checker = require_role(["ANALYST"])
    with pytest.raises(HTTPException) as exc_info:
        checker(user)
    assert exc_info.value.status_code == 403

def test_super_admin_bypass():
    user = MockUser("SUPER_ADMIN")
    checker = require_role(["ANALYST"])
    assert checker(user) == user

def test_require_permission_success():
    user = MockUser("ANALYST")
    checker = require_permission("run_sql")
    assert checker(user) == user

def test_require_permission_forbidden():
    user = MockUser("VIEWER")
    checker = require_permission("run_sql")
    with pytest.raises(HTTPException) as exc_info:
        checker(user)
    assert exc_info.value.status_code == 403

def test_require_permission_super_admin_bypass():
    user = MockUser("SUPER_ADMIN")
    checker = require_permission("manage_config")
    assert checker(user) == user

def test_refresh_token_ip_binding_success():
    ip = "192.168.1.100"
    token = create_refresh_token({"sub": "user123"}, client_ip=ip)
    payload = verify_refresh_token(token, request_ip=ip)
    assert payload["sub"] == "user123"

def test_refresh_token_ip_binding_failure():
    token = create_refresh_token({"sub": "user123"}, client_ip="192.168.1.100")
    with pytest.raises(ValueError) as exc_info:
        verify_refresh_token(token, request_ip="10.0.0.5")
    assert "Token is not bound to this IP address" in str(exc_info.value)
