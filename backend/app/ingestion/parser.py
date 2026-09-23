import re
import uuid
import secrets
from bs4 import BeautifulSoup
from langchain_text_splitters import RecursiveCharacterTextSplitter
from typing import List, Dict, Any

class EdgarHTMLParser:
    """
    Parses raw SEC HTML to extract specific Items (e.g., Item 1A, Item 7)
    using heuristics over the DOM structure.
    """
    
    @staticmethod
    def extract_item(html_content: str, item_name: str) -> str:
        """
        Attempts to extract a section (like 'Item 1A') from the raw HTML.
        This is a simplified heuristic parser for the benchmark.
        In a production system, this requires complex XBRL/DOM parsing.
        """
        soup = BeautifulSoup(html_content, "lxml")
        text = soup.get_text(separator="\n")
        
        # Extremely simplified heuristic: search for "ITEM 1A." and "ITEM 1B."
        # and capture everything between them.
        # This regex looks for the literal string "ITEM 1A" (case insensitive)
        pattern_start = re.escape(item_name)
        
        # We determine the "next" item to know where to stop
        next_item = ""
        if item_name.upper() == "ITEM 1A":
            next_item = "ITEM 1B"
        elif item_name.upper() == "ITEM 7":
            next_item = "ITEM 7A"
        else:
            return "" # Unsupported for this simplified parser

        pattern = re.compile(rf"{pattern_start}\.?(.*?){re.escape(next_item)}\.?", re.DOTALL | re.IGNORECASE)
        match = pattern.search(text)
        
        if match:
            # Return the captured group, stripped of massive whitespace blocks
            extracted = match.group(1).strip()
            # Clean up multiple newlines
            return re.sub(r'\n{3,}', '\n\n', extracted)
            
        return ""

    @staticmethod
    def extract_pdf_content(pdf_bytes: bytes, item_name: str) -> str:
        """
        Attempts to extract a section (like 'Item 1A') from a raw PDF.
        """
        import fitz  # PyMuPDF
        
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        text = ""
        for page in doc:
            text += page.get_text("text") + "\n"
            
        pattern_start = re.escape(item_name)
        next_item = ""
        if item_name.upper() == "ITEM 1A":
            next_item = "ITEM 1B"
        elif item_name.upper() == "ITEM 7":
            next_item = "ITEM 7A"
        else:
            return ""

        pattern = re.compile(rf"{pattern_start}\.?(.*?){re.escape(next_item)}\.?", re.DOTALL | re.IGNORECASE)
        match = pattern.search(text)
        
        if match:
            extracted = match.group(1).strip()
            return re.sub(r'\n{3,}', '\n\n', extracted)
            
        return ""

class TextChunker:
    """
    Splits text into chunks and wraps them in randomized XML fences
    to defend against prompt injection.
    """
    def __init__(self, chunk_size: int = 800, chunk_overlap: int = 100):
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ".", " ", ""]
        )

    def chunk_and_fence(self, text: str, base_metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Chunks the text, applies a randomized XML fence for security,
        and returns a list of dictionaries ready for ChromaDB.
        """
        raw_chunks = self.splitter.split_text(text)
        processed_chunks = []
        
        for i, chunk in enumerate(raw_chunks):
            # Generate a random 8-hex-character string for the fence
            random_fence = secrets.token_hex(4)
            fence_tag = f"untrusted_data_{random_fence}"
            
            fenced_text = f"<{fence_tag}>\n{chunk}\n</{fence_tag}>"
            
            chunk_metadata = base_metadata.copy()
            chunk_metadata["chunk_index"] = i
            chunk_metadata["fence_tag"] = fence_tag
            chunk_metadata["chunk_id"] = str(uuid.uuid4())
            
            processed_chunks.append({
                "id": chunk_metadata["chunk_id"],
                "text": fenced_text,
                "metadata": chunk_metadata
            })
            
        return processed_chunks
