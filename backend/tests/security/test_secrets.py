import pytest
import os
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app
from app.models.rbac import User

@pytest.fixture
def client():
    return TestClient(app)

def test_secret_manager_interface():
    """Test that the SecretProvider abstraction works as expected."""
    from app.services.secret_manager import EnvSecretManager, get_secret
    
    os.environ["TEST_SECRET_KEY"] = "super_secret_value"
    
    manager = EnvSecretManager()
    assert manager.get_secret("TEST_SECRET_KEY") == "super_secret_value"
    
    # Test the global helper
    assert get_secret("TEST_SECRET_KEY") == "super_secret_value"

def test_zero_downtime_secret_reload(client, tmp_path, monkeypatch):
    """Test that the admin endpoint hot-reloads secrets from the .env file without restarting."""
    from app.auth import dependencies
    
    # Run as SUPER_ADMIN
    def mock_get_current_user():
        return User(id="admin_1", username="admin_user", role="SUPER_ADMIN")
        
    app.dependency_overrides[dependencies.get_current_user] = mock_get_current_user
    
    # Setup a mock .env file
    env_file = tmp_path / ".env"
    env_file.write_text("MOCKED_API_KEY=initial_value_123")
    
    # Mock the os.path.join in the admin endpoint to point to our temp .env file
    with patch("os.path.join", return_value=str(env_file)):
        
        # 1. First reload
        response = client.post("/api/v1/admin/secrets/reload", headers={"Authorization": "Bearer token"})
        assert response.status_code == 200
        assert os.environ.get("MOCKED_API_KEY") == "initial_value_123"
        
        # 2. Update the file (simulating a secret rotation on disk)
        env_file.write_text("MOCKED_API_KEY=new_rotated_value_456")
        
        # 3. Reload again
        response = client.post("/api/v1/admin/secrets/reload", headers={"Authorization": "Bearer token"})
        assert response.status_code == 200
        assert os.environ.get("MOCKED_API_KEY") == "new_rotated_value_456"
        
    app.dependency_overrides.clear()
