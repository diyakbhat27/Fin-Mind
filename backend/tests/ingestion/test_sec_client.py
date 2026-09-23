import pytest
import httpx
from unittest.mock import patch, MagicMock
from app.ingestion.sec_client import SECArchiveClient

@pytest.fixture
def sec_client():
    return SECArchiveClient()

@pytest.mark.asyncio
async def test_get_company_submissions_success(sec_client):
    mock_response = MagicMock()
    mock_response.json.return_value = {"cik": "0000320193", "name": "Apple Inc."}
    mock_response.raise_for_status.return_value = None

    with patch("httpx.AsyncClient.get", return_value=mock_response) as mock_get:
        result = await sec_client.get_company_submissions("320193")
        
        # Verify the CIK was padded correctly to 10 digits
        mock_get.assert_called_once_with("https://data.sec.gov/submissions/CIK0000320193.json", timeout=10.0)
        assert result["name"] == "Apple Inc."

@pytest.mark.asyncio
async def test_get_company_submissions_http_error(sec_client):
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError("404 Not Found", request=MagicMock(), response=mock_response)

    with patch("httpx.AsyncClient.get", return_value=mock_response):
        with pytest.raises(httpx.HTTPStatusError):
            await sec_client.get_company_submissions("invalid_cik")

@pytest.mark.asyncio
async def test_fetch_raw_filing_success(sec_client):
    mock_response = MagicMock()
    mock_response.text = "<html><body>Item 1A. Risk Factors...</body></html>"
    mock_response.raise_for_status.return_value = None

    with patch("httpx.AsyncClient.get", return_value=mock_response) as mock_get:
        # Pass a CIK, accession number with dashes, and document name
        result = await sec_client.fetch_raw_filing("0000320193", "0000320193-23-000106", "aapl-20230930.htm")
        
        # Verify dashes were removed from the accession number
        expected_url = "https://www.sec.gov/Archives/edgar/data/0000320193/000032019323000106/aapl-20230930.htm"
        mock_get.assert_called_once_with(expected_url, timeout=20.0)
        assert "Item 1A" in result
