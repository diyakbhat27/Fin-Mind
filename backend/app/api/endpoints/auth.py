from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.models.rbac import User
from app.auth.security import verify_password
from app.auth.jwt import create_access_token
from app.core.rate_limit import limiter, get_client_ip, auth_backoff_tracker
from app.core.config import settings
import re
from typing import Any

router = APIRouter()

@router.post("/login")
@limiter.limit(lambda: settings.RATE_LIMIT_AUTH)
def login_access_token(
    request: Request,
    db: Session = Depends(get_db), form_data: OAuth2PasswordRequestForm = Depends()
) -> Any:
    """
    OAuth2 compatible token login, get an access token for future requests.
    Validates input schema strictly and enforces exponential backoff on repeated failures.
    """
    username = form_data.username.strip() if form_data.username else ""
    password = form_data.password if form_data.password else ""
    client_ip = get_client_ip(request)

    # 1. Strict Input Validation (Reject invalid types/lengths/formats)
    if not username or len(username) > 50 or not re.match(r'^[a-zA-Z0-9_\-\.@]+$', username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid username format or length."
        )

    if not password or len(password) > 128 or '\x00' in password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid password format or length."
        )

    # 2. Check Exponential Backoff (Per-Account & Per-IP)
    backoff_remaining = auth_backoff_tracker.check_backoff(username, client_ip)
    if backoff_remaining:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed login attempts. Please retry after {backoff_remaining} seconds.",
            headers={"Retry-After": str(backoff_remaining)}
        )

    # 3. Query Database and Verify Password
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        auth_backoff_tracker.record_failure(username, client_ip)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect username or password"
        )
        
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user"
        )

    # 4. Success: Reset failure tracking & return JWT
    auth_backoff_tracker.record_success(username, client_ip)
    role = user.role
    return {
        "access_token": create_access_token(
            data={"sub": user.id, "role": role}
        ),
        "token_type": "bearer",
    }

