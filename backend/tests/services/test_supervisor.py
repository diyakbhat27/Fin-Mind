import pytest
from unittest.mock import patch, MagicMock
from app.services.supervisor import supervisor_graph, Route, AgentState, RouteIntent
from app.services.compliance_agent import ComplianceDecision
from langgraph.graph import END

@patch('app.services.supervisor.PydanticOutputParser')
@patch('app.services.supervisor.ChatGoogleGenerativeAI')
@patch('app.services.supervisor.SecureRAGChain')
@patch.dict('os.environ', {'GEMINI_API_KEY': 'mock_key'})
def test_supervisor_routes_to_rag(mock_rag_chain, mock_llm, mock_parser):
    # Mock Gemini Flash to route to RAG
    mock_parser.return_value.invoke.return_value = RouteIntent(route=Route.RAG_AGENT)
    
    mock_rag_instance = mock_rag_chain.return_value
    mock_rag_instance.ask.return_value = {"answer": "Mock RAG Answer"}
        
    initial_state = {
        "query": "What are the risk factors?",
        "user_role": "VIEWER",
        "db_session": None,
        "next_node": None,
        "final_response": None
    }
        
    # Invoke the graph
    result = supervisor_graph.invoke(initial_state)
        
    # The router node should have executed and set next_node to rag_agent, executing SecureRAGChain
    assert mock_rag_instance.ask.called
    assert result["final_response"]["answer"] == "Mock RAG Answer"

@patch('app.services.supervisor.PydanticOutputParser')
@patch('app.services.supervisor.ChatGoogleGenerativeAI')
@patch('app.services.supervisor.QuantitativeAgent')
@patch.dict('os.environ', {'GEMINI_API_KEY': 'mock_key'})
def test_supervisor_rbac_edge_blocks_sql(mock_sql_agent, mock_llm, mock_parser):
    # Mock Gemini Flash to route to SQL
    mock_parser.return_value.invoke.return_value = RouteIntent(route=Route.SQL_AGENT)
    
    initial_state = {
        "query": "What is the leverage ratio?",
        "user_role": "VIEWER", # Viewer should NOT be allowed to access SQL
        "db_session": None,
        "next_node": None,
        "final_response": None
    }
    
    mock_sql_instance = mock_sql_agent.return_value
    result = supervisor_graph.invoke(initial_state)
        
    # SQL node should NOT have been called due to RBAC edge interception
    assert not mock_sql_instance.analyze.called
    assert "answer" in result["final_response"]
    assert "Sorry, there is no data available" in result["final_response"]["answer"]

@patch('app.services.supervisor.PydanticOutputParser')
@patch('app.services.supervisor.ChatGoogleGenerativeAI')
@patch('app.services.supervisor.QuantitativeAgent')
@patch.dict('os.environ', {'GEMINI_API_KEY': 'mock_key'})
def test_supervisor_rbac_edge_allows_sql(mock_sql_agent, mock_llm, mock_parser):
    # Mock Gemini Flash to route to SQL
    mock_parser.return_value.invoke.return_value = RouteIntent(route=Route.SQL_AGENT)
    
    initial_state = {
        "query": "What is the leverage ratio?",
        "user_role": "ANALYST", # Analyst IS allowed
        "db_session": MagicMock(),
        "next_node": None,
        "final_response": None
    }
    
    mock_sql_instance = mock_sql_agent.return_value
    mock_sql_instance.analyze.return_value = {"metric": "Leverage Ratio"}
    
    result = supervisor_graph.invoke(initial_state)
        
    # SQL node SHOULD have been called
    assert mock_sql_instance.analyze.called
    assert "error" not in result.get("final_response", {})

@patch('app.services.supervisor.PydanticOutputParser')
@patch('app.services.supervisor.ChatGoogleGenerativeAI')
def test_supervisor_rbac_compliance_denial(mock_llm, mock_parser):
    """
    Test that a VIEWER trying to access the compliance agent is denied by RBAC edge.
    """
    mock_parser.return_value.invoke.return_value = RouteIntent(route=Route.COMPLIANCE_AGENT)

    state = {
        "query": "Can we invest 100% in TSLA?",
        "user_role": "VIEWER",
        "db_session": None,
        "next_node": None,
        "final_response": None
    }
    
    result = supervisor_graph.invoke(state)
    assert "answer" in result["final_response"]
    assert "Sorry, there is no data available" in result["final_response"]["answer"]

@patch('app.services.compliance_agent.PydanticOutputParser')
@patch('app.services.compliance_agent.ChatGoogleGenerativeAI')
@patch('app.services.supervisor.PydanticOutputParser')
@patch('app.services.supervisor.ChatGoogleGenerativeAI')
def test_supervisor_compliance_approval(mock_sup_llm, mock_supervisor_parser, mock_comp_llm, mock_compliance_parser):
    """
    Test that an ANALYST can access the compliance agent and get a response.
    """
    # Mock routing
    mock_sup_llm.return_value.invoke.return_value = MagicMock(content='dummy')
    mock_supervisor_parser.return_value.invoke.return_value = RouteIntent(route=Route.COMPLIANCE_AGENT)
    
    # Mock compliance output
    mock_comp_runnable = mock_comp_llm.return_value.with_fallbacks.return_value
    mock_comp_runnable.invoke.return_value = MagicMock(content='dummy')
    mock_compliance_parser.return_value.invoke.return_value = ComplianceDecision(
        status="REJECTED",
        reasoning="Policy 1 violated."
    )

    state = {
        "query": "Can we invest 100% in TSLA?",
        "user_role": "ANALYST",
        "db_session": None,
        "next_node": None,
        "final_response": None
    }
    
    result = supervisor_graph.invoke(state)
    assert "COMPLIANCE REJECTED" in result["final_response"]["answer"]
    assert "Policy 1 violated" in result["final_response"]["answer"]

@patch('app.services.supervisor.SecureRAGChain')
@patch('app.services.supervisor.PydanticOutputParser')
@patch('app.services.supervisor.ChatGoogleGenerativeAI')
def test_supervisor_validator_pii_block(mock_llm, mock_supervisor_parser, mock_rag_chain):
    """
    Test that if an agent returns a raw SSN, the Validator node intercepts it.
    """
    mock_llm.return_value.invoke.return_value = MagicMock(content='dummy')
    mock_supervisor_parser.return_value.invoke.return_value = RouteIntent(route=Route.RAG_AGENT)
    
    # Mock RAG returning a bad SSN
    mock_rag_instance = mock_rag_chain.return_value
    mock_rag_instance.ask.return_value = {
        "answer": "The client's SSN is 123-45-6789.",
        "citations": []
    }
    
    state = {
        "query": "What is the SSN?",
        "user_role": "SUPER_ADMIN",
        "db_session": None,
        "next_node": None,
        "final_response": None
    }
    
    result = supervisor_graph.invoke(state)
    assert "error" in result["final_response"]
    assert "BLOCKED" in result["final_response"]["error"]
    assert "PII" in result["final_response"]["error"]
