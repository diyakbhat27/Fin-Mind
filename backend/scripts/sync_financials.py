import asyncio
import sys
import os

# Add backend directory to sys.path so we can run this from root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.database.session import SessionLocal, Base, engine
from app.models.financials import FinancialReport
from app.ingestion.xbrl_parser import XBRLParser

# Target portfolio
PORTFOLIO = {
    "AAPL": "0000320193",
    "MSFT": "0000789019",
    "TSLA": "0001318605"
}

TARGET_YEAR = 2023

async def sync():
    print("Starting XBRL financial synchronization...")
    
    # Ensure tables exist
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    
    parser = XBRLParser()
    
    for ticker, cik in PORTFOLIO.items():
        print(f"[{ticker}] Fetching XBRL company facts from SEC EDGAR...")
        facts = await parser.get_company_facts(cik)
        
        if not facts:
            print(f"[{ticker}] FAILED: Could not retrieve data from SEC.")
            continue
            
        print(f"[{ticker}] Extracting 10-K values for {TARGET_YEAR}...")
        metrics = parser.extract_metrics_for_year(facts, TARGET_YEAR)
        
        # Upsert logic to ensure we don't duplicate
        report = db.query(FinancialReport).filter_by(ticker=ticker, fiscal_year=TARGET_YEAR).first()
        if not report:
            report = FinancialReport(ticker=ticker, fiscal_year=TARGET_YEAR)
            db.add(report)
            
        report.total_assets = metrics.get("Assets")
        report.total_liabilities = metrics.get("Liabilities")
        report.total_equity = metrics.get("StockholdersEquity")
        report.total_current_assets = metrics.get("AssetsCurrent")
        report.total_current_liabilities = metrics.get("LiabilitiesCurrent")
        report.net_revenue = metrics.get("Revenues")
        report.operating_income = metrics.get("OperatingIncomeLoss")
        report.net_income = metrics.get("NetIncomeLoss")
        
        db.commit()
        print(f"[{ticker}] Successfully synced {TARGET_YEAR} data to SQLite DB.")
        
        # Strict rate limit compliance: sleep 0.2s between calls (max 10 requests / sec)
        # We sleep 1 second just to be completely safe during deployment
        await asyncio.sleep(1.0)
        
    db.close()
    print("Synchronization complete.")

if __name__ == "__main__":
    asyncio.run(sync())
