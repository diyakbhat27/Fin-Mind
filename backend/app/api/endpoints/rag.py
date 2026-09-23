import logging
import re
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from app.auth.dependencies import get_current_user
from app.models.rbac import User
from app.services.rag_chain import SecureRAGChain
from app.core.rate_limit import limiter
from app.core.config import settings

logger = logging.getLogger("finmind.rag")

router = APIRouter()
_rag_chain = None

def get_rag_chain():
    global _rag_chain
    if _rag_chain is None:
        _rag_chain = SecureRAGChain()
    return _rag_chain

class RAGQuery(BaseModel):
    query: str = Field(..., min_length=3, max_length=1000, description="Natural language search query")
    company: Optional[str] = Field(None, max_length=100, description="Optional target company name or ticker")
    year: Optional[int] = Field(None, ge=1990, le=2100, description="Optional 4-digit fiscal year")

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Query cannot be empty or whitespace only")
        if "\x00" in v:
            raise ValueError("Null bytes are prohibited")
        return v.strip()

    @field_validator("company")
    @classmethod
    def validate_company(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v_clean = v.strip()
        if not v_clean:
            raise ValueError("Company cannot be empty string")
        if "\x00" in v_clean:
            raise ValueError("Null bytes are prohibited")
        if not re.match(r"^[A-Za-z0-9\s.,&'-]+$", v_clean):
            raise ValueError("Company name contains invalid characters")
        return v_clean

class RAGResponse(BaseModel):
    answer: str
    citations: List[str]

@router.post("/query", response_model=RAGResponse)
@limiter.limit(lambda: settings.RATE_LIMIT_AUTHENTICATED)
def query_sec_data(
    request: Request,
    query_in: RAGQuery,
    current_user: User = Depends(get_current_user)
):
    """
    Executes a natural language query against the SEC vector database.
    Requires authentication. The user's role is strictly enforced by the vector store.
    """
    # For Phase 3, we extract the role from the user model directly.
    user_role = current_user.role
        
    try:
        chain = get_rag_chain()
        result = chain.ask(
            query=query_in.query,
            user_role=user_role,
            company=query_in.company,
            year=query_in.year
        )
        return RAGResponse(answer=result["answer"], citations=result["citations"])
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error executing SEC RAG query for user %s: %s",
            getattr(current_user, "username", "unknown"),
            e,
            exc_info=True
        )
        raise HTTPException(status_code=500, detail="An error occurred while querying the financial knowledge base.")

