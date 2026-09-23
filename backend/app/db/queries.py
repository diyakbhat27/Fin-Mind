from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models.financials import FinancialReport
from typing import Dict, Any

class FinancialMetricsEngine:
    """
    Executes pre-compiled SQLAlchemy ASTs for deterministic financial calculations.
    Zero raw string SQL. Zero LLM math.
    """
    def __init__(self, db: Session):
        self.db = db

    def get_leverage_ratio(self, ticker: str, year: int) -> Dict[str, Any]:
        """
        Leverage Ratio = Total Liabilities / Total Equity
        """
        stmt = select(FinancialReport).where(
            FinancialReport.ticker == ticker,
            FinancialReport.fiscal_year == year
        )
        report = self.db.execute(stmt).scalar_one_or_none()
        
        if not report:
            return {"error": "Report not found for given ticker and year."}
            
        if not report.total_equity or report.total_equity == 0:
            return {"error": "Cannot calculate leverage ratio: Total Equity is missing or zero."}
            
        ratio = report.total_liabilities / report.total_equity
        return {
            "metric": "Leverage Ratio",
            "ticker": ticker,
            "year": year,
            "value": round(ratio, 4),
            "formula": "Total Liabilities / Total Equity"
        }

    def get_operating_margin(self, ticker: str, year: int) -> Dict[str, Any]:
        """
        Operating Margin = Operating Income / Net Revenue
        """
        stmt = select(FinancialReport).where(
            FinancialReport.ticker == ticker,
            FinancialReport.fiscal_year == year
        )
        report = self.db.execute(stmt).scalar_one_or_none()
        
        if not report:
            return {"error": "Report not found for given ticker and year."}
            
        if not report.net_revenue or report.net_revenue == 0:
            return {"error": "Cannot calculate operating margin: Net Revenue is missing or zero."}
            
        margin = report.operating_income / report.net_revenue
        return {
            "metric": "Operating Margin",
            "ticker": ticker,
            "year": year,
            "value": round(margin, 4),
            "formula": "Operating Income / Net Revenue"
        }

    def get_roe(self, ticker: str, year: int) -> Dict[str, Any]:
        """
        Return on Equity = Net Income / Total Equity
        """
        stmt = select(FinancialReport).where(
            FinancialReport.ticker == ticker,
            FinancialReport.fiscal_year == year
        )
        report = self.db.execute(stmt).scalar_one_or_none()
        
        if not report:
            return {"error": "Report not found for given ticker and year."}
            
        if not report.total_equity or report.total_equity == 0:
            return {"error": "Cannot calculate ROE: Total Equity is missing or zero."}
            
        if not report.net_income:
            return {"error": "Cannot calculate ROE: Net Income is missing."}
            
        margin = report.net_income / report.total_equity
        return {
            "metric": "Return on Equity (ROE)",
            "ticker": ticker,
            "year": year,
            "value": round(margin, 4),
            "formula": "Net Income / Total Equity"
        }

    def get_current_ratio(self, ticker: str, year: int) -> Dict[str, Any]:
        """
        Current Ratio = Total Current Assets / Total Current Liabilities
        """
        stmt = select(FinancialReport).where(
            FinancialReport.ticker == ticker,
            FinancialReport.fiscal_year == year
        )
        report = self.db.execute(stmt).scalar_one_or_none()
        
        if not report:
            return {"error": "Report not found for given ticker and year."}
            
        if not report.total_current_liabilities or report.total_current_liabilities == 0:
            return {"error": "Cannot calculate Current Ratio: Current Liabilities are missing or zero."}
            
        if not report.total_current_assets:
            return {"error": "Cannot calculate Current Ratio: Current Assets are missing."}
            
        ratio = report.total_current_assets / report.total_current_liabilities
        return {
            "metric": "Current Ratio",
            "ticker": ticker,
            "year": year,
            "value": round(ratio, 4),
            "formula": "Total Current Assets / Total Current Liabilities"
        }
