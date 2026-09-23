from sqlalchemy import Column, String, ForeignKey
import uuid
from app.database.session import Base

class SecretReference(Base):
    __tablename__ = "secret_references"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    alias = Column(String(100), unique=True, nullable=False)
    provider = Column(String(50), nullable=False)
    description = Column(String(255), nullable=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)

class EncryptedSecret(Base):
    __tablename__ = "encrypted_secrets"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    reference_id = Column(String(36), ForeignKey("secret_references.id", ondelete="CASCADE"), unique=True)
    key_version = Column(String(10), nullable=False)
    iv_base64 = Column(String(64), nullable=False)
    tag_base64 = Column(String(64), nullable=False)
    ciphertext_base64 = Column(String, nullable=False)
