import pytest
from unittest.mock import patch, MagicMock
from app.services.rag_chain import SecureRAGChain
from app.core.prompts import RAG_SYSTEM_PROMPT_DEFAULT

@patch('app.services.rag_chain.RAGService')
@patch('app.services.rag_chain.ChatGoogleGenerativeAI')
@patch.dict('os.environ', {'GEMINI_API_KEY': 'mock_key_for_testing'})
def test_secure_rag_chain_insufficient_data(mock_llm, mock_rag_service):
    # Setup mock RAG service to return NO chunks
    mock_rag_instance = mock_rag_service.return_value
    mock_rag_instance.retrieve_context.return_value = []
    
    chain = SecureRAGChain()
    
    result = chain.ask(query="What is the revenue?", user_role="VIEWER")
    
    # Verify we short-circuit
    assert result["answer"] == "Sorry, there is no data available"
    assert result["citations"] == []
    # Verify LLM was NOT called to save money
    assert not mock_llm.return_value.invoke.called

@patch('app.services.rag_chain.RAGService')
@patch('app.services.rag_chain.ChatGoogleGenerativeAI.invoke')
@patch.dict('os.environ', {'GEMINI_API_KEY': 'mock_key_for_testing'})
def test_secure_rag_chain_prompt_fencing(mock_invoke, mock_rag_service):
    # Setup mock RAG service to return some chunks
    mock_rag_instance = mock_rag_service.return_value
    mock_rag_instance.retrieve_context.return_value = [
        {"id": "c1", "text": "Apple made $100B in Q4."},
        {"id": "c2", "text": "Supply chain risks include silicon shortages."}
    ]
    
    mock_invoke.return_value = "Mocked Answer"
    
    chain = SecureRAGChain()
    result = chain.ask(query="What is the revenue?", user_role="VIEWER")
    
    # Verify citations are returned
    assert result["citations"] == ["c1", "c2"]
    
    # Verify the LLM was called
    assert mock_invoke.called
    
    # Extract the prompt passed to the LLM
    call_args = mock_invoke.call_args[0][0]
    # In LangChain, this is a PromptValue object. We can extract the string.
    system_message = call_args.messages[0].content
    assert "untrusted_data_" in system_message
    assert "Apple made $100B in Q4." in system_message
    assert "Supply chain risks include silicon shortages." in system_message
    assert "Sorry, there is no data available" in system_message # Instruction exists
