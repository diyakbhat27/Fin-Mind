from app.db.vector_store import ChromaDBManager

class RAGService:
    def __init__(self):
        self.vector_store = ChromaDBManager()
        
    def retrieve_context(self, query: str, user_role: str, company: str = None, year: int = None, limit: int = 5) -> list:
        """
        Retrieves relevant 10-K chunks securely.
        """
        extra_filters = {}
        if company or year:
            conditions = []
            if company:
                conditions.append({"company": company})
            if year:
                conditions.append({"year": year})
                
            if len(conditions) == 1:
                extra_filters = conditions[0]
            else:
                extra_filters = {"$and": conditions}
                
        results = self.vector_store.search_with_rbac(
            query=query, 
            user_role=user_role, 
            n_results=limit, 
            extra_filters=extra_filters if extra_filters else None
        )
        
        # Results is a dictionary with 'ids', 'documents', 'metadatas', 'distances'
        chunks = []
        if results and results.get("documents") and len(results["documents"]) > 0:
            for i in range(len(results["documents"][0])):
                chunks.append({
                    "id": results["ids"][0][i],
                    "text": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "distance": results["distances"][0][i] if "distances" in results else None
                })
        return chunks
