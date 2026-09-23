from sqlalchemy import Column, String, Integer, DateTime
import uuid
import datetime
from app.database.session import Base

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    event_id = Column(String(36), unique=True, default=lambda: str(uuid.uuid4()))
    request_id = Column(String(36), nullable=True)
    user_id = Column(String(36), nullable=True)
    user_role = Column(String(50), nullable=True)
    client_ip = Column(String(45), nullable=True)
    event_type = Column(String(50), nullable=False)
    resource_accessed = Column(String(255), nullable=True)
    status_code = Column(Integer, nullable=False)
    payload_sanitized = Column(String, nullable=True) # JSON stored as string for exact hashing
    prev_hash = Column(String(64), nullable=False)
    entry_hash = Column(String(64), nullable=False)
