import httpx
from typing import Optional

class SECArchiveClient:
    """
    Client for fetching raw SEC EDGAR submissions.
    Bypasses EFTS to guarantee access to raw SGML/HTML files.
    """
    BASE_URL = "https://data.sec.gov/submissions/"
    ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/"

    def __init__(self, user_agent: str = "FinMind AdminContact@finmind.local"):
        self.headers = {"User-Agent": user_agent}

    async def get_company_submissions(self, cik: str) -> dict:
        """
        Fetches the master JSON index of all submissions for a CIK.
        CIK should be 10 digits padded with leading zeros.
        """
        url = f"{self.BASE_URL}CIK{cik.zfill(10)}.json"
        async with httpx.AsyncClient(headers=self.headers, follow_redirects=True) as client:
            response = await client.get(url, timeout=10.0)
            response.raise_for_status()
            return response.json()

    async def fetch_raw_filing(self, cik: str, accession_number: str, primary_document: str) -> str:
        """
        Fetches the raw HTML/SGML filing from the SEC Archives.
        """
        # SEC archive paths remove dashes from the accession number
        accession_no_dashes = accession_number.replace("-", "")
        url = f"{self.ARCHIVE_URL}{cik}/{accession_no_dashes}/{primary_document}"
        
        async with httpx.AsyncClient(headers=self.headers, follow_redirects=True) as client:
            response = await client.get(url, timeout=20.0)
            response.raise_for_status()
            return response.text
