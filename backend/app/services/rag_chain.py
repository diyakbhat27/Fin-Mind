import os
import uuid
import logging
from langchain_chroma import Chroma
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from app.services.rag_service import RAGService
from app.core.prompts import RAG_SYSTEM_PROMPT_DEFAULT, RAG_USER_PROMPT_DEFAULT, get_config
from app.services.secret_manager import get_secret
from sqlalchemy.orm import Session

logger = logging.getLogger("finmind.rag_chain")

class SecureRAGChain:
    """
    RAG Implementation strictly enforcing RBAC-filtered vector retrieval.
    """
    def __init__(self, db: Session = None):
        self.db = db
        self.rag_service = RAGService()
        # Read model config from DB or fallback
        llm_model = get_config(self.db, "rag_llm_model", "gemini-3.8-flash")
        
        # Fetch API key through our SecretManager interface
        api_key = get_secret("GEMINI_API_KEY") or "mock_api_key_for_local_eval"
        self.llm = ChatGoogleGenerativeAI(model=llm_model, temperature=0.0, max_retries=3, api_key=api_key)
        self.embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        self.vectorstore = Chroma(
            persist_directory="./chroma_db",
            embedding_function=self.embeddings
        )

    def ask(self, query: str, user_role: str, company: str = None, year: int = None) -> dict:
        """
        Answers a user query using only allowed documents.
        Executes the secured RAG pipeline.
        """
        # Dynamic Prompt
        system_prompt = get_config(self.db, "rag_system_prompt", RAG_SYSTEM_PROMPT_DEFAULT)
        user_prompt = get_config(self.db, "rag_user_prompt", RAG_USER_PROMPT_DEFAULT)

        # 1. Retrieve filtered context
        chunks = self.rag_service.retrieve_context(
            query=query, 
            user_role=user_role, 
            company=company, 
            year=year,
            limit=5
        )

        if not chunks:
            return {
                "answer": "Sorry, there is no data available",
                "citations": []
            }

        # 2. Extract the fence tag (assuming all chunks in a single retrieval share the same risk model, 
        # or we just use the first chunk's tag as the bounding tag for the prompt).
        # Actually, each chunk has its own random tag. Let's wrap ALL chunks in ONE master fence for the prompt,
        # OR just use the chunk's individual fences. The prompt says "inside the <{fence_tag}> blocks".
        # Let's generate a master fence for this specific prompt execution to be safe.
        import secrets
        master_fence = f"untrusted_data_{secrets.token_hex(4)}"

        # 3. Assemble the context block
        context_texts = []
        citations = []
        for chunk in chunks:
            # We wrap the chunk's text in our master fence and include the chunk ID
            # Assuming chunk['text'] contains the raw text (if it was fenced by parser, 
            # we just wrap it again, or we can just inject the ID into our master fence).
            context_texts.append(f"<{master_fence} id=\"{chunk['id']}\">\n{chunk['text']}\n</{master_fence}>")
            citations.append(chunk["id"])
        full_context = "\n\n".join(context_texts)

        # 4. Build the prompt
        system_message = system_prompt.format(fence_tag=master_fence, context=full_context)
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_message),
            ("human", user_prompt)
        ])

        # 5. Execute Chain
        chain = prompt | self.llm | StrOutputParser()
        
        try:
            answer = chain.invoke({"query": query})
        except Exception as e:
            logger.error("RAG chain LLM invocation failed: %s", e, exc_info=True)
            # Handle cases where API key is missing or invalid
            if "api_key" in str(e).lower() or "credentials" in str(e).lower():
                answer = "SYSTEM_ERROR: LLM API key not configured or invalid."
            else:
                answer = "SYSTEM_ERROR: LLM invocation failed due to an internal error."

        return {
            "answer": answer,
            "citations": citations
        }
