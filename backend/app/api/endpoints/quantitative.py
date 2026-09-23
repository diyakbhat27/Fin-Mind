import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
from app.auth.dependencies import get_current_user
from app.database.session import get_db
from app.models.rbac import User
from app.services.sql_agent import QuantitativeAgent
from app.core.rate_limit import limiter
from app.core.config import settings

logger = logging.getLogger("finmind.quant")

router = APIRouter()

class QuantQuery(BaseModel):
    query: str = Field(..., min_length=3, max_length=500, description="Financial quantitative query")

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Query cannot be empty or contain only whitespace.")
        if "\x00" in v:
            raise ValueError("Query cannot contain null bytes.")
        return v.strip()

@router.post("/analyze")
@limiter.limit(lambda: settings.RATE_LIMIT_AUTHENTICATED)
def analyze_financials(
    request: Request,
    query_in: QuantQuery, 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Executes a deterministic quantitative analysis using read-only SQLAlchemy ASTs.
    The LLM is strictly used as a semantic router.
    """
    # Enforce RBAC: ANALYST, ADMIN, or SUPER_ADMIN can run quantitative queries
    if current_user.role not in ["ANALYST", "ADMIN", "SUPER_ADMIN"]:
        raise HTTPException(status_code=403, detail="Forbidden. Required role: ANALYST, ADMIN, or SUPER_ADMIN")
        
    agent = QuantitativeAgent(db=db)
    
    try:
        result = agent.analyze(query_in.query)
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Error executing quantitative analysis for user %s: %s",
            getattr(current_user, "username", "unknown"),
            e,
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="An error occurred while executing the quantitative analysis."
        )
