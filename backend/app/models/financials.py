from sqlalchemy import Column, Integer, String, Float, UniqueConstraint
from app.database.session import Base

class FinancialReport(Base):
    __tablename__ = "financial_reports"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String, index=True, nullable=False)
    fiscal_year = Column(Integer, nullable=False)
    
    # Balance Sheet (Simplified for MVP)
    total_assets = Column(Float, nullable=True)
    total_liabilities = Column(Float, nullable=True)
    total_equity = Column(Float, nullable=True)
    total_current_assets = Column(Float, nullable=True)
    total_current_liabilities = Column(Float, nullable=True)
    
    # Income Statement
    net_revenue = Column(Float, nullable=True)
    operating_income = Column(Float, nullable=True)
    net_income = Column(Float, nullable=True)
    
    __table_args__ = (
        UniqueConstraint('ticker', 'fiscal_year', name='uix_ticker_year'),
    )
