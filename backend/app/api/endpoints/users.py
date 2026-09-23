import logging
import re
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, EmailStr, field_validator
from app.database.session import get_db
from app.auth.dependencies import get_current_user, require_role
from app.models.rbac import User
from app.auth.security import get_password_hash
from app.core.rate_limit import limiter
from app.core.config import settings

logger = logging.getLogger("finmind.users")

router = APIRouter()

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=30, pattern=r"^[a-zA-Z0-9_]+$", description="Alphanumeric and underscore username")
    password: str = Field(..., min_length=6, max_length=128, description="Password min 6 chars, max 128 chars")
    role: str = Field(..., pattern=r"^(VIEWER|ANALYST|ADMIN|SUPER_ADMIN)$", description="Valid RBAC role")
    email: Optional[EmailStr] = Field(None, description="Valid email address")

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if "\x00" in v:
            raise ValueError("Null bytes are prohibited in password")
        # Check for control characters
        for char in v:
            if ord(char) < 32 and char not in ('\t', '\n', '\r'):
                raise ValueError("Control characters are not allowed in password")
        return v

class UserResponse(BaseModel):
    id: str
    username: str
    email: Optional[str] = None
    role: str
    is_active: bool

    class Config:
        from_attributes = True

@router.get("/", response_model=List[UserResponse])
@limiter.limit(lambda: settings.RATE_LIMIT_AUTHENTICATED)
def get_users(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["ADMIN", "SUPER_ADMIN"]))
):
    """
    List all users.
    """
    return db.query(User).all()

@router.post("/", response_model=UserResponse)
@limiter.limit(lambda: settings.RATE_LIMIT_AUTHENTICATED)
def create_user(
    request: Request,
    user_in: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["ADMIN", "SUPER_ADMIN"]))
):
    """
    Create a new user.
    ADMIN cannot create ADMIN or SUPER_ADMIN users.
    """
    if current_user.role == "ADMIN" and user_in.role in ["ADMIN", "SUPER_ADMIN"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ADMINs can only create VIEWER or ANALYST users."
        )
        
    existing_user = db.query(User).filter(User.username == user_in.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already registered")
        
    email = str(user_in.email) if user_in.email else f"{user_in.username}@finmind.internal"
    new_user = User(
        username=user_in.username,
        email=email,
        hashed_password=get_password_hash(user_in.password),
        role=user_in.role
    )
    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        return new_user
    except Exception as e:
        db.rollback()
        logger.error("Database error while creating user %s: %s", user_in.username, e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="A database error occurred while creating user account."
        )

@router.put("/{user_id}/deactivate", response_model=UserResponse)
@limiter.limit(lambda: settings.RATE_LIMIT_AUTHENTICATED)
def deactivate_user(
    request: Request,
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["ADMIN", "SUPER_ADMIN"]))
):
    """
    Deactivate a user.
    ADMIN cannot deactivate ADMIN or SUPER_ADMIN users.
    """
    if not user_id or not user_id.strip() or not re.match(r'^[a-zA-Z0-9_\-]+$', user_id.strip()):
        raise HTTPException(status_code=400, detail="Invalid user_id format.")
    user = db.query(User).filter(User.id == user_id.strip()).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    if current_user.role == "ADMIN" and user.role in ["ADMIN", "SUPER_ADMIN"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ADMINs cannot deactivate ADMIN or SUPER_ADMIN users."
        )
        
    try:
        user.is_active = False
        db.commit()
        db.refresh(user)
        return user
    except Exception as e:
        db.rollback()
        logger.error("Database error while deactivating user %s: %s", user_id, e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="A database error occurred while updating user status."
        )

