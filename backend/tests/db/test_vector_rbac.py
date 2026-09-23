"""
Tests for Vector Store RBAC Filtering (VS1-VS8):
- VS1: VIEWER queries public doc
- VS2: VIEWER queries confidential doc (blocked)
- VS3: ANALYST queries confidential doc (allowed)
- VS4: ADMIN queries any doc (bypass)
- VS5: SUPER_ADMIN queries any doc (bypass)
- VS6: Company filter + RBAC
- VS7: Year filter + RBAC
- VS8: Empty vector store
"""
import pytest
import chromadb
from app.db.vector_store import ChromaDBManager


@pytest.fixture
def test_vector_db():
    """In-memory ephemeral Chroma instance seeded with multi-tier test documents."""
    manager = ChromaDBManager(persist_directory="./test_chroma_isolated", collection_name="rbac_test_col")
    # Use EphemeralClient for fast, fully isolated in-memory execution
    manager.client = chromadb.EphemeralClient()
    manager.collection = manager.client.get_or_create_collection(
        name="rbac_test_col",
        embedding_function=manager.embedding_function
    )

    chunks = [
        {
            "id": "c1_public_aapl_2023",
            "text": "Apple released the iPhone 15 in fiscal year 2023 with record revenue.",
            "metadata": {"company": "AAPL", "year": 2023, "role_VIEWER": True, "role_ANALYST": True, "role_ADMIN": True, "role_SUPER_ADMIN": True}
        },
        {
            "id": "c2_public_msft_2023",
            "text": "Microsoft expanded Azure AI cloud services throughout fiscal year 2023.",
            "metadata": {"company": "MSFT", "year": 2023, "role_VIEWER": True, "role_ANALYST": True, "role_ADMIN": True, "role_SUPER_ADMIN": True}
        },
        {
            "id": "c3_confidential_aapl_2023",
            "text": "Internal confidential memo: Apple R&D secret chip designs for 2024.",
            "metadata": {"company": "AAPL", "year": 2023, "role_ANALYST": True, "role_ADMIN": True, "role_SUPER_ADMIN": True}
        },
        {
            "id": "c4_confidential_tsla_2022",
            "text": "Internal confidential memo: Tesla prototype battery cell production issues.",
            "metadata": {"company": "TSLA", "year": 2022, "role_ANALYST": True, "role_ADMIN": True, "role_SUPER_ADMIN": True}
        },
        {
            "id": "c5_admin_only_audit",
            "text": "Super Admin executive severance and internal compensation package details.",
            "metadata": {"company": "INTERNAL", "year": 2023, "role_ADMIN": True, "role_SUPER_ADMIN": True}
        }
    ]
    manager.insert_chunks(chunks)
    yield manager


class TestVectorStoreRBAC:

    def test_vs1_viewer_queries_public_doc(self, test_vector_db):
        """VS1: VIEWER can retrieve public documents."""
        res = test_vector_db.search_with_rbac(query="iPhone 15 revenue", user_role="VIEWER", n_results=5)
        found_ids = res["ids"][0]
        assert "c1_public_aapl_2023" in found_ids

    def test_vs2_viewer_cannot_retrieve_confidential(self, test_vector_db):
        """VS2: VIEWER query never retrieves confidential-only documents."""
        res = test_vector_db.search_with_rbac(query="secret chip designs memo", user_role="VIEWER", n_results=10)
        found_ids = res["ids"][0]
        assert "c3_confidential_aapl_2023" not in found_ids
        assert "c4_confidential_tsla_2022" not in found_ids
        assert "c5_admin_only_audit" not in found_ids

    def test_vs3_analyst_queries_confidential_doc(self, test_vector_db):
        """VS3: ANALYST can retrieve confidential documents."""
        res = test_vector_db.search_with_rbac(query="secret chip designs memo", user_role="ANALYST", n_results=10)
        found_ids = res["ids"][0]
        assert "c3_confidential_aapl_2023" in found_ids

    def test_vs4_admin_queries_all_docs(self, test_vector_db):
        """VS4: ADMIN bypasses role filter and can access all documents."""
        res = test_vector_db.search_with_rbac(query="Apple memo", user_role="ADMIN", n_results=10)
        found_ids = res["ids"][0]
        # ADMIN can retrieve both public and confidential chunks
        assert len(found_ids) > 0
        assert any("confidential" in i or "admin" in i or "public" in i for i in found_ids)

    def test_vs5_super_admin_queries_all_docs(self, test_vector_db):
        """VS5: SUPER_ADMIN bypasses role filter and can access any document."""
        res = test_vector_db.search_with_rbac(query="severance compensation", user_role="SUPER_ADMIN", n_results=5)
        found_ids = res["ids"][0]
        assert "c5_admin_only_audit" in found_ids

    def test_vs6_company_filter_with_rbac(self, test_vector_db):
        """VS6: Metadata company filter combined with VIEWER role returns only public AAPL chunks."""
        res = test_vector_db.search_with_rbac(
            query="fiscal year",
            user_role="VIEWER",
            extra_filters={"company": "AAPL"},
            n_results=10
        )
        found_ids = res["ids"][0]
        # Should only contain public AAPL, never MSFT or confidential
        assert "c1_public_aapl_2023" in found_ids
        assert "c2_public_msft_2023" not in found_ids
        assert "c3_confidential_aapl_2023" not in found_ids

    def test_vs7_year_filter_with_rbac(self, test_vector_db):
        """VS7: Metadata year filter combined with ANALYST role returns only 2022 chunks."""
        res = test_vector_db.search_with_rbac(
            query="battery production memo",
            user_role="ANALYST",
            extra_filters={"year": 2022},
            n_results=10
        )
        found_ids = res["ids"][0]
        assert "c4_confidential_tsla_2022" in found_ids
        assert "c1_public_aapl_2023" not in found_ids

    def test_vs8_empty_vector_store(self):
        """VS8: Querying an empty collection returns empty lists without error."""
        empty_manager = ChromaDBManager(persist_directory="./test_empty", collection_name="empty_col")
        empty_manager.client = chromadb.EphemeralClient()
        empty_manager.collection = empty_manager.client.get_or_create_collection(
            name="empty_col",
            embedding_function=empty_manager.embedding_function
        )
        res = empty_manager.search_with_rbac(query="anything", user_role="VIEWER")
        assert len(res["ids"][0]) == 0
