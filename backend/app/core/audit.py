import json
import hashlib
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
from app.models.audit import AuditLog
from app.database.session import SessionLocal

class AuditLoggerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # For this MVP, we log the method and path. 
        # Detailed payload logging should happen at the router level where body is parsed.
        try:
            db = SessionLocal()
            AuditLogger.log_event(
                db=db,
                event_type=f"{request.method} {request.url.path}",
                status_code=response.status_code,
                client_ip=request.client.host if request.client else None
            )
            db.close()
        except Exception as e:
            # If DB is not ready or fails, don't crash the request
            pass
            
        return response

class AuditLogger:
    @staticmethod
    def _hash_data(data: str) -> str:
        return hashlib.sha256(data.encode('utf-8')).hexdigest()

    @staticmethod
    def _sanitize_payload(payload: Dict[str, Any]) -> str:
        """
        Removes sensitive data from payload before logging.
        """
        sanitized = payload.copy()
        sensitive_keys = ['password', 'token', 'access_token', 'refresh_token', 'secret', 'key']
        for k in sensitive_keys:
            if k in sanitized:
                sanitized[k] = "[REDACTED]"
        
        # Convert to deterministic JSON string for hashing
        return json.dumps(sanitized, sort_keys=True)

    @classmethod
    def log_event(
        cls, 
        db: Session, 
        event_type: str, 
        status_code: int,
        request_id: Optional[str] = None,
        user_id: Optional[str] = None,
        user_role: Optional[str] = None,
        client_ip: Optional[str] = None,
        resource_accessed: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None
    ) -> AuditLog:
        # Get previous hash
        last_log = db.query(AuditLog).order_by(AuditLog.id.desc()).first()
        prev_hash = last_log.entry_hash if last_log else "0" * 64

        sanitized_payload_str = cls._sanitize_payload(payload) if payload else "{}"
        
        # Calculate entry hash: sha256(prev_hash + payload)
        combined = prev_hash + sanitized_payload_str
        entry_hash = cls._hash_data(combined)
        
        new_log = AuditLog(
            request_id=request_id,
            user_id=user_id,
            user_role=user_role,
            client_ip=client_ip,
            event_type=event_type,
            resource_accessed=resource_accessed,
            status_code=status_code,
            payload_sanitized=sanitized_payload_str,
            prev_hash=prev_hash,
            entry_hash=entry_hash
        )
        db.add(new_log)
        db.commit()
        db.refresh(new_log)
        return new_log
