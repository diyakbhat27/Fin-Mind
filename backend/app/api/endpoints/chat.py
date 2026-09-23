import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
from app.auth.dependencies import get_current_user
from app.database.session import get_db
from app.models.rbac import User
from app.services.supervisor import supervisor_graph
from app.core.rate_limit import limiter
from app.core.config import settings

logger = logging.getLogger("finmind.chat")

router = APIRouter()

class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000, description="The user query (max 1000 chars)")

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Query cannot be empty or contain only whitespace.")
        if "\x00" in v:
            raise ValueError("Query cannot contain null bytes.")
        return v

@router.post("")
@limiter.limit(lambda: settings.RATE_LIMIT_CHAT)
def unified_chat(
    request: Request,
    chat_request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Unified entry point for all queries. 
    The LangGraph supervisor determines which agent handles the request.
    """
    user_role = current_user.role
    
    # 2. Invoke Supervisor Agent
    # We pass the auth info directly into the LangGraph state.
    state = {
        "query": chat_request.query,
        "user_id": str(current_user.id),
        "user_role": user_role,
        "db_session": db,
        "next_node": None,
        "final_response": None
    }
    
    import time
    from app.models.telemetry import TelemetryLog
    
    try:
        # LangGraph invoke processes the graph sequentially until END
        start_time = time.perf_counter()
        result = supervisor_graph.invoke(state)
        latency_ms = (time.perf_counter() - start_time) * 1000.0
        
        # Determine route taken from the supervisor output if available
        # The supervisor uses 'next_node' to decide where it went, but in the final state,
        # 'next_node' might just hold the last agent executed.
        route = result.get("route") or result.get("next_node", "UNKNOWN")
        
        # Log telemetry async (or sync since we're in a regular endpoint for now)
        try:
            telemetry = TelemetryLog(
                query=chat_request.query,
                route=route,
                latency_ms=latency_ms,
                user_role=user_role
            )
            db.add(telemetry)
            db.commit()
        except Exception as tel_err:
            db.rollback()
            logger.warning("Failed to record chat telemetry log: %s", tel_err)
        
        if result.get("final_response"):
            response = result["final_response"]
            if "error" in response:
                status = 403 if "Forbidden" in response["error"] else 400
                raise HTTPException(status_code=status, detail=response["error"])
            return response
            

        raise HTTPException(status_code=500, detail="Graph failed to return a final response.")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Chat orchestration exception for user %s: %s",
            getattr(current_user, "username", "unknown"),
            e,
            exc_info=True
        )
        raise HTTPException(status_code=500, detail="An error occurred while processing your chat request.")
