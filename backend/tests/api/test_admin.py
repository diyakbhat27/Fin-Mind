import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.models.rbac import User
from app.models.config import SystemConfig

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def mock_viewer_token():
    return "mock_viewer_token"

@pytest.fixture
def mock_super_admin_token():
    return "mock_super_admin_token"

# In a real setup, we'd mock the dependency or the db. For simplicity, we will mock the require_role dependency directly.

def test_admin_config_get_forbidden_for_viewer(client, monkeypatch):
    from app.auth import dependencies
    
    def mock_get_current_user():
        return User(id="user_1", username="viewer_user", role="VIEWER")
        
    app.dependency_overrides[dependencies.get_current_user] = mock_get_current_user
    
    response = client.get("/api/v1/admin/config", headers={"Authorization": "Bearer token"})
    
    if response.status_code != 403:
        print(response.json())
        
    assert response.status_code == 403
    app.dependency_overrides.clear()

def test_admin_config_get_allowed_for_super_admin(client):
    from app.auth import dependencies
    
    def mock_get_current_user():
        return User(id="user_1", username="admin_user", role="SUPER_ADMIN")
        
    app.dependency_overrides[dependencies.get_current_user] = mock_get_current_user
    
    response = client.get("/api/v1/admin/config", headers={"Authorization": "Bearer token"})
    
    assert response.status_code == 200
    app.dependency_overrides.clear()
    
def test_admin_config_put_allowed_for_super_admin(client):
    from app.auth import dependencies
    
    def mock_get_current_user():
        return User(id="user_1", username="admin_user", role="SUPER_ADMIN")
        
    app.dependency_overrides[dependencies.get_current_user] = mock_get_current_user
    
    payload = {
        "key": "rag_system_prompt",
        "value": "You are a NEW AI Assistant."
    }
    
    response = client.put("/api/v1/admin/config", json=payload, headers={"Authorization": "Bearer token"})
    
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    app.dependency_overrides.clear()
