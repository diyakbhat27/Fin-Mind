import asyncio
import argparse
from app.ingestion.sec_client import SECArchiveClient
from app.ingestion.parser import EdgarHTMLParser, TextChunker
from app.db.vector_store import ChromaDBManager

async def ingest_company_data(cik: str, ticker: str):
    print(f"[*] Starting ingestion for {ticker} (CIK: {cik})...")
    client = SECArchiveClient()
    parser = EdgarHTMLParser()
    chunker = TextChunker()
    vector_store = ChromaDBManager()
    
    try:
        submissions = await client.get_company_submissions(cik)
    except Exception as e:
        print(f"[!] Failed to fetch submissions for {ticker}: {e}")
        return

    recent_filings = submissions.get("filings", {}).get("recent", {})
    if not recent_filings:
        print(f"[!] No recent filings found for {ticker}.")
        return

    # Look for 10-K filings
    forms = recent_filings.get("form", [])
    accession_numbers = recent_filings.get("accessionNumber", [])
    primary_documents = recent_filings.get("primaryDocument", [])
    report_dates = recent_filings.get("reportDate", [])

    inserted_count = 0

    for i in range(len(forms)):
        if forms[i] == "10-K":
            acc_num = accession_numbers[i]
            doc_name = primary_documents[i]
            # Extract year from report date (YYYY-MM-DD)
            year = int(report_dates[i].split("-")[0])
            
            # We only care about FY2021 to FY2023 for the benchmark
            if year not in [2021, 2022, 2023]:
                continue
                
            print(f"  -> Fetching 10-K for {ticker} (FY{year})...")
            try:
                html_content = await client.fetch_raw_filing(cik, acc_num, doc_name)
                
                # Extract Item 1A and Item 7
                for item in ["Item 1A", "Item 7"]:
                    extracted_text = parser.extract_item(html_content, item)
                    if not extracted_text:
                        print(f"     [!] Could not extract {item} for {ticker} FY{year}")
                        continue
                        
                    # Base Metadata for ChromaDB
                    base_metadata = {
                        "company": ticker,
                        "cik": cik,
                        "year": year,
                        "section": item,
                        # Flattened roles for ChromaDB filtering
                        "role_SUPER_ADMIN": True,
                        "role_ANALYST": True,
                        "role_VIEWER": True # Public 10-Ks are accessible to VIEWERS
                    }
                    
                    chunks = chunker.chunk_and_fence(extracted_text, base_metadata)
                    if chunks:
                        vector_store.insert_chunks(chunks)
                        inserted_count += len(chunks)
                        print(f"     [+] Inserted {len(chunks)} chunks for {item}")
                        
            except Exception as e:
                print(f"  [!] Failed to process filing {acc_num}: {e}")

    print(f"[*] Completed {ticker}. Total chunks inserted: {inserted_count}\n")

async def main():
    parser = argparse.ArgumentParser(description="Fin Mind SEC Ingestion Pipeline")
    parser.add_argument("--benchmark", action="store_true", help="Ingest AAPL, MSFT, TSLA benchmark data")
    args = parser.parse_args()
    
    if args.benchmark:
        # Benchmark CIKs
        targets = [
            ("0000320193", "AAPL"),
            ("0000789019", "MSFT"),
            ("0001318605", "TSLA")
        ]
        for cik, ticker in targets:
            await ingest_company_data(cik, ticker)
    else:
        print("Run with --benchmark to ingest the standard dataset.")

if __name__ == "__main__":
    asyncio.run(main())
