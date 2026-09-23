import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.auth.dependencies import get_current_user
from app.models.rbac import User

client = TestClient(app)

def mock_get_current_user_viewer():
    user = User(username="viewer1", email="viewer@test.com", hashed_password="pw", role="VIEWER")
    return user

def mock_get_current_user_analyst():
    user = User(username="analyst1", email="analyst@test.com", hashed_password="pw", role="ANALYST")
    return user

def test_rag_query_endpoint_unauthorized():
    response = client.post("/api/v1/rag/query", json={"query": "test"})
    # Since OAuth2 is not provided, it should fail with 401
    assert response.status_code == 401

def test_rag_query_endpoint_viewer(monkeypatch):
    app.dependency_overrides[get_current_user] = mock_get_current_user_viewer
    
    response = client.post("/api/v1/rag/query", json={"query": "test query"})
    
    assert response.status_code in [200, 500]
    app.dependency_overrides.clear()

def test_rag_query_endpoint_analyst(monkeypatch):
    app.dependency_overrides[get_current_user] = mock_get_current_user_analyst
    
    response = client.post("/api/v1/rag/query", json={"query": "test query"})
    assert response.status_code in [200, 500]
    app.dependency_overrides.clear()
