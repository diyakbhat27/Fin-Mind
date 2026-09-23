from sqlalchemy import Column, String, Integer, Float, DateTime
import datetime
from app.database.session import Base

class TelemetryLog(Base):
    __tablename__ = "telemetry_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    query = Column(String(500), nullable=True)
    route = Column(String(50), nullable=True)
    latency_ms = Column(Float, nullable=False)
    user_role = Column(String(50), nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
