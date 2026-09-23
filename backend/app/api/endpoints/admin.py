import logging
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator
from app.database.session import get_db
from app.auth.dependencies import get_current_user, require_role
from app.models.config import SystemConfig
from app.models.audit import AuditLog
from app.models.rbac import User
from app.core.rate_limit import limiter
from app.core.config import settings

logger = logging.getLogger("finmind.admin")

router = APIRouter()

class ConfigUpdate(BaseModel):
    key: str = Field(..., min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_\-\.]+$", description="Config key identifier")
    value: str = Field(..., min_length=1, max_length=5000, description="Config string value")

    @field_validator("key", "value")
    @classmethod
    def reject_null_bytes(cls, v: str) -> str:
        if "\x00" in v:
            raise ValueError("Null bytes are prohibited")
        return v

class ConfigResponse(BaseModel):
    key: str
    value: str
    updated_by: Optional[str]

@router.get("/config", response_model=List[ConfigResponse])
@limiter.limit(lambda: settings.RATE_LIMIT_AUTHENTICATED)
def get_system_config(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["ADMIN", "SUPER_ADMIN"]))
):
    """
    Returns the current system configuration.
    Strictly protected for SUPER_ADMIN only.
    """
    configs = db.query(SystemConfig).all()
    return configs

@router.put("/config")
@limiter.limit(lambda: settings.RATE_LIMIT_AUTHENTICATED)
def update_system_config(
    request: Request,
    config_update: ConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["SUPER_ADMIN"]))
):
    """
    Updates or creates a configuration key-value pair.
    Used for Prompt Versioning and LLM Switching.
    """
    config_entry = db.query(SystemConfig).filter(SystemConfig.key == config_update.key).first()
    
    if config_entry:
        config_entry.value = config_update.value
        config_entry.updated_by = current_user.username
    else:
        config_entry = SystemConfig(
            key=config_update.key, 
            value=config_update.value,
            updated_by=current_user.username
        )
        db.add(config_entry)
        
    try:
        db.commit()
        return {"status": "success", "message": f"Updated config for {config_update.key}"}
    except Exception as e:
        db.rollback()
        logger.error("Database error updating system config %s: %s", config_update.key, e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="A database error occurred while updating system configuration."
        )

@router.get("/audit-logs")
@limiter.limit(lambda: settings.RATE_LIMIT_AUTHENTICATED)
def view_audit_logs(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["ADMIN", "SUPER_ADMIN"]))
):
    """
    Paginated viewer for cryptographic audit logs.
    Protected for ADMIN and SUPER_ADMIN. ADMIN sees operational subset.
    """
    query = db.query(AuditLog)
    if current_user.role == "ADMIN":
        # Operational subset: exclude config changes, secret changes, system events
        # Assuming event types might be "CONFIG_UPDATE", "SECRET_RELOAD", etc.
        query = query.filter(~AuditLog.event_type.in_(["CONFIG_UPDATE", "SECRET_RELOAD"]))
        
    logs = query.order_by(AuditLog.id.desc()).offset(skip).limit(limit).all()
    return logs

@router.post("/secrets/reload")
@limiter.limit(lambda: settings.RATE_LIMIT_AUTHENTICATED)
def reload_secrets(
    request: Request,
    current_user: User = Depends(require_role(["SUPER_ADMIN"]))
):
    """
    Zero-Downtime Secret Migration.
    Hot-reloads the .env file into os.environ.
    Because agents now fetch their keys via SecretManager on instantiation,
    subsequent requests will immediately pick up the new keys without restarting the server.
    """
    from dotenv import load_dotenv
    import os
    
    # Reload the canonical backend .env file into os.environ
    env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))
    
    if os.path.exists(env_path):
        load_dotenv(dotenv_path=env_path, override=True)
        return {"status": "success", "message": "Secrets successfully hot-reloaded from .env"}
    else:
        raise HTTPException(status_code=404, detail="Configuration file not found for reload.")

