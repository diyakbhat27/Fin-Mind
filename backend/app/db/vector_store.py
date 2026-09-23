import os
import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions

class ChromaDBManager:
    """
    Manages the persistent ChromaDB vector store for SEC filings.
    Implements RBAC metadata enforcement.
    """
    def __init__(self, persist_directory: str = "./chroma_data", collection_name: str = "sec_filings"):
        self.persist_directory = persist_directory
        self.client = chromadb.PersistentClient(path=self.persist_directory)
        
        # We strictly use local embeddings for Phase 2 to prevent API key leaks
        # We use the popular all-MiniLM-L6-v2 which is small and fast for CPU embedding
        self.embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=self.embedding_function
        )

    def insert_chunks(self, chunks: list[dict]):
        """
        Inserts chunks into the vector store.
        `chunks` is a list of dictionaries with 'id', 'text', and 'metadata'.
        """
        ids = [chunk["id"] for chunk in chunks]
        texts = [chunk["text"] for chunk in chunks]
        metadatas = [chunk["metadata"] for chunk in chunks]
        
        self.collection.upsert(
            ids=ids,
            documents=texts,
            metadatas=metadatas
        )

    def search_with_rbac(self, query: str, user_role: str, n_results: int = 5, extra_filters: dict = None) -> list:
        """
        Executes a vector search, enforcing RBAC at the query level.
        The `where` clause is mathematically evaluated before vector distance calculation.
        """
        # Ensure the user's role is in the 'allowed_roles' metadata field
        # ChromaDB supports the $contains operator for array fields (if metadata allowed_roles is a stringified list, 
        # or we just store 'allowed_roles' as a comma-separated string and do string matching, but the best way
        # in standard Chroma is to store scalar metadata fields or handle it via $in).
        # Wait, Chroma metadata values must be str, int, float, or bool. It does NOT support lists directly.
        # So we store "role_SUPER_ADMIN": True, "role_ANALYST": True in metadata.
        
        if user_role in ["ADMIN", "SUPER_ADMIN"]:
            # Admin and Super Admin have access to everything (public and confidential)
            final_where = extra_filters
        else:
            # RBAC Filter Construction
            rbac_filter = {f"role_{user_role}": True}
            
            final_where = rbac_filter
            
            if extra_filters:
                # If there are additional filters (like company="AAPL"), we must use $and
                final_where = {
                    "$and": [
                        rbac_filter,
                        extra_filters
                    ]
                }
            
        results = self.collection.query(
            query_texts=[query],
            n_results=n_results,
            where=final_where
        )
        return results
