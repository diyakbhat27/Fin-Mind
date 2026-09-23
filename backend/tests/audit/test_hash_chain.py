import pytest
import hashlib
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.audit import AuditLog
from app.database.session import Base
from app.core.audit import AuditLogger

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    yield db
    db.close()

def test_hash_chain_integrity(db_session):
    # Log 3 events
    log1 = AuditLogger.log_event(db_session, event_type="TEST_1", status_code=200, payload={"msg": "first"})
    log2 = AuditLogger.log_event(db_session, event_type="TEST_2", status_code=200, payload={"msg": "second", "password": "secret_password"})
    log3 = AuditLogger.log_event(db_session, event_type="TEST_3", status_code=200, payload={"msg": "third"})

    # Verify log1
    expected_prev = "0" * 64
    assert log1.prev_hash == expected_prev
    expected_hash1 = hashlib.sha256((expected_prev + json.dumps({"msg": "first"}, sort_keys=True)).encode('utf-8')).hexdigest()
    assert log1.entry_hash == expected_hash1

    # Verify log2 (ensure redaction worked)
    assert log2.prev_hash == log1.entry_hash
    expected_payload2 = json.dumps({"msg": "second", "password": "[REDACTED]"}, sort_keys=True)
    expected_hash2 = hashlib.sha256((log1.entry_hash + expected_payload2).encode('utf-8')).hexdigest()
    assert log2.entry_hash == expected_hash2
    assert log2.payload_sanitized == expected_payload2

    # Verify log3
    assert log3.prev_hash == log2.entry_hash
    expected_hash3 = hashlib.sha256((log2.entry_hash + json.dumps({"msg": "third"}, sort_keys=True)).encode('utf-8')).hexdigest()
    assert log3.entry_hash == expected_hash3

def test_tamper_detection_on_chain(db_session):
    # Log 2 events
    log1 = AuditLogger.log_event(db_session, event_type="TEST_1", status_code=200, payload={"data": "A"})
    log2 = AuditLogger.log_event(db_session, event_type="TEST_2", status_code=200, payload={"data": "B"})
    
    # Tamper with log1
    log1.payload_sanitized = json.dumps({"data": "MALICIOUS"}, sort_keys=True)
    db_session.commit()
    
    # Validation step (simulate the validator logic)
    # Re-hash log1
    recalculated_hash1 = hashlib.sha256((log1.prev_hash + log1.payload_sanitized).encode('utf-8')).hexdigest()
    
    # Because we tampered with the payload, the recalculated hash no longer matches the stored entry_hash
    assert recalculated_hash1 != log1.entry_hash
    
    # Even if they tried to update entry_hash of log1 to cover their tracks, log2.prev_hash would no longer match.
    assert log2.prev_hash == log1.entry_hash
