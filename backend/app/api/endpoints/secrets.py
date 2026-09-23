import os
import logging
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, Field, field_validator
from typing import List
from app.auth.dependencies import require_role
from app.models.rbac import User
from app.core.rate_limit import limiter
from app.core.config import settings

logger = logging.getLogger("finmind.secrets")

router = APIRouter()

class SecretResponse(BaseModel):
    key: str
    is_set: bool

class SecretUpdate(BaseModel):
    key: str = Field(..., min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_]+$", description="Environment variable secret key")
    value: str = Field(..., min_length=1, max_length=2000, description="Secret value")

    @field_validator("key", "value")
    @classmethod
    def reject_null_bytes(cls, v: str) -> str:
        if "\x00" in v:
            raise ValueError("Null bytes are prohibited")
        return v

@router.get("/", response_model=List[SecretResponse])
@limiter.limit(lambda: settings.RATE_LIMIT_AUTHENTICATED)
def get_secrets(
    request: Request,
    current_user: User = Depends(require_role(["ADMIN", "SUPER_ADMIN"]))
):
    """
    Returns a list of secret keys (reference names) without the actual values.
    """
    # Assuming secrets are stored in .env or environment variables
    # We will list standard secrets used in this application
    known_secrets = ["GEMINI_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY"]
    
    response = []
    for key in known_secrets:
        response.append({
            "key": key,
            "is_set": bool(os.environ.get(key))
        })
    return response

@router.put("/")
@limiter.limit(lambda: settings.RATE_LIMIT_AUTHENTICATED)
def update_secret(
    request: Request,
    secret: SecretUpdate,
    current_user: User = Depends(require_role(["SUPER_ADMIN"]))
):
    """
    Update a secret. Only SUPER_ADMIN can do this.
    The secret value never leaves the backend.
    """
    # Update the environment variable for immediate use
    os.environ[secret.key] = secret.value
    
    # Also write it to the canonical backend/.env file for persistence
    try:
        env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))
        
        env_vars = {}
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    if "=" in line and not line.strip().startswith("#"):
                        k, v = line.strip().split("=", 1)
                        env_vars[k] = v
                        
        env_vars[secret.key] = secret.value
        
        with open(env_path, "w", encoding="utf-8") as f:
            for k, v in env_vars.items():
                f.write(f"{k}={v}\n")
    except Exception as e:
        logger.error("Failed to persist secret update to disk: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An error occurred while persisting the secret."
        )
            
    return {"status": "success", "message": f"Secret {secret.key} updated securely."}

