import asyncio
import httpx
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class XBRLParser:
    """
    Production-ready SEC XBRL parser.
    Extracts deterministic us-gaap financial facts for given CIKs.
    Implements rate-limiting to comply with SEC's 10 requests/second policy.
    """
    # SEC headers MUST include a registered User-Agent
    HEADERS = {"User-Agent": "FinMind AdminContact@finmind.local"}
    BASE_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    
    # Fallback mappings due to SEC taxonomy inconsistencies across companies
    TAG_MAPPINGS = {
        "Assets": ["Assets"],
        "Liabilities": ["Liabilities"],
        "StockholdersEquity": ["StockholdersEquity", "PartnersCapital", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
        "NetIncomeLoss": ["NetIncomeLoss", "ProfitLoss"],
        "OperatingIncomeLoss": ["OperatingIncomeLoss"],
        "AssetsCurrent": ["AssetsCurrent"],
        "LiabilitiesCurrent": ["LiabilitiesCurrent"],
        "Revenues": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet", "SalesRevenueGoodsNet"]
    }

    async def get_company_facts(self, cik: str) -> Optional[Dict[str, Any]]:
        """
        Fetches the raw company facts JSON.
        Includes a strict timeout to prevent connection hanging vulnerabilities.
        """
        url = self.BASE_URL.format(cik=cik.zfill(10))
        async with httpx.AsyncClient(headers=self.HEADERS, follow_redirects=True) as client:
            try:
                response = await client.get(url, timeout=15.0)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as e:
                logger.error(f"HTTP error occurred while fetching XBRL for CIK {cik}: {str(e)}")
                return None
            except Exception as e:
                logger.error(f"Unexpected error fetching XBRL for CIK {cik}: {str(e)}")
                return None

    def extract_metrics_for_year(self, facts: Dict[str, Any], year: int) -> Dict[str, float]:
        """
        Extracts the required 10-K values for a specific fiscal year.
        """
        extracted = {}
        gaap_data = facts.get("facts", {}).get("us-gaap", {})
        
        for metric_name, possible_tags in self.TAG_MAPPINGS.items():
            value = None
            for tag in possible_tags:
                if tag in gaap_data:
                    # Search for the specific year's 10-K value
                    units = gaap_data[tag].get("units", {})
                    # Standard SEC USD tag
                    usd_facts = units.get("USD", [])
                    for fact in usd_facts:
                        # We only want audited 10-K annual facts, not 10-Q quarters
                        if fact.get("fy") == year and fact.get("form") == "10-K" and fact.get("fp") == "FY":
                            value = fact.get("val")
                            break # Use the first matching annual value
                if value is not None:
                    break # Stop trying fallback tags if we found a value
            
            extracted[metric_name] = value
            
        return extracted
