import pytest
from app.ingestion.parser import EdgarHTMLParser, TextChunker

def test_extract_item_1a():
    parser = EdgarHTMLParser()
    mock_html = """
    <html><body>
    <h1>Some Intro</h1>
    <p>ITEM 1A. RISK FACTORS</p>
    <p>These are the risk factors. The market is volatile.</p>
    <p>We could lose money.</p>
    <h2>ITEM 1B. UNRESOLVED STAFF COMMENTS</h2>
    <p>No comments.</p>
    </body></html>
    """
    
    extracted = parser.extract_item(mock_html, "Item 1A")
    assert "These are the risk factors" in extracted
    assert "We could lose money" in extracted
    assert "No comments" not in extracted
    assert "Some Intro" not in extracted

def test_chunker_fencing():
    chunker = TextChunker(chunk_size=50, chunk_overlap=0)
    text = "This is a very long string that should definitely be split into at least two or more chunks by the text splitter because its length exceeds fifty characters."
    
    metadata = {"company": "TEST"}
    chunks = chunker.chunk_and_fence(text, metadata)
    
    assert len(chunks) > 1
    
    for chunk in chunks:
        # Verify randomized XML fence exists
        fence_tag = chunk["metadata"]["fence_tag"]
        assert fence_tag.startswith("untrusted_data_")
        assert f"<{fence_tag}>" in chunk["text"]
        assert f"</{fence_tag}>" in chunk["text"]
        # Verify metadata injection
        assert chunk["metadata"]["company"] == "TEST"
        assert "chunk_index" in chunk["metadata"]
