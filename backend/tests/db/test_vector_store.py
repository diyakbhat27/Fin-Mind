import pytest
import os
import shutil
from app.db.vector_store import ChromaDBManager
from app.services.rag_service import RAGService

@pytest.fixture
def mock_chroma():
    db = ChromaDBManager(persist_directory="./test_chroma_data", collection_name="test_collection")
    # Patch with EphemeralClient to prevent Windows disk lock errors during tests
    import chromadb
    db.client = chromadb.EphemeralClient()
    db.collection = db.client.get_or_create_collection(
        name="test_collection",
        embedding_function=db.embedding_function
    )
    yield db

def test_rbac_vector_pre_filtering(mock_chroma):
    # Insert 5 chunks: 3 public (VIEWER), 2 confidential (SUPER_ADMIN only)
    chunks = [
        {"id": "1", "text": "Apple public risk 1", "metadata": {"company": "AAPL", "role_SUPER_ADMIN": True, "role_VIEWER": True}},
        {"id": "2", "text": "Apple public risk 2", "metadata": {"company": "AAPL", "role_SUPER_ADMIN": True, "role_VIEWER": True}},
        {"id": "3", "text": "Microsoft public risk", "metadata": {"company": "MSFT", "role_SUPER_ADMIN": True, "role_VIEWER": True}},
        {"id": "4", "text": "Secret acquisition plan", "metadata": {"company": "AAPL", "role_SUPER_ADMIN": True}},
        {"id": "5", "text": "Secret compliance violation", "metadata": {"company": "MSFT", "role_SUPER_ADMIN": True}},
    ]
    mock_chroma.insert_chunks(chunks)
    
    # Query as VIEWER
    viewer_results = mock_chroma.search_with_rbac(query="risk", user_role="VIEWER", n_results=5)
    # Chroma returns lists of lists for documents, metadatas, ids
    viewer_ids = viewer_results["ids"][0]
    assert len(viewer_ids) == 3
    assert "4" not in viewer_ids
    assert "5" not in viewer_ids
    
    # Query as SUPER_ADMIN
    admin_results = mock_chroma.search_with_rbac(query="secret", user_role="SUPER_ADMIN", n_results=5)
    admin_ids = admin_results["ids"][0]
    # They should see all 5 (or top 5), including secrets
    assert "4" in admin_ids
    assert "5" in admin_ids

def test_rag_service_extra_filters(mock_chroma):
    chunks = [
        {"id": "1", "text": "Apple 2023 risks", "metadata": {"company": "AAPL", "year": 2023, "role_VIEWER": True}},
        {"id": "2", "text": "Apple 2022 risks", "metadata": {"company": "AAPL", "year": 2022, "role_VIEWER": True}},
        {"id": "3", "text": "Microsoft 2023 risks", "metadata": {"company": "MSFT", "year": 2023, "role_VIEWER": True}},
    ]
    mock_chroma.insert_chunks(chunks)
    
    # We patch the service to use our test DB
    service = RAGService()
    service.vector_store = mock_chroma
    
    # Filter by AAPL and 2023
    results = service.retrieve_context(query="risks", user_role="VIEWER", company="AAPL", year=2023, limit=5)
    
    assert len(results) == 1
    assert results[0]["id"] == "1"
    assert results[0]["metadata"]["company"] == "AAPL"
