from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from typing import List
from app.database.session import get_db
from app.auth.jwt import decode_token
from app.models.rbac import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login")

ROLE_PERMISSIONS = {
    "VIEWER": ["read_public"],
    "ANALYST": ["read_public", "read_confidential", "run_sql", "run_compliance"],
    "ADMIN": ["read_public", "read_confidential", "run_sql", "run_compliance", "manage_users", "view_audit"],
    "SUPER_ADMIN": ["read_public", "read_confidential", "run_sql", "run_compliance", "manage_users", "manage_prompts", "manage_config", "view_audit"]
}

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = decode_token(token)
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")
        
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")
    return user

def require_role(required_roles: List[str]):
    def role_checker(current_user: User = Depends(get_current_user)):
        if current_user.role == "SUPER_ADMIN":
            return current_user  # Super Admin bypasses role checks
        if current_user.role in required_roles:
            return current_user
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough privileges")
    return role_checker

def require_permission(required_permission: str):
    def permission_checker(current_user: User = Depends(get_current_user)):
        if current_user.role == "SUPER_ADMIN":
            return current_user  # Super Admin bypasses
            
        allowed_perms = ROLE_PERMISSIONS.get(current_user.role, [])
        if required_permission in allowed_perms:
            return current_user
            
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Missing required permission: {required_permission}")
    return permission_checker
